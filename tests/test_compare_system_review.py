"""Adversarial system checks from independent compare review.

Real MySQL checks run only with FUNDLEX_COMPARE_MYSQL_TEST_URL pointing at a
disposable database. They drop only the four compare tables in that database.
Never point this variable at a production/shared database.
"""
from __future__ import annotations

import io
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.compare.service import CompareService
from fundlex.compare.store import CompareStore
from fundlex.compare.worker import CompareWorker
from fundlex.db import Database
from fundlex.store import Conflict, RunStore


def docx_bytes(text="left"):
    out = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(out)
    return out.getvalue()


def manifest(left, right, *, count=1):
    return [dict(client_pair_id=f"p{i}", label=f"Pair {i}",
                 left=dict(client_id=f"l{i}", name="a.docx", size=len(left)),
                 right=dict(client_id=f"r{i}", name="b.docx", size=len(right)))
            for i in range(count)]


def queued_pair(store, *, count=1):
    left, right = docx_bytes("管理费为0.40%。"), docx_bytes("管理费为0.30%。")
    task = store.create("alice", "review", manifest(left, right, count=count))
    store.upload("alice", task["id"], [
        dict(client_id=f"{side}{i}", name=name, data=data)
        for i in range(count) for side, name, data in (("l", "a.docx", left), ("r", "b.docx", right))
    ])
    store.seal("alice", task["id"])
    return task


def result_for(store, pair_id):
    files = {item["side"]: item for item in store.pair_inputs(pair_id)}
    return CompareService().compare(
        store.store.object_path(files["left"]["object_key"]),
        store.store.object_path(files["right"]["object_key"]),
        left_filename="a.docx", right_filename="b.docx")


