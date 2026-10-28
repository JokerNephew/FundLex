"""FL-D453/468/469 fencing, engine task and resume regression tests."""
from __future__ import annotations

import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from fundlex.guide_generation.api import register_guide_generation_routes
from fundlex.guide_generation.pipeline import GuidePipeline, PipelineConfig
from fundlex.guide_generation.worker import GuideGenerationWorker
from fundlex.model import ModelError
from fundlex.store import Conflict

from guide_generation_fakes import FakeGuideRouter
from test_guide_generation_pipeline import _prepare


def _config(corpus, **extra):
    return PipelineConfig(corpus_dir=str(corpus), path_b_latest_only=False,
                          path_b_max_calls=20, path_c_enabled=False,
                          semantic_applicability=False, max_residual_rounds=2,
                          residual_max_calls_per_round=10, **extra)


def test_stale_job_epoch_cannot_write_run_or_artifacts(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)
    first = gg.claim(lease_seconds=30)
    assert first and first["id"] == job_id
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET lease_until=? WHERE id=?", (0, job_id))
    second = gg.claim(lease_seconds=30)
    assert second and second["fencing_token"] == first["fencing_token"] + 1
    with pytest.raises(Conflict, match="stale guide generation worker lease"):
        with gg.fencing(job_id, first["fencing_token"], run_id):
            gg.update_run(run_id, status="complete")
    with pytest.raises(Conflict, match="stale guide generation worker lease"):
        gg.heartbeat(job_id, first["fencing_token"])
    with pytest.raises(Conflict, match="stale guide generation worker lease"):
        gg.finish_job(job_id, first["fencing_token"], status="completed")
    assert gg.get_run(run_id)["status"] == "queued"


