"""Persistence for the regulation-driven guide generation feature.

The feature shares the FundLex database and migration conventions but keeps its
tables in a separate ``gg_`` namespace.  Large JSON/text columns use
``MEDIUMTEXT`` so the MySQL adapter does not truncate evidence.  Every table
that participates in the evidence chain is keyed by run id and a stable object
id; stages are resumable through ``gg_steps`` and ``gg_jobs``.
"""
from __future__ import annotations

import json
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Iterable

from ..store import Conflict, NotFound, RunStore, StoreError
from .models import (
    ClauseUnit,
    ContractVersion,
    CorpusSnapshot,
    GuideItem,
    ImpactCandidate,
    LocalGuideCandidate,
    PolicyRequirement,
    RegulationBlock,
    RegulationDocument,
    canonical_json,
    sha256_json,
    utc_now,
)

SCHEMA_VERSION = "guide-generation-1"
CANDIDATE_VERSION_STATUSES = {
    "draft", "candidate_ready", "human_draft", "approved", "published",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gg_runs (
    id TEXT PRIMARY KEY, owner TEXT NOT NULL, filename TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '', source_sha256 TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT NOT NULL DEFAULT '', error_code TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL, updated_at REAL NOT NULL,
    corpus_snapshot_id TEXT NOT NULL DEFAULT '', regulation_document_id TEXT NOT NULL DEFAULT '',
    regulation_document_sha256 TEXT NOT NULL DEFAULT '', guide_sha256 TEXT NOT NULL DEFAULT '',
    evidence_sha256 TEXT NOT NULL DEFAULT '', report_sha256 TEXT NOT NULL DEFAULT '',
    engine_status TEXT NOT NULL DEFAULT 'not_run',
    qualification_status TEXT NOT NULL DEFAULT 'not_qualified',
    commit_sha TEXT NOT NULL DEFAULT '', code_build TEXT NOT NULL DEFAULT '',
    runtime_config_sha256 TEXT NOT NULL DEFAULT '', lockfile_sha256 TEXT NOT NULL DEFAULT '',
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS gg_candidate_guides (
    candidate_guide_id TEXT PRIMARY KEY, owner TEXT NOT NULL, run_id TEXT NOT NULL UNIQUE,
    current_version_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft',
    created_at REAL NOT NULL, updated_at REAL NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS gg_candidate_guides_owner ON gg_candidate_guides(owner, created_at);
CREATE TABLE IF NOT EXISTS gg_candidate_versions (
    candidate_version_id TEXT PRIMARY KEY, candidate_guide_id TEXT NOT NULL, run_id TEXT NOT NULL,
    version_no INTEGER NOT NULL, parent_version_id TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'draft',
    content_sha256 TEXT NOT NULL DEFAULT '', human_version_no INTEGER NOT NULL DEFAULT 0,
    approved_by TEXT NOT NULL DEFAULT '', approved_at REAL, published_by TEXT NOT NULL DEFAULT '', published_at REAL,
    created_at REAL NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}',
    UNIQUE(candidate_guide_id, version_no)
);
CREATE INDEX IF NOT EXISTS gg_candidate_versions_run ON gg_candidate_versions(run_id, version_no);
CREATE TABLE IF NOT EXISTS gg_blocks (
    run_id TEXT NOT NULL, block_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    type TEXT NOT NULL, text MEDIUMTEXT NOT NULL, article_no TEXT NOT NULL DEFAULT '',
    heading_level INTEGER NOT NULL DEFAULT 0, page INTEGER,
    source_anchor_json MEDIUMTEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, block_id)
);
CREATE TABLE IF NOT EXISTS gg_requirements (
    run_id TEXT NOT NULL, requirement_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
    article TEXT NOT NULL DEFAULT '', norm_type TEXT NOT NULL DEFAULT 'other',
    disposition TEXT NOT NULL DEFAULT 'uncertain', adjudication_status TEXT NOT NULL DEFAULT 'baseline',
    discovery_pass TEXT NOT NULL DEFAULT 'A', source_block_ids_json MEDIUMTEXT NOT NULL DEFAULT '[]',
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, requirement_id)
);
CREATE TABLE IF NOT EXISTS gg_contracts (
    contract_id TEXT PRIMARY KEY, fund_identity TEXT NOT NULL, display_name TEXT NOT NULL DEFAULT '',
    latest_version_id TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL, updated_at REAL NOT NULL,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS gg_contract_versions (
    contract_version_id TEXT PRIMARY KEY, contract_id TEXT NOT NULL, fund_identity TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '', version_date TEXT NOT NULL DEFAULT '',
    previous_version_id TEXT NOT NULL DEFAULT '', latest_known_version INTEGER NOT NULL DEFAULT 0,
    version_relation TEXT NOT NULL DEFAULT 'resolved', source_sha256 TEXT NOT NULL DEFAULT '',
    source_path TEXT NOT NULL DEFAULT '', source_size INTEGER NOT NULL DEFAULT 0,
    parser_version TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'pending',
    created_at REAL NOT NULL, updated_at REAL NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS gg_contract_versions_contract ON gg_contract_versions(contract_id);
CREATE TABLE IF NOT EXISTS gg_clauses (
    clause_id TEXT PRIMARY KEY, contract_version_id TEXT NOT NULL,
    section_path_json MEDIUMTEXT NOT NULL DEFAULT '[]', paragraph_start INTEGER NOT NULL DEFAULT 0,
    paragraph_end INTEGER NOT NULL DEFAULT 0, text MEDIUMTEXT NOT NULL,
    before_context MEDIUMTEXT NOT NULL DEFAULT '', after_context MEDIUMTEXT NOT NULL DEFAULT '',
    ordinal INTEGER NOT NULL DEFAULT 0, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS gg_clauses_version ON gg_clauses(contract_version_id, ordinal);
CREATE TABLE IF NOT EXISTS gg_snapshots (
    snapshot_id TEXT PRIMARY KEY, created_at REAL NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS gg_snapshot_members (
    snapshot_id TEXT NOT NULL, contract_version_id TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, contract_version_id)
);
CREATE TABLE IF NOT EXISTS gg_steps (
    run_id TEXT NOT NULL, stage TEXT NOT NULL, attempt INTEGER NOT NULL,
    status TEXT NOT NULL, input_hash TEXT NOT NULL DEFAULT '', output_hash TEXT NOT NULL DEFAULT '',
    error_code TEXT NOT NULL DEFAULT '', model_identity_json MEDIUMTEXT NOT NULL DEFAULT '{}',
    prompt_hash TEXT NOT NULL DEFAULT '', started_at REAL NOT NULL, finished_at REAL,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, stage, attempt)
);
CREATE TABLE IF NOT EXISTS gg_jobs (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0, lease_until REAL, fencing_token INTEGER NOT NULL DEFAULT 0,
    stage TEXT NOT NULL DEFAULT '', error_code TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL, updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS gg_jobs_work ON gg_jobs(status, lease_until);
CREATE TABLE IF NOT EXISTS gg_impacts (
    run_id TEXT NOT NULL, impact_id TEXT NOT NULL, requirement_id TEXT NOT NULL,
    contract_version_id TEXT NOT NULL, impact_status TEXT NOT NULL,
    disposition TEXT NOT NULL DEFAULT '', discovery_sources_json MEDIUMTEXT NOT NULL DEFAULT '[]',
    ordinal INTEGER NOT NULL DEFAULT 0, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, impact_id)
);
CREATE INDEX IF NOT EXISTS gg_impacts_req ON gg_impacts(run_id, requirement_id);
CREATE INDEX IF NOT EXISTS gg_impacts_contract ON gg_impacts(run_id, contract_version_id);
CREATE TABLE IF NOT EXISTS gg_local (
    run_id TEXT NOT NULL, local_id TEXT NOT NULL, requirement_ids_json MEDIUMTEXT NOT NULL DEFAULT '[]',
    impact_ids_json MEDIUMTEXT NOT NULL DEFAULT '[]', ordinal INTEGER NOT NULL DEFAULT 0,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, local_id)
);
CREATE TABLE IF NOT EXISTS gg_families (
    run_id TEXT NOT NULL, family_id TEXT NOT NULL, ordinal INTEGER NOT NULL DEFAULT 0,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, family_id)
);
CREATE TABLE IF NOT EXISTS gg_guide_items (
    run_id TEXT NOT NULL, guide_item_id TEXT NOT NULL, ordinal INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate', quality_status TEXT NOT NULL DEFAULT 'not_run',
    coverage_status TEXT NOT NULL DEFAULT 'not_run', version INTEGER NOT NULL DEFAULT 1,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, guide_item_id)
);
CREATE TABLE IF NOT EXISTS gg_findings (
    run_id TEXT NOT NULL, finding_id TEXT NOT NULL, guide_item_id TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL, severity TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'open',
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, finding_id)
);
CREATE TABLE IF NOT EXISTS gg_coverage (
    run_id TEXT NOT NULL, coverage_id TEXT NOT NULL, level TEXT NOT NULL, ref_id TEXT NOT NULL,
    status TEXT NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, coverage_id)
);
CREATE INDEX IF NOT EXISTS gg_coverage_level ON gg_coverage(run_id, level, status);
CREATE TABLE IF NOT EXISTS gg_applicability (
    run_id TEXT NOT NULL, result_id TEXT NOT NULL, guide_item_id TEXT NOT NULL,
    clause_id TEXT NOT NULL, verdict TEXT NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY(run_id, result_id)
);
CREATE TABLE IF NOT EXISTS gg_residual (
    run_id TEXT NOT NULL, round_no INTEGER NOT NULL, status TEXT NOT NULL,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL,
    PRIMARY KEY(run_id, round_no)
);
CREATE TABLE IF NOT EXISTS gg_evidence (
    run_id TEXT NOT NULL, evidence_id TEXT NOT NULL, kind TEXT NOT NULL, ref_id TEXT NOT NULL,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL,
    PRIMARY KEY(run_id, evidence_id)
);
CREATE TABLE IF NOT EXISTS gg_human_versions (
    run_id TEXT NOT NULL, version_no INTEGER NOT NULL, author TEXT NOT NULL DEFAULT '',
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL,
    PRIMARY KEY(run_id, version_no)
);
CREATE TABLE IF NOT EXISTS gg_human_changes (
    run_id TEXT NOT NULL, change_id TEXT NOT NULL, guide_item_id TEXT NOT NULL,
    change_type TEXT NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL,
    PRIMARY KEY(run_id, change_id)
);
CREATE TABLE IF NOT EXISTS gg_engine_runs (
    run_id TEXT NOT NULL, attempt INTEGER NOT NULL, status TEXT NOT NULL,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL,
    PRIMARY KEY(run_id, attempt)
);
CREATE TABLE IF NOT EXISTS gg_engine_results (
    run_id TEXT NOT NULL, guide_item_id TEXT NOT NULL, classification TEXT NOT NULL,
    payload_json MEDIUMTEXT NOT NULL DEFAULT '{}', PRIMARY KEY(run_id, guide_item_id)
);
CREATE TABLE IF NOT EXISTS gg_model_calls (
    call_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, role TEXT NOT NULL, task_type TEXT NOT NULL,
    status TEXT NOT NULL, created_at REAL NOT NULL, payload_json MEDIUMTEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS gg_model_calls_run ON gg_model_calls(run_id, created_at);
CREATE TABLE IF NOT EXISTS gg_artifacts (
    run_id TEXT NOT NULL, kind TEXT NOT NULL, object_key TEXT NOT NULL, sha256 TEXT NOT NULL,
    size INTEGER NOT NULL, created_at REAL NOT NULL, PRIMARY KEY(run_id, kind)
);
CREATE TABLE IF NOT EXISTS gg_corpus_state (
    key TEXT PRIMARY KEY, value MEDIUMTEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL
);
"""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _loads(raw: Any, default: Any = None) -> Any:
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


class GuideGenerationStore:
    def __init__(self, store: RunStore, *, read_only: bool = False):
        self.store = store
        self.database = store.database
        self.read_only = read_only or bool(getattr(store, "read_only", False))
        self._schema_ready = False
        self._transaction_db = ContextVar(f"gg_transaction_{id(self)}", default=None)

    @contextmanager
    def _connect(self):
        active = self._transaction_db.get()
        if active is not None:
            yield active
            return
        with self.database.connect() as db:
            yield db

    @contextmanager
    def candidate_transaction(self, run_id: str):
        """Serialize candidate edits and transitions, with one rollback boundary."""
        self.ensure_schema()
        if self._transaction_db.get() is not None:
            yield
            return
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            sql = "SELECT candidate_guide_id FROM gg_candidate_guides WHERE run_id=?"
            if self.database.dialect == "mysql":
                sql += " FOR UPDATE"
            if db.execute(sql, (run_id,)).fetchone() is None:
                raise NotFound("candidate guide not found")
            token = self._transaction_db.set(db)
            try:
                yield
            finally:
                self._transaction_db.reset(token)

    def ensure_schema(self) -> None:
        if self._schema_ready:
            return
        if self.read_only:
            self._schema_ready = True
            return
        with self._connect() as db:
            db.executescript(_SCHEMA)
        self._schema_ready = True

    # -- runs -----------------------------------------------------------------
    def create_run(self, *, owner: str, filename: str, source_type: str, source_sha256: str,
                   title: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_schema()
        run_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as db:
            db.execute("""INSERT INTO gg_runs
                (id,owner,filename,source_type,source_sha256,title,status,stage,created_at,updated_at,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, owner, filename, source_type, source_sha256, title, "queued", "QUEUED",
                 now, now, _dumps(payload or {})))
            candidate_id = uuid.uuid4().hex
            version_id = uuid.uuid4().hex
            db.execute("""INSERT INTO gg_candidate_guides
                (candidate_guide_id,owner,run_id,current_version_id,status,created_at,updated_at,payload_json)
                VALUES (?,?,?,?,?,?,?,?)""",
                       (candidate_id, owner, run_id, version_id, "draft", now, now, "{}"))
            db.execute("""INSERT INTO gg_candidate_versions
                (candidate_version_id,candidate_guide_id,run_id,version_no,status,created_at,payload_json)
                VALUES (?,?,?,?,?,?,?)""",
                       (version_id, candidate_id, run_id, 1, "draft", now, "{}"))
            merged = dict(payload or {})
            merged.update({"candidate_guide_id": candidate_id, "candidate_version_id": version_id,
                           "candidate_version_no": 1})
            db.execute("UPDATE gg_runs SET payload_json=?,updated_at=? WHERE id=?",
                       (_dumps(merged), now, run_id))
        return self.get_run(run_id)

    def _run_dict(self, row) -> dict[str, Any]:
        payload = _loads(row["payload_json"], {})
        result = {key: row[key] for key in (
            "id", "owner", "filename", "source_type", "source_sha256", "title", "status", "stage",
            "error_code", "created_at", "updated_at", "corpus_snapshot_id", "regulation_document_id",
            "regulation_document_sha256", "guide_sha256", "evidence_sha256", "report_sha256",
            "engine_status", "qualification_status", "commit_sha", "code_build",
            "runtime_config_sha256", "lockfile_sha256")}
        result["payload"] = payload or {}
        result.update(payload or {})
        return result

    def get_run(self, run_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with self._connect() as db:
            row = db.execute("SELECT * FROM gg_runs WHERE id=?", (run_id,)).fetchone()
            if row is None:
                raise NotFound("guide generation run not found")
            return self._run_dict(row)

    def get_run_for_owner(self, owner: str, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run.get("owner") != owner:
            raise NotFound("guide generation run not found")
        return run

    def update_run(self, run_id: str, **fields: Any) -> dict[str, Any]:
        self.ensure_schema()
        allowed = {"filename", "source_type", "source_sha256", "title", "status", "stage",
                   "error_code", "corpus_snapshot_id", "regulation_document_id",
                   "regulation_document_sha256", "guide_sha256", "evidence_sha256",
                   "report_sha256", "engine_status", "qualification_status", "commit_sha",
                   "code_build", "runtime_config_sha256", "lockfile_sha256"}
        payload = fields.pop("payload", None)
        with self._connect() as db:
            if payload is not None:
                current = db.execute("SELECT payload_json FROM gg_runs WHERE id=?", (run_id,)).fetchone()
                if current is None:
                    raise NotFound("guide generation run not found")
                merged = _loads(current["payload_json"], {})
                merged.update(payload)
                db.execute("UPDATE gg_runs SET payload_json=?, updated_at=? WHERE id=?",
                           (_dumps(merged), time.time(), run_id))
            assignments = [(key, value) for key, value in fields.items() if key in allowed]
            if assignments:
                db.execute("UPDATE gg_runs SET " + ",".join(f"{key}=?" for key, _ in assignments)
                           + ",updated_at=? WHERE id=?",
                           tuple(value for _, value in assignments) + (time.time(), run_id))
        return self.get_run(run_id)

    def list_runs(self, owner: str, limit: int = 100) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_runs WHERE owner=? ORDER BY created_at DESC LIMIT ?",
                              (owner, max(1, min(500, limit)))).fetchall()
            return [self._run_dict(row) for row in rows]

    # -- immutable candidate guide versions ----------------------------------
    def get_candidate(self, run_id: str, *, owner: str | None = None) -> dict[str, Any]:
        self.ensure_schema()
        with self._connect() as db:
            sql = "SELECT * FROM gg_candidate_guides WHERE run_id=?"
            params: list[Any] = [run_id]
            if owner is not None:
                sql += " AND owner=?"
                params.append(owner)
            row = db.execute(sql, params).fetchone()
            if row is None:
                raise NotFound("candidate guide not found")
            result = dict(row)
            result["payload"] = _loads(result.pop("payload_json"), {})
            versions = db.execute("SELECT * FROM gg_candidate_versions WHERE candidate_guide_id=? ORDER BY version_no",
                                  (row["candidate_guide_id"],)).fetchall()
            result["versions"] = []
            for version in versions:
                item = dict(version)
                item["payload"] = _loads(item.pop("payload_json"), {})
                result["versions"].append(item)
            return result

    def get_candidate_version(self, run_id: str, version_id: str = "", *, owner: str | None = None) -> dict[str, Any]:
        candidate = self.get_candidate(run_id, owner=owner)
        if not version_id:
            version_id = candidate["current_version_id"]
        for version in candidate["versions"]:
            if version["candidate_version_id"] == version_id:
                return {**version, "candidate_guide_id": candidate["candidate_guide_id"], "owner": candidate["owner"]}
        raise NotFound("candidate guide version not found")

    def update_candidate(self, run_id: str, *, status: str | None = None,
                         current_version_id: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        self.ensure_schema()
        with self._connect() as db:
            row = db.execute("SELECT payload_json,status,current_version_id FROM gg_candidate_guides WHERE run_id=?",
                             (run_id,)).fetchone()
            if row is None:
                raise NotFound("candidate guide not found")
            merged = _loads(row["payload_json"], {})
            if payload:
                merged.update(payload)
            db.execute("UPDATE gg_candidate_guides SET status=COALESCE(?,status),current_version_id=COALESCE(?,current_version_id),payload_json=?,updated_at=? WHERE run_id=?",
                       (status, current_version_id, _dumps(merged), time.time(), run_id))
        return self.get_candidate(run_id)

    def create_candidate_version(self, run_id: str, *, status: str, payload: dict[str, Any],
                                 content_sha256: str = "", human_version_no: int = 0,
                                 expected_current_version_id: str | None = None) -> dict[str, Any]:
        self.ensure_schema()
        if status not in CANDIDATE_VERSION_STATUSES:
            raise ValueError("invalid candidate version status")
        now = time.time()
        with self.candidate_transaction(run_id), self._connect() as db:
            guide = db.execute("SELECT * FROM gg_candidate_guides WHERE run_id=?", (run_id,)).fetchone()
            if guide is None:
                raise NotFound("candidate guide not found")
            if expected_current_version_id is not None and guide["current_version_id"] != expected_current_version_id:
                raise Conflict("candidate version changed")
            latest = db.execute("SELECT * FROM gg_candidate_versions WHERE candidate_guide_id=? ORDER BY version_no DESC LIMIT 1",
                                (guide["candidate_guide_id"],)).fetchone()
            number = int(latest["version_no"]) + 1 if latest else 1
            parent = latest["candidate_version_id"] if latest else ""
            version_id = uuid.uuid4().hex
            db.execute("""INSERT INTO gg_candidate_versions
                (candidate_version_id,candidate_guide_id,run_id,version_no,parent_version_id,status,content_sha256,human_version_no,created_at,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                       (version_id, guide["candidate_guide_id"], run_id, number, parent, status,
                        content_sha256, human_version_no, now, _dumps(payload)))
            db.execute("UPDATE gg_candidate_guides SET current_version_id=?,status=?,updated_at=? WHERE run_id=?",
                       (version_id, status, now, run_id))
        return self.get_candidate_version(run_id, version_id)

    def approve_candidate(self, run_id: str, *, actor: str, version_id: str,
                          owner: str | None = None) -> dict[str, Any]:
        self.ensure_schema()
        with self.candidate_transaction(run_id), self._connect() as db:
            sql = "SELECT current_version_id FROM gg_candidate_guides WHERE run_id=?"
            params: list[Any] = [run_id]
            if owner is not None:
                sql += " AND owner=?"
                params.append(owner)
            row = db.execute(sql, params).fetchone()
            if row is None or row["current_version_id"] != version_id:
                raise Conflict("candidate approval requires the current version")
            cursor = db.execute("UPDATE gg_candidate_versions SET status='approved',approved_by=?,approved_at=? WHERE candidate_version_id=? AND status IN ('candidate_ready','human_draft')",
                                (actor, time.time(), version_id))
            if cursor.rowcount != 1:
                raise Conflict("candidate version is not approvable")
            db.execute("UPDATE gg_candidate_guides SET status='approved',updated_at=? WHERE run_id=?", (time.time(), run_id))
        return self.get_candidate_version(run_id, version_id)

    def publish_candidate(self, run_id: str, *, actor: str, version_id: str,
                          owner: str | None = None) -> dict[str, Any]:
        self.ensure_schema()
        with self.candidate_transaction(run_id), self._connect() as db:
            sql = "SELECT current_version_id FROM gg_candidate_guides WHERE run_id=?"
            params: list[Any] = [run_id]
            if owner is not None:
                sql += " AND owner=?"
                params.append(owner)
            row = db.execute(sql, params).fetchone()
            if row is None or row["current_version_id"] != version_id:
                raise Conflict("candidate publication requires the current version")
            cursor = db.execute("UPDATE gg_candidate_versions SET status='published',published_by=?,published_at=? WHERE candidate_version_id=? AND status='approved'",
                                (actor, time.time(), version_id))
            if cursor.rowcount != 1:
                raise Conflict("candidate version must be approved before publication")
            db.execute("UPDATE gg_candidate_guides SET status='published',updated_at=? WHERE run_id=?", (time.time(), run_id))
        return self.get_candidate_version(run_id, version_id)

    # -- blocks and requirements ---------------------------------------------
    def replace_blocks(self, run_id: str, blocks: Iterable[RegulationBlock]) -> None:
        self.ensure_schema()
        rows = [(run_id, block.block_id, block.ordinal, block.type, block.text, block.article_no,
                 block.heading_level, block.page, _dumps(block.source_anchor)) for block in blocks]
        with self._connect() as db:
            db.execute("DELETE FROM gg_blocks WHERE run_id=?", (run_id,))
            db.executemany("""INSERT INTO gg_blocks
                (run_id,block_id,ordinal,type,text,article_no,heading_level,page,source_anchor_json)
                VALUES (?,?,?,?,?,?,?,?,?)""", rows)

    def get_blocks(self, run_id: str) -> list[RegulationBlock]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_blocks WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
            return [RegulationBlock(
                block_id=row["block_id"], ordinal=row["ordinal"], type=row["type"], text=row["text"],
                article_no=row["article_no"], heading_level=row["heading_level"], page=row["page"],
                source_anchor=_loads(row["source_anchor_json"], {}),
            ) for row in rows]

    def replace_requirements(self, run_id: str, requirements: Iterable[PolicyRequirement]) -> None:
        self.ensure_schema()
        rows = []
        for index, requirement in enumerate(requirements):
            rows.append((run_id, requirement.requirement_id, index, requirement.article,
                         requirement.norm_type, requirement.disposition, requirement.adjudication_status,
                         requirement.discovery_pass, _dumps(requirement.source_block_ids),
                         _dumps(requirement.to_dict())))
        with self._connect() as db:
            db.execute("DELETE FROM gg_requirements WHERE run_id=?", (run_id,))
            db.executemany("""INSERT INTO gg_requirements
                (run_id,requirement_id,ordinal,article,norm_type,disposition,adjudication_status,
                 discovery_pass,source_block_ids_json,payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)""", rows)

    def get_requirements(self, run_id: str) -> list[PolicyRequirement]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_requirements WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
            return [PolicyRequirement.from_dict(_loads(row["payload_json"], {})) for row in rows]

    def update_requirement(self, run_id: str, requirement: PolicyRequirement) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""UPDATE gg_requirements SET article=?,norm_type=?,disposition=?,adjudication_status=?,
                discovery_pass=?,source_block_ids_json=?,payload_json=? WHERE run_id=? AND requirement_id=?""",
                (requirement.article, requirement.norm_type, requirement.disposition,
                 requirement.adjudication_status, requirement.discovery_pass,
                 _dumps(requirement.source_block_ids), _dumps(requirement.to_dict()),
                 run_id, requirement.requirement_id))

    # -- corpus ---------------------------------------------------------------
    def upsert_contract_version(self, version: ContractVersion) -> None:
        self.ensure_schema()
        now = time.time()
        with self._connect() as db:
            db.execute("""INSERT OR REPLACE INTO gg_contract_versions
                (contract_version_id,contract_id,fund_identity,display_name,version_date,
                 previous_version_id,latest_known_version,version_relation,source_sha256,source_path,
                 source_size,parser_version,status,created_at,updated_at,payload_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,COALESCE((SELECT created_at FROM gg_contract_versions
                 WHERE contract_version_id=?),?),?,?)""",
                (version.contract_version_id, version.contract_id, version.fund_identity,
                 version.display_name, version.version_date, version.previous_version_id,
                 int(version.latest_known_version), version.version_relation, version.source_sha256,
                 version.source_path, version.source_size, version.parser_version, version.status,
                 version.contract_version_id, now, now, _dumps(version.to_dict())))
            db.execute("""INSERT OR REPLACE INTO gg_contracts
                (contract_id,fund_identity,display_name,latest_version_id,created_at,updated_at,payload_json)
                VALUES (?,?,?,?,COALESCE((SELECT created_at FROM gg_contracts WHERE contract_id=?),?),?,?)""",
                (version.contract_id, version.fund_identity, version.display_name,
                 version.contract_version_id if version.latest_known_version else "",
                 version.contract_id, now, now, _dumps(version.to_dict())))

    def get_contract_version(self, contract_version_id: str) -> ContractVersion | None:
        self.ensure_schema()
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM gg_contract_versions WHERE contract_version_id=?",
                             (contract_version_id,)).fetchone()
            return ContractVersion.from_dict(_loads(row["payload_json"], {})) if row else None

    def get_contract_versions(self, version_ids: Iterable[str]) -> list[ContractVersion]:
        self.ensure_schema()
        ids = [str(value) for value in version_ids if value]
        if not ids:
            return []
        result: list[ContractVersion] = []
        with self._connect() as db:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                rows = db.execute(
                    "SELECT payload_json FROM gg_contract_versions WHERE contract_version_id IN ("
                    + ",".join("?" for _ in chunk) + ")", chunk).fetchall()
                result.extend(ContractVersion.from_dict(_loads(row["payload_json"], {})) for row in rows)
        by_id = {item.contract_version_id: item for item in result}
        return [by_id[value] for value in ids if value in by_id]

    def list_contract_versions(self, *, latest_only: bool = False) -> list[ContractVersion]:
        self.ensure_schema()
        with self._connect() as db:
            sql = "SELECT payload_json FROM gg_contract_versions"
            if latest_only:
                sql += " WHERE latest_known_version=1"
            sql += " ORDER BY fund_identity, version_date"
            rows = db.execute(sql).fetchall()
            return [ContractVersion.from_dict(_loads(row["payload_json"], {})) for row in rows]

    def replace_clauses(self, contract_version_id: str, clauses: Iterable[ClauseUnit]) -> None:
        self.ensure_schema()
        rows = [(clause.clause_id, clause.contract_version_id, _dumps(clause.section_path),
                 clause.paragraph_start, clause.paragraph_end, clause.text, clause.before_context,
                 clause.after_context, index, _dumps({
                     **clause.metadata, "source_anchor": clause.source_anchor}))
                for index, clause in enumerate(clauses)]
        with self._connect() as db:
            db.execute("DELETE FROM gg_clauses WHERE contract_version_id=?", (contract_version_id,))
            db.executemany("""INSERT INTO gg_clauses
                (clause_id,contract_version_id,section_path_json,paragraph_start,paragraph_end,text,
                 before_context,after_context,ordinal,payload_json) VALUES (?,?,?,?,?,?,?,?,?,?)""", rows)

    def get_clauses_by_ids(self, clause_ids: Iterable[str]) -> list[ClauseUnit]:
        self.ensure_schema()
        ids = [str(value) for value in clause_ids if value]
        if not ids:
            return []
        result: list[ClauseUnit] = []
        with self._connect() as db:
            for start in range(0, len(ids), 500):
                chunk = ids[start:start + 500]
                rows = db.execute(
                    "SELECT * FROM gg_clauses WHERE clause_id IN (" + ",".join("?" for _ in chunk) + ")",
                    chunk).fetchall()
                for row in rows:
                    payload = _loads(row["payload_json"], {})
                    result.append(ClauseUnit(
                        clause_id=row["clause_id"], contract_version_id=row["contract_version_id"],
                        section_path=_loads(row["section_path_json"], []),
                        paragraph_start=row["paragraph_start"], paragraph_end=row["paragraph_end"],
                        text=row["text"], before_context=row["before_context"],
                        after_context=row["after_context"],
                        metadata={key: value for key, value in payload.items() if key != "source_anchor"},
                        source_anchor=payload.get("source_anchor") or {},
                    ))
        by_id = {clause.clause_id: clause for clause in result}
        return [by_id[value] for value in ids if value in by_id]

    def get_clauses(self, contract_version_id: str) -> list[ClauseUnit]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_clauses WHERE contract_version_id=? ORDER BY ordinal",
                              (contract_version_id,)).fetchall()
            result: list[ClauseUnit] = []
            for row in rows:
                payload = _loads(row["payload_json"], {})
                result.append(ClauseUnit(
                    clause_id=row["clause_id"], contract_version_id=row["contract_version_id"],
                    section_path=_loads(row["section_path_json"], []),
                    paragraph_start=row["paragraph_start"], paragraph_end=row["paragraph_end"],
                    text=row["text"], before_context=row["before_context"],
                    after_context=row["after_context"],
                    metadata={key: value for key, value in payload.items() if key != "source_anchor"},
                    source_anchor=payload.get("source_anchor") or {},
                ))
            return result

    def create_snapshot(self, snapshot: CorpusSnapshot) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("INSERT OR REPLACE INTO gg_snapshots (snapshot_id,created_at,payload_json) VALUES (?,?,?)",
                       (snapshot.snapshot_id, time.time(), _dumps(snapshot.to_dict())))
            db.execute("DELETE FROM gg_snapshot_members WHERE snapshot_id=?", (snapshot.snapshot_id,))
            db.executemany("INSERT INTO gg_snapshot_members (snapshot_id,contract_version_id) VALUES (?,?)",
                           [(snapshot.snapshot_id, item) for item in snapshot.contract_version_ids])

    def list_snapshots(self, limit: int = 10) -> list[CorpusSnapshot]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_snapshots ORDER BY created_at DESC LIMIT ?",
                              (max(1, min(100, limit)),)).fetchall()
            return [CorpusSnapshot(**_loads(row["payload_json"], {})) for row in rows]

    def get_snapshot(self, snapshot_id: str) -> CorpusSnapshot | None:
        self.ensure_schema()
        with self._connect() as db:
            row = db.execute("SELECT payload_json FROM gg_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
            return CorpusSnapshot(**_loads(row["payload_json"], {})) if row else None

    # -- stage state ----------------------------------------------------------
    def start_step(self, run_id: str, stage: str, input_hash: str, *,
                   attempt: int | None = None, model_identity: dict | None = None,
                   prompt_hash: str = "") -> int:
        self.ensure_schema()
        with self._connect() as db:
            if attempt is None:
                row = db.execute("SELECT COALESCE(MAX(attempt),0)+1 n FROM gg_steps WHERE run_id=? AND stage=?",
                                 (run_id, stage)).fetchone()
                attempt = int(row["n"])
            db.execute("""INSERT OR REPLACE INTO gg_steps
                (run_id,stage,attempt,status,input_hash,output_hash,error_code,model_identity_json,
                 prompt_hash,started_at,finished_at,payload_json) VALUES (?,?,?,?,?,'','',?,?,?,NULL,'{}')""",
                (run_id, stage, attempt, "running", input_hash, _dumps(model_identity or {}),
                 prompt_hash, time.time()))
            return attempt

    def finish_step(self, run_id: str, stage: str, attempt: int, *, status: str,
                    output_hash: str = "", error_code: str = "", payload: dict | None = None) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""UPDATE gg_steps SET status=?,output_hash=?,error_code=?,finished_at=?,payload_json=?
                WHERE run_id=? AND stage=? AND attempt=?""",
                (status, output_hash, error_code, time.time(), _dumps(payload or {}),
                 run_id, stage, attempt))

    def get_completed_step(self, run_id: str, stage: str, input_hash: str) -> dict | None:
        self.ensure_schema()
        with self._connect() as db:
            row = db.execute("""SELECT * FROM gg_steps WHERE run_id=? AND stage=? AND status='completed'
                ORDER BY attempt DESC LIMIT 1""", (run_id, stage)).fetchone()
            if row is None or row["input_hash"] != input_hash:
                return None
            return {"stage": row["stage"], "attempt": row["attempt"],
                    "output_hash": row["output_hash"], "payload": _loads(row["payload_json"], {})}

    def list_steps(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_steps WHERE run_id=? ORDER BY started_at", (run_id,)).fetchall()
            return [{"stage": row["stage"], "attempt": row["attempt"], "status": row["status"],
                     "input_hash": row["input_hash"], "output_hash": row["output_hash"],
                     "error_code": row["error_code"], "started_at": row["started_at"],
                     "finished_at": row["finished_at"]} for row in rows]

    # -- jobs -----------------------------------------------------------------
    def enqueue(self, run_id: str) -> str:
        self.ensure_schema()
        with self._connect() as db:
            existing = db.execute("SELECT id FROM gg_jobs WHERE run_id=? AND status IN ('queued','leased')",
                                  (run_id,)).fetchone()
            if existing:
                return existing["id"]
            job_id = uuid.uuid4().hex
            now = time.time()
            db.execute("""INSERT INTO gg_jobs (id,run_id,status,attempts,created_at,updated_at)
                VALUES (?,?,'queued',0,?,?)""", (job_id, run_id, now, now))
            db.execute("UPDATE gg_runs SET status='queued',stage='QUEUED',updated_at=? WHERE id=?", (now, run_id))
            return job_id

    def claim(self, *, lease_seconds: int = 3600) -> dict | None:
        self.ensure_schema()
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT * FROM gg_jobs WHERE status='queued'
                OR (status='leased' AND lease_until<?) ORDER BY created_at LIMIT 1""", (now,)).fetchone()
            if row is None:
                return None
            token = int(row["fencing_token"]) + 1
            db.execute("""UPDATE gg_jobs SET status='leased',attempts=attempts+1,fencing_token=?,
                lease_until=?,updated_at=? WHERE id=?""", (token, now + lease_seconds, now, row["id"]))
            return {"id": row["id"], "run_id": row["run_id"], "fencing_token": token,
                    "attempts": row["attempts"] + 1}

    def heartbeat(self, job_id: str, token: int, *, lease_seconds: int = 3600) -> None:
        with self._connect() as db:
            cursor = db.execute("""UPDATE gg_jobs SET lease_until=?,updated_at=? WHERE id=?
                AND fencing_token=? AND status='leased'""",
                (time.time() + lease_seconds, time.time(), job_id, token))
            if cursor.rowcount != 1:
                raise Conflict("stale guide generation worker lease")

    def finish_job(self, job_id: str, token: int, *, status: str, error_code: str = "") -> None:
        with self._connect() as db:
            cursor = db.execute("""UPDATE gg_jobs SET status=?,error_code=?,updated_at=?,lease_until=NULL
                WHERE id=? AND fencing_token=?""", (status, error_code, time.time(), job_id, token))
            if cursor.rowcount != 1:
                raise Conflict("stale guide generation worker lease")

    # -- impacts and candidates ----------------------------------------------
    def replace_impacts(self, run_id: str, impacts: Iterable[ImpactCandidate]) -> None:
        self.ensure_schema()
        rows = [(run_id, impact.impact_id, impact.requirement_id, impact.contract_version_id,
                 impact.impact_status, impact.disposition, _dumps(impact.discovery_sources), index,
                 _dumps(impact.to_dict())) for index, impact in enumerate(impacts)]
        with self._connect() as db:
            db.execute("DELETE FROM gg_impacts WHERE run_id=?", (run_id,))
            db.executemany("""INSERT INTO gg_impacts
                (run_id,impact_id,requirement_id,contract_version_id,impact_status,disposition,
                 discovery_sources_json,ordinal,payload_json) VALUES (?,?,?,?,?,?,?,?,?)""", rows)

    def add_impacts(self, run_id: str, impacts: Iterable[ImpactCandidate]) -> None:
        self.ensure_schema()
        rows = [(run_id, impact.impact_id, impact.requirement_id, impact.contract_version_id,
                 impact.impact_status, impact.disposition, _dumps(impact.discovery_sources), 0,
                 _dumps(impact.to_dict())) for impact in impacts]
        with self._connect() as db:
            db.executemany("""INSERT OR REPLACE INTO gg_impacts
                (run_id,impact_id,requirement_id,contract_version_id,impact_status,disposition,
                 discovery_sources_json,ordinal,payload_json) VALUES (?,?,?,?,?,?,?,?,?)""", rows)

    def get_impacts(self, run_id: str, *, requirement_id: str = "", impact_status: str = "") -> list[ImpactCandidate]:
        self.ensure_schema()
        sql = "SELECT payload_json FROM gg_impacts WHERE run_id=?"
        params: list[Any] = [run_id]
        if requirement_id:
            sql += " AND requirement_id=?"
            params.append(requirement_id)
        if impact_status:
            sql += " AND impact_status=?"
            params.append(impact_status)
        sql += " ORDER BY ordinal, impact_id"
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
            return [ImpactCandidate(**_loads(row["payload_json"], {})) for row in rows]

    def update_impact(self, run_id: str, impact: ImpactCandidate) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""UPDATE gg_impacts SET impact_status=?,disposition=?,discovery_sources_json=?,
                payload_json=? WHERE run_id=? AND impact_id=?""",
                (impact.impact_status, impact.disposition, _dumps(impact.discovery_sources),
                 _dumps(impact.to_dict()), run_id, impact.impact_id))

    def replace_local(self, run_id: str, candidates: Iterable[LocalGuideCandidate]) -> None:
        self.ensure_schema()
        rows = [(run_id, item.local_id, _dumps(item.requirement_ids), _dumps(item.impact_ids), index,
                 _dumps(item.to_dict())) for index, item in enumerate(candidates)]
        with self._connect() as db:
            db.execute("DELETE FROM gg_local WHERE run_id=?", (run_id,))
            db.executemany("""INSERT INTO gg_local
                (run_id,local_id,requirement_ids_json,impact_ids_json,ordinal,payload_json)
                VALUES (?,?,?,?,?,?)""", rows)

    def get_local(self, run_id: str) -> list[LocalGuideCandidate]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_local WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
            return [LocalGuideCandidate(**_loads(row["payload_json"], {})) for row in rows]

    def replace_families(self, run_id: str, families: Iterable[dict[str, Any]]) -> None:
        self.ensure_schema()
        rows = [(run_id, family["family_id"], index, _dumps(family)) for index, family in enumerate(families)]
        with self._connect() as db:
            db.execute("DELETE FROM gg_families WHERE run_id=?", (run_id,))
            db.executemany("INSERT INTO gg_families (run_id,family_id,ordinal,payload_json) VALUES (?,?,?,?)", rows)

    def get_families(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_families WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
            return [_loads(row["payload_json"], {}) for row in rows]

    def replace_guide_items(self, run_id: str, items: Iterable[GuideItem]) -> None:
        self.ensure_schema()
        rows = [(run_id, item.guide_item_id, index, item.status, item.quality_status,
                 item.coverage_status, item.version, _dumps(item.to_dict()))
                for index, item in enumerate(items)]
        with self._connect() as db:
            db.execute("DELETE FROM gg_guide_items WHERE run_id=?", (run_id,))
            db.executemany("""INSERT INTO gg_guide_items
                (run_id,guide_item_id,ordinal,status,quality_status,coverage_status,version,payload_json)
                VALUES (?,?,?,?,?,?,?,?)""", rows)

    def get_guide_items(self, run_id: str) -> list[GuideItem]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_guide_items WHERE run_id=? ORDER BY ordinal", (run_id,)).fetchall()
            return [GuideItem(**_loads(row["payload_json"], {})) for row in rows]

    def update_guide_item(self, run_id: str, item: GuideItem) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""UPDATE gg_guide_items SET status=?,quality_status=?,coverage_status=?,version=?,
                payload_json=? WHERE run_id=? AND guide_item_id=?""",
                (item.status, item.quality_status, item.coverage_status, item.version,
                 _dumps(item.to_dict()), run_id, item.guide_item_id))

    # -- findings / coverage / applicability ---------------------------------
    def replace_findings(self, run_id: str, findings: Iterable[dict[str, Any]]) -> None:
        self.ensure_schema()
        unique_findings = {item["finding_id"]: item for item in findings}
        rows = [(run_id, item["finding_id"], item.get("guide_item_id", ""), item["category"],
                 item["severity"], item.get("status", "open"), _dumps(item))
                for item in unique_findings.values()]
        with self._connect() as db:
            db.execute("DELETE FROM gg_findings WHERE run_id=?", (run_id,))
            db.executemany("""INSERT INTO gg_findings
                (run_id,finding_id,guide_item_id,category,severity,status,payload_json)
                VALUES (?,?,?,?,?,?,?)""", rows)

    def add_findings(self, run_id: str, findings: Iterable[dict[str, Any]]) -> None:
        self.ensure_schema()
        unique_findings = {item["finding_id"]: item for item in findings}
        rows = [(run_id, item["finding_id"], item.get("guide_item_id", ""), item["category"],
                 item["severity"], item.get("status", "open"), _dumps(item))
                for item in unique_findings.values()]
        with self._connect() as db:
            db.executemany("""INSERT OR REPLACE INTO gg_findings
                (run_id,finding_id,guide_item_id,category,severity,status,payload_json)
                VALUES (?,?,?,?,?,?,?)""", rows)

    def get_findings(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_findings WHERE run_id=? ORDER BY finding_id",
                              (run_id,)).fetchall()
            return [_loads(row["payload_json"], {}) for row in rows]

    def replace_coverage(self, run_id: str, results: Iterable[dict[str, Any]]) -> None:
        self.ensure_schema()
        rows = [(run_id, item["coverage_id"], item["level"], item["ref_id"], item["status"], _dumps(item))
                for item in results]
        with self._connect() as db:
            db.execute("DELETE FROM gg_coverage WHERE run_id=?", (run_id,))
            db.executemany("""INSERT INTO gg_coverage
                (run_id,coverage_id,level,ref_id,status,payload_json) VALUES (?,?,?,?,?,?)""", rows)

    def get_coverage(self, run_id: str, level: str = "") -> list[dict[str, Any]]:
        self.ensure_schema()
        sql = "SELECT payload_json FROM gg_coverage WHERE run_id=?"
        params: list[Any] = [run_id]
        if level:
            sql += " AND level=?"
            params.append(level)
        sql += " ORDER BY coverage_id"
        with self._connect() as db:
            rows = db.execute(sql, params).fetchall()
            return [_loads(row["payload_json"], {}) for row in rows]

    def add_applicability(self, run_id: str, results: Iterable[dict[str, Any]]) -> None:
        self.ensure_schema()
        rows = [(run_id, item["result_id"], item["guide_item_id"], item["clause_id"],
                 item["verdict"], _dumps(item)) for item in results]
        with self._connect() as db:
            db.executemany("""INSERT OR REPLACE INTO gg_applicability
                (run_id,result_id,guide_item_id,clause_id,verdict,payload_json)
                VALUES (?,?,?,?,?,?)""", rows)

    def get_applicability(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_applicability WHERE run_id=?", (run_id,)).fetchall()
            return [_loads(row["payload_json"], {}) for row in rows]

    def add_residual_round(self, run_id: str, round_no: int, status: str,
                           payload: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""INSERT OR REPLACE INTO gg_residual
                (run_id,round_no,status,payload_json,created_at) VALUES (?,?,?,?,?)""",
                (run_id, round_no, status, _dumps(payload), time.time()))

    def get_residual_rounds(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_residual WHERE run_id=? ORDER BY round_no", (run_id,)).fetchall()
            return [{"round_no": row["round_no"], "status": row["status"],
                     "created_at": row["created_at"], **_loads(row["payload_json"], {})} for row in rows]

    # -- evidence / human / engine ------------------------------------------
    def add_evidence(self, run_id: str, evidence_id: str, kind: str, ref_id: str,
                     payload: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""INSERT OR REPLACE INTO gg_evidence
                (run_id,evidence_id,kind,ref_id,payload_json,created_at) VALUES (?,?,?,?,?,?)""",
                (run_id, evidence_id, kind, ref_id, _dumps(payload), time.time()))

    def get_evidence_by_kind(self, run_id: str, kind: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_evidence WHERE run_id=? AND kind=? ORDER BY created_at, evidence_id",
                              (run_id, kind)).fetchall()
            return [{"evidence_id": row["evidence_id"], "kind": row["kind"], "ref_id": row["ref_id"],
                     "created_at": row["created_at"], **_loads(row["payload_json"], {})} for row in rows]

    def add_evidence_many(self, run_id: str, items: Iterable[tuple[str, str, str, dict[str, Any]]]) -> None:
        self.ensure_schema()
        now = time.time()
        rows = [(run_id, evidence_id, kind, ref_id, _dumps(payload), now)
                for evidence_id, kind, ref_id, payload in items]
        if not rows:
            return
        with self._connect() as db:
            db.executemany("""INSERT OR REPLACE INTO gg_evidence
                (run_id,evidence_id,kind,ref_id,payload_json,created_at) VALUES (?,?,?,?,?,?)""", rows)

    def get_evidence(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_evidence WHERE run_id=? ORDER BY created_at, evidence_id",
                              (run_id,)).fetchall()
            return [{"evidence_id": row["evidence_id"], "kind": row["kind"], "ref_id": row["ref_id"],
                     "created_at": row["created_at"], **_loads(row["payload_json"], {})} for row in rows]

    def save_human_version(self, run_id: str, version_no: int, author: str,
                           payload: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""INSERT INTO gg_human_versions
                (run_id,version_no,author,payload_json,created_at) VALUES (?,?,?,?,?)""",
                (run_id, version_no, author, _dumps(payload), time.time()))

    def list_human_versions(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_human_versions WHERE run_id=? ORDER BY version_no", (run_id,)).fetchall()
            return [{"version_no": row["version_no"], "author": row["author"],
                     "created_at": row["created_at"], **_loads(row["payload_json"], {})} for row in rows]

    def add_human_change(self, run_id: str, change: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""INSERT INTO gg_human_changes
                (run_id,change_id,guide_item_id,change_type,payload_json,created_at)
                VALUES (?,?,?,?,?,?)""",
                (run_id, change["change_id"], change["guide_item_id"], change["change_type"],
                 _dumps(change), time.time()))

    def list_human_changes(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_human_changes WHERE run_id=? ORDER BY created_at",
                              (run_id,)).fetchall()
            return [_loads(row["payload_json"], {}) for row in rows]

    def save_engine_run(self, run_id: str, attempt: int, status: str, payload: dict[str, Any]) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""INSERT OR REPLACE INTO gg_engine_runs
                (run_id,attempt,status,payload_json,created_at) VALUES (?,?,?,?,?)""",
                (run_id, attempt, status, _dumps(payload), time.time()))

    def replace_engine_results(self, run_id: str, results: Iterable[dict[str, Any]]) -> None:
        self.ensure_schema()
        rows = [(run_id, item["guide_item_id"], item["classification"], _dumps(item)) for item in results]
        with self._connect() as db:
            db.execute("DELETE FROM gg_engine_results WHERE run_id=?", (run_id,))
            db.executemany("""INSERT OR REPLACE INTO gg_engine_results
                (run_id,guide_item_id,classification,payload_json) VALUES (?,?,?,?)""", rows)

    def get_engine_results(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_engine_results WHERE run_id=?", (run_id,)).fetchall()
            return [_loads(row["payload_json"], {}) for row in rows]

    def get_engine_runs(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_engine_runs WHERE run_id=? ORDER BY attempt", (run_id,)).fetchall()
            return [{"attempt": row["attempt"], "status": row["status"], "created_at": row["created_at"],
                     **_loads(row["payload_json"], {})} for row in rows]

    # -- model calls and artifacts -------------------------------------------
    def record_model_call(self, run_id: str, record: Any) -> None:
        self.ensure_schema()
        payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
        call_id = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("""INSERT INTO gg_model_calls
                (call_id,run_id,role,task_type,status,created_at,payload_json) VALUES (?,?,?,?,?,?,?)""",
                (call_id, run_id, payload.get("role", ""), payload.get("task_type", ""),
                 "error" if payload.get("error_code") else "ok", time.time(), _dumps(payload)))
        return call_id

    def get_model_calls(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT payload_json FROM gg_model_calls WHERE run_id=? ORDER BY created_at",
                              (run_id,)).fetchall()
            return [_loads(row["payload_json"], {}) for row in rows]

    def put_artifact(self, run_id: str, kind: str, object_key: str, sha256: str, size: int) -> None:
        self.ensure_schema()
        with self._connect() as db:
            db.execute("""INSERT OR REPLACE INTO gg_artifacts
                (run_id,kind,object_key,sha256,size,created_at) VALUES (?,?,?,?,?,?)""",
                (run_id, kind, object_key, sha256, size, time.time()))

    def get_artifact(self, run_id: str, kind: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with self._connect() as db:
            row = db.execute("SELECT * FROM gg_artifacts WHERE run_id=? AND kind=?", (run_id, kind)).fetchone()
            return dict(row) if row else None

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        self.ensure_schema()
        with self._connect() as db:
            rows = db.execute("SELECT * FROM gg_artifacts WHERE run_id=? ORDER BY kind", (run_id,)).fetchall()
            return [dict(row) for row in rows]

    # -- summary --------------------------------------------------------------
    def stats(self, run_id: str) -> dict[str, Any]:
        self.ensure_schema()
        with self._connect() as db:
            def count(table: str, where: str = "", params: tuple = ()) -> int:
                sql = f"SELECT COUNT(*) n FROM {table}" + (f" WHERE {where}" if where else "")
                return int(db.execute(sql, params).fetchone()["n"])
            requirements = db.execute("""SELECT disposition,COUNT(*) n FROM gg_requirements
                WHERE run_id=? GROUP BY disposition""", (run_id,)).fetchall()
            impacts = db.execute("""SELECT impact_status,COUNT(*) n FROM gg_impacts
                WHERE run_id=? GROUP BY impact_status""", (run_id,)).fetchall()
            coverage = db.execute("""SELECT level,status,COUNT(*) n FROM gg_coverage
                WHERE run_id=? GROUP BY level,status""", (run_id,)).fetchall()
            return {
                "requirements": count("gg_requirements", "run_id=?", (run_id,)),
                "requirement_dispositions": {row["disposition"]: row["n"] for row in requirements},
                "impacts": count("gg_impacts", "run_id=?", (run_id,)),
                "impact_statuses": {row["impact_status"]: row["n"] for row in impacts},
                "local_candidates": count("gg_local", "run_id=?", (run_id,)),
                "families": count("gg_families", "run_id=?", (run_id,)),
                "guide_items": count("gg_guide_items", "run_id=?", (run_id,)),
                "findings": count("gg_findings", "run_id=?", (run_id,)),
                "coverage": count("gg_coverage", "run_id=?", (run_id,)),
                "coverage_by_level": {
                    f"{row['level']}:{row['status']}": row["n"] for row in coverage
                },
                "model_calls": count("gg_model_calls", "run_id=?", (run_id,)),
            }
