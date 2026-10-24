"""Audit Router strategy telemetry against the materialized edit path.

The delivery report contains two deliberately different observations:

* ``edit.evidence.strategy`` is the Router's per-operation decision;
* ``edit.content_source`` is the executor/planner path that produced the edit.

This tool compares those observations without loading a model, a DOCX, or a
network service.  It is intended for historical report scans and for small
fixture reports in regression tests.

Usage::

    .venv/bin/python -m tools.evaluation.strategy_consistency REPORT --json
    .venv/bin/python -m tools.evaluation.strategy_consistency RUN_DIR --json
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


# Sources are the executor's observable output.  A tier here means the
# materialized path, not the Router's requested/actual tier.
_SOURCE_TIER: dict[str, str] = {
    "tier1_template": "tier1_template",
    "tier1_splice": "tier2_minimal_splice",
    "tier1_delete": "deterministic_delete",
    "fragment_replace": "tier2_minimal_splice",
    "fragment_delete": "deterministic_delete",
    "fragment_mixed": "tier2_minimal_splice",
    "variant_replace": "tier2_minimal_splice",
    "variant_delete": "deterministic_delete",
    "target_span_delete": "deterministic_delete",
    "whole_paragraph_delete": "deterministic_delete",
    "composite_replace": "tier2_minimal_splice",
    "composite_delete": "deterministic_delete",
    "guide_text": "tier1_template",
    "composed": "tier3_model_compose",
    "composed_delete": "tier3_model_compose",
    "joint_compose": "tier3_model_compose",
    "joint_delete": "deterministic_delete",
    "merged": "merged",
    "merged_delete_append": "merged",
    "replace_covers_delete": "merged",
    "claim_site_reuse": "rebound",
    "atomic_paragraph": "rebound",
    "generated": "unknown",
}


def _report_paths(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("report.json"))
    return []


def _strategy_records(edit: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = edit.get("evidence") or {}
    records = evidence.get("strategy") or []
    return [item for item in records if isinstance(item, dict)]


def _operation_keys(edit: dict[str, Any]) -> list[str]:
    evidence = edit.get("evidence") or {}
    values = edit.get("operation_keys") or evidence.get("operation_keys") or []
    if not values:
        values = [item.get("operation") for item in _strategy_records(edit)
                  if item.get("operation")]
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def source_tier(content_source: object) -> str:
    """Return the observed executor tier for a serialized content source."""
    source = str(content_source or "")
    return _SOURCE_TIER.get(source, "unknown")


def _effective_source(edit: dict[str, Any]) -> str:
    """Use the planner source when a validated edit wraps it as ``generated``."""
    source = str(edit.get("content_source") or "")
    planning = str(edit.get("planning_content_source") or "")
    return planning if source == "generated" and planning else source


def inspect_report(report: dict[str, Any], *, report_path: str = "") -> dict[str, Any]:
    """Inspect one report and return a stable, JSON-serializable audit record."""
    edits_out: list[dict[str, Any]] = []
    mismatches: list[dict[str, Any]] = []
    duplicate_occurrences: list[dict[str, Any]] = []
    operation_counts: Counter[str] = Counter()
    operation_locations: dict[str, set[str]] = defaultdict(set)

    edits = ((report.get("edit_plan") or {}).get("edits") or [])
    for index, raw in enumerate(edits):
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("content_source") or "")
        effective_source = _effective_source(raw)
        observed = source_tier(effective_source)
        strategies = _strategy_records(raw)
        applicable = [item for item in strategies if item.get("applicable") is not False]
        keys = _operation_keys(raw)
        for key in keys:
            operation_counts[key] += 1
            operation_locations[key].add(str(raw.get("location") or ""))

        edit_record = {
            "index": index,
            "rule_id": raw.get("rule_id"),
            "target_id": raw.get("target_id"),
            "location": raw.get("location"),
            "content_source": source,
            "planning_content_source": raw.get("planning_content_source"),
            "effective_content_source": effective_source,
            "observed_tier": observed,
            "fingerprint": raw.get("fingerprint"),
            "fingerprint_status": "present" if raw.get("fingerprint") else "missing",
            "operation_keys": keys,
            "router": [
                {
                    "operation": item.get("operation"),
                    "requested": item.get("requested"),
                    "actual": item.get("actual"),
                    "applicable": item.get("applicable"),
                    "blocked": item.get("blocked"),
                }
                for item in applicable
            ],
        }
        edits_out.append(edit_record)
        actual_tiers = sorted({str(item.get("actual")) for item in applicable
                               if item.get("actual")})
        # Merged edits combine multiple executor paths and cannot be assigned a
        # single Router tier.  They remain visible in the report but are not
        # falsely counted as a mismatch.
        if observed not in {"unknown", "merged", "rebound"} and actual_tiers \
                and observed not in actual_tiers:
            mismatch = {
                "index": index,
                "rule_id": raw.get("rule_id"),
                "target_id": raw.get("target_id"),
                "location": raw.get("location"),
                "content_source": source,
                "effective_content_source": effective_source,
                "observed_tier": observed,
                "router_actual_tiers": actual_tiers,
                "operation_keys": keys,
                "code": "ROUTER_EXECUTOR_TIER_MISMATCH",
            }
            mismatches.append(mismatch)

    for key, count in sorted(operation_counts.items()):
        if count > 1:
            duplicate_occurrences.append({
                "operation_key": key,
                "count": count,
                "locations": sorted(operation_locations[key]),
                "code": "DUPLICATE_OPERATION_OCCURRENCE",
            })

    coverage = report.get("operation_coverage") or {}
    coverage_counts = coverage.get("counts") if isinstance(coverage, dict) else {}
    coverage_by_operation: dict[str, Counter[str]] = defaultdict(Counter)
    coverage_entries = coverage.get("entries") if isinstance(coverage, dict) else []
    for entry in coverage_entries or []:
        if not isinstance(entry, dict):
            continue
        keys = [str(key) for key in entry.get("operation_keys") or []]
        for key in keys:
            coverage_by_operation[key][str(entry.get("state") or "UNRESOLVED")] += 1
    return {
        "schema": "strategy-consistency-1",
        "report": report_path,
        "delivery_status": report.get("delivery_status"),
        "edit_count": len(edits_out),
        "edits": edits_out,
        "mismatches": mismatches,
        "duplicate_operation_occurrences": duplicate_occurrences,
        "operation_counts": dict(sorted(operation_counts.items())),
        "operation_coverage": dict(coverage_counts or {}),
        "coverage_by_operation": {
            key: dict(sorted(states.items()))
            for key, states in sorted(coverage_by_operation.items())
        },
        "summary": {
            "mismatch_count": len(mismatches),
            "duplicate_operation_count": len(duplicate_occurrences),
            "unknown_source_count": sum(item["observed_tier"] == "unknown"
                                        for item in edits_out),
            "missing_fingerprint_count": sum(
                item["fingerprint_status"] == "missing" for item in edits_out),
        },
    }


def inspect_path(path: Path) -> dict[str, Any]:
    """Inspect a report file or recursively scan a run directory."""
    paths = _report_paths(path)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for report_path in paths:
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            records.append(inspect_report(report, report_path=str(report_path)))
        except (OSError, json.JSONDecodeError) as error:
            errors.append({"report": str(report_path), "error": str(error)})
    if len(records) == 1 and path.is_file():
        result = records[0]
        if errors:
            result["errors"] = errors
        return result
    summary = Counter()
    for record in records:
        summary.update(record["summary"])
    return {
        "schema": "strategy-consistency-run-1",
        "path": str(path),
        "report_count": len(records),
        "reports": records,
        "errors": errors,
        "summary": dict(summary),
    }


def _print_table(result: dict[str, Any]) -> None:
    if "reports" in result:
        print(f"reports: {result['report_count']}  summary: {result['summary']}")
        for report in result["reports"]:
            print(f"{report['report']}: {report['summary']}")
        return
    print(f"report: {result['report'] or '<memory>'}")
    print(f"edits: {result['edit_count']}  summary: {result['summary']}")
    for mismatch in result["mismatches"]:
        print("MISMATCH", json.dumps(mismatch, ensure_ascii=False, sort_keys=True))
    for duplicate in result["duplicate_operation_occurrences"]:
        print("DUPLICATE", json.dumps(duplicate, ensure_ascii=False, sort_keys=True))


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="report.json or directory containing reports")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    if not _report_paths(args.path):
        print(f"report or directory not found: {args.path}", file=sys.stderr)
        return 2
    result = inspect_path(args.path)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_table(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
