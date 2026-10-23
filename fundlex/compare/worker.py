"""Independent compare worker with lease/fencing and pair failure isolation."""
from __future__ import annotations
import logging
import sqlite3
import time
import threading
from ..db import DatabaseError
from ..docx import DocxError
from .store import CompareStore, Conflict
from .service import CompareService


logger = logging.getLogger(__name__)
_TRANSIENT_ERRORS = (OSError, DatabaseError, sqlite3.DatabaseError)


class CompareWorker:
    def __init__(self, store: CompareStore, processor=None, *, lease_seconds: int = 300,
                 max_attempts: int = 3):
        if lease_seconds <= 0 or max_attempts <= 0:
            raise ValueError("invalid worker policy")
        self.store, self.processor = store, processor or CompareService()
        self.lease_seconds, self.max_attempts = lease_seconds, max_attempts

    def run_once(self) -> bool:
        job = self.store.claim(lease_seconds=self.lease_seconds, max_attempts=self.max_attempts)
        if not job:
            return False
        pair_id, token = job["id"], job["fencing_token"]
        stop = threading.Event()
        heartbeat_error = []
        def beat():
            while not stop.wait(max(0.5, self.lease_seconds / 3)):
                try:
                    self.store.heartbeat(pair_id, token, lease_seconds=self.lease_seconds)
                except Exception as exc:
                    heartbeat_error.append(exc)
                    return
        try:
            self.store.heartbeat(pair_id, token, lease_seconds=self.lease_seconds)
            thread = threading.Thread(target=beat, daemon=True)
            thread.start()
            files = {f["side"]: f for f in self.store.pair_inputs(pair_id)}
            left, right = files["left"], files["right"]
            lp = self.store.store.object_path(left["object_key"])
            rp = self.store.store.object_path(right["object_key"])
            for entry, path in ((left, lp), (right, rp)):
                if (not path.is_file() or path.stat().st_size != entry["size"]):
                    raise ValueError("COMPARE_INPUT_INTEGRITY_FAILED")
                import hashlib
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != entry["source_sha256"]:
                    raise ValueError("COMPARE_INPUT_INTEGRITY_FAILED")
            result = self.processor.compare(lp, rp, left_filename=left["filename"], right_filename=right["filename"])
            if heartbeat_error:
                raise heartbeat_error[0]
            self.store.finish(pair_id, token, result)
        except _TRANSIENT_ERRORS as exc:
            # I/O/database failures are retryable, but only for the bounded
            # number of attempts carried by the fencing row.
            logger.warning("compare pair transient failure type=%s", type(exc).__name__)
            try:
                self.store.retry(pair_id, token, "COMPARE_TRANSIENT_FAILURE",
                                 max_attempts=self.max_attempts)
            except Conflict:
                pass
            except _TRANSIENT_ERRORS as retry_exc:
                logger.warning("compare pair retry persistence failure type=%s",
                               type(retry_exc).__name__)
        except Conflict as exc:
            # A stale lease must never be converted into a terminal result.
            logger.info("compare pair lease no longer current type=%s", type(exc).__name__)
        except Exception as exc:
            # A malformed pair cannot poison the batch. Preserve a structured
            # result, while never exposing arbitrary exception text.
            if isinstance(exc, DocxError):
                code = "COMPARE_PARSE_FAILED"
            elif isinstance(exc, ValueError) and str(exc) in {
                    "COMPARE_INPUT_INTEGRITY_FAILED", "COMPARE_RESULT_INVALID"}:
                code = str(exc)
            else:
                code = "COMPARE_PROCESSING_FAILED"
            try:
                self.store.finish(pair_id, token, {"schema_version": "contract-compare-v1", "error_code": code,
                                                  "summary": {"total": 0, "modify": 0, "insert": 0, "delete": 0},
                                                  "diffs": [], "coverage": {"status": "incomplete", "warnings": [code]}},
                                  failed=True, error_code=code)
            except Conflict:
                pass
            except _TRANSIENT_ERRORS as persist_exc:
                # Leave the fenced lease for expiry/reclaim if recording the
                # terminal failure itself hits an infrastructure outage.
                logger.warning("compare pair failure persistence unavailable type=%s",
                               type(persist_exc).__name__)
        finally:
            stop.set()
            if 'thread' in locals():
                thread.join(timeout=2)
        return True

    def run_forever(self, *, poll_seconds: float = 1.0, stop_event=None) -> None:
        while stop_event is None or not stop_event.is_set():
            try:
                processed = self.run_once()
            except _TRANSIENT_ERRORS as exc:
                # A temporary database outage must not terminate the daemon.
                # Keep the log type-only: no paths, SQL, document text, or keys.
                logger.warning("compare worker poll failure type=%s", type(exc).__name__)
                if stop_event is not None:
                    stop_event.wait(min(max(poll_seconds, 0.05), 5.0))
                else:
                    time.sleep(min(max(poll_seconds, 0.05), 5.0))
                continue
            if not processed:
                time.sleep(poll_seconds)


def main(argv=None) -> int:
    """Run the independent compare queue worker.

    Deployment may invoke ``python -m fundlex.compare.worker`` with
    ``FUNDLEX_DATA_DIR``/``FUNDLEX_DATABASE_URL`` exactly as the API process.
    """
    import argparse
    from ..config import local_data_dir
    from ..store import RunStore
    parser = argparse.ArgumentParser(description="FundLex contract compare worker")
    parser.add_argument("--once", action="store_true", help="process one pair and exit")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args(argv)
    store = CompareStore(RunStore(local_data_dir()))
    worker = CompareWorker(store)
    if args.once:
        return 0 if worker.run_once() else 1
    worker.run_forever(poll_seconds=max(0.05, args.poll_seconds))
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
