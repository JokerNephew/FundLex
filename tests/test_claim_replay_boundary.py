"""Artifact claim replay boundary proof (plan §15.3, §24, §49)."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.generation.claim_replay import replay_claims


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{i}", text=text)
                           for i, text in enumerate(texts)]

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


RULES = {"G01": {"rule_id": "G01", "operations": [
    {"op": "append", "new_text": "新授权句", "condition": {"kind": "none"}}]}}


def _edit():
    return {"rule_id": "G01", "location": "p0", "start": 0, "end": 3,
            "replacement": "新授权句", "components": []}


def test_replay_proves_the_edit_reached_the_artifact():
    before = Inspection(["授权句。", "后文。"])
    after = Inspection(["新授权句。", "后文。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is True, replay["failures"]
    assert replay["checked"] == 1


def test_replay_rejects_a_change_outside_the_authorized_span():
    before = Inspection(["授权句。", "后文。"])
    after = Inspection(["新授权句。", "后文被改。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is False
    assert any(item["code"] == "CLAIM_OUTSIDE_SPAN_CHANGED"
               for item in replay["failures"])


def test_replay_rejects_a_change_inside_the_paragraph_but_outside_the_span():
    before = Inspection(["授权句。前文。", "后文。"])
    # The writer changed 前文 as well; the span itself is correct.
    after = Inspection(["新授权句。前文被改。", "后文。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is False
    assert any(item["location"] == "p0" and item["code"] == "CLAIM_OUTSIDE_SPAN_CHANGED"
               for item in replay["failures"])


def test_missing_replacement_is_still_reported_after_boundary_passes():
    before = Inspection(["授权句。"])
    after = Inspection(["授权句。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is False
    assert replay["failures"][0]["code"] == "CLAIM_NO_CHANGE_APPLIED"
