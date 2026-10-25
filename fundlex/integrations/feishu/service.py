"""Feishu orchestration around the existing FundLex task and worker stores."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from ...upload_validation import UploadValidationError, validate_docx_upload
from ..store import IntegrationConflict, IntegrationStore
from .cards import draft_card, status_card, text_card
from .events import MessageEvent, parse_message_event, _get

log = logging.getLogger(__name__)
_ACTIVE: "FeishuService | None" = None
_BINDING = re.compile(r"^(?:绑定|bind)\s*[:：]?\s*([A-Za-z0-9_-]{6,64})$", re.I)


def active_service() -> "FeishuService | None":
    return _ACTIVE


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "__dict__"):
        return {key: _plain(item) for key, item in vars(value).items() if not key.startswith("_")}
    return str(value)


class FeishuService:
    provider = "feishu"

    def __init__(self, store, tasks, task_service, client, *, base_url: str = ""):
        self.store = store
        self.tasks = tasks
        self.task_service = task_service
        self.client = client
        self.integrations = IntegrationStore(store)
        self.base_url = base_url or os.environ.get("FUNDLEX_PUBLIC_BASE_URL", "")
        self._stop = threading.Event()

    def install(self) -> None:
        global _ACTIVE
        _ACTIVE = self

    def stop(self) -> None:
        self._stop.set()

    def handle_message_event(self, data: Any) -> None:
        event = parse_message_event(data)
        if not event.event_id or not event.open_id or not event.chat_id:
            return
        payload = _plain(data)
        try:
            if not self.integrations.record_event(self.provider, event.event_id, event.event_type, payload):
                return
            self._handle_message(event)
            self.integrations.mark_event(self.provider, event.event_id, "processed")
        except IntegrationConflict as exc:
            # A conflicting event id is an integrity alarm. Do not mutate the
            # already stored event row while handling the untrusted duplicate.
            log.warning("Feishu event conflict event_id=%s code=%s", event.event_id, str(exc))
        except Exception as exc:  # event callback must remain short and recoverable
            log.warning("Feishu event failed event_id=%s error=%s", event.event_id, type(exc).__name__)
            self.integrations.mark_event(self.provider, event.event_id, "dead", type(exc).__name__)

    def handle_card_action_event(self, data: Any) -> str:
        header = _get(data, "header", default={})
        event_id = str(_get(header, "event_id", "eventId", default="") or "")
        if event_id:
            try:
                if not self.integrations.record_event(self.provider, event_id, "p2.card.action.trigger", _plain(data)):
                    return "该按钮操作已处理。"
            except IntegrationConflict as exc:
                log.warning("Feishu card action conflict event_id=%s code=%s", event_id, str(exc))
                return "按钮事件已失效，请重新发送附件。"
        try:
            result = self._handle_card_action_event(data)
            if event_id:
                self.integrations.mark_event(self.provider, event_id, "processed")
            return result
        except Exception as exc:
            if event_id:
                self.integrations.mark_event(self.provider, event_id, "dead", type(exc).__name__)
            log.warning("Feishu card action failed event_id=%s error=%s", event_id, type(exc).__name__)
            return "操作失败，请在 FundLex 工作台查看详情。"

    def _handle_card_action_event(self, data: Any) -> str:
        event = _get(data, "event", default={})
        operator = _get(event, "operator", default={})
        context = _get(event, "context", default={})
        action = _get(event, "action", default={})
        value = _get(action, "value", default={}) or {}
        command = str(value.get("command") or "").strip().lower()
        tenant_key = str(_get(operator, "tenant_key", "tenantKey", default="") or "")
        open_id = str(_get(operator, "open_id", "openId", default="") or "")
        chat_id = str(_get(context, "open_chat_id", "openChatId", default="") or "")
        message_id = str(_get(context, "open_message_id", "openMessageId", default="") or "")
        draft_id = str(value.get("draft_id") or "")
        if command not in {"confirm", "cancel"} or not tenant_key or not open_id or not chat_id:
            return "按钮已失效，请重新发送附件。"
        binding = self.integrations.identity(self.provider, tenant_key, open_id)
        if binding is None:
            return "请先绑定 FundLex 账号。"
        draft = self.integrations.active_draft(tenant_key, open_id, chat_id)
        if draft_id and (draft is None or draft["id"] != draft_id):
            return "该任务草稿已过期，请重新发送附件。"
        if command == "confirm":
            result = self.submit_draft(self._synthetic_event(tenant_key, open_id, chat_id, message_id), binding["user_id"], draft_id=draft_id or (draft or {}).get("id", ""))
            return {"submitted": "已提交，Worker 正在处理。",
                    "busy": "该草稿正在创建任务，请稍候。",
                    "failed": "提交失败，请稍后重试或在 FundLex 工作台查看详情。",
                    "missing": "没有可提交的任务草稿。"}.get(result, "操作失败，请稍后重试。")
        if draft:
            self.integrations.set_draft(draft["id"], status="CANCELLED")
        self.client.send_card(chat_id, text_card("已取消", "本次合同任务草稿已取消。"))
        return "草稿已取消。"

    @staticmethod
    def _synthetic_event(tenant_key: str, open_id: str, chat_id: str, message_id: str) -> MessageEvent:
        return MessageEvent(f"card:{message_id}", "p2.card.action.trigger", tenant_key, open_id, chat_id,
                            "p2p", message_id, "interactive", {"text": "确认"})

    def _send(self, event: MessageEvent, card: dict[str, Any]) -> None:
        self.client.send_card(event.chat_id, card)

    def _send_best_effort(self, event: MessageEvent, card: dict[str, Any]) -> None:
        try:
            self._send(event, card)
        except Exception as exc:
            log.warning("Feishu notification failed chat_id=%s error=%s", event.chat_id, type(exc).__name__)

    def _handle_message(self, event: MessageEvent) -> None:
        if event.chat_type not in {"p2p", "private"}:
            self._send(event, text_card("FundLex", "请在与 FundLex 机器人的私聊中使用合同任务。"))
            return
        binding = self.integrations.identity(self.provider, event.tenant_key, event.open_id)
        match = _BINDING.match(event.text)
        if match:
            try:
                owner = self.integrations.consume_binding_code(self.provider, event.tenant_key, event.open_id, match.group(1))
            except IntegrationConflict as exc:
                self._send(event, text_card("绑定失败", str(exc)))
                return
            self._send(event, text_card("绑定成功", f"已绑定 FundLex 账号。现在可以发送 DOCX 附件创建合同任务。账号：{owner[:8]}…"))
            return
        if binding is None:
            self._send(event, text_card("需要绑定账号", "请先在 FundLex 工作台“设置”中生成绑定码，再发送：绑定 绑定码"))
            return
        if event.message_type == "file":
            self._receive_file(event, binding["user_id"])
            return
        text = event.text
        if text in {"确认", "确认创建", "创建任务", "confirm"}:
            self.submit_draft(event, binding["user_id"])
        elif text in {"取消", "cancel"}:
            draft = self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)
            if draft:
                self.integrations.set_draft(draft["id"], status="CANCELLED")
            self._send(event, text_card("已取消", "本次合同任务草稿已取消。"))
        elif text:
            draft = self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)
            if draft is None:
                draft = self.integrations.create_draft(event.tenant_key, event.open_id, event.chat_id, binding["user_id"], text[:200])
                self._send(event, draft_card(draft["name"], [], error="请继续发送一个或多个 DOCX 附件。", draft_id=draft["id"]))
            else:
                self._send(event, draft_card(draft["name"], self.integrations.draft_files(draft["id"]), draft_id=draft["id"]))

    def _receive_file(self, event: MessageEvent, owner: str) -> None:
        draft = self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)
        if draft is None:
            draft = self.integrations.create_draft(event.tenant_key, event.open_id, event.chat_id, owner, "飞书合同任务")
        content = event.content
        file_key = str(content.get("file_key") or content.get("fileKey") or "")
        name = str(content.get("file_name") or content.get("fileName") or "合同.docx")
        if not file_key:
            self.integrations.set_draft(draft["id"], error_code="FEISHU_FILE_KEY_MISSING")
            self._send(event, draft_card(draft["name"], self.integrations.draft_files(draft["id"]), error="附件资源标识缺失，请重新发送。", draft_id=draft["id"]))
            return
        if any(item["message_id"] == event.message_id and item["file_key"] == file_key for item in self.integrations.draft_files(draft["id"])):
            return
        data, remote_name = self.client.download_message_resource(event.message_id, file_key, "file")
        name = Path(remote_name or name).name
        try:
            validate_docx_upload(name, data)
            storage_key, digest, size = self.store.stage(data)
        except UploadValidationError as exc:
            self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, len(data), hashlib.sha256(data).hexdigest(), "", "rejected", exc.code)
            self._send(event, draft_card(draft["name"], self.integrations.draft_files(draft["id"]), error=exc.code, draft_id=draft["id"]))
            return
        self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, size, digest, storage_key)
        self._send(event, draft_card(draft["name"], self.integrations.draft_files(draft["id"]), draft_id=draft["id"]))

    def submit_draft(self, event: MessageEvent, owner: str, *, draft_id: str = "") -> str:
        draft = self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)
        if draft_id:
            if not draft or draft["id"] != draft_id:
                self._send(event, text_card("任务草稿已过期", "请重新发送 DOCX 附件。"))
                return "missing"
        if draft:
            files = [item for item in self.integrations.draft_files(draft["id"]) if item["status"] == "accepted"]
            if not files:
                self._send(event, text_card("无法创建任务", "草稿中没有可用的 DOCX 附件。"))
                return "failed"
        if draft:
            claimed = self.integrations.claim_draft_for_submit(draft["id"])
            if claimed is None:
                if draft["status"] == "CONFIRMING":
                    self._send(event, text_card("正在创建任务", "该草稿已提交，正在等待任务卡片。"))
                    return "busy"
                return "busy"
            draft = claimed
        if not draft:
            self._send(event, text_card("没有待提交任务", "请先发送任务名称或 DOCX 附件。"))
            return "missing"
        files = [item for item in self.integrations.draft_files(draft["id"]) if item["status"] == "accepted"]
        if not files:
            self._send(event, text_card("无法创建任务", "草稿中没有可用的 DOCX 附件。"))
            return "failed"
        linked_task_id = ""
        try:
            task = self.task_service.create_task(owner, draft["name"],
                [{"client_id": f"feishu-{item['id']}", "name": item["name"], "size": item["size"]} for item in files],
                idempotency_key=draft["submit_idempotency_key"])
            uploads = []
            for item in files:
                path = self.store.object_path(item["storage_key"])
                data = path.read_bytes()
                uploads.append({"client_id": f"feishu-{item['id']}", "name": item["name"], "data": data})
            self.task_service.upload_files(owner, task["id"], uploads)
            self.task_service.seal_task(owner, task["id"])
            self.integrations.link_task(task["id"], draft, None)
            linked_task_id = task["id"]
            # Queue recovery before the first card send. If the WebSocket/API
            # call fails, the background outbox loop can still create the
            # initial status card without asking the user to resend files.
            self.integrations.add_outbox("task_status", task["id"], {"task_id": task["id"]}, f"task_status:{task['id']}:queued")
            card = status_card(draft["name"], task["status"], 0, task["total"], 0, "等待 Worker", self.base_url, task["id"])
            message_id = self.client.send_card(event.chat_id, card)
            self.integrations.set_channel_card(task["id"], message_id)
        except Exception as exc:
            if linked_task_id:
                # The task channel and recovery outbox are durable. Keep the
                # draft submitted so a later confirmation cannot create a
                # second task with a different state.
                self.integrations.set_draft(draft["id"], error_code=type(exc).__name__)
                self._send_best_effort(event, text_card("任务已创建", "状态卡片发送失败，后台会自动重试；请稍后查看任务状态。"))
                return "submitted"
            else:
                self.integrations.set_draft(draft["id"], status="COLLECTING", error_code=type(exc).__name__)
                self._send_best_effort(event, text_card("任务创建失败", "可以再次点击确认重试；请在 FundLex 工作台查看详细错误。"))
            return "failed"
        return "submitted"

    def sync_tasks(self) -> int:
        changed = 0
        for channel in self.integrations.channels():
            try:
                task = self.task_service.get_task(channel["owner_user_id"], channel["task_id"])
            except Exception:
                continue
            fingerprint = hashlib.sha256(json.dumps(task, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
            if self.integrations.update_channel(channel["task_id"], task["status"], int(task.get("completed", 0)), int(task.get("failed", 0)), str((task.get("delivery_counts") or {})), fingerprint):
                self.integrations.add_outbox("task_status", channel["task_id"], {"task_id": channel["task_id"]}, f"task_status:{channel['task_id']}:{fingerprint}")
                changed += 1
        return changed

    def send_outbox(self, limit: int = 20) -> int:
        sent = 0
        for item in self.integrations.pending_outbox(limit):
            try:
                payload = json.loads(item["payload_json"])
                channel = next((row for row in self.integrations.channels() if row["task_id"] == payload.get("task_id")), None)
                if channel is None:
                    self.integrations.finish_outbox(item["id"], error_code="FEISHU_CHANNEL_NOT_FOUND")
                    continue
                task = self.task_service.get_task(channel["owner_user_id"], channel["task_id"])
                card = status_card(task["name"], task["status"], int(task.get("completed", 0)), int(task.get("total", 0)), int(task.get("failed", 0)), str(task.get("delivery_counts") or {}), self.base_url, task["id"])
                if channel.get("card_message_id"):
                    self.client.update_card(channel["card_message_id"], card)
                else:
                    message_id = self.client.send_card(channel["chat_id"], card)
                    self.integrations.set_channel_card(channel["task_id"], message_id)
                self.integrations.finish_outbox(item["id"], fencing_token=int(item["fencing_token"]))
                sent += 1
            except Exception as exc:
                self.integrations.finish_outbox(item["id"], fencing_token=int(item["fencing_token"]), error_code=type(exc).__name__, retry=int(item.get("attempts", 1)) < 5)
        return sent

    def run_background(self, interval: float = 5.0) -> None:
        self.install()
        while not self._stop.wait(interval):
            self.sync_tasks()
            self.send_outbox()
