#!/usr/bin/env python3
"""Compare two scored wave runs (v1 vs v2) at metric / rule / case granularity.

Reads two ``score.json`` files produced by ``score_first_batch_20261029.py``
plus both run summaries, and prints a Markdown comparison table.  Pure reader:
never rewrites artifacts.  Label changes between runs are flagged, not
silently counted as improvement (EVALUATION_AND_OPTIMIZATION_PLAN §8).

Usage:
    compare_wave_runs_20261031.py --v1-score S1 --v2-score S2 \
        [--v1-run DIR] [--v2-run DIR] [--output OUT.md]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _totals(score: dict) -> dict:
    totals = score.get("totals") or {}
    delivery = score.get("delivery") or {}
    return {
        "targets": totals.get("targets"),
        "completed": totals.get("completed"),
        "rate": totals.get("target_completion_rate"),
        "verdicts": totals.get("verdicts") or {},
        "reported_complete": delivery.get("reported_complete"),
        "actually_complete": delivery.get("actually_complete"),
        "false_complete": delivery.get("false_complete"),
        "editable_cases": delivery.get("editable_cases"),
    }


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value * 100:.1f}%"
    return str(value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v1-score", required=True)
    parser.add_argument("--v2-score", required=True)
    parser.add_argument("--v1-run", help="v1 run summary.json directory")
    parser.add_argument("--v2-run", help="v2 run summary.json directory")
    parser.add_argument("--output")
    args = parser.parse_args()

    v1, v2 = _load(args.v1_score), _load(args.v2_score)
    labels1 = v1.get("labels_sha256")
    labels2 = v2.get("labels_sha256")
    lines: list[str] = []
    lines.append("# Wave run comparison")
    lines.append("")
    lines.append(f"- v1 scorer: `{v1.get('scorer_version')}`, labels sha: `{str(labels1)[:16]}…`")
    lines.append(f"- v2 scorer: `{v2.get('scorer_version')}`, labels sha: `{str(labels2)[:16]}…`")
    if labels1 != labels2:
        lines.append(f"- **WARNING: labels differ between runs — improvements may be label artefacts, investigate before counting**")
    t1, t2 = _totals(v1), _totals(v2)
    lines.append("")
    lines.append("## Core metrics")
    lines.append("")
    lines.append("| metric | v1 | v2 | Δ |")
    lines.append("| --- | --- | --- | --- |")
    rows = [
        ("targets (denominator)", t1["targets"], t2["targets"]),
        ("target completed", t1["completed"], t2["completed"]),
        ("target completion rate", t1["rate"], t2["rate"]),
        ("actually complete contracts", t1["actually_complete"], t2["actually_complete"]),
        ("reported complete", t1["reported_complete"], t2["reported_complete"]),
        ("false_complete", t1["false_complete"], t2["false_complete"]),
    ]
    for name, a, b in rows:
        delta = "—"
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            d = b - a
            delta = f"{d:+.1%}" if isinstance(a, float) else f"{d:+d}"
        lines.append(f"| {name} | {_fmt(a)} | {_fmt(b)} | {delta} |")
    verdict_keys = sorted(set(t1["verdicts"]) | set(t2["verdicts"]))
    for key in verdict_keys:
        a, b = t1["verdicts"].get(key, 0), t2["verdicts"].get(key, 0)
        lines.append(f"| verdict {key} | {a} | {b} | {b - a:+d} |")

    lines.append("")
    lines.append("## Rule completion")
    lines.append("")
    lines.append("| rule | v1 | v2 | Δ completed |")
    lines.append("| --- | --- | --- | --- |")
    rules = sorted(set(v1.get("rule_completion") or {}) | set(v2.get("rule_completion") or {}))
    for rule in rules:
        a = (v1.get("rule_completion") or {}).get(rule) or {}
        b = (v2.get("rule_completion") or {}).get(rule) or {}
        lines.append(f"| {rule} | {a.get('completed')}/{a.get('total')} | "
                     f"{b.get('completed')}/{b.get('total')} | "
                     f"{(b.get('completed') or 0) - (a.get('completed') or 0):+d} |")

    lines.append("")
    lines.append("## Per-case delivery / completion")
    lines.append("")
    lines.append("| case | v1 delivery | v1 verdicts | v2 delivery | v2 verdicts | Δ completed |")
    lines.append("| --- | --- | --- | --- | --- | --- |")

    def _case_map(score: dict) -> dict:
        return {c.get("case_id"): c for c in (score.get("cases") or [])}

    m1, m2 = _case_map(v1), _case_map(v2)
    for case in sorted(set(m1) | set(m2)):
        a, b = m1.get(case) or {}, m2.get(case) or {}
        ca, cb = a.get("counts") or {}, b.get("counts") or {}
        c1n, c2n = ca.get("completed") or 0, cb.get("completed") or 0
        va = ",".join(f"{k}:{v}" for k, v in sorted(ca.items())) or "—"
        vb = ",".join(f"{k}:{v}" for k, v in sorted(cb.items())) or "—"
        lines.append(f"| {case} ({a.get('group') or b.get('group') or ''}) | "
                     f"{a.get('delivery_status', '—')} | {va} | "
                     f"{b.get('delivery_status', '—')} | {vb} | {c2n - c1n:+d} |")
    text = "\n".join(lines) + "\n"
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
