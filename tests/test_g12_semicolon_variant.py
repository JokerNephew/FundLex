"""G12 must replace the whole allocation sentence when the source uses '；'."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import Target, plan_target

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g17_usage_site_closure import NoModel  # noqa: E402
from test_recall_core import _facts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发沪深300指数增强型发起式证券投资基金基金合同.docx"


def test_g12_variant_replaces_the_old_allocation_sentence():
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    rule = next(item for item in guide["groups"] if item["rule_id"] == "G12")
    inspection = inspect_docx(SOURCE, full=True)
    text = inspection.by_location("p244").text
    quote = "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示"
    start = text.find(quote)
    assert start >= 0
    target = Target("T", "G12", "p244", quote, "needs_edit", "",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=("G12:0",))
    facts = _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.replacement == ("赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
                                "赎回费用全额计入基金财产。")
    assert inspection.by_location("p244").text[edit.end:edit.end + 1] == "对"
