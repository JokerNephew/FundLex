#!/usr/bin/env python3
"""Verify second-batch (2026-10-31) v1 independent labels.

Checks:
* batch identity (schema id, batch id, selection sha256, case ids and order);
* every case's source sha256 re-hashed against the original DOCX;
* target integrity: rule id, op, scope, paragraph index, old_text / anchor
  spans, compact offsets, related-target references;
* rule_coverage consistency with targets (target entries present, no target
  without coverage);
* deterministic audit: audit_coverage + mandatory_checks re-run from the
  frozen facts, so a model typo that the producer silently kept is visible;
* DOCUMENT_PROTECTED cases carry no targets;
* label_quality issue inventory and review statistics.

Produces a summary JSON (verification report) usable as the frozen label
evidence companion.  Usage:

    .venv/bin/python tools/evaluation/verify_second_batch_labels_20261031.py \
        --labels <labels.json> --selection <selection.json> --summary-out <report.json>
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "tools/evaluation/first_batch_label_20261028.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("first_batch_label_tool_verify_second", TOOL)
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
    parser.add_argument("--expected-schema", default="fundlex-independent-labels-v1")
    args = parser.parse_args()
    labels_path = Path(args.labels)
    selection_path = Path(args.selection)
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    warnings: list[str] = []
    cases = labels.get("cases") or []
    if labels.get("schema") != args.expected_schema:
        problems.append(f"schema {labels.get('schema')!r} != {args.expected_schema!r}")
    if len(cases) != len(selection.get("cases") or []):
        problems.append(f"expected {len(selection.get('cases') or [])} cases, found {len(cases)}")
    sel_sha = hashlib.sha256(selection_path.read_bytes()).hexdigest()
    if labels.get("selection_sha256") != sel_sha:
        problems.append("selection sha256 mismatch")
    if [c["case_id"] for c in cases] != [c["case_id"] for c in selection.get("cases") or []]:
        problems.append("case order/ids differ from selection")

    totals = Counter()
    rule_target_totals = Counter()
    per_case: list[dict[str, object]] = []
    quality_issue_kinds = Counter()
    for case in cases:
        cid = case.get("case_id")
        contract = ROOT / (case.get("relative") or "")
        if not contract.exists():
            contract = Path(selection["source_root"]) / case["file"]
        if not contract.exists():
            problems.append(f"{cid}: contract missing")
            continue
        if hashlib.sha256(contract.read_bytes()).hexdigest() != case.get("sha256"):
            problems.append(f"{cid}: source hash mismatch")
        doc = tool.build_doc_model(contract)
        targets = case.get("targets") or []
        coverage = case.get("rule_coverage") or []
        fund = case.get("fund") or {}
        seen_ids = set()
        for t in targets:
            tid = t.get("target_id")
            if tid in seen_ids:
                problems.append(f"{cid}: duplicate target_id {tid}")
            seen_ids.add(tid)
            rid = t.get("rule_id")
            if rid not in tool.RULE_IDS:
                problems.append(f"{cid}/{tid}: invalid rule {rid!r}")
                continue
            rule_target_totals[rid] += 1
            if t.get("op") not in tool.ALLOWED_OPS[rid]:
                problems.append(f"{cid}/{tid}: invalid op {t.get('op')!r} for {rid}")
            idx = t.get("paragraph_index")
            if not isinstance(idx, int) or not (0 <= idx < len(doc.paragraphs)):
                problems.append(f"{cid}/{tid}: bad paragraph_index")
                continue
            para = doc.paragraphs[idx]
            if t.get("op") == "append":
                if not t.get("anchor_quote") or tool.find_span(para.text, t["anchor_quote"]) is None:
                    problems.append(f"{cid}/{tid}: append anchor not found in p{idx}")
                if not tool.compact(t.get("required_text")):
                    problems.append(f"{cid}/{tid}: append required_text empty")
                if (t.get("old_text") or ""):
                    problems.append(f"{cid}/{tid}: append old_text must be empty")
            else:
                span = tool.find_span(para.text, t.get("old_text") or "")
                if span is None:
                    problems.append(f"{cid}/{tid}: old_text not found in p{idx}")
                else:
                    if tool.compact_offsets(para.text, *span) != (t.get("compact_start"), t.get("compact_end")):
                        problems.append(f"{cid}/{tid}: compact offsets mismatch")
                    orig = para.text[span[0]:span[1]]
                    if tool.sha256_bytes(tool.compact(orig).encode("utf-8")) != t.get("old_text_sha256"):
                        problems.append(f"{cid}/{tid}: old_text_sha256 mismatch")
        for rel in [r for t in targets for r in (t.get("related_target_ids") or [])]:
            if rel not in seen_ids:
                warnings.append(f"{cid}: related_target_ids references unknown {rel}")
        cov_keys = {(c.get("rule_id"), c.get("scope")): c for c in coverage}
        for t in targets:
            key = (t.get("rule_id"), t.get("scope"))
            entry = cov_keys.get(key)
            if not entry or entry.get("status") != "target":
                problems.append(f"{cid}: coverage missing for target {key}")
        for c in coverage:
            if c.get("status") == "target" and not any(
                t.get("rule_id") == c.get("rule_id") and t.get("scope") == c.get("scope") for t in targets
            ):
                problems.append(f"{cid}: coverage says target but no target row: {(c.get('rule_id'), c.get('scope'))}")
        # deterministic re-audit from frozen facts
        audit = tool.audit_coverage(doc, coverage, targets)
        mandatory = tool.mandatory_checks(doc, fund, coverage, targets)
        cleared = set(((case.get("label_quality") or {}).get("adjudicated_cleared")) or [])
        warn_re = re.compile(r"(G\d+) [^p]*p(\d+)")
        for msg in audit + mandatory:
            tag = ""
            m = warn_re.search(str(msg))
            if m and f"{m.group(1)}:{m.group(2)}" in cleared:
                tag = "adjudicated "
            elif "G01 missing append target in 释义" in str(msg) and "G01:释义" in cleared:
                tag = "adjudicated "
            elif "G16 missing target" in str(msg) and any(k.startswith("G16:") for k in cleared):
                tag = "adjudicated "
            warnings.append(f"{cid}: {tag}audit: {msg}")
            if tag:
                totals.setdefault("adjudicated_warnings", 0)
                totals["adjudicated_warnings"] += 1
        lq = case.get("label_quality") or {}
        if lq.get("issue_count"):
            warnings.append(f"{cid}: label_quality issue_count={lq.get('issue_count')}")
            for item in (lq.get("issues") or [])[:8]:
                quality_issue_kinds[str(item).split(":")[0][:80]] += 1
        if case.get("protected") and targets:
            problems.append(f"{cid}: protected case has targets")
        if not targets and not case.get("protected") and not case.get("excluded"):
            satisfied = case.get("satisfied") or []
            not_app = case.get("not_applicable") or []
            if not satisfied and not not_app:
                warnings.append(f"{cid}: zero targets and no satisfied/not_applicable evidence")
        totals["targets"] += len(targets)
        totals["coverage_entries"] += len(coverage)
        totals["uncertain"] += len(case.get("uncertain") or [])
        totals["cases_with_targets"] += int(bool(targets))
        review = case.get("review") or {}
        totals[f"review_{review.get('status')}"] += 1
        usage = case.get("usage") or {}
        totals["model_calls"] += usage.get("calls") or 0
        totals["prompt_tokens"] += usage.get("prompt_tokens") or 0
        totals["completion_tokens"] += usage.get("completion_tokens") or 0
        per_case.append({
            "case_id": cid,
            "group": case.get("group"),
            "targets": len(targets),
            "satisfied": len(case.get("satisfied") or []),
            "not_applicable": len(case.get("not_applicable") or []),
            "unknown": len(case.get("unknown") or []),
            "uncertain": len(case.get("uncertain") or []),
            "label_quality_issues": (case.get("label_quality") or {}).get("issue_count"),
            "review_status": review.get("status"),
            "review_verdict": review.get("verdict"),
            "protected": bool(case.get("protected")),
        })
    summary = {
        "labels_path": str(labels_path),
        "labels_sha256": hashlib.sha256(labels_path.read_bytes()).hexdigest(),
        "selection_sha256": sel_sha,
        "cases": len(cases),
        "problems": problems,
        "warnings": warnings,
        "warning_count": len(warnings),
        "totals": dict(totals),
        "rule_target_totals": dict(rule_target_totals),
        "quality_issue_kinds": dict(quality_issue_kinds),
        "per_case": per_case,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if args.summary_out:
        Path(args.summary_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_out).write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
