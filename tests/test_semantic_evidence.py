"""Contracts for versioned source evidence and semantic approvals (R01-R03/S1)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from fundlex.semantic_evidence import (
    ApprovalBook,
    CoverageRecord,
    EvidenceError,
    EvidenceRef,
    SemanticApproval,
    approval_from_target,
    coverage_complete,
    dumps,
    evidence_from_composite,
    evidence_from_span,
    guide_fingerprint,
)

SOURCE = "sha-source-1"


def inspection(*texts: str, source: str = SOURCE):
    spans = [SimpleNamespace(location=f"p{index}", text=text)
             for index, text in enumerate(texts)]
    by_location = {span.location: span for span in spans}
    return SimpleNamespace(source_sha256=source, paragraphs=tuple(spans),
                           by_location=by_location.__getitem__)


def target(location="p0", quote="销售服务费可用于市场推广。", operations=("G17:0",),
           scope_id="G17:S01:L01", **kwargs):
    values = dict(target_id="T1", rule_id="G17", location=location, quote=quote,
                  state="needs_edit", reason="inventory", start=0, end=len(quote),
                  operations=operations, scope_id=scope_id)
    values.update(kwargs)
    return SimpleNamespace(**values)


def test_evidence_verifies_exact_slice_and_rejects_shifted_offsets():
    doc = inspection("销售服务费可用于市场推广。")
    evidence = evidence_from_span("E1", doc, "p0", quote="销售服务费可用于市场推广。")
    assert evidence.verify(doc) == (True, "")
    shifted = EvidenceRef(evidence.evidence_id, evidence.source_sha256,
                          (type(evidence.parts[0])("p0", 1, 5, evidence.parts[0].exact_quote),))
    ok, code = shifted.verify(doc)
    assert not ok and code == "EVIDENCE_QUOTE_MISMATCH"


def test_evidence_rejects_stale_source_and_non_literal_quote():
    doc = inspection("销售服务费可用于市场推广。")
    evidence = evidence_from_span("E1", doc, "p0", quote="销售服务费可用于市场推广。")
    ok, code = evidence.verify(inspection("销售服务费可用于市场推广。", source="other"))
    assert not ok and code == "EVIDENCE_SOURCE_MISMATCH"
    ellipsis = EvidenceRef("E2", SOURCE,
                           (type(evidence.parts[0])("p0", 0, 5, "销售服务…"),))
    ok, code = ellipsis.verify(doc)
    assert not ok and code == "EVIDENCE_QUOTE_NOT_LITERAL"


def test_occurrence_index_distinguishes_identical_quotes():
    doc = inspection("费用不同。费用不同。")
    first = evidence_from_span("E1", doc, "p0", quote="费用不同。", occurrence_index=0)
    second = evidence_from_span("E2", doc, "p0", quote="费用不同。", occurrence_index=1)
    assert first.parts[0].start == 0
    assert second.parts[0].start == 5
    with pytest.raises(EvidenceError) as error:
        evidence_from_span("E3", doc, "p0", quote="费用不同。", occurrence_index=2)
    assert error.value.code == "EVIDENCE_OCCURRENCE_OUT_OF_RANGE"


def test_composite_evidence_binds_every_part():
    doc = inspection("前半句，", "后半句。")
    evidence = evidence_from_composite("E1", doc, [
        {"location": "p0", "start": 0, "end": 4},
        {"location": "p1", "start": 0, "end": 4},
    ])
    assert evidence.text == "前半句，后半句。"
    assert evidence.verify(doc) == (True, "")


def test_approval_requires_operation_scope_and_live_quote():
    doc = inspection("销售服务费可用于市场推广。")
    with pytest.raises(EvidenceError) as error:
        approval_from_target("A1", target(operations=()), doc,
                             guide_id="g", guide_sha256="h")
    assert error.value.code == "APPROVAL_OPERATION_MISSING"
    with pytest.raises(EvidenceError) as error:
        approval_from_target("A1", target(scope_id=""), doc,
                             guide_id="g", guide_sha256="h")
    assert error.value.code == "APPROVAL_SCOPE_MISSING"
    with pytest.raises(EvidenceError) as error:
        approval_from_target("A1", target(quote="不存在的句子。"), doc,
                             guide_id="g", guide_sha256="h")
    assert error.value.code == "EVIDENCE_QUOTE_MISMATCH"
    with pytest.raises(EvidenceError) as error:
        approval_from_target("A1", target(quote="不存在的句子。", start=None, end=None),
                             doc, guide_id="g", guide_sha256="h")
    assert error.value.code == "EVIDENCE_QUOTE_NOT_FOUND"


def test_approval_consumption_checks_identity_and_state():
    doc = inspection("销售服务费可用于市场推广。")
    approval = approval_from_target("A1", target(), doc, guide_id="g", guide_sha256="h")
    assert approval.state == "approved"
    assert approval.check(doc, guide_id="g", guide_sha256="h").ok
    assert approval.check(doc, guide_id="other").code == "APPROVAL_GUIDE_MISMATCH"
    assert approval.check(doc, guide_sha256="stale").code == "APPROVAL_GUIDE_STALE"
    assert approval.check(doc, operation_keys=("G17:1",)).code == "APPROVAL_OPERATION_MISMATCH"
    assert approval.check(doc, scope_id="other").code == "APPROVAL_SCOPE_MISMATCH"
    assert approval.reject("wrong clause").check(doc).code == "APPROVAL_NOT_APPROVED"
    assert approval.leave_unresolved("need more context").check(doc).code == \
        "APPROVAL_NOT_APPROVED"


def test_approval_book_allows_only_its_own_target_and_operation():
    doc = inspection("销售服务费可用于市场推广。")
    bound = target()
    approval = approval_from_target("A1", bound, doc, guide_id="g", guide_sha256="h")
    book = ApprovalBook([approval])
    bound.approval_id = "A1"
    assert book.allows(bound, doc).ok
    other = target(operations=("G17:1",))
    other.approval_id = "A1"
    assert book.allows(other, doc).code == "APPROVAL_OPERATION_MISMATCH"
    unbound = target()
    assert book.allows(unbound, doc).code == "APPROVAL_MISSING"
    assert ApprovalBook().allows(bound, doc).code == "APPROVAL_UNKNOWN"


def test_guide_fingerprint_distinguishes_same_rule_id_across_guides():
    builtin = [{"rule_id": "G01", "title": "释义-基金份额类别定义"}]
    custom = [{"rule_id": "G01", "title": "基金销售服务费"}]
    assert guide_fingerprint(builtin) != guide_fingerprint(custom)
    assert guide_fingerprint(builtin) == guide_fingerprint([dict(builtin[0])])
    assert guide_fingerprint([{"rule_id": "G01", "title": "x"}]) != \
        guide_fingerprint([{"rule_id": "G01", "title": "x", "operations": []}])


def test_coverage_is_never_complete_when_a_pass_did_not_finish():
    full = CoverageRecord("sweep", total_units=10, visited_units=10)
    partial = CoverageRecord("inventory", total_units=10, visited_units=9, has_more=True)
    assert full.state == "complete"
    assert partial.state == "partial"
    assert partial.remaining == 1
    assert not coverage_complete([full, partial])
    assert coverage_complete([full])
    assert not coverage_complete([])
    assert CoverageRecord("x").state == "not_started"


def test_json_roundtrip_keeps_approval_verifiable():
    doc = inspection("销售服务费可用于市场推广。")
    approval = approval_from_target("A1", target(), doc, guide_id="g", guide_sha256="h")
    restored = SemanticApproval.from_dict(
        __import__("json").loads(dumps(approval)))
    assert restored.check(doc, guide_id="g", guide_sha256="h").ok
    book = ApprovalBook.from_dict(__import__("json").loads(dumps(ApprovalBook([approval]))))
    assert len(book) == 1
    with pytest.raises(EvidenceError):
        SemanticApproval.from_dict({**approval.as_dict(), "schema_version": "old"})
