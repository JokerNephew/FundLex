"""R03: approval-backed T3 binding and paged candidate discovery.

The locator's own word-bag/category check is a candidate fast path.  Once a target
carries a code-verified :class:`~fundlex.semantic_evidence.SemanticApproval`, a real
quote inside the authorized candidate window must bind even when that word bag does
not match.  Window, quote-existence, uniqueness and approval freshness checks still
fail closed.

These tests are fully offline: no model, network or deployment access.
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.docx import ParagraphSpan, TextSegment
from fundlex.recall import Target
from fundlex.semantic_evidence import (ApprovalBook, SemanticApproval,
                                       evidence_from_span)
from fundlex.targeting import (_open_operation_candidates, _open_rule_candidates,
                               locate_unresolved_targets)


class Facts:
    def as_ledger(self):
        return {}


class Inspection:
    def __init__(self, texts, sha: str = "sha-test"):
        self.source_sha256 = sha
        self.paragraphs = tuple(
            ParagraphSpan(location=f"p{index}", zone="body", section_path="",
                          text=text, segments=(TextSegment(0, len(text)),),
                          fingerprint=f"fp{index}")
            for index, text in enumerate(texts))

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


class Gateway:
    max_context_chars = 20000

    def __init__(self, location, quote):
        self.value = {"location": location, "quote": quote,
                      "semantic_role": "fee", "reason": "test"}
        self.calls = 0
        self.context = None

    def call(self, **kwargs):
        self.calls += 1
        self.context = kwargs.get("bounded_context")
        return SimpleNamespace(value=self.value)


# G05's own anchors name ``调低赎回费率``.  The paragraph carries the topic and is a
# valid G05 site, but the model's literal quote below does not contain that operation
# wording, so the historical word-bag anchor rejects it.
RULE = {
    "rule_id": "G05",
    "title": "费率调整",
    "requirement": "调低费率需公告",
    "operations": [{"op": "replace", "old_text": "调低赎回费率",
                    "new_text": "调低销售服务费率",
                    "condition": {"kind": "none"}}],
}
TEXT = "基金管理人可以调整本基金份额类别并调低费率，具体安排见本条款。"
QUOTE = "具体安排见本条款"


def _target(*, approval_id: str = "", quotes=("p0",)) -> Target:
    return Target(target_id="T1", rule_id="G05", location=quotes[0], quote="",
                  state="needs_edit", reason="T3_open_rule",
                  resolution="unresolved", site_candidates=tuple(quotes),
                  operations=("G05:0",), approval_id=approval_id)


def _approval(inspection, *, state: str = "approved", operation_key: str = "G05:0",
              quote: str = TEXT) -> SemanticApproval:
    return SemanticApproval(
        approval_id="AP1", guide_id="guide", guide_sha256="guide-sha",
        rule_id="G05", operation_key=operation_key,
        evidence=(evidence_from_span("AP1:source", inspection, "p0", quote=quote),),
        state=state)


def _locate(inspection, target, gateway, **kwargs):
    return locate_unresolved_targets([target], inspection, {"G05": RULE}, Facts(),
                                     gateway, **kwargs)


def test_approved_exact_quote_binds_even_when_word_bag_misses(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    inspection = Inspection([TEXT, "无关段落。"])
    target = _target(approval_id="AP1")
    approvals = ApprovalBook([_approval(inspection)])
    gateway = Gateway("p0", QUOTE)

    records = _locate(inspection, target, gateway, approvals=approvals)

    assert records[0]["status"] == "bound"
    assert records[0]["anchor_bypassed"] == "anchor_mismatch:quote_anchor_missing"
    assert records[0]["approval_id"] == "AP1"
    assert target.resolution == "resolved"
    assert (target.start, target.end) == (TEXT.index(QUOTE),
                                          TEXT.index(QUOTE) + len(QUOTE))
    assert target.quote == QUOTE


def test_without_approval_a_word_bag_miss_is_still_rejected(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    inspection = Inspection([TEXT])
    target = _target()
    gateway = Gateway("p0", QUOTE)

    records = _locate(inspection, target, gateway)

    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "anchor_mismatch:quote_anchor_missing"
    assert target.resolution == "unresolved"


def test_approval_does_not_accept_a_quote_that_is_not_in_the_location(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    inspection = Inspection([TEXT])
    target = _target(approval_id="AP1")
    approvals = ApprovalBook([_approval(inspection)])
    gateway = Gateway("p0", "本基金不收取任何费用")

    records = _locate(inspection, target, gateway, approvals=approvals)

    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "quote_not_found"
    assert target.resolution == "unresolved"


def test_approval_does_not_widen_the_candidate_window(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    other = "基金管理人可以调整本基金份额类别并调低费率，另行约定。"
    inspection = Inspection([TEXT, other])
    target = _target(approval_id="AP1")
    approvals = ApprovalBook([_approval(inspection)])
    gateway = Gateway("p1", other)

    records = _locate(inspection, target, gateway, approvals=approvals)

    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "location_outside_candidate_window"
    assert target.resolution == "unresolved"


def test_approval_for_a_different_operation_cannot_bypass(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    inspection = Inspection([TEXT])
    target = _target(approval_id="AP1")
    approvals = ApprovalBook([_approval(inspection, operation_key="G05:1")])
    gateway = Gateway("p0", QUOTE)

    records = _locate(inspection, target, gateway, approvals=approvals)

    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "anchor_mismatch:quote_anchor_missing"
    assert records[0]["approval_check"] == "APPROVAL_OPERATION_MISMATCH"
    assert target.resolution == "unresolved"


def test_stale_approval_cannot_bypass_the_anchor_gate(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    inspection = Inspection([TEXT])
    target = _target(approval_id="AP1")
    approvals = ApprovalBook([_approval(inspection)])
    inspection.source_sha256 = "sha-changed-after-approval"
    gateway = Gateway("p0", QUOTE)

    records = _locate(inspection, target, gateway, approvals=approvals)

    assert records[0]["status"] == "rejected"
    assert records[0]["reject_reason"] == "anchor_mismatch:quote_anchor_missing"
    assert records[0]["approval_check"] == "EVIDENCE_SOURCE_MISMATCH"
    assert target.resolution == "unresolved"


def test_candidate_paging_reaches_the_thirteenth_candidate():
    sentence = "销售服务费每日计提，按月支付。"
    inspection = Inspection([sentence] * 20)
    rule = {"rule_id": "X99", "title": "paging",
            "operations": [{"op": "replace", "old_text": sentence,
                            "new_text": "新条款"}]}
    section = SimpleNamespace(id="s1", locations=tuple(f"p{i}" for i in range(20)))
    section_by_id = {"s1": section}

    first = _open_rule_candidates(inspection, rule, ["s1"], section_by_id, Facts())
    assert isinstance(first, list)
    assert len(first) == 12 and first[0] == "p0" and first[-1] == "p11"
    assert first.total == 20 and first.has_more is True
    assert first.remaining == 8 and first.next_cursor == 12

    second = _open_rule_candidates(inspection, rule, ["s1"], section_by_id, Facts(),
                                   cursor=first.next_cursor)
    assert second[0] == "p12"  # the 13th candidate overall
    assert list(second) == [f"p{i}" for i in range(12, 20)]
    assert second.has_more is False and second.remaining == 0

    raised = _open_rule_candidates(inspection, rule, ["s1"], section_by_id, Facts(),
                                   limit=20)
    assert len(raised) == 20 and raised.has_more is False


def test_operation_candidate_paging_reaches_the_thirteenth_candidate():
    sentence = "销售服务费每日计提，按月支付。"
    inspection = Inspection([sentence] * 20)
    rule = {"rule_id": "X99", "title": "paging",
            "operations": [{"op": "replace", "old_text": sentence,
                            "new_text": "新条款"}]}
    section = SimpleNamespace(id="s1", locations=tuple(f"p{i}" for i in range(20)))
    record = SimpleNamespace(spec=SimpleNamespace(operation_index=0,
                                                  operation_id="X99:0"))

    first = _open_operation_candidates(inspection, rule, record, ["s1"],
                                       {"s1": section}, Facts())
    assert len(first) == 12 and first.has_more is True
    assert first.remaining == 8 and first.next_cursor == 12

    second = _open_operation_candidates(inspection, rule, record, ["s1"],
                                        {"s1": section}, Facts(),
                                        cursor=first.next_cursor)
    assert second[0] == "p12"  # the 13th candidate overall
    assert second.has_more is False and second.remaining == 0


def test_locator_context_can_show_a_raised_candidate_page(monkeypatch):
    monkeypatch.setenv("FUNDLEX_TARGET_LOCATOR", "1")
    sentence = "基金管理人可以调整本基金份额类别并调低费率，具体安排见本条款。"
    inspection = Inspection([sentence] * 20)
    target = _target(quotes=tuple(f"p{i}" for i in range(20)))
    gateway = Gateway("p0", "具体安排见本条款")

    _locate(inspection, target, gateway, candidate_limit=20)
    assert gateway.context is not None
    assert "[p19]" in gateway.context

    gateway = Gateway("p0", "具体安排见本条款")
    _locate(inspection, _target(quotes=tuple(f"p{i}" for i in range(20))), gateway)
    assert "[p19]" not in gateway.context
