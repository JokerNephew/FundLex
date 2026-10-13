"""Single-worker local queue runner. A separate process can call ``run_forever``."""

from __future__ import annotations

import json
import tempfile
import time
import threading
import os
import sqlite3
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable

from .store import Conflict, RunStore, sha256_file, engine_build, SCHEMA_VERSION, validate_delivery
from .config import local_data_dir


RETRYABLE_MODEL_CODES = {"MODEL_NETWORK_ERROR", "MODEL_RETRY_EXHAUSTED", "MODEL_CIRCUIT_OPEN",
                         "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED", "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_LEDGER_UNAVAILABLE", "MODEL_CHECKPOINT_UNAVAILABLE"}

Processor = Callable[[Path, Path, str], dict[str, Any]]


def _default_processor(input_path: Path, output_dir: Path, ruleset_version: str, *, checkpoint_dir: Path | None = None) -> dict[str, Any]:
    if ruleset_version == "v2":
        # v2 follows the rule package state: unreleased -> evaluation artifacts,
        # released -> formal delivery artifacts (gates are validated on load).
        from .v2_pipeline import process_v2
        return process_v2(input_path, output_dir, ruleset_version)
    from .pipeline import process
    return process(input_path, output_dir, ruleset_version, checkpoint_dir=checkpoint_dir)


