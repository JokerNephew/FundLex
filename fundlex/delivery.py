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
    ("VALIDATION", "修改未通过保护性校验"),
    ("TARGET", "合同中未能定位到该规则对应的目标条款"),
    ("COMPOSE", "复杂条款自动改写未能通过独立复核"),
    ("OVERLAP", "同一段落的多项修改无法安全合并"),
    ("COVERAGE", "规则覆盖检查发现未处理的缺口"),
    ("SWEEP", "全文查漏仍发现未完成的修改"),
    ("AUDIT", "独立复核认为修改尚未完成"),
)

_REASON_ORDER = ("OPEN_OBLIGATION", "APPLICABILITY", "RECALL_FACT", "FUND_TYPE",
                 "CLAIM_REPLAY", "VALIDATION", "OVERLAP", "COMPOSE", "TARGET",
                 "COVERAGE", "SWEEP", "AUDIT")


def business_reason(item: Mapping[str, Any]) -> str:
    text = " ".join(str(item.get(key) or "") for key in
                    ("code", "reason", "issue", "kind", "status"))
    for marker in _REASON_ORDER:
        if marker in text:
            for prefix, message in _BUSINESS_REASONS:
                if prefix == marker:
                    return message
    return "该规则的修改未能可靠完成，需要人工确认"


def _issues(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
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
        issues.append({"rule_id": rule_id, "location": location,
                       "obligation_id": str(item.get("obligation_id") or ""),
                       "business_reason": reason})
    return issues


def build_user_summary(report: Mapping[str, Any]) -> dict[str, Any]:
    status = str(report.get("delivery_status") or "")
    notices = list(report.get("business_notices") or [])
    if status == "excluded":
        return {"status": EXCLUDED, "headline": "该产品类型不在本次修改范围内",
                "issues": [], "notices": notices}
    issues = _issues(report)
    if status == "complete" and not issues:
        if notices:
            return {"status": COMPLETE_WITH_NOTICES,
                    "headline": "修改完成，但有业务提示",
                    "issues": [], "notices": notices}
        return {"status": COMPLETE, "headline": "修改完成", "issues": [], "notices": []}
    return {
        "status": PARTIAL,
        "headline": "部分修改无法可靠完成",
        "issues": issues,
        "notices": notices,
    }
