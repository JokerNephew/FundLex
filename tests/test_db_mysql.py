"""Real MySQL 8.0 integration checks for the database adapter.

Skipped unless ``FUNDLEX_MYSQL_TEST_URL`` points at a disposable MySQL database
(for example ``mysql://user:pass@127.0.0.1:3306/fundlex_test?charset=utf8mb4``).
Every test drops the FundLex tables first, so the module is repeatable.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import zipfile
from pathlib import Path

import pytest

from fundlex.db import Database, Row

MYSQL_URL = os.environ.get("FUNDLEX_MYSQL_TEST_URL", "").strip()

pytestmark = pytest.mark.skipif(not MYSQL_URL, reason="FUNDLEX_MYSQL_TEST_URL is not configured")

# Child tables first so DROP TABLE never trips a foreign key.
TABLES = ("task_batches", "task_files", "artifacts", "documents", "tasks", "batches", "requests", "probe")


def docx_bytes(label: str = "fixture") -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f"<document>{label}</document>")
    return stream.getvalue()


@pytest.fixture(autouse=True)
def clean_mysql():
    with Database(MYSQL_URL).connect() as db:
        for table in TABLES:
            db.execute(f"DROP TABLE IF EXISTS {table}")
    yield


def test_database_translation_row_access_and_environment(tmp_path: Path, monkeypatch):
    db = Database(MYSQL_URL)
    assert db.dialect == "mysql" and db.path is None

    with db.connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS probe (
                id TEXT PRIMARY KEY, payload TEXT, report_json TEXT,
                metadata TEXT NOT NULL DEFAULT '{}', quantity INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS probe_quantity ON probe(quantity);
            CREATE INDEX IF NOT EXISTS probe_quantity ON probe(quantity);
        """)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        assert {row["name"] for row in conn.execute("PRAGMA table_info(probe)")} == {
            "id", "payload", "report_json", "metadata", "quantity"}
        types = {row["name"]: row["data_type"] for row in conn.execute(
            "SELECT column_name AS name, data_type AS data_type FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name=? ORDER BY ordinal_position", ("probe",))}
        assert types["payload"] == "varchar" and types["report_json"] == "mediumtext" and types["metadata"] == "mediumtext"
        assert conn.execute("INSERT INTO probe(id,payload,quantity) VALUES(?,?,?)", ("a", "first", 1)).rowcount == 1
        conn.execute("INSERT OR REPLACE INTO probe(id,payload,report_json,metadata,quantity) VALUES(?,?,?,?,?)",
                     ("a", "second", '{"ok": true}', '{"note": "中文"}', 2))
        row = conn.execute("SELECT id,payload,report_json,metadata,quantity FROM probe WHERE id=?", ("a",)).fetchone()
        assert isinstance(row, Row)
        assert row["id"] == "a" and row[0] == "a" and row[4] == 2
        assert row["metadata"] == '{"note": "中文"}'
        assert row.keys() == ["id", "payload", "report_json", "metadata", "quantity"]
        assert tuple(row) == ("a", "second", '{"ok": true}', '{"note": "中文"}', 2)
        assert dict(row)["payload"] == "second"
        assert row[1:] == ("second", '{"ok": true}', '{"note": "中文"}', 2)
        with pytest.raises(IndexError):
            row["missing"]
        assert [item["n"] for item in conn.execute("SELECT COUNT(*) AS n FROM probe")] == [1]
        conn.execute("ALTER TABLE probe ADD COLUMN note TEXT NOT NULL DEFAULT ''")
        altered = {row["name"]: row["data_type"] for row in conn.execute(
            "SELECT column_name AS name, data_type AS data_type FROM information_schema.columns "
            "WHERE table_schema=DATABASE() AND table_name=? ORDER BY ordinal_position", ("probe",))}
        assert altered["note"] == "varchar" and altered["report_json"] == "mediumtext"

    with db.connect() as tx:
        tx.execute("BEGIN IMMEDIATE")
        tx.execute("INSERT INTO probe(id,payload,quantity) VALUES(?,?,?)", ("b", "committed", 3))

    with pytest.raises(RuntimeError):
        with db.connect() as tx:
            tx.execute("BEGIN IMMEDIATE")
            tx.execute("INSERT INTO probe(id,payload,quantity) VALUES(?,?,?)", ("c", "rolled back", 4))
            raise RuntimeError("rollback probe")

    with db.connect() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM probe").fetchone()["n"] == 2
        assert conn.execute("SELECT payload FROM probe WHERE id=?", ("b",)).fetchone()["payload"] == "committed"

    monkeypatch.setenv("FUNDLEX_DATABASE_URL", MYSQL_URL)
    assert Database.from_env(tmp_path / "fallback.sqlite3").dialect == "mysql"
    monkeypatch.delenv("FUNDLEX_DATABASE_URL")
    fallback = Database.from_env(tmp_path / "fallback.sqlite3")
    assert fallback.dialect == "sqlite" and fallback.path == (tmp_path / "fallback.sqlite3").resolve()


