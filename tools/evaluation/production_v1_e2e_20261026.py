#!/usr/bin/env python3
"""Production V1 acceptance for the ordinary and Compare user paths.

This runner uses a one-off public-contract account, follows the V1 browser UI,
then uses the authenticated browser session only for machine-readable evidence.
It deliberately records no password, bearer token, or environment value.
Cleanup is performed separately by the operator after the result has been
reviewed, because the production database is intentionally outside this script.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
import string
import time
import zipfile
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright


BASE = "https://fundlex.club"
SOURCE = Path("/home/opencode/data/funds_word/广发品质回报混合型证券投资基金基金合同_20230708.docx")
COMPARE_RIGHT = Path("/home/opencode/data/funds_word/广发ESG责任投资混合型证券投资基金基金合同_20230708.docx")
OUT = Path("/tmp/opencode/fundlex-production-v1-e2e-20261026")
MAX_WAIT = 2400


def random_part(size: int = 12) -> str:
    return "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(size))


def browser_json(page: Page, path: str, options: dict[str, Any] | None = None) -> dict[str, Any]:
    return page.evaluate(
        """async ({path, options}) => {
          const headers = new Headers(options?.headers || {});
          const token = sessionStorage.getItem('fundlex-auth-token');
          if (token) headers.set('Authorization', `Bearer ${token}`);
          const response = await fetch(path, {...(options || {}), headers, cache: 'no-store'});
          let body = null;
          try { body = await response.json(); } catch {}
          return {status: response.status, body};
        }""",
        {"path": path, "options": options or {}},
    )


def browser_bytes(page: Page, path: str) -> tuple[int, str | None, bytes]:
    result = page.evaluate(
        """async (path) => {
          const headers = new Headers();
          const token = sessionStorage.getItem('fundlex-auth-token');
          if (token) headers.set('Authorization', `Bearer ${token}`);
          const response = await fetch(path, {headers, cache: 'no-store'});
          const buffer = new Uint8Array(await response.arrayBuffer());
          let binary = '';
          for (let i = 0; i < buffer.length; i += 0x8000)
            binary += String.fromCharCode(...buffer.subarray(i, i + 0x8000));
          return {status: response.status, type: response.headers.get('content-type'), data: btoa(binary)};
        }""",
        path,
    )
    return int(result["status"]), result.get("type"), base64.b64decode(result["data"])


def save_download(page: Page, url: str, target: Path) -> dict[str, Any]:
    status, content_type, data = browser_bytes(page, url)
    if status != 200:
        raise RuntimeError(f"download {status}: {url}")
    target.write_bytes(data)
    return {"path": str(target), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "content_type": content_type}


def docx_check(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    return {"valid_zip": True, "document_xml_sha256": hashlib.sha256(xml).hexdigest(),
            "insertions": xml.count(b"<w:ins"), "deletions": xml.count(b"<w:del"),
            "has_revision_markup": b"<w:ins" in xml or b"<w:del" in xml,
            "document_xml_bytes": len(xml)}


def record_viewport(page: Page, name: str, path: str, result: dict[str, Any]) -> None:
    page.goto(BASE + path, wait_until="domcontentloaded", timeout=60000)
    result.setdefault("responsive", {}).setdefault(name, {})[path] = page.evaluate(
        """() => ({viewport: innerWidth, body_scroll_width: document.body.scrollWidth,
        document_scroll_width: document.documentElement.scrollWidth,
        hash: location.hash, title: document.title})"""
    )


def main() -> None:
    if not SOURCE.is_file() or not COMPARE_RIGHT.is_file():
        raise SystemExit("public source DOCX is missing")
    OUT.mkdir(parents=True, exist_ok=True)
    username = "e2e-v1-" + random_part()
    password = secrets.token_urlsafe(18)
    task_name = "生产V1真实用户路径验收-20261026"
    result: dict[str, Any] = {
        "base": BASE,
        "source": SOURCE.name,
        "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        "compare_right": COMPARE_RIGHT.name,
        "compare_right_sha256": hashlib.sha256(COMPARE_RIGHT.read_bytes()).hexdigest(),
        "task_name": task_name,
        "username": username,
        "credentials_retained": False,
    }
    account_dir = OUT / username
    account_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
        page = context.new_page()
        page_errors: list[str] = []
        console_errors: list[str] = []
        static_404: list[str] = []
        api_404: list[str] = []
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("response", lambda response: (api_404 if "/api/" in response.url else static_404).append(response.url)
                if response.status == 404 else None)

        try:
            page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
            assert "合同修订工作台" in page.title()
            result["home_title"] = page.title()
            result["home_html"] = page.locator("html").get_attribute("lang")
            page.screenshot(path=str(account_dir / "home-1440.png"), full_page=True)

            page.get_by_role("button", name="注册新账号").click()
            page.locator("#register-username").fill(username)
            page.locator("#register-display").fill("生产V1真实验收账号")
            page.locator("#register-password").fill(password)
            page.locator("#register-confirm").fill(password)
            page.get_by_role("button", name="注册并登录").click()
            page.locator("#login-view").wait_for(state="hidden", timeout=30000)
            result["registered_and_logged_in"] = True

            page.goto(BASE + "/guides", wait_until="domcontentloaded", timeout=60000)
            assert page.get_by_role("heading", name="当前指引").is_visible()
            guide_text = page.locator("body").inner_text()
            assert "内置" in guide_text or "已解析" in guide_text or "已发布" in guide_text
            result["guide_page_ok"] = True
            result["guide_excerpt"] = guide_text[:400]

            page.goto(BASE + "/tasks/new", wait_until="domcontentloaded", timeout=60000)
            assert page.locator("#view-import").is_visible()
            assert page.locator("#submit-task").is_visible()
            assert "当前指引" in page.locator("body").inner_text()
            page.locator("#task-name").fill(task_name)
            page.locator("#file-picker").set_input_files(str(SOURCE))
            assert SOURCE.name in page.locator("body").inner_text()
            page.locator("#submit-task").click()
            page.locator("#view-task").wait_for(state="visible", timeout=90000)
            result["task_submission_ui_ok"] = True

            task_id = ""
            task_snapshot: dict[str, Any] | None = None
            docs_payload: dict[str, Any] | None = None
            started = time.time()
            while time.time() - started < MAX_WAIT:
                listing = browser_json(page, "/api/tasks?page=1&page_size=200&sort=newest")
                if listing["status"] != 200:
                    raise RuntimeError(f"task listing HTTP {listing['status']}")
                matches = [item for item in listing["body"].get("items", []) if item.get("name") == task_name]
                if matches:
                    task_id = matches[0]["id"]
                    snapshot_result = browser_json(page, f"/api/tasks/{task_id}")
                    docs_result = browser_json(page, f"/api/tasks/{task_id}/documents?page=1&page_size=20&sort=oldest")
                    task_snapshot = snapshot_result["body"]
                    docs_payload = docs_result["body"] if docs_result["status"] == 200 else None
                    if task_snapshot.get("status") in {"completed", "failed"} and docs_payload and docs_payload.get("items"):
                        break
                time.sleep(10)
            if not task_id or not task_snapshot or not docs_payload:
                raise RuntimeError("production task did not produce a terminal document result")
            result["task_id"] = task_id
            result["waited_seconds"] = round(time.time() - started)
            result["task_status"] = {key: task_snapshot.get(key) for key in
                                      ("id", "name", "status", "total", "uploaded", "completed", "failed",
                                       "exceptions", "guide_snapshot", "delivery_counts")}
            document = docs_payload["items"][0]
            document_id = document["document_id"]
            result["document_id"] = document_id
            result["document_status"] = {key: document.get(key) for key in
                                          ("name", "job_status", "delivery_status", "eligibility", "phase",
                                           "target_counts", "source_sha256", "downloads", "reason_codes")}

            page.goto(BASE + f"/#task", wait_until="domcontentloaded", timeout=60000)
            # The option is deliberately hidden by the native select styling;
            # wait for it to be attached/populated rather than visible.
            page.locator(f"#task-select option[value='{task_id}']").wait_for(
                state="attached", timeout=30000)
            page.locator("#task-select").select_option(task_id)
            page.locator("#doc-rows").wait_for(timeout=30000)
            page.locator("[data-detail='doc:0']").click()
            page.locator("#detail-overlay").wait_for(state="visible", timeout=30000)
            result["detail_page_ok"] = True
            report_result = browser_json(page, f"/api/tasks/{task_id}/documents/{document_id}/report")
            if report_result["status"] != 200:
                raise RuntimeError(f"report HTTP {report_result['status']}")
            report = report_result["body"]
            (account_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result["report_summary"] = {
                "delivery_status": report.get("delivery_status"),
                "unresolved_count": len(report.get("unresolved") or []),
                "unresolved": report.get("unresolved") or [],
                "plan_count": (report.get("plan") or {}).get("count"),
                "model": {key: (report.get("model") or {}).get(key)
                          for key in ("http_attempts", "total_tokens", "estimated_cost_usd")},
                "output_validation": report.get("output_validation"),
                "artifacts": report.get("artifacts"),
            }

            # Preserve the ordinary-contract failure as the primary acceptance
            # result.  Do not let a later UI action replace it with an overlay or
            # Compare click error; the report has already been saved above.
            if document.get("job_status") == "failed" or report.get("error_code") \
                    or report.get("delivery_status") in {"not_generated", "incomplete"}:
                result["ordinary_failure"] = {
                    "error_code": report.get("error_code"),
                    "errors": report.get("errors") or [],
                    "delivery_status": report.get("delivery_status"),
                }
                raise RuntimeError(
                    "ordinary contract did not produce a complete deliverable: "
                    f"{report.get('error_code') or report.get('delivery_status')}"
                )

            downloads = document.get("downloads") or {}
            for kind in ("final", "redline", "working_final", "working_redline", "report_json", "report_md"):
                if kind in downloads:
                    suffix = ".json" if kind == "report_json" else ".md" if kind == "report_md" else ".docx"
                    result.setdefault("downloads", {})[kind] = save_download(
                        page, downloads[kind], account_dir / f"{kind}{suffix}"
                    )
            result["docx_checks"] = {kind: docx_check(account_dir / f"{kind}.docx")
                                      for kind in ("final", "redline", "working_final", "working_redline")
                                      if (account_dir / f"{kind}.docx").is_file()}
            validation = report.get("output_validation") or {}
            result["hash_checks"] = {}
            for logical, primary, fallback, expected_key in (
                ("final", "final", "working_final", "final_sha256"),
                ("redline", "redline", "working_redline", "redline_sha256"),
            ):
                actual_kind = primary if primary in result.get("downloads", {}) else fallback if fallback in result.get("downloads", {}) else None
                actual = result.get("downloads", {}).get(actual_kind or "", {}).get("sha256")
                expected = validation.get(expected_key)
                result["hash_checks"][logical] = {"download_kind": actual_kind, "expected": expected,
                                                  "actual": actual, "matched": bool(expected and actual == expected)}

            # Open Review through the V1 dialog, reject one revision when present,
            # and submit the actual decision request from the rendered review.
            if page.locator("[data-action='open-review']").count():
                page.locator("[data-action='open-review']").click()
                page.locator("[data-action='generate-selected']").wait_for(timeout=30000)
                revision_count = page.locator("[data-rev-toggle]").count()
                result["review_page_ok"] = True
                result["review_revision_count"] = revision_count
                if revision_count:
                    page.locator("[data-rev-toggle]").first.uncheck()
                    with page.expect_response(lambda response: response.url.endswith("/decisions") and response.request.method == "POST",
                                              timeout=120000) as decision_response:
                        page.locator("[data-action='generate-selected']").click()
                    response = decision_response.value
                    result["selection_http"] = response.status
                    result["selection_response"] = response.json()
                    if response.status != 200:
                        raise RuntimeError(f"selection HTTP {response.status}")
                    selected = None
                    selected_started = time.time()
                    while time.time() - selected_started < 120:
                        current = browser_json(page, f"/api/tasks/{task_id}/documents?page=1&page_size=20&sort=oldest")
                        selected = (current.get("body") or {}).get("items", [{}])[0]
                        if "selected_final" in (selected.get("downloads") or {}):
                            break
                        time.sleep(2)
                    if not selected or "selected_final" not in (selected.get("downloads") or {}):
                        raise RuntimeError("selected_final was not published after a successful decision")
                    result["selected_status"] = {key: selected.get(key) for key in ("downloads", "delivery_status", "eligibility")}
                    result.setdefault("downloads", {})["selected_final"] = save_download(
                        page, selected["downloads"]["selected_final"], account_dir / "selected_final.docx"
                    )
                    if "selected_redline" in selected["downloads"]:
                        result.setdefault("downloads", {})["selected_redline"] = save_download(
                            page, selected["downloads"]["selected_redline"], account_dir / "selected_redline.docx"
                        )
                    result["selected_docx_check"] = docx_check(account_dir / "selected_final.docx")

            # Compare is a real persistent task path and uses no model call. Close
            # the document detail modal first because the app marks the background
            # inert while it is open.
            if page.locator("#detail-overlay").is_visible():
                page.locator("#close-detail").click()
                page.locator("#detail-overlay").wait_for(state="hidden", timeout=30000)
            page.goto(BASE + "/#compare", wait_until="domcontentloaded", timeout=60000)
            page.locator("#compare-new").click()
            page.locator("#compare-name").fill("生产V1真实合同对比验收-20261026")
            page.locator("[data-compare-left='0']").set_input_files(str(SOURCE))
            page.locator("[data-compare-right='0']").set_input_files(str(COMPARE_RIGHT))
            page.locator("#compare-submit").click()
            compare_id = ""
            compare_started = time.time()
            while time.time() - compare_started < 900:
                listed = browser_json(page, "/api/compare/tasks")
                matches = [item for item in (listed.get("body") or {}).get("items", [])
                           if item.get("name") == "生产V1真实合同对比验收-20261026"]
                if matches:
                    compare_id = matches[0]["id"]
                    task = browser_json(page, f"/api/compare/tasks/{compare_id}").get("body") or {}
                    statuses = [pair.get("status") for pair in task.get("pairs", [])]
                    if statuses and all(status in {"succeeded", "incomplete", "failed"} for status in statuses):
                        break
                time.sleep(5)
            if not compare_id:
                raise RuntimeError("compare task was not created")
            result["compare_task_id"] = compare_id
            result["compare_waited_seconds"] = round(time.time() - compare_started)
            compare_task = browser_json(page, f"/api/compare/tasks/{compare_id}")["body"]
            result["compare_status"] = {key: compare_task.get(key) for key in ("status", "sealed", "total", "counts")}
            page.locator("[data-compare-task]").first.click()
            page.locator("#compare-viewer").wait_for(state="visible", timeout=120000)
            result["compare_ui_ok"] = True
            result["compare_summary"] = page.locator("#compare-summary").inner_text()
            pair_id = (compare_task.get("pairs") or [{}])[0].get("id")
            if pair_id:
                view_result = browser_json(page, f"/api/compare/pairs/{pair_id}/view")
                result["compare_view_http"] = view_result["status"]
                if view_result["status"] == 200:
                    (account_dir / "compare-view.json").write_text(
                        json.dumps(view_result["body"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                    )
                    result["compare_view"] = {
                        "summary": view_result["body"].get("summary"),
                        "coverage": view_result["body"].get("coverage"),
                        "diff_count": len(view_result["body"].get("diffs") or []),
                        "result_sha256": view_result["body"].get("result_sha256"),
                    }

            # Check the public V1 routes and three required widths after the
            # business path has been exercised.
            for width, height in ((1440, 900), (768, 1024), (390, 844)):
                page.set_viewport_size({"width": width, "height": height})
                page.goto(BASE + "/#overview", wait_until="domcontentloaded", timeout=60000)
                result.setdefault("viewports", {})[str(width)] = page.evaluate(
                    """() => ({innerWidth, bodyScrollWidth: document.body.scrollWidth,
                    documentScrollWidth: document.documentElement.scrollWidth,
                    overflow: document.documentElement.scrollWidth > innerWidth})"""
                )
                page.screenshot(path=str(account_dir / f"overview-{width}.png"), full_page=True)
            result["page_errors"] = page_errors
            result["console_errors"] = console_errors
            result["static_404"] = static_404
            result["api_404"] = api_404
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            result["error"] = errors[-1]
        finally:
            result["page_errors"] = page_errors
            result["console_errors"] = console_errors
            result["static_404"] = static_404
            result["api_404"] = api_404
            result["evidence_dir"] = str(account_dir)
            result["errors"] = errors
            (account_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            browser.close()
    print(json.dumps({key: value for key, value in result.items() if key not in {"console_errors", "page_errors"}},
                     ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
