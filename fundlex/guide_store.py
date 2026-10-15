"""Guide version persistence, owner configuration and parse jobs.

Guide versions, the owner's current-guide configuration and the asynchronous
parse queue share the runs database so the API, the worker and later processes
see one state.  The built-in guide is installed idempotently and stays visible
to every owner; a custom version is visible to its owner only.  A task binds an
immutable guide snapshot (version id + rules hash) at creation time; this module
is the only writer of that snapshot.

The tables follow the migration pattern of :mod:`fundlex.store`: create-if-
missing plus guarded ``ALTER ... ADD COLUMN``.  ``rules_json``/``issues_json``
are declared ``MEDIUMTEXT`` so the MySQL translation keeps them as full text
instead of the default bounded ``VARCHAR(255)``.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import time
import uuid
from pathlib import Path
from typing import Any

from .store import RunStore, StoreError

BUILTIN_GUIDE_ID = "builtin-v1"
BUILTIN_GUIDE_PATH = Path(__file__).resolve().parent.parent / "guides" / "builtin_guide_v1.json"
GUIDE_SOURCE_DIR = "guides"
ENABLEABLE_STATUSES = frozenset({"released", "parsed"})
MAX_GUIDE_JOB_ATTEMPTS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guide_versions (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, built_in INTEGER NOT NULL DEFAULT 0,
    filename TEXT NOT NULL, source_sha256 TEXT NOT NULL,
    document_sha256 TEXT NOT NULL DEFAULT '', parser_version TEXT NOT NULL DEFAULT '',
    schema_version TEXT NOT NULL DEFAULT '', prompt_versions TEXT NOT NULL DEFAULT '{}',
    rules_json MEDIUMTEXT NOT NULL DEFAULT '', rules_sha256 TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL, issues_json MEDIUMTEXT NOT NULL DEFAULT '{}',
    qualification_status TEXT NOT NULL DEFAULT 'not_run',
    created_at REAL NOT NULL, updated_at REAL NOT NULL, released_at REAL
);
CREATE TABLE IF NOT EXISTS guide_config (
    owner TEXT PRIMARY KEY, guide_version_id TEXT NOT NULL, updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS guide_jobs (
    id TEXT PRIMARY KEY, guide_version_id TEXT NOT NULL, owner TEXT NOT NULL, status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, lease_until REAL, error_code TEXT,
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
"""

_VERSION_COLUMNS = {
    "built_in": "INTEGER NOT NULL DEFAULT 0",
    "filename": "TEXT NOT NULL DEFAULT ''",
    "source_sha256": "TEXT NOT NULL DEFAULT ''",
    "document_sha256": "TEXT NOT NULL DEFAULT ''",
    "parser_version": "TEXT NOT NULL DEFAULT ''",
    "schema_version": "TEXT NOT NULL DEFAULT ''",
    "prompt_versions": "TEXT NOT NULL DEFAULT '{}'",
    "rules_json": "MEDIUMTEXT NOT NULL DEFAULT ''",
    "rules_sha256": "TEXT NOT NULL DEFAULT ''",
    "status": "TEXT NOT NULL DEFAULT 'uploaded'",
    "issues_json": "MEDIUMTEXT NOT NULL DEFAULT '{}'",
    "qualification_status": "TEXT NOT NULL DEFAULT 'not_run'",
    "created_at": "REAL NOT NULL DEFAULT 0",
    "updated_at": "REAL NOT NULL DEFAULT 0",
    "released_at": "REAL",
}
_JOB_COLUMNS = {
    "guide_version_id": "TEXT NOT NULL DEFAULT ''",
    "owner": "TEXT NOT NULL DEFAULT ''",
    "status": "TEXT NOT NULL DEFAULT 'queued'",
    "attempts": "INTEGER NOT NULL DEFAULT 0",
    "lease_until": "REAL",
    "error_code": "TEXT",
    "created_at": "REAL NOT NULL DEFAULT 0",
    "updated_at": "REAL NOT NULL DEFAULT 0",
}