def test_run_store_mysql_batch_claim_heartbeat_finish_and_download(tmp_path: Path):
    from fundlex.store import Conflict, RunStore

    store = RunStore(tmp_path, database_url=MYSQL_URL)
    assert store.database.dialect == "mysql"
    uploads = [("one.docx", docx_bytes("one")), ("two.docx", docx_bytes("two"))]
    batch = store.create_batch(owner="alice", ruleset_version="v1", ruleset_sha256="0" * 64,
                               uploads=uploads, idempotency_key="mysql-key")
    replay = store.create_batch(owner="alice", ruleset_version="v1", ruleset_sha256="0" * 64,
                                uploads=uploads, idempotency_key="mysql-key")
    assert replay["id"] == batch["id"] and len(batch["documents"]) == 2

    first = store.claim(lease_seconds=30)
    assert first["status"] == "queued" and first["fencing_token"] == 1 and first["attempt"] == 1
    store.heartbeat(first["id"], first["fencing_token"], lease_seconds=60)

    second = store.claim(lease_seconds=30)
    assert second["id"] != first["id"]
    store.finish(second["id"], second["fencing_token"],
                 report={"qualification_status": "excluded_by_fund_type", "delivery_status": "not_generated"},
                 artifacts={})

    with store._connect() as db:
        db.execute("UPDATE documents SET lease_until=0 WHERE id=?", (first["id"],))
    third = store.claim(lease_seconds=30)
    assert third["id"] == first["id"] and third["fencing_token"] > first["fencing_token"]
    with pytest.raises(Conflict):
        store.finish(first["id"], first["fencing_token"],
                     report={"delivery_status": "not_generated"}, artifacts={})

    report_path = tmp_path / "report.json"
    report = {"qualification_status": "eligible", "delivery_status": "not_generated", "actions": []}
    report_path.write_text(json.dumps(report), encoding="utf-8")
    store.finish(third["id"], third["fencing_token"], report=report, artifacts={"report_json": report_path})

    detail = store.get_batch("alice", batch["id"])
    assert detail["status"] == "completed"
    document = next(item for item in detail["documents"] if item["id"] == third["id"])
    assert document["status"] == "succeeded" and document["artifacts"] == ["report_json"]
    assert store.get_report("alice", batch["id"], third["id"])["qualification_status"] == "eligible"
    path, digest = store.get_artifact("alice", batch["id"], third["id"], "report_json")
    assert path.read_bytes() == report_path.read_bytes()
    assert digest == hashlib.sha256(report_path.read_bytes()).hexdigest()


def test_run_store_mysql_concurrent_claims_respect_row_locks(tmp_path: Path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from fundlex.store import RunStore

    store = RunStore(tmp_path, database_url=MYSQL_URL)
    batch = store.create_batch(owner="alice", ruleset_version="v1",
                               uploads=[("one.docx", docx_bytes("one")), ("two.docx", docx_bytes("two"))])
    barrier = threading.Barrier(2)

    def claim(_):
        barrier.wait(timeout=30)
        return store.claim(lease_seconds=30)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim, range(2)))
    assert all(item is not None for item in claims)
    assert {item["id"] for item in claims} == {document["id"] for document in batch["documents"]}
    assert store.claim() is None


