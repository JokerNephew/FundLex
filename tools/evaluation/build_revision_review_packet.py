"""Build source and actual-DOCX review evidence without assigning business scores.

Source candidates are deliberately broad lexical hints, not gold targets. Every
actual paragraph change is included, even outside those hints. The pipeline plan
and model judgments are not used to select or approve changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from fundlex.docx import inspect_docx


SOURCE_HINTS = re.compile(
    r"份额类别|[A-ZＡ-Ｚ]类.{0,8}份额|认购费|申购费|赎回费|销售服务费|"
    r"基金转换|转换业务|基金财产清算|剩余资产|剩余财产|浮动.{0,5}管理费")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def paragraphs(path: Path) -> dict[str, str]:
    return {span.location: span.text for span in inspect_docx(path, full=True).paragraphs}


def build_case(case: dict, source: Path, run: Path | None) -> dict:
    source_sha = digest(source)
    if source_sha != case["sha256"]:
        raise ValueError(f"SOURCE_HASH_MISMATCH:{case['case_id']}")
    before = paragraphs(source)
    locations = list(before)
    candidates = []
    for index, location in enumerate(locations):
        text = before[location]
        if SOURCE_HINTS.search(text):
            candidates.append({
                "location": location, "source": text,
                "previous": [{"location": loc, "text": before[loc]}
                             for loc in locations[max(0, index - 2):index]],
                "next": [{"location": loc, "text": before[loc]}
                         for loc in locations[index + 1:index + 3]],
            })
    packet = {
        "case_id": case["case_id"], "group": case["group"],
        "source_file": str(source), "source_sha256": source_sha,
        "source_paragraph_count": len(before),
        "source_candidates": candidates,
        "actual_artifact": None, "actual_changes": [],
        "business_review_status": "pending",
        "limitations": [
            "Lexical source candidates are not an independently confirmed target denominator.",
            "All actual paragraph changes are shown; unchanged required sites need human review.",
            "No engine plan, model self-assessment or fixed A/C assumption is used to approve edits.",
        ],
    }
    if run is None:
        return packet
    directory = run / case["case_id"]
    artifact = next((directory / name for name in (
        "final.docx", "final", "working_final.docx", "working_final")
        if (directory / name).is_file()), None)
    if artifact is None:
        packet["artifact_status"] = "unavailable"
        return packet
    # Historical downloads are extensionless. Leave them intact and inspect a
    # temporary byte-identical file with the DOCX extension.
    with TemporaryDirectory(prefix="fundlex-review-") as temporary:
        copy = Path(temporary) / "actual.docx"
        copy.write_bytes(artifact.read_bytes())
        after = paragraphs(copy)
    packet["actual_artifact"] = {
        "path": str(artifact), "sha256": digest(artifact),
        "kind": "working_final" if artifact.name.startswith("working_") else "final",
    }
    packet["paragraph_locations_preserved"] = set(before) == set(after)
    for location in dict.fromkeys([*before, *after]):
        if before.get(location) != after.get(location):
            packet["actual_changes"].append({
                "location": location, "before": before.get(location),
                "after": after.get(location), "review_status": "pending",
            })
    for candidate in candidates:
        candidate["actual"] = after.get(candidate["location"])
        candidate["changed"] = candidate["source"] != candidate["actual"]
    return packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--group", choices=("dev", "holdout"), required=True)
    parser.add_argument("--run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--data-root", type=Path,
                        default=Path("/home/opencode/data/funds_word"))
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    # Refuse overwrites so source-only and post-run evidence stay distinct.
    args.output.mkdir(parents=True, exist_ok=False)
    rows = []
    for case in selection["cases"]:
        if case["group"] != args.group:
            continue
        packet = build_case(case, args.data_root / case["file"], args.run)
        target = args.output / (case["case_id"] + ".json")
        target.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        rows.append({"case_id": case["case_id"], "packet": target.name,
                     "source_candidates": len(packet["source_candidates"]),
                     "actual_changes": len(packet["actual_changes"]),
                     "artifact": packet["actual_artifact"],
                     "business_review_status": "pending"})
    index = {"selection_sha256": digest(args.selection), "group": args.group,
             "mode": "source_and_actual" if args.run else "source_only",
             "cases": rows, "business_scores_assigned": False}
    (args.output / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"cases": len(rows), "mode": index["mode"],
                      "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
