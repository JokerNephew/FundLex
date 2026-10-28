"""UI/API regression fixtures. No Worker, model calls, or contract-engine acceptance.

Opt in with FUNDLEX_BROWSER_TESTS=1; requires Playwright and its Chromium browser.
Reports/revision views used for presentation tests are explicit UI fixtures.
"""
from __future__ import annotations

import io
import json
import os
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
        browser = playwright.chromium.launch(
            headless=os.getenv("FUNDLEX_BROWSER_HEADLESS", "1") != "0")
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
        for doc in payload["items"]:
            doc["downloads"] = {"working_redline": "/api/ui-fixture/redline", "selected_final": "/api/ui-fixture/selected"}
            doc["review_url"] = "/api/ui-fixture/revisions/" + doc["document_id"]
            if execution_mode:
                doc["execution_mode"] = execution_mode
            if delivery == "complete_with_exceptions":
                doc["downloads"] = {"redline": "/api/ui-fixture/redline", "final": "/api/ui-fixture/final"}
        route.fulfill(response=response, json=payload)
    context.route(f"**/api/tasks/{task}/documents?*", documents)
    revisions = {"html": '<p><del class="rev rev-del" data-rev="1">原文</del><ins class="rev rev-ins" data-rev="2">改文</ins></p><p><ins class="rev rev-ins" data-rev="4">新增句</ins></p>',
                 "revisions": [{"index": 1, "del_id": 1, "ins_id": 2, "revision_ids": [1, 2], "before": "原文", "after": "改文", "operation": "replace"},
                               {"index": 2, "del_id": 4, "ins_id": 5, "revision_ids": [4], "before": "", "after": "新增句", "operation": "insert"}]}
    context.route("**/api/ui-fixture/revisions/*", lambda route: route.fulfill(json=revisions))
    open_task(ui, task)
    page.locator("#doc-rows [data-detail]").first.click()
    page.wait_for_selector("#detail-body .detail-grid")
    return task, docs, revisions


def test_overview_units_filters_and_single_supported_mode(ui):
    task, _ = seed(ui, states=[("succeeded", "eligible", "complete")])
    page = open_page(ui)
    page.wait_for_function("document.querySelector('#overview-average').textContent==='90'")
    assert "90 秒 秒" not in page.inner_text("#overview-description")
    page.fill("#task-search", "不存在的筛选")
    page.wait_for_function("document.querySelector('#task-rows').textContent.includes('没有任务')")
    assert page.locator("#first-run-guide").is_hidden()
    page.locator('.sidebar [data-nav="import"]').click()
    # The workbench exposes one formal revision flow; the old mode selector is
    # gone rather than being a disabled/fake choice.
    assert page.locator("#import-mode").count() == 0
    assert "当前指引" in page.inner_text("#guide-binding")


def test_delivery_counts_and_worker_filter_match_api(ui):
    states = [("succeeded", "eligible", "complete"), ("succeeded", "eligible", "incomplete"),
              ("failed", "failed", "incomplete"), ("succeeded", "excluded_by_fund_type", "not_generated"),
              ("leased", "pending", "not_generated")]
    task, _ = seed(ui, 5, states)
    page = open_page(ui)
    row = page.locator(f'#task-rows tr:has([data-task="{task}"])')
    assert row.locator(".task-success").inner_text() == "1"
    assert row.locator(".task-error").inner_text() == "2"
    assert row.locator(".p-excluded").count() == 1
    row.locator("[data-task]").click()
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
    assert page.locator("#progress-evaluation-legend").is_visible()


def test_exception_delivery_remains_downloadable_without_direct_use_claim(ui):
    presentation(ui, delivery="complete_with_exceptions")
    page = ui[0]
    conclusion = page.locator("#detail-body .detail-grid")
    assert "不可认定" in conclusion.inner_text()
    assert "已通过交付校验" not in conclusion.inner_text()
    assert page.locator('[data-download="final"]').is_visible()
    assert "按例外清单人工核对" in page.inner_text("#detail-body")


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
    page.locator("#close-detail").click()
    page.keyboard.press("a")
    assert page.locator("#detail-overlay").is_hidden()


