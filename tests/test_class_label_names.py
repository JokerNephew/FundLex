"""class_label name-preservation tests (external review 2026-10-19, P0-B).

Letter-type classes canonicalise to "X类"; names the contract writes descriptively
("人民币份额", "A类人民币份额") are kept verbatim so generated policy text never
contains doubled forms such as "人民币类基金份额".
"""
from fundlex.recall import class_label


def test_letter_classes_stay_canonical():
    assert class_label(["A", "D"]) == "A类、D类基金份额"
    assert class_label(["A类基金份额", "D类基金份额"]) == "A类、D类基金份额"
    assert class_label(["C类"]) == "C类基金份额"


def test_descriptive_names_are_preserved():
    assert class_label(["人民币份额", "美元现汇份额"]) == "人民币份额、美元现汇份额"
    assert class_label(["A类人民币份额"]) == "A类人民币份额"
    assert class_label(["A类人民币份额", "C类美元现汇份额"]) == "A类人民币份额、C类美元现汇份额"


def test_placeholders_and_spacing():
    assert class_label(["default"]) == "基金份额"
    assert class_label(["default", "A"]) == "A类基金份额"
    assert class_label(["A 类"]) == "A类基金份额"
