

def test_g09_splice_applies_all_multi_class_wording_changes():
    from fundlex.generation.template import plan_g09_splice
    before = ("赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额净值并扣除相应的费用，"
              "赎回金额单位为元。")
    result = plan_g09_splice(before, [])
    assert result is not None
    assert "当日该类基金份额的基金份额净值" in result.replacement
    assert "扣除或加上相应的费用" in result.replacement
