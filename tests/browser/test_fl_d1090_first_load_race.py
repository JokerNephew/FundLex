"""FL-D1090 回归（修复=b17e516/FL-D1039 同域）：任务列表首载失败的错误空态
不得被并行的 loadTaskGuides 成功路径改写为空账号空态。

场景：/api/tasks 首次 500 后恢复；/api/guides 正常 200。
断言：1.5s/2.5s/3.5s 三时点 task-rows 保持「任务暂未加载」、不出现「没有任务」；
随后手动重试成功时正常渲染空账号文案（修刀不误伤）。
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                                reason="opt-in V1 Chromium suite")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=os.getenv("FUNDLEX_BROWSER_HEADLESS", "1") != "0")
        yield instance
        instance.close()


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


def respond(route, body, status=200):
    route.fulfill(status=status, content_type="application/json",
                  body=json.dumps(body, ensure_ascii=False))


def test_first_load_failure_empty_state_not_overwritten(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','d1090-probe')")
    page = context.new_page()
    calls = {"tasks": 0}

    def dispatch(route):
        path = route.request.url.split("://", 1)[1].split("/", 1)[-1].split("?")[0]
        full = "/" + path if not path.startswith("/") else path
        if not full.startswith("/api/"):
            return route.continue_()
        if full == "/api/tasks":
            calls["tasks"] += 1
            if calls["tasks"] == 1:
                return respond(route, {"detail": "pump"}, status=500)
            return respond(route, {"items": [], "total": 0, "page": 1, "page_size": 20})
        return route.continue_()

    page.route("**/api/**", dispatch)
    try:
        page.goto(base + "/#overview", wait_until="networkidle")
        for elapsed_ms in (1500, 2500, 3500):
            page.wait_for_timeout(1000)
            rows = page.locator("#task-rows").inner_text()
            assert "任务暂未加载" in rows, f"t={elapsed_ms}ms 错误空态丢失：{rows[:60]}"
            assert "没有任务" not in rows, f"t={elapsed_ms}ms 空账号文案覆盖错误态（FL-D1090 复现）"
        # 修刀不误伤：重试成功后空账号文案可正常出现
        page.locator('[data-action="task-retry"], #task-refresh, [data-refresh]').first.click() \
            if page.locator('[data-action="task-retry"], #task-refresh, [data-refresh]').count() else \
            page.evaluate("location.reload()")
        page.wait_for_timeout(2000)
        rows = page.locator("#task-rows").inner_text()
        assert "当前条件下没有任务" in rows or "任务暂未加载" not in rows, rows[:60]
    finally:
        context.close()
