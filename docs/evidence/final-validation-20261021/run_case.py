"""Record/replay an exact-HEAD validation case without exposing credentials.

Only record reads the server's model configuration, in memory. Production data,
credentials, databases and budget ledgers are never copied into this directory.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
ROOT = Path(__file__).resolve().parent
RUNTIME = Path("/tmp/opencode/final-validation-20261021")


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("case", choices=("D01", "D02", "D11", "D16"))
    parser.add_argument("mode", choices=("record", "replay"))
    args = parser.parse_args()
    plan = json.loads((ROOT / "index.json").read_text())
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    if head != plan["validation_head"]:
        raise SystemExit("VALIDATION_HEAD_MISMATCH")
    frozen = ROOT / "frozen" / args.case
    output = ROOT / ("artifacts" if args.mode == "record" else "replay") / args.case
    output.mkdir(parents=True, exist_ok=True)
    ledger = RUNTIME / args.case / "ledger.sqlite"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == "record":
        if frozen.exists() or ledger.exists():
            raise SystemExit("RECORD_EXISTS: keep the old attempt; use a new validation directory")
        raw = subprocess.check_output(["sudo", "-n", "cat", "/etc/fundlex-recall.env"], text=True)
        for line in raw.splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            name = name.strip().removeprefix("export ")
            if name.startswith(("LLM_", "FUNDLEX_MODEL_", "FUNDLEX_PRIMARY_", "FUNDLEX_REVIEW_")):
                os.environ[name] = value.strip()
        os.environ.update(FUNDLEX_MODEL_LEDGER=str(ledger), FUNDLEX_MODEL_MAX_REQUESTS="192",
                          FUNDLEX_MODEL_MAX_COST_USD="0.6")
    else:
        from fundlex.frozen import FrozenRun
        FrozenRun(frozen).verify()
        config = json.loads((frozen / "validation-config.json").read_text())
        for name, value in config["replay_environment"].items():
            os.environ[name] = value
        # An HTTP attempt in replay is an error, including accidentally constructed
        # clients or a fallback path that bypasses the gateway's replay branch.
        import httpx
        def forbidden(*args, **kwargs):
            raise AssertionError("REPLAY_NETWORK_FORBIDDEN")
        httpx.Client.send = forbidden
    os.environ.update(FUNDLEX_MODEL_MODE=args.mode, FUNDLEX_FROZEN_RUN_DIR=str(frozen),
                      FUNDLEX_DATA_DIR=str(RUNTIME / args.case / "data"),
                      FUNDLEX_GENERATION_STRATEGY="registry")
    from fundlex.models.roles import build_role_gateway
    from fundlex.recall_pipeline import process_recall_first, RecallPipelineStop
    selection = json.loads((REPO / "var/recall-first-evaluation/p6/selection.json").read_text())
    filename = next(item["file"] for item in selection["cases"] if item["case_id"] == args.case)
    source = Path("/home/opencode/data/funds_word") / filename
    guide = json.loads((REPO / "guides/builtin_guide_v1.json").read_text())
    binding = {"case_id": args.case, "head": head, "branch": plan["branch"],
               "document_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
               "guide_document_sha256": plan["guide"]["guide_document_sha256"], "mode": args.mode}
    write(output / "binding.json", binding)
    started = time.monotonic()
    gateway = build_role_gateway()
    try:
        report = process_recall_first(source, output, guide_document=guide, gateway=gateway)
    except RecallPipelineStop as exc:
        report = json.loads((frozen / "report.json").read_text()) if (frozen / "report.json").exists() else {}
        report["validation_stop"] = {"code": exc.code, "detail": exc.detail}
    finally:
        gateway.close()
    write(output / "report.json", report)
    if args.mode == "record":
        # Safe replay settings: whitelist only semantic configuration, never headers,
        # endpoint credentials, environment dumps or transport object representations.
        names = ("LLM_MODEL", "LLM_PROVIDER", "FUNDLEX_MODEL_CONTEXT_CHARS", "FUNDLEX_MODEL_MAX_CALLS",
                 "FUNDLEX_MODEL_MAX_OUTPUT_TOKENS", "FUNDLEX_MODEL_TIMEOUT_S", "FUNDLEX_MODEL_RETRIES",
                 "FUNDLEX_MODEL_REQUEST_OPTIONS_JSON", "FUNDLEX_MODEL_CONCURRENCY", "FUNDLEX_REVIEW_CONCURRENCY")
        settings = {name: os.environ[name] for name in names if name in os.environ}
        for role, cfg in gateway.configs.items():
            prefix = "FUNDLEX_" + role.upper() + "_"
            settings.update({prefix + "MODEL": cfg.model, prefix + "PROVIDER": cfg.provider,
                             prefix + "CONTEXT_CHARS": str(cfg.max_context_chars),
                             prefix + "MAX_CALLS": str(cfg.max_calls), prefix + "MAX_TOKENS": str(cfg.max_tokens),
                             prefix + "TIMEOUT_S": str(cfg.timeout_s), prefix + "RETRIES": str(cfg.retries),
                             prefix + "REQUEST_OPTIONS_JSON": json.dumps(dict(cfg.request_options))})
        write(frozen / "validation-config.json", {**binding, "replay_environment": settings})
        from fundlex.frozen import atomic_json
        manifest = json.loads((frozen / "manifest.json").read_text())
        manifest["validation-config.json"] = hashlib.sha256((frozen / "validation-config.json").read_bytes()).hexdigest()
        atomic_json(frozen / "manifest.json", manifest)
        write(ROOT / "reports" / (args.case + ".json"), report)
        import sqlite3
        with sqlite3.connect(ledger) as db, (ROOT / "ledgers" / (args.case + ".csv")).open("w") as stream:
            writer = csv.writer(stream)
            rows = db.execute("SELECT id,started,status,reserved_cost,charged_cost,metadata FROM requests ORDER BY started,id")
            writer.writerow(["request_id", "started", "status", "reserved_cost", "charged_cost", "metadata"])
            writer.writerows(rows)
    records = (report.get("obligations") or {}).get("records") or []
    true = [item for item in records if (item.get("applicability") or {}).get("status") == "TRUE"]
    model = report.get("model") or {}
    summary = {**binding, "elapsed_seconds": round(time.monotonic() - started, 2),
               "delivery": report.get("delivery_status"), "calls": model.get("http_attempts"),
               "tokens": model.get("total_tokens"), "cost_usd": model.get("estimated_cost_usd"),
               "true_obligations": len(true), "completion_counts": (report.get("obligations") or {}).get("counts"),
               "true_not_applicable": sum(item.get("completion") == "NOT_APPLICABLE" for item in true),
               "claim_verified": (report.get("artifact_claim_replay") or {}).get("verified"),
               "unresolved_count": len(report.get("unresolved") or []), "errors": report.get("errors"),
               "stop": report.get("validation_stop")}
    write(ROOT / "summaries" / (args.case + "-" + args.mode + ".json"), summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
