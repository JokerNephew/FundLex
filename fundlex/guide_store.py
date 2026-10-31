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

from .store import Conflict, RunStore, StoreError

BUILTIN_GUIDE_ID = "builtin-v1"
BUILTIN_GUIDE_PATH = Path(__file__).resolve().parent.parent / "guides" / "builtin_guide_v1.json"
GUIDE_SOURCE_DIR = "guides"
ENABLEABLE_STATUSES = frozenset({"released", "parsed"})
# Certification lifecycle: a parsed version only becomes enableable when its
# parse went through the same quality channel as the built-in guide
# (deterministic validation clean + independent verification without leftover
# findings).  Reparse always creates a new version, so certification is never
# inherited from a predecessor.
QUALIFICATION_NOT_RUN = "not_run"
QUALIFICATION_CERTIFIED = "certified"
QUALIFICATION_FROZEN = "frozen_builtin"
ENABLEABLE_QUALIFICATIONS = frozenset({QUALIFICATION_CERTIFIED, QUALIFICATION_FROZEN})
PARSEABLE_STATUSES = frozenset({"uploaded", "parse_failed", "parsed", "failed"})
# User-initiated "reparse" is a new version whenever the version may already
# have been observed by a task.  Only an unpublished, never-parsed version can
# safely reuse its identity for a first attempt.
REPARSEABLE_STATUSES = frozenset({"uploaded", "parse_failed", "parsed", "failed", "released"})
MAX_GUIDE_JOB_ATTEMPTS = 3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS guide_versions (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, built_in INTEGER NOT NULL DEFAULT 0,
    parent_version_id TEXT NOT NULL DEFAULT '',
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
CREATE TABLE IF NOT EXISTS guide_rule_config (
    owner TEXT NOT NULL, guide_version_id TEXT NOT NULL,
    disabled_json MEDIUMTEXT NOT NULL DEFAULT '[]', updated_at REAL NOT NULL,
    PRIMARY KEY (owner, guide_version_id)
);
CREATE TABLE IF NOT EXISTS guide_jobs (
    id TEXT PRIMARY KEY, guide_version_id TEXT NOT NULL, owner TEXT NOT NULL, status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, lease_until REAL, error_code TEXT,
    fencing_token INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
"""

_VERSION_COLUMNS = {
    "built_in": "INTEGER NOT NULL DEFAULT 0",
    "parent_version_id": "TEXT NOT NULL DEFAULT ''",
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
    "fencing_token": "INTEGER NOT NULL DEFAULT 0",
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
    from .guide import guide_document_sha256
    return guide_document_sha256(doc)


def _validation_clean(validation: dict[str, Any]) -> bool:
    """The built-in channel's exit condition, recomputed from components.

    Mirrors :func:`fundlex.guide.build_guide_document`: no deterministic
    errors, no uncovered paragraphs and no verifier leftovers.  Missing keys
    count as empty so older fixtures stay valid; anything present and
    non-empty fails closed.
    """
    if not isinstance(validation, dict):
        return False
    if validation.get("errors") or validation.get("coverage_gaps"):
        return False
    verification = validation.get("verification")
    if isinstance(verification, dict):
        if verification.get("findings") or verification.get("invalid_findings"):
            return False
    return True


def _quality_failure_issues(validation: dict[str, Any]) -> dict[str, Any]:
    """Structured, user-facing reasons when the quality channel rejects a parse."""
    verification = validation.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    issues: dict[str, Any] = {
        "error_code": "GUIDE_VALIDATION_UNCLEAN",
        "clean": False,
        "errors": validation.get("errors") or [],
        "warnings": validation.get("warnings") or [],
        "coverage_gaps": validation.get("coverage_gaps") or [],
        "verification": {"findings": verification.get("findings") or [],
                         "invalid_findings": verification.get("invalid_findings") or 0,
                         "coverage_explanation": verification.get("coverage_explanation") or ""},
        "rounds": validation.get("rounds") or 0,
        "rounds_detail": validation.get("rounds_detail") or [],
        "detail": "解析结果未通过确定性校验或独立验证，不能启用；请修正指引后重新上传解析。",
    }
    return issues


def _version_dict(row) -> dict[str, Any]:
    rules = _json_or(row["rules_json"], {})
    groups = rules.get("groups") if isinstance(rules, dict) else None
    issues = _json_or(row["issues_json"], {})
    return {
        "id": row["id"], "owner": row["owner"], "built_in": bool(row["built_in"]),
        "parent_version_id": row["parent_version_id"] or "",
        "filename": row["filename"], "source_sha256": row["source_sha256"],
        "document_sha256": row["document_sha256"], "rules_sha256": row["rules_sha256"],
        "parser_version": row["parser_version"], "schema_version": row["schema_version"],
        "prompt_versions": _json_or(row["prompt_versions"], {}),
        "status": row["status"], "issues": issues,
        "qualification_status": row["qualification_status"],
        "review": issues.get("review") if isinstance(issues.get("review"), dict) else None,
        "rules_count": len(groups) if isinstance(groups, list) else 0,
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "released_at": row["released_at"],
    }


def _job_dict(row) -> dict[str, Any]:
    return {"id": row["id"], "guide_version_id": row["guide_version_id"], "owner": row["owner"],
            "status": row["status"], "attempts": row["attempts"], "lease_until": row["lease_until"],
            "error_code": row["error_code"], "fencing_token": row["fencing_token"],
            "created_at": row["created_at"],
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
    # Enabling requires the same qualification as the built-in guide:
    # deterministic validation clean plus verification without leftover
    # findings.  A re-parse produces a new version that must re-qualify; the
    # predecessor's certification never carries over.
    if version["qualification_status"] not in ENABLEABLE_QUALIFICATIONS:
        raise ValueError("GUIDE_NOT_CERTIFIED")
    # A parsed guide is data, not executable policy.  Custom operations must
    # have controlled registry entries before an owner can enable the guide.
    from .generation.registry import operation_registry_coverage_gaps
    gaps = operation_registry_coverage_gaps(guide_document(store, version_id))
    if gaps:
        raise ValueError("GUIDE_OPERATION_REGISTRY_MISSING:" + ",".join(gaps))
    with store._connect() as db:
        db.execute("INSERT OR REPLACE INTO guide_config(owner,guide_version_id,updated_at) VALUES(?,?,?)",
                   (owner, version_id, time.time()))
    return version


def _rule_entries(document: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten guide groups, accepting both flat rules and nested groups."""
    entries: list[dict[str, Any]] = []
    for group in (document or {}).get("groups") or []:
        if not isinstance(group, dict):
            continue
        nested = group.get("rules")
        if isinstance(nested, list):
            for rule in nested:
                if isinstance(rule, dict) and rule.get("rule_id"):
                    entries.append(rule)
        elif group.get("rule_id"):
            entries.append(group)
    return entries


RULE_OP_LABELS = {"append": "新增", "replace": "修改", "delete": "删除", "move": "移动", "keep": "保留"}


def _rule_requirement(rule: dict[str, Any]) -> str:
    """Human-readable what-change text for one rule (FL-D730: WYSIWYG rule pickers)."""
    text = str(rule.get("requirement") or "").strip()
    return text or str(rule.get("title") or "")


def _rule_operations_summary(rule: dict[str, Any], *, limit: int = 4) -> list[dict[str, str]]:
    """Condense raw rule operations into a few human-readable labels with a snippet."""
    counts: dict[str, int] = {}
    details: dict[str, str] = {}
    for op in rule.get("operations") or []:
        if not isinstance(op, dict):
            continue
        label = RULE_OP_LABELS.get(str(op.get("op") or ""), "调整")
        counts[label] = counts.get(label, 0) + 1
        if label not in details:
            snippet = str(op.get("new_text") or op.get("old_text") or "").strip()
            if snippet:
                details[label] = snippet[:80] + ("…" if len(snippet) > 80 else "")
    summary: list[dict[str, str]] = []
    for label in list(counts)[:limit]:
        entry: dict[str, str] = {"label": f"{label} {counts[label]} 处"}
        if label in details:
            entry["detail"] = details[label]
        summary.append(entry)
    return summary


def rule_settings(store: RunStore, owner: str, version_id: str) -> dict[str, Any]:
    """Owner-scoped enable/disable state for one guide version.

    Disabling is a task-level business choice, not a mutation of the certified
    guide.  The guide document and its hashes stay untouched; the task snapshot
    records which rule ids were disabled at creation time.
    """
    version = get_version(store, owner, version_id)
    if version["status"] not in ENABLEABLE_STATUSES:
        raise ValueError("GUIDE_NOT_READY")
    document = guide_document(store, version_id)
    entries = _rule_entries(document)
    with store._connect() as db:
        row = db.execute("SELECT disabled_json FROM guide_rule_config "
                         "WHERE owner=? AND guide_version_id=?", (owner, version_id)).fetchone()
    raw = row["disabled_json"] if row is not None else "[]"
    try:
        disabled = json.loads(raw)
    except (ValueError, TypeError):
        raise ValueError("GUIDE_RULE_SETTINGS_INVALID") from None
    if not isinstance(disabled, list) or any(not isinstance(item, str) for item in disabled):
        raise ValueError("GUIDE_RULE_SETTINGS_INVALID")
    disabled_set = {str(item) for item in disabled if isinstance(item, str)}
    known = {str(rule.get("rule_id")) for rule in entries}
    if disabled_set - known:
        raise ValueError("GUIDE_RULE_SETTINGS_INVALID")
    return {
        "version_id": version_id,
        "disabled_rule_ids": sorted(disabled_set),
        "rules": [{
            "rule_id": str(rule.get("rule_id")),
            "title": str(rule.get("title") or ""),
            "section_hint": str(rule.get("section_hint") or ""),
            "enabled": str(rule.get("rule_id")) not in disabled_set,
            "requirement": _rule_requirement(rule),
            "operations": _rule_operations_summary(rule),
        } for rule in entries],
    }


def set_rule_settings(store: RunStore, owner: str, version_id: str,
                      disabled_rule_ids: list[str] | tuple[str, ...] | None) -> dict[str, Any]:
    """Persist disabled rule ids after validating them against the bound guide."""
    settings = rule_settings(store, owner, version_id)
    known = {item["rule_id"] for item in settings["rules"]}
    disabled = sorted({str(item).strip() for item in (disabled_rule_ids or [])
                       if str(item).strip()})
    unknown = sorted(set(disabled) - known)
    if unknown:
        raise ValueError("GUIDE_RULE_UNKNOWN:" + ",".join(unknown))
    if known and not (known - set(disabled)):
        raise ValueError("GUIDE_RULES_ALL_DISABLED")
    with store._connect() as db:
        db.execute("INSERT OR REPLACE INTO guide_rule_config"
                   "(owner,guide_version_id,disabled_json,updated_at) VALUES(?,?,?,?)",
                   (owner, version_id, json.dumps(disabled, ensure_ascii=False), time.time()))
    return rule_settings(store, owner, version_id)


def create_custom_version(store: RunStore, owner: str, filename: str, source_bytes: bytes,
                          *, parent_version_id: str = "") -> dict[str, Any]:
    """Stage a guide DOCX under ``objects/guides/<version_id>.docx`` and queue parsing.

    ``parent_version_id`` records the immutable predecessor when the owner
    re-parses an already-published guide.  The predecessor row and its rules
    hash are never modified.
    """
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
                (id,owner,built_in,parent_version_id,filename,source_sha256,status,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (version_id, owner, 0, parent_version_id or "", filename,
                 hashlib.sha256(data).hexdigest(), "uploaded", now, now))
            job_id = _insert_parse_job(db, version_id, owner)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {**get_version(store, owner, version_id), "job_id": job_id}


def reparse_version(store: RunStore, owner: str, version_id: str) -> dict[str, Any]:
    """Return the version a re-parse request should target.

    A version that may already have been observed by a task is immutable, so
    re-parsing it creates a new version with ``parent_version_id`` pointing at
    the old row.  The old row, rules and hash remain untouched.  If an active
    parse job already exists for the same source, that pending version is
    returned instead of creating duplicate versions for repeated clicks.
    """
    _ensure_tables(store)
    version = get_version(store, owner, version_id)
    if version["built_in"]:
        raise ValueError("GUIDE_BUILTIN_NOT_REPARSEABLE")
    if version["status"] not in REPARSEABLE_STATUSES:
        raise ValueError("GUIDE_NOT_PARSEABLE")
    with store._connect() as db:
        active = db.execute(
            """SELECT j.id AS job_id,v.* FROM guide_jobs j
               JOIN guide_versions v ON v.id=j.guide_version_id
               WHERE v.owner=? AND v.source_sha256=?
                 AND j.status IN ('queued','leased')
               ORDER BY j.created_at DESC LIMIT 1""",
            (owner, version["source_sha256"]),
        ).fetchone()
    if active is not None:
        return {**_version_dict(active), "job_id": active["job_id"]}
    source = guide_source_path(store, version_id)
    if not source.is_file():
        raise KeyError("guide source not available")
    data = source.read_bytes()
    # Retire the predecessor's retryable jobs before creating the new version.
    # Otherwise a worker could claim the old parse_failed job first and parse
    # the superseded version again.
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""UPDATE guide_jobs SET status='failed',
            error_code='GUIDE_VERSION_SUPERSEDED',lease_until=NULL,updated_at=?
            WHERE guide_version_id=? AND status IN ('queued','parse_failed')""",
                   (time.time(), version_id))
    return create_custom_version(store, owner, version["filename"], data,
                                 parent_version_id=version_id)


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
        row = db.execute("SELECT id,owner,status FROM guide_versions WHERE id=?", (version_id,)).fetchone()
        if row is None:
            raise KeyError("guide version not found")
        if row["status"] not in PARSEABLE_STATUSES:
            raise ValueError("GUIDE_NOT_PARSEABLE")
        if row["status"] in {"parsed", "released"}:
            # A published snapshot is immutable; callers must create a new
            # version instead of mutating rules bound to existing tasks.
            raise ValueError("GUIDE_REPARSE_REQUIRES_NEW_VERSION")
        # Repeated clicks must share the current job, including its retry budget.
        active = db.execute("SELECT id,status FROM guide_jobs WHERE guide_version_id=? "
                            "AND status IN ('queued','leased','parse_failed') ORDER BY created_at DESC",
                            (version_id,)).fetchone()
        if active is not None:
            db.execute("UPDATE guide_versions SET status=?,updated_at=? WHERE id=?",
                       ("parsing" if active["status"] == "leased" else "uploaded", time.time(), version_id))
            return active["id"]
        db.execute("UPDATE guide_versions SET status='uploaded',updated_at=? WHERE id=?",
                   (time.time(), version_id))
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
        # A leased job past its expiry, or a queued job left at the attempt
        # ceiling by an older release implementation, must not remain forever
        # unclaimable.
        exhausted = db.execute(
            "SELECT id,guide_version_id FROM guide_jobs WHERE attempts>=? AND ("
            "(status='leased' AND lease_until<=?) OR status IN ('queued','parse_failed'))",
            (MAX_GUIDE_JOB_ATTEMPTS, now)).fetchall()
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
        fencing_token = row["fencing_token"] + 1
        changed = db.execute("UPDATE guide_jobs SET status='leased',attempts=?,lease_until=?,"
                             "error_code=NULL,fencing_token=?,updated_at=? WHERE id=? AND "
                             "fencing_token=? AND (lease_until IS NULL OR lease_until<=?)",
                             (attempts, lease_until, fencing_token, now, row["id"],
                              row["fencing_token"], now)).rowcount
        if changed != 1:
            raise Conflict("guide job claim lost")
        db.execute("UPDATE guide_versions SET status='parsing',updated_at=? WHERE id=? "
                   "AND status IN ('uploaded','parse_failed')", (now, row["guide_version_id"]))
    return dict(row) | {"status": "leased", "attempts": attempts, "lease_until": lease_until,
                         "fencing_token": fencing_token}


def release_guide_job(store: RunStore, job_id: str, fencing_token: int) -> dict[str, Any]:
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
        if (row["status"] != "leased" or row["fencing_token"] != fencing_token
                or row["lease_until"] is None or row["lease_until"] <= now):
            raise Conflict("stale guide job lease")
        delay = min(2 * (2 ** max(row["attempts"] - 1, 0)) * random.uniform(0.8, 1.2), 300)
        # A release is a recoverable stop, not a failed attempt.  Refund the
        # claim so repeated model-budget/network stops cannot exhaust the retry
        # budget while a real expiry/crash still does.
        attempts = max(int(row["attempts"]) - 1, 0)
        changed = db.execute("UPDATE guide_jobs SET status='queued',attempts=?,lease_until=?,updated_at=? "
                             "WHERE id=? AND fencing_token=? AND status='leased' AND lease_until>?",
                             (attempts, now + delay, now, job_id, fencing_token, now)).rowcount
        if changed != 1:
            raise Conflict("stale guide job lease")
        db.execute("UPDATE guide_versions SET status='uploaded',updated_at=? WHERE id=? AND status='parsing'",
                   (now, row["guide_version_id"]))
        refreshed = db.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
    return _job_dict(refreshed)


def finish_guide_job(store: RunStore, job_id: str, fencing_token: int, *, document: dict[str, Any] | None = None,
                     error_code: str | None = None) -> dict[str, Any]:
    """Close a claimed job; returns ``{"job": ..., "version": ...}`` records.

    A parsed document moves the version to ``parsed`` with its rules, hashes,
    parser/prompt versions and validation issues — but only when the parse
    passed the same quality channel as the built-in guide (deterministic
    validation clean plus verification without leftover findings).  An unclean
    document is converted here into a terminal ``GUIDE_VALIDATION_UNCLEAN``
    failure with structured, user-facing reasons; low-quality parses are never
    silently released.  A re-parse creates a new version, which must qualify
    from scratch.  Other errors move the version to ``parse_failed``
    (retryable) or ``failed`` once attempts are exhausted.
    """
    _ensure_tables(store)
    if document is not None and not isinstance(document, dict):
        raise ValueError("GUIDE_DOCUMENT_INVALID")
    now = time.time()
    quality_issues: dict[str, Any] | None = None
    if document is not None and not error_code:
        validation = document.get("validation") if isinstance(document.get("validation"), dict) else {}
        if not _validation_clean(validation):
            quality_issues = _quality_failure_issues(validation)
            error_code = "GUIDE_VALIDATION_UNCLEAN"
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        job = db.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
        if job is None:
            raise KeyError("guide job not found")
        if (job["status"] != "leased" or job["fencing_token"] != fencing_token
                or job["lease_until"] is None or job["lease_until"] <= now):
            raise Conflict("stale guide job lease")
        version_id = job["guide_version_id"]
        if document is not None and not error_code:
            document_sha = _document_sha(document)
            issues = document.get("validation") if isinstance(document.get("validation"), dict) else {}
            db.execute("""UPDATE guide_versions SET status='parsed',rules_json=?,document_sha256=?,
                rules_sha256=?,parser_version=?,schema_version=?,prompt_versions=?,issues_json=?,
                qualification_status=?,updated_at=?
                WHERE id=?""",
                (json.dumps(document, ensure_ascii=False), document_sha, document_sha,
                 str(document.get("parser_version") or ""), str(document.get("schema_version") or ""),
                 json.dumps(document.get("prompt_versions") or {}, ensure_ascii=False),
                 json.dumps(issues, ensure_ascii=False), QUALIFICATION_CERTIFIED, now, version_id))
            changed = db.execute("UPDATE guide_jobs SET status='completed',error_code=NULL,lease_until=NULL,"
                                 "updated_at=? WHERE id=? AND fencing_token=? AND status='leased' "
                                 "AND lease_until>?", (now, job_id, fencing_token, now)).rowcount
            if changed != 1:
                raise Conflict("stale guide job lease")
        else:
            code = error_code or "GUIDE_PARSE_FAILED"
            # Quality-gate rejections are terminal for this version: the same
            # source re-parsed automatically would repeat the model spend, and
            # the user remedy is re-upload/re-parse into a new version.
            status = "failed" if (quality_issues is not None
                                  or job["attempts"] >= MAX_GUIDE_JOB_ATTEMPTS) else "parse_failed"
            issues = quality_issues or {"error_code": code, "errors": [{"code": code}],
                                        "attempts": job["attempts"]}
            db.execute("UPDATE guide_versions SET status=?,issues_json=?,updated_at=? WHERE id=?",
                       (status, json.dumps(issues, ensure_ascii=False), now, version_id))
            changed = db.execute("UPDATE guide_jobs SET status=?,error_code=?,lease_until=NULL,updated_at=? "
                                 "WHERE id=? AND fencing_token=? AND status='leased' AND lease_until>?",
                                 (status, code, now, job_id, fencing_token, now)).rowcount
            if changed != 1:
                raise Conflict("stale guide job lease")
        refreshed_job = db.execute("SELECT * FROM guide_jobs WHERE id=?", (job_id,)).fetchone()
        version = db.execute("SELECT * FROM guide_versions WHERE id=?", (version_id,)).fetchone()
    return {"job": _job_dict(refreshed_job), "version": _version_dict(version)}


def mark_guide_review(store: RunStore, owner: str, version_id: str,
                      review: dict[str, Any] | None) -> dict[str, Any]:
    """Record (or clear, with ``None``) a smoke-review verdict on a version.

    A ``needs_review`` verdict is advisory — it never blocks enabling — but it
    is shown to the owner with the dimensions that degraded versus the
    built-in guide.  ``review`` must be JSON-serializable; recommended shape:
    ``{"status": "needs_review", "dimensions": {...}, "evaluated_at": ...}``.
    """
    version = get_version(store, owner, version_id)
    if review is not None:
        if not isinstance(review, dict):
            raise ValueError("GUIDE_REVIEW_INVALID")
        json.dumps(review, ensure_ascii=False)  # fail fast on non-serializable values
    issues = version.get("issues") if isinstance(version.get("issues"), dict) else {}
    updated_issues = dict(issues)
    if review is None:
        updated_issues.pop("review", None)
    else:
        updated_issues["review"] = review
    with store._connect() as db:
        db.execute("UPDATE guide_versions SET issues_json=?,updated_at=? WHERE id=?",
                   (json.dumps(updated_issues, ensure_ascii=False), time.time(), version["id"]))
    return get_version(store, owner, version_id)


def diff_versions(store: RunStore, owner: str, version_id: str,
                  against_id: str) -> dict[str, Any]:
    """Deterministic diff of two visible, parsed versions (``against`` is the base)."""
    if not isinstance(against_id, str) or not against_id.strip():
        raise ValueError("GUIDE_DIFF_AGAINST_REQUIRED")
    # get_version enforces owner visibility for each side independently.
    get_version(store, owner, version_id)
    get_version(store, owner, against_id.strip())
    before = guide_document(store, against_id.strip())
    after = guide_document(store, version_id)
    from .guide_diff import diff_guide_documents
    return diff_guide_documents(before, after)


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
