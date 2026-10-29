"""G17 deletes the authorized usage sentence, not the paragraph's discount tail."""
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
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发中证A50交易型开放式指数证券投资基金联接基金合同20261020.docx"


def test_g17_keeps_unauthorized_rate_discount_tail():
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    rule = next(item for item in guide["groups"] if item["rule_id"] == "G17")
    inspection = inspect_docx(SOURCE, full=True)
    text = inspection.by_location("p799").text
    target = Target("T", "G17", "p799", text, "needs_edit", "",
                    start=0, end=len(text), resolution="resolved",
                    operations=("G17:0",))
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.replacement == ""
    after = text[:edit.start] + edit.replacement + text[edit.end:]
    assert after.startswith("基金管理人可根据基金发展情况下调销售服务费率")
    assert "销售服务费主要用于" not in after
