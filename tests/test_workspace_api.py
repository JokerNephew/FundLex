"""Owner-scoped workspace aggregation API tests.

The V1 home page calls ``/api/workspace/tasks``.  These checks use the real
TaskStore/CompareStore/GuideGenerationStore schemas and the password identity
adapter, so a missing table, a wrong owner column or a response-contract drift
fails here before a release candidate is staged.
"""
from __future__ import annotations

import io
import time
from datetime import datetime, timezone

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex.api import create_app


@pytest.fixture(autouse=True)
def _isolated_auth_env(monkeypatch):
    for name in ("FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL",
                 "FUNDLEX_AUTH_MODE", "FUNDLEX_DATA_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")


@pytest.fixture
def app_client(tmp_path):
    application = create_app(tmp_path)
    application.state.users.create_user("alice", "alice-password", "Alice")
    application.state.users.create_user("bob", "bob-password", "Bob")
    client = TestClient(application)
    alice = client.post("/api/auth/login", json={
        "username": "alice", "password": "alice-password"}).json()
    bob = client.post("/api/auth/login", json={
        "username": "bob", "password": "bob-password"}).json()
    return application, client, alice, bob


def _docx_bytes(label: str) -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def _revision(application, owner, name, *, job_status="succeeded",
              delivery_status="complete", when=None, upload_status="accepted"):
    data = _docx_bytes(name)
    task = application.state.tasks.create(
        owner, name, {"version": "v1", "sha256": "a" * 64},
        [{"client_id": "file-" + name, "name": name + ".docx", "size": len(data)}],
        engine_id="recall_first")
    application.state.tasks.uploads(owner, task["id"], [
        {"client_id": "file-" + name, "name": name + ".docx", "data": data}])
    stamp = time.time() if when is None else when
    with application.state.store._connect() as db:
        db.execute("UPDATE tasks SET created_at=?,updated_at=? WHERE id=?",
                   (stamp, stamp, task["id"]))
        db.execute("UPDATE task_files SET upload_status=? WHERE task_id=?",
                   (upload_status, task["id"]))
        db.execute("""UPDATE documents SET status=?,delivery_status=?,qualification_status=?,
                   updated_at=? WHERE id=(SELECT document_id FROM task_files
                   WHERE task_id=? AND document_id IS NOT NULL)""",
                   (job_status, delivery_status, "applicable", stamp, task["id"]))
    return task["id"]


def _compare(application, owner, name, *, status="running", pair_statuses=("pending",),
             when=None):
    task = application.state.compare_store.create(owner, name, [{
        "client_pair_id": "pair-" + name, "label": "pair",
        "left": {"client_id": "left-" + name, "name": "left.docx", "size": 10},
        "right": {"client_id": "right-" + name, "name": "right.docx", "size": 10},
    }])
    # The compare store has one pair per client_pair_id; create additional pair
    # rows directly for the aggregation fixture when more than one is needed.
    if len(pair_statuses) > 1:
        with application.state.store._connect() as db:
            base = db.execute("SELECT * FROM compare_pairs WHERE task_id=?",
                              (task["id"],)).fetchone()
            for index in range(1, len(pair_statuses)):
                db.execute("""INSERT INTO compare_pairs
                    (id,task_id,ordinal,client_pair_id,label,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)""",
                           ("pair-%s-%s" % (task["id"], index), task["id"], index,
                            "pair-%s-%s" % (task["id"], index), "pair",
                            "pending", base["created_at"], base["updated_at"]))
    stamp = time.time() if when is None else when
    with application.state.store._connect() as db:
        db.execute("UPDATE compare_tasks SET status=?,created_at=?,updated_at=? WHERE id=?",
                   (status, stamp, stamp, task["id"]))
        for index, pair_status in enumerate(pair_statuses):
            db.execute("""UPDATE compare_pairs SET status=?,updated_at=?
                WHERE task_id=? AND ordinal=?""", (pair_status, stamp, task["id"], index))
    return task["id"]


def _generation(application, owner, name, *, status="complete_with_unresolved",
                candidate_status="draft", when=None, filename=None):
    run = application.state.guide_generation_store.create_run(
        owner=owner, filename=filename or (name + ".docx"), source_type="docx",
        source_sha256="b" * 64, title=name)
    stamp = time.time() if when is None else when
    with application.state.store._connect() as db:
        db.execute("UPDATE gg_runs SET status=?,stage=?,created_at=?,updated_at=? WHERE id=?",
                   (status, "FINALIZE_GUIDE", stamp, stamp, run["id"]))
        db.execute("UPDATE gg_candidate_guides SET status=?,updated_at=? WHERE run_id=?",
                   (candidate_status, stamp, run["id"]))
    return run["id"]