def test_task_store_mysql_manifest_upload_query_and_task_controls(tmp_path: Path):
    from fundlex.rules import load_ruleset
    from fundlex.store import RunStore
    from fundlex.tasks import TaskStore

    store = RunStore(tmp_path, database_url=MYSQL_URL)
    tasks = TaskStore(store)
    data = docx_bytes("task")
    manifest = [{"client_id": f"file-{i}", "name": f"contract-{i}.docx", "size": len(data)} for i in range(3)]
    task = tasks.create("alice", "mysql 季度任务", load_ruleset("v1"), manifest, "mysql-task-key")
    assert task["total"] == 3 and task["uploaded"] == 0
    replay = tasks.create("alice", "mysql 季度任务", load_ruleset("v1"), manifest, "mysql-task-key")
    assert replay["id"] == task["id"]

    result = tasks.uploads("alice", task["id"],
                           [{"client_id": item["client_id"], "name": item["name"], "data": data, "error_code": None}
                            for item in manifest[:2]])
    assert [receipt["status"] for receipt in result["receipts"]] == ["accepted", "accepted"]
    assert result["task"]["uploaded"] == 2
    batch_id = result["receipts"][0]["batch_id"]
    documents = tasks.documents("alice", task["id"])
    assert documents["total"] == 3 and documents["items"][0]["upload_status"] == "accepted"

    job = store.claim()
    assert job is not None and job["batch_id"] == batch_id
    # retry() probes table existence through the adapter and propagates the stop to the task.
    store.retry(job["id"], job["fencing_token"], error_code="MODEL_CIRCUIT_OPEN")
    state = tasks.get("alice", task["id"])
    assert state["status"] == "paused" and state["pause_reason"] == "MODEL_CIRCUIT_OPEN"
    assert store.claim() is None

    assert tasks.control("alice", task["id"], "resume")["status"] == "queued"
    assert store.get_batch("alice", batch_id)["status"] == "queued"
    # Legacy batch controls still route through the parent task.
    assert store.pause("alice", batch_id)["status"] == "paused"
    assert store.resume("alice", batch_id)["status"] == "queued"


def test_model_budget_mysql_reserve_finish_and_snapshot():
    from fundlex.model_budget import BudgetError, ModelBudget

    budget = ModelBudget(MYSQL_URL, max_requests=4, max_cost_usd=1.0, concurrency=1)
    assert budget.database.dialect == "mysql" and budget.path is None
    first = budget.reserve(input_token_bound=1000, output_token_bound=100, lease_seconds=30)
    with pytest.raises(BudgetError, match="MODEL_CONCURRENCY_LIMIT"):
        budget.reserve(input_token_bound=1000, output_token_bound=100, lease_seconds=30)
    charged = budget.finish(first, {"error_code": None}, prompt_tokens=1000, completion_tokens=100, success=True)
    assert charged == pytest.approx((1000 * 1 + 100 * 5) / 1_000_000)

    second = budget.reserve(input_token_bound=10, output_token_bound=10, lease_seconds=30)
    budget.finish(second, {"error_code": "MODEL_NETWORK_ERROR"}, prompt_tokens=None,
                  completion_tokens=None, success=False)
    snapshot = budget.snapshot()
    assert snapshot["http_attempts"] == 2
    assert snapshot["statuses"] == {"completed": 1, "failed": 1}
    assert snapshot["estimated_cost_usd"] == pytest.approx((1000 * 1 + 100 * 5 + 10 * 1 + 10 * 5) / 1_000_000)
    with pytest.raises(BudgetError, match="MODEL_COST_BUDGET_EXCEEDED"):
        budget.reserve(input_token_bound=10_000_000, output_token_bound=10_000_000, lease_seconds=30)


def test_model_gateway_from_env_accepts_mysql_ledger(monkeypatch):
    monkeypatch.setenv("FUNDLEX_MODEL_LEDGER", MYSQL_URL)
    monkeypatch.setenv("LLM_BASE_URL", "https://model.invalid")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "never-log-this")
    from fundlex.model import ModelGateway

    gateway = ModelGateway.from_env()
    try:
        assert gateway.budget.database.dialect == "mysql"
        assert gateway.budget.snapshot()["http_attempts"] == 0
    finally:
        gateway.close()
