"""Readable, business-facing summaries of a recall-first report's edits.

Both the workbench (``GET /api/tasks/{id}/download/all`` and the task overview
markdown) and the offline delivery-package tool (``tools/evaluation/p6_package.py``)
need the *same* answer to "how many places did this contract change, and where".

Rather than re-implementing that extraction twice (they would drift), this module
is the single source of truth. It reads only what the engine itself recorded in
the report — the plan's edits, the guide's rule titles/requirements and the
audit verdicts — and never invents content.
"""
from __future__ import annotations

from typing import Any

# Short business labels for the "修改内容" column of the overview tables. The
# guide's own long titles are used verbatim in the per-case explanation; these
# stay concise so the overview reads at a glance.
RULE_SHORT = {
    "G01": "补充直销豁免（释义）",
    "G02": "释义份额类别按费用分组",
    "G03": "补充直销豁免（基本情况）",
    "G04": "基本情况份额类别按费用分组",
    "G05": "调整“调低赎回费率”/删除备案表述",
    "G06": "删除不同类别不得转换旧句",
    "G07": "单类别：补充直销申购豁免",
    "G08": "多类别：补充直销申购豁免",
    "G09": "赎回金额表述改为“扣除或加上”",
    "G10": "单类别：申购费用承担表述",
    "G11": "多类别：申购费用承担表述",
    "G12": "赎回费归属改为全额计入基金财产",
    "G13": "删除 7 日短期持有赎回费旧句",
    "G14": "调整可调低费率范围",
    "G15": "删除销售服务费支付旧条款",
    "G16": "补充销售服务费计提/返还条款",
    "G17": "删除销售服务费用途旧条款",
    "G18": "收益分配费用差异表述",
    "G19": "单类别浮动费：清算分配表述",
    "G20": "多类别浮动费：清算分配表述",
    "G22": "非浮动多类别：清算分配表述",
}

OP_TEXT = {"insert": "新增", "replace": "替换", "delete": "删除"}

# The per-case explanation keeps the table cells readable by clipping long text;
# the full wording stays available in the "（修改痕迹版）" DOCX for context.
CLIP_LIMIT_BEFORE = 160
CLIP_LIMIT_AFTER = 200

DELIVERY_TEXT = {
    "complete": "已修改并复核通过",
    "incomplete": "部分条款未修改（详见修改说明）",
    "not_generated": "未生成产物",
    "duplicate": "重复提交（同文件已处理）",
    "excluded": "整份排除类型，未修改",
    "excluded_by_fund_type": "整份排除类型，未修改",
}


def plan_edits(report: dict) -> list[dict]:
    """Every edit the engine actually applied, in plan order."""
    plan = report.get("plan") or {}
    if plan.get("edits"):
        return plan["edits"]
    # Older captures nest the same list under edit_plan.edits without rule ids.
    return (report.get("edit_plan") or {}).get("edits") or []


def rule_title(guide: dict, rule_id: str) -> str:
    for group in guide.get("groups") or []:
        if group.get("rule_id") == rule_id:
            # Titles carry a trailing "…：" separator; strip it for readability.
            return (group.get("title") or "").rstrip("：:") or rule_id
    return rule_id


def rule_label(guide: dict, rule_id: str) -> str:
    """Readable label for one edit's rule, joining composite ids ("G12+G13")."""
    if not rule_id:
        return ""
    parts = [part.strip() for part in str(rule_id).split("+") if part.strip()]
    return "＋".join(RULE_SHORT.get(part) or rule_title(guide, part) for part in parts)


def audit_verdicts(report: dict) -> dict[str, str]:
    """rule_id -> the audit's own verdict for that rule, for the 校验 column."""
    out: dict[str, str] = {}
    for round_info in (report.get("audit") or {}).get("rounds") or []:
        for result in round_info.get("results") or []:
            rule_id, verdict = result.get("rule_id"), result.get("verdict")
            if rule_id and verdict:
                out[rule_id] = verdict
    return out


def verdict_text(verdict: str | None) -> str:
    return {
        "completed": "通过（规则校验＋独立复核）",
        "satisfied": "通过（原合同已符合）",
        "wrong": "未通过（独立复核认为不符）",
        "missing": "未通过（独立复核认为缺失）",
    }.get(verdict or "", "通过（规则校验＋独立复核）" if verdict else "—")


def edit_count(report: dict) -> int:
    """How many places this contract was actually modified."""
    return len(plan_edits(report))


def edit_labels(report: dict) -> list[str]:
    """Distinct readable rule labels touched by this contract, in edit order."""
    guide = (report.get("guide") or {})
    return list(dict.fromkeys(rule_label(guide, e.get("rule_id") or "")
                              for e in plan_edits(report) if e.get("rule_id")))


def unresolved_entries(report: dict) -> list[dict]:
    return list(report.get("unresolved") or [])


def delivery_text(report: dict, result: dict | None = None) -> str:
    delivery = report.get("delivery_status") or (result or {}).get("delivery_status")
    return DELIVERY_TEXT.get(delivery, delivery or "未知")


def summary_detail(report: dict, result: dict | None = None) -> str:
    """The overview table's "说明" cell for one contract.

    Prefers the rule-level wording ("涉及：…"); when nothing was edited but items
    stayed unchanged by the safety rules, say so instead of leaving it blank.
    """
    labels = edit_labels(report)
    if labels:
        return "涉及：" + "、".join(labels)
    unresolved = unresolved_entries(report)
    if unresolved:
        return f"{len(unresolved)} 项按安全规则保持原文"
    return "无需修改"


