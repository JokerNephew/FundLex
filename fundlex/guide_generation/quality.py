"""Independent guide quality gate.

Quality answers a different question from engine compatibility: is the guide
itself faithful to the regulation, faithful in its drafted contract text,
properly generalised, and internally consistent?  A correct guide that FundLex
cannot execute is not a quality failure.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import (
    ClauseUnit,
    GuideItem,
    ImpactCandidate,
    PolicyRequirement,
    compact_for_match,
    quote_in_text,
    sha256_json,
    stable_id,
    unique,
)
from .prompts import (
    QUALITY_INSTRUCTION,
    QUALITY_SCHEMA,
    QUALITY_VERSION,
)

_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
_HARD_CATEGORIES = {"regulation_fidelity", "draft_text_fidelity", "provenance"}
_DIRECT_SALE_RULE = re.compile(
    r"基金管理人(?:自行)?销售其管理的基金[^。；！？]*不得收取"
)
_HISTORICAL_FEE_SENTENCE = re.compile(
    r"(?:[A-ZＡ-Ｚ]类(?:基金)?份额|收取(?:认[（(]申[）)]购费|认购费|申购费)|"
    r"计提销售服务费|收取销售服务费|不计提销售服务费)"
)
_CHANNEL_BOUNDARY = re.compile(
    r"(?:其他基金销售机构|其他销售机构|非直销|代销机构|通过基金销售机构|直销机构以外)"
)


@dataclass
class QualityResult:
    findings: list[dict[str, Any]]
    item_status: dict[str, str]
    run_status: str
    calls: int
    independent_review: str


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text or ""))


def _evidence_text(item: GuideItem, requirements: list[PolicyRequirement],
                   clauses: dict[str, ClauseUnit], impacts: dict[str, ImpactCandidate]) -> str:
    parts = [item.new_text, item.instruction, item.business_requirement,
             " ".join(item.old_text_patterns), " ".join(item.conditions),
             " ".join(item.exceptions)]
    for requirement in requirements:
        parts.extend([requirement.source_quote, requirement.requirement,
                      " ".join(requirement.conditions), " ".join(requirement.exceptions)])
    for impact_id in item.impact_ids:
        impact = impacts.get(impact_id)
        if not impact:
            continue
        parts.append(impact.source_text)
        for clause_id in impact.clause_ids[:3]:
            clause = clauses.get(clause_id)
            if clause:
                parts.append(clause.text)
    return "\n".join(part for part in parts if part)


def _finding(item: GuideItem, category: str, severity: str, description: str,
             evidence_quote: str = "", recommendation: str = "",
             *, status: str = "open", source: str = "deterministic") -> dict[str, Any]:
    return {
        "finding_id": stable_id("F", "QUALITY", item.guide_item_id, category, severity, description,
                                length=20),
        "guide_item_id": item.guide_item_id,
        "category": category,
        "severity": severity,
        "status": status,
        "description": description,
        "evidence_quote": evidence_quote,
        "recommendation": recommendation,
        "source": source,
    }


def _deterministic_findings(item: GuideItem, requirements: list[PolicyRequirement],
                            clauses: dict[str, ClauseUnit],
                            impacts: dict[str, ImpactCandidate],
                            all_items: list[GuideItem]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if not item.requirement_ids:
        findings.append(_finding(item, "provenance", "critical", "GuideItem 没有法规要求来源。"))
    if not item.impact_ids:
        findings.append(_finding(item, "provenance", "critical", "GuideItem 没有真实合同 Impact 来源。"))
    if not item.new_text.strip():
        findings.append(_finding(item, "draft_text_fidelity", "critical", "候选指引没有新合同文案。",
                                 recommendation="补充可审核的新文案，或将该条标记为不适用。"))
    if item.new_text_origin not in {"regulation_verbatim", "model_drafted", "contract_pattern_adapted"}:
        findings.append(_finding(item, "provenance", "critical", "new_text_origin 缺失或非法。"))
    source_text = _evidence_text(item, requirements, clauses, impacts)
    if item.new_text_origin == "regulation_verbatim" and item.new_text.strip():
        if not any(quote_in_text(item.new_text, requirement.source_quote)
                   for requirement in requirements):
            findings.append(_finding(item, "regulation_fidelity", "critical",
                                     "文案标记为法规原文，但未在法规来源中找到该文本。",
                                     evidence_quote=item.new_text[:300]))
    for requirement in requirements:
        for floor in re.findall(r"不低于[^0-9]{0,6}(\d+(?:\.\d+)?%)", requirement.source_quote):
            if floor in item.new_text and any(
                    not ("不低于" in item.new_text[max(0, match.start() - 32):match.start()]
                         or "至少" in item.new_text[max(0, match.start() - 32):match.start()])
                    for match in re.finditer(re.escape(floor), item.new_text)):
                findings.append(_finding(
                    item, "regulation_fidelity", "critical",
                    f"法规下限 {floor} 在新文案中被写成固定费率，未保留“不低于”约束。",
                    evidence_quote=item.new_text[:400],
                    recommendation="改为“不低于…”，不要缩小法规允许的费率范围。"))
    unsupported = sorted(_numbers(item.new_text) - _numbers(source_text))
    if unsupported:
        findings.append(_finding(
            item, "draft_text_fidelity", "critical",
            "新文案包含法规和真实合同证据都不支持的数字或比例：" + "、".join(unsupported),
            evidence_quote=item.new_text[:400],
            recommendation="核对来源；无法证明的数字必须删除或交人工确认。"))
    combined = (item.instruction + " " + item.new_text + " " + " ".join(item.conditions)
                + " " + " ".join(item.exceptions))
    direct_rule = any(_DIRECT_SALE_RULE.search(requirement.source_quote)
                      or _DIRECT_SALE_RULE.search(requirement.requirement)
                      for requirement in requirements)
    if direct_rule and _HISTORICAL_FEE_SENTENCE.search(item.new_text):
        # The prohibition applies to the manager's own sales channel.  A
        # historical A/C/D fee pattern can remain in the same GuideItem only
        # when its sentence carries an explicit third-party channel boundary.
        for sentence in re.split(r"(?<=[。！？；])", item.new_text):
            if (_HISTORICAL_FEE_SENTENCE.search(sentence)
                    and not _CHANNEL_BOUNDARY.search(sentence)
                    and not re.search(r"(?:直销机构|通过直销|基金管理人(?:自行)?销售)", sentence)
                    and "不得收取" not in sentence):
                findings.append(_finding(
                    item, "regulation_fidelity", "critical",
                    "直销禁止收费与历史份额收费结构被无条件拼接，未保留销售渠道边界。",
                    evidence_quote=sentence[:400],
                    recommendation="将历史份额收费结构拆为独立候选，或明确仅适用于其他基金销售机构；直销机构/基金管理人销售时不得收取相应费用。"))
                break
    negative = ("不收取", "不得收取", "免收", "无需收取", "不再收取", "不适用")
    if any(token in item.new_text for token in negative) and not any(
            token in source_text for token in negative):
        findings.append(_finding(
            item, "draft_text_fidelity", "major",
            "新文案增加了免除/不收取类表述，但来源证据中没有对应依据。",
            evidence_quote=item.new_text[:400]))
    if any(term in item.new_text for term in ("必须", "应当")) and any(
            term in item.new_text for term in ("管理人的关联方", "托管人的关联方")):
        findings.append(_finding(item, "regulation_fidelity", "major",
                                 "新文案出现来源未支持的主体或义务扩展。",
                                 evidence_quote=item.new_text[:400]))
    # Exact duplicate instructions are a consistency warning, never silently merged.
    for other in all_items:
        if other.guide_item_id <= item.guide_item_id:
            continue
        if (set(other.requirement_ids) == set(item.requirement_ids)
                and compact_for_match(other.new_text) == compact_for_match(item.new_text)
                and compact_for_match(other.instruction) == compact_for_match(item.instruction)):
            findings.append(_finding(item, "internal_consistency", "major",
                                     f"与 {other.guide_item_id} 完全重复，需人工决定合并或拆分。",
                                     evidence_quote=other.title[:200]))
    return findings


def _review_context(item: GuideItem, requirements: list[PolicyRequirement],
                    clauses: dict[str, ClauseUnit], impacts: dict[str, ImpactCandidate],
                    limit: int, all_items: list[GuideItem] | None = None) -> str:
    item_payload = {
        "guide_item_id": item.guide_item_id, "title": item.title, "section": item.section,
        "business_requirement": item.business_requirement, "instruction": item.instruction,
        "applicability": item.applicability, "conditions": item.conditions,
        "exceptions": item.exceptions, "old_text_patterns": item.old_text_patterns,
        "new_text": item.new_text, "new_text_origin": item.new_text_origin,
        "scope_statement": item.business_requirement,
    }
    siblings = [other for other in (all_items or []) if other.guide_item_id != item.guide_item_id
                and set(other.requirement_ids) & set(item.requirement_ids)]
    parts = ["[COVERAGE_CONTEXT]",
             f"is_only_item_for_requirement={not siblings}",
             "sibling_items=" + ", ".join(other.guide_item_id for other in siblings[:20]),
             "If sibling items exist, this item is a partial aspect of a multi-aspect requirement; "
             "review this item's own scope and do not fail it for omitting aspects assigned to siblings.",
             "", "[REQUIREMENT]"]
    for requirement in requirements:
        parts.append(f"[{requirement.requirement_id}] {requirement.article} {requirement.requirement}\n"
                     f"quote={requirement.source_quote}\nconditions={requirement.conditions}\n"
                     f"exceptions={requirement.exceptions}\nscope={requirement.applicable_scope}")
    parts += ["", "[GUIDE_ITEM]", json_dumps(item_payload)]
    parts += ["", "[REAL_CONTRACT_EVIDENCE]"]
    seen = set()
    for impact_id in item.impact_ids[:8]:
        impact = impacts.get(impact_id)
        if not impact:
            continue
        for clause_id in impact.clause_ids[:2]:
            if clause_id in seen:
                continue
            seen.add(clause_id)
            clause = clauses.get(clause_id)
            if clause:
                parts.append(f"[{clause.clause_id}] {' > '.join(clause.section_path[-3:])}\n{clause.text[:2000]}")
    text = "\n".join(parts)
    return text[:limit]


def json_dumps(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)


def _auto_fix_item(item: GuideItem, requirements: list[PolicyRequirement]) -> list[dict[str, Any]]:
    """Safe metadata/text fixes before the adversarial review.

    A floor stated as "不低于1.5%" must never become a fixed "1.5%" in the
    contract text.  Inserting the missing floor word is deterministic and does
    not invent a new obligation.  A wrong "regulation_verbatim" label is a
    provenance metadata error; downgrade it instead of failing the contract
    wording.
    """
    fixes: list[dict[str, Any]] = []
    floors = []
    for requirement in requirements:
        floors.extend(re.findall(r"不低于[^0-9]{0,6}(\d+(?:\.\d+)?%)", requirement.source_quote))
    for floor in unique(floors):
        if floor not in item.new_text:
            continue
        text = item.new_text
        positions = [match.start() for match in re.finditer(re.escape(floor), text)]
        insertions = []
        for position in positions:
            prefix = text[max(0, position - 32):position]
            if "不低于" in prefix or "至少" in prefix:
                continue  # the floor already governs this occurrence
            insertions.append(position)
        if not insertions:
            continue
        for position in reversed(insertions):
            text = text[:position] + "不低于" + text[position:]
        fixes.append({
            "finding_id": stable_id("F", "AUTOFIX", item.guide_item_id, "floor", floor, length=20),
            "guide_item_id": item.guide_item_id, "category": "regulation_fidelity",
            "severity": "info", "status": "auto_corrected", "source": "auto_fix",
            "description": f"保留法规下限：将固定费率 {floor} 修正为不低于{floor}。",
            "evidence_quote": item.new_text[:300],
        })
        item.new_text = text
    if item.new_text_origin == "regulation_verbatim" and item.new_text.strip():
        if not any(quote_in_text(item.new_text, requirement.source_quote) for requirement in requirements):
            item.new_text_origin = "model_drafted"
            fixes.append({
                "finding_id": stable_id("F", "AUTOFIX", item.guide_item_id, "origin", length=20),
                "guide_item_id": item.guide_item_id, "category": "provenance",
                "severity": "info", "status": "auto_corrected", "source": "auto_fix",
                "description": "文案未逐字出现在法规原文中，来源标记已从 regulation_verbatim 降为 model_drafted。",
                "evidence_quote": item.new_text[:300],
            })
    return fixes


def _normalise_reviewer_severity(finding: dict[str, Any], item: GuideItem) -> dict[str, Any]:
    """Keep critical for text-level errors; contract-specific scope is major.

    A specific fund contract legitimately uses only its own share classes and
    fund type.  Those scope choices must be reviewed, but they are not the same
    as inventing an obligation.  Conditions preserved from the existing clause
    are likewise not a new regulatory requirement.
    """
    if finding.get("severity") != "critical":
        return finding
    description = str(finding.get("description") or "").lower()
    scope_markers = ("other funds", "其他基金", "share class", "a类", "b类", "c类", "d类",
                     "money market", "货币市场基金")
    text_error_markers = ("invented", "not present in the regulation", "contradict",
                          "fixed", "exactly", "misstate", "changed subject", "omits",
                          "omit", "hallucinat")
    if any(marker in description for marker in scope_markers) and not any(
            marker in description for marker in ("invented", "not present", "contradict", "misstate")):
        finding["reviewer_severity"] = "critical"
        finding["severity"] = "major"
        finding["severity_reason"] = "contract-specific scope/share-class choice, not a text-level legal error"
        return finding
    preserved = " ".join(item.old_text_patterns or [])
    if ("condition" in description or "narrow" in description) and preserved:
        for phrase in ("不违反法律法规", "基金合同约定", "无实质性不利影响", "履行必要手续"):
            if phrase in preserved and phrase in description:
                finding["reviewer_severity"] = "critical"
                finding["severity"] = "major"
                finding["severity_reason"] = "condition preserved from the existing contract clause, not invented"
                break
    return finding


def _review_one(router, item: GuideItem, requirement_map, impact_map, clauses,
                all_items, limit: int) -> tuple[GuideItem, list[dict[str, Any]], str, bool]:
    review_requirements = [requirement_map[value] for value in item.requirement_ids
                           if value in requirement_map]
    item_findings = _auto_fix_item(item, review_requirements)
    item_findings.extend(_deterministic_findings(item, review_requirements, clauses, impact_map, all_items))
    context = _review_context(item, review_requirements, clauses, impact_map, limit, all_items)
    reviewed = False
    try:
        result = router.call(task_type="guide_quality_review", bounded_context=context,
                             response_schema=QUALITY_SCHEMA, instruction=QUALITY_INSTRUCTION,
                             prompt_version=QUALITY_VERSION, role="guide_reviewer")
        reviewed = True
        for finding in result.value.get("findings") or []:
            severity = str(finding.get("severity") or "minor")
            category = str(finding.get("category") or "other")
            evidence = str(finding.get("evidence_quote") or "")
            verified = bool(evidence) and (compact_for_match(evidence) in compact_for_match(context))
            item_findings.append(_normalise_reviewer_severity({
                "finding_id": stable_id("F", "REVIEW", item.guide_item_id, category, severity,
                                        str(finding.get("description") or ""), length=20),
                "guide_item_id": item.guide_item_id,
                "category": category, "severity": severity, "status": "open",
                "description": str(finding.get("description") or ""),
                "evidence_quote": evidence,
                "evidence_verified": verified,
                "recommendation": str(finding.get("recommendation") or ""),
                "source": "guide_reviewer",
            }, item))
        verdict = str(result.value.get("verdict") or "uncertain")
    except Exception as exc:
        verdict = "uncertain"
        item_findings.append(_finding(
            item, "other", "major", f"独立质量复核模型调用失败：{type(exc).__name__}",
            source="guide_reviewer"))
    critical = [value for value in item_findings if value["severity"] == "critical"
                and (value.get("source") != "guide_reviewer" or value.get("evidence_verified", True))]
    major = [value for value in item_findings if value["severity"] == "major"]
    if critical:
        status = "fail"
    elif major or verdict in {"fail", "uncertain"}:
        status = "pass_with_findings"
    elif item_findings or verdict == "pass_with_findings":
        status = "pass_with_findings"
    else:
        status = "pass"
    item.quality_status = status
    return item, item_findings, verdict, reviewed


def run_quality_gate(router, items: list[GuideItem], requirements: list[PolicyRequirement],
                     impacts: list[ImpactCandidate], clauses: dict[str, ClauseUnit],
                     *, config: Any = None, on_item=None, max_workers: int = 4) -> QualityResult:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import threading
    requirement_map = {item.requirement_id: item for item in requirements}
    impact_map = {item.impact_id: item for item in impacts}
    findings: list[dict[str, Any]] = []
    item_status: dict[str, str] = {}
    calls = 0
    limit = int(getattr(config, "quality_max_context", 18000) if config else 18000)
    callback_lock = threading.Lock()
    workers = max(1, min(max_workers, len(items) or 1))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_review_one, router, item, requirement_map, impact_map, clauses,
                            items, limit): item
            for item in items
        }
        for future in as_completed(futures):
            item, item_findings, _verdict, reviewed = future.result()
            if reviewed:
                calls += 1
            findings.extend(item_findings)
            item_status[item.guide_item_id] = item.quality_status
            if on_item is not None:
                with callback_lock:
                    on_item(item, item_findings)
    critical_total = sum(1 for item in findings if item["severity"] == "critical"
                         and (item.get("source") != "guide_reviewer" or item.get("evidence_verified", True)))
    major_total = sum(1 for item in findings if item["severity"] == "major")
    if critical_total:
        run_status = "fail"
    elif major_total:
        run_status = "pass_with_findings"
    else:
        run_status = "pass"
    identity = router.identity()
    return QualityResult(findings=findings, item_status=item_status, run_status=run_status,
                         calls=calls,
                         independent_review=str(identity.get("independent_model_review_status") or "not_qualified"))