def test_two_workers_interleave_and_old_worker_cannot_overwrite_new_epoch(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    gg.enqueue(run_id)

    class BlockingFactory:
        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()

        def __call__(self):
            self.started.set()
            assert self.release.wait(15)
            return FakeGuideRouter()

    factory = BlockingFactory()
    old_worker = GuideGenerationWorker(store, router_factory=factory, lease_seconds=300)
    errors = []

    def run_old():
        try:
            old_worker.run_once()
        except BaseException as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    thread = threading.Thread(target=run_old)
    thread.start()
    assert factory.started.wait(10)
    with gg._connect() as db:
        job = db.execute("SELECT id,fencing_token FROM gg_jobs WHERE run_id=?", (run_id,)).fetchone()
        db.execute("UPDATE gg_jobs SET lease_until=? WHERE id=?", (0, job["id"]))
    new_worker = GuideGenerationWorker(store, router_factory=FakeGuideRouter, lease_seconds=60)
    assert new_worker.run_once() is True
    expected = gg.get_run(run_id)
    factory.release.set()
    thread.join(20)
    assert not errors
    after = gg.get_run(run_id)
    assert after["status"] == expected["status"]
    assert after["qualification_status"] == expected["qualification_status"]
    assert "worker_error" not in (after.get("payload") or {})
    jobs = {}
    with gg._connect() as db:
        rows = db.execute("SELECT id,status,fencing_token FROM gg_jobs WHERE run_id=?", (run_id,)).fetchall()
        jobs = {row["id"]: dict(row) for row in rows}
    assert jobs[job["id"]]["status"] == "completed"
    assert jobs[job["id"]]["fencing_token"] == job["fencing_token"] + 1


def test_model_pause_is_resumable_with_new_epoch_and_keeps_evidence(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    gg.enqueue(run_id)

    def unavailable():
        raise ModelError("MODEL_CONFIG_MISSING")

    assert GuideGenerationWorker(store, router_factory=unavailable).run_once() is True
    paused = gg.get_run(run_id)
    assert paused["status"] == "paused"
    assert paused["payload"]["blocked_reason"] == "MODEL_CONFIG_MISSING"
    assert gg.claim() is None
    with gg._connect() as db:
        paused_jobs = [dict(row) for row in db.execute(
            "SELECT id,status FROM gg_jobs WHERE run_id=?", (run_id,)).fetchall()]
    assert paused_jobs and paused_jobs[0]["status"] == "paused"
    application = FastAPI()
    register_guide_generation_routes(application, store, gg, lambda: "u")
    with TestClient(application) as client:
        resumed = client.post(f"/api/guide-generation/runs/{run_id}/resume")
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["status"] == "queued"
        again = client.post(f"/api/guide-generation/runs/{run_id}/resume")
        assert again.status_code == 200
        assert again.json()["status"] == "already_running"
    with pytest.raises(Exception):
        gg.resume_run(run_id, owner="other", actor="other")
    with pytest.raises(Exception):
        gg.resume_run("missing", owner="u", actor="u")
    assert GuideGenerationWorker(store, router_factory=FakeGuideRouter).run_once() is True
    run = gg.get_run(run_id)
    assert run["status"] in {"complete", "complete_with_unresolved"}
    assert (run.get("payload") or {}).get("resume_epoch") == 1
    assert run["qualification_status"] in {"candidate_ready", "candidate_with_findings"}
    with gg._connect() as db:
        statuses = {row["status"] for row in db.execute(
            "SELECT status FROM gg_jobs WHERE run_id=?", (run_id,)).fetchall()}
    assert "superseded" in statuses and "completed" in statuses
    history = (gg.get_run(run_id).get("payload") or {}).get("resume_history") or []
    assert history and history[-1]["previous_status"] == "paused"
    assert history[-1]["previous_error_code"] == "MODEL_CONFIG_MISSING"


def test_transient_model_failure_retries_with_bounded_backoff(tmp_path, monkeypatch):
    store, gg, run_id, corpus = _prepare(tmp_path)
    gg.enqueue(run_id)
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise ModelError("MODEL_NETWORK_ERROR")
        return FakeGuideRouter()

    worker = GuideGenerationWorker(store, router_factory=flaky)
    assert worker.run_once() is True
    waiting = gg.get_run(run_id)
    assert waiting["status"] == "retry_wait"
    assert gg.claim() is None
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET next_attempt_at=0 WHERE run_id=?", (run_id,))
    assert worker.run_once() is True
    assert gg.get_run(run_id)["status"] in {"complete", "complete_with_unresolved"}
    assert attempts["n"] == 2


def test_engine_compatibility_endpoint_is_consumed_and_idempotent(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    GuidePipeline(gg, run_id, FakeGuideRouter(), _config(corpus)).run()
    frozen = gg.get_candidate_version(run_id)
    artifact = frozen["payload"]["guide_artifact"]
    application = FastAPI()
    register_guide_generation_routes(application, store, gg, lambda: "u")
    worker = GuideGenerationWorker(store, router_factory=FakeGuideRouter)
    with TestClient(application) as client:
        first = client.post(f"/api/guide-generation/runs/{run_id}/engine-compatibility")
        assert first.status_code == 202, first.text
        second = client.post(f"/api/guide-generation/runs/{run_id}/engine-compatibility")
        assert second.status_code == 202
        assert second.json().get("idempotent") is True
        assert worker.run_once() is True
        run = gg.get_run(run_id)
        assert run["engine_status"] == "completed"
        assert run["status"] in {"complete", "complete_with_unresolved"}
        assert gg.get_engine_runs(run_id)
        assert gg.get_engine_runs(run_id)[0]["candidate_version_id"] == frozen["candidate_version_id"]
        after = gg.get_candidate_version(run_id)
        assert after["candidate_version_id"] == frozen["candidate_version_id"]
        assert after["payload"]["guide_artifact"] == artifact
        third = client.post(f"/api/guide-generation/runs/{run_id}/engine-compatibility")
        assert third.status_code == 202
        assert third.json().get("idempotent") is True
        assert len(gg.get_engine_runs(run_id)) == 1


def test_explicit_engine_config_calls_the_existing_method(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    result = GuidePipeline(gg, run_id, FakeGuideRouter(),
                           _config(corpus, run_engine_compatibility=True)).run()
    assert result["engine_status"] == "completed"
    assert gg.get_engine_runs(run_id)


def test_engine_failure_has_its_own_status_and_can_be_retried(tmp_path, monkeypatch):
    store, gg, run_id, corpus = _prepare(tmp_path)
    GuidePipeline(gg, run_id, FakeGuideRouter(), _config(corpus)).run()
    application = FastAPI()
    register_guide_generation_routes(application, store, gg, lambda: "u")
    worker = GuideGenerationWorker(store, router_factory=FakeGuideRouter)
    monkeypatch.setattr("fundlex.guide_generation.pipeline.run_engine_compatibility",
                        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("engine boom")))
    with TestClient(application) as client:
        assert client.post(f"/api/guide-generation/runs/{run_id}/engine-compatibility").status_code == 202
        assert worker.run_once() is True
        failed = gg.get_run(run_id)
        assert failed["engine_status"] == "failed"
        assert failed["status"] in {"complete", "complete_with_unresolved"}
        assert (failed.get("payload") or {}).get("engine_error_code")
    monkeypatch.undo()
    with TestClient(application) as client:
        assert client.post(f"/api/guide-generation/runs/{run_id}/engine-compatibility").status_code == 202
        assert worker.run_once() is True
        assert gg.get_run(run_id)["engine_status"] == "completed"
