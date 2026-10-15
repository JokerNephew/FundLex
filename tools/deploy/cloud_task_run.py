"""Run one real contract through the cloud workbench (recall-first engine).

Uploads a real DOCX to the server, submits a recall-first task as a temporary user,
waits for the worker, then downloads the produced artifacts to a local directory and
prints the report highlights. The temporary account and its task are removed afterwards.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.cloud_task_run `
      --contract "funds_word\\广发品质回报混合型证券投资基金基金合同_20230708.docx" `
      --output var/cloud-runs/quality-return-01 [--keep] [--timeout-min 40]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SERVER_RUNNER = r'''
import io, json, os, random, secrets, string, sys, time
from pathlib import Path
import httpx

sys.path.insert(0, "/opt/fundlex-recall-first")
env = {}
for line in open("/etc/fundlex-recall.env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        key, value = line.split("=", 1)
        env[key] = value
for key, value in env.items():
    os.environ.setdefault(key, value)

from fundlex.store import RunStore
from fundlex.auth import UserStore, SessionStore

payload = open(sys.argv[1], "rb").read()
filename = sys.argv[2]
timeout_s = float(sys.argv[3])

store = RunStore(env["FUNDLEX_DATA_DIR"])
users = UserStore(store.database)
sessions = SessionStore(store.database)

suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
username = f"cloud-run-{suffix}"
password = secrets.token_urlsafe(18)
user = users.create_user(username=username, password=password, display_name="云端验证账号", role="member")
base = "http://127.0.0.1:8010"
out = {"username": username, "user_id": user["id"]}
task_id = None
try:
    with httpx.Client(base_url=base, timeout=120) as client:
        login = client.post("/api/auth/login", json={"username": username, "password": password})
        out["login"] = login.status_code
        headers = {"Authorization": "Bearer " + login.json()["token"]}
        create = client.post("/api/tasks", headers=headers, json={
            "name": f"云端真实运行-{filename[:20]}-{suffix}",
            "engine_id": "recall_first",
            "files": [{"client_id": "c1", "name": filename, "size": len(payload)}],
        })
        out["task_create"] = create.status_code
        task = create.json()
        task_id = task["id"]
        out["task_id"] = task_id
        out["guide_snapshot"] = task.get("guide_snapshot")
        upload = client.post(f"/api/tasks/{task_id}/uploads", headers=headers,
                             data={"client_ids": json.dumps(["c1"])},
                             files=[("files", (filename, payload,
                                               "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))])
        out["upload"] = upload.status_code
        receipts = upload.json().get("receipts") or []
        out["upload_receipt"] = receipts[0].get("status") if receipts else None
        document_id = receipts[0].get("document_id") if receipts else None
        out["document_id"] = document_id
        out["seal"] = client.post(f"/api/tasks/{task_id}/seal", headers=headers).status_code

        started = time.time()
        status = None
        while time.time() - started < timeout_s:
            snapshot = client.get(f"/api/tasks/{task_id}", headers=headers).json()
            status = snapshot.get("status")
            if status in ("completed", "failed"):
                break
            time.sleep(10)
        out["task_status"] = status
        out["waited_s"] = round(time.time() - started)
        documents = client.get(f"/api/tasks/{task_id}/documents", headers=headers).json()
        items = documents.get("items") or []
        if items:
            item = items[0]
            out["job_status"] = item.get("job_status")
            out["delivery_status"] = item.get("delivery_status")
            out["error_code"] = item.get("error_code")
            out["target_counts"] = item.get("target_counts")
            report_url = item.get("report_url")
            if report_url:
                report = client.get(report_url, headers=headers).json()
                out["engine_id"] = report.get("engine_id")
                out["duration_ms"] = report.get("duration_ms")
                out["model"] = {k: report.get("model", {}).get(k)
                                for k in ("http_attempts", "estimated_cost_usd", "total_tokens")}
                out["qualification"] = (report.get("qualification") or {}).get("status")
                out["facts_summary"] = {
                    "fund_type": (report.get("facts") or {}).get("fund_type"),
                    "class_count": (report.get("facts") or {}).get("class_count"),
                    "service_group": (report.get("facts") or {}).get("service_group"),
                    "subscription_group": (report.get("facts") or {}).get("subscription_group"),
                    "is_floating_fee": (report.get("facts") or {}).get("is_floating_fee"),
                }
                out["targets"] = [
                    {"rule_id": t.get("rule_id"), "state": t.get("state"), "status": t.get("status"),
                     "location": t.get("location"), "reason": (t.get("reason") or "")[:80]}
                    for t in (report.get("targets") or [])
                ]
                out["plan"] = {
                    "count": (report.get("plan") or {}).get("count"),
                    "edits": [
                        {"rule_id": e.get("rule_id"), "location": e.get("location"),
                         "replacement_head": (e.get("replacement") or "")[:100]}
                        for e in ((report.get("plan") or {}).get("edits") or [])
                    ],
                }
                out["unresolved"] = [
                    {"kind": u.get("kind"), "code": u.get("code"), "rule_id": u.get("rule_id"),
                     "reason": (u.get("reason") or "")[:120]}
                    for u in (report.get("unresolved") or [])
                ]
                out["sweep_findings"] = len((report.get("sweep") or {}).get("findings") or [])
                out["output_validation"] = {
                    k: (report.get("output_validation") or {}).get(k)
                    for k in ("kind", "final_sha256", "redline_sha256")
                }
                out["artifacts"] = report.get("artifacts")
        # download artifacts
        downloads = {}
        if items and items[0].get("downloads"):
            for kind, url in items[0]["downloads"].items():
                response = client.get(url, headers=headers)
                if response.status_code == 200:
                    target = sys.argv[4] + "/" + kind + Path(url).suffix
                    os.makedirs(sys.argv[4], exist_ok=True)
                    open(target, "wb").write(response.content)
                    downloads[kind] = {"path": target, "bytes": len(response.content),
                                       "etag": response.headers.get("etag")}
        out["downloads"] = downloads
finally:
    keep = len(sys.argv) > 5 and sys.argv[5] == "keep"
    if not keep:
        try:
            with store.database.connect() as db:
                if task_id:
                    batches = db.execute("SELECT batch_id FROM task_batches WHERE task_id=?", (task_id,)).fetchall()
                    for batch in batches:
                        bid = batch["batch_id"] if isinstance(batch, dict) else batch[0]
                        db.execute("DELETE FROM artifacts WHERE document_id IN (SELECT id FROM documents WHERE batch_id=?)", (bid,))
                        db.execute("DELETE FROM documents WHERE batch_id=?", (bid,))
                        db.execute("DELETE FROM task_batches WHERE batch_id=?", (bid,))
                        db.execute("DELETE FROM batches WHERE id=?", (bid,))
                    db.execute("DELETE FROM task_files WHERE task_id=?", (task_id,))
                    db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
                db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
                db.execute("DELETE FROM users WHERE id=?", (user["id"],))
            out["cleanup"] = "done"
        except Exception as exc:
            out["cleanup"] = f"failed: {type(exc).__name__}: {exc}"
    else:
        out["cleanup"] = "kept"
print("RUN_JSON:" + json.dumps(out, ensure_ascii=False, default=str))
'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a real contract through the cloud workbench")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True, help="local directory for downloaded artifacts")
    parser.add_argument("--timeout-min", type=float, default=40)
    parser.add_argument("--keep", action="store_true", help="keep the temporary user and task")
    args = parser.parse_args(argv)

    contract = Path(args.contract)
    if not contract.exists():
        contract = REPO / args.contract
    if not contract.exists():
        raise SystemExit(f"contract not found: {args.contract}")
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, load_credentials
    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        sftp = client.open_sftp()
        remote_contract = f"/tmp/fundlex-contract-{int(time.time())}.docx"
        sftp.put(str(contract), remote_contract)
        with sftp.open("/tmp/fundlex_cloud_run.py", "w") as handle:
            handle.write(SERVER_RUNNER)
        remote_out = f"/tmp/fundlex-cloud-out-{int(time.time())}"
        sftp.close()
        print(f"uploaded {contract.name} ({contract.stat().st_size} bytes); running")
        command = (f"/opt/fundlex-recall-first/.venv/bin/python -X utf8 /tmp/fundlex_cloud_run.py "
                   f"{remote_contract} '{contract.name}' {int(args.timeout_min * 60)} {remote_out}"
                   + (" keep" if args.keep else ""))
        stdin, stdout, stderr = client.exec_command(command, timeout=args.timeout_min * 60 + 600)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        data = None
        for line in out.splitlines():
            if line.startswith("RUN_JSON:"):
                data = json.loads(line[len("RUN_JSON:"):])
        if data is None:
            print("no result; stderr tail:")
            print(err[-3000:])
            return 1
        (output / "cloud_run.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        sftp = client.open_sftp()
        try:
            for entry in sftp.listdir(remote_out):
                sftp.get(remote_out + "/" + entry, str(output / entry))
                print("downloaded:", entry, (output / entry).stat().st_size, "bytes")
        except IOError:
            print("no artifacts downloaded")
        finally:
            sftp.close()
        for key in ("task_status", "job_status", "delivery_status", "error_code", "engine_id",
                    "duration_ms", "model", "qualification", "facts_summary", "plan",
                    "sweep_findings", "output_validation", "artifacts", "cleanup", "waited_s"):
            print(f"  {key}: {data.get(key)}")
        print("  targets:")
        for target in data.get("targets") or []:
            print("   -", target)
        print("  unresolved:")
        for item in (data.get("unresolved") or [])[:8]:
            print("   -", item)
        if code != 0:
            print("stderr tail:", err[-1500:])
        client.exec_command(f"rm -f {remote_contract} /tmp/fundlex_cloud_run.py; rm -rf {remote_out}")
    finally:
        client.close()
    print(f"results written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
