import json

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from fundlex.guide_generation.api import public_pipeline_config, register_guide_generation_routes
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.store import RunStore


@pytest.mark.parametrize("config", [[], None, 123, "bad", {"corpus_dir": "/etc"},
    {"sample_contract": "/etc/passwd"}, {"soft_max_cost": 1000},
    {"corpus_limit": "2"}, {"corpus_limit": True}, {"path_c_enabled": []},
    {"path_b_max_calls": -1}, {"path_b_batch_chars": {}}, {"model": "x"}])
def test_public_config_rejects_paths_invalid_types_and_spending(config):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        public_pipeline_config(json.dumps(config))
    assert exc.value.status_code == 422


def test_upload_closed_for_success_and_validation_failures(tmp_path, monkeypatch):
    from starlette.datastructures import UploadFile

    monkeypatch.delenv("FUNDLEX_DATABASE_URL", raising=False)
    monkeypatch.setenv("FUNDLEX_GUIDE_CORPUS_DIR", str(tmp_path / "public-corpus"))
    monkeypatch.setenv("FUNDLEX_GUIDE_RUN_MAX_CALLS", "15")
    monkeypatch.setenv("FUNDLEX_GUIDE_RUN_MAX_COST_USD", "0.5")
    store = RunStore(tmp_path / "data")
    gg = GuideGenerationStore(store)
    app = FastAPI()
    register_guide_generation_routes(app, store, gg, lambda: "alice")
    client = TestClient(app)
    closed = []
    original = UploadFile.close

    async def close(self):
        closed.append(self.filename)
        await original(self)

    monkeypatch.setattr(UploadFile, "close", close)
    for filename, data, config, expected in [
        ("bad.txt", b"some text", "{}", 422),
        ("a.pdf", b"", "{}", 422),
        ("a.pdf", b"some text", '{"corpus_dir":"/etc"}', 422),
        ("a.pdf", b"some text", '{"corpus_limit":2}', 201),
    ]:
        before = len(closed)
        response = client.post("/api/guide-generation/runs", files={"file": (filename, data)},
                               data={"config": config})
        assert response.status_code == expected, response.text
        assert len(closed) > before
    run = gg.list_runs("alice")[0]
    assert run["config"]["corpus_dir"] == str(tmp_path / "public-corpus")
    assert run["config"]["soft_max_calls"] == 15
    assert run["config"]["soft_max_cost"] == 0.5
    assert "corpus_dir" not in response.json()["config"]
    assert len(gg.list_runs("alice")) == 1
