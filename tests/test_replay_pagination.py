"""Pagination boundaries for replay scanning and the task/contract pages.

The replay half covers R13/R14 truncated batches; the task half pins the SQL
paging contract (page boundaries, ``total`` and task-wide ``reason_options``)
that the workbench list endpoints rely on.
"""
from __future__ import annotations

import io
import json
import zipfile
from types import SimpleNamespace

from fundlex.generation.claim_replay import check_delete_residuals, replay_claims


def _docx(label: str = "fixture") -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f"<document>{label}</document>")
    return output.getvalue()


def _task_store(tmp_path):
    from fundlex.store import RunStore
    from fundlex.tasks import TaskStore

    store = RunStore(tmp_path / "pagination-store")
    return store, TaskStore(store)


def _task_with_files(tasks, data: bytes, count: int):
    manifest = [{"client_id": f"file-{index}", "name": f"合同{index:03}.docx", "size": len(data)}
                for index in range(count)]
    task = tasks.create("alice", "分页任务", {"version": "g1", "sha256": "a" * 64},
                        manifest, "pagination-key", engine_id="recall_first",
                        guide_version_id="", guide_rules_sha256="")
    return task, manifest


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


def test_task_store_document_pages_keep_stable_boundaries(tmp_path):
    data = _docx()
    store, tasks = _task_store(tmp_path)
    task, manifest = _task_with_files(tasks, data, 7)

    for sort, expected in (("oldest", [item["name"] for item in manifest]),
                           ("newest", [item["name"] for item in manifest][::-1]),
                           ("name", sorted((item["name"] for item in manifest), key=str.casefold)),
                           ("name_desc", sorted((item["name"] for item in manifest),
                                                key=str.casefold, reverse=True))):
        collected, page = [], 1
        while True:
            body = tasks.documents("alice", task["id"], sort=sort, page=page, page_size=2)
            assert body["total"] == 7 and body["page"] == page and body["page_size"] == 2
            collected.extend(item["name"] for item in body["items"])
            if len(body["items"]) < 2:
                break
            page += 1
        assert collected == expected
    assert tasks.documents("alice", task["id"], page=5, page_size=2)["items"] == []
    assert tasks.documents("alice", task["id"], page=5, page_size=2)["total"] == 7


def test_task_store_reason_options_cover_every_contract_not_just_the_page(tmp_path):
    data = _docx()
    store, tasks = _task_store(tmp_path)
    task, manifest = _task_with_files(tasks, data, 3)
    tasks.uploads("alice", task["id"],
                  [{"client_id": item["client_id"], "name": item["name"], "data": data,
                    "error_code": None} for item in manifest])
    reports = [
        {"actions": [{"status": "failed", "failure_reason": "TARGET_SCOPE_UNRESOLVED"}]},
        {"actions": [{"status": "failed", "failure_reason": "RELEASE_GATE_CLOSED"}]},
        {"unresolved": [{"code": "QUALIFICATION_EVIDENCE_MISSING"}]},
    ]
    rows = tasks.documents("alice", task["id"])["items"]
    with store._connect() as db:
        for row, report in zip(rows, reports):
            db.execute("UPDATE documents SET report_json=? WHERE id=?",
                       (json.dumps(report), row["document_id"]))
    page = tasks.documents("alice", task["id"], page=2, page_size=1)
    assert page["total"] == 3 and len(page["items"]) == 1
    assert page["items"][0]["reason_codes"] == ["RELEASE_GATE_CLOSED"]
    assert {option["code"]: option["count"] for option in page["reason_options"]} == {
        "TARGET_SCOPE_UNRESOLVED": 1,
        "RELEASE_GATE_CLOSED": 1,
        "QUALIFICATION_EVIDENCE_MISSING": 1,
    }
    import pytest

    from fundlex.store import NotFound

    with pytest.raises(NotFound):
        tasks.documents("bob", task["id"])
