"""Identical body/summary clauses must share one rule scope even without a 摘要 title."""
from types import SimpleNamespace

from fundlex.docx import inspect_docx
from fundlex.recall import Target
from fundlex.recall_pipeline import _expand_duplicate_copy_scopes
from fundlex.rule_scope import RuleScope
import json

SOURCE = ("funds_word/基金合同第一批/广发美国房地产指数证券投资基金基金合同.docx")
GUIDE = json.loads((__import__("pathlib").Path(__file__).resolve().parents[1] /
                    "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))


def test_fee_clause_summary_copy_is_added_to_scope():
    inspection = inspect_docx(SOURCE, full=True)
    scope = RuleScope("G15", frozenset(), frozenset({"p720"}), "body", False,
                      frozenset({"销售服务费"}), "resolved", ())
    scopes = {"G15": scope}
    target = Target("T", "G15", "p720", inspection.by_location("p720").text,
                    "needs_edit", "", operations=("G15:0",))
    targets = [target]
    rules = {rule["rule_id"]: rule for rule in GUIDE["groups"] if rule["rule_id"] == "G15"}
    _expand_duplicate_copy_scopes(targets, scopes, inspection, rules)
    assert scopes["G15"].contains("p1129")
    assert scopes["G15"].include_summary_copies
    assert any(item.location == "p1129" for item in targets)


def test_numbered_income_and_liquidation_summary_copies_are_cloned():
    from fundlex.recall import Target
    inspection = inspect_docx(SOURCE, full=True)
    guide = {rule["rule_id"]: rule for rule in GUIDE["groups"]}
    scopes = {
        "G18": RuleScope("G18", frozenset(), frozenset({"p734"}), "body", False,
                         frozenset({"收益分配"}), "resolved", ()),
        "G22": RuleScope("G22", frozenset(), frozenset({"p883"}), "body", False,
                         frozenset(), "resolved", ()),
    }
    targets = [
        Target("T18", "G18", "p734",
               "由于本基金A类基金份额不收取销售服务费，而C类基金份额收取销售服务费",
               "needs_edit", "", operations=("G18:0",)),
        Target("T22", "G22", "p883",
               "按基金份额持有人持有的基金份额比例进行分配。",
               "needs_edit", "", operations=("G22:0",)),
    ]
    _expand_duplicate_copy_scopes(targets, scopes, inspection, guide)
    assert any(item.rule_id == "G18" and item.location == "p1095" for item in targets)
    assert any(item.rule_id == "G22" and item.location == "p1239" for item in targets)
