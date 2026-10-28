"""Local guide candidates, pattern induction and generalised guide items."""
from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable

from .models import (
    ClauseUnit,
    GuideItem,
    ImpactCandidate,
    LocalGuideCandidate,
    PolicyRequirement,
    compact_for_match,
    merge_strings,
    normalize_space,
    sha256_json,
    stable_id,
    unique,
)
from .prompts import (
    LOCAL_CANDIDATE_INSTRUCTION,
    LOCAL_CANDIDATE_SCHEMA,
    LOCAL_CANDIDATE_VERSION,
    MERGE_INSTRUCTION,
    MERGE_SCHEMA,
    MERGE_VERSION,
)

_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
_DIRECT_SALE_PROHIBITION = re.compile(
    r"基金管理人(?:自行)?销售其管理的基金[^。；！？]*不得收取(?:认[（(]申[）)]购费|认购费|申购费|销售服务费)"
)
_DIRECT_CHANNEL = re.compile(r"(?:基金管理人(?:自行)?销售|直销机构|通过直销)")
_THIRD_PARTY_CHANNEL = re.compile(
    r"(?:其他基金销售机构|其他销售机构|非直销|代销机构|通过基金销售机构|直销机构以外)"
)
_HISTORICAL_FEE_TEXT = re.compile(
    r"(?:[A-ZＡ-Ｚ]类(?:基金)?份额|收取(?:认[（(]申[）)]购费|认购费|申购费)|"
    r"计提销售服务费|收取销售服务费|销售服务费(?:按|每日|由|从|计提)|不计提销售服务费)"
)


def _split_sentences(text: str) -> list[str]:
    return [value for value in re.split(r"(?<=[。！？；])", text or "") if value.strip()]


def _qualify_direct_sale_fee_text(text: str) -> tuple[str, bool]:
    """Separate a direct-sale prohibition from an unqualified fee pattern.

    Contract patterns such as "A/D charge subscription fees and C charges a
    service fee" describe the fee-bearing share-class structure.  They cannot
    be placed immediately after the manager's own-sales prohibition without a
    channel boundary.  Preserve the pattern, but attach it to the third-party
    sales channel so a reviewer can still inspect the historical arrangement.
    """
    parts = _split_sentences(text)
    if not parts:
        return text, False
    if not _DIRECT_SALE_PROHIBITION.search(text):
        return text, False
    changed = False
    qualified: list[str] = []
    for part in parts:
        if (_HISTORICAL_FEE_TEXT.search(part)
                and not _THIRD_PARTY_CHANNEL.search(part)
                and not _DIRECT_CHANNEL.search(part)):
            part = "通过其他基金销售机构销售本基金份额时，" + part.lstrip()
            changed = True
        qualified.append(part)
    return "".join(qualified), changed


def _normalise_direct_sale_candidate(candidate: LocalGuideCandidate,
                                     requirements: dict[str, PolicyRequirement]) -> None:
    relevant = [requirements[value] for value in candidate.requirement_ids if value in requirements]
    if not any(_DIRECT_SALE_PROHIBITION.search(item.source_quote)
               or _DIRECT_SALE_PROHIBITION.search(item.requirement) for item in relevant):
        return
    text = candidate.new_text
    direct_quote = next(
        (value.source_quote or value.requirement for value in relevant
         if _DIRECT_SALE_PROHIBITION.search(value.source_quote or value.requirement)),
        "基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。",
    )
    if _HISTORICAL_FEE_TEXT.search(text) and not _DIRECT_SALE_PROHIBITION.search(text):
        text = direct_quote.rstrip("。；") + "。" + text
    new_text, changed = _qualify_direct_sale_fee_text(text)
    if not changed:
        return
    candidate.new_text = new_text
    candidate.conditions = merge_strings(
        candidate.conditions,
        *(item.conditions for item in relevant),
        ["基金管理人自行销售其管理的基金时适用直销禁止收费安排"],
    )
    candidate.exceptions = merge_strings(
        candidate.exceptions,
        *(item.exceptions for item in relevant),
        ["通过其他基金销售机构销售时，历史份额类别收费结构须按实际销售渠道分别适用"],
    )
    candidate.applicability = normalize_space(
        "；".join(value for value in (
            candidate.applicability,
            "基金管理人自行销售其管理的基金时适用禁止收费；通过其他基金销售机构销售时，历史份额类别收费结构单独适用。",
        ) if value)
    )
    candidate.notes = normalize_space(
        "；".join(value for value in (candidate.notes, "direct_sale_fee_scope_guard") if value)
    )


