import hashlib
import io
import json
from zipfile import ZipFile

from docx import Document
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from fundlex.compare.api import register_compare_routes
from fundlex.compare.worker import CompareWorker
from fundlex.docx import DOCUMENT
from fundlex.store import RunStore
from fundlex.compare.store import CompareStore


def _docx(text: str) -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


def _ready_pair(tmp_path):
    left, right = _docx("费率为0.40%"), _docx("费率为0.30%")
    application = FastAPI()

    def user_dependency(x_fundlex_user: str = Header(default="")):
        return x_fundlex_user or "anonymous"

    def validate_upload(name: str, data: bytes) -> str:
        if not name.lower().endswith(".docx"):
            raise HTTPException(415, "UNSUPPORTED_FILE")
        return name

    compare_store = CompareStore(RunStore(tmp_path))
    application.state.compare_store = compare_store
    register_compare_routes(application, compare_store, user_dependency, validate_upload,
                            max_upload_bytes=8 * 1024 * 1024, max_batch_bytes=16 * 1024 * 1024)
    client = TestClient(application)
    headers = {"X-FundLex-User": "alice"}
    payload = {"name": "人工选择", "pairs": [{
        "client_pair_id": "pair-1", "label": "费率",
        "left": {"client_id": "left-1", "name": "left.docx", "size": len(left)},
        "right": {"client_id": "right-1", "name": "right.docx", "size": len(right)},
    }]}
    created = client.post("/api/compare/tasks", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    uploaded = client.post(
        f"/api/compare/tasks/{task_id}/uploads", headers=headers,
        data={"client_ids": json.dumps(["left-1", "right-1"])},
        files=[("files", ("left.docx", left)), ("files", ("right.docx", right))],
    )
    assert uploaded.status_code == 200, uploaded.text
    assert client.post(f"/api/compare/tasks/{task_id}/seal", headers=headers).status_code == 200
    assert CompareWorker(client.app.state.compare_store).run_once()
    pair_id = created.json()["pairs"][0]["id"]
    pair = client.get(f"/api/compare/pairs/{pair_id}", headers=headers)
    assert pair.status_code == 200, pair.text
    return client, headers, pair_id, pair.json(), left, right


def test_selection_api_persists_epoch_generates_idempotent_artifacts_and_downloads(tmp_path):
    client, headers, pair_id, pair, left, right = _ready_pair(tmp_path)
    selection_url = f"/api/compare/pairs/{pair_id}/selection"

    initial = client.get(selection_url, headers=headers)
    assert initial.status_code == 200, initial.text
    state = initial.json()
    assert state["selection"]["selection_epoch"] == 0
    assert state["assessment"]["pending_ids"] == ["D0001"]
    assert state["assessment"]["can_generate"] is False

    binding = {
        "expected_epoch": 0,
        "result_sha256": pair["result_sha256"],
        "left_source_sha256": pair["left"]["source_sha256"],
        "right_source_sha256": pair["right"]["source_sha256"],
    }
    conflict = client.put(selection_url, headers=headers, json={**binding, "decisions": {"D0001": "right"},
                                                               "result_sha256": "0" * 64})
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == "SELECTION_BINDING_MISMATCH"

    saved = client.put(selection_url, headers=headers,
                       json={**binding, "decisions": {"D0001": "right"}})
    assert saved.status_code == 200, saved.text
    saved_state = saved.json()
    assert saved_state["selection"]["selection_epoch"] == 1
    assert saved_state["selection"]["decisions"] == {"D0001": "right"}
    assert saved_state["assessment"]["can_generate"] is True

    stale = client.put(selection_url, headers=headers,
                       json={**binding, "decisions": {"D0001": "left"}})
    assert stale.status_code == 409
    assert stale.json()["detail"] == "SELECTION_EPOCH_CONFLICT"

    current_binding = {**binding, "expected_epoch": 1}
    preview = client.post(f"{selection_url}/preview", headers=headers, json=current_binding)
    assert preview.status_code == 200, preview.text
    assert preview.json()["assessment"]["can_generate"] is True

    generation_headers = {**headers, "Idempotency-Key": "gen-1"}
    generated = client.post(f"{selection_url}/generate", headers=generation_headers, json=current_binding)
    assert generated.status_code == 200, generated.text
    generation = generated.json()
    assert generation["version"] == 1
    assert {item["kind"] for item in generation["artifacts"]} == {
        "selected_final", "selected_redline", "selection_report_json", "selection_report_markdown",
    }

    repeated = client.post(f"{selection_url}/generate", headers=generation_headers, json=current_binding)
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["version"] == generation["version"]

    final_url = f"/api/compare/pairs/{pair_id}/selection-artifacts/1/selected_final"
    download = client.get(final_url, headers=headers)
    assert download.status_code == 200, download.text
    assert download.headers["x-content-sha256"] == hashlib.sha256(download.content).hexdigest()
    with ZipFile(io.BytesIO(download.content)) as archive:
        assert DOCUMENT in archive.namelist()
        assert b"0.30%" in archive.read(DOCUMENT)

    report = client.get(f"/api/compare/pairs/{pair_id}/selection-artifacts/1/report", headers=headers)
    assert report.status_code == 200, report.text
    assert "0.30%" in report.text

    changed = client.put(selection_url, headers=headers,
                         json={**current_binding, "decisions": {"D0001": "left"}})
    assert changed.status_code == 200, changed.text
    assert all(item["status"] == "stale" for item in changed.json()["artifacts"])

    second_binding = {**current_binding, "expected_epoch": 2}
    second = client.post(f"{selection_url}/generate", headers={**headers, "Idempotency-Key": "gen-2"},
                         json=second_binding)
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2
    assert any(item["version"] == 1 and item["status"] == "stale" for item in second.json()["artifacts"])
    assert any(item["version"] == 2 and item["status"] == "current" for item in second.json()["artifacts"])

    reused = client.post(f"{selection_url}/generate", headers={**headers, "Idempotency-Key": "gen-1"},
                         json=second_binding)
    assert reused.status_code == 409
    assert reused.json()["detail"] == "IDEMPOTENCY_KEY_CONFLICT"

    forbidden = client.get(final_url, headers={"X-FundLex-User": "bob"})
    assert forbidden.status_code == 404

    with client.app.state.compare_store._connect() as db:
        db.execute("UPDATE compare_selection_drafts SET decision_hash=? WHERE pair_id=?", ("0" * 64, pair_id))
    tampered = client.get(selection_url, headers=headers)
    assert tampered.status_code == 409
    assert tampered.json()["detail"] == "COMPARE_SELECTION_INVALID"
