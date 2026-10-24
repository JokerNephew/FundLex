"""FL-D233: composite geometry is not authority over adjacent class policies."""
import json
from dataclasses import replace
from pathlib import Path

import pytest
from docx import Document

from fundlex.docx import inspect_docx
from fundlex.generation.claim_replay import replay_claims
from fundlex.recall import ClassFact, Target, compact_offsets, plan_edits
from test_recall_core import _facts


HEAD = "本基金 A 类、Y 类基金份额的申购费用由该类基金份额的投资人承担，"
TAIL = "不列入基金财产。"
PROTECTED = "本基金 C 类基金份额、E 类基金份额和 F 类基金份额不收取申购费。 "


def inspection(tmp_path, name, paragraphs):
    path = tmp_path / (name + ".docx")
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    doc.save(path)
    return inspect_docx(path, full=True)


@pytest.mark.parametrize("swallow_tail", [False, True])
def test_g11_composite_preserves_independent_tail_and_replay_rejects_overdelete(
        tmp_path, swallow_tail):
    guide = json.loads((Path(__file__).resolve().parents[1] /
                        "guides/builtin_guide_v1.json").read_text())
    rule = next(rule for rule in guide["groups"] if rule["rule_id"] == "G11")
    source = inspection(tmp_path, "source", [HEAD, TAIL + PROTECTED])
    facts = _facts()
    facts = replace(facts, classes=(*facts.classes, ClassFact(
        name="Y类", subscription_fee=True, service_fee=False, current=True,
        rate=None, quote=HEAD)))
    target = Target("T11", "G11", "p0", HEAD, "needs_edit", "source",
                    resolution="composite", operations=("G11:0",),
                    composite=(f"p0:0:{len(compact_offsets(HEAD)[0])}",
                               f"p1:0:{len(compact_offsets(TAIL + PROTECTED)[0])}"))
    plan = plan_edits({"G11": rule}, [target], source, facts, None, max_compose_calls=0)
    assert not plan["conflicts"]
    assert plan["ledger"][0]["status"] == "planned"
    assert target.composite[-1] == f"p1:0:{len(TAIL)}"
    edits = plan["edits"]
    assert edits[1]["end"] == len(TAIL)
    if swallow_tail:
        edits[1]["end"] = len(TAIL + PROTECTED)
        edits[1]["components"][0]["end"] = len(TAIL + PROTECTED)
        edits[1]["components"][0]["expected_old_text"] = TAIL + PROTECTED
    actual = inspection(tmp_path, "result", [edits[0]["replacement"],
                                             "" if swallow_tail else PROTECTED])
    proof = replay_claims(edits, source, actual, rules_by_id={"G11": rule}, facts=facts,
                          targets_by_id={target.target_id: target.as_dict()})
    if swallow_tail:
        assert not proof["verified"]
        assert any(f["code"] == "CLAIM_OPERATION_SPAN_UNAUTHORIZED" for f in proof["failures"])
    else:
        assert proof["verified"], proof["failures"]
        assert actual.by_location("p1").text == PROTECTED
