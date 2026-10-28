"""Password-session browser coverage for the regulation candidate workflow.

The candidate Worker, persistence and HTTP routes are real.  The model router
is deterministic so this test remains a repeatable UI/integration check and
does not spend model budget.
"""
from __future__ import annotations

import io
import os
import socket
import sys
import threading
import time
from pathlib import Path

import pytest

from fundlex.api import create_app
from fundlex.guide_generation.worker import GuideGenerationWorker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guide_generation_fakes import FakeGuideRouter


pytestmark = pytest.mark.skipif(
    os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
    reason="opt-in browser suite")


def _docx_bytes(*paragraphs: str) -> bytes:
    from docx import Document

    stream = io.BytesIO()
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(stream)
    return stream.getvalue()


def _regulation_bytes() -> bytes:
    return _docx_bytes(
        "测试销售费用管理规定",
        "第一条",
        "基金管理人销售其管理的基金，不得收取认（申）购费、销售服务费。",
        "第二条",
        "对于投资者持续持有期限少于七日的基金份额，应当收取不低于赎回金额1.5%的赎回费，并将上述赎回费全额计入基金财产。",
    )


def _contract(path: Path) -> None:
    path.write_bytes(_docx_bytes(
        "测试基金基金合同",
        "第一部分  前言",
        "订立本基金合同的目的是保护投资人合法权益。",
        "第二部分  基金费用与税收",
        "一、基金费用的种类",
        "本基金A类基金份额不收取销售服务费，C类基金份额的销售服务费按前一日C类基金份额资产净值的0.40%年费率计提。",
        "第三部分  基金份额的申购与赎回",
        "本基金A类基金份额的申购费率由基金管理人决定，并在招募说明书中列示。",
        "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。",
    ))


@pytest.fixture
def password_browser_app(tmp_path, monkeypatch):
    import uvicorn

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    _contract(corpus / "测试基金基金合同_20240101.docx")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    monkeypatch.setenv("FUNDLEX_GUIDE_CORPUS_DIR", str(corpus))
    monkeypatch.setenv("FUNDLEX_ALLOW_REGISTRATION", "0")
    app = create_app(tmp_path / "data", auth_db=str(tmp_path / "auth.sqlite3"))
    username = "guidebrowser"
    password = "guide-browser-password"
    app.state.users.create_user(username, password, "法规浏览器验收", "member")
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
    try:
        yield app, base, username, password, corpus
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=os.getenv("FUNDLEX_BROWSER_HEADLESS", "1") != "0")
        yield instance
        instance.close()


def test_password_browser_candidate_upload_edit_publish_and_download(browser, password_browser_app):
    app, base, username, password, corpus = password_browser_app
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.goto(base + "/")
        page.locator("#login-username").fill(username)
        page.locator("#login-password").fill(password)
        page.locator("#login-submit").click()
        page.locator("#topbar-user").wait_for(state="visible")

        page.goto(base + "/#generation?mode=new")
        page.locator("#gg-file").wait_for(state="attached")
        page.locator("#gg-file").set_input_files({
            "name": "测试法规.docx",
            "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "buffer": _regulation_bytes(),
        })
        page.locator("#gg-cost-ack").check()
        page.locator("#gg-submit").click()
        import re
        page.wait_for_url(re.compile(r".*#generation\?.*mode=detail.*id=[0-9a-f]+.*"), timeout=30000)
        run_id = page.evaluate("() => new URLSearchParams(location.hash.split('?')[1]).get('id')")
        assert run_id

        # Run the real persisted candidate job after the browser has enqueued it.
        worker = GuideGenerationWorker(app.state.store, router_factory=lambda: FakeGuideRouter())
        assert worker.run_once() is True

        page.locator('[data-gg-action="refresh"]').click()
        page.locator('[data-gg-tab="guide"]').click()
        page.locator("[data-gg-item]").first.wait_for()
        page.locator("[data-gg-item]").first.click()
        page.locator('[data-gg-field="title"]').fill("浏览器人工确认指引")
        page.locator('[data-gg-action="save"]').click()
        page.get_by_text("人工草稿 · 待审阅", exact=False).first.wait_for()

        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-tab="versions"]').click()
        page.get_by_role("button", name="批准当前精确版本").click()
        page.get_by_text("候选已批准", exact=False).first.wait_for()
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="发布已批准版本").click()
        page.get_by_text("候选已发布", exact=False).first.wait_for()
        assert page.get_by_role("button", name="批准当前精确版本").is_disabled()
        assert page.get_by_role("button", name="发布已批准版本").is_disabled()

        with page.expect_download() as download_info:
            page.get_by_role("button", name="当前候选 DOCX").click()
        download = download_info.value
        downloaded = Path(download.path())
        assert downloaded.read_bytes()[:2] == b"PK"

        # The browser's authenticated fetch path is required; an unauthenticated
        # request to the same owner-scoped artifact is rejected.
        unauthenticated = context.request.get(
            f"{base}/api/guide-generation/runs/{run_id}/download/guide")
        assert unauthenticated.status == 401
        candidate = app.state.guide_generation_store.get_candidate(run_id)
        assert candidate["status"] == "published"
        assert candidate["versions"][-1]["status"] == "published"
    finally:
        context.close()
    assert not errors, errors
