"""Request and multipart resource guards for upload endpoints.

The normal DOCX validator remains the authority for ZIP/package safety.  This
module limits work before a route can retain upload bytes: request size,
concurrency, request rate, receive timeout, and multipart part/header/file
budgets are all bounded independently.
"""
from __future__ import annotations

import asyncio
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Callable

from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.responses import JSONResponse


class UploadGuardError(Exception):
    def __init__(self, status_code: int, code: str, detail: str, retry_after: int | None = None):
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.retry_after = retry_after


@dataclass(frozen=True)
class UploadGuardSettings:
    max_request_bytes: int = 52 * 1024 * 1024
    guide_request_bytes: int = 26 * 1024 * 1024
    max_concurrent_per_ip: int = 2
    max_concurrent_global: int = 8
    requests_per_minute: int = 12
    burst: int = 4
    receive_timeout_seconds: float = 30.0
    request_timeout_seconds: float = 180.0
    min_rate_bytes_per_second: int = 1024
    min_rate_grace_seconds: float = 5.0
    # The product no longer imposes a 20-file count limit. Keep a high
    # multipart safety ceiling so hostile zero-byte part floods still terminate.
    max_parts: int = 20000
    max_fields: int = 8
    max_headers_per_part: int = 16
    max_header_bytes: int = 16 * 1024
    max_field_bytes: int = 64 * 1024

    @classmethod
    def from_env(cls) -> "UploadGuardSettings":
        def integer(name: str, default: int) -> int:
            try:
                value = int(os.environ.get(name, str(default)))
            except ValueError:
                return default
            return value if value > 0 else default

        def number(name: str, default: float) -> float:
            try:
                value = float(os.environ.get(name, str(default)))
            except ValueError:
                return default
            return value if value > 0 else default

        return cls(
            max_request_bytes=integer("FUNDLEX_UPLOAD_REQUEST_BYTES", cls.max_request_bytes),
            guide_request_bytes=integer("FUNDLEX_GUIDE_REQUEST_BYTES", cls.guide_request_bytes),
            max_concurrent_per_ip=integer("FUNDLEX_UPLOAD_CONCURRENCY_PER_IP", cls.max_concurrent_per_ip),
            max_concurrent_global=integer("FUNDLEX_UPLOAD_CONCURRENCY_GLOBAL", cls.max_concurrent_global),
            requests_per_minute=integer("FUNDLEX_UPLOAD_REQUESTS_PER_MINUTE", cls.requests_per_minute),
            burst=integer("FUNDLEX_UPLOAD_BURST", cls.burst),
            receive_timeout_seconds=number("FUNDLEX_UPLOAD_RECEIVE_TIMEOUT_SECONDS", cls.receive_timeout_seconds),
            request_timeout_seconds=number("FUNDLEX_UPLOAD_TIMEOUT_SECONDS", cls.request_timeout_seconds),
            min_rate_bytes_per_second=integer("FUNDLEX_UPLOAD_MIN_RATE_BYTES", cls.min_rate_bytes_per_second),
            min_rate_grace_seconds=number("FUNDLEX_UPLOAD_MIN_RATE_GRACE_SECONDS", cls.min_rate_grace_seconds),
            max_parts=integer("FUNDLEX_MULTIPART_MAX_PARTS", cls.max_parts),
            max_fields=integer("FUNDLEX_MULTIPART_MAX_FIELDS", cls.max_fields),
            max_headers_per_part=integer("FUNDLEX_MULTIPART_MAX_HEADERS", cls.max_headers_per_part),
            max_header_bytes=integer("FUNDLEX_MULTIPART_MAX_HEADER_BYTES", cls.max_header_bytes),
            max_field_bytes=integer("FUNDLEX_MULTIPART_MAX_FIELD_BYTES", cls.max_field_bytes),
        )


