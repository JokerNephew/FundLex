"""Feishu orchestration around the existing FundLex task and worker stores."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ...upload_validation import (MAX_BATCH_BYTES, UploadValidationError,
                                  has_tracked_revisions, validate_docx_upload)
from ...compare.ingest import prepare_compare_upload
from ...guide_generation.service import MAX_REGULATION_BYTES, create_run as create_guide_run
from ..store import IntegrationConflict, IntegrationStore
from .cards import (active_draft_card, compare_prompt_card, compare_status_card,
                    diagnosis_prompt_card, diagnosis_result_card, draft_card,
                    friendly_error, guide_confirm_card, guide_prompt_card, guide_status_card,
                    stage_label, status_label,
                    menu_card, notice_card, result_card, retired_card,
                    revision_status_card, task_list_card, task_name_card,
                    text_card)
from .events import MessageEvent, parse_message_event, _get

log = logging.getLogger(__name__)
_ACTIVE: "FeishuService | None" = None
_BINDING = re.compile(r"^(?:绑定|bind)\s*[:：]?\s*([A-Za-z0-9_-]{6,64})$", re.I)
_CONFIRM = {"确认", "确认创建", "创建任务", "confirm"}
_CANCEL = {"取消", "cancel"}
_MENU = {"菜单", "任务中心", "help", "帮助", "/menu"}
_TASKS = {"任务", "我的任务", "/tasks", "任务列表"}
_TASK_PAGE_SIZE = 6
_START = {
    "合同修订": "revision", "修订": "revision", "revision": "revision",
    "合同对比": "compare", "对比": "compare", "compare": "compare",
    "生成指引": "guide", "法规指引": "guide", "指引生成": "guide",
    "只读诊断": "diagnosis", "诊断": "diagnosis", "diagnosis": "diagnosis",
    "评测": "evaluation", "evaluation": "evaluation",
}
_TASK_LABELS = {"revision": "合同修订", "compare": "合同对比", "guide": "法规指引生成",
                "diagnosis": "只读诊断", "evaluation": "评测"}


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


def _key(value: Any) -> str:
    return str(value or "").strip().casefold()


class FeishuService:
    provider = "feishu"

    def __init__(self, store, tasks, task_service, client, *, base_url: str = "",
                 compare_store=None, guide_store=None):
        self.store = store
        self.tasks = tasks
        self.task_service = task_service
        self.client = client
        self.integrations = IntegrationStore(store)
        self.compare = compare_store
        self.guides = guide_store
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

    # ------------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------------
    def _handle_message(self, event: MessageEvent) -> None:
        if event.chat_type not in {"p2p", "private"}:
            self._send(event, text_card("FundLex", "请在与 FundLex 机器人的私聊中使用任务中心。"))
            return
        binding = self.integrations.identity(self.provider, event.tenant_key, event.open_id)
        match = _BINDING.match(event.text)
        if match:
            try:
                owner = self.integrations.consume_binding_code(self.provider, event.tenant_key, event.open_id, match.group(1))
            except IntegrationConflict as exc:
                self._send(event, text_card("绑定失败", str(exc)))
                return
            self._send(event, text_card("绑定成功", f"已绑定 FundLex 账号。现在可以发送 DOCX 创建任务。账号：{owner[:8]}…"))
            menu_id = self._send(event, menu_card(None, note="本卡片已自动置顶；以后可直接从会话置顶区打开，不用再发“菜单”。"))
            self._pin_menu(event, menu_id)
            return
        if binding is None:
            self._send(event, text_card("需要绑定账号", "请先在 FundLex 工作台“设置”中生成绑定码或二维码，再发送：绑定 绑定码"))
            return

        text = event.text
        lowered = _key(text)
        if lowered in _MENU:
            self._show_menu(event)
            return
        if lowered in _TASKS:
            self._show_tasks(event, binding["user_id"])
            return
        if lowered in _START:
            self._start_flow(event, binding["user_id"], _START[lowered])
            return

        active = self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)
        if event.message_type == "file":
            if active is None:
                active = self._create_draft(event, binding["user_id"], "revision",
                                            self._time_name("revision"), step="collecting", send=False)
            if (active.get("step") or "") == "name":
                self.integrations.update_draft(active["id"], step=self._step_after_name(active.get("task_type") or "revision"))
                active = self.integrations.draft(active["id"])
            self._receive_file(event, binding["user_id"], active)
            return
        if event.message_type not in {"text", "file"}:
            self._send(event, text_card("请发送文件", "请以文件形式发送 DOCX（法规指引可发 PDF）；图片、语音、视频和普通文本不能作为合同附件。"))
            return
        if active is not None:
            self._handle_active_text(event, binding["user_id"], active, text)
            return
        if lowered in _CONFIRM or lowered in _CANCEL:
            self._send(event, text_card("没有待处理任务", "请先在任务中心选择任务类型并发送文件。"))
            return
        if text:
            self._show_menu(event, note="未识别为任务命令。请从任务中心选择业务类型；合同修订可直接发送 DOCX。")
            return
        self._show_menu(event)

    def _handle_active_text(self, event: MessageEvent, owner: str, draft: dict[str, Any], text: str) -> None:
        lowered = _key(text)
        if (draft.get("step") or "") == "name":
            # Legacy drafts created before the file-first rollout.
            if lowered in _CANCEL:
                self._cancel_draft(event, draft)
                return
            if text and lowered not in _CONFIRM:
                self._save_task_name(event, draft, text)
                return
            self._send(event, task_name_card(draft, error="请先填写任务名称，再发送文件。"))
            return
        if lowered in _CONFIRM:
            result = self.submit_draft(event, owner, draft_id=draft["id"])
            if result == "submitted":
                return
            self._send(event, text_card("提交结果", {
                "busy": "该草稿正在处理，请稍候。",
                "failed": "提交失败，请稍后重试或在 FundLex 工作台查看详情。",
                "missing": "没有可提交的任务草稿。",
            }.get(result, "操作失败，请稍后重试。")))
            return
        if lowered in _CANCEL:
            self._cancel_draft(event, draft)
            return
        if text:
            self._send(event, text_card("需要我做什么？",
                                        "发送文件可继续添加；发送 `确认` 创建任务，"
                                        "发送 `取消` 放弃本次任务。"))
            self._send_card_for_draft(event, draft)
            return
        self._send_card_for_draft(event, draft)

    def _handle_card_action_event(self, data: Any) -> str:
        event_data = _get(data, "event", default={})
        operator = _get(event_data, "operator", default={})
        context = _get(event_data, "context", default={})
        action = _get(event_data, "action", default={})
        value = _get(action, "value", default={}) or {}
        form_value = _get(action, "form_value", default={}) or {}
        if isinstance(form_value, str):
            try:
                form_value = json.loads(form_value)
            except (TypeError, ValueError):
                form_value = {}
        if not isinstance(form_value, dict):
            form_value = {}
        action_name = str(_get(action, "name", default="") or "")
        command = str(value.get("command") or "").strip().lower()
        tenant_key = str(_get(operator, "tenant_key", "tenantKey", default="") or "")
        open_id = str(_get(operator, "open_id", "openId", default="") or "")
        chat_id = str(_get(context, "open_chat_id", "openChatId", default="") or "")
        message_id = str(_get(context, "open_message_id", "openMessageId", default="") or "")
        if not tenant_key or not open_id:
            return "按钮已失效，请重新发送附件。"
        binding = self.integrations.identity(self.provider, tenant_key, open_id)
        if binding is None:
            return "请先绑定 FundLex 账号。"
        if not chat_id:
            draft = self.integrations.active_draft(tenant_key, open_id, "")
            chat_id = (draft or {}).get("chat_id", "")
        if not chat_id:
            return "按钮已失效，请重新发送附件。"
        event = self._synthetic_event(tenant_key, open_id, chat_id, message_id, command or action_name)
        owner = binding["user_id"]

        if form_value or action_name == "save_task_name" or command == "skip_name":
            # Feishu may return a generated button name for form submissions;
            # the presence of form_value plus the active draft step is the
            # stable contract, not the button label/name.
            log.info("Feishu form submit name=%s fields=%s", action_name, sorted(form_value))
            draft = self._draft_for(event, "")
            if draft is None or (draft.get("step") or "") != "name":
                return "该任务名称卡片已过期，请重新选择任务。"
            name = str(form_value.get("task_name") or "").strip() or str(draft.get("name") or "飞书合同任务")
            self._save_task_name(event, draft, name)
            return "任务名称已保存，请发送文件。"

        if not command:
            # Defensive fallback for Feishu clients that drop form_value or
            # generate an unknown form button name. The name card only has
            # save/skip/cancel actions, so an unknown action is a submit.
            draft = self._draft_for(event, "")
            if draft is not None and (draft.get("step") or "") == "name":
                log.info("Feishu name card fallback name=%s value=%s form=%s",
                         action_name, sorted(value), sorted(form_value))
                self._save_task_name(event, draft, str(draft.get("name") or "飞书合同任务"))
                return "任务名称已保存，请发送文件。"

        if command in {"menu", "open_workbench"}:
            if command == "open_workbench":
                link = f"{self.base_url.rstrip('/')}/" if self.base_url else ""
                self._send(event, notice_card("FundLex 工作台",
                                              f"请打开工作台查看完整详情：{link}" if link else "请登录 FundLex 工作台查看。"))
                return "已发送工作台链接。"
            self._show_menu(event, message_id=message_id)
            return "已打开任务中心。"
        if command in {"start_revision", "start_compare", "start_guide", "start_diagnosis", "start_evaluation"}:
            task_type = command.removeprefix("start_")
            self._start_flow(event, owner, task_type, message_id=message_id)
            return "已进入对应任务。"
        if command == "show_tasks":
            # Never replace the pinned task-centre card with a task list.
            pinned = self.integrations.get_state(
                self.provider, f"menu_card:{tenant_key}:{open_id}")
            target_message = "" if message_id and message_id == pinned else message_id
            self._show_tasks(event, owner, page=int(value.get("page") or 1),
                             message_id=target_message)
            return "已刷新任务列表。"
        if command == "continue_draft":
            draft = self.integrations.active_draft(tenant_key, open_id, chat_id)
            if draft:
                self._send_card_for_draft(event, draft, new_message=True)
                return "已恢复当前草稿。"
            self._show_menu(event, message_id=message_id)
            return "当前没有未完成草稿。"
        if command == "switch_task":
            target = str(value.get("task_type") or "")
            if target not in _TASK_LABELS:
                return "任务类型无效，请返回任务中心重新选择。"
            draft = self.integrations.active_draft(tenant_key, open_id, chat_id)
            if draft and target:
                self._cancel_draft(event, draft, notify=False)
                self._start_flow(event, owner, target)
                return "已取消当前草稿并开始新任务。"
            return "当前草稿已变化，请重新选择任务。"
        if command == "cancel":
            draft = self._draft_for(event, str(value.get("draft_id") or ""))
            if draft:
                self._cancel_draft(event, draft)
                return "草稿已取消。"
            return "没有可取消的草稿。"
        if command in {"remove_file", "replace_side", "replace_file"}:
            draft = self._draft_for(event, str(value.get("draft_id") or ""))
            if draft is None:
                return "该任务草稿已过期，请重新发送文件。"
            task_type = draft.get("task_type") or "revision"
            if command == "replace_side":
                side = str(value.get("side") or "")
                if task_type != "compare" or side not in {"left", "right"}:
                    return "该对比草稿已过期，请重新发送文件。"
                for item in self._accepted_files(draft["id"]):
                    if item.get("side") == side:
                        self.integrations.remove_draft_file(draft["id"], item["id"])
                self.integrations.update_draft(draft["id"], step=side)
                self._send_card_for_draft(event, self.integrations.draft(draft["id"]))
                return f"请发送新的{'左' if side == 'left' else '右'}侧 DOCX。"
            file_id = str(value.get("file_id") or "")
            removed = self.integrations.remove_draft_file(draft["id"], file_id) if file_id else None
            if removed is None:
                return "该文件已不在草稿中。"
            if command == "replace_file":
                self.integrations.update_draft(draft["id"], step="waiting_file")
            elif task_type == "compare":
                self.integrations.update_draft(draft["id"], step=removed.get("side") or "left")
            elif task_type == "guide":
                self.integrations.update_draft(draft["id"], step="waiting_file")
            self._send_card_for_draft(event, self.integrations.draft(draft["id"]))
            return "已移除文件。"
        if command in {"swap_sides", "reset_left"}:
            draft = self._draft_for(event, str(value.get("draft_id") or ""))
            if draft is None or (draft.get("task_type") or "") != "compare":
                return "该对比草稿已过期，请重新发送附件。"
            if command == "swap_sides":
                if not self.integrations.swap_draft_files(draft["id"]):
                    return "左右文件不完整，暂时不能交换。"
            else:
                self.integrations.update_draft(draft["id"], step="left")
            self._send_card_for_draft(event, self.integrations.draft(draft["id"]))
            return "已更新对比文件。"
        if command == "confirm":
            draft = self._draft_for(event, str(value.get("draft_id") or ""))
            if draft is None:
                return "该任务草稿已过期，请重新发送附件。"
            result = self.submit_draft(event, owner, draft_id=draft["id"])
            return {
                "submitted": "已提交，Worker 正在处理。",
                "busy": "该草稿正在创建任务，请稍候。",
                "failed": "提交失败，请稍后重试或在 FundLex 工作台查看详情。",
                "missing": "没有可提交的任务草稿。",
            }.get(result, "操作失败，请稍后重试。")
        if command == "view_task":
            return self._view_task(event, owner, str(value.get("task_type") or "revision"),
                                   str(value.get("task_id") or ""))
        if command == "send_file":
            return self._send_result_file(event, owner, str(value.get("task_type") or "revision"),
                                          str(value.get("task_id") or ""), str(value.get("kind") or ""))
        return "按钮已失效，请重新发送附件。"

    # ------------------------------------------------------------------
    # Draft lifecycle
    # ------------------------------------------------------------------
    def _accepted_files(self, draft_id: str) -> list[dict[str, Any]]:
        return [item for item in self.integrations.draft_files(draft_id) if item["status"] == "accepted"]

    def _create_draft(self, event: MessageEvent, owner: str, task_type: str, name: str,
                      *, step: str | None = None, metadata: dict[str, Any] | None = None,
                      send: bool = True) -> dict[str, Any]:
        metadata = metadata or {}
        draft = self.integrations.create_draft(
            event.tenant_key, event.open_id, event.chat_id, owner, name,
            task_type=task_type, step=step or self._initial_step(task_type), metadata=metadata)
        self._refresh_pinned_menu(event, draft)
        if not send:
            return draft
        self._send_card_for_draft(event, draft)
        return self.integrations.draft(draft["id"])

    def _card_for_draft(self, draft: dict[str, Any]) -> dict[str, Any]:
        task_type = draft.get("task_type") or "revision"
        if (draft.get("step") or "") == "name":
            return task_name_card(draft)
        files = [item for item in self.integrations.draft_files(draft["id"])
                 if item.get("status") in {"accepted", "rejected"}]
        if task_type == "revision":
            return draft_card(draft["name"], files, draft_id=draft["id"])
        if task_type in {"diagnosis", "evaluation"}:
            return draft_card(draft["name"], files, draft_id=draft["id"], mode=task_type)
        if task_type == "compare":
            accepted = [item for item in files if item.get("status") == "accepted"]
            left = next((f for f in accepted if f.get("side") == "left"), None)
            right = next((f for f in accepted if f.get("side") == "right"), None)
            step = draft.get("step") or ("confirm" if left and right else "right" if left else "left")
            return compare_prompt_card(draft["id"], step, left, right, name=draft.get("name") or "")
        if task_type == "guide":
            regulation = next((f for f in files if f.get("kind") == "regulation"
                               and f.get("status") == "accepted"), None)
            if regulation:
                return guide_confirm_card(draft["id"], regulation["name"], regulation["size"],
                                          regulation["id"], task_name=draft.get("name") or "")
            return guide_prompt_card(draft["id"])
        return text_card("FundLex", "当前任务类型不可用，请返回任务中心。")

    def _send_card_for_draft(self, event: MessageEvent, draft: dict[str, Any], *,
                             new_message: bool = False) -> None:
        card = self._card_for_draft(draft)
        if new_message and draft.get("card_message_id"):
            self._retire_card(draft["card_message_id"])
        message_id = "" if new_message else (draft.get("card_message_id") or "")
        if message_id:
            try:
                self.client.update_card(message_id, card)
                return
            except Exception as exc:
                log.warning("Feishu card update failed message_id=%s error=%s", message_id, type(exc).__name__)
        sent = self._send(event, card)
        if sent:
            self.integrations.update_draft(draft["id"], card_message_id=sent)

    def _draft_for(self, event: MessageEvent, draft_id: str) -> dict[str, Any] | None:
        if draft_id:
            try:
                draft = self.integrations.draft(draft_id)
            except Exception:
                return None
            if (draft["tenant_key"], draft["open_id"], draft["chat_id"]) != (event.tenant_key, event.open_id, event.chat_id):
                return None
            if draft["status"] not in {"COLLECTING", "CONFIRMING"}:
                return None
            return draft
        return self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)

    @staticmethod
    def _time_name(task_type: str) -> str:
        label = _TASK_LABELS.get(task_type, "飞书任务")
        return f"{label} {datetime.now():%Y-%m-%d %H:%M:%S}"

    @staticmethod
    def _initial_step(task_type: str) -> str:
        return {"compare": "left", "guide": "waiting_file"}.get(task_type, "collecting")

    @staticmethod
    def _step_after_name(task_type: str) -> str:
        # Kept for drafts created before the file-first rollout.
        return FeishuService._initial_step(task_type)

    def _save_task_name(self, event: MessageEvent, draft: dict[str, Any], name: str) -> None:
        clean = (name or "").strip()[:200]
        if not clean:
            self._send(event, task_name_card(draft, error="任务名称不能为空。"))
            return
        task_type = draft.get("task_type") or "revision"
        metadata = {**self.integrations.draft_metadata(draft), "name_source": "manual"}
        self.integrations.update_draft(draft["id"], name=clean, step=self._step_after_name(task_type),
                                       metadata=metadata)
        # A submitted form card can be removed/rewritten by the Feishu client.
        # Always use a fresh message for the next step so it remains visible.
        self._send_card_for_draft(event, self.integrations.draft(draft["id"]), new_message=True)

    def _retire_card(self, message_id: str, reason: str = "这张卡片已被新卡片替代。") -> None:
        if not message_id:
            return
        try:
            self.client.update_card(message_id, retired_card(reason))
        except Exception as exc:
            log.warning("Feishu card retire failed message_id=%s error=%s",
                        message_id, type(exc).__name__)

    def _pin_menu(self, event: MessageEvent, message_id: str) -> None:
        """Keep exactly one pinned task-centre card for this private chat."""
        if not message_id:
            return
        pin = getattr(self.client, "pin_message", None)
        unpin = getattr(self.client, "unpin_message", None)
        if pin is None or unpin is None:
            return
        key = f"menu_card:{event.tenant_key}:{event.open_id}"
        previous = self.integrations.get_state(self.provider, key)
        try:
            if previous and previous != message_id:
                try:
                    unpin(previous)
                except Exception as exc:
                    log.warning("Feishu old menu unpin failed error=%s", type(exc).__name__)
            pin(message_id)
            self.integrations.set_state(self.provider, key, message_id)
        except Exception as exc:
            log.warning("Feishu menu pin failed chat_id=%s error=%s", event.chat_id, type(exc).__name__)

    def _refresh_pinned_menu(self, event: MessageEvent, active: dict[str, Any] | None) -> None:
        """Keep the pinned entry in sync with the current draft state."""
        message_id = self.integrations.get_state(
            self.provider, f"menu_card:{event.tenant_key}:{event.open_id}")
        if not message_id:
            return
        try:
            self.client.update_card(message_id, menu_card(active))
        except Exception as exc:
            log.warning("Feishu pinned menu refresh failed chat_id=%s error=%s",
                        event.chat_id, type(exc).__name__)

    def _cancel_draft(self, event: MessageEvent, draft: dict[str, Any], *,
                      notify: bool = True) -> None:
        self.integrations.update_draft(draft["id"], status="CANCELLED", error_code="")
        self._refresh_pinned_menu(event, None)
        self._retire_card(draft.get("card_message_id") or "", "本次任务草稿已取消。")
        try:
            self.integrations.discard_draft_files(draft["id"])
        except Exception as exc:
            log.warning("Feishu draft cleanup failed draft=%s error=%s", draft["id"], type(exc).__name__)
        if notify:
            # A cancelled draft must leave the user with a working entry point,
            # not just a one-line "cancelled" notice.  Re-send the task centre
            # and make it the current pinned card.
            try:
                self._show_menu(event, note="本次任务草稿已取消，暂存文件已清理。请重新选择任务。")
            except Exception as exc:
                log.warning("Feishu cancel menu failed chat_id=%s error=%s",
                            event.chat_id, type(exc).__name__)

    def _start_flow(self, event: MessageEvent, owner: str, task_type: str, *, message_id: str = "") -> None:
        # Always emit a fresh card message. Updating the clicked menu card in
        # place looks like a transient toast to users when the menu is far up
        # the chat, and makes it look as if no next step appeared.
        _ = message_id
        active = self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)
        if active is not None:
            if (active.get("task_type") or "revision") == task_type:
                self._send_card_for_draft(event, active, new_message=True)
            else:
                self._send(event, active_draft_card(active, f"start_{task_type}"))
            return
        self._create_draft(event, owner, task_type, self._time_name(task_type), send=True)

    def _show_menu(self, event: MessageEvent, *, message_id: str = "", note: str = "") -> None:
        active = self.integrations.active_draft(event.tenant_key, event.open_id, event.chat_id)
        card = menu_card(active, note)
        if message_id:
            try:
                self.client.update_card(message_id, card)
                return
            except Exception:
                pass
        sent = self._send(event, card)
        if sent:
            self._pin_menu(event, sent)

    # ------------------------------------------------------------------
    # Incoming files
    # ------------------------------------------------------------------
    def _receive_file(self, event: MessageEvent, owner: str, draft: dict[str, Any]) -> None:
        task_type = draft.get("task_type") or "revision"
        if task_type == "compare":
            self._receive_compare_file(event, draft)
        elif task_type == "guide":
            self._receive_guide_file(event, draft)
        else:
            self._receive_contract_file(event, owner, draft)

    def _receive_contract_file(self, event: MessageEvent, owner: str, draft: dict[str, Any]) -> None:
        content = event.content
        file_key = str(content.get("file_key") or content.get("fileKey") or "")
        name = str(content.get("file_name") or content.get("fileName") or "合同.docx")
        if not file_key:
            self.integrations.update_draft(draft["id"], error_code="FEISHU_FILE_KEY_MISSING")
            self._send_card_for_draft(event, draft)
            return
        if any(item["message_id"] == event.message_id and item["file_key"] == file_key
               for item in self.integrations.draft_files(draft["id"])):
            return
        try:
            data, remote_name = self.client.download_message_resource(event.message_id, file_key, "file")
        except Exception as exc:
            log.warning("Feishu file download failed draft=%s error=%s", draft["id"], type(exc).__name__)
            self._send(event, text_card("文件下载失败", "飞书没有返回该文件内容，请重新发送文件消息。"))
            self._send_card_for_draft(event, draft)
            return
        name = Path(remote_name or name).name
        digest = hashlib.sha256(data).hexdigest()
        accepted = self._accepted_files(draft["id"])
        if any(item.get("sha256") == digest for item in accepted):
            self._send(event, text_card("文件重复", "该文件已在当前任务中，未重复添加。"))
            self._send_card_for_draft(event, draft)
            return
        try:
            validate_docx_upload(name, data)
            # Tracked changes from another department are accepted; FundLex
            # overlays its own revisions with a distinct author.
        except UploadValidationError as exc:
            self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, len(data),
                                             digest, "", "rejected", exc.code)
            self._send_card_for_draft(event, draft)
            return
        if sum(int(item["size"]) for item in accepted) + len(data) > MAX_BATCH_BYTES:
            self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, len(data),
                                             digest, "", "rejected", "UPLOAD_REQUEST_SIZE_LIMIT")
            self._send_card_for_draft(event, draft)
            return
        try:
            storage_key, digest, size = self.store.stage(data)
        except Exception as exc:
            log.warning("Feishu file stage failed draft=%s error=%s", draft["id"], type(exc).__name__)
            self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, len(data),
                                             digest, "", "rejected", "FILE_STAGE_FAILED")
            self._send_card_for_draft(event, draft)
            return
        self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, size, digest, storage_key)
        self.integrations.update_draft(draft["id"], error_code="")
        draft = self.integrations.draft(draft["id"])
        # Put the first file card at the bottom of the chat so the confirm
        # button is visible right after the user's first upload.
        self._send_card_for_draft(event, draft, new_message=not accepted)

    def _receive_compare_file(self, event: MessageEvent, draft: dict[str, Any]) -> None:
        files = self._accepted_files(draft["id"])
        left = next((f for f in files if f.get("side") == "left"), None)
        right = next((f for f in files if f.get("side") == "right"), None)
        if left and right:
            self._send(event, compare_prompt_card(draft["id"], "confirm", left, right,
                                                  name=draft.get("name") or "",
                                                  error="左右文件都已收到；这份新文件未加入。如需替换请点“替换左侧/右侧”。"))
            return
        side = "left" if left is None else "right"
        content = event.content
        file_key = str(content.get("file_key") or content.get("fileKey") or "")
        name = str(content.get("file_name") or content.get("fileName") or f"{side}.docx")
        if not file_key:
            self._send(event, compare_prompt_card(draft["id"], side, left, right, error="附件资源标识缺失，请重新发送。"))
            return
        if any(item["message_id"] == event.message_id and item["file_key"] == file_key
               for item in self.integrations.draft_files(draft["id"])):
            return
        try:
            data, remote_name = self.client.download_message_resource(event.message_id, file_key, "file")
        except Exception as exc:
            log.warning("Feishu compare download failed draft=%s error=%s", draft["id"], type(exc).__name__)
            self._send(event, compare_prompt_card(draft["id"], side, left, right,
                                                  error="文件下载失败，请重新发送。"))
            return
        name = Path(remote_name or name).name
        original_digest = hashlib.sha256(data).hexdigest()
        if any(item.get("sha256") == original_digest and item.get("side") == side
               for item in self._accepted_files(draft["id"])):
            self._send(event, compare_prompt_card(draft["id"], side, left, right,
                                                  error="该文件已在当前侧，未重复添加。"))
            return
        if sum(int(item["size"]) for item in self._accepted_files(draft["id"])) + len(data) > MAX_BATCH_BYTES:
            self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, len(data),
                                             original_digest, "", "rejected",
                                             "UPLOAD_REQUEST_SIZE_LIMIT", side=side)
            self._send(event, compare_prompt_card(draft["id"], side, left, right,
                                                  error=friendly_error("UPLOAD_REQUEST_SIZE_LIMIT")))
            return
        try:
            prepared = prepare_compare_upload(name, data)
            storage_key, digest, size = self.store.stage(prepared["data"])
        except (UploadValidationError, ValueError) as exc:
            code = getattr(exc, "code", None) or "COMPARE_INVALID_DOCX"
            self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, len(data),
                                             original_digest, "", "rejected", code,
                                             side=side)
            self._send(event, compare_prompt_card(draft["id"], side, left, right, error=friendly_error(code)))
            return
        self.integrations.add_draft_file(
            draft["id"], event.message_id, file_key, name, prepared["original_size"],
            prepared["original_sha256"], storage_key, side=side,
            revisions_accepted=prepared["revisions_accepted"])
        updated_files = self._accepted_files(draft["id"])
        has_left = any(f.get("side") == "left" for f in updated_files)
        has_right = any(f.get("side") == "right" for f in updated_files)
        self.integrations.update_draft(draft["id"], step="confirm" if has_left and has_right else "right" if has_left else "left",
                                       error_code="")
        draft = self.integrations.draft(draft["id"])
        self._send_card_for_draft(event, draft)

    def _receive_guide_file(self, event: MessageEvent, draft: dict[str, Any]) -> None:
        existing = [f for f in self._accepted_files(draft["id"]) if f.get("kind") == "regulation"]
        if existing:
            self._send(event, text_card("已有法规原文", "这份新文件未加入；如需替换请在上方卡片点“替换文件”。"))
            return
        content = event.content
        file_key = str(content.get("file_key") or content.get("fileKey") or "")
        name = str(content.get("file_name") or content.get("fileName") or "regulation.pdf")
        if not file_key:
            self._send(event, guide_prompt_card(draft["id"], error="附件资源标识缺失，请重新发送。"))
            return
        if any(item["message_id"] == event.message_id and item["file_key"] == file_key
               for item in self.integrations.draft_files(draft["id"])):
            return
        try:
            data, remote_name = self.client.download_message_resource(event.message_id, file_key, "file")
        except Exception as exc:
            log.warning("Feishu guide download failed draft=%s error=%s", draft["id"], type(exc).__name__)
            self._send(event, guide_prompt_card(draft["id"], error="文件下载失败，请重新发送。"))
            return
        name = Path(remote_name or name).name
        suffix = Path(name).suffix.lower()
        if suffix not in {".pdf", ".docx"}:
            self._send(event, guide_prompt_card(draft["id"], error="只支持 PDF/DOCX 法规原文。"))
            return
        if not data or len(data) > MAX_REGULATION_BYTES:
            self._send(event, guide_prompt_card(draft["id"], error="法规文件为空或超过 80 MB。"))
            return
        if suffix == ".docx":
            try:
                validate_docx_upload(name, data)
            except UploadValidationError as exc:
                self._send(event, guide_prompt_card(draft["id"], error=friendly_error(exc.code)))
                return
        storage_key, digest, size = self.store.stage(data)
        self.integrations.add_draft_file(draft["id"], event.message_id, file_key, name, size, digest,
                                         storage_key, kind="regulation")
        self.integrations.update_draft(draft["id"], step="confirm", error_code="")
        draft = self.integrations.draft(draft["id"])
        self._send_card_for_draft(event, draft, new_message=not existing)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    def submit_draft(self, event: MessageEvent, owner: str, *, draft_id: str = "") -> str:
        draft = self._draft_for(event, draft_id)
        if draft is None:
            return "missing"
        task_type = draft.get("task_type") or "revision"
        if task_type == "compare":
            return self._submit_compare(event, owner, draft)
        if task_type == "guide":
            return self._submit_guide(event, owner, draft)
        return self._submit_contract(event, owner, draft)

    def _submit_contract(self, event: MessageEvent, owner: str, draft: dict[str, Any]) -> str:
        files = self._accepted_files(draft["id"])
        if not files:
            self._send(event, text_card("无法创建任务", "草稿中没有可用的 DOCX 附件。"))
            return "failed"
        claimed = self.integrations.claim_draft_for_submit(draft["id"])
        if claimed is None:
            self._send(event, text_card("正在创建任务", "该草稿已提交，正在等待任务卡片。"))
            return "busy"
        draft = claimed
        mode = {"diagnosis": "diagnosis", "evaluation": "evaluation"}.get(draft.get("task_type") or "revision", "delivery")
        linked_task_id = ""
        draft_card_id = draft.get("card_message_id") or ""
        try:
            task = self.task_service.create_task(owner, draft["name"],
                [{"client_id": f"feishu-{item['id']}", "name": item["name"], "size": item["size"]} for item in files],
                idempotency_key=draft["submit_idempotency_key"], mode=mode)
            uploads = []
            for item in files:
                data = self.store.object_path(item["storage_key"]).read_bytes()
                uploads.append({"client_id": f"feishu-{item['id']}", "name": item["name"], "data": data})
            self.task_service.upload_files(owner, task["id"], uploads)
            self.task_service.seal_task(owner, task["id"])
            channel_type = mode if mode in {"diagnosis", "evaluation"} else "revision"
            self.integrations.link_task(task["id"], draft, None, task_type=channel_type)
            self._refresh_pinned_menu(event, None)
            linked_task_id = task["id"]
            dedupe = (f"task_status:{task['id']}:queued" if mode == "delivery"
                      else f"task_status:{mode}:{task['id']}:queued")
            self.integrations.add_outbox("task_status", task["id"],
                                         {"task_id": task["id"], "task_type": channel_type}, dedupe)
            card = self._task_status_card(owner, task["id"], mode)
            message_id = self.client.send_card(event.chat_id, card)
            self.integrations.set_channel_card(task["id"], message_id)
            self._retire_card(draft_card_id, "任务已创建，请使用下方最新的状态卡。")
            try:
                self.integrations.discard_draft_files(draft["id"])
            except Exception:
                pass
        except Exception as exc:
            if linked_task_id:
                self.integrations.update_draft(draft["id"], error_code=type(exc).__name__)
                self._retire_card(draft_card_id, "任务已创建，状态卡正在自动重试。")
                self._send_best_effort(event, text_card("任务已创建", "状态卡片发送失败，后台会自动重试；请稍后查看任务状态。"))
                return "submitted"
            self.integrations.update_draft(draft["id"], status="COLLECTING", error_code=type(exc).__name__)
            self._send_best_effort(event, text_card("任务创建失败", "可以再次点击确认重试；请在 FundLex 工作台查看详细错误。"))
            return "failed"
        return "submitted"

    def _submit_compare(self, event: MessageEvent, owner: str, draft: dict[str, Any]) -> str:
        files = self._accepted_files(draft["id"])
        left = next((f for f in files if f.get("side") == "left"), None)
        right = next((f for f in files if f.get("side") == "right"), None)
        if left is None or right is None:
            self._send(event, compare_prompt_card(draft["id"], "confirm", left, right, error="请先补齐左右两份 DOCX。"))
            return "failed"
        if self.compare is None:
            self._send(event, text_card("对比服务未配置", "请联系管理员检查 Compare 服务。"))
            return "failed"
        claimed = self.integrations.claim_draft_for_submit(draft["id"])
        if claimed is None:
            self._send(event, text_card("正在创建任务", "该对比草稿已提交，请稍候。"))
            return "busy"
        draft = claimed
        target_id = str(draft.get("target_id") or "")
        draft_card_id = draft.get("card_message_id") or ""
        try:
            if target_id:
                current = self.compare.get(owner, target_id)
            else:
                pair = {"client_pair_id": "feishu-pair-1", "label": draft["name"],
                        "left": {"client_id": f"feishu-{left['id']}", "name": left["name"], "size": left["size"]},
                        "right": {"client_id": f"feishu-{right['id']}", "name": right["name"], "size": right["size"]}}
                task = self.compare.create(owner, draft["name"], [pair],
                                           idempotency_key=draft["submit_idempotency_key"])
                target_id = task["id"]
                current = task
                self.integrations.update_draft(draft["id"], target_id=target_id, task_id=target_id)
            if not current.get("sealed"):
                uploads = []
                for item in (left, right):
                    data = self.store.object_path(item["storage_key"]).read_bytes()
                    uploads.append({"client_id": f"feishu-{item['id']}", "name": item["name"], "data": data,
                                    "original_sha256": item["sha256"], "original_size": item["size"],
                                    "revisions_accepted": item.get("revisions_accepted", 0)})
                receipts = self.compare.upload(owner, target_id, uploads)
                if any(item.get("status") not in {"accepted", "already_accepted"}
                       for item in receipts.get("receipts") or []):
                    raise RuntimeError("COMPARE_UPLOAD_REJECTED")
                self.compare.seal(owner, target_id)
            self.integrations.link_task(target_id, draft, None, task_type="compare")
            self._refresh_pinned_menu(event, None)
            self.integrations.add_outbox("task_status", target_id,
                                         {"task_id": target_id, "task_type": "compare"},
                                         f"task_status:compare:{target_id}:queued")
            card = compare_status_card(self.compare.get(owner, target_id), self.base_url)
            message_id = self.client.send_card(event.chat_id, card)
            self.integrations.set_channel_card(target_id, message_id)
            self._retire_card(draft_card_id, "对比任务已创建，请使用下方最新的状态卡。")
            try:
                self.integrations.discard_draft_files(draft["id"])
            except Exception:
                pass
        except Exception as exc:
            self.integrations.update_draft(draft["id"], status="COLLECTING", error_code=type(exc).__name__)
            self._send_best_effort(event, text_card("对比任务创建失败", "可以再次点击确认重试；请在 FundLex 工作台查看详细错误。"))
            return "failed"
        return "submitted"

    def _submit_guide(self, event: MessageEvent, owner: str, draft: dict[str, Any]) -> str:
        files = [f for f in self._accepted_files(draft["id"]) if f.get("kind") == "regulation"]
        if not files:
            self._send(event, guide_prompt_card(draft["id"], error="请先发送法规原文。"))
            return "failed"
        if self.guides is None:
            self._send(event, text_card("指引服务未配置", "请联系管理员检查指引生成服务。"))
            return "failed"
        claimed = self.integrations.claim_draft_for_submit(draft["id"])
        if claimed is None:
            self._send(event, text_card("正在创建任务", "该指引草稿已提交，请稍候。"))
            return "busy"
        draft = claimed
        target_id = str(draft.get("target_id") or "")
        draft_card_id = draft.get("card_message_id") or ""
        try:
            if target_id:
                run = self.guides.get_run_for_owner(owner, target_id)
            else:
                item = files[0]
                data = self.store.object_path(item["storage_key"]).read_bytes()
                run = create_guide_run(self.store, self.guides, owner, item["name"], data)
                target_id = run["id"]
                self.integrations.update_draft(draft["id"], target_id=target_id, task_id=target_id)
            self.integrations.link_task(target_id, draft, None, task_type="guide")
            self._refresh_pinned_menu(event, None)
            self.integrations.add_outbox("task_status", target_id,
                                         {"task_id": target_id, "task_type": "guide"},
                                         f"task_status:guide:{target_id}:queued")
            card = guide_status_card(run, self.base_url)
            message_id = self.client.send_card(event.chat_id, card)
            self.integrations.set_channel_card(target_id, message_id)
            self._retire_card(draft_card_id, "指引任务已创建，请使用下方最新的状态卡。")
            try:
                self.integrations.discard_draft_files(draft["id"])
            except Exception:
                pass
        except Exception as exc:
            self.integrations.update_draft(draft["id"], status="COLLECTING", error_code=type(exc).__name__)
            self._send_best_effort(event, text_card("指引任务创建失败", "可以再次点击确认重试；请在 FundLex 工作台查看详细错误。"))
            return "failed"
        return "submitted"

    # ------------------------------------------------------------------
    # Task list and result return
    # ------------------------------------------------------------------
    def _collect_tasks(self, owner: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        try:
            page = self.tasks.list(owner, page=1, page_size=50, sort="newest")
            for task in page.get("items") or []:
                mode = task.get("mode") or "delivery"
                task_type = mode if mode in {"diagnosis", "evaluation"} else "revision"
                detail = f"合同 {task.get('completed', 0)}/{task.get('total', 0)} 已处理 · 失败 {task.get('failed', 0)}"
                try:
                    not_generated = int((task.get("delivery_counts") or {}).get("not_generated") or 0)
                except (TypeError, ValueError):
                    not_generated = 0
                if not_generated:
                    detail += f" · 未生成 {not_generated}"
                items.append({"task_type": task_type, "task_id": task.get("id"), "name": task.get("name"),
                              "status": task.get("status"), "detail": detail,
                              "can_send": not task.get("legacy") and int(task.get("downloadable_count") or 0) > 0,
                              "created_at": self._timestamp(task.get("created_at"))})
        except Exception as exc:
            log.warning("Feishu task list failed error=%s", type(exc).__name__)
        if self.compare is not None:
            try:
                for task in self.compare.list(owner)[:50]:
                    counts = task.get("counts") or {}
                    detail = f"{task.get('total', 0)} 组 · 成功 {counts.get('succeeded', 0)} · 不完整 {counts.get('incomplete', 0)}"
                    items.append({"task_type": "compare", "task_id": task.get("id"), "name": task.get("name"),
                                  "status": task.get("status"), "detail": detail,
                                  "can_send": any(p.get("status") in {"succeeded", "incomplete"} for p in task.get("pairs") or []),
                                  "created_at": self._timestamp(task.get("created_at"))})
            except Exception as exc:
                log.warning("Feishu compare list failed error=%s", type(exc).__name__)
        if self.guides is not None:
            try:
                for run in self.guides.list_runs(owner, limit=50):
                    detail = f"阶段：{stage_label(run.get('stage')) or status_label(run.get('status')) or '—'}"
                    items.append({"task_type": "guide", "task_id": run.get("id"),
                                  "name": run.get("title") or run.get("filename"), "status": run.get("status"),
                                  "detail": detail, "can_send": False,
                                  "created_at": self._timestamp(run.get("created_at"))})
            except Exception as exc:
                log.warning("Feishu guide list failed error=%s", type(exc).__name__)
        items.sort(key=lambda item: item.get("created_at") or 0, reverse=True)
        return items

    @staticmethod
    def _timestamp(value: Any) -> float:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                from datetime import datetime
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                return 0.0
        return 0.0

    def _show_tasks(self, event: MessageEvent, owner: str, *, page: int = 1, message_id: str = "") -> None:
        page = max(1, int(page or 1))
        items = self._collect_tasks(owner)
        if items and (page - 1) * _TASK_PAGE_SIZE >= len(items):
            page = max(1, (len(items) - 1) // _TASK_PAGE_SIZE + 1)
        start = (page - 1) * _TASK_PAGE_SIZE
        page_items = items[start:start + _TASK_PAGE_SIZE]
        card = task_list_card(page_items, page=page, has_more=len(items) > start + _TASK_PAGE_SIZE,
                              has_prev=page > 1, start=start)
        if message_id:
            try:
                self.client.update_card(message_id, card)
                return
            except Exception:
                pass
        self._send(event, card)

    def _view_task(self, event: MessageEvent, owner: str, task_type: str, task_id: str) -> str:
        if not task_id:
            return "任务 ID 缺失。"
        try:
            if task_type == "compare" and self.compare is not None:
                self._send(event, compare_status_card(self.compare.get(owner, task_id), self.base_url))
            elif task_type == "guide" and self.guides is not None:
                self._send(event, guide_status_card(self.guides.get_run_for_owner(owner, task_id), self.base_url))
            else:
                task = self.task_service.get_task(owner, task_id)
                self._send(event, self._task_status_card(owner, task_id, task.get("mode") or "delivery"))
            return "已发送任务详情。"
        except Exception:
            return "任务不存在或无权访问。"

    def _downloads_for_docs(self, owner: str, task_id: str) -> dict[str, str]:
        try:
            docs = self.task_service.list_documents(owner, task_id, page=1, page_size=100).get("items") or []
        except Exception:
            return {}
        downloads: dict[str, str] = {}
        for doc in docs:
            for kind, url in (doc.get("downloads") or {}).items():
                if url and kind not in downloads:
                    downloads[kind] = url
        return downloads

    def _task_status_card(self, owner: str, task_id: str, mode: str = "delivery") -> dict[str, Any]:
        task = self.task_service.get_task(owner, task_id)
        if task.get("status") in {"completed", "completed_with_exceptions", "failed"}:
            downloads = self._downloads_for_docs(owner, task_id)
            return result_card(task, self.base_url, mode=mode, downloads=downloads)
        if mode in {"diagnosis", "evaluation"}:
            return diagnosis_result_card(task, self.base_url, mode=mode)
        return revision_status_card(task, self.base_url)

    def _send_result_file(self, event: MessageEvent, owner: str, task_type: str, task_id: str, kind: str) -> str:
        if not task_id:
            return "任务 ID 缺失。"
        sent = 0
        try:
            if task_type == "compare" and self.compare is not None:
                task = self.compare.get(owner, task_id)
                for index, pair in enumerate(task.get("pairs") or [], 1):
                    if pair.get("status") not in {"succeeded", "incomplete"}:
                        continue
                    try:
                        detail = self.compare.get_pair(owner, pair["id"])
                        payload = detail.get("result") or {}
                        data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                        self.client.send_file(event.chat_id, f"合同对比-{index}-{pair['id'][:8]}.json", data)
                        sent += 1
                    except Exception:
                        continue
            elif task_type == "guide" and self.guides is not None:
                self.guides.get_run_for_owner(owner, task_id)
                wanted = (("guide", "generated_guide.docx"),
                          ("evidence_json", "guide_generation_evidence.json"))
                for artifact_kind, filename in wanted:
                    if kind not in {"all", artifact_kind}:
                        continue
                    artifact = self.guides.get_artifact(task_id, artifact_kind)
                    if not artifact:
                        continue
                    path = self.store.object_path(artifact["object_key"])
                    if path.is_file():
                        self.client.send_file(event.chat_id, filename, path.read_bytes())
                        sent += 1
                if not sent:
                    return "指引任务尚未生成可发送文件。"
            else:
                docs = self.task_service.list_documents(owner, task_id, page=1, page_size=100).get("items") or []
                for doc in docs:
                    document_id = doc.get("document_id")
                    if not document_id:
                        continue
                    available = doc.get("downloads") or {}
                    if kind == "all":
                        if task_type == "diagnosis":
                            order = ["report_md", "report_json"]
                        elif task_type == "evaluation":
                            order = ["evaluation_final", "evaluation_redline", "report_md", "report_json"]
                        elif "final" in available or "redline" in available:
                            order = ["final", "redline", "report_md", "report_json"]
                        else:
                            order = ["working_final", "working_redline", "report_md", "report_json"]
                        chosen = []
                        for candidate in order:
                            if candidate == "report_json" and "report_md" in available:
                                continue
                            if candidate in available:
                                chosen.append(candidate)
                    elif kind in available:
                        chosen = [kind]
                    elif kind == "report_md" and "report_json" in available:
                        chosen = ["report_json"]
                    else:
                        chosen = []
                    for download_kind in chosen:
                        try:
                            data, filename = self.tasks.artifact(owner, task_id, document_id, download_kind)
                            self.client.send_file(event.chat_id, filename, data)
                            sent += 1
                        except Exception:
                            continue
        except Exception as exc:
            log.warning("Feishu result send failed task=%s kind=%s error=%s", task_id, kind, type(exc).__name__)
            return "文件发送失败，请在 FundLex 工作台下载。"
        if not sent:
            return "该任务没有可发送的文件。"
        return f"已发送 {sent} 个文件。"

    # ------------------------------------------------------------------
    # Status sync and outbox
    # ------------------------------------------------------------------
    def sync_tasks(self) -> int:
        changed = 0
        for channel in self.integrations.channels():
            task_type = channel.get("task_type") or "revision"
            try:
                if task_type == "compare":
                    if self.compare is None:
                        continue
                    task = self.compare.get(channel["owner_user_id"], channel["task_id"])
                    status = str(task.get("status") or "")
                    counts = task.get("counts") or {}
                    fingerprint = hashlib.sha256(json.dumps(task, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
                    if self.integrations.update_channel(channel["task_id"], status, int(counts.get("succeeded") or 0),
                                                        int(counts.get("failed") or 0), json.dumps(counts),
                                                        fingerprint, external_status=status,
                                                        progress_json=json.dumps(counts)):
                        self.integrations.add_outbox("task_status", channel["task_id"],
                                                     {"task_id": channel["task_id"], "task_type": "compare"},
                                                     f"task_status:compare:{channel['task_id']}:{fingerprint}")
                        changed += 1
                elif task_type == "guide":
                    if self.guides is None:
                        continue
                    run = self.guides.get_run_for_owner(channel["owner_user_id"], channel["task_id"])
                    status = str(run.get("status") or "")
                    fingerprint = hashlib.sha256(json.dumps(run, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
                    if self.integrations.update_channel(channel["task_id"], status, 0, 0,
                                                        str(run.get("stage") or ""), fingerprint,
                                                        external_status=str(run.get("stage") or status),
                                                        progress_json=json.dumps({"stage": run.get("stage"), "status": status})):
                        self.integrations.add_outbox("task_status", channel["task_id"],
                                                     {"task_id": channel["task_id"], "task_type": "guide"},
                                                     f"task_status:guide:{channel['task_id']}:{fingerprint}")
                        changed += 1
                else:
                    task = self.task_service.get_task(channel["owner_user_id"], channel["task_id"])
                    mode = task.get("mode") or ("diagnosis" if task_type == "diagnosis" else
                                                "evaluation" if task_type == "evaluation" else "delivery")
                    fingerprint = hashlib.sha256(json.dumps(task, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
                    if self.integrations.update_channel(channel["task_id"], task["status"], int(task.get("completed", 0)),
                                                        int(task.get("failed", 0)), str(task.get("delivery_counts") or {}),
                                                        fingerprint, external_status=task["status"]):
                        dedupe = (f"task_status:{channel['task_id']}:{fingerprint}" if mode == "delivery"
                                  else f"task_status:{mode}:{channel['task_id']}:{fingerprint}")
                        self.integrations.add_outbox("task_status", channel["task_id"],
                                                     {"task_id": channel["task_id"], "task_type": task_type}, dedupe)
                        changed += 1
            except Exception:
                continue
        return changed

    def send_outbox(self, limit: int = 20) -> int:
        sent = 0
        for item in self.integrations.pending_outbox(limit):
            try:
                payload = json.loads(item["payload_json"])
                task_id = str(payload.get("task_id") or "")
                task_type = str(payload.get("task_type") or "revision")
                channel = next((row for row in self.integrations.channels() if row["task_id"] == task_id), None)
                if channel is None:
                    self.integrations.finish_outbox(item["id"], error_code="FEISHU_CHANNEL_NOT_FOUND")
                    continue
                if task_type == "compare" and self.compare is not None:
                    card = compare_status_card(self.compare.get(channel["owner_user_id"], task_id), self.base_url)
                elif task_type == "guide" and self.guides is not None:
                    card = guide_status_card(self.guides.get_run_for_owner(channel["owner_user_id"], task_id), self.base_url)
                else:
                    task = self.task_service.get_task(channel["owner_user_id"], task_id)
                    mode = task.get("mode") or ("diagnosis" if task_type == "diagnosis" else
                                                "evaluation" if task_type == "evaluation" else "delivery")
                    card = self._task_status_card(channel["owner_user_id"], task_id, mode)
                if channel.get("card_message_id"):
                    self.client.update_card(channel["card_message_id"], card)
                else:
                    message_id = self.client.send_card(channel["chat_id"], card)
                    self.integrations.set_channel_card(task_id, message_id)
                self.integrations.finish_outbox(item["id"], fencing_token=int(item["fencing_token"]))
                sent += 1
            except Exception as exc:
                self.integrations.finish_outbox(item["id"], fencing_token=int(item["fencing_token"]),
                                                error_code=type(exc).__name__, retry=int(item.get("attempts", 1)) < 5)
        return sent

    def run_background(self, interval: float = 5.0) -> None:
        self.install()
        while not self._stop.wait(interval):
            self.sync_tasks()
            self.send_outbox()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _synthetic_event(tenant_key: str, open_id: str, chat_id: str, message_id: str,
                         text: str = "卡片操作") -> MessageEvent:
        return MessageEvent(f"card:{message_id}", "p2.card.action.trigger", tenant_key, open_id, chat_id,
                            "p2p", message_id, "text", {"text": text})

    def _send(self, event: MessageEvent, card: dict[str, Any]) -> str:
        return self.client.send_card(event.chat_id, card)

    def _send_best_effort(self, event: MessageEvent, card: dict[str, Any]) -> None:
        try:
            self._send(event, card)
        except Exception as exc:
            log.warning("Feishu notification failed chat_id=%s error=%s", event.chat_id, type(exc).__name__)
