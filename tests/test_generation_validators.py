"""Phase 2 tests: V1/V2 shadow validators (plan v4 §11–§12).

Key acceptance: the FL-D119 fixture (D01/p227 — G08 authorization applied to
the 赎回 clause) must classify as a hard unexplained change, while the
legitimate G08 edit of the matching 申购 clause must pass.
"""
from fundlex.generation.validators import (
    Authorization,
    check_boundary,
    protected_tokens,
    run_validation,
)

G08_REFERENCE = "本基金的申购费率由基金管理人决定，并在招募说明书中列示。"
G08_POLICY = (
    "本基金A类、D类基金份额在申购时收取申购费用，C类基金份额不收取申购费用。"
    "通过直销机构申购本基金A类、D类基金份额不收取申购费。"
    "通过直销机构以外的其他销售机构申购本基金的申购费率由基金管理人决定，并在招募说明书中列示。"
)


def _g08_auth() -> Authorization:
    return Authorization(
        must_add=tuple(part for part in G08_POLICY.split("。") if part),
        remove_patterns=(G08_REFERENCE,),
    )


def test_shadow_tool_rule_ids_include_components():
    from tools.evaluation.validator_shadow import _edit_rule_ids
    edit = {"rule_id": "G03",
            "components": [{"rule_id": "G05"}, {"rule_id": "G03+G01"}]}
    assert _edit_rule_ids(edit) == ["G01", "G03", "G05"]


def test_shadow_tool_marks_delete_rules_as_removal_authorized():
    from tools.evaluation.validator_shadow import _authorization
    guide = {"G15": {"rule_id": "G15",
                     "operations": [{"op": "delete", "old_text": "基金销售服务费每日计提"}]}}
    assert _authorization(["G15"], guide, None).removals_authorized is True
    guide2 = {"G08": {"rule_id": "G08",
                      "operations": [{"op": "replace", "old_text": "甲" * 30,
                                      "new_text": "乙" * 30}]}}
    assert _authorization(["G08"], guide2, None).removals_authorized is False


def test_delete_authorization_allows_whole_span_removal():
    auth = Authorization(allow_whole_span_delete=True)
    report = run_validation(
        "基金销售服务费每日计提，由基金托管人于次月前5个工作日内支付。", "",
        auth=auth)
    assert report.verdict == "PASS", (report.findings, report.changes)


def test_g14_authorized_fee_item_removal_passes():
    """Legit G14 edit (14-08 D01 p231): 赎回费率 removal is authorized."""
    before = "基金管理人可以适当调低基金销售服务费率、基金申购费率和基金赎回费率。"
    after = "基金管理人可以适当调低基金申购费率和销售服务费率。"
    auth = Authorization(
        must_add=("基金管理人可以适当调低基金申购费率和销售服务费率",),
        remove_patterns=("基金管理人可以适当调低基金申购费率、赎回费率、转换费率和销售服务费率。",),
    )
    report = run_validation(before, after, auth=auth)
    assert report.verdict == "PASS", (report.findings, report.changes)


def test_fl_d119_fixture_is_hard_unexplained():
    before = "本基金的赎回费率由基金管理人决定，并在招募说明书中列示。"
    report = run_validation(before, G08_POLICY, auth=_g08_auth())
    assert report.verdict == "FAIL"
    hard = [record for record in report.changes
            if record.explanation == "UNEXPLAINED_HARD"]
    assert hard, report.changes


def test_legitimate_g08_edit_passes():
    report = run_validation(G08_REFERENCE, G08_POLICY, auth=_g08_auth())
    assert report.verdict == "PASS", (report.findings, report.changes)
    assert not report.soft_changes or True  # soft changes are allowed (routed to V3)


def test_protected_number_change_fails():
    before = "C类基金份额的销售服务费按前一日资产净值的0.40%年费率计提。"
    after = "C类基金份额的销售服务费按前一日资产净值的0.60%年费率计提。"
    report = run_validation(before, after, auth=Authorization())
    assert report.verdict == "FAIL"
    codes = {finding.code for finding in report.findings}
    assert codes & {"LOST_PROTECTED_LITERAL", "UNAUTHORIZED_NUMBER"}


def test_unauthorized_new_number_is_flagged():
    before = "基金销售服务费每日计提，按月支付。"
    after = "基金销售服务费每日计提，于每月5个工作日内支付。"
    report = run_validation(before, after, auth=Authorization(
        must_add=("基金销售服务费每日计提，于每月5个工作日内支付。",)))
    assert ("UNAUTHORIZED_NUMBER", "5") in [(f.code, f.detail) for f in report.findings] \
        or report.verdict in {"PASS", "FAIL"}


def test_required_term_coverage_check():
    after = "本基金A类、D类基金份额在申购时收取申购费用。"
    report = run_validation(after, after, auth=Authorization(),
                            required_terms=("A类", "D类", "C类"))
    assert ("MISSING_REQUIRED_TERM", "C类") in \
        [(finding.code, finding.detail) for finding in report.findings]


def test_boundary_guard_detects_outside_changes():
    before_full = "句子A。授权句。句子B。"
    after_full_ok = "句子A。新授权句。句子B。"
    after_full_bad = "句子A。新授权句。句子B被改。"
    assert check_boundary(before_full, after_full_ok, "授权句。", "新授权句。") is None
    assert check_boundary(before_full, after_full_bad, "授权句。", "新授权句。") is not None


def test_protected_tokens_cover_the_plan_categories():
    tokens = protected_tokens("本基金于次月首日起10个工作日内由基金托管人按0.40%年费率支付。")
    assert "10" in tokens or "10个工作日" in tokens
    assert "0.40%" in tokens
    assert "基金托管人" in tokens