class BoundedMultiPartParser(MultiPartParser):
    """Starlette's parser with file, part, header and aggregate budgets."""

    max_request_parts = 32
    max_request_fields = 8
    max_file_bytes = 25 * 1024 * 1024
    max_total_file_bytes = 50 * 1024 * 1024
    max_field_bytes = 64 * 1024
    max_header_bytes = 16 * 1024
    max_headers_per_part = 16

    def __init__(self, headers: Headers, stream, *, max_files=1000, max_fields=1000,
                 max_part_size=1024 * 1024):
        super().__init__(headers, stream, max_files=max_files, max_fields=max_fields,
                         max_part_size=max_part_size)
        self.max_request_parts = _positive_env("FUNDLEX_MULTIPART_MAX_PARTS", self.max_request_parts)
        self.max_request_fields = _positive_env("FUNDLEX_MULTIPART_MAX_FIELDS", self.max_request_fields)
        self.max_file_bytes = _positive_env("FUNDLEX_MAX_UPLOAD_BYTES", self.max_file_bytes)
        self.max_total_file_bytes = _positive_env("FUNDLEX_MAX_BATCH_BYTES", self.max_total_file_bytes)
        self.max_field_bytes = _positive_env("FUNDLEX_MULTIPART_MAX_FIELD_BYTES", self.max_field_bytes)
        self.max_header_bytes = _positive_env("FUNDLEX_MULTIPART_MAX_HEADER_BYTES", self.max_header_bytes)
        self.max_headers_per_part = _positive_env("FUNDLEX_MULTIPART_MAX_HEADERS", self.max_headers_per_part)
        self.max_part_size = self.max_field_bytes
        self._part_count = 0
        self._field_count = 0
        self._total_file_bytes = 0
        self._current_file_bytes = 0
        self._current_header_bytes = 0
        self._current_header_count = 0

    def on_part_begin(self) -> None:
        self._part_count += 1
        if self._part_count > self.max_request_parts:
            raise MultiPartException("Too many multipart parts.")
        self._current_file_bytes = 0
        self._current_header_bytes = 0
        self._current_header_count = 0
        super().on_part_begin()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._current_header_bytes += end - start
        if self._current_header_bytes > self.max_header_bytes:
            raise MultiPartException("Multipart part headers exceeded maximum size.")
        super().on_header_field(data, start, end)

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._current_header_bytes += end - start
        if self._current_header_bytes > self.max_header_bytes:
            raise MultiPartException("Multipart part headers exceeded maximum size.")
        super().on_header_value(data, start, end)

    def on_header_end(self) -> None:
        self._current_header_count += 1
        if self._current_header_count > self.max_headers_per_part:
            raise MultiPartException("Too many multipart part headers.")
        super().on_header_end()

    def on_headers_finished(self) -> None:
        super().on_headers_finished()
        if self._current_part.file is None:
            self._field_count += 1
            if self._field_count > self.max_request_fields:
                raise MultiPartException("Too many multipart fields.")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        size = end - start
        if self._current_part.file is not None:
            self._current_file_bytes += size
            self._total_file_bytes += size
            if self._current_file_bytes > self.max_file_bytes:
                raise MultiPartException("Multipart file exceeded maximum size.")
            if self._total_file_bytes > self.max_total_file_bytes:
                raise MultiPartException("Multipart file budget exceeded.")
        super().on_part_data(data, start, end)


def install_multipart_limits() -> None:
    """Install bounded parser references used by Starlette Request.form()."""
    # Request._get_form resolves MultiPartParser through the requests module's
    # global.  Set both references so this remains compatible across Starlette
    # minor versions without replacing Request or FastAPI internals.
    import starlette.formparsers as formparsers
    import starlette.requests as requests
    formparsers.MultiPartParser = BoundedMultiPartParser
    requests.MultiPartParser = BoundedMultiPartParser


