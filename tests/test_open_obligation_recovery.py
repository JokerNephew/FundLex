"""Open-obligation recovery (external review 2026-10-20 P1).

An applicable obligation whose paragraph the inventory missed must not disappear, but a
model also may not search the whole contract.  Code first narrows the candidate region
with deterministic anchors; the primary locator may only choose inside it, and code
re-verifies quote uniqueness, topic/class/keyword anchors before a target is created.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fundlex.docx import ParagraphSpan, TextSegment
from fundlex.recall import Target
from fundlex.targeting import locate_unresolved_targets, targets_for_open_rules


class Facts:
    def as_ledger(self):
        return {}


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [
            ParagraphSpan(location=f"p{index}", zone="body", section_path="",
                          text=text, segments=(TextSegment(0, len(text)),),
                          fingerprint=f"fp{index}")
            for index, text in enumerate(texts)]

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


class Gateway:
    max_context_chars = 20000

    def __init__(self, location, quote):
        self.location = location
        self.quote = quote
        self.calls = 0
        self.context = None

    def call(self, **kwargs):
        self.calls += 1
        self.context = kwargs.get("bounded_context")
        return SimpleNamespace(value={"location": self.location, "quote": self.quote,
                                      "semantic_role": "fee", "reason": "test"})


RULE = {
    "rule_id": "G05",
    "title": "费率调整",
    "requirement": "调低费率需公告",
    "operations": [{"op": "replace", "old_text": "调低赎回费率",
                    "new_text": "调低销售服务费率", "condition": {"kind": "none"}}],
    "old_text_variants": [],
}


def _obligations():
    record = SimpleNamespace(spec=SimpleNamespace(rule_id="G05"),
                             applicability=SimpleNamespace(status="TRUE"))
    return SimpleNamespace(records=[record])


def _sections(*locations):
    return [SimpleNamespace(id="s1", locations=tuple(locations))]


def _mapping():
    return {"G05": ["s1"]}


def test_no_deterministic_candidate_means_no_model_call(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    inspection = Inspection(["本基金由基金管理人管理。"])
    gateway = Gateway("p0", "本基金由基金管理人管理。")
    created = targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(), inspection,
                                     _mapping(), _sections("p0"))
    assert created == []
    assert gateway.calls == 0


def test_satisfied_target_condition_status_is_available_before_auto_branch(monkeypatch):
    """A satisfied target must be audited without triggering local-import scoping."""
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    satisfied = Target(
        target_id="T-satisfied", rule_id="G05", location="p0", quote="",
        state="satisfied", reason="inventory", out_of_scope=False,
        operations=("G05:0",), resolution="resolved")
    inspection = Inspection(["基金管理人可以调整基金份额类别，调低赎回费率。"])
    assert targets_for_open_rules(
        _obligations(), [satisfied], {"G05": RULE}, Facts(), inspection,
        _mapping(), _sections("p0")) == []


def test_g12_open_candidates_reject_nav_fee_and_rate_sibling(monkeypatch):
    import json
    from pathlib import Path
    from fundlex.obligations import compile_obligations, apply_facts
    from test_recall_core import _facts
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    rule = next(r for r in json.loads((Path(__file__).resolve().parents[1] /
        "guides/builtin_guide_v1.json").read_text())["groups"] if r["rule_id"] == "G12")
    facts = _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    source = Inspection([
        "赎回金额为有效赎回份额乘以当日基金份额净值并扣除相应的费用。",
        "本基金的赎回费率由基金管理人决定，具体见招募说明书的规定。",
    ])
    created = targets_for_open_rules(ledger, [], {"G12": rule}, facts, source,
                                    {"G12": ["s1"]}, _sections("p0", "p1"))
    assert created == []


def test_valid_locator_quote_inside_code_candidates_creates_target(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    text = "基金管理人可以调整基金份额类别，调低赎回费率。"
    inspection = Inspection([text, "其他条款。"])
    gateway = Gateway("p0", text)
    created = targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(), inspection,
                                     _mapping(), _sections("p0", "p1"))
    assert len(created) == 1 and created[0].site_candidates == ("p0",)
    targets = list(created)
    records = locate_unresolved_targets(targets, inspection, {"G05": RULE}, Facts(), gateway)
    assert records[0]["status"] == "bound"
    assert targets[0].resolution == "resolved"
    assert (targets[0].start, targets[0].end) == (0, len(text))


def test_locator_outside_candidate_region_is_rejected(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    text = "基金管理人可以调整基金份额类别，调低赎回费率。"
    inspection = Inspection([text, "另一个段落。"])
    gateway = Gateway("p1", "另一个段落。")
    targets = list(targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(),
                                          inspection, _mapping(), _sections("p0")))
    records = locate_unresolved_targets(targets, inspection, {"G05": RULE}, Facts(), gateway)
    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "location_outside_candidate_window"
    assert targets[0].resolution == "unresolved"


def test_locator_quote_without_anchor_evidence_is_rejected():
    # A manually created candidate must still pass the code anchor verification: this
    # paragraph does not carry the rule topic, so a quote inside it cannot bind G05.
    inspection = Inspection(["基金管理人可以调整其他事项。"])
    target = Target(target_id="T3001", rule_id="G05", location="p0", quote="",
                    state="needs_edit", reason="T3_open_rule", resolution="unresolved",
                    site_candidates=("p0",))
    gateway = Gateway("p0", "基金管理人可以调整其他事项。")
    records = locate_unresolved_targets([target], inspection, {"G05": RULE}, Facts(), gateway)
    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"].startswith("anchor_mismatch:")
    assert target.resolution == "unresolved"


def test_duplicate_summary_copy_is_created_for_identical_clause(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    text = "基金管理人可以调整基金份额类别，调低赎回费率。"
    inspection = Inspection([text, text, "其他条款。"])
    gateway = Gateway("p1", text)
    targets = list(targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(),
                                          inspection, _mapping(), _sections("p0", "p1")))
    records = locate_unresolved_targets(targets, inspection, {"G05": RULE}, Facts(), gateway)
    assert records[0]["status"] == "bound"
    assert records[0].get("duplicates") == 1
    assert len(targets) == 2
    assert targets[1].location == "p0"
    assert targets[1].quote == text
    assert targets[1].resolution == "resolved"


def test_default_mode_is_auto_and_anchored_rule_creates_target(monkeypatch):
    monkeypatch.delenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", raising=False)
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    text = "基金管理人可以调整基金份额类别，调低赎回费率。"
    inspection = Inspection([text])
    created = targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(), inspection,
                                     _mapping(), _sections("p0"))
    assert len(created) == 1
    assert created[0].site_candidates == ("p0",)


def test_disabled_flag_creates_nothing(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "0")
    text = "基金管理人可以调整基金份额类别，调低赎回费率。"
    inspection = Inspection([text])
    assert targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(), inspection,
                                  _mapping(), _sections("p0")) == []


def test_locator_context_excludes_non_candidate_paragraphs(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    text = "基金管理人可以调整基金份额类别，调低赎回费率。"
    inspection = Inspection([text, "不应被模型看到的无关段落。"])
    gateway = Gateway("p0", text)
    targets = list(targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(),
                                          inspection, _mapping(), _sections("p0")))
    locate_unresolved_targets(targets, inspection, {"G05": RULE}, Facts(), gateway)
    assert gateway.context is not None
    assert "[p0]" in gateway.context
    assert "[p1]" not in gateway.context


def test_bare_topic_quote_inside_anchored_paragraph_is_rejected(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto")
    text = "基金管理人可以调整基金份额类别，调低赎回费率。"
    inspection = Inspection([text])
    gateway = Gateway("p0", "基金管理人可以")
    targets = list(targets_for_open_rules(_obligations(), [], {"G05": RULE}, Facts(),
                                          inspection, _mapping(), _sections("p0")))
    records = locate_unresolved_targets(targets, inspection, {"G05": RULE}, Facts(), gateway)
    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "anchor_mismatch:quote_anchor_missing"
    assert targets[0].resolution == "unresolved"
