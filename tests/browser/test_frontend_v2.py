"""Browser smoke coverage for the React/Vite workbench entry.

This suite checks the shipped React shell and deep-link refresh behavior. It
does not start the Worker or call a model; the real document delivery path is
covered by the separate live end-to-end evidence.
"""
from __future__ import annotations

import io
import json
import os
import re
import socket
import threading
import time

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
    reason="opt-in React V2 Chromium smoke suite",
)


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def live_app(tmp_path, monkeypatch):
    import uvicorn
    from fundlex.api import create_app

    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    app = create_app(tmp_path / "data", auth_db=str(tmp_path / "auth.sqlite3"))
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield base
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def test_react_routes_and_deep_links(browser, live_app):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','v2-browser-check')")
    page = context.new_page()
    page_errors: list[str] = []
    console_errors: list[str] = []
    api_404s: list[str] = []
    missing_resources: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
    def collect_404(response):
        if response.status != 404:
            return
        if "/api/" in response.url:
            api_404s.append(response.url)
        else:
            missing_resources.append(response.url)

    page.on("response", collect_404)
    try:
        for path, heading in (("/tasks", "任务"), ("/tasks/new", "新建任务"), ("/guides", "指引配置"), ("/settings", "设置")):
            response = page.goto(live_app + path, wait_until="networkidle")
            assert response and response.ok
            page.locator("#root").wait_for(state="visible")
            assert heading in page.locator("body").inner_text()
        response = page.goto(live_app + "/tasks/nonexistent/documents/doc/review", wait_until="networkidle")
        assert response and response.ok
        page.locator("#root").wait_for(state="visible")
        assert not page_errors
        unexpected_console_errors = [
            message for message in console_errors
            if message != "Failed to load resource: the server responded with a status of 404 (Not Found)"
        ]
        assert not unexpected_console_errors, f"console errors: {unexpected_console_errors}; API 404s: {api_404s}; resources: {missing_resources}"
        assert not missing_resources, f"404 resources: {missing_resources}; expected API 404s: {api_404s}"
    finally:
        context.close()


def test_built_entry_and_assets_are_cacheable(browser, live_app):
    context = browser.new_context()
    try:
        response = context.request.get(live_app + "/")
        assert response.ok
        assert "no-store" in response.headers.get("cache-control", "")
        html = response.text()
        assert "/assets/" in html
        assets = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
        assert assets
        for asset in assets:
            asset_response = context.request.get(live_app + asset)
            assert asset_response.ok
            assert "immutable" in asset_response.headers.get("cache-control", "")
    finally:
        context.close()


def test_real_task_document_deep_links_use_task_scoped_api(browser, live_app):
    from docx import Document

    stream = io.BytesIO()
    document = Document()
    document.add_paragraph("React V2 浏览器深链测试合同。")
    document.save(stream)
    data = stream.getvalue()
    identity = "v2-document-check"
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script(f"localStorage.setItem('fundlex-dev-user', {json.dumps(identity)});")
    page = context.new_page()
    requests: list[str] = []
    page_errors: list[str] = []
    page.on("request", lambda request: requests.append(request.url))
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        headers = {"X-FundLex-User": identity}
        created = context.request.post(
            live_app + "/api/tasks",
            headers=headers,
            data={
                "name": "React V2 深链任务",
                "engine_id": "recall_first",
                "files": [{"client_id": "browser-doc-1", "name": "深链合同.docx", "size": len(data)}],
            },
        )
        assert created.ok, created.text()
        task_id = created.json()["id"]
        uploaded = context.request.post(
            live_app + f"/api/tasks/{task_id}/uploads",
            headers=headers,
            multipart={
                "client_ids": json.dumps(["browser-doc-1"]),
                "files": {
                    "name": "深链合同.docx",
                    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "buffer": data,
                },
            },
        )
        assert uploaded.ok, uploaded.text()
        documents = context.request.get(live_app + f"/api/tasks/{task_id}/documents", headers=headers)
        assert documents.ok, documents.text()
        document_id = documents.json()["items"][0]["document_id"]

        response = page.goto(live_app + f"/tasks/{task_id}/documents/{document_id}/detail", wait_until="networkidle")
        assert response and response.ok
        assert "深链合同.docx" in page.locator("body").inner_text()
        assert "报告读取失败" in page.locator("body").inner_text()

        response = page.goto(live_app + f"/tasks/{task_id}/documents/{document_id}/review", wait_until="networkidle")
        assert response and response.ok
        assert "修订呈现读取失败" in page.locator("body").inner_text()
        assert any(f"/api/tasks/{task_id}/documents/{document_id}" in url for url in requests)
        assert not page_errors, page_errors
    finally:
        context.close()