def _headers(identity):
    return {"Authorization": "Bearer " + identity["token"]}


def test_workspace_requires_authentication_and_is_not_the_spa_fallback(app_client):
    _, client, _, _ = app_client
    response = client.get("/api/workspace/tasks")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "AUTHENTICATION_REQUIRED"
    bad = client.get("/api/workspace/tasks", headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 401
    assert bad.headers["content-type"].startswith("application/json")


def test_empty_workspace_and_query_validation(app_client):
    _, client, alice, _ = app_client
    response = client.get("/api/workspace/tasks", headers=_headers(alice))
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [], "total": 0, "page": 1, "page_size": 20,
        "stats": {"active": 0, "attention": 0, "recent_completed": 0,
                  "recent_window_days": 7},
    }
    assert client.get("/api/workspace/tasks?page_size=100",
                      headers=_headers(alice)).status_code == 200
    for query in ("page=0", "page_size=101", "kind=unknown",
                  "status=unknown", "date_from=2026-10-20&date_to=2026-10-10",
                  "date_to=9999-12-31"):
        assert client.get("/api/workspace/tasks?" + query,
                          headers=_headers(alice)).status_code == 422


def test_aggregation_owner_isolation_filters_pagination_and_contract(app_client):
    application, client, alice, bob = app_client
    alice_owner, bob_owner = alice["user"]["id"], bob["user"]["id"]
    now = time.time()
    recent = now - 3600
    old = now - 10 * 86400

    completed = _revision(application, alice_owner, "Alpha completed", when=recent)
    failed = _revision(application, alice_owner, "Beta failed", job_status="failed",
                       delivery_status="not_generated", when=recent)
    compared = _compare(application, alice_owner, "Gamma compare", when=recent + 1,
                        pair_statuses=("succeeded", "pending"))
    generated = _generation(application, alice_owner, "Delta generation", when=recent + 2,
                            filename="hidden-regulation-file.docx")
    other = _revision(application, bob_owner, "Bob only", when=old)

    response = client.get("/api/workspace/tasks", headers=_headers(alice))
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert {item["id"] for item in body["items"]} == {completed, failed, compared, generated}
    assert body["stats"] == {"active": 1, "attention": 2, "recent_completed": 1,
                             "recent_window_days": 7}
    by_kind = {item["kind"]: item for item in body["items"]}
    items_by_id = {item["id"]: item for item in body["items"]}
    assert set(by_kind) == {"revision", "compare", "generation"}
    assert by_kind["generation"]["candidate_status"] == "draft"
    assert {note["code"] for note in by_kind["generation"]["attention"]} == {
        "complete_with_unresolved", "candidate_review"}
    assert items_by_id[failed]["attention"][0]["code"] == "failed"
    assert items_by_id[completed]["attention"] == []
    assert items_by_id[completed]["status_group"] == "completed"
    assert items_by_id[failed]["status_group"] == "attention"
    assert by_kind["compare"]["progress"] == {"total": 2, "completed": 1}
    assert by_kind["compare"]["scale"] == {"value": 2, "unit": "组合同"}
    assert by_kind["generation"]["scale"] == {"value": 1, "unit": "份法规"}

    # Every item is metadata only, including ISO timestamps and status groups.
    for item in body["items"]:
        assert item["created_at"].endswith("+00:00")
        assert item["updated_at"].endswith("+00:00")
        assert item["status_group"] in {"active", "attention", "completed"}
        assert item["kind"] in {"revision", "compare", "generation"}

    bob_items = client.get("/api/workspace/tasks", headers=_headers(bob)).json()
    assert bob_items["total"] == 1
    assert {item["id"] for item in bob_items["items"]} == {other}
    assert not ({item["name"] for item in bob_items["items"]} & {
        "Alpha completed", "Beta failed", "Gamma compare", "Delta generation"})

    filtered = client.get("/api/workspace/tasks?kind=revision",
                          headers=_headers(alice)).json()
    assert filtered["total"] == 2 and {item["kind"] for item in filtered["items"]} == {"revision"}
    attention = client.get("/api/workspace/tasks?status=attention",
                           headers=_headers(alice)).json()
    assert attention["total"] == 2
    assert {item["id"] for item in attention["items"]} == {failed, generated}
    completed_only = client.get("/api/workspace/tasks?status=completed",
                                headers=_headers(alice)).json()
    assert completed_only["total"] == 1 and completed_only["items"][0]["id"] == completed
    searched = client.get("/api/workspace/tasks?q=alpha", headers=_headers(alice)).json()
    assert searched["total"] == 1 and searched["items"][0]["id"] == completed
    by_filename = client.get("/api/workspace/tasks?q=hidden-regulation",
                             headers=_headers(alice)).json()
    assert by_filename["total"] == 1 and by_filename["items"][0]["id"] == generated
    assert by_filename["items"][0]["filename"] == "hidden-regulation-file.docx"

    today = datetime.now(timezone.utc).date()
    old_day = datetime.fromtimestamp(old, timezone.utc).date()
    if old_day < today:
        dated = client.get(
            "/api/workspace/tasks?date_from=%s&date_to=%s" % (old_day, old_day),
            headers=_headers(alice)).json()
        assert dated["total"] == 0  # old belongs to Bob, not Alice
        bob_dated = client.get(
            "/api/workspace/tasks?date_from=%s&date_to=%s" % (old_day, old_day),
            headers=_headers(bob)).json()
        assert bob_dated["total"] == 1 and bob_dated["items"][0]["id"] == other

    first = client.get("/api/workspace/tasks?page=1&page_size=2",
                       headers=_headers(alice)).json()
    second = client.get("/api/workspace/tasks?page=2&page_size=2",
                        headers=_headers(alice)).json()
    assert first["total"] == second["total"] == 4
    assert len(first["items"]) == len(second["items"]) == 2
    assert not ({item["id"] for item in first["items"]} &
                {item["id"] for item in second["items"]})
    assert {item["id"] for item in first["items"] + second["items"]} == {
        completed, failed, compared, generated}
    named = client.get("/api/workspace/tasks?sort=name", headers=_headers(alice)).json()
    assert [item["name"] for item in named["items"]] == sorted(
        ["Alpha completed", "Beta failed", "Gamma compare", "Delta generation"],
        key=str.casefold)
    newest = client.get("/api/workspace/tasks?sort=created_desc",
                        headers=_headers(alice)).json()
    assert newest["items"][0]["id"] == generated
    # Stats are owner-wide and are not narrowed by list filters.
    assert newest["stats"]["active"] == 1


