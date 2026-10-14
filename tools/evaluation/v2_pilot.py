"""Bounded real-model v2 evaluation runner through the real API and worker.

Runs evaluation-mode batches with ``process_v2``, downloads the persisted
evaluation artifacts through the owner-scoped API and records every report for
the independent scorer. The global budget ledger and caps come from the
environment; this runner never enlarges them on its own.

Run (from the repository root, after registering a bounded budget):

    .venv\\Scripts\\python.exe -X utf8 -m tools.evaluation.v2_pilot --input <docx dir> \\
        --output <run dir> --expected-count 16 --batch-size 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from pathlib import Path

from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.jobs import Worker
from fundlex.model import ModelGateway
from fundlex.rules_v2 import PROMPT_VERSIONS_V2, load_ruleset_v2
from fundlex.store import engine_build
from fundlex.v2_pipeline import STOP_CODES, process_v2

OWNER = "v2-evaluation"


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
    parser.add_argument("--expected-count", type=int)
    parser.add_argument("--batch-size", type=int, default=1, choices=[1, 2, 3])
    args = parser.parse_args()
    files = sorted(Path(args.input).glob("*.docx"))
    if args.expected_count is not None and len(files) != args.expected_count:
        raise SystemExit(f"expected {args.expected_count} DOCX files, found {len(files)}")
    if not files:
        raise SystemExit("no DOCX inputs")
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = [{"file": str(path.resolve()), "source_sha256": sha256_file(path),
                 "size": path.stat().st_size} for path in files]
    dataset_hash = sha256_bytes(json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode())
    ruleset = load_ruleset_v2("v2")
    if ruleset.auto_write_enabled:
        raise SystemExit("v2 evaluation requires closed write gates")
    gateway = ModelGateway.from_env()
    # Worst case per contract: 1 fund type + 1 profile + up to 3 locate windows
    # + up to 3 generation calls + up to 3 verification calls = 11 logical calls
    # (each HTTP attempt additionally reserves its own worst-case cost and a
    # retry reserves again; the shared ledger enforces the registered cap).
    worst_case_per_contract = 2 + 3 + 3 + 3
    protocol = {
        "schema": "v2-evaluation-1",
        "dataset_sha256": dataset_hash,
        "document_count": len(files),
        "ruleset_version": ruleset.version,
        "ruleset_sha256": ruleset.sha256,
        "engine_build": engine_build(),
        "model": gateway.model,
        "provider": gateway.provider,
        "request_options_sha256": sha256_bytes(json.dumps(gateway.request_options, sort_keys=True).encode()),
        "prompt_versions": PROMPT_VERSIONS_V2,
        "execution_mode": "evaluation",
        "batch_size": args.batch_size,
        "workers": 1,
        "model_concurrency": gateway.budget.concurrency,
        "max_context_chars": gateway.max_context_chars,
        "max_output_tokens": gateway.max_completion_tokens,
        "budget": gateway.budget.snapshot(),
        "worst_case_calls_per_contract": worst_case_per_contract,
        "worst_case_calls_total": worst_case_per_contract * len(files),
        "purpose": "bounded evaluation of rule-constrained locate/generate/verify edits",
        "automatic_write": False,
        "releasable_contract": False,
    }
    protocol["budget_configuration"] = {key: protocol["budget"][key] for key in
                                        ("max_http_attempts", "max_cost_usd", "concurrency",
                                         "rates_usd_per_million")}
    protocol_path = root / "protocol.json"
    if protocol_path.exists():
        old = json.loads(protocol_path.read_text(encoding="utf-8"))
        keys = ("dataset_sha256", "ruleset_sha256", "engine_build", "model",
                "request_options_sha256", "prompt_versions", "budget_configuration")
        if any(old.get(key) != protocol.get(key) for key in keys):
            raise SystemExit("protocol changed: use a new evaluation run directory")
    else:
        write(protocol_path, protocol)
        write(root / "manifest.json", manifest)
    state_root = Path(os.environ.get("FUNDLEX_V2_STATE_DIR",
                                     str(Path(os.environ.get("FUNDLEX_DATA_DIR", root)) / "state")))
    app = create_app(state_root)
    client = TestClient(app)
    headers = {"X-FundLex-User": OWNER}
    artifacts_root = root / "docx"
    artifacts_root.mkdir(exist_ok=True)
    stopped: list[str] = []

    def processor(source: Path, output: Path, version: str):
        with ModelGateway.from_env() as model:
            report = process_v2(source, output, version, model, evaluation=True)
        if report.get("error_code") in STOP_CODES:
            stopped.append(report["error_code"])
        if any(target.get("reason") in STOP_CODES
               for action in report.get("actions", []) for target in action.get("targets", [])):
            stopped.append("MODEL_BUDGET_OR_SERVICE_STOP")
        return report

    worker = Worker(app.state.store, processor)
    batches: list[str] = []
    records: list[dict] = []
    for offset in range(0, len(files), args.batch_size):
        group = files[offset:offset + args.batch_size]
        request_key = sha256_bytes((dataset_hash + ":" + str(offset)).encode())
        response = client.post("/api/batches", headers={**headers, "Idempotency-Key": request_key},
                               data={"ruleset_version": "v2"},
                               files=[("files", (path.name, path.read_bytes())) for path in group])
        response.raise_for_status()
        batch_id = response.json()["id"]
        batches.append(batch_id)
        deadline = time.monotonic() + len(group) * 900 + 240
        while True:
            detail = client.get(f"/api/batches/{batch_id}", headers=headers).json()
            if detail["status"] == "completed":
                break
            if detail["status"] == "paused" or stopped:
                write(root / "stopped.json", {"batch_id": batch_id, "batch_offset": offset,
                                              "reasons": stopped or ["BATCH_PAUSED"],
                                              "budget": ModelGateway.from_env().budget.snapshot()})
                raise SystemExit("evaluation stopped safely; inspect stopped.json")
            if time.monotonic() > deadline:
                raise SystemExit("batch execution deadline exceeded")
            if not worker.run_once():
                time.sleep(0.5)
        batch_reports = []
        for document in detail["documents"]:
            report = client.get(document["report_url"], headers=headers)
            report.raise_for_status()
            report = report.json()
            assert report.get("execution_mode") == "evaluation", "evaluation mode must persist"
            assert "final" not in document["downloads"] and "redline" not in document["downloads"]
            folder = artifacts_root / Path(document["name"]).stem
            folder.mkdir(parents=True, exist_ok=True)
            validation = report.get("output_validation") or {}
            for kind, hash_key, name in (("evaluation_final", "final_sha256", "evaluation_final.docx"),
                                         ("evaluation_redline", "redline_sha256", "evaluation_redline.docx")):
                url = document["downloads"].get(kind)
                if not url:
                    continue
                delivered = client.get(url, headers=headers)
                delivered.raise_for_status()
                target = folder / name
                target.write_bytes(delivered.content)
                assert sha256_file(target) == validation.get(hash_key), f"{kind} download hash mismatch"
            batch_reports.append({
                "document_id": document["document_id"], "name": document["name"],
                "delivery_status": document["delivery_status"], "report": report,
                "downloads": document["downloads"],
                "final_docx": str((folder / "evaluation_final.docx").resolve())
                if (folder / "evaluation_final.docx").is_file() else None,
                "redline_docx": str((folder / "evaluation_redline.docx").resolve())
                if (folder / "evaluation_redline.docx").is_file() else None,
            })
        write(root / f"batch_{offset // args.batch_size + 1:03}.json", batch_reports)
        records.extend(batch_reports)
        budget = ModelGateway.from_env().budget.snapshot()
        summary = summarize(records, batches, budget, dataset_hash, len(files), ruleset.sha256, protocol["engine_build"])
        write(root / "summary.json", summary)
        print(json.dumps({"batch": offset // args.batch_size + 1, "evaluated": summary["evaluated"],
                          "delivery": summary["delivery"], "http_attempts": budget["http_attempts"],
                          "estimated_cost_usd": round(budget["estimated_cost_usd"], 6)}, ensure_ascii=False),
              flush=True)
    unchanged = all(sha256_file(Path(item["file"])) == item["source_sha256"] for item in manifest)
    summary = summarize(records, batches, ModelGateway.from_env().budget.snapshot(), dataset_hash,
                        len(files), ruleset.sha256, protocol["engine_build"])
    summary["source_files_unchanged"] = unchanged
    summary["completed"] = unchanged and summary["evaluated"] == len(files)
    write(root / "summary.json", summary)
    lines = ["# FundLex v2 评测运行", "",
             f"- 文档：{summary['evaluated']}/{len(files)}",
             f"- 规则：v2 {ruleset.sha256}",
             f"- 执行模式：evaluation（不构成正式最终合同）",
             f"- 交付统计：{summary['delivery']}",
             f"- 修改数合计：{summary['edits_total']}",
             f"- 源文件未改变：{unchanged}",
             f"- 预算：{summary['budget']}"]
    (root / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert summary["completed"]


def summarize(records: list[dict], batches: list[str], budget: dict, dataset_hash: str,
              document_count: int, ruleset_sha256: str, engine: str) -> dict:
    from collections import Counter
    delivery = Counter(item["delivery_status"] for item in records)
    actions: dict[str, Counter] = {}
    target_reasons = Counter()
    edits_total = 0
    tokens = Counter()
    for item in records:
        report = item["report"]
        edits_total += report.get("edit_plan", {}).get("count", 0) or 0
        for action in report.get("actions", []):
            counter = actions.setdefault(action["action_id"], Counter())
            counter[action["status"]] += 1
            for target in action.get("targets", []):
                if target.get("reason"):
                    target_reasons[target["reason"]] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens", "http_attempts",
                    "error_count", "rate_limit_count", "checkpoint_reuses"):
            tokens[key] += report.get("model", {}).get(key) or 0
    return {"schema": "v2-evaluation-summary-1", "evaluated": len(records),
            "batch_ids": batches, "dataset_sha256": dataset_hash, "document_count": document_count,
            "ruleset_sha256": ruleset_sha256, "engine_build": engine,
            "delivery": dict(delivery), "actions": {key: dict(value) for key, value in actions.items()},
            "target_reasons": dict(target_reasons), "edits_total": edits_total,
            "model_usage": dict(tokens), "budget": budget, "automatic_write_enabled": False,
            "releasable_contract": False}


if __name__ == "__main__":
    main()
