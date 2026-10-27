from pathlib import Path
import re
import sys
import time

from fastapi.testclient import TestClient
import pytest

from fundlex.api import create_app
from fundlex.guide_generation.worker import GuideGenerationWorker
from fundlex.model import ModelError
from fundlex.store import Conflict


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_GUIDE_MAX_ATTEMPTS", "3")
    monkeypatch.delenv("FUNDLEX_DATABASE_URL", raising=False)
    monkeypatch.delenv("FUNDLEX_FRONTEND_VERSION", raising=False)
    monkeypatch.delenv("FUNDLEX_FRONTEND_BASE_PATH", raising=False)
    app = create_app(tmp_path / "data")
    gg = app.state.guide_generation
    run = gg.create_run(owner="alice", filename="public.docx", source_type="docx",
                        source_sha256="hash")
    gg.enqueue(run["id"])
    return app, gg, run, TestClient(app)


def test_owner_explicit_resume_is_finite_and_never_complete(setup):
    app, gg, run, client = setup

    def unavailable():
        raise ModelError("MODEL_HTTP_402")

    worker = GuideGenerationWorker(app.state.store, router_factory=unavailable)
    url = f"/api/guide-generation/runs/{run['id']}/resume"
    alice = {"X-FundLex-User": "alice"}
    candidate = gg.get_candidate(run["id"])
    assert client.post(url).status_code == 401
    assert client.post(url, headers=alice).status_code == 409  # queued
    for attempt in range(1, 4):
        assert worker.run_once()
        assert not worker.run_once()  # no automatic paid retry loop
        current = gg.get_run(run["id"])
        assert current["status"] == ("failed" if attempt == 3 else "paused")
        assert current["error_code"] == "MODEL_HTTP_402"
        retry = gg.retry_state(run["id"])
        assert retry == {"attempts": attempt, "max_attempts": 3, "can_resume": attempt < 3}
        assert client.post(url, headers={"X-FundLex-User": "bob"}).status_code == 404
        result = client.post(url, headers=alice)
        assert result.status_code == (409 if attempt == 3 else 202), result.text
        if attempt < 3:
            assert result.json()["status"] == "queued"
            assert client.post(url, headers=alice).status_code == 409
        assert gg.get_candidate(run["id"]) == candidate


def test_terminal_candidate_not_resumable(setup):
    app, gg, run, client = setup
    job = gg.claim()
    gg.finish_job(job["id"], job["fencing_token"], status="completed",
                  run_status="complete", run_stage="COMPLETED")
    response = client.post(f"/api/guide-generation/runs/{run['id']}/resume",
                           headers={"X-FundLex-User": "alice"})
    assert response.status_code == 409
    assert gg.get_run(run["id"])["status"] == "complete"


def test_expired_final_lease_exhausts_without_new_attempt(setup):
    app, gg, run, client = setup
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET attempts=3,status='leased',lease_until=? WHERE run_id=?",
                   (time.time() - 1, run["id"]))
    assert gg.claim() is None
    assert gg.get_run(run["id"])["status"] == "failed"
    assert gg.get_run(run["id"])["error_code"] == "GUIDE_RETRY_LIMIT"


def test_stale_finish_does_not_overwrite_run_or_error(setup):
    app, gg, run, client = setup
    first = gg.claim()
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET lease_until=? WHERE id=?", (time.time() - 1, first["id"]))
    second = gg.claim()
    assert second["fencing_token"] > first["fencing_token"]
    gg.update_run(run["id"], status="running", stage="EXTRACT_REQUIREMENTS", error_code="")
    with pytest.raises(Conflict):
        gg.finish_job(first["id"], first["fencing_token"], status="completed",
                      run_status="complete", run_stage="COMPLETED")
    assert gg.get_run(run["id"])["status"] == "running"
    assert gg.get_run(run["id"])["stage"] == "EXTRACT_REQUIREMENTS"


def test_noncomplete_pipeline_result_never_reported_completed(setup, monkeypatch):
    app, gg, run, client = setup

    class PausedPipeline:
        def __init__(self, *args):
            pass

        def run(self):
            return {"status": "paused"}

    monkeypatch.setattr("fundlex.guide_generation.worker.GuidePipeline", PausedPipeline)
    worker = GuideGenerationWorker(app.state.store, router_factory=lambda: object())
    assert worker.run_once()
    assert gg.get_run(run["id"])["status"] == "failed"
    assert gg.get_run(run["id"])["error_code"] == "GUIDE_RESULT_NOT_COMPLETE"


def test_worker_deployment_caps_bound_persisted_config(setup, monkeypatch):
    app, gg, run, client = setup
    monkeypatch.setenv("FUNDLEX_GUIDE_RUN_MAX_CALLS", "7")
    monkeypatch.setenv("FUNDLEX_GUIDE_RUN_MAX_COST_USD", "0.1")
    gg.update_run(run["id"], payload={"config": {"soft_max_calls": 9999, "soft_max_cost": 99}})

    class CappedPipeline:
        def __init__(self, store, run_id, router, config):
            assert config.soft_max_calls == 7
            assert config.soft_max_cost == 0.1

        def run(self):
            return {"status": "complete_with_unresolved"}

    monkeypatch.setattr("fundlex.guide_generation.worker.GuidePipeline", CappedPipeline)
    worker = GuideGenerationWorker(app.state.store, router_factory=lambda: object())
    assert worker.run_once()
    assert gg.get_run(run["id"])["status"] == "complete_with_unresolved"


def test_v1_cache_busting_and_legacy_generation_redirect(setup, monkeypatch):
    app, gg, run, client = setup
    first = client.get("/")
    assert first.status_code == 200
    for asset in ("app.css", "app.js", "compare.css", "compare.js", "workspace.js",
                  "guide_generation.js", "guide_generation.css"):
        assert re.search(r"/static/" + re.escape(asset) + r"\?v=[a-f0-9]{16}", first.text)
    before = re.search(r"workspace\.js\?v=([a-f0-9]+)", first.text).group(1)
    original = Path.read_bytes

    def changed_asset(path):
        value = original(path)
        return value + b"/* changed */" if path.name == "workspace.js" else value

    monkeypatch.setattr(Path, "read_bytes", changed_asset)
    second = client.get("/")
    after = re.search(r"workspace\.js\?v=([a-f0-9]+)", second.text).group(1)
    assert before != after
    assert "no-store" in first.headers["cache-control"]
    redirect = client.get("/guide-generation", follow_redirects=False)
    assert redirect.status_code == 307
    assert redirect.headers["location"] == "/#generation"


def test_generation_redirect_and_assets_respect_proxy_prefix(setup, tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_FRONTEND_BASE_PATH", "/test")
    client = TestClient(create_app(tmp_path / "prefixed"))
    html = client.get("/").text
    for asset in ("workspace.js", "guide_generation.js", "guide_generation.css"):
        assert f'/test/static/{asset}?v=' in html
    assert client.get("/guide-generation", follow_redirects=False).headers["location"] == "/test/#generation"


def test_missing_optional_generation_does_not_break_app(setup, tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "fundlex.guide_generation.store", None)
    app = create_app(tmp_path / "without-module")
    assert app.state.guide_generation is None
    client = TestClient(app)
    response = client.get("/api/workspace/tasks", headers={"X-FundLex-User": "alice"})
    assert response.status_code == 200
    assert response.json()["total"] == 0