def _normalise_direct_sale_family(family: dict[str, Any],
                                  requirements: dict[str, PolicyRequirement]) -> None:
    local = LocalGuideCandidate(
        local_id=str(family.get("family_id") or "family"),
        impact_ids=list(family.get("impact_ids") or []),
        requirement_ids=list(family.get("requirement_ids") or []),
        needs_modification="yes", applicability=str(family.get("applicability") or ""),
        conditions=list(family.get("conditions") or []),
        exceptions=list(family.get("exceptions") or []),
        new_text=str(family.get("new_text") or ""),
        notes=str(family.get("merge_rationale") or ""),
    )
    _normalise_direct_sale_candidate(local, requirements)
    family["new_text"] = local.new_text
    family["conditions"] = local.conditions
    family["exceptions"] = local.exceptions
    family["applicability"] = local.applicability
    if local.notes and "direct_sale_fee_scope_guard" in local.notes:
        family["merge_rationale"] = normalize_space(
            "；".join(value for value in (family.get("merge_rationale") or "", local.notes)
                      if value)
        )


@dataclass
class AuthoringConfig:
    local_batch_size: int = 4
    local_max_chars: int = 22000
    merge_max_members: int = 12
    merge_similarity: float = 0.62
    quality_max_context: int = 18000


def _signature(text: str, width: int = 3) -> set[str]:
    compact = re.sub(r"\s+", "", text or "")
    if len(compact) <= width:
        return {compact} if compact else set()
    return {compact[index:index + width] for index in range(len(compact) - width + 1)}


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _section_key(clause: ClauseUnit | None) -> str:
    if not clause or not clause.section_path:
        return ""
    return clause.section_path[0]


def _impact_group_key(impact: ImpactCandidate, clause: ClauseUnit | None) -> tuple:
    return (impact.requirement_id, _section_key(clause), impact.impact_status)


def _group_impacts(impacts: list[ImpactCandidate], clauses: dict[str, ClauseUnit],
                   config: AuthoringConfig) -> list[list[ImpactCandidate]]:
    buckets: dict[tuple, list[ImpactCandidate]] = {}
    for impact in impacts:
        clause = clauses.get(impact.clause_ids[0]) if impact.clause_ids else None
        buckets.setdefault(_impact_group_key(impact, clause), []).append(impact)
    groups: list[list[ImpactCandidate]] = []
    for bucket in buckets.values():
        bucket.sort(key=lambda item: item.impact_id)
        # A local pattern batch optimises model calls only.  It never removes an
        # impact: every id is passed to the author model and every id that the
        # model omits receives a fallback local candidate.
        for start in range(0, len(bucket), config.local_batch_size):
            groups.append(bucket[start:start + config.local_batch_size])
    return groups


def _requirement_context(requirements: list[PolicyRequirement]) -> str:
    return "\n".join(
        f"[{item.requirement_id}] article={item.article} norm={item.norm_type}\n"
        f"requirement={item.requirement}\nconditions={item.conditions}\n"
        f"exceptions={item.exceptions}\nscope={item.applicable_scope}\n"
        f"quote={item.source_quote}"
        for item in requirements)


def _impact_context(impacts: list[ImpactCandidate], clauses: dict[str, ClauseUnit],
                    limit: int) -> str:
    lines: list[str] = []
    for impact in impacts:
        pieces = []
        for clause_id in impact.clause_ids[:4]:
            clause = clauses.get(clause_id)
            if clause:
                pieces.append(f"[{clause.clause_id}] section={' > '.join(clause.section_path[-3:])}\n{clause.text}")
        block = (f"[IMPACT {impact.impact_id}] status={impact.impact_status} "
                 f"contract={impact.contract_version_id} "
                 f"reason={impact.impact_reason[:400]}\n" + "\n".join(pieces))
        if sum(len(item) for item in lines) + len(block) > limit:
            break
        lines.append(block)
    return "\n\n".join(lines)


def _fallback_local(impacts: list[ImpactCandidate], requirements: list[PolicyRequirement],
                    reason: str) -> list[LocalGuideCandidate]:
    result: list[LocalGuideCandidate] = []
    for impact in impacts:
        requirement = next((item for item in requirements if item.requirement_id == impact.requirement_id), None)
        local_id = stable_id("LG", impact.impact_id, "fallback", length=20)
        result.append(LocalGuideCandidate(
            local_id=local_id, impact_ids=[impact.impact_id],
            requirement_ids=[impact.requirement_id],
            needs_modification="uncertain",
            business_goal=requirement.requirement if requirement else "待人工复核",
            applicability="模型未返回可验证候选，需人工判断。",
            conditions=requirement.conditions if requirement else [],
            exceptions=requirement.exceptions if requirement else [],
            old_text_patterns=[impact.source_text[:600]] if impact.source_text else [],
            new_text="", new_text_origin="model_drafted", notes=reason,
            payload={"fallback": True},
        ))
    return result


