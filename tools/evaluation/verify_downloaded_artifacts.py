"""Reopen downloaded DOCX files and reconcile source, revisions and report.

This is a mechanical artifact check, not independent business approval. It never
calls a model and never treats planned edits as evidence of policy completeness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile
from tempfile import TemporaryDirectory

from lxml import etree

from fundlex.docx import inspect_docx

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _xml_texts(path: Path, *, accept: bool = True) -> dict[str, list[str]]:
    result = {}
    with ZipFile(path) as package:
        for name in sorted(package.namelist()):
            if not name.startswith("word/") or not name.endswith(".xml"):
                continue
            root = etree.fromstring(package.read(name), etree.XMLParser(
                resolve_entities=False, no_network=True))
            paragraphs = []
            for paragraph in root.xpath("//w:p", namespaces=NS):
                pieces = []
                for node in paragraph.xpath(".//w:t | .//w:delText", namespaces=NS):
                    if node.xpath("ancestor::w:del" if accept else "ancestor::w:ins", namespaces=NS):
                        continue
                    pieces.append(node.text or "")
                paragraphs.append("".join(pieces))
            if paragraphs:
                result[name] = paragraphs
    return result


def verify_case(case_dir: Path, source: Path) -> dict:
    report = json.loads((case_dir / "report.json").read_text(encoding="utf-8"))
    result = {"case_id": case_dir.name, "delivery_status": report.get("delivery_status"),
              "checks": {}, "changed_paragraphs": [], "plan_artifact_mismatches": []}
    checks = result["checks"]
    checks["source_hash"] = hashlib.sha256(source.read_bytes()).hexdigest() == report.get("source_sha256")
    paths = {}
    for kind in ("final", "redline"):
        paths[kind] = next((case_dir / name for name in (
            kind, kind + ".docx", "working_" + kind, "working_" + kind + ".docx")
            if (case_dir / name).is_file()), None)
        checks[kind + "_available"] = paths[kind] is not None
        if paths[kind]:
            digest = hashlib.sha256(paths[kind].read_bytes()).hexdigest()
            result[kind + "_sha256"] = digest
            checks[kind + "_hash"] = digest == (report.get("output_validation") or {}).get(kind + "_sha256")
    if all(paths.values()):
        checks["accepted_matches_final"] = _xml_texts(paths["redline"]) == _xml_texts(paths["final"])
        checks["rejected_matches_source"] = _xml_texts(paths["redline"], accept=False) == _xml_texts(source)
        with ZipFile(paths["final"]) as package:
            root = etree.fromstring(package.read("word/document.xml"))
            checks["final_no_revisions"] = not root.xpath("//w:ins | //w:del", namespaces=NS)
        with ZipFile(paths["redline"]) as package:
            root = etree.fromstring(package.read("word/document.xml"))
            result["revisions"] = {name: len(root.xpath("//w:" + name, namespaces=NS)) for name in ("ins", "del")}
        before = {p.location: p.text for p in inspect_docx(source, full=True).paragraphs}
        # Historical P6 downloads have no filename extension. Inspect a temporary
        # byte-identical DOCX without altering the retained download evidence.
        with TemporaryDirectory(prefix="fundlex-download-review-") as temporary:
            inspection_path = Path(temporary) / "final.docx"
            inspection_path.write_bytes(paths["final"].read_bytes())
            after = {p.location: p.text for p in inspect_docx(inspection_path, full=True).paragraphs}
        plan = (report.get("plan") or {}).get("edits") or []
        checks["paragraph_locations_preserved"] = set(before) == set(after)
        for location in sorted(set(before) | set(after)):
            old, new = before.get(location, ""), after.get(location, "")
            edits = [edit for edit in plan if edit.get("location") == location]
            expected = old
            for edit in sorted(edits, key=lambda item: (int(item["start"]), int(item["end"])), reverse=True):
                start, end = int(edit["start"]), int(edit["end"])
                expected = expected[:start] + str(edit.get("replacement") or "") + expected[end:]
            if new != expected:
                result["plan_artifact_mismatches"].append({"location": location, "expected": expected, "actual": new})
            if new != old:
                result["changed_paragraphs"].append({"location": location, "before": old, "after": new,
                                                      "rules": [edit.get("rule_id") for edit in edits]})
        checks["plan_matches_actual"] = not result["plan_artifact_mismatches"]
    result["mechanical_pass"] = all(checks.values())
    result["business_complete"] = "not assessed by this tool"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, default=Path("/home/opencode/data/funds_word"))
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    batch = json.loads((args.run / "batch.json").read_text(encoding="utf-8"))
    cases = {case["case_id"]: case for case in selection["cases"]}
    reviews = []
    for case_id in batch["cases"]:
        directory = args.run / case_id
        if not (directory / "report.json").exists():
            reviews.append({"case_id": case_id, "mechanical_pass": False, "reason": "no report/artifact"})
            continue
        review = verify_case(directory, args.data_root / cases[case_id]["file"])
        (directory / "artifact-review.json").write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        reviews.append({key: value for key, value in review.items() if key not in {"changed_paragraphs", "plan_artifact_mismatches"}})
    summary = {"cases": reviews, "passed": sum(bool(row["mechanical_pass"]) for row in reviews), "total": len(reviews)}
    (args.run / "artifact-reviews.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return int(summary["passed"] != summary["total"])


if __name__ == "__main__":
    raise SystemExit(main())
