"""Multi-leaf class scopes, fee-title families and copy-key identity.

No model calls and no network access.  The 景宁 fixture is a real repository
contract; tiny fake inspections cover title variants that the fixture lacks.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fundlex.docx import inspect_docx
from fundlex.recall import Target, structure_index
from fundlex.recall_pipeline import _apply_scope_gate
from fundlex.rule_scope import build_leaf_sections, resolve_rule_scopes

ROOT = Path(__file__).resolve().parents[1]
JINGNING = (ROOT / "funds_word" / "基金合同第一批"
            / "广发景宁纯债债券型证券投资基金基金合同.docx")


@pytest.fixture(scope="module")
def jingning():
    if not JINGNING.exists():
        pytest.skip(f"missing fixture: {JINGNING}")
    inspection = inspect_docx(JINGNING)
    return inspection, structure_index(inspection)


def _rule(rule_id: str, title: str = "", section_hint: str = "") -> dict:
    return {"rule_id": rule_id, "title": title, "section_hint": section_hint}


def _span(location: str, text: str, zone: str = "body") -> SimpleNamespace:
    return SimpleNamespace(location=location, text=text, zone=zone, logical_zone=zone,
                           section_path="")


def _section(section_id: str, title: str, locations: tuple[str, ...],
             zone: str = "body") -> SimpleNamespace:
    return SimpleNamespace(id=section_id, title=title, zone=zone, locations=locations)


def _inspection(spans: tuple[SimpleNamespace, ...]) -> SimpleNamespace:
    by_location = {span.location: span for span in spans}
    return SimpleNamespace(paragraphs=spans,
                           by_location=lambda location: by_location[location])


def _fee_rule(rule_id: str = "G15") -> dict:
    return _rule(rule_id, "基金费用与税收-3、基金销售服务费", "基金费用与税收")


def _class_rule(rule_id: str = "G05") -> dict:
    return _rule(rule_id, "基金的基本情况-份额类别设置", "基金的基本情况")


# ---------------------------------------------------------------------------
# 景宁 real contract: p148 and p155 are both body G05 sites
# ---------------------------------------------------------------------------

def test_jingning_g05_scope_covers_setting_and_class_leaves(jingning):
    """G05 must inspect both 八、基金份额类别设置 (p148) and 九、基金份额的类别 (p155)."""

    inspection, sections = jingning
    scope = resolve_rule_scopes(
        [_class_rule("G05")], sections, inspection, {"G05": ["S05"]},
    )["G05"]

    assert scope.resolution == "resolved"
    assert scope.leaf_ids == frozenset({"S05:L09", "S05:L10"})
    assert {f"p{number}" for number in range(147, 157)} <= scope.locations
    assert {"p148", "p155"} <= scope.locations
    assert scope.contains("p148") and scope.contains("p155")
    for location in ("p148", "p155"):
        text = inspection.by_location(location).text
        assert "调低赎回费率" in text
        assert "报中国证监会备案" in text
    assert any(item == "multi_leaf=2" for item in scope.evidence)

    # Unrelated locations stay outside: 释义 definition, the subscription-fee
    # leaf and the fee-adjustment chapter.
    for excluded in ("p120", "p142", "p778", "p779", "p780"):
        assert excluded not in scope.locations
        assert not scope.contains(excluded)
    assert scope.zone == "body"
    assert scope.include_summary_copies is False


def test_jingning_g05_scope_gate_accepts_p155_and_rejects_p120(jingning):
    """The same RuleScope used by the pipeline gate must admit p155, not p120."""

    inspection, sections = jingning
    scope = resolve_rule_scopes(
        [_class_rule("G05")], sections, inspection, {"G05": ["S05"]},
    )["G05"]
    inside = Target("T1", "G05", "p155", "份额类别", "needs_edit", "")
    outside = Target("T2", "G05", "p120", "基金份额类别", "needs_edit", "")
    audit: dict = {"dropped": [], "dropped_counts": {}}

    _apply_scope_gate([inside, outside], {"G05": scope}, audit)

    assert inside.out_of_scope is False
    assert inside.scope_id
    assert outside.out_of_scope is True
    assert audit["dropped_counts"].get("plan:OUT_OF_RULE_SCOPE:G05") == 1


def test_jingning_g04_keeps_the_single_definition_leaf(jingning):
    """The multi-leaf policy must not pull the p148 fee-adjustment leaf into G04."""

    inspection, sections = jingning
    scope = resolve_rule_scopes(
        [_class_rule("G04")], sections, inspection, {"G04": ["S05"]},
    )["G04"]

    assert scope.resolution == "resolved"
    assert scope.leaf_ids == frozenset({"S05:L10"})
    assert "p151" in scope.locations
    assert "p148" not in scope.locations


def test_jingning_g05_summary_mapping_does_not_widen_without_a_real_copy(jingning):
    """A mapped summary chapter is not admitted unless a real copy key matches."""

    inspection, sections = jingning
    mapping = {"G05": ["S05", "S26"]}
    default = resolve_rule_scopes([_class_rule("G05")], sections, inspection,
                                  mapping)["G05"]
    assert default.include_summary_copies is False
    assert "p1104" not in default.locations

    explicit = resolve_rule_scopes(
        [_class_rule("G05")], sections, inspection, mapping,
        include_summary_copies={"G05": True},
        summary_copy_keys={"G05": ["份额类别"]},
    )["G05"]
    # 景宁's summary has no copy of the class-setup clause, only unrelated
    # holders'-meeting powers (p1104/p1107).
    assert explicit.include_summary_copies is False
    assert "p1104" not in explicit.locations
    assert "p1107" not in explicit.locations
    assert any(item == "summary_copy=no_matching_copy_key" for item in explicit.evidence)


def test_jingning_copy_keys_come_from_title_word_family(jingning):
    """Fixed tokens mis-keyed 基金份额的类别 as 销售服务费 and fee-types likewise."""

    inspection, sections = jingning
    leaves = {leaf.id: leaf for leaf in build_leaf_sections(inspection, sections)}

    assert leaves["S05:L10"].copy_key == "份额类别"
    assert leaves["S17:L02"].copy_key == "基金费用种类"
    assert leaves["S17:L06"].copy_key == "费用调整"
    assert leaves["S26:L14"].copy_key == "销售服务费"
    # The holders'-meeting summary merely mentions fees; it is not a fee copy.
    assert leaves["S26:L03"].copy_key == ""


def test_jingning_g15_explicit_service_fee_key_selects_only_the_real_copy(jingning):
    inspection, sections = jingning
    mapping = {"G15": ["S17", "S26"]}
    rules = [_fee_rule("G15")]

    default = resolve_rule_scopes(rules, sections, inspection, mapping)["G15"]
    assert default.include_summary_copies is False
    assert "p1234" not in default.locations

    explicit = resolve_rule_scopes(
        rules, sections, inspection, mapping,
        include_summary_copies={"G15": True},
        summary_copy_keys={"G15": ["服务费"]},
    )["G15"]
    assert explicit.include_summary_copies is True
    assert {"p764", "p1234", "p1255"} <= explicit.locations
    # Fee-types and holders'-meeting summaries are different clauses.
    assert "p1209" not in explicit.locations
    assert "p1084" not in explicit.locations

    wrong_key = resolve_rule_scopes(
        rules, sections, inspection, mapping,
        include_summary_copies={"G15": True},
        summary_copy_keys={"G15": ["基金费用种类"]},
    )["G15"]
    assert wrong_key.include_summary_copies is False
    assert "p1209" not in wrong_key.locations


# ---------------------------------------------------------------------------
# Fee chapter and sales-service-fee leaf title variants
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("section_title", [
    "第十四部分基金费用",
    "第十四部分基金的费用",
    "第十四部分费用与税收",
])
def test_fee_chapter_title_word_family_resolves(section_title):
    spans = (
        _span("p1", "一、基金费用的种类"),
        _span("p2", "基金管理费、基金托管费等费用。"),
        _span("p3", "二、销售服务费的计提与支付"),
        _span("p4", "销售服务费每日计提，按月支付。"),
    )
    sections = (_section("S01", section_title, ("p1", "p2", "p3", "p4")),)

    scope = resolve_rule_scopes([_fee_rule()], sections, _inspection(spans),
                                {"G15": ["S01"]})["G15"]

    assert scope.resolution == "resolved"
    assert {"p3", "p4"} <= scope.locations
    assert "p1" not in scope.locations  # fee-types list, not the fee clause
    assert len(scope.leaf_ids) == 1


@pytest.mark.parametrize("heading", [
    "二、C类基金份额的销售服务费",
    "3、销售服务费的计提与支付",
    "二、服务费",
])
def test_sales_fee_leaf_title_variants_resolve(heading):
    spans = (
        _span("p1", "一、基金费用的种类"),
        _span("p2", "基金管理费、基金托管费等费用。"),
        _span("p3", heading),
        _span("p4", "销售服务费每日计提，按月支付。"),
    )
    sections = (_section("S01", "第十四部分基金费用", ("p1", "p2", "p3", "p4")),)

    scope = resolve_rule_scopes([_fee_rule()], sections, _inspection(spans),
                                {"G15": ["S01"]})["G15"]

    assert scope.resolution == "resolved"
    assert {"p3", "p4"} <= scope.locations
    assert "p1" not in scope.locations
    assert len(scope.leaf_ids) == 1


# ---------------------------------------------------------------------------
# Multiple definition leaves and ambiguous parent topology
# ---------------------------------------------------------------------------

def test_multiple_definition_leaves_are_all_selected():
    spans = (
        _span("p1", "八、基金份额类别设置"),
        _span("p2", "基金管理人可以变更现有基金份额类别的申购费率、调低赎回费率。"),
        _span("p3", "九、基金份额的类别"),
        _span("p4", "本基金将基金份额分为A类和C类两个类别。在投资者申购A类基金份额时"
                     "收取申购费用，不计提销售服务费；申购C类基金份额时不收取申购费用，"
                     "从本类别基金资产中计提销售服务费。"),
        _span("p5", "十、基金份额分类说明"),
        _span("p6", "本基金将基金份额分为A类和C类两个类别。A类基金份额收取认购费用，"
                     "不计提销售服务费；C类基金份额不收取认购费用，计提销售服务费。"),
    )
    sections = (_section("S01", "第三部分基金的基本情况",
                         ("p1", "p2", "p3", "p4", "p5", "p6")),)

    scope = resolve_rule_scopes([_class_rule("G04")], sections, _inspection(spans),
                                {"G04": ["S01"]})["G04"]

    assert scope.resolution == "resolved"
    assert len(scope.leaf_ids) == 2
    assert {"p4", "p6"} <= scope.locations
    assert "p2" not in scope.locations  # fee-adjustment only, not a definition
    assert any(item == "multi_leaf=2" for item in scope.evidence)


def test_g02_multiple_glossary_definition_leaves_are_all_selected():
    spans = (
        _span("p1", "55、基金份额类别：本基金将基金份额分为A类和C类两个类别。"
                     "A类基金份额收取申购费用，不计提销售服务费；C类基金份额不收取"
                     "申购费用，从本类别基金资产中计提销售服务费。"),
        _span("p2", "56、基金份额类别（补充）：本基金将基金份额分为A类和C类两个类别。"
                     "A类基金份额收取认购费用，不计提销售服务费；C类基金份额不收取"
                     "认购费用，从本类别基金资产中计提销售服务费。"),
        _span("p3", "57、不可抗力：指本基金合同当事人不能预见、不能避免且不能克服的客观事件。"),
    )
    sections = (_section("S01", "第二部分释义", ("p1", "p2", "p3")),)

    scope = resolve_rule_scopes([_rule("G02", "释义-基金份额类别定义", "释义")],
                                sections, _inspection(spans),
                                {"G02": ["S01"]})["G02"]

    assert scope.resolution == "resolved"
    assert len(scope.leaf_ids) == 2
    assert {"p1", "p2"} <= scope.locations
    assert "p3" not in scope.locations


def test_class_candidates_across_parent_sections_keep_the_parent_fallback():
    spans = (
        _span("p1", "八、基金份额类别设置"),
        _span("p2", "基金管理人可以增加新的基金份额类别、调低赎回费率。"),
        _span("p3", "其他事项。"),
        _span("p10", "九、基金份额的类别"),
        _span("p11", "基金管理人可以变更现有基金份额类别、调低赎回费率。"),
    )
    sections = (
        _section("S01", "第三部分基金的基本情况", ("p1", "p2", "p3")),
        _section("S02", "第三部分基金的基本情况（续）", ("p10", "p11")),
    )

    scope = resolve_rule_scopes([_class_rule("G05")], sections, _inspection(spans),
                                {"G05": ["S01", "S02"]})["G05"]

    assert scope.resolution == "section_fallback"
    assert {"p2", "p11"} <= scope.locations
    # The ambiguous topology keeps the mapped parent section instead of
    # arbitrarily choosing one of the two class leaves.
    assert "p3" in scope.locations
    assert any("class_leaves_ambiguous" in item for item in scope.evidence)


# ---------------------------------------------------------------------------
# Explicit class summary copies still require a matching clause identity
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("copy_key", ["份额类别", "基金份额的类别"])
def test_explicit_class_summary_copy_key_matches_only_the_real_copy(copy_key):
    spans = (
        _span("p1", "八、基金份额类别设置"),
        _span("p2", "基金管理人可以增加新的基金份额类别、调低赎回费率。"),
        _span("p10", "二、基金份额的类别", zone="summary"),
        _span("p11", "本基金将基金份额分为A类和C类两个类别。", zone="summary"),
        _span("p12", "三、基金份额持有人大会", zone="summary"),
        _span("p13", "基金份额持有人大会可以调整基金份额类别。", zone="summary"),
    )
    sections = (
        _section("S01", "第三部分基金的基本情况", ("p1", "p2")),
        _section("S02", "第二十三部分基金合同内容摘要",
                 ("p10", "p11", "p12", "p13"), zone="summary"),
    )
    mapping = {"G05": ["S01", "S02"]}
    rules = [_class_rule("G05")]

    default = resolve_rule_scopes(rules, sections, _inspection(spans),
                                  mapping)["G05"]
    assert default.include_summary_copies is False
    assert "p10" not in default.locations

    explicit = resolve_rule_scopes(
        rules, sections, _inspection(spans), mapping,
        include_summary_copies={"G05": True},
        summary_copy_keys={"G05": [copy_key]},
    )["G05"]
    assert explicit.include_summary_copies is True
    assert explicit.zone == "body+summary"
    assert {"p10", "p11"} <= explicit.locations
    assert "p13" not in explicit.locations  # unrelated holders'-meeting leaf