def _author_group(router, group, reqs, requirement_map, clauses, config):
    context = ("[REQUIREMENT]\n" + _requirement_context(reqs) +
               "\n\n[IMPACTS]\n" + _impact_context(group, clauses, config.local_max_chars))
    try:
        result = router.call(task_type="guide_local_candidate", bounded_context=context,
                             response_schema=LOCAL_CANDIDATE_SCHEMA,
                             instruction=LOCAL_CANDIDATE_INSTRUCTION,
                             prompt_version=LOCAL_CANDIDATE_VERSION,
                             role="guide_author")
    except Exception as exc:
        return _fallback_local(group, reqs, f"local_candidate_model_failed:{type(exc).__name__}"), 0
    group_ids = {item.impact_id for item in group}
    produced: set[str] = set()
    candidates: list[LocalGuideCandidate] = []
    for index, item in enumerate(result.value.get("candidates") or []):
        ids = [str(value) for value in item.get("impact_ids") or [] if str(value) in group_ids]
        if not ids:
            continue
        produced.update(ids)
        local_id = stable_id("LG", *sorted(ids), index, length=20)
        requirement_ids = unique(
            [str(value) for value in item.get("requirement_ids") or []
             if str(value) in requirement_map] or
            [impact.requirement_id for impact in group
             if impact.impact_id in ids and impact.requirement_id in requirement_map])
        first_clause = clauses.get(ids[0]) if ids else None
        new_text = str(item.get("new_text") or "")
        origin = str(item.get("new_text_origin") or "model_drafted")
        relation = str(item.get("clause_relation") or "same_rule")
        needs_modification = str(item.get("needs_modification") or "uncertain")
        if relation != "same_rule":
            needs_modification = "no"
        if origin == "regulation_verbatim" and new_text and not any(
                compact_for_match(new_text) in compact_for_match(req.source_quote)
                or compact_for_match(new_text) in compact_for_match(req.requirement)
                for req in reqs):
            origin = "model_drafted"
        candidates.append(LocalGuideCandidate(
            local_id=local_id, impact_ids=sorted(set(ids)),
            requirement_ids=requirement_ids,
            section=(first_clause.section_path[0] if first_clause and first_clause.section_path else ""),
            needs_modification=needs_modification,
            business_goal=str(item.get("business_goal") or ""),
            semantic_changes=[str(value) for value in item.get("semantic_changes") or []],
            applicability=str(item.get("applicability") or ""),
            conditions=[str(value) for value in item.get("conditions") or []],
            exceptions=[str(value) for value in item.get("exceptions") or []],
            old_text_patterns=[str(value) for value in item.get("old_text_patterns") or []],
            new_text=new_text,
            new_text_origin=origin,
            notes=str(item.get("notes") or ""),
            payload={"raw": item, "clause_relation": relation},
        ))
    missing = [item for item in group if item.impact_id not in produced]
    if missing:
        candidates.extend(_fallback_local(missing, reqs, "model_omitted_impact"))
    return candidates, 1


def build_local_candidates(router, requirements: list[PolicyRequirement],
                           impacts: list[ImpactCandidate], clauses: dict[str, ClauseUnit],
                           config: AuthoringConfig | None = None,
                           *, max_workers: int = 4) -> tuple[list[LocalGuideCandidate], int]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    config = config or AuthoringConfig()
    requirement_map = {item.requirement_id: item for item in requirements}
    groups = _group_impacts([item for item in impacts if item.impact_status in {"definite", "possible"}],
                            clauses, config)
    candidates: list[LocalGuideCandidate] = []
    calls = 0
    if not groups:
        return [], 0
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(groups)))) as executor:
        futures = []
        for group in groups:
            reqs = [requirement_map[item.requirement_id] for item in group
                    if item.requirement_id in requirement_map]
            reqs = list({item.requirement_id: item for item in reqs}.values())
            futures.append(executor.submit(_author_group, router, group, reqs,
                                          requirement_map, clauses, config))
        for future in as_completed(futures):
            values, used = future.result()
            candidates.extend(values)
            calls += used
    requirement_map = {item.requirement_id: item for item in requirements}
    for candidate in candidates:
        _normalise_direct_sale_candidate(candidate, requirement_map)
    candidates.sort(key=lambda item: item.local_id)
    return candidates, calls


@dataclass
class FamilyResult:
    families: list[dict[str, Any]]
    calls: int


