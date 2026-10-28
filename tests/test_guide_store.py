"""Guide version persistence, owner configuration and parse-job tests.

The built-in guide must be idempotent and globally visible; custom versions are
private to their owner and can only be enabled after parsing.
"""
from __future__ import annotations

import hashlib
import io
import time

import pytest
from docx import Document

from fundlex import guide_store
from fundlex.guide import GUIDE_SCHEMA_VERSION
from fundlex.store import Conflict, RunStore, StoreError


def guide_docx(label: str = "指引正文示例") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def make_store(tmp_path) -> RunStore:
    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    return store


def parsed_document() -> dict:
    return {"schema_version": GUIDE_SCHEMA_VERSION, "parser_version": "guide-parse-1",
            "prompt_versions": {"guide_parse": "guide_parse_v1", "guide_verify": "guide_verify_v1"},
            "source_sha256": "ab" * 32,
            "groups": [{"rule_id": "G01", "title": "示例规则"}],
            "validation": {"errors": [], "warnings": [], "coverage_gaps": [], "clean": True}}


def test_builtin_guide_is_idempotent_and_visible_to_everyone(tmp_path):
    store = RunStore(tmp_path / "state")
    assert guide_store.ensure_builtin_guide(store) == guide_store.BUILTIN_GUIDE_ID
    assert guide_store.ensure_builtin_guide(store) == guide_store.BUILTIN_GUIDE_ID
    with store._connect() as db:
        rows = db.execute("SELECT id FROM guide_versions").fetchall()
    assert [row["id"] for row in rows] == [guide_store.BUILTIN_GUIDE_ID]
    for owner in ("alice", "bob"):
        version = guide_store.get_version(store, owner, guide_store.BUILTIN_GUIDE_ID)
        assert version["built_in"] is True
        assert version["status"] == "released"
        assert version["qualification_status"] == "frozen_builtin"
    document = guide_store.guide_document(store, guide_store.BUILTIN_GUIDE_ID)
    assert document["schema_version"] == GUIDE_SCHEMA_VERSION
    assert document["groups"]
    assert version["rules_sha256"] == document["document_sha256"]
    assert version["document_sha256"] == document["document_sha256"]
    assert guide_store.current_guide(store, "alice")["id"] == guide_store.BUILTIN_GUIDE_ID
    assert [item["id"] for item in guide_store.list_versions(store, "alice")] == [guide_store.BUILTIN_GUIDE_ID]


def test_custom_version_creation_and_owner_isolation(tmp_path):
    store = make_store(tmp_path)
    data = guide_docx()
    version = guide_store.create_custom_version(store, "alice", "custom-guide.docx", data)
    assert version["status"] == "uploaded"
    assert version["job_id"]
    assert version["owner"] == "alice"
    assert version["source_sha256"] == hashlib.sha256(data).hexdigest()
    assert guide_store.get_version(store, "alice", version["id"])["id"] == version["id"]
    with pytest.raises(KeyError):
        guide_store.get_version(store, "bob", version["id"])
    with pytest.raises(KeyError):
        guide_store.guide_document(store, version["id"])
    assert version["id"] in [item["id"] for item in guide_store.list_versions(store, "alice")]
    assert version["id"] not in [item["id"] for item in guide_store.list_versions(store, "bob")]
    source = guide_store.guide_source_path(store, version["id"])
    assert source.is_file() and source.read_bytes() == data
    assert source.is_relative_to(store.objects)
    assert guide_store.guide_source_path(store, guide_store.BUILTIN_GUIDE_ID) == guide_store.BUILTIN_GUIDE_PATH


