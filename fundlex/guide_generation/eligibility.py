"""Shared run/version eligibility gates for guide candidates.

The module deliberately has no model calls.  It evaluates the persisted run,
findings, requirement dispositions, coverage, residual and guide-item content
so the pipeline, approval and publication paths cannot disagree about whether
a candidate is eligible.

A candidate may only become approvable when *all* gates are explicitly green.
Missing or unknown quality/coverage is therefore a failure, not a pass.
"""
from __future__ import annotations

from typing import Any, Iterable

from .models import sha256_json

# Quality statuses that mean the independent review actually completed and did
# not record an open critical finding.  Anything else (including a missing
# summary) blocks eligibility.
PASSING_QUALITY_STATUSES = frozenset({"pass", "pass_with_findings"})
# Coverage only passes when the auditor explicitly closed every topic, impact
# and latest-contract question.  ``complete_with_unresolved`` is not a pass.
PASSING_COVERAGE_STATUSES = frozenset({"pass"})
RUN_COMPLETE_STATUSES = frozenset({"complete", "complete_with_unresolved", "completed"})


def is_open_critical(finding: dict[str, Any]) -> bool:
    """A critical finding blocks while it is open.

    A reviewer-authored finding whose cited evidence could not be verified is
    kept as review evidence but has never been allowed to drive a gate; this
    mirrors the historical quality-gate filter (FL-D377).
    """
    if finding.get("severity") != "critical":
        return False
    if finding.get("status") not in {"open", "", None}:
        return False
    if finding.get("source") == "guide_reviewer" and finding.get("evidence_verified") is False:
        return False
    return True


def open_critical_findings(findings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [finding for finding in findings if is_open_critical(finding)]


def _finding_key(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": str(finding.get("finding_id") or ""),
        "category": str(finding.get("category") or ""),
        "source": str(finding.get("source") or ""),
        "guide_item_id": str(finding.get("guide_item_id") or ""),
        "evidence_verified": finding.get("evidence_verified"),
    }


def evaluate_run_eligibility(gg, run_id: str) -> dict[str, Any]:
    """Return a deterministic, content-bound gate snapshot.

    The returned ``gate_sha256`` changes whenever any dependency changes:
    quality status, open criticals, requirement disposition/evidence, guide
    item content, coverage counts/topics, residual saturation and the frozen
    regulation source.  Candidate versions store this digest so approval and
    publication can reject a stale qualification.
    """
    run = gg.get_run(run_id)
    payload = run.get("payload") or {}
    findings = gg.get_findings(run_id)
    requirements = gg.get_requirements(run_id)
    items = gg.get_guide_items(run_id)
    quality = payload.get("quality") or {}
    coverage = payload.get("coverage") or {}
    residual = payload.get("residual") or {}

    criticals = open_critical_findings(findings)
    quality_status = str(quality.get("run_status") or "")
    coverage_status = str(coverage.get("run_status") or "")
    unresolved_impacts = int((coverage.get("impacts") or {}).get("unresolved", 0) or 0)
    requirement_gaps = int((coverage.get("requirements") or {}).get("gap", 0) or 0)
    latest_uncertain = int(coverage.get("latest_uncertain", 0) or 0)
    missing_topics = coverage.get("missing_topics") or []
    unhandled = sum(1 for item in requirements if not item.disposition)

    checks = {
        "requirements_present": bool(requirements),
        "guide_items_present": bool(items),
        "all_requirements_dispositioned": unhandled == 0,
        "all_requirements_have_evidence": all(
            item.source_quote and item.source_block_ids for item in requirements),
        "all_guide_items_have_requirement": all(item.requirement_ids for item in items),
        "all_guide_items_have_impact": all(item.impact_ids for item in items),
        "all_guide_items_have_new_text_origin": all(item.new_text_origin for item in items),
        "quality_gate_passed": (quality_status in PASSING_QUALITY_STATUSES and not criticals),
        "no_open_critical_findings": not criticals,
        "coverage_gate_passed": (coverage_status in PASSING_COVERAGE_STATUSES
                                 and not missing_topics
                                 and unresolved_impacts == 0
                                 and requirement_gaps == 0
                                 and latest_uncertain == 0),
        "residual_saturated": residual.get("saturated") is True,
    }
    qualified = all(checks.values())
    source_sha256 = str(run.get("source_sha256") or "")
    regulation_sha256 = str(run.get("regulation_document_sha256") or "")
    items_sha256 = sha256_json([item.to_dict() for item in items])
    requirement_sha256 = sha256_json([
        {"requirement_id": item.requirement_id, "disposition": item.disposition,
         "source_block_ids": list(item.source_block_ids or []),
         "source_quote": item.source_quote}
        for item in requirements
    ])
    snapshot = {
        "schema_version": "guide-eligibility-1",
        "run_id": run_id,
        "qualified": qualified,
        "checks": checks,
        "quality_run_status": quality_status,
        "quality_gate_passed": checks["quality_gate_passed"],
        "coverage_run_status": coverage_status,
        "coverage_gate_passed": checks["coverage_gate_passed"],
        "open_critical_findings": len(criticals),
        "open_critical_finding_keys": sorted(
            (_finding_key(finding) for finding in criticals),
            key=lambda item: (item["finding_id"], item["category"], item["source"],
                              item["guide_item_id"])),
        "unhandled_requirements": unhandled,
        "requirement_gaps": requirement_gaps,
        "unresolved_impacts": unresolved_impacts,
        "latest_contract_uncertain": latest_uncertain,
        "missing_topics": len(missing_topics),
        "missing_topic_ids": sorted(str(topic.get("topic_id") or "") for topic in missing_topics),
        "residual_saturated": residual.get("saturated") is True,
        "source_sha256": source_sha256,
        "regulation_document_sha256": regulation_sha256,
        "guide_items_sha256": items_sha256,
        "requirements_sha256": requirement_sha256,
        "model_identity": payload.get("model_identity") or {},
    }
    snapshot["gate_sha256"] = sha256_json(snapshot)
    return snapshot