def test_idempotent_create_has_one_winner_under_concurrency(tmp_path, monkeypatch):
    monkeypatch.delenv("FUNDLEX_DATABASE_URL", raising=False)
    store = CompareStore(RunStore(tmp_path))
    a, b = docx_bytes("A"), docx_bytes("B")
    barrier = threading.Barrier(8)

    def create(_):
        barrier.wait(timeout=10)
        return store.create("alice", "one request", manifest(a, b), "same-request")["id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        ids = list(pool.map(create, range(8)))
    assert len(set(ids)) == 1
    assert len(store.list("alice")) == 1


def test_expired_worker_cannot_finish_retry_or_heartbeat(tmp_path):
    store = CompareStore(RunStore(tmp_path))
    queued_pair(store)
    first = store.claim()
    result = result_for(store, first["id"])
    with store._connect() as db:
        db.execute("UPDATE compare_pairs SET lease_until=0 WHERE id=?", (first["id"],))
    with pytest.raises(Conflict):
        store.finish(first["id"], first["fencing_token"], result)
    with pytest.raises(Conflict):
        store.retry(first["id"], first["fencing_token"], "TRANSIENT")
    with pytest.raises(Conflict):
        store.heartbeat(first["id"], first["fencing_token"])
    newer = store.claim()
    assert newer["id"] == first["id"] and newer["fencing_token"] > first["fencing_token"]
    with pytest.raises(Conflict):
        store.finish(first["id"], first["fencing_token"], result)
    store.finish(newer["id"], newer["fencing_token"], result)


@pytest.mark.parametrize("corruption", ["missing", "same-size-change"])
def test_input_integrity_failure_is_pair_local(tmp_path, corruption):
    store = CompareStore(RunStore(tmp_path))
    task = queued_pair(store, count=2)
    pair_id = task["pairs"][0]["id"]
    source = store.store.object_path(store.pair_inputs(pair_id)[0]["object_key"])
    if corruption == "missing":
        source.unlink()
    else:
        data = source.read_bytes()
        source.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    worker = CompareWorker(store)
    assert worker.run_once() and worker.run_once() and not worker.run_once()
    final = store.get("alice", task["id"])
    assert final["status"] == "completed"
    assert final["counts"]["failed"] == 1 and final["counts"]["succeeded"] == 1
    assert final["pairs"][0]["error_code"] == "COMPARE_INPUT_INTEGRITY_FAILED"


def test_rejected_result_coordinates_never_become_success(tmp_path):
    store = CompareStore(RunStore(tmp_path))
    queued_pair(store)
    job = store.claim()
    result = result_for(store, job["id"])
    result["diffs"][0]["left"]["block_id"] = "BOGUS"
    result["diffs"][0]["left_spans"][0]["block_id"] = "BOGUS"
    with pytest.raises(ValueError, match="COMPARE_RESULT_INVALID"):
        store.finish(job["id"], job["fencing_token"], result)
    assert store.get_pair("alice", job["id"])["status"] == "leased"


def test_result_shape_requires_type_specific_spans(tmp_path):
    store = CompareStore(RunStore(tmp_path))
    task = queued_pair(store)
    job = store.claim()
    result = result_for(store, job["id"])
    result["diffs"] = [{"id": "D0001", "type": "modify"}]
    result["summary"] = {"total": 1, "modify": 1, "insert": 0, "delete": 0}
    with pytest.raises(ValueError, match="COMPARE_RESULT_INVALID"):
        store.finish(job["id"], job["fencing_token"], result)
    assert store.get_pair("alice", job["id"])["status"] == "leased"


def test_password_routes_deny_foreign_and_revoked_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    app = create_app(tmp_path)
    alice = app.state.users.create_user("alice", "alice-test-password", "Alice")
    app.state.users.create_user("bob", "bob-test-password", "Bob")
    client = TestClient(app)

    def login(name):
        token = client.post("/api/auth/login", json={"username": name, "password": f"{name}-test-password"}).json()["token"]
        return {"Authorization": f"Bearer {token}"}

    ah, bh = login("alice"), login("bob")
    a, b = docx_bytes("A"), docx_bytes("B")
    task = client.post("/api/compare/tasks", headers=ah,
                       json={"name": "secret", "pairs": manifest(a, b)}).json()
    tid, pid = task["id"], task["pairs"][0]["id"]
    for path in (f"/api/compare/tasks/{tid}", f"/api/compare/tasks/{tid}/pairs",
                 f"/api/compare/pairs/{pid}", f"/api/compare/pairs/{pid}/view"):
        assert client.get(path, headers=bh).status_code == 404
        assert client.get(path, headers={"X-FundLex-User": alice["id"]}).status_code == 401
    assert client.post(f"/api/compare/tasks/{tid}/seal", headers=bh).status_code == 404
    assert client.post(f"/api/compare/tasks/{tid}/uploads", headers=bh,
                       data={"client_ids": '["l0"]'}, files={"files": ("a.docx", a)}).status_code == 404
    assert client.get("/api/compare/tasks", headers=bh).json()["total"] == 0
    app.state.users.set_disabled(alice["id"], True)
    assert client.get("/api/compare/tasks", headers=ah).status_code == 401


def test_view_fails_closed_when_source_or_result_object_changes(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    app = create_app(tmp_path)
    store = app.state.compare_store
    task = queued_pair(store)
    assert CompareWorker(store).run_once()
    pid = task["pairs"][0]["id"]
    client = TestClient(app)
    path = f"/api/compare/pairs/{pid}/view"
    headers = {"X-FundLex-User": "alice"}
    assert client.get(path, headers=headers).status_code == 200
    source = store.store.object_path(store.pair_inputs(pid)[0]["object_key"])
    data = source.read_bytes()
    source.write_bytes(bytes([data[0] ^ 1]) + data[1:])
    response = client.get(path, headers=headers)
    assert response.status_code == 409 and response.json()["detail"] == "COMPARE_INPUT_INTEGRITY_FAILED"
    source.write_bytes(data)
    with store._connect() as db:
        artifact = db.execute("SELECT object_key FROM compare_artifacts WHERE pair_id=?", (pid,)).fetchone()
    store.store.object_path(artifact["object_key"]).unlink()
    assert client.get(path, headers=headers).status_code == 409


MYSQL_URL = os.environ.get("FUNDLEX_COMPARE_MYSQL_TEST_URL", "").strip()


@pytest.fixture
def mysql_store(tmp_path):
    if not MYSQL_URL:
        pytest.skip("FUNDLEX_COMPARE_MYSQL_TEST_URL is not configured")
    with Database(MYSQL_URL).connect() as db:
        for table in ("compare_selection_artifacts", "compare_selection_drafts",
                      "compare_artifacts", "compare_pair_files", "compare_pairs", "compare_tasks"):
            db.execute(f"DROP TABLE IF EXISTS {table}")
    yield CompareStore(RunStore(tmp_path, database_url=MYSQL_URL))


def test_mysql_long_result_identity_idempotency_and_single_claim(mysql_store):
    store = mysql_store
    left, right = docx_bytes("left"), docx_bytes("right")
    task = store.create("alice", "mysql", manifest(left, right), "same")
    assert store.create("alice", "mysql", manifest(left, right), "same")["id"] == task["id"]
    store.upload("alice", task["id"], [dict(client_id="l0", name="a.docx", data=left),
                                        dict(client_id="r0", name="b.docx", data=right)])
    store.seal("alice", task["id"])
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = list(pool.map(lambda _: store.claim(), range(2)))
    job = next(j for j in jobs if j)
    assert sum(j is not None for j in jobs) == 1
    result = result_for(store, job["id"])
    result["diagnostics"]["long_payload"] = "payload" * 2000
    store.finish(job["id"], job["fencing_token"], result)
    pair = store.get_pair("alice", job["id"])
    assert pair["status"] == "succeeded"
    assert pair["result"]["diagnostics"]["long_payload"] == "payload" * 2000


@pytest.mark.parametrize("operation", ["finish", "retry"])
def test_mysql_stale_snapshot_cannot_overwrite_newer_fence(mysql_store, operation):
    """Pause after the old transaction's read; a competing lease must not win.

    Before the fix the SELECT did not lock, so the new worker reclaimed the row
    and old finish/retry then wrote through its token1 snapshot over token2.
    """
    store = mysql_store
    queued_pair(store)
    first = store.claim()
    result = result_for(store, first["id"])
    original_connect = store._connect
    old_read, resume = threading.Event(), threading.Event()
    old_name = "compare-old-worker"

    class PausingConnection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, params=()):
            cursor = self.db.execute(sql, params)
            if (threading.current_thread().name == old_name
                    and sql.startswith("SELECT * FROM compare_pairs WHERE id=")):
                old_read.set()
                assert resume.wait(5), "review did not release old worker"
            return cursor

        def __getattr__(self, name):
            return getattr(self.db, name)

    @contextmanager
    def wrapped_connect():
        with original_connect() as db:
            yield PausingConnection(db)

    store._connect = wrapped_connect
    old_errors, newer_jobs = [], []

    def old_work():
        try:
            if operation == "finish":
                store.finish(first["id"], first["fencing_token"], result)
            else:
                store.retry(first["id"], first["fencing_token"], "REVIEW_TRANSIENT")
        except Exception as exc:
            old_errors.append(exc)

    def newer_work():
        # Set expiry with a concurrent writer: FOR UPDATE must block this until
        # old transaction commits.  Keep it conditional so a completed/retry
        # state is never revived merely by the regression harness.
        with original_connect() as db:
            db.execute("UPDATE compare_pairs SET lease_until=0 WHERE id=? AND status IN ('leased','running')",
                       (first["id"],))
        newer_jobs.append(store.claim())

    old_thread = threading.Thread(target=old_work, name=old_name)
    newer_thread = threading.Thread(target=newer_work, name="compare-new-worker")
    old_thread.start()
    assert old_read.wait(5)
    newer_thread.start()
    # Waiting for a blocked writer is the behavior under test. An Event wait
    # permits the other thread to run without spinning or a long polling delay.
    newer_thread.join(timeout=0.2)
    assert newer_thread.is_alive(), "old worker's SELECT did not lock its lease"
    resume.set()
    old_thread.join(timeout=5)
    newer_thread.join(timeout=5)
    assert not old_thread.is_alive() and not newer_thread.is_alive()
    assert old_errors == []
    assert newer_jobs == [None]
    final = store.get_pair("alice", first["id"])
    assert final["status"] == ("succeeded" if operation == "finish" else "retry_wait")


def test_mysql_exhausted_cleanup_cannot_overwrite_concurrent_heartbeat(mysql_store, monkeypatch):
    """Cleanup's old snapshot must not erase a lease renewed after that read.

    The synchronization establishes an InnoDB consistent read before the
    heartbeat commits.  A plain SELECT would keep seeing the expired version
    and its unconditional UPDATE would mark the renewed pair failed.  FOR
    UPDATE must instead read the current version and skip cleanup.
    """
    store = mysql_store
    queued_pair(store)
    first = store.claim()
    pair_id = first["id"]
    real_now = time.time()
    cleanup_now = real_now + 20
    with store._connect() as db:
        db.execute("UPDATE compare_pairs SET status='running',lease_until=? WHERE id=?",
                   (real_now + 5, pair_id))

    snapshot_ready = threading.Event()
    heartbeat_done = threading.Event()
    release_cleanup = threading.Event()
    original_connect = store._connect
    old_name = "compare-exhausted-cleanup"

    class PausingConnection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, params=()):
            if (threading.current_thread().name == old_name
                    and sql.startswith("SELECT * FROM compare_pairs WHERE status IN")):
                # Establish the transaction's non-locking snapshot before the
                # heartbeat changes the row.  FOR UPDATE remains a current read.
                self.db.execute("SELECT * FROM compare_pairs WHERE id=?", (pair_id,)).fetchone()
                snapshot_ready.set()
                assert heartbeat_done.wait(5), "heartbeat did not commit"
                assert release_cleanup.wait(5), "review did not release cleanup"
            return self.db.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self.db, name)

    @contextmanager
    def wrapped_connect():
        with original_connect() as db:
            yield PausingConnection(db)

    def now_for_thread():
        return cleanup_now if threading.current_thread().name == old_name else time.time()

    monkeypatch.setattr("fundlex.compare.store._now", now_for_thread)
    store._connect = wrapped_connect
    cleanup_result, heartbeat_errors = [], []

    def cleanup():
        try:
            cleanup_result.append(store.claim(max_attempts=1))
        except Exception as exc:
            cleanup_result.append(exc)

    def heartbeat():
        try:
            store.heartbeat(pair_id, first["fencing_token"], lease_seconds=300)
        except Exception as exc:
            heartbeat_errors.append(exc)
        finally:
            heartbeat_done.set()

    cleanup_thread = threading.Thread(target=cleanup, name=old_name)
    heartbeat_thread = threading.Thread(target=heartbeat, name="compare-heartbeat")
    cleanup_thread.start()
    assert snapshot_ready.wait(5)
    heartbeat_thread.start()
    heartbeat_thread.join(timeout=5)
    assert not heartbeat_thread.is_alive()
    release_cleanup.set()
    cleanup_thread.join(timeout=5)
    assert not cleanup_thread.is_alive()
    assert heartbeat_errors == []
    assert cleanup_result == [None]
    final = store.get_pair("alice", pair_id)
    assert final["status"] == "running"
    with store._connect() as db:
        lease = db.execute("SELECT lease_until FROM compare_pairs WHERE id=?", (pair_id,)).fetchone()
    assert lease["lease_until"] > cleanup_now


