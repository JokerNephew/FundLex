import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from fundlex.guide_generation.api import public_pipeline_config, register_guide_generation_routes
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.store import RunStore


def test_generation_pagination_is_owner_scoped_unbounded_and_legacy_compatible(tmp_path, monkeypatch):
    monkeypatch.delenv("FUNDLEX_DATABASE_URL", raising=False)
    store = RunStore(tmp_path / "data")
    gg = GuideGenerationStore(store)
    app = FastAPI()
    register_guide_generation_routes(app, store, gg, lambda: "alice")
    now = time.time()
    with store._connect() as db:
        db.executemany("""INSERT INTO gg_runs(id,owner,filename,title,status,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?)""", [
                (f"g{i:03}", "alice", f"法规{i:03}.pdf", f"Regulation {i:03}",
                 "failed" if i == 400 else "queued", now + i, now + i) for i in range(401)]
                + [("private", "bob", "secret.pdf", "secret", "queued", now, now)])
    client = TestClient(app)
    url = "/api/guide-generation/runs"
    legacy = client.get(url, params={"limit": 2}).json()
    assert legacy["total"] == 401
    assert legacy["page"] == 1
    assert legacy["page_size"] == 2
    assert len(legacy["items"]) == 2
    pages = [client.get(url, params={"page": p, "page_size": 200}).json() for p in (1, 2, 3)]
    assert len({item["id"] for page in pages for item in page["items"]}) == 401
    assert all(page["total"] == 401 for page in pages)
    assert all(item["owner"] == "alice" for page in pages for item in page["items"])
    result = client.get(url, params={"page": 1, "page_size": 20, "q": "REGULATION 400", "status": "failed"}).json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == "g400"
    assert client.get(url, params={"q": "secret"}).json()["total"] == 0
    assert client.get(url, params={"q": "%"}).json()["total"] == 0
    for params in ({"page": 0}, {"page_size": 201}, {"page_size": 0}, {"limit": 201}):
        assert client.get(url, params=params).status_code == 422
    corpus = client.get("/api/guide-generation/corpus").json()
    assert corpus["default_corpus_limit"] == 1
    assert "不代表全库核验" in corpus["scope_note"]


def test_default_corpus_scope_is_explicit_bounded_and_server_controlled(monkeypatch):
    monkeypatch.delenv("FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT", raising=False)
    assert public_pipeline_config("{}")["corpus_limit"] == 1
    assert public_pipeline_config('{"corpus_limit":null}')["corpus_limit"] == 1
    assert public_pipeline_config('{"corpus_limit":514}')["corpus_limit"] == 514
    monkeypatch.setenv("FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT", "2")
    assert public_pipeline_config("{}")["corpus_limit"] == 2
    assert public_pipeline_config('{"corpus_limit":1}')["corpus_limit"] == 1
