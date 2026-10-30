"""Regression tests for the 2026-10-31 worker/queue stability audit fixes.

A2-F1: gg worker pause/fail writes re-enter fencing, so a stale lease stands
       down instead of polluting the new epoch's run state.
A2-F2: gg claim caps attempts and sweeps exhausted jobs to a fenced terminal
       failure (GG_ATTEMPTS_EXHAUSTED) instead of an infinite crash loop.
A2-F3: enqueue dedupes retry_wait jobs and claim enforces one live job per run.
A2-F4/B14-01: document worker stands down on takeover Conflicts inside its
       compensating paths, and run_forever absorbs transient claim-time DB
       faults with bounded backoff instead of terminating.
B14-02: a finish that fails mid-publish reaps the attempt-namespaced objects.
B14-04: stale fundlex_job_* workspaces are reaped only when provably dead.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import pytest
from docx import Document

import fundlex.store
from fundlex.jobs import Worker
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.guide_generation.worker import GuideGenerationWorker
from fundlex.model import ModelError
from fundlex.store import Conflict, RunStore

from guide_generation_fakes import FakeGuideRouter
from test_guide_generation_pipeline import _prepare


# ---------------------------------------------------------------------------
# shared helpers
# ---------------------------------------------------------------------------

def docx_bytes(text: str = "fixture") -> bytes:
    output = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    return output.getvalue()


def make_doc_store(tmp_path: Path) -> RunStore:
    store = RunStore(tmp_path)
    store.create_batch(owner="alice", ruleset_version="v1",
                       uploads=[("one.docx", docx_bytes())])
    return store


def doc_row(store: RunStore) -> dict:
    with store._connect() as db:
        return dict(db.execute("SELECT * FROM documents").fetchone())


def takeover_existing_lease(store: RunStore) -> dict:
    """Expire the live lease and reclaim the document as a newer epoch."""
    with store._connect() as db:
        db.execute("UPDATE documents SET lease_until=0")
    reclaim = store.claim(lease_seconds=60)
    assert reclaim is not None
    return reclaim


class _ClaimGate:
    """Delegating store facade whose claim fails transiently N times."""

    def __init__(self, inner, failures: int):
        self._inner = inner
        self.failures = failures

    def claim(self, **kwargs):
        if self.failures > 0:
            self.failures -= 1
            raise sqlite3.OperationalError("database is locked")
        return self._inner.claim(**kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


def gg_job_rows(gg: GuideGenerationStore, run_id: str) -> list[dict]:
    with gg._connect() as db:
        return [dict(row) for row in db.execute(
            "SELECT * FROM gg_jobs WHERE run_id=? ORDER BY created_at", (run_id,)).fetchall()]


# ---------------------------------------------------------------------------
# A2-F1 — compensating gg worker writes re-enter fencing
# ---------------------------------------------------------------------------

def _reclaim_gg_job(gg: GuideGenerationStore, run_id: str) -> dict:
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET lease_until=0 WHERE run_id=?", (run_id,))
    reclaim = gg.claim(lease_seconds=60)
    assert reclaim is not None
    return reclaim


def test_gg_stale_worker_model_error_cannot_pause_new_epoch(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)

    def reclaim_then_fail():
        reclaim = _reclaim_gg_job(gg, run_id)
        assert reclaim["fencing_token"] == 2
        raise ModelError("MODEL_CONFIG_MISSING")

    worker = GuideGenerationWorker(store, router_factory=reclaim_then_fail, lease_seconds=300)
    assert worker.run_once() is True
    run = gg.get_run(run_id)
    # Pre-fix the stale worker wrote status=paused + blocked_reason here.
    assert run["status"] == "queued"
    assert "blocked_reason" not in (run.get("payload") or {})
    job = gg_job_rows(gg, run_id)[0]
    assert job["status"] == "leased" and job["fencing_token"] == 2


def test_gg_stale_worker_unexpected_error_cannot_fail_new_epoch(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    gg.enqueue(run_id)

    def reclaim_then_fail():
        _reclaim_gg_job(gg, run_id)
        raise RuntimeError("boom")

    worker = GuideGenerationWorker(store, router_factory=reclaim_then_fail, lease_seconds=300)
    assert worker.run_once() is True
    run = gg.get_run(run_id)
    # Pre-fix the stale worker wrote status=failed + payload.worker_error here.
    assert run["status"] == "queued"
    assert "worker_error" not in (run.get("payload") or {})


def test_gg_lease_holder_model_error_still_pauses(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)

    def unavailable():
        raise ModelError("MODEL_CONFIG_MISSING")

    assert GuideGenerationWorker(store, router_factory=unavailable).run_once() is True
    run = gg.get_run(run_id)
    assert run["status"] == "paused"
    assert (run.get("payload") or {}).get("blocked_reason") == "MODEL_CONFIG_MISSING"
    assert gg_job_rows(gg, run_id)[0]["status"] == "paused"
    assert job_id  # sanity: the paused job is the enqueued one


# ---------------------------------------------------------------------------
# A2-F2 — gg claim attempts cap and terminal sweep
# ---------------------------------------------------------------------------

def test_gg_claim_attempts_exhausted_marked_terminal(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)
    token = 0
    for expected in range(1, 6):  # default cap is 5 claims
        job = gg.claim(lease_seconds=60)
        assert job and job["id"] == job_id and job["attempts"] == expected
        token = job["fencing_token"]
        with gg._connect() as db:
            db.execute("UPDATE gg_jobs SET lease_until=0 WHERE id=?", (job_id,))
    # The crash loop stops here: the sweep retires the job instead of leasing.
    assert gg.claim(lease_seconds=60) is None
    run = gg.get_run(run_id)
    assert run["status"] == "failed" and run["stage"] == "FAILED"
    assert run["error_code"] == "GG_ATTEMPTS_EXHAUSTED"
    row = gg_job_rows(gg, run_id)[0]
    assert row["status"] == "failed" and row["error_code"] == "GG_ATTEMPTS_EXHAUSTED"
    # The terminal sweep is fenced: the crashed worker cannot write any more.
    with pytest.raises(Conflict, match="stale guide generation worker lease"):
        gg.heartbeat(job_id, token, lease_seconds=60)
    assert gg.claim(lease_seconds=60) is None  # stays terminal


def test_gg_claim_max_attempts_parameter(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)
    first = gg.claim(lease_seconds=60, max_attempts=1)
    assert first and first["attempts"] == 1
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET lease_until=0 WHERE id=?", (job_id,))
    assert gg.claim(lease_seconds=60, max_attempts=1) is None
    assert gg.get_run(run_id)["error_code"] == "GG_ATTEMPTS_EXHAUSTED"


def test_gg_claim_attempts_cap_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GUIDE_JOB_MAX_ATTEMPTS", "2")
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)
    for _ in range(2):
        job = gg.claim(lease_seconds=60)
        assert job is not None
        with gg._connect() as db:
            db.execute("UPDATE gg_jobs SET lease_until=0 WHERE id=?", (job_id,))
    assert gg.claim(lease_seconds=60) is None
    assert gg.get_run(run_id)["error_code"] == "GG_ATTEMPTS_EXHAUSTED"


def test_gg_retry_wait_at_cap_is_retired_immediately(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)
    job = gg.claim(lease_seconds=60)
    gg.finish_job(job_id, job["fencing_token"], status="retry_wait",
                  error_code="MODEL_NETWORK_ERROR", next_attempt_at=time.time() + 3600)
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET attempts=? WHERE id=?", (5, job_id))
    # Not yet due, but already at the cap: the doomed retry is retired now.
    assert gg.claim(lease_seconds=60) is None
    run = gg.get_run(run_id)
    assert run["status"] == "failed" and run["error_code"] == "GG_ATTEMPTS_EXHAUSTED"


# ---------------------------------------------------------------------------
# A2-F3 — one live job per run
# ---------------------------------------------------------------------------

def test_gg_enqueue_dedupes_retry_wait_jobs(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)
    assert gg.enqueue(run_id) == job_id  # queued dedupe (unchanged)
    job = gg.claim(lease_seconds=60)
    assert gg.enqueue(run_id) == job_id  # leased dedupe (unchanged)
    gg.finish_job(job_id, job["fencing_token"], status="retry_wait",
                  error_code="MODEL_NETWORK_ERROR", next_attempt_at=time.time() + 3600)
    # A2-F3: retry_wait is still the run's single live job.
    assert gg.enqueue(run_id) == job_id
    assert len(gg_job_rows(gg, run_id)) == 1


def test_gg_claim_self_heals_duplicate_wait_jobs(tmp_path):
    store, gg, run_id, corpus = _prepare(tmp_path)
    job_id = gg.enqueue(run_id)
    now = time.time()
    with gg._connect() as db:
        # Pre-fix legacy race data: a second live job for the same run.
        db.execute("""INSERT INTO gg_jobs (id,run_id,status,attempts,created_at,updated_at)
            VALUES (?,?,'queued',0,?,?)""", (uuid.uuid4().hex, run_id, now + 0.01, now + 0.01))
    first = gg.claim(lease_seconds=60)
    assert first and first["id"] == job_id
    rows = {row["id"]: row for row in gg_job_rows(gg, run_id)}
    assert rows[job_id]["status"] == "leased"
    duplicate = next(row for row in rows.values() if row["id"] != job_id)
    assert duplicate["status"] == "superseded"
    assert gg.claim(lease_seconds=60) is None  # already leased live
    with gg._connect() as db:
        db.execute("""INSERT INTO gg_jobs (id,run_id,status,attempts,created_at,updated_at)
            VALUES (?,?,'queued',0,?,?)""", (uuid.uuid4().hex, run_id, now + 0.02, now + 0.02))
    # A queued sibling is never claimed while another epoch of the run is live.
    assert gg.claim(lease_seconds=60) is None
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET status='superseded' WHERE run_id=? AND status='queued'", (run_id,))
    gg.finish_job(job_id, first["fencing_token"], status="completed")
    assert gg.claim(lease_seconds=60) is None


def test_gg_resume_after_exhaustion_starts_new_epoch(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GUIDE_JOB_MAX_ATTEMPTS", "1")
    store, gg, run_id, corpus = _prepare(tmp_path)
    gg.enqueue(run_id)
    job = gg.claim(lease_seconds=60)
    with gg._connect() as db:
        db.execute("UPDATE gg_jobs SET lease_until=0 WHERE id=?", (job["id"],))
    assert gg.claim(lease_seconds=60) is None
    assert gg.get_run(run_id)["error_code"] == "GG_ATTEMPTS_EXHAUSTED"
    resumed = gg.resume_run(run_id, owner="u", actor="u", reason="retry")
    assert resumed["status"] == "queued"
    fresh = gg.claim(lease_seconds=60)
    assert fresh and fresh["attempts"] == 1  # new job row, fresh attempt budget


# ---------------------------------------------------------------------------
# A2-F4 — document worker stands down on takeover inside compensating paths
# ---------------------------------------------------------------------------

def test_run_once_takeover_conflict_in_retry_path_returns_true(tmp_path):
    store = make_doc_store(tmp_path)

    def processor(source, output_dir, ruleset_version):
        takeover_existing_lease(store)
        raise OSError("network down")

    worker = Worker(store, processor=processor, lease_seconds=60)
    assert worker.run_once() is True  # pre-fix: Conflict escaped store.retry
    row = doc_row(store)
    assert row["status"] == "leased"  # owned by the newer epoch
    assert row["fencing_token"] == 2
    assert row["report_json"] in (None, "")


def test_run_once_takeover_conflict_in_failure_report_returns_true(tmp_path):
    store = make_doc_store(tmp_path)

    def processor(source, output_dir, ruleset_version):
        takeover_existing_lease(store)
        raise ValueError("boom")

    worker = Worker(store, processor=processor, lease_seconds=60)
    assert worker.run_once() is True  # pre-fix: Conflict escaped the failure finish
    row = doc_row(store)
    assert row["status"] == "leased" and row["fencing_token"] == 2
    assert row["report_json"] in (None, "")  # stale failure report must not land


# ---------------------------------------------------------------------------
# B14-01 — run_forever absorbs transient claim-time DB faults
# ---------------------------------------------------------------------------

def test_run_forever_absorbs_transient_claim_faults(tmp_path):
    store = make_doc_store(tmp_path)
    gate = _ClaimGate(store, failures=2)
    worker = Worker(gate, processor=lambda src, out, version: {"delivery_status": "not_generated"},
                    lease_seconds=60)
    stopped = threading.Event()
    errors: list[BaseException] = []

    def run():
        try:
            worker.run_forever(poll_seconds=0.02, concurrency=1, stop_event=stopped)
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while time.time() < deadline and doc_row(store)["status"] != "succeeded":
        time.sleep(0.05)
    stopped.set()
    thread.join(10)
    assert not errors
    assert gate.failures == 0
    assert doc_row(store)["status"] == "succeeded"


def test_run_forever_gives_up_on_persistent_db_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_WORKER_DB_FAILURE_LIMIT", "2")
    store = make_doc_store(tmp_path)
    gate = _ClaimGate(store, failures=99)
    worker = Worker(gate, processor=lambda src, out, version: {}, lease_seconds=60)
    with pytest.raises(sqlite3.OperationalError):
        worker.run_forever(poll_seconds=0.02, concurrency=1)


def test_gg_run_forever_absorbs_transient_claim_faults(tmp_path, monkeypatch):
    store, gg, run_id, corpus = _prepare(tmp_path)
    gg.enqueue(run_id)
    worker = GuideGenerationWorker(store, router_factory=FakeGuideRouter)
    worker.gg_store = _ClaimGate(worker.gg_store, failures=2)
    stopped = threading.Event()
    errors: list[BaseException] = []

    def run():
        try:
            worker.run_forever(poll_seconds=0.02, stop_event=stopped)
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    terminal = {"complete", "complete_with_unresolved"}
    deadline = time.time() + 60
    while time.time() < deadline and gg.get_run(run_id)["status"] not in terminal:
        time.sleep(0.1)
    stopped.set()
    thread.join(10)
    assert not errors
    assert gg.get_run(run_id)["status"] in terminal


def test_gg_run_forever_gives_up_on_persistent_db_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GUIDE_DB_FAILURE_LIMIT", "2")
    store = RunStore(tmp_path)
    worker = GuideGenerationWorker(store, router_factory=FakeGuideRouter)
    worker.gg_store = _ClaimGate(worker.gg_store, failures=99)
    with pytest.raises(sqlite3.OperationalError):
        worker.run_forever(poll_seconds=0.02)


# ---------------------------------------------------------------------------
# B14-02 — failed finish reaps attempt-namespaced result objects
# ---------------------------------------------------------------------------

def test_failed_finish_reaps_attempt_objects(tmp_path, monkeypatch):
    store = make_doc_store(tmp_path)
    real_sha256 = fundlex.store.sha256_file

    def flaky_sha256(path):
        candidate = Path(str(path))
        if "results" in candidate.parts and candidate.name == "report_md.md":
            raise OSError(28, "No space left on device")
        return real_sha256(path)

    def processor(source, output_dir, ruleset_version):
        raise ValueError("boom")

    monkeypatch.setattr("fundlex.store.sha256_file", flaky_sha256)
    worker = Worker(store, processor=processor, lease_seconds=60)
    with pytest.raises(OSError):
        worker.run_once()
    row = doc_row(store)
    leftover = store.object_path(f"results/{row['id']}/{int(row['fencing_token'])}")
    assert not leftover.exists() or not any(leftover.rglob("*"))


# ---------------------------------------------------------------------------
# B14-04 — stale fundlex_job_* workspaces reaped only when provably dead
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.name == "nt", reason="pid liveness probing is POSIX-only")
def test_stale_workspace_reaped_only_when_owner_dead(tmp_path):
    store = make_doc_store(tmp_path)
    lease = store.claim(lease_seconds=60)
    doc_id, token = lease["id"], lease["fencing_token"]
    root = str(store.root.resolve())
    tmp_root = Path(tempfile.gettempdir())
    created: list[Path] = []

    def fake_ws(marker):
        path = tmp_root / f"fundlex_job_qa_{uuid.uuid4().hex}"
        path.mkdir()
        (path / "out").mkdir()
        if marker is not None:
            (path / "workspace.json").write_text(json.dumps(marker), encoding="utf-8")
        created.append(path)
        return path

    try:
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait(30)
        dead_pid = proc.pid
        live_owner = fake_ws({"document_id": doc_id, "fencing_token": 999,
                              "store_root": root, "pid": os.getpid()})
        dead_owner = fake_ws({"document_id": doc_id, "fencing_token": 999,
                              "store_root": root, "pid": dead_pid})
        foreign = fake_ws({"document_id": doc_id, "fencing_token": 999,
                           "store_root": str(tmp_path / "other"), "pid": dead_pid})
        markerless = fake_ws(None)
        live_epoch = fake_ws({"document_id": doc_id, "fencing_token": int(token),
                              "store_root": root, "pid": dead_pid})
        Worker(store, processor=lambda *args: {}, lease_seconds=60)._reap_stale_workspaces()
        assert live_owner.exists()   # owning pid still alive
        assert foreign.exists()      # belongs to another store root
        assert markerless.exists()   # legacy workspace: left to the OS
        assert live_epoch.exists()   # recorded attempt is still the live epoch
        assert not dead_owner.exists()
    finally:
        for path in created:
            shutil.rmtree(path, ignore_errors=True)
