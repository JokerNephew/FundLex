"""Validator hard gate (plan §15–§16)."""
from __future__ import annotations

from fundlex.generation.validators import (Authorization, HARD_CODES, check_components,
                                           protected_tokens, run_validation, validate_edit)


def test_missing_required_term_is_a_hard_failure():
    report = run_validation("A类基金份额", "A类基金份额", auth=Authorization(),
                            required_terms=("A类", "C类"))
    assert report.verdict == "FAIL"
    finding = next(item for item in report.findings if item.code == "MISSING_REQUIRED_TERM")
    assert finding.severity == "hard"
    assert finding.failure_class == "GENERATION"
    assert report.as_dict()["verdict"] == "FAIL"


def test_outside_span_change_is_a_hard_failure():
    report = run_validation("授权句", "新授权句", auth=Authorization(must_add=("新授权句",)),
                            before_full="前文。授权句。后文。",
                            after_full="前文。新授权句。后文被改。")
    assert report.verdict == "FAIL"
    assert any(item.code == "OUTSIDE_SPAN_CHANGED" for item in report.findings)


def test_protected_fee_topic_flip_is_hard():
    # Authorizing the 申购 clause must never explain deleting 赎回.
    before = "本基金的赎回费率由基金管理人决定，并在招募说明书中列示。"
    after = "本基金的申购费率由基金管理人决定，并在招募说明书中列示。"
    auth = Authorization(must_add=("本基金的申购费率由基金管理人决定",),
                         remove_patterns=("本基金的申购费率由基金管理人决定，并在招募说明书中列示。",))
    report = run_validation(before, after, auth=auth)
    assert report.verdict == "FAIL"


def test_authorized_fee_topic_removal_passes_when_its_own_clause_is_removed():
    before = "基金管理人可以调低申购费率和赎回费率。"
    after = "基金管理人可以调低申购费率。"
    auth = Authorization(remove_patterns=("基金管理人可以调低申购费率和赎回费率。",))
    report = run_validation(before, after, auth=auth)
    assert report.verdict == "PASS", (report.findings, report.changes)


def test_component_must_be_present_in_the_same_site():
    components = [
        {"id": "daily_accrual", "terms": ("每日计提",)},
        {"id": "direct_refund", "terms": ("直销机构",)},
        {"id": "over_one_year_refund", "terms": ("超过一年",)},
    ]
    report = run_validation(
        "基金销售服务费每日计提。", "基金销售服务费每日计提，直销机构申购的份额不收取。",
        auth=Authorization(), components=components)
    assert report.verdict == "FAIL"
    missing = [item.detail for item in report.findings if item.code == "COMPONENT_MISSING"]
    assert any("over_one_year_refund" in detail for detail in missing)


def test_component_present_elsewhere_in_document_does_not_count():
    # The site text is the only text supplied; 超过一年 elsewhere is irrelevant.
    findings = check_components("基金销售服务费每日计提，直销机构不收取。", [
        {"id": "over_one_year_refund", "terms": ("超过一年",)}])
    assert findings and findings[0].code == "COMPONENT_MISSING"


def test_all_components_present_passes():
    report = validate_edit(
        "基金销售服务费每日计提。",
        "基金销售服务费每日计提。投资者通过直销机构申购的不收取销售服务费；"
        "通过其他销售机构申购且持续持有期限超过一年的，不再继续收取。",
        auth=Authorization(),
        components=(
            {"id": "daily_accrual", "terms": ("每日计提",)},
            {"id": "direct_refund", "terms": ("直销机构",)},
            {"id": "over_one_year_refund", "terms": ("超过一年",)},
        ))
    assert report.verdict == "PASS", report.findings


def test_number_from_verified_fact_is_authorized_but_invented_number_is_not():
    ok = run_validation("费率为0.40%。", "费率为0.40%，年费率0.20%。",
                        auth=Authorization(), authorized_numbers=("0.20%",))
    assert ok.verdict == "PASS", ok.findings
    bad = run_validation("费率为0.40%。", "费率为0.40%，年费率0.33%。",
                         auth=Authorization())
    assert bad.verdict == "FAIL"
    assert any(item.code == "UNAUTHORIZED_NUMBER" and item.detail == "0.33%"
               for item in bad.findings)


def test_hard_code_set_covers_every_plan_required_code():
    assert {"MISSING_REQUIRED_TERM", "OUTSIDE_SPAN_CHANGED", "UNAUTHORIZED_NUMBER",
            "LOST_PROTECTED_LITERAL", "UNEXPLAINED_HARD", "TARGET_SOURCE_MISMATCH",
            "STRUCTURE_UNSAFE"} <= HARD_CODES


def test_list_ordinals_are_not_financial_protected_literals():
    # Replacing the text after a list number legitimately removes the marker from
    # the span; it is not a lost financial amount (round14-12 D03 G11).
    before = "4、A 类基金份额的申购费用由投资人承担，不列入基金财产。"
    after = "通过直销机构申购本基金A类基金份额不收取申购费。"
    auth = Authorization(must_add=("通过直销机构申购本基金A类基金份额不收取申购费。",),
                         remove_patterns=(before,))
    report = run_validation(before, after, auth=auth)
    assert report.verdict == "PASS", report.findings
    # A genuine amount is still protected.
    tokens = protected_tokens("管理费按前一日资产净值的0.40%计提，共10个工作日。")
    assert "0.40%" in tokens and ("10个工作日" in tokens or "10" in tokens)


def test_fee_topic_flip_is_hard_with_the_rules_own_removal_pattern():
    before = "本基金的管理费按前一日基金资产净值的0.40%年费率计提。"
    after = "本基金的托管费按前一日基金资产净值的0.40%年费率计提。"
    # The authorization names the old clause but its policy text still says 管理费;
    # it does not authorize inventing a 托管费 clause.
    auth = Authorization(must_add=("本基金的管理费按前一日基金资产净值的0.40%年费率计提。",),
                         remove_patterns=(before,))
    report = run_validation(before, after, auth=auth)
    assert report.verdict == "FAIL"
    assert any(item.code == "TOPIC_LOST" for item in report.findings)


def test_g05_authorized_topic_shift_is_not_a_flip():
    before = "基金管理人可以调低赎回费率。"
    after = "基金管理人可以调低销售服务费率。"
    auth = Authorization(must_add=("基金管理人可以调低销售服务费率。",),
                         remove_patterns=("基金管理人可以调低赎回费率。",))
    report = run_validation(before, after, auth=auth)
    assert report.verdict == "PASS", (report.findings, report.changes)
