"""G15 business notice tests (user ruling 2026-10-19).

The old sales-service-fee payment clause is deleted either way; when its deadline /
subject / path deviates from the guide reference, the run records a
``CONTRACT_POSSIBLY_ERRONEOUS`` business notice — a warning that never affects
completion.
"""
from fundlex.recall import g15_contract_deviation

REFERENCE = (
    "C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金托管人发送基金销售服务费"
    "划付指令，经基金托管人复核后于次月首日起10个工作日内从基金财产中一次性支付给登记机构，"
    "由登记机构代付给销售机构。若遇法定节假日、公休日等，支付日期顺延。"
)


def test_reference_wording_produces_no_notice():
    assert g15_contract_deviation([REFERENCE], REFERENCE) == []


def test_deadline_difference_is_reported():
    contract = ("基金销售服务费每日计提，逐日累计至每月月末，按月支付，由基金托管人根据与基金"
                "管理人核对一致的财务数据，自动在月初5个工作日内按照指定的账户路径进行资金支付。")
    reasons = g15_contract_deviation([REFERENCE], contract)
    assert any("支付时限" in reason for reason in reasons)
    assert any("自动" in reason or "账户路径" in reason for reason in reasons)


def test_subject_family_normalisation_avoids_false_notice():
    # 注册登记机构 / 登记机构 are the same family; 管理人 / 基金管理人 too.
    variant = ("C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金托管人发送基金销售"
               "服务费划付指令，经基金托管人复核后于次月首日起10个工作日内从基金财产中一次性支付给"
               "注册登记机构，由注册登记机构代付给销售机构。")
    assert g15_contract_deviation([REFERENCE], variant) == []
