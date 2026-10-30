"""Regression coverage for the 2026-10 frontend issue fixes (A9/B11/B12 audits).

Uses the same temporary Uvicorn app + Chromium setup as
``test_v1_frontend_remediation``; helpers and fixtures are imported from it to
keep one boot implementation. Opt in with FUNDLEX_BROWSER_TESTS=1.
"""
from __future__ import annotations

import json
import os
import time
import re

import pytest

from .test_v1_frontend_remediation import (base_api, browser, install_api, live_dev, live_password, open_dev,
                                           respond)

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                                reason="opt-in V1 Chromium suite")


def _dev_page(browser, width=1440, height=1000):
    context = browser.new_context(viewport={"width": width, "height": height})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','frontend-fixes')")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    return context, page, errors


def _paused_task_scenario():
    doc = {"task_id": "t", "batch_id": "b", "document_id": "doc", "name": "合同.docx", "size": 100,
           "upload_status": "accepted", "eligibility": "eligible", "job_status": "queued",
           "delivery_status": "not_generated", "downloads": {"redline": "/dl/redline.docx"},
           "reason_codes": [], "review_url": "/api/tasks/t/documents/doc/revisions",
           "report_url": "/api/tasks/t/report"}
    task = {"id": "t", "name": "暂停任务", "status": "paused", "total": 1, "uploaded": 1, "pending_upload": 0,
            "rejected": 0, "completed": 0, "processing": 0, "queued": 1, "failed": 0, "legacy": False,
            "delivery_counts": {}, "qualification_counts": {"eligible": 1}, "successful": 0, "exceptions": 0,
            "pause_reason": "MODEL_CIRCUIT_OPEN", "summary_url": "/api/tasks/t/report"}

    def scenario(path, query, route):
        if path == "/api/tasks/t":
            return respond(route, task)
        if path == "/api/tasks/t/documents":
            return respond(route, {"items": [doc], "total": 1, "page": 1, "page_size": 20})
        if path == "/api/tasks/t/documents/doc":
            return respond(route, doc)
        if path == "/api/tasks/t/documents/doc/revisions":
            return respond(route, {"selection_epoch": 1, "manifest_hash": "mhash",
                                   "html": "<p data-rev=\"1\">原条款文本</p>",
                                   "revisions": [{"del_id": 1, "ins_id": 2, "index": 1,
                                                  "operation": "replace", "rule_id": "R-1",
                                                  "section": "第一条", "before": "旧文本", "after": "新文本"}]})
        if path == "/api/tasks/t/report":
            return respond(route, {"delivery_status": "not_generated", "qualification_status": "eligible",
                                   "actions": []})
        return respond(route, {})

    return scenario


def test_wrong_old_password_keeps_dialog_and_session(browser, live_password):
    """B12-P1-1：401 被稳定错误契约映射后，不得再误判为会话失效并登出。"""
    _app, base = live_password
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    try:
        page.goto(base + "/", wait_until="networkidle")
        page.locator("#login-username").fill("frontend-a")
        page.locator("#login-password").fill("frontend-a-password")
        page.locator("#login-submit").click()
        page.locator("#topbar-user").wait_for(state="visible")
        token = page.evaluate("sessionStorage.getItem('fundlex-auth-token')")
        page.locator("#password-btn").click()
        page.locator("#pwd-old").fill("wrong-old-password")
        page.locator("#pwd-new").fill("replacement-password-1")
        page.locator("#pwd-confirm").fill("replacement-password-1")
        page.locator("#pwd-submit").click()
        page.locator("#pwd-error").wait_for(state="visible")
        assert "当前密码不正确" in page.locator("#pwd-error").inner_text()
        assert page.locator("#password-view").is_visible(), "窗口必须保持打开让用户改正"
        assert page.locator("#login-view").is_hidden()
        assert page.evaluate("sessionStorage.getItem('fundlex-auth-token')") == token
    finally:
        context.close()


