"""V1 front-end remediation probes: workspace aggregate, Compare/guide/auth races,
guide initialisation, download names, status colours, keyboard entry and Review epochs.

These tests use the *real* repository HTML/JS through a temporary Uvicorn app and
Chromium.  Only the listed API responses are fixtures; static assets, app.js,
compare.js, workspace.js and guide_generation.js are the working-tree sources.
They are not production E2E and do not call the model.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                                reason="opt-in V1 Chromium suite")

CAP = {
    "auth_mode": "dev",
    "login_required": False,
    "registration_open": False,
    "app_version": "frontend-remediation",
    "upload_limits": {"max_file_bytes": 64 * 1024 * 1024},
    "engine": {"id": "test-engine", "delivery_mode": "formal", "guide": None, "actions_total": 0},
}


def _docx_bytes(*paragraphs: str) -> bytes:
    import io
    from docx import Document
    stream = io.BytesIO()
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(stream)
    return stream.getvalue()


def _start(app):
    import uvicorn
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
    return server, thread, sock, base


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=os.getenv("FUNDLEX_BROWSER_HEADLESS", "1") != "0")
        yield instance
        instance.close()


@pytest.fixture
def live_dev(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_FRONTEND_VERSION", "v1")
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "default"))
    from fundlex.api import create_app
    app = create_app(tmp_path / "data", auth_db=str(tmp_path / "auth.sqlite3"))
    server, thread, sock, base = _start(app)
    yield app, base
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


@pytest.fixture
def live_password(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    monkeypatch.setenv("FUNDLEX_FRONTEND_VERSION", "v1")
    monkeypatch.setenv("FUNDLEX_ALLOW_REGISTRATION", "0")
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "default"))
    from fundlex.api import create_app
    app = create_app(tmp_path / "data", auth_db=str(tmp_path / "auth.sqlite3"))
    app.state.users.create_user("frontend-a", "frontend-a-password", "A", "member")
    app.state.users.create_user("frontend-b", "frontend-b-password", "B", "member")
    server, thread, sock, base = _start(app)
    yield app, base
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


def respond(route, body, status=200, headers=None):
    route.fulfill(status=status, content_type="application/json", body=json.dumps(body, ensure_ascii=False), headers=headers or {})


def install_api(page, handler):
    """Install one API dispatcher; ``handler(path, query, route)`` returns True when handled."""
    def dispatch(route):
        parts = urlsplit(route.request.url)
        if not parts.path.startswith("/api/"):
            return route.continue_()
        handler(parts.path, parse_qs(parts.query), route)
    page.route("**/api/**", dispatch)


def base_api(handler):
    """Wrap a scenario handler with the default app boot responses."""
    def dispatch(path, query, route):
        if path == "/api/capabilities":
            return respond(route, CAP)
        if path == "/api/tasks":
            return respond(route, {"items": [], "total": 0, "page": 1, "page_size": 20})
        if path == "/api/tasks/stats":
            return respond(route, {"total": 0, "counts": {}, "daily": []})
        if path == "/api/guides":
            return respond(route, {"items": []})
        if path == "/api/integrations/feishu/binding":
            return respond(route, {"bound": False})
        return handler(path, query, route)
    return dispatch


def open_dev(page, base, fragment=""):
    page.goto(base + "/" + fragment, wait_until="networkidle")


def test_workspace_aggregate_error_empty_filter_pagination_and_deep_link(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','workspace-probe')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    requests: list[str] = []
    fail = {"first": True}

    items = [
        {"kind": "revision", "id": "REV-1", "name": "修订任务｜价值优选", "status": "running", "phase": "DISCOVERY_REQUIREMENT_RETRIEVAL",
         "scale": {"value": 12, "unit": "份合同"}, "attention": [], "created_at": "2026-10-28T01:00:00", "updated_at": "2026-10-28T02:00:00"},
        {"kind": "compare", "id": "CMP-1", "name": "比对任务｜A/B", "status": "complete_with_unresolved", "scale": {"value": 4, "unit": "组"},
         "attention": [{"label": "1 组覆盖不完整"}], "created_at": "2026-10-27T01:00:00", "updated_at": "2026-10-27T02:00:00"},
        {"kind": "generation", "id": "GEN-1", "name": "法规任务｜销售费用", "status": "failed", "scale": {"value": 2, "unit": "条"},
         "attention": ["模型服务异常"], "created_at": "2026-10-26T01:00:00", "updated_at": "2026-10-26T02:00:00"},
    ]

    def scenario(path, query, route):
        if path == "/api/workspace/tasks":
            requests.append(route.request.url)
            if fail["first"]:
                fail["first"] = False
                return respond(route, {"detail": "boom"}, status=500)
            kind = (query.get("kind") or [""])[0]
            rows = [item for item in items if not kind or item["kind"] == kind]
            return respond(route, {"items": rows, "total": 45, "page": int((query.get("page") or ["1"])[0]),
                                   "page_size": 20, "stats": {"active": 5, "attention": 8, "recent_completed": 12}})
        if path.startswith("/api/compare/tasks"):
            if path == "/api/compare/tasks":
                return respond(route, {"items": [], "total": 0})
            return respond(route, {"id": "CMP-1", "name": "比对任务｜A/B", "status": "succeeded", "total": 1, "pairs": []})
        if path.startswith("/api/tasks/REV-1"):
            return respond(route, {"id": "REV-1", "name": "修订任务｜价值优选", "status": "running", "total": 12, "uploaded": 12,
                                   "pending_upload": 0, "rejected": 0, "completed": 3, "processing": 1, "queued": 0, "failed": 0,
                                   "successful": 3, "exceptions": 0, "delivery_counts": {}, "qualification_counts": {}})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base)
        page.locator("#workspace-state").filter(has_text="暂时无法读取").wait_for()
        assert page.locator("#workspace-active").inner_text() == "—"
        page.locator("#workspace-refresh").click()
        page.locator(".workspace-task-name").first.wait_for()
        assert page.locator("#workspace-active").inner_text() == "5"
        assert page.locator("#workspace-attention").inner_text() == "8"
        assert page.locator("#workspace-completed").inner_text() == "12"
        assert page.locator(".workspace-task-name").first.inner_text() == "修订任务｜价值优选"
        assert page.locator('.workspace-launcher p, .workspace-metric small').count() == 0
        assert page.locator('#workspace-state').inner_text() == ''
        assert page.locator('.workspace-table th').nth(5).inner_text() == '创建时间'
        assert page.locator('#workspace-task-rows tr').first.locator('td').first.locator('small').count() == 0
        expected_created = page.evaluate("value => new Date(value).toLocaleString('zh-CN', {month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})", items[0]['created_at'])
        assert page.locator('.workspace-time').first.inner_text() == expected_created

        page.locator('[data-workspace-kind="compare"]').click()
        page.wait_for_url(re.compile(r".*kind=compare.*"))
        assert any("kind=compare" in url for url in requests)
        assert page.locator('[data-workspace-kind="compare"]').get_attribute("aria-pressed") == "true"

        page.locator("#workspace-search").fill("比对")
        page.wait_for_url(re.compile(r".*q=.*"))
        page.locator("#workspace-pagination [data-workspace-page='2']").click()
        page.wait_for_url(re.compile(r".*page=2.*"))

        page.reload(wait_until="networkidle")
        page.locator(".workspace-task-name").first.wait_for()
        assert page.locator("#workspace-search").input_value() == "比对"
        assert page.locator('[data-workspace-kind="compare"]').get_attribute("aria-pressed") == "true"

        page.locator('[data-workspace-open="compare"]').first.click()
        page.wait_for_url(re.compile(r".*#compare\?.*mode=detail.*id=CMP-1.*"))

        page.evaluate("document.dispatchEvent(new Event('fundlex:identity-reset'))")
        assert page.locator("#workspace-active").inner_text() == "—"
        assert page.locator(".workspace-task-name").count() == 0
    finally:
        context.close()
    assert page_errors == []


def test_compare_generate_late_response_cannot_save_the_previous_pair(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-race')")
    page = context.new_page()
    held: list = []
    writes: list[str] = []
    pair_ids = ["P1", "P2"]

    def view(pair_id):
        return {"pair": {"id": pair_id, "label": pair_id}, "result_sha256": "a" * 64,
                "left": {"name": pair_id + "-left.docx", "html": '<p data-block-id="b"><mark data-diff-id="D1">old</mark></p>'},
                "right": {"name": pair_id + "-right.docx", "html": '<p data-block-id="b"><mark data-diff-id="D1">new</mark></p>'},
                "summary": {"total": 1, "modify": 1, "insert": 0, "delete": 0}, "coverage": {"status": "complete"},
                "diffs": [{"id": "D1", "type": "modify", "section": "正文",
                           "left": {"text": "old", "block_id": "b"}, "right": {"text": "new", "block_id": "b"}}]}

    def selection(pair_id, decisions=None, epoch=0, generated=False):
        chosen = decisions if decisions is not None else {"D1": "pending"}
        pending = [key for key, value in chosen.items() if value == "pending"]
        artifacts = []
        if generated:
            artifacts = [{"version": epoch, "current": True, "stale": False,
                          "files": {"final": {"kind": "final", "sha256": "f" * 64, "size": 10,
                                              "download_url": f"/api/compare/pairs/{pair_id}/selection-artifacts/{epoch}/final"},
                                    "redline": {"kind": "redline", "sha256": "e" * 64, "size": 11,
                                                "download_url": f"/api/compare/pairs/{pair_id}/selection-artifacts/{epoch}/redline"}},
                          "report": {"version": epoch}}]
        return {"pair_id": pair_id, "result_sha256": "a" * 64, "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                "selection_epoch": epoch, "draft": {"selection_epoch": epoch, "decisions": chosen,
                                                    "decision_hash": ("d" if epoch == 0 else "e") * 64},
                "decisions": chosen, "assessment": {"pending_ids": pending, "issues": [], "can_generate": not pending},
                "diffs": view(pair_id)["diffs"], "artifacts": artifacts}

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [{"id": "T", "name": "race", "status": "succeeded", "total": 2,
                                              "pairs": [{"id": pair, "label": pair, "status": "succeeded",
                                                         "left": {"name": pair + "-left.docx"}, "right": {"name": pair + "-right.docx"},
                                                         "summary": {"total": 1}} for pair in pair_ids]}]})
        if path == "/api/compare/tasks/T":
            return respond(route, {"id": "T", "name": "race", "status": "succeeded", "total": 2,
                                   "pairs": [{"id": pair, "label": pair, "status": "succeeded",
                                              "left": {"name": pair + "-left.docx"}, "right": {"name": pair + "-right.docx"},
                                              "summary": {"total": 1}} for pair in pair_ids]})
        if route.request.method == "PUT" and re.fullmatch(r"/api/compare/pairs/P[12]/selection", path):
            pair_id = path.split("/")[4]
            body = json.loads(route.request.post_data or "{}")
            writes.append(path)
            return respond(route, selection(pair_id, decisions=body.get("decisions"), epoch=1))
        match = re.fullmatch(r"/api/compare/pairs/(P[12])/(view|selection)", path)
        if match:
            pair_id, kind = match.groups()
            return respond(route, view(pair_id) if kind == "view" else selection(pair_id))
        if path == "/api/compare/pairs/P1/selection/generate":
            held.append(route)
            return
        if path.endswith("/selection/preview"):
            return respond(route, {"assessment": {"pending_ids": [], "issues": [], "can_generate": True}})
        if path == "/api/compare/pairs/P2/selection/generate":
            return respond(route, {"version": 3})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T&pair=P1")
        page.locator("#compare-pair-title").filter(has_text="P1").wait_for()
        page.locator("#compare-selection-right-all").click()
        page.locator("#compare-selection-status").filter(has_text="已保存").wait_for()
        assert writes and writes[-1] == "/api/compare/pairs/P1/selection"

        page.locator("#compare-selection-generate").click()
        assert held, "generate request should be held"
        page.locator('[data-compare-pair="1"]').click()
        page.locator("#compare-pair-title").filter(has_text="P2").wait_for()
        page.locator("#compare-selection-progress").filter(has_text="待选择").wait_for()
        page.wait_for_timeout(300)
        switch_index = len(writes)
        page.locator("#compare-selection-left-all").click()
        page.locator("#compare-selection-status").filter(has_text="已保存").wait_for()

        respond(held.pop(), {"version": 1, "artifacts": []})
        page.wait_for_timeout(400)
        assert page.locator("#compare-pair-title").inner_text().endswith("P2")
        assert writes[switch_index:] and all(path.endswith("/P2/selection") for path in writes[switch_index:])
        assert not any(path.endswith("/P1/selection") for path in writes[switch_index:])
    finally:
        context.close()


def test_compare_stale_task_404_clears_previous_identity_cards(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-stale')")
    page = context.new_page()

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [], "total": 0})
        if path == "/api/compare/tasks/MISSING":
            return respond(route, {"detail": "not found"}, status=404)
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=MISSING")
        page.locator("#compare-task-name").filter(has_text="任务不可用").wait_for()
        assert "读取任务失败" in page.locator("#compare-task-status").inner_text()
        assert page.locator("#compare-pair-list").inner_text().strip() == ""
        back = page.locator("#compare-task-status [data-compare-back-list]")
        assert back.is_visible()
        back.click()
        page.wait_for_url(re.compile(r".*#compare\?.*mode=list.*"))
    finally:
        context.close()


def test_compare_word_style_reader_renders_merged_redline_and_display_modes(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    # 1600px：FL-D843 起比对区为页面内嵌 region（受应用框宽约束），rail 拖宽后
    # 源文档栏可分配宽度受总宽钳制，扩大视口保留「拖大可调宽」断言空间。
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-word-style')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    merged = ('<div class="compare-document compare-merged-document">'
              '<p class="compare-block has-change" data-block-id="R1">保留 <del class="compare-del" data-diff-id="D1">旧条款</del>'
              '<ins class="compare-ins" data-diff-id="D1">新条款</ins> 结尾</p></div>')
    diffs = [{"id": "D1", "type": "modify", "section": "正文",
              "left": {"text": "旧条款", "block_id": "L1"},
              "right": {"text": "新条款", "block_id": "R1"}}]

    def view():
        return {"pair": {"id": "P1", "label": "Word 样式"}, "result_sha256": "a" * 64,
                "left": {"name": "原文档.docx", "html": '<p data-block-id="L1"><mark class="compare-diff modify" data-diff-id="D1">旧条款</mark></p>'},
                "right": {"name": "修订文档.docx", "html": '<p data-block-id="R1"><mark class="compare-diff modify" data-diff-id="D1">新条款</mark></p>'},
                "merged": {"name": "修订文档.docx", "html": merged},
                "summary": {"total": 1, "modify": 1, "insert": 0, "delete": 0}, "coverage": {"status": "incomplete", "warnings": ["UNSUPPORTED_VISIBLE_CONTENT:header", "UNSUPPORTED_VISIBLE_CONTENT:footer"]},
                "diffs": diffs}

    def selection():
        return {"pair_id": "P1", "result_sha256": "a" * 64, "left_source_sha256": "b" * 64,
                "right_source_sha256": "c" * 64, "selection_epoch": 0,
                "draft": {"selection_epoch": 0, "decisions": {"D1": "pending"}, "decision_hash": "d" * 64},
                "decisions": {"D1": "pending"}, "assessment": {"pending_ids": ["D1"], "issues": [], "can_generate": False},
                "diffs": diffs, "artifacts": []}

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [{"id": "T", "name": "word-style", "status": "succeeded", "total": 1,
                                              "pairs": [{"id": "P1", "label": "Word 样式", "status": "succeeded",
                                                         "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                                         "summary": {"total": 1}}]}]})
        if path == "/api/compare/tasks/T":
            return respond(route, {"id": "T", "name": "word-style", "status": "succeeded", "total": 1,
                                   "pairs": [{"id": "P1", "label": "Word 样式", "status": "succeeded",
                                              "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                              "summary": {"total": 1}}]})
        if path == "/api/compare/pairs/P1/view":
            return respond(route, view())
        if path == "/api/compare/pairs/P1/selection":
            return respond(route, selection())
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T&pair=P1")
        page.locator("#compare-word-merged-pane .compare-ins").filter(has_text="新条款").wait_for()
        assert page.locator("#compare-word-merged-pane .compare-del").inner_text() == "旧条款"
        assert page.locator("#compare-revision-count-rail").inner_text() == "1"
        assert page.locator("#compare-merged-title").inner_text() == "Word 样式"
        assert page.locator("#compare-coverage-chip").is_visible()
        assert "2 项未覆盖" in page.locator("#compare-coverage-summary").inner_text()
        page.locator("#compare-coverage-summary").click()
        assert "header" in page.locator("#compare-coverage-list").inner_text()
        assert page.locator("#compare-coverage-list").is_visible()
        # FL-D843：比对结果区为页面内嵌 region（无 dialog/backdrop/全屏锁）
        assert page.locator("#compare-viewer").get_attribute("role") == "region"
        assert page.evaluate("document.body.classList.contains('compare-fullscreen-open')") is False
        rail = page.locator(".compare-word-revisions")
        rail_width = rail.bounding_box()["width"]
        splitter = page.locator("#compare-rail-splitter")
        assert splitter.is_visible()
        grip = splitter.bounding_box()
        page.mouse.move(grip["x"] + 3, grip["y"] + min(240, grip["height"] / 2))
        page.mouse.down()
        page.mouse.move(grip["x"] + 63, grip["y"] + min(240, grip["height"] / 2), steps=5)
        page.mouse.up()
        page.wait_for_timeout(150)
        assert rail.bounding_box()["width"] >= rail_width + 20

        # FL-D843：无关闭按钮，退出经「← 返回比对任务列表」回列表再进入
        page.locator("[data-compare-back-list]").click()
        assert page.locator("#compare-viewer").is_hidden()
        page.locator('[data-compare-task="T"]').click()
        page.locator("#compare-viewer").wait_for(state="visible")
        page.wait_for_selector('#compare-pair-list > *', state='attached')
        page.locator('[data-compare-pair="0"]').click()
        page.locator("#compare-viewer").wait_for(state="visible")

        page.locator("#compare-show-sources").uncheck()
        assert page.locator(".compare-word-sources").evaluate("element => getComputedStyle(element).display") == "none"
        page.locator("#compare-show-sources").check()
        assert page.locator(".compare-word-sources").evaluate("element => getComputedStyle(element).display") != "none"
        sources = page.locator(".compare-word-sources")
        sources_width = sources.bounding_box()["width"]
        word_splitter = page.locator("#compare-word-splitter")
        assert word_splitter.is_visible()
        word_grip = word_splitter.bounding_box()
        page.mouse.move(word_grip["x"] + 3, word_grip["y"] + min(240, word_grip["height"] / 2))
        page.mouse.down()
        page.mouse.move(word_grip["x"] - 47, word_grip["y"] + min(240, word_grip["height"] / 2), steps=5)
        page.mouse.up()
        page.wait_for_timeout(150)
        assert sources.bounding_box()["width"] >= sources_width + 20

        page.locator("#compare-markup-mode").select_option("final")
        assert page.locator("#compare-word-merged-pane .compare-del").evaluate("element => getComputedStyle(element).display") == "none"
        assert page.locator("#compare-word-merged-pane .compare-block.has-change").evaluate("element => getComputedStyle(element, '::before').display") == "none"

        page.locator('[data-compare-view-mode="classic"]').click()
        assert page.locator("#compare-word-view").is_hidden()
        assert page.locator("#compare-classic-view").is_visible()
        assert page.locator("#compare-left-pane .compare-diff").inner_text() == "旧条款"
        page.locator('[data-compare-view-mode="word"]').click()
        assert page.locator("#compare-word-view").is_visible()
        assert page.locator("#compare-classic-view").is_hidden()
    finally:
        context.close()
    assert page_errors == []


@pytest.mark.parametrize("count,unequal", [(60, False), (650, True)])
def test_compare_scroll_sync_uses_aligned_paragraphs(browser, live_dev, count, unequal):
    """Scrolling a long-enough document must keep the left, merged and right
    panes on the same paragraph instead of mapping scrollbar ratios."""
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-scroll-sync')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    def block(index: int, side: str) -> str:
        text = f"第{index + 1}条 " + ("本合同双方应当按照约定履行义务。" * (3 + index % 4))
        if index == 30:
            text += '<ins class="compare-ins" data-diff-id="D1">新增内容</ins>'
        return f'<p class="compare-block" data-block-id="{side}{index}">{text}</p>'

    inserted = ''.join(f'<p class="compare-block" data-block-id="R-extra-{i}">新增独立条款{i}</p>' for i in range(15)) if unequal else ''
    right_ids = [i for i in range(count) if not (unequal and 280 <= i < 300)]
    merged = '<div class="compare-document compare-merged-document">' + inserted + "".join(
        block(index, "L" if unequal and 280 <= index < 300 else "R") for index in range(count)) + "</div>"
    left_html = '<div class="compare-document">' + "".join(block(index, "L") for index in range(count)) + "</div>"
    right_html = '<div class="compare-document">' + inserted + "".join(block(index, "R") for index in right_ids) + "</div>"
    alignment = [{"id": f"G{i}", "left": [f"L{i}"], "right": [f"R{i}"] if i in right_ids else []} for i in range(count)]
    diffs = [{"id": "D1", "type": "insert", "section": "正文",
              "left": None, "left_anchor": {"block_id": "L30"},
              "right": {"text": "新增内容", "block_id": "R30"},
              "right_spans": [{"block_id": "R30"}]}]

    def view():
        return {"pair": {"id": "P5", "label": "滚动同步"}, "result_sha256": "a" * 64,
                "left": {"name": "原文档.docx", "html": left_html},
                "right": {"name": "修订文档.docx", "html": right_html},
                "merged": {"name": "修订文档.docx", "html": merged},
                "summary": {"total": 1, "insert": 1, "modify": 0, "delete": 0},
                "coverage": {"status": "complete", "warnings": []}, "diffs": diffs, "alignment": alignment}

    def selection():
        return {"pair_id": "P5", "result_sha256": "a" * 64,
                "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                "selection_epoch": 0,
                "draft": {"selection_epoch": 0, "decisions": {"D1": "pending"}, "decision_hash": "d" * 64},
                "decisions": {"D1": "pending"},
                "assessment": {"pending_ids": ["D1"], "issues": [], "can_generate": False},
                "diffs": diffs, "artifacts": []}

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [{"id": "T5", "name": "scroll-sync", "status": "succeeded", "total": 1,
                                              "pairs": [{"id": "P5", "label": "滚动同步", "status": "succeeded",
                                                         "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                                         "summary": {"total": 1}}]}]})
        if path == "/api/compare/tasks/T5":
            return respond(route, {"id": "T5", "name": "scroll-sync", "status": "succeeded", "total": 1,
                                   "pairs": [{"id": "P5", "label": "滚动同步", "status": "succeeded",
                                              "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                              "summary": {"total": 1}}]})
        if path == "/api/compare/pairs/P5/view":
            return respond(route, view())
        if path == "/api/compare/pairs/P5/selection":
            return respond(route, selection())
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T5&pair=P5")
        page.locator("#compare-word-merged-pane .compare-ins").wait_for(state="attached")
        page.locator("#compare-show-sources").check()
        page.locator("#compare-word-left-pane .compare-block").first.wait_for(state="visible")
        page.wait_for_timeout(300)
        page.locator("#compare-word-merged-pane").evaluate("element => { element.scrollTop += 520; }")
        page.wait_for_timeout(700)
        read_visible = """() => {
          const read = id => {
            const pane = document.getElementById(id), doc = pane?._virtualDoc;
            if (!pane || !doc) return null;
            const top = pane.scrollTop, rect = pane.getBoundingClientRect();
            for (const chunk of doc.chunks) {
              if (!chunk.el) continue;
              for (let i = 0; i < chunk.el.children.length; i++) {
                const node = chunk.el.children[i], r = node.getBoundingClientRect();
                if (r.top - rect.top + top + r.height > top + 1) {
                  return {index: chunk.start + i, text: node.textContent.trim().slice(0, 18)};
                }
              }
            }
            return null;
          };
          return document.getElementById('compare-classic-view').hidden
            ? {merged: read('compare-word-merged-pane'), left: read('compare-word-left-pane'), right: read('compare-word-right-pane')}
            : {left: read('compare-left-pane'), right: read('compare-right-pane')};
        }"""
        visible = page.evaluate(read_visible)
        assert visible["left"]["text"] == visible["right"]["text"] == visible["merged"]["text"]
        for pane_id, index in [('compare-word-left-pane', count - 80 if unequal else 35),
                               ('compare-word-right-pane', 160 if unequal else 22),
                               ('compare-word-merged-pane', 350 if unequal else 32)]:
            page.locator('#' + pane_id).evaluate('(e,i)=>e._virtualDoc.scrollToBlockIndex(i,.3)', index)
            page.wait_for_timeout(700)
            visible = page.evaluate(read_visible)
            assert visible['left']['text'] == visible['right']['text'] == visible['merged']['text'], visible
        page.locator('[data-compare-view-mode="classic"]').click()
        page.wait_for_timeout(700)
        for pane_id, delta in [('compare-left-pane', 5000 if unequal else 500), ('compare-right-pane', -1200 if unequal else -250)]:
            page.locator('#' + pane_id).evaluate('(e,d)=>e.scrollTop+=d', delta)
            page.wait_for_timeout(700)
            visible = page.evaluate(read_visible)
            assert visible['left']['text'] == visible['right']['text'], visible
    finally:
        context.close()
    assert page_errors == []


def test_compare_save_retry_enables_generate_after_failed_autosave(browser, live_dev):
    """A failed automatic save must leave the explicit save action usable.
    Clicking it must not pass the click event as a diff-id array, and a
    successful retry must enable generation."""
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-save-retry')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    merged = ('<div class="compare-document compare-merged-document">'
              '<p class="compare-block has-change" data-block-id="R4">保留 <del class="compare-del" data-diff-id="D4">旧条款</del>'
              '<ins class="compare-ins" data-diff-id="D4">新条款</ins> 结尾</p></div>')
    diffs = [{"id": "D4", "type": "modify", "section": "正文",
              "left": {"text": "旧条款", "block_id": "L4"},
              "right": {"text": "新条款", "block_id": "R4"}}]
    put_count = {"value": 0}

    def selection(decision="pending", epoch=0):
        decisions = {"D4": decision}
        pending = [] if decision != "pending" else ["D4"]
        return {"pair_id": "P4", "result_sha256": "a" * 64,
                "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                "selection_epoch": epoch,
                "draft": {"selection_epoch": epoch, "decisions": decisions, "decision_hash": "d" * 64},
                "decisions": decisions,
                "assessment": {"pending_ids": pending, "issues": [], "can_generate": not pending},
                "diffs": diffs, "artifacts": []}

    def view():
        return {"pair": {"id": "P4", "label": "保存重试"}, "result_sha256": "a" * 64,
                "left": {"name": "原文档.docx", "html": '<p data-block-id="L4"><mark class="compare-diff modify" data-diff-id="D4">旧条款</mark></p>'},
                "right": {"name": "修订文档.docx", "html": '<p data-block-id="R4"><mark class="compare-diff modify" data-diff-id="D4">新条款</mark></p>'},
                "merged": {"name": "修订文档.docx", "html": merged},
                "summary": {"total": 1, "modify": 1, "insert": 0, "delete": 0},
                "coverage": {"status": "complete", "warnings": []}, "diffs": diffs}

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [{"id": "T4", "name": "save-retry", "status": "succeeded", "total": 1,
                                              "pairs": [{"id": "P4", "label": "保存重试", "status": "succeeded",
                                                         "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                                         "summary": {"total": 1}}]}]})
        if path == "/api/compare/tasks/T4":
            return respond(route, {"id": "T4", "name": "save-retry", "status": "succeeded", "total": 1,
                                   "pairs": [{"id": "P4", "label": "保存重试", "status": "succeeded",
                                              "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                              "summary": {"total": 1}}]})
        if path == "/api/compare/pairs/P4/view":
            return respond(route, view())
        if path == "/api/compare/pairs/P4/selection":
            if route.request.method == "PUT":
                put_count["value"] += 1
                if put_count["value"] == 1:
                    return respond(route, {"detail": "forced failure"}, status=500)
                return respond(route, selection("right", 1))
            return respond(route, selection())
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T4&pair=P4")
        page.locator("#compare-word-merged-pane .compare-ins").wait_for(state="visible")
        page.locator("#compare-selection-right-all").click()
        page.locator("#compare-selection-status").filter(has_text="保存未完成").wait_for()
        assert page.locator("#compare-selection-save").is_enabled()
        assert not page.locator("#compare-selection-generate").is_enabled()
        page.locator("#compare-selection-save").click()
        page.locator("#compare-selection-status").filter(has_text="已保存").wait_for()
        page.wait_for_timeout(100)
        assert not page.locator("#compare-selection-save").is_enabled()
        assert page.locator("#compare-selection-generate").is_enabled()
        assert "1 / 1" in page.locator("#compare-selection-progress").inner_text()
        assert put_count["value"] == 2
    finally:
        context.close()
    assert page_errors == []


def test_compare_diff_click_locates_virtualized_pure_insertion(browser, live_dev):
    """A pure insertion whose right block id is absent from the merged projection
    must still scroll the virtual document to its inserted mark."""
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-virtual-click')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))

    blocks = []
    for index in range(70):
        text = f"第{index + 1}条 " + "本合同双方应当按照约定履行义务。" * 8
        if index == 55:
            blocks.append(f'<p class="compare-block has-change">{text}<ins class="compare-ins" data-diff-id="D60">新增条款</ins></p>')
        else:
            blocks.append(f'<p class="compare-block">{text}</p>')
    merged = '<div class="compare-document compare-merged-document">' + ''.join(blocks) + '</div>'
    diffs = [{"id": "D60", "type": "insert", "section": "正文",
              "left": None, "right": {"text": "新增条款", "block_id": "R-MISSING"},
              "right_spans": [{"block_id": "R-MISSING"}]}]

    def view():
        return {"pair": {"id": "P2", "label": "虚拟定位"}, "result_sha256": "a" * 64,
                "left": {"name": "原文档.docx", "html": '<p data-block-id="L1">原条款</p>'},
                "right": {"name": "修订文档.docx", "html": '<p data-block-id="R-MISSING">新增条款</p>'},
                "merged": {"name": "修订文档.docx", "html": merged},
                "summary": {"total": 1, "insert": 1, "modify": 0, "delete": 0},
                "coverage": {"status": "complete", "warnings": []}, "diffs": diffs}

    def selection():
        return {"pair_id": "P2", "result_sha256": "a" * 64,
                "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                "selection_epoch": 0,
                "draft": {"selection_epoch": 0, "decisions": {"D60": "pending"}, "decision_hash": "d" * 64},
                "decisions": {"D60": "pending"},
                "assessment": {"pending_ids": ["D60"], "issues": [], "can_generate": False},
                "diffs": diffs, "artifacts": []}

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [{"id": "T2", "name": "virtual-click", "status": "succeeded", "total": 1,
                                              "pairs": [{"id": "P2", "label": "虚拟定位", "status": "succeeded",
                                                         "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                                         "summary": {"total": 1}}]}]})
        if path == "/api/compare/tasks/T2":
            return respond(route, {"id": "T2", "name": "virtual-click", "status": "succeeded", "total": 1,
                                   "pairs": [{"id": "P2", "label": "虚拟定位", "status": "succeeded",
                                              "left": {"name": "原文档.docx"}, "right": {"name": "修订文档.docx"},
                                              "summary": {"total": 1}}]})
        if path == "/api/compare/pairs/P2/view":
            return respond(route, view())
        if path == "/api/compare/pairs/P2/selection":
            return respond(route, selection())
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T2&pair=P2")
        page.locator("#compare-word-merged-pane .compare-ins").wait_for(state="attached")
        page.locator(".compare-diff-item .compare-diff-jump").first.click()
        page.wait_for_timeout(700)
        assert page.locator("#compare-diff-counter").inner_text() == "1 / 1"
        mark = page.locator('#compare-word-merged-pane .compare-ins.is-active[data-diff-id="D60"]')
        assert mark.count() == 1
        mark_box = mark.bounding_box()
        pane_box = page.locator("#compare-word-merged-pane").bounding_box()
        assert mark_box and pane_box
        assert mark_box["y"] >= pane_box["y"] - 1
        assert mark_box["y"] + mark_box["height"] <= pane_box["y"] + pane_box["height"] + 1
    finally:
        context.close()
    assert page_errors == []


def test_guide_run_switch_rejects_late_detail_and_download(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','guide-race')")
    page = context.new_page()
    held: list = []
    downloads: list[str] = []
    hold_a_refresh = {"armed": False}
    runs = {run_id: {"id": run_id, "title": f"Regulation {run_id}", "filename": f"{run_id}.docx", "status": "complete",
                     "stage": "FINALIZE_GUIDE", "qualification_status": "candidate_ready", "updated_at": "2026-10-28T01:00:00",
                     "artifacts": {"evidence_json": f"/api/guide-generation/runs/{run_id}/download/evidence_json"},
                     "summary": {}, "stats": {}, "stages": [],
                     "candidate": {"status": "candidate_ready", "current_version_id": f"{run_id}-v1", "current_version_no": 1}}
            for run_id in ("A", "B")}

    def scenario(path, query, route):
        if path == "/api/guide-generation/runs":
            return respond(route, {"items": [runs["A"], runs["B"]]})
        if path == "/api/guide-generation/runs/A" and hold_a_refresh["armed"]:
            held.append(route)
            return
        match = re.fullmatch(r"/api/guide-generation/runs/([AB])", path)
        if match:
            return respond(route, runs[match.group(1)])
        match = re.fullmatch(r"/api/guide-generation/runs/([AB])/guide", path)
        if match:
            return respond(route, {"items": [{"guide_item_id": "G1", "title": f"Guide content {match.group(1)}",
                                              "conditions": [], "exceptions": [], "old_text_patterns": []}],
                                   "families": [], "human_versions": [], "human_changes": []})
        match = re.fullmatch(r"/api/guide-generation/runs/([AB])/requirements", path)
        if match:
            return respond(route, {"items": []})
        if re.fullmatch(r"/api/guide-generation/runs/([AB])/candidate", path):
            return respond(route, {"candidate_guide_id": "C", "run_id": path.split("/")[4], "owner": "o",
                                   "status": "candidate_ready", "current_version_id": "v1", "versions": []})
        match = re.fullmatch(r"/api/guide-generation/runs/([AB])/download/([a-z_]+)", path)
        if match:
            run_id, kind = match.groups()
            downloads.append(f"/runs/{run_id}/download/{kind}")
            return route.fulfill(status=200, body=b"{}" if kind.endswith("json") else b"<p>ok</p>",
                                 headers={"Content-Type": "application/json" if kind.endswith("json") else "text/html",
                                          "Content-Disposition": f'attachment; filename="{run_id}-{kind}.{"json" if kind.endswith("json") else "html"}"'})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#generation?mode=detail&id=A")
        page.locator("#gg-detail-head").filter(has_text="Regulation A").wait_for()
        page.locator('[data-gg-tab="guide"]').click()
        page.locator("#gg-panel").filter(has_text="Guide content A").wait_for()

        hold_a_refresh["armed"] = True
        page.locator('[data-gg-action="refresh"]').click()
        deadline = time.monotonic() + 5
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        assert held

        page.evaluate("location.hash='#generation?mode=detail&id=B'")
        page.locator("#gg-detail-head").filter(has_text="Regulation B").wait_for()
        page.locator('[data-gg-tab="guide"]').click()
        page.locator("#gg-panel").filter(has_text="Guide content B").wait_for()

        respond(held.pop(), runs["A"])
        page.wait_for_timeout(400)
        assert "Regulation B" in page.locator("#gg-detail-head").inner_text()
        assert "Guide content B" in page.locator("#gg-panel").inner_text()

        page.locator('[data-gg-tab="versions"]').click()
        with page.expect_download():
            page.locator('[data-gg-download="evidence_json"]').click()
        page.wait_for_timeout(200)
        assert downloads and downloads[-1] == "/runs/B/download/evidence_json"
    finally:
        context.close()


def test_guide_initialisation_retry_keyboard_and_existing_deep_link(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','guide-init')")
    page = context.new_page()
    page_errors: list[str] = []
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    fail = {"first": True}
    runs = {run_id: {"id": run_id, "title": f"Regulation {run_id}", "filename": f"{run_id}.docx", "status": "complete",
                     "stage": "FINALIZE_GUIDE", "qualification_status": "candidate_ready", "updated_at": "2026-10-28T01:00:00",
                     "artifacts": {}, "summary": {}, "stats": {}, "stages": [], "candidate": None}
            for run_id in ("A", "B")}

    def scenario(path, query, route):
        if path == "/api/guide-generation/runs":
            if fail["first"]:
                fail["first"] = False
                return respond(route, {"detail": "list unavailable"}, status=500)
            return respond(route, {"items": [runs["A"], runs["B"]]})
        if re.fullmatch(r"/api/guide-generation/runs/[AB]", path):
            return respond(route, runs[path.rsplit("/", 1)[-1]])
        if re.fullmatch(r"/api/guide-generation/runs/[AB]/(guide|requirements|candidate)", path):
            if path.endswith("guide"):
                return respond(route, {"items": [], "families": [], "human_versions": [], "human_changes": []})
            if path.endswith("requirements"):
                return respond(route, {"items": []})
            return respond(route, {"candidate_guide_id": "C", "run_id": "A", "owner": "o", "status": "draft",
                                   "current_version_id": "", "versions": []})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#generation?mode=list")
        page.locator("#gg-list-results .gg-error").wait_for()
        page.get_by_role("button", name="重试").click()
        page.locator("[data-gg-run]").first.wait_for()
        assert page.locator("[data-gg-run]").count() == 2

        page.locator("[data-gg-run]").nth(1).focus()
        page.keyboard.press("Enter")
        page.wait_for_url(re.compile(r".*#generation\?.*mode=detail.*id=B.*"))
        page.locator("#gg-detail-head").filter(has_text="Regulation B").wait_for()

        page.reload(wait_until="networkidle")
        page.locator("#gg-detail-head").filter(has_text="Regulation B").wait_for()
    finally:
        context.close()
    assert page_errors == []


def test_guide_badges_use_warning_not_green_pass_and_download_names(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','guide-badge')")
    page = context.new_page()
    artifacts = {
        "guide": "/api/guide-generation/runs/A/download/guide",
        "evidence_json": "/api/guide-generation/runs/A/download/evidence_json",
        "evidence_html": "/api/guide-generation/runs/A/download/evidence_html",
        "engine_json": "/api/guide-generation/runs/A/download/engine_json",
        "engine_html": "/api/guide-generation/runs/A/download/engine_html",
    }
    detail = {"id": "A", "title": "Regulation A", "filename": "A.docx", "status": "complete_with_unresolved",
              "stage": "FINALIZE_GUIDE", "qualification_status": "pass_with_findings", "artifacts": artifacts,
              "updated_at": "2026-10-28T01:00:00", "summary": {"finalize": {"checklist": {"residual_saturated": False}}},
              "stats": {}, "stages": [{"stage": "FINALIZE_GUIDE", "status": "pass_with_findings"}],
              "candidate": {"status": "candidate_with_findings", "current_version_id": "v1", "current_version_no": 1},
              "engine_status": "not_run"}

    def scenario(path, query, route):
        if path == "/api/guide-generation/runs/A":
            return respond(route, detail)
        if re.fullmatch(r"/api/guide-generation/runs/A/(quality|coverage|residual|requirements)", path):
            return respond(route, {"items": [], "summary": {}, "rounds": []})
        if path == "/api/guide-generation/runs/A/candidate":
            return respond(route, {"candidate_guide_id": "C", "run_id": "A", "owner": "o", "status": "candidate_with_findings",
                                   "current_version_id": "v1", "versions": [{"candidate_version_id": "v1", "version_no": 1,
                                                                               "status": "candidate_with_findings", "payload": {}}]})
        if path.startswith("/api/guide-generation/runs/A/download/"):
            kind = path.rsplit("/", 1)[-1]
            ext = "docx" if kind in {"guide", "guide_ai"} else ("json" if kind.endswith("json") else "html")
            mime = ("application/vnd.openxmlformats-officedocument.wordprocessingml.document" if ext == "docx"
                    else "application/json" if ext == "json" else "text/html")
            return route.fulfill(status=200, body=b"PK" if ext == "docx" else b"{}" if ext == "json" else b"<p/>",
                                 headers={"Content-Type": mime,
                                          "Content-Disposition": f'attachment; filename="guide_generation_evidence.{ext}"' if kind.startswith("evidence")
                                          else f'attachment; filename="{kind}.{ext}"'})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#generation?mode=detail&id=A")
        page.locator("#gg-detail-head").filter(has_text="Regulation A").wait_for()
        badge = page.locator(".gg-badge").filter(has_text="已完成 · 仍有问题").first
        badge.wait_for()
        assert "gg-warning" in (badge.get_attribute("class") or "")
        colour = badge.evaluate("node => getComputedStyle(node).color")
        assert "22, 101, 52" not in colour and "rgb(22, 101, 52)" not in colour
        finding = page.locator(".gg-badge").filter(has_text="存在问题").first
        assert "gg-warning" in (finding.get_attribute("class") or "")

        page.locator('[data-gg-tab="versions"]').click()
        names = {}
        for kind in ("evidence_json", "evidence_html", "engine_json", "engine_html"):
            with page.expect_download() as info:
                page.locator(f'[data-gg-download="{kind}"]').click()
            names[kind] = info.value.suggested_filename
        assert names["evidence_json"].endswith(".json") and "docx" not in names["evidence_json"]
        assert names["evidence_html"].endswith(".html")
        assert names["engine_json"].endswith(".json")
        assert names["engine_html"].endswith(".html")
    finally:
        context.close()


def test_v1_review_generation_submits_selection_epoch_and_manifest(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','review-epoch')")
    page = context.new_page()
    bodies: list[dict] = []
    doc = {"task_id": "t", "batch_id": "b", "document_id": "doc", "name": "合同.docx", "size": 100, "upload_status": "accepted",
           "eligibility": "eligible", "job_status": "succeeded", "delivery_status": "incomplete",
           "downloads": {"redline": "/api/tasks/t/documents/doc/download/redline"},
           "review_url": "/api/batches/b/documents/doc/revisions"}
    task = {"id": "t", "name": "任务", "status": "completed", "total": 1, "uploaded": 1, "pending_upload": 0, "rejected": 0,
            "completed": 1, "processing": 0, "queued": 0, "failed": 0, "legacy": False, "delivery_counts": {"incomplete": 1},
            "qualification_counts": {"eligible": 1}, "successful": 0, "exceptions": 0, "summary_url": "/api/tasks/t/report"}

    def scenario(path, query, route):
        if path == "/api/tasks/t":
            return respond(route, task)
        if path == "/api/tasks/t/documents":
            return respond(route, {"items": [doc], "total": 1, "page": 1, "page_size": 20})
        if path == "/api/tasks/t/documents/doc":
            return respond(route, doc)
        if path == "/api/batches/b/documents/doc/revisions":
            return respond(route, {"document_id": "doc", "html": '<p><del data-rev="1">旧文</del><ins data-rev="2">新文</ins></p>',
                                   "revisions": [{"del_id": 1, "ins_id": 2, "index": 1, "operation": "replace",
                                                  "before": "旧文", "after": "新文"}],
                                   "selection_epoch": 0, "manifest_hash": "a" * 64,
                                   "download_url": "/api/batches/b/documents/doc/download/selected_final"})
        if path == "/api/batches/b/documents/doc/decisions":
            bodies.append(json.loads(route.request.post_data or "{}"))
            return respond(route, {"document_id": "doc", "accepted": [1], "rejected": [], "sha256": "b" * 64,
                                   "selection_epoch": 1, "manifest_hash": "c" * 64,
                                   "download_url": "/api/batches/b/documents/doc/download/selected_final"})
        if path == "/api/tasks/t/report":
            return respond(route, {"delivery_status": "incomplete", "qualification_status": "eligible", "actions": []})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#document?id=t&document=doc&tab=review")
        page.locator('[data-action="generate-selected"]').wait_for()
        panel = page.locator("#detail-panel").bounding_box()
        assert panel and panel["x"] >= 10 and panel["y"] >= 10
        assert panel["width"] <= 1430 and panel["height"] <= 990
        assert page.locator("#detail-overlay").is_visible()
        page.locator('[data-action="generate-selected"]').click()
        page.locator("#review-message").filter(has_text="已生成").wait_for()
        assert bodies[0]["selection_epoch"] == 0 and bodies[0]["manifest_hash"] == "a" * 64

        page.locator('[data-action="generate-selected"]').click()
        page.wait_for_timeout(300)
        assert len(bodies) >= 2
        assert bodies[1]["selection_epoch"] == 1 and bodies[1]["manifest_hash"] == "c" * 64
    finally:
        context.close()


def test_v1_password_late_401_from_previous_account_does_not_logout_new_session(browser, live_password):
    _app, base = live_password
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    held: list = []

    def binding(route):
        held.append(route)

    page.route("**/api/integrations/feishu/binding", binding)
    try:
        page.goto(base + "/", wait_until="networkidle")
        page.locator("#login-username").fill("frontend-a")
        page.locator("#login-password").fill("frontend-a-password")
        page.locator("#login-submit").click()
        page.locator("#topbar-user").wait_for(state="visible")
        page.locator('.sidebar [data-nav="settings"]').click()
        deadline = time.monotonic() + 5
        while not held and time.monotonic() < deadline:
            page.wait_for_timeout(50)
        assert held

        page.locator("#logout-btn").click()
        page.locator("#login-username").wait_for(state="visible")
        page.locator("#login-username").fill("frontend-b")
        page.locator("#login-password").fill("frontend-b-password")
        page.locator("#login-submit").click()
        page.locator("#topbar-user").wait_for(state="visible")
        token_b = page.evaluate("() => sessionStorage.getItem('fundlex-auth-token')")
        assert token_b

        respond(held.pop(0), {"detail": "AUTHENTICATION_REQUIRED"}, status=401)
        page.wait_for_timeout(500)
        assert page.evaluate("() => sessionStorage.getItem('fundlex-auth-token')") == token_b
        assert page.locator("#login-view").is_hidden()
        assert page.locator("#topbar-user").is_visible()
    finally:
        context.close()


def test_compare_failed_pair_shows_structured_failure_diagnostics(browser, live_dev):
    """FL-D546: terminal pair failures surface stage/type/retryability from the
    worker diagnostics field; paused pairs keep the same status label source."""
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-diagnostics')")
    page = context.new_page()
    pairs = [
        {"id": "PF", "label": "失败组", "status": "failed", "error_code": "COMPARE_PROCESSING_FAILED",
         "left": {"name": "a.docx"}, "right": {"name": "b.docx"},
         "diagnostics": {"failure": {"error_code": "COMPARE_PROCESSING_FAILED", "stage": "compare",
                                      "error_type": "RuntimeError", "retryable": False}}},
        {"id": "PP", "label": "暂停组", "status": "paused",
         "left": {"name": "c.docx"}, "right": {"name": "d.docx"}},
    ]

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [{"id": "T", "name": "diag", "status": "completed", "total": 2,
                                              "pairs": pairs}]})
        if path == "/api/compare/tasks/T":
            return respond(route, {"id": "T", "name": "diag", "status": "completed", "total": 2,
                                   "pairs": pairs})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T")
        error = page.locator(".compare-pair-status.is-failed .compare-pair-error")
        error.wait_for()
        assert error.inner_text() == "处理失败：文本比对环节出错，请重新创建合同组"
        paused = page.locator(".compare-pair-status", has_text="暂停组")
        assert paused.locator(".compare-pair-state").inner_text().startswith("已暂停")
        assert page.locator(".compare-pair-status.is-failed .compare-pair-state").inner_text() == "失败"
    finally:
        context.close()


def test_compare_selection_save_generate_download_restore_and_stale_version(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-selection')")
    page = context.new_page()
    current = {"decisions": {"D1": "pending", "D2": "pending"}, "epoch": 0, "versions": []}
    diffs = [
        {"id": "D1", "type": "modify", "section": "费率", "left": {"text": "0.40%", "block_id": "b1"},
         "right": {"text": "0.35%", "block_id": "b1"}},
        {"id": "D2", "type": "modify", "section": "期限", "left": {"text": "30 天", "block_id": "b2"},
         "right": {"text": "365 天", "block_id": "b2"}},
    ]

    def selection_payload():
        pending = [key for key, value in current["decisions"].items() if value == "pending"]
        return {"pair_id": "P1", "result_sha256": "a" * 64, "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                "selection_epoch": current["epoch"],
                "draft": {"selection_epoch": current["epoch"], "decisions": dict(current["decisions"]),
                          "decision_hash": ("d" if current["epoch"] == 0 else "e") * 64},
                "decisions": dict(current["decisions"]),
                "assessment": {"pending_ids": pending, "issues": [], "can_generate": not pending},
                "diffs": diffs, "artifacts": current["versions"]}

    def view_payload():
        return {"pair": {"id": "P1", "label": "P1"}, "result_sha256": "a" * 64,
                "left": {"name": "left.docx", "html": '<p data-block-id="b1"><mark data-diff-id="D1">0.40%</mark></p><p data-block-id="b2"><mark data-diff-id="D2">30 天</mark></p>'},
                "right": {"name": "right.docx", "html": '<p data-block-id="b1"><mark data-diff-id="D1">0.35%</mark></p><p data-block-id="b2"><mark data-diff-id="D2">365 天</mark></p>'},
                "summary": {"total": 2, "modify": 2, "insert": 0, "delete": 0}, "coverage": {"status": "complete"},
                "diffs": diffs}

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [{"id": "T", "name": "selection", "status": "succeeded", "total": 1,
                                              "pairs": [{"id": "P1", "label": "P1", "status": "succeeded",
                                                         "left": {"name": "left.docx"}, "right": {"name": "right.docx"},
                                                         "summary": {"total": 2}}]}]})
        if path == "/api/compare/tasks/T":
            return respond(route, {"id": "T", "name": "selection", "status": "succeeded", "total": 1,
                                   "pairs": [{"id": "P1", "label": "P1", "status": "succeeded",
                                              "left": {"name": "left.docx"}, "right": {"name": "right.docx"},
                                              "summary": {"total": 2}}]})
        if path == "/api/compare/pairs/P1/view":
            return respond(route, view_payload())
        if path == "/api/compare/pairs/P1/selection":
            if route.request.method == "PUT":
                body = json.loads(route.request.post_data or "{}")
                changed = any(current["decisions"].get(key) != value for key, value in body.get("decisions", {}).items())
                current["decisions"] = dict(body.get("decisions", {}))
                if changed:
                    current["epoch"] += 1
                    for version in current["versions"]:
                        version["stale"] = True
                        version["current"] = False
            return respond(route, selection_payload())
        if path == "/api/compare/pairs/P1/selection/generate":
            version = {"version": current["epoch"], "current": True, "stale": False,
                       "files": {"final": {"kind": "final", "sha256": "f" * 64, "size": 1200,
                                           "download_url": "/api/compare/pairs/P1/selection-artifacts/1/final"},
                                 "redline": {"kind": "redline", "sha256": "e" * 64, "size": 1300,
                                             "download_url": "/api/compare/pairs/P1/selection-artifacts/1/redline"}},
                       "report": {"version": current["epoch"]}}
            current["versions"] = [version]
            return respond(route, {"version": current["epoch"], "files": version["files"]})
        if "/selection-artifacts/" in path:
            return route.fulfill(status=200, body=b"PK" * 700, headers={
                "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "Content-Disposition": 'attachment; filename="selected-final.docx"'})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T&pair=P1")
        page.locator("#compare-selection-progress").filter(has_text="待选择 2").wait_for()
        page.locator('input[data-diff-id="D1"][value="right"]').check()
        page.locator("#compare-selection-status").filter(has_text="已保存").wait_for()
        page.locator('input[data-diff-id="D2"][value="right"]').check()
        page.locator("#compare-selection-generate").wait_for(state="visible")
        page.wait_for_function("!document.querySelector('#compare-selection-generate').disabled")
        page.locator("#compare-selection-generate").click()
        page.locator("#compare-selection-status").filter(has_text="已生成版本").wait_for()
        assert current["decisions"] == {"D1": "right", "D2": "right"}
        downloads = page.locator("[data-selection-download]")
        assert downloads.count() == 2
        with page.expect_download() as info:
            downloads.first.click()
        assert info.value.suggested_filename == "selected-final.docx"

        page.reload(wait_until="networkidle")
        page.locator("#compare-selection-progress").filter(has_text="已选择 2 / 2").wait_for()
        assert page.locator('input[data-diff-id="D1"][value="right"]').is_checked()
        generated_epoch = current["epoch"]
        assert f"· v{generated_epoch}" in page.locator("#compare-selection-downloads").inner_text()

        page.locator('input[data-diff-id="D1"][value="left"]').check()
        page.locator("#compare-selection-status").filter(has_text="已保存").wait_for()
        page.wait_for_function("document.querySelector('#compare-selection-downloads').textContent.includes('已过期')")
        assert current["epoch"] == generated_epoch + 1
    finally:
        context.close()


def test_compare_insert_delete_and_mixed_choices_still_generate(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','compare-structural')")
    page = context.new_page()
    decisions = {"D1": "pending", "D2": "pending", "D3": "pending"}
    diffs = [
        {"id": "D1", "type": "modify", "section": "正文", "left": {"text": "旧文", "block_id": "b1"}, "right": {"text": "新文", "block_id": "b1"}},
        {"id": "D2", "type": "insert", "section": "正文", "left": {"text": "", "block_id": "b2"}, "right": {"text": "新增整段", "block_id": "b2"}},
        {"id": "D3", "type": "delete", "section": "正文", "left": {"text": "删除整段", "block_id": "b3"}, "right": {"text": "", "block_id": "b3"}},
    ]

    def payload():
        pending = [key for key, value in decisions.items() if value == "pending"]
        return {"pair_id": "P1", "result_sha256": "a" * 64, "left_source_sha256": "b" * 64, "right_source_sha256": "c" * 64,
                "selection_epoch": 0, "draft": {"selection_epoch": 0, "decisions": dict(decisions), "decision_hash": "d" * 64},
                "decisions": dict(decisions), "assessment": {"pending_ids": pending, "issues": [], "can_generate": not pending},
                "diffs": diffs, "artifacts": []}

    def scenario(path, query, route):
        if path == "/api/compare/tasks/T":
            return respond(route, {"id": "T", "name": "structural", "status": "succeeded", "total": 1,
                                   "pairs": [{"id": "P1", "label": "P1", "status": "succeeded",
                                              "left": {"name": "left.docx"}, "right": {"name": "right.docx"}, "summary": {"total": 3}}]})
        if path == "/api/compare/pairs/P1/view":
            return respond(route, {"pair": {"id": "P1", "label": "P1"}, "result_sha256": "a" * 64,
                                   "left": {"name": "left.docx", "html": "<p data-block-id='b1'><mark data-diff-id='D1'>旧文</mark></p><p data-block-id='b3'><mark data-diff-id='D3'>删除整段</mark></p>"},
                                   "right": {"name": "right.docx", "html": "<p data-block-id='b1'><mark data-diff-id='D1'>新文</mark></p><p data-block-id='b2'><mark data-diff-id='D2'>新增整段</mark></p>"},
                                   "summary": {"total": 3, "modify": 1, "insert": 1, "delete": 1}, "coverage": {"status": "complete"},
                                   "diffs": diffs})
        if path == "/api/compare/pairs/P1/selection":
            if route.request.method == "PUT":
                body = json.loads(route.request.post_data or "{}")
                decisions.update(body.get("decisions", {}))
            return respond(route, payload())
        if path == "/api/compare/pairs/P1/selection/generate":
            return respond(route, {"version": 1})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T&pair=P1")
        page.locator("#compare-selection-progress").filter(has_text="待选择 3").wait_for()
        page.locator("#compare-selection-right-all").click()
        page.wait_for_function("document.querySelector('#compare-selection-progress').textContent.includes('待选择 0')")
        page.wait_for_function("!document.querySelector('#compare-selection-generate').disabled")
        assert page.locator("#compare-selection-issues").inner_text().strip() == ""
        page.locator("#compare-selection-generate").click()
        page.locator("#compare-selection-status").filter(has_text="已生成版本").wait_for()
    finally:
        context.close()
