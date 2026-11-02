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


def test_ingest_strips_inert_attached_template_link(tmp_path):
    """Word .doc→.docx saves keep an attachedTemplate rel; ingest must accept (FL-D1024)."""
    import io, zipfile, hashlib
    from fundlex.compare.ingest import prepare_compare_upload
    try:
        from docx import Document
    except ImportError:
        import pytest; pytest.skip("python-docx unavailable")
    doc = Document()
    doc.add_paragraph("第一条 基金合同当事人及权利义务")
    doc.add_paragraph("基金管理人：广发基金管理有限公司")
    buf = io.BytesIO()
    doc.save(buf)
    raw = buf.getvalue()
    attached = (
        '<Relationship Id="rIdAttachedTpl1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/attachedTemplate" '
        'Target="file:///C:/Templates/Normal.dotm" TargetMode="External"/>')
    rebuilt = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(raw)) as src, zipfile.ZipFile(rebuilt, "w") as dst:
        for item in src.namelist():
            content = src.read(item)
            if item == "word/_rels/settings.xml.rels":
                content = content.replace(b"</Relationships>", attached.encode() + b"</Relationships>")
            dst.writestr(item, content)
    data = rebuilt.getvalue()
    out = prepare_compare_upload("converted.docx", data)
    assert out["original_sha256"] == hashlib.sha256(data).hexdigest()
    assert out["original_size"] == len(data)
