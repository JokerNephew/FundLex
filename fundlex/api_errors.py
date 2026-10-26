"""Stable, non-sensitive errors for the HTTP API."""

from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any

from fastapi import HTTPException


LOGGER = logging.getLogger("fundlex.api")
CORRELATION_ID_HEADER = "X-Correlation-ID"
_correlation_id: ContextVar[str] = ContextVar("fundlex_correlation_id", default="")
_SAFE_CODE = re.compile(r"^[A-Z][A-Z0-9_.-]{1,96}$")
_MESSAGES = {
    400: "请求无效。", 401: "需要登录后才能执行此操作。", 403: "当前账号无权执行此操作。",
    404: "请求的资源不存在。", 409: "请求与当前资源状态冲突。", 413: "上传内容超过允许大小。",
    415: "文件格式不受支持。", 422: "请求或文件无法处理。", 500: "服务暂时不可用，请稍后重试。",
    503: "服务暂时不可用，请稍后重试。",
}


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(value: str):
    return _correlation_id.set(value)


def reset_correlation_id(token) -> None:
    _correlation_id.reset(token)


def correlation_id() -> str:
    return _correlation_id.get() or new_correlation_id()


def _candidate(value: Any) -> str | None:
    return value if isinstance(value, str) and _SAFE_CODE.fullmatch(value) else None


def error_code(exc: BaseException | None, fallback: str) -> str:
    """Return an explicitly assigned stable code, never arbitrary exception text."""
    if exc is not None:
        code = _candidate(getattr(exc, "code", None))
        if code:
            return code
        args = getattr(exc, "args", ())
        if args:
            code = _candidate(args[0])
            if code:
                return code
    return _candidate(fallback) or "INTERNAL_ERROR"


def code_from_detail(detail: Any, status_code: int) -> str:
    code = _candidate(detail)
    if code:
        return code
    return {400: "INVALID_REQUEST", 401: "AUTHENTICATION_REQUIRED", 403: "FORBIDDEN",
            404: "NOT_FOUND", 409: "CONFLICT", 413: "UPLOAD_TOO_LARGE",
            415: "UNSUPPORTED_FILE", 422: "INVALID_REQUEST", 503: "SERVICE_UNAVAILABLE"}.get(
                status_code, "INTERNAL_ERROR")


def message_for(status_code: int) -> str:
    return _MESSAGES.get(status_code, _MESSAGES[500])


def log_handled_error(exc: BaseException | None, code: str, *, request_id: str | None = None) -> str:
    """Log only metadata safe for a production log."""
    cid = request_id or correlation_id()
    LOGGER.warning("api error correlation_id=%s code=%s exception_type=%s",
                   cid, code, type(exc).__name__ if exc is not None else "HTTPException")
    return cid


def raise_api_error(status_code: int, exc: BaseException, *, fallback: str) -> None:
    code = error_code(exc, fallback)
    raise HTTPException(status_code, code) from exc