def _candidate_signature(item: LocalGuideCandidate) -> set[str]:
    return _signature(" ".join([item.business_goal, item.instruction if hasattr(item, "instruction") else "",
                                item.applicability, item.new_text]))


def _cluster_locals(candidates: list[LocalGuideCandidate], config: AuthoringConfig) -> list[list[LocalGuideCandidate]]:
    buckets: dict[tuple, list[LocalGuideCandidate]] = {}
    for item in candidates:
        # Merge across contract versions and requirement overlaps within the
        # same section; the model merge step decides whether the business
        # content is genuinely the same.
        buckets.setdefault((tuple(sorted(item.requirement_ids)), item.section, item.new_text_origin),
                           []).append(item)
    clusters: list[list[LocalGuideCandidate]] = []
    for bucket in buckets.values():
        remaining = list(bucket)
        while remaining:
            seed = remaining.pop(0)
            seed_sig = _signature(" ".join([seed.business_goal, seed.applicability, seed.new_text,
                                            " ".join(seed.semantic_changes)]))
            cluster = [seed]
            for candidate in list(remaining):
                sig = _signature(" ".join([candidate.business_goal, candidate.applicability,
                                           candidate.new_text, " ".join(candidate.semantic_changes)]))
                if _jaccard(seed_sig, sig) >= config.merge_similarity:
                    cluster.append(candidate)
                    remaining.remove(candidate)
                if len(cluster) >= config.merge_max_members:
                    break
            for start in range(0, len(cluster), config.merge_max_members):
                clusters.append(cluster[start:start + config.merge_max_members])
    return clusters


def _deterministic_family(cluster: list[LocalGuideCandidate], requirements: dict[str, PolicyRequirement]) -> dict[str, Any]:
    first = cluster[0]
    req_ids = merged = unique([value for item in cluster for value in item.requirement_ids])
    impact_ids = unique([value for item in cluster for value in item.impact_ids])
    section = ""
    requirement_text = "；".join(requirements[value].requirement for value in req_ids if value in requirements)
    family_id = stable_id("CF", *sorted(item.local_id for item in cluster), length=20)
    return {
        "family_id": family_id, "local_ids": [item.local_id for item in cluster],
        "requirement_ids": req_ids, "impact_ids": impact_ids,
        "title": requirement_text[:80] or first.business_goal[:80] or "候选修改指引",
        "section": section, "business_requirement": first.business_goal or requirement_text,
        "instruction": first.business_goal or first.applicability,
        "applicability": first.applicability,
        "conditions": merge_strings(*[item.conditions for item in cluster]),
        "exceptions": merge_strings(*[item.exceptions for item in cluster]),
        "old_text_patterns": merge_strings(*[item.old_text_patterns for item in cluster]),
        "new_text": first.new_text, "new_text_origin": first.new_text_origin,
        "merge_rationale": "确定性相似度聚类；未强制合并业务条件不同的候选。",
        "merge_method": "deterministic",
    }


def induce_families(router, candidates: list[LocalGuideCandidate],
                    requirements: list[PolicyRequirement],
                    clauses: dict[str, ClauseUnit],
                    config: AuthoringConfig | None = None) -> FamilyResult:
    config = config or AuthoringConfig()
    requirement_map = {item.requirement_id: item for item in requirements}
    clusters = _cluster_locals(candidates, config)
    families: list[dict[str, Any]] = []
    calls = 0
    for cluster in clusters:
        if len(cluster) == 1:
            families.append(_deterministic_family(cluster, requirement_map))
            continue
        context = "[LOCAL_CANDIDATES]\n" + "\n\n".join(
            f"[{item.local_id}] requirements={item.requirement_ids}\n"
            f"needs_modification={item.needs_modification}\n"
            f"business_goal={item.business_goal}\n"
            f"semantic_changes={item.semantic_changes}\n"
            f"applicability={item.applicability}\nconditions={item.conditions}\nexceptions={item.exceptions}\n"
            f"old={item.old_text_patterns}\nnew={item.new_text}\norigin={item.new_text_origin}"
            for item in cluster)
        try:
            result = router.call(task_type="guide_merge", bounded_context=context,
                                 response_schema=MERGE_SCHEMA, instruction=MERGE_INSTRUCTION,
                                 prompt_version=MERGE_VERSION, role="guide_author")
            calls += 1
        except Exception:
            families.append(_deterministic_family(cluster, requirement_map))
            continue
        expected = {item.local_id for item in cluster}
        produced: set[str] = set()
        for index, item in enumerate(result.value.get("families") or []):
            local_ids = [str(value) for value in item.get("local_ids") or []
                         if str(value) in expected and str(value) not in produced]
            if not local_ids:
                continue
            produced.update(local_ids)
            members = [value for value in cluster if value.local_id in local_ids]
            req_ids = unique([value for member in members for value in member.requirement_ids])
            impact_ids = unique([value for member in members for value in member.impact_ids])
            families.append({
                "family_id": stable_id("CF", *sorted(local_ids), index, length=20),
                "local_ids": sorted(set(local_ids)), "requirement_ids": req_ids,
                "impact_ids": impact_ids,
                "title": str(item.get("title") or "候选修改指引"),
                "section": str(item.get("section") or ""),
                "business_requirement": str(item.get("business_requirement") or ""),
                "instruction": str(item.get("instruction") or ""),
                "applicability": str(item.get("applicability") or ""),
                "conditions": [str(value) for value in item.get("conditions") or []],
                "exceptions": [str(value) for value in item.get("exceptions") or []],
                "old_text_patterns": [str(value) for value in item.get("old_text_patterns") or []],
                "new_text": str(item.get("new_text") or ""),
                "new_text_origin": str(item.get("new_text_origin") or "model_drafted"),
                "merge_rationale": str(item.get("merge_rationale") or ""),
                "merge_method": "model",
            })
        missing = [member for member in cluster if member.local_id not in produced]
        if missing:
            families.append(_deterministic_family(missing, requirement_map))
    for family in families:
        _normalise_direct_sale_family(family, requirement_map)
    return FamilyResult(families=families, calls=calls)


