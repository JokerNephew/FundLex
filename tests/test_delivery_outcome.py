"""Two-state delivery presentation (FL-D654, mechanism E)."""
from __future__ import annotations

from fundlex.delivery import delivery_outcome


def _report(**overrides):
    report = {
        "delivery_status": "incomplete",
        "guide": {"groups": [{
            "rule_id": "G09", "title": "赎回金额计算口径",
            "section_hint": "基金份额的申购与赎回",
            "requirement": "赎回金额按份额类别调整",
        }]},
        "unresolved": [{
            "kind": "obligation", "code": "OPEN_OBLIGATION", "rule_id": "G09",
            "obligation_id": "G09:B1:O1", "location": "p159",
            "reason": "CLAIM_REPLAY_FAILED: verified site missing",
        }],
        "miss_classification": {"entries": [{
            "obligation_id": "G09:B1:O1", "rule_id": "G09",
            "miss_class": "MISS_MODEL_DEFERRAL",
            "message_zh": "审核模型判断该处不适用，但未获确定性证实，保留诚实扣件。",
            "en": "Model deferral held honestly.",
        }]},
    }
    report.update(overrides)
    return report


def test_complete_has_no_holds():
    outcome = delivery_outcome(_report(delivery_status="complete", unresolved=[]))
    assert outcome["state"] == "complete"
    assert outcome["zh"] == "完整完成"
    assert outcome["holds"] == []
    assert outcome["hold_count"] == 0
    assert outcome["engine_status"] == "complete"


def test_complete_with_exceptions_counts_as_complete():
    outcome = delivery_outcome(_report(delivery_status="complete_with_exceptions",
                                       unresolved=[]))
    assert outcome["state"] == "complete"


def test_incomplete_is_honest_hold_with_readable_text():
    outcome = delivery_outcome(_report())
    assert outcome["state"] == "honest_hold"
    assert outcome["zh"] == "诚实扣件"
    assert outcome["hold_count"] == 1
    hold = outcome["holds"][0]
    assert hold["title"] == "赎回金额计算口径"
    assert hold["section"] == "基金份额的申购与赎回"
    # User-readable Chinese text, not a bare engine key.
    assert "完成" in hold["business_reason"] or "复核" in hold["business_reason"] \
        or hold["business_reason"] != "CLAIM_REPLAY_FAILED"
    assert hold["review_note"]
    assert hold["miss_class"] == "MISS_MODEL_DEFERRAL"
    assert "诚实扣件" in hold["miss_reason_zh"]
    assert hold["miss_reason_en"]


def test_hold_without_miss_entry_still_readable():
    report = _report()
    del report["miss_classification"]
    outcome = delivery_outcome(report)
    hold = outcome["holds"][0]
    assert "miss_class" not in hold
    assert hold["business_reason"]
    assert hold["review_note"]


def test_not_generated_without_unresolved_gets_fallback_hold():
    outcome = delivery_outcome(_report(delivery_status="not_generated",
                                       unresolved=[], misses=None,
                                       miss_classification={}))
    assert outcome["state"] == "honest_hold"
    assert outcome["hold_count"] == 1
    assert outcome["holds"][0]["title"] == "任务未完成"


def test_excluded_is_honest_hold():
    outcome = delivery_outcome(_report(delivery_status="excluded"))
    assert outcome["state"] == "honest_hold"


def test_machine_codes_are_secondary_not_primary_text():
    outcome = delivery_outcome(_report())
    hold = outcome["holds"][0]
    # The code field stays for audit, but the primary reason is a Chinese
    # sentence, never the code itself.
    assert hold["code"]
    assert hold["business_reason"].strip() != hold["code"]
