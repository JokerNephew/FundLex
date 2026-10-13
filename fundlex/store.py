"""SQLite task state and isolated local objects for the development profile.

The database contains metadata, never document bodies.  Each worker update is
guarded by a monotonically increasing fencing token.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "fundlex-result-v1"

def engine_build() -> str:
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


class StoreError(Exception):
    pass


class NotFound(StoreError):
    pass


class Conflict(StoreError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_delivery(report: dict[str, Any], artifacts: dict[str, Path]) -> None:
    if report.get("delivery_status") != "complete":
        return
    validation = report.get("output_validation")
    if not {"final", "redline"}.issubset(artifacts) or not isinstance(validation, dict):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    required = {"validated_edits": {"package", "revisions", "final_equivalence", "non_target", "template_text"},
                "validated_unchanged": {"package", "zero_edit", "byte_identity"}}
    checks = validation.get("checks")
    if validation.get("kind") not in required or not isinstance(checks, (list, tuple)) or not required[validation["kind"]].issubset(checks):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    for kind in ("final", "redline"):
        if not artifacts[kind].is_file() or validation.get(f"{kind}_sha256") != sha256_file(artifacts[kind]):
            raise ValueError("ARTIFACT_VERIFICATION_MISMATCH")


class RunStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.objects = self.root / "objects"
        self.objects.mkdir(exist_ok=True)
        self.db_path = self.root / "runs.sqlite3"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, ruleset_version TEXT NOT NULL,
                    ruleset_sha256 TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL, idempotency_key TEXT, request_hash TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(owner, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    ordinal INTEGER NOT NULL, filename TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL, source_size INTEGER NOT NULL,
                    input_key TEXT NOT NULL, status TEXT NOT NULL,
                    qualification_status TEXT, delivery_status TEXT NOT NULL DEFAULT 'not_generated',
                    error_code TEXT, report_json TEXT,
                    attempt INTEGER NOT NULL DEFAULT 0, fencing_token INTEGER NOT NULL DEFAULT 0,
                    lease_until REAL, next_attempt_at REAL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(batch_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    document_id TEXT NOT NULL REFERENCES documents(id), kind TEXT NOT NULL,
                    object_key TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
                    PRIMARY KEY(document_id, kind)
                );
                CREATE INDEX IF NOT EXISTS documents_work ON documents(status, next_attempt_at, lease_until);
            """)
            for name, definition in {"engine_build": "TEXT NOT NULL DEFAULT ''", "schema_version": "TEXT NOT NULL DEFAULT ''"}.items():
                if name not in {row["name"] for row in db.execute("PRAGMA table_info(batches)")}:
                    db.execute(f"ALTER TABLE batches ADD COLUMN {name} {definition}")
            if "ruleset_sha256" not in {row["name"] for row in db.execute("PRAGMA table_info(batches)")}:
                db.execute("ALTER TABLE batches ADD COLUMN ruleset_sha256 TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def object_path(self, key: str) -> Path:
        # Keys are generated here, but validate again before every read.
        path = (self.objects / key).resolve()
        if not path.is_relative_to(self.objects.resolve()):
            raise StoreError("invalid object key")
        return path

    def stage(self, data: bytes) -> tuple[str, str, int]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"inputs/{uuid.uuid4().hex}.docx"
        path = self.object_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return key, digest, len(data)

    def create_batch(self, *, owner: str, ruleset_version: str,
                     uploads: list[tuple[str, bytes]], idempotency_key: str | None = None,
                     ruleset_sha256: str = "") -> dict[str, Any]:
        if not uploads:
            raise ValueError("at least one DOCX is required")
        if not owner or not ruleset_version:
            raise ValueError("owner and ruleset version are required")
        fingerprints = [(name, hashlib.sha256(data).hexdigest()) for name, data in uploads]
        build = engine_build()
        request_hash = hashlib.sha256(json.dumps([ruleset_version, ruleset_sha256, build, SCHEMA_VERSION, fingerprints], ensure_ascii=False).encode()).hexdigest()
        with self._connect() as db:
            if idempotency_key:
                existing = db.execute("SELECT id, request_hash FROM batches WHERE owner=? AND idempotency_key=?",
                                      (owner, idempotency_key)).fetchone()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise Conflict("idempotency key was used for different input")
                    return self.get_batch(owner, existing["id"])
        staged: list[tuple[str, str, str, int]] = []
        try:
            for name, data in uploads:
                key, digest, size = self.stage(data)
                staged.append((name, key, digest, size))
            batch_id = uuid.uuid4().hex
            now = time.time()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO batches
                    (id,owner,ruleset_version,ruleset_sha256,status,idempotency_key,request_hash,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (batch_id, owner, ruleset_version, ruleset_sha256, "queued", idempotency_key, request_hash, now, now))
                db.execute("UPDATE batches SET engine_build=?,schema_version=? WHERE id=?", (build, SCHEMA_VERSION, batch_id))
                for ordinal, (name, key, digest, size) in enumerate(staged):
                    db.execute("""INSERT INTO documents
                        (id,batch_id,ordinal,filename,source_sha256,source_size,input_key,status,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (uuid.uuid4().hex, batch_id, ordinal, name, digest, size, key, "queued", now, now))
            return self.get_batch(owner, batch_id)
        except Exception:
            for _, key, _, _ in staged:
                self.object_path(key).unlink(missing_ok=True)
            # A simultaneous request may have won the idempotency race.
            if idempotency_key:
                with self._connect() as db:
                    existing = db.execute("SELECT id, request_hash FROM batches WHERE owner=? AND idempotency_key=?",
                                          (owner, idempotency_key)).fetchone()
                    if existing and existing["request_hash"] == request_hash:
                        return self.get_batch(owner, existing["id"])
            raise

    def list_batches(self, owner: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM batches WHERE owner=? ORDER BY created_at DESC", (owner,)).fetchall()
            return [self._batch_dict(db, row) for row in rows]

    def get_batch(self, owner: str, batch_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM batches WHERE id=? AND owner=?", (batch_id, owner)).fetchone()
            if row is None:
                raise NotFound("batch not found")
            return self._batch_dict(db, row)

    def _batch_dict(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        docs = db.execute("SELECT * FROM documents WHERE batch_id=? ORDER BY ordinal", (row["id"],)).fetchall()
        result = {key: row[key] for key in ("id", "ruleset_version", "ruleset_sha256", "status", "created_at", "updated_at")}
        result["documents"] = [self._document_dict(db, doc) for doc in docs]
        result["counts"] = {
            "total": len(docs), "succeeded": sum(doc["status"] == "succeeded" for doc in docs),
            "failed": sum(doc["status"] == "failed" for doc in docs),
            "pending": sum(doc["status"] not in ("succeeded", "failed") for doc in docs),
        }
        return result

    def _document_dict(self, db: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
        artifacts = db.execute("SELECT kind FROM artifacts WHERE document_id=?", (row["id"],)).fetchall()
        return {key: row[key] for key in ("id", "batch_id", "filename", "source_sha256", "status",
                                          "qualification_status", "delivery_status", "error_code", "attempt") } | {
            "artifacts": [item["kind"] for item in artifacts],
            "report_url": f"/api/batches/{row['batch_id']}/documents/{row['id']}/report",
            "download_urls": {item["kind"]: f"/api/batches/{row['batch_id']}/documents/{row['id']}/download/{item['kind']}" for item in artifacts},
        }

    def get_document(self, owner: str, batch_id: str, document_id: str) -> dict[str, Any]:
        self.get_batch(owner, batch_id)
        with self._connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=? AND batch_id=?", (document_id, batch_id)).fetchone()
            if row is None:
                raise NotFound("document not found")
            return self._document_dict(db, row)

    def get_report(self, owner: str, batch_id: str, document_id: str) -> dict[str, Any]:
        self.get_document(owner, batch_id, document_id)
        with self._connect() as db:
            row = db.execute("SELECT report_json FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row or not row["report_json"]:
            raise NotFound("report not available")
        return json.loads(row["report_json"])

    def get_artifact(self, owner: str, batch_id: str, document_id: str, kind: str) -> tuple[Path, str]:
        self.get_document(owner, batch_id, document_id)
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE document_id=? AND kind=?", (document_id, kind)).fetchone()
        if row is None:
            raise NotFound("artifact not available")
        path = self.object_path(row["object_key"])
        if not path.is_file() or path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
            raise Conflict("artifact integrity check failed")
        return path, row["sha256"]

    def claim(self, *, lease_seconds: int = 300, max_attempts: int = 3) -> dict[str, Any] | None:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            exhausted = db.execute("""SELECT id,batch_id,source_sha256 FROM documents
                WHERE status IN ('leased','running') AND lease_until<=? AND attempt>=?""",
                (now, max_attempts)).fetchall()
            for expired in exhausted:
                report = {"document_id": expired["id"], "source_sha256": expired["source_sha256"],
                          "qualification_status": "failed", "delivery_status": "not_generated",
                          "error_code": "WORKER_ATTEMPTS_EXHAUSTED",
                          "errors": [{"code": "WORKER_ATTEMPTS_EXHAUSTED", "stage": "worker"}]}
                db.execute("""UPDATE documents SET status='failed',qualification_status='failed',
                    delivery_status='not_generated',error_code='WORKER_ATTEMPTS_EXHAUSTED',
                    report_json=?,lease_until=NULL,updated_at=? WHERE id=?""",
                    (json.dumps(report), now, expired["id"]))
                self._refresh_batch(db, expired["batch_id"], now)
            row = db.execute("""SELECT d.*, b.ruleset_version, b.ruleset_sha256, b.engine_build, b.schema_version FROM documents d JOIN batches b ON b.id=d.batch_id
                WHERE b.status IN ('queued','running') AND d.attempt < ? AND
                (d.status='queued' OR (d.status='retry_wait' AND d.next_attempt_at<=?) OR
                 (d.status IN ('leased','running') AND d.lease_until<=?))
                ORDER BY d.created_at,d.ordinal LIMIT 1""", (max_attempts, now, now)).fetchone()
            if not row:
                return None
            token = row["fencing_token"] + 1
            attempt = row["attempt"] + 1
            db.execute("""UPDATE documents SET status='leased', attempt=?, fencing_token=?, lease_until=?,
                next_attempt_at=NULL, updated_at=? WHERE id=?""",
                (attempt, token, now + lease_seconds, now, row["id"]))
            db.execute("UPDATE batches SET status='running',updated_at=? WHERE id=?", (now, row["batch_id"]))
            return dict(row) | {"attempt": attempt, "fencing_token": token}

    def heartbeat(self, document_id: str, token: int, *, lease_seconds: int = 300) -> None:
        with self._connect() as db:
            changed = db.execute("""UPDATE documents SET status='running',lease_until=?,updated_at=?
                WHERE id=? AND fencing_token=? AND status IN ('leased','running') AND lease_until>?""",
                (time.time() + lease_seconds, time.time(), document_id, token, time.time())).rowcount
            if not changed:
                raise Conflict("stale worker lease")

    def finish(self, document_id: str, token: int, *, report: dict[str, Any],
               artifacts: dict[str, Path], failed: bool = False, error_code: str | None = None) -> None:
        # Verify all outputs before publication. Only report files are allowed for incomplete results.
        try:
            validate_delivery(report, artifacts)
        except ValueError as exc:
            raise Conflict(str(exc)) from exc
        delivery = report.get("delivery_status", "not_generated")
        if delivery == "complete" and not {"final", "redline"}.issubset(artifacts):
            raise Conflict("complete result requires both verified contracts")
        if delivery != "complete" and ("final" in artifacts or "redline" in artifacts):
            raise Conflict("incomplete result cannot publish contract downloads")
        verified = {}
        for kind, path in artifacts.items():
            if kind not in {"final", "redline", "report_json", "report_md"} or not path.is_file():
                raise StoreError("invalid artifact")
            verified[kind] = (sha256_file(path), path.stat().st_size)
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            if not row or row["fencing_token"] != token or row["status"] not in ("leased", "running"):
                raise Conflict("stale worker lease")
            if row["lease_until"] is not None and row["lease_until"] < now:
                raise Conflict("expired worker lease")
            for kind, path in artifacts.items():
                # Attempt objects are immutable. Database pointer is published only while token is current.
                key = f"results/{document_id}/{token}/{uuid.uuid4().hex}/{kind}{path.suffix}"
                target = self.object_path(key)
                target.parent.mkdir(parents=True, exist_ok=True)
                with path.open("rb") as source, target.open("xb") as output:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                digest, size = verified[kind]
                if sha256_file(target) != digest:
                    raise Conflict("artifact copy verification failed")
                db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?)",
                           (document_id, kind, key, digest, size))
            db.execute("""UPDATE documents SET status=?,qualification_status=?,delivery_status=?,error_code=?,
                report_json=?,lease_until=NULL,updated_at=? WHERE id=?""",
                ("failed" if failed else "succeeded", report.get("qualification_status"), delivery,
                 error_code, json.dumps(report, ensure_ascii=False), now, document_id))
            self._refresh_batch(db, row["batch_id"], now)

    def retry(self, document_id: str, token: int, *, error_code: str, max_attempts: int = 3,
              base_delay_seconds: int = 2) -> None:
        now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            if not row or row["fencing_token"] != token or row["status"] not in ("leased", "running"):
                raise Conflict("stale worker lease")
            if row["lease_until"] is None or row["lease_until"] <= now:
                raise Conflict("expired worker lease")
            terminal = row["attempt"] >= max_attempts
            pause_required = error_code in {"MODEL_CIRCUIT_OPEN", "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED", "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_LEDGER_UNAVAILABLE"}
            delay = min(base_delay_seconds * (2 ** max(row["attempt"] - 1, 0)) * random.uniform(0.8, 1.2), 300)
            db.execute("""UPDATE documents SET status=?,error_code=?,next_attempt_at=?,lease_until=NULL,
                updated_at=? WHERE id=?""", ("failed" if terminal else "retry_wait", error_code,
                                                None if terminal else now + delay, now, document_id))
            if terminal:
                report = {"document_id": document_id, "source_sha256": row["source_sha256"],
                          "qualification_status": "failed", "delivery_status": "not_generated",
                          "error_code": error_code, "errors": [{"code": error_code, "stage": "worker"}]}
                db.execute("UPDATE documents SET report_json=?,qualification_status='failed',delivery_status='not_generated' WHERE id=?",
                           (json.dumps(report), document_id))
            self._refresh_batch(db, row["batch_id"], now)
            if not terminal and (pause_required or (row["attempt"] >= 2 and error_code in {"MODEL_NETWORK_ERROR", "MODEL_RETRY_EXHAUSTED"})):
                db.execute("UPDATE batches SET status='paused',updated_at=? WHERE id=?", (now, row["batch_id"]))

    def pause(self, owner: str, batch_id: str) -> dict[str, Any]:
        self.get_batch(owner, batch_id)
        with self._connect() as db:
            db.execute("UPDATE batches SET status='paused',updated_at=? WHERE id=? AND status!='completed'",
                       (time.time(), batch_id))
        return self.get_batch(owner, batch_id)

    def resume(self, owner: str, batch_id: str) -> dict[str, Any]:
        self.get_batch(owner, batch_id)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT COUNT(*) AS pending FROM documents WHERE batch_id=? AND status NOT IN ('succeeded','failed')", (batch_id,)).fetchone()
            db.execute("UPDATE batches SET status=?,updated_at=? WHERE id=?",
                       ("queued" if row["pending"] else "completed", time.time(), batch_id))
        return self.get_batch(owner, batch_id)

    @staticmethod
    def _refresh_batch(db: sqlite3.Connection, batch_id: str, now: float) -> None:
        row = db.execute("SELECT COUNT(*) AS pending FROM documents WHERE batch_id=? AND status NOT IN ('succeeded','failed')", (batch_id,)).fetchone()
        current = db.execute("SELECT status FROM batches WHERE id=?", (batch_id,)).fetchone()["status"]
        state = "completed" if row["pending"] == 0 else ("paused" if current == "paused" else "running")
        db.execute("UPDATE batches SET status=?,updated_at=? WHERE id=?", (state, now, batch_id))
