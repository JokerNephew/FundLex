"""Old-site tails must not make a multi-component rule look already satisfied."""
from __future__ import annotations

import json
from pathlib import Path

from fundlex.recall import satisfied_by_new_text
from fundlex.targeting import normalise_locator_location
from test_recall_core import _facts

ROOT = Path(__file__).resolve().parents[1]
GUIDE = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))


def _rule(rule_id: str) -> dict:
    return next(rule for rule in GUIDE["groups"] if rule["rule_id"] == rule_id)


def test_g09_old_tail_alone_is_not_satisfied():
    old_tail = ("赎回金额为按实际确认的有效赎回份额乘以当日对应份额类别的基金份额净值"
                "并扣除相应的费用，赎回金额单位为元。")
    assert satisfied_by_new_text(_rule("G09"), _facts(), old_tail) is None


def test_g09_complete_new_policy_is_satisfied():
    new = ("赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额的基金份额净值"
           "并扣除或加上相应的费用，赎回金额单位为元。")
    assert satisfied_by_new_text(_rule("G09"), _facts(), new)


def test_g11_c_class_tail_alone_is_not_satisfied():
    old_tail = "4、申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。"
    assert satisfied_by_new_text(_rule("G11"), _facts(), old_tail) is None


def test_g11_full_new_policy_is_satisfied():
    new = ("通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的"
           "申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。")
    assert satisfied_by_new_text(_rule("G11"), _facts(), new)


def test_locator_bracket_labels_normalise_to_the_candidate():
    allowed = {"p164", "p245"}
    assert normalise_locator_location("[p164]", allowed) == "p164"
    assert normalise_locator_location("【p245】", allowed) == "p245"
    assert normalise_locator_location("candidate p245 paragraph", allowed) == "p245"
    assert normalise_locator_location("p999", allowed) == "p999"