def test_enable_rules_and_reset_to_builtin(tmp_path):
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", guide_docx())
    with pytest.raises(ValueError, match="GUIDE_NOT_ENABLEABLE"):
        guide_store.set_current_guide(store, "alice", version["id"])
    with pytest.raises(KeyError):
        guide_store.set_current_guide(store, "bob", version["id"])
    with pytest.raises(KeyError):
        guide_store.set_current_guide(store, "alice", "missing-version")
    job = guide_store.claim_guide_job(store)
    result = guide_store.finish_guide_job(store, job["id"], job["fencing_token"], document=parsed_document())
    assert result["version"]["status"] == "parsed"
    guide_store.set_current_guide(store, "alice", version["id"])
    assert guide_store.current_guide(store, "alice")["id"] == version["id"]
    assert guide_store.current_guide(store, "bob")["id"] == guide_store.BUILTIN_GUIDE_ID
    parsed = guide_store.get_version(store, "alice", version["id"])
    assert parsed["rules_count"] == 1 and parsed["parser_version"] == "guide-parse-1"
    assert parsed["prompt_versions"]["guide_parse"] == "guide_parse_v1"
    assert parsed["issues"]["clean"] is True
    guide_store.set_current_guide(store, "alice", guide_store.BUILTIN_GUIDE_ID)
    assert guide_store.current_guide(store, "alice")["id"] == guide_store.BUILTIN_GUIDE_ID


def test_parse_job_claim_finish_retry_and_attempts_exhausted(tmp_path):
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", guide_docx())
    job = guide_store.claim_guide_job(store)
    assert job["id"] == version["job_id"]
    assert job["status"] == "leased" and job["attempts"] == 1
    assert job["fencing_token"] == 1
    assert guide_store.get_version(store, "alice", version["id"])["status"] == "parsing"
    assert guide_store.claim_guide_job(store) is None  # one job in flight per owner
    released = guide_store.release_guide_job(store, job["id"], job["fencing_token"])
    assert released["status"] == "queued" and released["attempts"] == 0
    assert guide_store.get_version(store, "alice", version["id"])["status"] == "uploaded"
    assert guide_store.claim_guide_job(store) is None  # backoff instead of a hot loop
    with store._connect() as db:
        db.execute("UPDATE guide_jobs SET lease_until=NULL WHERE id=?", (job["id"],))
    second = guide_store.claim_guide_job(store)
    assert second["attempts"] == 1
    failed = guide_store.finish_guide_job(store, second["id"], second["fencing_token"], error_code="GUIDE_SOURCE_EMPTY")
    assert failed["job"]["status"] == "parse_failed" and failed["job"]["error_code"] == "GUIDE_SOURCE_EMPTY"
    assert failed["version"]["status"] == "parse_failed"
    assert failed["version"]["issues"]["error_code"] == "GUIDE_SOURCE_EMPTY"
    with pytest.raises(ValueError, match="GUIDE_NOT_ENABLEABLE"):
        guide_store.set_current_guide(store, "alice", version["id"])
    third = guide_store.claim_guide_job(store)
    assert third["attempts"] == 2
    retryable = guide_store.finish_guide_job(store, third["id"], third["fencing_token"],
                                             error_code="GUIDE_SOURCE_EMPTY")
    assert retryable["job"]["status"] == "parse_failed"
    fourth = guide_store.claim_guide_job(store)
    assert fourth["attempts"] == 3
    terminal = guide_store.finish_guide_job(store, fourth["id"], fourth["fencing_token"],
                                            error_code="GUIDE_SOURCE_EMPTY")
    assert terminal["job"]["status"] == "failed" and terminal["version"]["status"] == "failed"
    assert guide_store.claim_guide_job(store) is None
    with pytest.raises(KeyError):
        guide_store.release_guide_job(store, "missing-job", 1)
    with pytest.raises(KeyError):
        guide_store.finish_guide_job(store, "missing-job", 1, error_code="GUIDE_PARSE_FAILED")


def test_recoverable_release_does_not_consume_attempt_budget(tmp_path):
    """Repeated model/network stops must not leave a queued job unclaimable."""
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", guide_docx())
    for expected in (1, 1, 1):
        job = guide_store.claim_guide_job(store)
        assert job is not None and job["attempts"] == expected
        released = guide_store.release_guide_job(store, job["id"], job["fencing_token"])
        assert released["status"] == "queued" and released["attempts"] == 0
        with store._connect() as db:
            db.execute("UPDATE guide_jobs SET lease_until=NULL WHERE id=?", (job["id"],))
    claimed = guide_store.claim_guide_job(store)
    assert claimed is not None and claimed["guide_version_id"] == version["id"]
    final = guide_store.finish_guide_job(store, claimed["id"], claimed["fencing_token"],
                                         document=parsed_document())
    assert final["job"]["status"] == "completed" and final["version"]["status"] == "parsed"


