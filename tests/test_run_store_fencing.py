"""Deterministic fencing races for the revision RunStore.

The SQLite tests let a second RunStore take over between the validation SELECT
and the final UPDATE. This models the interleaving at the exact fencing
boundary without depending on scheduler timing. The MySQL tests use a
disposable URL when ``FUNDLEX_MYSQL_TEST_URL`` is configured and are skipped
otherwise.
"""

from __future__ import annotations

import io
import json
import os
from contextlib import contextmanager
from pathlib import Path

import pytest
from docx import Document

from fundlex.db import Database
from fundlex.store import Conflict, RunStore


def docx_bytes(text: str = "fixture") -> bytes:
    output = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(output)
    return output.getvalue()


def make_store(tmp_path: Path) -> tuple[RunStore, dict]:
    store = RunStore(tmp_path)
    batch = store.create_batch(owner="alice", ruleset_version="v1",
                               uploads=[("one.docx", docx_bytes())])
    return store, batch


def _pause_after_document_read(store: RunStore, callback):
    original_connect = store._connect

    class PausingCursor:
        def __init__(self, cursor, pause):
            self.cursor = cursor
            self.pause = pause
            self.paused = False

        def _pause_after_read(self):
            if not self.paused:
                self.paused = True
                self.pause()

        def fetchone(self):
            row = self.cursor.fetchone()
            self._pause_after_read()
            return row

        def fetchall(self):
            rows = self.cursor.fetchall()
            self._pause_after_read()
            return rows

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    class PausingConnection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, params=()):
            cursor = self.db.execute(sql, params)
            if sql.startswith("SELECT * FROM documents WHERE id="):
                return PausingCursor(cursor, lambda: callback(self.db))
            return cursor

        def __getattr__(self, name):
            return getattr(self.db, name)

    @contextmanager
    def wrapped_connect():
        with original_connect() as db:
            yield PausingConnection(db)

    store._connect = wrapped_connect


def test_finish_rejects_interleaved_new_fence_after_validation(tmp_path: Path):
    store, _ = make_store(tmp_path)
    lease = store.claim(lease_seconds=30)
    newer_store = RunStore(tmp_path)
    report = {"delivery_status": "not_generated"}

    def newer_attempt(_db):
        with newer_store._connect() as db:
            db.execute("UPDATE documents SET lease_until=0 WHERE id=?", (lease["id"],))
        newer = newer_store.claim(lease_seconds=30)
        assert newer and newer["fencing_token"] > lease["fencing_token"]
        newer_store.finish(newer["id"], newer["fencing_token"],
                           report={"delivery_status": "not_generated"}, artifacts={})

    _pause_after_document_read(store, newer_attempt)
    with pytest.raises(Conflict, match="stale worker lease"):
        store.finish(lease["id"], lease["fencing_token"], report=report, artifacts={})

    with store._connect() as db:
        row = db.execute("SELECT status,attempt,fencing_token,report_json FROM documents WHERE id=?",
                         (lease["id"],)).fetchone()
    assert row["status"] == "succeeded"
    assert row["attempt"] == lease["attempt"] + 1
    assert row["fencing_token"] == lease["fencing_token"] + 1
    assert json.loads(row["report_json"])["delivery_status"] == "not_generated"


def test_retry_rejects_interleaved_new_fence_after_validation(tmp_path: Path):
    store, _ = make_store(tmp_path)
    lease = store.claim(lease_seconds=30)
    newer_store = RunStore(tmp_path)

    def newer_attempt(_db):
        with newer_store._connect() as db:
            db.execute("UPDATE documents SET lease_until=0 WHERE id=?", (lease["id"],))
        newer = newer_store.claim(lease_seconds=30)
        assert newer and newer["fencing_token"] > lease["fencing_token"]
        newer_store.finish(newer["id"], newer["fencing_token"],
                           report={"delivery_status": "not_generated"}, artifacts={})

    _pause_after_document_read(store, newer_attempt)
    with pytest.raises(Conflict, match="stale worker lease"):
        store.retry(lease["id"], lease["fencing_token"], error_code="TEMPORARY")

    with store._connect() as db:
        row = db.execute("SELECT status,attempt,fencing_token,error_code FROM documents WHERE id=?",
                         (lease["id"],)).fetchone()
    assert row["status"] == "succeeded"
    assert row["attempt"] == lease["attempt"] + 1
    assert row["fencing_token"] == lease["fencing_token"] + 1
    assert row["error_code"] is None


