"""Real task-workbench revision run: task API -> worker -> evaluation downloads.

This is the integration acceptance entry for the contract-revision mode: it
creates a persistent task, uploads the DOCX files through the owner-scoped API,
drains the default worker (which dispatches v2 by ruleset version) and verifies
the downloaded evaluation artifacts against the server-reported hashes.

Run::

    .venv\\Scripts\\python.exe -X utf8 -m tools.evaluation.task_revision_run \\
        --input <docx dir> --output <run dir> --task-name <name>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.jobs import Worker

OWNER = "task-revision-run"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--task-name", default="合同修订（评测）任务")
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--upload-chunk", type=int, default=20)
    args = parser.parse_args()
    files = sorted(Path(args.input).glob("*.docx"))
    if args.expected_count is not None and len(files) != args.expected_count:
        raise SystemExit(f"expected {args.expected_count} files, found {len(files)}")
    if not files:
        raise SystemExit("no DOCX inputs")
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    state = root / "state"
    app = create_app(state)
    client = TestClient(app)
    headers = {"X-FundLex-User": OWNER}
    manifest = [{"client_id": f"c{index}", "name": path.name, "size": path.stat().st_size}
                for index, path in enumerate(files, start=1)]
    dataset_hash = sha256_bytes(json.dumps(
        [(item["name"], sha256_file(path)) for item, path in zip(manifest, files)],
        ensure_ascii=False, sort_keys=True).encode())
    response = client.post("/api/tasks", headers={**headers, "Idempotency-Key": "task-" + dataset_hash[:24]},
                           json={"name": args.task_name, "ruleset_version": "v2", "files": manifest})
    response.raise_for_status()
    task_id = response.json()["id"]
    receipts = []
    for offset in range(0, len(files), args.upload_chunk):
        group = files[offset:offset + args.upload_chunk]
        ids = [f"c{offset + index + 1}" for index in range(len(group))]
        upload = client.post(f"/api/tasks/{task_id}/uploads", headers=headers,
                             data={"client_ids": json.dumps(ids)},
                             files=[("files", (path.name, path.read_bytes())) for path in group])
        upload.raise_for_status()
        receipts.extend(upload.json()["receipts"])
    assert all(item["status"] == "accepted" for item in receipts), receipts
    client.post(f"/api/tasks/{task_id}/seal", headers=headers).raise_for_status()
    started = time.monotonic()
    worker = Worker(app.state.store)
    while worker.run_once():
        pass
    duration_s = round(time.monotonic() - started, 1)
    summary = client.get(f"/api/tasks/{task_id}", headers=headers).json()
    documents = client.get(f"/api/tasks/{task_id}/documents", headers=headers,
                           params={"page_size": 200}).json()
    artifacts_root = root / "docx"
    records = []
    for document in documents["items"]:
        report = client.get(document["report_url"], headers=headers).json() if document["report_url"] else {}
        folder = artifacts_root / Path(document["name"]).stem
        folder.mkdir(parents=True, exist_ok=True)
        validation = report.get("output_validation") or {}
        saved = {}
        for kind, hash_key in (("final", "final_sha256"), ("redline", "redline_sha256"),
                               ("evaluation_final", "final_sha256"), ("evaluation_redline", "redline_sha256")):
            url = (document.get("downloads") or {}).get(kind)
            if not url:
                continue
            delivered = client.get(url, headers=headers)
            delivered.raise_for_status()
            target = folder / f"{kind}.docx"
            target.write_bytes(delivered.content)
            assert sha256_file(target) == validation.get(hash_key), f"{kind} hash mismatch"
            saved[kind] = str(target.resolve())
        records.append({"name": document["name"], "document_id": document["document_id"],
                        "eligibility": document["eligibility"], "delivery_status": document["delivery_status"],
                        "execution_mode": document["execution_mode"], "error_code": document["error_code"],
                        "reason_codes": document["reason_codes"],
                        "edits": report.get("edit_plan", {}).get("count", 0),
                        "final_sha256": validation.get("final_sha256"),
                        "artifacts": saved, "report": report})
    result = {"schema": "task-revision-run-1", "task_id": task_id, "task_name": args.task_name,
              "ruleset_version": summary["ruleset_version"], "ruleset_sha256": summary["ruleset_sha256"],
              "documents": len(records), "delivery_counts": summary["delivery_counts"],
              "qualification_counts": summary["qualification_counts"],
              "duration_s": duration_s, "receipts": receipts, "records": records}
    write(root / "summary.json", result)
    lines = [f"# 任务修订运行：{args.task_name}", "",
             f"- 任务 ID：{task_id}",
             f"- 规则：{summary['ruleset_version']}（{summary['ruleset_sha256']}）",
             f"- 合同：{len(records)} 份；处理耗时 {duration_s}s",
             f"- 资格：{summary['qualification_counts']}",
             f"- 交付：{summary['delivery_counts']}", "",
             "| 合同 | 资格 | 交付状态 | 修改处数 | 评测修改版 SHA-256 |", "| --- | --- | --- | --- | --- |"]
    for record in records:
        lines.append(f"| {record['name']} | {record['eligibility']} | {record['delivery_status']} "
                     f"| {record['edits']} | {(record['final_sha256'] or '')[:16]} |")
    (root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"task_id": task_id, "documents": len(records), "delivery": summary["delivery_counts"],
                      "duration_s": duration_s}, ensure_ascii=False))


if __name__ == "__main__":
    main()
