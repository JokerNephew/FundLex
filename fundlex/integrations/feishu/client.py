"""Small official ``lark-oapi`` adapter used by the Feishu service.

The SDK is imported lazily so local Web/API processes can run without Feishu
credentials or the optional dependency.  The service entrypoint itself fails
closed when production configuration is incomplete.
"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any, Protocol


class FeishuConfigurationError(RuntimeError):
    pass


class FeishuClient(Protocol):
    def send_card(self, receive_id: str, card: dict[str, Any]) -> str: ...
    def reply_card(self, message_id: str, card: dict[str, Any]) -> str: ...
    def update_card(self, message_id: str, card: dict[str, Any]) -> None: ...
    def download_message_resource(self, message_id: str, file_key: str, resource_type: str = "file") -> tuple[bytes, str | None]: ...
    def start(self) -> None: ...


def _response_error(response: Any) -> RuntimeError | None:
    code = getattr(response, "code", 0)
    if code in (None, 0):
        return None
    message = getattr(response, "msg", None) or getattr(response, "message", None) or "Feishu API request failed"
    return RuntimeError(f"FEISHU_API_{code}: {message}")


class FeishuOpenApiClient:
    def __init__(self, app_id: str, app_secret: str, *, log_level: Any = None):
        if not app_id.strip() or not app_secret.strip():
            raise FeishuConfigurationError("FUNDLEX_FEISHU_APP_ID and FUNDLEX_FEISHU_APP_SECRET are required")
        try:
            import lark_oapi as lark
        except ImportError as exc:  # pragma: no cover - exercised in deployment checks
            raise FeishuConfigurationError("lark-oapi is required for the Feishu service") from exc
        builder = lark.Client.builder().app_id(app_id).app_secret(app_secret)
        if log_level is not None:
            builder = builder.log_level(log_level)
        self.client = builder.build()
        self._lark = lark

    @classmethod
    def from_env(cls) -> "FeishuOpenApiClient":
        return cls(os.environ.get("FUNDLEX_FEISHU_APP_ID", ""), os.environ.get("FUNDLEX_FEISHU_APP_SECRET", ""))

    @staticmethod
    def _card_content(card: dict[str, Any]) -> str:
        return json.dumps(card, ensure_ascii=False, separators=(",", ":"))

    def send_card(self, receive_id: str, card: dict[str, Any]) -> str:
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
        body = (CreateMessageRequestBody.builder().receive_id(receive_id).msg_type("interactive")
                .content(self._card_content(card)).uuid(os.urandom(16).hex()).build())
        response = self.client.im.v1.message.create(
            CreateMessageRequest.builder().receive_id_type("chat_id").request_body(body).build())
        error = _response_error(response)
        if error:
            raise error
        return str(getattr(getattr(response, "data", None), "message_id", "") or "")

    def reply_card(self, message_id: str, card: dict[str, Any]) -> str:
        from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody
        body = (ReplyMessageRequestBody.builder().msg_type("interactive").content(self._card_content(card))
                .reply_in_thread(False).uuid(os.urandom(16).hex()).build())
        response = self.client.im.v1.message.reply(
            ReplyMessageRequest.builder().message_id(message_id).request_body(body).build())
        error = _response_error(response)
        if error:
            raise error
        return str(getattr(getattr(response, "data", None), "message_id", "") or "")

    def update_card(self, message_id: str, card: dict[str, Any]) -> None:
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
        body = PatchMessageRequestBody.builder().content(self._card_content(card)).build()
        response = self.client.im.v1.message.patch(
            PatchMessageRequest.builder().message_id(message_id).request_body(body).build())
        error = _response_error(response)
        if error:
            raise error

    def download_message_resource(self, message_id: str, file_key: str, resource_type: str = "file") -> tuple[bytes, str | None]:
        from lark_oapi.api.im.v1 import GetMessageResourceRequest
        request = (GetMessageResourceRequest.builder().message_id(message_id).file_key(file_key)
                   .type(resource_type).build())
        response = self.client.im.v1.message_resource.get(request)
        error = _response_error(response)
        if error:
            raise error
        stream = getattr(response, "file", None)
        if stream is None:
            raise RuntimeError("FEISHU_FILE_EMPTY")
        return stream.read(), getattr(response, "file_name", None)

    def start(self) -> None:
        from .events import build_event_handler
        handler = build_event_handler(self)
        ws = self._lark.ws.Client(
            os.environ["FUNDLEX_FEISHU_APP_ID"], os.environ["FUNDLEX_FEISHU_APP_SECRET"],
            event_handler=handler, auto_reconnect=True)
        ws.start()
