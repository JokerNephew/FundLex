"""Persistent worker for regulation candidate guide runs.

This worker deliberately uses the ``gg_jobs`` lease/fencing tables and the
candidate pipeline.  It never enters the ordinary contract execution queue.

Every pipeline/run/artifact write happens inside :meth:`fencing`, so a worker
whose lease was taken over cannot overwrite the new epoch's run or files.
Model/infrastructure failures pause the run (or schedule a bounded transient
retry) instead of exporting an empty candidate.
"""
from __future__ import annotations

import os
import sqlite3
import threading
import time
from typing import Any

from ..db import DatabaseError
from ..model import ModelError
from ..store import Conflict, RunStore
from .model_router import GuideModelRouter
from .pipeline import GuidePipeline, PipelineConfig
from .store import GuideGenerationStore


# Transport/rate failures are recoverable with bounded backoff.  Authentication,
# configuration, balance and local budget-cap errors are not: they pause and
# require an owner resume, so a permanent provider failure cannot loop forever.
TRANSIENT_MODEL_CODES = frozenset({
    "MODEL_NETWORK_ERROR", "MODEL_HTTP_ERROR", "MODEL_RETRY_EXHAUSTED",
    "MODEL_CONCURRENCY_LIMIT", "MODEL_CIRCUIT_OPEN", "MODEL_LEDGER_UNAVAILABLE",
})
ENGINE_QUEUED_STATUSES = frozenset({"queued", "running", "failed"})


def _transient_attempt_limit() -> int:
    try:
        return max(1, int(os.environ.get("FUNDLEX_GUIDE_TRANSIENT_ATTEMPTS", "5")))
    except ValueError:
        return 5


