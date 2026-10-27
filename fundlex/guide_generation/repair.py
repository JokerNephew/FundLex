"""One bounded repair pass for guide items with critical review findings."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from .models import (
    ClauseUnit,
    GuideItem,
    ImpactCandidate,
    PolicyRequirement,
    compact_for_match,
    stable_id,
)
from .prompts import REPAIR_INSTRUCTION, REPAIR_SCHEMA, REPAIR_VERSION
from .quality import _auto_fix_item


def _repair_context(item: GuideItem, requirements: list[PolicyRequirement],
                    impacts: list[ImpactCandidate], clauses: dict[str, ClauseUnit],
                    findings: list[dict[str, Any]], limit: int = 18000) -> str:
    parts = ["[REQUIREMENT]"]
    for requirement in requirements:
        parts.append(f"[{requirement.requirement_id}] {requirement.article}\n"
                     f"requirement={requirement.requirement}\nquote={requirement.source_quote}\n"
                     f"conditions={requirement.conditions}\nexceptions={requirement.exceptions}")
    parts += ["", "[GUIDE_ITEM]", json.dumps({
        "guide_item_id": item.guide_item_id, "title": item.title, "section": item.section,
        "business_requirement": item.business_requirement, "instruction": item.instruction,
        "applicability": item.applicability, "conditions": item.conditions,
        "exceptions": item.exceptions, "old_text_patterns": item.old_text_patterns,
        "new_text": item.new_text, "new_text_origin": item.new_text_origin,
    }, ensure_ascii=False, indent=2)]
    parts += ["", "[REVIEW_FINDINGS]"]
    for finding in findings:
        if finding.get("severity") != "critical" or finding.get("status") not in {"open", None, ""}:
            continue
        parts.append(f"- [{finding.get('category')}] {finding.get('description')}\n"
                     f"  evidence={finding.get('evidence_quote', '')}")
    parts += ["", "[REAL_CONTRACT_EVIDENCE]"]
    seen = set()
    for impact_id in item.impact_ids[:6]:
        impact = next((item for item in impacts if item.impact_id == impact_id), None)
        if not impact:
            continue
        for clause_id in impact.clause_ids[:2]:
            if clause_id in seen:
                continue
            seen.add(clause_id)
            clause = clauses.get(clause_id)
            if clause:
                parts.append(f"[{clause.clause_id}] {' > '.join(clause.section_path[-3:])}\n{clause.text[:2000]}")
    return "\n".join(parts)[:limit]


def repair_items(router, items: list[GuideItem], requirements: list[PolicyRequirement],
                 impacts: list[ImpactCandidate], clauses: dict[str, ClauseUnit],
                 findings: list[dict[str, Any]], *, max_workers: int = 4
                 ) -> tuple[list[GuideItem], list[dict[str, Any]], int]:
    requirement_map = {item.requirement_id: item for item in requirements}
    by_item: dict[str, list[dict[str, Any]]] = {}
    for finding in findings:
        if finding.get("severity") == "critical" and finding.get("guide_item_id"):
            by_item.setdefault(finding["guide_item_id"], []).append(finding)
    targets = [item for item in items if item.guide_item_id in by_item]
    if not targets:
        return [], [], 0

    def one(item: GuideItem):
        reqs = [requirement_map[value] for value in item.requirement_ids if value in requirement_map]
        context = _repair_context(item, reqs, impacts, clauses, by_item[item.guide_item_id])
        try:
            result = router.call(task_type="guide_repair", bounded_context=context,
                                 response_schema=REPAIR_SCHEMA, instruction=REPAIR_INSTRUCTION,
                                 prompt_version=REPAIR_VERSION, role="guide_author")
        except Exception as exc:
            return item, [], f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
        value = result.value
        item.title = str(value.get("title") or item.title)
        item.business_requirement = str(value.get("business_requirement") or item.business_requirement)
        item.instruction = str(value.get("instruction") or item.instruction)
        item.applicability = str(value.get("applicability") or item.applicability)
        item.conditions = [str(v) for v in value.get("conditions") or item.conditions]
        item.exceptions = [str(v) for v in value.get("exceptions") or item.exceptions]
        item.old_text_patterns = [str(v) for v in value.get("old_text_patterns") or item.old_text_patterns]
        item.new_text = str(value.get("new_text") or item.new_text)
        item.new_text_origin = str(value.get("new_text_origin") or item.new_text_origin)
        item.version += 1
        item.status = "repaired"
        item.quality_status = "not_run"
        fixes = _auto_fix_item(item, reqs)
        return item, fixes, str(value.get("repair_notes") or "")

    repaired: list[GuideItem] = []
    extra_findings: list[dict[str, Any]] = []
    calls = 0
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(targets)))) as executor:
        futures = [executor.submit(one, item) for item in targets]
        for future in as_completed(futures):
            item, fixes, note = future.result()
            if item.status == "repaired":
                calls += 1
                repaired.append(item)
                extra_findings.extend(fixes)
                extra_findings.append({
                    "finding_id": stable_id("F", "REPAIR", item.guide_item_id, note, length=20),
                    "guide_item_id": item.guide_item_id, "category": "repair",
                    "severity": "info", "status": "repaired", "source": "guide_repair",
                    "description": "已执行一轮独立复核后的修复：" + (note or "字段已更新"),
                    "evidence_quote": item.new_text[:300],
                })
    return repaired, extra_findings, calls
