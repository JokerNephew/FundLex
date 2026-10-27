"""Requirement, impact, contract and semantic applicability coverage."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import (
    ClauseUnit,
    ContractVersion,
    GuideItem,
    ImpactCandidate,
    PolicyRequirement,
    stable_id,
    unique,
)
from .prompts import (
    APPLICABILITY_INSTRUCTION,
    APPLICABILITY_SCHEMA,
    APPLICABILITY_VERSION,
    COVERAGE_INSTRUCTION,
    COVERAGE_SCHEMA,
    COVERAGE_VERSION,
)


@dataclass
class CoverageResult:
    rows: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    applicability: list[dict[str, Any]]
    run_status: str
    requirement_summary: dict[str, int] = field(default_factory=dict)
    impact_summary: dict[str, int] = field(default_factory=dict)
    contract_summary: dict[str, int] = field(default_factory=dict)
    calls: int = 0


def _row(level: str, ref_id: str, status: str, **payload: Any) -> dict[str, Any]:
    return {
        "coverage_id": stable_id("COV", level, ref_id, status, length=20),
        "level": level, "ref_id": ref_id, "status": status,
        **payload,
    }


def _finding(category: str, severity: str, ref_id: str, description: str,
             evidence_quote: str = "") -> dict[str, Any]:
    return {
        "finding_id": stable_id("F", "COVERAGE", category, ref_id, description, length=20),
        "guide_item_id": "", "category": category, "severity": severity, "status": "open",
        "description": description, "evidence_quote": evidence_quote, "source": "coverage_gate",
    }


def _sweep_state(sweep_batches: list[dict[str, Any]], version_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    state: dict[str, dict[str, Any]] = {}
    for batch in sweep_batches:
        version_id = str(batch.get("contract_version_id") or "")
        if not version_id:
            continue
        item = state.setdefault(version_id, {"swept": 0, "affected": 0, "not_affected": 0,
                                             "uncertain": 0, "errors": 0})
        item["swept"] += 1
        status = str(batch.get("status") or "uncertain")
        if status in {"affected", "not_affected", "uncertain"}:
            item[status] += 1
        elif status == "model_error":
            item["errors"] += 1
    return state


def _representative_clauses(item: GuideItem, impacts: dict[str, ImpactCandidate],
                            clauses: dict[str, ClauseUnit], limit: int = 4) -> list[ClauseUnit]:
    selected: list[ClauseUnit] = []
    seen: set[str] = set()

    def add(clause_id: str) -> None:
        clause = clauses.get(clause_id)
        if clause and clause.clause_id not in seen and len(selected) < limit:
            seen.add(clause.clause_id)
            selected.append(clause)

    item_impacts = [impacts[value] for value in item.impact_ids if value in impacts]
    # Rare/singleton impacts first: they carry the highest review value.
    item_impacts.sort(key=lambda impact: (len(impact.clause_ids), impact.impact_id))
    for impact in item_impacts:
        for clause_id in impact.clause_ids:
            add(clause_id)
            if len(selected) >= limit:
                return selected
    return selected


def _audit_context(requirements: list[PolicyRequirement], items: list[GuideItem],
                   impacts: list[ImpactCandidate], limit: int = 24000) -> str:
    parts = ["[REQUIREMENTS]"]
    for requirement in requirements:
        parts.append(f"- {requirement.requirement_id} [{requirement.article}] "
                     f"disposition={requirement.disposition} :: {requirement.requirement[:200]}")
    parts.append("\n[GUIDE_ITEMS]")
    for item in items:
        parts.append(f"- {item.guide_item_id} req={','.join(item.requirement_ids)} "
                     f"impacts={len(item.impact_ids)} "
                     f"title={item.title[:80]} :: {item.instruction[:160]} "
                     f"new={item.new_text[:180]}")
    parts.append("\n[IMPACTS_WITHOUT_FINAL_DISPOSITION]")
    unresolved = [item for item in impacts
                  if item.impact_status in {"definite", "possible"}
                  and item.disposition not in {"adjudicated_false_positive", "not_applicable"}]
    for impact in unresolved[:120]:
        parts.append(f"- {impact.impact_id} req={impact.requirement_id} "
                     f"contract={impact.contract_version_id} status={impact.impact_status} "
                     f"reason={impact.impact_reason[:140]}")
    text = "\n".join(parts)
    return text[:limit]


def run_coverage_gate(router, requirements: list[PolicyRequirement], impacts: list[ImpactCandidate],
                      items: list[GuideItem], clauses: dict[str, ClauseUnit],
                      versions: list[ContractVersion], sweep_batches: list[dict[str, Any]],
                      snapshot: Any, *, semantic_applicability: bool = True,
                      max_applicability_per_item: int = 3) -> CoverageResult:
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    applicability: list[dict[str, Any]] = []
    calls = 0
    requirement_map = {item.requirement_id: item for item in requirements}
    impact_map = {item.impact_id: item for item in impacts}
    item_by_requirement: dict[str, list[GuideItem]] = {}
    item_by_impact: dict[str, list[GuideItem]] = {}
    for item in items:
        for requirement_id in item.requirement_ids:
            item_by_requirement.setdefault(requirement_id, []).append(item)
        for impact_id in item.impact_ids:
            item_by_impact.setdefault(impact_id, []).append(item)

    # Requirement coverage ---------------------------------------------------
    requirement_counts: dict[str, int] = {}
    for requirement in requirements:
        covered_items = item_by_requirement.get(requirement.requirement_id, [])
        impact_list = [item for item in impacts if item.requirement_id == requirement.requirement_id]
        if covered_items:
            status = "covered"
            reason = "存在直接绑定该要求的候选指引。"
        elif requirement.disposition in {"no_contract_change", "out_of_contract_scope",
                                          "needs_external_baseline"}:
            status = "disposed"
            reason = requirement.disposition_reason or requirement.disposition
        elif requirement.disposition == "uncertain":
            status = "uncertain"
            reason = requirement.disposition_reason or "要求处置本身不确定。"
        elif impact_list and all(item.disposition in {"adjudicated_false_positive", "not_applicable"}
                                 or item.impact_status == "unlikely" for item in impact_list):
            status = "disposed"
            reason = "全部已发现影响均经复核否定或不适用。"
        else:
            status = "gap"
            reason = "要求需要修改合同，但没有候选指引覆盖。"
            findings.append(_finding("requirement_coverage", "critical", requirement.requirement_id,
                                     f"{requirement.requirement_id} 为 modify_contract，但没有 GuideItem：{requirement.requirement[:200]}",
                                     requirement.source_quote[:300]))
        requirement_counts[status] = requirement_counts.get(status, 0) + 1
        rows.append(_row("requirement", requirement.requirement_id, status,
                         guide_item_ids=[item.guide_item_id for item in covered_items],
                         disposition=requirement.disposition, reason=reason,
                         impact_ids=[item.impact_id for item in impact_list]))

    # Impact coverage --------------------------------------------------------
    impact_counts: dict[str, int] = {}
    for impact in impacts:
        if impact.impact_status == "unlikely" and not impact.disposition:
            impact.disposition = "adjudicated_false_positive"
            impact.disposition_reason = impact.disposition_reason or "发现路径判定 unlikely，未进入候选指引。"
        covered_items = item_by_impact.get(impact.impact_id, [])
        if covered_items:
            status = "covered"
            impact.guide_item_ids = [item.guide_item_id for item in covered_items]
            reason = "存在直接绑定该影响的候选指引。"
        elif impact.disposition in {"adjudicated_false_positive", "not_applicable"}:
            status = impact.disposition
            reason = impact.disposition_reason or "经复核否定或不适用。"
        elif impact.impact_status == "unlikely":
            status = "false_positive"
            reason = impact.disposition_reason or "发现路径判定 unlikely。"
        else:
            status = "unresolved"
            reason = impact.disposition_reason or "确定/可能影响没有最终去向。"
            if impact.impact_status == "definite":
                findings.append(_finding("impact_coverage", "critical", impact.impact_id,
                                         f"确定影响 {impact.impact_id} 没有候选指引或明确处置。",
                                         impact.source_text[:300]))
        impact_counts[status] = impact_counts.get(status, 0) + 1
        rows.append(_row("impact", impact.impact_id, status,
                         requirement_id=impact.requirement_id,
                         contract_version_id=impact.contract_version_id,
                         impact_status=impact.impact_status,
                         guide_item_ids=[item.guide_item_id for item in covered_items],
                         reason=reason))

    # Contract × requirement coverage ---------------------------------------
    sweep = _sweep_state(sweep_batches, [version.contract_version_id for version in versions])
    impacts_by_key: dict[tuple[str, str], list[ImpactCandidate]] = {}
    for impact in impacts:
        impacts_by_key.setdefault((impact.contract_version_id, impact.requirement_id), []).append(impact)
    latest_ids = set(getattr(snapshot, "latest_version_ids", []) or [])
    contract_counts: dict[str, int] = {}
    for version in versions:
        version_id = version.contract_version_id
        state = sweep.get(version_id)
        is_latest = version_id in latest_ids
        for requirement in requirements:
            key = (version_id, requirement.requirement_id)
            affected = [item for item in impacts_by_key.get(key, [])
                        if item.impact_status in {"definite", "possible"}]
            if affected:
                status = "affected"
                reason = "存在确定或可能影响。"
            elif state and state["swept"] and state["uncertain"] == 0 and state["errors"] == 0:
                status = "not_affected"
                reason = "合同所有语义扫描批次均完成，且未发现该要求的确定/可能影响。"
            elif state and state["swept"]:
                status = "uncertain"
                reason = "合同已扫描，但批次结果包含 affected/uncertain 或模型错误。"
            else:
                status = "uncertain"
                reason = "该合同未被语义扫描覆盖。"
            contract_counts[status] = contract_counts.get(status, 0) + 1
            rows.append(_row("contract_requirement", f"{version_id}:{requirement.requirement_id}",
                             status, contract_version_id=version_id,
                             contract_id=version.contract_id,
                             requirement_id=requirement.requirement_id,
                             latest_known=is_latest, reason=reason))
    # Latest contracts are a hard completeness boundary.
    latest_uncertain = [row for row in rows if row["level"] == "contract_requirement"
                        and row.get("latest_known") and row["status"] == "uncertain"]
    if latest_uncertain:
        findings.append(_finding(
            "contract_coverage", "critical", "latest_contracts",
            f"{len(latest_uncertain)} 个 latest-known 合同×要求组合仍为 uncertain。",
            latest_uncertain[0]["reason"]))

    # Semantic applicability -------------------------------------------------
    if semantic_applicability:
        for item in items:
            for clause in _representative_clauses(item, impact_map, clauses, max_applicability_per_item):
                requirement_text = "\n".join(
                    f"[{requirement.requirement_id}] {requirement.requirement}\nquote={requirement.source_quote}"
                    for requirement in requirements if requirement.requirement_id in item.requirement_ids)
                item_json = json.dumps({
                    "guide_item_id": item.guide_item_id, "title": item.title,
                    "instruction": item.instruction, "applicability": item.applicability,
                    "conditions": item.conditions, "exceptions": item.exceptions,
                    "old_text_patterns": item.old_text_patterns,
                    "new_text": item.new_text,
                }, ensure_ascii=False)
                context = (f"[REQUIREMENT]\n{requirement_text}\n\n"
                           f"[GUIDE_ITEM]\n{item_json}\n\n"
                           f"[CONTRACT_CLAUSE]\n[{clause.clause_id}] {' > '.join(clause.section_path[-3:])}\n{clause.text[:3000]}")
                try:
                    result = router.call(task_type="guide_applicability", bounded_context=context,
                                         response_schema=APPLICABILITY_SCHEMA,
                                         instruction=APPLICABILITY_INSTRUCTION,
                                         prompt_version=APPLICABILITY_VERSION,
                                         role="coverage_auditor")
                    calls += 1
                    verdict = str(result.value.get("verdict") or "ambiguous")
                    reason = str(result.value.get("reason") or "")
                    quote = str(result.value.get("evidence_quote") or "")
                except Exception as exc:
                    verdict, reason, quote = "ambiguous", f"模型调用失败：{type(exc).__name__}", ""
                applicability.append({
                    "result_id": stable_id("AP", item.guide_item_id, clause.clause_id, length=20),
                    "guide_item_id": item.guide_item_id, "clause_id": clause.clause_id,
                    "verdict": verdict, "reason": reason, "evidence_quote": quote,
                })
                if verdict in {"not_covered", "ambiguous"}:
                    severity = "critical" if verdict == "not_covered" else "major"
                    findings.append(_finding(
                        "semantic_applicability", severity, item.guide_item_id,
                        f"{item.guide_item_id} 对真实合同条款 {clause.clause_id} 的适用性为 {verdict}：{reason}",
                        clause.text[:300]))
                    if verdict == "not_covered":
                        for impact_id in item.impact_ids:
                            impact = impact_map.get(impact_id)
                            if impact and clause.clause_id in impact.clause_ids:
                                impact.disposition = "unresolved"
                                impact.disposition_reason = (
                                    impact.disposition_reason + "；Semantic Applicability 判定 not_covered").strip("；")

    # Independent coverage audit --------------------------------------------
    context = _audit_context(requirements, items, impacts, 24000)
    try:
        result = router.call(task_type="guide_coverage_audit", bounded_context=context,
                             response_schema=COVERAGE_SCHEMA, instruction=COVERAGE_INSTRUCTION,
                             prompt_version=COVERAGE_VERSION, role="coverage_auditor")
        calls += 1
        audit = result.value
        for item in audit.get("requirement_results") or []:
            requirement_id = str(item.get("requirement_id") or "")
            existing = next((row for row in rows if row["level"] == "requirement"
                             and row["ref_id"] == requirement_id), None)
            if existing and item.get("status") == "gap" and existing["status"] in {"uncertain", "gap"}:
                existing["status"] = "gap"
                existing["reason"] = "独立覆盖审计追加 gap：" + str(item.get("reason") or "")
                findings.append(_finding("requirement_coverage", "critical", requirement_id,
                                         "独立覆盖审计发现要求缺口：" + str(item.get("reason") or "")))
        for item in audit.get("impact_results") or []:
            impact_id = str(item.get("impact_id") or "")
            existing = next((row for row in rows if row["level"] == "impact"
                             and row["ref_id"] == impact_id), None)
            status = str(item.get("status") or "")
            if existing and status in {"covered", "false_positive", "not_applicable", "unresolved"}:
                if status in {"false_positive", "not_applicable"} and existing["status"] == "unresolved":
                    existing["status"] = status
                    existing["reason"] = "独立覆盖审计追加处置：" + str(item.get("reason") or "")
                elif status == "unresolved" and existing["status"] == "uncertain":
                    existing["status"] = "unresolved"
                    existing["reason"] = "独立覆盖审计认为覆盖不足：" + str(item.get("reason") or "")
                    findings.append(_finding("impact_coverage", "major", impact_id,
                                             "独立覆盖审计认为该影响未被充分覆盖。"))
        for item in audit.get("missing_topics") or []:
            findings.append(_finding("semantic_coverage", "critical",
                                     ",".join(item.get("requirement_ids") or []) or "missing_topic",
                                     "独立覆盖审计发现未覆盖主题：" + str(item.get("description") or ""),
                                     str(item.get("evidence_quote") or "")[:300]))
    except Exception as exc:
        findings.append(_finding("semantic_coverage", "major", "coverage_audit",
                                 f"独立覆盖审计模型调用失败：{type(exc).__name__}"))
        calls += 1

    # Recompute summaries after the audit overrides.
    requirement_counts = {}
    for row in rows:
        if row["level"] == "requirement":
            requirement_counts[row["status"]] = requirement_counts.get(row["status"], 0) + 1
    impact_counts = {}
    for row in rows:
        if row["level"] == "impact":
            impact_counts[row["status"]] = impact_counts.get(row["status"], 0) + 1
    contract_counts = {}
    for row in rows:
        if row["level"] == "contract_requirement":
            contract_counts[row["status"]] = contract_counts.get(row["status"], 0) + 1
    critical = [item for item in findings if item["severity"] == "critical"]
    unresolved_impact = impact_counts.get("unresolved", 0)
    latest_uncertain_after = [row for row in rows if row["level"] == "contract_requirement"
                              and row.get("latest_known") and row["status"] == "uncertain"]
    complete = not critical and not latest_uncertain_after and unresolved_impact == 0
    run_status = "pass" if complete else "complete_with_unresolved"
    return CoverageResult(rows=rows, findings=findings, applicability=applicability,
                          run_status=run_status, requirement_summary=requirement_counts,
                          impact_summary=impact_counts, contract_summary=contract_counts,
                          calls=calls)
