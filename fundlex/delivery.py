"""User-facing delivery summary (plan §33).

Internal codes stay in ``unresolved`` for debugging; the user sees one of three
states and, for a partial delivery, the rule/location plus a business-language
reason.  The projection never invents success: it reads ``delivery_status`` and the
obligation ledger, both fail-closed.
"""
from __future__ import annotations

from typing import Any, Mapping

COMPLETE = "complete"
COMPLETE_WITH_NOTICES = "complete_with_notices"
PARTIAL = "partial"
EXCLUDED = "excluded"

_BUSINESS_REASONS = (
    ("OPEN_OBLIGATION", "该规则要求修改的条款未能在合同中定位，或修改未完成"),
    ("APPLICABILITY_UNKNOWN", "无法从合同原文确认该规则是否适用"),
    ("RECALL_FACT", "合同中的费率或份额类别事实无法从原文可靠确认"),
    ("FUND_TYPE", "产品类型无法从合同原文可靠确认"),
    ("CLAIM_REPLAY", "已生成的修改未能在最终文档中完整复核"),
    ("CLAIM_OPERATION", "该条款的自动修改未能在最终文档中完成，系统已保留原文"),
    ("VALIDATION", "修改未通过保护性校验"),
    ("TARGET", "合同中未能定位到该规则对应的目标条款"),
    ("COMPOSE", "复杂条款自动改写未能通过独立复核"),
    ("OVERLAP", "同一段落的多项修改无法安全合并"),
    ("COVERAGE", "规则覆盖检查发现未处理的缺口"),
    ("SWEEP", "全文查漏仍发现未完成的修改"),
    ("AUDIT", "独立复核认为修改尚未完成"),
)

_REASON_ORDER = ("OPEN_OBLIGATION", "APPLICABILITY", "RECALL_FACT", "FUND_TYPE",
                 "CLAIM_REPLAY", "CLAIM_OPERATION", "VALIDATION", "OVERLAP", "COMPOSE",
                 "AUDIT", "SWEEP", "COVERAGE", "TARGET")

_COVERAGE_SUCCESS_STATES = {
    "SATISFIED", "ARTIFACT_VERIFIED", "ALREADY_SATISFIED", "NOT_APPLICABLE",
}


def _completion_blockers(report: Mapping[str, Any]) -> list[str]:
    """Return proof inconsistencies that must keep a delivery partial.

    The worker normally writes ``unresolved`` from the same ledger.  The summary is
    also consumed for old reports and API payloads, so it must not trust a lone
    ``delivery_status=complete`` when a later projection or replay says otherwise.
    UNKNOWN and CONFLICT are deliberately treated as open states.
    """
    blockers: list[str] = []
    if report.get("unresolved"):
        blockers.append("unresolved")

    coverage = report.get("operation_coverage")
    if isinstance(coverage, Mapping):
        entries = coverage.get("entries") or ()
        if any(str(item.get("state") or "").upper() not in _COVERAGE_SUCCESS_STATES
               for item in entries if isinstance(item, Mapping)):
            blockers.append("coverage_unresolved")

    obligations = report.get("obligations")
    records = obligations.get("records") if isinstance(obligations, Mapping) else ()
    if any(str(item.get("completion") or "").upper() not in _COVERAGE_SUCCESS_STATES
           for item in records if isinstance(item, Mapping)):
        blockers.append("obligation_unresolved")

    replay = report.get("artifact_claim_replay") or report.get("claim_replay")
    if isinstance(replay, Mapping):
        from .generation.effects import effect_proof_passed
        if replay.get("verified") is False:
            blockers.append("claim_replay_failed")
        replay_records = replay.get("obligations") or {}
        if isinstance(replay_records, Mapping) and any(
                not effect_proof_passed(
                    item,
                    operation_id=str(item.get("operation_id") or ""),
                    obligation_id=str(item.get("obligation_id") or obligation_id),
                )
                or str(item.get("state") or "").upper() != "PASS"
                or str(item.get("artifact_status") or "").upper()
                in {"UNKNOWN", "CONFLICT", "UNPROVEN", "WRONG_EFFECT",
                    "MISSING_EFFECT", "RESIDUAL_OLD_TEXT"}
                or any(str(site.get("state") or "").upper()
                       != "PASS"
                       or str(site.get("artifact_status") or "").upper()
                       in {"UNKNOWN", "CONFLICT", "UNPROVEN", "WRONG_EFFECT",
                           "MISSING_EFFECT", "RESIDUAL_OLD_TEXT"}
                       for site in item.get("site_effects") or ()
                       if isinstance(site, Mapping))
                for obligation_id, item in replay_records.items()
                if isinstance(item, Mapping)):
            blockers.append("claim_operation_unresolved")
    return blockers


