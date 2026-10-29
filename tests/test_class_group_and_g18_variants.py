"""Coordinated class groups and G18's multi-class fee-difference clause."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import (ClassFact, Facts, Target, _class_group_phrase_span,
                            plan_target)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g17_usage_site_closure import NoModel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发道琼斯美国石油开发与生产指数证券投资基金（QDII-LOF）基金合同.docx"
GUIDE = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))


def _facts() -> Facts:
    names = [("A类人民币", True, False), ("A类美元现汇", True, False),
             ("C类人民币", False, True), ("C类美元现汇", False, True),
             ("E类人民币", False, True), ("E类美元现汇", False, True)]
    classes = tuple(ClassFact(name=name, subscription_fee=sub, service_fee=svc,
                              current=True, rate=None, quote=name)
                    for name, sub, svc in names)
    return Facts(fund_type="open_regular", fund_type_quote="契约型开放式",
                 fund_type_basis="test", classes=classes,
                 floating_management_fee=False, floating_quote="", floating_basis="",
                 notes="", quotes_verified={}, problems=(),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def _rule(rule_id: str) -> dict:
    return next(item for item in GUIDE["groups"] if item["rule_id"] == rule_id)


def test_group_phrase_span_expands_coordinated_labels():
    text = "称为C类基金份额或E类基金份额。"
    start, end = _class_group_phrase_span(text, 2, 8)
    assert text[start:end] == "C类基金份额或E类基金份额"


def test_g02_replaces_the_whole_coordinated_group():
    inspection = inspect_docx(SOURCE, full=True)
    text = inspection.by_location("p126").text
    quote = "C类基金份额或E类基金份额"
    start = text.find(quote)
    target = Target("T", "G02", "p126", quote, "needs_edit", "",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=("G02:1",))
    rule = _rule("G02")
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.replacement == "C类人民币、C类美元现汇、E类人民币、E类美元现汇"
    assert edit.end == start + len(quote)


def test_g18_uses_every_actual_class_group():
    inspection = inspect_docx(SOURCE, full=True)
    text = inspection.by_location("p926").text
    quote = ("由于本基金A类基金份额不收取销售服务费，"
             "而C类基金份额和E类基金份额收取销售服务费")
    start = text.find(quote)
    target = Target("T", "G18", "p926", quote, "needs_edit", "",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=("G18:0",))
    rule = _rule("G18")
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.replacement == ("由于本基金A类人民币、A类美元现汇和"
                                "C类人民币、C类美元现汇、E类人民币、E类美元现汇费用收取不同")


def test_g08_actual_rate_variant_is_bound_and_replaced():
    from types import SimpleNamespace

    from fundlex.recall import ensure_g08_actual_rate_targets, assign_target_operations

    inspection = inspect_docx(
        ROOT / "funds_word" / "基金合同第一批" /
        "广发美国房地产指数证券投资基金基金合同.docx", full=True)
    rule = _rule("G08")
    facts = _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    scope = {"G08": SimpleNamespace(locations=frozenset(
        {f"p{i}" for i in range(123, 348)}))}
    targets = ensure_g08_actual_rate_targets([], {"G08": rule}, inspection, scope)
    assert len(targets) == 1
    target = targets[0]
    assert target.location == "p162"
    assign_target_operations(targets, {"G08": rule}, inspection, facts, ledger)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert "在申购时收取申购费用" in edit.replacement
    assert "通过直销机构申购本基金" in edit.replacement


def test_g11_replaces_pre_existing_c_class_sentence_without_duplication():
    inspection = inspect_docx(
        ROOT / "funds_word" / "基金合同第一批" /
        "广发富信优选六个月持有期混合型基金中基金（FOF）基金合同20261020.docx", full=True)
    rule = _rule("G11")
    text = inspection.by_location("p245").text
    quote = "申购费用由投资人承担，不列入基金财产。"
    start = text.find(quote)
    target = Target("T", "G11", "p245", quote, "needs_edit", "",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=("G11:1",))
    facts = _facts()
    # This fixture has A/C/E classes; the G11 text instantiates C only once.
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    after = text[:edit.start] + edit.replacement + text[edit.end:]
    assert after.count("本基金C类基金份额不收取申购费用。") == 1


def test_g18_preserves_distribution_tail_after_fee_sentence():
    inspection = inspect_docx(SOURCE, full=True)
    text = inspection.by_location("p1322").text
    quote = ("由于本基金A类基金份额不收取销售服务费，"
             "而C类基金份额和E类基金份额收取销售服务费，"
             "各基金份额类别对应的可供分配利润将有所不同，"
             "本基金同一类别的每一基金份额享有同等分配权；")
    start = text.find(quote)
    target = Target("T", "G18", "p1322", quote, "needs_edit", "",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=("G18:0",))
    rule = _rule("G18")
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.replacement.endswith(
        "，各基金份额类别对应的可供分配利润将有所不同，"
        "本基金同一类别的每一基金份额享有同等分配权；")


def test_g18_fee_existence_variant_is_already_satisfied():
    from fundlex.recall import satisfied_operation_keys
    rule = _rule("G18")
    facts = _facts()  # A/C two classes
    body = ("4、由于本基金A类和C类基金份额的费用存在不同，不同类别的基金份额在收益分配"
            "数额方面可能有所不同，基金管理人可对各类别基金份额分别制定收益分配方案，"
            "同一类别内的每一基金份额享有同等分配权；")
    keys = satisfied_operation_keys(rule, facts, body)
    assert "G18:0" in keys
