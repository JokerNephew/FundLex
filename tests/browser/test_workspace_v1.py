"""V1 sibling businesses, deep links and aggregate dashboard (no model calls)."""
from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.getenv('FUNDLEX_BROWSER_TESTS') != '1', reason='opt-in V1 Chromium')


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        instance = p.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def live(tmp_path, monkeypatch):
    import uvicorn
    monkeypatch.setenv('FUNDLEX_AUTH_MODE', 'dev')
    monkeypatch.setenv('FUNDLEX_FRONTEND_VERSION', 'v1')
    monkeypatch.setenv('FUNDLEX_DATA_DIR', str(tmp_path / 'default'))
    from fundlex.api import create_app
    app = create_app(tmp_path / 'data', auth_db=str(tmp_path / 'auth.sqlite3'))
    server = uvicorn.Server(uvicorn.Config(app, log_level='critical'))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    for _ in range(200):
        if server.started:
            break
        time.sleep(.02)
    assert server.started
    yield f'http://127.0.0.1:{sock.getsockname()[1]}'
    server.should_exit = True
    thread.join(timeout=10)
    sock.close()


@pytest.mark.parametrize('width', [390, 768, 1440])
def test_sibling_business_navigation_dashboard_and_separate_create_pages(browser, live, width):
    from playwright.sync_api import expect
    context = browser.new_context(viewport={'width': width, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(live, wait_until='networkidle')
        expect(page.locator('#view-workspace')).to_be_visible()
        expect(page.locator('#workspace-state')).to_contain_text('共 0 个匹配任务')
        assert page.locator('.sidebar [data-nav="import"]').count() == 0
        assert page.locator('.sidebar [data-nav="task"]').count() == 0
        assert [n.inner_text() for n in page.locator('.sidebar .nav-btn').all()][:4] == ['工作台', '合同修改', '合同比对', '指引生成']
        page.locator('[data-workspace-new="compare"]').click()
        expect(page.locator('#compare-create')).to_be_visible()
        expect(page.locator('.compare-task-card')).to_be_hidden()
        assert '#compare?mode=new' in page.url
        page.reload(wait_until='networkidle')
        expect(page.locator('#compare-create')).to_be_visible()
        page.locator('#compare-back-bar [data-nav="compare"]').click()
        expect(page.locator('.compare-task-card')).to_be_visible()
        expect(page.locator('#compare-create')).to_be_hidden()
        page.locator('.sidebar [data-nav="overview"]').click()
        expect(page.locator('#view-overview')).to_be_visible()
        page.locator('#view-overview [data-action="new-task"]').first.click()
        expect(page.locator('#view-import')).to_be_visible()
        expect(page.locator('.sidebar [data-nav="overview"]')).to_have_attribute('aria-current', 'page')
        page.locator('[data-nav="workspace"]').last.click()
        page.locator('[data-workspace-new="generation"]').click()
        expect(page.locator('#view-generation')).to_be_visible()
        assert 'mode=new' in page.url
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if os.getenv('FUNDLEX_UX_EVIDENCE'):
            out = Path(os.environ['FUNDLEX_UX_EVIDENCE']);out.mkdir(parents=True, exist_ok=True)
            page.locator('.sidebar [data-nav="workspace"]').click()
            page.screenshot(path=str(out / f'workspace-{width}.png'))
        assert not errors
    finally:
        context.close()


def test_workspace_filter_query_pagination_and_identity_reset(browser, live):
    from playwright.sync_api import expect
    context = browser.new_context()
    page = context.new_page()
    requests = []

    def aggregate(route):
        requests.append(route.request.url)
        route.fulfill(json={'items': [], 'total': 45, 'page': int(route.request.url.split('page=')[-1].split('&')[0]) if 'page=' in route.request.url else 1,
                            'page_size': 20, 'stats': {'active': 5, 'attention': 8, 'recent_completed': 12}})

    page.route('**/api/workspace/tasks?*', aggregate)
    try:
        page.goto(live, wait_until='networkidle')
        expect(page.locator('#workspace-active')).to_have_text('5')
        page.locator('[data-workspace-kind="compare"]').click()
        page.locator('#workspace-search').fill('合同')
        expect(page).to_have_url(__import__('re').compile('.*q=.*'))
        page.locator('#workspace-pagination [data-workspace-page="2"]').click()
        expect(page).to_have_url(__import__('re').compile('.*page=2.*'))
        page.reload(wait_until='networkidle')
        expect(page.locator('#workspace-search')).to_have_value('合同')
        expect(page.locator('[data-workspace-kind="compare"]')).to_have_attribute('aria-pressed', 'true')
        page.evaluate("document.dispatchEvent(new Event('fundlex:identity-reset'))")
        expect(page.locator('#workspace-active')).to_have_text('—')
        assert requests
    finally:
        context.close()
