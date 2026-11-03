"""FL-D1089 回归：超限上传必须归因 UPLOAD_SIZE_LIMIT，不得被 MANIFEST_FILE_MISMATCH 覆盖。

机理：API 读流以 MAX_UPLOAD_BYTES+1 截断 → 校验层正确归因 UPLOAD_SIZE_LIMIT；但
清单比对的 `item["size"] != f["size"]` 曾因截断尺寸无条件改判 MANIFEST_FILE_MISMATCH，
用户被误导为「文件与清单不匹配」。修复=清单比对仅在无既有 error_code 时进行。
"""
from concurrent.futures import ThreadPoolExecutor
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

ALICE = {"X-FundLex-User": "alice"}


def package(label="fixture"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f"<document>{label}</document>")
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setattr("fundlex.upload_validation.MAX_UPLOAD_BYTES", 1024)
    monkeypatch.setattr("fundlex.api.MAX_UPLOAD_BYTES", 1024)
    from fundlex.api import create_app
    return TestClient(create_app(tmp_path / "task-store"))


def test_oversize_upload_keeps_size_limit_attribution(client):
    data = package() + b"x" * 2048  # ~2KB，大于打补丁后的 1024 上限
    create = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "d1089"},
                         json={"name": "超限归因", "engine_id": "recall_first",
                               "files": [{"client_id": "big-1", "name": "大件.docx", "size": len(data)}]})
    assert create.status_code == 201
    task = create.json()["id"]
    upload = client.post(f"/api/tasks/{task}/uploads", headers=ALICE,
                         data={"client_ids": json.dumps(["big-1"])},
                         files=[("files", ("大件.docx", data))])
    assert upload.status_code == 200
    documents = client.get(f"/api/tasks/{task}/documents", headers=ALICE).json()["items"]
    assert len(documents) == 1
    assert documents[0]["upload_status"] == "rejected"
    assert documents[0]["error_code"] == "UPLOAD_SIZE_LIMIT", documents[0]


def test_true_manifest_mismatch_still_reports_mismatch(client):
    """对照组：真实「声明尺寸与实传内容不符」仍判 MANIFEST_FILE_MISMATCH（修刀不误伤正路）。"""
    data = package()
    create = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "d1089-b"},
                         json={"name": "真实不符", "engine_id": "recall_first",
                               "files": [{"client_id": "odd-1", "name": "合同.docx", "size": len(data) + 999}]})
    assert create.status_code == 201
    task = create.json()["id"]
    upload = client.post(f"/api/tasks/{task}/uploads", headers=ALICE,
                         data={"client_ids": json.dumps(["odd-1"])},
                         files=[("files", ("合同.docx", data))])
    assert upload.status_code == 200
    documents = client.get(f"/api/tasks/{task}/documents", headers=ALICE).json()["items"]
    assert documents[0]["upload_status"] == "rejected"
    assert documents[0]["error_code"] == "MANIFEST_FILE_MISMATCH", documents[0]
