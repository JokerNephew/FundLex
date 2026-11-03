"""FL-D1080：修订审查「改动清单」显示修改人 + 按修改人筛选（浏览器实证）。"""
from __future__ import annotations

import os

import pytest

from .test_v1_frontend_remediation import (base_api, browser, install_api, live_dev,
                                           open_dev, respond)

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                                reason="opt-in browser suite")

_SHOTS = os.getenv("FUNDLEX_REVIEW_AUTHOR_SHOTS", "/tmp/opencode/qa/review-author")


def _authored_review_scenario():
    doc = {"task_id": "t", "batch_id": "b", "document_id": "doc", "name": "费率合同.docx", "size": 100,
           "upload_status": "accepted", "eligibility": "eligible", "job_status": "completed",
           "delivery_status": "not_generated", "downloads": {"redline": "/dl/redline.docx"},
           "reason_codes": [], "review_url": "/api/tasks/t/documents/doc/revisions",
           "report_url": "/api/tasks/t/report"}
    task = {"id": "t", "name": "修改人审查任务", "status": "completed_with_exceptions", "total": 1,
            "uploaded": 1, "pending_upload": 0, "rejected": 0, "completed": 1, "processing": 0,
            "queued": 0, "failed": 0, "legacy": False, "delivery_counts": {},
            "qualification_counts": {"eligible": 1}, "successful": 1, "exceptions": 0,
            "summary_url": "/api/tasks/t/report"}

    def scenario(path, query, route):
        if path == "/api/tasks/t":
            return respond(route, task)
        if path == "/api/tasks/t/documents":
            return respond(route, {"items": [doc], "total": 1, "page": 1, "page_size": 20})
        if path == "/api/tasks/t/documents/doc":
            return respond(route, doc)
        if path == "/api/tasks/t/documents/doc/revisions":
            return respond(route, {"selection_epoch": 1, "manifest_hash": "mhash",
                                   "html": '<p>赎<u>回费</u>条款。</p>',
                                   "revisions": [
                                       {"del_id": 1, "ins_id": 2, "index": 1, "operation": "replace",
                                        "rule_id": "R-1", "section": "第一条", "before": "旧费率",
                                        "after": "新费率", "author": "张编辑"},
                                       {"del_id": 3, "ins_id": None, "index": 2, "operation": "delete",
                                        "rule_id": "R-2", "section": "第二条", "before": "冗余句",
                                        "after": "", "author": "李法务"}]})
        if path == "/api/tasks/t/report":
            return respond(route, {"delivery_status": "not_generated", "qualification_status": "eligible",
                                   "actions": []})
        return respond(route, {})

    return scenario


def test_review_rail_shows_author_and_filters(browser, live_dev):
    import pathlib
    pathlib.Path(_SHOTS).mkdir(parents=True, exist_ok=True)
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','author-probe')")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        install_api(page, base_api(_authored_review_scenario()))
        open_dev(page, base, "#document?id=t&document=doc&tab=review")
        layout = page.locator("#detail-overlay .review-layout")
        layout.wait_for(state="visible", timeout=20000)
        # ① 每条修订头显示修改人徽标
        authors = page.locator(".rev-item .rev-author").all_inner_texts()
        assert "张编辑" in authors and "李法务" in authors, f"作者徽标缺失：{authors}"
        # ② 修改人筛选下拉存在且含两个作者
        select = page.locator("#review-author-filter")
        assert select.is_visible()
        assert "张编辑" in select.inner_text() and "李法务" in select.inner_text()
        page.screenshot(path=f"{_SHOTS}/a-01-authors.png")
        # ③ 选「张编辑」→ 只留其修订；计数联动
        select.select_option("张编辑")
        visible = page.locator(".rev-item[data-rev-item]:visible")
        assert visible.count() == 1, f"筛选后可见条数应为 1，实测 {visible.count()}"
        assert "张编辑" in visible.first.inner_text()
        title = page.locator(".review-list-title").inner_text()
        assert "1 / 2" in title, f"计数应『1 / 2 条』，实测：{title}"
        page.screenshot(path=f"{_SHOTS}/a-02-filtered.png")
        # ④ 复位 → 两条全回
        select.select_option("")
        assert page.locator(".rev-item[data-rev-item]:visible").count() == 2
        assert not errors, f"pageerror: {errors}"
    finally:
        context.close()
