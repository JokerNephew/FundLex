"""Persistence for independent contract comparison tasks.

This store deliberately uses the existing :class:`RunStore` database and object
store while keeping comparison tables and lifecycle separate from revision
batches.  Document bodies are stored as objects; only metadata and result JSON
are persisted in the database.
"""
from __future__ import annotations

import hashlib
from html import escape as html_escape
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from ..docx import DocxError
from ..store import Conflict, NotFound, RunStore, sha256_file


PAIR_STATUSES = {"pending", "queued", "leased", "running", "succeeded", "incomplete", "failed", "retry_wait"}


def _now() -> float:
    return time.time()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_filename(name: str) -> bool:
    path = Path(str(name).replace("\\", "/"))
    return bool(name and path.name == name and name.strip() and not any(ord(c) < 32 for c in name))


class CompareStore:
    """SQLite/MySQL compatible compare task store backed by ``RunStore``."""

    def __init__(self, store: RunStore):
        self.store = store
        with self.store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS compare_tasks (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                    status TEXT NOT NULL, sealed INTEGER NOT NULL DEFAULT 0,
                    idempotency_key TEXT, request_hash TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(owner, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS compare_pairs (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES compare_tasks(id),
                    ordinal INTEGER NOT NULL, client_pair_id TEXT NOT NULL, label TEXT NOT NULL,
                    status TEXT NOT NULL, error_code TEXT, result_json LONGTEXT,
                    result_sha256 TEXT, attempt INTEGER NOT NULL DEFAULT 0,
                    fencing_token INTEGER NOT NULL DEFAULT 0, lease_until REAL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(task_id, ordinal), UNIQUE(task_id, client_pair_id)
                );
                CREATE TABLE IF NOT EXISTS compare_pair_files (
                    pair_id TEXT NOT NULL REFERENCES compare_pairs(id), side TEXT NOT NULL,
                    client_id TEXT NOT NULL, filename TEXT NOT NULL, size INTEGER NOT NULL,
                    upload_status TEXT NOT NULL DEFAULT 'pending', error_code TEXT,
                    source_sha256 TEXT, object_key TEXT,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    PRIMARY KEY(pair_id, side), UNIQUE(pair_id, client_id)
                );
                CREATE TABLE IF NOT EXISTS compare_artifacts (
                    pair_id TEXT NOT NULL REFERENCES compare_pairs(id), kind TEXT NOT NULL,
                    object_key TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
                    PRIMARY KEY(pair_id, kind)
                );
                CREATE TABLE IF NOT EXISTS compare_selection_drafts (
                    pair_id TEXT PRIMARY KEY REFERENCES compare_pairs(id),
                    selection_epoch INTEGER NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    left_source_sha256 TEXT NOT NULL,
                    right_source_sha256 TEXT NOT NULL,
                    decisions_json LONGTEXT NOT NULL,
                    decision_hash TEXT NOT NULL,
                    binding_hash TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS compare_selection_artifacts (
                    pair_id TEXT NOT NULL REFERENCES compare_pairs(id),
                    version INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    object_key TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    selection_epoch INTEGER NOT NULL,
                    result_sha256 TEXT NOT NULL,
                    left_source_sha256 TEXT NOT NULL,
                    right_source_sha256 TEXT NOT NULL,
                    decision_hash TEXT NOT NULL,
                    binding_hash TEXT NOT NULL,
                    idempotency_key VARCHAR(128),
                    status TEXT NOT NULL DEFAULT 'current',
                    created_at REAL NOT NULL,
                    PRIMARY KEY(pair_id, version, kind),
                    UNIQUE(pair_id, idempotency_key, kind)
                );
                CREATE INDEX IF NOT EXISTS compare_pairs_work
                    ON compare_pairs(status, lease_until, updated_at);
                CREATE INDEX IF NOT EXISTS compare_selection_artifacts_lookup
                    ON compare_selection_artifacts(pair_id, version, status);
            """)

    def _connect(self):
        return self.store._connect()

    @staticmethod
    def _owned_task(db, owner: str, task_id: str):
        row = db.execute("SELECT * FROM compare_tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
        if row is None:
            raise NotFound("compare task not found")
        return row

    def _owned_task_locked(self, db, owner: str, task_id: str):
        """Load an owned task for a mutating transaction.

        SQLite's BEGIN IMMEDIATE already serializes writers.  MySQL needs a
        current locking read: a non-locking snapshot can observe ``sealed=0``
        while a concurrent seal commits, allowing an upload to land after the
        pair was marked incomplete.
        """
        sql = "SELECT * FROM compare_tasks WHERE id=? AND owner=?"
        if self.store.database.dialect == "mysql":
            sql += " FOR UPDATE"
        row = db.execute(sql, (task_id, owner)).fetchone()
        if row is None:
            raise NotFound("compare task not found")
        return row

    def create(self, owner: str, name: str, pairs: list[dict[str, Any]],
               idempotency_key: str | None = None) -> dict[str, Any]:
        if not owner or not str(name).strip() or not pairs:
            raise ValueError("name and at least one pair are required")
        if len(pairs) > 1000:
            raise ValueError("too many compare pairs")
        seen_pair, seen_client = set(), set()
        normalized = []
        for pair in pairs:
            if not isinstance(pair, dict):
                raise ValueError("invalid pair")
            pair_id = str(pair.get("client_pair_id") or "").strip()
            label = str(pair.get("label") or pair_id).strip()
            left, right = pair.get("left"), pair.get("right")
            if not pair_id or pair_id in seen_pair or not isinstance(left, dict) or not isinstance(right, dict):
                raise ValueError("invalid pair manifest")
            seen_pair.add(pair_id)
            sides = []
            for side, entry in (("left", left), ("right", right)):
                client_id = str(entry.get("client_id") or "").strip()
                filename = str(entry.get("name") or "")
                size = entry.get("size")
                if (not client_id or client_id in seen_client or not _safe_filename(filename)
                        or not filename.lower().endswith(".docx") or not isinstance(size, int) or size <= 0):
                    raise ValueError("invalid file manifest")
                seen_client.add(client_id)
                sides.append({"side": side, "client_id": client_id, "filename": filename, "size": size})
            normalized.append({"client_pair_id": pair_id, "label": label, "files": sides})
        fingerprint = hashlib.sha256(_json({"name": str(name).strip(), "pairs": normalized}).encode()).hexdigest()
        now = _now()
        try:
            with self._connect() as db:
                if idempotency_key:
                    existing = db.execute("SELECT id,request_hash FROM compare_tasks WHERE owner=? AND idempotency_key=?",
                                          (owner, idempotency_key)).fetchone()
                    if existing:
                        if existing["request_hash"] != fingerprint:
                            raise Conflict("idempotency key was used for different input")
                        return self.get(owner, existing["id"])
                task_id = uuid.uuid4().hex
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO compare_tasks
                (id,owner,name,status,sealed,idempotency_key,request_hash,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?)""",
                       (task_id, owner, str(name).strip(), "uploading", 0, idempotency_key,
                        fingerprint, now, now))
                for ordinal, pair in enumerate(normalized):
                    pid = uuid.uuid4().hex
                    db.execute("""INSERT INTO compare_pairs
                    (id,task_id,ordinal,client_pair_id,label,status,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?)""",
                           (pid, task_id, ordinal, pair["client_pair_id"], pair["label"], "pending", now, now))
                    for item in pair["files"]:
                        db.execute("""INSERT INTO compare_pair_files
                        (pair_id,side,client_id,filename,size,upload_status,created_at,updated_at)
                        VALUES(?,?,?,?,?,?,?,?)""",
                               (pid, item["side"], item["client_id"], item["filename"], item["size"],
                                "pending", now, now))
        except Exception:
            if idempotency_key:
                with self._connect() as db:
                    existing = db.execute("SELECT id,request_hash FROM compare_tasks WHERE owner=? AND idempotency_key=?",
                                          (owner, idempotency_key)).fetchone()
                    if existing and existing["request_hash"] == fingerprint:
                        return self.get(owner, existing["id"])
            raise
        return self.get(owner, task_id)

    def list(self, owner: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM compare_tasks WHERE owner=? ORDER BY created_at DESC", (owner,)).fetchall()
            return [self._task_dict(db, row) for row in rows]

    def get(self, owner: str, task_id: str) -> dict[str, Any]:
        with self._connect() as db:
            return self._task_dict(db, self._owned_task(db, owner, task_id))

    def _task_dict(self, db, row) -> dict[str, Any]:
        pairs = db.execute("SELECT * FROM compare_pairs WHERE task_id=? ORDER BY ordinal", (row["id"],)).fetchall()
        items = [self._pair_dict(db, p) for p in pairs]
        counts = {"total": len(items), "succeeded": sum(p["status"] == "succeeded" for p in items),
                  "failed": sum(p["status"] == "failed" for p in items),
                  "incomplete": sum(p["status"] == "incomplete" for p in items),
                  "pending": sum(p["status"] not in {"succeeded", "failed", "incomplete"} for p in items)}
        uploaded_pairs = sum(all(p.get(side, {}).get("upload_status") == "accepted"
                                 for side in ("left", "right")) for p in items)
        return {"id": row["id"], "name": row["name"], "status": row["status"],
                "sealed": bool(row["sealed"]), "created_at": row["created_at"], "updated_at": row["updated_at"],
                "total": len(items), "uploaded_pairs": uploaded_pairs, "counts": counts, "pairs": items}

    def pairs(self, owner: str, task_id: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            task = self._owned_task(db, owner, task_id)
            return [self._pair_dict(db, p) for p in db.execute(
                "SELECT * FROM compare_pairs WHERE task_id=? ORDER BY ordinal", (task["id"],)).fetchall()]

    def _pair_dict(self, db, row) -> dict[str, Any]:
        files = db.execute("SELECT * FROM compare_pair_files WHERE pair_id=? ORDER BY side", (row["id"],)).fetchall()
        mapped = {}
        for file in files:
            mapped[file["side"]] = {"client_id": file["client_id"], "name": file["filename"], "size": file["size"],
                                     "upload_status": file["upload_status"], "error_code": file["error_code"],
                                     "source_sha256": file["source_sha256"]}
        result = {"id": row["id"], "task_id": row["task_id"], "ordinal": row["ordinal"],
                  "client_pair_id": row["client_pair_id"], "label": row["label"], "status": row["status"],
                  "error_code": row["error_code"], "summary": None, "coverage": None,
                  "result_sha256": row["result_sha256"], "left": mapped.get("left"), "right": mapped.get("right"),
                  "view_url": f"/api/compare/pairs/{row['id']}/view",
                  "result_url": f"/api/compare/pairs/{row['id']}"}
        if row["result_json"]:
            try:
                payload = json.loads(row["result_json"])
                result["summary"] = payload.get("summary")
                result["coverage"] = payload.get("coverage")
            except (TypeError, ValueError):
                pass
        return result

    def _verify_result(self, db, row) -> dict[str, Any]:
        """A result is bound to both immutable bytes and the database pointer."""
        try:
            result = json.loads(row["result_json"])
        except (TypeError, ValueError):
            raise Conflict("COMPARE_RESULT_INVALID") from None
        if row["status"] not in {"succeeded", "incomplete"}:
            return result
        artifact = db.execute("SELECT * FROM compare_artifacts WHERE pair_id=? AND kind='result_json'",
                              (row["id"],)).fetchone()
        if artifact is None:
            raise Conflict("COMPARE_RESULT_INVALID")
        path = self.store.object_path(artifact["object_key"])
        if (not path.is_file() or path.stat().st_size != artifact["size"]
                or sha256_file(path) != artifact["sha256"]
                or artifact["sha256"] != row["result_sha256"]
                or hashlib.sha256(_json(result).encode()).hexdigest() != artifact["sha256"]):
            raise Conflict("COMPARE_RESULT_INVALID")
        return result

    def upload(self, owner: str, task_id: str, uploads: list[dict[str, Any]]) -> dict[str, Any]:
        """Commit validated uploads; each item has client_id/name/data/error_code."""
        self.get(owner, task_id)
        ids = [str(item.get("client_id") or "") for item in uploads]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate client_id")
        staged: list[str] = []
        committed = False
        receipts = []
        try:
            for item in uploads:
                if not item.get("error_code"):
                    key, digest, size = self.store.stage(item["data"])
                    item.update(key=key, digest=digest, size=size)
                    staged.append(key)
                else:
                    item.update(digest=hashlib.sha256(item.get("data", b"")).hexdigest(), size=len(item.get("data", b"")))
            now = _now()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                task = self._owned_task_locked(db, owner, task_id)
                if task["sealed"]:
                    raise Conflict("COMPARE_TASK_SEALED")
                for item in uploads:
                    row = db.execute("""SELECT f.*,p.id pair_id,p.status pair_status,p.task_id
                        FROM compare_pair_files f JOIN compare_pairs p ON p.id=f.pair_id
                        WHERE p.task_id=? AND f.client_id=?""", (task_id, item.get("client_id"))).fetchone()
                    receipt = {"client_id": item.get("client_id"), "status": "rejected", "pair_id": None, "error_code": None}
                    if row is None:
                        receipt["error_code"] = "MANIFEST_ENTRY_NOT_FOUND"
                    elif row["upload_status"] == "accepted":
                        same = row["source_sha256"] == item["digest"] and row["size"] == item["size"] and row["filename"] == item.get("name")
                        receipt.update(status="already_accepted" if same else "rejected", pair_id=row["pair_id"],
                                       error_code=None if same else "UPLOAD_IDENTITY_CONFLICT")
                    elif item.get("error_code"):
                        receipt.update(pair_id=row["pair_id"], error_code=item["error_code"])
                        db.execute("UPDATE compare_pair_files SET upload_status='rejected',error_code=?,updated_at=? WHERE pair_id=? AND side=?",
                                   (item["error_code"], now, row["pair_id"], row["side"]))
                    elif row["filename"] != item.get("name") or row["size"] != item["size"]:
                        receipt.update(pair_id=row["pair_id"], error_code="MANIFEST_FILE_MISMATCH")
                        db.execute("UPDATE compare_pair_files SET upload_status='rejected',error_code=?,updated_at=? WHERE pair_id=? AND side=?",
                                   ("MANIFEST_FILE_MISMATCH", now, row["pair_id"], row["side"]))
                    else:
                        db.execute("""UPDATE compare_pair_files SET upload_status='accepted',error_code=NULL,
                            source_sha256=?,object_key=?,updated_at=? WHERE pair_id=? AND side=?""",
                                   (item["digest"], item["key"], now, row["pair_id"], row["side"]))
                        receipt.update(status="accepted", pair_id=row["pair_id"])
                    receipts.append(receipt)
                db.execute("UPDATE compare_tasks SET updated_at=? WHERE id=?", (now, task_id))
                committed = True
                # No object is released until after the metadata transaction commits.
                used = {r.get("client_id") for r in receipts if r.get("status") == "accepted"}
            for item in uploads:
                if item.get("key") and item.get("client_id") not in used:
                    self.store.object_path(item["key"]).unlink(missing_ok=True)
            return {"receipts": receipts, "task": self.get(owner, task_id)}
        except Exception:
            if not committed:
                for key in staged:
                    self.store.object_path(key).unlink(missing_ok=True)
            raise

    def seal(self, owner: str, task_id: str) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            task = self._owned_task_locked(db, owner, task_id)
            if task["sealed"]:
                return self._task_dict(db, task)
            now = _now()
            pairs = db.execute("SELECT * FROM compare_pairs WHERE task_id=? ORDER BY ordinal", (task_id,)).fetchall()
            for pair in pairs:
                files = db.execute("SELECT * FROM compare_pair_files WHERE pair_id=?", (pair["id"],)).fetchall()
                complete = len(files) == 2 and all(f["upload_status"] == "accepted" and f["object_key"] for f in files)
                if complete:
                    db.execute("UPDATE compare_pairs SET status='queued',error_code=NULL,updated_at=? WHERE id=?", (now, pair["id"]))
                else:
                    db.execute("UPDATE compare_pairs SET status='failed',error_code='COMPARE_PAIR_INCOMPLETE',updated_at=? WHERE id=?", (now, pair["id"]))
            queued = db.execute("SELECT COUNT(*) c FROM compare_pairs WHERE task_id=? AND status='queued'", (task_id,)).fetchone()["c"]
            db.execute("UPDATE compare_tasks SET sealed=1,status=?,updated_at=? WHERE id=?",
                       ("queued" if queued else "completed", now, task_id))
            return self._task_dict(db, self._owned_task(db, owner, task_id))

    def get_pair(self, owner: str, pair_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("""SELECT p.*,t.owner FROM compare_pairs p JOIN compare_tasks t ON t.id=p.task_id
                WHERE p.id=? AND t.owner=?""", (pair_id, owner)).fetchone()
            if row is None:
                raise NotFound("compare pair not found")
            result = self._pair_dict(db, row)
            if row["result_json"]:
                result["result"] = self._verify_result(db, row)
            return result

    # --- human Compare selection drafts and generated artifacts ------------

    @staticmethod
    def _selection_result_ids(result: dict[str, Any]) -> tuple[str, ...]:
        diffs = result.get("diffs")
        if not isinstance(diffs, list):
            raise Conflict("COMPARE_RESULT_INVALID")
        return tuple(str(item.get("id", "")) for item in diffs if isinstance(item, dict))

    def _selection_row(self, db, owner: str, pair_id: str, *, lock: bool = False):
        sql = """SELECT p.*,t.owner FROM compare_pairs p JOIN compare_tasks t ON t.id=p.task_id
            WHERE p.id=? AND t.owner=?"""
        if lock and self.store.database.dialect == "mysql":
            sql += " FOR UPDATE"
        row = db.execute(sql, (pair_id, owner)).fetchone()
        if row is None:
            raise NotFound("compare pair not found")
        if row["status"] not in {"succeeded", "incomplete"}:
            raise Conflict("COMPARE_RESULT_NOT_READY")
        return row

    def _selection_files(self, db, pair_id: str) -> dict[str, dict[str, Any]]:
        files = {item["side"]: dict(item) for item in db.execute(
            "SELECT * FROM compare_pair_files WHERE pair_id=?", (pair_id,)).fetchall()}
        if set(files) != {"left", "right"} or any(not item.get("object_key") for item in files.values()):
            raise Conflict("COMPARE_INPUT_NOT_READY")
        return files

    def _selection_result_locked(self, db, row) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
        result = self._verify_result(db, row)
        files = self._selection_files(db, row["id"])
        for side, item in files.items():
            path = self.store.object_path(item["object_key"])
            if (not path.is_file() or path.stat().st_size != item["size"]
                    or sha256_file(path) != item["source_sha256"]):
                raise Conflict("COMPARE_INPUT_INTEGRITY_FAILED")
            if result.get(side, {}).get("sha256") != item["source_sha256"]:
                raise Conflict("COMPARE_RESULT_INVALID")
        return result, files

    @staticmethod
    def _selection_draft_dict(row, assessment) -> dict[str, Any]:
        return {
            "selection_epoch": int(row["selection_epoch"]),
            "result_sha256": row["result_sha256"],
            "left_source_sha256": row["left_source_sha256"],
            "right_source_sha256": row["right_source_sha256"],
            "decisions": dict(assessment.decisions),
            "decision_hash": row["decision_hash"],
            "binding_hash": row["binding_hash"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _selection_assessment(row, result: dict[str, Any], draft):
        """Read a draft only after verifying its canonical hashes.

        The source/result binding is checked by ``_selection_result_locked``.
        This second check protects the persisted decision map and its two
        derived hashes from a damaged or manually altered database row.
        """
        from .selection import SelectionError, assess_selection, binding_hash, decision_hash
        try:
            decisions = json.loads(draft["decisions_json"])
            assessment = assess_selection(result, decisions, result_sha256=row["result_sha256"])
            decision_values = dict(decisions)
            expected_decision_hash = decision_hash(assessment.decisions)
            expected_binding_hash = binding_hash(
                result_sha256=row["result_sha256"],
                left_source_sha256=draft["left_source_sha256"],
                right_source_sha256=draft["right_source_sha256"],
                selection_epoch=int(draft["selection_epoch"]),
                decisions=assessment.decisions,
            )
        except (TypeError, ValueError, KeyError, SelectionError):
            raise Conflict("COMPARE_SELECTION_INVALID") from None
        if (decision_values != assessment.decision_map
                or draft["decision_hash"] != expected_decision_hash
                or draft["binding_hash"] != expected_binding_hash):
            raise Conflict("COMPARE_SELECTION_INVALID")
        return assessment

    def _selection_artifacts(self, db, pair_id: str) -> list[dict[str, Any]]:
        rows = db.execute("""SELECT version,kind,sha256,size,selection_epoch,result_sha256,
            left_source_sha256,right_source_sha256,decision_hash,binding_hash,status,created_at
            FROM compare_selection_artifacts WHERE pair_id=? ORDER BY version DESC,kind""", (pair_id,)).fetchall()
        return [{
            "version": row["version"], "kind": row["kind"], "sha256": row["sha256"], "size": row["size"],
            "selection_epoch": row["selection_epoch"], "result_sha256": row["result_sha256"],
            "left_source_sha256": row["left_source_sha256"], "right_source_sha256": row["right_source_sha256"],
            "decision_hash": row["decision_hash"], "binding_hash": row["binding_hash"],
            "status": row["status"], "created_at": row["created_at"],
            "download_url": f"/api/compare/pairs/{pair_id}/selection-artifacts/{row['version']}/{row['kind']}",
        } for row in rows]

    def _selection_view_locked(self, db, row, result: dict[str, Any], *, assessment) -> dict[str, Any]:
        draft = db.execute("SELECT * FROM compare_selection_drafts WHERE pair_id=?", (row["id"],)).fetchone()
        if draft is None:
            raise Conflict("COMPARE_SELECTION_NOT_INITIALIZED")
        return {
            "pair": {"id": row["id"], "task_id": row["task_id"], "label": row["label"],
                     "ordinal": row["ordinal"], "status": row["status"]},
            "result_sha256": row["result_sha256"],
            "left_source_sha256": draft["left_source_sha256"],
            "right_source_sha256": draft["right_source_sha256"],
            "diffs": result.get("diffs", []),
            "selection": self._selection_draft_dict(draft, assessment),
            "assessment": assessment.to_dict(),
            "artifacts": self._selection_artifacts(db, row["id"]),
        }

    def _ensure_selection_draft_locked(self, db, row, result: dict[str, Any], files: dict[str, dict[str, Any]]):
        from .selection import assess_selection, binding_hash, decision_hash
        current = db.execute("SELECT * FROM compare_selection_drafts WHERE pair_id=?", (row["id"],)).fetchone()
        left_hash, right_hash = files["left"]["source_sha256"], files["right"]["source_sha256"]
        if current is not None:
            if (current["result_sha256"] != row["result_sha256"] or current["left_source_sha256"] != left_hash
                    or current["right_source_sha256"] != right_hash):
                raise Conflict("COMPARE_SELECTION_BINDING_MISMATCH")
            return current
        decisions = {diff_id: "pending" for diff_id in self._selection_result_ids(result)}
        assessment = assess_selection(result, decisions, result_sha256=row["result_sha256"])
        now = _now()
        epoch = 0
        db.execute("""INSERT INTO compare_selection_drafts
            (pair_id,selection_epoch,result_sha256,left_source_sha256,right_source_sha256,decisions_json,
             decision_hash,binding_hash,updated_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                   (row["id"], epoch, row["result_sha256"], left_hash, right_hash, _json(dict(assessment.decisions)),
                    decision_hash(assessment.decisions), binding_hash(result_sha256=row["result_sha256"],
                    left_source_sha256=left_hash, right_source_sha256=right_hash,
                    selection_epoch=epoch, decisions=assessment.decisions), now, now))
        return db.execute("SELECT * FROM compare_selection_drafts WHERE pair_id=?", (row["id"],)).fetchone()

    def get_selection(self, owner: str, pair_id: str) -> dict[str, Any]:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._selection_row(db, owner, pair_id, lock=True)
            result, files = self._selection_result_locked(db, row)
            draft = self._ensure_selection_draft_locked(db, row, result, files)
            assessment = self._selection_assessment(row, result, draft)
            return self._selection_view_locked(db, row, result, assessment=assessment)

    def save_selection(self, owner: str, pair_id: str, *, expected_epoch: int,
                       result_sha256: str, left_source_sha256: str, right_source_sha256: str,
                       decisions: dict[str, str]) -> dict[str, Any]:
        from .selection import assess_selection, binding_hash, decision_hash, normalize_decisions
        if type(expected_epoch) is not int or expected_epoch < 0:
            raise ValueError("INVALID_SELECTION_EPOCH")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = self._selection_row(db, owner, pair_id, lock=True)
            result, files = self._selection_result_locked(db, row)
            draft = self._ensure_selection_draft_locked(db, row, result, files)
            if expected_epoch != draft["selection_epoch"]:
                raise Conflict("SELECTION_EPOCH_CONFLICT")
            if (result_sha256 != row["result_sha256"] or left_source_sha256 != files["left"]["source_sha256"]
                    or right_source_sha256 != files["right"]["source_sha256"]):
                raise Conflict("SELECTION_BINDING_MISMATCH")
            full = normalize_decisions(result, decisions)
            assessment = assess_selection(result, full, result_sha256=row["result_sha256"])
            current = self._selection_assessment(row, result, draft)
            if current.decision_map != full:
                epoch = draft["selection_epoch"] + 1
                now = _now()
                db.execute("""UPDATE compare_selection_drafts SET selection_epoch=?,decisions_json=?,decision_hash=?,
                    binding_hash=?,updated_at=? WHERE pair_id=?""",
                           (epoch, _json(full), decision_hash(full), binding_hash(
                               result_sha256=row["result_sha256"], left_source_sha256=files["left"]["source_sha256"],
                               right_source_sha256=files["right"]["source_sha256"], selection_epoch=epoch,
                               decisions=full), now, pair_id))
                db.execute("UPDATE compare_selection_artifacts SET status='stale' WHERE pair_id=? AND status='current'",
                           (pair_id,))
                draft = db.execute("SELECT * FROM compare_selection_drafts WHERE pair_id=?", (pair_id,)).fetchone()
            return self._selection_view_locked(db, row, result, assessment=assessment)

    def preview_selection(self, owner: str, pair_id: str, *, expected_epoch: int,
                          result_sha256: str, left_source_sha256: str, right_source_sha256: str) -> dict[str, Any]:
        view = self.get_selection(owner, pair_id)
        selection = view["selection"]
        if expected_epoch != selection["selection_epoch"]:
            raise Conflict("SELECTION_EPOCH_CONFLICT")
        if (result_sha256 != view["result_sha256"] or left_source_sha256 != view["left_source_sha256"]
                or right_source_sha256 != view["right_source_sha256"]):
            raise Conflict("SELECTION_BINDING_MISMATCH")
        return {"pair": view["pair"], "selection": selection, "assessment": view["assessment"],
                "artifacts": view["artifacts"]}

    def selection_generation_inputs(self, owner: str, pair_id: str, *, expected_epoch: int,
                                    result_sha256: str, left_source_sha256: str,
                                    right_source_sha256: str) -> dict[str, Any]:
        view = self.get_selection(owner, pair_id)
        selection = view["selection"]
        if expected_epoch != selection["selection_epoch"]:
            raise Conflict("SELECTION_EPOCH_CONFLICT")
        if (result_sha256 != view["result_sha256"] or left_source_sha256 != view["left_source_sha256"]
                or right_source_sha256 != view["right_source_sha256"]):
            raise Conflict("SELECTION_BINDING_MISMATCH")
        files = {item["side"]: item for item in self.pair_inputs(pair_id)}
        return {"result": self.get_pair(owner, pair_id)["result"], "decisions": selection["decisions"],
                "selection_epoch": selection["selection_epoch"], "result_sha256": view["result_sha256"],
                "left_path": self.store.object_path(files["left"]["object_key"]),
                "right_path": self.store.object_path(files["right"]["object_key"]),
                "left_source_sha256": view["left_source_sha256"],
                "right_source_sha256": view["right_source_sha256"]}

    def publish_selection_generation(self, owner: str, pair_id: str, *, expected_epoch: int,
                                     result_sha256: str, left_source_sha256: str,
                                     right_source_sha256: str, idempotency_key: str | None,
                                     final_path: Path, redline_path: Path,
                                     report_builder: Callable[[int, str, str], tuple[bytes, bytes]]) -> dict[str, Any]:
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise ValueError("INVALID_IDEMPOTENCY_KEY")
        staged: list[Path] = []
        copied: list[Path] = []
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = self._selection_row(db, owner, pair_id, lock=True)
                result, files = self._selection_result_locked(db, row)
                draft = self._ensure_selection_draft_locked(db, row, result, files)
                if expected_epoch != draft["selection_epoch"]:
                    raise Conflict("SELECTION_EPOCH_CONFLICT")
                if (result_sha256 != row["result_sha256"] or left_source_sha256 != files["left"]["source_sha256"]
                        or right_source_sha256 != files["right"]["source_sha256"]):
                    raise Conflict("SELECTION_BINDING_MISMATCH")
                if idempotency_key:
                    existing = db.execute("""SELECT * FROM compare_selection_artifacts
                        WHERE pair_id=? AND idempotency_key=? AND kind='selected_final'""", (pair_id, idempotency_key)).fetchone()
                    if existing:
                        if (existing["selection_epoch"] != draft["selection_epoch"]
                                or existing["result_sha256"] != row["result_sha256"]
                                or existing["left_source_sha256"] != files["left"]["source_sha256"]
                                or existing["right_source_sha256"] != files["right"]["source_sha256"]
                                or existing["decision_hash"] != draft["decision_hash"]
                                or existing["binding_hash"] != draft["binding_hash"]):
                            raise Conflict("IDEMPOTENCY_KEY_CONFLICT")
                        return self._selection_generation_dict(db, pair_id, existing["version"])
                assessment = self._selection_assessment(row, result, draft)
                decisions = assessment.decision_map
                if not assessment.can_generate:
                    if assessment.pending_ids:
                        raise Conflict("PENDING_SELECTIONS")
                    raise Conflict("SELECTION_UNSUPPORTED")
                version = (db.execute("""SELECT COALESCE(MAX(version),0)+1 AS version
                    FROM compare_selection_artifacts WHERE pair_id=?""", (pair_id,)).fetchone()["version"])
                final_hash, redline_hash = sha256_file(final_path), sha256_file(redline_path)
                report_json, report_markdown = report_builder(version, final_hash, redline_hash)
                artifacts = (("selected_final", final_path, final_hash, "docx"),
                             ("selected_redline", redline_path, redline_hash, "docx"))
                report_temp = self.store.object_path(f"compare/selection-temp/{uuid.uuid4().hex}.json")
                report_temp.parent.mkdir(parents=True, exist_ok=True)
                report_temp.write_bytes(report_json)
                staged.append(report_temp)
                md_temp = self.store.object_path(f"compare/selection-temp/{uuid.uuid4().hex}.md")
                md_temp.write_bytes(report_markdown)
                staged.append(md_temp)
                artifacts += (("selection_report_json", report_temp, hashlib.sha256(report_json).hexdigest(), "json"),
                              ("selection_report_markdown", md_temp, hashlib.sha256(report_markdown).hexdigest(), "md"))
                now = _now()
                db.execute("UPDATE compare_selection_artifacts SET status='stale' WHERE pair_id=? AND status='current'", (pair_id,))
                for kind, source, digest, extension in artifacts:
                    key = f"compare/selection/{pair_id}/{version}/{kind}.{extension}"
                    target = self.store.object_path(key)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with source.open("rb") as incoming, target.open("xb") as output:
                        for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                            output.write(chunk)
                        output.flush(); os.fsync(output.fileno())
                    if sha256_file(target) != digest:
                        raise Conflict("SELECTION_ARTIFACT_INTEGRITY_FAILED")
                    copied.append(target)
                    db.execute("""INSERT INTO compare_selection_artifacts
                        (pair_id,version,kind,object_key,sha256,size,selection_epoch,result_sha256,
                         left_source_sha256,right_source_sha256,decision_hash,binding_hash,idempotency_key,status,created_at)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (pair_id, version, kind, key, digest, target.stat().st_size,
                        draft["selection_epoch"], row["result_sha256"], files["left"]["source_sha256"], files["right"]["source_sha256"],
                        draft["decision_hash"], draft["binding_hash"], idempotency_key, "current", now))
                return self._selection_generation_dict(db, pair_id, version)
        except Exception:
            for path in copied + staged:
                path.unlink(missing_ok=True)
            raise
        finally:
            for path in staged:
                path.unlink(missing_ok=True)

    def _selection_generation_dict(self, db, pair_id: str, version: int) -> dict[str, Any]:
        rows = db.execute("SELECT * FROM compare_selection_artifacts WHERE pair_id=? AND version=? ORDER BY kind",
                          (pair_id, version)).fetchall()
        if not rows:
            raise NotFound("selection artifact not found")
        first = rows[0]
        return {"pair_id": pair_id, "version": version, "status": first["status"],
                "selection_epoch": first["selection_epoch"], "result_sha256": first["result_sha256"],
                "left_source_sha256": first["left_source_sha256"], "right_source_sha256": first["right_source_sha256"],
                "decision_hash": first["decision_hash"], "binding_hash": first["binding_hash"],
                "artifacts": self._selection_artifacts(db, pair_id)}

    def get_selection_artifact(self, owner: str, pair_id: str, version: int, kind: str) -> tuple[dict[str, Any], Path]:
        aliases = {"final": "selected_final", "redline": "selected_redline", "report": "selection_report_markdown",
                   "report_json": "selection_report_json"}
        kind = aliases.get(kind, kind)
        if kind not in {"selected_final", "selected_redline", "selection_report_json", "selection_report_markdown"}:
            raise NotFound("selection artifact not found")
        with self._connect() as db:
            row = self._selection_row(db, owner, pair_id)
            artifact = db.execute("SELECT * FROM compare_selection_artifacts WHERE pair_id=? AND version=? AND kind=?",
                                  (pair_id, version, kind)).fetchone()
            if artifact is None:
                raise NotFound("selection artifact not found")
            path = self.store.object_path(artifact["object_key"])
            if (not path.is_file() or path.stat().st_size != artifact["size"]
                    or sha256_file(path) != artifact["sha256"]):
                raise Conflict("SELECTION_ARTIFACT_INTEGRITY_FAILED")
            return dict(artifact), path

    def source_integrity(self, pair_id: str) -> None:
        """Verify both pair objects before a worker or view consumes them."""
        for file in self.pair_inputs(pair_id):
            path = self.store.object_path(file["object_key"])
            if (not path.is_file() or path.stat().st_size != file["size"]
                    or sha256_file(path) != file["source_sha256"]):
                raise Conflict("COMPARE_INPUT_INTEGRITY_FAILED")

    def pair_inputs(self, pair_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM compare_pair_files WHERE pair_id=? ORDER BY side", (pair_id,)).fetchall()
            if len(rows) != 2:
                raise NotFound("compare pair inputs not found")
            return tuple(dict(r) for r in rows)  # type: ignore[return-value]

    def claim(self, *, lease_seconds: int = 300, max_attempts: int = 3) -> dict[str, Any] | None:
        if lease_seconds <= 0 or max_attempts <= 0:
            raise ValueError("invalid worker lease policy")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expired_sql = """SELECT * FROM compare_pairs WHERE status IN ('leased','running')
                AND lease_until<=? AND attempt>=?"""
            if self.store.database.dialect == "mysql":
                # The cleanup decision must observe the latest committed lease
                # state.  A plain snapshot can read an expired row while a
                # concurrent finish/heartbeat is committing a newer state.
                # SKIP LOCKED also prevents two otherwise independent claimers
                # from deadlocking on the same InnoDB gap when there is no
                # expired row to clean up.  The later claim select still uses
                # its own row lock, and the cleanup UPDATE remains fenced.
                expired_sql += " FOR UPDATE SKIP LOCKED"
            expired = db.execute(expired_sql, (now, max_attempts)).fetchall()
            for pair in expired:
                changed = db.execute("""UPDATE compare_pairs SET status='failed',error_code='COMPARE_PROCESSING_FAILED',
                    lease_until=NULL,updated_at=?
                    WHERE id=? AND fencing_token=? AND status IN ('leased','running')
                    AND lease_until<=? AND attempt>=?""",
                                     (now, pair["id"], pair["fencing_token"], now, max_attempts)).rowcount
                if changed == 1:
                    self._refresh_task(db, pair["task_id"], now)
            sql = """SELECT p.*,t.owner FROM compare_pairs p JOIN compare_tasks t ON t.id=p.task_id
                WHERE t.sealed=1 AND t.status IN ('queued','running') AND
                (p.status='queued' OR (p.status='retry_wait' AND p.lease_until<=?) OR
                 (p.status IN ('leased','running') AND p.lease_until<=?))
                ORDER BY t.updated_at,p.ordinal LIMIT 1"""
            if self.store.database.dialect == "mysql":
                # A concurrent claimer may already hold the candidate row
                # lock.  Skip it and return no job instead of deadlocking;
                # fencing_token still makes every successful claim exclusive.
                sql += " FOR UPDATE SKIP LOCKED"
            row = db.execute(sql, (now, now)).fetchone()
            if not row:
                return None
            token, attempt = row["fencing_token"] + 1, row["attempt"] + 1
            db.execute("UPDATE compare_pairs SET status='leased',attempt=?,fencing_token=?,lease_until=?,updated_at=? WHERE id=?",
                       (attempt, token, now + lease_seconds, now, row["id"]))
            db.execute("UPDATE compare_tasks SET status='running',updated_at=? WHERE id=?", (now, row["task_id"]))
            result = dict(row)
            result.update(attempt=attempt, fencing_token=token)
            return result

    def heartbeat(self, pair_id: str, token: int, *, lease_seconds: int = 300) -> None:
        now = _now()
        with self._connect() as db:
            changed = db.execute("""UPDATE compare_pairs SET status='running',lease_until=?,updated_at=?
                WHERE id=? AND fencing_token=? AND status IN ('leased','running') AND lease_until>?""",
                                 (now + lease_seconds, now, pair_id, token, now)).rowcount
            if not changed:
                raise Conflict("stale compare worker lease")

    def finish(self, pair_id: str, token: int, result: dict[str, Any], *, failed: bool = False,
               error_code: str | None = None) -> None:
        if not isinstance(result, dict):
            raise ValueError("COMPARE_RESULT_INVALID")
        if not failed:
            summary = result.get("summary")
            if (result.get("schema_version") != "contract-compare-v1"
                    or not isinstance(summary, dict)
                    or not all(type(summary.get(k)) is int and summary.get(k) >= 0
                               for k in ("total", "modify", "insert", "delete"))
                    or not isinstance(result.get("diffs"), list)
                    or not isinstance(result.get("coverage"), dict)):
                raise ValueError("COMPARE_RESULT_INVALID")
            diffs = result["diffs"]
            if any(not isinstance(diff, dict) for diff in diffs):
                raise ValueError("COMPARE_RESULT_INVALID")
            if summary["total"] != len(diffs) or any(summary[k] != sum(d.get("type") == k for d in diffs)
                                                       for k in ("modify", "insert", "delete")):
                raise ValueError("COMPARE_RESULT_INVALID")
            if result["coverage"].get("status") not in {"complete", "incomplete"}:
                raise ValueError("COMPARE_RESULT_INVALID")
            files = {item["side"]: item for item in self.pair_inputs(pair_id)}
            # Parse the immutable inputs at the storage boundary and validate
            # every persisted span against its block text.  A malformed worker
            # result must fail closed instead of rendering as an unmarked diff.
            from .parser import parse_compare_document
            documents = {}
            for side in ("left", "right"):
                if (not isinstance(result.get(side), dict)
                        or result[side].get("sha256") != files[side]["source_sha256"]):
                    raise ValueError("COMPARE_RESULT_INVALID")
                path = self.store.object_path(files[side]["object_key"] or "")
                if (not path.is_file() or path.stat().st_size != files[side]["size"]
                        or sha256_file(path) != files[side]["source_sha256"]):
                    raise ValueError("COMPARE_INPUT_INTEGRITY_FAILED")
                try:
                    documents[side] = parse_compare_document(path, filename=files[side]["filename"], side="L" if side == "left" else "R")
                except (OSError, DocxError):
                    raise
                except Exception as exc:
                    raise ValueError("COMPARE_RESULT_INVALID") from exc
            block_map = {side: {block.block_id: block for block in doc.blocks}
                         for side, doc in documents.items()}

            def validate_span(value, side: str, *, anchor: bool = False) -> None:
                if not isinstance(value, dict) or not isinstance(value.get("block_id"), str):
                    raise ValueError("COMPARE_RESULT_INVALID")
                if (type(value.get("start")) is not int
                        or type(value.get("end")) is not int
                        or value["start"] < 0 or value["end"] < value["start"]
                        or not isinstance(value.get("text"), str)):
                    raise ValueError("COMPARE_RESULT_INVALID")
                if anchor:
                    if value["start"] != value["end"] or value["text"]:
                        raise ValueError("COMPARE_RESULT_INVALID")
                elif value["end"] <= value["start"]:
                    raise ValueError("COMPARE_RESULT_INVALID")
                block = block_map[side].get(value["block_id"])
                if block is None:
                    virtual = f"{'L' if side == 'left' else 'R'}-virtual"
                    if not (anchor and not block_map[side] and value["block_id"] == virtual
                            and value["start"] == value["end"] == 0):
                        raise ValueError("COMPARE_RESULT_INVALID")
                elif value["end"] > len(block.raw_text):
                    raise ValueError("COMPARE_RESULT_INVALID")
                elif not anchor and value["text"] != block.raw_text[value["start"]:value["end"]]:
                    raise ValueError("COMPARE_RESULT_INVALID")

            def side_spans(diff: dict[str, Any], side: str) -> list[dict[str, Any]]:
                plural = diff.get(f"{side}_spans")
                primary = diff.get(side)
                if plural is not None and not isinstance(plural, list):
                    raise ValueError("COMPARE_RESULT_INVALID")
                spans = plural if plural is not None else ([primary] if primary is not None else [])
                if primary is not None and (not spans or spans[0] != primary):
                    raise ValueError("COMPARE_RESULT_INVALID")
                for span in spans:
                    validate_span(span, side)
                previous: tuple[str, int] | None = None
                for span in spans:
                    key = (span["block_id"], span["start"])
                    if previous is not None and key < previous:
                        raise ValueError("COMPARE_RESULT_INVALID")
                    previous = (span["block_id"], span["end"])
                return spans

            seen_ids = set()
            for diff in diffs:
                if (not isinstance(diff, dict) or diff.get("type") not in {"modify", "insert", "delete"}
                        or not isinstance(diff.get("id"), str) or not diff["id"].strip()
                        or diff["id"] in seen_ids):
                    raise ValueError("COMPARE_RESULT_INVALID")
                seen_ids.add(diff["id"])
                left_spans = side_spans(diff, "left")
                right_spans = side_spans(diff, "right")
                left_anchor = diff.get("left_anchor")
                right_anchor = diff.get("right_anchor")
                if left_anchor is not None:
                    validate_span(left_anchor, "left", anchor=True)
                if right_anchor is not None:
                    validate_span(right_anchor, "right", anchor=True)
                if diff["type"] == "modify":
                    if not left_spans or not right_spans or left_anchor is not None or right_anchor is not None:
                        raise ValueError("COMPARE_RESULT_INVALID")
                elif diff["type"] == "delete":
                    if not left_spans or right_spans or left_anchor is not None or right_anchor is None:
                        raise ValueError("COMPARE_RESULT_INVALID")
                elif not right_spans or left_spans or left_anchor is None or right_anchor is not None:
                    raise ValueError("COMPARE_RESULT_INVALID")

            # Run the same complete projection used by the view endpoint before
            # publishing a successful result.  This catches cross-diff overlap
            # and ensures every accepted diff has a visible mark or anchor.
            from .render import render_compare_document
            for side, document in documents.items():
                rendered = render_compare_document(document, diffs,
                                                   side=side)
                expected = {diff["id"] for diff in diffs}
                if any(f'data-diff-id="{html_escape(diff_id, quote=True)}"' not in rendered
                       for diff_id in expected):
                    raise ValueError("COMPARE_RESULT_INVALID")
        encoded = _json(result)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        now = _now()
        target = None
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                select_sql = "SELECT * FROM compare_pairs WHERE id=?"
                if self.store.database.dialect == "mysql":
                    # Keep the token/status check and the terminal write in one
                    # row lock.  SQLite serializes BEGIN IMMEDIATE, while MySQL
                    # otherwise permits a stale worker's snapshot to overwrite a
                    # newer fencing token after the newer worker commits.
                    select_sql += " FOR UPDATE"
                row = db.execute(select_sql, (pair_id,)).fetchone()
                if not row or row["fencing_token"] != token or row["status"] not in {"leased", "running"}:
                    raise Conflict("stale compare worker lease")
                if row["lease_until"] is None or row["lease_until"] < now:
                    raise Conflict("expired compare worker lease")
                if failed:
                    status, result_sha = "failed", None
                else:
                    status = "incomplete" if result.get("coverage", {}).get("status") == "incomplete" else "succeeded"
                    result_sha = digest
                    key = f"compare/results/{pair_id}/{token}/{uuid.uuid4().hex}.json"
                    target = self.store.object_path(key)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open("xb") as stream:
                        stream.write(encoded.encode("utf-8"))
                        stream.flush()
                        os.fsync(stream.fileno())
                    size = target.stat().st_size
                    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
                        raise Conflict("compare result integrity failed")
                    db.execute("INSERT OR REPLACE INTO compare_artifacts VALUES(?,?,?,?,?)",
                               (pair_id, "result_json", key, digest, size))
                # The predicate is a second fencing barrier for backends where a
                # lock is unavailable or a transaction was interrupted.  Never
                # let a stale worker claim that it finished successfully.
                changed = db.execute("""UPDATE compare_pairs SET status=?,error_code=?,result_json=?,result_sha256=?,lease_until=NULL,updated_at=?
                    WHERE id=? AND fencing_token=? AND status IN ('leased','running') AND lease_until>?""",
                                     (status, error_code, encoded if not failed else _json(result), result_sha,
                                      now, pair_id, token, now)).rowcount
                if changed != 1:
                    raise Conflict("stale compare worker lease")
                task_id = row["task_id"]
                self._refresh_task(db, task_id, now)
        except Exception:
            # A stale result must not leave an orphaned result object behind.
            if target is not None:
                target.unlink(missing_ok=True)
            raise

    @staticmethod
    def _refresh_task(db, task_id: str, now: float) -> None:
        counts = db.execute("SELECT status,COUNT(*) c FROM compare_pairs WHERE task_id=? GROUP BY status", (task_id,)).fetchall()
        pending = sum(r["c"] for r in counts if r["status"] not in {"succeeded", "failed", "incomplete"})
        db.execute("UPDATE compare_tasks SET status=?,updated_at=? WHERE id=?", ("completed" if pending == 0 else "running", now, task_id))

    def retry(self, pair_id: str, token: int, error_code: str, *, max_attempts: int = 3) -> None:
        if max_attempts <= 0:
            raise ValueError("invalid worker retry policy")
        now = _now()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            select_sql = "SELECT * FROM compare_pairs WHERE id=?"
            if self.store.database.dialect == "mysql":
                select_sql += " FOR UPDATE"
            row = db.execute(select_sql, (pair_id,)).fetchone()
            if not row or row["fencing_token"] != token or row["status"] not in {"leased", "running"}:
                raise Conflict("stale compare worker lease")
            if row["lease_until"] is None or row["lease_until"] < now:
                raise Conflict("expired compare worker lease")
            if row["attempt"] >= max_attempts:
                changed = db.execute("""UPDATE compare_pairs SET status='failed',error_code=?,lease_until=NULL,updated_at=?
                    WHERE id=? AND fencing_token=? AND status IN ('leased','running') AND lease_until>?""",
                                     (error_code, now, pair_id, token, now)).rowcount
                if changed != 1:
                    raise Conflict("stale compare worker lease")
                self._refresh_task(db, row["task_id"], now)
            else:
                changed = db.execute("""UPDATE compare_pairs SET status='retry_wait',error_code=?,lease_until=?,updated_at=?
                    WHERE id=? AND fencing_token=? AND status IN ('leased','running') AND lease_until>?""",
                                     (error_code, now + min(2 ** row["attempt"], 60), now, pair_id, token, now)).rowcount
                if changed != 1:
                    raise Conflict("stale compare worker lease")
