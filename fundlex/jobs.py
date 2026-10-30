"""Single-worker local queue runner. A separate process can call ``run_forever``."""

from __future__ import annotations

import json
import tempfile
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import os
import sqlite3
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .store import (Conflict, RunStore, sha256_file, engine_build, SCHEMA_VERSION,
                    validate_delivery, is_recall_report)
from .db import DatabaseError
from .config import local_data_dir


RETRYABLE_MODEL_CODES = {"MODEL_NETWORK_ERROR", "MODEL_RETRY_EXHAUSTED", "MODEL_CIRCUIT_OPEN",
                         "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED", "MODEL_CALL_BUDGET_EXCEEDED",
                         "MODEL_LEDGER_UNAVAILABLE", "MODEL_CHECKPOINT_UNAVAILABLE",
                         "MODEL_REPLAY_MISS", "MODEL_CASSETTE_UNAVAILABLE",
                         "MODEL_CONCURRENCY_LIMIT", "MODEL_RESERVATION_EXPIRED"}

Processor = Callable[[Path, Path, str], dict[str, Any]]

# Name of the liveness marker written into every ``fundlex_job_*`` workspace.
_WORKSPACE_MARKER = "workspace.json"


def _pid_alive(pid: int) -> bool:
    """POSIX liveness probe.  Never use ``os.kill`` on Windows: any signal
    value there terminates the process, so non-POSIX platforms report alive
    and the caller must rely on its fencing-token check instead."""
    if pid <= 0 or os.name == "nt":
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return True  # inconclusive: stay conservative, treat as alive
    return True


def _disabled_rule_ids(raw: Any) -> list[str]:
    """A damaged snapshot must not silently enable rules the user disabled."""
    if raw is None or raw == "":
        return []
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        raise ValueError("GUIDE_RULE_SETTINGS_INVALID") from None
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip()
                                          for item in value):
        raise ValueError("GUIDE_RULE_SETTINGS_INVALID")
    return value


@contextmanager
def _document_trace(job: dict[str, Any], store: RunStore) -> Iterator[None]:
    """Open one Langfuse trace per document revision (no-op when tracing is off).

    Tracing is best-effort: a failure here must never block a revision, so any
    exception from the observability layer is contained by that layer itself.
    """
    from . import observability, trace_sink
    if not (observability.enabled() or trace_sink.enabled()):
        yield
        return
    document_id = job.get("id") or ""
    input_key = job.get("input_key") or ""
    metadata = {
        "document_id": document_id,
        "engine_id": job.get("engine_id", ""),
        "input_key": input_key,
        "source_sha256": job.get("source_sha256", ""),
        "guide_version_id": job.get("guide_version_id", ""),
        "owner": job.get("owner", ""),
    }
    name = f"recall-first:{input_key or document_id}"
    with trace_sink.trace_document(name=name, document_id=document_id,
                                   metadata=metadata,
                                   tags=["recall-first", job.get("engine_id", "")]):
        with observability.trace_document(name=name, document_id=document_id, metadata=metadata,
                                          tags=["recall-first", job.get("engine_id", "")]):
            yield
    observability.flush()


def _default_processor(input_path: Path, output_dir: Path, ruleset_version: str, *, engine_id: str = "",
                       guide_version_id: str = "", guide_document: dict[str, Any] | None = None,
                       checkpoint_dir: Path | None = None, gateway: Any = None,
                       mode: str = "delivery",
                       disabled_rule_ids: list[str] | None = None) -> dict[str, Any]:
    # The runtime serves exactly one engine: the guide-bound recall-first
    # pipeline. The retired rulesets are no longer reachable from the worker, so
    # an unbound or legacy job fails closed instead of silently running the old
    # ruleset-only path. Their offline runners import the pipelines directly.
    if engine_id != "recall_first":
        raise ValueError("ENGINE_RETIRED")
    # The recall-first engine consumes the bound guide snapshot, never a ruleset
    # file; an unbound call is a caller bug and fails inside the pipeline with
    # its own error report.
    from .recall_pipeline import process_recall_first
    return process_recall_first(input_path, output_dir, guide_document=guide_document, gateway=gateway,
                                checkpoint_dir=checkpoint_dir, execution_mode="delivery",
                                disabled_rule_ids=disabled_rule_ids)