def test_exhausted_cleanup_skips_interleaved_renewed_lease(tmp_path: Path):
    store, _ = make_store(tmp_path)
    lease = store.claim(lease_seconds=30, max_attempts=1)
    newer_store = RunStore(tmp_path)
    cleanup_started = False
    original_connect = store._connect

    class PausingConnection:
        def __init__(self, db):
            self.db = db

        def execute(self, sql, params=()):
            cursor = self.db.execute(sql, params)
            if not cleanup_started and sql.startswith("SELECT id,batch_id,source_sha256,fencing_token,attempt FROM documents"):
                class CleanupCursor:
                    def fetchall(inner):
                        nonlocal cleanup_started
                        rows = cursor.fetchall()
                        cleanup_started = True
                        with newer_store._connect() as db:
                            db.execute("UPDATE documents SET lease_until=0 WHERE id=?", (lease["id"],))
                        newer = newer_store.claim(lease_seconds=30, max_attempts=2)
                        assert newer and newer["fencing_token"] > lease["fencing_token"]
                        newer_store.finish(newer["id"], newer["fencing_token"],
                                           report={"delivery_status": "not_generated"}, artifacts={})
                        return rows

                    def __getattr__(inner, name):
                        return getattr(cursor, name)

                return CleanupCursor()
            return cursor

        def __getattr__(self, name):
            return getattr(self.db, name)

    @contextmanager
    def wrapped_connect():
        with original_connect() as db:
            yield PausingConnection(db)

    store._connect = wrapped_connect
    assert store.claim(max_attempts=1) is None

    with store._connect() as db:
        row = db.execute("SELECT status,error_code,lease_until,fencing_token,report_json FROM documents WHERE id=?",
                         (lease["id"],)).fetchone()
    assert row["status"] == "succeeded"
    assert row["error_code"] is None
    assert row["lease_until"] is None
    assert row["fencing_token"] == lease["fencing_token"] + 1
    assert json.loads(row["report_json"])["delivery_status"] == "not_generated"


MYSQL_URL = os.environ.get("FUNDLEX_MYSQL_TEST_URL", "").strip()


@pytest.fixture
def mysql_run_store(tmp_path: Path):
    if not MYSQL_URL:
        pytest.skip("FUNDLEX_MYSQL_TEST_URL is not configured")
    with Database(MYSQL_URL).connect() as db:
        for table in ("task_batches", "task_files", "artifacts", "documents", "tasks", "batches"):
            db.execute(f"DROP TABLE IF EXISTS {table}")
    yield RunStore(tmp_path, database_url=MYSQL_URL)


def test_mysql_run_store_lifecycle_and_fencing(mysql_run_store: RunStore):
    store = mysql_run_store
    batch = store.create_batch(owner="alice", ruleset_version="v1", uploads=[("one.docx", docx_bytes())])
    first = store.claim(lease_seconds=30, max_attempts=2)
    assert first and first["attempt"] == 1 and first["fencing_token"] == 1

    with store._connect() as db:
        db.execute("UPDATE documents SET lease_until=0 WHERE id=?", (first["id"],))
    second = store.claim(lease_seconds=30, max_attempts=2)
    assert second and second["fencing_token"] > first["fencing_token"]
    with pytest.raises(Conflict):
        store.retry(first["id"], first["fencing_token"], error_code="STALE")
    store.finish(second["id"], second["fencing_token"],
                 report={"delivery_status": "not_generated"}, artifacts={})
    assert store.get_batch("alice", batch["id"])["status"] == "completed"
