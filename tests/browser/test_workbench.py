"""UI/API regression fixtures. No Worker, model calls, or contract-engine acceptance.

Opt in with FUNDLEX_BROWSER_TESTS=1; requires Playwright and its Chromium browser.
Reports/revision views used for presentation tests are explicit UI fixtures.
"""
from __future__ import annotations

import io
import json
import os
import re
import socket
import threading
import time
import uuid
from pathlib import Path

import pytest

# V1 is the default workbench; V2 retains its own explicit opt-in coverage.
pytestmark = pytest.mark.skipif(
    os.getenv("FUNDLEX_BROWSER_TESTS") != "1" and os.getenv("FUNDLEX_LEGACY_BROWSER_TESTS") != "1",
    reason="opt-in V1 workbench suite")


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


def open_page(ui, view="overview"):
    page, _, _, base = ui
    page.goto(base + "/#" + view)
    page.wait_for_function("document.querySelector('#upload-limit').textContent.includes('MiB')")
    return page


def docx_bytes():
    from docx import Document
    stream = io.BytesIO()
    doc = Document()
    doc.add_paragraph("前后端接口测试合同，非引擎业务验收。")
    doc.save(stream)
    return stream.getvalue()


def seed(ui, count=1, states=None, name="交互测试任务", report=None):
    _, context, app, base = ui
    data = docx_bytes()
    files = [{"client_id": f"c{i}", "name": f"合同{i}.docx", "size": len(data)} for i in range(count)]
    headers = {"X-FundLex-User": "browser-check"}
    response = context.request.post(base + "/api/tasks", headers=headers,
                                    data={"name": name, "engine_id": "recall_first", "files": files})
    assert response.ok, response.text()
    task = response.json()["id"]
    for entry in files:
        response = context.request.post(base + f"/api/tasks/{task}/uploads", headers=headers,
            multipart={"client_ids": json.dumps([entry["client_id"]]),
                       "files": {"name": entry["name"], "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "buffer": data}})
        assert response.ok, response.text()
    docs = context.request.get(base + f"/api/tasks/{task}/documents", headers=headers).json()["items"]
    if states or report:
        with app.state.store._connect() as db:
            for index, doc in enumerate(docs):
                status, qualification, delivery = states[index] if states else ("succeeded", "eligible", "incomplete")
                now = time.time()
                db.execute("UPDATE documents SET status=?,qualification_status=?,delivery_status=?,"
                           "started_at=?,finished_at=?,report_json=? WHERE id=?",
                           (status, qualification, delivery, now-90, now, json.dumps(report) if report else None, doc["document_id"]))
    return task, docs


def open_task(ui, task):
    page = open_page(ui)
    page.locator(f'#task-rows [data-task="{task}"]').click()
    page.wait_for_selector("#doc-rows [data-detail]")
    return page


def test_verification_blocked_report_explains_waiting_without_business_residual(ui):
    report = {"qualification_status": "eligible", "delivery_status": "not_generated",
              "verification_status": "verification_blocked", "unresolved": [],
              "verification_blockers": [{"code": "MODEL_REPLAY_MISS", "stage": "audit"}]}
    task, _ = seed(ui, states=[("retry_wait", "eligible", "not_generated")], report=report)
    page = open_task(ui, task)
    page.locator("#doc-rows [data-detail]").first.click()
    page.get_by_role("heading", name="验证暂未完成，等待恢复处理").wait_for()
    assert page.locator("#detail-body").get_by_text("当前文件尚未通过最终交付校验。", exact=False).is_visible()
    assert page.get_by_role("button", name="最终版 DOCX", exact=True).count() == 0


def presentation(ui, count=1, execution_mode="", summary=False, delivery="incomplete"):
    if execution_mode == "evaluation":
        delivery = "evaluation_modified"
    report = {"qualification_status": "eligible", "delivery_status": delivery,
              "guide": {"groups": [{"rule_id": "G01", "title": "已规划条款"}, {"rule_id": "G02", "title": "未执行条款"}]},
              "targets": [{"target_id": "T1", "rule_id": "G01", "state": "needs_edit", "quote": "原文"},
                          {"target_id": "T2", "rule_id": "G02", "state": "needs_edit", "quote": "未改原文"}],
              "plan": {"edits": [{"target_id": "T1", "rule_id": "G01", "operation": "replace", "replacement": "完整联合改文", "components": [{"target_id": "T1", "expected_old_text": "原文", "replacement": "首片段"}, {"target_id": "T3", "replacement": "次片段"}]}]}}
    if summary:
        report["user_summary"] = {"headline": "有一项条款需要人工核对", "issues": [{"rule_id": "G02", "business_reason": "未找到可安全修改的正文位置"}]}
    task, docs = seed(ui, count, states=[("succeeded", "eligible", delivery)] * count, report=report)
    page, context, _, _ = ui
    def documents(route):
        response = route.fetch()
        payload = response.json()
        if 'items' not in payload and 'document_id' not in payload:
            return route.fulfill(response=response)
        for doc in payload.get("items", [payload]):
            doc["downloads"] = {"working_redline": "/api/ui-fixture/redline", "selected_final": "/api/ui-fixture/selected"}
            doc["review_url"] = "/api/ui-fixture/revisions/" + doc["document_id"]
            if execution_mode:
                doc["execution_mode"] = execution_mode
            if delivery == "complete_with_exceptions":
                doc["downloads"] = {"redline": "/api/ui-fixture/redline", "final": "/api/ui-fixture/final"}
        route.fulfill(status=response.status, json=payload)
    context.route(f"**/api/tasks/{task}/documents?*", documents)
    context.route(f"**/api/tasks/{task}/documents/*", documents)
    revisions = {"html": '<p><del class="rev rev-del" data-rev="1">原文</del><ins class="rev rev-ins" data-rev="2">改文</ins></p><p><ins class="rev rev-ins" data-rev="4">新增句</ins></p>',
                 "revisions": [{"index": 1, "del_id": 1, "ins_id": 2, "revision_ids": [1, 2], "before": "原文", "after": "改文", "operation": "replace"},
                               {"index": 2, "del_id": 4, "ins_id": 5, "revision_ids": [4], "before": "", "after": "新增句", "operation": "insert"}]}
    context.route("**/api/ui-fixture/revisions/*", lambda route: route.fulfill(json=revisions))
    open_task(ui, task)
    page.locator("#doc-rows [data-detail]").first.click()
    page.wait_for_selector("#detail-body .result-summary")
    return task, docs, revisions


@pytest.mark.parametrize('width', [390, 768, 1280, 1440])
def test_object_heading_long_parent_and_deep_link_return(ui, width):
    from playwright.sync_api import expect
    page, _, _, base = ui
    name = '标题与长任务名称验证' * 12
    task, docs = seed(ui, name=name)
    page.set_viewport_size({'width': width, 'height': 1000})
    page.goto(base + f'/#task?id={task}', wait_until='networkidle')
    expect(page.locator('#task-object-title')).to_have_text(name)
    expect(page.locator('h1:visible')).to_have_count(1)
    expect(page.locator('#breadcrumb [aria-current="page"]')).to_have_text('任务详情')
    page.locator('#doc-rows [data-detail]').first.click()
    expect(page.locator('#detail-title')).to_have_text(docs[0]['name'])
    page.reload(wait_until='networkidle')
    expect(page.locator('#detail-title')).to_have_text(docs[0]['name'])
    expect(page.locator('h1:visible')).to_have_count(1)
    parent = page.locator('#breadcrumb [data-crumb="task"]')
    expect(parent).to_have_attribute('title', name)
    assert name not in page.locator('#breadcrumb [aria-current="page"]').inner_text()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert page.evaluate('''() => {
      const leaf=document.querySelector('#breadcrumb [aria-current=page]').getBoundingClientRect();
      const nav=document.querySelector('#breadcrumb').getBoundingClientRect();
      return leaf.left>=nav.left && leaf.right<=nav.right+1;
    }''')
    if os.getenv('FUNDLEX_UX_EVIDENCE'):
        out = Path(os.environ['FUNDLEX_UX_EVIDENCE']); out.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(out / f'headers-document-{width}.png'))
    parent.click()
    expect(page.locator('#view-task')).to_be_visible()
    expect(page.locator('#task-object-title')).to_have_text(name)
    assert page.url.endswith(f'#task?id={task}')


def test_overview_units_filters_and_single_supported_mode(ui):
    task, _ = seed(ui, states=[("succeeded", "eligible", "complete")])
    page = open_page(ui)
    page.wait_for_function("document.querySelector('#overview-average').textContent==='90'")
    assert "90 秒 秒" not in page.inner_text("#overview-description")
    page.fill("#task-search", "不存在的筛选")
    page.wait_for_function("document.querySelector('#task-rows').textContent.includes('没有任务')")
    assert page.locator("#first-run-guide").is_hidden()
    page.locator('#view-overview [data-action="new-task"]').first.click()
    assert page.locator("#import-mode option").count() == 1
    assert page.locator("#import-mode").is_disabled()
    assert page.locator("#import-mode").inner_text() == "合同修订"


def test_revision_task_columns_detail_metadata_and_responsive_layout(ui):
    task, _ = seed(ui, count=2, name="布局检查任务")
    seed(ui, name="A排序任务")
    page, context, _, base = ui
    headers = {"X-FundLex-User": "browser-check"}
    task_data = context.request.get(base + f"/api/tasks/{task}", headers=headers).json()
    guide_id = task_data["guide_snapshot"]["version_id"]
    guides = context.request.get(base + "/api/guides", headers=headers).json()["items"]
    guide = next(item for item in guides if item["id"] == guide_id)

    # Open by task route rather than entering through the list: the guide label
    # must resolve even when overview never loaded the guide catalogue first.
    page.goto(base + f"/#task?id={task}")
    page.wait_for_selector("#doc-rows [data-detail]")
    page.wait_for_function("!document.querySelector('#task-guide-meta').hidden")
    # FL-D717 定稿文案：任务绑定指引快照后显示「文件名 · 已锁定」（不直显 version_id）
    assert page.locator("#task-guide-value").inner_text() == f"{guide['filename']} · 已锁定"

    page.goto(base + "/#overview")
    row = page.locator(f'#task-rows tr:has([data-task="{task}"])')
    row.wait_for()
    page.fill("#task-search", "布局检查任务")
    page.wait_for_function("document.querySelectorAll('#task-rows tr[data-row-key]').length===1")
    page.fill("#task-search", "")
    page.wait_for_function("document.querySelectorAll('#task-rows tr[data-row-key]').length===2")
    page.select_option("#task-sort", "name")
    page.wait_for_function("document.querySelector('#task-rows tr[data-row-key] .task-list-name')?.textContent==='A排序任务'")
    assert page.locator("#task-rows .task-list-name").all_text_contents() == ["A排序任务", "布局检查任务"]
    assert [text.strip() for text in page.locator("#view-overview .task-list-table th").all_text_contents()] == [
        "任务", "合同份数", "成功 / 异常", "状态", "进度", "创建时间", ""
    ]
    assert row.locator("td").count() == 7
    assert row.locator("td").nth(0).locator("small, .row-sub").count() == 0
    assert row.locator("td").nth(5).inner_text().strip()
    assert guide["filename"] not in row.inner_text()

    for width in (390, 768, 1280, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        layout = page.evaluate("""() => {
          const wrap = document.querySelector('#view-overview .task-list-table').parentElement;
          const table = wrap.querySelector('table');
          const cells = [...document.querySelector('#task-rows tr').cells].map(cell => {
            const rect = cell.getBoundingClientRect();
            return {left: rect.left, right: rect.right};
          });
          return {width: innerWidth, pageWidth: document.documentElement.scrollWidth,
            left: wrap.getBoundingClientRect().left, right: wrap.getBoundingClientRect().right,
            clientWidth: wrap.clientWidth, tableWidth: table.scrollWidth, cells};
        }""")
        assert layout["pageWidth"] <= width + 1
        assert layout["left"] >= -1 and layout["right"] <= width + 1
        assert layout["tableWidth"] >= layout["clientWidth"]
        assert all(layout["cells"][i]["left"] >= layout["cells"][i - 1]["right"] - 1
                   for i in range(1, len(layout["cells"])))

    row.locator("[data-task]").click()
    page.wait_for_selector("#doc-rows [data-detail]")
    assert page.locator("#result-counts, #doc-scope, #doc-scope-note").count() == 0
    assert page.locator("#doc-rows .row-sub").count() == 0
    assert "本次交付" not in page.inner_text("#view-task")
    assert " · 匹配 " not in page.inner_text("#view-task")

    for width in (390, 768, 1280, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        layout = page.evaluate("""() => {
          const actions = document.querySelector('.task-detail-actions');
          const card = actions.closest('.card').getBoundingClientRect();
          const buttons = [...actions.querySelectorAll('.btn')].map(button => {
            const rect = button.getBoundingClientRect();
            return {left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom};
          });
          const guide = document.querySelector('#task-guide-meta strong');
          return {width: innerWidth, pageWidth: document.documentElement.scrollWidth,
            cardLeft: card.left, cardRight: card.right,
            actionsLeft: actions.getBoundingClientRect().left,
            actionsRight: actions.getBoundingClientRect().right,
            buttons, guideWidth: guide.clientWidth, guideScrollWidth: guide.scrollWidth};
        }""")
        assert layout["pageWidth"] <= width + 1
        assert layout["actionsLeft"] >= layout["cardLeft"] - 1
        assert layout["actionsRight"] <= layout["cardRight"] + 1
        assert layout["guideScrollWidth"] <= layout["guideWidth"] + 1
        for i, first in enumerate(layout["buttons"]):
            assert first["left"] >= layout["cardLeft"] - 1
            assert first["right"] <= layout["cardRight"] + 1
            for second in layout["buttons"][i + 1:]:
                overlap_x = min(first["right"], second["right"]) - max(first["left"], second["left"])
                overlap_y = min(first["bottom"], second["bottom"]) - max(first["top"], second["top"])
                assert overlap_x <= 0 or overlap_y <= 0


def test_delivery_counts_and_worker_filter_match_api(ui):
    states = [("succeeded", "eligible", "complete"), ("succeeded", "eligible", "incomplete"),
              ("failed", "failed", "incomplete"), ("succeeded", "excluded_by_fund_type", "not_generated"),
              ("leased", "pending", "not_generated")]
    task, _ = seed(ui, 5, states)
    page = open_page(ui)
    row = page.locator(f'#task-rows tr:has([data-task="{task}"])')
    assert row.locator(".task-success").inner_text() == "1"
    assert row.locator(".task-error").inner_text() == "2"
    assert "份合同" not in row.inner_text()
    assert "成功 / 异常" not in row.inner_text()
    assert row.locator(".p-excluded").count() == 1
    row.locator("[data-task]").click()
    assert page.locator("#task-ruleset").count() == 0
    page.select_option("#doc-completeness-filter", "not_generated")
    page.wait_for_function("document.querySelectorAll('#doc-rows [data-detail]').length===2")
    excluded = page.locator("#doc-rows tr", has_text="合同3.docx")
    assert excluded.get_attribute("class") != "row-exception"
    page.select_option("#doc-completeness-filter", "")
    page.select_option("#doc-status-filter", "running")
    page.wait_for_function("document.querySelectorAll('#doc-rows [data-detail]').length===1")
    assert "处理中" in page.inner_text("#doc-rows")
    assert "合同4.docx" in page.inner_text("#doc-rows")


def test_report_does_not_mark_unexecuted_targets_applied(ui):
    presentation(ui)
    page = ui[0]
    row = page.locator('.action-evidence', has_text="未执行条款")
    assert "待修改" in row.inner_text()
    assert "已修改" not in row.inner_text()
    assert "完整联合改文" in page.locator("#detail-body").text_content()
    assert "首片段" not in page.locator("#detail-body").text_content()
    assert "工作文件（未完成）" in page.locator('[data-download="selected_final"]').inner_text()


def test_report_shows_incomplete_business_issues(ui):
    presentation(ui, summary=True)
    page = ui[0]
    assert "仍需人工核对 · 1 项" in page.inner_text("#detail-body")
    assert "未执行条款" in page.inner_text("#detail-body")
    assert "未改原文" in page.inner_text("#detail-body")
    assert "未找到可安全修改的正文位置" in page.inner_text("#detail-body")


def test_evaluation_result_hides_formal_review_entry(ui):
    presentation(ui, execution_mode="evaluation")
    page = ui[0]
    assert not page.locator('[data-action="open-review"]').count()
    assert "评测文件不能作为正式合同" in page.inner_text("#detail-body")
    assert page.locator("#overall-progress .p-evaluation").evaluate("n=>n.style.width") == "100%"
    assert page.locator("#progress-evaluation-legend").get_attribute('hidden') is None
    assert page.locator('#view-document').is_visible()


def test_exception_delivery_remains_downloadable_without_direct_use_claim(ui):
    presentation(ui, delivery="complete_with_exceptions")
    page = ui[0]
    conclusion = page.locator("#detail-body .result-summary")
    assert "需核对例外" in conclusion.inner_text()
    assert "已通过交付校验" not in conclusion.inner_text()
    assert page.locator('[data-download="final"]').is_visible()
    assert "按例外清单人工核对" in page.inner_text("#detail-body")


@pytest.mark.parametrize('width', [390, 768, 1280, 1440])
@pytest.mark.parametrize('delivery', ['incomplete', 'complete_with_exceptions', 'evaluation_modified'])
def test_contract_result_compact_summary_actions_and_folded_evidence(ui, width, delivery):
    from playwright.sync_api import expect
    page = ui[0]
    page.set_viewport_size({'width': width, 'height': 1000})
    presentation(ui, delivery=delivery, execution_mode='evaluation' if delivery.startswith('evaluation') else '')
    expect(page.locator('.result-summary')).to_be_visible()
    expect(page.locator('.result-status-grid>div')).to_have_count(3)
    expect(page.locator('.result-evidence')).not_to_have_attribute('open', '')
    expect(page.locator('.result-evidence .detail-grid')).to_be_hidden()
    assert page.locator('.result-summary').bounding_box()['height'] < (320 if width == 390 else 230)
    boxes = [node.bounding_box() for node in page.locator('.result-status-grid>div').all()]
    assert max(box['y'] for box in boxes) - min(box['y'] for box in boxes) < 2
    if delivery == 'complete_with_exceptions':
        expect(page.locator('[data-download="final"]')).to_be_visible()
        expect(page.locator('.result-summary')).to_contain_text('需核对例外')
    elif delivery.startswith('evaluation'):
        expect(page.locator('.result-summary')).to_contain_text('评测文件不能作为正式合同')
        expect(page.locator('[data-action="open-review"]')).to_have_count(0)
    else:
        expect(page.locator('.result-summary')).to_contain_text('结果不完整')
        expect(page.locator('[data-action="open-review"]')).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    if os.getenv('FUNDLEX_UX_EVIDENCE'):
        out=Path(os.environ['FUNDLEX_UX_EVIDENCE']);out.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(out / f'result-{delivery}-{width}.png'))
    page.locator('.result-evidence>summary').click()
    expect(page.locator('.result-evidence .detail-grid')).to_be_visible()


@pytest.mark.parametrize('view', ['overview', 'task'])
def test_repeated_slow_refresh_keeps_rows_focus_and_recovers_after_error(ui, view):
    from playwright.sync_api import expect
    page, context, _, _ = ui
    task, _ = seed(ui)
    open_task(ui, task) if view == 'task' else open_page(ui)
    row_id = 'doc-rows' if view == 'task' else 'task-rows'
    expect(page.locator(f'#{row_id} tr[data-row-key]')).to_have_count(1)
    pending=[]
    if view == 'task':
        context.route(f'**/api/tasks/{task}/documents?*', lambda route: pending.append((route, route.fetch())))
    else:
        def hold_task_list(route):
            if 'sort=newest' in route.request.url:
                pending.append((route, route.fetch()))
            else:
                route.continue_()
        context.route('**/api/tasks?*', hold_task_list)
    page.evaluate('''id => {
      window.stableRow=document.querySelector('#'+id+' tr');
      window.stableAction=stableRow.querySelector('button');
      window.stableProgress=document.querySelector('#overall-progress .p-done');
      stableAction.focus();
    }''',row_id)
    for attempt in range(3):
        page.wait_for_timeout(10500)
        for _ in range(200):
            if pending:break
            page.wait_for_timeout(25)
        assert pending,'expected the actual ten-second background poll'
        assert page.evaluate('id=>getComputedStyle(document.getElementById(id)).opacity',row_id) == '1'
        assert page.evaluate('id=>stableRow===document.querySelector("#"+id+" tr") && stableAction.isConnected',row_id)
        if attempt == 1:
            requests=list(pending);pending.clear()
            for route,response in requests:
                route.fulfill(status=503,json={'detail':'temporary fixture failure'})
            expect(page.locator('#'+('doc' if view == 'task' else 'task')+'-refresh-note')).to_be_visible()
        else:
            requests=list(pending);pending.clear()
            for route,response in requests:
                payload=response.json()
                if attempt == 0:
                    if view == 'task':payload['items'][0]['job_status']='running'
                    else:payload['items'][0]['name']='后台静默更新任务'
                route.fulfill(status=response.status, json=payload)
            expect(page.locator(f'#{row_id}')).to_contain_text('正在处理' if view == 'task' and attempt == 0 else '后台静默更新任务' if attempt == 0 else '合同0.docx' if view == 'task' else '交互测试任务')
            expect(page.locator('#'+('doc' if view == 'task' else 'task')+'-refresh-note')).to_be_hidden() if attempt == 2 else None
        assert page.evaluate('stableAction.isConnected && document.activeElement===stableAction')
        assert page.evaluate('stableProgress===document.querySelector("#overall-progress .p-done")')


def test_guide_configuration_and_panels_do_not_expose_hashes(ui):
    from playwright.sync_api import expect
    page, context, _, base = ui
    page=open_page(ui,'guide')
    expect(page.locator('#guide-rows [data-guide-rules]')).not_to_have_count(0)
    versions=context.request.get(base+'/api/guides',headers={'X-FundLex-User':'browser-check'}).json()['items']
    hashes=[entry['rules_sha256'] for entry in versions if entry.get('rules_sha256')]
    assert hashes,'use a real hash-bearing guide fixture'
    # The merged V1 surfaces a short immutable marker; full hashes must not be
    # rendered as visible text (they remain available only via title attributes).
    for hash_value in hashes:assert hash_value not in page.locator('#view-guide').inner_text()
    for action in ['rules','issues']:
        page.locator(f'#guide-rows [data-guide-{action}]').first.click()
        expect(page.locator('#guide-overlay-body h3').first).to_have_text('指引信息')
        for hash_value in hashes:assert hash_value not in page.locator('#guide-overlay-body').inner_text()
        page.locator('#guide-overlay-close').click()


def test_guide_rule_switches_and_model_settings_are_editable(ui, monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv('FUNDLEX_MODEL_SECRETS_KEY', Fernet.generate_key().decode())
    from playwright.sync_api import expect
    page, context, _, base = ui
    page = open_page(ui, 'guide')
    rules_button = page.locator('#guide-rows [data-guide-rules]').first
    guide_id = rules_button.get_attribute('data-guide-rules')
    rules_button.click()
    expect(page.locator('#guide-overlay-body')).to_contain_text('规则组启停')
    toggle = page.locator('[data-guide-rule-toggle]').first
    toggle.uncheck()
    page.locator('[data-guide-rule-save]').click()
    page.wait_for_timeout(500)
    settings = context.request.get(
        base + f'/api/guides/{guide_id}/rule-settings',
        headers={'X-FundLex-User': 'browser-check'}).json()
    assert settings['disabled_rule_ids'], settings
    page.locator('#guide-overlay-close').click()

    page.locator('.sidebar [data-nav="models"]').click()
    expect(page.locator('#model-settings-card')).to_be_visible()
    expect(page.locator('#feishu-connect-card')).to_be_hidden()
    expect(page.locator('#model-settings-body')).to_contain_text('执行模型')
    expect(page.locator('#model-settings-body')).to_contain_text('检查模型')
    # 读取态不显示表单，点击「修改配置」进入编辑态（FL-D750 读取态/编辑态重做）
    expect(page.locator('#model-settings-form')).to_have_count(0)
    page.locator('[data-model-edit="primary"]').click()
    expect(page.locator('#model-settings-form')).to_be_visible()
    for label in ('超时', 'tokens', '重试次数', '上下文字符', 'JSON'):
        assert label not in page.locator('#model-settings-form').inner_text()
    page.locator('[data-model-role="primary"] [data-model-source-opt="personal"]').click()
    page.locator('#model-primary-provider').select_option('openai')
    page.locator('#model-primary-api_key').fill('browser-fixture-execution-key')
    page.locator('#model-primary-model').fill('personal-browser-model')
    with page.expect_response(lambda r: '/api/settings/model' in r.url and r.request.method == 'PUT') as saved:
        page.locator('[data-action="model-settings-save"][data-model-save="primary"]').click()
    assert saved.value.status == 200
    page.locator('[data-model-edit="review"]').click()
    page.locator('[data-model-role="review"] [data-model-source-opt="personal"]').click()
    page.locator('#model-review-provider').select_option('deepseek')
    page.locator('#model-review-api_key').fill('browser-fixture-review-key')
    page.locator('#model-review-model').fill('different-check-model')
    with page.expect_response(lambda r: '/api/settings/model' in r.url and r.request.method == 'PUT') as saved_review:
        page.locator('[data-action="model-settings-save"][data-model-save="review"]').click()
    assert saved_review.value.status == 200
    expect(page.locator('#model-settings-source')).to_have_text('我的模型配置')
    expect(page.locator('#model-settings-body')).to_contain_text('personal-browser-model')
    expect(page.locator('#model-settings-body')).to_contain_text('different-check-model')
    page.reload()
    page.locator('[data-model-edit="primary"]').click()
    expect(page.locator('#model-primary-model')).to_have_value('personal-browser-model')
    expect(page.locator('#model-primary-api_key')).to_have_value('')
    page.locator('[data-model-edit-cancel]').click()
    page.locator('[data-model-edit="review"]').click()
    expect(page.locator('#model-review-model')).to_have_value('different-check-model')
    expect(page.locator('#model-review-provider')).to_have_value('deepseek')
    expect(page.locator('#model-review-api_key')).to_have_value('')
    page.locator('[data-model-edit-cancel]').click()
    page.locator('[data-action="model-copy-primary"]').click()
    expect(page.locator('#model-review-model')).to_have_value('personal-browser-model')
    expect(page.locator('#model-review-provider')).to_have_value('openai')
    with page.expect_response(lambda r: '/api/settings/model' in r.url and r.request.method == 'PUT'):
        page.locator('[data-action="model-settings-save"][data-model-save="review"]').click()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('[data-action="model-settings-reset"][data-model-reset="primary"]').click()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('[data-action="model-settings-reset"][data-model-reset="review"]').click()
    expect(page.locator('#model-settings-source')).to_have_text('系统默认')


def test_model_and_feishu_pages_are_separate(ui):
    from playwright.sync_api import expect
    page, _, _, _ = ui
    requests = []
    page.on('request', lambda request: requests.append(request.url))
    open_page(ui, 'models')
    # 读取态为角色卡，无表单（FL-D750）；卡容器即模型页标识
    expect(page.locator('#model-settings-card')).to_be_visible()
    expect(page.locator('#model-settings-body')).to_contain_text('执行模型')
    expect(page.locator('#feishu-connect-card')).to_be_hidden()
    assert not any('/api/integrations/feishu/binding' in url for url in requests)
    page.reload()
    expect(page.locator('#model-settings-card')).to_be_visible()
    expect(page.locator('#feishu-connect-card')).to_be_hidden()
    requests.clear()
    page.locator('.sidebar [data-nav="settings"]').click()
    expect(page.locator('#feishu-connect-card')).to_be_visible()
    expect(page.locator('#model-settings-card')).to_be_hidden()
    expect(page.locator('#breadcrumb')).to_contain_text('飞书绑定')
    assert not any('/api/settings/model' in url for url in requests)


def test_model_connection_check_is_explicit_and_edit_invalidates_result(ui):
    from playwright.sync_api import expect
    page, context, _, _ = ui
    calls = []
    def fake_test(route):
        calls.append(route.request.post_data_json)
        route.fulfill(status=200, json={'ok': True, 'message': '连接正常，测试响应已收到。'})
    context.route('**/api/settings/model/test', fake_test)
    open_page(ui, 'models')
    # 读取态默认无表单（FL-D750）：未点击「验证连接」不得发起测试请求
    expect(page.locator('#model-settings-form')).to_have_count(0)
    assert not calls
    page.locator('[data-model-edit="primary"]').click()
    expect(page.locator('#model-settings-form')).to_be_visible()
    assert not calls
    page.locator('[data-model-role="primary"] [data-model-source-opt="personal"]').click()
    page.locator('#model-primary-model').fill('example-model')
    page.locator('#model-primary-api_key').fill('browser-fixture-test-key')
    page.locator('[data-model-test="primary"]').click()
    expect(page.locator('#model-primary-status')).to_contain_text('连接正常')
    assert len(calls) == 1
    page.locator('#model-primary-model').fill('another-model')
    expect(page.locator('#model-primary-status')).to_contain_text('尚未验证')
    assert len(calls) == 1


def test_revision_pair_checkbox_keyboard_and_insert_navigation(ui):
    presentation(ui)
    page = ui[0]
    page.locator('[data-action="open-review"]').click()
    page.wait_for_selector("#review-doc")
    page.locator('[data-rev-toggle="1"]').uncheck()
    assert page.locator('#review-doc [data-rev="1"]').evaluate("n=>n.classList.contains('rejected')")
    assert page.locator('#review-doc [data-rev="2"]').evaluate("n=>n.classList.contains('rejected')")
    page.locator('#review-doc [data-rev="2"]').click()
    page.keyboard.press("a")
    assert page.locator('[data-rev-toggle="1"]').is_checked()
    page.keyboard.press("r")
    assert not page.locator('[data-rev-toggle="1"]').is_checked()
    page.locator('#review-doc [data-rev="4"]').click()
    assert page.locator('[data-rev-item="4"]').evaluate("n=>n.classList.contains('active')")
    page.keyboard.press("r")
    assert not page.locator('[data-rev-toggle="4"]').is_checked()
    page.locator('[data-action="review-close"]').click()
    page.locator('[data-action="open-review"]').click()
    page.wait_for_selector("#review-doc")
    assert not page.locator('[data-rev-toggle="4"]').is_checked()
    page.locator('#breadcrumb [data-crumb="task"]').click()
    page.keyboard.press("a")
    assert page.locator("#detail-overlay").is_hidden()


def test_review_list_splitter_drag(ui):
    presentation(ui)
    page = ui[0]
    page.locator('[data-action="open-review"]').click()
    page.wait_for_selector("#review-doc")
    review_list = page.locator(".review-list")
    before = review_list.bounding_box()["width"]
    splitter = page.locator("#review-splitter")
    assert splitter.is_visible()
    grip = splitter.bounding_box()
    page.mouse.move(grip["x"] + 3, grip["y"] + min(220, grip["height"] / 2))
    page.mouse.down()
    page.mouse.move(grip["x"] - 57, grip["y"] + min(220, grip["height"] / 2), steps=5)
    page.mouse.up()
    page.wait_for_timeout(200)
    assert review_list.bounding_box()["width"] >= before + 20
    assert page.evaluate("Number(localStorage.getItem('fundlex-review-list-width'))") >= before + 20


def test_old_review_failure_cannot_overwrite_new_report(ui):
    _, _, _ = presentation(ui, 2)
    page, context, _, _ = ui
    pending = []
    context.route("**/api/ui-fixture/revisions/*", lambda route: pending.append(route))
    page.locator('[data-action="open-review"]').click()
    for _ in range(100):
        if pending:
            break
        page.wait_for_timeout(50)
    assert pending
    page.locator('#breadcrumb [data-crumb="task"]').click()
    page.locator("#doc-rows [data-detail]").nth(1).click()
    page.wait_for_selector('[data-action="open-review"]')
    pending[0].fulfill(status=503, json={"detail": "fixture failure"})
    page.wait_for_timeout(100)
    assert "业务结论" in page.inner_text("#detail-body")
    assert "无法生成合同呈现" not in page.inner_text("#detail-body")
    assert page.locator("#detail-title").inner_text() == "合同1.docx"


@pytest.mark.parametrize("hold", ["create", "uploads"])
def test_upload_completion_preserves_new_draft(ui, hold):
    page, context, _, _ = ui
    pending = []
    pattern = "**/api/tasks" if hold == "create" else "**/api/tasks/*/uploads"
    def intercept(route):
        if route.request.method != "POST":
            route.continue_()
            return
        pending.append((route, route.fetch()))
    context.route(pattern, intercept)
    open_page(ui, "import")
    page.fill("#task-name", "旧上传任务")
    page.set_input_files("#file-picker", {"name": "旧合同.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "buffer": docx_bytes()})
    page.locator("#submit-task").click()
    # Wait for the held network response, not a machine-speed-dependent 150ms.
    for _ in range(100):
        if pending:
            break
        page.wait_for_timeout(50)
    assert pending
    page.locator('.sidebar [data-nav="overview"]').click()
    page.locator('#view-overview [data-action="new-task"]').first.click()
    page.fill("#task-name", "新草稿不得覆盖")
    route, response = pending.pop()
    route.fulfill(response=response)
    page.wait_for_function("!document.querySelector('[data-action=choose-files]').disabled")
    assert page.locator("#task-name").input_value() == "新草稿不得覆盖"
    assert not page.locator("#task-name").is_disabled()
    assert page.locator("#cancel-recover").is_hidden()
    assert page.locator("#upload-progress").is_hidden()
    assert page.locator("#view-import").is_visible()
    page.set_input_files("#file-picker", {"name": "新合同.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "buffer": docx_bytes()})
    assert "新合同.docx" in page.inner_text("#import-rows")


def test_failed_guide_can_be_retried_from_page(ui):
    from fundlex import guide_store
    page, _, app, _ = ui
    version = guide_store.create_custom_version(app.state.store, "browser-check", "失败指引.docx", docx_bytes())
    for _ in range(guide_store.MAX_GUIDE_JOB_ATTEMPTS):
        job = guide_store.claim_guide_job(app.state.store)
        guide_store.finish_guide_job(app.state.store, job["id"], job["fencing_token"], error_code="GUIDE_PARSE_FAILED")
    open_page(ui, "guide")
    # 重新解析已收敛到指引详情弹层（FL-D753 行内操作收敛），先打开详情
    page.locator(f'[data-guide-issues="{version["id"]}"]').click()
    button = page.locator(f'#guide-overlay-body [data-guide-parse="{version["id"]}"]')
    assert button.is_enabled()
    button.click()
    page.wait_for_function("document.querySelector('#guide-rows').textContent.includes('待解析')")
    assert not page.locator("#toast").is_hidden()


def test_csv_download_contains_real_bom_and_rows(ui, tmp_path):
    task, _ = seed(ui)
    page = open_task(ui, task)
    with page.expect_download() as item:
        page.locator('[data-action="export-results"]').click()
    item.value.save_as(tmp_path / "results.csv")
    content = (tmp_path / "results.csv").read_bytes()
    assert content.startswith(b"\xef\xbb\xbf")
    text = content.decode("utf-8-sig")
    assert "\r\n" in text and "合同0.docx" in text
    assert "状态清单" in page.inner_text("#toast")


def test_login_expiry_message_and_role_hash_guard(ui, monkeypatch):
    page, context, app, base = ui
    password = uuid.uuid4().hex
    app.state.users.create_user("browsermember", password, "测试成员", "member")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    page.goto(base)
    page.wait_for_selector("#login-form", state="visible")
    page.fill("#login-username", "browsermember")
    page.fill("#login-password", "incorrect-password")
    page.locator("#login-submit").click()
    page.wait_for_selector("#login-error", state="visible")
    assert "用户名或密码不正确" in page.inner_text("#login-error")
    page.fill("#login-password", password)
    page.locator("#login-submit").click()
    page.wait_for_selector("#login-view", state="hidden")
    page.evaluate("location.hash='users'")
    page.wait_for_timeout(100)
    assert page.locator("#view-users").is_hidden()
    page.evaluate("location.hash='settings'")
    page.wait_for_timeout(100)
    # V1 settings is now the member-facing Feishu page, not dev-only settings.
    assert page.locator("#view-settings").is_visible()
    assert page.locator('#breadcrumb [aria-current="page"]').inner_text() == '飞书绑定'
    assert page.locator('#feishu-binding-code-btn').count() == 0
    page.locator('.sidebar [data-nav="overview"]').click()
    token = page.evaluate("sessionStorage.getItem('fundlex-auth-token')")
    context.request.post(base + "/api/auth/logout", headers={"Authorization": "Bearer " + token})
    page.locator('#view-overview .toolbar [data-action="refresh"]').click()
    page.wait_for_selector("#login-view", state="visible")
    assert page.locator("#login-error").is_visible()
    assert "登录状态已失效" in page.inner_text("#login-error")
    assert page.locator(".app").evaluate("n=>n.inert")


@pytest.mark.parametrize("width", [1440, 768, 390])
def test_page_layouts_fit_viewport(ui, width, tmp_path):
    page, _, _, _ = ui
    page.set_viewport_size({"width": width, "height": 900})
    open_page(ui)
    for view in ["overview", "import", "task", "guide"]:
        if view in {'import', 'task'}:
            page.evaluate('(view)=>window.FundLexWorkbench.navigate(view)', view)
        else:
            page.locator(f'.sidebar [data-nav="{view}"]').click()
        assert page.locator(f"#view-{view}").is_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
        assert not page.locator(".app").evaluate("n=>n.inert")
        page.screenshot(path=str(tmp_path / f"{view}-{width}.png"), full_page=True)
    page.locator('[data-action="help-open"]').click()
    assert page.locator("#help-overlay").is_visible()
    page.keyboard.press("Escape")
    assert page.locator("#help-overlay").is_hidden()


@pytest.mark.parametrize("width", [1440, 768, 390])
def test_report_and_review_fit_viewport(ui, width, tmp_path):
    page = ui[0]
    page.set_viewport_size({"width": width, "height": 900})
    presentation(ui, summary=True)
    for mode in ["report", "review"]:
        if mode == "review":
            page.locator('[data-action="open-review"]').click()
            page.wait_for_selector("#review-doc")
        assert page.locator("#detail-panel").evaluate("n=>n.scrollWidth<=n.clientWidth+1")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
        page.screenshot(path=str(tmp_path / f"{mode}-{width}.png"), full_page=True)


def test_missing_artifact_shows_plan_instead_of_applied(ui):
    task, _, _ = presentation(ui)
    page, context, _, _ = ui
    page.locator('#breadcrumb [data-crumb="task"]').click()
    context.unroute(f"**/api/tasks/{task}/documents?*")
    context.unroute(f"**/api/tasks/{task}/documents/*")
    page.locator('#view-task [data-action="refresh"]').click()
    page.wait_for_timeout(200)
    page.locator("#doc-rows [data-detail]").first.click()
    page.wait_for_selector(".action-evidence")
    row = page.locator(".action-evidence", has_text="已规划条款")
    assert "已规划" in row.inner_text()
    assert "已修改" not in row.inner_text()
    assert "拟修改为（尚未生成）" in row.text_content()


def test_generation_blocks_duplicate_requests_and_late_reply(ui):
    _, docs, _ = presentation(ui, 2)
    page, context, _, _ = ui
    pending = []
    context.route("**/api/batches/*/documents/*/decisions", lambda route: pending.append(route))
    page.locator('[data-action="open-review"]').click()
    page.wait_for_selector("#review-doc")
    page.locator('[data-action="generate-selected"]').click()
    page.wait_for_timeout(100)
    assert len(pending) == 1
    assert page.locator('[data-action="generate-selected"]').is_disabled()
    page.keyboard.press("r")
    assert page.locator('[data-rev-toggle="1"]').is_checked()
    page.locator('#breadcrumb [data-crumb="task"]').click()
    page.locator("#doc-rows [data-detail]").nth(1).click()
    page.wait_for_selector('[data-action="open-review"]')
    pending[0].fulfill(json={"accepted": [1, 4], "rejected": [], "download_url": "/api/ui-fixture/selected"})
    page.wait_for_timeout(100)
    assert page.locator("#detail-title").inner_text() == "合同1.docx"
    assert not page.locator('[data-action="download-selected"]').count()
    assert "业务结论" in page.inner_text("#detail-body")


def test_generation_preserves_disabled_review_navigation(ui):
    presentation(ui)
    page, context, _, _ = ui
    context.route("**/api/batches/*/documents/*/decisions", lambda route: route.fulfill(
        json={"accepted": [1, 4], "rejected": [], "download_url": "/api/ui-fixture/selected"}))
    page.locator('[data-action="open-review"]').click()
    page.wait_for_selector("#review-doc")
    page.locator('[data-action="generate-selected"]').click()
    page.wait_for_selector('[data-action="download-selected"]')
    page.wait_for_function("!document.querySelector('[data-action=generate-selected]').disabled")
    assert page.locator('[data-action="review-prev"]').is_disabled()
    assert page.locator('[data-action="review-next"]').is_disabled()


def test_overview_polls_other_task_after_selected_task_completed(ui):
    task, _ = seed(ui, states=[("succeeded", "eligible", "complete")], name="已结束任务")
    page = open_page(ui)
    page.wait_for_selector(f'#task-rows [data-task="{task}"]')
    another, _ = seed(ui, name="后台新建任务")
    page.wait_for_selector(f'#task-rows [data-task="{another}"]', timeout=10000)
    assert "后台新建任务" in page.inner_text("#task-rows")


def test_failed_stats_are_unavailable_instead_of_zero(ui):
    page, context, _, _ = ui
    context.route("**/api/tasks/stats", lambda route: route.fulfill(status=503, json={"detail": "fixture failure"}))
    open_page(ui)
    page.wait_for_timeout(100)
    for element in ["stat-month-contracts", "stat-completion-rate", "stat-average"]:
        assert page.locator("#" + element).inner_text() == "—"


def test_download_all_stays_disabled_until_terminal_result_exists(ui):
    task, _ = seed(ui)
    page = open_task(ui, task)
    assert page.locator('[data-action="download-all"]').is_disabled()


@pytest.mark.parametrize("has_guide", [False, True])
def test_unavailable_guide_blocks_new_task_with_explanation(ui, has_guide):
    page, context, _, _ = ui
    def unavailable(route):
        response = route.fetch()
        payload = response.json()
        if not has_guide:
            payload["engine"]["guide"] = None
        payload["engine"]["delivery_mode"] = "unavailable"
        route.fulfill(response=response, json=payload)
    context.route("**/api/capabilities", unavailable)
    open_page(ui, "import")
    assert "当前指引不可用" in page.inner_text("#guide-binding")
    assert "暂时不能创建任务" in page.inner_text("#import-mode-note")
    assert page.locator("#submit-task").is_disabled()


def test_authenticated_summary_download_uses_server_filename(ui, tmp_path):
    task, _ = seed(ui)
    page = open_task(ui, task)
    with page.expect_download() as item:
        page.locator('[data-action="download-summary"]').click()
    assert item.value.suggested_filename.endswith(".md")
    item.value.save_as(tmp_path / "summary.md")
    assert "交互测试任务" in (tmp_path / "summary.md").read_text()


def test_old_admin_response_cannot_expire_new_login(ui, monkeypatch):
    page, context, app, base = ui
    password = uuid.uuid4().hex
    app.state.users.create_user("browseradmin", password, "管理员样本", "admin")
    app.state.users.create_user("browsermember", password, "成员样本", "member")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    pending = []
    def hold_create(route):
        if route.request.method == "POST":
            pending.append(route)
        else:
            route.continue_()
    context.route("**/api/admin/users", hold_create)
    page.goto(base)
    page.wait_for_selector("#login-form", state="visible")
    page.fill("#login-username", "browseradmin")
    page.fill("#login-password", password)
    page.locator("#login-submit").click()
    page.wait_for_selector("#login-view", state="hidden")
    page.locator('.sidebar [data-nav="users"]').click()
    page.fill("#new-user-name", "pendinguser")
    page.fill("#new-user-password", uuid.uuid4().hex)
    page.locator("#user-create-btn").click()
    page.wait_for_timeout(100)
    assert len(pending) == 1
    page.locator("#logout-btn").click()
    page.wait_for_selector("#login-view", state="visible")
    assert not page.locator("#new-user-password").input_value()
    page.fill("#login-username", "browsermember")
    page.fill("#login-password", password)
    page.locator("#login-submit").click()
    page.wait_for_selector("#login-view", state="hidden")
    pending[0].fulfill(status=401, json={"detail": "expired old request"})
    page.wait_for_timeout(100)
    assert page.locator("#login-view").is_hidden()
    assert page.locator("#topbar-username").inner_text() == "成员样本"
    assert page.locator("#view-users").is_hidden()
    assert page.locator("#user-create-btn").is_enabled()
