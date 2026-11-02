"""FL-D1024: parser-rejected uploads must leave server-side evidence.

The ingest guard flattens the cause into COMPARE_INVALID_DOCX for clients;
without capture, a real user file rejected at prepare_compare_upload leaves
zero diagnosis on the server. This test pins: response keeps the public code
unchanged, and the file bytes + traceback are captured under the diag dir.
"""
import hashlib
import io

from docx import Document
from fastapi.testclient import TestClient

from fundlex.api import create_app


def _docx():
    buf = io.BytesIO()
    doc = Document()
    doc.add_paragraph("急诊合并件测试用合同，非业务验收。")
    doc.save(buf)
    return buf.getvalue()


def test_rejected_upload_bytes_and_traceback_are_captured(tmp_path, monkeypatch):
    diag = tmp_path / "diag"
    monkeypatch.setenv("FUNDLEX_REJECT_DIAG_DIR", str(diag))

    def _boom(name, data):
        raise ValueError("synthetic ingest failure for FL-D1024 test")

    monkeypatch.setattr(
        "fundlex.compare.ingest.prepare_compare_upload", _boom)

    left, right = _docx(), _docx()
    client = TestClient(create_app(tmp_path / "store"))
    headers = {"X-FundLex-User": "alice"}
    payload = {"name": "capture", "pairs": [{"client_pair_id": "p", "label": "P",
        "left": {"client_id": "l", "name": "left.docx", "size": len(left)},
        "right": {"client_id": "r", "name": "right.docx", "size": len(right)}}]}
    created = client.post("/api/compare/tasks", headers=headers, json=payload)
    assert created.status_code == 201
    task_id = created.json()["id"]
    uploaded = client.post(
        f"/api/compare/tasks/{task_id}/uploads", headers=headers,
        data={"client_ids": '["l","r"]'},
        files=[("files", ("left.docx", left)), ("files", ("right.docx", right))])
    assert uploaded.status_code == 200
    receipt = next(item for item in uploaded.json()["receipts"]
                   if item["client_id"] == "l")
    # 响应面零变化：对外仍是扁平 COMPARE_INVALID_DOCX
    assert receipt["error_code"] == "COMPARE_INVALID_DOCX"
    # 诊断面：字节+异常落盘，sha 与上传文件一致
    sha = hashlib.sha256(left).hexdigest()[:16]
    captured = diag / f"reject-{sha}.docx"
    assert captured.exists(), f"capture missing: {list(diag.iterdir())}"
    assert captured.read_bytes() == left
