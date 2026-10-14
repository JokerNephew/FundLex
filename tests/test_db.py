"""Adapter-layer checks that always run on the SQLite local profile."""

from __future__ import annotations

from pathlib import Path

import pytest

from fundlex.db import Database, Row


def test_sqlite_url_path_and_row_compatibility(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FUNDLEX_DATABASE_URL", raising=False)
    url = "sqlite:///" + (tmp_path / "adapter.sqlite3").as_posix()
    db = Database(url)
    assert db.dialect == "sqlite" and db.path == (tmp_path / "adapter.sqlite3").resolve()
    with db.connect() as conn:
        conn.executescript("CREATE TABLE t (id TEXT PRIMARY KEY, payload TEXT);")
        assert conn.execute("INSERT INTO t VALUES (?,?)", ("a", "中文")).rowcount == 1
        row = conn.execute("SELECT id,payload FROM t WHERE id=?", ("a",)).fetchone()
        assert isinstance(row, Row) and row["payload"] == "中文" and row[0] == "a"
        assert row.keys() == ["id", "payload"] and tuple(row) == ("a", "中文")
        assert dict(row) == {"id": "a", "payload": "中文"}
        conn.execute("INSERT OR REPLACE INTO t VALUES (?,?)", ("a", "替换"))
        assert conn.execute("SELECT payload FROM t").fetchone()["payload"] == "替换"
        assert conn.execute("PRAGMA table_info(t)").fetchall()

    with pytest.raises(RuntimeError):
        with db.connect() as conn:
            conn.execute("INSERT INTO t VALUES (?,?)", ("b", "rolled back"))
            raise RuntimeError("rollback probe")
    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM t").fetchone()["n"] == 1

    plain = Database(tmp_path / "plain.sqlite3")
    assert plain.dialect == "sqlite" and plain.path == (tmp_path / "plain.sqlite3").resolve()
    assert Database.from_env(tmp_path / "plain.sqlite3").path == plain.path


def test_run_store_accepts_sqlite_url(tmp_path: Path):
    from fundlex.store import RunStore

    url = "sqlite:///" + (tmp_path / "store.sqlite3").as_posix()
    store = RunStore(tmp_path, database_url=url)
    assert store.database.dialect == "sqlite"
    batch = store.create_batch(owner="alice", ruleset_version="v1", uploads=[("a.docx", b"docx")])
    job = store.claim(lease_seconds=30)
    assert job is not None and job["batch_id"] == batch["id"]
    store.finish(job["id"], job["fencing_token"], report={"delivery_status": "not_generated"}, artifacts={})
    assert store.get_batch("alice", batch["id"])["status"] == "completed"