def test_mysql_seal_waits_for_upload_and_never_marks_complete_inputs_incomplete(mysql_store):
    """A seal cannot snapshot an unuploaded pair while its upload commits."""
    store = mysql_store
    left, right = docx_bytes("left"), docx_bytes("right")
    task = store.create("alice", "seal-race", manifest(left, right))
    reached, release = threading.Event(), threading.Event()
    original = store._owned_task_locked
    calls = {"count": 0}

    def paused(db, owner, task_id):
        row = original(db, owner, task_id)
        calls["count"] += 1
        if threading.current_thread().name == "compare-upload" and calls["count"] == 1:
            reached.set()
            assert release.wait(5)
        return row

    store._owned_task_locked = paused
    upload_errors = []

    def upload():
        try:
            store.upload("alice", task["id"], [dict(client_id="l0", name="a.docx", data=left),
                                                dict(client_id="r0", name="b.docx", data=right)])
        except Exception as exc:
            upload_errors.append(exc)

    upload_thread = threading.Thread(target=upload, name="compare-upload")
    upload_thread.start()
    assert reached.wait(5)
    seal_result = []
    seal_thread = threading.Thread(target=lambda: seal_result.append(store.seal("alice", task["id"])),
                                   name="compare-seal")
    seal_thread.start()
    seal_thread.join(timeout=0.2)
    assert seal_thread.is_alive(), "MySQL seal did not wait for upload's task lock"
    release.set()
    upload_thread.join(timeout=5)
    seal_thread.join(timeout=5)
    assert upload_errors == [] and len(seal_result) == 1
    assert seal_result[0]["pairs"][0]["status"] == "queued"
