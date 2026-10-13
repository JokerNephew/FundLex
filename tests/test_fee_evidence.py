import pytest

from fundlex.fee_evidence import fee_value, verify_fee_evidence


@pytest.mark.parametrize("quote,field,name,expected", [
    ("H类基金份额收取申购费用，不计提销售服务费。", "sales_service_fee", "H", False),
    ("J 类及 K 类基金份额不收取申购费用，计提销售服务费。", "sales_service_fee", "K", True),
    ("H类基金份额收取申购费用，J类基金份额不收取申购费用。", "subscription_fee", "H", True),
    ("H类基金份额收取申购费用，J类基金份额不收取申购费用。", "subscription_fee", "J", False),
    ("H类基金份额收取申购费用，养老金通过直销机构申购时免收申购费用。", "subscription_fee", "H", True),
    ("H类基金份额收取申购费用。H类基金份额通过直销机构申购时免收申购费用。", "subscription_fee", "H", True),
    ("通过直销机构申购H类基金份额免收申购费用。", "subscription_fee", "H", None),
    ("H类基金份额通过电子交易申购时免收申购费用。", "subscription_fee", "H", None),
    ("H类基金份额收取申购费用。销售服务费率为0.40%。", "sales_service_fee", "H", None),
    ("H类基金份额收取申购费用，J类基金份额计提销售服务费。", "sales_service_fee", "H", None),
    ("H类基金份额销售服务费率为0.00%。", "sales_service_fee", "H", False),
    ("H类基金份额销售服务费率为0.40%。", "sales_service_fee", "H", True),
    ("H类基金份额销售服务费按年费率0.40%计算。", "sales_service_fee", "H", True),
    ("H类基金份额销售服务费率不超过0.40%。", "sales_service_fee", "H", None),
    ("H类基金份额收取申购费用，不收取申购费用。", "subscription_fee", "H", None),
    ("H类基金份额收取申购费用。H类基金份额不收取申购费用。", "subscription_fee", "H", None),
    ("收取申购费用且不计提销售服务费的基金份额称为H类基金份额。", "sales_service_fee", "H", False),
    ("H类和J类基金份额分别收取申购费用和销售服务费。", "subscription_fee", "H", None),
    ("H类基金份额不计提管理费。", "sales_service_fee", "H", None),
    ("对H类基金份额免收申购费。", "subscription_fee", "H", False),
    ("对特定投资者的H类基金份额免收申购费。", "subscription_fee", "H", None),
    ("H类基金份额可以收取申购费用。", "subscription_fee", "H", None),
    ("H类基金份额是否收取申购费用。", "subscription_fee", "H", None),
    ("H类基金份额不得收取申购费用。", "subscription_fee", "H", None),
    ("H类基金份额收取申购费用，但不收取销售服务费。", "sales_service_fee", "H", False),
    ("H类基金份额不收取认购和申购费。", "subscription_fee", "H", False),
])
def test_clause_bound_facts(quote, field, name, expected):
    assert fee_value(quote, field, name) is expected


def test_single_class_requires_verified_binding():
    quote = "本基金收取申购费用，不计提销售服务费。"
    assert fee_value(quote, "sales_service_fee", "__single__") is None
    assert fee_value(quote, "sales_service_fee", "__single__", single_bound=True) is False
    assert fee_value("H类基金份额计提销售服务费。", "sales_service_fee", "__single__", single_bound=True) is None


def test_exact_source_never_joins_or_normalizes_quotes():
    quote = "H类基金份额不收取申购费用。"
    assert verify_fee_evidence(quote, "subscription_fee", "H", ["前言" + quote + "后续"]) is False
    assert verify_fee_evidence(quote, "subscription_fee", "H", ["H类基金份额", "不收取申购费用。"]) is None
    assert verify_fee_evidence(quote, "subscription_fee", "H", ["H 类基金份额不收取申购费用。"]) is None
    assert verify_fee_evidence("", "subscription_fee", "H", [quote]) is None


