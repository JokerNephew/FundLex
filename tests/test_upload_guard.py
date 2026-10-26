"""Controlled FL-D288 request and multipart resource guard checks."""
from __future__ import annotations

import asyncio
import io
import json

import pytest
from fastapi.testclient import TestClient
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException

from fundlex.api import create_app
from fundlex.upload_guard import (
    BoundedMultiPartParser,
    UploadGuardSettings,
    UploadResourceMiddleware,
)


def _scope(path="/api/tasks/t/uploads", *, client=("127.0.0.1", 1), headers=()):
    return {
        "type": "http", "http_version": "1.1", "method": "POST", "path": path,
        "raw_path": path.encode(), "query_string": b"", "scheme": "http",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
        "client": client, "server": ("test", 80),
    }


async def _call_middleware(middleware, scope, receive):
    messages = []

    async def send(message):
        messages.append(message)

    await middleware(scope, receive, send)
    return messages


def _request_receive(body=b"", *, delay=0):
    sent = False

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            if delay:
                await asyncio.sleep(delay)
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    return receive


def test_content_length_is_rejected_before_application_read():
    seen = False

    async def app(scope, receive, send):
        nonlocal seen
        seen = True

    settings = UploadGuardSettings(max_request_bytes=10, guide_request_bytes=10)
    middleware = UploadResourceMiddleware(app, settings=settings)
    messages = asyncio.run(_call_middleware(
        middleware,
        _scope(headers=[("content-length", "11"), ("content-type", "multipart/form-data; boundary=x")]),
        _request_receive(b"x" * 11),
    ))
    assert messages[0]["status"] == 413
    assert json.loads(messages[1]["body"])['error'] == "UPLOAD_REQUEST_SIZE_LIMIT"
    assert seen is False