def edit_before_after(edit: dict) -> tuple[str, str]:
    """The (修改前, 修改后) wording for one edit, without clipping.

    The recall-first edit keeps the original wording in several places depending on
    the content source: the top-level edit's own keys, its ``evidence`` block, or —
    most commonly for a replace/delete — ``components[*].expected_old_text`` (the
    exact text the component was anchored to). An ``insert`` keeps the original and
    appends, so its "before" side is stated explicitly rather than left empty.
    """
    evidence = edit.get("evidence") or {}
    operation = edit.get("operation") or ""
    if operation == "insert":
        return "（保留原文，在其后追加新条款）", (str(edit["replacement"]) if edit.get("replacement") else "（无）")

    before = ""
    for key in ("matched_old_text", "old_text", "source_quote", "original", "expected_old_text"):
        value = edit.get(key) or evidence.get(key)
        if value:
            before = str(value)
            break
    if not before:
        for component in edit.get("components") or []:
            if not isinstance(component, dict):
                continue
            for key in ("matched_old_text", "expected_old_text", "old_text", "source_quote"):
                value = component.get(key) or (component.get("evidence") or {}).get(key)
                if value:
                    before = str(value)
                    break
            if before:
                break
    if not before:
        delete_texts = evidence.get("delete_texts")
        if delete_texts:
            before = " ".join(str(item) for item in delete_texts)

    replacement = edit.get("replacement")
    after = "（删除该句）" if (operation == "delete" or not replacement) else str(replacement)
    return before, after


def operation_text(edit: dict) -> str:
    """The 操作 label, calling a replace-with-empty-replacement what it really is."""
    operation = edit.get("operation") or ""
    if operation == "replace" and not edit.get("replacement"):
        return "删除"
    return OP_TEXT.get(operation, operation or "—")


FINAL_ROOT = "最终版（接受修订后）"
WORKING_ROOT = "工作文件（未完成）"
NOTES_ROOT = "逐份修改说明"


def archive_entry(kind: str, name: str, suffix: str, *, delivery_status: str | None = None) -> tuple[str, str]:
    """Where one downloaded artifact goes inside the task ZIP.

    Returns ``(folder_root, arcname)`` so both the caller and its tests share one
    definition. The accepted-revision contract goes in its own root folder
    (``最终版（接受修订后）``); revision and report files live next to that
    contract's notes under ``逐份修改说明/<合同>/``.

    The final contract is whichever version applies to the delivery — the user's
    selection when there is one, otherwise the engine's own. Two revision
    artifacts can coexist:

    * ``redline`` — the engine's full tracked changes, always present;
    * ``selected_redline`` — the same artefact after a review, i.e. the tracked
      changes the user kept.

    They are named ``（全量痕迹版）`` and ``（选择修订版）`` so a reader can tell which
    is which without opening them.
    """
    if kind.startswith("working_") or (delivery_status == "incomplete" and
                                       kind in {"selected_final", "selected_redline"}):
        label = {"working_final": "工作文件", "working_redline": "工作文件修订痕迹",
                 "selected_final": "工作文件（人工选择）",
                 "selected_redline": "工作文件修订痕迹（人工选择）"}[kind]
        return WORKING_ROOT, f"{WORKING_ROOT}/{name}/{name}（{label}）{suffix}"
    if kind in {"final", "selected_final"}:
        return FINAL_ROOT, f"{FINAL_ROOT}/{name}{suffix}"
    if kind in {"redline", "working_redline"}:
        return NOTES_ROOT, f"{NOTES_ROOT}/{name}/{name}（全量痕迹版）{suffix}"
    if kind == "selected_redline":
        return NOTES_ROOT, f"{NOTES_ROOT}/{name}/{name}（选择修订版）{suffix}"
    return NOTES_ROOT, f"{NOTES_ROOT}/{name}/{kind}{suffix}"


# Which artifact fills each ZIP slot, most specific first. A user's selection, when
# it differs from "accept everything", replaces the engine's own version.
ARCHIVE_PREFERENCE = {
    "final": ("selected_final", "final", "working_final"),
    "redline": ("redline", "working_redline"),
    "selected_redline": ("selected_redline",),
}


def archive_kinds(downloads) -> list[str]:
    """The artifact kinds to package, collapsing each slot to its best candidate.

    ``downloads`` is the document's available ``kind -> url`` mapping. A reviewed
    contract contributes *two* revision files: the engine's full redline plus the
    post-review selection. Kinds with no competing alternative (reports) are kept
    as-is, in the order they were recorded.
    """
    available = set(downloads or ())
    contested = {kind for group in ARCHIVE_PREFERENCE.values() for kind in group}
    chosen = [next((kind for kind in group if kind in available), None)
              for group in ARCHIVE_PREFERENCE.values()]
    chosen = [kind for kind in chosen if kind is not None]
    chosen.extend(kind for kind in (downloads or ()) if kind not in contested)
    return chosen


def clip(text: str, limit: int) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


def rule_requirement(guide: dict, rule_id: str) -> str:
    for group in guide.get("groups") or []:
        if group.get("rule_id") == rule_id:
            return group.get("requirement") or ""
    return ""


__all__ = [
    "RULE_SHORT", "OP_TEXT", "DELIVERY_TEXT", "CLIP_LIMIT_BEFORE", "CLIP_LIMIT_AFTER",
    "FINAL_ROOT", "WORKING_ROOT", "NOTES_ROOT",
    "plan_edits", "rule_title", "rule_label", "audit_verdicts", "verdict_text",
    "edit_count", "edit_labels", "unresolved_entries", "delivery_text",
    "summary_detail", "edit_before_after", "operation_text", "archive_entry",
    "archive_kinds", "ARCHIVE_PREFERENCE", "clip", "rule_requirement",
]
