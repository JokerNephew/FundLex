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


SINGLE_CLASS_POLICY = POLICY  # the same template used above


def _facts(service_fee: bool):
    return {"classes": [{"name": "基金份额", "service_fee": service_fee}]}


def test_single_class_contract_scores_the_applicable_clause():
    """A single-class fund gets the subscription clause without a C-class clause.

    The engine must not invent a C class that charges no sales service fee, so the
    service clauses of the policy cannot appear. Scoring the full template would read
    the engine's correct work as a miss (found on D09/D13 of the real dev set).
    """
    from tools.evaluation.p6_score import appendix_present_applicable_clauses

    document = ("不可抗力：客观事件。投资者通过直销机构（含基金管理人及其销售子公司，下同）"
                "申购本基金基金份额时，不收取认购/申购费用。")
    assert appendix_present_applicable_clauses(POLICY, document, _facts(False)) is True


def test_single_class_contract_still_needs_the_subscription_clause():
    from tools.evaluation.p6_score import appendix_present_applicable_clauses

    assert appendix_present_applicable_clauses(POLICY, "基金管理人应当公告年度报告。",
                                               _facts(False)) is False


def test_service_fee_contract_requires_the_full_policy():
    from tools.evaluation.p6_score import appendix_present_applicable_clauses

    document = ("投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类基金份额时，"
                "不收取认购/申购费用。")
    # The contract has a service-fee class, so the C-class clause must also be present.
    assert appendix_present_applicable_clauses(POLICY, document, _facts(True)) is False


def test_multi_sentence_quotation_does_not_require_its_last_sentence():
    """A quotation naming a later clause must not make a completed deletion look kept.

    D01's G17 requirement quotes two sentences: the clause to delete, then a neighbouring
    sentence ("…使用范围不包括基金募集期间的上述费用。") that the engine keeps on purpose
    as its own paragraph. The trailing fragment alone reported the deletion as ``kept``.
    """
    from tools.evaluation.p6_score import _superseded_survives

    target = {
        "old_text": "销售服务费主要用于支付销售机构佣金",
        "requirement": ("删除原条款“C类基金份额的销售服务费主要用于支付销售机构佣金、以及基金管理人的"
                        "基金行销广告费、促销活动费、基金份额持有人服务费等。C类基金份额的销售服务费"
                        "使用范围不包括基金募集期间的上述费用。”。"),
    }
    # The deleted sentence is gone; only the neighbouring sentence survives.
    final = "销售服务费使用范围不包括基金募集期间的上述费用。"
    assert _superseded_survives(target, "", final) is False


def test_single_sentence_quotation_still_detects_a_surviving_clause():
    from tools.evaluation.p6_score import _superseded_survives

    # One sentence, anchor at the end: the whole quotation is the deletion target.
    target = {
        "old_text": "由登记机构代付给销售机构",
        "requirement": ("删除原条款中“经基金托管人复核后于次月首日起10个工作日内从基金财产中一次性"
                        "支付给登记机构，由登记机构代付给销售机构。”。"),
    }
    final = "经基金托管人复核后于次月首日起10个工作日内从基金财产中一次性支付给登记机构，由登记机构代付给销售机构。"
    assert _superseded_survives(target, "", final) is True
    # With the clause actually removed, the same target reads as completed.
    assert _superseded_survives(target, "", "基金销售服务费按月支付。") is False


