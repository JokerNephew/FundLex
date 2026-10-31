"""Upload lifecycle quality gate: certification, enable gate, needs_review, immutability.

The parse channel the Worker drives (parse -> deterministic validation ->
independent verification) must not silently release low-quality results:
an unclean document finishes the version as terminal ``failed`` with
structured, user-facing reasons and never becomes enableable.
"""
from __future__ import annotations

import io
import json

import pytest
from docx import Document

from fundlex import guide_store
from fundlex.guide import GUIDE_SCHEMA_VERSION
from fundlex.store import RunStore


def docx_bytes(label: str = "指引正文示例") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def make_store(tmp_path) -> RunStore:
    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    return store


def clean_document(rules=None) -> dict:
    return {"schema_version": GUIDE_SCHEMA_VERSION, "parser_version": "guide-parse-1",
            "prompt_versions": {"guide_parse": "guide_parse_v1", "guide_verify": "guide_verify_v1"},
            "source_sha256": "ab" * 32,
            "groups": rules if rules is not None else [{"rule_id": "G01", "title": "示例规则"}],
            "validation": {"errors": [], "warnings": [], "coverage_gaps": [], "clean": True,
                           "rounds": 1,
                           "verification": {"findings": [], "invalid_findings": 0,
                                            "coverage_explanation": "覆盖完整"}}}


def unclean_document(*, errors=None, findings=None) -> dict:
    document = clean_document()
    document["validation"] = {
        "errors": errors if errors is not None else
                  [{"code": "RULE_OPERATION_INVALID", "rule_id": "G01", "detail": "未知操作"}],
        "warnings": [{"code": "RULE_TITLE_LONG", "detail": "标题过长"}],
        "coverage_gaps": [3],
        "clean": False, "rounds": 3,
        "rounds_detail": [{"round": 1, "clean": False}, {"round": 2, "clean": False}],
        "verification": {"findings": findings if findings is not None else
                         [{"kind": "uncovered", "description": "指引第3段未被覆盖",
                           "paragraphs": [3], "evidence_quote": "……"}],
                         "invalid_findings": 0, "coverage_explanation": "存在缺口"},
    }
    return document


def parse_once(store, tmp_version) -> dict:
    job = guide_store.claim_guide_job(store)
    return guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                        document=tmp_version)


def test_clean_parse_is_certified_and_enableable(tmp_path):
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    result = parse_once(store, clean_document())
    assert result["job"]["status"] == "completed"
    assert result["version"]["status"] == "parsed"
    assert result["version"]["qualification_status"] == guide_store.QUALIFICATION_CERTIFIED
    enabled = guide_store.set_current_guide(store, "alice", version["id"])
    assert enabled["id"] == version["id"]


def test_unclean_parse_fails_terminally_with_structured_issues(tmp_path):
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    job = guide_store.claim_guide_job(store)
    assert job["attempts"] == 1
    result = guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                          document=unclean_document())
    # Terminal despite remaining attempt budget: blind re-parse of the same
    # source would just repeat the spend; the remedy is re-upload/re-parse.
    assert result["job"]["status"] == "failed"
    assert result["job"]["error_code"] == "GUIDE_VALIDATION_UNCLEAN"
    assert result["version"]["status"] == "failed"
    issues = result["version"]["issues"]
    assert issues["error_code"] == "GUIDE_VALIDATION_UNCLEAN"
    assert issues["clean"] is False
    assert issues["errors"][0]["code"] == "RULE_OPERATION_INVALID"
    assert issues["coverage_gaps"] == [3]
    assert issues["verification"]["findings"][0]["kind"] == "uncovered"
    assert issues["rounds"] == 3 and issues["detail"]
    # No rules silently released, not claimable again, not enableable.
    assert result["version"]["rules_sha256"] == ""
    assert guide_store.claim_guide_job(store) is None
    with pytest.raises(ValueError, match="GUIDE_NOT_ENABLEABLE"):
        guide_store.set_current_guide(store, "alice", version["id"])
    # The failed version is reparseable into a NEW version (never mutated).
    reparsed = guide_store.reparse_version(store, "alice", version["id"])
    assert reparsed["id"] != version["id"]
    assert reparsed["parent_version_id"] == version["id"]
    assert reparsed["qualification_status"] == guide_store.QUALIFICATION_NOT_RUN


def test_verification_findings_alone_block_certification(tmp_path):
    store = make_store(tmp_path)
    guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    result = parse_once(store, unclean_document(errors=[], findings=[{"kind": "uncovered"}]))
    assert result["version"]["status"] == "failed"
    assert result["version"]["issues"]["error_code"] == "GUIDE_VALIDATION_UNCLEAN"