def business_reason(item: Mapping[str, Any]) -> str:
    text = " ".join(str(item.get(key) or "") for key in
                    ("code", "reason", "issue", "kind", "status"))
    for marker in _REASON_ORDER:
        if marker in text:
            for prefix, message in _BUSINESS_REASONS:
                if prefix == marker:
                    return message
    return "该规则的修改未能可靠完成，需要人工确认"


def _rule_groups(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    guide = report.get("guide") if isinstance(report.get("guide"), Mapping) else {}
    groups = guide.get("groups") if isinstance(guide.get("groups"), list) else []
    return {str(group.get("rule_id") or ""): group for group in groups
            if isinstance(group, Mapping) and group.get("rule_id")}


def _issue_quote(report: Mapping[str, Any], rule_id: str, location: str) -> tuple[str, bool]:
    """Best source quote for a user to find the clause in Word.

    Prefer the exact unresolved site.  A sibling target of the same rule is still
    useful as a wording reference, but is explicitly marked as not the same site.
    """
    targets = report.get("targets") if isinstance(report.get("targets"), list) else []
    exact = next((target for target in targets
                  if isinstance(target, Mapping)
                  and str(target.get("rule_id") or "") == rule_id
                  and str(target.get("location") or "") == location
                  and str(target.get("quote") or "")), None)
    if exact is not None:
        return str(exact.get("quote") or ""), True
    sibling = next((target for target in targets
                    if isinstance(target, Mapping)
                    and str(target.get("rule_id") or "") == rule_id
                    and str(target.get("quote") or "")), None)
    return (str(sibling.get("quote") or ""), False) if sibling is not None else ("", False)


def _issues(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    groups = _rule_groups(report)
    for item in report.get("unresolved") or []:
        if not isinstance(item, Mapping):
            continue
        rule_id = str(item.get("rule_id") or "")
        location = str(item.get("location") or "")
        reason = business_reason(item)
        key = (rule_id, location, reason)
        if key in seen:
            continue
        seen.add(key)
        group = groups.get(rule_id) or {}
        title = str(group.get("title") or "").strip()
        section = str(group.get("section_hint") or "").strip()
        quote, exact_site = _issue_quote(report, rule_id, location)
        if exact_site:
            review_note = ("该规则未写入修订版，修订痕迹中不会出现本处；"
                           "请用 Word 搜索下面这段原文核对是否需要人工修改。")
        elif quote:
            review_note = ("该规则未写入修订版，修订痕迹中不会出现本处；"
                           f"请先到“{section or title or '对应章节'}”核对下面这段同类原文。")
        else:
            review_note = ("该规则未写入修订版，修订痕迹中不会出现本处；"
                           f"请到“{section or title or '对应章节'}”按指引要求人工核对。")
        issues.append({
            "rule_id": rule_id,
            "title": title or "未能自动修改的条款",
            "section": section,
            "location": location,
            "obligation_id": str(item.get("obligation_id") or ""),
            "business_reason": reason,
            "requirement": str(group.get("requirement") or "").strip(),
            "quote": quote,
            "quote_exact_site": exact_site,
            "review_note": review_note,
        })
    return issues


def build_user_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("delivery_status") or "")
    notices = list(report.get("business_notices") or [])
    if status == "excluded":
        return {"status": EXCLUDED, "headline": "该产品类型不在本次修改范围内",
                "issues": [], "notices": notices}
    issues = _issues(report)
    blockers = _completion_blockers(report)
    if status == "complete" and not issues and not blockers:
        if notices:
            return {"status": COMPLETE_WITH_NOTICES,
                    "headline": "修改完成，但有业务提示",
                    "issues": [], "notices": notices}
        return {"status": COMPLETE, "headline": "修改完成", "issues": [], "notices": []}
    if status == "complete" and blockers and not issues:
        issues = [{"rule_id": "", "title": "交付证明未收敛", "section": "",
                   "location": "", "obligation_id": "",
                   "business_reason": "交付证明仍包含未解决的操作或站点",
                   "requirement": "", "quote": "", "quote_exact_site": False,
                   "review_note": "请重新复核操作、站点和最终文档证明。"}]
    return {
        "status": PARTIAL,
        "headline": "部分修改无法可靠完成",
        "issues": issues,
        "notices": notices,
    }