def _dedupe_families(families: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple, dict[str, Any]] = {}
    for family in families:
        key = (tuple(sorted(family.get("requirement_ids") or [])),
               compact_for_match(family.get("new_text") or ""),
               compact_for_match(family.get("instruction") or ""))
        if key not in merged:
            merged[key] = dict(family)
            continue
        target = merged[key]
        target["impact_ids"] = unique((target.get("impact_ids") or []) + (family.get("impact_ids") or []))
        target["local_ids"] = unique((target.get("local_ids") or []) + (family.get("local_ids") or []))
        target["old_text_patterns"] = unique((target.get("old_text_patterns") or [])
                                             + (family.get("old_text_patterns") or []))
        target["conditions"] = unique((target.get("conditions") or []) + (family.get("conditions") or []))
        target["exceptions"] = unique((target.get("exceptions") or []) + (family.get("exceptions") or []))
        target["deduped_family_ids"] = unique((target.get("deduped_family_ids") or [])
                                              + [family.get("family_id", "")])
    return list(merged.values())


def families_to_guide_items(families: list[dict[str, Any]],
                            clauses: dict[str, ClauseUnit],
                            impacts: dict[str, ImpactCandidate]) -> list[GuideItem]:
    items: list[GuideItem] = []
    for family in _dedupe_families(families):
        evidence_ids = []
        for impact_id in family.get("impact_ids") or []:
            impact = impacts.get(impact_id)
            if not impact:
                continue
            evidence_ids.append(impact_id)
            evidence_ids.extend(impact.clause_ids)
        section = family.get("section") or ""
        if not section:
            sections = []
            for impact_id in family.get("impact_ids") or []:
                impact = impacts.get(impact_id)
                if impact and impact.clause_ids:
                    clause = clauses.get(impact.clause_ids[0])
                    if clause and clause.section_path:
                        sections.append(clause.section_path[0])
            section = sections[0] if sections else ""
        requirement_ids = list(family.get("requirement_ids") or [])
        if not requirement_ids:
            requirement_ids = unique(
                impacts[impact_id].requirement_id for impact_id in family.get("impact_ids") or []
                if impact_id in impacts)
        items.append(GuideItem(
            guide_item_id="G-" + family["family_id"].split("-", 1)[-1],
            requirement_ids=requirement_ids,
            impact_ids=list(family.get("impact_ids") or []),
            clause_family_ids=[family["family_id"]],
            section=section,
            title=family.get("title") or "候选修改指引",
            business_requirement=family.get("business_requirement") or "",
            instruction=family.get("instruction") or "",
            applicability=family.get("applicability") or "",
            conditions=list(family.get("conditions") or []),
            exceptions=list(family.get("exceptions") or []),
            old_text_patterns=list(family.get("old_text_patterns") or []),
            new_text=family.get("new_text") or "",
            new_text_origin=family.get("new_text_origin") or "model_drafted",
            evidence_ids=unique(evidence_ids),
            metadata={"family_id": family["family_id"],
                      "local_ids": family.get("local_ids") or [],
                      "merge_rationale": family.get("merge_rationale") or ""},
        ))
    return items
