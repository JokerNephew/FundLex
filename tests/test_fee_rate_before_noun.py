"""A service-fee rate written before its noun still proves the polarity."""
from fundlex.fee_evidence import fee_value


def test_service_fee_rate_before_noun():
    quote = ("C类基金份额或C类份额：指从本类别基金资产中计提年费率为0.25%的"
             "销售服务费而不收取申购费用的基金份额类别")
    assert fee_value(quote, "sales_service_fee", "C") is True
    assert fee_value(quote, "subscription_fee", "C") is False


def test_a_class_definition_with_or_separator():
    quote = ("A类基金份额或A类份额：指投资人申购时收取申购费用，"
             "但不从本类别资产中计提销售服务费的基金份额类别")
    assert fee_value(quote, "subscription_fee", "A") is True
    assert fee_value(quote, "sales_service_fee", "A") is False
