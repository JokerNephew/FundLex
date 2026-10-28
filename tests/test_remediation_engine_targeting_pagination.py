"""FL-D441 (engine): scope filtering happens on every candidate page.

The audit probe built 13 valid anchors, resolved the rule to only p12, and the
default consumer read only the first 12 anchors before applying the scope.  The
legal p12 candidate was therefore starved forever.  These tests consume the
candidate pages until an in-scope anchor exists and keep the cursor/coverage
observable; the locator prompt reports its own page instead of silently dropping
the tail.
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.docx import TextSegment
from fundlex.obligations import compile_obligations
from fundlex.recall import Facts, Target
from fundlex.rule_scope import RuleScope
from fundlex.targeting import (CandidatePage, _open_operation_candidates,
                               locate_unresolved_targets, target_for_missing_operation,
                               targets_for_open_rules)

OLD = "基金管理人可以调整该项费用并提前公告。"
RULE = {
    "rule_id": "G99", "title": "费用调整",
    "operations": [{"op": "replace", "old_text": OLD,
                    "new_text": "基金管理人应提前公告。",
                    "condition": {"kind": "none"}}],
}


class Inspection:
    def __init__(self, texts, sha: str = "source"):
        self.paragraphs = tuple(
            SimpleNamespace(location=f"p{i}", text=text, zone="body",
                            logical_zone="body", section_path="",
                            segments=(TextSegment(0, len(text)),),
                            fingerprint=f"p{i}")
            for i, text in enumerate(texts))
        self.source_sha256 = sha

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _facts() -> Facts:
    return Facts("普通开放式基金", "", "", (), False, "", "", "", {}, ())


def _case(count: int = 13):
    inspection = Inspection([OLD + f"第{i}项。" for i in range(count)])
    section = SimpleNamespace(id="S", title="基金费用",
                              locations=tuple(span.location
                                              for span in inspection.paragraphs),
                              zone="body")
    obligation = compile_obligations({"groups": [RULE]})
    record = obligation.records[0]
    scope = RuleScope("G99", frozenset({"S:L"}), frozenset({f"p{count - 1}"}),
                      "body", False, frozenset(), "resolved", ())
    return inspection, section, obligation, record, scope


def test_missing_operation_consumes_page_two_and_records_coverage():
    inspection, section, obligation, record, scope = _case()
    coverage: dict = {}
    target = target_for_missing_operation(
        record, [], {"G99": RULE}, _facts(), inspection, {"G99": ["S"]},
        [section], scopes={"G99": scope}, coverage=coverage)
    assert target is not None
    assert target.location == "p12"
    assert target.site_candidates == ("p12",)
    scan = coverage["G99:0"]
    assert scan["pages"] == 2
    assert scan["scanned"] == 13
    assert scan["scope_rejected"] == 12
    assert scan["has_more"] is False and scan["complete"] is True
    assert getattr(target, "candidate_coverage", {})["in_scope"] == 1


def test_open_rule_consumes_page_two_instead_of_starving():
    inspection, section, obligation, _, scope = _case()
    coverage: dict = {}
    created = targets_for_open_rules(
        obligation, [], {"G99": RULE}, _facts(), inspection, {"G99": ["S"]},
        [section], scopes={"G99": scope}, coverage=coverage)
    assert len(created) == 1
    assert created[0].location == "p12"
    assert created[0].site_candidates == ("p12",)
    assert coverage["G99:0"]["pages"] == 2
    assert coverage["G99:0"]["scope_rejected"] == 12


def test_candidate_pages_stay_explicit_and_resumable():
    inspection, section, _, record, _ = _case(count=20)
    first = _open_operation_candidates(inspection, RULE, record, ["S"], {"S": section},
                                       _facts())
    second = _open_operation_candidates(inspection, RULE, record, ["S"], {"S": section},
                                        _facts(), cursor=first.next_cursor)
    assert isinstance(first, CandidatePage)
    assert len(first) == 12 and first.has_more is True
    assert first.next_cursor == 12 and first.remaining == 8
    assert list(second) == [f"p{i}" for i in range(12, 20)]
    assert second.has_more is False and second.remaining == 0


class Gateway:
    max_context_chars = 20000

    def __init__(self):
        self.contexts: list[str] = []

    def call(self, **kwargs):
        self.contexts.append(kwargs["bounded_context"])
        return SimpleNamespace(value={
            "location": "p12", "quote": OLD, "semantic_role": "fee",
            "reason": "scripted locator"})


def test_locator_reports_truncation_and_resumes_with_the_next_page():
    inspection = Inspection([OLD] * 20)
    target = Target("T", "G99", "p0", "", "needs_edit", "T3_open_rule",
                    resolution="unresolved",
                    site_candidates=tuple(f"p{i}" for i in range(20)),
                    operations=("G99:0",))
    gateway = Gateway()
    first = locate_unresolved_targets([target], inspection, {"G99": RULE}, _facts(),
                                      gateway, candidate_limit=12)
    assert first[0]["status"] == "rejected"
    assert first[0]["reject_reason"] == "location_outside_candidate_window"
    assert first[0]["candidate_coverage"]["total"] == 20
    assert first[0]["candidate_coverage"]["shown"] == 12
    assert first[0]["candidate_coverage"]["remaining"] == 8
    assert first[0]["candidate_coverage"]["next_cursor"] == 12
    assert first[0]["resume_cursor"] == 12
    assert "CANDIDATE_COVERAGE total=20 shown=12 remaining=8" in gateway.contexts[0]
    assert getattr(target, "_candidate_cursor") == 12

    second = locate_unresolved_targets([target], inspection, {"G99": RULE}, _facts(),
                                       gateway, candidate_limit=12)
    assert second[0]["status"] == "bound"
    assert target.location == "p12"
    assert target.resolution == "resolved"
    assert second[0]["candidate_coverage"]["cursor"] == 12
    assert second[0]["candidate_coverage"]["shown"] == 8
