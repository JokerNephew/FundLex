"""Offline tests for deterministic rule scopes resolved to leaf subsections.

No model calls and no network access.  The D06 and 景宁 contracts are real
repository fixtures; tiny fake inspections cover policies that need a structure
the fixtures do not contain.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from fundlex.docx import inspect_docx
from fundlex.recall import structure_index
from fundlex.rule_scope import (
    build_leaf_sections,
    resolve_rule_scopes,
    scope_locations,
    scope_locations_for_window,
)

ROOT = Path(__file__).resolve().parents[1]
D06 = (ROOT / "funds_word"
       / "广发创业板交易型开放式指数证券投资基金发起式联接基金基金合同_20250319.docx")
JINGNING = (ROOT / "funds_word" / "基金合同第一批"
            / "广发景宁纯债债券型证券投资基金基金合同.docx")
QDII = (ROOT / "funds_word" / "基金合同第一批"
        / "广发全球稳健配置混合型证券投资基金（QDII）基金合同.docx")


@pytest.fixture(scope="module")
def d06():
    assert D06.exists(), D06
    inspection = inspect_docx(D06)
    return inspection, structure_index(inspection)


@pytest.fixture(scope="module")
def jingning():
    assert JINGNING.exists(), JINGNING
    inspection = inspect_docx(JINGNING)
    return inspection, structure_index(inspection)


@pytest.fixture(scope="module")
def qdii():
    assert QDII.exists(), QDII
    inspection = inspect_docx(QDII)
    return inspection, structure_index(inspection)


def _rule(rule_id: str, title: str = "", section_hint: str = "") -> dict:
    return {"rule_id": rule_id, "title": title, "section_hint": section_hint}


def _locations(scope) -> list[str]:
    return sorted(scope.locations, key=lambda value: int(value[1:]) if value[1:].isdigit() else 0)


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


# ---------------------------------------------------------------------------
# D06: G06 / G15-G17 / G18 / G19-G22 / G07
# ---------------------------------------------------------------------------

def test_d06_g06_scope_is_the_class_clause_only(d06):
    inspection, sections = d06
    scopes = resolve_rule_scopes(
        [_rule("G06", "基金的基本情况-份额类别设置")],
        sections, inspection, {"G06": ["S04"]},
    )
    scope = scopes["G06"]

    assert scope.resolution == "resolved"
    assert scope.zone == "body"
    assert {f"p{number}" for number in range(130, 138)} <= scope.locations
    assert "p280" not in scope.locations
    assert scope.leaf_ids and all(leaf_id.startswith("S04:L") for leaf_id in scope.leaf_ids)
    assert scope.contains("p131") and not scope.contains("p280")


def test_d06_g06_ignores_near_keyword_conversion_paragraph_in_purchase_chapter(d06):
    """p280 mentions 份额类别 but is a 基金转换 clause and must stay out."""

    inspection, sections = d06
    # Even if the scope model maps the purchase chapter, the G06 policy only
    # reads the mapped 基本情况 leaf.
    scopes = resolve_rule_scopes(
        [_rule("G06", "基金的基本情况-份额类别设置")],
        sections, inspection, {"G06": ["S04", "S07"]},
    )
    scope = scopes["G06"]

    assert scope.resolution == "resolved"
    assert "p280" not in scope.locations
    assert "p277" not in scope.locations  # 十一、基金转换 heading
    assert "p279" not in scope.locations
    assert {f"p{number}" for number in range(130, 138)} <= scope.locations


def test_d06_g15_g16_g17_default_body_only_excludes_summary_fee_copies(d06):
    inspection, sections = d06
    rules = [_rule(rule_id, "基金费用与税收-3、基金销售服务费")
             for rule_id in ("G15", "G16", "G17")]
    mapping = {rule_id: ["S16", "S28"] for rule_id in ("G15", "G16", "G17")}
    scopes = resolve_rule_scopes(rules, sections, inspection, mapping)

    summary_copies = {f"p{number}" for number in range(1286, 1290)}
    for rule_id in ("G15", "G16", "G17"):
        scope = scopes[rule_id]
        assert scope.resolution == "resolved"
        assert scope.include_summary_copies is False
        assert scope.zone == "body"
        assert {f"p{number}" for number in range(807, 811)} <= scope.locations
        assert not (scope.locations & summary_copies)
        # The fee-types list mentions 销售服务费 but is not the fee clause site.
        assert "p768" not in scope.locations


def test_qdii_g15_g16_g17_resolve_class_prefixed_fee_heading(qdii):
    """QDII titles the fee clause ``3、C类基金份额的销售服务费``.

    The class prefix must still identify the sales-service-fee leaf; the body
    payment/usage paragraphs p969-p971 belong to it, while the summary copy
    p1151 stays excluded by the default policy.
    """
    inspection, sections = qdii
    rules = [_rule(rule_id, "基金费用与税收-3、基金销售服务费")
             for rule_id in ("G15", "G16", "G17")]
    mapping = {rule_id: ["S17", "S26"] for rule_id in ("G15", "G16", "G17")}
    scopes = resolve_rule_scopes(rules, sections, inspection, mapping)

    for rule_id in ("G15", "G16", "G17"):
        scope = scopes[rule_id]
        assert scope.resolution == "resolved"
        assert scope.leaf_ids == frozenset({"S17:L04"})
        assert {"p969", "p970", "p971"} <= scope.locations
        assert "p1151" not in scope.locations
        assert scope.include_summary_copies is False


def test_d06_g15_summary_copy_requires_both_explicit_flag_and_copy_key(d06):
    inspection, sections = d06
    rules = [_rule("G15", "基金费用与税收-3、基金销售服务费")]
    mapping = {"G15": ["S16", "S28"]}

    default = resolve_rule_scopes(rules, sections, inspection, mapping)["G15"]
    assert default.include_summary_copies is False
    assert "p1286" not in default.locations and "p1289" not in default.locations

    flag_only = resolve_rule_scopes(
        rules, sections, inspection, mapping,
        include_summary_copies={"G15": True},
    )["G15"]
    assert flag_only.include_summary_copies is False
    assert "p1286" not in flag_only.locations

    explicit = resolve_rule_scopes(
        rules, sections, inspection, mapping,
        include_summary_copies={"G15": True},
        summary_copy_keys={"G15": ["销售服务费"]},
    )["G15"]
    assert explicit.include_summary_copies is True
    assert explicit.zone == "body+summary"
    assert {f"p{number}" for number in range(1286, 1290)} <= explicit.locations
    assert {f"p{number}" for number in range(807, 811)} <= explicit.locations


def test_d06_g18_income_principle_includes_copy_key_matched_summary(d06):
    inspection, sections = d06
    scopes = resolve_rule_scopes(
        [_rule("G18", "第十六部分基金的收益与分配-基金收益分配原则")],
        sections, inspection, {"G18": ["S17", "S28"]},
    )
    scope = scopes["G18"]

    assert scope.resolution == "resolved"
    assert scope.include_summary_copies is True
    assert scope.zone == "body+summary"
    assert "p831" in scope.locations
    assert "p1245" in scope.locations
    # Non-principle income leaves are not part of G18.
    assert "p825" not in scope.locations
    assert "p1248" not in scope.locations


def test_d06_g19_to_g22_liquidation_residual_includes_copy_key_matched_summary(d06):
    inspection, sections = d06
    rule_ids = ("G19", "G20", "G21", "G22")
    rules = [_rule(rule_id, "基金财产的清算-基金财产清算剩余资产的分配")
             for rule_id in rule_ids]
    mapping = {rule_id: ["S20", "S29"] for rule_id in rule_ids}
    scopes = resolve_rule_scopes(rules, sections, inspection, mapping)

    for rule_id in rule_ids:
        scope = scopes[rule_id]
        assert scope.resolution == "resolved"
        assert scope.include_summary_copies is True
        assert "p987" in scope.locations
        assert "p1359" in scope.locations
        assert "p984" not in scope.locations   # 清算费用
        assert "p1356" not in scope.locations
        assert "p988" not in scope.locations   # 清算公告
        assert "p1360" not in scope.locations


def test_d06_g07_purchase_price_fee_leaf_is_narrowed(d06):
    inspection, sections = d06
    scopes = resolve_rule_scopes(
        [_rule("G07", "基金份额的申购与赎回-申购和赎回的价格、费用及其用途")],
        sections, inspection, {"G07": ["S07"]},
    )
    scope = scopes["G07"]

    assert scope.resolution == "resolved"
    assert "p224" in scope.locations
    assert "p233" in scope.locations
    assert "p199" not in scope.locations  # 三、申购与赎回的原则
    assert "p234" not in scope.locations  # 七、拒绝或暂停申购


def test_d06_g01_g02_use_only_the_glossary_class_definition_paragraph(d06):
    inspection, sections = d06
    scopes = resolve_rule_scopes(
        [_rule("G01", "释义-基金份额类别定义", "释义"),
         _rule("G02", "释义-基金份额类别定义", "释义")],
        sections, inspection, {"G01": ["S03"], "G02": ["S03"]},
    )

    for rule_id in ("G01", "G02"):
        scope = scopes[rule_id]
        assert scope.resolution == "resolved"
        assert "p98" in scope.locations
        assert "p130" not in scope.locations  # basics copy is not the glossary site
        assert len(scope.locations) == 1


# ---------------------------------------------------------------------------
# 景宁 G04: complete basics definition vs fee adjustment vs glossary
# ---------------------------------------------------------------------------

def test_jingning_g04_prefers_complete_basics_definition_over_fee_clause_and_glossary(jingning):
    """G04 uses p150-p156; p148 is only a fee-adjustment clause and p120 is a copy."""

    inspection, sections = jingning
    scopes = resolve_rule_scopes(
        [_rule("G04", "基金的基本情况-份额类别设置", "基金的基本情况")],
        sections, inspection, {"G04": ["S05"]},
    )
    scope = scopes["G04"]

    assert scope.resolution == "resolved"
    assert "p148" not in scope.locations
    assert "p151" in scope.locations
    assert "p120" not in scope.locations  # complete basics definition exists
    assert scope.include_summary_copies is False


def test_jingning_g03_uses_definition_while_g05_g06_cover_all_class_leaves(jingning):
    """G03 appends after the class definition; G05/G06 inspect both class leaves.

    G05's fee-adjustment/redemption-filing clause is repeated in the 设置 leaf
    (p148) and the 类别 leaf (p155).  Both are legal body sites in the same
    basics chapter, so selecting only the first leaf loses p155.  G06 stays
    bounded to those class leaves and can never reach p280.
    """

    inspection, sections = jingning
    scopes = resolve_rule_scopes(
        [_rule(rule_id, "基金的基本情况-份额类别设置", "基金的基本情况")
         for rule_id in ("G03", "G05", "G06")],
        sections, inspection, {rule_id: ["S05"] for rule_id in ("G03", "G05", "G06")},
    )

    assert scopes["G03"].resolution == "resolved"
    assert "p151" in scopes["G03"].locations
    assert "p148" not in scopes["G03"].locations
    assert scopes["G03"].leaf_ids == frozenset({"S05:L10"})
    for rule_id in ("G05", "G06"):
        scope = scopes[rule_id]
        assert scope.resolution == "resolved"
        assert scope.leaf_ids == frozenset({"S05:L09", "S05:L10"})
        assert "p148" in scope.locations
        assert "p155" in scope.locations
        # p151 belongs to the same 类别 leaf as p155; the leaf, not the
        # paragraph, is the physical boundary.
        assert "p151" in scope.locations
        assert "p120" not in scope.locations       # 释义 definition copy
        assert "p142" not in scope.locations       # 认购费率 under another leaf
        assert "p778" not in scope.locations       # 费用调整 chapter
        assert scope.include_summary_copies is False


def test_g04_adds_glossary_definition_when_basics_has_only_the_fee_clause():
    spans = (
        _span("p1", "八、基金份额类别设置"),
        _span("p2", "在符合法律法规且不损害已有基金份额持有人权益的情况下，"
                     "基金管理人可以增加新的基金份额类别、变更现有基金份额类别的申购费率。"),
        _span("p3", "九、其他事项"),
        _span("p4", "其他内容。"),
        _span("p10", "55、基金份额类别：本基金将基金份额分为A类和C类不同的类别。"
                      "在投资者申购基金份额时收取申购费用而不计提销售服务费的，称为A类基金份额；"
                      "在投资者申购基金份额时不收取申购费用而是从本类别基金资产中计提销售服务费的，"
                      "称为C类基金份额。"),
        _span("p11", "56、规定媒介：指符合中国证监会规定条件的媒介。"),
    )
    inspection = _inspection(spans)
    sections = (
        _section("S01", "第三部分基金的基本情况", ("p1", "p2", "p3", "p4")),
        _section("S02", "第二部分释义", ("p10", "p11")),
    )
    scope = resolve_rule_scopes(
        [_rule("G04", "基金的基本情况-份额类别设置", "基金的基本情况")],
        sections, inspection, {"G04": ["S01"]},
    )["G04"]

    assert scope.resolution == "resolved"
    assert "p10" in scope.locations
    assert "p2" not in scope.locations
    assert "p1" not in scope.locations
    assert any("glossary_definition_added" in item for item in scope.evidence)


def test_g04_unresolved_without_any_class_definition_leaf():
    spans = (
        _span("p1", "八、基金份额类别设置"),
        _span("p2", "基金管理人可以增加新的基金份额类别、变更现有基金份额类别的申购费率。"),
        _span("p3", "九、其他事项"),
    )
    sections = (_section("S01", "第三部分基金的基本情况", ("p1", "p2", "p3")),)
    scope = resolve_rule_scopes(
        [_rule("G04", "基金的基本情况-份额类别设置", "基金的基本情况")],
        sections, _inspection(spans), {"G04": ["S01"]},
    )["G04"]

    assert scope.resolution == "unresolved"
    assert scope.locations == frozenset()
    assert scope.leaf_ids == frozenset()


def test_g06_exact_sentence_fallback_stays_inside_basics():
    spans = (
        _span("p1", "八、基金合同当事人的权利"),
        _span("p2", "不同基金份额类别之间不得互相转换。"),
        _span("p3", "九、其他事项"),
        _span("p10", "十一、基金转换"),
        _span("p11", "不同基金份额类别之间不得互相转换。"),
    )
    sections = (
        _section("S01", "第三部分基金的基本情况", ("p1", "p2", "p3")),
        _section("S02", "第六部分基金份额的申购与赎回", ("p10", "p11")),
    )
    scope = resolve_rule_scopes(
        [_rule("G06", "基金的基本情况-份额类别设置")],
        sections, _inspection(spans), {"G06": ["S01", "S02"]},
    )["G06"]

    assert scope.resolution == "fallback_exact"
    assert scope.locations == frozenset({"p2"})
    assert "p11" not in scope.locations


# ---------------------------------------------------------------------------
# Leaf identity and projection helpers
# ---------------------------------------------------------------------------

def test_leaf_sections_assign_each_paragraph_once_and_link_summary_copies(d06):
    inspection, sections = d06
    leaves = build_leaf_sections(inspection, sections)
    ids = [leaf.id for leaf in leaves]

    assert len(ids) == len(set(ids))
    for leaf in leaves:
        assert leaf.id.startswith(f"{leaf.parent_section_id}:L")
        assert leaf.parent_section_id
    assigned = [location for leaf in leaves for location in leaf.locations]
    readable = [span.location for span in inspection.paragraphs
                if (span.logical_zone or span.zone) in {"body", "summary"}]
    assert sorted(assigned) == sorted(readable)
    assert len(assigned) == len(set(assigned))

    income_summary = next(leaf for leaf in leaves
                          if leaf.zone == "summary" and "p1245" in leaf.locations)
    assert income_summary.copy_key == "收益分配"
    assert income_summary.summary_of
    body_income = next(leaf for leaf in leaves if leaf.id == income_summary.summary_of)
    assert body_income.zone == "body" and "p831" in body_income.locations

    fee_summary = next(leaf for leaf in leaves
                       if leaf.zone == "summary" and "p1286" in leaf.locations)
    assert fee_summary.copy_key == "销售服务费"
    body_fee = next(leaf for leaf in leaves if leaf.id == fee_summary.summary_of)
    assert body_fee.zone == "body" and "p807" in body_fee.locations


def test_g01_unresolved_when_glossary_section_is_not_mapped(d06):
    inspection, sections = d06
    scope = resolve_rule_scopes(
        [_rule("G01", "释义-基金份额类别定义", "释义")],
        sections, inspection, {"G01": ["S04"]},
    )["G01"]

    assert scope.resolution == "unresolved"
    assert scope.locations == frozenset()


def test_default_rule_falls_back_to_mapped_section_leaves_only():
    spans = (
        _span("p1", "第一部分其他事项"),
        _span("p2", "本部分只包含本规则可以查看的普通段落。"),
        _span("p10", "第十部分无关章节"),
        _span("p11", "无关内容。"),
    )
    sections = (
        _section("S01", "第九部分其他事项", ("p1", "p2")),
        _section("S02", "第十部分无关章节", ("p10", "p11")),
    )
    scope = resolve_rule_scopes(
        [_rule("G99", "模糊规则", "模糊提示")],
        sections, _inspection(spans), {"G99": ["S01"]},
    )["G99"]

    assert scope.resolution == "section_fallback"
    assert scope.locations == frozenset({"p1", "p2"})
    assert "p10" not in scope.locations and "p11" not in scope.locations
    assert any(item.startswith("base_sections=") for item in scope.evidence)


def test_scope_projection_helpers(d06):
    inspection, sections = d06
    scopes = resolve_rule_scopes(
        [_rule("G06", "基金的基本情况-份额类别设置"),
         _rule("G15", "基金费用与税收-3、基金销售服务费")],
        sections, inspection, {"G06": ["S04"], "G15": ["S16"]},
    )

    assert scope_locations(scopes)["G06"] == scopes["G06"].locations
    window = SimpleNamespace(locations=("p130", "p807", "p1286"))
    projected = scope_locations_for_window(scopes, window)
    assert projected["G06"] == frozenset({"p130"})
    assert projected["G15"] == frozenset({"p807"})


def test_unresolved_rule_does_not_fall_back_to_mapped_chapter(d06):
    inspection, sections = d06
    scope = resolve_rule_scopes(
        [_rule("G15", "基金费用与税收-3、基金销售服务费")],
        sections, inspection, {"G15": ["S04"]},
    )["G15"]

    assert scope.resolution == "unresolved"
    assert scope.locations == frozenset()
    assert scope.contains("p130") is False
