"""SQLite/MySQL-compatible persistence for external channels.

The store deliberately contains no Feishu SDK calls. Business state is durable
before an outbound notification is attempted, and all lookups are owner scoped.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from pathlib import Path
from typing import Any


class IntegrationConflict(Exception):
    pass


class IntegrationNotFound(Exception):
    pass


class IntegrationStore:
    def __init__(self, store):
        self.store = store
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS external_identities (
                    provider TEXT NOT NULL, tenant_key TEXT NOT NULL, subject_id TEXT NOT NULL,
                    user_id TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    revoked_at REAL, PRIMARY KEY(provider, tenant_key, subject_id),
                    UNIQUE(provider, tenant_key, user_id)
                );
                CREATE TABLE IF NOT EXISTS integration_binding_codes (
                    code_hash TEXT PRIMARY KEY, provider TEXT NOT NULL, user_id TEXT NOT NULL,
                    expires_at REAL NOT NULL, consumed_at REAL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS integration_events (
                    provider TEXT NOT NULL, event_id TEXT NOT NULL, event_type TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    received_at REAL NOT NULL, processed_at REAL, error_code TEXT,
                    PRIMARY KEY(provider, event_id)
                );
                CREATE TABLE IF NOT EXISTS feishu_drafts (
                    id TEXT PRIMARY KEY, tenant_key TEXT NOT NULL, open_id TEXT NOT NULL,
                    chat_id TEXT NOT NULL, owner_user_id TEXT NOT NULL, name TEXT NOT NULL,
                    status TEXT NOT NULL, card_message_id TEXT, task_id TEXT,
                    submit_idempotency_key TEXT NOT NULL UNIQUE, created_at REAL NOT NULL,
                    updated_at REAL NOT NULL, expires_at REAL NOT NULL, version INTEGER NOT NULL DEFAULT 0,
                    last_error_code TEXT
                );
                CREATE TABLE IF NOT EXISTS feishu_draft_files (
                    id TEXT PRIMARY KEY, draft_id TEXT NOT NULL, message_id TEXT NOT NULL,
                    file_key TEXT NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL,
                    sha256 TEXT NOT NULL, storage_key TEXT NOT NULL, status TEXT NOT NULL,
                    error_code TEXT, created_at REAL NOT NULL,
                    UNIQUE(draft_id, message_id, file_key)
                );
                 CREATE TABLE IF NOT EXISTS task_channels (
                     provider TEXT NOT NULL, task_id TEXT NOT NULL, tenant_key TEXT NOT NULL,
                     open_id TEXT NOT NULL, owner_user_id TEXT NOT NULL DEFAULT '', chat_id TEXT NOT NULL, card_message_id TEXT,
                    last_task_status TEXT, last_completed INTEGER NOT NULL DEFAULT 0,
                    last_failed INTEGER NOT NULL DEFAULT 0, last_delivery_state TEXT,
                    last_state_fingerprint TEXT, last_synced_at REAL, created_at REAL NOT NULL,
                    PRIMARY KEY(provider, task_id)
                 );
                 CREATE TABLE IF NOT EXISTS integration_outbox (
                     id TEXT PRIMARY KEY, provider TEXT NOT NULL, event_type TEXT NOT NULL,
                     aggregate_id TEXT NOT NULL, dedupe_key TEXT NOT NULL UNIQUE, payload_json MEDIUMTEXT NOT NULL,
                     status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at REAL NOT NULL,
                     created_at REAL NOT NULL, sent_at REAL, last_error_code TEXT,
                     lease_until REAL, fencing_token INTEGER NOT NULL DEFAULT 0
                 );
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(task_channels)")}
            if "owner_user_id" not in columns:
                db.execute("ALTER TABLE task_channels ADD COLUMN owner_user_id TEXT NOT NULL DEFAULT ''")
            outbox_columns = {row["name"] for row in db.execute("PRAGMA table_info(integration_outbox)")}
            if "lease_until" not in outbox_columns:
                db.execute("ALTER TABLE integration_outbox ADD COLUMN lease_until REAL")
            if "fencing_token" not in outbox_columns:
                db.execute("ALTER TABLE integration_outbox ADD COLUMN fencing_token INTEGER NOT NULL DEFAULT 0")

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    def create_binding_code(self, provider: str, user_id: str, ttl_seconds: int = 600) -> dict[str, Any]:
        code = secrets.token_urlsafe(12).replace("-", "A").replace("_", "B")[:12].upper()
        now = time.time()
        with self.store._connect() as db:
            db.execute("DELETE FROM integration_binding_codes WHERE user_id=? AND provider=? AND consumed_at IS NULL", (user_id, provider))
            db.execute("INSERT INTO integration_binding_codes(code_hash,provider,user_id,expires_at,created_at) VALUES(?,?,?,?,?)",
                       (self._hash(code), provider, user_id, now + ttl_seconds, now))
        return {"code": code, "expires_at": now + ttl_seconds}

    def consume_binding_code(self, provider: str, tenant_key: str, subject_id: str, code: str) -> str:
        now = time.time()
        digest = self._hash(code.strip().upper())
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM integration_binding_codes WHERE code_hash=? AND provider=?", (digest, provider)).fetchone()
            if row is None:
                raise IntegrationConflict("FEISHU_BINDING_CODE_INVALID")
            if row["consumed_at"] is not None:
                raise IntegrationConflict("FEISHU_BINDING_CODE_CONSUMED")
            if float(row["expires_at"]) < now:
                raise IntegrationConflict("FEISHU_BINDING_CODE_EXPIRED")
            existing_subject = db.execute("SELECT * FROM external_identities WHERE provider=? AND tenant_key=? AND subject_id=?",
                                          (provider, tenant_key, subject_id)).fetchone()
            if existing_subject and existing_subject["revoked_at"] is None and existing_subject["user_id"] != row["user_id"]:
                raise IntegrationConflict("FEISHU_IDENTITY_ALREADY_BOUND")
            existing_user = db.execute("SELECT * FROM external_identities WHERE provider=? AND tenant_key=? AND user_id=?",
                                       (provider, tenant_key, row["user_id"])).fetchone()
            if existing_user and existing_user["revoked_at"] is None and existing_user["subject_id"] != subject_id:
                raise IntegrationConflict("FEISHU_USER_ALREADY_BOUND")
            if (existing_subject is not None and existing_subject["revoked_at"] is not None
                    and existing_user is not None and existing_user["revoked_at"] is not None
                    and existing_subject["user_id"] != row["user_id"]
                    and existing_user["subject_id"] != subject_id):
                # Both historical rows already occupy the composite unique
                # keys. Do not delete audit history merely to permit a subject
                # swap; ask the account owner to bind with a fresh subject.
                raise IntegrationConflict("FEISHU_REBIND_CONFLICT")
            db.execute("UPDATE integration_binding_codes SET consumed_at=? WHERE code_hash=? AND consumed_at IS NULL", (now, digest))
            if existing_subject is not None and existing_subject["user_id"] == row["user_id"]:
                db.execute("UPDATE external_identities SET revoked_at=NULL,updated_at=? WHERE provider=? AND tenant_key=? AND subject_id=?",
                           (now, provider, tenant_key, subject_id))
            elif existing_user is not None and existing_user["revoked_at"] is not None and existing_subject is None:
                db.execute("UPDATE external_identities SET subject_id=?,revoked_at=NULL,updated_at=? WHERE provider=? AND tenant_key=? AND user_id=?",
                           (subject_id, now, provider, tenant_key, row["user_id"]))
            elif existing_subject is not None and existing_subject["revoked_at"] is not None:
                db.execute("UPDATE external_identities SET user_id=?,revoked_at=NULL,updated_at=? WHERE provider=? AND tenant_key=? AND subject_id=?",
                           (row["user_id"], now, provider, tenant_key, subject_id))
            elif existing_subject is None:
                try:
                    db.execute("INSERT INTO external_identities(provider,tenant_key,subject_id,user_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                               (provider, tenant_key, subject_id, row["user_id"], now, now))
                except Exception as exc:
                    raise IntegrationConflict("FEISHU_IDENTITY_ALREADY_BOUND") from exc
            return row["user_id"]

    def identity(self, provider: str, tenant_key: str, subject_id: str) -> dict[str, Any] | None:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM external_identities WHERE provider=? AND tenant_key=? AND subject_id=? AND revoked_at IS NULL",
                             (provider, tenant_key, subject_id)).fetchone()
        return dict(row) if row else None

    def binding_for_user(self, provider: str, user_id: str) -> dict[str, Any] | None:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM external_identities WHERE provider=? AND user_id=? AND revoked_at IS NULL",
                             (provider, user_id)).fetchone()
        return dict(row) if row else None

    def revoke_user_binding(self, provider: str, user_id: str) -> None:
        with self.store._connect() as db:
            db.execute("UPDATE external_identities SET revoked_at=?,updated_at=? WHERE provider=? AND user_id=? AND revoked_at IS NULL",
                       (time.time(), time.time(), provider, user_id))

    def record_event(self, provider: str, event_id: str, event_type: str, payload: dict[str, Any]) -> bool:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode()).hexdigest()
        now = time.time()
        with self.store._connect() as db:
            existing = db.execute("SELECT event_type,payload_sha256 FROM integration_events WHERE provider=? AND event_id=?",
                                  (provider, event_id)).fetchone()
            if existing is not None:
                if existing["event_type"] != event_type or existing["payload_sha256"] != digest:
                    raise IntegrationConflict("INTEGRATION_EVENT_PAYLOAD_CONFLICT")
                return False
            try:
                db.execute("INSERT INTO integration_events(provider,event_id,event_type,payload_sha256,status,received_at) VALUES(?,?,?,?,?,?)",
                           (provider, event_id, event_type, digest, "received", now))
            except Exception:
                # A concurrent insert is a normal duplicate delivery. Re-read it
                # so an event-id collision with a different payload is never
                # silently accepted.
                existing = db.execute("SELECT event_type,payload_sha256 FROM integration_events WHERE provider=? AND event_id=?",
                                      (provider, event_id)).fetchone()
                if existing is not None and (existing["event_type"] != event_type or existing["payload_sha256"] != digest):
                    raise IntegrationConflict("INTEGRATION_EVENT_PAYLOAD_CONFLICT")
                if existing is not None:
                    return False
                raise
        return True

    def mark_event(self, provider: str, event_id: str, status: str, error_code: str | None = None) -> None:
        with self.store._connect() as db:
            db.execute("UPDATE integration_events SET status=?,processed_at=?,attempts=attempts+1,error_code=? WHERE provider=? AND event_id=?",
                       (status, time.time(), error_code, provider, event_id))

    def active_draft(self, tenant_key: str, open_id: str, chat_id: str) -> dict[str, Any] | None:
        now = time.time()
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM feishu_drafts WHERE tenant_key=? AND open_id=? AND chat_id=? AND status IN ('COLLECTING','CONFIRMING') AND expires_at>? ORDER BY created_at DESC LIMIT 1",
                             (tenant_key, open_id, chat_id, now)).fetchone()
        return dict(row) if row else None

    def create_draft(self, tenant_key: str, open_id: str, chat_id: str, owner_user_id: str, name: str, ttl_seconds: int = 86400) -> dict[str, Any]:
        now = time.time()
        result = (uuid.uuid4().hex, tenant_key, open_id, chat_id, owner_user_id, name, "COLLECTING", "", None,
                  f"feishu:{tenant_key}:{uuid.uuid4().hex}", now, now, now + ttl_seconds, 0, None)
        with self.store._connect() as db:
            db.execute("INSERT INTO feishu_drafts(id,tenant_key,open_id,chat_id,owner_user_id,name,status,card_message_id,task_id,submit_idempotency_key,created_at,updated_at,expires_at,version,last_error_code) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", result)
            row = db.execute("SELECT * FROM feishu_drafts WHERE id=?", (result[0],)).fetchone()
        return dict(row)

    def draft_files(self, draft_id: str) -> list[dict[str, Any]]:
        with self.store._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM feishu_draft_files WHERE draft_id=? ORDER BY created_at", (draft_id,))]

    def add_draft_file(self, draft_id: str, message_id: str, file_key: str, name: str, size: int, sha256: str, storage_key: str, status: str = "accepted", error_code: str | None = None) -> bool:
        try:
            with self.store._connect() as db:
                db.execute("INSERT INTO feishu_draft_files(id,draft_id,message_id,file_key,name,size,sha256,storage_key,status,error_code,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                           (uuid.uuid4().hex, draft_id, message_id, file_key, name, size, sha256, storage_key, status, error_code, time.time()))
            return True
        except Exception:
            return False

    def set_draft(self, draft_id: str, *, status: str | None = None, card_message_id: str | None = None, task_id: str | None = None, error_code: str | None = None) -> None:
        values, updates = [], []
        for key, value in (("status", status), ("card_message_id", card_message_id), ("task_id", task_id), ("last_error_code", error_code)):
            if value is not None:
                updates.append(f"{key}=?"); values.append(value)
        updates.extend(["updated_at=?", "version=version+1"]); values.extend([time.time(), draft_id])
        with self.store._connect() as db:
            db.execute(f"UPDATE feishu_drafts SET {','.join(updates)} WHERE id=?", values)

    def claim_draft_for_submit(self, draft_id: str) -> dict[str, Any] | None:
        """Atomically move one collecting draft into its submit phase."""
        stale_before = time.time() - 120
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM feishu_drafts WHERE id=?", (draft_id,)).fetchone()
            if row is None:
                raise IntegrationNotFound("FEISHU_DRAFT_NOT_FOUND")
            if float(row["expires_at"]) <= time.time():
                return None
            if row["status"] == "CONFIRMING" and float(row["updated_at"]) > stale_before:
                return None
            if row["status"] not in {"COLLECTING", "CONFIRMING"}:
                return None
            db.execute("UPDATE feishu_drafts SET status='CONFIRMING',updated_at=?,version=version+1 WHERE id=? AND status IN ('COLLECTING','CONFIRMING')",
                       (time.time(), draft_id))
            claimed = db.execute("SELECT * FROM feishu_drafts WHERE id=?", (draft_id,)).fetchone()
        return dict(claimed) if claimed else None

    def draft(self, draft_id: str) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM feishu_drafts WHERE id=?", (draft_id,)).fetchone()
        if row is None:
            raise IntegrationNotFound("FEISHU_DRAFT_NOT_FOUND")
        return dict(row)

    def link_task(self, task_id: str, draft: dict[str, Any], card_message_id: str | None) -> None:
        now = time.time()
        with self.store._connect() as db:
            existing = db.execute("SELECT task_id FROM task_channels WHERE provider='feishu' AND task_id=?", (task_id,)).fetchone()
            if existing is None:
                db.execute("INSERT INTO task_channels(provider,task_id,tenant_key,open_id,owner_user_id,chat_id,card_message_id,last_task_status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           ("feishu", task_id, draft["tenant_key"], draft["open_id"], draft["owner_user_id"], draft["chat_id"], card_message_id, "queued", now))
            db.execute("UPDATE feishu_drafts SET status='SUBMITTED',task_id=?,card_message_id=?,last_error_code=NULL,updated_at=?,version=version+1 WHERE id=?",
                       (task_id, card_message_id, now, draft["id"]))

    def channels(self) -> list[dict[str, Any]]:
        with self.store._connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM task_channels WHERE provider='feishu' ORDER BY created_at")]

    def update_channel(self, task_id: str, status: str, completed: int, failed: int, delivery_state: str, fingerprint: str) -> bool:
        with self.store._connect() as db:
            row = db.execute("SELECT last_state_fingerprint FROM task_channels WHERE provider='feishu' AND task_id=?", (task_id,)).fetchone()
            if row is None:
                return False
            if row["last_state_fingerprint"] == fingerprint:
                return False
            db.execute("UPDATE task_channels SET last_task_status=?,last_completed=?,last_failed=?,last_delivery_state=?,last_state_fingerprint=?,last_synced_at=? WHERE provider='feishu' AND task_id=?",
                       (status, completed, failed, delivery_state, fingerprint, time.time(), task_id))
            return True

    def set_channel_card(self, task_id: str, card_message_id: str) -> None:
        with self.store._connect() as db:
            db.execute("UPDATE task_channels SET card_message_id=? WHERE provider='feishu' AND task_id=?", (card_message_id, task_id))

    def add_outbox(self, event_type: str, aggregate_id: str, payload: dict[str, Any], dedupe_key: str) -> bool:
        try:
            with self.store._connect() as db:
                db.execute("INSERT INTO integration_outbox(id,provider,event_type,aggregate_id,dedupe_key,payload_json,status,next_attempt_at,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                           (uuid.uuid4().hex, "feishu", event_type, aggregate_id, dedupe_key, json.dumps(payload, ensure_ascii=False), "pending", time.time(), time.time()))
            return True
        except Exception:
            return False

    def pending_outbox(self, limit: int = 20, lease_seconds: int = 120) -> list[dict[str, Any]]:
        now = time.time()
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            query = "SELECT * FROM integration_outbox WHERE provider='feishu' AND ((status IN ('pending','retry_wait') AND next_attempt_at<=?) OR (status='sending' AND lease_until<=?)) ORDER BY created_at LIMIT ?"
            if getattr(self.store.database, "dialect", "sqlite") == "mysql":
                query += " FOR UPDATE"
            rows = db.execute(query, (now, now, max(1, min(limit, 100)))).fetchall()
            result = []
            for row in rows:
                changed = db.execute("UPDATE integration_outbox SET status='sending',attempts=attempts+1,lease_until=?,fencing_token=fencing_token+1 WHERE id=? AND (status IN ('pending','retry_wait') OR (status='sending' AND lease_until<=?))", (now + lease_seconds, row["id"], now)).rowcount
                if not changed:
                    continue
                updated = db.execute("SELECT * FROM integration_outbox WHERE id=? AND status='sending'", (row["id"],)).fetchone()
                if updated:
                    result.append(dict(updated))
        return result

    def finish_outbox(self, outbox_id: str, *, fencing_token: int | None = None, error_code: str | None = None, retry: bool = False) -> None:
        now = time.time()
        status = "retry_wait" if retry else "dead" if error_code else "sent"
        next_attempt = now + min(300, 2 ** 5) if retry else now
        with self.store._connect() as db:
            where = "id=? AND status='sending'"
            values: list[Any] = [status, None if retry else now, next_attempt, error_code, outbox_id]
            if fencing_token is not None:
                where += " AND fencing_token=?"
                values.append(fencing_token)
            db.execute(f"UPDATE integration_outbox SET status=?,sent_at=?,next_attempt_at=?,last_error_code=?,lease_until=NULL WHERE {where}", values)

    def health(self) -> dict[str, Any]:
        with self.store._connect() as db:
            counts = {status: db.execute("SELECT COUNT(*) FROM integration_events WHERE provider='feishu' AND status=?", (status,)).fetchone()[0]
                      for status in ("received", "processing", "processed", "retry_wait", "dead")}
            outbox = db.execute("SELECT COUNT(*) FROM integration_outbox WHERE provider='feishu' AND status IN ('pending','retry_wait')").fetchone()[0]
            last = db.execute("SELECT MAX(received_at) FROM integration_events WHERE provider='feishu'").fetchone()[0]
        return {"pending_events": counts["received"] + counts["processing"], "retry_events": counts["retry_wait"], "dead_events": counts["dead"], "pending_outbox": outbox, "last_event_at": last}