def test_contract_detail_closes_back_to_task_via_escape_and_background(browser, live_dev):
    """A9-F02：Esc 与背景点击都要关闭合同详情并回到 #task，不留空白页。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    install_api(page, base_api(_paused_task_scenario()))
    try:
        open_dev(page, base, "#task?id=t")
        page.locator("#doc-rows [data-detail]").wait_for()
        page.locator("#doc-rows [data-detail]").first.click()
        page.locator("#detail-overlay").wait_for(state="visible")
        page.keyboard.press("Escape")
        assert page.locator("#detail-overlay").is_hidden()
        assert page.evaluate("location.hash").startswith("#task"), "Esc 后必须回到任务页哈希"

        page.locator("#doc-rows [data-detail]").first.click()
        page.locator("#detail-overlay").wait_for(state="visible")
        # 生产设计：详情在文档页内联呈现，没有背景层；进入修订审查后才是固定遮罩，
        # 此时点击遮罩背景必须同样关闭并回到任务页。
        page.locator("[data-action='open-review']").click()
        page.locator("#detail-overlay .review-layout").wait_for(state="visible")
        assert page.locator("#detail-overlay").evaluate(
            "el => getComputedStyle(el).position") == "fixed"
        page.locator("#detail-overlay").click(position={"x": 5, "y": 5})
        assert page.locator("#detail-overlay").is_hidden()
        assert page.evaluate("location.hash").startswith("#task")
        assert not errors, errors
    finally:
        context.close()


def test_paused_task_shows_paused_rows_download_hint_and_verdict(browser, live_dev):
    """B12-P1-6/P1-2：任务暂停时行的处理徽标合成“已暂停”；无终态结果时给出下载提示。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    install_api(page, base_api(_paused_task_scenario()))
    try:
        open_dev(page, base, "#task?id=t")
        page.locator("#doc-rows [data-detail]").wait_for()
        assert "已暂停" in page.locator("#doc-rows tr").first.inner_text()
        assert "排队中" not in page.locator("#doc-rows").inner_text()
        assert page.locator("#download-hint").is_visible()
        assert page.locator('[data-action="download-all"]').is_disabled()

        page.locator("#doc-rows [data-detail]").first.click()
        page.locator("#detail-body .result-summary").wait_for()
        assert page.locator(".result-verdict strong").inner_text() == "已暂停"
        grid = page.locator(".result-status-grid")
        assert "已暂停" in grid.inner_text()
        assert not errors, errors
    finally:
        context.close()


def test_generate_selected_recovers_from_failing_revisions_preload(browser, live_dev):
    """A9-F03：生成前读取修订状态失败后，控件必须恢复、消息可读、无未处理拒绝。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    calls = {"revisions": 0}
    doc = {"task_id": "t", "batch_id": "b", "document_id": "doc", "name": "合同.docx", "size": 100,
           "upload_status": "accepted", "eligibility": "eligible", "job_status": "succeeded",
           "delivery_status": "incomplete",
           "downloads": {"redline": "/api/batches/b/documents/doc/download/redline"},
           "review_url": "/api/batches/b/documents/doc/revisions"}
    task = {"id": "t", "name": "任务", "status": "completed", "total": 1, "uploaded": 1, "pending_upload": 0,
            "rejected": 0, "completed": 1, "processing": 0, "queued": 0, "failed": 0, "legacy": False,
            "delivery_counts": {"incomplete": 1}, "qualification_counts": {"eligible": 1},
            "successful": 0, "exceptions": 0, "summary_url": "/api/tasks/t/report"}

    def scenario(path, query, route):
        if path == "/api/tasks/t":
            return respond(route, task)
        if path == "/api/tasks/t/documents":
            return respond(route, {"items": [doc], "total": 1, "page": 1, "page_size": 20})
        if path == "/api/tasks/t/documents/doc":
            return respond(route, doc)
        if path == "/api/batches/b/documents/doc/revisions":
            calls["revisions"] += 1
            if calls["revisions"] > 1:
                return respond(route, {"detail": "fixture outage"}, status=503)
            # manifest_hash 缺失会触发点击“生成”时的前置重取，正是 A9-F03 失败的入口。
            return respond(route, {"document_id": "doc", "html": '<p><del data-rev="1">旧文</del><ins data-rev="2">新文</ins></p>',
                                   "revisions": [{"del_id": 1, "ins_id": 2, "index": 1, "operation": "replace",
                                                  "before": "旧文", "after": "新文"}],
                                   "selection_epoch": 0, "manifest_hash": None,
                                   "download_url": "/api/batches/b/documents/doc/download/selected_final"})
        if path == "/api/tasks/t/report":
            return respond(route, {"delivery_status": "incomplete", "qualification_status": "eligible", "actions": []})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#document?id=t&document=doc&tab=review")
        page.locator('[data-action="generate-selected"]').wait_for()
        assert calls["revisions"] == 1
        page.locator('[data-action="generate-selected"]').click()
        page.locator("#review-message").filter(has_text="读取修订状态未完成").wait_for()
        assert calls["revisions"] >= 2
        assert page.locator('[data-action="generate-selected"]').is_enabled(), "失败后控件必须恢复可重试"
        assert not errors, errors
    finally:
        context.close()


def test_compare_queued_detail_shows_pair_files_and_pending_note(browser, live_dev):
    """B12-P1-4：排队中的比对详情要展开合同组并说明状态，不再是空白页。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    queued = {"id": "T", "name": "排队比对", "status": "queued", "total": 1,
              "pairs": [{"id": "P1", "label": "合同 1", "status": "queued",
                         "left": {"name": "A-募集合同.docx"}, "right": {"name": "B-托管合同.docx"}}]}

    def scenario(path, query, route):
        if path == "/api/compare/tasks":
            return respond(route, {"items": [queued], "total": 1})
        if path == "/api/compare/tasks/T":
            return respond(route, queued)
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T")
        page.locator("#compare-pair-list").get_by_text("A-募集合同.docx").wait_for()
        assert page.locator("#compare-pending-note").is_visible()
        assert page.locator(".compare-groups-disclosure").evaluate("n => n.open")
        assert page.locator("#compare-viewer").is_hidden(), "无结果的合同组不应打开空白比对窗"
        assert not errors, errors
    finally:
        context.close()


