"""Execution adapter for deterministic DOCX compare."""
from __future__ import annotations
import hashlib
import time
from pathlib import Path
from typing import Any

from . import parser, text_diff


class CompareService:
    def compare(self, left: Path, right: Path, *, left_filename: str = "", right_filename: str = "") -> dict[str, Any]:
        started = time.perf_counter()
        result = text_diff.compare_docx(left, right, left_filename=left_filename, right_filename=right_filename)
        payload = result.to_dict() if hasattr(result, "to_dict") else dict(result)
        payload.setdefault("schema_version", "contract-compare-v1")
        diagnostics = dict(payload.get("diagnostics") or {})
        diagnostics.setdefault("processing_ms", round((time.perf_counter() - started) * 1000, 2))
        payload["diagnostics"] = diagnostics
        return payload

    def compare_bytes(self, left_data: bytes, right_data: bytes, *, left_filename: str = "", right_filename: str = "") -> dict[str, Any]:
        import tempfile
        with tempfile.TemporaryDirectory(prefix="fundlex-compare-") as tmp:
            lp, rp = Path(tmp) / "left.docx", Path(tmp) / "right.docx"
            lp.write_bytes(left_data); rp.write_bytes(right_data)
            return self.compare(lp, rp, left_filename=left_filename, right_filename=right_filename)
