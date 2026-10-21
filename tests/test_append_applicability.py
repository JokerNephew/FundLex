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

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


def _facts(classes=()):
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=tuple(classes), floating_management_fee=False, floating_quote="",
                 floating_basis="", notes="", quotes_verified={}, problems=())


def _section(id_, title, locations):
    return Section(id=id_, title=title, zone="body", locations=tuple(locations),
                   chars=0, preview="")


def test_fires_when_section_exists_and_policy_missing():
    inspection = _FakeInspection([("p1", "第一条 本基金的名称"), ("p2", "基金份额类别：第二条释义的其他内容")])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections)
    assert len(hits) == 1
    assert hits[0].rule_id == "G01"
    assert hits[0].operation == "append"
    # The append anchors at the rule's own business clause.
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
    inspection = _FakeInspection([("p1", "第二条 释义"), ("p2", "基金份额类别：第二条释义的其他内容")])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections,
                                        known=[("G01", "p2")])
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
    inspection = _FakeInspection([("p1", "第二条 释义"), ("p2", "基金份额类别：第二条释义的其他内容")])
    sections = [_section("S1", "第二条 释义", ["p1", "p2"])]
    hits = append_applicability_targets(inspection, [rule], _facts(), sections)
    assert len(hits) == 1


def test_append_with_missing_service_class_is_not_out_of_scope():
    """The append path drops only the sentence naming the absent class (FL-D090).

    The guide's policy names a C-class service-fee group; a product with A/Y classes
    has none, but the policy still belongs in the document. The append must be planned
    rather than declared out of scope, and the resulting text must read as a complete
    sentence with the class names the product actually has.
    """
    from fundlex.recall import _append_without_missing_group

    policy = ("投资者通过直销机构申购本基金A类基金份额时，不收取认购/申购费用；"
              "通过直销机构申购的C类基金份额，不收取销售服务费。")
    facts = _facts([ClassFact(name="A类基金份额", subscription_fee=True, service_fee=False,
                              current=True, rate=None, quote=""),
                    ClassFact(name="Y类基金份额", subscription_fee=True, service_fee=False,
                              current=True, rate=None, quote="")])
    resolved = _append_without_missing_group(policy, facts)
    assert resolved is not None
    assert "C类基金份额" not in resolved          # the absent class is not mentioned
    assert "A类、Y类基金份额" in resolved          # the real classes are named
    assert resolved.endswith("。")


def test_append_without_missing_group_returns_none_when_subscription_class_absent():
    from fundlex.recall import _append_without_missing_group

    policy = "投资者通过直销机构申购本基金A类基金份额时，不收取费用。"
    assert _append_without_missing_group(policy, _facts()) is None


def test_heading_hint_falls_back_to_section_end():
    """A heading is never used as the append anchor (the clause would land after it)."""
    from fundlex.recall import _looks_like_heading

    assert _looks_like_heading("第二部分  释义")
    assert _looks_like_heading("第十五部分基金费用与税收")
    assert _looks_like_heading("七、基金合同的变更、终止与基金财产的清算")
    assert not _looks_like_heading("不可抗力：指本基金合同当事人不能预见、不能避免且不能克服的客观事件")
    assert not _looks_like_heading("投资者通过直销机构申购本基金A类基金份额时，不收取认购/申购费用。")


def test_hinted_location_wins_over_section_end():
    inspection = _FakeInspection([
        ("p1", "第二部分  释义"),
        ("p2", "基金份额类别：本基金分A类、B类。"),
        ("p3", "不可抗力：客观事件。"),
    ])
    sections = [_section("S1", "第二部分 释义", ["p1", "p2", "p3"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections,
                                        hinted={"G01": "p2"})
    assert hits[0].locations == ("p2",)


def test_heading_hint_is_ignored_in_favour_of_business_anchor():
    inspection = _FakeInspection([
        ("p1", "第二部分  释义"),
        ("p2", "基金份额类别定义。"),
        ("p3", "不可抗力：客观事件。"),
    ])
    sections = [_section("S1", "第二部分 释义", ["p1", "p2", "p3"])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections,
                                        hinted={"G01": "p1"})
    assert hits[0].locations == ("p2",)


def test_override_rules_let_an_absent_target_be_replaced():
    """An inventory "absent" target must not mask the append the pass just located.

    ``_survey_targets_from_hits`` normally skips a hit whose rule already has a target at
    the same location. The append pass names its rules in ``override_rules`` so an
    ``absent`` judgment — the very thing it exists to correct (D09/D13) — cannot suppress
    the discovered clause.
    """
    from fundlex.recall import SurveyHit
    from fundlex.recall_pipeline import _survey_targets_from_hits

    quote = "基金份额类别：本基金分A类、B类。"

    class _Segment:
        start = 0
        end = 10_000

    class _Span:
        location = "p2"
        text = quote
        segments = (_Segment(),)

    class _Doc:
        def by_location(self, location):
            return _Span()

    class _Existing:
        rule_id = "G01"
        location = "p2"
        composite = []
        start = 0
        end = 0

    hit = SurveyHit(rule_id="G01", operation="append", locations=("p2",), quote=quote,
                    start=0, end=0, ratio=1.0, index=1)
    hit.with_parts([("p2", 0, len(quote))])
    rules_by_id = {"G01": APPEND_RULE}

    without = _survey_targets_from_hits([hit], rules_by_id, _Doc(), [_Existing()],
                                        start_index=0)
    assert without[0] == []                     # suppressed by the existing target

    with_override = _survey_targets_from_hits([hit], rules_by_id, _Doc(), [_Existing()],
                                              start_index=0,
                                              override_rules=frozenset({"G01"}))
    assert [t.rule_id for t in with_override[0]] == ["G01"]


def test_existing_policy_in_definition_does_not_cover_summary_copy():
    policy = APPEND_RULE['operations'][0]['new_text']
    inspection = _FakeInspection([
        ('p1', '基金份额类别：A类、C类。' + policy),
        ('p2', '基金合同摘要'), ('p3', '基金份额类别：A类、C类。')])
    sections = [_section('S1', '释义', ['p1']), _section('S2', '摘要释义', ['p2', 'p3'])]
    hits = append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections,
                                        known=[('G01', 'p1')])
    assert [hit.locations for hit in hits] == [('p3',)]
    assert hits[0].operation_keys == ('G01:0',)


def test_no_business_anchor_leaves_append_open():
    inspection = _FakeInspection([('p1', '第二部分 释义'), ('p2', '不可抗力：客观事件。')])
    sections = [_section('S1', '释义', ['p1', 'p2'])]
    assert append_applicability_targets(inspection, [APPEND_RULE], _facts(), sections) == []