class Worker:
    def __init__(self, store: RunStore, processor: Processor | None = None, *, lease_seconds: int = 900):
        self.store = store
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


    def _run_once(self) -> bool:
        min_free = int(os.environ.get("FUNDLEX_MIN_FREE_BYTES", str(256 * 1024 * 1024)))
        if shutil.disk_usage(self.store.root).free < min_free:
            raise OSError("local storage below configured free-space reserve")
        job = self.store.claim(lease_seconds=self.lease_seconds)
        if job is None:
            return False
        doc_id, token = job["id"], job["fencing_token"]
        with tempfile.TemporaryDirectory(prefix="fundlex_job_") as workspace:
            output_dir = Path(workspace) / "out"
            output_dir.mkdir()
            source = self.store.object_path(job["input_key"])
            try:
                if not source.is_file() or source.stat().st_size != job["source_size"] or sha256_file(source) != job["source_sha256"]:
                    raise ValueError("INPUT_INTEGRITY_FAILED")
                if job.get("ruleset_sha256"):
                    from .rules import RuleError, load_ruleset
                    from .rules_v2 import RuleV2Error, load_ruleset_v2
                    try:
                        current_ruleset_sha = load_ruleset(job["ruleset_version"]).sha256
                    except RuleError:
                        try:
                            current_ruleset_sha = load_ruleset_v2(job["ruleset_version"]).sha256
                        except RuleV2Error as exc:
                            raise ValueError("RULESET_NOT_FOUND") from exc
                    if current_ruleset_sha != job["ruleset_sha256"]:
                        raise ValueError("RULESET_HASH_MISMATCH")
                if job.get("engine_build") and (job["engine_build"] != engine_build() or job["schema_version"] != SCHEMA_VERSION):
                    raise ValueError("ENGINE_SCHEMA_MISMATCH")
                with self._lease_heartbeat(doc_id, token):
                    if self.processor is _default_processor:
                        report = self.processor(source, output_dir, job["ruleset_version"],
                            checkpoint_dir=self.store.root / "checkpoints" / doc_id)
                    else:
                        report = self.processor(source, output_dir, job["ruleset_version"])
                if isinstance(report, dict) and report.get("error_code") in RETRYABLE_MODEL_CODES:
                    self.store.retry(doc_id, token, error_code=report["error_code"])
                    return True
                if not isinstance(report, dict):
                    raise ValueError("INVALID_PIPELINE_REPORT")
                report["document_id"] = doc_id
                report["engine_build"] = job.get("engine_build", "")
                report["schema_version"] = job.get("schema_version", "")
                report.setdefault("source_sha256", job["source_sha256"])
                report.setdefault("ruleset_version", job["ruleset_version"])
                report.setdefault("ruleset_sha256", job.get("ruleset_sha256", ""))
                report.setdefault("delivery_status", "not_generated")
                qualification = report.get("qualification_status")
                if qualification is None and isinstance(report.get("qualification"), dict):
                    report["qualification_status"] = report["qualification"].get("status")
                paths = self._artifact_paths(report, output_dir)
                max_output_bytes = int(os.environ.get("FUNDLEX_MAX_RESULT_BYTES", str(100 * 1024 * 1024)))
                if sum(path.stat().st_size for path in paths.values()) > max_output_bytes:
                    raise ValueError("RESULT_SIZE_LIMIT")
                validate_delivery(report, paths)
                if report.get("execution_mode") == "evaluation":
                    paths.pop("final", None)
                    paths.pop("redline", None)
                    if isinstance(report.get("artifacts"), dict):
                        report["artifacts"].pop("final", None)
                        report["artifacts"].pop("redline", None)
                    if report.get("delivery_status") not in {"evaluation_modified", "evaluation_unmodified", "incomplete"}:
                        paths.pop("evaluation_final", None)
                        paths.pop("evaluation_redline", None)
                        if isinstance(report.get("artifacts"), dict):
                            report["artifacts"].pop("evaluation_final", None)
                            report["artifacts"].pop("evaluation_redline", None)
                elif report["delivery_status"] != "complete":
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
                else:
                    md = paths["report_md"]
                    md.write_text(md.read_text(encoding="utf-8") + "\n" + self._markdown(report), encoding="utf-8")
                self.store.finish(doc_id, token, report=report, artifacts=paths,
                                  failed=bool(report.get("qualification_status") == "failed" or report.get("error_code")),
                                  error_code=report.get("error_code"))
            except Conflict as exc:
                # An expired worker cannot publish over a newer attempt.
                if str(exc) in {"stale worker lease", "expired worker lease"}:
                    return True
                raise
            except Exception as exc:
                if isinstance(exc, (OSError, sqlite3.OperationalError)) or getattr(exc, "code", "") in RETRYABLE_MODEL_CODES:
                    self.store.retry(doc_id, token, error_code=getattr(exc, "code", "TEMPORARY_STORAGE_FAILURE"))
                    return True
                code = str(exc) if str(exc) in {"INPUT_INTEGRITY_FAILED", "RULESET_HASH_MISMATCH",
                                                  "INVALID_PIPELINE_REPORT", "ENGINE_SCHEMA_MISMATCH", "RESULT_SIZE_LIMIT",
                                                  "MISSING_VERIFIED_ARTIFACTS", "ARTIFACT_VERIFICATION_MISMATCH"} else "PROCESSING_FAILED"
                report = {
                    "document_id": doc_id, "source_sha256": job["source_sha256"],
                    "ruleset_version": job["ruleset_version"], "ruleset_sha256": job.get("ruleset_sha256", ""),
                    "engine_build": job.get("engine_build", ""), "schema_version": job.get("schema_version", ""),
                    "qualification_status": "failed",
                    "delivery_status": "not_generated", "error_code": code,
                    "errors": [{"code": code, "stage": "worker", "message": type(exc).__name__}],
                }
                md = output_dir / "report.md"
                md.write_text(self._markdown(report), encoding="utf-8")
                report_path = output_dir / "report.json"
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                self.store.finish(doc_id, token, report=report,
                                  artifacts={"report_json": report_path, "report_md": md},
                                  failed=True, error_code=code)
        return True

    @staticmethod
    def _artifact_paths(report: dict[str, Any], output_dir: Path) -> dict[str, Path]:
        values = report.get("artifacts", {})
        paths: dict[str, Path] = {}
        conventions = {"report_md": "report.md"}
        if report.get("execution_mode") == "evaluation":
            conventions.update({"evaluation_final": "evaluation_final.docx",
                                "evaluation_redline": "evaluation_redline.docx"})
        else:
            conventions.update({"final": "final.docx", "redline": "redline.docx"})
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

    def run_forever(self, *, poll_seconds: float = 1.0) -> None:
        while True:
            if not self.run_once():
                time.sleep(poll_seconds)


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
        worker.run_forever()


if __name__ == "__main__":
    main()
