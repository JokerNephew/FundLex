"""Authenticated Test environment smoke checks; never targets production."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import zipfile
from pathlib import Path

import httpx


def fail(message: str) -> None:
    raise SystemExit(f"SMOKE FAILED: {message}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8110")
    parser.add_argument("--credentials", default="/etc/fundlex-test-credentials")
    parser.add_argument("--docx", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900.0,
                        help="maximum time to wait for the persistent Worker")
    parser.add_argument("--poll-seconds", type=float, default=2.0,
                        help="delay between task/document status reads")
    parser.add_argument("--output", type=Path,
                        help="write the JSON evidence record to this path")
    args = parser.parse_args()
    if os.environ.get("FUNDLEX_ENV") == "production":
        fail("caller has FUNDLEX_ENV=production")
    if ":8010" in args.base_url or "fundlex.club" in args.base_url:
        fail("production URL is forbidden")
    credentials = json.loads(Path(args.credentials).read_text(encoding="utf-8"))
    if credentials.get("environment") != "test":
        fail("credential file is not marked Test")
    if not args.docx.is_file() or args.docx.suffix.lower() != ".docx":
        fail("a real DOCX is required")
    if args.timeout_seconds <= 0 or args.poll_seconds <= 0:
        fail("timeout and poll intervals must be positive")
    result: dict = {"environment": "test", "base_url": args.base_url, "started_at": time.time(),
                    "status_history": []}
    with httpx.Client(base_url=args.base_url, timeout=30, follow_redirects=False) as client:
        capabilities = client.get("/api/capabilities")
        if capabilities.status_code != 200 or capabilities.json().get("environment") != "test":
            fail(f"capabilities: {capabilities.status_code}")
        login = client.post("/api/auth/login", json=credentials["member"])
        if login.status_code != 200:
            fail(f"login: {login.status_code}")
        token = login.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        health = client.get("/api/health", headers=headers)
        if health.status_code != 200:
            fail(f"health: {health.status_code} {health.text[:200]}")
        task = client.post("/api/tasks", headers=headers, json={
            "name": "Test smoke", "engine_id": "recall_first",
            "files": [{"client_id": "smoke-1", "name": args.docx.name, "size": args.docx.stat().st_size}],
        })
        if task.status_code != 201:
            fail(f"task: {task.status_code} {task.text[:300]}")
        task_json = task.json()
        task_id = task_json["id"]
        upload = client.post(f"/api/tasks/{task_id}/uploads", headers=headers,
                             data={"client_ids": json.dumps(["smoke-1"])},
                             files={"files": (args.docx.name, args.docx.read_bytes(),
                                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
        if upload.status_code != 200:
            fail(f"upload: {upload.status_code} {upload.text[:300]}")
        seal = client.post(f"/api/tasks/{task_id}/seal", headers=headers)
        if seal.status_code not in {200, 201}:
            fail(f"seal: {seal.status_code} {seal.text[:300]}")
        upload_json = upload.json()
        receipts = upload_json.get("receipts") or []
        result.update({"task_id": task_id,
                       "document_id": receipts[0].get("document_id") if receipts else None,
                       "upload_status": upload_json.get("task", {}).get("upload_status")})
        result["health"] = health.json()
        document_id = result["document_id"]
        if not document_id:
            fail("accepted upload did not return a document_id")

        deadline = time.monotonic() + args.timeout_seconds
        final_task = task_json
        final_document = None
        while True:
            task_read = client.get(f"/api/tasks/{task_id}", headers=headers)
            document_read = client.get(f"/api/tasks/{task_id}/documents/{document_id}", headers=headers)
            if task_read.status_code != 200 or document_read.status_code != 200:
                fail(f"status read: task={task_read.status_code} document={document_read.status_code}")
            final_task = task_read.json()
            final_document = document_read.json()
            result["status_history"].append({
                "at": time.time(),
                "task_status": final_task.get("status"),
                "job_status": final_document.get("job_status"),
                "delivery_status": final_document.get("delivery_status"),
                "error_code": final_document.get("error_code"),
            })
            if final_document.get("job_status") in {"succeeded", "failed"}:
                break
            if time.monotonic() >= deadline:
                fail(f"Worker timeout after {args.timeout_seconds:g}s: {json.dumps(result['status_history'][-1])}")
            time.sleep(args.poll_seconds)

        result["task"] = final_task
        result["document"] = final_document
        result["error_code"] = final_document.get("error_code")
        result["delivery_status"] = final_document.get("delivery_status")
        result["artifact_links"] = final_document.get("downloads") or {}
        report_url = final_document.get("report_url")
        result["report_url"] = report_url
        if report_url:
            report_read = client.get(report_url, headers=headers)
            result["report_http_status"] = report_read.status_code
            if report_read.status_code == 200:
                try:
                    result["report"] = report_read.json()
                except ValueError:
                    result["report"] = {"text": report_read.text}
            else:
                result["report_error"] = report_read.text[:500]
        else:
            result["report"] = None
    result["docx_sha256"] = hashlib.sha256(args.docx.read_bytes()).hexdigest()
    result["finished_at"] = time.time()
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
