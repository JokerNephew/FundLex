#!/usr/bin/env python3
"""Production first-batch browser acceptance with downloads and idle-user checks.

This runner follows the deployed V1 browser path (register, current guide, upload,
real Worker/model, result page, authorized downloads). It never records a password,
session token, environment value, or provider credential. It leaves the temporary
account/task in place as acceptance evidence; an operator may remove them after review.

The mechanical artifact review is not business approval. A separate reviewer must
read the source, the guide, and the downloaded final DOCX; a complete report alone is
not sufficient evidence.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import string
import time
import zipfile
from pathlib import Path
from typing import Any

import httpx
from playwright.sync_api import Page, sync_playwright

from tools.evaluation.verify_downloaded_artifacts import verify_case

BASE = "https://fundlex.club"
DEFAULT_SOURCE = Path(
    "/home/opencode/fundlex/funds_word/基金合同第一批/"
    "广发价值优选混合型证券投资基金基金合同.docx"
)
DEFAULT_OUT = Path("/tmp/opencode/fundlex-production-first-batch-20261028")
MAX_WAIT_SECONDS = 1800


def random_part(size: int = 10) -> str:
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
        raise RuntimeError(f"download HTTP {status}: {url}")
    target.write_bytes(data)
    return {
        "path": str(target),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content_type": content_type,
    }


def docx_facts(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    return {
        "valid_zip": True,
        "document_xml_sha256": hashlib.sha256(xml).hexdigest(),
        "insertions": xml.count(b"<w:ins"),
        "deletions": xml.count(b"<w:del"),
        "has_revision_markup": b"<w:ins" in xml or b"<w:del" in xml,
        "document_xml_bytes": len(xml),
    }


def _save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--keep-session", action="store_true", help="Do not call logout at the end")
    args = parser.parse_args()

    source = args.source.resolve()
    if not source.is_file() or source.suffix.lower() != ".docx":
        raise SystemExit(f"source DOCX missing: {source}")
    output = args.out.resolve()
    output.mkdir(parents=True, exist_ok=True)
    username = "audit-batch-" + random_part()
    password = secrets.token_urlsafe(24)
    task_name = "首批合同正式交付验收-" + random_part(6)
    result: dict[str, Any] = {
        "base": args.base,
        "source": source.name,
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "audit_username": username,
        "task_name": task_name,
        "credentials_retained": False,
        "scope": "deployed browser path; mechanical checks only, independent business review still required",
    }
    errors: list[str] = []
    page_errors: list[str] = []
    console_errors: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 960}, accept_downloads=True)
        page = context.new_page()
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        try:
            page.goto(args.base + "/", wait_until="domcontentloaded", timeout=60000)
            title = page.title()
            assert any(marker in title for marker in ("合同修订工作台", "FundLex", "工作台")), title
            page.locator("#register-link").click()
            page.locator("#register-username").fill(username)
            page.locator("#register-display").fill("首批合同交付验收临时账号")
            page.locator("#register-password").fill(password)
            page.locator("#register-confirm").fill(password)
            page.locator("#register-submit").click()
            page.locator("#login-view").wait_for(state="hidden", timeout=30000)
            result["registered_login"] = True

            workspace = browser_json(page, "/api/workspace/tasks?page=1&page_size=20")
            result["workspace_http"] = workspace["status"]
            if workspace["status"] == 200:
                body = workspace.get("body") or {}
                result["workspace"] = {
                    "total": body.get("total"),
                    "stats": body.get("stats"),
                    "item_count": len(body.get("items") or []),
                }
            else:
                errors.append(f"workspace HTTP {workspace['status']}")

            page.goto(args.base + "/#guide", wait_until="domcontentloaded", timeout=60000)
            page.get_by_role("heading", name="当前指引", exact=True).wait_for(timeout=30000)
            guide_text = page.locator("body").inner_text()
            result["guide_page"] = True
            result["guide_excerpt"] = guide_text[:500]
            page.screenshot(path=str(output / "guide-1440.png"), full_page=True)

            page.goto(args.base + "/#import", wait_until="domcontentloaded", timeout=60000)
            page.locator("#task-name").fill(task_name)
            page.locator("#file-picker").set_input_files(str(source))
            page.locator("#submit-task").click()
            page.locator("#view-task").wait_for(state="visible", timeout=90000)
            result["browser_submitted"] = True

            started = time.monotonic()
            phases: list[dict[str, Any]] = []
            task: dict[str, Any] | None = None
            document: dict[str, Any] | None = None
            task_id = ""
            while time.monotonic() - started < MAX_WAIT_SECONDS:
                listing = browser_json(page, "/api/tasks?page=1&page_size=100&sort=newest")
                matches = [
                    item for item in (listing.get("body") or {}).get("items", [])
                    if item.get("name") == task_name
                ]
                if matches:
                    task_id = matches[0]["id"]
                    result["task_id"] = task_id
                    task_response = browser_json(page, f"/api/tasks/{task_id}")
                    task = task_response.get("body") or {}
                    docs_response = browser_json(
                        page, f"/api/tasks/{task_id}/documents?page=1&page_size=20&sort=oldest"
                    )
                    docs = (docs_response.get("body") or {}).get("items", [])
                    if docs:
                        document = docs[0]
                        phase = {
                            "task": task.get("status"),
                            "job": document.get("job_status"),
                            "delivery": document.get("delivery_status"),
                        }
                        if not phases or phases[-1] != phase:
                            phases.append(phase)
                        if task.get("status") in {"completed", "failed", "paused"}:
                            break
                page.wait_for_timeout(3000)
            result["phases"] = phases
            result["elapsed_seconds"] = round(time.monotonic() - started, 1)
            if not task or not document:
                raise RuntimeError("task/document did not become available")
            result["task"] = {
                key: task.get(key)
                for key in ("status", "total", "uploaded", "completed", "failed", "exceptions",
                            "delivery_counts", "pause_reason", "guide_snapshot")
            }
            result["document"] = {
                key: document.get(key)
                for key in ("document_id", "job_status", "delivery_status", "phase",
                            "reason_codes", "downloads", "batch_id")
            }
            document_id = document["document_id"]
            report_response = browser_json(
                page, f"/api/tasks/{task_id}/documents/{document_id}/report"
            )
            result["report_http"] = report_response["status"]
            if report_response["status"] != 200:
                raise RuntimeError(f"report HTTP {report_response['status']}")
            report = report_response.get("body") or {}
            _save_json(output / "report.json", report)
            result["report_summary"] = {
                key: report.get(key)
                for key in ("delivery_status", "engine_id", "engine_version", "engine_build",
                            "error_code", "model", "output_validation", "artifact_claim_replay",
                            "final_omission_review", "unresolved")
            }

            page.goto(args.base + f"/#task?id={task_id}", wait_until="domcontentloaded", timeout=60000)
            page.locator("[data-detail]").first.wait_for(state="visible", timeout=30000)
            page.locator("[data-detail]").first.click()
            page.locator("#detail-overlay").wait_for(state="visible", timeout=30000)
            result["result_page_opened"] = True
            page.screenshot(path=str(output / "result-1440.png"), full_page=True)

            # Delivery artifact materialization can lag the terminal job status;
            # poll the document listing until final/redline links are published.
            download_deadline = time.monotonic() + 300
            while True:
                downloads = document.get("downloads") or {}
                if downloads.get("final") and downloads.get("redline"):
                    break
                if time.monotonic() > download_deadline:
                    break
                page.wait_for_timeout(4000)
                docs_response = browser_json(
                    page, f"/api/tasks/{task_id}/documents?page=1&page_size=20&sort=oldest"
                )
                docs = (docs_response.get("body") or {}).get("items", [])
                if docs:
                    document = docs[0]
            result["download_wait_seconds"] = round(
                max(0.0, 300 - (download_deadline - time.monotonic())), 1
            )
            result["downloads"] = {}
            for kind, url in downloads.items():
                if kind not in {"final", "redline", "working_final", "working_redline",
                                "report_json", "report_md"}:
                    continue
                suffix = ".json" if kind == "report_json" else ".md" if kind == "report_md" else ".docx"
                dest = output / f"{kind}{suffix}"
                record = save_download(page, url, dest)
                if suffix == ".docx":
                    record["docx"] = docx_facts(dest)
                record["unauthenticated_http"] = httpx.get(args.base + url, timeout=30).status_code
                result["downloads"][kind] = record

            final_path = output / "final.docx"
            redline_path = output / "redline.docx"
            if not final_path.is_file() or not redline_path.is_file():
                raise RuntimeError("final/redline download unavailable")
            artifact_review = verify_case(output, source)
            _save_json(output / "artifact-review.json", artifact_review)
            result["artifact_review"] = {
                key: artifact_review.get(key)
                for key in ("mechanical_pass", "business_complete", "checks", "revisions",
                            "final_sha256", "redline_sha256")
            }
            result["artifact_review"]["changed_paragraphs"] = len(
                artifact_review.get("changed_paragraphs") or []
            )
            result["artifact_review"]["plan_artifact_mismatches"] = len(
                artifact_review.get("plan_artifact_mismatches") or []
            )
            result["hash_checks"] = {}
            for kind in ("final", "redline"):
                actual = (result["downloads"].get(kind) or {}).get("sha256")
                expected = (report.get("output_validation") or {}).get(kind + "_sha256")
                result["hash_checks"][kind] = {
                    "actual": actual,
                    "expected": expected,
                    "matched": bool(actual and expected and actual == expected),
                }

            # Exercise the real decision endpoint and download both selected forms.
            revisions = browser_json(
                page, f"/api/tasks/{task_id}/documents/{document_id}/revisions"
            )
            revision_rows = (revisions.get("body") or {}).get("revisions") or []
            result["revision_count"] = len(revision_rows)
            if revision_rows:
                decisions = [
                    {"del_id": revision_rows[0]["del_id"], "decision": "reject"},
                    *[
                        {"del_id": row["del_id"], "decision": "accept"}
                        for row in revision_rows[1:3]
                    ],
                ]
                selected = browser_json(
                    page,
                    f"/api/tasks/{task_id}/documents/{document_id}/decisions",
                    {"method": "POST", "headers": {"Content-Type": "application/json"},
                     "body": json.dumps({"decisions": decisions})},
                )
                result["selection_http"] = selected["status"]
                current = browser_json(
                    page, f"/api/tasks/{task_id}/documents?page=1&page_size=20&sort=oldest"
                )
                selected_doc = ((current.get("body") or {}).get("items") or [{}])[0]
                selected_downloads = selected_doc.get("downloads") or {}
                result["selected_downloads"] = {}
                for kind in ("selected_final", "selected_redline"):
                    if kind not in selected_downloads:
                        continue
                    target = output / f"{kind}.docx"
                    result["selected_downloads"][kind] = save_download(
                        page, selected_downloads[kind], target
                    )
                    result["selected_downloads"][kind]["docx"] = docx_facts(target)
                result["selected_unauthorized_http"] = httpx.get(
                    args.base + (selected_downloads.get("selected_final") or ""), timeout=30
                ).status_code if selected_downloads.get("selected_final") else None

            result["terminal_success"] = (
                task.get("status") == "completed"
                and report.get("delivery_status") == "complete"
                and artifact_review.get("mechanical_pass") is True
            )
            for width in (1440, 390):
                page.set_viewport_size({"width": width, "height": 960})
                result.setdefault("responsive", {})[str(width)] = page.evaluate(
                    "({width: innerWidth, scroll: document.documentElement.scrollWidth})"
                )
            result["page_errors"] = page_errors
            result["console_errors"] = console_errors
            if not args.keep_session:
                browser_json(page, "/api/auth/logout", {"method": "POST"})
                result["audit_session_logged_out"] = True
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
            result["error"] = errors[-1]
            result["page_errors"] = page_errors
            result["console_errors"] = console_errors
            try:
                page.screenshot(path=str(output / "failure.png"), full_page=True)
            except Exception:
                pass
        finally:
            result["errors"] = errors
            _save_json(output / "result.json", result)
            browser.close()

    print(json.dumps({
        key: result.get(key)
        for key in ("registered_login", "workspace_http", "browser_submitted", "task_id",
                    "elapsed_seconds", "terminal_success", "error", "artifact_review")
    }, ensure_ascii=False, indent=2))
    return 0 if not errors and result.get("terminal_success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
