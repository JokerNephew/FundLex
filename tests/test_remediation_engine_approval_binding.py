"""FL-D457: a semantic approval is bound to one physical target and version.

The old audit probe approved p0, then moved the target (same quote) to p1 and the
planner still produced an ``approved_span_delete``.  These tests keep the legal
approval working and reject every rebinding axis: rule, operation, location,
offsets, occurrence, guide/condition version and empty operations.
"""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from fundlex.recall import Facts, RecallError, Target, plan_target
from fundlex.semantic_evidence import (ApprovalBook, approval_from_target,
                                       condition_fingerprint, guide_fingerprint)


class Inspection:
    def __init__(self, texts, sha: str = "source"):
        self.paragraphs = tuple(
            SimpleNamespace(location=f"p{i}", text=text, zone="body",
                            logical_zone="body", section_path="")
            for i, text in enumerate(texts))
        self.source_sha256 = sha

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _facts() -> Facts:
    return Facts("普通开放式基金", "", "", (), False, "", "", "", {}, ())


def _target(inspection, *, location="p0", quote=None, start=0, end=None,
            operations=("G17:0",), rule_id="G17", scope_id="G17:S01:L01",
            occurrence=-1) -> Target:
    quote = quote if quote is not None else inspection.by_location(location).text
    return Target("T1", rule_id, location, quote, "needs_edit", "",
                  start=start, end=len(quote) if end is None else end,
                  resolution="resolved", segment_ok=True,
                  operations=operations, scope_id=scope_id,
                  occurrence_index=occurrence)


def test_legal_approval_still_authorizes_its_own_site_and_operation():
    doc = Inspection(["销售服务费可用于市场推广。", "本基金的管理费按0.5%计提。"])
    target = _target(doc)
    approval = approval_from_target("A1", target, doc, guide_id="g",
                                    guide_sha256="h", condition_digest="c")
    target.approval_id = "A1"
    book = ApprovalBook([approval])
    assert book.allows(target, doc).ok
    assert book.allows(replace(target, operations=("G17:0",)), doc).ok


def test_approval_cannot_move_to_another_paragraph_with_identical_text():
    doc = Inspection(["销售服务费可用于市场推广。", "销售服务费可用于市场推广。"])
    original = _target(doc)
    approval = approval_from_target("A1", original, doc, guide_id="g",
                                    guide_sha256="h", condition_digest="c")
    original.approval_id = "A1"
    book = ApprovalBook([approval])
    moved = replace(original, target_id="T2", location="p1")
    check = book.allows(moved, doc)
    assert not check.ok
    assert check.code == "APPROVAL_SITE_MISMATCH"


def test_approval_cannot_move_to_different_offsets_or_occurrence():
    doc = Inspection(["销售服务费可用于市场推广。"])
    original = _target(doc, start=0, end=13)
    approval = approval_from_target("A1", original, doc, guide_id="g",
                                    guide_sha256="h")
    original.approval_id = "A1"
    book = ApprovalBook([approval])
    shifted = replace(original, start=1, end=12)
    assert not book.allows(shifted, doc).ok
    occurrence = replace(original, occurrence_index=1)
    assert not book.allows(occurrence, doc).ok


def test_empty_operations_or_a_different_operation_are_rejected():
    doc = Inspection(["销售服务费可用于市场推广。"])
    original = _target(doc)
    approval = approval_from_target("A1", original, doc, guide_id="g",
                                    guide_sha256="h")
    original.approval_id = "A1"
    book = ApprovalBook([approval])
    assert book.allows(replace(original, operations=()), doc).code == \
        "APPROVAL_OPERATION_MISSING"
    assert book.allows(replace(original, operations=("G17:1",)), doc).code == \
        "APPROVAL_OPERATION_MISMATCH"
    assert book.allows(replace(original, rule_id="G18"), doc).code == \
        "APPROVAL_RULE_MISMATCH"


def test_guide_scope_and_condition_versions_must_match():
    doc = Inspection(["销售服务费可用于市场推广。"])
    original = _target(doc)
    approval = approval_from_target("A1", original, doc, guide_id="guide-one",
                                    guide_sha256="hash-one",
                                    condition_digest=condition_fingerprint({
                                        "rule_id": "G17",
                                        "operations": [{"op": "delete",
                                                        "old_text": "x"}]}))
    original.approval_id = "A1"
    assert ApprovalBook([approval], guide_id="guide-one",
                        guide_sha256="hash-one",
                        condition_digests={"G17": approval.condition_digest}) \
        .allows(original, doc).ok
    stale_guide = ApprovalBook([approval], guide_id="guide-one",
                               guide_sha256="hash-two",
                               condition_digests={"G17": approval.condition_digest})
    assert stale_guide.allows(original, doc).code == "APPROVAL_GUIDE_STALE"
    stale_condition = ApprovalBook([approval], guide_id="guide-one",
                                   guide_sha256="hash-one",
                                   condition_digests={"G17": "other"})
    assert stale_condition.allows(original, doc).code == "APPROVAL_CONDITION_STALE"
    moved_scope = replace(original, scope_id="G17:S02:L01")
    assert ApprovalBook([approval], guide_id="guide-one",
                        guide_sha256="hash-one") \
        .allows(moved_scope, doc).code == "APPROVAL_SCOPE_MISMATCH"


def test_planner_never_uses_a_rebound_approval_for_approved_delete():
    """Old audit probe condition: same quote, another physical paragraph."""
    doc = Inspection(["销售服务费可用于市场推广。", "本基金的管理费按0.5%计提。"])
    rule = {"rule_id": "G99", "title": "删除旧用途",
            "operations": [{"op": "delete", "old_text": "销售服务费主要用于销售机构营销。",
                            "condition": {"kind": "none"}}]}
    original = _target(doc, rule_id="G99", scope_id="G99:S:L", operations=("G99:0",))
    approval = approval_from_target("A1", original, doc, guide_id="g",
                                    guide_sha256="h")
    original.approval_id = "A1"
    book = ApprovalBook([approval])

    class NoModel:
        def call(self, **kwargs):  # pragma: no cover - must never run
            raise AssertionError("model must not be called")

    moved = replace(original, target_id="T2", location="p1",
                    quote=doc.by_location("p1").text, start=0,
                    end=len(doc.by_location("p1").text))
    try:
        edit = plan_target(rule, moved, doc, _facts(), NoModel(),
                           compose_budget=[0], approvals=book)
    except RecallError as error:
        assert error.code != ""
        return
    assert edit is None or edit.content_source != "approved_span_delete"
    assert edit is None or edit.location != "p1"


def test_claim_replay_adapter_carries_the_physical_binding():
    from fundlex.generation.claim_replay import _approval_target

    doc = Inspection(["销售服务费可用于市场推广。", "销售服务费可用于市场推广。"])
    original = _target(doc)
    approval = approval_from_target("A1", original, doc, guide_id="g",
                                    guide_sha256="h")
    original.approval_id = "A1"
    book = ApprovalBook([approval])
    moved = replace(original, target_id="T2", location="p1")
    serialized = moved.as_dict()
    assert not book.allows(_approval_target(serialized), doc).ok
    serialized["location"] = "p0"
    assert book.allows(_approval_target(serialized), doc).ok
