from datetime import date, datetime, timedelta, timezone
import time

from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
import pytest

from fundlex.compare.store import CompareStore
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.store import RunStore
from fundlex.tasks import TaskStore
from fundlex.workspace import register_workspace_routes, workspace_tasks


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("FUNDLEX_DATABASE_URL", raising=False)
    store = RunStore(tmp_path / "data")
    tasks = TaskStore(store)
    compare = CompareStore(store)
    gg = GuideGenerationStore(store)
    gg.ensure_schema()
    app = FastAPI()

    def user(x_fundlex_user: str = Header("")):
        if not x_fundlex_user:
            raise HTTPException(401)
        return x_fundlex_user

    register_workspace_routes(app, store, user)
    return store, tasks, compare, gg, TestClient(app)


def revision(tasks, owner="alice", name="修改合同"):
    return tasks.create(owner, name, {"version": "v", "sha256": "s"},
                        [{"client_id": "f", "name": "contract.docx", "size": 20}])


def generation(gg, owner="alice", name="销售费用法规"):
    return gg.create_run(owner=owner, filename=name + ".pdf", title=name,
                         source_type="pdf", source_sha256="s")


def comparison(compare, owner="alice", name="比对合同"):
    return compare.create(owner, name, [{"client_pair_id": "p", "left": {
        "client_id": "l", "name": "l.docx", "size": 10}, "right": {
        "client_id": "r", "name": "r.docx", "size": 10}}])


def test_owner_isolation_units_and_real_attention(setup):
    store, tasks, compare, gg, client = setup
    revision(tasks)
    comparison(compare)
    run = generation(gg)
    gg.update_run(run["id"], status="complete", stage="COMPLETED")
    revision(tasks, "bob", "private")
    comparison(compare, "bob", "private")
    generation(gg, "bob", "private")
    assert client.get("/api/workspace/tasks").status_code == 401
    result = client.get("/api/workspace/tasks", headers={"X-FundLex-User": "alice"}).json()
    assert result["total"] == 3
    assert {i["scale"]["unit"] for i in result["items"]} == {"份合同", "组合同", "份法规"}
    assert all("private" not in i["name"] for i in result["items"])
    gen = next(i for i in result["items"] if i["kind"] == "generation")
    assert gen["status"] == "complete"
    assert gen["status_group"] == "attention"
    assert {a["code"] for a in gen["attention"]} == {"candidate_review"}


