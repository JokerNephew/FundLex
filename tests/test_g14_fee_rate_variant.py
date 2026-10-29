"""G14 must accept contracts that repeat the noun after 和/及."""
from __future__ import annotations

import json
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.recall import (Target, _expand_fee_rate_reference,
                            _normalise_fee_rate_reference,
                            assign_target_operations)
from test_recall_core import _facts

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发价值优选混合型证券投资基金基金合同.docx"


def _g14_rule() -> dict:
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
    return next(rule for rule in guide["groups"] if rule["rule_id"] == "G14")


def test_repeated_noun_normalises_and_expands():
    source = "基金管理人可以适当调低基金申购费率和基金赎回费率。"
    canonical = "基金管理人可以适当调低基金申购费率和赎回费率。"
    assert _normalise_fee_rate_reference(source) == _normalise_fee_rate_reference(canonical)
    assert _expand_fee_rate_reference(canonical) in source


def test_g14_canonical_quote_attributes_to_repeated_noun_source():
    inspection = inspect_docx(SOURCE, full=True)
    quote = "基金管理人可以适当调低基金申购费率和赎回费率。"
    target = Target("T_G14", "G14", "p209", quote, "needs_edit", "rebind",)
    assign_target_operations([target], {"G14": _g14_rule()}, inspection, _facts())
    assert target.out_of_scope is False, target.reason
    assert "G14:3" in target.operations, target.operations