@pytest.mark.parametrize("connector", ["及", "和", "与", "、"])
@pytest.mark.parametrize("name", ["H", "J", "K"])
def test_complete_names_with_explicit_joint_subject(connector, name):
    quote = connector.join(f"{c}类基金份额" for c in ("H", "J", "K")) + "不收取销售服务费。"
    assert fee_value(quote, "sales_service_fee", name) is False


@pytest.mark.parametrize("quote,name,expected", [
    ("H类基金份额销售服务费按前一日H类基金份额资产净值的0.50%年费率计提。", "H", True),
    ("H类基金份额销售服务费按前一日H类基金份额资产净值的0%年费率计提。", "H", False),
    ("H类基金份额销售服务费按前一日J类基金份额资产净值的0.50%年费率计提。", "H", None),
    ("H类基金份额销售服务费按前一日J类基金份额资产净值的0.50%年费率计提。", "J", None),
    ("H类基金份额销售服务费按前一日H类基金份额资产净值计算，管理费按0.50%年费率计提。", "H", None),
    ("H类基金份额销售服务费不按前一日H类基金份额资产净值的0.50%年费率计提。", "H", None),
    ("H类基金份额销售服务费按前一日H类基金份额资产净值的0.50%年费率不计提。", "H", None),
    ("特定投资者H类基金份额销售服务费按前一日H类基金份额资产净值的0.50%年费率计提。", "H", None),
    ("H类基金份额销售服务费率为0%，H类基金份额通过直销机构销售服务费率为0.50%。", "H", False),
    ("H类基金份额销售服务费率为0%，H类基金份额销售服务费率为0.50%。", "H", None),
    ("H类基金份额不收取销售服务费和J类基金份额计提销售服务费。", "H", False),
    ("H类基金份额不收取销售服务费和J类基金份额计提销售服务费。", "J", True),
    ("H类基金份额J类基金份额不收取销售服务费。", "H", None),
])
def test_repeated_subject_rates_keep_property_and_scope(quote, name, expected):
    assert fee_value(quote, "sales_service_fee", name) is expected


@pytest.mark.parametrize("name,expected", [("H", False), ("J", True), ("K", True)])
def test_respective_same_fee_does_not_hide_previous_class(name, expected):
    quote = "本基金H类基金份额不收取销售服务费，J类基金份额和K类基金份额分别从本类别份额基金资产中计提销售服务费。"
    assert fee_value(quote, "sales_service_fee", name) is expected


@pytest.mark.parametrize("quote,field", [
    ("J类基金份额和K类基金份额分别收取申购费和销售服务费。", "sales_service_fee"),
    ("J类基金份额和K类基金份额分别收取申购费和销售服务费。", "subscription_fee"),
    ("J类基金份额和K类基金份额分别从本类别基金资产中计提销售服务费和管理费。", "sales_service_fee"),
    ("J类基金份额和K类基金份额分别从本类别基金资产中按0.20%和0.40%计提销售服务费。", "sales_service_fee"),
    ("J类基金份额和K类基金份额分别从本类别基金资产中计提销售服务费，申购费率为0%。", "sales_service_fee"),
    ("J类基金份额和K类基金份额分别从本类别基金资产中计提销售服务费和不计提销售服务费。", "sales_service_fee"),
    ("J类基金份额分别从本类别基金资产中计提销售服务费。", "sales_service_fee"),
])
@pytest.mark.parametrize("name", ["J", "K"])
def test_respective_allocation_remains_ambiguous(quote, field, name):
    assert fee_value(quote, field, name) is None


def test_joint_respective_special_investors_remain_unknown():
    quote = "特定投资者J类基金份额和K类基金份额分别从本类别基金资产中计提销售服务费。"
    assert fee_value(quote, "sales_service_fee", "J") is None
    assert fee_value(quote, "sales_service_fee", "K") is None


@pytest.mark.parametrize("prefix", ["不", "并不", "无需", "以往会", "计划"])
@pytest.mark.parametrize("name", ["J", "K"])
def test_joint_respective_narrative_is_not_an_explicit_current_fee(prefix, name):
    quote = "J类基金份额和K类基金份额" + prefix + "分别从本类别基金资产中计提销售服务费。"
    assert fee_value(quote, "sales_service_fee", name) is None
