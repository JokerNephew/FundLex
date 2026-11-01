"""指引版本对比的首次用户视角走查（FL-D770/771）。

真实后端（store/端点/静态资源全部真实），Chromium 走「我的指引 → 版本对比」
完整路径；不调用模型（版本由 store helper 直接预置为已解析）。
截图存 FUNDLEX_GUIDE_DIFF_SHOTS（默认 /tmp/opencode/qa/shots）作为走查证据。
"""
from __future__ import annotations

import io
import os
import socket
import threading
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                                reason="opt-in browser suite")

SHOTS = Path(os.getenv("FUNDLEX_GUIDE_DIFF_SHOTS", "/tmp/opencode/qa/shots"))


def _docx(*paragraphs: str) -> bytes:
    from docx import Document
    stream = io.BytesIO()
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(stream)
    return stream.getvalue()


def _document(rules) -> dict:
    from fundlex.guide import GUIDE_SCHEMA_VERSION
    return {"schema_version": GUIDE_SCHEMA_VERSION, "parser_version": "guide-parse-1",
            "prompt_versions": {"guide_parse": "guide_parse_v1"},
            "groups": rules,
            "validation": {"errors": [], "warnings": [], "coverage_gaps": [],
                           "clean": True, "rounds": 1,
                           "verification": {"findings": [], "invalid_findings": 0}}}


def _parsed(store, name: str, paragraphs, rules) -> dict:
    from fundlex import guide_store
    version = guide_store.create_custom_version(store, "alice", name, _docx(*paragraphs))
    job = guide_store.claim_guide_job(store)
    return guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                        document=_document(rules))["version"]


def _ensure_v2_dist() -> Path:
    """V2 用例需要当前源码构建的 dist；源码新于产物时现场构建一次。"""
    frontend = Path(__file__).resolve().parents[2] / "frontend"
    entry = frontend / "dist" / "index.html"
    source = frontend / "src" / "pages" / "Guides" / "CompareCard.tsx"
    if entry.is_file() and entry.stat().st_mtime >= source.stat().st_mtime:
        return frontend / "dist"
    import subprocess
    build = subprocess.run(
        [str(frontend / "node_modules" / ".bin" / "vite"), "build"],
        cwd=frontend, capture_output=True, text=True, timeout=600)
    assert build.returncode == 0, build.stdout + build.stderr
    return frontend / "dist"


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    import uvicorn
    from fundlex.api import create_app
    app = create_app(tmp_path_factory.mktemp("guide-diff") / "data")
    store = app.state.store
    old = _parsed(store, "赎回费指引v1.docx",
                  ["第一章 总则", "赎回费由基金份额持有人承担", "第七章 附则"],
                  [{"rule_id": "G01", "title": "赎回费归属（旧）", "requirement": "要求",
                    "operations": [{"op": "append", "new_text": "甲"}]}])
    new = _parsed(store, "赎回费指引v2.docx",
                  ["第一章 总则", "赎回费全额计入基金财产", "第七章 附则"],
                  [{"rule_id": "G01", "title": "赎回费归属（新）", "requirement": "要求",
                    "operations": [{"op": "append", "new_text": "甲"}]},
                   {"rule_id": "G02", "title": "销售服务费", "requirement": "要求"}])
    server_socket = socket.socket()
    server_socket.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{server_socket.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [server_socket]},
                              daemon=True)
    thread.start()
    import time
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield {"base": base, "old": old, "new": new}
    server.should_exit = True
    thread.join(timeout=10)
    server_socket.close()


@pytest.fixture(scope="module")
def live_v2(tmp_path_factory, monkeypatch_module):
    """V2 React 壳的同款真实后端（React 页面覆盖版本对比卡第二读者）。"""
    import uvicorn
    _ensure_v2_dist()
    from fundlex.api import create_app
    monkeypatch_module.setenv("FUNDLEX_FRONTEND_VERSION", "v2")
    app = create_app(tmp_path_factory.mktemp("guide-diff-v2") / "data")
    store = app.state.store
    old = _parsed(store, "赎回费指引v1.docx",
                  ["第一章 总则", "赎回费由基金份额持有人承担"],
                  [{"rule_id": "G01", "title": "赎回费归属（旧）",
                    "operations": [{"op": "append", "new_text": "甲"}]}])
    new = _parsed(store, "赎回费指引v2.docx",
                  ["第一章 总则", "赎回费全额计入基金财产"],
                  [{"rule_id": "G01", "title": "赎回费归属（新）",
                    "operations": [{"op": "append", "new_text": "甲"}]},
                   {"rule_id": "G02", "title": "销售服务费"}])
    server_socket = socket.socket()
    server_socket.bind(("127.0.0.1", 0))
    base = f"http://127.0.0.1:{server_socket.getsockname()[1]}"
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [server_socket]},
                              daemon=True)
    thread.start()
    import time
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    yield {"base": base, "old": old, "new": new}
    server.should_exit = True
    thread.join(timeout=10)
    server_socket.close()


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch
    patch = MonkeyPatch()
    yield patch
    patch.undo()


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(
            headless=os.getenv("FUNDLEX_BROWSER_HEADLESS", "1") != "0")
        yield instance
        instance.close()


def _page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','alice')")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, errors


