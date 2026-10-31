"""V1 工作台：带修订痕迹的 DOCX 上传不再被拒收（2026-10-31 基底固化决策）。

No Worker or model calls: this verifies the upload acceptance boundary and the
transparency of the base semantics in the UI (no special prompt is required).
Opt in with FUNDLEX_BROWSER_TESTS=1.
"""
from __future__ import annotations

import io
import json
import os
import re
import socket
import threading
import time
import zipfile
from pathlib import Path

import pytest
from lxml import etree

pytestmark = pytest.mark.skipif(
    os.getenv("FUNDLEX_BROWSER_TESTS") != "1" and os.getenv("FUNDLEX_LEGACY_BROWSER_TESTS") != "1",
    reason="opt-in V1 workbench suite")

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
DOCUMENT_PART = "word/document.xml"


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def live_app(tmp_path, monkeypatch):
    import uvicorn
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_FRONTEND_VERSION", "v1")
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    from fundlex.api import create_app
    app = create_app(tmp_path / "data", auth_db=str(tmp_path / "auth.sqlite3"))
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(.02)
    assert server.started
    yield app, base
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


@pytest.fixture
def ui(browser, live_app):
    app, base = live_app
    context = browser.new_context(viewport={"width": 1440, "height": 960})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','browser-check')")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page, context, app, base
    context.close()
    assert not errors, errors


def tracked_docx_bytes() -> bytes:
    """Synthetic contract carrying a foreign ``法律部`` ins/del pair."""
    from docx import Document

    stream = io.BytesIO()
    doc = Document()
    doc.add_paragraph("前后端接口测试合同，非引擎业务验收。")
    doc.save(stream)

    with zipfile.ZipFile(io.BytesIO(stream.getvalue())) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    root = etree.fromstring(parts[DOCUMENT_PART])
    paragraph = root.find(_q("body")).find(_q("p"))

    def run(text, tag="t"):
        r = etree.Element(_q("r"))
        t = etree.SubElement(r, _q(tag))
        t.text = text
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        return r

    for kind, rid, tag, text in (("ins", "9001", "t", "（法律部插入）"),
                                 ("del", "9002", "delText", "（法律部删除）")):
        wrapper = etree.SubElement(paragraph, _q(kind))
        wrapper.set(_q("id"), rid)
        wrapper.set(_q("author"), "法律部")
        wrapper.set(_q("date"), "2026-10-01T00:00:00Z")
        wrapper.append(run(text, tag))
    parts[DOCUMENT_PART] = etree.tostring(root, encoding="UTF-8", xml_declaration=True)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


UPLOAD_FILE = {"name": "带痕迹合同.docx",
               "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               "buffer": None}  # filled per test


def test_tracked_upload_accepted_via_api(ui):
    _, context, _, base = ui
    data = tracked_docx_bytes()
    headers = {"X-FundLex-User": "browser-check"}
    response = context.request.post(base + "/api/tasks", headers=headers,
                                    data={"name": "带痕迹上传任务", "engine_id": "recall_first",
                                          "files": [{"client_id": "c0",
                                                     "name": UPLOAD_FILE["name"],
                                                     "size": len(data)}]})
    assert response.ok, response.text()
    task = response.json()["id"]
    response = context.request.post(base + f"/api/tasks/{task}/uploads", headers=headers,
        multipart={"client_ids": json.dumps(["c0"]),
                   "files": {**UPLOAD_FILE, "buffer": data}})
    assert response.ok, f"tracked upload must not be rejected: {response.text()}"
    docs = context.request.get(base + f"/api/tasks/{task}/documents",
                               headers=headers).json()["items"]
    assert [doc["name"] for doc in docs] == [UPLOAD_FILE["name"]]
    # The file is accepted for processing, never refused for tracked changes.
    assert "EXISTING_REVISION" not in json.dumps(docs, ensure_ascii=False)


def test_tracked_upload_accepted_via_page(ui):
    page, context, _, base = ui
    data = tracked_docx_bytes()
    page.goto(base + "/#import")
    page.wait_for_function("document.querySelector('#upload-limit').textContent.includes('MiB')")
    page.fill("#task-name", "带痕迹页面上传")
    page.set_input_files("#file-picker", {**UPLOAD_FILE, "buffer": data})
    assert UPLOAD_FILE["name"] in page.inner_text("#import-rows")
    page.locator("#submit-task").click()
    # Upload completes (the progress box re-hides) without any tracked-changes
    # refusal toast, and the task appears on the server.
    for _ in range(100):
        if page.locator("#upload-progress").is_hidden():
            break
        page.wait_for_timeout(50)
    assert page.locator("#upload-progress").is_hidden()
    if page.locator("#toast").is_visible():
        toast_text = page.inner_text("#toast")
        assert "修订" not in toast_text and "EXISTING_REVISION" not in toast_text
    for _ in range(100):
        response = context.request.get(base + "/api/tasks",
                                       headers={"X-FundLex-User": "browser-check"})
        if any(item["name"] == "带痕迹页面上传" for item in response.json()["items"]):
            break
        page.wait_for_timeout(50)
    else:
        raise AssertionError("task not created after page upload")
    detail = page.inner_text("#detail-body") if page.locator("#detail-body").count() else ""
    assert "修订痕迹" not in detail