def test_review_renders_void_document_tags_without_page_error(browser, live_app):
    """A real revision payload may contain HTML void tags such as ``<hr>``."""
    task_id = "review-task"
    document_id = "review-document"
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','review-browser-check');")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def json_route(route, body):
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))

    document = {
        "task_id": task_id,
        "document_id": document_id,
        "name": "Review void tag.docx",
        "job_status": "succeeded",
        "delivery_status": "complete",
        "downloads": {"redline": f"/api/tasks/{task_id}/documents/{document_id}/download/redline"},
    }
    revisions = {
        "document_id": document_id,
        "html": "<p>原文</p><hr><p><ins data-rev='2'>新文</ins></p>",
        "revisions": [{"del_id": 1, "ins_id": 2, "old_text": "原文", "new_text": "新文"}],
    }

    def handle(route):
        request = route.request
        path = request.url.split("/api", 1)[-1].split("?", 1)[0]
        if path == f"/tasks/{task_id}/documents/{document_id}":
            return json_route(route, document)
        if path == f"/tasks/{task_id}/documents":
            return json_route(route, {"items": [document], "total": 1, "page": 1, "page_size": 200})
        if path == f"/tasks/{task_id}/documents/{document_id}/revisions":
            return json_route(route, revisions)
        return route.continue_()

    page.route("**/api/**", handle)
    try:
        response = page.goto(live_app + f"/tasks/{task_id}/documents/{document_id}/review", wait_until="networkidle")
        assert response and response.ok
        page.get_by_role("heading", name="修订清单").wait_for(state="visible")
        assert "Review void tag.docx" in page.locator("body").inner_text()
        assert not page_errors, page_errors
    finally:
        context.close()


def test_new_task_manifest_search_filter_pagination_and_compare_entry(browser, live_app, tmp_path):
    """The React upload list keeps the original manifest interactions reachable."""
    from docx import Document

    files = []
    for index in range(11):
        path = tmp_path / f"清单合同-{index:02d}.docx"
        document = Document()
        document.add_paragraph(f"合同 {index}")
        document.save(path)
        files.append(path)
    invalid = tmp_path / "说明.txt"
    invalid.write_text("invalid", encoding="utf-8")

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','v2-manifest-check');")
    page = context.new_page()
    try:
        response = page.goto(live_app + "/tasks/new", wait_until="networkidle")
        assert response and response.ok
        page.locator("input[type=file]").first.set_input_files([str(path) for path in files] + [str(invalid)])
        page.get_by_text("文件清单").wait_for()
        assert "第 1 / 2 页" in page.locator("body").inner_text()
        assert page.locator(".upload-manifest-table tbody tr").count() == 10

        page.get_by_role("button", name="下一页").click()
        assert "清单合同-10.docx" in page.locator("body").inner_text()
        page.get_by_placeholder("搜索当前待提交文件").fill("10.docx")
        assert page.locator(".upload-manifest-table tbody tr").count() == 1
        page.get_by_placeholder("搜索当前待提交文件").fill("")
        page.get_by_role("combobox").last.select_option("issue")
        assert "说明.txt" in page.locator("body").inner_text()
        assert page.locator(".upload-manifest-table tbody tr").count() == 1

        compare = page.locator('a[href="/compare"]')
        assert compare.is_visible()
        compare.click()
        page.wait_for_url(re.compile(r"/compare$"))
        page.locator('[data-nav="compare"]').click()
        page.locator("#compare-new").wait_for(state="visible")
        assert "独立合同对比工作台" in page.locator("body").inner_text()
        assert page.locator('a[href="/"]').is_visible()
    finally:
        context.close()


def test_new_task_invalid_replacement_removes_old_upload_row(browser, live_app, tmp_path):
    """A failed replacement cannot leave the previous file silently submittable."""
    from docx import Document

    original = tmp_path / "原合同.docx"
    document = Document()
    document.add_paragraph("原合同")
    document.save(original)
    invalid = tmp_path / "替换说明.txt"
    invalid.write_text("invalid", encoding="utf-8")

    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','v2-replace-check');")
    page = context.new_page()
    try:
        response = page.goto(live_app + "/tasks/new", wait_until="networkidle")
        assert response and response.ok
        page.locator("input[type=file]").first.set_input_files(str(original))
        page.get_by_text("原合同.docx").wait_for()
        page.get_by_role("button", name="替换").click()
        page.wait_for_timeout(100)
        page.locator('input[type=file][accept*="docx"]').last.set_input_files(str(invalid))
        page.get_by_text("只支持 DOCX 文件。", exact=False).wait_for()
        assert "原合同.docx" not in page.locator(".upload-manifest-table").inner_text()
        assert "替换说明.txt" in page.locator(".upload-manifest-table").inner_text()
        assert page.get_by_role("button", name="创建任务并上传").is_disabled()
    finally:
        context.close()


def test_shell_shrinks_when_viewport_changes_from_desktop_to_medium(browser, live_app):
    """Responsive layout also stays bounded when a browser is resized in place."""
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','v2-resize-check');")
    page = context.new_page()
    try:
        response = page.goto(live_app + "/tasks", wait_until="networkidle")
        assert response and response.ok
        page.set_viewport_size({"width": 768, "height": 900})
        page.wait_for_timeout(150)
        metrics = page.evaluate("""() => ({ viewport: innerWidth, documentWidth: document.documentElement.scrollWidth, bodyWidth: document.body.scrollWidth })""")
        assert metrics["documentWidth"] <= metrics["viewport"]
        assert metrics["bodyWidth"] <= metrics["viewport"]
    finally:
        context.close()
