"""Post-parse footprint smoke for custom guide versions.

The model verifier alone can miss silent regressions (a re-parse of the same
source once dropped G16-G22 while reporting ``clean``).  This module compares
a freshly parsed version's rule footprint against its lineage baseline —
the parent re-parse version, or the built-in guide when the uploaded source
IS the built-in source — and records an advisory ``needs_review`` verdict on
the version.  The verdict never blocks enabling; it tells the owner which
dimension degraded.  Everything here is deterministic; no model is called.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import guide_store
from .guide_diff import diff_guide_documents
from .store import RunStore

# A regression is either any rule disappearing from the lineage, or the rule
# count falling off a cliff relative to the baseline.
CLIFF_RATIO = 0.5


def _flatten_rule_ids(document: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for group in (document or {}).get("groups") or []:
        if not isinstance(group, dict):
            continue
        nested = group.get("rules")
        if isinstance(nested, list):
            ids.extend(str(rule.get("rule_id")) for rule in nested
                       if isinstance(rule, dict) and rule.get("rule_id"))
        elif group.get("rule_id"):
            ids.append(str(group["rule_id"]))
    return sorted(ids)


def _covered_paragraphs(document: dict[str, Any]) -> set[int]:
    covered: set[int] = set()
    for group in (document or {}).get("groups") or []:
        if isinstance(group, dict):
            covered.update(index for index in (group.get("source_paragraphs") or [])
                           if isinstance(index, int))
    return covered


def _baseline(store: RunStore, owner: str, version: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """The comparison baseline for one version, or ``None`` when there is none."""
    parent_id = version.get("parent_version_id") or ""
    if parent_id:
        try:
            return parent_id, guide_store.guide_document(store, parent_id)
        except KeyError:
            pass
    builtin = guide_store.get_version(store, owner, guide_store.BUILTIN_GUIDE_ID)
    if version.get("source_sha256") and version["source_sha256"] == builtin["source_sha256"]:
        return guide_store.BUILTIN_GUIDE_ID, guide_store.guide_document(store, builtin["id"])
    return None


def review_version_footprint(store: RunStore, owner: str, version_id: str) -> dict[str, Any]:
    """Evaluate one parsed version and stamp/clear its ``needs_review`` verdict.

    Returns ``{"baseline": ..., "needs_review": bool, "dimensions": {...}}``;
    versions without a baseline or without parsed rules are left untouched.
    """
    version = guide_store.get_version(store, owner, version_id)
    if version["status"] not in guide_store.ENABLEABLE_STATUSES:
        return {"baseline": None, "needs_review": False, "dimensions": {},
                "skipped": version["status"]}
    baseline = _baseline(store, owner, version)
    if baseline is None:
        return {"baseline": None, "needs_review": False, "dimensions": {}, "skipped": "no_baseline"}
    baseline_id, baseline_doc = baseline
    document = guide_store.guide_document(store, version_id)
    diff = diff_guide_documents(baseline_doc, document)
    before_ids = set(_flatten_rule_ids(baseline_doc))
    after_ids = set(_flatten_rule_ids(document))
    removed = sorted(before_ids - after_ids)
    summary = diff["summary"]
    cliff = bool(before_ids) and summary["rules_after"] < CLIFF_RATIO * summary["rules_before"]
    # Rule-id churn without paragraph-coverage loss is granularity drift
    # (rules merged/split), not lost instructions — still advisory, but the
    # dimensions must say so instead of reading as a content cliff.
    before_covered = _covered_paragraphs(baseline_doc)
    after_covered = _covered_paragraphs(document)
    coverage_lost = sorted(before_covered - after_covered)
    granularity_only = not coverage_lost
    needs_review = bool(removed) or cliff
    dimensions = {"baseline_version_id": baseline_id,
                  "rules_before": summary["rules_before"], "rules_after": summary["rules_after"],
                  "removed_rule_ids": removed, "added_rule_ids": sorted(after_ids - before_ids),
                  "changed_rules": summary["changed"], "cliff_ratio": CLIFF_RATIO,
                  "cliff": cliff,
                  "coverage_lost_paragraphs": coverage_lost,
                  "granularity_only": granularity_only}
    if needs_review:
        review = {"status": "needs_review", "dimensions": dimensions,
                  "evaluated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        guide_store.mark_guide_review(store, owner, version_id, review)
    else:
        # A healthy re-parse clears any verdict inherited by the previous attempt.
        guide_store.mark_guide_review(store, owner, version_id, None)
    return {"baseline": baseline_id, "needs_review": needs_review, "dimensions": dimensions}
