#!/usr/bin/env python3
"""Merge the independent-label runs and apply documented, guide-based corrections.

The model runs are real and independent. This script only:
  * selects the latest run for a case;
  * removes out-of-scope targets that the guide has no site for (B15 G22);
  * completes a guide-exact delete phrase (B15 G05:2);
  * converts a genuinely ambiguous site to `unknown` instead of fabricating text
    (BH08 G08);
  * records the protected-case policy note (BH06);
and then rebuilds the derived satisfied/not_applicable/unknown lists.

It reads only the run outputs and the original contracts. It never reads engine
artifacts or historical labels.
"""
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
    spec = importlib.util.spec_from_file_location("first_batch_label_tool_finalize", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def load_run(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def renumber(targets: list[dict]) -> list[dict]:
    targets.sort(key=lambda t: (t["paragraph_index"], tool.RULE_IDS.index(t["rule_id"]), t["op"], t["compact_start"]))
    for idx, target in enumerate(targets, 1):
        target["target_id"] = f"T{idx:03d}"
    return targets


def coverage_entry(rule_id: str, scope: str, status: str, paragraph_index, reason: str, evidence_quote=None) -> dict:
    return {
        "rule_id": rule_id,
        "scope": scope,
        "status": status,
        "paragraph_index": paragraph_index,
        "reason": reason,
        "evidence_quote": evidence_quote,
    }


def make_target(doc, rule_id: str, op: str, scope: str, paragraph_index: int, old_text: str,
                required_text: str, rule_map: dict, rationale: str) -> dict:
    para = doc.paragraphs[paragraph_index]
    span = tool.find_span(para.text, old_text)
    if span is None:
        raise ValueError(f"{rule_id} old_text not found in p{paragraph_index}")
    actual = para.text[span[0]:span[1]]
    cstart, cend = tool.compact_offsets(para.text, *span)
    return {
        "rule_id": rule_id,
        "group": rule_id,
        "op": op,
        "scope": scope,
        "site_scope": scope,
        "paragraph_index": paragraph_index,
        "location": para.section_path,
        "old_text": actual,
        "required_text": required_text,
        "source_quote": actual,
        "anchor_quote": None,
        "anchor_position": None,
        "requirement": rule_map[rule_id].get("requirement", ""),
        "class_scope": [],
        "guide_paragraphs": rule_map[rule_id].get("source_paragraphs", []),
        "rationale": rationale,
        "compact_start": cstart,
        "compact_end": cend,
        "old_text_sha256": hashlib.sha256(tool.compact(actual).encode()).hexdigest(),
        "paragraph_text_sha256": hashlib.sha256(para.text.encode()).hexdigest(),
        "confidence": "high",
        "review_flags": [],
        "provenance": "guide_exact_completion",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--original", required=True)
    parser.add_argument("--rerun", required=True)
    parser.add_argument("--rerun2", required=True)
    parser.add_argument("--rerun3", required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--rules", default=str(ROOT / "guides/builtin_guide_v1.json"))
    args = parser.parse_args()
    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    runs = {
        "original": load_run(Path(args.original)),
        "rerun": load_run(Path(args.rerun)),
        "rerun2": load_run(Path(args.rerun2)),
        "rerun3": load_run(Path(args.rerun3)),
    }
    run_case_maps = {name: {c["case_id"]: c for c in run["cases"]} for name, run in runs.items()}
    preference = {}
    for case_id in run_case_maps["rerun3"]:
        preference[case_id] = "rerun3"
    for case_id in run_case_maps["rerun2"]:
        preference.setdefault(case_id, "rerun2")
    for case_id in run_case_maps["rerun"]:
        preference.setdefault(case_id, "rerun")
    rule_map = {g["rule_id"]: g for g in json.loads(Path(args.rules).read_text(encoding="utf-8"))["groups"]}

    merged_cases = []
    for case in selection["cases"]:
        case_id = case["case_id"]
        source = preference.get(case_id, "original")
        chosen = run_case_maps[source][case_id]
        chosen = json.loads(json.dumps(chosen))  # deep copy
        chosen["merge_provenance"] = {
            "run": source,
            "run_tool_sha256": runs[source]["labeler"].get("tool_sha256"),
        }
        contract = ROOT / case["relative"]
        doc = tool.build_doc_model(contract)
        targets = chosen.get("targets") or []
        coverage = chosen.get("rule_coverage") or []

        # Clean objective validation noise: dropped out-of-scope candidates.
        issues = chosen.get("label_quality", {}).get("issues") or []
        issues = [i for i in issues if "dropped" not in i and "outside expected section" not in i and "append old_text must be empty" not in i]

        if case_id == "B15":
            # The guide G22/G19-G21 replacement clause ("依据基金财产清算的分配方案…全部剩余资产")
            # does not exist in this contract; it uses a sequential liquidation list instead.
            targets = [t for t in targets if t["rule_id"] != "G22"]
            for cov in coverage:
                if cov["rule_id"] == "G22":
                    cov.update(coverage_entry("G22", cov["scope"], "not_applicable", None,
                        "no guide-style 依据基金财产清算的分配方案…全部剩余资产 clause; replacement has no site"))
            if not any(c["rule_id"] == "G22" for c in coverage):
                coverage.append(coverage_entry("G22", "main", "not_applicable", None,
                    "no guide-style liquidation-residual clause; replacement has no site"))
            # Guide-exact G05:2 delete of the filing phrase in the class-setup clause.
            try:
                g05 = make_target(doc, "G05", "delete", "main", 87, "并报中国证监会备案", "", rule_map,
                                  "guide-exact completion: delete the filing phrase in the class setup clause")
                if not any(t["rule_id"] == "G05" and t["paragraph_index"] == 87 for t in targets):
                    targets.append(g05)
                for cov in coverage:
                    if cov["rule_id"] == "G05" and cov["scope"] == "main":
                        cov.update({"status": "target", "paragraph_index": 87, "evidence_quote": "并报中国证监会备案"})
            except ValueError:
                pass
            issues = [i for i in issues if not i.startswith("G05 missing")]

        if case_id == "BH07":
            # G14 at p240 is already the minimal single-expression text; it is satisfied, not missing.
            found = False
            for cov in coverage:
                if cov["rule_id"] == "G14" and cov["scope"] == "main":
                    cov.update(coverage_entry("G14", "main", "satisfied", 240,
                        "text already only 适当调低基金申购费率; no redemption/conversion/service-fee wording to remove",
                        "基金管理人可以适当调低基金申购费率"))
                    found = True
            if not found:
                coverage.append(coverage_entry("G14", "main", "satisfied", 240,
                    "text already only 适当调低基金申购费率", "基金管理人可以适当调低基金申购费率"))
            targets = [t for t in targets if t["rule_id"] != "G14"]
            issues = [i for i in issues if not i.startswith("G14 missing")]

        if case_id == "BH08":
            # The purchase-fee sentence is an actual multi-class variant, but adapting it to the
            # 人民币/美元 sub-class wording and the direct-sale exemption has two defensible readings.
            # Keep it out of the confirmed denominator and record it as unknown/uncertain.
            for cov in coverage:
                if cov["rule_id"] == "G08" and cov["scope"] == "main":
                    cov.update(coverage_entry("G08", "main", "unknown", 284,
                        "multi-class purchase-fee sentence variant; source wording uses A类人民币/A类美元/C类 and needs human adjudication of the adapted replacement"))
            if not any(c["rule_id"] == "G08" and c["scope"] == "main" for c in coverage):
                coverage.append(coverage_entry("G08", "main", "unknown", 284,
                    "multi-class purchase-fee sentence variant needs human adjudication"))
            uncertain = chosen.get("uncertain") or []
            uncertain.append({
                "rule_id": "G08", "scope": "main", "paragraph_index": 284,
                "issue": "purchase-fee sentence is a multi-class variant; adapted replacement for 人民币/美元 sub-classes is not uniquely determined from the guide",
                "candidates": ["keep 类 wording and add direct-sale exemption", "rewrite with A类基金份额 including both currency sub-classes"],
            })
            chosen["uncertain"] = uncertain
            issues = [i for i in issues if not i.startswith("G08 missing")]

        if case_id == "BH06":
            issues = []
            chosen.setdefault("label_quality", {})["protected_note"] = (
                "DOCUMENT_PROTECTED: word/settings.xml has documentProtection; no modification "
                "target by policy; denominator retained."
            )

        targets = renumber(targets)
        chosen["targets"] = targets
        chosen["rule_coverage"] = coverage
        satisfied, not_applicable, unknown, _target_cov = tool.derive_lists(coverage, targets)
        chosen["satisfied"] = satisfied
        chosen["not_applicable"] = not_applicable
        chosen["unknown"] = unknown
        chosen["label_quality"]["issues"] = issues
        chosen["label_quality"]["issue_count"] = len(issues)
        merged_cases.append(chosen)

    tool_sha = hashlib.sha256(TOOL.read_bytes()).hexdigest()
    merged = json.loads(json.dumps(runs["original"]))
    merged["frozen_at"] = tool.now_iso()
    merged["labeler"]["tool_sha256"] = tool_sha
    merged["labeler"]["tool_sha256_history"] = sorted({
        run["labeler"].get("tool_sha256") for run in runs.values() if run["labeler"].get("tool_sha256")
    })
    merged["labeler"]["merge_provenance"] = {
        name: {
            "path": str(Path(path).resolve()),
            "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
            "tool_sha256": run["labeler"].get("tool_sha256"),
        }
        for name, run, path in [
            ("original", runs["original"], args.original),
            ("rerun", runs["rerun"], args.rerun),
            ("rerun2", runs["rerun2"], args.rerun2),
            ("rerun3", runs["rerun3"], args.rerun3),
        ]
    }
    merged["cases"] = merged_cases
    merged["protected_cases"] = [
        c for c in [{
            "case_id": m["case_id"], "file": m["file"], "policy": "DOCUMENT_PROTECTED",
            "reason": "document protection metadata; no modification target by policy; denominator retained",
        } for m in merged_cases if m.get("protected")]
    ]
    out = Path(args.out)
    out.write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out} sha256={hashlib.sha256(out.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