def test_compare_generate_requires_saved_selection_epoch(browser, live_dev):
    """A9-F06：选择尚未保存（epoch<1）时拦截生成请求，提示先保存。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    posts: list[str] = []
    view = {"pair": {"id": "P1", "label": "P1"}, "result_sha256": "a" * 64,
            "left": {"name": "left.docx", "html": '<p data-block-id="b"><mark data-diff-id="D1">old</mark></p>'},
            "right": {"name": "right.docx", "html": '<p data-block-id="b"><mark data-diff-id="D1">new</mark></p>'},
            "summary": {"total": 1, "modify": 1, "insert": 0, "delete": 0}, "coverage": {"status": "complete"},
            "diffs": [{"id": "D1", "type": "modify", "section": "正文",
                       "left": {"text": "old", "block_id": "b"}, "right": {"text": "new", "block_id": "b"}}]}
    selection = {"pair_id": "P1", "result_sha256": "a" * 64, "left_source_sha256": "b" * 64,
                 "right_source_sha256": "c" * 64, "selection_epoch": 0,
                 "draft": {"selection_epoch": 0, "decisions": {"D1": "left"}, "decision_hash": "d" * 64},
                 "decisions": {"D1": "left"},
                 "assessment": {"pending_ids": [], "issues": [], "can_generate": True},
                 "diffs": view["diffs"], "artifacts": []}

    def scenario(path, query, route):
        if path in {"/api/compare/tasks", "/api/compare/tasks/T"}:
            body = {"id": "T", "name": "比对", "status": "succeeded", "total": 1,
                    "pairs": [{"id": "P1", "label": "P1", "status": "succeeded",
                               "left": {"name": "left.docx"}, "right": {"name": "right.docx"},
                               "summary": {"total": 1}}]}
            return respond(route, {"items": [body], "total": 1} if path.endswith("tasks") else body)
        if path == "/api/compare/pairs/P1/view":
            return respond(route, view)
        if path == "/api/compare/pairs/P1/selection" and route.request.method == "GET":
            return respond(route, selection)
        if path.endswith("/selection/generate"):
            posts.append(path)
            return respond(route, {"version": 1})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=detail&id=T&pair=P1")
        page.locator("#compare-selection-generate").wait_for(state="visible")
        assert page.locator("#compare-selection-generate").is_enabled()
        page.locator("#compare-selection-generate").click()
        page.locator("#compare-selection-status").filter(has_text="请先保存当前选择").wait_for()
        assert not posts, "epoch<1 时不允许发出生成请求"
        assert not errors, errors
    finally:
        context.close()


def test_compare_default_task_name_and_docx_hint(browser, live_dev):
    """B12-P1-4/P3：空名称自动生成带时间戳的任务名；上传卡片说明 .doc 需另存。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    created: list[dict] = []

    def scenario(path, query, route):
        if path == "/api/compare/tasks" and route.request.method == "POST":
            created.append(json.loads(route.request.post_data or "{}"))
            name = created[-1].get("name", "")
            return respond(route, {"id": "T2", "name": name, "status": "uploading", "total": 1, "pairs": []})
        if path == "/api/compare/tasks/T2/uploads":
            young = created[-1]["pairs"][0]
            return respond(route, {"receipts": [{"client_id": young["left"]["client_id"], "status": "accepted"},
                                                {"client_id": young["right"]["client_id"], "status": "accepted"}],
                                   "task": {"id": "T2", "status": "uploading", "total": 1, "pairs": []}})
        if path == "/api/compare/tasks/T2/seal":
            return respond(route, {"id": "T2", "name": created[-1]["name"], "status": "queued", "total": 1,
                                   "pairs": [{"id": "P9", "label": "合同 1", "status": "queued",
                                              "left": {"name": "a.docx"}, "right": {"name": "b.docx"}}]})
        if path == "/api/compare/tasks/T2":
            return respond(route, {"id": "T2", "name": created[-1]["name"], "status": "queued", "total": 1,
                                   "pairs": [{"id": "P9", "label": "合同 1", "status": "queued",
                                              "left": {"name": "a.docx"}, "right": {"name": "b.docx"}}]})
        if path == "/api/compare/tasks":
            return respond(route, {"items": [], "total": 0})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#compare?mode=new")
        first = page.locator('[data-compare-left="0"]')
        first.wait_for(state="attached")
        assert ".doc 请先另存为 .docx" in page.locator(".compare-file-card").first.inner_text()
        page.set_input_files('[data-compare-left="0"]', [{"name": "a.docx",
                                                          "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                                          "buffer": b"PK\x03\x04fake"}])
        page.set_input_files('[data-compare-right="0"]', [{"name": "b.docx",
                                                           "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                                           "buffer": b"PK\x03\x04fake"}])
        page.locator("#compare-submit").click()
        page.locator("#compare-detail").wait_for(state="visible")
        assert "已提交" in page.locator("#compare-upload-message").text_content()
        assert created, "必须提交创建请求"
        assert re.fullmatch(r"合同比对 \d{4}/\d{1,2}/\d{1,2} \d{2}:\d{2}:\d{2}", created[0]["name"]), created[0]["name"]
        assert not errors, errors
    finally:
        context.close()


def test_workspace_date_inputs_validate_real_dates(browser, live_dev):
    """B12-P3：日期改用可输入的 YYYY-MM-DD 文本框，非法日期不进入路由。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)

    def scenario(path, query, route):
        if path == "/api/workspace/tasks":
            return respond(route, {"items": [], "total": 0, "page": 1, "page_size": 20, "stats": {}})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base)
        start = page.locator("#workspace-date-from")
        assert start.get_attribute("type") == "text"
        assert start.get_attribute("placeholder") == "YYYY-MM-DD"
        start.fill("2026-13-40")
        start.dispatch_event("change")
        page.wait_for_timeout(200)
        assert "date_from" not in page.evaluate("location.hash"), "非法日期不得写入路由"
        start.fill("2026-10-31")
        start.dispatch_event("change")
        page.wait_for_function("location.hash.includes('date_from=2026-10-31')")
        for picker in ["#file-picker", "#folder-picker", "#replace-picker", "#guide-file"]:
            assert page.locator(picker).get_attribute("aria-label"), f"{picker} 缺少可访问名称"
        assert not errors, errors
    finally:
        context.close()


def test_guide_list_fallback_caches_and_loads_more(browser, live_dev):
    """A9-F05：服务不分页结论缓存后不再重复双请求；超 50 条给出“加载更多”。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    hits: list[str] = []
    runs = [{"id": f"R{i}", "title": f"生成任务{i}", "filename": f"法规{i}.docx", "status": "complete",
             "stage": "FINALIZE_GUIDE", "qualification_status": "candidate_ready",
             "created_at": 1700000000 + i, "updated_at": 1700000000 + i} for i in range(60)]

    def scenario(path, query, route):
        if path == "/api/guide-generation/runs":
            hits.append(f"page={query.get('page', ['-'])[0]},limit={query.get('limit', ['-'])[0]}")
            if "page" in query:
                # 旧版响应：没有分页元数据，应触发一次 limit=200 回退。
                return respond(route, {"items": runs})
            return respond(route, {"items": runs})
        return respond(route, {})

    install_api(page, base_api(scenario))
    try:
        open_dev(page, base, "#generation?mode=list")
        page.locator("#gg-list-results .gg-table-wrap tbody tr").first.wait_for()
        assert page.locator("#gg-list-results tbody tr").count() == 50
        assert "200" in page.locator("#gg-list-scope").inner_text()
        assert hits[:2] == ["page=1,limit=-", "page=-,limit=200"], hits
        page.locator("[data-gg-list-more]").click()
        assert page.locator("#gg-list-results tbody tr").count() == 60
        page.locator('[data-gg-action="refresh"]').click()
        page.locator("#gg-list-results .gg-table-wrap").wait_for()
        paged_hits = [hit for hit in hits if hit.startswith("page=1")]
        assert len(paged_hits) == 1, f"缓存后不应再请求分页端点：{hits}"
        assert not errors, errors
    finally:
        context.close()


def test_guide_poll_backs_off_then_stops_with_notice(browser, live_dev):
    """A9-F08：轮询失败按 10s/30s 退避，连续 3 次后停止并显示提示而非静默停摆。"""
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','frontend-fixes')")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    fetches = {"count": 0}
    running = {"id": "R", "title": "生成中", "filename": "法规.docx", "status": "running",
               "stage": "BUILD_LOCAL_GUIDE_CANDIDATES", "qualification_status": "draft",
               "summary": {}, "stats": {}, "stages": [], "artifacts": {}, "retry": None,
               "created_at": 1700000000, "updated_at": 1700000000}

    def scenario(path, query, route):
        if path == "/api/guide-generation/runs/R":
            fetches["count"] += 1
            if fetches["count"] == 1:
                return respond(route, running)
            return respond(route, {"detail": "MODEL_HTTP_ERROR"}, status=503)
        return respond(route, {})

    install_api(page, base_api(scenario))

    def advance_until(expected, limit_ms=120000):
        # run_for 只推进模拟时钟；fetch 走真实网络，且首个轮询要等 loadTab 内部的
        # 计时器随模拟时钟走过才排程。用小步推进并用真实时间等待请求完成，避免大步
        # 跳跃错过尚未排程的退避定时器。
        advanced = 0
        while advanced < limit_ms:
            if fetches["count"] >= expected:
                return
            page.clock.run_for(500)
            advanced += 500
            time.sleep(0.05)
        raise AssertionError(f"期待第 {expected} 次轮询，实际 {fetches['count']} 次")

    try:
        page.clock.install()
        page.goto(base + "/#generation?mode=detail&id=R", wait_until="networkidle")
        page.locator("#gg-detail-head").wait_for()
        assert fetches["count"] == 1
        advance_until(2)  # 首次轮询失败 → 10s 退避
        advance_until(3)  # 第二次失败 → 30s 退避
        advance_until(4)  # 第三次失败 → 停止并提示
        page.locator("#gg-detail-head").get_by_text("自动刷新已连续失败").wait_for()
        assert fetches["count"] == 4, fetches
        for _ in range(130):
            page.clock.run_for(500)
        assert fetches["count"] == 4, "停止后不应继续轮询"
        assert page.locator('[data-gg-action="refresh"]').first.is_visible(), "必须保留手动刷新入口"
        assert not errors, errors
    finally:
        context.close()


def test_narrow_desktop_scroll_shadow_hint_toggles_with_viewport(browser, live_dev):
    """B11-P1：761–1180px 下表格容器有滚动阴影提示，宽屏下不出现。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser, width=900, height=900)
    install_api(page, base_api(lambda path, query, route: respond(route, {})))
    try:
        open_dev(page, base)
        page.locator("#view-workspace .table-wrap").wait_for()
        wide = page.evaluate("getComputedStyle(document.querySelector('#view-workspace .table-wrap')).backgroundImage")
        assert "linear-gradient" in wide and "radial-gradient" in wide, wide
        page.set_viewport_size({"width": 1400, "height": 900})
        page.wait_for_timeout(100)
        narrow = page.evaluate("getComputedStyle(document.querySelector('#view-workspace .table-wrap')).backgroundImage")
        assert narrow == "none", narrow
        assert not errors, errors
    finally:
        context.close()


def test_invalid_hash_toasts_and_returns_to_workspace(browser, live_dev):
    """无效哈希提示并回到工作台，而不是静默跳转。"""
    _app, base = live_dev
    context, page, errors = _dev_page(browser)
    install_api(page, base_api(lambda path, query, route: respond(route, {})))
    try:
        open_dev(page, base, "#definitely-not-a-view")
        page.locator(".toast-item").filter(has_text="链接无效或已过期").wait_for()
        assert page.evaluate("location.hash") == "#workspace"
        assert page.locator("#view-workspace").is_visible()
        assert not errors, errors
    finally:
        context.close()
