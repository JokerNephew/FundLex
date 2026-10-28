"""Retrospective blind benchmark scoring.

The benchmark is deliberately regulation-specific; the guide generation
pipeline never imports or reads this module or the gold file.  Scoring happens
only after a run has been exported, and reads the actual persisted guide items,
impact coverage and corpus clauses.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import ClauseUnit, compact_for_match
from .store import GuideGenerationStore


def _terms(value: str) -> set[str]:
    return {item for item in re.split(r"[\s,，;；、]+", value or "") if item}


def _contains_all(text: str, terms: Iterable[str]) -> bool:
    compact = compact_for_match(text)
    return all(compact_for_match(term) and compact_for_match(term) in compact for term in terms)


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    compact = compact_for_match(text)
    return any(compact_for_match(term) and compact_for_match(term) in compact for term in terms)


@dataclass
class BenchmarkResult:
    payload: dict[str, Any]
    output_path: Path


def score_run(store: GuideGenerationStore, run_id: str, gold_path: str | Path,
              *, data_root: str | Path | None = None) -> BenchmarkResult:
    gold = json.loads(Path(gold_path).read_text(encoding="utf-8"))
    run = store.get_run(run_id)
    requirements = store.get_requirements(run_id)
    impacts = store.get_impacts(run_id)
    items = store.get_guide_items(run_id)
    coverage = store.get_coverage(run_id)
    findings = store.get_findings(run_id)
    residual = store.get_residual_rounds(run_id)
    snapshot = store.get_snapshot(run["corpus_snapshot_id"]) if run.get("corpus_snapshot_id") else None
    versions = store.get_contract_versions(snapshot.contract_version_ids) if snapshot else []
    clauses: list[ClauseUnit] = []
    clauses_by_version: dict[str, list[ClauseUnit]] = {}
    for version in versions:
        values = store.get_clauses(version.contract_version_id)
        clauses_by_version[version.contract_version_id] = values
        clauses.extend(values)
    impact_by_clause: dict[str, list] = {}
    for impact in impacts:
        for clause_id in impact.clause_ids:
            impact_by_clause.setdefault(clause_id, []).append(impact)
    impact_coverage = {row.get("ref_id"): row for row in coverage if row.get("level") == "impact"}
    item_by_id = {item.guide_item_id: item for item in items}

    # -- requirement recall ---------------------------------------------------
    requirement_results = []
    requirement_matches: dict[str, str] = {}
    for definition in gold.get("critical_requirements") or []:
        matches = []
        for requirement in requirements:
            if requirement.adjudication_status == "unresolved_article":
                continue
            text = "\n".join([requirement.requirement, requirement.source_quote,
                              " ".join(requirement.conditions), " ".join(requirement.exceptions)])
            article_ok = not definition.get("article_hint") or definition["article_hint"] in (requirement.article or "")
            if not article_ok:
                continue
            if not _contains_all(text, definition.get("must_terms") or []):
                continue
            if definition.get("any_terms") and not _contains_any(text, definition["any_terms"]):
                continue
            matches.append(requirement)
        matched_ids = [item.requirement_id for item in matches]
        for requirement_id in matched_ids:
            requirement_matches.setdefault(requirement_id, definition["id"])
        requirement_results.append({
            "gold_id": definition["id"],
            "critical": bool(definition.get("critical", True)),
            "description": definition["description"],
            "matched": bool(matches),
            "matched_requirement_ids": matched_ids,
            "matched_requirement_count": len(matches),
        })
    critical_requirements = [item for item in requirement_results if item["critical"]]
    critical_requirement_recall = (
        sum(1 for item in critical_requirements if item["matched"]) / len(critical_requirements)
        if critical_requirements else 1.0)

    # -- known clause pattern recall -----------------------------------------
    pattern_results = []
    for definition in gold.get("clause_patterns") or []:
        matching_clauses = [
            clause for clause in clauses
            if _contains_all(clause.text, definition.get("must_terms") or [])
            and (not definition.get("any_terms") or _contains_any(clause.text, definition["any_terms"]))
        ]
        covered_clauses = []
        covered_by: list[dict[str, Any]] = []
        for clause in matching_clauses:
            linked = impact_by_clause.get(clause.clause_id, [])
            covered = False
            for impact in linked:
                row = impact_coverage.get(impact.impact_id) or {}
                if row.get("status") == "covered" and row.get("guide_item_ids"):
                    covered = True
                    covered_by.append({"clause_id": clause.clause_id, "impact_id": impact.impact_id,
                                       "guide_item_ids": row.get("guide_item_ids")})
                    break
            if not covered:
                # A guide item can explicitly cover the pattern even if the
                # historical clause was not retrieved as an impact.
                for item in items:
                    text = " ".join([item.instruction, item.new_text, item.title,
                                     " ".join(item.conditions), " ".join(item.exceptions)])
                    if _contains_any(text, definition.get("expected_action_terms") or []):
                        covered = True
                        covered_by.append({"clause_id": clause.clause_id,
                                           "guide_item_ids": [item.guide_item_id],
                                           "match": "guide_action_terms"})
                        break
            if covered:
                covered_clauses.append(clause.clause_id)
        pattern_results.append({
            "gold_id": definition["id"],
            "critical": bool(definition.get("critical", False)),
            "description": definition["description"],
            "matching_clause_count": len(matching_clauses),
            "covered_clause_count": len(covered_clauses),
            "covered_clause_ids": covered_clauses[:100],
            "covered_by": covered_by[:100],
            "present_in_corpus": bool(matching_clauses),
            "covered": bool(covered_clauses),
            "recall": (len(covered_clauses) / len(matching_clauses)) if matching_clauses else None,
        })
    applicable_patterns = [item for item in pattern_results if item["present_in_corpus"]]
    known_clause_pattern_recall = (
        sum(1 for item in applicable_patterns if item["covered"]) / len(applicable_patterns)
        if applicable_patterns else 1.0)
    critical_fn = [item for item in applicable_patterns if item["critical"] and not item["covered"]]

    # -- condition / exception and draft fidelity ----------------------------
    condition_results = []
    for definition in gold.get("critical_requirements") or []:
        expected = definition.get("guide_expected_terms") or []
        if not expected:
            continue
        matched_items = []
        for item in items:
            text = " ".join([item.instruction, item.new_text, item.title,
                             " ".join(item.conditions), " ".join(item.exceptions)])
            if _contains_all(text, expected):
                matched_items.append(item.guide_item_id)
        condition_results.append({
            "gold_id": definition["id"], "expected_terms": expected,
            "matched": bool(matched_items), "guide_item_ids": matched_items,
        })
    condition_coverage = (
        sum(1 for item in condition_results if item["matched"]) / len(condition_results)
        if condition_results else 1.0)
    fidelity_findings = [
        item for item in findings
        if item.get("severity") == "critical"
        and item.get("category") in {"regulation_fidelity", "draft_text_fidelity", "provenance"}
        and (item.get("source") != "guide_reviewer" or item.get("evidence_verified", True))
    ]

    # -- guide false positives / burden --------------------------------------
    guide_false_positives = []
    for item in items:
        mapped_gold = {requirement_matches[value] for value in item.requirement_ids
                       if value in requirement_matches}
        if mapped_gold:
            continue
        text = " ".join([item.title, item.instruction, item.new_text])
        gold_terms = [term for definition in (gold.get("critical_requirements") or [])
                      for term in definition.get("must_terms") or []]
        if not _contains_any(text, gold_terms):
            guide_false_positives.append(item.guide_item_id)
    false_positive_rate = len(guide_false_positives) / len(items) if items else 0.0

    # -- human guide comparison (revealed only after generation) -------------
    human_guide_path = Path(gold.get("human_guide_source") or "")
    human_guide = {"available": False}
    human_paragraphs: list[str] = []
    if human_guide_path.is_file():
        from ..guide import extract_guide_source
        source = extract_guide_source(human_guide_path)
        human_paragraphs = [paragraph.text for paragraph in source.paragraphs if paragraph.text.strip()]
        human_guide = {
            "available": True,
            "source_sha256": source.source_sha256,
            "paragraphs": len(human_paragraphs),
        }
    human_overlap = []
    for item in items:
        item_text = compact_for_match(" ".join([item.title, item.instruction, item.new_text,
                                                " ".join(item.old_text_patterns)]))
        best = 0.0
        best_text = ""
        for paragraph in human_paragraphs:
            candidate = compact_for_match(paragraph)
            if not candidate or not item_text:
                continue
            # Character 3-gram Jaccard is a conservative lexical overlap signal.
            def grams(text: str) -> set[str]:
                return {text[index:index + 3] for index in range(max(0, len(text) - 2))}
            left, right = grams(item_text), grams(candidate)
            if not left or not right:
                continue
            score = len(left & right) / len(left | right)
            if score > best:
                best, best_text = score, paragraph
        human_overlap.append({"guide_item_id": item.guide_item_id, "overlap": round(best, 4),
                              "human_paragraph": best_text[:300]})
    average_human_overlap = (
        sum(item["overlap"] for item in human_overlap) / len(human_overlap)
        if human_overlap else 0.0)

    residual_status = (run.get("payload") or {}).get("residual", {})
    payload = {
        "schema_version": "guide-generation-benchmark-result-1",
        "benchmark_id": gold.get("benchmark_id"),
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regulation_sha256": run.get("source_sha256"),
        "corpus_snapshot_id": run.get("corpus_snapshot_id"),
        "corpus": {"contracts": len(versions), "clauses": len(clauses)},
        "metrics": {
            "critical_requirement_recall": round(critical_requirement_recall, 4),
            "critical_guide_false_negative": len(critical_fn),
            "known_clause_pattern_recall": round(known_clause_pattern_recall, 4),
            "condition_term_coverage": round(condition_coverage, 4),
            "guide_false_positive_rate": round(false_positive_rate, 4),
            "critical_fidelity_findings": len(fidelity_findings),
            "guide_item_count": len(items),
            "manual_review_burden_items": len(items),
            "average_human_guide_overlap": round(average_human_overlap, 4),
            "residual_rounds": len(residual),
            "residual_status": residual_status.get("status"),
            "residual_saturated": residual_status.get("saturated"),
        },
        "requirement_results": requirement_results,
        "pattern_results": pattern_results,
        "condition_results": condition_results,
        "guide_false_positive_ids": guide_false_positives,
        "critical_fidelity_findings": fidelity_findings[:100],
        "human_guide": human_guide,
        "human_guide_overlap": human_overlap[:300],
        "residual_rounds": residual,
        "run_status": run.get("status"),
        "qualification_status": run.get("qualification_status"),
        "blind_input_policy": {
            "generation_inputs_allowed": gold.get("generation_inputs_allowed"),
            "generation_inputs_forbidden": gold.get("generation_inputs_forbidden"),
            "human_guide_revealed_after_generation": True,
        },
    }
    output_dir = Path(gold_path).resolve().parent / "results"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run_id}.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str),
                           encoding="utf-8")
    return BenchmarkResult(payload=payload, output_path=output_path)


def _pct(value: Any) -> str:
    try:
        return f"{float(value):.1%}"
    except (TypeError, ValueError):
        return "—"


def summary_text(result: BenchmarkResult) -> str:
    metrics = result.payload.get("metrics") or {}
    lines = [
        f"Benchmark: {result.payload.get('benchmark_id')}",
        f"Run: {result.payload.get('run_id')}",
        f"Critical requirement recall: {_pct(metrics.get('critical_requirement_recall'))}",
        f"Known clause pattern recall: {_pct(metrics.get('known_clause_pattern_recall'))}",
        f"Critical guide false negative: {metrics.get('critical_guide_false_negative')}",
        f"Condition term coverage: {_pct(metrics.get('condition_term_coverage'))}",
        f"Guide false positive rate: {_pct(metrics.get('guide_false_positive_rate'))}",
        f"Critical fidelity findings: {metrics.get('critical_fidelity_findings')}",
        f"Guide items / manual review burden: {metrics.get('guide_item_count')}",
        f"Average human-guide overlap: {_pct(metrics.get('average_human_guide_overlap'))}",
        f"Residual: {metrics.get('residual_status')} (saturated={metrics.get('residual_saturated')})",
        f"Result file: {result.output_path}",
    ]
    return "\n".join(lines)
