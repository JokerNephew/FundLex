"""An absent G06 target must not hide a surviving short prohibition sentence."""
from __future__ import annotations

import json
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.recall import Target, ensure_delete_targets


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发价值优选混合型证券投资基金基金合同.docx"


def _g06_rule() -> dict:
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    return next(rule for rule in guide["groups"] if rule["rule_id"] == "G06")


def test_absent_g06_quote_does_not_cover_real_source_sentence():
    inspection = inspect_docx(SOURCE, full=True)
    quote = "本基金不同基金份额类别之间不得互相转换。"
    absent = Target(
        "T009", "G06", "p128", quote, "absent", "guide variant absent",
        start=184, end=204, operations=("G06:0",), resolution="resolved",
        segment_ok=True,
    )
    created = ensure_delete_targets(
        [absent], {"G06": _g06_rule()}, inspection, limit=20,
    )
    assert any(item.rule_id == "G06" and item.location == "p128"
               and item.state == "needs_edit"
               and "不同基金份额类别之间不得互相转换" in item.quote
               for item in created), created
    assert absent.state == "absent"
