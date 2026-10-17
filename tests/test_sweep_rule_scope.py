"""FL-D109: sweep requirements are scoped to the window's sections, with hard fallbacks.

The final sweep used to give every guide rule to every window, so a window over the
收益分配 section was asked to judge 清算 and 申购费 rules too. The model answered anyway,
and the code discarded the noise afterwards (round 9 recorded ``SWEEP_LOCATION_OUT_OF_SCOPE``
362 times) while the requirements block went out once per window (D09: 10 times).

``_window_rule_scope`` narrows each window to the rules its sections can host. Because the
rule->section mapping is **model-produced and can be wrong**, the narrowing must never turn
a mapping error into a missed obligation. These tests pin both halves: the narrowing, and
the two fallbacks that keep a rule alive when the mapping disagrees with reality.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fundlex.recall_pipeline import (
    _Chunk,
    _sweep_requirements_for,
    _window_rule_scope,
)


@dataclass
class _Section:
    id: str
    locations: tuple[str, ...] = ()


@dataclass
class _Span:
    location: str
    zone: str = "body"


def sections():
    return [_Section("S01", ("p1", "p2")),
            _Section("S02", ("p3", "p4")),
            _Section("S03", ("p5", "p6"))]


def chunk(cid, locations):
    text = "\n".join(f"[{loc}] 正文" for loc in locations)
    return _Chunk(id=cid, locations=tuple(locations), text=text)


def rules():
    return [{"rule_id": rid, "title": f"{rid} 标题", "requirement": "要求",
             "operations": [{"op": "delete", "old_text": "旧文本"}]}
            for rid in ("G01", "G02", "G03")]


def test_scope_assigns_only_the_rules_of_the_window_sections():
    mapping = {"G01": ["S01"], "G02": ["S02"], "G03": ["S03"]}
    # Every section is covered by some window, so no unreachable-rule fallback applies.
    scoped = _window_rule_scope([chunk("C001", ("p1", "p2")), chunk("C002", ("p3", "p4")),
                                 chunk("C003", ("p5", "p6"))],
                                mapping=mapping, sections=sections(), rules=rules(),
                                mandatory=set())
    by_id = {c.id: ids for c, ids in scoped}
    assert by_id["C001"] == {"G01"}
    assert by_id["C002"] == {"G02"}
    assert by_id["C003"] == {"G03"}


def test_mandatory_rule_is_forced_into_its_mapped_window():
    """An unmet obligation is asked about wherever its sections are, mapping aside."""
    mapping = {"G01": ["S01"], "G02": ["S02"], "G03": ["S03"]}
    scoped = _window_rule_scope([chunk("C001", ("p1", "p2")), chunk("C002", ("p3", "p4"))],
                                mapping=mapping, sections=sections(), rules=rules(),
                                mandatory={"G02"})
    by_id = {c.id: ids for c, ids in scoped}
    assert "G02" in by_id["C002"]
    # The mandatory rule is not sprayed into unrelated windows.
    assert "G02" not in by_id["C001"]


def test_rule_no_window_reaches_is_asked_everywhere():
    """A mapping that points at a section no window covers degrades to the old behaviour."""
    mapping = {"G01": ["S01"], "G02": ["S02"], "G03": ["S03"]}
    # Only S01/S02 appear in the windows; S03 is never swept.
    scoped = _window_rule_scope([chunk("C001", ("p1", "p2")), chunk("C002", ("p3", "p4"))],
                                mapping=mapping, sections=sections(), rules=rules(),
                                mandatory=set())
    for _chunk, ids in scoped:
        assert "G03" in ids, "a rule no window can reach must still be asked"


def test_mandatory_rule_with_empty_mapping_is_asked_everywhere():
    """A mandatory rule the mapping never places at all must not vanish."""
    mapping = {"G01": ["S01"], "G02": [], "G03": ["S03"]}
    scoped = _window_rule_scope([chunk("C001", ("p1", "p2")), chunk("C002", ("p5", "p6"))],
                                mapping=mapping, sections=sections(), rules=rules(),
                                mandatory={"G02"})
    for _chunk, ids in scoped:
        assert "G02" in ids


def test_requirements_for_subset_is_smaller_and_contains_only_those_rules():
    full = _sweep_requirements_for(rules(), {"G01", "G02", "G03"})
    narrow = _sweep_requirements_for(rules(), {"G02"})
    assert len(narrow) < len(full)
    assert "G02" in narrow
    assert "G01" not in narrow and "G03" not in narrow
