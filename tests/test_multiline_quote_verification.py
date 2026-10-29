"""A multi-paragraph fee quote is verified line by line."""
from __future__ import annotations

from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.recall import _verify_quote

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发沪深300指数增强型发起式证券投资基金基金合同.docx"


def test_multiline_management_fee_quote_is_verified():
    inspection = inspect_docx(SOURCE, full=True)
    quote = ("（1）A类基金份额和C类基金份额\n"
             "本基金A类和C类基金份额的管理费按前一日该类基金份额基金资产净值的1.0%年费率计提。\n"
             "H＝E×1.0%÷当年天数\n"
             "H为每日应计提的基金管理费\n"
             "E为前一日该类基金份额的基金资产净值")
    assert _verify_quote(inspection, quote)


def test_one_invented_line_still_fails():
    inspection = inspect_docx(SOURCE, full=True)
    quote = "本基金A类和C类基金份额的管理费按前一日该类基金份额基金资产净值的1.0%年费率计提。\n不存在的管理费条款。"
    assert not _verify_quote(inspection, quote)