def test_deleted_paragraph_that_no_longer_exists_scores_completed():
    """A successful deletion leaves no paragraph for the scorer to locate.

    ``score_target`` searches the final document for the paragraph that carried the
    clause. A completed deletion changes that paragraph, so the search returns -1.
    Requiring a located paragraph turned the engine's correct work into ``kept`` for
    five dev-set cases (FL-D098).
    """
    from tools.evaluation.p6_score import score_target

    clause = ("C类基金份额的销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、"
              "促销活动费、基金份额持有人服务费等。")
    target = {
        "target_id": "t1", "rule_id": "G17", "op": "delete",
        "old_text": "销售服务费主要用于支付销售机构佣金",
        "requirement": f"删除原条款“{clause}”。",
        "compact_start": 0,
    }
    # The clause (and its paragraph) is gone from the final document.
    final = ["基金管理人应当在每年结束之日起三个月内，编制完成基金年度报告。"]
    verdict = score_target(target, {"classes": []}, final, [clause])
    assert verdict["verdict"] == "completed"
    assert verdict["final_paragraph"] < 0

    # A surviving clause still reads as kept.
    verdict2 = score_target(target, {"classes": []}, [clause], [clause])
    assert verdict2["verdict"] == "kept"


def test_replace_with_a_small_wording_variant_scores_completed():
    """A correct replacement must not be scored kept just because of one extra word.

    G14 asks for "基金管理人可以适当调低基金申购费率和销售服务费率。", which contracts
    deliver as "…调低基金申购费率和基金销售服务费率。" (one extra "基金"). The label's
    old_text ("可以适当调低基金申购费率") is a substring of that corrected sentence, so the
    "old wording still in its region" fallback fired and the engine's correct work read as a
    miss for four dev-set cases (FL-D099).
    """
    from tools.evaluation.p6_score import score_target

    required = "基金管理人可以适当调低基金申购费率和销售服务费率。"
    old = "可以适当调低基金申购费率"
    region = ("在对基金份额持有人利益无实质性不利影响的前提下，基金管理人可以在不违反法律法规规定及"
              "基金合同约定的情形下根据市场情况制定基金促销计划。在基金促销活动期间，按相关监管部门"
              "要求履行必要手续后，基金管理人可以适当调低基金申购费率和基金销售服务费率。")
    target = {"target_id": "t", "rule_id": "G14", "op": "replace", "old_text": old,
              "required_text": required, "compact_start": 0}
    verdict = score_target(target, {"classes": []}, [region], [region])
    assert verdict["verdict"] == "completed"


def test_replace_that_was_never_made_still_scores_kept():
    """The alignment fallback must not accept a clause the engine left untouched.

    D12/G14 keeps the original "…调低基金申购费率、基金赎回费率、转换费率和销售服务费率。"
    and the engine's own audit agrees it was never edited (`RECALL_EDIT_OVERLAP`).
    """
    from tools.evaluation.p6_score import score_target

    required = "基金管理人可以适当调低基金申购费率和销售服务费率。"
    old = "可以适当调低基金申购费率、基金赎回费率"
    region = ("对基金份额持有人无实质性不利影响的前提下，基金管理人可以在不违反法律法规规定及基金合同"
              "约定的情形下根据市场情况制定基金促销计划。在基金促销活动期间，按相关监管部门要求履行必要"
              "手续后，基金管理人可以适当调低基金申购费率、基金赎回费率、转换费率和销售服务费率。")
    target = {"target_id": "t", "rule_id": "G14", "op": "replace", "old_text": old,
              "required_text": required, "compact_start": 0}
    verdict = score_target(target, {"classes": []}, [region], [region])
    assert verdict["verdict"] == "kept"


def test_score_selects_only_run_cases_by_default(tmp_path):
    """A dev-only run must not be diluted by unrun holdout labels (FL-D116)."""
    import json
    from tools.evaluation.p6_score import _select_label_cases
    labels = [{"case_id": "D01", "group": "dev"}, {"case_id": "H01", "group": "holdout"}]
    (tmp_path / "batch.json").write_text(json.dumps({"cases": ["D01"]}), encoding="utf-8")
    selected, missing, warning = _select_label_cases(labels, tmp_path, "run")
    assert [case["case_id"] for case in selected] == ["D01"]
    assert missing == {"H01"}
    assert warning is None
    selected, missing, _ = _select_label_cases(labels, tmp_path, "all")
    assert [case["case_id"] for case in selected] == ["D01", "H01"]
    assert missing == set()
