"""Requirement, impact, contract and semantic applicability coverage."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import (
    ClauseUnit,
    ContractVersion,
    GuideItem,
    ImpactCandidate,
    PolicyRequirement,
    compact_for_match,
    stable_id,
    unique,
)
from .scope import section_in_scope, texts_in_scope
from .prompts import (
    APPLICABILITY_INSTRUCTION,
    APPLICABILITY_SCHEMA,
    APPLICABILITY_VERSION,
    COVERAGE_INSTRUCTION,
    COVERAGE_SCHEMA,
    COVERAGE_VERSION,
    TOPIC_COVERAGE_INSTRUCTION,
    TOPIC_COVERAGE_SCHEMA,
    TOPIC_COVERAGE_VERSION,
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
    missing_topics: list[dict[str, Any]] = field(default_factory=list)
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
                   impacts: list[ImpactCandidate], limit: int = 24000,
                   *, selected_impact_ids: set[str] | None = None,
                   include_requirements: bool = False,
                   global_items: list[GuideItem] | None = None) -> str:
    selected = (impacts if selected_impact_ids is None else
                [item for item in impacts if item.impact_id in selected_impact_ids])
    if selected_impact_ids is not None:
        requirement_ids = {item.requirement_id for item in selected}
        if not include_requirements:
            requirements = [item for item in requirements if item.requirement_id in requirement_ids]
        impact_ids = {item.impact_id for item in selected}
        if not include_requirements:
            items = [item for item in items if impact_ids.intersection(item.impact_ids)]
    parts = ["[REQUIREMENTS]"]
    for requirement in requirements:
        parts.append(f"- {requirement.requirement_id} [{requirement.article}] "
                     f"disposition={requirement.disposition} :: {requirement.requirement[:200]}")
    if global_items:
        # The detailed guide items below are scoped to the audit batch.  A
        # truncated context once hid 31 of 90 items and the auditor reported
        # their topics as missing.  Keep a compact index of every item ahead
        # of the detailed section so "not shown in detail" is never mistaken
        # for "no guide item exists".
        parts.append("\n[ALL_GUIDE_ITEM_INDEX]")
        for item in global_items:
            parts.append(f"- {item.guide_item_id} req={','.join(item.requirement_ids)} "
                         f"title={item.title[:80]}")
    parts.append("\n[GUIDE_ITEMS]")
    for item in items:
        parts.append(f"- {item.guide_item_id} req={','.join(item.requirement_ids)} "
                     f"impacts={len(item.impact_ids)} "
                     f"title={item.title[:80]} :: {item.instruction[:160]} "
                     f"new={item.new_text[:180]}")
    parts.append("\n[IMPACTS_WITHOUT_FINAL_DISPOSITION]")
    unresolved = [item for item in selected
                  if item.impact_status in {"definite", "possible"}
                  and item.disposition not in {"adjudicated_false_positive", "not_applicable"}]
    for impact in unresolved:
        parts.append(f"- {impact.impact_id} req={impact.requirement_id} "
                     f"contract={impact.contract_version_id} status={impact.impact_status} "
                     f"reason={impact.impact_reason[:140]}")
    text = "\n".join(parts)
    return text[:limit]


def _topic_candidates(topic: dict[str, Any], items: list[GuideItem]) -> list[GuideItem]:
    topic_ids = {str(value) for value in topic.get("requirement_ids") or [] if value}
    candidates = [item for item in items
                  if topic_ids and set(item.requirement_ids) & topic_ids]
    if not candidates:
        description = compact_for_match(str(topic.get("description") or ""))
        tokens = set(re.findall(r"[\u4e00-\u9fff]{2}", description))
        scored = []
        for item in items:
            text = compact_for_match(" ".join((item.title, item.instruction, item.new_text)))
            overlap = sum(1 for token in tokens if token in text)
            if overlap:
                scored.append((overlap, item))
        scored.sort(key=lambda pair: (-pair[0], pair[1].guide_item_id))
        candidates = [item for _, item in scored[:3]]
    return candidates[:4]


def _adjudicate_topics(router, topics: list[dict[str, Any]], items: list[GuideItem]
                       ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """Ask a strict judge whether an existing item covers each reported topic.

    The coverage auditor can over-report at topic granularity even when every
    item is visible.  A topic is closed as covered only when the judge names a
    real candidate item; omitted topics, invalid ids and uncertain verdicts
    remain unresolved and keep the gate closed.
    """
    prepared: list[tuple[dict[str, Any], list[GuideItem]]] = []
    unresolved: list[dict[str, Any]] = []
    for topic in topics:
        candidates = _topic_candidates(topic, items)
        if not candidates:
            topic["coverage_verdict"] = "uncertain"
            topic["coverage_reason"] = "no candidate guide item"
            unresolved.append(topic)
            continue
        prepared.append((topic, candidates))
    resolved: list[dict[str, Any]] = []
    calls = 0
    batch_size = 6
    for start in range(0, len(prepared), batch_size):
        batch = prepared[start:start + batch_size]
        lines = ["[TOPICS]"]
        allowed: dict[str, set[str]] = {}
        by_id: dict[str, dict[str, Any]] = {}
        for topic, candidates in batch:
            topic_id = str(topic["topic_id"])
            by_id[topic_id] = topic
            allowed[topic_id] = {item.guide_item_id for item in candidates}
            lines.append(
                f"[TOPIC id={topic_id}] requirements={','.join(topic.get('requirement_ids') or [])}\n"
                f"description={topic.get('description') or ''}\n"
                f"evidence={topic.get('evidence_quote') or ''}")
            for item in candidates:
                lines.append(f"  [CANDIDATE {item.guide_item_id}] title={item.title[:100]}\n"
                             f"  new={item.new_text[:500]}")
        try:
            result = router.call(task_type="guide_topic_coverage",
                                 bounded_context="\n".join(lines),
                                 response_schema=TOPIC_COVERAGE_SCHEMA,
                                 instruction=TOPIC_COVERAGE_INSTRUCTION,
                                 prompt_version=TOPIC_COVERAGE_VERSION,
                                 role="coverage_auditor")
            calls += 1
        except Exception:
            unresolved.extend(topic for topic, _ in batch)
            continue
        seen: set[str] = set()
        for row in result.value.get("results") or []:
            topic_id = str(row.get("topic_id") or "")
            topic = by_id.get(topic_id)
            if topic is None or topic_id in seen:
                continue
            seen.add(topic_id)
            verdict = str(row.get("verdict") or "uncertain")
            named = [str(value) for value in row.get("guide_item_ids") or []]
            valid = [value for value in named if value in allowed.get(topic_id, set())]
            topic["coverage_reason"] = str(row.get("reason") or "")
            if verdict == "covered" and valid:
                topic["coverage_verdict"] = "covered"
                topic["covered_by"] = valid
                resolved.append(topic)
            else:
                topic["coverage_verdict"] = ("not_covered" if verdict == "not_covered"
                                             else "uncertain")
                unresolved.append(topic)
        for topic_id, topic in by_id.items():
            if topic_id in seen:
                continue
            topic["coverage_verdict"] = "uncertain"
            topic["coverage_reason"] = "adjudicator omitted topic"
            unresolved.append(topic)
    return resolved, unresolved, calls


def run_coverage_gate(router, requirements: list[PolicyRequirement], impacts: list[ImpactCandidate],
                      items: list[GuideItem], clauses: dict[str, ClauseUnit],
                      versions: list[ContractVersion], sweep_batches: list[dict[str, Any]],
                      snapshot: Any, *, semantic_applicability: bool = True,
                      max_applicability_per_item: int = 3,
                      scope_sections: list[str] | None = None) -> CoverageResult:
    rows: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    applicability: list[dict[str, Any]] = []
    missing_topics: list[dict[str, Any]] = []
    seen_topic_ids: set[str] = set()
    calls = 0
    requirement_map = {item.requirement_id: item for item in requirements}
    impact_map = {item.impact_id: item for item in impacts}
    scope = list(scope_sections or [])

    def _impact_in_scope(impact: ImpactCandidate) -> bool:
        if not scope:
            return True
        for clause_id in impact.clause_ids:
            clause = clauses.get(clause_id)
            if clause and section_in_scope(" > ".join(clause.section_path), scope):
                return True
        return False

    def _requirement_in_scope(requirement: PolicyRequirement) -> bool:
        if not scope:
            return True
        if texts_in_scope(requirement.candidate_contract_domains, scope):
            return True
        return any(item.requirement_id == requirement.requirement_id and _impact_in_scope(item)
                   for item in impacts)

    item_by_requirement: dict[str, list[GuideItem]] = {}
    item_by_impact: dict[str, list[GuideItem]] = {}
    for item in items:
        if scope and item.section and not section_in_scope(item.section, scope):
            continue
        for requirement_id in item.requirement_ids:
            item_by_requirement.setdefault(requirement_id, []).append(item)
        for impact_id in item.impact_ids:
            item_by_impact.setdefault(impact_id, []).append(item)
    scope_items = [item for item in items
                   if not scope or not item.section or section_in_scope(item.section, scope)]
    scoped_requirements = [item for item in requirements if _requirement_in_scope(item)]

    # Requirement coverage ---------------------------------------------------
    requirement_counts: dict[str, int] = {}
    for requirement in requirements:
        if not _requirement_in_scope(requirement):
            status = "out_of_scope"
            reason = "指引范围外章节，不纳入覆盖分母。"
            requirement_counts[status] = requirement_counts.get(status, 0) + 1
            rows.append(_row("requirement", requirement.requirement_id, status,
                             disposition=requirement.disposition, reason=reason,
                             impact_ids=[]))
            continue
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
        if not _impact_in_scope(impact):
            impact.disposition = "not_applicable"
            impact.disposition_reason = "指引范围外章节，不纳入覆盖分母。"
            impact_counts["out_of_scope"] = impact_counts.get("out_of_scope", 0) + 1
            rows.append(_row("impact", impact.impact_id, "out_of_scope",
                             requirement_id=impact.requirement_id,
                             contract_version_id=impact.contract_version_id,
                             impact_status=impact.impact_status,
                             guide_item_ids=[], reason=impact.disposition_reason))
            continue
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
        version_batches = [batch for batch in sweep_batches
                           if str(batch.get("contract_version_id") or "") == version_id]
        is_latest = version_id in latest_ids
        for requirement in requirements:
            key = (version_id, requirement.requirement_id)
            if not _requirement_in_scope(requirement):
                contract_counts["out_of_scope"] = contract_counts.get("out_of_scope", 0) + 1
                rows.append(_row("contract_requirement", f"{version_id}:{requirement.requirement_id}",
                                 "out_of_scope", contract_version_id=version_id,
                                 contract_id=version.contract_id,
                                 requirement_id=requirement.requirement_id,
                                 latest_known=is_latest, reason="指引范围外章节。"))
                continue
            affected = [item for item in impacts_by_key.get(key, [])
                        if item.impact_status in {"definite", "possible"} and _impact_in_scope(item)]
            # Scope sweep evidence to this requirement: a batch only speaks
            # about its own requirement window, and a per-requirement resolver
            # verdict takes precedence over the coarse batch status.
            relevant: list[str] = []
            for batch in version_batches:
                resolution = (batch.get("resolution") or {}).get("resolved") or {}
                if resolution:
                    if requirement.requirement_id in resolution:
                        relevant.append(str(resolution[requirement.requirement_id]))
                    continue
                window = batch.get("requirement_ids")
                if window and requirement.requirement_id not in window:
                    continue
                relevant.append(str(batch.get("status") or "uncertain"))
            if affected:
                status = "affected"
                reason = "存在确定或可能影响。"
            elif relevant and all(value == "not_affected" for value in relevant):
                status = "not_affected"
                reason = "该要求相关的语义扫描批次均完成，且未发现确定/可能影响。"
            elif any(value in {"uncertain", "model_error"} for value in relevant):
                status = "uncertain"
                reason = "该要求相关的扫描批次仍有 uncertain 或模型错误。"
            elif relevant:
                status = "uncertain"
                reason = "该要求相关的扫描批次为 affected，但没有对应 Impact。"
            else:
                status = "uncertain"
                reason = "该要求未被语义扫描覆盖。"
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
    # A single response for every impact is unreliable: the model may produce
    # hundreds of rows even when asked to be concise, and the strict schema
    # correctly rejects that response.  Audit requirements once, then audit
    # only impacts that still have no deterministic disposition in bounded
    # batches.  This preserves fail-closed behavior while making each response
    # structurally deliverable and independently traceable.
    def apply_audit(audit: dict[str, Any], *, include_requirements: bool,
                    allowed_requirement_ids: set[str] | None = None) -> None:
        nonlocal findings
        if include_requirements:
            for item in audit.get("requirement_results") or []:
                requirement_id = str(item.get("requirement_id") or "")
                if (allowed_requirement_ids is not None
                        and requirement_id not in allowed_requirement_ids):
                    continue
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
                if status == "covered" and existing["status"] == "unresolved":
                    # A semantic auditor may only close an impact as covered
                    # when it names a real GuideItem already present in this
                    # run.  Otherwise the deterministic row stays unresolved.
                    guide_ids = [str(value) for value in item.get("guide_item_ids") or []]
                    allowed = {guide_item.guide_item_id for guide_item in items}
                    if guide_ids and set(guide_ids).issubset(allowed):
                        existing["status"] = "covered"
                        existing["guide_item_ids"] = guide_ids
                        existing["reason"] = "独立覆盖审计确认已有候选指引覆盖：" + str(item.get("reason") or "")
                if status in {"false_positive", "not_applicable"} and existing["status"] == "unresolved":
                    existing["status"] = status
                    existing["reason"] = "独立覆盖审计追加处置：" + str(item.get("reason") or "")
                elif status == "unresolved" and existing["status"] == "uncertain":
                    existing["status"] = "unresolved"
                    existing["reason"] = "独立覆盖审计认为覆盖不足：" + str(item.get("reason") or "")
                    findings.append(_finding("impact_coverage", "major", impact_id,
                                             "独立覆盖审计认为该影响未被充分覆盖。"))
        for item in audit.get("missing_topics") or []:
            topic_ids = [str(value) for value in item.get("requirement_ids") or [] if value]
            if (allowed_requirement_ids is not None and topic_ids
                    and not set(topic_ids) & allowed_requirement_ids):
                # This batch only owns the supplied requirements; a topic that
                # belongs to another batch is reviewed there, not duplicated.
                continue
            description = str(item.get("description") or "")
            topic_id = stable_id("CT", ",".join(sorted(topic_ids)),
                                 compact_for_match(description)[:200], length=20)
            if topic_id in seen_topic_ids:
                continue
            seen_topic_ids.add(topic_id)
            missing_topics.append({
                "topic_id": topic_id,
                "requirement_ids": topic_ids,
                "description": description,
                "evidence_quote": str(item.get("evidence_quote") or "")[:600],
                "coverage_verdict": "unresolved",
            })
    # Requirement audits are batched.  Sending every requirement and every
    # guide item in one 24k-char request truncated the item list; the auditor
    # then reported the invisible items' topics as missing (FL-D379).  Each
    # batch owns a bounded requirement slice, sees the detailed guide items
    # bound to that slice, and receives a compact index of every existing item.
    requirement_audit_batch = 16
    for start in range(0, len(scoped_requirements), requirement_audit_batch):
        batch = scoped_requirements[start:start + requirement_audit_batch]
        batch_ids = {item.requirement_id for item in batch}
        batch_items = [item for item in scope_items
                       if set(item.requirement_ids) & batch_ids]
        try:
            result = router.call(
                task_type="guide_coverage_audit",
                bounded_context=_audit_context(
                    batch, batch_items, impacts, 24000,
                    selected_impact_ids=set(), include_requirements=True,
                    global_items=scope_items),
                response_schema=COVERAGE_SCHEMA, instruction=COVERAGE_INSTRUCTION,
                prompt_version=COVERAGE_VERSION, role="coverage_auditor")
            calls += 1
            apply_audit(result.value, include_requirements=True,
                        allowed_requirement_ids=batch_ids)
        except Exception as exc:
            findings.append(_finding(
                "semantic_coverage", "major",
                f"coverage_audit_requirements_{start // requirement_audit_batch + 1}",
                f"独立要求覆盖审计模型调用失败：{type(exc).__name__}"))
            calls += 1

    audit_targets = [item for item in impacts
                     if _impact_in_scope(item)
                     and item.impact_status in {"definite", "possible"}
                     and not item_by_impact.get(item.impact_id)
                     and item.disposition not in {"adjudicated_false_positive", "not_applicable"}]
    audit_batch_size = 40
    for start in range(0, len(audit_targets), audit_batch_size):
        batch = audit_targets[start:start + audit_batch_size]
        try:
            result = router.call(
                task_type="guide_coverage_audit",
                bounded_context=_audit_context(
                    scoped_requirements, scope_items, impacts, 24000,
                    selected_impact_ids={item.impact_id for item in batch}),
                response_schema=COVERAGE_SCHEMA, instruction=COVERAGE_INSTRUCTION,
                prompt_version=COVERAGE_VERSION, role="coverage_auditor")
            calls += 1
            apply_audit(result.value, include_requirements=False)
        except Exception as exc:
            findings.append(_finding("semantic_coverage", "major",
                                     f"coverage_audit_impacts_{start // audit_batch_size + 1}",
                                     f"独立影响覆盖审计模型调用失败：{type(exc).__name__}"))
            calls += 1

    # A topic-level judge separates "the auditor did not see a covering item"
    # from a genuine gap.  Only unresolved topics create critical findings and
    # are handed to the supplement stage.
    resolved_topics, unresolved_topics, topic_calls = _adjudicate_topics(
        router, missing_topics, scope_items)
    calls += topic_calls
    for topic in resolved_topics + unresolved_topics:
        rows.append(_row(
            "topic", topic["topic_id"],
            "covered" if topic.get("coverage_verdict") == "covered" else "unresolved",
            requirement_ids=topic.get("requirement_ids") or [],
            description=topic.get("description") or "",
            evidence_quote=topic.get("evidence_quote") or "",
            reason=topic.get("coverage_reason") or "",
            guide_item_ids=topic.get("covered_by") or []))
    for topic in unresolved_topics:
        findings.append(_finding(
            "semantic_coverage", "critical",
            ",".join(topic.get("requirement_ids") or []) or "missing_topic",
            "独立覆盖审计发现未覆盖主题：" + str(topic.get("description") or ""),
            str(topic.get("evidence_quote") or "")[:300]))
    missing_topics = unresolved_topics

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
                          missing_topics=missing_topics, calls=calls)