class Worker:
    def __init__(self, store: RunStore, processor: Processor | None = None, *, lease_seconds: int = 900):
        self.store = store
        self._guide_lock = threading.Lock()
        self.processor = processor or _default_processor
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.lease_seconds = lease_seconds

    @contextmanager
    def _worker_lock(self):
        # OS lock is released on process death; the file itself is never the lock.
        with (self.store.root / "worker.lock").open("a+b") as stream:
            stream.seek(0)
            if stream.read(1) == b"":
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise Conflict("local profile permits only one worker") from exc
            try:
                yield
            finally:
                stream.seek(0)
                if os.name == "nt":
                    msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(stream, fcntl.LOCK_UN)

    @contextmanager
    def _lease_heartbeat(self, document_id, token):
        stopped = threading.Event()
        errors = []
        def renew():
            while not stopped.wait(max(0.05, self.lease_seconds / 3)):
                try:
                    self.store.heartbeat(document_id, token, lease_seconds=self.lease_seconds)
                except Exception as exc:
                    errors.append(exc)
                    break
        self.store.heartbeat(document_id, token, lease_seconds=self.lease_seconds)
        thread = threading.Thread(target=renew, daemon=True)
        thread.start()
        try:
            yield
            if errors:
                raise errors[0]
        finally:
            stopped.set()
            thread.join(timeout=35)

    def run_once(self) -> bool:
        with self._worker_lock():
            return self._run_once()

    @staticmethod
    def _is_takeover(exc: BaseException) -> bool:
        """True when the lease predicate rejected a write: a newer attempt owns
        the document now, so the stale worker simply stands down (fail-closed)."""
        return isinstance(exc, Conflict) and str(exc) in {"stale worker lease", "expired worker lease"}

    def _reap_attempt_objects(self, document_id: str, token: int) -> None:
        """Drop result objects copied by a ``finish`` that failed before commit.

        Object keys are namespaced per attempt (``results/<doc>/<token>/``), so
        once ``finish`` raised, everything under the prefix was copied by this
        attempt and is referenced by no database row: the terminal UPDATE and
        the artifact inserts commit or roll back together (B14-02)."""
        shutil.rmtree(self.store.object_path(f"results/{document_id}/{int(token)}"),
                      ignore_errors=True)

    def _mark_workspace(self, workspace: str, doc_id: str, token: int) -> None:
        try:
            (Path(workspace) / _WORKSPACE_MARKER).write_text(json.dumps({
                "document_id": doc_id, "fencing_token": int(token),
                "store_root": str(self.store.root.resolve()), "pid": os.getpid(),
            }), encoding="utf-8")
        except OSError:
            pass  # the marker only enables stale-workspace reaping

    def _reap_stale_workspaces(self) -> None:
        """Remove ``fundlex_job_*`` workspaces orphaned by a killed worker (B14-04).

        A workspace is only removed when its marker proves it belongs to this
        store root, its owning pid is dead, and the recorded attempt is no
        longer the live fencing epoch, so a live or foreign worker's directory
        is never touched.  Legacy marker-less directories are left to the OS.
        """
        try:
            candidates = list(Path(tempfile.gettempdir()).glob("fundlex_job_*"))
        except OSError:
            return
        for path in candidates:
            try:
                marker = json.loads((path / _WORKSPACE_MARKER).read_text(encoding="utf-8"))
                if marker.get("store_root") != str(self.store.root.resolve()):
                    continue
                pid = int(marker.get("pid") or 0)
                if _pid_alive(pid):
                    continue
                document_id = str(marker.get("document_id") or "")
                token = int(marker.get("fencing_token") or 0)
                if not document_id or not token:
                    continue
                with self.store._connect() as db:
                    row = db.execute("SELECT fencing_token,status FROM documents WHERE id=?",
                                     (document_id,)).fetchone()
                if (row is not None and int(row["fencing_token"]) == token
                        and row["status"] in ("leased", "running")):
                    continue  # the recorded attempt is still the live epoch
                shutil.rmtree(path, ignore_errors=True)
            except Exception:  # noqa: BLE001 - reaping is best-effort
                continue

    def _run_once(self) -> bool:
        min_free = int(os.environ.get("FUNDLEX_MIN_FREE_BYTES", str(256 * 1024 * 1024)))
        if shutil.disk_usage(self.store.root).free < min_free:
            raise OSError("local storage below configured free-space reserve")
        self._reap_stale_workspaces()
        if self._run_guide_job():
            return True
        job = self.store.claim(lease_seconds=self.lease_seconds)
        if job is None:
            return False
        doc_id, token = job["id"], job["fencing_token"]
        with tempfile.TemporaryDirectory(prefix="fundlex_job_", ignore_cleanup_errors=True) as workspace:
            self._mark_workspace(workspace, doc_id, token)
            output_dir = Path(workspace) / "out"
            output_dir.mkdir()
            source = self.store.object_path(job["input_key"])
            try:
                if not source.is_file() or source.stat().st_size != job["source_size"] or sha256_file(source) != job["source_sha256"]:
                    raise ValueError("INPUT_INTEGRITY_FAILED")
                if (self.processor is _default_processor and job.get("engine_id") != "recall_first"
                        and job.get("ruleset_sha256")):
                    # The runtime worker serves the guide-bound engine only. A
                    # legacy job that still names a retired ruleset fails closed
                    # rather than silently running against a different package.
                    # Offline runners inject their own processor and are exempt.
                    raise ValueError("RULESET_RETIRED")
                if job.get("engine_build") and (job["engine_build"] != engine_build() or job["schema_version"] != SCHEMA_VERSION):
                    raise ValueError("ENGINE_SCHEMA_MISMATCH")
                guide_document = self._bound_guide_document(job)
                from . import model_settings
                preferences = model_settings.decode_snapshot(job.get("model_preferences") or "{}")
                with self._lease_heartbeat(doc_id, token):
                    if self.processor is _default_processor:
                        gateway = (model_settings.gateway_for(preferences, store=self.store,
                                     owner=job.get("owner")) if preferences else None)
                        try:
                            with _document_trace(job, self.store):
                                report = self.processor(source, output_dir, job["ruleset_version"],
                                    engine_id=job.get("engine_id", ""), guide_version_id=job.get("guide_version_id", ""),
                                    guide_document=guide_document, checkpoint_dir=self.store.root / "checkpoints" / doc_id,
                                    mode=job.get("mode", "delivery"), gateway=gateway,
                                    disabled_rule_ids=_disabled_rule_ids(job.get("disabled_rule_ids")))
                        finally:
                            # Explicitly injected gateways are caller-owned in the
                            # pipeline API; this Worker created this one per job.
                            close = getattr(gateway, "close", None)
                            if callable(close):
                                try:
                                    close()
                                except Exception:  # noqa: BLE001 - cleanup must not mask job result
                                    pass
                    else:
                        report = self.processor(source, output_dir, job["ruleset_version"])
                if isinstance(report, dict) and report.get("error_code") in RETRYABLE_MODEL_CODES:
                    self.store.retry(doc_id, token, error_code=report["error_code"],
                                    report=report)
                    return True
                if not isinstance(report, dict):
                    raise ValueError("INVALID_PIPELINE_REPORT")
                if preferences:
                    report["model_preferences"] = preferences
                report["document_id"] = doc_id
                report["engine_build"] = job.get("engine_build", "")
                if is_recall_report(report):
                    # The recall report keeps its own schema 3; the worker schema
                    # stays in the batch row and is not allowed to overwrite it.
                    report.setdefault("schema_version", job.get("schema_version", ""))
                else:
                    report["schema_version"] = job.get("schema_version", "")
                report.setdefault("source_sha256", job["source_sha256"])
                report.setdefault("ruleset_version", job["ruleset_version"])
                report.setdefault("ruleset_sha256", job.get("ruleset_sha256", ""))
                report.setdefault("delivery_status", "not_generated")
                qualification = report.get("qualification_status")
                if qualification is None and isinstance(report.get("qualification"), dict):
                    report["qualification_status"] = report["qualification"].get("status")
                mode = str(job.get("mode") or "delivery")
                task_bound = bool(self.store.document_task_id(doc_id))
                if task_bound:
                    # The pipeline always writes delivery-named outputs; the
                    # persisted job mode is applied afterwards and cannot be
                    # changed by the report itself.
                    report["execution_mode"] = "delivery"
                paths = self._artifact_paths(report, output_dir)
                max_output_bytes = int(os.environ.get("FUNDLEX_MAX_RESULT_BYTES", str(100 * 1024 * 1024)))
                if sum(path.stat().st_size for path in paths.values()) > max_output_bytes:
                    raise ValueError("RESULT_SIZE_LIMIT")
                validate_delivery(report, paths)
                if mode == "evaluation" and task_bound:
                    # The recall pipeline always writes the validated pair under
                    # final/redline; evaluation exposes the same bytes under
                    # evaluation_* names and never as formal deliverables.
                    status = str(report.get("delivery_status") or "")
                    report["execution_mode"] = "evaluation"
                    if status in {"complete", "complete_with_exceptions"}:
                        plan = report.get("edit_plan") or {}
                        validation = report.get("output_validation") or {}
                        if status == "complete_with_exceptions":
                            evaluation_status = "evaluation_modified_with_exceptions"
                        elif validation.get("kind") == "recall_validated_unchanged" or plan.get("count") == 0:
                            evaluation_status = "evaluation_unmodified"
                        else:
                            evaluation_status = "evaluation_modified"
                        for old, new in (("final", "evaluation_final"), ("redline", "evaluation_redline")):
                            source = paths.pop(old, None)
                            if source is not None:
                                target = output_dir / f"{new}.docx"
                                source.replace(target)
                                paths[new] = target
                        report["delivery_status"] = evaluation_status
                    else:
                        # Incomplete/failed/excluded evaluation keeps only its
                        # report. Produced bytes must not become ordinary
                        # working_final/working_redline delivery files or enter
                        # manual revision selection.
                        for kind in ("final", "redline", "working_final", "working_redline",
                                     "evaluation_final", "evaluation_redline"):
                            paths.pop(kind, None)
                    if isinstance(report.get("artifacts"), dict):
                        for old in ("final", "redline", "working_final", "working_redline",
                                    "evaluation_final", "evaluation_redline"):
                            report["artifacts"].pop(old, None)
                elif mode == "evaluation":
                    # Legacy direct-batch runners keep their historical report
                    # mode when they explicitly ask for evaluation.
                    status = str(report.get("delivery_status") or "")
                    if report.get("execution_mode") == "evaluation" and status in {"complete", "complete_with_exceptions"}:
                        plan = report.get("edit_plan") or {}
                        validation = report.get("output_validation") or {}
                        if status == "complete_with_exceptions":
                            evaluation_status = "evaluation_modified_with_exceptions"
                        elif validation.get("kind") == "recall_validated_unchanged" or plan.get("count") == 0:
                            evaluation_status = "evaluation_unmodified"
                        else:
                            evaluation_status = "evaluation_modified"
                        for old, new in (("final", "evaluation_final"), ("redline", "evaluation_redline")):
                            source = paths.pop(old, None)
                            if source is not None:
                                target = output_dir / f"{new}.docx"
                                source.replace(target)
                                paths[new] = target
                        report["delivery_status"] = evaluation_status
                elif mode == "diagnosis" and task_bound:
                    # Diagnosis runs the full pipeline for evidence, but only the
                    # report is published; never expose the modified contracts.
                    for kind in ("final", "redline", "working_final", "working_redline",
                                 "evaluation_final", "evaluation_redline"):
                        paths.pop(kind, None)
                        if isinstance(report.get("artifacts"), dict):
                            report["artifacts"].pop(kind, None)
                    report["diagnosis_status"] = report.get("delivery_status")
                    report["execution_mode"] = "diagnosis"
                    report["delivery_status"] = "diagnosed"
                elif task_bound and report["delivery_status"] not in {"complete", "complete_with_exceptions"}:
                    paths.pop("final", None)
                    paths.pop("redline", None)
                    if isinstance(report.get("artifacts"), dict):
                        report["artifacts"].pop("final", None)
                        report["artifacts"].pop("redline", None)
                elif not task_bound and mode == "diagnosis":
                    # Historical direct batches never had a diagnosis mode.
                    pass
                elif not task_bound and report["delivery_status"] not in {"complete", "complete_with_exceptions"}:
                    paths.pop("final", None)
                    paths.pop("redline", None)
                    if isinstance(report.get("artifacts"), dict):
                        report["artifacts"].pop("final", None)
                        report["artifacts"].pop("redline", None)
                report_path = output_dir / "report.json"
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                paths["report_json"] = report_path
                if "report_md" not in paths:
                    md = output_dir / "report.md"
                    md.write_text(self._markdown(report), encoding="utf-8")
                    paths["report_md"] = md
                # A pipeline-written report.md already carries the per-change detail;
                # appending the worker header would only duplicate the stub.
                try:
                    self.store.finish(doc_id, token, report=report, artifacts=paths,
                                      failed=bool(report.get("qualification_status") == "failed" or report.get("error_code")),
                                      error_code=report.get("error_code"))
                except BaseException:
                    # finish commits its UPDATE and artifact rows atomically;
                    # on raise, this attempt's copied objects are unreferenced.
                    self._reap_attempt_objects(doc_id, token)
                    raise
            except Conflict as exc:
                # An expired worker cannot publish over a newer attempt.
                if self._is_takeover(exc):
                    return True
                raise
            except Exception as exc:
                if self._is_recall_stop(exc):
                    # Recoverable model/transport stop: retry under the normal
                    # lease policy (budget/circuit stops also pause the task) and
                    # leave the model budget ledger to the next attempt.
                    try:
                        self.store.retry(doc_id, token, error_code=exc.code,
                                        report=getattr(exc, "report", None))
                    except Conflict as lease_exc:
                        # A2-F4: the lease was taken over mid-processing; the
                        # newer epoch owns the retry decision (fail-closed).
                        if not self._is_takeover(lease_exc):
                            raise
                    return True
                if isinstance(exc, (OSError, sqlite3.OperationalError, DatabaseError)) or getattr(exc, "code", "") in RETRYABLE_MODEL_CODES:
                    try:
                        self.store.retry(doc_id, token, error_code=getattr(exc, "code", "TEMPORARY_STORAGE_FAILURE"))
                    except Conflict as lease_exc:
                        if not self._is_takeover(lease_exc):
                            raise
                    return True
                raw_code = str(exc)
                known_codes = {"INPUT_INTEGRITY_FAILED", "RULESET_HASH_MISMATCH", "RULESET_RETIRED",
                               "INVALID_PIPELINE_REPORT", "ENGINE_SCHEMA_MISMATCH", "RESULT_SIZE_LIMIT",
                               "MISSING_VERIFIED_ARTIFACTS", "ARTIFACT_VERIFICATION_MISMATCH",
                               "GUIDE_VERSION_MISSING", "GUIDE_RULESET_HASH_MISMATCH",
                               "GUIDE_NOT_CERTIFIED"}
                code = ("GUIDE_OPERATION_REGISTRY_MISSING"
                        if raw_code.startswith("GUIDE_OPERATION_REGISTRY_MISSING")
                        else raw_code if raw_code in known_codes else "PROCESSING_FAILED")
                report = {
                    "document_id": doc_id, "source_sha256": job["source_sha256"],
                    "ruleset_version": job["ruleset_version"], "ruleset_sha256": job.get("ruleset_sha256", ""),
                    "engine_build": job.get("engine_build", ""), "schema_version": job.get("schema_version", ""),
                    "qualification_status": "failed",
                    "delivery_status": "not_generated", "error_code": code,
                    "errors": [{"code": code, "stage": "worker", "message": type(exc).__name__}],
                }
                if self.store.document_task_id(doc_id):
                    # Even a failed terminal attempt carries the persisted job
                    # mode, never a fabricated delivery identity.
                    report["execution_mode"] = str(job.get("mode") or "delivery")
                md = output_dir / "report.md"
                md.write_text(self._markdown(report), encoding="utf-8")
                report_path = output_dir / "report.json"
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                try:
                    self.store.finish(doc_id, token, report=report,
                                      artifacts={"report_json": report_path, "report_md": md},
                                      failed=True, error_code=code)
                except BaseException as finish_exc:
                    self._reap_attempt_objects(doc_id, token)
                    # A2-F4: a newer attempt took over; its epoch owns the
                    # terminal state and this failure report must not land.
                    if not self._is_takeover(finish_exc):
                        raise
        return True

    def _run_guide_job(self) -> bool:
        if not self._guide_lock.acquire(blocking=False):
            return False
        try:
            return self._run_guide_job_locked()
        finally:
            self._guide_lock.release()

    def _run_guide_job_locked(self) -> bool:
        """Parse one queued guide version; ``False`` when no job is available.

        A model stop (config missing, circuit open, budget/ledger stop, transport
        stop) releases the lease without consuming the attempt so the next run
        can retry; every other error is recorded on the job and the version.
        """
        from . import guide_store
        job = guide_store.claim_guide_job(self.store, lease_seconds=max(self.lease_seconds, 600))
        if job is None:
            return False
        from .guide import GuideError, build_guide_document, extract_guide_source
        from .model import ModelGateway
        try:
            path = guide_store.guide_source_path(self.store, job["guide_version_id"])
            if not path.is_file():
                raise GuideError("GUIDE_SOURCE_UNREADABLE", {"path": str(path)})
            source = extract_guide_source(path)
            document = build_guide_document(source, ModelGateway.from_env())
        except Exception as exc:  # noqa: BLE001 - job errors must not kill the worker
            if self._is_guide_stop(exc):
                try:
                    guide_store.release_guide_job(self.store, job["id"], job["fencing_token"])
                except Conflict as lease_exc:
                    if str(lease_exc) != "stale guide job lease":
                        raise
                return True
            code = getattr(exc, "code", None) or "GUIDE_PARSE_FAILED"
            try:
                guide_store.finish_guide_job(self.store, job["id"], job["fencing_token"], error_code=str(code))
            except Conflict as lease_exc:
                if str(lease_exc) != "stale guide job lease":
                    raise
            return True
        try:
            guide_store.finish_guide_job(self.store, job["id"], job["fencing_token"], document=document)
        except Conflict as lease_exc:
            if str(lease_exc) != "stale guide job lease":
                raise
        return True

    def _bound_guide_document(self, job: dict[str, Any]) -> dict[str, Any] | None:
        """Resolve and verify the guide snapshot bound to a recall-first job.

        The batch records the version id and rules hash at task creation; a
        version that disappeared or changed since is a hard failure, never a
        silent fallback to a different guide.
        """
        if job.get("engine_id") != "recall_first":
            return None
        from . import guide_store
        version_id = job.get("guide_version_id") or ""
        try:
            version = guide_store.get_version(self.store, job.get("owner", ""), version_id)
        except KeyError:
            raise ValueError("GUIDE_VERSION_MISSING") from None
        if (version.get("rules_sha256") or "") != (job.get("guide_rules_sha256") or ""):
            raise ValueError("GUIDE_RULESET_HASH_MISMATCH")
        try:
            document = guide_store.guide_document(self.store, version_id)
            from .guide import validate_runtime_guide
            from .generation.registry import operation_registry_coverage_gaps
            gaps = operation_registry_coverage_gaps(document)
            if gaps:
                raise ValueError("GUIDE_OPERATION_REGISTRY_MISSING:" + ",".join(gaps))
            validate_runtime_guide(
                document, approved_source_sha256=version["source_sha256"],
                approved_document_sha256=job.get("guide_rules_sha256"))
            return document
        except KeyError:
            raise ValueError("GUIDE_VERSION_MISSING") from None

    @staticmethod
    def _is_recall_stop(exc: BaseException) -> bool:
        from .recall_pipeline import RecallPipelineStop
        return isinstance(exc, RecallPipelineStop)

    @staticmethod
    def _is_guide_stop(exc: BaseException) -> bool:
        from .recall_pipeline import STOP_CODES
        code = getattr(exc, "code", "")
        if not isinstance(code, str) or not code:
            return False
        if code.startswith("GUIDE_MODEL_FAILED:"):
            code = code.split(":", 1)[1]
        return code in STOP_CODES

    @staticmethod
    def _artifact_paths(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
        values = report.get("artifacts", {})
        paths: dict[str, Path] = {}
        # report_json is normally written by the worker after validation; an
        # already present report file is picked up like report_md.
        conventions = {"report_md": "report.md", "report_json": "report.json"}
        if report.get("execution_mode") == "evaluation":
            conventions.update({"evaluation_final": "evaluation_final.docx",
                                "evaluation_redline": "evaluation_redline.docx"})
        else:
            # Incomplete recall results keep their produced pair under the
            # working names; the worker never strips them for those reports.
            conventions.update({"final": "final.docx", "redline": "redline.docx",
                                "working_final": "working_final.docx",
                                "working_redline": "working_redline.docx"})
        for kind, conventional in conventions.items():
            raw = values.get(kind) if isinstance(values, dict) else None
            path = Path(raw) if raw else output_dir / conventional
            if not path.is_absolute():
                path = output_dir / path
            path = path.resolve()
            if not path.is_relative_to(output_dir.resolve()):
                raise ValueError("artifact outside attempt directory")
            if path.is_file():
                paths[kind] = path
        return paths

    @staticmethod
    def _markdown(report: dict[str, Any]) -> str:
        if report.get("plan") or report.get("guide"):
            # The pipeline report owns the user-facing per-change detail: rule,
            # requirement, before text, after text and proof state.
            from .recall_pipeline import _report_markdown
            return _report_markdown(report)
        lines = ["# FundLex 合同处理报告", "", f"- 合同 ID：{report.get('document_id', '')}",
                 f"- 源文件 SHA-256：{report.get('source_sha256', '')}",
                 f"- 规则版本：{report.get('ruleset_version', '')}",
                 f"- 规则 SHA-256：{report.get('ruleset_sha256', '')}",
                 f"- 引擎：{report.get('engine_build', '')}",
                 f"- Schema：{report.get('schema_version', '')}",
                 f"- 资格：{report.get('qualification_status', 'unknown')}",
                 f"- 交付完整性：{report.get('delivery_status', 'not_generated')}"]
        if report.get("error_code"):
            lines.append(f"- 错误代码：{report['error_code']}")
        return "\n".join(lines) + "\n"

    def run_until_idle(self, *, limit: int | None = None) -> int:
        completed = 0
        while limit is None or completed < limit:
            if not self.run_once():
                break
            completed += 1
        return completed

    def run_forever(self, *, poll_seconds: float = 1.0, concurrency: int = 2,
                    stop_event: threading.Event | None = None) -> None:
        if not 1 <= concurrency <= 8:
            raise ValueError("workflow concurrency must be between 1 and 8")
        # Keep one process owner; only its bounded execution slots bypass run_once's lock.
        from . import guide_store
        guide_store._ensure_tables(self.store)
        stopped = stop_event or threading.Event()
        try:
            transient_limit = max(1, int(os.environ.get("FUNDLEX_WORKER_DB_FAILURE_LIMIT", "6")))
        except ValueError:
            transient_limit = 6
        def consume():
            transient_failures = 0
            while not stopped.is_set():
                try:
                    progressed = self._run_once()
                except (sqlite3.OperationalError, DatabaseError):
                    # B14-01: a transient claim-time database fault must not
                    # kill the consume loop.  Back off bounded; only give up
                    # when the outage persists beyond the failure limit.
                    transient_failures += 1
                    if transient_failures >= transient_limit:
                        raise
                    stopped.wait(min(30.0, 0.5 * (2 ** (transient_failures - 1))))
                    continue
                transient_failures = 0
                if not progressed:
                    stopped.wait(poll_seconds)
        with self._worker_lock():
            with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="fundlex") as pool:
                futures = [pool.submit(consume) for _ in range(concurrency)]
                try:
                    while not stopped.wait(poll_seconds):
                        for future in futures:
                            if future.done():
                                future.result()
                                # A consumer may observe stop between the outer wait
                                # and this completion check. That is a clean shutdown.
                                if stopped.is_set():
                                    break
                                raise RuntimeError("workflow slot stopped unexpectedly")
                finally:
                    stopped.set()


def main() -> None:
    import argparse
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="drain currently available work then exit")
    args = parser.parse_args()
    store = RunStore(local_data_dir())
    worker = Worker(store)
    if args.once:
        print(f"processed {worker.run_until_idle()} document(s)")
    else:
        worker.run_forever(concurrency=int(os.environ.get("FUNDLEX_WORKFLOW_CONCURRENCY", "2")))


if __name__ == "__main__":
    main()
