"""Standalone V1 generation workspace contracts; API mocks, no model calls.

Run: FUNDLEX_BROWSER_TESTS=1 .venv/bin/python -m pytest -q
     tests/browser/test_v1_generation_workspace.py
The miniature shell implements only the documented FundLexWorkbench contract.
"""
from __future__ import annotations

import copy
import json
import os
import re
import socket
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

pytestmark = pytest.mark.skipif(os.getenv("FUNDLEX_BROWSER_TESTS") != "1", reason="opt-in V1 Chromium suite")
ROOT = Path(__file__).resolve().parents[2]
BASE = "http://generation.test"
HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/static/app.css"><link rel="stylesheet" href="/static/guide_generation.css">
<style>body{height:auto;overflow:auto}.fixture-main{padding:20px;max-width:1200px;margin:auto}</style>
</head><body><main class="fixture-main"><section class="section" id="view-generation" aria-label="指引生成"><div id="gg-root"></div></section></main>
<div id="fixture-toast" role="status"></div><button id="fixture-parent" onclick="FundLexWorkbench.navigate('generation',{mode:'list'})">指引生成</button><script>
(() => {
  let epoch = 0, owner = 'owner-one', authenticated = true;
  window.fixtureDownloads = [];
  const headers = () => ({Authorization:'Bearer browser-fixture', 'X-Fixture-Owner':owner});
  const emit = () => {
    const [view, query] = location.hash.slice(1).split('?');
    const route = Object.fromEntries(new URLSearchParams(query || ''));
    document.querySelector('#view-generation').hidden = view !== 'generation';
    document.querySelector('#view-generation').classList.toggle('active', view === 'generation');
    document.dispatchEvent(new CustomEvent('fundlex:route', {detail:{view,...route}}));
  };
  window.FundLexWorkbench = {
    esc:value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
    authenticated:() => authenticated, epoch:() => epoch,
    appPath:path => path, toast:message => {document.querySelector('#fixture-toast').textContent = message;},
    json:async(path, options={}) => {
      const started = epoch;
      const response = await fetch(path, {...options,headers:{...headers(),...(options.headers || {})}});
      const body = await response.json();
      if (started !== epoch) throw new Error('identity changed');
      if (!response.ok) {const error=new Error(body.detail || `HTTP ${response.status}`);error.code=response.status;error.raw=body.detail;throw error;}
      return body;
    },
    navigate:(view, options={}) => {
      if(window.FundLexGuideGeneration?.hasUnsavedChanges() && !confirm('有未保存内容，是否离开？')) return;
      const next = '#' + view + '?' + new URLSearchParams(options);
      if(location.hash === next) emit(); else location.hash = next;
    },
    go:view => window.FundLexWorkbench.navigate(view),
    download:async(path, name) => {
      const started = epoch;
      const response = await fetch(path, {headers:headers()});
      if(!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      if(started !== epoch) return;
      const url = URL.createObjectURL(blob), anchor=document.createElement('a');
      anchor.href=url; anchor.download=name; anchor.click(); URL.revokeObjectURL(url);
      window.fixtureDownloads.push({path,name});
    },
  };
  window.fixtureReset = () => {epoch++; authenticated=false; owner='owner-two'; document.dispatchEvent(new Event('fundlex:identity-reset'));};
  window.fixtureLogin = () => {authenticated=true; emit();};
  window.addEventListener('hashchange',emit);
  window.addEventListener('DOMContentLoaded', emit);
})();
</script><script src="/static/guide_generation.js" defer></script></body></html>"""


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(headless=True)
        yield instance
        instance.close()


def item(item_id="GI-1", title="销售费用"):
    return {"guide_item_id": item_id, "title": title, "section": "费用",
            "business_requirement": "符合新规", "instruction": "修改相关收费约定", "applicability": "普通合同",
            "conditions": ["适用份额"], "exceptions": ["例外情形"], "old_text_patterns": ["原条款"],
            "new_text": "建议新条款", "new_text_origin": "model_drafted", "requirement_ids": ["REQ-1"],
            "impact_ids": ["IMP-1"], "quality_status": "pass", "coverage_status": "covered", "version": 1}


class MockGeneration:
    def __init__(self, page, *, base=BASE, api_only=False):
        self.page = page
        self.calls = []
        self.patches = []
        self.transitions = []
        self.downloads = []
        self.uploads = []
        self.list_queries = []
        self.list_items = None
        self.legacy_list = False
        self.resumes = []
        self.resume_error = None
        self.retry = {"attempts": 1, "max_attempts": 3, "can_resume": False}
        self.config = {}
        self.conflict = False
        self.hold = None
        self.held = []
        self.fail = set()
        self.candidate_status = "candidate_ready"
        self.qualification = "candidate_ready"
        self.run_status = "complete"
        self.items = [item(), item("GI-2", "赎回费用")]
        self.versions = [self.version(1, [item()], "draft"), self.version(2, self.items, "candidate_ready")]
        self.current = "version-2"
        page.route(base + ("/api/guide-generation/**" if api_only else "/**"), self.handle)

    @staticmethod
    def version(number, items, status, parent=""):
        return {"candidate_version_id": f"version-{number}", "version_no": number,
                "parent_version_id": parent or (f"version-{number-1}" if number > 1 else ""),
                "status": status, "created_at": 1793059200 + number, "content_sha256": str(number) * 64,
                "payload": {"guide_items": copy.deepcopy(items)}}

    def detail(self, run_id="run-one"):
        return {"id": run_id, "filename": "法规.docx", "title": "销售费用法规", "status": self.run_status,
                "stage": "BUILD_EVIDENCE", "qualification_status": self.qualification, "retry": self.retry, "config": self.config,
                "updated_at": 1793059200, "created_at": 1793059200,
                "corpus_snapshot_id": "snapshot-1", "regulation_document_sha256": "a" * 64,
                "guide_sha256": "b" * 64, "engine_status": "not_run",
                "candidate": {"status": self.candidate_status, "current_version_id": self.current,
                              "current_version_no": len(self.versions)},
                "stats": {"requirements": 1, "impacts": 51, "guide_items": len(self.items), "findings": 3},
                "stages": [{"stage": "INGEST_REGULATION", "status": "complete"},
                           {"stage": "EXTRACT_REQUIREMENTS", "status": "running"}],
                "summary": {"quality": {"run_status": "pass_with_findings"},
                            "finalize": {"critical_quality_findings": 1, "requirement_gaps": 2,
                                         "unresolved_impacts": 3, "latest_contract_uncertain": 4,
                                         "checklist": {"all_requirements_have_evidence": True,
                                                       "requirement_coverage_complete": False}}},
                "artifacts": {kind: f"/api/guide-generation/runs/{run_id}/download/{kind}"
                              for kind in ("guide", "guide_ai", "evidence_json", "evidence_html")}}

    def candidate(self):
        return {"status": self.candidate_status, "current_version_id": self.current, "versions": copy.deepcopy(self.versions)}

    def handle(self, route):
        request = route.request
        url = urlparse(request.url)
        if url.path == "/":
            return route.fulfill(body=HTML, content_type="text/html")
        if url.path.startswith("/static/"):
            path = ROOT / "frontend" / url.path.rsplit("/", 1)[1]
            return route.fulfill(body=path.read_text(), content_type="application/javascript" if path.suffix == ".js" else "text/css")
        if not url.path.startswith("/api/guide-generation"):
            return route.fulfill(status=404, json={"detail": "not found"})
        self.calls.append((request.method, url.path, request.headers))
        suffix = url.path.removeprefix("/api/guide-generation")
        if suffix in self.fail:
            return route.fulfill(status=503, json={"detail": "暂时不可用"})
        if suffix == "/corpus":
            payload = {"contracts": 514, "latest_contracts": 500, "parsed": 512, "parse_failed": 2,
                       "latest_snapshot": {"snapshot_id": "snapshot-1"}}
        elif suffix == "/runs" and request.method == "POST":
            self.uploads.append(request.post_data_buffer.decode("utf-8", errors="replace"))
            self.config = json.loads(re.search(r'name="config"\r\n\r\n([^\r\n]+)', self.uploads[-1])[1])
            payload = {**self.detail("new-run"), "status": "queued", "stage": "INGEST_REGULATION"}
        elif suffix == "/runs":
            params = parse_qs(url.query, keep_blank_values=True)
            self.list_queries.append(params)
            runs = self.list_items if self.list_items is not None else [self.detail(), {**self.detail("run-two"), "title": "另一法规", "status": "failed"}]
            if "page" in params and not self.legacy_list:
                q, status = params.get("q", [""])[0], params.get("status", [""])[0]
                runs = [run for run in runs if (not q or q in run["title"] or q in run["filename"]) and (not status or run["status"] == status)]
                page_number, page_size = int(params["page"][0]), int(params["page_size"][0])
                payload = {"items": runs[(page_number-1)*page_size:page_number*page_size], "total": len(runs), "page": page_number, "page_size": page_size}
            else:
                payload = {"items": runs[:int(params.get("limit", ["50"])[0])]}
        elif suffix in ("/runs/run-one", "/runs/new-run", "/runs/run-two"):
            payload = self.detail(suffix.rsplit("/", 1)[1])
        elif suffix.endswith("/resume"):
            self.resumes.append(request.headers)
            if self.resume_error:
                code, detail = self.resume_error
                return route.fulfill(status=code, json={"detail": detail})
            self.run_status = "queued"
            self.retry = {**self.retry, "can_resume": False}
            payload = self.detail()
        elif suffix.endswith("/requirements"):
            payload = {"items": [{"requirement_id": "REQ-1", "article": "第三条", "requirement": "调整费用",
                                  "source_quote": "法规原文 <script>window.injected=true</script>",
                                  "disposition": "modify_contract", "disposition_reason": "费率调整",
                                  "conditions": ["普通份额"], "exceptions": ["不适用例外"]}]}
        elif suffix.endswith("/guide") and "/download/" not in suffix:
            payload = {"items": self.items, "human_versions": [], "human_changes": [], "guide_sha256": "b" * 64}
        elif "/guide/items/" in suffix:
            body = request.post_data_json
            self.patches.append(body)
            if self.conflict:
                self.conflict = False
                return route.fulfill(status=409, json={"detail": "CANDIDATE_VERSION_CONFLICT"})
            assert body.pop("expected_current_version_id") == self.current
            item_id = suffix.rsplit("/", 1)[1]
            target = next(entry for entry in self.items if entry["guide_item_id"] == item_id)
            target.update(body, quality_status="human_review_pending")
            self.candidate_status = "human_draft"
            version = self.version(len(self.versions) + 1, self.items, "human_draft")
            self.current = version["candidate_version_id"]
            self.versions.append(version)
            payload = {"item": copy.deepcopy(target), "candidate_version": copy.deepcopy(version),
                       "guide_sha256": "c" * 64, "version_no": len(self.versions) - 2}
        elif suffix.endswith("/candidate"):
            payload = self.candidate()
        elif suffix.endswith("/candidate/approve") or suffix.endswith("/candidate/publish"):
            action = suffix.rsplit("/", 1)[1]
            body = request.post_data_json
            self.transitions.append((action, body))
            assert body == {"version_id": self.current}
            self.candidate_status = "approved" if action == "approve" else "published"
            self.versions[-1]["status"] = self.candidate_status
            payload = {"status": self.candidate_status, "version": self.versions[-1], "runtime_guide_import": "not_requested"}
        elif suffix.endswith("/impacts"):
            page = int(parse_qs(url.query).get("page", ["1"])[0])
            payload = {"total": 51, "page": page, "page_size": 50, "items": [{
                "impact_id": f"IMP-{page}", "requirement_id": "REQ-1", "contract_version_id": "contract-version-1",
                "impact_status": "possible", "source_text": "合同原文：原费用约定", "impact_reason": "需调整费率",
                "disposition": "unresolved", "disposition_reason": "尚需确认", "guide_item_ids": ["GI-1"]}]}
        elif suffix.endswith("/quality"):
            payload = {"summary": {"run_status": "pass_with_findings"}, "findings": [
                {"severity": "critical", "status": "open", "description": "收费范围需核对", "evidence_quote": "质量证据"},
                {"severity": "medium", "status": "open", "description": "一般质量问题"},
                {"severity": "critical", "status": "resolved", "description": "已解决的问题"}]}
        elif suffix.endswith("/coverage"):
            payload = {"summary": {}, "total": 5001, "items": [
                {"level": "requirement", "ref_id": "REQ-1", "status": "gap", "reason": "要求尚未覆盖"},
                {"level": "impact", "ref_id": "IMP-1", "status": "covered", "reason": "已处理"}], "applicability": [
                {"guide_item_id": "GI-1", "clause_id": "CL-1", "verdict": "ambiguous", "reason": "适用边界不明", "evidence_quote": "适用性原文"}]}
        elif suffix.endswith("/residual"):
            payload = {"summary": {"saturated": False, "status": "budget_exhausted"},
                       "rounds": [{"round_no": 1, "status": "complete", "new_patterns": 2, "new_impacts": 3,
                                   "uncovered": [{"pattern_description": "补漏发现费率模式", "reason": "条款缺失",
                                                  "evidence_quote": "补漏原文", "requirement_ids": ["REQ-1"],
                                                  "contract_version_id": "contract-version-1"}]}]}
        elif "/download/" in suffix:
            self.downloads.append(request.headers)
            return route.fulfill(body=b"mock-artifact", headers={"Content-Disposition": 'attachment; filename="fixture.docx"'})
        else:
            return route.fulfill(status=404, json={"detail": "not found"})
        if self.hold == suffix:
            self.held.append((route, copy.deepcopy(payload)))
            return
        return route.fulfill(json=copy.deepcopy(payload))


def workspace(browser, *, width=1440):
    context = browser.new_context(viewport={"width": width, "height": 1000}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    mock = MockGeneration(page)
    return context, page, mock, errors


def go(page, tab="overview", run_id="run-one"):
    page.goto(f"{BASE}/#generation?mode=detail&id={run_id}&tab={tab}")
    page.locator("#gg-detail-head h1").wait_for()


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_separate_list_new_detail_and_refresh(browser, width):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser, width=width)
    try:
        page.goto(BASE + "/#generation?mode=list")
        expect(page.locator("#gg-list-scope")).to_contain_text("当前账号共 2 个匹配任务")
        page.locator("#gg-query").fill("另一")
        page.locator("#gg-filter button[type=submit]").click()
        expect(page.locator(".gg-table tbody tr")).to_have_count(1)
        expect(page.locator(".gg-table tbody")).to_contain_text("另一法规")
        page.locator('[data-gg-action="new"]').click()
        expect(page.locator("#gg-create")).to_be_visible()
        expect(page.locator("#gg-list-results")).to_have_count(0)
        expect(page.locator("#gg-file")).to_be_hidden()
        expect(page.locator("#gg-submit")).to_be_disabled()
        page.locator("#gg-file").set_input_files({"name": "新监管规定.pdf", "mimeType": "application/pdf", "buffer": b"text-pdf-fixture"})
        expect(page.locator("#gg-task-name")).to_have_value("新监管规定")
        expect(page.locator("#gg-file-label")).to_contain_text("新监管规定.pdf")
        expect(page.locator("#gg-corpus")).to_contain_text("本次任务实际使用范围和快照以任务详情为准")
        assert "snapshot-1" not in page.locator("#gg-corpus").inner_text()
        assert page.locator("#gg-list-results").count() == 0
        page.locator("#gg-cost-ack").check()
        expect(page.locator("#gg-submit")).to_be_enabled()
        page.locator("#gg-submit").click()
        expect(page).to_have_url(__import__("re").compile(r"id=new-run"))
        expect(page.locator(".gg-tab")).to_have_text(["总览", "候选指引", "法规依据", "待处理问题", "版本与导出"])
        expect(page.locator("#gg-panel")).to_contain_text("不估算完成百分比")
        expect(page.locator("#gg-panel")).to_contain_text("生成结束后仍需完成候选核验")
        expect(page.locator("#gg-detail-head")).to_contain_text("候选门禁")
        expect(page.locator("#gg-detail-head")).to_contain_text("阶段")
        assert "候选资格" not in page.locator("#gg-detail-head").inner_text()
        assert "runtime_guide_import=not_requested" not in page.locator("#gg-panel").inner_text()
        assert len(mock.uploads) == 1
        assert '"path_b_latest_only":true' in mock.uploads[0]
        assert "run_engine_compatibility" not in mock.uploads[0]
        assert "corpus_limit" not in mock.uploads[0]
        assert "corpus_dir" not in mock.uploads[0] and "sample_contract" not in mock.uploads[0]
        page.reload()
        expect(page.locator("#gg-detail-head")).to_contain_text("销售费用法规")
        assert "id=new-run" in page.url
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()


def test_editor_cas_unsaved_navigation_and_conflict(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    try:
        go(page, "guide")
        editor = page.locator('[data-gg-field="new_text"]')
        editor.fill("人工新文 <script>window.injected=true</script>")
        expect(page.locator("#gg-dirty-count")).to_have_text("1 条未保存")
        assert page.evaluate("FundLexGuideGeneration.hasUnsavedChanges()")
        page.locator('[data-gg-item="GI-2"]').click()
        page.locator('[data-gg-field="title"]').fill("第二条人工标题")
        expect(page.locator("#gg-dirty-count")).to_have_text("2 条未保存")
        page.locator('[data-gg-item="GI-1"]').click()
        expect(editor).to_have_value("人工新文 <script>window.injected=true</script>")
        # Main shell periodically re-emits an unchanged route after capabilities refresh.
        page.evaluate("document.dispatchEvent(new CustomEvent('fundlex:route',{detail:{view:'generation',mode:'detail',id:'run-one',tab:'guide'}}))")
        expect(editor).to_have_value("人工新文 <script>window.injected=true</script>")
        expect(page.locator("#gg-dirty-count")).to_have_text("2 条未保存")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator('[data-gg-tab="versions"]').click()
        assert "tab=guide" in page.url
        expect(editor).to_have_value("人工新文 <script>window.injected=true</script>")
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-save-status")).to_contain_text("已保存为人工版本")
        assert mock.current == "version-3"
        expect(page.locator("#gg-dirty-count")).to_have_text("1 条未保存")
        page.locator('[data-gg-item="GI-2"]').click()
        expect(page.locator('[data-gg-field="title"]')).to_have_value("第二条人工标题")
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-dirty-count")).to_have_text("无未保存编辑")
        assert mock.current == "version-4"
        assert len(mock.patches) == 2
        mock.conflict = True
        page.locator('[data-gg-field="instruction"]').fill("发生冲突仍保留的编辑")
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-save-status")).to_contain_text("未保存编辑仍保留")
        expect(page.locator('[data-gg-field="instruction"]')).to_have_value("发生冲突仍保留的编辑")
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-action="discard"]').click()
        expect(page.locator("#gg-dirty-count")).to_have_text("无未保存编辑")
        assert page.evaluate("window.injected === undefined")
        assert errors == []
    finally:
        context.close()


def test_exact_approval_publication_download_and_readonly(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    try:
        go(page, "versions")
        expect(page.locator('[data-gg-transition="approve"]')).to_be_enabled()
        expect(page.locator('[data-gg-transition="publish"]')).to_be_disabled()
        expect(page.locator("#gg-panel")).to_contain_text("初始版本")
        expect(page.locator("#gg-version-diff")).to_contain_text("GI-2")
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-transition="approve"]').click()
        expect(page.locator('[data-gg-transition="publish"]')).to_be_enabled()
        assert mock.transitions == [("approve", {"version_id": "version-2"})]
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-transition="publish"]').click()
        expect(page.locator('[data-gg-transition="publish"]')).to_be_disabled()
        expect(page.locator("#gg-panel")).to_contain_text("runtime_guide_import=not_requested")
        expect(page.locator("#fixture-toast")).to_contain_text("尚未导入或启用")
        with page.expect_download() as artifact:
            page.locator('[data-gg-download="guide"]').click()
        assert artifact.value.suggested_filename == "generated_guide.docx"
        assert mock.downloads[0]["authorization"] == "Bearer browser-fixture"
        assert mock.downloads[0]["x-fixture-owner"] == "owner-one"
        assert all("token" not in href.lower() for href in page.locator("a").evaluate_all("nodes=>nodes.map(n=>n.href)"))
        page.locator('[data-gg-tab="guide"]').click()
        expect(page.locator('[data-gg-field="new_text"]')).to_be_disabled()
        expect(page.locator("#gg-panel")).to_contain_text("已发布版本")
        assert errors == []
    finally:
        context.close()


def test_findings_never_show_ready_or_approvable(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    mock.qualification = "candidate_with_findings"
    mock.run_status = "complete_with_unresolved"
    try:
        go(page, "versions")
        expect(page.locator('[data-gg-transition="approve"]')).to_be_disabled()
        expect(page.locator("#gg-panel")).to_contain_text("不作为 AI 候选可批准的依据")
        page.locator('[data-gg-tab="issues"]').click()
        expect(page.locator("#gg-panel")).to_contain_text("待处理 2 条，其中关键 1 条")
        expect(page.locator("#gg-panel")).to_contain_text("存在未展示记录")
        expect(page.locator("#gg-panel")).to_contain_text("预算已用尽")
        expect(page.locator("#gg-panel")).to_contain_text("不是对完整性的 100% 证明")
        expect(page.locator("#gg-panel")).to_contain_text("适用边界不明")
        page.get_by_text("第 1 轮", exact=True).click()
        expect(page.locator("#gg-panel")).to_contain_text("补漏发现费率模式")
        expect(page.locator("#gg-panel")).to_contain_text("补漏原文")
        assert not any(method == "POST" for method, _, _ in mock.calls)
        assert errors == []
    finally:
        context.close()


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_regulation_and_impact_quotes_pagination_and_responsive_editor(browser, width):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser, width=width)
    try:
        go(page, "requirements")
        page.locator(".gg-requirement summary").first.click()
        expect(page.locator(".gg-quote").first).to_contain_text("法规原文 <script>")
        expect(page.locator("#gg-impacts")).to_contain_text("IMP-1")
        page.locator('#gg-impacts [data-gg-page="2"]').click()
        expect(page.locator("#gg-impacts")).to_contain_text("IMP-2")
        page.locator("#gg-impacts summary").click()
        expect(page.locator("#gg-impacts .gg-quote")).to_contain_text("合同原文：原费用约定")
        expect(page.locator('#gg-impacts [data-gg-page="3"]')).to_be_disabled()
        page.locator('[data-gg-tab="guide"]').click()
        expect(page.locator("#gg-editor")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator('[data-gg-field="new_text"]').fill("窄屏人工编辑")
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-save-status")).to_contain_text("已保存")
        assert page.evaluate("window.injected === undefined")
        assert errors == []
    finally:
        context.close()


def test_route_and_identity_cancel_late_data_and_mutation(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    try:
        mock.hold = "/runs/run-one/guide"
        go(page, "guide")
        page.wait_for_function("document.querySelector('#gg-panel')?.textContent.includes('正在读取')")
        page.locator('[data-gg-tab="overview"]').click()
        expect(page.locator("#gg-panel")).to_contain_text("处理进度")
        assert mock.held
        held_route, held_payload = mock.held.pop()
        held_route.fulfill(json=held_payload)
        expect(page.locator("#gg-panel")).to_contain_text("处理进度")
        expect(page.locator("#gg-editor")).to_have_count(0)
        mock.hold = None
        page.locator('[data-gg-tab="guide"]').click()
        page.locator('[data-gg-field="instruction"]').fill("旧账号尚未提交的内容")
        mock.hold = "/runs/run-one/guide/items/GI-1"
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-save-status")).to_have_text("保存中…")
        page.evaluate("fixtureReset()")
        expect(page.locator("#gg-root")).to_be_empty()
        held_route, held_payload = mock.held.pop()
        held_route.fulfill(json=held_payload)
        expect(page.locator("#gg-root")).to_be_empty()
        assert not page.evaluate("FundLexGuideGeneration.hasUnsavedChanges()")
        mock.hold = None
        page.evaluate("fixtureLogin()")
        expect(page.locator("#gg-editor")).to_be_visible()
        assert mock.calls[-1][2]["x-fixture-owner"] == "owner-two"
        assert errors == []
    finally:
        context.close()


def test_running_poll_uses_real_stages_and_stops_when_leaving(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    mock.run_status = "running"
    try:
        page.clock.install()
        go(page)
        expect(page.locator("#gg-panel")).to_contain_text("法规读取")
        expect(page.locator("#gg-panel")).to_contain_text("要求提取")
        expect(page.locator("#gg-panel")).not_to_contain_text("INGEST_REGULATION")
        original = sum(path == "/api/guide-generation/runs/run-one" for _, path, _ in mock.calls)
        page.clock.fast_forward(5100)
        page.wait_for_function("document.querySelector('#gg-panel')?.textContent.includes('处理进度')")
        assert sum(path == "/api/guide-generation/runs/run-one" for _, path, _ in mock.calls) > original
        page.evaluate("FundLexWorkbench.navigate('workspace')")
        current = len(mock.calls)
        page.clock.fast_forward(15000)
        page.wait_for_timeout(30)
        assert len(mock.calls) == current
        assert errors == []
    finally:
        context.close()


def test_server_pagination_search_status_page2_refresh_and_return(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser, width=390)
    mock.list_items = [{**mock.detail(f"paged-{i}"), "title": f"分页法规 {i}", "status": "paused"} for i in range(1, 26)]
    try:
        page.goto(BASE + "/#generation?mode=list")
        expect(page.locator("#gg-list-scope")).to_contain_text("25 个匹配任务")
        page.locator("#gg-query").fill("分页法规")
        page.locator("#gg-status").select_option("paused")
        page.locator('#gg-filter button[type="submit"]').click()
        expect(page.locator(".gg-table tbody tr")).to_have_count(20)
        page.locator('[data-gg-list-page="2"]').click()
        expect(page.locator(".gg-table tbody tr")).to_have_count(5)
        expect(page.locator(".gg-table tbody")).to_contain_text("分页法规 21")
        assert parse_qs(urlparse(page.url).fragment.split("?", 1)[1])["page"] == ["2"]
        page.reload()
        expect(page.locator("#gg-list-scope")).to_contain_text("第 2 页")
        expect(page.locator("#gg-query")).to_have_value("分页法规")
        expect(page.locator("#gg-status")).to_have_value("paused")
        expect(page.locator(".gg-table tbody tr")).to_have_count(5)
        assert mock.list_queries[-1] == {"page": ["2"], "page_size": ["20"], "q": ["分页法规"], "status": ["paused"]}
        expect(page.locator("#gg-list-scope")).not_to_contain_text("200")
        page.locator('[data-gg-action="new"]').click()
        page.locator('#fixture-parent').click()
        expect(page.locator("#gg-list-scope")).to_contain_text("第 2 页")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()


def test_visible_corpus_limit_validates_integer_scope_and_sends_one(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser, width=390)
    try:
        page.goto(BASE + "/#generation?mode=new")
        page.locator(".gg-advanced summary").click()
        scope = page.get_by_label("参考合同样本上限（选填）", exact=True)
        expect(scope).to_have_attribute("type", "number")
        expect(scope).to_have_attribute("min", "1")
        expect(scope).to_have_attribute("max", "10000")
        expect(scope).to_have_value("")
        expect(page.locator("#gg-corpus-limit-hint")).to_contain_text("不代表全库覆盖")
        expect(page.locator("#gg-corpus-limit-hint")).to_contain_text("不是费用上限")
        page.locator("#gg-file").set_input_files({"name": "有限范围法规.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "buffer": b"scope-upload-fixture"})
        page.locator("#gg-cost-ack").check()
        expect(page.locator("#gg-submit")).to_be_enabled()
        for value in ("0", "-1", "10001", "1.5", "1e3", "e"):
            scope.fill("")
            if value == "e":
                scope.press("e")
            else:
                scope.fill(value)
            expect(scope).to_have_attribute("aria-invalid", "true")
            expect(page.locator("#gg-corpus-limit-error")).to_contain_text("整数")
            expect(page.locator("#gg-submit")).to_be_disabled()
            # The handler also guards scripted submits, not just native validation.
            page.locator("#gg-create").evaluate("form=>form.dispatchEvent(new Event('submit',{bubbles:true,cancelable:true}))")
            assert mock.uploads == []
        scope.fill("10000")
        expect(page.locator("#gg-submit")).to_be_enabled()
        scope.fill("")
        expect(page.locator("#gg-submit")).to_be_enabled()
        expect(page.locator("#gg-corpus-limit-error")).to_be_empty()
        scope.fill("1")
        page.locator("#gg-submit").click()
        expect(page.locator("#gg-run-scope")).to_contain_text("样本上限：1 份")
        expect(page.locator("#gg-run-scope")).to_contain_text("不代表全库覆盖")
        assert mock.config == {"path_b_latest_only": True, "corpus_limit": 1}
        assert type(mock.config["corpus_limit"]) is int
        page.reload()
        expect(page.locator("#gg-run-scope")).to_contain_text("不代表全库覆盖")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()


def test_legacy_backend_keeps_bounded_scope_without_false_pagination(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    mock.legacy_list = True
    try:
        page.goto(BASE + "/#generation?mode=list&page=2&q=另一&status=failed")
        expect(page.locator("#gg-list-scope")).to_contain_text("未返回可靠分页信息")
        expect(page.locator("#gg-list-scope")).to_contain_text("不代表全量任务统计")
        expect(page.locator(".gg-table tbody tr")).to_have_count(1)
        expect(page.locator("#gg-list-pages")).to_be_empty()
        assert mock.list_queries[-1] == {"limit": ["200"]}
        assert errors == []
    finally:
        context.close()


@pytest.mark.parametrize("run_status", ["paused", "failed"])
def test_explicit_resume_counts_budget_pending_and_owner(browser, run_status):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    mock.run_status = run_status
    mock.retry["can_resume"] = True
    mock.hold = "/runs/run-one/resume"
    try:
        go(page)
        expect(page.locator(".gg-retry")).to_contain_text("处理尝试 1 / 3 次")
        expect(page.locator(".gg-retry")).to_contain_text("消耗预算")
        expect(page.locator(".gg-retry")).to_contain_text("不会自动执行付费重试")
        assert mock.resumes == []
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator('[data-gg-action="resume"]').click()
        assert mock.resumes == []
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-action="resume"]').click()
        expect(page.locator('[data-gg-action="resume"]')).to_be_disabled()
        expect(page.locator("#gg-resume-status")).to_contain_text("请勿重复操作")
        page.locator('[data-gg-action="resume"]').evaluate("button=>button.click()")
        assert len(mock.resumes) == 1
        assert mock.resumes[0]["x-fixture-owner"] == "owner-one"
        assert mock.resumes[0]["authorization"] == "Bearer browser-fixture"
        assert page.evaluate("FundLexGuideGeneration.hasUnsavedChanges()")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator('#fixture-parent').click()
        expect(page.locator("#gg-resume-status")).to_contain_text("请勿重复操作")
        held_route, payload = mock.held.pop()
        mock.hold = None
        held_route.fulfill(status=202, json=payload)
        expect(page.locator(".gg-task-status")).to_contain_text("排队中")
        expect(page.locator('[data-gg-action="resume"]')).to_have_count(0)
        mock.run_status = "failed"
        mock.retry = {"attempts": 3, "max_attempts": 3, "can_resume": False}
        page.locator('[data-gg-action="refresh"]').click()
        expect(page.locator(".gg-retry")).to_contain_text("处理尝试 3 / 3 次")
        expect(page.locator('[data-gg-action="resume"]')).to_have_count(0)
        assert len(mock.resumes) == 1
        assert errors == []
    finally:
        context.close()


@pytest.mark.parametrize("code,detail,expected", [
    (404, "guide generation run not found", "当前账号无权访问"),
    (401, "session expired", "登录状态已失效"),
    (409, "GUIDE_RETRY_LIMIT", "处理尝试次数上限"),
    (409, "GUIDE_RUN_NOT_RESUMABLE", "不会自动重试"),
])
def test_resume_owner_and_state_errors_are_not_automatically_retried(browser, code, detail, expected):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    mock.run_status = "failed"
    mock.retry["can_resume"] = True
    mock.resume_error = (code, detail)
    try:
        go(page)
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-action="resume"]').click()
        expect(page.locator("#gg-resume-status")).to_contain_text(expected)
        expect(page.locator('[data-gg-action="resume"]')).to_be_enabled()
        assert len(mock.resumes) == 1
        assert not page.evaluate("FundLexGuideGeneration.hasUnsavedChanges()")
        assert errors == []
    finally:
        context.close()


def test_resume_identity_reset_discards_late_response(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    mock.run_status = "paused"
    mock.retry["can_resume"] = True
    mock.hold = "/runs/run-one/resume"
    try:
        go(page)
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-action="resume"]').click()
        expect(page.locator("#gg-resume-status")).to_contain_text("正在请求")
        page.evaluate("fixtureReset()")
        held_route, payload = mock.held.pop()
        held_route.fulfill(status=202, json=payload)
        expect(page.locator("#gg-root")).to_be_empty()
        expect(page.locator("#fixture-toast")).to_be_empty()
        assert len(mock.resumes) == 1
        assert not page.evaluate("FundLexGuideGeneration.hasUnsavedChanges()")
        assert errors == []
    finally:
        context.close()


def test_findings_candidate_can_be_human_edited_without_activation_claim(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    mock.qualification = mock.candidate_status = "candidate_with_findings"
    mock.versions[-1]["status"] = "candidate_with_findings"
    mock.run_status = "complete_with_unresolved"
    try:
        go(page, "guide")
        page.locator('[data-gg-field="instruction"]').fill("人工确认后的指令")
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-save-status")).to_contain_text("已保存为人工版本")
        assert mock.versions[-1]["status"] == "human_draft"
        page.locator('[data-gg-tab="versions"]').click()
        expect(page.locator('[data-gg-transition="approve"]')).to_be_enabled()
        expect(page.locator("#gg-panel")).to_contain_text("未自动重跑模型核验")
        expect(page.locator("#gg-panel")).to_contain_text("runtime_guide_import=not_requested")
        expect(page.locator('[data-gg-transition="publish"]')).to_be_disabled()
        assert mock.transitions == []
        assert errors == []
    finally:
        context.close()


def test_partial_errors_empty_guide_and_invalid_file(browser):
    from playwright.sync_api import expect
    context, page, mock, errors = workspace(browser)
    try:
        mock.fail.add("/runs/run-one/quality")
        go(page, "issues")
        expect(page.locator("#gg-panel")).to_contain_text("质量核验读取失败")
        expect(page.locator("#gg-panel")).to_contain_text("要求尚未覆盖")
        mock.items = []
        page.locator('[data-gg-tab="guide"]').click()
        expect(page.locator("#gg-panel")).to_contain_text("尚无候选指引")
        page.locator('#fixture-parent').click()
        page.locator('[data-gg-action="new"]').click()
        page.locator("#gg-file").set_input_files({"name": "错误.txt", "mimeType": "text/plain", "buffer": b"invalid"})
        expect(page.locator("#gg-submit")).to_be_disabled()
        expect(page.locator("#fixture-toast")).to_contain_text("80 MB")
        assert mock.uploads == []
        assert errors == []
    finally:
        context.close()


@pytest.fixture
def live_shell(tmp_path, monkeypatch):
    """Actual V1 shell/backend with generation HTTP intercepted; no Worker."""
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
    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()


@pytest.mark.parametrize("width", [390, 768, 1440])
def test_real_v1_shell_deep_link_and_preserved_editor(browser, live_shell, width):
    from playwright.sync_api import expect
    context = browser.new_context(viewport={"width": width, "height": 1000})
    context.add_init_script("localStorage.setItem('fundlex-dev-user','v1-generation-check')")
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    mock = MockGeneration(page, base=live_shell, api_only=True)
    try:
        page.goto(live_shell + "/#generation?mode=detail&id=run-one&tab=guide")
        expect(page.locator("#gg-editor")).to_be_visible()
        expect(page.locator('.nav-btn[data-nav="generation"]')).to_have_class(__import__("re").compile("active"))
        expect(page.locator('h1:visible')).to_have_count(1)
        expect(page.locator('#breadcrumb [aria-current="page"]')).to_have_text('任务详情')
        expect(page.locator('.topbar h1')).to_have_count(0)
        editor = page.locator('[data-gg-field="new_text"]')
        editor.fill("真实 V1 壳中的未保存修订")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator('#breadcrumb [data-crumb="generation"]').click()
        expect(editor).to_have_value("真实 V1 壳中的未保存修订")
        page.evaluate("document.dispatchEvent(new CustomEvent('fundlex:route',{detail:FundLexWorkbench.route()}))")
        expect(editor).to_have_value("真实 V1 壳中的未保存修订")
        page.once("dialog", lambda dialog: dialog.dismiss())
        page.locator('[data-gg-tab="versions"]').click()
        expect(editor).to_have_value("真实 V1 壳中的未保存修订")
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-save-status")).to_contain_text("已保存")
        mock.conflict = True
        page.locator('[data-gg-field="instruction"]').fill("真实共享 helper 的冲突保留")
        page.locator('[data-gg-action="save"]').click()
        expect(page.locator("#gg-save-status")).to_contain_text("未保存编辑仍保留")
        expect(page.locator('[data-gg-field="instruction"]')).to_have_value("真实共享 helper 的冲突保留")
        page.once("dialog", lambda dialog: dialog.accept())
        page.locator('[data-gg-action="discard"]').click()
        expect(page.locator("#gg-dirty-count")).to_have_text("无未保存编辑")
        page.locator('[data-gg-tab="versions"]').click()
        expect(page.locator("#gg-panel")).to_contain_text("runtime_guide_import=not_requested")
        assert mock.patches
        assert mock.calls[-1][2]["x-fundlex-user"] == "v1-generation-check"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert errors == []
    finally:
        context.close()


def test_real_shell_detail_error_keeps_unique_heading_and_parent_navigation(browser, live_shell):
    from playwright.sync_api import expect
    context = browser.new_context()
    page = context.new_page()
    mock = MockGeneration(page, base=live_shell, api_only=True)
    mock.fail.add('/runs/run-one')
    try:
        page.goto(live_shell + '/#generation?mode=detail&id=run-one')
        expect(page.locator('#gg-detail-error [role="alert"]')).to_be_visible()
        expect(page.locator('h1:visible')).to_have_count(1)
        expect(page.locator('h1:visible')).to_have_text('任务暂不可用')
        page.locator('#breadcrumb [data-crumb="generation"]').click()
        expect(page.locator('#gg-filter')).to_be_visible()
        expect(page.locator('h1:visible')).to_have_count(1)
    finally:
        context.close()
