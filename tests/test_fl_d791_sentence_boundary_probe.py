"""FL-D791: terminator-anchored deterministic deletes survive a truncated survey span.

The model survey occasionally stops one character before a sentence terminator
(B12 loop-4 bound G13 as 76..120 where loop-3 bound 76..121 including "。").
Every terminator-anchored deterministic matcher then misses and the edit degrades
to stochastic compose, looping on identical content-check rejections (11 rounds →
honest incomplete where loop-3 deterministically composed and completed).

The plan-stage sentence-boundary probe extends the *probe* slice by a single
adjacent terminator so the deterministic delete consumes the whole sentence.  The
audited target identity and the compose fallbacks keep the original slice.
"""
from __future__ import annotations

import json
from pathlib import Path

from fundlex import recall as R

GUIDE = json.loads((Path(__file__).resolve().parents[1]
                    / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
RULES = {rule["rule_id"]: rule for rule in GUIDE["groups"]}

# Real B12 p244 source paragraph (public contract text), the loop-4 site.
P244 = ("5、赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
        "赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示；"
        "对于持续持有期少于7日的投资者收取不低于1.5%的赎回费，并将上述赎回费全额计入基金财产。")
EXPECTED = ("5、赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
            "赎回费用全额计入基金财产。")


class _Segment:
    def __init__(self, start, end):
        self.start = start
        self.end = end


class _Span:
    def __init__(self, location, text):
        self.location = location
        self.text = text
        self.raw = text
        self.safe_text = text
        self.zone = "body"
        self.logical_zone = "body"
        self.section_path = "基金费用与税收"
        self.segments = (_Segment(0, len(text)),)


class _Inspection:
    source_sha256 = "fixture"

    def __init__(self, text):
        self.paragraphs = [_Span("p244", text)]

    def by_location(self, location):
        return self.paragraphs[0]


def _facts():
    return R.Facts(fund_type="股票型", fund_type_quote="", fund_type_basis="", classes=(),
                   floating_management_fee=False, floating_quote="", floating_basis="",
                   notes="", quotes_verified=False, problems=())


class _ExplodingGateway:
    """Any compose call is a test failure: the deterministic path must suffice."""

    def __getattr__(self, name):
        raise AssertionError(f"model gateway called: {name}")


def _g12_target_wide():
    # Loop-4 shape: G12 span covers the whole clause including the G13 sentence.
    return R.Target(target_id="T011", rule_id="G12", location="p244", quote=P244[2:121],
                    state="needs_edit", reason="x", start=2, end=121,
                    resolution="resolved", segment_ok=True, operations=("G12:0",))


def _g13_target_truncated():
    # Loop-4 shape: the survey stopped one character before the "。".
    return R.Target(target_id="T012", rule_id="G13", location="p244",
                    quote=P244[76:120], state="needs_edit", reason="x", start=76, end=120,
                    resolution="resolved", segment_ok=True, operations=("G13:0",))


def _plan(rule_id, target, inspection, gateway=None):
    budget = [10]
    edit = R._plan_target_inner(RULES[rule_id], target, inspection, _facts(),
                                gateway, compose_budget=budget)
    assert budget == [10], "deterministic planning must not spend compose budget"
    return edit


def test_truncated_g13_span_plans_deterministic_short_holding_delete():
    inspection = _Inspection(P244)
    edit = _plan("G13", _g13_target_truncated(), inspection, _ExplodingGateway())
    assert edit.content_source == "short_holding_delete"
    assert (edit.start, edit.end) == (76, 121)  # probe consumed the "。"
    assert edit.replacement == ""
    assert edit.evidence["deleted_quote"].endswith("基金财产。")


def test_loop4_shapes_compose_to_the_loop3_atomic_paragraph():
    inspection = _Inspection(P244)
    edit_g12 = _plan("G12", _g12_target_wide(), inspection, _ExplodingGateway())
    edit_g13 = _plan("G13", _g13_target_truncated(), inspection, _ExplodingGateway())
    assert edit_g12.content_source == "variant_replace"
    out = R._atomic_paragraph_edits([edit_g12, edit_g13], inspection)
    assert len(out) == 1
    atomic = out[0]
    assert atomic.content_source == "atomic_paragraph"
    assert atomic.replacement == EXPECTED
    # No doubled sentence terminator at the joint boundary (the loop-4 defect).
    assert "。。" not in atomic.replacement


def test_loop3_shapes_still_compose_identically():
    inspection = _Inspection(P244)
    t_g12 = R.Target(target_id="T010", rule_id="G12", location="p244", quote=P244[2:76],
                     state="needs_edit", reason="x", start=2, end=76,
                     resolution="resolved", segment_ok=True, operations=("G12:0",))
    t_g13 = R.Target(target_id="T011", rule_id="G13", location="p244", quote=P244[76:121],
                     state="needs_edit", reason="x", start=76, end=121,
                     resolution="resolved", segment_ok=True, operations=("G13:0",))
    out = R._atomic_paragraph_edits(
        [_plan("G12", t_g12, inspection, _ExplodingGateway()),
         _plan("G13", t_g13, inspection, _ExplodingGateway())], inspection)
    assert out[0].replacement == EXPECTED


def test_probe_does_not_extend_into_mid_sentence_text():
    # A span whose next character is NOT a terminator must stay unchanged and the
    # delete must fail closed instead of borrowing authorization.
    chopped = P244[:100]  # sentence continues after the span
    target = R.Target(target_id="T012", rule_id="G13", location="p244", quote=P244[76:100],
                      state="needs_edit", reason="x", start=76, end=100,
                      resolution="resolved", segment_ok=True, operations=("G13:0",))
    try:
        edit = _plan("G13", target, _Inspection(chopped))
    except Exception:
        return  # fail-closed planner exception is the honest outcome here
    assert edit.content_source != "short_holding_delete"


def test_approved_delete_probe_consumes_the_adjacent_terminator():
    # Generic (non-G13) deterministic delete path: the approval-owned span must not
    # lose its complete-clause status just because the survey omitted "。".
    rule = {"rule_id": "G99",
            "requirement": "删除短持有期赎回费句。",
            "operations": [{"op": "delete", "condition": {"kind": "none", "value": None},
                            "old_text": "对于持续持有期少于7日的投资者收取不低于1.5%的赎回费，"
                                        "并将上述赎回费全额计入基金财产。"}],
            "old_text_variants": []}

    class _Allow:
        ok = True

    class _Approvals:
        def allows(self, target, inspection):
            return _Allow()

    sentence = "对于持续持有期少于7日的投资者收取不低于1.5%的赎回费，并将上述赎回费全额计入基金财产。"
    text = "总则。" + sentence
    inspection = _Inspection(text)
    target = R.Target(target_id="T001", rule_id="G99", location="p244",
                      quote=text[3:3 + len(sentence) - 1], state="needs_edit", reason="x",
                      start=3, end=3 + len(sentence) - 1, resolution="resolved",
                      segment_ok=True, operations=("G99:0",), approval_id="AP:x")
    edit = R._plan_target_inner(rule, target, inspection, _facts(), _ExplodingGateway(),
                                compose_budget=[10], approvals=_Approvals())
    assert edit is not None
    assert edit.content_source == "approved_span_delete"
    assert edit.replacement == ""
    assert text[edit.end - 1] == "。"  # the terminator was consumed


def test_atomic_record_passes_content_check_in_pipeline_shape():
    inspection = _Inspection(P244)
    edit_g12 = _plan("G12", _g12_target_wide(), inspection, _ExplodingGateway())
    edit_g13 = _plan("G13", _g13_target_truncated(), inspection, _ExplodingGateway())
    atomic = R._atomic_paragraph_edits([edit_g12, edit_g13], inspection)[0]
    record = atomic.as_dict()
    # The pipeline serialises the composed parts as a top-level key (loop-3 record).
    record["components"] = record["evidence"]["atomic_components"]
    check = R.content_check_factory([record], inspection)
    span = inspection.by_location(record["location"])
    docx_edit = {**record, "source_sha256": inspection.source_sha256,
                 "expected_old_text": span.text[record["start"]:record["end"]]}
    assert check(docx_edit) is True
