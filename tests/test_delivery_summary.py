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
        "guide": {"groups": [
            {"rule_id": "G16", "title": "销售服务费支付机制", "section_hint": "基金费用与税收",
             "requirement": "补充销售服务费计提与返还机制"},
            {"rule_id": "G08", "title": "申购费用列示", "section_hint": "基金份额的申购与赎回",
             "requirement": "按实际类别列示申购费用"}]},
        "targets": [{"rule_id": "G16", "location": "p809", "quote": "销售服务费每日计提，按月支付。"},
                    {"rule_id": "G08", "location": "p227", "quote": "本基金申购费率由基金管理人决定。"}],
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
    assert summary["issues"][0]["title"] == "销售服务费支付机制"
    assert summary["issues"][0]["section"] == "基金费用与税收"
    assert summary["issues"][0]["quote"] == "销售服务费每日计提，按月支付。"
    assert summary["issues"][0]["quote_exact_site"] is True
    assert "修订痕迹中不会出现" in summary["issues"][0]["review_note"]


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


def test_complete_status_cannot_hide_unresolved_operation_coverage():
    summary = build_user_summary({
        "delivery_status": "complete", "unresolved": [],
        "operation_coverage": {"entries": [{
            "rule_id": "G16", "operation_keys": ["G16:1"],
            "location": "p809", "state": "UNRESOLVED",
        }]},
    })
    assert summary["status"] == PARTIAL
    assert summary["issues"]


def test_unknown_obligation_blocks_success_summary():
    summary = build_user_summary({
        "delivery_status": "complete", "unresolved": [],
        "obligations": {"records": [{
            "rule_id": "G02", "operation_id": "G02:0", "completion": "UNKNOWN",
        }]},
    })
    assert summary["status"] == PARTIAL


def test_failed_claim_replay_blocks_success_even_when_status_is_stale():
    summary = build_user_summary({
        "delivery_status": "complete", "unresolved": [],
        "artifact_claim_replay": {
            "verified": True,
            "obligations": {"G18:B1:O1": {
                "state": "CONFLICT", "operation_id": "G18:0",
            }},
        },
    })
    assert summary["status"] == PARTIAL


def test_claim_replay_alias_and_unknown_site_effect_block_success():
    summary = build_user_summary({
        "delivery_status": "complete", "unresolved": [],
        "claim_replay": {"verified": True, "obligations": {
            "G08:B1:O1": {"state": "PASS", "site_effects": [
                {"state": "UNKNOWN", "artifact_status": "UNKNOWN"},
            ]},
        }},
    })
    assert summary["status"] == PARTIAL


def test_unrecognized_coverage_state_blocks_success():
    summary = build_user_summary({
        "delivery_status": "complete", "unresolved": [],
        "operation_coverage": {"entries": [{
            "rule_id": "G08", "location": "p20", "state": "future_state",
        }]},
    })
    assert summary["status"] == PARTIAL
