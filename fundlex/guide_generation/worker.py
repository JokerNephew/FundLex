"""Persistent worker for regulation candidate guide runs.

This worker deliberately uses the ``gg_jobs`` lease/fencing tables and the
candidate pipeline.  It never enters the ordinary contract execution queue.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

from ..model import ModelError
from ..store import Conflict, RunStore
from .model_router import GuideModelRouter
from .pipeline import GuidePipeline, PipelineConfig
from .store import GuideGenerationStore


class GuideGenerationWorker:
    def __init__(self, store: RunStore, *, router_factory=GuideModelRouter.from_env,
                 lease_seconds: int = 1800):
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.store = store
        self.gg_store = GuideGenerationStore(store)
        self.router_factory = router_factory
        self.lease_seconds = lease_seconds

    def _heartbeat(self, job_id: str, token: int, stop: threading.Event, errors: list[BaseException]) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        while not stop.wait(interval):
            try:
                self.gg_store.heartbeat(job_id, token, lease_seconds=self.lease_seconds)
            except BaseException as exc:  # lease loss is handled by the owner
                errors.append(exc)
                return

    def run_once(self) -> bool:
        job = self.gg_store.claim(lease_seconds=self.lease_seconds)
        if job is None:
            return False
        job_id = job["id"]
        token = job["fencing_token"]
        run_id = job["run_id"]
        stop = threading.Event()
        heartbeat_errors: list[BaseException] = []
        thread = threading.Thread(target=self._heartbeat, args=(job_id, token, stop, heartbeat_errors), daemon=True)
        thread.start()
        try:
            run = self.gg_store.get_run(run_id)
            config = PipelineConfig.from_payload(run.get("config") or run.get("payload", {}).get("config") or {})
            # API and worker may have different service overrides. A persisted
            # config must never raise this worker's deployment spending caps.
            config.soft_max_calls = min(config.soft_max_calls, int(os.environ.get(
                "FUNDLEX_GUIDE_RUN_MAX_CALLS", "6000")))
            config.soft_max_cost = min(config.soft_max_cost, float(os.environ.get(
                "FUNDLEX_GUIDE_RUN_MAX_COST_USD", "12")))
            router = self.router_factory()
            try:
                result = GuidePipeline(self.gg_store, run_id, router, config).run()
            finally:
                close = getattr(router, "close", None)
                if close:
                    close()
            if heartbeat_errors:
                raise heartbeat_errors[0]
            result_status = result.get("status")
            if result_status not in {"complete", "complete_with_unresolved", "completed"}:
                raise ValueError("GUIDE_RESULT_NOT_COMPLETE")
            self.gg_store.finish_job(job_id, token, status="completed",
                                     run_status=result_status, run_stage="COMPLETED")
        except (ModelError,) as exc:
            code = getattr(exc, "code", "MODEL_ERROR")
            exhausted = job["attempts"] >= self.gg_store.max_attempts()
            try:
                self.gg_store.finish_job(job_id, token, status="failed" if exhausted else "retry_wait",
                                         error_code=code, run_status="failed" if exhausted else "paused",
                                         run_stage="FAILED" if exhausted else "PAUSED",
                                         run_payload={"blocked_reason": code})
            except Conflict:
                return True
        except Conflict:
            # A stale worker must never publish a result over a newer lease.
            return True
        except Exception as exc:  # noqa: BLE001 - persist the terminal stage failure
            code = getattr(exc, "code", None) or str(exc)[:160] or type(exc).__name__
            try:
                self.gg_store.finish_job(job_id, token, status="failed", error_code=code,
                                         run_status="failed", run_stage="FAILED",
                                         run_payload={"worker_error": type(exc).__name__})
            except Conflict:
                return True
        finally:
            stop.set()
            thread.join(timeout=5)
        return True

    def run_until_idle(self, *, limit: int | None = None) -> int:
        completed = 0
        while limit is None or completed < limit:
            if not self.run_once():
                break
            completed += 1
        return completed

    def run_forever(self, *, poll_seconds: float = 1.0, stop_event: threading.Event | None = None) -> None:
        stopped = stop_event or threading.Event()
        while not stopped.is_set():
            if not self.run_once():
                stopped.wait(max(0.05, poll_seconds))


def main() -> None:
    worker = GuideGenerationWorker(RunStore(os.environ.get("FUNDLEX_DATA_DIR", "")))
    worker.run_forever(poll_seconds=float(os.environ.get("FUNDLEX_GUIDE_POLL_SECONDS", "1")))


if __name__ == "__main__":
    main()
