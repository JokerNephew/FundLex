"""R13/R14: claim replay and residual scans must expose truncated batches."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.generation.claim_replay import check_delete_residuals, replay_claims


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{i}", text=text)
                           for i, text in enumerate(texts)]

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


def _replay_fixture(count: int = 45):
    before = Inspection([f"原文第{i}条。" for i in range(count)])
    after = Inspection([f"新文第{i}条。" for i in range(count)])
    edits = [{"location": f"p{i}", "rule_id": "MISSING", "start": 0,
              "end": len(before.paragraphs[i].text),
              "replacement": f"计划第{i}条。"} for i in range(count)]
    return edits, before, after


def test_replay_default_batch_reports_truncation_and_continues():
    edits, before, after = _replay_fixture()
    first = replay_claims(edits, before, after, rules_by_id={})
    assert first["verified"] is False
    assert first["checked"] == 40
    assert first["checked_this_page"] == 40
    assert first["total_locations"] == 45
    assert first["truncated"] is True
    assert first["remaining"] == 5
    assert first["next_cursor"] == 40
    assert len(first["failures"]) == 40

    second = replay_claims(edits, before, after, rules_by_id={},
                           cursor=first["next_cursor"])
    assert second["verified"] is False
    assert second["checked"] == 45
    assert second["checked_this_page"] == 5
    assert second["truncated"] is False
    assert second["remaining"] == 0
    assert second["next_cursor"] is None
    assert len(second["failures"]) == 5


def test_replay_raised_limit_checks_all_45():
    edits, before, after = _replay_fixture()
    proof = replay_claims(edits, before, after, rules_by_id={}, max_failures=100)
    assert proof["verified"] is False
    assert proof["checked"] == 45
    assert proof["truncated"] is False
    assert proof["remaining"] == 0
    assert proof["next_cursor"] is None
    assert len(proof["failures"]) == 45


def test_replay_page_size_truncates_without_counting_as_verified():
    edits, before, after = _replay_fixture()
    proof = replay_claims(edits, before, after, rules_by_id={}, page_size=10)
    assert proof["verified"] is False
    assert proof["checked"] == 10
    assert proof["truncated"] is True
    assert proof["remaining"] == 35
    assert proof["next_cursor"] == 10


def test_delete_residual_default_batch_reports_truncation_and_continues():
    sentence = "销售服务费每日计提，按月支付。"
    after = Inspection([sentence] * 45)
    rules = {"G15": {"rule_id": "G15", "operations": [
        {"op": "delete", "old_text": sentence}]}}

    first = check_delete_residuals(rules, after)
    assert len(first) == 40
    assert first.truncated is True
    assert first.remaining == 5
    assert first.next_cursor == 40
    assert first.total_candidates == 45
    assert first.checked == 1

    second = check_delete_residuals(rules, after, cursor=first.next_cursor)
    assert len(second) == 5
    assert second.truncated is False
    assert second.remaining == 0
    assert second.next_cursor is None


def test_delete_residual_raised_limit_checks_all_45():
    sentence = "销售服务费每日计提，按月支付。"
    after = Inspection([sentence] * 45)
    rules = {"G15": {"rule_id": "G15", "operations": [
        {"op": "delete", "old_text": sentence}]}}
    findings = check_delete_residuals(rules, after, max_failures=100)
    assert len(findings) == 45
    assert findings.truncated is False
    assert findings.remaining == 0
