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


def test_g08_actual_rate_variant_is_evidence_not_a_site():
    """FL-D602: the actual-rate wording closes applicability, it is never a target."""
    from fundlex.recall import find_g08_actual_rate_site, missing_guide_site

    inspection = inspect_docx(
        ROOT / "funds_word" / "基金合同第一批" /
        "广发美国房地产指数证券投资基金基金合同.docx", full=True)
    rule = _rule("G08")
    facts = _facts()
    site = find_g08_actual_rate_site(inspection)
    assert site is not None and site["location"] == "p162"
    evidence = missing_guide_site("G08", [], {"G08": rule}, inspection, facts)
    assert evidence is not None
    assert evidence["variant_location"] == "p162"
    assert "实际执行的申购费率" in evidence["variant_quote"]


def test_g22_ordered_list_variant_is_evidence_not_a_site():
    """FL-D601: the ordered-list liquidation item closes applicability, never a target."""
    import dataclasses

    from fundlex.recall import find_g22_ordered_list_site, missing_guide_site

    inspection = inspect_docx(
        ROOT / "funds_word" / "基金合同第一批" /
        "广发美国房地产指数证券投资基金基金合同.docx", full=True)
    rule = _rule("G22")
    facts = dataclasses.replace(_facts(), quotes_verified={"floating": True})
    site = find_g22_ordered_list_site(inspection)
    assert site is not None
    assert site["location"] == "p883"
    assert site["quote"].startswith("按基金份额持有人持有的基金份额比例进行分配")
    evidence = missing_guide_site("G22", [], {"G22": rule}, inspection, facts)
    assert evidence is not None
    assert evidence["variant_location"] == "p883"


def test_missing_guide_site_keeps_live_target_and_canonical_sentence():
    """FL-D601/602: a live target or the canonical sentence blocks FALSE closure."""
    import dataclasses
    from types import SimpleNamespace

    from fundlex.recall import missing_guide_site

    rule = _rule("G22")
    facts = dataclasses.replace(_facts(), quotes_verified={"floating": True})
    canonical = str(rule["operations"][0]["old_text"])
    inspection = SimpleNamespace(paragraphs=[SimpleNamespace(text=canonical,
                                                             location="p1")])
    live = Target("T", "G22", "p1", canonical, "needs_edit", "")
    assert missing_guide_site("G22", [live], {"G22": rule}, inspection, facts) is None
    assert missing_guide_site("G22", [], {"G22": rule}, inspection, facts) is None
    empty = SimpleNamespace(paragraphs=[SimpleNamespace(text="无关条款。", location="p1")])
    evidence = missing_guide_site("G22", [], {"G22": rule}, empty, facts)
    assert evidence is not None and evidence["site"] == "G22"
    assert "variant_location" not in evidence


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
    from test_recall_core import _facts as simple_facts
    rule = _rule("G18")
    facts = simple_facts()  # A/C two classes
    body = ("4、由于本基金A类和C类基金份额的费用存在不同，不同类别的基金份额在收益分配"
            "数额方面可能有所不同，基金管理人可对各类别基金份额分别制定收益分配方案，"
            "同一类别内的每一基金份额享有同等分配权；")
    keys = satisfied_operation_keys(rule, facts, body)
    assert "G18:0" in keys


def test_g08_prefixed_class_fee_clause_is_attributed():
    from fundlex.recall import assign_target_operations, Target
    inspection = inspect_docx(
        ROOT / "funds_word" / "基金合同第一批" /
        "广发弘利3个月滚动持有债券型证券投资基金基金合同.docx", full=True)
    text = inspection.by_location("p216").text
    target = Target("T", "G08", "p216", text, "needs_edit", "",
                    start=0, end=len(text), resolution="resolved",
                    operations=("G08:0",))
    rule = _rule("G08")
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    errors = assign_target_operations([target], {"G08": rule}, inspection, facts, ledger)
    assert not errors, errors
    assert target.operations == ("G08:0",)


def test_g14_promotion_clause_converges_verb_to_lower():
    """FL-D606: the promotion-context clause grants 调整 (either direction);
    G14 authorizes lowering only, so the deterministic generator converges the
    verb to 调低 together with the fee-item narrowing."""
    import fundlex.recall as recall

    rule = _rule("G14")
    replace_ops = [op for op in (rule.get("operations") or []) if op.get("op") == "replace"]
    facts = _facts()  # multi-class with service fee → 申购费率+销售服务费率 allowed
    actual = ("在基金促销活动期间，基金管理人可以按中国证监会要求履行必要手续后，"
              "对投资者适当调整基金申购费率、赎回费率、销售服务费率和转换费率。")

    original = recall._tier1_enabled
    recall._tier1_enabled = lambda: True
    try:
        result = recall._plan_tier1(rule, replace_ops, facts, actual)
    finally:
        recall._tier1_enabled = original

    assert result is not None
    assert "对投资者适当调低" in result.replacement
    assert "适当调整" not in result.replacement
    assert "赎回费率" not in result.replacement
    assert "转换费率" not in result.replacement
    assert "申购费率" in result.replacement
    assert "销售服务费率" in result.replacement
    # The non-promotion lead-in survives verbatim.
    assert result.replacement.startswith("在基金促销活动期间")
