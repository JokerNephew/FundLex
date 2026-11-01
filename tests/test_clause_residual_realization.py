"""Replaced-clause residual detection with class-set realization (B17 G11 p294).

The guide declares canonical class sets (``C类基金份额不收取申购费用``), while
contracts realize the same clause with different joiners and additional class
members (``C类基金份额和E类基金份额不收取申购费用``).  A literal containment
check then cannot see the survivor: the replacement removed the first sentence
of the compound old clause at B17 p294 but the class-expanded tail stayed,
replay still reported PASS and the run delivered ``complete`` — a true "该改未
改" false complete.  Detection must follow the clause through source
realization (same non-class skeleton, superset class labels) and judge
retention by occurrence count plus skeleton/label equality with the new text.
"""
from __future__ import annotations

from fundlex.generation.effects import _replaced_clause_residuals

B17_BEFORE = ("4、A类基金份额的申购费用由投资人承担，不列入基金财产；"
              "C类基金份额和E类基金份额不收取申购费用。")
B17_AFTER = ("4、通过直销机构申购本基金A类基金份额不收取申购费，"
             "通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，"
             "不列入基金财产。本基金C类、E类基金份额不收取申购费用。"
             "C类基金份额和E类基金份额不收取申购费用。")
G11_OP_OLD = "申购费用由投资人承担，不列入基金财产。"
G11_ONE_OF_ALTERNATIVE = ("本基金A类基金份额的申购费用由投资人承担，不列入基金财产；"
                          "C类基金份额不收取申购费用。")
G11_NEW = ("通过直销机构申购本基金A类基金份额不收取申购费，"
           "通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，"
           "不列入基金财产。本基金C类、E类基金份额不收取申购费用。")


def test_b17_class_expanded_tail_is_a_residual():
    residuals = _replaced_clause_residuals(
        B17_BEFORE, B17_AFTER, [G11_OP_OLD, G11_ONE_OF_ALTERNATIVE], G11_NEW)
    assert residuals == ["C类基金份额和E类基金份额不收取申购费用"]


def test_new_text_retention_is_not_a_residual():
    after = ("4、通过直销机构申购本基金A类基金份额不收取申购费，"
             "通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，"
             "不列入基金财产。本基金C类、E类基金份额不收取申购费用。")
    assert _replaced_clause_residuals(
        B17_BEFORE, after, [G11_OP_OLD, G11_ONE_OF_ALTERNATIVE], G11_NEW) == []


def test_joiner_normalized_retention_is_not_a_residual():
    """New text keeps the same statement with a normalized enumeration style."""
    before = "申购费用由投资人承担，不列入基金财产；C类基金份额和E类基金份额不收取申购费用。"
    new = ("通过其他销售机构申购本基金的申购费用由投资人承担，不列入基金财产。"
           "C类、E类基金份额不收取申购费用。")
    after = new
    residuals = _replaced_clause_residuals(
        before, after, [G11_ONE_OF_ALTERNATIVE, G11_OP_OLD], new)
    assert residuals == []


def test_narrower_class_set_is_a_different_statement_fail_closed():
    """The source listing fewer classes than the reference never realizes it."""
    before = "4、相关条款；B类基金份额不收取申购费用。"
    after = before
    residuals = _replaced_clause_residuals(
        before, after, [G11_ONE_OF_ALTERNATIVE],
        "本基金A类基金份额的申购费用由投资人承担，不列入基金财产。")
    # B-only is not the C-class clause; nothing matches, nothing is flagged —
    # but crucially the C-clause is not *found* in this source either, so no
    # false realization occurs.
    assert residuals == []


def test_duplicate_beyond_new_text_allowance_is_flagged():
    """New text retaining the clause once cannot excuse a second survivor."""
    before = "4、A类基金份额的申购费用由投资人承担，不列入基金财产；C类基金份额不收取申购费用。"
    new = ("本基金A类基金份额的申购费用由投资人承担，不列入基金财产。"
           "C类基金份额不收取申购费用。")
    after = new + "C类基金份额不收取申购费用。"
    residuals = _replaced_clause_residuals(
        before, after, [G11_ONE_OF_ALTERNATIVE], new)
    assert "C类基金份额不收取申购费用" in residuals


def test_legacy_literal_clause_behaviour_unchanged():
    before = "管理费按前一日基金资产净值计提。托管费按前一日基金资产净值计提。"
    after = "托管费按前一日基金资产净值计提。"
    new = "托管费由托管人按约定收取。"
    residuals = _replaced_clause_residuals(
        before, after, ["管理费按前一日基金资产净值计提"], new)
    assert residuals == []
    after_leftover = "管理费按前一日基金资产净值计提。托管费由托管人按约定收取。"
    residuals = _replaced_clause_residuals(
        before, after_leftover, ["管理费按前一日基金资产净值计提"], new)
    assert residuals == ["管理费按前一日基金资产净值计提"]
