"""Single-worker local queue runner. A separate process can call ``run_forever``."""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from .store import Conflict, RunStore, sha256_file


Processor = Callable[[Path, Path, str], dict[str, Any]]


def _default_processor(input_path: Path, output_dir: Path, ruleset_version: str) -> dict[str, Any]:
    from .pipeline import process
    return process(input_path, output_dir, ruleset_version)


class Worker:
    def __init__(self, store: RunStore, processor: Processor | None = None, *, lease_seconds: int = 900):
        self.store = store
        self.processor = processor or _default_processor
        self.lease_seconds = lease_seconds

    def run_once(self) -> bool:
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
                    from .rules import load_ruleset
                    if load_ruleset(job["ruleset_version"]).sha256 != job["ruleset_sha256"]:
                        raise ValueError("RULESET_HASH_MISMATCH")
                self.store.heartbeat(doc_id, token, lease_seconds=self.lease_seconds)
                report = self.processor(source, output_dir, job["ruleset_version"])
                if not isinstance(report, dict):
                    raise ValueError("INVALID_PIPELINE_REPORT")
                report.setdefault("document_id", doc_id)
                report.setdefault("source_sha256", job["source_sha256"])
                report.setdefault("ruleset_version", job["ruleset_version"])
                report.setdefault("ruleset_sha256", job.get("ruleset_sha256", ""))
                report.setdefault("delivery_status", "not_generated")
                qualification = report.get("qualification_status")
                if qualification is None and isinstance(report.get("qualification"), dict):
                    report["qualification_status"] = report["qualification"].get("status")
                paths = self._artifact_paths(report, output_dir)
                if report["delivery_status"] == "complete" and not {"final", "redline"}.issubset(paths):
                    raise ValueError("MISSING_VERIFIED_ARTIFACTS")
                if report["delivery_status"] != "complete":
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
                self.store.finish(doc_id, token, report=report, artifacts=paths,
                                  failed=bool(report.get("qualification_status") == "failed" or report.get("error_code")),
                                  error_code=report.get("error_code"))
            except Conflict:
                # An expired worker cannot publish over a newer attempt.
                raise
            except Exception as exc:
                code = str(exc) if str(exc) in {"INPUT_INTEGRITY_FAILED", "RULESET_HASH_MISMATCH",
                                                  "INVALID_PIPELINE_REPORT",
                                                  "MISSING_VERIFIED_ARTIFACTS"} else "PROCESSING_FAILED"
                report = {
                    "document_id": doc_id, "source_sha256": job["source_sha256"],
                    "ruleset_version": job["ruleset_version"], "ruleset_sha256": job.get("ruleset_sha256", ""),
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
        for kind, conventional in {"final": "final.docx", "redline": "redline.docx", "report_md": "report.md"}.items():
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
    store = RunStore(os.environ.get("FUNDLEX_DATA_DIR", "var/fundlex"))
    worker = Worker(store)
    if args.once:
        print(f"processed {worker.run_until_idle()} document(s)")
    else:
        worker.run_forever()


if __name__ == "__main__":
    main()