def _retry_delay(attempts: int) -> float:
    try:
        base = max(1.0, float(os.environ.get("FUNDLEX_GUIDE_RETRY_BASE_SECONDS", "10")))
    except ValueError:
        base = 10.0
    return min(300.0, base * (2 ** max(0, attempts - 1)))


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

    def _pause_or_retry(self, run_id: str, job: dict[str, Any], code: str,
                        *, engine: bool = False) -> None:
        transient = code in TRANSIENT_MODEL_CODES
        attempts = int(job.get("attempts") or 1)
        if transient and attempts < _transient_attempt_limit():
            delay = _retry_delay(attempts)
            self.gg_store.update_run(
                run_id, status="retry_wait", stage="RETRY_WAIT", error_code=code,
                payload={**self.gg_store.get_run(run_id).get("payload", {}),
                         "blocked_reason": code, "retry_attempt": attempts,
                         "retry_next_at": time.time() + delay,
                         "retry_max_attempts": _transient_attempt_limit()})
            self.gg_store.finish_job(job["id"], job["fencing_token"], status="retry_wait",
                                     error_code=code, next_attempt_at=time.time() + delay)
            return
        self.gg_store.update_run(
            run_id, status="paused", stage="PAUSED", error_code=code,
            payload={**self.gg_store.get_run(run_id).get("payload", {}),
                     "blocked_reason": code, "paused_at": time.time(),
                     "pause_job_id": job["id"],
                     "pause_fencing_token": job["fencing_token"]})
        self.gg_store.finish_job(job["id"], job["fencing_token"], status="paused",
                                 error_code=code)

    def _run_engine_only(self, run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = payload.get("engine_request") or {}
        input_sha256 = str(request.get("input_sha256") or "")
        request_id = str(request.get("request_id") or "")
        run = self.gg_store.get_run(run_id)
        config = PipelineConfig.from_payload(run.get("config") or payload.get("config") or {})
        router = self.router_factory()
        try:
            pipeline = GuidePipeline(self.gg_store, run_id, router, config)
            current = pipeline.engine_input()
            if input_sha256 and input_sha256 != current["input_sha256"]:
                raise ValueError("ENGINE_INPUT_MISMATCH")
            return pipeline.run_engine_compatibility(request_id=request_id,
                                                     input_sha256=input_sha256)
        finally:
            close = getattr(router, "close", None)
            if close:
                close()

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
        engine_only = False
        try:
            with self.gg_store.fencing(job_id, token, run_id):
                run = self.gg_store.get_run(run_id)
                payload = run.get("payload") or {}
                engine_only = bool(payload.get("engine_requested")) and (
                    payload.get("engine_status") in ENGINE_QUEUED_STATUSES)
                if engine_only:
                    try:
                        self._run_engine_only(run_id, payload)
                    except Exception as exc:  # noqa: BLE001 - engine failure is isolated
                        code = getattr(exc, "code", None) or str(exc)[:160] or type(exc).__name__
                        self.gg_store.update_run(
                            run_id, engine_status="failed",
                            payload={**self.gg_store.get_run(run_id).get("payload", {}),
                                     "engine_status": "failed",
                                     "engine_requested": False,
                                     "engine_error_code": code,
                                     "engine_error": str(exc)[:500],
                                     "engine_failed_at": time.time()})
                        self.gg_store.finish_job(job_id, token, status="failed", error_code=code)
                        return True
                    self.gg_store.finish_job(job_id, token, status="completed")
                    return True
                config = PipelineConfig.from_payload(run.get("config") or payload.get("config") or {})
                router = self.router_factory()
                try:
                    result = GuidePipeline(self.gg_store, run_id, router, config).run()
                finally:
                    close = getattr(router, "close", None)
                    if close:
                        close()
                if heartbeat_errors:
                    raise heartbeat_errors[0]
                self.gg_store.update_run(run_id, status=result.get("status", "complete_with_unresolved"),
                                         stage="COMPLETED")
                self.gg_store.finish_job(job_id, token, status="completed")
        except ModelError as exc:
            code = getattr(exc, "code", "MODEL_ERROR")
            try:
                # The fencing ContextVar unwound with the pipeline block, so a
                # plain update_run here would bypass the lease guard (A2-F1).
                # Re-bind the fence: when a newer epoch owns the job the entry
                # check raises Conflict and no stale pause/retry state lands.
                with self.gg_store.fencing(job_id, token, run_id):
                    if engine_only:
                        self.gg_store.update_run(
                            run_id, engine_status="failed",
                            payload={**self.gg_store.get_run(run_id).get("payload", {}),
                                     "engine_status": "failed", "engine_requested": False,
                                     "engine_error_code": code,
                                     "engine_failed_at": time.time()})
                        self.gg_store.finish_job(job_id, token, status="failed", error_code=code)
                    else:
                        self._pause_or_retry(run_id, job, code)
            except Conflict:
                return True
        except Conflict:
            # A stale worker must never publish a result over a newer lease.
            return True
        except Exception as exc:  # noqa: BLE001 - persist the terminal stage failure
            code = getattr(exc, "code", None) or str(exc)[:160] or type(exc).__name__
            try:
                # Same re-bind as the model-error branch (A2-F1): terminal
                # failure state is only written by the live lease holder.
                with self.gg_store.fencing(job_id, token, run_id):
                    if engine_only:
                        self.gg_store.update_run(
                            run_id,
                            payload={**self.gg_store.get_run(run_id).get("payload", {}),
                                     "engine_status": "failed", "engine_requested": False,
                                     "engine_error_code": code,
                                     "engine_error": str(exc)[:500],
                                     "engine_failed_at": time.time()})
                        self.gg_store.finish_job(job_id, token, status="failed", error_code=code)
                    else:
                        self.gg_store.update_run(run_id, status="failed", stage="FAILED", error_code=code,
                                                 payload={"worker_error": type(exc).__name__})
                        self.gg_store.finish_job(job_id, token, status="failed", error_code=code)
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
        try:
            transient_limit = max(1, int(os.environ.get("FUNDLEX_GUIDE_DB_FAILURE_LIMIT", "6")))
        except ValueError:
            transient_limit = 6
        transient_failures = 0
        while not stopped.is_set():
            try:
                progressed = self.run_once()
            except (sqlite3.OperationalError, DatabaseError):
                # B14-01: absorb transient claim-time DB faults with bounded
                # backoff; a persistent outage still terminates the loop.
                transient_failures += 1
                if transient_failures >= transient_limit:
                    raise
                stopped.wait(min(30.0, 0.5 * (2 ** (transient_failures - 1))))
                continue
            transient_failures = 0
            if not progressed:
                stopped.wait(max(0.05, poll_seconds))


def main() -> None:
    worker = GuideGenerationWorker(RunStore(os.environ.get("FUNDLEX_DATA_DIR", "")))
    worker.run_forever(poll_seconds=float(os.environ.get("FUNDLEX_GUIDE_POLL_SECONDS", "1")))


if __name__ == "__main__":
    main()
