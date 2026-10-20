"""User-facing delivery states (plan §33)."""
from __future__ import annotations

from fundlex.delivery import (COMPLETE, COMPLETE_WITH_NOTICES, EXCLUDED, PARTIAL,
                              build_user_summary)


def test_complete_without_notices():
    summary = build_user_summary({"delivery_status": "complete", "unresolved": []})
    assert summary["status"] == COMPLETE
    assert summary["headline"] == "修改完成"


def test_complete_with_business_notice_is_still_a_success():
    summary = build_user_summary({
        "delivery_status": "complete", "unresolved": [],
        "business_notices": [{"code": "G15_CONTRACT_DEVIATION",
                              "message": "原合同可能有误"}]})
    assert summary["status"] == COMPLETE_WITH_NOTICES
    assert summary["notices"]


def test_partial_delivery_lists_rule_location_and_business_reason():
    summary = build_user_summary({
        "delivery_status": "incomplete",
        "unresolved": [
            {"kind": "obligation", "code": "OPEN_OBLIGATION", "rule_id": "G16",
             "obligation_id": "G16:B1:O1", "location": "p809",
             "reason": "OPEN_OBLIGATION:applicable_without_target"},
            {"kind": "claim_replay", "code": "CLAIM_REPLAY_FAILED", "rule_id": "G08",
             "location": "p227", "reason": "CLAIM_REPLACEMENT_MISSING"},
        ]})
    assert summary["status"] == PARTIAL
    assert summary["headline"] == "部分修改无法可靠完成"
    assert [(item["rule_id"], item["location"]) for item in summary["issues"]] == [
        ("G16", "p809"), ("G08", "p227")]
    assert "未能在合同中定位" in summary["issues"][0]["business_reason"]
    assert "未能在最终文档中" in summary["issues"][1]["business_reason"]


def test_partial_delivery_never_hides_an_issue_behind_another():
    summary = build_user_summary({
        "delivery_status": "not_generated",
        "unresolved": [
            {"code": "CLAIM_REPLAY_FAILED", "rule_id": "G08", "location": "p1"},
            {"code": "CLAIM_REPLAY_FAILED", "rule_id": "G08", "location": "p1"},
            {"code": "COVERAGE_GAP", "rule_id": "G14", "location": "p2"},
        ]})
    assert summary["status"] == PARTIAL
    assert len(summary["issues"]) == 2


def test_excluded_is_not_a_partial_failure():
    summary = build_user_summary({"delivery_status": "excluded",
                                  "qualification": {"fund_type": "etf"}})
    assert summary["status"] == EXCLUDED
    assert summary["headline"].startswith("该产品类型")
