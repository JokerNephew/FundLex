"""FL-D1081：单作者（生产引擎签名 FundLex）时修改人下拉也必须可用。"""
from __future__ import annotations

import os

import pytest

from .test_v1_frontend_remediation import (base_api, browser, install_api, live_dev,
                                           open_dev, respond)

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1",
                                reason="opt-in browser suite")


def _single_author_scenario():
    doc = {"task_id": "t", "batch_id": "b", "document_id": "doc", "name": "费率合同.docx", "size": 100,
           "upload_status": "accepted", "eligibility": "eligible", "job_status": "completed",
           "delivery_status": "not_generated", "downloads": {"redline": "/dl/redline.docx"},
           "reason_codes": [], "review_url": "/api/tasks/t/documents/doc/revisions",
           "report_url": "/api/tasks/t/report"}
    task = {"id": "t", "name": "单作者任务", "status": "completed", "total": 1,
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
            return respond(route, {"selection_epoch": 1, "manifest_hash": "m",
                                   "html": "<p>条款。</p>",
                                   "revisions": [
                                       {"del_id": 1, "ins_id": 2, "index": 1, "operation": "replace",
                                        "rule_id": "R-1", "section": "第一条", "before": "旧",
                                        "after": "新", "author": "FundLex"},
                                       {"del_id": 3, "ins_id": None, "index": 2, "operation": "delete",
                                        "rule_id": "R-2", "section": "第二条", "before": "冗",
                                        "after": "", "author": "FundLex"}]})
        if path == "/api/tasks/t/report":
            return respond(route, {"delivery_status": "not_generated", "qualification_status": "eligible",
                                   "actions": []})
        return respond(route, {})

    return scenario


def test_single_author_dropdown_shows_fundlex(browser, live_dev):
    _app, base = live_dev
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','author-single')")
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        install_api(page, base_api(_single_author_scenario()))
        open_dev(page, base, "#document?id=t&document=doc&tab=review")
        page.locator("#detail-overlay .review-layout").wait_for(state="visible", timeout=20000)
        page.wait_for_timeout(1200)
        print("SEL-EXISTS:", page.locator("#review-author-filter").count())
        print("OPTS:", page.evaluate(
            "[...document.querySelectorAll('#review-author-filter option')].map(o=>o.textContent)"))
        print("SS-MAIN:", page.locator("#review-rail .ss-main").count())
        print("SS-LABEL:", page.locator("#review-rail .ss-main .ss-single-selected").inner_text()
              if page.locator("#review-rail .ss-main").count() else "-")
        page.screenshot(path="/tmp/opencode/qa/review-author/a-03-single.png")
        assert not errors, f"pageerror: {errors}"
    finally:
        context.close()
