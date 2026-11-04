"""Single-worker local queue runner. A separate process can call ``run_forever``."""

from __future__ import annotations

import json
import os
import tempfile
import time
import traceback
import threading
from concurrent.futures import ThreadPoolExecutor
import logging
import os
import sqlite3
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

from .store import (Conflict, RunStore, sha256_file, engine_build, SCHEMA_VERSION,
                    validate_delivery, is_recall_report, is_direct_report)
from .direct_pipeline import (ENGINE_ID as DIRECT_ENGINE_ID,
                              DirectPipelineError, process_direct_edit)
from .db import DatabaseError
from .config import local_data_dir


_logger = logging.getLogger(__name__)

RETRYABLE_MODEL_CODES = {"MODEL_NETWORK_ERROR", "MODEL_RETRY_EXHAUSTED", "MODEL_CIRCUIT_OPEN",
                         "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED", "MODEL_CALL_BUDGET_EXCEEDED",
                         "MODEL_LEDGER_UNAVAILABLE", "MODEL_CHECKPOINT_UNAVAILABLE",
                         "MODEL_REPLAY_MISS", "MODEL_CASSETTE_UNAVAILABLE",
                         "MODEL_CONCURRENCY_LIMIT", "MODEL_RESERVATION_EXPIRED"}

Processor = Callable[[Path, Path, str], dict[str, Any]]


def _json_dict(raw) -> dict:
    try:
        value = json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}

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
    # The runtime serves exactly one engine: the direct-through card pipeline.
    # The recall-first pipeline and the retired rulesets are no longer
    # reachable from the worker; their offline runners import the pipelines
    # directly and are exempt because they inject their own processor.
    raise ValueError("LEGACY_ENGINE_RETIRED")


