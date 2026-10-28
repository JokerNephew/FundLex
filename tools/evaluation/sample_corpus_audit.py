"""Read-only parser admission manifest for new real-contract samples (no model)."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from lxml import etree

from fundlex.docx import DocxError, inspect_docx
from fundlex.recall import g06_scope_locations
from tools.evaluation.sample_corpus import DEFAULT_SAMPLE_ROOT


def audit(source: Path) -> dict:
    rows = []
    for path in sorted(source.glob("*.docx")):
        if path.name.startswith("~$"):
            continue
        row = {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
               "bytes": path.stat().st_size}
        try:
            inspection = inspect_docx(path, full=True)
            row.update(status="parse_ok", paragraphs=len(inspection.paragraphs),
                       g06_scope_locations=sorted(g06_scope_locations(inspection)))
        except DocxError as exc:
            row.update(status="parse_rejected", error_code=exc.code)
        except Exception as exc:  # preserve the denominator even for an unexpected failure
            row.update(status="unexpected_error", error_type=type(exc).__name__)
        # Distinguish the engine's generic XML error from malformed XML/package
        # errors. Never repair originals or use a permissive parser for admission.
        try:
            with ZipFile(path) as package:
                data = package.read("word/document.xml")
                root = etree.fromstring(data, etree.XMLParser(resolve_entities=False, no_network=True))
                row["document_namespace"] = etree.QName(root).namespace
                row["document_xml_well_formed"] = True
        except (BadZipFile, KeyError, etree.XMLSyntaxError, OSError) as exc:
            row["document_xml_well_formed"] = False
            row["package_diagnostic"] = type(exc).__name__
        rows.append(row)
    return {"schema": "sample-corpus-admission-v1", "source": str(source.resolve()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "total": len(rows), "counts": dict(Counter(row["status"] for row in rows)),
            "scope": "parser admission only; no business gold or delivery qualification",
            "rows": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SAMPLE_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.source.is_dir():
        parser.error("source directory does not exist")
    result = audit(args.source)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"total": result["total"], "counts": result["counts"],
                      "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