def _positive_env(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


class UploadResourceMiddleware:
    """ASGI guard for upload request size, concurrency, rate and time limits."""

    def __init__(self, app: Callable, *, settings: UploadGuardSettings):
        self.app = app
        self.settings = settings
        self._global_active = 0
        self._ip_active: dict[str, int] = defaultdict(int)
        self._recent: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    @staticmethod
    def _is_upload(scope: dict[str, Any]) -> bool:
        if scope.get("type") != "http" or scope.get("method", "").upper() != "POST":
            return False
        path = scope.get("path", "")
        return path.endswith("/uploads") or path == "/api/guides"

    @staticmethod
    def _client_key(scope: dict[str, Any]) -> str:
        client = scope.get("client")
        return str(client[0]) if client else "unknown"

    def _request_limit(self, path: str) -> int:
        return self.settings.guide_request_bytes if path == "/api/guides" else self.settings.max_request_bytes

    async def _admit(self, key: str) -> None:
        now = time.monotonic()
        async with self._lock:
            if self._global_active >= self.settings.max_concurrent_global:
                raise UploadGuardError(429, "UPLOAD_CONCURRENCY_LIMIT", "too many uploads in progress", 2)
            if self._ip_active[key] >= self.settings.max_concurrent_per_ip:
                raise UploadGuardError(429, "UPLOAD_CONCURRENCY_LIMIT", "too many uploads from this client", 2)
            recent = self._recent[key]
            cutoff = now - 60.0
            while recent and recent[0] <= cutoff:
                recent.popleft()
            if len(recent) >= self.settings.requests_per_minute + self.settings.burst:
                raise UploadGuardError(429, "UPLOAD_RATE_LIMIT", "upload request rate exceeded", 60)
            recent.append(now)
            self._global_active += 1
            self._ip_active[key] += 1

    async def _release(self, key: str) -> None:
        async with self._lock:
            self._global_active = max(0, self._global_active - 1)
            self._ip_active[key] = max(0, self._ip_active[key] - 1)
            if self._ip_active[key] == 0:
                self._ip_active.pop(key, None)

    def _response(self, error: UploadGuardError) -> JSONResponse:
        headers = {"Cache-Control": "no-store"}
        if error.retry_after is not None:
            headers["Retry-After"] = str(error.retry_after)
        return JSONResponse({"error": error.code, "detail": error.detail},
                            status_code=error.status_code, headers=headers)

    async def __call__(self, scope: dict[str, Any], receive: Callable, send: Callable):
        if not self._is_upload(scope):
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        limit = self._request_limit(scope.get("path", ""))
        try:
            if content_length is not None:
                declared = int(content_length)
                if declared < 0:
                    raise ValueError
            else:
                declared = None
        except ValueError:
            await self._response(UploadGuardError(400, "INVALID_CONTENT_LENGTH", "invalid Content-Length header"))(scope, receive, send)
            return
        if declared is not None and declared > limit:
            await self._response(UploadGuardError(413, "UPLOAD_REQUEST_SIZE_LIMIT", "upload request body is too large"))(scope, receive, send)
            return
        if not headers.get("content-type", "").lower().startswith("multipart/form-data"):
            await self._response(UploadGuardError(415, "MULTIPART_REQUIRED", "upload endpoints require multipart/form-data"))(scope, receive, send)
            return

        key = self._client_key(scope)
        try:
            await self._admit(key)
        except UploadGuardError as error:
            await self._response(error)(scope, receive, send)
            return

        started = time.monotonic()
        received = 0
        response_started = False

        async def guarded_receive():
            nonlocal received
            try:
                message = await asyncio.wait_for(receive(), self.settings.receive_timeout_seconds)
            except asyncio.TimeoutError as exc:
                raise UploadGuardError(408, "UPLOAD_RECEIVE_TIMEOUT", "upload receive timed out") from exc
            if message.get("type") == "http.request":
                body = message.get("body", b"") or b""
                received += len(body)
                if received > limit:
                    raise UploadGuardError(413, "UPLOAD_REQUEST_SIZE_LIMIT", "upload request body is too large")
                elapsed = time.monotonic() - started
                if (received and elapsed > self.settings.min_rate_grace_seconds
                        and received / elapsed < self.settings.min_rate_bytes_per_second):
                    raise UploadGuardError(408, "UPLOAD_RATE_TOO_SLOW", "upload receive rate is too slow")
            return message

        async def guarded_send(message):
            nonlocal response_started
            if message.get("type") == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(self.app(scope, guarded_receive, guarded_send),
                                   self.settings.request_timeout_seconds)
        except UploadGuardError as error:
            if not response_started:
                await self._response(error)(scope, receive, send)
        except asyncio.TimeoutError:
            if not response_started:
                await self._response(UploadGuardError(408, "UPLOAD_TIMEOUT", "upload request timed out"))(scope, receive, send)
        finally:
            await self._release(key)


def add_upload_guard(application, *, max_upload_bytes: int, max_batch_bytes: int) -> UploadGuardSettings:
    settings = UploadGuardSettings.from_env()
    install_multipart_limits()
    application.add_middleware(UploadResourceMiddleware, settings=settings)
    return settings