class Worker:
    def __init__(self, store: RunStore, processor: Processor | None = None, *, lease_seconds: int = 900):
        self.store = store
        self._guide_lock = threading.Lock()
        # FL-D1127：域开关——专职指引解析进程=GUIDE=1/CONTRACTS=0；
        # 合同主力进程=GUIDE=0/CONTRACTS=1；默认全开保持单进程旧行为。
        self._guide_enabled = os.environ.get("FUNDLEX_WORKFLOW_GUIDE", "1") != "0"
        self._contracts_enabled = os.environ.get("FUNDLEX_WORKFLOW_CONTRACTS", "1") != "0"
        # FL-D1047：真实提速不降质——flock 只包 claim/finish/retry/reap 等
        # 秒级临界区，模型定位/改写/DOCX 写回（耗时主体）在锁外并行。
        self._critical = threading.Lock()
        self.processor = processor or _default_processor
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.lease_seconds = lease_seconds
        self._last_retention_sweep = 0.0

    def _prune_storage(self, now: float) -> None:
        """Periodic bounded-retention sweep (B13 F5 / FL-D557).

        Runs lazily inside the worker loop like ``_reap_stale_workspaces``:
        no extra systemd unit to deploy, the same policy covers the dev
        profile, and any failure is logged and contained — retention must
        never take the worker or a job down.
        """
        from . import retention
        if now - self._last_retention_sweep < retention.retention_interval_seconds():
            return
        self._last_retention_sweep = now
        try:
            stats = retention.prune_checkpoints(self.store.root, now=now)
        except Exception as exc:  # noqa: BLE001 - retention must be fail-closed
            _logger.warning("checkpoint retention sweep failed: %s", type(exc).__name__)
            return
        if stats["removed_files"] or stats["removed_dirs"]:
            _logger.info("checkpoint retention removed %d files (%d bytes) and %d dirs",
                         stats["removed_files"], stats["removed_bytes"], stats["removed_dirs"])

    @contextmanager
    def _worker_lock(self, *, blocking: bool = False):
        # OS lock is released on process death; the file itself is never the lock.
        # blocking=False keeps the historical mutual exclusion for whole-loop
        # callers; critical-section callers pass blocking=True.
        with (self.store.root / "worker.lock").open("a+b") as stream:
            stream.seek(0)
            if stream.read(1) == b"":
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK if not blocking else msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream, fcntl.LOCK_EX if blocking else fcntl.LOCK_EX | fcntl.LOCK_NB)
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

    @contextmanager
    def _critical_section(self):
        """Claim/finish/retry/reap 的租约与存储临界区（秒级）。

        跨进程互斥由 flock（worker.lock 文件），进程内由 ``_critical``；
        绝不跨区域持有：model 调用与 DOCX 处理一律在锁外。
        临界区一律**阻塞式**：窗口是秒级，两个进程/线程仅需按序用过——
        绝不把良性互斥竞争升级成 worker 崩溃（R4）。
        """
        with self._critical:
            with self._worker_lock(blocking=True):
                yield

    def run_once(self) -> bool:
        # FL-D1047：可并发调用——互斥只在临界区，模型与写回主体并行。
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
        with self._critical_section():
            # R2：stale workspace 重扫与存储清理只能在临界区内（含自锁语义），
            # 保留 retention fail-closed 语义不变。
            # FL-D1127：housekeeping 只由合同域进程执行，指引解析专职进程不重复做。
            if self._contracts_enabled:
                self._reap_stale_workspaces()
                self._prune_storage(time.time())
        # FL-D1127：指引解析与合同任务分进程互不阻塞；域开关默认全开=旧行为不变。
        if self._guide_enabled and self._run_guide_job():
            return True
        if not self._contracts_enabled:
            return False
        with self._critical_section():
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
                job_engine = str(job.get("engine_id") or "")
                if self.processor is _default_processor:
                    if job_engine == DIRECT_ENGINE_ID:
                        pass  # 直通卡包引擎，按绑定 schema 路由
                    elif job_engine == "recall_first":
                        # recall 引擎已退役。在途旧任务以真实码失败关闭，
                        # 历史报告只读；绝不作为新任务的旧引擎 fallback。
                        raise ValueError("LEGACY_ENGINE_RETIRED")
                    elif job.get("ruleset_sha256"):
                        raise ValueError("RULESET_RETIRED")
                    else:
                        raise ValueError("ENGINE_RETIRED")
                # FL-D1058（以集成树 c80007e 为准）：跨补丁引擎指纹漂移不得误杀
                # 卡包任务。直通版本不可变性由卡包（guide 版本+hash 快照）承担，
                # 非整包指纹；非卡包任务仍按整包指纹 on/off 防护。
                if job.get("engine_build") and job["engine_build"] != engine_build() \
                        and str(job.get("guide_schema_version") or "") != "guide_card_v1":
                    raise ValueError("ENGINE_SCHEMA_MISMATCH")
                if job.get("engine_build") and job["schema_version"] != SCHEMA_VERSION:
                    raise ValueError("ENGINE_SCHEMA_MISMATCH")
                # INT 用户级模型偏好（old-era 列）：直通引擎以任务创建时冻结的
                # snapshot_json 为唯一模型来源；preferences 仅作报告审计字段透传
                # （对齐集成树 c80007e 口径）。
                from . import model_settings
                preferences = model_settings.decode_snapshot(job.get("model_preferences") or "{}")
                effective_source, effective_sha = source, str(job["source_sha256"])
                # F1：租约心跳必须从转换第一步就包住——不然 >lease_seconds 的
                # 转换会被终杀并烧 attempt（FL 接管判不接受）。转换耗时主体
                # （300s×2）与模型改写共享同一条租约接续语义。
                with self._lease_heartbeat(doc_id, token):
                    if str(job.get("conversion_state") or "") in {"pending_convert", "convert_failed", "converted"}:
                        # 异步转换（用户裁决）：worker 第一步执行 doc_convert——
                        # 300s 上限+一次软件重试；终态如实出码；attempt 幂等不重复转换。
                        effective_source, effective_sha = self._converted_source(job)
                        source = effective_source
                    if self.processor is _default_processor:
                        with _document_trace(job, self.store):
                            card_document, guide_meta = self._bound_card_document(job)
                            snapshot = _json_dict(job.get("snapshot_json"))
                            report = process_direct_edit(
                                source, output_dir,
                                card_document=card_document, guide=guide_meta,
                                model_snapshot=snapshot.get("model") if isinstance(snapshot, dict) else {},
                                source_sha256=effective_sha,
                                document_id=doc_id,
                                mode=str(job.get("mode") or "delivery"))
                    else:
                        report = self.processor(source, output_dir, job["ruleset_version"])
                if isinstance(report, dict) and report.get("error_code") in RETRYABLE_MODEL_CODES:
                    with self._critical_section():
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
                    # FL-D1047：校验/摘要/对象拷贝在临界区外完成；
                    # 临界区只包 BEGIN IMMEDIATE 的原子 UPDATE/INSERT。
                    prepared = self.store.prepare_finish_artifacts(
                        doc_id, token, report=report, artifacts=paths)
                    with self._critical_section():
                        self.store.commit_finish(doc_id, token, report=report, prepared=prepared,
                                                 failed=bool(report.get("qualification_status") == "failed" or report.get("error_code")),
                                                 error_code=report.get("error_code"))
                except BaseException:
                    # finish commits its UPDATE and artifact rows atomically;
                    # on raise, this attempt's copied objects are unreferenced.
                    with self._critical_section():
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
                        with self._critical_section():
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
                        with self._critical_section():
                            self.store.retry(doc_id, token, error_code=getattr(exc, "code", "TEMPORARY_STORAGE_FAILURE"))
                    except Conflict as lease_exc:
                        if not self._is_takeover(lease_exc):
                            raise
                    return True
                # 真相先行：终端失败的 traceback 必须先打到 stderr（journalctl
                # 可见，绝不再出现只剩 PROCESSING_FAILED 的哑巴错误）。
                traceback.print_exc()
                # 含稳定 .code 的失败异常（DirectPipelineError/DocxError 等）
                # 一律以真实错误码结案；不再被 known_codes 名单抹平。
                exc_code = getattr(exc, "code", None)
                raw_code = str(exc_code) if isinstance(exc_code, str) and exc_code else str(exc)
                exc_get = exc_code
                known_codes = {"INPUT_INTEGRITY_FAILED", "RULESET_HASH_MISMATCH", "RULESET_RETIRED",
                               "INVALID_PIPELINE_REPORT", "ENGINE_SCHEMA_MISMATCH", "RESULT_SIZE_LIMIT",
                               "MISSING_VERIFIED_ARTIFACTS", "ARTIFACT_VERIFICATION_MISMATCH",
                               "GUIDE_VERSION_MISSING", "GUIDE_RULESET_HASH_MISMATCH",
                               "GUIDE_NOT_CERTIFIED", "LEGACY_ENGINE_RETIRED",
                               "ENGINE_RETIRED", "GUIDE_SCHEMA_UNSUPPORTED",
                               "GUIDE_CARD_DOCUMENT_INVALID"}
                stable_code = bool(raw_code and raw_code.upper() == raw_code
                                   and "_" in raw_code and " " not in raw_code
                                   and raw_code.isascii() and len(raw_code) < 80)
                code = ("GUIDE_OPERATION_REGISTRY_MISSING"
                        if raw_code.startswith("GUIDE_OPERATION_REGISTRY_MISSING")
                        else raw_code if stable_code else "PROCESSING_FAILED")
                # 病灶必须可检索：错误码是给机器的，诊断文字是给人的
                # （fl-D1058 口径续）。原文截断脱敏，不写回影响文档结构。
                detail = f"{type(exc).__name__}: {str(exc)[:160]}"
                report = {
                    "document_id": doc_id, "source_sha256": job["source_sha256"],
                    "ruleset_version": job["ruleset_version"], "ruleset_sha256": job.get("ruleset_sha256", ""),
                    "engine_build": job.get("engine_build", ""), "schema_version": job.get("schema_version", ""),
                    "qualification_status": "failed",
                    "delivery_status": "not_generated", "error_code": code,
                    "errors": [{"code": code, "stage": "worker", "message": detail}],
                    "unresolved": [{"code": code, "message": detail}],
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
                    prepared = self.store.prepare_finish_artifacts(
                        doc_id, token, report=report,
                        artifacts={"report_json": report_path, "report_md": md})
                    with self._critical_section():
                        self.store.commit_finish(doc_id, token, report=report, prepared=prepared,
                                                 failed=True, error_code=code)
                except BaseException as finish_exc:
                    with self._critical_section():
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
        with self._critical_section():
            job = guide_store.claim_guide_job(self.store, lease_seconds=max(self.lease_seconds, 600))
        if job is None:
            return False
        from .guide import GuideError, extract_guide_source
        from .guide_cards import build_guide_card_document
        from .model import ModelGateway
        try:
            path = guide_store.guide_source_path(self.store, job["guide_version_id"])
            if not path.is_file():
                raise GuideError("GUIDE_SOURCE_UNREADABLE", {"path": str(path)})
            source = extract_guide_source(path)
            # 直通解析入口（适配器语义已由第 1 线对齐）：模型处理在锁外，
            # 只有 lease/finish 在临界区（R4）。
            document = build_guide_card_document(source, ModelGateway.from_env())
        except Exception as exc:  # noqa: BLE001 - job errors must not kill the worker
            if self._is_guide_stop(exc):
                try:
                    with self._critical_section():
                        guide_store.release_guide_job(self.store, job["id"], job["fencing_token"])
                except Conflict as lease_exc:
                    if str(lease_exc) != "stale guide job lease":
                        raise
                return True
            traceback.print_exc()
            code = getattr(exc, "code", None) or "GUIDE_PARSE_FAILED"
            try:
                with self._critical_section():
                    guide_store.finish_guide_job(self.store, job["id"], job["fencing_token"],
                                                 error_code=str(code))
            except Conflict as lease_exc:
                if str(lease_exc) != "stale guide job lease":
                    raise
            return True
        try:
            with self._critical_section():
                finished = guide_store.finish_guide_job(self.store, job["id"],
                                                        job["fencing_token"], document=document)
        except Conflict as lease_exc:
            if str(lease_exc) != "stale guide job lease":
                raise
            return True
        if finished["version"]["status"] == "parsed":
            # Deterministic footprint smoke against the version's lineage
            # baseline: silent regressions the model verifier missed become an
            # advisory needs_review verdict.  The stamp must never kill a job.
            try:
                from .guide_smoke import review_version_footprint
                review_version_footprint(self.store, job["owner"], job["guide_version_id"])
            except Exception:  # noqa: BLE001 - advisory marking only
                pass
        return True

    def _bound_card_document(self, job: dict[str, Any]) -> tuple[dict, dict]:
        """Resolve and verify the frozen card-pack snapshot bound to a job.

        The task froze (version id, pack hash, schema) at creation; the worker
        re-checks all three against storage.  A version that disappeared, was
        rewritten, or still carries the legacy schema is a hard failure —
        never a silent fallback to the owner's current guide or legacy engine.
        """
        from . import guide_store
        version_id = job.get("guide_version_id") or ""
        try:
            version = guide_store.get_version(self.store, job.get("owner", ""), version_id)
        except KeyError:
            raise ValueError("GUIDE_VERSION_MISSING") from None
        if (version.get("rules_sha256") or "") != (job.get("guide_rules_sha256") or ""):
            raise ValueError("GUIDE_RULESET_HASH_MISMATCH")
        schema = str(version.get("schema_version") or "")
        if schema != guide_store.CARD_SCHEMA_VERSION:
            raise ValueError("GUIDE_SCHEMA_UNSUPPORTED")
        if str(job.get("guide_schema_version") or "") not in {"", guide_store.CARD_SCHEMA_VERSION}:
            raise ValueError("GUIDE_SCHEMA_UNSUPPORTED")
        try:
            document = guide_store.guide_document(self.store, version_id)
        except KeyError:
            raise ValueError("GUIDE_VERSION_MISSING") from None
        from .guide import GuideError
        from .guide_cards import validate_card_document
        try:
            brief = validate_card_document(document)
        except GuideError as exc:
            raise ValueError("GUIDE_CARD_DOCUMENT_INVALID") from exc
        if brief.get("state") != "OK" or int(brief.get("card_count") or 0) < 1:
            raise ValueError("GUIDE_CARD_DOCUMENT_INVALID")
        return document, {"version_id": version["id"], "schema_version": schema,
                          "document_sha256": version["document_sha256"],
                          "parser_version": version["parser_version"]}

    def _converted_source(self, job: dict[str, Any]) -> tuple[Path, str]:
        """Materialize the converted DOCX for a pending_convert document.

        Request-time sync conversion is forbidden by the product decision;
        conversion runs here in the worker identity.  A cached converted object
        (per document) makes every later attempt idempotent — no re-conversion.
        """
        doc_id, token = job["id"], job["fencing_token"]
        cached_key = str(job.get("converted_key") or "")
        if cached_key:
            cached = self.store.object_path(cached_key)
            cached_sha = str(job.get("converted_sha256") or "")
            if (cached.is_file() and cached_sha
                    and sha256_file(cached) == cached_sha):
                return cached, cached_sha
        from .doc_convert import DocConvertError, convert_doc_to_docx
        from .upload_validation import UploadValidationError, validate_docx_upload
        raw = self.store.object_path(job["input_key"])
        timeout_s = int(os.environ.get("FUNDLEX_DOC_CONVERT_TIMEOUT_S", "300"))
        converted: bytes | None = None
        last: DocConvertError | None = None
        for _ in range(2):  # 300s 上限 + 一次软件重试（工单②）
            try:
                converted = convert_doc_to_docx(raw.read_bytes(), timeout_s=timeout_s)
                break
            except DocConvertError as exc:
                last = exc
        if converted is None:
            self._mark_conversion_failed(doc_id, token)
            raise DirectPipelineError(getattr(last, "code", None) or "LEGACY_DOC_CONVERT_FAILED")
        try:
            validate_docx_upload("converted-target.docx", converted)
        except UploadValidationError as exc:
            self._mark_conversion_failed(doc_id, token)
            raise DirectPipelineError(str(exc.code)) from exc
        key = f"converted/{doc_id}.docx"
        target = self.store.object_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_key = target.parent / f"{target.name}.part-{token}"
        with temp_key.open("wb") as stream:
            stream.write(converted)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_key, target)
        digest = sha256_file(target)
        now = time.time()
        with self._critical_section(), self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE documents SET conversion_state='converted',
                converted_key=?,converted_sha256=?,converted_size=?,updated_at=?
                WHERE id=? AND fencing_token=? AND status IN ('leased','running')""",
                (key, digest, len(converted), now, doc_id, token)).rowcount
            if changed != 1:
                raise Conflict("stale worker lease")
        return target, digest

    def _mark_conversion_failed(self, document_id: str, token: int) -> None:
        """诚实终态：转换状态落库 convert_failed（用户可随后手动 retry）。"""
        with self._critical_section(), self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""UPDATE documents SET conversion_state='convert_failed',updated_at=?
                WHERE id=? AND fencing_token=? AND status IN ('leased','running')""",
                (time.time(), document_id, token))

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
        if is_direct_report(report):
            block = report.get("direct_edit") or {}
            lines = ["# FundLex 合同修改结果", "",
                     f"- 合同 ID：{report.get('document_id', '')}",
                     f"- 源文件 SHA-256：{report.get('source_sha256', '')}",
                     f"- 指引版本：{(report.get('guide') or {}).get('version_id', '')}",
                     f"- 引擎：{report.get('engine_id', '')} {report.get('engine_version', '')}",
                     f"- 交付完整性：{report.get('delivery_status', 'not_generated')}",
                     f"- 实际写回处数：{block.get('actual_written_count', 0)}", ""]
            for change in block.get("changes") or []:
                lines.append(f"## {change.get('rule_card_id', '')} · {change.get('location', '')}")
                lines.append("")
                lines.append(f"修改前：{str(change.get('before', '')).strip()}")
                lines.append("")
                lines.append(f"修改后：{str(change.get('after', '')).strip()}")
                lines.append("")
            if report.get("delivery_status") == "incomplete":
                lines.append("本次处理未产生任何可交付的实质修改，合同未交付。")
                lines.append("")
            return "\n".join(lines)
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

    def run_forever(self, *, poll_seconds: float = 1.0, concurrency: int = 3,
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
        # FL-D1047：槽位真并行；临界区由 claim/finish/retry 自包含，
        # 不再全程持 OS 锁（fencing token 下并发天然安全）。
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
    if os.environ.get("FUNDLEX_DOC_CONVERT_WARMUP", "1") != "0":
        # 异步转换预热（FL-D1074）：worker 身份进程启动先起一次 soffice，
        # 字体/模块缓存提前建立，首个 .doc 不再吃 120s 冷启动拒收。
        try:
            from .doc_convert import warm_up
            warm_up()
        except Exception:
            pass
    worker = Worker(store)
    if args.once:
        print(f"processed {worker.run_until_idle()} document(s)")
    else:
        worker.run_forever(concurrency=int(os.environ.get("FUNDLEX_WORKFLOW_CONCURRENCY", "3")))


if __name__ == "__main__":
    main()
