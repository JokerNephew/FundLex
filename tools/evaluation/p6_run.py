"""P6 batch runner: run the frozen sample set through the real app path, one account.

Registers a single temporary account, then for every case in the selection submits a real
recall_first task, waits for the worker (the app makes the real model calls), downloads the
final DOCX, the redline and the report, and stores everything under the run directory. The
account and its tasks are the only server-side state this leaves behind; FL-D053 tracks the
cleanup limitation.

Usage::

    .venv/bin/python -m tools.evaluation.p6_run --group dev --run-id p6-dev-baseline-01
"""
from __future__ import annotations

import argparse
import json
import secrets
import string
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8010"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", default="var/recall-first-evaluation/p6/selection.json")
    parser.add_argument("--data-root", default="/home/opencode/data")
    parser.add_argument("--output-root", default="var/recall-first-evaluation")
    parser.add_argument("--run-id", default="p6-dev-baseline-01")
    parser.add_argument("--group", default="dev", choices=("dev", "holdout", "all"))
    parser.add_argument("--timeout", type=float, default=900)
    parser.add_argument("--case", action="append", default=None)
    args = parser.parse_args()

    selection = json.loads(Path(args.selection).read_text(encoding="utf-8"))
    cases = [case for case in selection["cases"]
             if args.group == "all" or case["group"] == args.group]
    if args.case:
        wanted = set(args.case)
        cases = [case for case in cases if case["case_id"] in wanted]
    words_root = Path(args.data_root) / "funds_word"
    run_dir = Path(args.output_root) / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    suffix = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(8))
    username = f"cloud-eval-{suffix}"
    password = secrets.token_urlsafe(18)
    results: list[dict] = []
    batch = {"run_id": args.run_id, "group": args.group, "username": username,
             "cases": [case["case_id"] for case in cases], "started": time.time()}

    with httpx.Client(base_url=BASE, timeout=180) as client:
        register = client.post("/api/auth/register", json={
            "username": username, "password": password, "display_name": "P6 评测账号"})
        if register.status_code >= 400:
            print("REGISTER_FAILED", register.status_code, register.text[:300])
            return 1
        login = client.post("/api/auth/login", json={"username": username, "password": password})
        headers = {"Authorization": "Bearer " + login.json()["token"]}

        # A republish while the batch is in flight changes ``engine_build()``; the queued
        # jobs then fail closed with ENGINE_SCHEMA_MISMATCH and the run is no longer a
        # single-engine comparison (FL-D096). The per-case error code below is the signal:
        # abort loudly instead of scoring a mixture of engine revisions.
        print("BATCH_START", args.run_id, args.group, flush=True)

        for case in cases:
            contract = words_root / case["file"]
            payload = contract.read_bytes()
            case_dir = run_dir / case["case_id"]
            case_dir.mkdir(parents=True, exist_ok=True)
            entry: dict = {"case_id": case["case_id"], "file": case["file"],
                           "sha256": case["sha256"], "bytes": len(payload)}
            started = time.time()
            create = client.post("/api/tasks", headers=headers, json={
                "name": f"P6-{case['case_id']}-{suffix}",
                "engine_id": "recall_first",
                "files": [{"client_id": "c1", "name": case["file"], "size": len(payload)}]})
            entry["task_create"] = create.status_code
            if create.status_code >= 400:
                entry["create_body"] = create.text[:300]
                results.append(entry)
                continue
            task_id = create.json()["id"]
            entry["task_id"] = task_id
            upload = client.post(
                f"/api/tasks/{task_id}/uploads", headers=headers,
                data={"client_ids": json.dumps(["c1"])},
                files=[("files", (case["file"], payload,
                                  "application/vnd.openxmlformats-officedocument."
                                  "wordprocessingml.document"))])
            entry["upload"] = upload.status_code
            receipts = upload.json().get("receipts") or []
            entry["upload_receipt"] = receipts[0].get("status") if receipts else None
            entry["seal"] = client.post(f"/api/tasks/{task_id}/seal", headers=headers).status_code
            status = None
            while time.time() - started < args.timeout:
                snapshot = client.get(f"/api/tasks/{task_id}", headers=headers).json()
                status = snapshot.get("status")
                if status in ("completed", "failed"):
                    break
                time.sleep(8)
            entry["task_status"] = status
            entry["waited_s"] = round(time.time() - started)
            documents = client.get(f"/api/tasks/{task_id}/documents", headers=headers).json()
            items = documents.get("items") or []
            if items:
                item = items[0]
                for key in ("job_status", "delivery_status", "error_code", "target_counts"):
                    entry[key] = item.get(key)
                report_url = (item.get("downloads") or {}).get("report_json")
                if report_url:
                    report = client.get(report_url, headers=headers).json()
                    (case_dir / "report.json").write_text(
                        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
                    entry["engine_id"] = report.get("engine_id")
                    entry["report_delivery_status"] = report.get("delivery_status")
                    model = report.get("model") or {}
                    entry["model"] = {k: model.get(k) for k in
                                      ("http_attempts", "calls", "estimated_cost_usd",
                                       "total_tokens", "input_tokens", "output_tokens")}
                    entry["facts"] = {
                        "fund_type": (report.get("facts") or {}).get("fund_type"),
                        "class_count": (report.get("facts") or {}).get("class_count"),
                        "service_group": (report.get("facts") or {}).get("service_group"),
                        "is_floating_fee": (report.get("facts") or {}).get("is_floating_fee")}
                    entry["targets"] = [{"rule_id": t.get("rule_id"), "state": t.get("state"),
                                         "status": t.get("status"), "location": t.get("location"),
                                         "origin": t.get("origin"),
                                         "reason": (t.get("reason") or "")[:80]}
                                        for t in (report.get("targets") or [])]
                    entry["unresolved"] = [{"kind": u.get("kind"), "code": u.get("code"),
                                            "rule_id": u.get("rule_id"),
                                            "location": u.get("location")}
                                           for u in (report.get("unresolved") or [])]
                    entry["sweep_findings"] = len((report.get("sweep") or {}).get("findings") or [])
                    entry["output_validation"] = {
                        k: (report.get("output_validation") or {}).get(k)
                        for k in ("kind", "final_sha256", "redline_sha256")}
                downloads = {}
                for kind, url in (items[0].get("downloads") or {}).items():
                    response = client.get(url, headers=headers)
                    if response.status_code == 200:
                        target = case_dir / (kind + Path(url).suffix)
                        target.write_bytes(response.content)
                        downloads[kind] = {"path": str(target), "bytes": len(response.content)}
                entry["downloads"] = downloads
            results.append(entry)
            (case_dir / "result.json").write_text(
                json.dumps(entry, ensure_ascii=False, indent=1), encoding="utf-8")
            print("CASE", case["case_id"], entry.get("task_status"),
                  entry.get("report_delivery_status"),
                  "targets=", len(entry.get("targets") or []),
                  "unresolved=", len(entry.get("unresolved") or []),
                  "cost=", (entry.get("model") or {}).get("estimated_cost_usd"),
                  flush=True)
            if entry.get("error_code") == "ENGINE_SCHEMA_MISMATCH":
                # A republish changed engine_build() while the batch was queued. The
                # remaining cases would run under a different engine revision, so the run
                # is not a single-engine comparison and must not be scored (FL-D096).
                batch["aborted"] = "ENGINE_SCHEMA_MISMATCH"
                batch["aborted_at"] = case["case_id"]
                print("BATCH_ABORTED ENGINE_SCHEMA_MISMATCH at", case["case_id"],
                      "- republished mid-run; discard this run", flush=True)
                break

    batch["results"] = results
    (run_dir / "batch.json").write_text(json.dumps(batch, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    totals = {
        "cases": len(results),
        "completed": sum(1 for row in results if row.get("task_status") == "completed"),
        "delivery_complete": sum(1 for row in results
                                 if row.get("report_delivery_status") == "complete"),
        "calls": sum((row.get("model") or {}).get("calls") or
                     (row.get("model") or {}).get("http_attempts") or 0 for row in results),
        "cost_usd": round(sum((row.get("model") or {}).get("estimated_cost_usd") or 0
                              for row in results), 4),
    }
    print("TOTALS", json.dumps(totals, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