def test_unbounded_owner_counts_and_pagination(setup):
    store, tasks, compare, gg, client = setup
    # More than the old API's 200 record ceiling; no per-source truncation.
    with store._connect() as db:
        now = time.time()
        db.executemany("""INSERT INTO gg_runs(id,owner,filename,title,source_type,source_sha256,
            status,stage,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            [(f"g{i:04}", "alice", "reg.pdf", f"Regulation {i:04}", "pdf", "s", "queued",
              "QUEUED", now, now) for i in range(411)])
    query = {"kind": "generation", "page": 3, "page_size": 200}
    result = client.get("/api/workspace/tasks", params=query,
                        headers={"X-FundLex-User": "alice"}).json()
    assert result["total"] == 411
    assert len(result["items"]) == 11
    assert result["stats"]["active"] == 411
    query.update(q="Regulation 0410", page=1)
    narrowed = client.get("/api/workspace/tasks", params=query,
                          headers={"X-FundLex-User": "alice"}).json()
    assert narrowed["total"] == 1
    assert narrowed["stats"] == result["stats"]
    pages = [workspace_tasks(store, "alice", page=p, page_size=200) for p in (1, 2, 3)]
    assert len({i["id"] for p in pages for i in p["items"]}) == 411


def test_search_dates_status_sort_and_owner_wide_stats(setup):
    store, tasks, compare, gg, client = setup
    a, b, c = [generation(gg, name=n) for n in ("Alpha销售", "beta销售", "other")]
    gg.update_run(a["id"], status="complete", stage="COMPLETED")
    gg.update_candidate(a["id"], status="published")
    gg.update_run(b["id"], status="failed", stage="FAILED")
    old = datetime(2026, 1, 2, tzinfo=timezone.utc).timestamp()
    with store._connect() as db:
        db.execute("UPDATE gg_runs SET created_at=?,updated_at=? WHERE id=?", (old, old, c["id"]))
        db.execute("UPDATE gg_candidate_guides SET updated_at=? WHERE run_id=?", (old, c["id"]))
    all_rows = workspace_tasks(store, "alice")
    assert all_rows["stats"] == {"active": 1, "attention": 1, "recent_completed": 1, "recent_window_days": 7}
    today_utc = datetime.now(timezone.utc).date()
    result = workspace_tasks(store, "alice", q="销售", status="completed", sort="name",
                             date_from=today_utc, date_to=today_utc)
    assert result["total"] == 1
    assert result["items"][0]["id"] == a["id"]
    assert result["stats"] == all_rows["stats"]
    assert workspace_tasks(store, "alice", q="ALPHA")["total"] == 1
    assert workspace_tasks(store, "alice", date_from=date(2026, 1, 2), date_to=date(2026, 1, 2))["total"] == 1
    for params in ({"status": "succeeded"}, {"page_size": 201}, {"kind": "bad"},
                   {"date_from": "bad"}, {"date_from": "2026-10-27", "date_to": "2026-10-26"},
                   {"date_to": "9999-12-31"}):
        assert client.get("/api/workspace/tasks", params=params,
                          headers={"X-FundLex-User": "alice"}).status_code == 422


def test_optional_generation_absent_and_database_failure_not_silenced(tmp_path, monkeypatch):
    monkeypatch.delenv("FUNDLEX_DATABASE_URL", raising=False)
    store = RunStore(tmp_path / "without-generation")
    tasks = TaskStore(store)
    CompareStore(store)
    revision(tasks)
    result = workspace_tasks(store, "alice", generation_available=False)
    assert result["total"] == 1
    assert result["items"][0]["kind"] == "revision"
    # It is not valid to suppress a broken installed source as an empty list.
    with pytest.raises(Exception):
        workspace_tasks(store, "alice", generation_available=True)


def test_revision_failure_incomplete_and_child_updated_at(setup):
    store, tasks, compare, gg, client = setup
    task = revision(tasks)
    with store._connect() as db:
        db.execute("UPDATE tasks SET paused=1,sealed=1 WHERE id=?", (task["id"],))
    result = workspace_tasks(store, "alice")["items"][0]
    assert result["status"] == "paused"
    assert {a["code"] for a in result["attention"]} == {"paused", "upload_pending"}
    task2 = comparison(compare)
    with store._connect() as db:
        db.execute("UPDATE compare_tasks SET status='completed' WHERE id=?", (task2["id"],))
        db.execute("UPDATE compare_pairs SET status='failed' WHERE task_id=?", (task2["id"],))
    result = workspace_tasks(store, "alice", kind="compare")["items"][0]
    assert result["status"] == "completed"
    assert result["status_group"] == "attention"
    assert result["attention"][0]["code"] == "failed"


def test_recent_completed_window_is_seven_days(setup):
    store, tasks, compare, gg, client = setup
    now = datetime.now(timezone.utc)
    for days in (2, 8):
        run = generation(gg, name=f"completed {days}")
        gg.update_run(run["id"], status="complete")
        gg.update_candidate(run["id"], status="approved")
        then = (now - timedelta(days=days)).timestamp()
        with store._connect() as db:
            db.execute("UPDATE gg_runs SET updated_at=? WHERE id=?", (then, run["id"]))
            db.execute("UPDATE gg_candidate_guides SET updated_at=? WHERE run_id=?", (then, run["id"]))
    assert workspace_tasks(store, "alice", now=now)["stats"]["recent_completed"] == 1


def test_comparison_completed_and_incomplete_are_distinct(setup):
    store, tasks, compare, gg, client = setup
    complete = comparison(compare, name="complete")
    incomplete = comparison(compare, name="incomplete")
    with store._connect() as db:
        for task, status in ((complete, "succeeded"), (incomplete, "incomplete")):
            db.execute("UPDATE compare_tasks SET status='completed' WHERE id=?", (task["id"],))
            db.execute("UPDATE compare_pairs SET status=? WHERE task_id=?", (status, task["id"]))
    rows = workspace_tasks(store, "alice", status="completed")
    assert rows["total"] == 1
    assert rows["items"][0]["id"] == complete["id"]
    assert rows["stats"]["recent_completed"] == 1
    assert rows["stats"]["attention"] == 1
