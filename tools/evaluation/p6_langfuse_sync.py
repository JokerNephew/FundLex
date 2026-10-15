"""Push P6 evaluation verdicts onto their Langfuse traces as scores.

This is the "process <-> outcome" bridge: the worker traced every model call
per document (see ``fundlex/observability.py``), and this tool replays the
scorer's verdicts back onto those same traces, so a failing target can be
inspected next to the exact model calls that produced it.

Ordering matters: run the batch **with tracing enabled** first, then score it,
then run this. Traces are keyed by the document id, which the scorer receives
via each case's ``report.json``.

Usage
-----
    FUNDLEX_LANGFUSE_PUBLIC_KEY=... FUNDLEX_LANGFUSE_SECRET_KEY=... \\
        .venv/bin/python tools/evaluation/p6_langfuse_sync.py \\
            --run var/recall-first-evaluation/p6-dev-round1-01 \\
            --labels var/recall-first-evaluation/p6/labels.json

Each target verdict becomes a ``target_verdict`` categorical score; each case
also gets numeric ``target_completion_rate`` and a boolean
``delivery_false_complete`` so trends are visible in the Langfuse dashboard.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fundlex import observability  # noqa: E402


def _document_id(case_dir: Path) -> str | None:
    report = case_dir / "report.json"
    if not report.exists():
        return None
    try:
        return json.loads(report.read_text(encoding="utf-8")).get("document_id")
    except (ValueError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--score", default=None, help="score.json path (default: <run>/score.json)")
    parser.add_argument("--run", required=True, help="run directory")
    parser.add_argument("--dry-run", action="store_true", help="print what would be sent, do not call Langfuse")
    args = parser.parse_args()

    run_dir = Path(args.run)
    score_path = Path(args.score) if args.score else run_dir / "score.json"
    if not score_path.exists():
        print(f"score file not found: {score_path}", file=sys.stderr)
        return 2
    payload = json.loads(score_path.read_text(encoding="utf-8"))

    if not args.dry_run and not observability.enabled():
        print("Langfuse is not configured (set FUNDLEX_LANGFUSE_PUBLIC_KEY/SECRET_KEY).", file=sys.stderr)
        return 3

    sent, skipped = 0, 0
    for case in payload.get("cases", []):
        case_id = case["case_id"]
        document_id = _document_id(run_dir / case_id)
        if not document_id:
            skipped += 1
            print(f"  skip {case_id}: no report.json/document_id")
            continue
        verdicts = case.get("verdicts", [])
        completed = sum(1 for v in verdicts if v.get("verdict") == "completed")
        rate = round(completed / len(verdicts), 4) if verdicts else 0.0
        if args.dry_run:
            print(f"  {case_id} -> trace seed fundlex:{document_id}: "
                  f"{len(verdicts)} verdicts, rate={rate}")
            for v in verdicts:
                print(f"      {v.get('rule_id')} {v.get('target_id')} = {v.get('verdict')}")
            continue
        for v in verdicts:
            observability.record_score(
                name="target_verdict", value=v.get("verdict") or "unknown",
                trace_seed=document_id, data_type="CATEGORICAL",
                comment=v.get("detail") or None,
                metadata={"case_id": case_id, "rule_id": v.get("rule_id"),
                          "target_id": v.get("target_id")})
            sent += 1
        observability.record_score(
            name="target_completion_rate", value=rate, trace_seed=document_id,
            data_type="NUMERIC", metadata={"case_id": case_id})
        false_complete = bool(case.get("reported_complete")) and not bool(case.get("actually_complete"))
        if case.get("reported_complete") is not None:
            observability.record_score(
                name="delivery_false_complete", value=false_complete,
                trace_seed=document_id, data_type="BOOLEAN",
                metadata={"case_id": case_id})

    if not args.dry_run:
        observability.flush()
        print(f"pushed {sent} verdict scores; skipped {skipped} cases without a document id")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
