"""Interactive cards kept deliberately small and stable for private chats.

Product rules for this module:

* Cards are the only Feishu UI.  Any state that needs an extra click should be
  explained in the card itself, not in a separate chat message.
* A card must always tell the user (a) what happened, (b) what to do next.
* Raw status/error codes never reach the user; they are translated here.
"""
from __future__ import annotations

from typing import Any

TYPE_LABELS = {
    "revision": "合同修订",
    "compare": "合同对比",
    "guide": "法规指引生成",
    "diagnosis": "只读诊断",
    "evaluation": "评测",
}

STATUS_LABELS = {
    "queued": "排队中",
    "pending": "排队中",
    "leased": "处理中",
    "running": "处理中",
    "processing": "处理中",
    "submitted": "已提交",
    "uploading": "上传中",
    "sealed": "已提交",
    "completed": "已完成",
    "succeeded": "已完成",
    "complete": "已完成",
    "candidate_ready": "草案已生成",
    "complete_with_unresolved": "已完成（有未解决项）",
    "completed_with_exceptions": "部分完成（有异常）",
    "incomplete": "部分完成",
    "failed": "失败",
    "cancelled": "已取消",
    "canceled": "已取消",
    "paused": "已暂停",
    "collecting": "收集中",
}

STAGE_LABELS = {
    "QUEUED": "排队中",
    "INGEST": "读取法规原文",
    "EXTRACT": "提取条款",
    "VERIFY": "核验条款",
    "SNAPSHOT": "生成法规快照",
    "DISCOVERY": "发现影响点",
    "MARKER_SWEEP": "扫描标记",
    "MARKER_ADJUDICATE": "判定标记",
    "MARKER_MERGE": "合并标记",
    "AUTHORING": "起草指引",
    "QUALITY": "质量检查",
    "REPAIR": "修复指引",
    "COVERAGE": "覆盖检查",
    "SUPPLEMENT": "补写指引",
    "RESIDUAL": "收尾核验",
}

DELIVERY_LABELS = {
    "complete": "完整交付",
    "incomplete": "不完整",
    "not_generated": "未生成（需处理）",
    "failed": "失败",
    "final": "最终版",
    "redline": "修订版",
    "report_md": "报告",
    "report_json": "报告数据",
    "working_final": "工作文件",
    "working_redline": "工作修订版",
    "evaluation_final": "评测修改版",
    "evaluation_redline": "评测修订痕迹",
    "unverified": "未验证",
}

ERROR_LABELS = {
    "UNSUPPORTED_FILE_FORMAT": "只支持 .docx 文件；PDF 请先用 Word 另存为 DOCX。",
    "UPLOAD_SIZE_LIMIT": "单个文件超过 25 MB，请压缩后重新发送。",
    "UPLOAD_REQUEST_SIZE_LIMIT": "本批文件合计超过 50 MB，请分批发或先压缩。",
    "INVALID_DOCX_PACKAGE": "文件不是可编辑的 DOCX（可能是 PDF 改后缀或文件已损坏）。",
    "ENCRYPTED_DOCX": "文件已加密，请先取消密码保护。",
    "DUPLICATE_DOCX_MEMBER": "DOCX 内部结构异常，请用 Word 重新另存。",
    "DOCX_PART_SIZE_LIMIT": "DOCX 内部单部件过大，请用 Word 重新另存。",
    "DOCX_COMPRESSION_RATIO_LIMIT": "DOCX 压缩比异常，请用 Word 重新另存。",
    "DOCX_EXPANDED_SIZE_LIMIT": "DOCX 解压后体积过大，请精简图片后重发。",
    "FILE_STAGE_FAILED": "文件暂存失败，请重新发送。",
    "FEISHU_FILE_KEY_MISSING": "飞书没有返回附件标识，请重新发送文件消息。",
    "EXISTING_REVISION_UNSUPPORTED": "检测到合同带有未处理的修订痕迹（Word 修订模式）。请先在 Word 中接受或拒绝全部修订、关闭修订模式并另存，再重新发送。",
    "DOCUMENT_PROTECTED": "文档受保护，请先在 Word 中取消保护后再发送。",
    "COMPARE_INVALID_DOCX": "对比文件必须是可编辑 DOCX。",
    "COMPARE_UPLOAD_REJECTED": "对比文件上传被拒绝，请检查文件后重试。",
}