def test_late_guide_worker_cannot_release_or_finish_new_attempt(tmp_path):
    store = make_store(tmp_path)
    version = guide_store.create_custom_version(store, "alice", "custom.docx", guide_docx())
    first = guide_store.claim_guide_job(store, lease_seconds=60)
    with store._connect() as db:
        db.execute("UPDATE guide_jobs SET lease_until=0 WHERE id=?", (first["id"],))

    second = guide_store.claim_guide_job(store, lease_seconds=60)
    assert second["fencing_token"] == first["fencing_token"] + 1
    with pytest.raises(Conflict, match="stale guide job lease"):
        guide_store.release_guide_job(store, first["id"], first["fencing_token"])
    with pytest.raises(Conflict, match="stale guide job lease"):
        guide_store.finish_guide_job(store, first["id"], first["fencing_token"], document=parsed_document())
    with pytest.raises(Conflict, match="stale guide job lease"):
        guide_store.finish_guide_job(store, first["id"], first["fencing_token"],
                                     error_code="OLD_WORKER_FAILURE")
    with store._connect() as db:
        row = db.execute("SELECT status,attempts,fencing_token,error_code FROM guide_jobs WHERE id=?",
                         (version["job_id"],)).fetchone()
    assert dict(row) == {"status": "leased", "attempts": 2,
                         "fencing_token": second["fencing_token"], "error_code": None}
    finished = guide_store.finish_guide_job(store, second["id"], second["fencing_token"],
                                            error_code="CURRENT_WORKER_FAILURE")
    assert finished["job"]["error_code"] == "CURRENT_WORKER_FAILURE"


def test_existing_sqlite_guide_jobs_table_gets_fencing_token_migration(tmp_path):
    store = RunStore(tmp_path / "state")
    with store._connect() as db:
        db.execute("""CREATE TABLE guide_jobs (
            id TEXT PRIMARY KEY, guide_version_id TEXT NOT NULL, owner TEXT NOT NULL,
            status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
            lease_until REAL, error_code TEXT, created_at REAL NOT NULL,
            updated_at REAL NOT NULL)""")
    guide_store._ensure_tables(store)
    with store._connect() as db:
        columns = {row["name"]: row for row in db.execute("PRAGMA table_info(guide_jobs)")}
    assert columns["fencing_token"]["dflt_value"] == "0"
    assert columns["fencing_token"]["notnull"] == 1


def test_guide_source_path_rejects_unsafe_version_ids(tmp_path):
    store = make_store(tmp_path)
    with pytest.raises(KeyError):
        guide_store.guide_source_path(store, "missing")
    now = time.time()
    with store._connect() as db:
        db.execute("INSERT INTO guide_versions(id,owner,built_in,filename,source_sha256,status,created_at,updated_at)"
                   " VALUES(?,?,?,?,?,?,?,?)",
                   ("../../escape", "alice", 0, "escape.docx", "", "uploaded", now, now))
    with pytest.raises(StoreError, match="invalid guide source path"):
        guide_store.guide_source_path(store, "../../escape")
    assert not (store.objects.parent / "escape.docx").exists()


def test_guide_metrics_count_versions_and_jobs(tmp_path):
    store = make_store(tmp_path)
    metrics = guide_store.guide_metrics(store)
    assert metrics["versions"] == {"total": 1, "built_in": 1, "custom": 0, "by_status": {"released": 1}}
    assert metrics["jobs"]["total"] == 0
    version = guide_store.create_custom_version(store, "alice", "custom.docx", guide_docx())
    job = guide_store.claim_guide_job(store)
    guide_store.finish_guide_job(store, job["id"], job["fencing_token"], document=parsed_document())
    guide_store.set_current_guide(store, "alice", version["id"])
    metrics = guide_store.guide_metrics(store)
    assert metrics["versions"]["custom"] == 1
    assert metrics["versions"]["by_status"]["parsed"] == 1
    assert metrics["jobs"]["by_status"] == {"completed": 1}
    assert metrics["owners_configured"] == 1