def test_chunked_body_is_stopped_at_early_budget():
    consumed = 0

    async def app(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body"):
                break

    async def receive():
        nonlocal consumed
        consumed += 1
        return {"type": "http.request", "body": b"12345", "more_body": True}

    settings = UploadGuardSettings(max_request_bytes=8, guide_request_bytes=8)
    messages = asyncio.run(_call_middleware(
        UploadResourceMiddleware(app, settings=settings),
        _scope(headers=[("content-type", "multipart/form-data; boundary=x")]), receive,
    ))
    assert messages[0]["status"] == 413
    assert consumed == 2


def test_slow_receive_and_rate_limit_are_bounded():
    async def app(scope, receive, send):
        await receive()

    timeout_settings = UploadGuardSettings(receive_timeout_seconds=0.01, request_timeout_seconds=1)
    timeout_messages = asyncio.run(_call_middleware(
        UploadResourceMiddleware(app, settings=timeout_settings),
        _scope(headers=[("content-type", "multipart/form-data; boundary=x")]),
        _request_receive(b"", delay=0.05),
    ))
    assert timeout_messages[0]["status"] == 408
    assert json.loads(timeout_messages[1]["body"])['error'] == "UPLOAD_RECEIVE_TIMEOUT"

    rate_settings = UploadGuardSettings(requests_per_minute=1, burst=0, max_concurrent_per_ip=2)
    middleware = UploadResourceMiddleware(lambda scope, receive, send: asyncio.sleep(0), settings=rate_settings)
    scope = _scope(headers=[("content-type", "multipart/form-data; boundary=x")])
    first = asyncio.run(_call_middleware(middleware, scope, _request_receive()))
    second = asyncio.run(_call_middleware(middleware, scope, _request_receive()))
    assert first == []
    assert second[0]["status"] == 429
    assert json.loads(second[1]["body"])['error'] == "UPLOAD_RATE_LIMIT"


def test_per_ip_concurrency_gate_rejects_second_inflight_request():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def app(scope, receive, send):
        entered.set()
        await release.wait()

    settings = UploadGuardSettings(max_concurrent_per_ip=1, requests_per_minute=20)
    middleware = UploadResourceMiddleware(app, settings=settings)
    scope = _scope(headers=[("content-type", "multipart/form-data; boundary=x")])

    async def run():
        first = asyncio.create_task(_call_middleware(middleware, scope, _request_receive()))
        await entered.wait()
        second = await _call_middleware(middleware, scope, _request_receive())
        release.set()
        await first
        return second

    messages = asyncio.run(run())
    assert messages[0]["status"] == 429
    assert json.loads(messages[1]["body"])['error'] == "UPLOAD_CONCURRENCY_LIMIT"


def test_multipart_part_and_header_limits_reject_before_route():
    boundary = b"guard"
    body = (b"--guard\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.docx\"\r\n"
            + b"X-Too-Large: " + b"x" * 100 + b"\r\n\r\nhello\r\n--guard--\r\n")

    async def stream():
        yield body

    parser = BoundedMultiPartParser(
        Headers({"content-type": "multipart/form-data; boundary=guard"}), stream(),
    )
    parser.max_header_bytes = 32
    with pytest.raises(MultiPartException, match="headers"):
        asyncio.run(parser.parse())


def test_multipart_part_and_field_budgets_are_enforced():
    async def stream():
        yield (b"--guard\r\nContent-Disposition: form-data; name=\"a\"\r\n\r\n1\r\n"
               b"--guard\r\nContent-Disposition: form-data; name=\"b\"\r\n\r\n2\r\n"
               b"--guard--\r\n")

    parser = BoundedMultiPartParser(
        Headers({"content-type": "multipart/form-data; boundary=guard"}), stream(),
    )
    parser.max_request_fields = 1
    with pytest.raises(MultiPartException, match="fields"):
        asyncio.run(parser.parse())

    async def many_parts():
        yield (b"--guard\r\nContent-Disposition: form-data; name=\"a\"\r\n\r\n1\r\n"
               b"--guard\r\nContent-Disposition: form-data; name=\"b\"\r\n\r\n2\r\n"
               b"--guard--\r\n")

    parser = BoundedMultiPartParser(
        Headers({"content-type": "multipart/form-data; boundary=guard"}), many_parts(),
    )
    parser.max_request_parts = 1
    with pytest.raises(MultiPartException, match="parts"):
        asyncio.run(parser.parse())


def test_parser_closes_spooled_file_when_file_budget_is_exceeded():
    async def stream():
        yield (b"--guard\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.docx\"\r\n"
               b"Content-Type: application/octet-stream\r\n\r\n123456\r\n--guard--\r\n")

    parser = BoundedMultiPartParser(
        Headers({"content-type": "multipart/form-data; boundary=guard"}), stream(),
    )
    parser.max_file_bytes = 3
    with pytest.raises(MultiPartException, match="file exceeded"):
        asyncio.run(parser.parse())
    assert parser._files_to_close_on_error
    assert all(file.closed for file in parser._files_to_close_on_error)


def test_app_rejects_oversized_content_length_before_multipart_parse(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_UPLOAD_REQUEST_BYTES", "100")
    monkeypatch.setenv("FUNDLEX_GUIDE_REQUEST_BYTES", "100")
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/guides", headers={"X-FundLex-User": "alice"},
        files={"file": ("guide.docx", b"x" * 200)},
    )
    assert response.status_code == 413
    assert response.json()["error"] == "UPLOAD_REQUEST_SIZE_LIMIT"


def test_app_rejects_malformed_multipart_without_creating_guide(tmp_path):
    client = TestClient(create_app(tmp_path))
    response = client.post(
        "/api/guides", headers={
            "X-FundLex-User": "alice",
            "Content-Type": "multipart/form-data; boundary=broken",
        }, data=b"--broken\r\nnot-a-header\r\n",
    )
    assert response.status_code == 400
    assert client.get("/api/guides", headers={"X-FundLex-User": "alice"}).json()["items"]
