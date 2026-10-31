"""FL-D692: scorer class-enumeration fold + currency-split equivalence layers.

Mainline-authorised instrument fix (labels frozen): loop-3 wrong:7 and two of
B15's not_executed verdicts were instrument artifacts — the obligations were
present verbatim in final.docx but written in an equivalent class-naming form
the scorer could not absorb:

(a) fold vs expanded enumeration: label 「C类基金份额和E类基金份额」 vs engine
    (guide-slot instantiation) 「C类、E类基金份额」 — after the existing letter
    collapse the expanded form read 「基金份额和基金份额」 vs the folded
    「基金份额」, and neither exact-substring nor fuzzy 0.9 bridged the
    connector-joined duplicate subject (the mainline reviewer's mechanism).
(b) currency-split class names per product facts: B15 writes
    「A类人民币、A类美元」/「C类人民币、C类美元」 where the label names
    「A类基金份额」/「C类基金份额」; the fee obligation is class-letter-scoped.

Every positive case below is a real (required_text, final.docx site) pair from
the loop-3 wave; negatives must stay distinct.
"""
import sys

sys.path.insert(0, "tools/evaluation")
from tools.evaluation.p6_score import _clause_present, _normalise_policy


def test_fold_vs_expanded_enumeration_b17_t003():
    assert _clause_present(
        "本基金A类基金份额在申购时收取申购费用，C类基金份额和E类基金份额不收取申购费用",
        "本基金A类基金份额在申购时收取申购费用，C类、E类基金份额不收取申购费用。通过直销机构")


def test_folded_short_clause_b17_t006():
    assert _clause_present("本基金C类基金份额和E类基金份额不收取申购费用",
                           "本基金C类、E类基金份额不收取申购费用。")


def test_triple_class_fold_b17_t012():
    assert _clause_present("由于本基金A类基金份额和C类基金份额、E类基金份额费用收取不同",
                           "由于本基金A类基金份额和C类、E类基金份额费用收取不同")


def test_currency_split_distribution_clause_b15_t011():
    assert _clause_present(
        "由于本基金A类基金份额和C类基金份额费用收取不同",
        "由于本基金A类人民币、A类美元和C类人民币、C类美元费用收取不同")


def test_currency_split_direct_sales_clause_b15_t005():
    assert _clause_present(
        "通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的申购费用由投资人承担，不列入基金财产",
        "通过直销机构申购本基金A类人民币、A类美元不收取申购费，通过其他销售机构申购本基金A类人民币、A类美元的申购费用由投资人承担，不列入基金财产")


def test_currency_split_g16_refund_clause_b15_t008():
    assert _clause_present(
        "（1）直销机构：对于投资者通过直销机构持有的C类基金份额计提的销售服务费，在投资者赎回C类基金份额或基金合同终止时，随赎回款（或清算款）一并返还给投资者",
        "（1）直销机构：对于投资者通过直销机构持有的C类人民币、C类美元计提的销售服务费，在投资者赎回C类人民币、C类美元或基金合同终止时，随赎回款（或清算款）一并返还给投资者")


def test_currency_split_short_clause_b15_t005_tail():
    assert _clause_present("本基金C类基金份额不收取申购费用",
                           "本基金C类人民币、C类美元不收取申购费用。")


def test_negatives_stay_distinct():
    assert not _clause_present("本基金C类基金份额不收取申购费用",
                               "本基金C类基金份额收取申购费用")
    assert not _clause_present("销售服务费每日计提", "管理费每日计提")
    assert not _clause_present("通过直销机构申购本基金A类基金份额不收取申购费",
                               "直销机构名单详见招募说明书")


def test_existing_letter_collapse_semantics_unchanged():
    # Different real class letters still equate to the template letter (the
    # append clauses' established equivalence family; test_p6_score_append).
    assert _normalise_policy("申购本基金A类、D类基金份额时") == \
        _normalise_policy("申购本基金A类基金份额时")
    assert _normalise_policy("申购本基金A类、B类和C类基金份额时") == \
        _normalise_policy("申购本基金A类基金份额时")
    # The new layers are idempotent and neutral on class-free text.
    value = _normalise_policy("A类人民币、A类美元和C类人民币、C类美元费用收取不同")
    assert _normalise_policy(value) == value
    plain = _normalise_policy("基金管理人可以适当调低基金申购费率和销售服务费率")
    assert _normalise_policy(plain) == plain
