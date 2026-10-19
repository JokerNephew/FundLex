"""Phase 4 tests: tier-1 deterministic generators (plan v4 §7, §25).

G14 structured fee-item removal (rebuild / converge modes) and the bounded
splice used by G09 — all pure text transforms, no model calls.
"""
from fundlex.generation.template import (
    fee_items,
    plan_fee_item_removal,
    plan_g09_splice,
    plan_policy_replacement,
    plan_splice,
    splice_pairs,
)

CANONICAL_MULTI = "基金申购费率和销售服务费率。"
CANONICAL_SINGLE = "基金申购费率。"


def _allowed_multi() -> set[str]:
    return {"申购费率", "销售服务费率"}


def test_g14_multi_class_rebuild_removes_redemption_and_conversion():
    before = "基金管理人可以适当调低基金申购费率、基金赎回费率、基金转换费率和基金销售服务费率。"
    result = plan_fee_item_removal(before, _allowed_multi(), CANONICAL_MULTI)
    assert result is not None
    assert result.replacement == "基金管理人可以适当调低基金申购费率和销售服务费率。"
    assert result.content_source == "tier1_template"


def test_g14_single_class_keeps_only_subscription_fee():
    before = "基金管理人可以适当调低基金申购费率和基金赎回费率。"
    result = plan_fee_item_removal(before, {"申购费率"}, CANONICAL_SINGLE)
    assert result is not None
    assert result.replacement == "基金管理人可以适当调低基金申购费率。"


def test_g14_multi_class_adds_service_fee_item():
    """D16 p224 shape: the guide's multi-class wording ADDS 销售服务费率."""
    before = "基金管理人可以适当调低基金申购费率和基金赎回费率。"
    result = plan_fee_item_removal(before, _allowed_multi(), CANONICAL_MULTI)
    assert result is not None
    assert result.replacement == "基金管理人可以适当调低基金申购费率和销售服务费率。"


def test_g09_applies_both_multi_class_fixes():
    contract = ("赎回金额为按实际确认的有效赎回份额乘以当日基金份额净值"
                "并扣除相应的费用，赎回金额单位为元。")
    result = plan_g09_splice(contract, [])
    assert result is not None
    assert "当日该类基金份额的基金份额净值" in result.replacement
    assert "扣除或加上相应的费用" in result.replacement


def test_g14_mixed_order_is_canonicalised():
    # 14-08 D01 p231 shape: 销售服务费 listed first — output must follow the
    # guide's own order (the scorer compares against the guide sentence).
    before = "基金管理人可以适当调低基金销售服务费率、基金申购费率和基金赎回费率。"
    result = plan_fee_item_removal(before, _allowed_multi(), CANONICAL_MULTI,
                                   ["申购费率", "销售服务费率"])
    assert result is not None
    assert result.replacement == "基金管理人可以适当调低基金申购费率和销售服务费率。"


def test_g14_qualifier_clause_converges_to_guide_tail():
    # 2026-10-19 ruling: "全部或者部分份额类别" qualifiers are authorized to
    # disappear — the clause converges to the guide's canonical tail.
    before = "基金管理人可以适当调低全部或者部分份额类别的申购费率、赎回费率、转换费率和销售服务费率。"
    result = plan_fee_item_removal(before, _allowed_multi(), CANONICAL_MULTI)
    assert result is not None
    assert result.replacement == "基金管理人可以适当调低基金申购费率和销售服务费率。"


def test_g14_tail_content_is_preserved():
    before = "基金管理人可以适当调低基金申购费率和基金赎回费率，并最迟应于新的费率实施日前公告。"
    result = plan_fee_item_removal(before, {"申购费率"}, CANONICAL_SINGLE)
    assert result is not None
    assert result.replacement.endswith("，并最迟应于新的费率实施日前公告。")
    assert "赎回费率" not in result.replacement


def test_g14_already_satisfied_returns_none():
    before = "基金管理人可以适当调低基金申购费率和销售服务费率。"
    assert plan_fee_item_removal(before, _allowed_multi(), CANONICAL_MULTI) is None


def test_g09_bounded_splice_applies_guide_pair():
    old_text = ("赎回金额为按实际确认的有效赎回份额乘以当日对应份额类别的基金份额净值并扣除相应的费用，"
                "赎回金额单位为元。")
    new_text = ("赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额的基金份额净值并扣除或加上相应的费用，"
                "赎回金额单位为元。")
    pairs = splice_pairs(old_text, new_text)
    assert pairs
    contract = ("赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额净值并扣除相应的费用，"
                "赎回金额单位为元。")
    result = plan_splice(contract, pairs)
    assert result is not None
    assert "扣除或加上相应的费用" in result.replacement
    assert result.content_source == "tier1_splice"


def test_fee_item_extraction():
    assert fee_items("调低基金申购费率、基金赎回费率") == {"申购费率", "赎回费率"}
    assert fee_items("无费率字样") == set()


def test_g08_clean_clause_replaced_deterministically():
    before = "本基金的申购费率由基金管理人决定，并在招募说明书中列示。"
    policy = ("本基金A类基金份额在申购时收取申购费用，C类基金份额不收取申购费用。"
              "通过直销机构申购本基金A类基金份额不收取申购费。"
              "通过直销机构以外的其他销售机构申购本基金的申购费率由基金管理人决定，并在招募说明书中列示。")
    result = plan_policy_replacement(before, policy, "G08")
    assert result is not None
    assert result.replacement == policy


def test_g08_mixed_clause_is_rejected():
    mixed = ("本基金的申购费率、申购份额具体的计算方法、赎回费率、赎回金额具体的计算方法"
             "和收费方式由基金管理人根据基金合同的规定确定，并在招募说明书中列示。")
    assert plan_policy_replacement(mixed, "X" * 40, "G08") is None


def test_g11_clean_clause_replaced_deterministically():
    before = "申购费用由投资人承担，不列入基金财产。"
    policy = ("通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的"
              "申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。")
    result = plan_policy_replacement(before, policy, "G11")
    assert result is not None
    assert result.replacement == policy
