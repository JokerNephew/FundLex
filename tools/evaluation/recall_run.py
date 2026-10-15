"""Library-level runner for the recall-first engine (development and evaluation).

Runs the real pipeline with a real model gateway on one contract or a directory of
contracts, keeping every artifact and the model ledger under the run directory.

Usage (PowerShell):
  .venv\\Scripts\\python.exe -X utf8 -m tools.evaluation.recall_run `
      --input funds_word --output var/recall-runs/dev-01 --pattern 品质回报 `
      --ledger var/recall-runs/dev-01/ledger.sqlite --max-calls 60 --max-cost-usd 2
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def _load_llm_environment() -> None:
    """Copy model settings from the Windows User scope into this process (no printing)."""
    names = ("LLM_PROVIDER", "LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY",
             "FUNDLEX_MODEL_EXTRA_HEADERS_JSON", "FUNDLEX_MODEL_USER_AGENT",
             "FUNDLEX_MODEL_REQUEST_OPTIONS_JSON")
    for name in names:
        if not os.environ.get(name):
            value = os.environ.get(name) or _user_env(name)
            if value:
                os.environ[name] = value


def _user_env(name: str) -> str:
    if sys.platform != "win32":
        return ""
    import subprocess
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"[Environment]::GetEnvironmentVariable('{name}','User')"],
            capture_output=True, text=True, timeout=30)
    except OSError:
        return ""
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the recall-first engine on real contracts")
    parser.add_argument("--input", required=True, help="DOCX file or directory of DOCX files")
    parser.add_argument("--output", required=True, help="run directory")
    parser.add_argument("--guide", default="guides/builtin_guide_v1.json")
    parser.add_argument("--pattern", default="", help="only files whose name contains this text")
    parser.add_argument("--limit", type=int, default=0, help="maximum number of contracts (0 = all)")
    parser.add_argument("--ledger", default="", help="model ledger sqlite path (default: <output>/ledger.sqlite)")
    parser.add_argument("--max-calls", type=int, default=120)
    parser.add_argument("--max-cost-usd", type=float, default=5.0)
    parser.add_argument("--context-chars", type=int, default=32000)
    parser.add_argument("--max-output-tokens", type=int, default=4000)
    parser.add_argument("--timeout-s", type=float, default=180.0)
    parser.add_argument("--business-rounds", type=int, default=3)
    parser.add_argument("--sweep-chunks", type=int, default=40)
    parser.add_argument("--resume", action="store_true", help="skip contracts with an existing report.json")
    args = parser.parse_args(argv)

    _load_llm_environment()
    os.environ["FUNDLEX_MODEL_LEDGER"] = args.ledger or str(Path(args.output) / "ledger.sqlite")
    os.environ["FUNDLEX_MODEL_MAX_CALLS"] = str(args.max_calls)
    # The ledger's own ceiling must match this run's cap: the per-process counter and
    # the shared ledger are separate limits, and a small default would stop the run.
    os.environ["FUNDLEX_MODEL_MAX_REQUESTS"] = str(args.max_calls)
    os.environ["FUNDLEX_MODEL_MAX_COST_USD"] = str(args.max_cost_usd)
    os.environ["FUNDLEX_MODEL_CONTEXT_CHARS"] = str(args.context_chars)
    os.environ["FUNDLEX_MODEL_MAX_OUTPUT_TOKENS"] = str(args.max_output_tokens)
    os.environ["FUNDLEX_MODEL_TIMEOUT_S"] = str(args.timeout_s)
    os.environ.setdefault("FUNDLEX_MODEL_INPUT_USD_PER_M", "0.15")
    os.environ.setdefault("FUNDLEX_MODEL_OUTPUT_USD_PER_M", "0.6")
    os.environ.setdefault("FUNDLEX_MODEL_CONCURRENCY", "1")

    from fundlex.guide import load_guide_document
    from fundlex.model import ModelGateway
    from fundlex.recall_pipeline import RecallPipelineStop, process_recall_first

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    guide = load_guide_document(args.guide)

    source = Path(args.input)
    if source.is_dir():
        files = sorted(path for path in source.glob("*.docx")
                       if not path.name.startswith("~$") and (args.pattern in path.name if args.pattern else True))
    else:
        files = [source]
    if args.limit:
        files = files[:args.limit]
    if not files:
        print("no input documents found")
        return 2

    summary: list[dict] = []
    started = time.time()
    for index, path in enumerate(files, start=1):
        contract_dir = output / f"{index:03d}-{path.stem[:40]}"
        contract_dir.mkdir(parents=True, exist_ok=True)
        report_path = contract_dir / "report.json"
        if args.resume and report_path.exists():
            report = json.loads(report_path.read_text(encoding="utf-8"))
            print(f"[{index}/{len(files)}] {path.name}: cached {report.get('delivery_status')}")
            summary.append(_summary_row(path, report))
            continue
        gateway = ModelGateway.from_env()
        print(f"[{index}/{len(files)}] {path.name}: running")
        try:
            report = process_recall_first(path, contract_dir, guide_document=guide, gateway=gateway,
                                          execution_mode="evaluation",
                                          max_business_rounds=args.business_rounds,
                                          max_sweep_chunks=args.sweep_chunks)
        except RecallPipelineStop as stop:
            report = {"engine_id": "recall_first", "delivery_status": "stopped",
                      "error_code": f"STOP:{stop.code}", "source_sha256": "", "targets": []}
            print(f"    STOP {stop.code}")
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        metrics = report.get("model") or {}
        print(f"    status={report.get('delivery_status')} targets={len(report.get('targets') or [])} "
              f"edits={((report.get('plan') or {}).get('count'))} "
              f"calls={metrics.get('http_attempts')} cost={round(metrics.get('estimated_cost_usd') or 0, 4)} "
              f"duration={round((report.get('duration_ms') or 0) / 1000)}s")
        summary.append(_summary_row(path, report))

    summary_path = output / "summary.json"
    summary_path.write_text(json.dumps({
        "input": str(source), "pattern": args.pattern, "contracts": summary,
        "elapsed_s": round(time.time() - started, 1),
        "ledger": os.environ["FUNDLEX_MODEL_LEDGER"],
        "limits": {"max_calls": args.max_calls, "max_cost_usd": args.max_cost_usd,
                   "context_chars": args.context_chars},
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"summary: {summary_path}")
    return 0


def _summary_row(path: Path, report: dict) -> dict:
    plan = report.get("plan") or {}
    metrics = report.get("model") or {}
    targets = report.get("targets") or []
    return {
        "file": path.name,
        "delivery_status": report.get("delivery_status"),
        "error_code": report.get("error_code"),
        "targets": len(targets),
        "needs_edit": sum(1 for item in targets if item.get("state") == "needs_edit"),
        "edits": plan.get("count"),
        "unresolved": len(report.get("unresolved") or []),
        "calls": metrics.get("http_attempts"),
        "cost_usd": metrics.get("estimated_cost_usd"),
        "duration_ms": report.get("duration_ms"),
        "final_sha256": (report.get("output_validation") or {}).get("final_sha256"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
