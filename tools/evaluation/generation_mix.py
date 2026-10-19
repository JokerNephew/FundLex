"""Reproduce the generation mix of a p6 run (plan v4 §22).

Counts the ``content_source`` of every edit in ``edit_plan.edits`` across a run
directory and reports the deterministic vs model-produced split. The tool must
reproduce the FL-D120 baseline on ``p6-dev-round14-05`` (284 edits, ≈64 %
deterministic incl. deterministic fallbacks).

Usage:
  .venv/bin/python -X utf8 -m tools.evaluation.generation_mix \
      var/recall-first-evaluation/p6-dev-round14-05 [--by-rule] [--json]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

#: ``content_source`` values whose final text is produced without a model call.
DETERMINISTIC_SOURCES = frozenset({
    "guide_text", "fragment_replace", "fragment_delete", "fragment_mixed",
    "variant_replace", "variant_delete", "target_span_delete",
    "composite_replace", "composite_delete", "whole_paragraph_delete",
    "tier1_template", "tier1_splice", "tier1_delete",
})
#: Values that involve a model call (``merged`` is a mechanical merge whose
#: components may themselves be deterministic or composed — counted separately).
MODEL_SOURCES = frozenset({"composed", "composed_delete"})
MERGE_SOURCES = frozenset({"merged"})


def classify(content_source: str) -> str:
    if content_source in DETERMINISTIC_SOURCES:
        return "deterministic"
    if content_source in MODEL_SOURCES:
        return "model"
    if content_source in MERGE_SOURCES:
        return "merge"
    return "other"


def collect(run_dir: Path) -> dict:
    """Aggregate edit sources over every case directory of one run."""
    by_source: Counter = Counter()
    by_class: Counter = Counter()
    by_rule: dict[str, Counter] = defaultdict(Counter)
    cases = 0
    edits = 0
    for case_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        report_path = case_dir / "report.json"
        if not report_path.exists():
            continue
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        cases += 1
        for edit in (report.get("edit_plan") or {}).get("edits") or []:
            source = str(edit.get("content_source") or "?")
            by_source[source] += 1
            by_class[classify(source)] += 1
            by_rule[str(edit.get("rule_id") or "?")][source] += 1
            edits += 1
    return {
        "run": str(run_dir),
        "cases": cases,
        "edits": edits,
        "by_source": dict(by_source.most_common()),
        "by_class": dict(by_class),
        "by_rule": {rule: dict(counter) for rule, counter in sorted(by_rule.items())},
    }


def _print(data: dict, by_rule: bool) -> None:
    edits = data["edits"] or 1
    print(f"run: {data['run']}  cases: {data['cases']}  edits: {data['edits']}")
    print("by content_source:")
    for source, count in data["by_source"].items():
        print(f"  {source:<24} {count:>4}  ({count / edits * 100:.1f}%)")
    deterministic = data["by_class"].get("deterministic", 0)
    model = data["by_class"].get("model", 0)
    merge = data["by_class"].get("merge", 0)
    print(f"deterministic: {deterministic} ({deterministic / edits * 100:.1f}%)"
          f"  model: {model} ({model / edits * 100:.1f}%)"
          f"  merged(mechanical): {merge} ({merge / edits * 100:.1f}%)")
    if by_rule:
        print("by rule:")
        for rule, counter in data["by_rule"].items():
            print(f"  {rule:<16} {counter}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="p6 run directory")
    parser.add_argument("--by-rule", action="store_true", help="also list per-rule counts")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args(argv)
    if not args.run.is_dir():
        print(f"not a directory: {args.run}", file=sys.stderr)
        return 2
    data = collect(args.run)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=1))
    else:
        _print(data, args.by_rule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
