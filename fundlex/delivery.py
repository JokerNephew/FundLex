"""User-facing delivery summary (plan §33).

Internal codes stay in ``unresolved`` for debugging; the user sees one of three
states and, for a partial delivery, the rule/location plus a business-language
reason.  The projection never invents success: it reads ``delivery_status`` and the
obligation ledger, both fail-closed.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

COMPLETE = "complete"
COMPLETE_WITH_NOTICES = "complete_with_notices"
PARTIAL = "partial"
EXCLUDED = "excluded"
VERIFICATION_BLOCKED = "verification_blocked"

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

# Short, user-facing reasons for every failure class the engine can emit.  The
# order is specific-first: a code such as RECALL_TARGET_STRUCTURE must win over
# the generic TARGET marker.
_FAILURE_REASONS = (
    ("EXISTING_REVISION_UNSUPPORTED", "文件包含未接受的修订痕迹，请先接受所有修订或上传清理版"),
    ("DOCUMENT_PROTECTED", "文件受文档保护，无法写入修改"),
    ("INPUT_INTEGRITY_FAILED", "上传文件损坏或格式不受支持"),
    ("RECALL_TARGET_STRUCTURE", "目标段落含不可编辑结构（域、文本框或内容控件），无法写入修订"),
    ("RECALL_EDIT_OVERLAP", "同一段落的多项修改范围重叠，无法安全合并"),
    ("RECALL_TARGET_OPERATION_UNATTRIBUTED", "目标条款无法归属到具体规则操作"),
    ("RECALL_TARGET_OPERATION_NOT_APPLICABLE", "目标条款不适用于该规则分支"),
    ("RECALL_FACT_UNVERIFIED", "合同中的费率或份额类别事实无法从原文可靠确认"),
    ("RECALL_QUOTE_UNRESOLVED", "修改依据的原文引文未能在合同中定位"),
    ("MODEL_RETRY_EXHAUSTED", "模型调用多次失败，已停止重试"),
    ("MODEL_SCHEMA_INVALID", "模型返回格式不符合要求"),
    ("MODEL_OUTPUT_TRUNCATED", "模型输出被截断，未能完整返回"),
    ("MODEL_BUDGET_EXCEEDED", "模型调用预算已用尽"),
    ("MODEL_CALL_LIMIT", "模型调用次数已达上限"),
    ("MODEL_CONTEXT_LIMIT", "模型上下文不足，未能处理该条款"),
    ("GUIDE_NOT_CERTIFIED", "指引版本未通过认证"),
    ("RULESET_HASH_MISMATCH", "任务规则版本与当前规则不一致"),
    ("GUIDE_RULESET_HASH_MISMATCH", "指引与规则版本不一致"),
    ("RESIDUAL_OLD_TEXT", "修改后原条款仍然存在，未达到删除/替换效果"),
    ("EFFECT_SITE_UNPROVEN", "未能证明修改在最终文档中落到对应条款位置，该条款未完成"),
    ("CLAIM_EXECUTION_EFFECT_MISSING", "该条款的修改效果未在最终文档中体现"),
    ("CLAIM_PLANNED_EFFECT_MISSING", "修改计划要求的效果未在最终文档中体现"),
    ("CLAIM_OPERATION_NOT_PLANNED", "该条款未进入修改计划"),
    ("CLAIM_OPERATION_UNPROVEN", "该条款的修改未能在最终文档中证明"),
    ("CLAIM_NO_CHANGE_APPLIED", "该条款的修改没有实际写入文档"),
    ("LEDGER_EVIDENCE_UNBOUND", "存在无法归属到具体规则的证据"),
    ("AUDIT_NOT_COMPLETED", "独立复核未完成"),
    ("FINAL_MODEL_SWEEP_FINDING", "全文查漏仍发现未完成项"),
    ("FINAL_COVERAGE_UNRESOLVED", "规则覆盖检查发现未处理项"),
    ("FINAL_OPERATION_UNPROVEN", "规则操作未能在最终文档中证明"),
    ("SURVEY_QUOTE_UNRESOLVED", "补漏时引用的原文未能在合同中定位"),
    ("PROCESSING_FAILED", "处理过程异常，未能生成修改"),
    ("OUTPUT_WRITE_FAILED", "生成修改文件失败"),
    ("REPORT_WRITE_FAILED", "生成报告失败"),
    ("FROZEN_RUN_WRITE_FAILED", "保存运行记录失败"),
    ("VERIFICATION_BLOCKED", "验证暂未完成，等待恢复处理"),
    ("QUALIFICATION_FAILED", "合同不符合本次处理条件"),
    ("EXCLUDED", "产品类型不在本次修改范围内"),
)

_REASON_ORDER = ("OPEN_OBLIGATION", "APPLICABILITY", "RECALL_FACT", "FUND_TYPE",
                 "CLAIM_REPLAY", "CLAIM_OPERATION", "VALIDATION", "OVERLAP", "COMPOSE",
                 "AUDIT", "SWEEP", "COVERAGE", "TARGET")


def failure_reason(value: Any) -> str:
    """Concise Chinese explanation for an engine error code or reason string."""
    text = str(value or "")
    if not text:
        return ""
    for code, message in _FAILURE_REASONS:
        if code in text:
            return message
    return ""


_COVERAGE_SUCCESS_STATES = {
    "SATISFIED", "ARTIFACT_VERIFIED", "ALREADY_SATISFIED", "NOT_APPLICABLE",
}

# Codes that prove the artifact/delivery is incomplete even under review_assisted.
# New engine codes must never fall through to "complete with review items" merely
# because an older classifier did not know them.
_ALWAYS_BLOCKING_CODES = frozenset({
    "EFFECT_SITE_UNPROVEN",
    "CLAIM_OPERATION_UNPROVEN",
    "CLAIM_OPERATION_NOT_PLANNED",
    "CLAIM_EXECUTION_EFFECT_MISSING",
    "CLAIM_PLANNED_EFFECT_MISSING",
    "CLAIM_NO_CHANGE_APPLIED",
    "CLAIM_LOCATION_MISSING",
    "CLAIM_REPLACEMENT_MISSING",
    "CLAIM_VALIDATION_FAILED",
    "CLAIM_VALIDATION_UNKNOWN",
    "CLAIM_VALIDATION_CONFLICT",
    "RESIDUAL_OLD_TEXT",
    "FINAL_OPERATION_UNPROVEN",
    "FINAL_RESIDUAL_OLD_TEXT",
})
_ALWAYS_BLOCKING_PREFIXES = (
    "CLAIM_", "EFFECT_", "RESIDUAL_", "MODEL_", "DOCUMENT_", "OUTPUT_",
    "REPORT_", "FROZEN_", "PROCESSING_", "INPUT_", "EXISTING_REVISION",
    "RECALL_EDIT_OVERLAP", "FINAL_OPERATION", "FINAL_RESIDUAL", "GUIDE_",
    "RULESET_", "GUIDE_RULESET",
)
_KNOWN_ITEM_PREFIXES = (
    "OPEN_OBLIGATION", "APPLICABILITY", "RECALL_FACT", "FUND_TYPE",
    "FACT_PREREQUISITE", "AUDIT_", "SWEEP_", "SURVEY_", "COVERAGE_", "TARGET_",
    "COMPOSE", "OVERLAP", "VALIDATION", "LEDGER_EVIDENCE_UNBOUND",
    "FINAL_MODEL_SWEEP_FINDING", "FINAL_COVERAGE_UNRESOLVED", "VERIFICATION_",
    "QUALIFICATION_", "RECALL_QUOTE_UNRESOLVED", "RECALL_TARGET_",
)


def _item_code(item: Mapping[str, Any]) -> str:
    return str(item.get("code") or "")


def _is_always_blocking(code: str) -> bool:
    value = str(code or "").upper()
    if not value:
        return False
    return (value in _ALWAYS_BLOCKING_CODES
            or value.startswith(_ALWAYS_BLOCKING_PREFIXES))


def _is_known_item_code(code: str) -> bool:
    value = str(code or "").upper()
    if not value:
        return True
    if any(value.startswith(prefix) for prefix in _KNOWN_ITEM_PREFIXES):
        return True
    return bool(failure_reason(value))


def _requires_blocker(item: Any) -> bool:
    """Whether one reported item must keep the delivery incomplete.

    A claim/effect/residual code is always blocking.  A code outside every known
    taxonomy is also blocking: silently treating a future code as a review note is
    the failure mode R13/R14 close here.  Generic kind-only rows keep the existing
    pipeline bucket, except Claim Replay rows.
    """
    if not isinstance(item, Mapping):
        return False
    if str(item.get("kind") or "").strip().lower() == "claim_replay":
        return True
    code = _item_code(item)
    if not code:
        return False
    if _is_always_blocking(code):
        return True
    return not _is_known_item_code(code)


def _blocker_key(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (str(item.get("rule_id") or ""), str(item.get("location") or ""),
            _item_code(item), str(item.get("obligation_id") or ""))


def _with_fail_closed_blockers(report: Mapping[str, Any],
                               blockers: Sequence[Any],
                               review_items: Sequence[Any],
                               business_items: Sequence[Any]
                               ) -> tuple[list[Any], list[Any], list[Any]]:
    """Move proof failures/unknown codes out of review or business buckets."""
    kept_blockers: list[Any] = []
    kept_review: list[Any] = []
    kept_business: list[Any] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add_blocker(item: Any) -> None:
        if not isinstance(item, Mapping):
            return
        key = _blocker_key(item)
        if key in seen:
            return
        seen.add(key)
        kept_blockers.append(item)

    for item in blockers:
        if isinstance(item, Mapping):
            add_blocker(item)
        else:
            kept_blockers.append(item)
    for item in review_items:
        if _requires_blocker(item):
            add_blocker(item)
        else:
            kept_review.append(item)
    for item in business_items:
        if _requires_blocker(item):
            add_blocker(item)
        else:
            kept_business.append(item)
    # Even when a report supplies pre-classified buckets, an explicit unresolved
    # Claim/Effect failure must not stay hidden in a review list.
    for item in report.get("unresolved") or []:
        if _requires_blocker(item):
            add_blocker(item)
    return kept_blockers, kept_review, kept_business


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
        if replay.get("truncated") is True:
            # A capped batch is not a clean result even if every checked item passed.
            blockers.append("claim_replay_truncated")
        if replay.get("remaining_unknown") is True:
            blockers.append("claim_replay_remaining_unknown")
        replay_failures = replay.get("failures") or ()
        if isinstance(replay_failures, (list, tuple)) and replay_failures:
            # ``verified=False`` should already be present, but old/hand-written
            # reports may disagree.  Any recorded failure keeps delivery incomplete.
            blockers.append("claim_replay_failures")
            if any(not isinstance(item, Mapping)
                   or _requires_blocker(item) for item in replay_failures):
                blockers.append("claim_replay_unclassified_failure")
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
    specific = failure_reason(text)
    if specific:
        return specific
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
            "code": str(item.get("code") or item.get("kind") or ""),
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
    errors = [item for item in (report.get("errors") or [])
              if isinstance(item, Mapping)]
    error_issues = [{
        "rule_id": "", "title": "处理失败", "section": "", "location": "",
        "obligation_id": "",
        "business_reason": failure_reason(item.get("code")) or "处理未完成",
        "requirement": "", "quote": "", "quote_exact_site": False,
        "review_note": "",
    } for item in errors]
    if error_issues:
        issues = error_issues + issues
    if status == "not_generated" and not issues:
        issues = [{
            "rule_id": "", "title": "未生成修改文件", "section": "", "location": "",
            "obligation_id": "",
            "business_reason": "未匹配到可修改条款或处理未完成",
            "requirement": "", "quote": "", "quote_exact_site": False,
            "review_note": "",
        }]
    policy = str(report.get("delivery_policy") or "strict")
    if policy == "review_assisted":
        # The report already split unresolved into blockers / review / business.
        # Only the blocker bucket may keep a delivery partial.  Re-apply the
        # fail-closed gate here: an older report may put a Claim/Effect failure or
        # an unknown future code in the review bucket.
        blockers = list(report.get("delivery_blockers") or [])
        review_items = list(report.get("review_items") or [])
        business_items = list(report.get("business_pending") or [])
        blockers, review_items, business_items = _with_fail_closed_blockers(
            report, blockers, review_items, business_items)
    else:
        blockers = _completion_blockers(report)
        review_items = []
        business_items = []
    if report.get("verification_status") == VERIFICATION_BLOCKED:
        return {"status": VERIFICATION_BLOCKED, "headline": "验证暂未完成，等待恢复处理",
                "issues": issues, "notices": notices,
                "verification_blockers": list(report.get("verification_blockers") or [])}
    if status == "complete" and not blockers:
        if review_items or business_items:
            parts = []
            if review_items:
                parts.append(f"{len(review_items)} 项人工复核")
            if business_items:
                parts.append(f"{len(business_items)} 项业务待定")
            return {"status": COMPLETE_WITH_NOTICES,
                    "headline": "修改完成，" + "、".join(parts),
                    "issues": issues, "notices": notices,
                    "review_items": review_items, "business_pending": business_items}
        if notices:
            return {"status": COMPLETE_WITH_NOTICES,
                    "headline": "修改完成，但有业务提示",
                    "issues": [], "notices": notices}
        return {"status": COMPLETE, "headline": "修改完成", "issues": [], "notices": []}
    if status == "complete" and blockers and not issues:
        first_blocker = next((item for item in blockers
                              if isinstance(item, Mapping)), None)
        if first_blocker is None:
            replay = (report.get("artifact_claim_replay")
                      or report.get("claim_replay"))
            if isinstance(replay, Mapping):
                first_blocker = next(
                    (item for item in replay.get("failures") or ()
                     if isinstance(item, Mapping) and _requires_blocker(item)),
                    None)
        first_blocker = first_blocker or {}
        blocker_code = _item_code(first_blocker)
        issues = [{"rule_id": str(first_blocker.get("rule_id") or ""),
                   "code": blocker_code, "title": "交付证明未收敛", "section": "",
                   "location": str(first_blocker.get("location") or ""),
                   "obligation_id": str(first_blocker.get("obligation_id") or ""),
                   "business_reason": (failure_reason(blocker_code)
                                       or str(first_blocker.get("reason") or "")
                                       or "交付证明仍包含未解决的操作或站点"),
                   "requirement": "", "quote": "", "quote_exact_site": False,
                   "review_note": "请重新复核操作、站点和最终文档证明。"}]
    if status == "not_generated":
        reason = str((issues[0].get("business_reason") if issues else "")
                     or "未生成修改文件")
        return {"status": PARTIAL, "headline": f"未生成修改文件：{reason}",
                "issues": issues, "notices": notices}
    if error_issues:
        return {"status": PARTIAL,
                "headline": "处理失败：" + str(error_issues[0].get("business_reason") or ""),
                "issues": issues, "notices": notices}
    return {
        "status": PARTIAL,
        "headline": "部分修改无法可靠完成",
        "issues": issues,
        "notices": notices,
    }
