"""Build the built-in guide document from the source DOCX with the real model.

The runner extracts the guide DOCX, drives parse -> deterministic validation ->
independent verification with bounded repair rounds, writes the resulting guide
document and prints a concise summary. Exit code 0 only when the validation is
clean; exit code 1 when errors or verifier findings remain; exit code 2 when the
model transport or configuration fails.

Run (from the repository root, with the LLM_* variables present):

    .venv\\Scripts\\python.exe -X utf8 -m tools.build_builtin_guide \\
        --source references\\source\\<guide>.docx --output guides\\builtin_guide_v1.json \\
        --ledger var\\guide-build-ledger.sqlite --max-calls 12 --max-cost-usd 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from fundlex.guide import (GuideError, build_guide_document, extract_guide_source,
                           guide_document_sha256, save_guide_document)
from fundlex.model import ModelError, ModelGateway

DEFAULT_MAX_COMPLETION_TOKENS = 8000


def configure_environment(args: argparse.Namespace) -> None:
    """Apply CLI overrides before ModelGateway.from_env() reads the environment."""
    if args.ledger:
        os.environ["FUNDLEX_MODEL_LEDGER"] = str(Path(args.ledger).resolve())
    if args.max_calls is not None:
        os.environ["FUNDLEX_MODEL_MAX_REQUESTS"] = str(args.max_calls)
        os.environ["FUNDLEX_MODEL_MAX_CALLS"] = str(args.max_calls)
    if args.max_cost_usd is not None:
        os.environ["FUNDLEX_MODEL_MAX_COST_USD"] = str(args.max_cost_usd)
    if args.max_context_chars is not None:
        os.environ["FUNDLEX_MODEL_CONTEXT_CHARS"] = str(args.max_context_chars)
    os.environ["FUNDLEX_MODEL_MAX_OUTPUT_TOKENS"] = str(args.max_completion_tokens)


def summarize(document: dict, output: Path) -> dict:
    validation = document["validation"]
    model = document.get("model") or {}
    metrics = model.get("metrics") or {}
    budget = model.get("budget") or {}
    return {
        "output": str(output),
        "source_sha256": document["source_sha256"],
        "document_sha256": guide_document_sha256(document),
        "groups": len(document["groups"]),
        "rule_ids": [group.get("rule_id") for group in document["groups"]],
        "errors": validation["errors"],
        "warnings": validation["warnings"],
        "findings": validation["verification"]["findings"],
        "invalid_findings": validation["verification"]["invalid_findings"],
        "coverage_gaps": validation["coverage_gaps"],
        "rounds": validation["rounds"],
        "rounds_detail": validation.get("rounds_detail", []),
        "clean": validation["clean"],
        "logical_calls": model.get("logical_calls"),
        "http_attempts": metrics.get("http_attempts"),
        "estimated_cost_usd": round(float(metrics.get("estimated_cost_usd") or 0.0), 6),
        "budget": {"http_attempts": budget.get("http_attempts"), "estimated_cost_usd": budget.get("estimated_cost_usd"),
                   "max_http_attempts": budget.get("max_http_attempts"), "max_cost_usd": budget.get("max_cost_usd"),
                   "statuses": budget.get("statuses")},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build a guide document from the guide DOCX with the real model.")
    parser.add_argument("--source", required=True, help="path to the guide DOCX")
    parser.add_argument("--output", required=True, help="path of the guide JSON to write")
    parser.add_argument("--ledger", default=None, help="budget ledger SQLite path (defaults to the shared ledger)")
    parser.add_argument("--max-calls", type=int, default=None, help="hard logical-call and request cap")
    parser.add_argument("--max-cost-usd", type=float, default=None, help="hard estimated-cost cap")
    parser.add_argument("--max-completion-tokens", type=int, default=DEFAULT_MAX_COMPLETION_TOKENS,
                        help=f"completion token ceiling (default {DEFAULT_MAX_COMPLETION_TOKENS})")
    parser.add_argument("--max-context-chars", type=int, default=None, help="context character ceiling")
    parser.add_argument("--max-repair-rounds", type=int, default=2, help="bounded repair rounds after the first parse")
    args = parser.parse_args(argv)
    configure_environment(args)
    output = Path(args.output)
    try:
        gateway = ModelGateway.from_env()
    except ModelError as exc:
        print(json.dumps({"error": f"GATEWAY_CONFIG_FAILED:{exc.code}"}, ensure_ascii=False))
        return 2
    try:
        with gateway:
            source = extract_guide_source(args.source)
            document = build_guide_document(source, gateway, max_repair_rounds=args.max_repair_rounds)
    except GuideError as exc:
        print(json.dumps({"error": exc.code, "details": exc.details}, ensure_ascii=False))
        return 2
    save_guide_document(document, output)
    summary = summarize(document, output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["clean"] else 1


if __name__ == "__main__":
    sys.exit(main())
