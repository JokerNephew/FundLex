"""Full-width parenthesised ordinals are headings, not operation sites."""
from fundlex.recall import _looks_like_heading


def test_fullwidth_chinese_ordinal_is_a_heading():
    assert _looks_like_heading("（五）基金财产清算剩余资产的分配")
    assert _looks_like_heading("（一）基金财产清算剩余资产分配")


def test_policy_body_starting_with_a_digit_list_is_not_a_heading():
    assert not _looks_like_heading(
        "依据基金财产清算的分配方案，将基金财产清算后的全部剩余资产扣除基金财产清算费用。")
