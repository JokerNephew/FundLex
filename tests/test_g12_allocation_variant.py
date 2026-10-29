"""G12's differently-worded allocation clause is replaced deterministically."""
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
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发美国房地产指数证券投资基金基金合同.docx"


def test_g12_allocation_variant_replaces_the_whole_clause():
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    rule = next(item for item in guide["groups"] if item["rule_id"] == "G12")
    inspection = inspect_docx(SOURCE, full=True)
    text = inspection.by_location("p165").text
    quote = ("本基金各类基金份额的赎回费用由该类基金份额持有人承担，"
             "其中不低于赎回费总额的25%应当归入基金财产，其余部分用于支付注册登记费等相关手续费。")
    assert text == quote
    target = Target("T", "G12", "p165", quote, "needs_edit", "",
                    start=0, end=len(text), resolution="resolved",
                    operations=("G12:1",))
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.replacement == ("赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
                                "赎回费用全额计入基金财产。")