def _ensure_columns(db, table: str, columns: dict[str, str]) -> None:
    present = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
    for name, definition in columns.items():
        if name not in present:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _ensure_tables(store: RunStore) -> None:
    """Create the guide schema once per store instance (guarded DDL)."""
    if getattr(store, "_guide_schema_ready", False):
        return
    with store._connect() as db:
        db.executescript(_SCHEMA)
        _ensure_columns(db, "guide_versions", _VERSION_COLUMNS)
        _ensure_columns(db, "guide_jobs", _JOB_COLUMNS)
    store._guide_schema_ready = True


def _source_path(store: RunStore, version_id: str) -> Path:
    """Objects-area path for one guide source with the RunStore safety check."""
    path = (store.objects / GUIDE_SOURCE_DIR / f"{version_id}.docx").resolve()
    if not path.is_relative_to(store.objects.resolve()):
        raise StoreError("invalid guide source path")
    return path


def _json_or(raw: Any, default: Any) -> Any:
    try:
        value = json.loads(raw) if raw else default
    except (ValueError, TypeError):
        return default
    return value if isinstance(value, type(default)) else default


def _document_sha(doc: dict[str, Any]) -> str:
    stored = str(doc.get("document_sha256") or "")
    if stored:
        return stored
    from .guide import guide_document_sha256
    return guide_document_sha256(doc)


def _version_dict(row) -> dict[str, Any]:
    rules = _json_or(row["rules_json"], {})
    groups = rules.get("groups") if isinstance(rules, dict) else None
    return {
        "id": row["id"], "owner": row["owner"], "built_in": bool(row["built_in"]),
        "filename": row["filename"], "source_sha256": row["source_sha256"],
        "document_sha256": row["document_sha256"], "rules_sha256": row["rules_sha256"],
        "parser_version": row["parser_version"], "schema_version": row["schema_version"],
        "prompt_versions": _json_or(row["prompt_versions"], {}),
        "status": row["status"], "issues": _json_or(row["issues_json"], {}),
        "qualification_status": row["qualification_status"],
        "rules_count": len(groups) if isinstance(groups, list) else 0,
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "released_at": row["released_at"],
    }


def _job_dict(row) -> dict[str, Any]:
    return {"id": row["id"], "guide_version_id": row["guide_version_id"], "owner": row["owner"],
            "status": row["status"], "attempts": row["attempts"], "lease_until": row["lease_until"],
            "error_code": row["error_code"], "created_at": row["created_at"],
            "updated_at": row["updated_at"]}


