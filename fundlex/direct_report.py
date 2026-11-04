"""direct_edit_v1 报告的用户口径：结果页、总览、ZIP 清单/CSV、飞书共用一处提取。

本模块是新直通流程（guide_card_v1 指引卡 + DirectWriteResult 实际写回证据）的
**唯一**用户报告构造处。所有用户出口——工作台结果详情、结果总览.md、批量 ZIP
内的结果清单.csv 与逐份修改说明.csv、公开版单份 report_md/report_json、飞书
摘要——必须从这里取「实际写回了几处、每处改前/改后」，绝不再读 plan.edits、
target_counts 或模型提案账。

口径（用户裁决，不可回归）：
- 「完成」＝ 至少一处实质修改**实际写回**且最终文件可授权下载；零处写回一律
  「未完成」。完成不代表所有应改处都改了，不输出「全部改完」类表述。
- 只陈述已写回的改动：位置、对应指引卡、改前文字、改后文字、实际处数。
- 技术故障如实说「没有形成可交付修改」，但内部错误码、跳过卡片与「请人工核查」
  清单绝不进入用户件。

历史旧引擎报告不走本模块；旧报表的最小只读兼容渲染留在
``fundlex.edit_summary``（见该模块头部标注）。
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

# 报告外壳 schema：第 4 条后端线把第 3 条 DirectWriteResult.to_dict() 放进
# report["write_result"]（或顶层 "direct_edit"），并用 "direct_edit_v1" 标记新报告。
REPORT_SCHEMA_VERSION = "direct_edit_v1"
WRITE_SCHEMA_VERSION = "direct_edit_write_v1"
PUBLIC_SCHEMA_VERSION = "direct_edit_public_v1"

# 写回器定位出 write result 的容忍键（首推 write_result）。
_WRITE_KEYS = ("write_result", "direct_edit", "direct_edit_v1", "direct_write")

ACTION_TEXT = {
    "replace": "替换",
    "delete": "删除",
    "insert_before": "新增（条款前）",
    "insert_after": "新增（条款后）",
    "insert": "新增",
}

# 结果清单.csv / 逐份修改说明.csv 的表头。数据全部换成实际写回账。
# 用户亲令（2026-11-03）：结果清单加「修改详情」列（逐处写清位置/对应指引卡/
# 改前/改后，单元格内换行分条）；逐份修改说明的详细版保持不动。
RESULT_LIST_HEADER = ["序号", "合同文件", "处理结果", "修改处数", "修改内容摘要",
                      "修改详情", "备注"]
EDIT_DETAIL_HEADER = ["序号", "修改类型", "位置", "修改前", "修改后", "对应指引"]

# 逐处对照在 CSV 里的截断上限（全文在带痕版 DOCX 里）。
CLIP_LIMIT_BEFORE = 160
CLIP_LIMIT_AFTER = 200
DETAIL_CLIP_NOTE = "（全文见同目录带痕版文件）"

# 「修改详情」列：每处前后文各 120 字，单元格总量 2000 字防巨格（用户亲令③）。
DETAIL_COLUMN_CLIP = 120
DETAIL_COLUMN_TOTAL = 2000
DETAIL_COLUMN_OVERFLOW_NOTE = "…（其余见逐份修改说明与带痕版文件）"

OUTCOME_LABELS = ["完成", "未完成", "处理中", "处理失败"]

# 「最终版」修订语义（第 3 条契约 §五，事实陈述，不用文案掩盖）：
FINAL_REVISION_NOTE = (
    "最终版为全部修订已定案的版本：其中既有本次按指引的修改，也包括合同中原有的修订痕迹，"
    "均已定案不再显示标记。带痕版保留全部修订标记，可在 Word 中逐条接受或拒绝；"
    "在工作台逐条选择后还可下载按您选择生成的版本。"
)
COMPLETE_NOTE = "「完成」表示本次处理已形成可交付修改并提供下载，不代表合同所有条款均已复核完毕。"

# 用户拍板 C（2026-11-02）：normalized_base 档合同必须显著标注。
# 词表权威值（协调者）："strict_dual_layer" | "normalized_base"，默认 strict_dual_layer；
# 标注只认 normalized_base 一个值，strict_dual_layer/缺省/未知一律走原样，无附加说明。
REVISION_TIER_NORMALIZED_BASE = "normalized_base"
REVISION_TIER_STRICT_DUAL_LAYER = "strict_dual_layer"
NORMALIZED_BASE_NOTE = "本合同原修订痕迹已并入定稿，无法单独撤回原修订。"


def revision_tier(report: Mapping[str, Any] | None,
                  doc: Mapping[str, Any] | None = None) -> str:
    """合同所在修订层档：'strict_dual_layer'（默认） / 'normalized_base'。

    读取顺序：report.revision_tier → report.direct_edit.revision_tier（及 write_result）
    → doc.revision_tier；缺省/未知一律按 strict_dual_layer（不加提示，不误报）。
    """
    if isinstance(report, Mapping):
        found = find_write_result(report)
        sources = [report, report.get("direct_edit"), found]
        if isinstance(found, Mapping):
            sources.append(found.get("write_result"))
        for source in sources:
            if isinstance(source, Mapping) and source.get("revision_tier"):
                return str(source["revision_tier"])
    if isinstance(doc, Mapping) and doc.get("revision_tier"):
        return str(doc["revision_tier"])
    return REVISION_TIER_STRICT_DUAL_LAYER


def normalized_base(report: Mapping[str, Any] | None,
                    doc: Mapping[str, Any] | None = None) -> bool:
    return revision_tier(report, doc) == REVISION_TIER_NORMALIZED_BASE


# ---------------------------------------------------------------------------
# 写回证据定位（对第 3 条 DirectWriteResult 形状的唯一解释处）
# ---------------------------------------------------------------------------

def find_write_result(report: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    """在报告外壳里定位 DirectWriteResult；不是直通报告时返回 None。"""
    if not isinstance(report, Mapping):
        return None
    if report.get("schema_version") == WRITE_SCHEMA_VERSION:
        return report
    for key in _WRITE_KEYS:
        candidate = report.get(key)
        if isinstance(candidate, Mapping):
            # 直通写回块的判定依据是 schema_version；缺 schema_version 但带
            # changes/actual_written_count 的（早期夹具）也接受。
            if candidate.get("schema_version") == WRITE_SCHEMA_VERSION:
                return candidate
            if isinstance(candidate.get("changes"), list) or (
                    "actual_written_count" in candidate and "status" in candidate):
                return candidate
    return None


def is_direct_report(report: Mapping[str, Any] | None) -> bool:
    """该报告是否属于 direct_edit_v1 直通流程（区别于历史旧引擎报告）。

    唯一判据（协调者裁决 D1）：顶层 ``report_contract == "direct_edit_v1"``；
    早期夹具的 ``schema_version`` 标记与 direct_edit 写回块存在兜底识别。
    """
    if not isinstance(report, Mapping):
        return False
    if report.get("report_contract") == REPORT_SCHEMA_VERSION:
        return True
    if report.get("schema_version") == REPORT_SCHEMA_VERSION:
        return True
    return find_write_result(report) is not None


# ---------------------------------------------------------------------------
# 实际写回改动（唯一计数来源）
# ---------------------------------------------------------------------------

def _card_index(report: Mapping[str, Any] | None) -> dict[str, str]:
    """card_id -> 指引卡标题（guide_card_v1 卡包）。"""
    guide = (report or {}).get("guide") if isinstance(report, Mapping) else None
    if not isinstance(guide, Mapping):
        return {}
    cards = guide.get("cards")
    if not isinstance(cards, list):
        return {}
    out: dict[str, str] = {}
    for card in cards:
        if isinstance(card, Mapping) and card.get("card_id"):
            out[str(card["card_id"])] = str(card.get("title") or card["card_id"])
    return out


def written_changes(report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """实际写回、可重开验证的改动清单（status=="written"），人读化。

    每条：index/action/action_text/location/section/before/after/card_id/card_title。
    计划、提案与 skipped 一律不出现在这里。
    """
    write = find_write_result(report)
    if not isinstance(write, Mapping):
        return []
    cards = _card_index(report)
    rows: list[dict[str, Any]] = []
    for item in write.get("changes") or []:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") != "written":
            continue
        card_id = str(item.get("rule_card_id") or "")
        section = str(item.get("section_path") or "").strip()
        location = str(item.get("location") or "").strip()
        place = section or location or "—"
        rows.append({
            "index": len(rows) + 1,
            "action": str(item.get("action") or ""),
            "action_text": ACTION_TEXT.get(str(item.get("action") or ""), "修改"),
            "location": place,
            "section": section,
            "before": str(item.get("before") or "").strip(),
            "after": str(item.get("after") or "").strip(),
            "card_id": card_id,
            "card_title": cards.get(card_id, card_id),
        })
    return rows


def written_count(report: Mapping[str, Any] | None) -> int:
    """实际修改处数。有逐处清单按清单数；清单缺失时退回写回器重开确认数。"""
    rows = written_changes(report)
    if rows:
        return len(rows)
    write = find_write_result(report)
    if isinstance(write, Mapping) and write.get("changes") is None:
        count = write.get("actual_written_count")
        return int(count) if isinstance(count, int) and count > 0 else 0
    return 0


def technical_failure(report: Mapping[str, Any] | None,
                      doc: Mapping[str, Any] | None = None) -> bool:
    """是否属于「技术故障、没有形成可交付修改」（内部码永不外传）。

    第 4 线冻结契约：技术失败 = ``delivery_status == "not_generated"``
    （report.error_code 仅存内部，不透传给用户）。
    """
    doc = doc or {}
    if (doc.get("job_status") or "") == "failed":
        return True
    if (doc.get("delivery_status") or "") == "not_generated":
        return True
    if isinstance(report, Mapping):
        failure = report.get("technical_failure")
        if isinstance(failure, Mapping) and failure:
            return True
        if (report.get("status") or "") == "failed":
            return True
        if (report.get("delivery_status") or "") == "not_generated":
            return True
        if report.get("error_code"):
            return True
    return False


def document_outcome(report: Mapping[str, Any] | None,
                     doc: Mapping[str, Any] | None = None) -> str:
    """单份合同主状态：processing / failed / complete / incomplete。

    终态判定优先第 4 线权威字段：``delivery_status`` ∈
    {complete, incomplete, not_generated}（裁决 D3：not_generated→处理失败）。
    """
    doc = doc or {}
    if (doc.get("upload_status") or "") == "rejected":
        return "failed"
    job = doc.get("job_status") or ""
    if job in {"queued", "running", "leased", "retry_wait", "paused", "not_started", ""} and \
            find_write_result(report) is None and not doc.get("delivery_status"):
        return "processing"
    if job == "failed":
        return "failed"
    delivery = (doc.get("delivery_status") or ((report or {}).get("delivery_status")
                if isinstance(report, Mapping) else "")) or ""
    if delivery == "not_generated":
        return "failed"
    if delivery in {"complete", "incomplete"}:
        return delivery
    return "complete" if written_count(report) >= 1 else "incomplete"


def outcome_label(report: Mapping[str, Any] | None,
                  doc: Mapping[str, Any] | None = None) -> str:
    return {"complete": "完成", "incomplete": "未完成",
            "processing": "处理中", "failed": "处理失败"}[
        document_outcome(report, doc)]


def outcome_note(report: Mapping[str, Any] | None,
                 doc: Mapping[str, Any] | None = None) -> str:
    """结果区的人读说明；不含错误码、不派送人工待办。"""
    outcome = document_outcome(report, doc)
    if outcome == "complete":
        return COMPLETE_NOTE
    if outcome == "processing":
        return "合同仍在处理中，结束后会显示实际修改结果。"
    if outcome == "failed" or technical_failure(report, doc):
        return "本次处理发生故障，没有形成可交付的修改；可重新上传该合同再试一次。"
    return "本次按指引核对后没有形成可交付的修改，合同未做改动。"


def deliverable_available(doc: Mapping[str, Any] | None,
                          kind: str = "final") -> bool:
    """授权下载链接是否存在（前端据此决定是否给下载按钮）。"""
    downloads = (doc or {}).get("downloads")
    return isinstance(downloads, Mapping) and bool(downloads.get(kind))


def result_list_row_extra_note(report: Mapping[str, Any] | None,
                               doc: Mapping[str, Any] | None = None) -> str:
    """结果清单「备注」列附加：normalized_base 档的层档标注（拍板 C）。"""
    return NORMALIZED_BASE_NOTE if normalized_base(report, doc) else ""


# ---------------------------------------------------------------------------
# 逐处对照（详情页 / 逐份修改说明.csv / 公开版报告共用）
# ---------------------------------------------------------------------------

def _clip(text: str, limit: int, *, with_note: bool = False) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit] + "…" + (DETAIL_CLIP_NOTE if with_note else "")


def edit_detail_rows(report: Mapping[str, Any]) -> list[list[str]]:
    """逐份（修改说明）.csv 的数据行：序号/修改类型/位置/修改前/修改后/对应指引。"""
    rows: list[list[str]] = []
    for change in written_changes(report):
        rows.append([
            str(change["index"]), change["action_text"], change["location"],
            _clip(change["before"], CLIP_LIMIT_BEFORE, with_note=True) or "—",
            _clip(change["after"], CLIP_LIMIT_AFTER, with_note=True) or "（删除）",
            change["card_title"] or "—",
        ])
    return rows


def change_summary(report: Mapping[str, Any]) -> str:
    """一份合同的修改内容摘要（涉及哪些指引卡标题，去重保序）。"""
    titles = list(dict.fromkeys(change["card_title"] for change in written_changes(report)
                                if change["card_title"]))
    return "、".join(titles) if titles else "—"


def csv_safe(value: Any) -> str:
    """CSV 单元格防公式注入：以 = + - @ 开头的内容前补单引号。"""
    text = str(value if value is not None else "")
    return ("'" + text) if text[:1] in ("=", "+", "-", "@") else text


def detail_column(report: Mapping[str, Any] | None) -> str:
    """结果清单「修改详情」列：逐处分条（位置/对应指引卡/改前/改后），换行分隔。

    唯一数据源 written_changes；历史旧报告无 direct 数据时返回空串，不报错。
    """
    changes = written_changes(report)
    if not changes:
        return ""
    entries = []
    for change in changes:
        before = _clip(change["before"], DETAIL_COLUMN_CLIP) or "—"
        after = _clip(change["after"], DETAIL_COLUMN_CLIP) or "（删除）"
        card = change["card_title"] or "—"
        entries.append(
            f"{change['index']}. [{change['action_text']}] 位置：{change['location']}"
            f"｜对应指引：{card}\n改前：{before}\n改后：{after}")
    text = "\n\n".join(entries)
    if len(text) > DETAIL_COLUMN_TOTAL:
        text = text[:DETAIL_COLUMN_TOTAL - len(DETAIL_COLUMN_OVERFLOW_NOTE)] \
            + DETAIL_COLUMN_OVERFLOW_NOTE
    return text


def result_list_row(index: int, name: str, report: Mapping[str, Any] | None,
                    doc: Mapping[str, Any] | None = None) -> list[str]:
    """结果清单.csv 的一行：序号/合同文件/处理结果/修改处数/修改内容摘要/修改详情/备注。"""
    outcome = document_outcome(report, doc)
    count = written_count(report)
    if outcome == "failed":
        note = "处理未完成，未生成可交付文件，可重新上传后再试"
    elif outcome == "processing":
        note = ""
    elif outcome == "incomplete":
        note = ("本次处理发生故障，未形成可交付修改"
                if technical_failure(report, doc) else "本合同未形成可交付修改")
    else:
        note = ""
    tier_note = result_list_row_extra_note(report, doc)
    if tier_note:
        note = f"{note}；{tier_note}" if note else tier_note
    return [str(index), name, outcome_label(report, doc),
            str(count) if outcome in {"complete", "incomplete"} else "—",
            change_summary(report) if count else "—", detail_column(report), note]


# ---------------------------------------------------------------------------
# 结果总览.md（tasks.py 的 report() 在直通任务上改走这里，第 4 线接线）
# ---------------------------------------------------------------------------

def overview_counts(entries: Iterable[tuple[str, Mapping[str, Any] | None,
                                          Mapping[str, Any] | None]]) -> dict[str, int]:
    """(name, report, doc) 序列 → 四桶计数；未上传/未处理的也计入对应桶。"""
    counts = {label: 0 for label in OUTCOME_LABELS}
    for _name, report, doc in entries:
        counts[outcome_label(report, doc)] += 1
    return counts


def render_overview(task_name: str,
                    entries: Iterable[tuple[str, Mapping[str, Any] | None,
                                            Mapping[str, Any] | None]]) -> str:
    """直通任务的结果总览.md 全文。

    ``entries`` 为 (合同名, report, doc)。只列实际写回结果，不出「按人工选择」、
    「需要人工处理」清单或内部原因码。
    """
    entries = list(entries)
    counts = overview_counts(entries)
    lines = [
        f"# {task_name} — 处理结果总览",
        "",
        "；".join(f"{label} {counts[label]} 份" for label in OUTCOME_LABELS),
        "",
        f"- {COMPLETE_NOTE}",
        "- 「修改处数」为实际写回合同并可通过下载文件核对的改动数；处理中或处理失败的合同不计修改数。",
        "",
        "| 合同文件 | 处理结果 | 修改处数 | 修改内容 |",
        "| --- | --- | --- | --- |",
    ]
    for name, report, doc in entries:
        outcome = document_outcome(report, doc)
        count = written_count(report)
        cell_count = str(count) if outcome in {"complete", "incomplete"} else "—"
        summary = change_summary(report) if count else outcome_note(report, doc)
        safe_name = str(name).replace("|", "\\|").replace("\n", " ")
        safe_summary = summary.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {safe_name} | {outcome_label(report, doc)} | {cell_count} | {safe_summary} |")
    if any(document_outcome(report, doc) == "failed" for _n, report, doc in entries):
        lines += ["", "## 处理失败的合同",
                  "失败合同未生成可交付文件，可在任务中重新上传该合同后再试一次。"]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 公开版单份报告（report_md / report_json 的用户下载版，与内部技术版分离）
# ---------------------------------------------------------------------------

def public_project(report: Mapping[str, Any],
                   doc: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """公开版报告数据：不含 skipped、reason_code、hash、内部诊断。"""
    outcome = document_outcome(report, doc)
    count = written_count(report)
    changes = [{
        "index": change["index"],
        "action": change["action_text"],
        "location": change["location"],
        "before": change["before"],
        "after": change["after"],
        "guide": {"card_id": change["card_id"], "title": change["card_title"]},
    } for change in written_changes(report)]
    downloads = (doc or {}).get("downloads") or {}
    files = {kind: bool(downloads.get(kind))
             for kind in ("final", "redline", "selected_final", "selected_redline")
             if downloads.get(kind)}
    tier = revision_tier(report, doc)
    return {
        "schema_version": PUBLIC_SCHEMA_VERSION,
        "contract": str((doc or {}).get("name") or ""),
        "status": outcome,
        "status_text": outcome_label(report, doc),
        "edit_count": count,
        "note": outcome_note(report, doc),
        "changes": changes,
        "files": files,
        "final_revision_note": FINAL_REVISION_NOTE if outcome == "complete" else "",
        "revision_tier": tier,
        "revision_tier_note": NORMALIZED_BASE_NOTE if tier == REVISION_TIER_NORMALIZED_BASE else "",
    }


def render_public_markdown(name: str, report: Mapping[str, Any],
                           doc: Mapping[str, Any] | None = None) -> str:
    """公开版单份报告 Markdown（report_md 用户下载件）。"""
    project = public_project(report, doc)
    lines = [
        f"# {name} — 修改结果",
        "",
        f"- 处理结果：{project['status_text']}"
        + (f"（实际修改 {project['edit_count']} 处）" if project["edit_count"] else ""),
        f"- {project['note']}",
    ]
    if project["status"] == "complete":
        lines += ["", f"> {FINAL_REVISION_NOTE}"]
    if project["revision_tier_note"]:
        lines += ["", f"> ⚠ {project['revision_tier_note']}"]
    if project["changes"]:
        lines += ["", "## 逐处修改对照", "",
                  "| # | 位置 | 对应指引 | 修改前 | 修改后 |",
                  "| --- | --- | --- | --- | --- |"]
        for change in project["changes"]:
            cells = [str(change["index"]), change["location"],
                     change["guide"]["title"] or change["guide"]["card_id"],
                     _clip(change["before"], CLIP_LIMIT_BEFORE, with_note=True) or "—",
                     _clip(change["after"], CLIP_LIMIT_AFTER, with_note=True) or "（删除）"]
            lines.append("| " + " | ".join(
                cell.replace("|", "\\|").replace("\n", " ") for cell in cells) + " |")
    files = [label for label, on in (
        ("最终版（全部修订已定案）", project["files"].get("final")),
        ("带痕版（保留全部修订标记）", project["files"].get("redline")),
        ("按您选择生成的版本", project["files"].get("selected_final")),
    ) if on]
    if files:
        lines += ["", "## 可下载文件", ""] + [f"- {label}" for label in files]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 飞书摘要（与结果页/总览/ZIP 同一计数来源）
# ---------------------------------------------------------------------------

def feishu_document_summary(report: Mapping[str, Any] | None,
                            doc: Mapping[str, Any] | None = None) -> dict[str, str]:
    """一份合同的飞书短文。``status_text`` 与 count 和工作台完全一致。"""
    outcome = document_outcome(report, doc)
    count = written_count(report)
    if outcome == "complete":
        text = f"完成 · 实际修改 {count} 处"
    elif outcome == "processing":
        text = "处理中"
    elif outcome == "failed":
        text = "处理失败，未生成可交付文件"
    else:
        text = "未完成 · 未形成可交付修改"
    return {"status": outcome, "status_text": outcome_label(report, doc),
            "edit_count": str(count), "text": text}


def feishu_task_summary(task_name: str,
                        entries: Iterable[tuple[str, Mapping[str, Any] | None,
                                                Mapping[str, Any] | None]]) -> str:
    """任务级飞书摘要：总数行 + 逐份一行，与总览同口径。"""
    entries = list(entries)
    counts = overview_counts(entries)
    lines = [
        f"{task_name}：处理结束。"
        + "；".join(f"{label} {counts[label]} 份" for label in OUTCOME_LABELS),
    ]
    for name, report, doc in entries:
        summary = feishu_document_summary(report, doc)
        lines.append(f"· {name}：{summary['text']}")
    return "\n".join(lines)


__all__ = [
    "REPORT_SCHEMA_VERSION", "WRITE_SCHEMA_VERSION", "PUBLIC_SCHEMA_VERSION",
    "ACTION_TEXT", "RESULT_LIST_HEADER", "EDIT_DETAIL_HEADER",
    "OUTCOME_LABELS", "FINAL_REVISION_NOTE", "COMPLETE_NOTE",
    "REVISION_TIER_NORMALIZED_BASE", "REVISION_TIER_STRICT_DUAL_LAYER",
    "NORMALIZED_BASE_NOTE", "DETAIL_COLUMN_CLIP", "DETAIL_COLUMN_TOTAL",
    "DETAIL_COLUMN_OVERFLOW_NOTE",
    "find_write_result", "is_direct_report", "written_changes", "written_count",
    "technical_failure", "document_outcome", "outcome_label", "outcome_note",
    "deliverable_available", "edit_detail_rows", "change_summary", "csv_safe",
    "detail_column", "result_list_row", "result_list_row_extra_note",
    "revision_tier", "normalized_base",
    "overview_counts", "render_overview",
    "public_project", "render_public_markdown",
    "feishu_document_summary", "feishu_task_summary",
]