def test_uncertified_parsed_version_cannot_be_enabled(tmp_path):
    """Legacy rows (parsed before certification existed) must not be enableable."""
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    parse_once(store, clean_document())
    with store._connect() as db:
        db.execute("UPDATE guide_versions SET qualification_status='not_run' WHERE id=?",
                   (version["id"],))
    with pytest.raises(ValueError, match="GUIDE_NOT_CERTIFIED"):
        guide_store.set_current_guide(store, "alice", version["id"])
    assert guide_store.current_guide(store, "alice")["id"] == guide_store.BUILTIN_GUIDE_ID
    # Rule settings are unaffected by the enable gate.
    settings = guide_store.rule_settings(store, "alice", version["id"])
    assert settings["rules"][0]["rule_id"] == "G01"


def test_reparse_requalifies_and_never_mutates_predecessor(tmp_path):
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    first = parse_once(store, clean_document())["version"]
    guide_store.set_current_guide(store, "alice", version["id"])
    before = guide_store.get_version(store, "alice", version["id"])

    reparsed = guide_store.reparse_version(store, "alice", version["id"])
    assert reparsed["parent_version_id"] == version["id"]
    assert reparsed["qualification_status"] == guide_store.QUALIFICATION_NOT_RUN
    # The new version is not enableable until it re-qualifies.
    with pytest.raises(ValueError, match="GUIDE_NOT_ENABLEABLE|GUIDE_NOT_CERTIFIED"):
        guide_store.set_current_guide(store, "alice", reparsed["id"])
    second = parse_once(store, clean_document(rules=[{"rule_id": "G01", "title": "改过"},
                                                     {"rule_id": "G02", "title": "新增"}]))["version"]
    assert second["qualification_status"] == guide_store.QUALIFICATION_CERTIFIED
    assert second["rules_sha256"] != before["rules_sha256"]

    after = guide_store.get_version(store, "alice", version["id"])
    # Immutability: the observed predecessor keeps every hash, rule and status.
    assert after["rules_sha256"] == before["rules_sha256"] == first["rules_sha256"]
    assert after["document_sha256"] == before["document_sha256"]
    assert after["status"] == "parsed"
    assert after["qualification_status"] == guide_store.QUALIFICATION_CERTIFIED
    assert after["rules_count"] == 1
    old_document = guide_store.guide_document(store, version["id"])
    assert [group["rule_id"] for group in old_document["groups"]] == ["G01"]
    new_document = guide_store.guide_document(store, reparsed["id"])
    assert [group["rule_id"] for group in new_document["groups"]] == ["G01", "G02"]
    # The current guide still points at the old certified snapshot until the
    # owner explicitly enables the new version.
    assert guide_store.current_guide(store, "alice")["id"] == version["id"]


def test_needs_review_marking_is_advisory_and_owner_scoped(tmp_path):
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    parse_once(store, clean_document())
    review = {"status": "needs_review", "evaluated_at": "2026-10-31T00:00:00Z",
              "dimensions": {"targets_before": 100, "targets_after": 40, "reason": "recall_drop"}}
    marked = guide_store.mark_guide_review(store, "alice", version["id"], review)
    assert marked["review"]["status"] == "needs_review"
    assert marked["review"]["dimensions"]["targets_after"] == 40
    assert marked["issues"]["review"] == review
    # Advisory only: the version remains certified and enableable.
    guide_store.set_current_guide(store, "alice", version["id"])
    # Persisted across fresh reads.
    assert guide_store.get_version(store, "alice", version["id"])["review"] == review
    cleared = guide_store.mark_guide_review(store, "alice", version["id"], None)
    assert cleared["review"] is None
    assert "review" not in cleared["issues"]
    with pytest.raises(KeyError):
        guide_store.mark_guide_review(store, "bob", version["id"], review)
    with pytest.raises(ValueError, match="GUIDE_REVIEW_INVALID"):
        guide_store.mark_guide_review(store, "alice", version["id"], "needs_review")


def test_failed_issues_round_trip_as_strict_json(tmp_path):
    """issues_json must stay valid JSON for the frontend pre-render."""
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", docx_bytes())
    result = parse_once(store, unclean_document())
    with store._connect() as db:
        raw = db.execute("SELECT issues_json FROM guide_versions WHERE id=?",
                         (version["id"],)).fetchone()["issues_json"]
    assert json.loads(raw)["error_code"] == result["version"]["issues"]["error_code"]
