"""FL-D286 regressions for public error contracts and sensitive output."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.compare.worker import CompareWorker
from fundlex.db import DatabaseError


def _docx(text: str) -> bytes:
    from docx import Document

    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


def _compare_payload(left: bytes, right: bytes) -> dict:
    return {
        "name": "compare",
        "pairs": [{
            "client_pair_id": "pair-1",
            "label": "pair",
            "left": {"client_id": "left-1", "name": "left.docx", "size": len(left)},
            "right": {"client_id": "right-1", "name": "right.docx", "size": len(right)},
        }],
    }


def test_api_conflict_has_stable_code_generic_message_and_correlation_id(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    headers = {"X-FundLex-User": "alice", "Idempotency-Key": "same-input"}
    left, right = _docx("left"), _docx("right")
    first = client.post("/api/compare/tasks", headers=headers, json=_compare_payload(left, right))
    assert first.status_code == 201

    changed = _compare_payload(left, _docx("different"))
    response = client.post("/api/compare/tasks", headers=headers, json=changed)
    body = response.json()
    assert response.status_code == 409
    assert body["error_code"] == body["detail"] == "CONFLICT"
    assert body["message"] == "请求与当前资源状态冲突。"
    assert body["correlation_id"] == response.headers["X-Correlation-ID"]
    assert "same-input" not in response.text


def test_malformed_docx_and_missing_file_use_stable_public_errors(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    headers = {"X-FundLex-User": "alice"}
    left, right = _docx("left"), _docx("right")
    created = client.post("/api/compare/tasks", headers=headers, json=_compare_payload(left, right))
    task_id = created.json()["id"]

    malformed = b"this is not a DOCX and must not become an exception detail"
    uploaded = client.post(
        f"/api/compare/tasks/{task_id}/uploads", headers=headers,
        data={"client_ids": '["left-1", "right-1"]'},
        files=[("files", ("left.docx", malformed)), ("files", ("right.docx", right))],
    )
    assert uploaded.status_code == 200
    receipts = uploaded.json()["receipts"]
    assert receipts[0]["error_code"] == "COMPARE_INVALID_DOCX"
    assert "not a DOCX" not in uploaded.text

    missing = client.get("/api/batches/does-not-exist/documents/does-not-exist/download/final", headers=headers)
    assert missing.status_code == 404
    assert missing.json()["error_code"] == missing.json()["detail"] == "NOT_FOUND"
    assert "does-not-exist" not in missing.text


def test_compare_result_integrity_failure_has_no_internal_error_text(tmp_path: Path):
    client = TestClient(create_app(tmp_path))
    headers = {"X-FundLex-User": "alice"}
    left, right = _docx("left"), _docx("right")
    created = client.post("/api/compare/tasks", headers=headers, json=_compare_payload(left, right))
    task_id = created.json()["id"]
    uploaded = client.post(
        f"/api/compare/tasks/{task_id}/uploads", headers=headers,
        data={"client_ids": '["left-1", "right-1"]'},
        files=[("files", ("left.docx", left)), ("files", ("right.docx", right))],
    )
    assert uploaded.status_code == 200
    assert client.post(f"/api/compare/tasks/{task_id}/seal", headers=headers).status_code == 200
    assert CompareWorker(client.app.state.compare_store).run_once()
    pair_id = created.json()["pairs"][0]["id"]
    source = client.app.state.compare_store.store.object_path(
        client.app.state.compare_store.pair_inputs(pair_id)[0]["object_key"]
    )
    original = source.read_bytes()
    source.write_bytes(b"private path / database password=never-returned")
    response = client.get(f"/api/compare/pairs/{pair_id}/view", headers=headers)
    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == body["detail"] == "COMPARE_INPUT_INTEGRITY_FAILED"
    assert body["message"] == "请求与当前资源状态冲突。"
    assert body["correlation_id"] == response.headers["X-Correlation-ID"]
    assert "private path" not in response.text
    source.write_bytes(original)


def test_unexpected_file_or_database_error_returns_generic_response_and_safe_log(tmp_path: Path, monkeypatch, caplog):
    app = create_app(tmp_path)
    secret = "mysql://service:secret-password@db.internal/fundlex?ssl=true /srv/fundlex/auth.db"

    def broken_list(_owner):
        raise DatabaseError(secret)

    monkeypatch.setattr(app.state.compare_store, "list", broken_list)
    caplog.set_level(logging.WARNING, logger="fundlex.api")
    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/compare/tasks", headers={"X-FundLex-User": "alice"})
    body = response.json()
    assert response.status_code == 500
    assert body["error_code"] == body["detail"] == "DATABASE_ERROR"
    assert body["message"] == "服务暂时不可用，请稍后重试。"
    assert body["correlation_id"] == response.headers["X-Correlation-ID"]
    assert secret not in response.text
    assert "secret-password" not in caplog.text
    assert "/srv/fundlex" not in caplog.text
    assert body["correlation_id"] in caplog.text
