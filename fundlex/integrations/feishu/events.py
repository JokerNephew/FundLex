"""Event extraction and long-connection registration for lark-oapi."""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)
# Feishu expects a card callback response within ~3 seconds.  Heavy work
# (task creation, uploading many files, sending result files) runs in this
# pool while the callback returns a short acknowledgement.
_CARD_ACTIONS = ThreadPoolExecutor(max_workers=4, thread_name_prefix="feishu-card")


def _get(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, dict) and name in value:
            return value[name]
        if value is not None and hasattr(value, name):
            return getattr(value, name)
    return default


def _content(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {"text": raw}
    return value if isinstance(value, dict) else {"text": str(value)}


@dataclass(frozen=True)
class MessageEvent:
    event_id: str
    event_type: str
    tenant_key: str
    open_id: str
    chat_id: str
    chat_type: str
    message_id: str
    message_type: str
    content: dict[str, Any]

    @property
    def text(self) -> str:
        return str(self.content.get("text") or "").strip()


def parse_message_event(data: Any) -> MessageEvent:
    header = _get(data, "header", default={})
    event = _get(data, "event", default={})
    message = _get(event, "message", default={})
    sender = _get(event, "sender", default={})
    sender_id = _get(sender, "sender_id", default={})
    return MessageEvent(
        event_id=str(_get(header, "event_id", "eventId", default="") or _get(message, "message_id", default="")),
        event_type="im.message.receive_v1",
        tenant_key=str(_get(header, "tenant_key", "tenantKey", default="") or _get(sender, "tenant_key", default="")),
        open_id=str(_get(sender_id, "open_id", "openId", default="")),
        chat_id=str(_get(message, "chat_id", "chatId", default="")),
        chat_type=str(_get(message, "chat_type", "chatType", default="")),
        message_id=str(_get(message, "message_id", "messageId", default="")),
        message_type=str(_get(message, "message_type", "messageType", default="")),
        content=_content(_get(message, "content", default={})),
    )


def _log_card_action_failure(future) -> None:
    try:
        exc = future.exception()
    except Exception:  # cancelled
        return
    if exc is not None:
        log.warning("Feishu deferred card action failed error=%s", type(exc).__name__)


def build_event_handler(client: Any):
    import lark_oapi as lark
    from lark_oapi.event.callback.model.p2_card_action_trigger import P2CardActionTriggerResponse
    from .service import active_service

    def on_message(data):
        service = active_service()
        if service is not None:
            service.handle_message_event(data)

    def on_card_action(data):
        service = active_service()
        if service is None:
            return P2CardActionTriggerResponse({"toast": {"type": "warning", "content": "FundLex 服务尚未就绪"}})
        future = _CARD_ACTIONS.submit(service.handle_card_action_event, data)
        future.add_done_callback(_log_card_action_failure)
        try:
            message = future.result(timeout=2.0)
        except FuturesTimeoutError:
            return P2CardActionTriggerResponse({
                "toast": {"type": "info", "content": "已开始处理，请稍候；下一步卡片会自动出现。"}})
        except Exception as exc:  # pragma: no cover - defensive boundary
            log.warning("Feishu card callback failed error=%s", type(exc).__name__)
            message = "操作失败，请稍后重试。"
        return P2CardActionTriggerResponse({"toast": {"type": "success", "content": message}})

    return (lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(on_message)
            .register_p2_card_action_trigger(on_card_action).build())
