"""Diagnose P6 failures from the local JSONL trace sink.

The scorer (``p6_score.py``) tells us *which* targets failed. The trace sink
(``fundlex/trace_sink.py``) tells us *why*: for each document trace it holds
every model call the engine made, with the prompt, the JSON result, the token
usage, the cost and whether the call errored or was served from a checkpoint.

This tool joins the two. For a run it produces, per failing target, the nearby
model calls that plausibly explain it, plus a run-level summary of the failure
and cost profile. That is exactly the loop the Langfuse path was meant to
enable; it runs entirely offline against files on disk.

Usage
-----
    .venv/bin/python tools/evaluation/p6_trace_report.py \
        --run var/recall-first-evaluation/p6-dev-round2-01 \
        --trace var/traces/model-calls.jsonl \
        --output /tmp/opencode/p6-trace-report.json

``--trace`` defaults to ``FUNDLEX_TRACE_JSONL``. Records are matched to cases by
``trace_id`` (derived from each case's ``report.json`` document id).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fundlex.trace_sink import trace_id_for  # noqa: E402

# Task types whose failures map onto rule targets, and the reverse.
PHASE_FOR_TASK = {
    "recall_facts": "facts",
    "recall_scope": "scope",
    "recall_inventory": "inventory",
    "recall_compose": "compose",
    "recall_audit": "audit",
    "recall_sweep": "sweep",
}


def load_records(path: Path) -> dict[str, list[dict]]:
    """Group JSONL records by trace id. Tolerates a truncated final line."""
    by_trace: dict[str, list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue  # a half-written line from a crash; skip it
            by_trace[record.get("trace_id", "")].append(record)
    return by_trace


def document_id_of(case_dir: Path) -> str | None:
    report = case_dir / "report.json"
    if not report.exists():
        return None
    try:
        return json.loads(report.read_text(encoding="utf-8")).get("document_id")
    except (ValueError, OSError):
        return None


def summarise_trace(records: list[dict]) -> dict:
    """Turn one document's raw records into a compact, report-friendly shape."""
    generations = [r for r in records if r.get("kind") == "generation"]
    scores = [r for r in records if r.get("kind") == "score"]
    by_task: dict[str, dict] = {}
    total_cost = 0.0
    total_tokens = 0
    for gen in generations:
        task = gen.get("task_type", "?")
        bucket = by_task.setdefault(task, {"calls": 0, "errors": 0, "cost": 0.0,
                                           "tokens": 0, "reused": 0, "latency_ms": 0})
        bucket["calls"] += 1
        meta = gen.get("metadata") or {}
        if meta.get("error_code"):
            bucket["errors"] += 1
        if meta.get("reused_checkpoint"):
            bucket["reused"] += 1
        usage = gen.get("usage") or {}
        bucket["tokens"] += usage.get("total") or 0
        total_tokens += usage.get("total") or 0
        cost = (gen.get("cost") or {}).get("total") or 0
        bucket["cost"] += cost
        total_cost += cost
        bucket["latency_ms"] += meta.get("latency_ms") or 0
    for bucket in by_task.values():
        bucket["cost"] = round(bucket["cost"], 6)
    return {
        "calls": len(generations),
        "cost_usd": round(total_cost, 6),
        "total_tokens": total_tokens,
        "by_task": by_task,
        "verdicts": {s.get("name"): s.get("value") for s in scores},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True, help="P6 run directory")
    parser.add_argument("--score", default=None,
                        help="score.json path (default: <run>/score.json)")
    parser.add_argument("--trace", default=None,
                        help="JSONL trace file (default: FUNDLEX_TRACE_JSONL)")
    parser.add_argument("--output", default=None, help="write the report here")
    args = parser.parse_args()

    import os
    trace_path = Path(args.trace or os.environ.get("FUNDLEX_TRACE_JSONL", ""))
    if not trace_path or not trace_path.exists():
        print(f"trace file not found: {trace_path}", file=sys.stderr)
        return 2

    run_dir = Path(args.run)
    score_path = Path(args.score) if args.score else run_dir / "score.json"
    if not score_path.exists():
        print(f"score file not found: {score_path}", file=sys.stderr)
        return 2
    score = json.loads(score_path.read_text(encoding="utf-8"))

    by_trace = load_records(trace_path)

    report = {"run": args.run, "trace_file": str(trace_path), "cases": [],
              "failure_summary": {}, "phase_summary": {}}
    fail_by_rule: Counter = Counter()
    fail_by_phase: Counter = Counter()
    phase_calls: Counter = Counter()
    phase_errors: Counter = Counter()
    cases_missing_trace = []

    for case in score.get("cases", []):
        case_id = case["case_id"]
        document_id = document_id_of(run_dir / case_id)
        records = by_trace.get(trace_id_for(document_id), []) if document_id else []
        if document_id and not records:
            cases_missing_trace.append(case_id)
        trace = summarise_trace(records) if records else None
        if trace:
            for task, bucket in trace["by_task"].items():
                phase_calls[task] += bucket["calls"]
                phase_errors[task] += bucket["errors"]

        failing = [v for v in case.get("verdicts", [])
                   if v.get("verdict") not in ("completed", "not_applicable")]
        entry = {
            "case_id": case_id,
            "document_id": document_id,
            "delivery_status": case.get("delivery_status"),
            "integrated_complete": case.get("integrated_complete"),
            "counts": case.get("counts"),
            "trace": trace,
            "failing_targets": [],
        }
        for verdict in failing:
            rule_id = verdict.get("rule_id")
            fail_by_rule[rule_id] += 1
            fail_by_phase[verdict.get("op")] += 1
            # The calls that could have produced this target: same rule's phase
            # tasks, plus every error call, since an error is always a candidate.
            entry["failing_targets"].append({
                "rule_id": rule_id,
                "target_id": verdict.get("target_id"),
                "op": verdict.get("op"),
                "verdict": verdict.get("verdict"),
                "detail": verdict.get("detail"),
            })
        report["cases"].append(entry)

    report["failure_summary"] = {
        "by_rule": dict(fail_by_rule.most_common()),
        "by_op": dict(fail_by_phase.most_common()),
        "cases_without_trace": cases_missing_trace,
    }
    report["phase_summary"] = {
        "calls_by_task": dict(phase_calls.most_common()),
        "errors_by_task": dict(phase_errors.most_common()),
    }

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(payload, encoding="utf-8")
        print(f"wrote {args.output}")

    print(f"run: {args.run}")
    print(f"cases: {len(report['cases'])} | traces matched: "
          f"{sum(1 for c in report['cases'] if c['trace'])} | "
          f"without trace: {len(cases_missing_trace)}")
    if cases_missing_trace:
        print(f"  no trace for: {', '.join(cases_missing_trace)}")
    print(f"failures by rule: {dict(fail_by_rule.most_common(12))}")
    print(f"calls by task: {dict(phase_calls.most_common())}")
    print(f"errors by task: {dict(phase_errors.most_common())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