def test_old_review_failure_cannot_overwrite_new_report(ui):
    _, _, _ = presentation(ui, 2)
    page, context, _, _ = ui
    pending = []
    context.route("**/api/ui-fixture/revisions/*", lambda route: pending.append(route))
    page.locator('[data-action="open-review"]').click()
    page.wait_for_timeout(100)
    assert pending
    page.locator("#close-detail").click()
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
        index = len(pending)
        pending.append((route, None))
        pending[index] = (route, route.fetch())
    page.route(pattern, intercept)
    open_page(ui, "import")
    page.fill("#task-name", "旧上传任务")
    page.set_input_files("#file-picker", {"name": "旧合同.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "buffer": docx_bytes()})
    page.locator("#submit-task").click()
    deadline = time.monotonic() + 15
    while not pending and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    assert pending
    page.locator('.sidebar [data-nav="overview"]').click()
    page.locator('#view-overview [data-action="new-task"]').first.click()
    page.fill("#task-name", "新草稿不得覆盖")
    deadline = time.monotonic() + 15
    while pending and pending[-1][1] is None and time.monotonic() < deadline:
        page.wait_for_timeout(100)
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
    button = page.locator(f'[data-guide-parse="{version["id"]}"]')
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


def test_task_deep_link_selects_task(ui):
    task, _ = seed(ui)
    page, _, _, base = ui
    page.goto(base + f"/?task={task}#task")
    page.wait_for_function("document.querySelector('#selected-task-title').textContent.includes('交互测试任务')")
    assert page.locator("#view-task").is_visible()


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
    assert page.locator("#view-settings").is_visible()
    assert page.locator("#dev-settings-panel").is_hidden()
    assert page.locator("#feishu-binding-code-btn").is_visible()
    assert page.locator("#capability-details").inner_text()
    page.evaluate("location.hash='overview'")
    page.wait_for_timeout(100)
    token = page.evaluate("sessionStorage.getItem('fundlex-auth-token')")
    headers = {"Authorization": "Bearer " + token}
    capabilities = context.request.get(base + "/api/capabilities", headers=headers)
    assert capabilities.ok
    assert capabilities.json()["auth_mode"] == "password"
    assert "upload_limits" in capabilities.json()
    assert context.request.get(base + "/api/integrations/feishu/binding", headers=headers).ok
    assert context.request.get(base + "/api/settings/guide", headers=headers).ok
    assert context.request.get(base + "/api/admin/users", headers=headers).status == 404
    context.request.post(base + "/api/auth/logout", headers={"Authorization": "Bearer " + token})
    page.locator('#view-overview [data-action="refresh"]').first.click()
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
    page.locator("#close-detail").click()
    context.unroute(f"**/api/tasks/{task}/documents?*")
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
    page.locator("#close-detail").click()
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


def _compare_docx(paragraphs):
    from docx import Document
    stream = io.BytesIO()
    document = Document()
    for value in paragraphs:
        document.add_paragraph(value)
    document.save(stream)
    return stream.getvalue()


def _compare_revision_docx():
    from docx import Document
    from docx.oxml import OxmlElement
    from lxml import etree
    from zipfile import ZIP_DEFLATED, ZipFile
    from fundlex.docx import Q

    source = _compare_docx(["原文字"])
    with ZipFile(io.BytesIO(source)) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    root = etree.fromstring(parts["word/document.xml"])
    paragraph = root.find(".//" + Q("p"))
    run = paragraph.find(Q("r"))
    text = run.find(Q("t"))
    deleted = OxmlElement("w:del")
    deleted.set(Q("id"), "1")
    deleted_run = OxmlElement("w:r")
    deleted_text = OxmlElement("w:delText")
    deleted_text.text = text.text
    deleted_run.append(deleted_text)
    deleted.append(deleted_run)
    inserted = OxmlElement("w:ins")
    inserted.set(Q("id"), "2")
    inserted_run = OxmlElement("w:r")
    inserted_text = OxmlElement("w:t")
    inserted_text.text = "新文字"
    inserted_run.append(inserted_text)
    inserted.append(inserted_run)
    paragraph.remove(run)
    paragraph.extend([deleted, inserted])
    parts["word/document.xml"] = etree.tostring(root)
    output = io.BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return output.getvalue()


def _seed_compare(ui):
    _, context, app, base = ui
    left = _compare_docx(["前文", "费率为0.40%", "后文"])
    right = _compare_docx(["前文", "费率为0.30%", "后文"])
    headers = {"X-FundLex-User": "browser-check", "Content-Type": "application/json"}
    payload = {"name": "选择版浏览器测试", "pairs": [{
        "client_pair_id": "p", "label": "第一组",
        "left": {"client_id": "l", "name": "left.docx", "size": len(left)},
        "right": {"client_id": "r", "name": "right.docx", "size": len(right)},
    }]}
    created = context.request.post(base + "/api/compare/tasks", headers=headers,
                                   data=json.dumps(payload))
    assert created.ok, created.text()
    task = created.json()["id"]
    upload_headers = {"X-FundLex-User": "browser-check"}
    for client_id, filename, content in (("l", "left.docx", left), ("r", "right.docx", right)):
        uploaded = context.request.post(
            base + f"/api/compare/tasks/{task}/uploads", headers=upload_headers,
            multipart={
                "client_ids": json.dumps([client_id]),
                "files": {
                    "name": filename,
                    "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    "buffer": content,
                },
            })
        assert uploaded.ok, uploaded.text()
    assert context.request.post(base + f"/api/compare/tasks/{task}/seal", headers=headers).ok
    from fundlex.compare.worker import CompareWorker
    assert CompareWorker(app.state.compare_store).run_once()
    return task


def _open_compare_selection(ui, task):
    page, _, _, base = ui
    page.goto(base + "/#compare")
    page.locator(f'[data-compare-task="{task}"]').click()
    page.locator('[data-compare-pair="0"]').click()
    page.wait_for_selector("#compare-diff-list .compare-diff-row")
    page.wait_for_function("document.querySelector('#compare-selection-progress').textContent.includes('待选')")
    return page


def test_compare_splitter_drag_keyboard_and_reset(ui):
    task = _seed_compare(ui)
    page = _open_compare_selection(ui, task)
    gutter = page.locator("#compare-gutter")
    gutter.scroll_into_view_if_needed()
    gutter.wait_for(state="visible")
    left = page.locator("#compare-left-pane")
    width_before = left.bounding_box()["width"]
    box = gutter.bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(box["x"] + box["width"] / 2 - 120, box["y"] + box["height"] / 2, steps=8)
    assert page.locator("#compare-split-preview").evaluate("node => node.style.opacity") == "1"
    assert page.locator("#compare-split-preview").evaluate("node => node.style.left") != ""
    page.mouse.up()
    page.wait_for_timeout(150)
    assert page.locator("#compare-split-preview").evaluate("node => node.style.opacity") == ""
    width_dragged = left.bounding_box()["width"]
    assert width_dragged < width_before - 40
    assert gutter.get_attribute("aria-valuenow") != "50"

    gutter.focus()
    page.keyboard.press("ArrowLeft")
    page.wait_for_timeout(100)
    assert left.bounding_box()["width"] < width_dragged
    page.keyboard.press("Enter")
    page.wait_for_timeout(100)
    assert abs(left.bounding_box()["width"] - width_before) < 8

    page.set_viewport_size({"width": 390, "height": 844})
    assert gutter.is_hidden()


def test_compare_selection_save_generate_download_restore_and_mobile(ui):
    task = _seed_compare(ui)
    page = _open_compare_selection(ui, task)
    progress = page.locator("#compare-selection-progress")
    assert "待选 1" in progress.inner_text()
    assert page.locator("#compare-selection-generate").is_disabled()

    page.locator("#compare-select-right").click()
    page.wait_for_function("document.querySelector('#compare-selection-progress').textContent.includes('已选 1 / 1')")
    page.locator("#compare-selection-save").click()
    page.wait_for_function("document.querySelector('#compare-selection-status').textContent.includes('选择已保存')")
    page.locator("#compare-selection-generate").click()
    page.wait_for_function("document.querySelector('#compare-selection-status').textContent.includes('已生成版本 1')")
    final = page.locator('#compare-selection-versions [data-compare-filename*="最终版"]')
    assert final.count() == 1
    assert page.locator('#compare-selection-versions [data-compare-report-version="1"]').is_visible()
    with page.expect_download() as download_info:
        final.click()
    download = download_info.value
    assert download.path() and download.path().stat().st_size > 1000

    # Refresh restores the saved decisions and the current generated version.
    page = _open_compare_selection(ui, task)
    page.wait_for_function("document.querySelector('#compare-selection-progress').textContent.includes('已选 1 / 1')")
    assert "版本 1" in page.locator("#compare-selection-versions").inner_text()
    assert "当前版本" in page.locator("#compare-selection-versions").inner_text()

    # A changed decision is saved as a new epoch and marks the old version stale.
    page.locator('.compare-diff-choice input[value="left"]').first.check()
    page.locator("#compare-selection-save").click()
    page.wait_for_function("document.querySelector('#compare-selection-status').textContent.includes('选择已保存')")
    page.wait_for_function("document.querySelector('#compare-selection-versions').textContent.includes('已过期')")

    page.set_viewport_size({"width": 390, "height": 844})
    metrics = page.evaluate("() => ({viewport: innerWidth, document: document.documentElement.scrollWidth, body: document.body.scrollWidth})")
    assert metrics["document"] <= metrics["viewport"] and metrics["body"] <= metrics["viewport"]
    assert page.locator("#compare-selection").is_visible()
    assert page.locator("#compare-selection-generate").is_visible()


def test_compare_upload_accepts_word_revisions_and_shows_notice(ui):
    page, context, _, base = ui
    left_file = _compare_revision_docx()
    page.goto(base + "/#compare")
    page.wait_for_function("document.querySelector('#upload-limit').textContent.includes('MiB')")
    page.locator("#compare-new").click()
    page.locator("[data-compare-left]").set_input_files({
        "name": "revision.docx",
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "buffer": left_file,
    })
    page.locator("[data-compare-right]").set_input_files({
        "name": "right.docx",
        "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "buffer": _compare_docx(["新文字"]),
    })
    page.locator("#compare-submit").click()
    page.wait_for_function(
        "document.querySelector('#compare-upload-message').textContent.includes('已提交')"
        " && document.querySelector('#compare-upload-message').textContent.includes('自动接受 3 处已有修订')")
    page.wait_for_function("document.querySelector('#toast').textContent.includes('自动接受 3 处已有修订')")

    tasks = context.request.get(base + "/api/compare/tasks", headers={"X-FundLex-User": "browser-check"})
    assert tasks.ok
    task = next(item for item in tasks.json()["items"] if item["name"] == "合同对比")
    left = task["pairs"][0]["left"]
    assert left["revisions_accepted"] == 3
    assert left["original_size"] == len(left_file)
    assert left["normalized_size"] == left["size"]
    assert left["normalized_sha256"] == left["source_sha256"]
    assert left["normalized_sha256"] != left["original_sha256"]