def test_guide_version_compare_first_time_user_walkthrough(live, browser):
    SHOTS.mkdir(parents=True, exist_ok=True)
    context, page, page_errors = _page(browser)
    try:
        page.goto(live["base"] + "/#guide", wait_until="networkidle")
        # 批1（FL-D739）指引页 tab 化：版本对比卡位于「版本对比与上传」分区，先切过去。
        page.locator('[data-guide-page-tab="diff"]').click()
        # 版本对比卡在指引列表之后出现；两个下拉各两个自定义版本+内置，无 UUID 上屏。
        card = page.locator("#guide-diff-card")
        card.wait_for()
        assert "版本对比" in card.inner_text()
        to_selector = page.locator("#guide-diff-to")
        from_selector = page.locator("#guide-diff-from")
        to_selector.wait_for()
        assert "赎回费指引v" in to_selector.inner_text()
        assert "（内置）" in to_selector.inner_text()
        card_text = card.inner_text()
        # 版本对比卡不得把版本 UUID 上屏（文件名+时间+当前/内置标签已足够辨版本）。
        assert live["old"]["id"] not in card_text and live["new"]["id"] not in card_text
        # 默认对比 = 最新两版：规则差异自动加载，三分组可见。
        page.locator(".guide-diff-grid").wait_for(timeout=15000)
        grid_text = page.locator(".guide-diff-grid").inner_text()
        assert "新增规则 · 1 条" in grid_text and "G02" in grid_text
        assert "删除规则 · 0 条" in grid_text and "修改规则 · 1 条" in grid_text
        # 修改项可展开字段级细节：标题 旧→新。
        page.locator(".guide-diff-change summary").first.click()
        fields = page.locator(".guide-diff-fields").inner_text()
        assert "标题" in fields and "赎回费归属（旧）" in fields and "赎回费归属（新）" in fields
        page.screenshot(path=str(SHOTS / "guide-diff-rules.png"), full_page=False)
        # 原文比对：合并稿默认，差异高亮存在。
        page.locator('[data-guide-diff-tab="text"]').click()
        page.locator(".guide-diff-merged .compare-document").wait_for(timeout=15000)
        merged = page.locator(".guide-diff-merged").inner_text()
        assert "赎回费" in merged
        assert page.locator(".guide-diff-merged .compare-ins, .guide-diff-merged .compare-del, "
                            ".guide-diff-merged .compare-diff").count() >= 1
        page.screenshot(path=str(SHOTS / "guide-diff-text-merged.png"), full_page=False)
        # 并排对照：左右两栏都是原文。
        page.locator('[data-guide-diff-view="side"]').click()
        page.locator(".guide-diff-panes .compare-pane").nth(1).wait_for(timeout=15000)
        assert page.locator(".guide-diff-panes .compare-pane").count() == 2
        assert "赎回费由基金份额持有人承担" in page.locator(".guide-diff-panes .compare-pane").nth(0).inner_text()
        assert "赎回费全额计入基金财产" in page.locator(".guide-diff-panes .compare-pane").nth(1).inner_text()
        page.screenshot(path=str(SHOTS / "guide-diff-text-side.png"), full_page=False)
        # 基准换成内置指引：人读提示，无错误码上屏。
        from fundlex import guide_store
        from_selector.select_option(guide_store.BUILTIN_GUIDE_ID)
        page.locator("#guide-diff-body", has_text="内置指引没有上传的原文文件").wait_for(timeout=15000)
        assert "BUILTIN_SOURCE_UNAVAILABLE" not in page.locator("#guide-diff-body").inner_text()
        page.screenshot(path=str(SHOTS / "guide-diff-builtin-hint.png"), full_page=False)
        assert not page_errors, page_errors
    finally:
        context.close()


def test_guide_version_compare_v2_walkthrough(live_v2, browser):
    """V2 React 指引页走查：同一版本对比体验第二读者。"""
    SHOTS.mkdir(parents=True, exist_ok=True)
    context = browser.new_context(viewport={"width": 1440, "height": 1100})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','alice')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    try:
        page.goto(live_v2["base"] + "/guides", wait_until="networkidle")
        page.get_by_role("heading", name="版本对比").wait_for(timeout=20000)
        page.locator(".guide-diff-grid").wait_for(timeout=15000)
        grid = page.locator(".guide-diff-grid").inner_text()
        assert "新增规则 · 1 条" in grid and "G02" in grid and "修改规则 · 1 条" in grid
        # 修改项展开给字段级 旧→新，不再是 JSON 团。
        page.locator(".guide-diff-change summary").first.click()
        fields = page.locator(".guide-diff-fields").inner_text()
        assert "标题" in fields and "赎回费归属（旧）" in fields
        assert '"old"' not in page.locator(".guide-diff-grid").inner_text()
        page.screenshot(path=str(SHOTS / "guide-diff-v2-rules.png"))
        page.get_by_role("tab", name="原文比对").click()
        page.locator(".guide-diff-merged").wait_for(timeout=15000)
        assert "赎回费" in page.locator(".guide-diff-merged").inner_text()
        page.get_by_role("button", name="并排对照").click()
        page.locator(".guide-diff-panes .guide-diff-pane").nth(1).wait_for(timeout=15000)
        assert page.locator(".guide-diff-panes .guide-diff-pane").count() == 2
        page.screenshot(path=str(SHOTS / "guide-diff-v2-text-side.png"))
        # 版本下拉不带 UUID 前缀。
        card = page.locator("text=版本对比").locator("..").locator("..")
        assert live_v2["old"]["id"] not in card.inner_text()
        assert not page_errors, page_errors
    finally:
        context.close()


