"""Conditional appends must not be lost when the model inventory skips them.

Append rules carry no reference anchor, so the reference-anchored survey cannot
find them and the decision rests entirely on the windowed model inventory. When
that judgment says ``not_applicable`` — for example because the contract writes
"直销渠道" where the guide writes "直销机构" — the obligation is dropped and the
appended policy never reaches the document (FL-D060/FL-D090, seen on D07 of the
real dev set).

``append_applicability_targets`` is the deterministic safety net. These tests pin
both directions: it fires when the section exists and the policy is missing, and
it stays silent when the policy is already present or the section is absent.
"""

from fundlex.recall import (
    ClassFact,
    Facts,
    Section,
    append_applicability_targets,
    structure_index,
)

APPEND_RULE = {
    "rule_id": "G01",
    "title": "释义-基金份额类别定义：",
    "section_hint": "释义",
    "requirement": "在释义原条款后增加政策条款。",
    "operations": [{
        "op": "append",
        "condition": {"kind": "none", "value": None},
        "new_text": "投资者通过直销机构申购本基金A类基金份额时，不收取认购/申购费用。",
    }],
    "old_text_variants": [],
}


class _FakeParagraph:
    def __init__(self, location, text):
        self.location = location
        self.text = text
        self.raw = text


class _FakeInspection:
    def __init__(self, paragraphs):
        self.paragraphs = [_FakeParagraph(loc, text) for loc, text in paragraphs]


def _facts(classes=()):
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=tuple(classes), floating_management_fee=False, floating_quote="",
                 floating_basis="", notes="", quotes_verified={}, problems=())


def _section(id_, title, locations):
    return Section(id=id_, title=title, zone="body", locations=tuple(locations),
                   chars=0, preview="")


def test_fires_when_section_exists_and_policy_missing():
    inspection = _FakeInspection([("p1", "第一条 本基金的名称"), ("p2", "第二条 释义的其他内容")])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections)
    assert len(hits) == 1
    assert hits[0].rule_id == "G01"
    assert hits[0].operation == "append"
    # The append anchors at the last paragraph of the named section.
    assert hits[0].locations == ("p2",)


def test_silent_when_policy_already_present():
    inspection = _FakeInspection([
        ("p1", "第二条 释义"),
        ("p2", "投资者通过直销机构申购本基金A类基金份额时，不收取认购/申购费用。"),
    ])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections)
    assert hits == []


def test_silent_when_section_absent():
    inspection = _FakeInspection([("p1", "第一条 本基金的名称"), ("p2", "第三条 其他")])
    sections = [_section("S1", "第一条 本基金的名称", ["p1"]),
                _section("S2", "第三条 其他", ["p2"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections)
    assert hits == []


def test_silent_when_rule_already_has_a_target():
    inspection = _FakeInspection([("p1", "第二条 释义"), ("p2", "第二条 释义的其他内容")])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections,
                                        known=[("G01", "p1")])
    assert hits == []


def test_replace_only_rule_is_untouched():
    rule = {**APPEND_RULE, "operations": [{"op": "replace", "condition": {"kind": "none"},
                                          "old_text": "原条款内容至少八个字", "new_text": "新内容"}]}
    inspection = _FakeInspection([("p1", "第二条 释义"), ("p2", "其他内容")])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [rule], _facts(), sections)
    assert hits == []


def test_service_group_empty_does_not_suppress_the_append():
    """A contract with no service-fee class still gets the unconditional append.

    ``instantiate_slots`` reports SERVICE_GROUP_EMPTY, but the append condition is
    ``none`` so it must still be proposed — this is the D07 shape.
    """
    rule = {**APPEND_RULE, "operations": [{
        "op": "append", "condition": {"kind": "none", "value": None},
        "new_text": "投资者通过直销机构申购本基金A类基金份额时，不收取费用。{{SERVICE_GROUP}}",
    }]}
    inspection = _FakeInspection([("p1", "第二条 释义"), ("p2", "第二条 释义的其他内容")])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [rule], _facts(), sections)
    assert len(hits) == 1