def status_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未知"
    return STATUS_LABELS.get(text, STATUS_LABELS.get(text.lower(), text))


def stage_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return STAGE_LABELS.get(text, STAGE_LABELS.get(text.upper(), text))


def format_bytes(value: Any) -> str:
    try:
        size = float(value or 0)
    except (TypeError, ValueError):
        size = 0.0
    if size < 1024:
        return f"{int(size)} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def friendly_error(code: Any, *, fallback: str = "文件未接收，请检查格式和大小后重试。") -> str:
    text = str(code or "").strip()
    if not text:
        return ""
    return ERROR_LABELS.get(text, fallback)


def delivery_summary(counts: Any) -> str:
    if not isinstance(counts, dict) or not counts:
        return "—"
    parts = []
    for key, value in counts.items():
        try:
            count = int(value or 0)
        except (TypeError, ValueError):
            count = 0
        if count:
            parts.append(f"{DELIVERY_LABELS.get(str(key), str(key))} {count}")
    return " · ".join(parts) if parts else "—"


def _button(text: str, command: str, *, draft_id: str = "", style: str = "primary",
            extra: dict[str, Any] | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {"command": command}
    if draft_id:
        value["draft_id"] = draft_id
    if extra:
        value.update(extra)
    # Card JSON 2.0 uses behaviors for callback data; keep the legacy value
    # field as a harmless compatibility aid for older clients.
    return {"tag": "button", "text": {"tag": "plain_text", "content": text},
            "type": style, "value": value,
            "behaviors": [{"type": "callback", "value": value}]}


def _card(title: str, elements: list[dict[str, Any]], *, template: str = "blue") -> dict[str, Any]:
    return {"schema": "2.0", "config": {"update_multi": True},
            "header": {"template": template, "title": {"tag": "plain_text", "content": title}},
            "body": {"elements": elements}}


def _markdown(content: str) -> dict[str, Any]:
    return {"tag": "markdown", "content": content}


def _actions(*buttons: dict[str, Any]) -> dict[str, Any]:
    # Card JSON 2.0 removed the legacy ``action`` interaction module. Buttons
    # must be direct body elements or live inside a container such as column_set.
    return {"tag": "column_set", "flex_mode": "flow",
            "columns": [{"tag": "column", "width": "auto", "elements": [button]}
                        for button in buttons]}


def _progress(task: dict[str, Any]) -> str:
    total = int(task.get("total") or 0)
    completed = int(task.get("completed") or 0)
    failed = int(task.get("failed") or 0)
    if not total:
        return "尚未开始"
    percent = max(0, min(100, round(completed * 100 / total)))
    text = f"{completed}/{total}（{percent}%）"
    if failed:
        text += f" · 失败 {failed}"
    return text


def _next_step(status: str, mode: str) -> str:
    if status in {"queued", "pending", "submitted", "sealed"}:
        return "已排队，Worker 领取后会自动更新此卡。"
    if status in {"running", "processing", "leased"}:
        return "正在处理，完成后会自动更新此卡并出现下载按钮。"
    if status == "paused":
        return "任务已暂停，请到 FundLex 工作台处理。"
    if status == "failed":
        return "任务失败，可发送报告定位原因，或到工作台重试。"
    if status in {"completed_with_exceptions", "incomplete"}:
        return "部分合同未达到正式交付标准；可发送工作文件/报告，或到工作台处理。"
    if mode == "evaluation":
        return "可发送评测文件；评测文件不能作为正式合同。"
    return "可发送交付文件，或到工作台查看逐份详情。"


def menu_card(active: dict[str, Any] | None = None, note: str = "") -> dict[str, Any]:
    lines = [note, ""] if note else []
    lines += ["请选择要办理的业务。", "",
              "**合同修订**：按当前指引修改合同。",
              "**合同对比**：比较两份 DOCX 的差异。",
              "**法规指引生成**：从法规原文生成待审核指引。",
              "**只读诊断**：跑完整流程，只回诊断报告。",
              "**评测**：产出评测文件，不作为正式合同。",
              "",
              "也可以直接在私聊发送 DOCX，默认按合同修订处理。"]
    buttons: list[dict[str, Any]] = []
    if active is not None:
        label = TYPE_LABELS.get(active.get("task_type") or "revision", "任务")
        lines += ["", f"⚠️ 当前有未完成的{label}草稿。"]
        buttons.append(_button(f"继续{label}草稿", "continue_draft"))
    return _card("FundLex 任务中心", [
        _markdown("\n".join(lines)),
        _actions(_button("合同修订", "start_revision"),
                 _button("合同对比", "start_compare"),
                 _button("生成指引", "start_guide")),
        _actions(_button("只读诊断", "start_diagnosis"),
                 _button("评测", "start_evaluation"),
                 _button("我的任务", "show_tasks", style="default")),
        *([_actions(*buttons)] if buttons else []),
    ])


def active_draft_card(active: dict[str, Any], command: str) -> dict[str, Any]:
    label = TYPE_LABELS.get(active.get("task_type") or "revision", "任务")
    new_label = TYPE_LABELS.get(str(command or "").removeprefix("start_"), "新任务")
    return _card("有未完成任务", [
        _markdown(f"当前有一个未完成的**{label}**草稿。\n"
                  f"可以继续当前草稿，或取消它并开始**{new_label}**。"),
        _actions(_button("继续当前", "continue_draft"),
                 _button(f"取消并开始{new_label}", "switch_task", style="default",
                         extra={"task_type": str(command or "").removeprefix("start_")}),
                 _button("取消当前", "cancel", draft_id=str(active.get("id") or ""), style="danger")),
        _actions(_button("返回任务中心", "menu", style="default")),
    ], template="orange")


def task_name_card(draft: dict[str, Any], *, error: str = "") -> dict[str, Any]:
    """Legacy form card.

    New drafts never start on a form: the form submission used to leave users
    on a card that looked like it had vanished.  The card is retained only so
    drafts created before the file-first rollout can still be finished.
    """
    label = TYPE_LABELS.get(draft.get("task_type") or "revision", "任务")
    elements: list[dict[str, Any]] = [
        _markdown(f"请填写本次**{label}**的任务名称，保存后再发送文件。"
                  + (f"\n\n⚠️ {error}" if error else "")),
        {"tag": "form", "name": "task_name_form", "elements": [
            {"tag": "input", "name": "task_name",
             "label": {"tag": "plain_text", "content": "任务名称"},
             "placeholder": {"tag": "plain_text", "content": "例如：XX基金合同修订"},
             "default_value": str(draft.get("name") or ""), "max_length": 200, "width": "fill"},
            {"tag": "button", "name": "save_task_name", "form_action_type": "submit",
             "text": {"tag": "plain_text", "content": "保存并继续"}, "type": "primary"},
        ]},
        _actions(_button("使用默认名称并继续", "skip_name", style="default"),
                 _button("取消", "cancel", draft_id=str(draft.get("id") or ""), style="danger")),
    ]
    return _card(f"{label} · 任务名称", elements)


def draft_card(name: str, files: list[dict[str, Any]], *, error: str | None = None,
               draft_id: str = "", mode: str = "revision") -> dict[str, Any]:
    label = TYPE_LABELS.get(mode, "合同任务")
    accepted = [item for item in files if item.get("status") == "accepted"]
    total_size = sum(int(item.get("size") or 0) for item in accepted)
    lines = [f"任务名：**{name}**"]
    if accepted:
        lines.append(f"已收到 **{len(accepted)}** 个文件，共 {format_bytes(total_size)}。")
    else:
        lines.append("请直接发送合同文件，可一次发多个。")
        lines.append("支持 `.docx`；单个 ≤25 MB，本批合计 ≤50 MB。")
    if mode == "diagnosis":
        lines.append("只跑诊断，不交付修改后的合同。")
    elif mode == "evaluation":
        lines.append("产出评测文件和报告；评测文件不能作为正式合同。")
    if error:
        lines.append(f"⚠️ {error}")
    if accepted:
        lines.append("确认后会创建任务并开始处理（会消耗模型处理资源）。")
    if len(files) > 20:
        lines.append(f"文件较多，仅显示前 20 个；其余 {len(files) - 20} 个已接收。")
    elements: list[dict[str, Any]] = [_markdown("\n".join(lines))]
    for index, item in enumerate(files[:20], 1):
        status = item.get("status") or "accepted"
        if status == "accepted":
            suffix = ""
        else:
            suffix = f" ⚠️ {friendly_error(item.get('error_code'))}"
        elements.append(_markdown(f"{index}. **{item['name']}** · {format_bytes(item.get('size'))}{suffix}"))
        elements.append(_actions(_button("移除", "remove_file", style="default",
                                         extra={"file_id": item["id"]})))
    buttons = []
    if accepted:
        confirm = "开始诊断" if mode == "diagnosis" else "开始评测" if mode == "evaluation" else "确认创建任务"
        buttons.append(_button(confirm, "confirm", draft_id=draft_id))
    buttons.append(_button("取消", "cancel", draft_id=draft_id, style="danger"))
    elements.append(_actions(*buttons))
    return _card(f"FundLex {label}", elements)


def compare_prompt_card(draft_id: str, step: str, left: dict[str, Any] | None = None,
                        right: dict[str, Any] | None = None, *, error: str | None = None,
                        name: str = "") -> dict[str, Any]:
    if step == "confirm" and not (left and right):
        step = "right" if left else "left"
    lines: list[str] = []
    if name:
        lines.append(f"任务名：**{name}**")
        lines.append("")
    if step == "left":
        lines.append("第 1 步：请发送**左侧（原版）** DOCX。")
    elif step == "right":
        lines.append("第 1 步已完成。")
        lines.append("第 2 步：请发送**右侧（对比版）** DOCX。")
    else:
        lines.append("左右两份文件都已收到，请确认开始对比。")
    if left:
        lines.append(f"左侧（原版）：**{left.get('name', '')}** · {format_bytes(left.get('size'))}")
    if right:
        lines.append(f"右侧（对比版）：**{right.get('name', '')}** · {format_bytes(right.get('size'))}")
    if step == "confirm":
        lines.append("\n完成后可在对比页逐处查看和选择。")
    if error:
        lines.append(f"\n⚠️ {error}")
    buttons = []
    if step == "confirm":
        buttons = [_button("开始对比", "confirm", draft_id=draft_id),
                   _button("交换左右", "swap_sides", draft_id=draft_id, style="default"),
                   _button("替换左侧", "replace_side", style="default", extra={"side": "left"}),
                   _button("替换右侧", "replace_side", style="default", extra={"side": "right"}),
                   _button("取消", "cancel", draft_id=draft_id, style="danger")]
    else:
        if left:
            buttons.append(_button("替换左侧", "replace_side", style="default", extra={"side": "left"}))
        if right:
            buttons.append(_button("替换右侧", "replace_side", style="default", extra={"side": "right"}))
        buttons.append(_button("取消", "cancel", draft_id=draft_id, style="danger"))
    return _card("FundLex 合同对比", [_markdown("\n".join(lines)), _actions(*buttons)])


def compare_status_card(task: dict[str, Any], base_url: str = "") -> dict[str, Any]:
    status = str(task.get("status") or "unknown")
    counts = task.get("counts") or {}
    total = int(task.get("total") or 0)
    succeeded = int(counts.get("succeeded") or 0)
    incomplete = int(counts.get("incomplete") or 0)
    failed = int(counts.get("failed") or 0)
    done_pairs = succeeded + incomplete + failed
    diffs = 0
    for pair in task.get("pairs") or []:
        summary = pair.get("summary") or {}
        if isinstance(summary, dict):
            diffs += int(summary.get("total") or summary.get("differences") or 0)
    done = status in {"succeeded", "incomplete", "failed", "completed", "completed_with_exceptions"}
    title = "合同对比 · 已完成" if done else "合同对比 · 处理中"
    template = "green" if status == "succeeded" else "red" if status in {"failed", "incomplete"} else "blue"
    lines = [f"**{task.get('name') or '合同对比'}**",
             f"状态：{status_label(status)}",
             f"合同组：{done_pairs}/{total} · 成功 {succeeded} · 不完整 {incomplete} · 失败 {failed}"]
    if diffs:
        lines.append(f"差异：**{diffs}** 处")
    if not done:
        lines.append("完成后会自动更新此卡；逐处选择在对比页进行。")
    link = (f"\n[打开对比页]({base_url.rstrip('/')}/#compare?mode=detail&id={task.get('id', '')})"
            if base_url and task.get("id") else "")
    elements: list[dict[str, Any]] = [_markdown("\n".join(lines) + link)]
    if done and task.get("id"):
        elements.append(_actions(_button("发送对比结果", "send_file", extra={
            "task_type": "compare", "task_id": task["id"], "kind": "report_json"})))
    return _card(title, elements, template=template)


def guide_prompt_card(draft_id: str = "", *, error: str | None = None) -> dict[str, Any]:
    lines = ["请直接发送法规原文，支持 **PDF/DOCX**（上限 80 MB）。",
             "生成完成后只出草案；审核和发布在 FundLex 工作台进行。",
             "生成会调用模型并可能持续较长时间。"]
    if error:
        lines.append(f"\n⚠️ {error}")
    return _card("FundLex 法规指引生成", [_markdown("\n".join(lines)),
                                           _actions(_button("取消", "cancel", draft_id=draft_id,
                                                            style="danger"))])


def guide_confirm_card(draft_id: str, name: str, size: int, file_id: str = "",
                       *, task_name: str = "") -> dict[str, Any]:
    buttons = [_button("开始生成", "confirm", draft_id=draft_id)]
    if file_id:
        buttons.append(_button("替换文件", "replace_file", style="default", extra={"file_id": file_id}))
    buttons.append(_button("取消", "cancel", draft_id=draft_id, style="danger"))
    lines = []
    if task_name:
        lines += [f"任务名：**{task_name}**", ""]
    lines += [f"**{name}** · {format_bytes(size)}", "",
              "开始后会创建一次指引生成 run；完成后请在工作台审核并发布。"]
    return _card("FundLex 法规指引生成 · 确认", [_markdown("\n".join(lines)), _actions(*buttons)])


def guide_status_card(run: dict[str, Any], base_url: str = "") -> dict[str, Any]:
    status = str(run.get("status") or "unknown")
    stage = stage_label(run.get("stage"))
    done = status in {"complete", "complete_with_unresolved", "completed", "candidate_ready", "failed"}
    title = ("法规指引生成 · 草案已生成" if status == "candidate_ready"
             else "法规指引生成 · 已完成" if done else "法规指引生成 · 处理中")
    template = "red" if status == "failed" else "green" if done else "blue"
    lines = [f"**{run.get('title') or run.get('filename') or '法规指引'}**",
             f"状态：{status_label(status)}" + (f" · {stage}" if stage else "")]
    if run.get("error_code"):
        lines.append(f"错误：{friendly_error(run['error_code'], fallback='处理失败，请打开工作台查看详情。')}")
    if run.get("qualification_status"):
        lines.append(f"资格：{run['qualification_status']}")
    if status == "candidate_ready":
        lines.append("草案已生成，请到工作台审核、修改并发布。")
    link = (f"\n[打开指引生成页]({base_url.rstrip('/')}/#generation?mode=detail&id={run.get('id', '')})"
            if base_url and run.get("id") else "")
    elements: list[dict[str, Any]] = [_markdown("\n".join(lines) + link)]
    if done and status != "failed" and run.get("id"):
        elements.append(_actions(
            _button("发送指引草案", "send_file", extra={
                "task_type": "guide", "task_id": run["id"], "kind": "guide"}),
            _button("发送证据", "send_file", style="default", extra={
                "task_type": "guide", "task_id": run["id"], "kind": "evidence_json"}),
        ))
    return _card(title, elements, template=template)


def diagnosis_prompt_card(draft_id: str = "", mode: str = "diagnosis", *, error: str | None = None) -> dict[str, Any]:
    label = "只读诊断" if mode == "diagnosis" else "评测"
    lines = ["请直接发送一个或多个基金合同 DOCX。"]
    if mode == "diagnosis":
        lines.append("会跑完整修订流程，但只回诊断报告，不交付修改后的合同。")
    else:
        lines.append("会跑完整修订流程，产出评测文件和报告；评测文件不能作为正式合同。")
    if error:
        lines.append(f"\n⚠️ {error}")
    return _card(f"FundLex {label}", [_markdown("\n".join(lines)),
                                       _actions(_button("取消", "cancel", draft_id=draft_id,
                                                        style="danger"))])


def diagnosis_result_card(task: dict[str, Any], base_url: str = "", mode: str = "diagnosis") -> dict[str, Any]:
    label = "只读诊断" if mode == "diagnosis" else "评测"
    status = str(task.get("status") or "unknown")
    done = status in {"completed", "completed_with_exceptions", "failed"}
    title = f"{label} · 已完成" if done else f"{label} · 处理中"
    template = "red" if status == "failed" else "green" if done else "blue"
    lines = [f"**{task.get('name') or label}**", f"状态：{status_label(status)}",
             f"合同进度：{_progress(task)}"]
    if task.get("delivery_counts"):
        lines.append(f"结果：{delivery_summary(task['delivery_counts'])}")
    if done:
        lines.append(_next_step(status, mode))
    link = f"\n[打开任务详情]({base_url.rstrip('/')}/tasks/{task.get('id', '')})" if base_url and task.get("id") else ""
    buttons = []
    if task.get("id"):
        buttons.append(_button("发送报告", "send_file", style="primary",
                               extra={"task_type": mode, "task_id": task["id"], "kind": "report_md"}))
    buttons.append(_button("打开工作台", "open_workbench", style="default"))
    return _card(title, [_markdown("\n".join(lines) + link), _actions(*buttons)], template=template)


def revision_status_card(task: dict[str, Any], base_url: str = "") -> dict[str, Any]:
    status = str(task.get("status") or "unknown")
    title = {"completed": "任务已完成", "completed_with_exceptions": "任务部分完成",
             "failed": "任务处理失败", "paused": "任务已暂停"}.get(status, "任务处理中")
    link = f"\n[打开 FundLex 详情]({base_url.rstrip('/')}/tasks/{task.get('id', '')})" if base_url and task.get("id") else ""
    content = (f"**{task.get('name') or '合同修订'}**\n状态：{status_label(status)}\n"
               f"合同进度：{_progress(task)}")
    content += f"\n{_next_step(status, 'revision')}"
    template = "green" if status == "completed" else "red" if status in {"completed_with_exceptions", "failed"} else "blue"
    return _card(title, [_markdown(content + link)], template=template)


def result_card(task: dict[str, Any], base_url: str = "", *, mode: str = "revision",
                downloads: dict[str, str] | None = None) -> dict[str, Any]:
    downloads = downloads or {}
    counts = task.get("delivery_counts") or {}
    not_generated = 0
    try:
        not_generated = int(counts.get("not_generated") or 0)
    except (TypeError, ValueError):
        not_generated = 0
    missing_delivery = not any(downloads.get(kind) for kind in
                               ("final", "redline", "working_final", "working_redline"))
    attention = mode in {"revision", "delivery"} and not_generated > 0
    title = "任务结果"
    if mode == "diagnosis":
        title = "诊断报告"
    elif mode == "evaluation":
        title = "评测结果（非正式合同）"
    elif attention:
        title = "任务未生成交付文件" if missing_delivery else "任务部分完成（有未生成）"
    lines = [f"**{task.get('name') or title}**",
             f"状态：{'处理结束（未生成交付文件）' if attention else status_label(task.get('status'))}",
             f"合同进度：{_progress(task)}"]
    if counts:
        lines.append(f"交付：{delivery_summary(counts)}")
    if attention:
        lines.append(f"⚠️ 有 {not_generated} 份合同未生成交付文件。"
                     "常见原因是合同带有未处理的修订痕迹、文档受保护，或规则不适用。")
        lines.append("请先发送报告查看具体原因；在 Word 中接受/拒绝全部修订并另存后，可重新发送合同。")
    else:
        lines.append(_next_step(str(task.get("status") or ""), mode))
    if mode == "evaluation":
        lines.append("⚠️ 评测文件仅用于评测，不能作为正式合同交付。")
    link = f"\n[打开任务详情]({base_url.rstrip('/')}/tasks/{task.get('id', '')})" if base_url and task.get("id") else ""
    buttons: list[dict[str, Any]] = []
    task_id = str(task.get("id") or "")
    sendable: list[tuple[str, str]] = []
    if mode == "diagnosis":
        report_kind = "report_md" if downloads.get("report_md") else "report_json" if downloads.get("report_json") else ""
        if report_kind:
            sendable.append((report_kind, "发送诊断报告"))
    elif mode == "evaluation":
        for kind, text in (("evaluation_final", "发送评测修改版"),
                           ("evaluation_redline", "发送评测修订痕迹"),
                           ("report_md" if downloads.get("report_md") else "report_json", "发送报告")):
            if downloads.get(kind) and (kind, text) not in sendable:
                sendable.append((kind, text))
    else:
        for kind, text in (("final", "发送最终版"), ("redline", "发送修订版"),
                           ("report_md" if downloads.get("report_md") else "report_json", "发送报告")):
            if downloads.get(kind) and (kind, text) not in sendable:
                sendable.append((kind, text))
        if not downloads.get("final") and downloads.get("working_final"):
            sendable.append(("working_final", "发送工作文件"))
    if len(sendable) > 1:
        buttons.append(_button("发送全部交付", "send_file",
                               extra={"task_type": mode, "task_id": task_id, "kind": "all"}))
    for kind, text in sendable:
        buttons.append(_button(text, "send_file", style="default" if buttons else "primary",
                               extra={"task_type": mode, "task_id": task_id, "kind": kind}))
    buttons.append(_button("打开工作台", "open_workbench", style="default"))
    template = "orange" if attention else "red" if task.get("status") in {"failed", "completed_with_exceptions"} else "green"
    return _card(title, [_markdown("\n".join(lines) + link), _actions(*buttons)], template=template)


def task_list_card(items: list[dict[str, Any]], *, page: int = 1, has_more: bool = False,
                   has_prev: bool = False, start: int = 0) -> dict[str, Any]:
    if not items:
        return _card("我的任务", [_markdown("暂无任务。"),
                                  _actions(_button("刷新", "show_tasks", style="default"),
                                           _button("任务中心", "menu", style="default"))])
    elements: list[dict[str, Any]] = [_markdown(f"第 {page} 页")]
    for index, item in enumerate(items, 1):
        label = TYPE_LABELS.get(item.get("task_type") or "revision", "任务")
        status = status_label(item.get("status"))
        detail = item.get("detail") or ""
        elements.append(_markdown(f"**{start + index}. {label} · {item.get('name') or '未命名'}**\n"
                                  f"状态：{status}" + (f"\n{detail}" if detail else "")))
        buttons = []
        if item.get("task_id"):
            buttons.append(_button("查看", "view_task", extra={"task_type": item.get("task_type") or "revision",
                                                               "task_id": item["task_id"]}))
            if item.get("can_send"):
                buttons.append(_button("发送报告", "send_file", style="default",
                                       extra={"task_type": item.get("task_type") or "revision",
                                              "task_id": item["task_id"], "kind": "report_md"}))
        if buttons:
            elements.append(_actions(*buttons))
    nav = []
    if has_prev:
        nav.append(_button("上一页", "show_tasks", style="default", extra={"page": page - 1}))
    nav.append(_button("刷新", "show_tasks", style="default", extra={"page": page}))
    if has_more:
        nav.append(_button("下一页", "show_tasks", style="default", extra={"page": page + 1}))
    nav.append(_button("任务中心", "menu", style="default"))
    elements.append(_actions(*nav))
    return _card("我的任务", elements)


def notice_card(title: str, content: str, *, template: str = "blue",
                buttons: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    elements = [_markdown(content)]
    if buttons:
        elements.append(_actions(*buttons))
    return _card(title, elements, template=template)


def text_card(title: str, content: str) -> dict[str, Any]:
    return _card(title, [_markdown(content)])


def retired_card(reason: str) -> dict[str, Any]:
    """Small placeholder used when a newer card replaces an older one."""
    return _card("卡片已更新", [
        _markdown(f"{reason}\n请使用会话中**最新的一张卡片**继续；旧按钮不再生效。"),
    ], template="grey")
