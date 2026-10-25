"""Interactive cards kept deliberately small and stable for private chats."""
from __future__ import annotations

from typing import Any


def _button(text: str, value: str, draft_id: str = "") -> dict[str, Any]:
    action = {"command": value}
    if draft_id:
        action["draft_id"] = draft_id
    return {"tag": "button", "text": {"tag": "plain_text", "content": text}, "type": "primary", "value": action}


def draft_card(name: str, files: list[dict[str, Any]], *, error: str | None = None, draft_id: str = "") -> dict[str, Any]:
    lines = [f"**{name}**", f"已添加 {len(files)} 个 DOCX 文件。"]
    lines.extend(f"{index}. {item['name']}（{item['size']} bytes）" for index, item in enumerate(files, 1))
    if error:
        lines.append(f"⚠️ {error}")
    return {"schema": "2.0", "header": {"template": "blue", "title": {"tag": "plain_text", "content": "FundLex 合同任务"}},
            "body": {"elements": [{"tag": "markdown", "content": "\n".join(lines)},
                                      {"tag": "action", "actions": [_button("确认创建任务", "confirm", draft_id), _button("取消", "cancel", draft_id)] }]}}


def status_card(name: str, status: str, completed: int, total: int, failed: int, delivery: str, base_url: str = "", task_id: str = "") -> dict[str, Any]:
    title = "任务已完成" if status == "completed" else "任务处理状态"
    link = f"\n[打开 FundLex 详情]({base_url.rstrip('/')}/tasks/{task_id})" if base_url and task_id else ""
    content = f"**{name}**\n状态：{status}\n合同：{completed}/{total} 已处理\n失败：{failed}\n交付：{delivery}{link}"
    return {"schema": "2.0", "header": {"template": "green" if status == "completed" else "blue", "title": {"tag": "plain_text", "content": title}},
            "body": {"elements": [{"tag": "markdown", "content": content}]}}


def text_card(title: str, content: str) -> dict[str, Any]:
    return {"schema": "2.0", "header": {"template": "blue", "title": {"tag": "plain_text", "content": title}},
            "body": {"elements": [{"tag": "markdown", "content": content}]}}
