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


@pytest.mark.parametrize('width', [390, 768, 1280, 1440])
def test_sibling_business_navigation_dashboard_and_separate_create_pages(browser, live, width):
    from playwright.sync_api import expect
    context = browser.new_context(viewport={'width': width, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(live, wait_until='networkidle')
        expect(page.locator('#view-workspace')).to_be_visible()
        expect(page.locator('#workspace-state')).to_contain_text('已更新任务列表')
        assert page.locator('.sidebar [data-nav="import"]').count() == 0
        assert page.locator('.sidebar [data-nav="task"]').count() == 0
        assert [n.inner_text() for n in page.locator('.sidebar .nav-btn').all()][:4] == ['工作台', '合同修改', '合同比对', '指引生成']
        page.locator('[data-workspace-new="compare"]').click()
        expect(page.locator('#compare-create')).to_be_visible()
        expect(page.locator('.compare-task-card')).to_be_hidden()
        assert '#compare?mode=new' in page.url
        page.reload(wait_until='networkidle')
        expect(page.locator('#compare-create')).to_be_visible()
        page.locator('#breadcrumb [data-crumb="compare"]').click()
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


@pytest.mark.parametrize('width', [390, 768, 1280, 1440])
def test_topbar_is_the_only_page_heading_and_mobile_location_stays_visible(browser, live, width):
    from playwright.sync_api import expect
    context = browser.new_context(viewport={'width': width, 'height': 1000})
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    routes = [
        ('workspace', '#workspace-state', '工作台'),
        ('overview', '#task-pagination', '合同修改'),
        ('import', '#submit-task', '合同修改›新建任务'),
        ('compare?mode=list', '#compare-new', '合同比对'),
        ('compare?mode=new', '#compare-submit', '合同比对›新建任务'),
        ('generation?mode=list', '#gg-filter', '指引生成'),
        ('generation?mode=new', '#gg-create', '指引生成›新建任务'),
        ('guide', '#guide-current-body', '修改指引'),
        ('settings', '#feishu-connect-card', '飞书绑定'),
    ]
    try:
        for fragment, ready, title in routes:
            page.goto(live + '/#' + fragment, wait_until='networkidle')
            expect(page.locator(ready)).to_be_visible()
            expect(page.locator('h1:visible')).to_have_count(1)
            expect(page.locator('.topbar #breadcrumb')).to_be_visible()
            expect(page.locator('.main #breadcrumb, .main h1:visible, .main .eyebrow:visible')).to_have_count(0)
            assert page.locator('#breadcrumb').inner_text().replace('\n', '').replace(' ', '') == title
            assert title.split('›')[-1] in page.title()
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            assert page.evaluate('''() => {
              const crumb=document.querySelector('#breadcrumb').getBoundingClientRect();
              const bar=document.querySelector('.topbar').getBoundingClientRect();
              const nav=document.querySelector('.sidebar').getBoundingClientRect();
              const current=document.querySelector('#breadcrumb [aria-current=page]').getBoundingClientRect();
              return crumb.height>0 && crumb.top>=bar.top && crumb.bottom<=bar.bottom+1 &&
                     current.right<=bar.right && nav.top>=bar.bottom-1;
            }''')
            if fragment == 'overview':
                expect(page.locator('#view-overview [data-action="new-task"]:visible')).to_have_count(1)
            if os.getenv('FUNDLEX_UX_EVIDENCE'):
                out = Path(os.environ['FUNDLEX_UX_EVIDENCE']); out.mkdir(parents=True, exist_ok=True)
                name = fragment.replace('?mode=', '-')
                page.screenshot(path=str(out / f'headers-{name}-{width}.png'))
        assert not errors
    finally:
        context.close()


@pytest.mark.parametrize('business', ['compare', 'generation'])
def test_topbar_parent_restores_list_query_after_deep_reload(browser, live, business):
    from playwright.sync_api import expect
    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto(live + f'/#{business}?mode=list&q=保持筛选&status=failed&page=2', wait_until='networkidle')
        page.locator('#compare-new' if business == 'compare' else '[data-gg-action="new"]').click()
        expect(page.locator('#breadcrumb [aria-current="page"]')).to_have_text('新建任务')
        page.reload(wait_until='networkidle')
        page.locator(f'#breadcrumb [data-crumb="{business}"]').click()
        expect(page.locator('#compare-search' if business == 'compare' else '#gg-query')).to_have_value('保持筛选')
        assert 'q=' in page.url and 'page=2' in page.url and 'status=failed' in page.url
        expect(page.locator('#breadcrumb [aria-current="page"]')).to_have_text('合同比对' if business == 'compare' else '指引生成')
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
