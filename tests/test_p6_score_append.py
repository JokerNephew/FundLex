"""The P6 scorer must not report an executed append as missing.

The append rules (G01/G03/G16) quote policy wording with an assumed share-class
set ("A类"/"C类"). Real contracts often have a different set ("A类、D类",
"A类、B类"), and the engine appends the policy with the contract's own classes.
Before this fix the scorer compared the literal lead clause, so a correctly
appended policy was scored ``not_executed`` whenever the class list differed —
a false negative that made the engine look worse than it is (found by reading
the JSONL trace of a real dev-set run).
"""

from tools.evaluation.p6_score import _normalise_policy, appendix_present

POLICY = ("投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类基金份额时，"
          "不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。")


def test_exact_policy_is_present():
    assert appendix_present(POLICY, POLICY)


def test_extra_share_class_letters_still_count_as_present():
    # The contract has A/B/C classes; the engine appended with "A类、B类".
    document = ("类别。投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类、B类"
                "基金份额时，不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。")
    assert appendix_present(POLICY, document)


def test_three_class_contract_satisfies_two_class_policy():
    document = ("投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类、D类基金份额时，"
                "不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。")
    assert appendix_present(POLICY, document)


def test_absent_policy_is_not_accepted():
    # A contract that mentions 直销机构 in other clauses must not be scored as done.
    document = "通过直销机构申购本基金A类基金份额不收取申购费。本基金C类基金份额不收取申购费用。"
    assert appendix_present(POLICY, document) is False


def test_unrelated_text_is_not_accepted():
    assert appendix_present(POLICY, "基金管理人应当在每年结束之日起三个月内公告年度报告。") is False


def test_normalisation_collapses_class_enumerations():
    assert _normalise_policy("申购本基金A类、D类基金份额时") == _normalise_policy("申购本基金A类基金份额时")
    assert _normalise_policy("申购本基金A类、B类和C类基金份额时") == _normalise_policy("申购本基金A类基金份额时")
