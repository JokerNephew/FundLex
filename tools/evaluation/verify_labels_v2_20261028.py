#!/usr/bin/env python3
"""Verify v2 labels: target integrity + review-finding resolution completeness."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/evaluation/first_batch_label_20261028.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("first_batch_label_tool_verify_v2", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--selection", required=True)
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
    if [c["case_id"] for c in cases] != [c["case_id"] for c in selection["cases"]]:
        problems.append("case order/ids differ from selection")
    totals = {"targets": 0, "uncertain": 0, "findings": 0, "applied": 0, "finding_uncertain": 0, "rejected": 0}
    per_case = []
    for case in cases:
        cid = case["case_id"]
        contract = ROOT / case["relative"]
        if not contract.exists():
            problems.append(f"{cid}: contract missing")
            continue
        if hashlib.sha256(contract.read_bytes()).hexdigest() != case["sha256"]:
            problems.append(f"{cid}: source hash mismatch")
        doc = tool.build_doc_model(contract)
        targets = case.get("targets") or []
        if case.get("target_count") != len(targets):
            problems.append(f"{cid}: target_count={case.get('target_count')} != len(targets)={len(targets)}")
        totals["targets"] += len(targets)
        totals["uncertain"] += len(case.get("uncertain") or [])
        for t in targets:
            if t.get("rule_id") not in tool.RULE_IDS:
                problems.append(f"{cid}: invalid rule")
                continue
            idx = t.get("paragraph_index")
            if not isinstance(idx, int) or not (0 <= idx < len(doc.paragraphs)):
                problems.append(f"{cid}/{t.get('target_id')}: bad paragraph_index")
                continue
            para = doc.paragraphs[idx]
            if t.get("op") == "append":
                if not t.get("anchor_quote") or tool.find_span(para.text, t["anchor_quote"]) is None:
                    problems.append(f"{cid}/{t.get('target_id')}: append anchor not found")
            else:
                span = tool.find_span(para.text, t.get("old_text") or "")
                if span is None:
                    problems.append(f"{cid}/{t.get('target_id')}: old_text not found")
                else:
                    if tool.compact_offsets(para.text, *span) != (t.get("compact_start"), t.get("compact_end")):
                        problems.append(f"{cid}/{t.get('target_id')}: compact offsets mismatch")
        facts = case.get("facts") or {}
        if not isinstance(facts.get("classes"), list):
            problems.append(f"{cid}: facts.classes missing")
        findings = case.get("review_findings_total") or 0
        resolutions = case.get("review_resolutions") or []
        totals["findings"] += findings
        totals["applied"] += case.get("review_findings_applied") or 0
        totals["finding_uncertain"] += case.get("review_findings_uncertain") or 0
        totals["rejected"] += case.get("review_findings_rejected") or 0
        if len(resolutions) != findings:
            problems.append(f"{cid}: {len(resolutions)} resolutions for {findings} findings")
        if case.get("review_findings_uncertain") != sum(1 for r in resolutions if r.get("decision") == "uncertain"):
            problems.append(f"{cid}: uncertain counter mismatch")
        if case.get("protected") and targets:
            problems.append(f"{cid}: protected case has targets")
        per_case.append({
            "case_id": cid, "group": case.get("group"), "targets": len(targets),
            "target_count": case.get("target_count"), "findings": findings,
            "applied": case.get("review_findings_applied"),
            "uncertain_findings": case.get("review_findings_uncertain"),
            "rejected": case.get("review_findings_rejected"),
            "uncertain": len(case.get("uncertain") or []),
            "protected": bool(case.get("protected")),
        })
    protected = [c["case_id"] for c in cases if c.get("protected")]
    expected_protected = [c["case_id"] for c in cases if c.get("document", {}).get("protection", {}).get("protected")]
    if protected != expected_protected:
        problems.append(f"protected mismatch: {protected} vs {expected_protected}")
    summary = {
        "labels_path": str(labels_path),
        "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "cases": len(cases),
        "problems": problems,
        "totals": totals,
        "protected_cases": protected,
        "per_case": per_case,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.summary_out:
        Path(args.summary_out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
