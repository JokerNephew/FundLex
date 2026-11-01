"""Browser scenario: upload a guide, see the version list, open the diff view.

Covers the React「指引」page end to end with the real API and guide store;
parsing is seeded through the store (the model channel is covered by the
worker quality-channel tests) so this stays deterministic and model-free.
"""
from __future__ import annotations

import io
import json
import os
import socket
import threading
import time

import pytest

pytestmark = [
    pytest.mark.browser,
    pytest.mark.v1,
    pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                       reason="opt-in browser suite"),
]


def _docx_bytes(label: str) -> bytes:
    from docx import Document

    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def _document(rules, *, clean=True, errors=None) -> dict:
    from fundlex.guide import GUIDE_SCHEMA_VERSION

    return {"schema_version": GUIDE_SCHEMA_VERSION, "parser_version": "guide-parse-1",
            "prompt_versions": {"guide_parse": "guide_parse_v1", "guide_verify": "guide_verify_v1"},
            "groups": rules,
            "validation": {"errors": errors or [], "warnings": [], "coverage_gaps": [],
                           "clean": clean, "rounds": 1,
                           "verification": {"findings": [], "invalid_findings": 0}}}


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=os.getenv("FUNDLEX_BROWSER_HEADLESS", "1") != "0")
        yield instance
        instance.close()


@pytest.fixture
def live_app(tmp_path, monkeypatch):
    import uvicorn

    from fundlex import guide_store
    from fundlex.api import create_app
    from fundlex.store import RunStore

    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_FRONTEND_VERSION", "v2")
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    # Seed the store BEFORE create_app so both share rows through SQLite.
    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    first = guide_store.create_custom_version(store, "local-dev", "guide-v1.docx",
                                              _docx_bytes("指引 v1"))
    job = guide_store.claim_guide_job(store)
    guide_store.finish_guide_job(
        store, job["id"], job["fencing_token"],
        document=_document([{"rule_id": "G01", "title": "旧服务费条款",
                             "requirement": "按旧口径修改", "operations": []}]))
    second = guide_store.reparse_version(store, "local-dev", first["id"])
    job = guide_store.claim_guide_job(store)
    guide_store.finish_guide_job(
        store, job["id"], job["fencing_token"],
        document=_document([{"rule_id": "G01", "title": "新服务费条款",
                             "requirement": "按新口径修改", "operations": []},
                            {"rule_id": "G02", "title": "新增直销优惠",
                             "requirement": "补充直销口径", "operations": []}]))
    app = create_app(tmp_path / "state")
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
    yield base, {"first": first["id"], "second": second["id"]}
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def test_upload_list_and_compare_view(browser, live_app, tmp_path):
    base, ids = live_app
    page = browser.new_page(viewport={"width": 1440, "height": 980})
    page_errors: list[str] = []
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    try:
        page.goto(f"{base}/guides", wait_until="networkidle")
        page.wait_for_selector("text=我的指引", timeout=15_000)
        # Version list: built-in plus the two seeded, parsed versions.  Round-2 UI
        # intentionally hides raw version ids (FL-D721 技术黑话清除); anchor on the
        # per-version detail links instead of visible id text (FL-D733).
        page.wait_for_selector(f"css=a[href='/guides/{ids['second']}']", timeout=15_000)
        page.wait_for_selector(f"css=a[href='/guides/{ids['first']}']", timeout=15_000)
        page.wait_for_selector("text=内置", timeout=15_000)
        # Upload flow: a fresh DOCX appears in the list as uploaded/parsing.
        upload_path = tmp_path / "fresh-guide.docx"
        upload_path.write_bytes(_docx_bytes("浏览器上传指引"))
        page.locator('input[type="file"]').set_input_files(str(upload_path))
        page.get_by_role("button", name="上传并解析").click()
        page.wait_for_selector("text=fresh-guide.docx", timeout=15_000)
        # Compare view: defaults current-vs-previous and shows the rule delta.
        page.wait_for_selector("h2:has-text('版本对比')", timeout=15_000)
        against = page.get_by_label("基准版本")
        against.select_option(ids["first"])
        target = page.get_by_label("对比版本")
        target.select_option(ids["second"])
        summary = page.locator("[data-testid='guide-diff-summary']")
        summary.wait_for(timeout=15_000)
        text = summary.inner_text().replace(" ", "").replace("\u00a0", "")
        # 摘要文案在两条前端线略异：stats 卡「规则数 1→2」 vs 段落「规则 1 条 → 2 条」，
        # 断言只锁定「1 变 2」语义，不绑定具体排版（FL-D733 同类口径）。
        assert "1→2" in text or "1条→2条" in text
        # 修改规则的字段差异在折叠 details 里（guide-diff 主线交互），先展开再断言。
        change = page.locator(".guide-diff-change summary")
        if change.count():
            change.first.click()
        body = page.locator("body").inner_text()
        assert "新增规则" in body and "G02" in body
        assert "新服务费条款" in body and "旧服务费条款" in body
        assert not page_errors, page_errors
    finally:
        page.close()
