#!/usr/bin/env python3
"""Opt-in real deployed V1 browser acceptance, one independently runnable phase.

No mocks, API-created tasks, hidden feature flags, automatic model retries, or
stored credentials. Each invocation creates its own disposable e2e-v1ws account
through the UI and logs out/in through the UI. Revision/generation require an
explicit registered budget reference and --allow-model-calls. Smoke/compare do
not invoke models. A timeout/failure is evidence, never a successful delivery.

Example (after deployment/budget registration):
  python verify_v1_three_business_e2e.py --phase compare --out /path/evidence
  python cleanup_v1_three_business_e2e.py --username NAME --evidence .../result.json

Passwords/tokens live only in RAM and the ephemeral browser's session storage.
No HAR, trace, persistent profile, storage-state, or raw exception is saved.
Downloaded contracts/reports are public work products, not authentication data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile

from lxml import etree
from playwright.sync_api import expect, sync_playwright


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
WIDTHS = (1440, 1280, 768, 390)
COMPARE_INPUTS = Path("/tmp/opencode/compare-selection-prod-e2e/real-clean")
DEFAULT_CONTRACT = Path("/home/opencode/data/funds_word/广发品质回报混合型证券投资基金基金合同_20230708.docx")


class AcceptanceFailure(RuntimeError):
    pass


def require(value, code):
    if not value:
        raise AcceptanceFailure(code)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def docx(path: Path, *, reject=False):
    with ZipFile(path) as archive:
        require(archive.testzip() is None, "DOCX_CORRUPT_ZIP")
        root = etree.fromstring(archive.read("word/document.xml"), parser=etree.XMLParser(resolve_entities=False, no_network=True))
    query = ".//w:t[not(ancestor::w:ins)] | .//w:delText" if reject else ".//w:t[not(ancestor::w:del)]"
    paragraphs = ["".join(n.text or "" for n in p.xpath(query, namespaces=NS))
                  for p in root.xpath("//w:body//w:p", namespaces=NS)]
    return {"paragraphs": [p for p in paragraphs if p],
            "insertions": len(root.xpath("//w:ins", namespaces=NS)),
            "deletions": len(root.xpath("//w:del", namespaces=NS))}


def validate_redline(source, final, redline):
    before, after, tracked, rejected = docx(source), docx(final), docx(redline), docx(redline, reject=True)
    require(before["paragraphs"] != after["paragraphs"], "NO_ACTUAL_CONTRACT_CHANGE")
    require(tracked["insertions"] + tracked["deletions"] > 0, "REDLINE_HAS_NO_TRACKED_CHANGES")
    require(tracked["paragraphs"] == after["paragraphs"], "ACCEPTED_REDLINE_DIFFERS_FROM_FINAL")
    require(rejected["paragraphs"] == before["paragraphs"], "REJECTED_REDLINE_DIFFERS_FROM_SOURCE")
    require(not after["insertions"] and not after["deletions"], "FINAL_HAS_UNACCEPTED_REVISIONS")
    return {"actual_text_changed": True, "accepted_redline_matches_final": True,
            "rejected_redline_matches_source": True, "insertions": tracked["insertions"],
            "deletions": tracked["deletions"], "source_paragraphs": len(before["paragraphs"]),
            "final_paragraphs": len(after["paragraphs"])}


class Runner:
    def __init__(self, args, page, context, evidence, output):
        self.args, self.page, self.context = args, page, context
        self.result, self.out = evidence, output
        self.step = "initialization"
        self.page.on("response", self.observe_creation)
        self.page.on("pageerror", lambda error: self.result.__setitem__("page_error_count", self.result["page_error_count"] + 1))

    def checkpoint(self):
        (self.out / "result.json").write_text(json.dumps(self.result, ensure_ascii=False, indent=2) + "\n")

    def observe_creation(self, response):
        # Record ownership IDs as soon as creation succeeds, even if later UI
        # rendering fails. Do not keep auth response/token/request payloads.
        if response.request.method != "POST" or response.status not in (200, 201, 202):
            return
        path = urlsplit(response.url).path
        if path == self.api_path("/api/auth/register"):
            self.result["uid"] = response.json().get("user", {}).get("id")
            self.checkpoint()
        for kind, endpoint in (("revision", "/api/tasks"), ("compare", "/api/compare/tasks"), ("generation", "/api/guide-generation/runs")):
            if path == self.api_path(endpoint):
                body = response.json()
                task_id = body.get("id") or (body.get("task") or {}).get("id")
                if task_id and task_id not in self.result["task_ids"][kind]:
                    self.result["task_ids"][kind].append(task_id)
                    self.checkpoint()

    def api_path(self, path):
        return urlsplit(self.args.base).path.rstrip("/") + path

    def get(self, path):
        # Read-only evidence from the browser's own authenticated session.
        answer = self.page.evaluate("""async path => {
          const token=sessionStorage.getItem('fundlex-auth-token');
          const response=await fetch(path,{headers:token?{Authorization:`Bearer ${token}`}:{},cache:'no-store'});
          return {status:response.status,body:await response.json()};
        }""", self.api_path(path))
        require(answer["status"] == 200, f"EVIDENCE_GET_HTTP_{answer['status']}")
        return answer["body"]

    def route(self, fragment, selector):
        self.page.goto(self.args.base.rstrip("/") + "/" + fragment, wait_until="domcontentloaded")
        expect(self.page.locator(selector)).to_be_visible()

    def deep_reload(self, fragment, selector):
        self.route(fragment, selector)
        self.page.reload(wait_until="domcontentloaded")
        expect(self.page.locator(selector)).to_be_visible()
        require(self.page.evaluate("location.hash") == fragment, "DEEP_LINK_NOT_PRESERVED")
        self.result.setdefault("deep_reload", []).append(fragment)

    def screenshot(self, name):
        self.page.screenshot(path=str(self.out / f"{name}.png"), full_page=True,
                             mask=[self.page.locator("input[type=password], #login-username, #register-username, #register-display, #feishu-oauth-qr, .user-info, #user-menu")])

    def responsive(self, name, *, compare=False):
        metrics = {}
        for width in WIDTHS:
            self.page.set_viewport_size({"width": width, "height": 1000})
            self.page.wait_for_timeout(150)
            data = self.page.evaluate("""() => ({width:innerWidth,
              document:document.documentElement.scrollWidth,body:document.body.scrollWidth,
              overflow:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)>innerWidth+1})""")
            require(not data["overflow"], f"HORIZONTAL_OVERFLOW_{name}_{width}")
            location = self.page.evaluate("""() => {
              const bar=document.querySelector('.topbar').getBoundingClientRect();
              const crumb=document.querySelector('.topbar #breadcrumb').getBoundingClientRect();
              const leaf=document.querySelector('#breadcrumb [aria-current=page]').getBoundingClientRect();
              return {visible:crumb.height>0 && crumb.width>0,
                inside:crumb.top>=bar.top && crumb.bottom<=bar.bottom+1 && leaf.right<=crumb.right+1,
                headings:[...document.querySelectorAll('h1')].filter(n=>n.getClientRects().length).length};
            }""")
            require(location["visible"] and location["inside"], f"TOPBAR_LOCATION_NOT_VISIBLE_{width}")
            require(location["headings"] == 1, f"DUPLICATE_OR_MISSING_PAGE_HEADING_{width}")
            data["location"] = location
            if compare:
                rail = self.page.evaluate("""() => {
                  const d=document.querySelector('.compare-document-area').getBoundingClientRect();
                  const r=document.querySelector('.compare-diff-rail').getBoundingClientRect();
                  return {right:r.x>=d.right-1,before:r.bottom<=d.top+1};
                }""")
                require(rail["right"] if width > 760 else rail["before"], "COMPARE_DIFF_RAIL_POSITION")
                data["rail"] = rail
            metrics[str(width)] = data
            self.screenshot(f"{name}-{width}")
        self.result.setdefault("viewports", {})[name] = metrics
        self.page.set_viewport_size({"width": 1440, "height": 1000})
        self.checkpoint()

    def parent(self, parent, selector):
        self.page.locator(f'#breadcrumb [data-crumb="{parent}"]').click()
        expect(self.page.locator(selector)).to_be_visible()
        self.result.setdefault("parent_navigation", []).append(parent)

    def login(self):
        self.step = "register_and_actual_ui_login"
        page = self.page
        password = secrets.token_urlsafe(24)
        self.route("#workspace", "#login-view")
        page.locator("#register-link").click()
        page.locator("#register-username").fill(self.result["username"])
        page.locator("#register-display").fill("V1三业务验收")
        page.locator("#register-password").fill(password)
        page.locator("#register-confirm").fill(password)
        page.locator("#register-submit").click()
        expect(page.locator("#login-view")).to_be_hidden()
        page.locator("#logout-btn").click()
        expect(page.locator("#login-view")).to_be_visible()
        page.locator("#login-username").fill(self.result["username"])
        page.locator("#login-password").fill(password)
        page.locator("#login-submit").click()
        expect(page.locator("#login-view")).to_be_hidden()
        del password
        user = self.get("/api/auth/me")
        require(user["username"] == self.result["username"], "UI_LOGIN_WRONG_IDENTITY")
        self.result.update(uid=user["id"], ui_registered=True, ui_reauthenticated=True)
        # Never serialize browser storage. Application login already clears its
        # password inputs; explicitly clear residual registration DOM fields.
        page.locator("#register-password").fill("") if page.locator("#register-password").is_visible() else None
        page.evaluate("document.querySelectorAll('input[type=password]').forEach(n=>n.value='')")
        self.checkpoint()

    def smoke(self):
        self.step = "smoke_routes"
        for fragment, selector, parent in (
            ("#workspace", "#view-workspace", None),
            ("#overview", "#view-overview", None),
            ("#import", "#view-import", "overview"),
            ("#compare?mode=list", "#compare-new", None),
            ("#compare?mode=new", "#compare-submit", "compare"),
            ("#generation?mode=list", "#gg-filter", None),
            ("#generation?mode=new", "#gg-create", "generation"),
            ("#guide", "#guide-current-body", None),
            ("#settings", "#feishu-connect-card", None),
        ):
            self.deep_reload(fragment, selector)
            require(self.page.locator('.main #breadcrumb, .main h1:visible, .main .eyebrow:visible').count() == 0,
                    "REPEATED_CONTENT_PAGE_HEADING")
            self.responsive(re.sub(r"[^a-z0-9]+", "-", fragment).strip("-"))
            if parent:
                self.parent(parent, {"workspace": "#view-workspace", "overview": "#view-overview",
                                     "compare": "#compare-new", "generation": "#gg-filter"}[parent])
        self.result["delivery_scope"] = "navigation_only_no_business_task_or_model_call"

    def filechooser(self, selector, path):
        with self.page.expect_file_chooser() as pending:
            self.page.locator(selector).first.click()
        pending.value.set_files(str(path.resolve()))

    def task_id(self, kind):
        ids = self.result["task_ids"][kind]
        require(len(ids) == 1, "EXPECTED_EXACTLY_ONE_UI_CREATED_TASK")
        return ids[0]

    def wait(self, kind, endpoint, terminal):
        self.step = f"wait_{kind}_real_worker"
        deadline = time.monotonic() + self.args.wait_minutes * 60
        while True:
            body = self.get(endpoint)
            status = body.get("status")
            self.result.setdefault("worker", {})[kind] = {key: body.get(key) for key in ("id", "status", "stage", "error_code", "qualification_status")}
            self.checkpoint()
            if status in terminal:
                return body
            require(status not in {"failed", "paused", "retry_wait"}, f"{kind.upper()}_STOPPED_{status}")
            require(time.monotonic() < deadline, f"{kind.upper()}_FINITE_WAIT_EXPIRED")
            self.page.wait_for_timeout(min(5000, max(1, (deadline - time.monotonic()) * 1000)))

    def download(self, selector, kind, suffix):
        button = self.page.locator(selector).first
        expect(button).to_be_visible()
        with self.page.expect_download(timeout=120000) as pending:
            button.click()
        target = self.out / (kind + suffix)
        pending.value.save_as(target)
        self.result.setdefault("downloads", {})[kind] = {"sha256": sha(target), "bytes": target.stat().st_size}
        return target

    def download_auth(self, path):
        require(path and path.startswith("/"), "DOWNLOAD_URL_MISSING")
        # Browser UI supplies the authorized download above. This isolated HTTP
        # request deliberately has no session token and must be denied.
        response = self.context.request.get(self.args.base.rstrip("/") + path.removeprefix(urlsplit(self.args.base).path.rstrip("/")))
        require(response.status == 401, "UNAUTHENTICATED_DOWNLOAD_NOT_DENIED")
        self.result["unauthenticated_download_http"] = response.status

    def compare(self):
        self.step = "compare_real_upload"
        left, right = self.args.left, self.args.right
        self.route("#compare?mode=list", "#compare-new")
        self.page.locator("#compare-new").click()
        expect(self.page.locator("#compare-submit")).to_be_visible()
        self.page.locator("#compare-name").fill("真实公开合同·三业务比对验收")
        for side, path in (("left", left), ("right", right)):
            self.filechooser(f'[data-compare-choose="{side}"]', path)
            expect(self.page.locator(f'[data-file-side="{side}"] .compare-file-name')).to_have_text(path.name)
        self.responsive("compare-upload")
        with self.page.expect_response(lambda r: r.url.endswith("/seal") and r.request.method == "POST", timeout=120000):
            self.page.locator("#compare-submit").click()
        task_id = self.task_id("compare")
        task = self.wait("compare", f"/api/compare/tasks/{task_id}", {"completed", "completed_with_exceptions", "succeeded", "failed"})
        pairs = task.get("pairs") or []
        require(len(pairs) == 1 and pairs[0].get("status") == "succeeded", "COMPARE_PAIR_NOT_COMPLETE")
        self.result["pair_ids"] = [pairs[0]["id"]]
        fragment = f"#compare?mode=detail&id={task_id}"
        self.deep_reload(fragment, "#compare-viewer")
        choices = self.page.locator('[data-selection-choice="right"]')
        expect(choices.first).to_be_enabled()
        require(choices.count() > 0, "COMPARE_NO_REAL_DIFFERENCES")
        for index in range(choices.count()):
            self.page.locator('[data-selection-choice="right"]').nth(index).check()
            expect(self.page.locator("#compare-selection-status")).to_have_text("已保存")
        self.page.reload(wait_until="domcontentloaded")
        for choice in self.page.locator('[data-selection-choice="right"]').all():
            expect(choice).to_be_checked()
        with self.page.expect_response(lambda r: r.url.endswith("/selection/generate"), timeout=120000) as generated:
            self.page.locator("#compare-selection-generate").click()
        require(generated.value.status == 200, "COMPARE_SELECTION_GENERATION_FAILED")
        self.step = "compare_actual_artifacts"
        for kind, suffix in (("selected_final", ".docx"), ("selected_redline", ".docx"),
                             ("selection_report_json", ".json"), ("selection_report_markdown", ".md")):
            self.download(f'[data-selection-download$="/{kind}"]', kind, suffix)
        report = json.loads((self.out / "selection_report_json.json").read_text())
        for kind in ("selected_final", "selected_redline"):
            require(sha(self.out / f"{kind}.docx") == report["outputs"][kind]["sha256"], "COMPARE_REPORT_HASH_MISMATCH")
        require(docx(self.out / "selected_final.docx")["paragraphs"] == docx(right)["paragraphs"], "COMPARE_FINAL_DIFFERS_FROM_CHOSEN_RIGHT")
        self.result["docx_validation"] = validate_redline(left, self.out / "selected_final.docx", self.out / "selected_redline.docx")
        self.result["report_hashes_match"] = True
        self.download_auth(self.page.locator('[data-selection-download$="/selected_final"]').get_attribute("data-selection-download"))
        self.responsive("compare-reader", compare=True)
        self.parent("compare", "#compare-new")
        self.result["delivery_scope"] = "deterministic_comparison_and_selected_contract_no_model"

    def revision(self):
        self.step = "revision_current_guide_and_real_upload"
        self.route("#guide", "#guide-current-body")
        require(bool(self.page.locator("#guide-current-body").inner_text().strip()), "CURRENT_GUIDE_NOT_VISIBLE")
        self.route("#overview", "#view-overview")
        self.page.locator('#view-overview [data-action="new-task"]').first.click()
        expect(self.page.locator("#view-import")).to_be_visible()
        self.page.locator("#task-name").fill("真实公开合同·三业务正式修改验收")
        self.filechooser('#view-import [data-action="choose-files"]', self.args.contract)
        expect(self.page.locator("#import-rows")).to_contain_text(self.args.contract.name)
        self.responsive("revision-upload")
        self.page.locator("#submit-task").click()
        expect(self.page.locator("#view-task")).to_be_visible(timeout=120000)
        task_id = self.task_id("revision")
        task = self.wait("revision", f"/api/tasks/{task_id}", {"completed", "completed_with_exceptions", "failed"})
        self.result["guide_snapshot"] = task.get("guide_snapshot")
        docs = self.get(f"/api/tasks/{task_id}/documents?page=1&page_size=20").get("items", [])
        require(len(docs) == 1, "REVISION_EXPECTED_ONE_DOCUMENT")
        document = docs[0]
        document_id = document["document_id"]
        self.result["document_ids"] = [document_id]
        self.result["document_status"] = {k: document.get(k) for k in ("job_status", "delivery_status", "eligibility", "error_code", "reason_codes")}
        self.deep_reload(f"#task?id={task_id}", "#doc-rows")
        self.responsive("revision-task")
        self.page.locator('[data-detail="doc:0"]').click()
        expect(self.page.locator("#detail-body")).to_be_visible()
        self.step = "revision_actual_downloads_and_report"
        downloads = document.get("downloads") or {}
        for kind in ("report_json", "report_md", "final", "redline", "working_final", "working_redline"):
            if kind in downloads and self.page.locator(f'[data-download="{kind}"]').count():
                self.download(f'[data-download="{kind}"]', kind, ".json" if kind == "report_json" else ".md" if kind == "report_md" else ".docx")
        require((self.out / "report_json.json").exists(), "REVISION_REPORT_NOT_DELIVERED")
        report = json.loads((self.out / "report_json.json").read_text())
        self.result["model_evidence"] = {k: (report.get("model") or {}).get(k) for k in ("http_attempts", "total_tokens", "estimated_cost_usd")}
        require(document.get("delivery_status") in {"complete", "complete_with_exceptions"}
                and report.get("execution_mode") == "delivery" and not report.get("error_code"), "REVISION_NOT_FORMAL_DELIVERABLE")
        require((report.get("model") or {}).get("http_attempts", 0) > 0, "REVISION_NO_REAL_MODEL_EVIDENCE")
        require(report.get("source_sha256") == sha(self.args.contract), "REVISION_SOURCE_HASH_MISMATCH")
        validation = report.get("output_validation") or {}
        for kind in ("final", "redline"):
            require((self.out / f"{kind}.docx").exists(), f"REVISION_MISSING_{kind.upper()}")
            require(sha(self.out / f"{kind}.docx") == validation.get(f"{kind}_sha256"), "REVISION_REPORT_HASH_MISMATCH")
        self.result["report_hashes_match"] = True
        self.result["docx_validation"] = validate_redline(self.args.contract, self.out / "final.docx", self.out / "redline.docx")
        fragment = f"#document?id={task_id}&document={document_id}&tab=review"
        self.deep_reload(fragment, '#view-document [data-action="generate-selected"]')
        self.responsive("revision-review")
        require(self.page.locator("[data-rev-toggle]").count() > 0, "REVIEW_HAS_NO_ACTUAL_REVISIONS")
        self.download_auth(downloads["final"])
        self.parent("task", "#view-task")
        self.parent("overview", "#view-overview")
        self.result["delivery_scope"] = "formal_real_model_revision_downloads_and_review"

    def generation(self):
        self.step = "generation_real_regulation_upload"
        self.route("#generation?mode=list", "#gg-filter")
        self.page.locator('[data-gg-action="new"]').click()
        self.filechooser('[data-gg-action="pick"]', self.args.regulation)
        expect(self.page.locator("#gg-file-label")).to_contain_text(self.args.regulation.name)
        if self.args.corpus_limit is not None:
            details = self.page.locator(".gg-advanced")
            details.locator("summary").click()
            control = self.page.locator("#gg-corpus-limit")
            require(control.count() == 1 and control.is_visible(), "GENERATION_CORPUS_LIMIT_UI_NOT_AVAILABLE")
            control.fill(str(self.args.corpus_limit))
        self.page.locator("#gg-cost-ack").check()
        self.responsive("generation-upload")
        with self.page.expect_response(lambda r: urlsplit(r.url).path == self.api_path("/api/guide-generation/runs") and r.request.method == "POST", timeout=120000) as created:
            self.page.locator("#gg-submit").click()
        require(created.value.status == 201, "GENERATION_UI_SUBMISSION_REJECTED")
        run_id = self.task_id("generation")
        run = self.wait("generation", f"/api/guide-generation/runs/{run_id}", {"complete", "complete_with_unresolved", "completed"})
        self.result["qualification_status"] = run.get("qualification_status")
        self.result["runtime_guide_import"] = "not_requested"
        fragment = f"#generation?mode=detail&id={run_id}"
        self.deep_reload(fragment, "#gg-detail-head")
        self.responsive("generation-overview")
        for tab in ("guide", "requirements", "issues", "versions"):
            self.page.locator(f'[data-gg-tab="{tab}"]').click()
            expect(self.page.locator("#gg-panel")).to_be_visible()
        self.step = "generation_actual_candidate_artifacts"
        for kind, suffix in (("guide", ".docx"), ("evidence_json", ".json"), ("evidence_html", ".html")):
            self.download(f'[data-gg-download="{kind}"]', kind, suffix)
            expected = run.get({"guide": "guide_sha256", "evidence_json": "evidence_sha256", "evidence_html": "report_sha256"}[kind])
            require(expected and sha(self.out / f"{kind}{suffix}") == expected, "GENERATION_ARTIFACT_HASH_MISMATCH")
        evidence = json.loads((self.out / "evidence_json.json").read_text())
        require((evidence.get("regulation") or {}).get("source_sha256") == sha(self.args.regulation), "GENERATION_SOURCE_HASH_MISMATCH")
        require((evidence.get("qualification") or {}).get("guide_is_candidate_only") is True, "GENERATION_CANDIDATE_BOUNDARY_MISSING")
        items = evidence.get("guide_items") or []
        require(items and evidence.get("model_calls"), "GENERATION_NO_REAL_ITEMS_OR_MODEL_CALLS")
        exported = "\n".join(docx(self.out / "guide.docx")["paragraphs"])
        by_requirement = {r["requirement_id"]: r for r in evidence.get("requirements", [])}
        for item in items:
            require(item.get("title") and item["title"] in exported, "GENERATION_DOCX_MISSING_ITEM_TITLE")
            require(item.get("new_text") and item["new_text"].strip() in exported, "GENERATION_DOCX_MISSING_NEW_TEXT")
            requirements = [by_requirement[r] for r in item.get("requirement_ids", []) if r in by_requirement]
            require(requirements and all(r.get("source_quote") and r.get("source_block_ids") for r in requirements), "GENERATION_ITEM_MISSING_REGULATION_EVIDENCE")
        self.result.update(candidate_items_verified=len(items), report_hashes_match=True,
                           model_call_count=len(evidence["model_calls"]),
                           work_product="candidate_with_findings" if run.get("qualification_status") == "candidate_with_findings" else "candidate_only_not_runtime_active",
                           runtime_activation_performed=False)
        self.download_auth(run["artifacts"]["guide"])
        self.responsive("generation-versions")
        self.parent("generation", "#gg-filter")
        self.result["delivery_scope"] = "real_model_candidate_work_product_not_runtime_active"


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("revision", "compare", "generation", "smoke"), required=True)
    parser.add_argument("--base", default="https://fundlex.club")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--inputs", type=Path, default=COMPARE_INPUTS, help="Directory containing left.docx/right.docx")
    parser.add_argument("--left", type=Path)
    parser.add_argument("--right", type=Path)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--regulation", "--pdf", type=Path)
    parser.add_argument("--corpus-limit", type=int, help="Only through a visible legitimate generation advanced field")
    parser.add_argument("--wait-minutes", type=float, default=40)
    parser.add_argument("--allow-model-calls", action="store_true")
    parser.add_argument("--budget-reference", help="Pre-registered ledger/approval reference; never a secret")
    args = parser.parse_args()
    parsed = urlsplit(args.base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
        parser.error("--base must be a credential-free HTTP(S) deployment URL")
    if not 0 < args.wait_minutes <= 120:
        parser.error("--wait-minutes must be > 0 and <= 120")
    if args.phase in ("revision", "generation") and not (args.allow_model_calls and args.budget_reference):
        parser.error("Paid phases require --allow-model-calls and a pre-registered --budget-reference")
    args.left, args.right = args.left or args.inputs / "left.docx", args.right or args.inputs / "right.docx"
    paths = [args.contract] if args.phase == "revision" else [args.left, args.right] if args.phase == "compare" else [args.regulation] if args.phase == "generation" else []
    if any(path is None or not path.is_file() for path in paths):
        parser.error("Required real input file is missing")
    if args.phase == "generation" and args.regulation.suffix.lower() != ".pdf":
        parser.error("Generation acceptance requires a real text-layer PDF")
    if args.corpus_limit is not None and not 1 <= args.corpus_limit <= 10000:
        parser.error("--corpus-limit must be between 1 and 10000")
    args.input_files = paths
    return args


def main():
    args = arguments()
    username = "e2e-v1ws-" + secrets.token_hex(8)
    output = args.out / username
    output.mkdir(parents=True, exist_ok=False)
    output.chmod(0o700)
    result = {"username": username, "phase": args.phase, "base": args.base,
              "task_ids": {"revision": [], "compare": [], "generation": []},
              "inputs": [{"name": p.name, "sha256": sha(p)} for p in args.input_files],
              "budget_reference": args.budget_reference, "credentials_retained": False,
              "page_error_count": 0, "passed": False, "automatic_paid_retries": 0}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
        page = context.new_page()
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(60000)
        runner = Runner(args, page, context, result, output)
        runner.checkpoint()
        try:
            runner.login()
            runner.deep_reload("#workspace", "#view-workspace")
            runner.responsive("workspace")
            getattr(runner, args.phase)()
            require(result["page_error_count"] == 0, "BROWSER_RUNTIME_ERRORS")
            result["passed"] = True
        except Exception as exc:
            result["failure"] = {"step": runner.step,
                                 "code": str(exc) if isinstance(exc, AcceptanceFailure) else type(exc).__name__}
            # Never dump arbitrary browser errors, request bodies or auth DOM.
        finally:
            runner.checkpoint()
            context.close()
            browser.close()
    print(json.dumps({"passed": result["passed"], "username": username,
                      "evidence": str(output / "result.json"), "failure": result.get("failure")}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
