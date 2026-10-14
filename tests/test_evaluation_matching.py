"""Independent scorer must reject altered actual DOCX and source coordinates."""
import hashlib
import json

import pytest
from docx import Document

from tools.evaluation.matching_audit import evaluate, replay
from tools.evaluation.release_evidence import final_reviewed_actions
from rules.release_v2 import validate_evidence


def write_docx(path, text):
    doc = Document()
    doc.add_paragraph(text)
    doc.save(path)


def fixture_run(tmp_path, actual):
    source = tmp_path / "source.docx"
    final = tmp_path / "final.docx"
    write_docx(source, "旧条款。保留原文。")
    write_docx(final, actual)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    labels = tmp_path / "targets.json"
    labels.write_text(json.dumps({"predictions_read": False, "kind": "independent_ai_reference",
        "cases": [{"case_id": "case", "source_path": str(source), "source_sha256": source_hash,
                   "actions": [{"action_id": "R07-A1", "status": "reviewed", "targets": [
                       {"location": "p0", "start": 0, "end": 4, "quote": "旧条款。", "expectation": "modify"}]}]}]}), encoding="utf-8")
    (tmp_path / "freeze.json").write_text(json.dumps({"sha256": hashlib.sha256(labels.read_bytes()).hexdigest()}), encoding="utf-8")
    rules = tmp_path / "rules.json"
    rules.write_text(json.dumps({"actions": [{"action_id": "R07-A1", "generation": {
        "mode": "template", "template_text": "新条款。"}}]}), encoding="utf-8")
    edit = {"location": "p0", "start": 0, "end": 4, "expected_old_text": "旧条款。",
            "action_id": "R07-A1", "replacement": "新条款。", "verification": {"passed": True}}
    (tmp_path / "batch_001.json").write_text(json.dumps([{"final_docx": str(final), "report": {
        "source_sha256": source_hash, "edit_plan": {"edits": [edit]}}}]), encoding="utf-8")
    return labels, rules


def test_actual_artifact_is_checked_independently_of_report(tmp_path):
    labels, rules = fixture_run(tmp_path, "新条款。保留原文。")
    result = evaluate(labels, tmp_path, rules)
    assert result["overall"]["edited_correct"] == 1
    write_docx(tmp_path / "final.docx", "新条款。误删余文。")
    result = evaluate(labels, tmp_path, rules)
    assert result["overall"]["confirmed_wrong_edits"] == 1
    assert result["overall"]["artifact_mismatch_cases"] == 1


def test_frozen_labels_cannot_be_relabelled(tmp_path):
    labels, rules = fixture_run(tmp_path, "新条款。保留原文。")
    labels.write_text(labels.read_text() + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="changed after freezing"):
        evaluate(labels, tmp_path, rules)


def test_replay_rejects_overlap_and_wrong_source_quote():
    first = {"location": "p0", "start": 1, "end": 4, "expected_old_text": "bcd", "replacement": "X"}
    second = {"location": "p0", "start": 3, "end": 5, "expected_old_text": "de", "replacement": "Y"}
    with pytest.raises(ValueError, match="overlapping"):
        replay({"p0": "abcdef"}, [first, second])
    first["expected_old_text"] = "bad"
    with pytest.raises(ValueError, match="quote mismatch"):
        replay({"p0": "abcdef"}, [first])


def test_evidence_counter_ignores_superseded_review():
    binding = {"source_sha256": "source", "plan_sha256": "final-plan",
               "redline_sha256": "redline", "final_sha256": "final"}
    report = {"source_sha256": "source", "edit_plan": {"sha256": "final-plan"},
              "output_validation": {"redline_sha256": "redline", "final_sha256": "final"},
              "actual_content_verifications": [{**binding, "passed": True,
                  "actions": [{"action_id": "R07-A1", "passed": True}]}]}
    assert final_reviewed_actions(report) == {"R07-A1"}
    report["actual_content_verifications"][-1]["plan_sha256"] = "superseded-plan"
    assert final_reviewed_actions(report) == set()


def test_release_cannot_rebind_stale_real_evidence(tmp_path):
    (tmp_path / "protocol.json").write_text(json.dumps({"engine_build": "old-engine"}), encoding="utf-8")
    with pytest.raises(SystemExit, match="does not match"):
        validate_evidence([str(tmp_path)], {"engine_build": "new-engine", "model_transport_sha256": "transport"})
