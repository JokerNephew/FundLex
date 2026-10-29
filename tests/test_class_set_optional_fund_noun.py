"""A model class name without 基金 still proves the same class set."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fundlex.docx import inspect_docx
from fundlex.fact_evidence import verify_class_set

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发美国房地产指数证券投资基金基金合同.docx"


def test_currency_classes_without_the_optional_noun_verify():
    inspection = inspect_docx(SOURCE, full=True)
    quote = ("本基金A类人民币基金份额、A类美元基金份额、C类人民币基金份额、"
             "C类美元基金份额分别设置代码")
    classes = [SimpleNamespace(name=name, current=True) for name in
               ("A类人民币份额", "A类美元份额", "C类人民币份额", "C类美元份额")]
    result = verify_class_set(inspection, classes, quote)
    assert result["quote_verified"] is True
    assert result["set_complete_verified"] is True, result
