"""Long-connection runtime for user-owned (other-tenant) Feishu apps.

The deployment bot keeps its own client.  Every onboarded app gets an additional
lark WebSocket client so messages sent to *that* bot reach the same FundLex
service, and replies/results are sent back through the app that received them.

The runtime is intentionally defensive: a broken user app must never stop the
deployment bot.  All failures are recorded in the onboarding table and logged by
stable code only (never credentials).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

from .client import FeishuConfigurationError, FeishuOpenApiClient
from .events import build_event_handler, parse_message_event

log = logging.getLogger(__name__)

RETRY_BASE_SECONDS = 15.0
RETRY_MAX_SECONDS = 300.0


class FeishuAppRuntime:
    def __init__(self, onboarding, service):
        self.onboarding = onboarding
        self.service = service
        self._apps: dict[str, dict[str, Any]] = {}
        self._retry_at: dict[str, float] = {}
        self._failures: dict[str, int] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ----------------------------------------------------
    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="fundlex-feishu-apps", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self, interval: float = 5.0) -> None:
        while not self._stop.wait(interval):
            try:
                self.sync_once()
            except Exception as exc:  # the loop must survive store/network errors
                log.warning("Feishu app runtime sync failed error=%s", type(exc).__name__)

    def sync_once(self) -> None:
        try:
            rows = self.onboarding.apps_for_runtime()
        except Exception as exc:
            log.warning("Feishu app registry unreadable error=%s", type(exc).__name__)
            return
        wanted = {row["app_id"]: row for row in rows}
        with self._lock:
            for app_id in wanted:
                entry = self._apps.get(app_id)
                if entry is None:
                    if time.monotonic() >= self._retry_at.get(app_id, 0.0):
                        self._start_app(app_id)
                elif entry["thread"] is not None and entry["thread"].is_alive():
                    # Keep the heartbeat fresh; tenant may only be known after
                    # the first event, which is exactly when routing starts.
                    self.onboarding.mark_runtime(app_id, True, tenant_key=entry["tenant_key"])
                else:
                    self._apps.pop(app_id, None)
                    self.onboarding.mark_runtime(app_id, False)
                    log.warning("Feishu user app connection stopped app=%s", app_id)
            for app_id in set(self._apps) - set(wanted):
                entry = self._apps.pop(app_id)
                entry["active"] = False
                self._close_socket(entry)
                self._retry_at.pop(app_id, None)
                self._failures.pop(app_id, None)
                self.onboarding.mark_runtime(app_id, False)
                log.info("Feishu user app removed app=%s", app_id)

    # -- connections --------------------------------------------------
    def _start_app(self, app_id: str) -> None:
        try:
            secret = self.onboarding.secret_for(app_id)
            client = FeishuOpenApiClient(app_id, secret)
        except FeishuConfigurationError as exc:
            log.warning("Feishu user app client unavailable app=%s code=%s", app_id, exc)
            self.onboarding.mark_runtime(app_id, False)
            self._schedule_retry(app_id)
            return
        except Exception as exc:
            log.warning("Feishu user app credentials unreadable app=%s error=%s",
                        app_id, type(exc).__name__)
            self.onboarding.mark_runtime(app_id, False)
            self._schedule_retry(app_id)
            return
        entry: dict[str, Any] = {"client": client, "tenant_key": "", "thread": None,
                                 "ws": None, "active": True}
        handler = build_event_handler(
            client, on_event=lambda data: self._seen(app_id, data))

        def run() -> None:
            try:
                import lark_oapi as lark
                ws = lark.ws.Client(app_id, secret, event_handler=handler, auto_reconnect=True)
                entry["ws"] = ws
                self._failures.pop(app_id, None)
                self._retry_at.pop(app_id, None)
                ws.start()  # blocks until the connection ends
            except Exception as exc:
                log.warning("Feishu user app connection failed app=%s error=%s",
                            app_id, type(exc).__name__)
            finally:
                self.onboarding.mark_runtime(app_id, False)
                if entry["active"]:
                    self._schedule_retry(app_id)

        thread = threading.Thread(target=run, name=f"fundlex-feishu-{app_id[-6:]}", daemon=True)
        entry["thread"] = thread
        self._apps[app_id] = entry
        thread.start()
        self.onboarding.mark_runtime(app_id, True)
        log.info("Feishu user app connection started app=%s", app_id)

    def _schedule_retry(self, app_id: str) -> None:
        failures = self._failures.get(app_id, 0) + 1
        self._failures[app_id] = failures
        delay = min(RETRY_MAX_SECONDS, RETRY_BASE_SECONDS * (2 ** (failures - 1)))
        self._retry_at[app_id] = time.monotonic() + delay

    @staticmethod
    def _close_socket(entry: dict[str, Any]) -> None:
        ws = entry.get("ws")
        disconnect = getattr(ws, "_disconnect", None)
        if callable(disconnect):
            try:
                disconnect()
            except Exception as exc:  # closing must never raise into the loop
                log.warning("Feishu user app socket close failed error=%s", type(exc).__name__)

    def _seen(self, app_id: str, data: Any) -> None:
        entry = self._apps.get(app_id)
        if entry is not None and not entry.get("active", True):
            return
        try:
            tenant = parse_message_event(data).tenant_key
        except Exception:
            tenant = ""
        if entry is not None and tenant:
            entry["tenant_key"] = tenant
        self.onboarding.record_event(app_id, tenant)

    # -- routing ------------------------------------------------------
    def client_for(self, tenant_key: str):
        if not tenant_key:
            return None
        with self._lock:
            for entry in self._apps.values():
                if entry["tenant_key"] == tenant_key:
                    return entry["client"]
        return None

    def connected_tenants(self) -> list[str]:
        with self._lock:
            return sorted({entry["tenant_key"] for entry in self._apps.values()
                           if entry["tenant_key"]})