def test_workspace_static_entry_contract(app_client):
    import shutil
    import subprocess
    from pathlib import Path

    _, client, alice, _ = app_client
    assert client.get("/static/workspace.js").status_code == 200
    assert client.get("/api/workspace/tasks", headers=_headers(alice)).status_code == 200
    frontend = Path(__file__).resolve().parents[1] / "frontend"
    source = (frontend / "workspace.js").read_text(encoding="utf-8")
    assert "/api/workspace/tasks" in source
    for element in ("workspace-task-rows", "workspace-active", "workspace-attention",
                    "workspace-completed", "workspace-pagination", "workspace-refresh",
                    "workspace-search", "workspace-status", "workspace-sort",
                    "workspace-date-from", "workspace-date-to"):
        assert element in source
    # The script is an entry point only when the V1 shell includes it.  A future
    # merge that copies the workspace markup must also copy the script tag.
    shell = frontend / "compare.html"
    if shell.is_file():
        html = shell.read_text(encoding="utf-8")
        if "view-workspace" in html or "data-workspace-open" in html:
            assert '<script src="/static/workspace.js"' in html
    if shutil.which("node"):
        checked = subprocess.run(["node", "--check", str(frontend / "workspace.js")],
                                 text=True, capture_output=True, timeout=20)
        assert checked.returncode == 0, checked.stderr


def test_completed_filter_is_the_recent_metric_not_all_history(app_client):
    application, client, alice, _ = app_client
    now = time.time()
    recent = _revision(application, alice["user"]["id"], "Recent completed", when=now - 60)
    old = _revision(application, alice["user"]["id"], "Old completed", when=now - 30 * 86400)
    body = client.get("/api/workspace/tasks", headers=_headers(alice)).json()
    assert body["total"] == 2
    assert body["stats"]["recent_completed"] == 1
    completed = client.get("/api/workspace/tasks?status=completed",
                           headers=_headers(alice)).json()
    assert completed["total"] == 1
    assert completed["items"][0]["id"] == recent
    assert old not in {item["id"] for item in completed["items"]}


def test_backend_query_error_is_not_masked_as_an_empty_workspace(app_client):
    application, _, alice, _ = app_client
    with application.state.store._connect() as db:
        db.execute("DROP TABLE gg_runs")
    strict = TestClient(application, raise_server_exceptions=False)
    response = strict.get("/api/workspace/tasks", headers=_headers(alice))
    assert response.status_code == 500
    assert response.json()["error_code"] == "INTERNAL_ERROR"
