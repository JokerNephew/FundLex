"""Publication/download gates rebind v3 review to exact final artifacts."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fundlex import rules_v2, v2_pipeline
from fundlex.api import create_app
from fundlex.jobs import Worker
from fundlex.store import Conflict, validate_delivery
from fundlex.v2 import canonical_sha
from test_v2_artifact_pipeline import ArtifactGateway, fixture


def successful_report(tmp_path, monkeypatch):
    source, _, output = fixture(tmp_path, monkeypatch)
    report = v2_pipeline.process_v2(source, output, gateway=ArtifactGateway(
        [("R06-A1", "pass"), ("R07-A1", "pass")], output), evaluation=True)
    assert report["delivery_status"] == "evaluation_modified"
    paths = {kind: Path(path) for kind, path in report["artifacts"].items()}
    return report, paths


def rehash(review):
    review["record_sha256"] = canonical_sha({key: value for key, value in review.items()
                                            if key != "record_sha256"})


def test_v3_real_pipeline_review_authorizes_exact_pair(tmp_path, monkeypatch):
    report, paths = successful_report(tmp_path, monkeypatch)
    validate_delivery(report, paths)
    formal = copy.deepcopy(report)
    formal.update(execution_mode="delivery", delivery_status="complete")
    formal["output_validation"]["kind"] = "validated_edits"
    validate_delivery(formal, {"final": paths["evaluation_final"], "redline": paths["evaluation_redline"]})


@pytest.mark.parametrize("mutation,code", [
    (lambda report: report.pop("actual_content_verifications"), "ACTUAL_CONTENT_REVIEW_MISSING"),
    (lambda report: report["actual_content_verifications"][-1].update(passed=False), "ACTUAL_CONTENT_REVIEW_INVALID"),
    (lambda report: report["actual_content_verifications"][-1].update(record_sha256="f" * 64), "ACTUAL_CONTENT_REVIEW_INVALID"),
    (lambda report: report["actual_content_verifications"][-1].update(plan_sha256="f" * 64), "ACTUAL_CONTENT_REVIEW_BINDING_MISMATCH"),
    (lambda report: report["actual_content_verifications"][-1].update(final_sha256="f" * 64), "ACTUAL_CONTENT_REVIEW_BINDING_MISMATCH"),
    (lambda report: report["actual_content_verifications"][-1]["actions"].pop(), "ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING"),
    (lambda report: report["actual_content_verifications"][-1]["actions"][0]["windows"][0].update(passed=False), "ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING"),
    (lambda report: report["edit_plan"]["edits"][0].update(location="p999"), "ACTUAL_CONTENT_REVIEW_PLAN_MISMATCH"),
    (lambda report: report["actual_content_verifications"][-1]["actions"][0]["windows"][0].update(edit_locations=[]), "ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING"),
    (lambda report: report["actual_content_verifications"][-1]["actions"][0]["windows"][0]["items"][0].update(result="unknown"), "ACTUAL_CONTENT_REVIEW_INVALID"),
    (lambda report: report["actual_content_verifications"][-1]["actions"][0]["windows"][0]["items"].pop(), "ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING"),
])
def test_v3_refuses_missing_forged_stale_or_incomplete_review(tmp_path, monkeypatch, mutation, code):
    report, paths = successful_report(tmp_path, monkeypatch)
    mutation(report)
    if "actual_content_verifications" in report:
        review = report["actual_content_verifications"][-1]
        if review.get("record_sha256") != "f" * 64:
            rehash(review)
    with pytest.raises(ValueError, match=code):
        validate_delivery(report, paths)


def test_legacy_v02_files_keep_existing_gate(tmp_path, monkeypatch):
    report, paths = successful_report(tmp_path, monkeypatch)
    report["engine_version"] = "0.2.0"
    report.pop("actual_content_verifications")
    validate_delivery(report, paths)


def run_worker(tmp_path, monkeypatch, decisions):
    source, subset, _ = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(rules_v2, "load_ruleset_v2", lambda *args, **kwargs: subset)
    app = create_app(tmp_path / "state")
    client = TestClient(app)
    headers = {"X-FundLex-User": "review-test-owner"}
    # The legacy ruleset HTTP route is retired; seed the batch directly, as the
    # offline v2 runner does.
    batch = app.state.store.create_batch(owner="review-test-owner", ruleset_version="v2",
                                         ruleset_sha256="0" * 64,
                                         uploads=[("source.docx", source.read_bytes())])
    batch_id = batch["id"]
    gateway = ArtifactGateway(decisions, tmp_path / "unused-output")
    worker = Worker(app.state.store, lambda source, output, version:
                    v2_pipeline.process_v2(source, output, version, gateway, evaluation=True))
    assert worker.run_once()
    document = client.get(f"/api/batches/{batch_id}", headers=headers).json()["documents"][0]
    return client, app.state.store, headers, batch_id, document


def test_review_refusal_persists_exceptions_and_report_only_downloads(tmp_path, monkeypatch):
    client, _, headers, _, document = run_worker(tmp_path, monkeypatch,
        [("R06-A1", "reject"), ("R07-A1", "reject")])
    assert document["delivery_status"] == "incomplete"
    assert set(document["downloads"]) == {"report_json", "report_md"}
    report_response = client.get(document["report_url"], headers=headers)
    assert report_response.status_code == 200
    report = report_response.json()
    assert report["error_code"] is None
    assert report["edit_plan"]["reason"] == "V3_ARTIFACT_REVIEW_REJECTED"
    assert {e["reason"] for e in report["exceptions"]} == {"V3_ARTIFACT_SEMANTIC_REJECTED"}
    assert not report["actual_content_verifications"][-1]["passed"]


@pytest.mark.parametrize("change", ["missing_review", "missing_action", "other_artifact"])
def test_download_revalidates_persisted_v3_review_and_both_files(tmp_path, monkeypatch, change):
    client, store, headers, batch_id, document = run_worker(tmp_path, monkeypatch,
        [("R06-A1", "pass"), ("R07-A1", "pass")])
    document_id = document["document_id"]
    assert client.get(document["downloads"]["evaluation_final"], headers=headers).status_code == 200
    report = store.get_report("review-test-owner", batch_id, document_id)
    if change == "missing_review":
        report.pop("actual_content_verifications")
    elif change == "missing_action":
        report["actual_content_verifications"][-1]["actions"].pop()
        rehash(report["actual_content_verifications"][-1])
    else:
        counterpart, _ = store.get_artifact("review-test-owner", batch_id, document_id, "evaluation_redline")
        counterpart.write_bytes(b"tampered counterpart")
    with store._connect() as db:
        db.execute("UPDATE documents SET report_json=? WHERE id=?",
                   (json.dumps(report, ensure_ascii=False), document_id))
    with pytest.raises(Conflict):
        store.get_artifact("review-test-owner", batch_id, document_id, "evaluation_final")
    assert client.get(document["downloads"]["evaluation_final"], headers=headers).status_code == 409
