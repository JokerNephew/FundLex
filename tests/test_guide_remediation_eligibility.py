"""FL-D374/338/455 eligibility, immutability and verified download tests."""
from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fundlex.guide_generation.api import register_guide_generation_routes
from fundlex.guide_generation.coverage import CoverageResult
from fundlex.guide_generation.eligibility import evaluate_run_eligibility
from fundlex.guide_generation.pipeline import GuidePipeline, PipelineConfig
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.store import RunStore

from guide_generation_fakes import FakeGuideRouter
from test_guide_generation_pipeline import _prepare


def _config(corpus, **extra):
    return PipelineConfig(corpus_dir=str(corpus), path_b_latest_only=False,
                          path_b_max_calls=20, path_c_enabled=False,
                          semantic_applicability=False, max_residual_rounds=2,
                          residual_max_calls_per_round=10, soft_max_calls=500,
                          **extra)


def _complete_run(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    router = FakeGuideRouter()
    result = GuidePipeline(gg, run_id, router, _config(corpus)).run()
    assert result["qualification_status"] == "candidate_ready", result.get("payload", {}).get("finalize")
    return store, gg, run_id, corpus, router


def _critical_finding():
    return {
        "finding_id": "F-LATE-CRITICAL", "category": "semantic_coverage",
        "severity": "critical", "status": "open", "source": "coverage_gate",
        "description": "覆盖阶段之后新增的 critical",
    }


def test_quality_failure_creates_blocked_draft_not_approvable(tmp_path):
    store, gg, run_id, corpus, router = _complete_run(tmp_path)
    gg.add_findings(run_id, [_critical_finding()])
    pipeline = GuidePipeline(gg, run_id, router, _config(corpus))
    final = pipeline.stage_finalize()
    assert final["qualified"] is False
    assert final["qualification_status"] == "candidate_with_findings"
    assert final["checklist"]["quality_gate_passed"] is False
    version = gg.get_candidate_version(run_id)
    assert version["status"] == "draft"
    assert version["qualification_status"] == "blocked"
    application = FastAPI()
    register_guide_generation_routes(application, store, gg, lambda: "u")
    with TestClient(application) as client:
        assert client.post(f"/api/guide-generation/runs/{run_id}/candidate/approve").status_code == 409
        assert client.post(f"/api/guide-generation/runs/{run_id}/candidate/publish").status_code == 409


def test_unqualified_independent_reviewer_blocks_candidate_ready(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)

    class SameModelRouter(FakeGuideRouter):
        def identity(self):
            identity = super().identity()
            author = identity["guide_author"]["model"]
            identity["guide_reviewer"]["model"] = author
            identity["guide_reviewer"]["same_model_as_author"] = True
            identity["independent_model_review"] = False
            identity["independent_model_review_status"] = "independent_model_review_not_qualified"
            return identity

    result = GuidePipeline(gg, run_id, SameModelRouter(), _config(corpus)).run()

    assert result["payload"]["quality"]["run_status"] == "pass"
    assert result["qualification_status"] == "candidate_with_findings"
    assert result["payload"]["finalize"]["checklist"][
        "independent_model_review_qualified"] is False
    assert result["payload"]["finalize"]["gates"][
        "configured_independent_model_review_status"] == "independent_model_review_not_qualified"


def test_eligibility_uses_identity_frozen_at_quality_review(tmp_path):
    store, gg, run_id, corpus, _router = _complete_run(tmp_path)

    class ChangedQualifiedRouter(FakeGuideRouter):
        def identity(self):
            identity = super().identity()
            identity["guide_reviewer"]["model"] = "later-reviewer-config"
            return identity

    # Reopening a completed run refreshes top-level runtime identity, but must
    # not rewrite which independently qualified reviewer actually reviewed it.
    resumed = GuidePipeline(gg, run_id, ChangedQualifiedRouter(), _config(corpus))
    resumed._update(payload=resumed.payload)
    gates = evaluate_run_eligibility(gg, run_id)

    assert gates["qualified"] is True
    assert gates["model_identity"]["guide_reviewer"]["model"] == "fake-guide-reviewer"


def test_independent_reviewer_call_failure_is_a_blocking_critical(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)

    class ReviewerFailureRouter(FakeGuideRouter):
        def _value(self, task_type, context):
            if task_type == "guide_quality_review":
                raise RuntimeError("fake reviewer unavailable")
            return super()._value(task_type, context)

    result = GuidePipeline(gg, run_id, ReviewerFailureRouter(), _config(corpus)).run()
    review_failures = [finding for finding in gg.get_findings(run_id)
                       if finding.get("category") == "review_execution"
                       and finding.get("status") == "open"]

    assert result["qualification_status"] == "candidate_with_findings"
    assert result["payload"]["quality"]["run_status"] == "fail"
    assert review_failures
    assert all(finding["severity"] == "critical" for finding in review_failures)


def test_independent_reviewer_uncertain_verdict_blocks_candidate_ready(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)

    class UncertainReviewerRouter(FakeGuideRouter):
        def _value(self, task_type, context):
            if task_type == "guide_quality_review":
                return {"verdict": "uncertain", "findings": [], "notes": "fake uncertainty"}
            return super()._value(task_type, context)

    result = GuidePipeline(gg, run_id, UncertainReviewerRouter(), _config(corpus)).run()
    blocked_findings = [finding for finding in gg.get_findings(run_id)
                        if finding.get("category") == "review_verdict"
                        and finding.get("status") == "open"]

    assert result["qualification_status"] == "candidate_with_findings"
    assert result["payload"]["quality"]["run_status"] == "fail"
    assert blocked_findings
    assert all(finding["severity"] == "critical" for finding in blocked_findings)


def test_coverage_critical_after_quality_recomputes_quality_gate(tmp_path, monkeypatch):
    store, gg, run_id, corpus = _prepare(tmp_path)
    pipeline = GuidePipeline(gg, run_id, FakeGuideRouter(), _config(corpus))
    pipeline.payload.update(quality={"run_status": "pass"}, residual={"saturated": True})
    finding = {"finding_id": "F-COV-LATE", "category": "semantic_coverage",
               "severity": "critical", "status": "open", "source": "coverage_gate",
               "description": "独立审计未覆盖主题"}
    result = CoverageResult(
        rows=[], findings=[finding], applicability=[],
        run_status="complete_with_unresolved",
        requirement_summary={"covered": 1}, impact_summary={"covered": 1},
        missing_topics=[{"topic_id": "TOPIC", "requirement_ids": [],
                         "description": "no anchor"}])
    monkeypatch.setattr("fundlex.guide_generation.pipeline.run_coverage_gate",
                        lambda *a, **k: result)
    pipeline.stage_coverage()
    assert pipeline.payload["quality"]["run_status"] == "fail"
    final = pipeline.stage_finalize()
    assert final["qualified"] is False
    assert final["critical_quality_findings"] >= 1
    assert gg.get_candidate_version(run_id)["status"] == "draft"


def test_finalize_cache_invalidates_when_quality_or_findings_change(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    pipeline = GuidePipeline(gg, run_id, FakeGuideRouter(), _config(corpus))
    pipeline.payload.update(quality={"run_status": "pass"},
                            coverage={"run_status": "pass"}, residual={"saturated": True})
    pipeline._update(payload=pipeline.payload)
    first = pipeline._stage("FINALIZE_GUIDE", "same-key", pipeline.stage_finalize,
                            revalidate=pipeline._finalize_cache_valid)
    assert first["gate_sha256"]
    pipeline.payload["quality"] = {"run_status": "fail", "critical_total": 1}
    pipeline._update(payload=pipeline.payload)
    assert pipeline._finalize_cache_valid(first) is False
    second = pipeline._stage("FINALIZE_GUIDE", "same-key", pipeline.stage_finalize,
                             revalidate=pipeline._finalize_cache_valid)
    assert second["gate_sha256"] != first["gate_sha256"]
    assert second["qualified"] is False


def test_publish_revalidates_qualification_and_content(tmp_path):
    store, gg, run_id, corpus, router = _complete_run(tmp_path)
    version = gg.get_candidate_version(run_id)
    gg.approve_candidate(run_id, actor="u", version_id=version["candidate_version_id"])
    gg.add_findings(run_id, [_critical_finding()])
    with pytest.raises(Exception, match="CANDIDATE_QUALIFICATION_BLOCKED"):
        gg.publish_candidate(run_id, actor="u", version_id=version["candidate_version_id"])


def test_approval_rejects_corrupt_version_artifact(tmp_path):
    store, gg, run_id, corpus, router = _complete_run(tmp_path)
    version = gg.get_candidate_version(run_id)
    artifact = version["payload"]["guide_artifact"]
    path = store.object_path(artifact["object_key"])
    path.write_bytes(b"corrupted candidate bytes")
    with pytest.raises(Exception, match="CANDIDATE_ARTIFACT_INTEGRITY"):
        gg.approve_candidate(run_id, actor="u", version_id=version["candidate_version_id"])


def test_late_finalize_cannot_overwrite_published_bytes(tmp_path):
    store, gg, run_id, corpus, router = _complete_run(tmp_path)
    version = gg.get_candidate_version(run_id)
    gg.approve_candidate(run_id, actor="u", version_id=version["candidate_version_id"])
    gg.publish_candidate(run_id, actor="u", version_id=version["candidate_version_id"])
    frozen = gg.get_candidate_version(run_id)
    artifact = frozen["payload"]["guide_artifact"]
    path = store.object_path(artifact["object_key"])
    before = path.read_bytes()
    before_sha = hashlib.sha256(before).hexdigest()
    items = gg.get_guide_items(run_id)
    items[0].new_text = "晚到流水线试图改写已发布版本"
    gg.replace_guide_items(run_id, items)
    final = GuidePipeline(gg, run_id, router, _config(corpus)).stage_finalize()
    after = gg.get_candidate_version(run_id)
    assert after["candidate_version_id"] == frozen["candidate_version_id"]
    assert after["status"] == "published"
    assert path.read_bytes() == before
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before_sha
    assert final["late_rejected"] is True
    assert all(v["version_no"] <= frozen["version_no"]
               for v in gg.get_candidate(run_id)["versions"])


def test_human_draft_requires_explicit_revalidation(tmp_path):
    from fundlex.guide_generation.human import update_guide_item
    store, gg, run_id, corpus, router = _complete_run(tmp_path)
    item = gg.get_guide_items(run_id)[0]
    result = update_guide_item(gg, run_id, item.guide_item_id,
                               {"instruction": "人工修改后的指引"}, "u")
    version = result["candidate_version"]
    assert version["status"] == "human_draft"
    assert version["qualification_status"] == "human_review_required"
    gg.add_findings(run_id, [_critical_finding()])
    with pytest.raises(Exception, match="CANDIDATE_QUALIFICATION_BLOCKED"):
        gg.approve_candidate(run_id, actor="u", version_id=version["candidate_version_id"])


def test_download_and_report_reject_corrupt_bytes_without_leaking_them(tmp_path):
    store, gg, run_id, corpus, router = _complete_run(tmp_path)
    version = gg.get_candidate_version(run_id)
    guide_path = store.object_path(version["payload"]["guide_artifact"]["object_key"])
    guide_bytes = guide_path.read_bytes()
    application = FastAPI()
    register_guide_generation_routes(application, store, gg, lambda: "u")
    with TestClient(application) as client:
        ok = client.get(f"/api/guide-generation/runs/{run_id}/download/guide")
        assert ok.status_code == 200 and ok.content == guide_bytes
        guide_path.write_bytes(b"truncated-corrupt-guide")
        corrupt = client.get(f"/api/guide-generation/runs/{run_id}/download/guide")
        assert corrupt.status_code == 409
        assert "ARTIFACT_INTEGRITY_MISMATCH" in corrupt.text
        assert b"truncated-corrupt-guide" not in corrupt.content
    other_app = FastAPI()
    register_guide_generation_routes(other_app, store, gg, lambda: "other")
    with TestClient(other_app) as client:
        assert client.get(f"/api/guide-generation/runs/{run_id}/download/guide").status_code == 404
    # Report uses the same verified accessor.
    evidence = gg.get_artifact(run_id, "evidence_html")
    report_path = store.object_path(evidence["object_key"])
    report_path.write_bytes(b"<html>corrupt report</html>")
    with TestClient(application) as client:
        response = client.get(f"/api/guide-generation/runs/{run_id}/report")
        assert response.status_code == 409
        assert "ARTIFACT_INTEGRITY_MISMATCH" in response.text