def load_builtin_document() -> dict[str, Any]:
    """The frozen built-in guide document (authoritative ``document_sha256``)."""
    data = json.loads(BUILTIN_GUIDE_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise StoreError("built-in guide document is invalid")
    return data


def ensure_builtin_guide(store: RunStore) -> str:
    """Install the built-in guide version idempotently; returns its id."""
    _ensure_tables(store)
    doc = load_builtin_document()
    document_sha = _document_sha(doc)
    now = time.time()
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM guide_versions WHERE id=?", (BUILTIN_GUIDE_ID,)).fetchone()
        if row is None:
            db.execute("""INSERT INTO guide_versions
                (id,owner,built_in,filename,source_sha256,document_sha256,parser_version,schema_version,
                 prompt_versions,rules_json,rules_sha256,status,issues_json,qualification_status,
                 created_at,updated_at,released_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (BUILTIN_GUIDE_ID, "", 1, str(doc.get("source_path_hint") or BUILTIN_GUIDE_PATH.name),
                 str(doc.get("source_sha256") or ""), document_sha, str(doc.get("parser_version") or ""),
                 str(doc.get("schema_version") or ""), json.dumps(doc.get("prompt_versions") or {}, ensure_ascii=False),
                 json.dumps(doc, ensure_ascii=False), document_sha, "released",
                 json.dumps(doc.get("validation") or {}, ensure_ascii=False), "frozen_builtin", now, now, now))
        elif (row["rules_sha256"] != document_sha or row["built_in"] != 1 or row["status"] != "released"
                or row["qualification_status"] != "frozen_builtin"):
            # Converge to the frozen file without rewriting timestamps on every call.
            db.execute("""UPDATE guide_versions SET built_in=1,status='released',qualification_status='frozen_builtin',
                filename=?,source_sha256=?,document_sha256=?,parser_version=?,schema_version=?,prompt_versions=?,
                rules_json=?,rules_sha256=?,updated_at=? WHERE id=?""",
                (str(doc.get("source_path_hint") or BUILTIN_GUIDE_PATH.name), str(doc.get("source_sha256") or ""),
                 document_sha, str(doc.get("parser_version") or ""), str(doc.get("schema_version") or ""),
                 json.dumps(doc.get("prompt_versions") or {}, ensure_ascii=False),
                 json.dumps(doc, ensure_ascii=False), document_sha, now, BUILTIN_GUIDE_ID))
    return BUILTIN_GUIDE_ID


def list_versions(store: RunStore, owner: str) -> list[dict[str, Any]]:
    """Built-in plus the owner's custom versions, built-in first."""
    _ensure_tables(store)
    ensure_builtin_guide(store)
    with store._connect() as db:
        rows = db.execute("SELECT * FROM guide_versions WHERE built_in=1 OR owner=? "
                          "ORDER BY built_in DESC, created_at DESC", (owner,)).fetchall()
    return [_version_dict(row) for row in rows]


def get_version(store: RunStore, owner: str, version_id: str) -> dict[str, Any]:
    """Version metadata; built-in visible to everyone, custom only to its owner."""
    _ensure_tables(store)
    if version_id == BUILTIN_GUIDE_ID:
        ensure_builtin_guide(store)
    with store._connect() as db:
        row = db.execute("SELECT * FROM guide_versions WHERE id=?", (version_id,)).fetchone()
    if row is None or (not row["built_in"] and row["owner"] != owner):
        raise KeyError("guide version not found")
    return _version_dict(row)


def guide_document(store: RunStore, version_id: str) -> dict[str, Any]:
    """The stored rules document for a version (parsed custom or built-in)."""
    _ensure_tables(store)
    if version_id == BUILTIN_GUIDE_ID:
        ensure_builtin_guide(store)
    with store._connect() as db:
        row = db.execute("SELECT * FROM guide_versions WHERE id=?", (version_id,)).fetchone()
    if row is None:
        raise KeyError("guide version not found")
    raw = row["rules_json"] or ""
    if raw:
        doc = _json_or(raw, {})
        if isinstance(doc, dict) and doc:
            return doc
    if row["built_in"]:
        return load_builtin_document()
    raise KeyError("guide document not available")


def current_guide(store: RunStore, owner: str) -> dict[str, Any]:
    """The owner's configured guide version, defaulting to the built-in."""
    _ensure_tables(store)
    ensure_builtin_guide(store)
    with store._connect() as db:
        config = db.execute("SELECT guide_version_id FROM guide_config WHERE owner=?", (owner,)).fetchone()
        if config:
            row = db.execute("SELECT * FROM guide_versions WHERE id=?", (config["guide_version_id"],)).fetchone()
            if row is not None and (row["built_in"] or row["owner"] == owner):
                return _version_dict(row)
        row = db.execute("SELECT * FROM guide_versions WHERE id=?", (BUILTIN_GUIDE_ID,)).fetchone()
    return _version_dict(row)


def set_current_guide(store: RunStore, owner: str, version_id: str) -> dict[str, Any]:
    """Point the owner's new tasks at a visible, enableable version.

    Only ``released`` and ``parsed`` versions may be enabled; anything else
    (uploaded, parsing, parse_failed, failed, archived) raises
    ``ValueError("GUIDE_NOT_ENABLEABLE")``.
    """
    version = get_version(store, owner, version_id)
    if version["status"] not in ENABLEABLE_STATUSES:
        raise ValueError("GUIDE_NOT_ENABLEABLE")
    with store._connect() as db:
        db.execute("INSERT OR REPLACE INTO guide_config(owner,guide_version_id,updated_at) VALUES(?,?,?)",
                   (owner, version_id, time.time()))
    return version


def create_custom_version(store: RunStore, owner: str, filename: str, source_bytes: bytes) -> dict[str, Any]:
    """Stage a guide DOCX under ``objects/guides/<version_id>.docx`` and queue parsing."""
    _ensure_tables(store)
    if not isinstance(owner, str) or not owner:
        raise ValueError("GUIDE_OWNER_REQUIRED")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("GUIDE_FILENAME_REQUIRED")
    if not isinstance(source_bytes, (bytes, bytearray)) or not source_bytes:
        raise ValueError("GUIDE_SOURCE_INVALID")
    data = bytes(source_bytes)
    version_id, now = uuid.uuid4().hex, time.time()
    path = _source_path(store, version_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        with store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""INSERT INTO guide_versions
                (id,owner,built_in,filename,source_sha256,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)""",
                (version_id, owner, 0, filename, hashlib.sha256(data).hexdigest(), "uploaded", now, now))
            job_id = _insert_parse_job(db, version_id, owner)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {**get_version(store, owner, version_id), "job_id": job_id}


def _insert_parse_job(db, version_id: str, owner: str) -> str:
    job_id, now = uuid.uuid4().hex, time.time()
    db.execute("""INSERT INTO guide_jobs
        (id,guide_version_id,owner,status,attempts,created_at,updated_at) VALUES(?,?,?,?,?,?,?)""",
        (job_id, version_id, owner, "queued", 0, now, now))
    return job_id


def enqueue_parse(store: RunStore, version_id: str) -> str:
    """Queue one parse job for a custom version; returns the job id."""
    _ensure_tables(store)
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT id,owner FROM guide_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            raise KeyError("guide version not found")
        return _insert_parse_job(db, version_id, row["owner"])


def claim_guide_job(store: RunStore, *, lease_seconds: int = 600) -> dict[str, Any] | None:
    """Claim the oldest parse job whose owner has no active lease.

    Expired leases are reclaimed; a job is never attempted more than
    ``MAX_GUIDE_JOB_ATTEMPTS`` times, and one owner has at most one job in
    flight so two custom guides cannot interleave.
    """
    _ensure_tables(store)
    now = time.time()
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        exhausted = db.execute("SELECT id,guide_version_id FROM guide_jobs WHERE status='leased' "
                               "AND lease_until<=? AND attempts>=?",
                               (now, MAX_GUIDE_JOB_ATTEMPTS)).fetchall()
        for item in exhausted:
            db.execute("UPDATE guide_jobs SET status='failed',error_code='GUIDE_PARSE_ATTEMPTS_EXHAUSTED',"
                       "lease_until=NULL,updated_at=? WHERE id=?", (now, item["id"]))
            db.execute("UPDATE guide_versions SET status='failed',updated_at=? WHERE id=? "
                       "AND status IN ('uploaded','parsing','parse_failed')", (now, item["guide_version_id"]))
        candidate = """SELECT j.* FROM guide_jobs j WHERE j.attempts < ?
            AND (j.lease_until IS NULL OR j.lease_until<=?)
            AND (j.status IN ('queued','parse_failed') OR j.status='leased')
            AND NOT EXISTS (SELECT 1 FROM guide_jobs active WHERE active.owner=j.owner
                AND active.status='leased' AND active.lease_until>?)
            ORDER BY j.created_at,j.id LIMIT 1"""
        if store.database.dialect == "mysql":
            # Without the row lock two workers could claim the same guide job.
            candidate += " FOR UPDATE"
        row = db.execute(candidate, (MAX_GUIDE_JOB_ATTEMPTS, now, now)).fetchone()
        if row is None:
            return None
        attempts = row["attempts"] + 1
        lease_until = now + lease_seconds
        db.execute("UPDATE guide_jobs SET status='leased',attempts=?,lease_until=?,error_code=NULL,"
                   "updated_at=? WHERE id=?", (attempts, lease_until, now, row["id"]))
        db.execute("UPDATE guide_versions SET status='parsing',updated_at=? WHERE id=? "
                   "AND status IN ('uploaded','parse_failed')", (now, row["guide_version_id"]))
    return dict(row) | {"status": "leased", "attempts": attempts, "lease_until": lease_until}


def release_guide_job(store: RunStore, job_id: str) -> dict[str, Any]:
    """Return a claimed job to the queue without consuming the attempt.

    ``lease_until`` doubles as the earliest re-claim time with the same
    exponential backoff as document retries, so a stopped parse cannot spin.
    """
    _ensure_tables(store)
    now = time.time()
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise KeyError("guide job not found")
        if row["status"] == "leased":
            delay = min(2 * (2 ** max(row["attempts"] - 1, 0)) * random.uniform(0.8, 1.2), 300)
            db.execute("UPDATE guide_jobs SET status='queued',lease_until=?,updated_at=? WHERE id=?",
                       (now + delay, now, job_id))
            db.execute("UPDATE guide_versions SET status='uploaded',updated_at=? WHERE id=? AND status='parsing'",
                       (now, row["guide_version_id"]))
        refreshed = db.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
    return _job_dict(refreshed)


def finish_guide_job(store: RunStore, job_id: str, *, document: dict[str, Any] | None = None,
                     error_code: str | None = None) -> dict[str, Any]:
    """Close a claimed job; returns ``{"job": ..., "version": ...}`` records.

    A parsed document moves the version to ``parsed`` with its rules, hashes,
    parser/prompt versions and validation issues.  An error moves it to
    ``parse_failed`` (retryable) or ``failed`` once attempts are exhausted.
    """
    _ensure_tables(store)
    if document is not None and not isinstance(document, dict):
        raise ValueError("GUIDE_DOCUMENT_INVALID")
    now = time.time()
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError("guide job not found")
        version_id = job["guide_version_id"]
        if document is not None and not error_code:
            document_sha = _document_sha(document)
            issues = document.get("validation") if isinstance(document.get("validation"), dict) else {}
            db.execute("""UPDATE guide_versions SET status='parsed',rules_json=?,document_sha256=?,
                rules_sha256=?,parser_version=?,schema_version=?,prompt_versions=?,issues_json=?,updated_at=?
                WHERE id=?""",
                (json.dumps(document, ensure_ascii=False), document_sha, document_sha,
                 str(document.get("parser_version") or ""), str(document.get("schema_version") or ""),
                 json.dumps(document.get("prompt_versions") or {}, ensure_ascii=False),
                 json.dumps(issues, ensure_ascii=False), now, version_id))
            db.execute("UPDATE guide_jobs SET status='completed',error_code=NULL,lease_until=NULL,"
                       "updated_at=? WHERE id=?", (now, job_id))
        else:
            code = error_code or "GUIDE_PARSE_FAILED"
            status = "failed" if job["attempts"] >= MAX_GUIDE_JOB_ATTEMPTS else "parse_failed"
            issues = {"error_code": code, "errors": [{"code": code}], "attempts": job["attempts"]}
            db.execute("UPDATE guide_versions SET status=?,issues_json=?,updated_at=? WHERE id=?",
                       (status, json.dumps(issues, ensure_ascii=False), now, version_id))
            db.execute("UPDATE guide_jobs SET status=?,error_code=?,lease_until=NULL,updated_at=? WHERE id=?",
                       (status, code, now, job_id))
        refreshed_job = db.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
        version = db.execute("SELECT * FROM guide_versions WHERE id=?", (version_id,)).fetchone()
    return {"job": _job_dict(refreshed_job), "version": _version_dict(version)}


def guide_source_path(store: RunStore, version_id: str) -> Path:
    """Stored source for a version; built-in resolves to the frozen JSON."""
    _ensure_tables(store)
    with store._connect() as db:
        row = db.execute("SELECT built_in FROM guide_versions WHERE id=?", (version_id,)).fetchone()
    if row is None:
        raise KeyError("guide version not found")
    if row["built_in"]:
        return BUILTIN_GUIDE_PATH
    return _source_path(store, version_id)


def guide_metrics(store: RunStore) -> dict[str, Any]:
    """Counters for dashboards: version and parse-job states."""
    _ensure_tables(store)
    with store._connect() as db:
        versions = {row["status"]: row["n"] for row in
                    db.execute("SELECT status,COUNT(*) AS n FROM guide_versions GROUP BY status")}
        jobs = {row["status"]: row["n"] for row in
                db.execute("SELECT status,COUNT(*) AS n FROM guide_jobs GROUP BY status")}
        built_in = db.execute("SELECT COUNT(*) AS n FROM guide_versions WHERE built_in=1").fetchone()["n"]
        custom = db.execute("SELECT COUNT(*) AS n FROM guide_versions WHERE built_in=0").fetchone()["n"]
        configured = db.execute("SELECT COUNT(*) AS n FROM guide_config").fetchone()["n"]
    return {"versions": {"total": built_in + custom, "built_in": built_in, "custom": custom,
                         "by_status": versions},
            "jobs": {"total": sum(jobs.values()), "by_status": jobs},
            "owners_configured": configured}
