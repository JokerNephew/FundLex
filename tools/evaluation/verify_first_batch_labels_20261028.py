#!/usr/bin/env python3
"""Verify the independent first-batch labels against the frozen sources.

Reads only the labels file, the frozen selection and the original contracts.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/evaluation/first_batch_label_20261028.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("first_batch_label_tool_verify", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=str(ROOT / "var/recall-first-evaluation/first-batch-20261028/labels-first-batch-20261028.json"))
    parser.add_argument("--selection", default=str(ROOT / "docs/evidence/selection-first-batch-20261028.json"))
    parser.add_argument("--summary-out", default="")
    args = parser.parse_args()

    labels_path = Path(args.labels)
    selection_path = Path(args.selection)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    cases = labels.get("cases") or []
    if len(cases) != 28:
        problems.append(f"expected 28 cases, found {len(cases)}")
    if labels.get("selection_sha256") != hashlib.sha256(selection_path.read_bytes()).hexdigest():
        problems.append("selection hash mismatch")
    selected_ids = [c["case_id"] for c in selection["cases"]]
    case_ids = [c["case_id"] for c in cases]
    if case_ids != selected_ids:
        problems.append("case ids/order differ from selection")
    target_count = 0
    uncertain_count = 0
    protected: list[str] = []
    per_case: list[dict] = []
    for case in cases:
        case_id = case["case_id"]
        if case.get("protected"):
            protected.append(case_id)
        uncertain_count += len(case.get("uncertain") or [])
        name = case.get("relative") or case.get("file")
        contract = ROOT / name if name else None
        if contract is None or not contract.exists():
            problems.append(f"{case_id}: contract missing")
            continue
        if hashlib.sha256(contract.read_bytes()).hexdigest() != case["sha256"]:
            problems.append(f"{case_id}: source hash mismatch")
        doc = tool.build_doc_model(contract)
        coverage_keys = {(c["rule_id"], c["scope"]) for c in case.get("rule_coverage") or []}
        for rule in tool.RULE_IDS:
            if ("main", rule) not in {(s, r) for r, s in coverage_keys}:
                problems.append(f"{case_id}: missing main coverage {rule}")
        local_targets = list(case.get("targets") or [])
        target_count += len(local_targets)
        for target in local_targets:
            tid = target.get("target_id")
            rule = target.get("rule_id")
            if rule not in tool.RULE_IDS:
                problems.append(f"{case_id}/{tid}: invalid rule {rule}")
                continue
            if target.get("op") not in tool.ALLOWED_OPS[rule]:
                problems.append(f"{case_id}/{tid}: invalid op for {rule}")
            idx = target.get("paragraph_index")
            if not isinstance(idx, int) or not (0 <= idx < len(doc.paragraphs)):
                problems.append(f"{case_id}/{tid}: bad paragraph_index")
                continue
            para = doc.paragraphs[idx]
            if target.get("scope") == "summary" and not para.is_summary:
                problems.append(f"{case_id}/{tid}: summary scope on main paragraph")
            if target.get("scope") == "main" and para.is_summary:
                problems.append(f"{case_id}/{tid}: main scope on summary paragraph")
            if target.get("op") == "append":
                if not target.get("anchor_quote") or tool.find_span(para.text, target["anchor_quote"]) is None:
                    problems.append(f"{case_id}/{tid}: append anchor quote not found")
            else:
                old_text = target.get("old_text") or ""
                span = tool.find_span(para.text, old_text)
                if span is None:
                    problems.append(f"{case_id}/{tid}: old_text not found")
                else:
                    cstart, cend = tool.compact_offsets(para.text, *span)
                    if (cstart, cend) != (target.get("compact_start"), target.get("compact_end")):
                        problems.append(f"{case_id}/{tid}: compact offsets mismatch")
            expected_sha = target.get("old_text_sha256")
            if expected_sha and expected_sha != hashlib.sha256(tool.compact(target.get("old_text", "")).encode()).hexdigest():
                problems.append(f"{case_id}/{tid}: old_text hash mismatch")
        per_case.append({
            "case_id": case_id,
            "group": case.get("group"),
            "targets": len(local_targets),
            "satisfied": len(case.get("satisfied") or []),
            "not_applicable": len(case.get("not_applicable") or []),
            "unknown": len(case.get("unknown") or []),
            "uncertain": len(case.get("uncertain") or []),
            "issues": (case.get("label_quality") or {}).get("issue_count", 0),
            "review": (case.get("review") or {}).get("status"),
            "protected": bool(case.get("protected")),
        })
    text = labels_path.read_text(encoding="utf-8")
    for forbidden in ("report.json", "redline.docx", "final.docx", "engine report"):
        if forbidden in text:
            problems.append(f"labels contain engine-artifact reference: {forbidden}")
    summary = {
        "labels_path": str(labels_path),
        "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "cases": len(cases),
        "targets": target_count,
        "uncertain": uncertain_count,
        "protected_cases": protected,
        "problems": problems,
        "per_case": per_case,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.summary_out:
        Path(args.summary_out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
