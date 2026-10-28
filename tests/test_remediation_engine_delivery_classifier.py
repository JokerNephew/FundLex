"""FL-D437: worker gate and user summary share one typed delivery decision.

The audit probe showed an unknown ``NEW_ENGINE_PROOF_ERROR`` counted as a review
item by the worker gate (complete) while the summary reported partial, and a real
``RECALL_EDIT_OVERLAP`` assigned to G14 became ``business_pending``.  Typed proof
failures now win over the rule-number bucket; strict/review_assisted stay distinct.
"""
from __future__ import annotations

from fundlex.delivery import build_user_summary, requires_blocker
from fundlex.recall_pipeline import _classify_delivery_items, _delivery_complete


def test_unknown_engine_failure_blocks_worker_and_summary_consistently():
    item = {"kind": "coverage", "code": "NEW_ENGINE_PROOF_ERROR",
            "rule_id": "G99", "reason": "new proof failure"}
    blockers, review, business = _classify_delivery_items([item])
    assert blockers == [item] and review == [] and business == []
    assert requires_blocker(item)
    assert _delivery_complete([item], policy="review_assisted",
                              claim_replay_verified=True,
                              final_omission_blocking=False) is False
    summary = build_user_summary({
        "delivery_status": "complete", "delivery_policy": "review_assisted",
        "unresolved": [item], "delivery_blockers": blockers,
        "review_items": review, "business_pending": business,
    })
    assert summary["status"] == "partial"


def test_g14_overlap_is_a_blocker_not_business_pending():
    item = {"rule_id": "G14", "code": "RECALL_EDIT_OVERLAP"}
    blockers, review, business = _classify_delivery_items([item])
    assert blockers == [item] and business == []
    assert _delivery_complete([item], policy="review_assisted",
                              claim_replay_verified=True) is False


def test_g18_claim_failure_is_a_blocker_not_business_pending():
    item = {"kind": "claim_replay", "rule_id": "G18",
            "code": "CLAIM_OPERATION_NOT_PLANNED", "claim_replay_failed": True}
    blockers, review, business = _classify_delivery_items([item])
    assert blockers == [item] and business == []
    assert _delivery_complete([item], policy="review_assisted") is False


def test_unfinished_audit_stays_a_review_item_under_review_assisted():
    item = {"kind": "coverage", "code": "AUDIT_NOT_COMPLETED",
            "rule_id": "G99", "reason": "audit round not finished"}
    blockers, review, business = _classify_delivery_items([item])
    assert blockers == [] and review == [item] and business == []
    assert _delivery_complete([item], policy="review_assisted") is True
    assert _delivery_complete([item], policy="strict") is False
    summary = build_user_summary({
        "delivery_status": "complete", "delivery_policy": "review_assisted",
        "unresolved": [item], "delivery_blockers": blockers,
        "review_items": review, "business_pending": business,
    })
    assert summary["status"] == "complete_with_notices"


def test_fact_business_item_stays_business_but_typed_claim_does_not():
    business = {"kind": "obligation", "code": "OPEN_OBLIGATION",
                "rule_id": "G14", "reason": "FACT_PREREQUISITE_UNVERIFIED"}
    blockers, review, pending = _classify_delivery_items([business])
    assert pending == [business] and blockers == []
    assert _delivery_complete([business], policy="review_assisted") is True
    typed = {"kind": "claim_replay", "rule_id": "G14",
             "code": "CLAIM_OPERATION_UNPROVEN"}
    blockers, review, pending = _classify_delivery_items([typed])
    assert blockers == [typed] and pending == []


def test_summary_cannot_report_complete_with_a_blocker():
    item = {"rule_id": "G14", "code": "RECALL_EDIT_OVERLAP"}
    summary = build_user_summary({
        "delivery_status": "complete", "delivery_policy": "review_assisted",
        "unresolved": [item], "delivery_blockers": [item],
        "review_items": [], "business_pending": [],
    })
    assert summary["status"] == "partial"
    assert summary["issues"]
