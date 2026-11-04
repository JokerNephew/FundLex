"""Persistent business tasks over the existing worker's technical batches.

The immutable manifest is the source of task size. Document publication and
task association share one transaction, so workers cannot see orphan batches.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .edit_summary import (OUTCOME_LABELS, delivery_text, edit_count,
                           outcome_label, summary_detail)
from .recall import ENGINE_ID as RECALL_ENGINE_ID
from .direct_pipeline import ENGINE_ID as DIRECT_ENGINE_ID, ENGINE_VERSION as DIRECT_ENGINE_VERSION
from .store import (Conflict, NotFound, ReportJsonError, RunStore, SCHEMA_VERSION,
                     engine_build, parse_report_json, servable_artifact_kinds)


# One task document is a LEFT JOIN of its manifest row and its published
# document.  The list endpoints select exactly these columns so the rows they
# page over can be turned into the existing response shape without per-row
# queries.
_DOCUMENT_COLUMNS = """f.task_id,f.client_id,f.ordinal,f.name,f.size,f.upload_status,
    f.error_code AS file_error,f.document_id,d.batch_id,d.status,
    d.qualification_status,d.delivery_status,d.error_code AS document_error,
    d.source_sha256,d.report_json,d.updated_at AS document_updated_at,d.execution_mode,
    d.conversion_state"""
_DOCUMENT_FROM = "task_files f LEFT JOIN documents d ON d.id=f.document_id"
_JOB_STATUS = "COALESCE(d.status,'not_started')"
_ELIGIBILITY = "COALESCE(NULLIF(d.qualification_status,''),'pending')"
_DELIVERY_STATUS = "COALESCE(NULLIF(d.delivery_status,''),'not_generated')"
_UPLOAD_STATUS = "COALESCE(NULLIF(f.upload_status,''),'pending')"
# Reason codes are stable ASCII identifiers.  Only such a code can be used as
# a safe `instr(report_json, code)` prefilter; anything else falls back to
# inspecting every row that passed the other filters.
_PLAIN_REASON_CODE = re.compile(r"^[A-Za-z0-9_.:-]{1,96}$")


def _casefold_value(value):
    """SQLite helper so name filters/order match Python ``str.casefold``."""
    return "" if value is None else str(value).casefold()


def _source_field(source, name: str) -> str:
    """Read a rule-source identifier from either a mapping or an object.

    The recall-first engine binds a guide version (a dict); the retired rulesets
    exposed ``version``/``sha256`` attributes. Accepting both keeps the legacy
    offline runners working while the runtime uses the guide binding only.
    """
    if isinstance(source, dict):
        value = source.get(name)
    else:
        value = getattr(source, name, None)
    return str(value or "")


class TaskStore:
    def __init__(self, store: RunStore):
        self.store = store
        with store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, name TEXT NOT NULL,
                    ruleset_version TEXT NOT NULL, ruleset_sha256 TEXT NOT NULL,
                    paused INTEGER NOT NULL DEFAULT 0, pause_reason TEXT,
                    sealed INTEGER NOT NULL DEFAULT 0, idempotency_key TEXT,
                    mode VARCHAR(32) NOT NULL DEFAULT 'delivery',
                    request_hash TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(owner,idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS task_files (
                    task_id TEXT NOT NULL REFERENCES tasks(id), client_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL, name TEXT NOT NULL, size INTEGER NOT NULL,
                    upload_status TEXT NOT NULL DEFAULT 'pending', error_code TEXT,
                    document_id TEXT UNIQUE REFERENCES documents(id),
                    PRIMARY KEY(task_id,client_id), UNIQUE(task_id,ordinal)
                );
                CREATE TABLE IF NOT EXISTS task_batches (
                    task_id TEXT NOT NULL REFERENCES tasks(id),
                    batch_id TEXT PRIMARY KEY REFERENCES batches(id)
                );
            """)
            db.executescript("""
                CREATE TABLE IF NOT EXISTS admin_audit_log (
                    id TEXT PRIMARY KEY,
                    actor TEXT NOT NULL, action TEXT NOT NULL,
                    task_id TEXT NOT NULL DEFAULT '', document_id TEXT NOT NULL DEFAULT '',
                    detail TEXT NOT NULL DEFAULT '', created_at REAL NOT NULL
                );
            """)
            for name, definition in {"engine_id": "TEXT NOT NULL DEFAULT ''",
                                     "guide_version_id": "TEXT NOT NULL DEFAULT ''",
                                     "guide_rules_sha256": "TEXT NOT NULL DEFAULT ''",
                                     "guide_schema_version": "TEXT NOT NULL DEFAULT ''",
                                     "engine_version": "TEXT NOT NULL DEFAULT ''",
                                     "snapshot_json": "MEDIUMTEXT NOT NULL DEFAULT ''",
                                     "mode": "VARCHAR(32) NOT NULL DEFAULT 'delivery'",
                                     "disabled_rule_ids": "TEXT NOT NULL DEFAULT '[]'",
                                     "model_preferences": "MEDIUMTEXT NOT NULL DEFAULT '{}'"}.items():
                if name not in {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}:
                    db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")

    @staticmethod
    def _owned(db, owner, task_id):
        row = db.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
        if row is None:
            raise NotFound("task not found")
        return row

    def create(self, owner, name, source, files, idempotency_key=None,
               engine_id="", guide_version_id="", guide_rules_sha256="", mode="delivery",
               disabled_rule_ids=None, model_preferences=None, model_preferences_factory=None,
               guide_schema_version="", engine_version="", snapshot: dict | None = None):
        """Create a task bound to a rule source.

        ``source`` is the bound guide version for the recall-first engine; the
        retired rulesets provide a ``version``/``sha256`` pair instead. Either
        way the binding is part of the request fingerprint.
        """
        if mode not in {"delivery", "evaluation", "diagnosis"}:
            raise ValueError("TASK_MODE_INVALID")
        disabled = sorted({str(item).strip() for item in (disabled_rule_ids or [])
                           if str(item).strip()})
        source_version = _source_field(source, "version")
        source_sha256 = _source_field(source, "sha256")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if model_preferences_factory is not None:
                model_preferences = model_preferences_factory(db)
            binding = [engine_id, guide_version_id, guide_rules_sha256]
            snapshot_json = json.dumps(snapshot or {}, ensure_ascii=False, sort_keys=True)
            if guide_schema_version or engine_version or snapshot:
                binding += [guide_schema_version, engine_version, snapshot_json]
            if disabled:
                binding.append(disabled)
            if model_preferences:
                binding.append(model_preferences)
            if mode != "delivery":
                binding.append(mode)
            payload = [name, source_version, source_sha256, files]
            if any(binding):
                # Legacy requests keep their previous fingerprint; a bound engine is
                # part of the identity of a new-style task.
                payload.append(binding)
            fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if idempotency_key:
                old = db.execute("SELECT id,request_hash FROM tasks WHERE owner=? AND idempotency_key=?",
                                 (owner, idempotency_key)).fetchone()
                if old:
                    if old["request_hash"] != fingerprint:
                        raise Conflict("TASK_IDEMPOTENCY_CONFLICT")
                    return self._snapshot(db, self._owned(db, owner, old["id"]))
            task_id, now = uuid.uuid4().hex, time.time()
            db.execute("""INSERT INTO tasks(id,owner,name,ruleset_version,ruleset_sha256,engine_id,
                guide_version_id,guide_rules_sha256,guide_schema_version,engine_version,snapshot_json,
                mode,disabled_rule_ids,idempotency_key,request_hash,
                created_at,updated_at,model_preferences)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (task_id, owner, name, source_version, source_sha256, engine_id,
                        guide_version_id, guide_rules_sha256, guide_schema_version, engine_version,
                        snapshot_json, mode,
                        json.dumps(disabled, ensure_ascii=False), idempotency_key, fingerprint, now, now,
                        json.dumps(model_preferences or {}, ensure_ascii=False)))
            db.executemany("INSERT INTO task_files(task_id,client_id,ordinal,name,size) VALUES(?,?,?,?,?)",
                           [(task_id, item["client_id"], i, item["name"], item["size"]) for i, item in enumerate(files)])
            return self._snapshot(db, self._owned(db, owner, task_id))

    @staticmethod
    def _chunks(values, size=400):
        """Bound IN (...) lists so SQLite's variable limit is never reached."""
        for start in range(0, len(values), size):
            yield values[start:start + size]

    @staticmethod
    def _decode_report(raw):
        """Decode one persisted report once; ``(report, error_code)``."""
        try:
            return parse_report_json(raw) or {}, None
        except ReportJsonError as exc:
            return None, exc.code

    @staticmethod
    def _collect_reasons(report, error):
        reasons = {error} if error else set()
        for entry in report.get("unresolved") or []:
            if isinstance(entry, dict):
                code = entry.get("code") or entry.get("reason")
                if isinstance(code, str) and code:
                    reasons.add(code)
        for action in report.get("actions", []):
            if not isinstance(action, dict):
                continue
            if action.get("failure_reason"):
                reasons.add(action["failure_reason"])
            for candidate in action.get("candidates", []):
                if isinstance(candidate, dict) and candidate.get("status") == "failed" and candidate.get("reason"):
                    reasons.add(candidate["reason"])
            # v2 actions expose located targets instead of v1 candidates.
            for target in action.get("targets", []):
                if isinstance(target, dict) and target.get("status") == "failed" and target.get("reason"):
                    reasons.add(target["reason"])
        return sorted(reasons)

    @staticmethod
    def _phase(report) -> str:
        windows = report.get("windows") if isinstance(report, dict) else None
        if not isinstance(windows, list):
            return ""
        for window in reversed(windows):
            if not isinstance(window, dict):
                continue
            rounds = window.get("rounds")
            if not isinstance(rounds, list):
                continue
            for entry in reversed(rounds):
                if not isinstance(entry, dict):
                    continue
                for key in ("stage", "phase"):
                    value = entry.get(key)
                    if isinstance(value, str) and value:
                        return value
        return ""

    @classmethod
    def _reason_view(cls, raw, error):
        """Return ``(reason_codes, phase, report_error)`` with a single parse.

        Callers that page a task reuse this per-file view for both the page
        rows and ``reason_options``, so a report is decoded at most once per
        request.
        """
        report, failure = cls._decode_report(raw)
        if report is None:
            reasons = {error} if error else set()
            reasons.add(failure)
            return sorted(reasons), "", failure
        return cls._collect_reasons(report, error), cls._phase(report), None

    @classmethod
    def _artifact_kinds(cls, db, document_ids):
        """Batch artifact kinds for many documents in bounded chunks."""
        result = {}
        ids = [str(item) for item in dict.fromkeys(document_ids) if item]
        for chunk in cls._chunks(ids):
            marks = ",".join("?" for _ in chunk)
            for row in db.execute(f"SELECT document_id,kind FROM artifacts WHERE document_id IN ({marks}) "
                                  "ORDER BY document_id,kind", chunk):
                result.setdefault(row["document_id"], []).append(row["kind"])
        return result

    def _summary_documents(self, db, task_ids):
        """Summary inputs for a bounded task set with no per-document query."""
        ids = [str(item) for item in dict.fromkeys(task_ids) if item]
        result = {task_id: [] for task_id in ids}
        if not ids:
            return result
        rows = []
        for chunk in self._chunks(ids):
            marks = ",".join("?" for _ in chunk)
            rows.extend(db.execute(f"""SELECT f.task_id,f.upload_status,f.document_id,d.status,
                d.qualification_status,d.delivery_status,d.report_json,
                d.updated_at AS document_updated_at
                FROM {_DOCUMENT_FROM} WHERE f.task_id IN ({marks})
                ORDER BY f.task_id,f.ordinal""", chunk).fetchall())
        artifacts = self._artifact_kinds(db, [row["document_id"] for row in rows if row["document_id"]])
        for row in rows:
            report, failure = self._decode_report(row["report_json"])
            result[row["task_id"]].append({
                "upload_status": row["upload_status"],
                "result_schema": (report.get("report_contract")
                                  if isinstance(report, dict) and report else None),
                "job_status": row["status"] or "not_started",
                "eligibility": row["qualification_status"],
                "delivery_status": row["delivery_status"] or "not_generated",
                "phase": self._phase(report) if report else "",
                "report_error": failure,
                "document_updated_at": row["document_updated_at"] or 0,
                "artifact_count": len(artifacts.get(row["document_id"], ())),
            })
        return result

    def _fold(self, db, column):
        """Unicode casefold expression for name filters and ordering.

        SQLite has no Unicode ``lower()``; registering the Python casefold keeps
        the SQL filters byte-for-byte compatible with the previous in-memory
        implementation.  MySQL uses its Unicode-aware ``LOWER``.
        """
        if self.store.database.dialect == "sqlite":
            create = getattr(getattr(db, "_raw", None), "create_function", None)
            if callable(create):
                create("fundlex_casefold", 1, _casefold_value)
                return f"fundlex_casefold({column})"
        return f"LOWER({column})"

    @staticmethod
    def _document_filters(name_fold, filters):
        """SQL predicates shared by the page, count and reason candidate query."""
        clauses, params = [], []
        q = filters.get("q") or ""
        if q:
            # ``instr`` matches the Python substring test literally; LIKE would
            # treat ``%``/``_`` in the search box as wildcards.
            clauses.append(f"instr({name_fold}, ?) > 0")
            params.append(q.casefold())
        for key, expression in (("eligibility", _ELIGIBILITY),
                                ("delivery_status", _DELIVERY_STATUS),
                                ("upload_status", _UPLOAD_STATUS)):
            value = filters.get(key)
            if value:
                clauses.append(f"{expression} = ?")
                params.append(value)
        job = filters.get("job_status")
        if job == "running":
            clauses.append(f"{_JOB_STATUS} IN ('leased','running')")
        elif job:
            clauses.append(f"{_JOB_STATUS} = ?")
            params.append(job)
        return clauses, params

    @staticmethod
    def _document_order(name_fold, sort):
        """Mirror ``_page`` document ordering in SQL, including ordinal ties."""
        if sort == "exceptions":
            return (f"CASE WHEN {_JOB_STATUS}='failed' THEN 0 "
                    f"WHEN f.upload_status='rejected' THEN 1 "
                    f"WHEN {_DELIVERY_STATUS}='incomplete' THEN 2 "
                    f"WHEN {_DELIVERY_STATUS}='complete_with_exceptions' THEN 3 "
                    "WHEN substr(COALESCE(d.qualification_status,''),1,8) = 'excluded' THEN 4 "
                    "ELSE 5 END, f.ordinal")
        if sort == "status":
            return (f"CASE {_JOB_STATUS} WHEN 'not_started' THEN 0 WHEN 'queued' THEN 1 "
                    "WHEN 'retry_wait' THEN 2 WHEN 'leased' THEN 3 WHEN 'running' THEN 3 "
                    "WHEN 'failed' THEN 4 WHEN 'succeeded' THEN 5 ELSE 6 END, f.ordinal")
        if sort == "name":
            return f"{name_fold}, f.ordinal"
        if sort == "name_desc":
            return f"{name_fold} DESC, f.ordinal"
        if sort == "newest":
            return "f.ordinal DESC"
        return "f.ordinal"

    @staticmethod
    def _error_code_filter(error_code):
        """Safe SQL superset for a reason code that lives inside report JSON.

        A reason can come from the document/task-file error code or from the
        persisted report.  The report part is prefiltered with ``instr`` so the
        exact (unchanged) Python check only inspects plausible rows.  When no
        safe superset exists the caller keeps every row that passed the other
        filters and filters exactly in Python.
        """
        if not error_code or not _PLAIN_REASON_CODE.match(error_code):
            return None, []
        clause = ("(instr(COALESCE(d.report_json,''), ?) > 0 "
                  "OR COALESCE(d.error_code, f.error_code) = ?")
        if error_code == "REPORT_JSON_INVALID":
            # Corrupt JSON cannot contain its own stable error code.
            clause += " OR (d.report_json IS NOT NULL AND d.report_json <> '')"
        clause += ")"
        return clause, [error_code, error_code]

    @staticmethod
    def _direct_row_extras(raw_report_json):
        """裁决 D2：直通报告行追加 result_schema/edit_count（旧报告绝不带）。"""
        if not raw_report_json or "direct_edit_v1" not in raw_report_json[:400]:
            return {}
        report, _ = TaskStore._decode_report(raw_report_json)
        if not report or report.get("report_contract") != "direct_edit_v1":
            return {}
        from .direct_report import written_count
        block = report.get("direct_edit") if isinstance(report.get("direct_edit"), dict) else {}
        return {"result_schema": "direct_edit_v1", "edit_count": written_count(report),
                "revision_tier": str(block.get("revision_tier") or "strict_dual_layer")}

    @staticmethod
    def _document_from_row(row, task_id, artifacts, view):
        document_id = row["document_id"]
        reasons, phase, report_error = view
        extras = TaskStore._direct_row_extras(row["report_json"] if document_id else None)
        kinds = artifacts.get(document_id, ()) if document_id else ()
        return {
            "task_id": task_id,
            "batch_id": row["batch_id"],
            "document_id": document_id,
            "client_id": row["client_id"],
            "name": row["name"],
            "size": row["size"],
            "job_status": row["status"] or "not_started",
            "upload_status": row["upload_status"],
            "eligibility": row["qualification_status"],
            "delivery_status": row["delivery_status"] or "not_generated",
            "execution_mode": (row["execution_mode"] or "") if document_id else "",
            "error_code": row["document_error"] or row["file_error"],
            "conversion_state": (row["conversion_state"] or "") if document_id else "",
            "report_url": (f"/api/tasks/{task_id}/documents/{document_id}/report"
                           if document_id and row["report_json"] else None),
            "downloads": ({kind: f"/api/tasks/{task_id}/documents/{document_id}/download/{kind}"
                           for kind in servable_artifact_kinds(kinds, row["execution_mode"])}
                          if document_id else {}),
            "source_sha256": row["source_sha256"],
            "phase": phase,
            "report_error": report_error,
            "document_updated_at": row["document_updated_at"] or 0,
            "artifact_count": len(kinds),
            "reason_codes": reasons,
            "ordinal": row["ordinal"],
        } | extras

    def _task_views(self, db, task_id):
        """One pass over a task's files for reason codes, phases and options."""
        rows = db.execute(f"""SELECT f.client_id,f.error_code AS file_error,
            d.error_code AS document_error,d.report_json
            FROM {_DOCUMENT_FROM} WHERE f.task_id=?""", (task_id,)).fetchall()
        views, counts = {}, Counter()
        for row in rows:
            view = self._reason_view(row["report_json"], row["document_error"] or row["file_error"])
            views[row["client_id"]] = view
            counts.update(view[0])
        return views, counts

    @classmethod
    def _reasons(cls, raw, error):
        return cls._reason_view(raw, error)[0]

    @classmethod
    def _report_error(cls, raw):
        return cls._decode_report(raw)[1]

    @classmethod
    def _report_phase(cls, raw) -> str:
        """Read the latest persisted Worker phase for task aggregation."""
        report, _ = cls._decode_report(raw)
        return cls._phase(report) if report else ""

    @staticmethod
    def _task_status(total, uploaded, completed, processing, failed, paused):
        """Derived task state; the SQL aggregate in ``_task_base_sql`` mirrors it."""
        terminal = uploaded == total and completed == total
        if terminal and failed == completed and completed:
            return "failed"
        if terminal and failed:
            return "completed_with_exceptions"
        if terminal:
            return "completed"
        if paused:
            return "paused"
        if processing:
            return "running"
        return "queued" if uploaded > completed else "uploading"

    @classmethod
    def _status_matches(cls, status, state):
        """API status filter contract, including the historical failed alias."""
        return (not state or state == status
                or (state == "failed" and status == "completed_with_exceptions"))

    @staticmethod
    def _summary(row, docs, *, legacy=False):
        total = len(docs)
        uploaded = sum(d["upload_status"] == "accepted" for d in docs)
        completed = sum(d["job_status"] in {"succeeded", "failed"} for d in docs)
        processing = sum(d["job_status"] in {"leased", "running"} for d in docs)
        failed = sum(d["job_status"] == "failed" for d in docs)
        exceptions = sum(d["upload_status"] == "rejected" or d["job_status"] == "failed" or
                         (d["job_status"] == "succeeded" and d["eligibility"] != "excluded_by_fund_type"
                          and d["delivery_status"] in {"incomplete", "not_generated"}) for d in docs)
        terminal = uploaded == total and completed == total
        status = TaskStore._task_status(total, uploaded, completed, processing, failed, bool(row["paused"]))
        # A task is legacy once it was produced by a retired engine. The runtime
        # serves the guide-bound engine only, so anything else is read-only
        # history even when it still has a first-class task row.
                # A task is legacy once it was produced by a retired engine (the
        # direct-through engine included for reference is never legacy).
        legacy = legacy or (row["engine_id"] or "") != DIRECT_ENGINE_ID
        phase = "交付" if terminal else max(
            (doc for doc in docs if doc.get("phase")),
            key=lambda doc: doc.get("document_updated_at", 0),
            default={},
        ).get("phase", "")
        result_schema = next((doc["result_schema"] for doc in docs
                              if doc.get("result_schema")), None)
        try:
            disabled_rule_ids = json.loads(row["disabled_rule_ids"] or "[]")
        except (TypeError, ValueError):
            disabled_rule_ids = []
        if not isinstance(disabled_rule_ids, list):
            disabled_rule_ids = []
        return {"id": row["id"], "name": row["name"], "legacy": legacy, "ruleset_version": row["ruleset_version"],
                "ruleset_sha256": row["ruleset_sha256"], "status": status,
                "engine_id": row["engine_id"], "mode": row["mode"] or "delivery",
                "result_schema": result_schema,
                "disabled_rule_ids": disabled_rule_ids,
                "model_preferences": json.loads(row["model_preferences"] or "{}")
                    if "model_preferences" in row.keys() else {},
                "guide_snapshot": {"version_id": row["guide_version_id"],
                                   "rules_sha256": row["guide_rules_sha256"],
                                   "schema_version": (row["guide_schema_version"] or "")
                                   if "guide_schema_version" in row.keys() else "",
                                   "engine_version": (row["engine_version"] or "")
                                   if "engine_version" in row.keys() else ""},
                "upload_status": "complete" if uploaded == total else "sealed_incomplete" if row["sealed"] else "partial" if uploaded else "pending",
                "total": total, "uploaded": uploaded, "pending_upload": sum(d["upload_status"] == "pending" for d in docs),
                "rejected": sum(d["upload_status"] == "rejected" for d in docs),
                "queued": sum(d["job_status"] in {"queued", "retry_wait"} for d in docs),
                "processing": processing, "completed": completed, "failed": failed,
                "successful": sum(d["job_status"] == "succeeded" and d["delivery_status"] in
                                  {"complete", "complete_with_exceptions"} for d in docs),
                "exceptions": exceptions,
                "qualification_counts": dict(Counter(d["eligibility"] or "pending" for d in docs)),
                "delivery_counts": dict(Counter(d["delivery_status"] for d in docs)),
                "phase": phase,
                "downloadable_count": sum(1 for doc in docs if doc.get("artifact_count", 0) > 0),
                "report_json_errors": sum(1 for doc in docs if doc.get("report_error")),
                "created_at": datetime.fromtimestamp(row["created_at"], timezone.utc).isoformat(),
                "updated_at": datetime.fromtimestamp(row["updated_at"], timezone.utc).isoformat(),
                "pause_reason": row["pause_reason"], "summary_url": f"/api/tasks/{row['id']}/report"}

    def _snapshot(self, db, row):
        documents = self._summary_documents(db, [row["id"]]).get(row["id"], [])
        return self._summary(row, documents)

    @staticmethod
    def _legacy_batch(db, owner, task_id):
        batch_id = task_id.removeprefix("legacy-")
        batch = db.execute("""SELECT * FROM batches WHERE id=? AND owner=?
            AND NOT EXISTS(SELECT 1 FROM task_batches WHERE batch_id=batches.id)""",
                           (batch_id, owner)).fetchone()
        if batch is None:
            raise NotFound("task not found")
        return batch

    def assert_owned(self, owner, task_id):
        """Ownership check without building a summary for access-controlled routes."""
        with self.store._connect() as db:
            if task_id.startswith("legacy-"):
                self._legacy_batch(db, owner, task_id)
            else:
                self._owned(db, owner, task_id)

    def _legacy(self, owner, task_id):
        batch_id = task_id.removeprefix("legacy-")
        with self.store._connect() as db:
            batch = self._legacy_batch(db, owner, task_id)
            rows = db.execute("SELECT * FROM documents WHERE batch_id=? ORDER BY ordinal", (batch_id,)).fetchall()
            artifacts = self._artifact_kinds(db, [row["id"] for row in rows])
        docs = []
        for row in rows:
            reasons, _, report_error = self._reason_view(row["report_json"], row["error_code"])
            docs.append({"batch_id": batch_id, "document_id": row["id"], "client_id": row["id"],
                         "name": row["filename"], "size": row["source_size"], "job_status": row["status"],
                         "upload_status": "accepted", "eligibility": row["qualification_status"],
                         "delivery_status": row["delivery_status"], "error_code": row["error_code"],
                         "report_url": (f"/api/batches/{batch_id}/documents/{row['id']}/report"
                                        if row["report_json"] else None),
                         "downloads": {kind: f"/api/batches/{batch_id}/documents/{row['id']}/download/{kind}"
                                       for kind in servable_artifact_kinds(artifacts.get(row["id"], ()),
                                                                           row["execution_mode"])},
                         "source_sha256": row["source_sha256"], "report_error": report_error,
                         "ordinal": row["ordinal"], "reason_codes": reasons})
        task = dict(batch) | {"id": task_id, "name": "历史任务 · " + datetime.fromtimestamp(batch["created_at"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
                              "paused": batch["status"] == "paused", "sealed": True, "pause_reason": None,
                              "mode": "delivery"}
        return self._summary(task, docs, legacy=True), docs

    def get(self, owner, task_id):
        if task_id.startswith("legacy-"):
            return self._legacy(owner, task_id)[0]
        with self.store._connect() as db:
            return self._snapshot(db, self._owned(db, owner, task_id))

    @staticmethod
    def _task_base_sql():
        """Owner tasks with SQL-computed file counters and derived state.

        The aggregate subquery is scoped to the owner so a list request never
        scans another owner's manifest rows.  ``task_status`` mirrors
        ``_task_status`` exactly; it exists so the status filter and paging
        happen before any summary is built.
        """
        return """
            SELECT t.*, CASE
                WHEN COALESCE(a.total,0) > 0
                 AND COALESCE(a.uploaded,0) = COALESCE(a.total,0)
                 AND COALESCE(a.completed,0) = COALESCE(a.total,0)
                 AND COALESCE(a.failed,0) = COALESCE(a.completed,0) THEN 'failed'
                WHEN COALESCE(a.uploaded,0) = COALESCE(a.total,0)
                 AND COALESCE(a.completed,0) = COALESCE(a.total,0)
                 AND COALESCE(a.failed,0) > 0 THEN 'completed_with_exceptions'
                WHEN COALESCE(a.uploaded,0) = COALESCE(a.total,0)
                 AND COALESCE(a.completed,0) = COALESCE(a.total,0) THEN 'completed'
                WHEN COALESCE(t.paused,0) <> 0 THEN 'paused'
                WHEN COALESCE(a.processing,0) > 0 THEN 'running'
                WHEN COALESCE(a.uploaded,0) > COALESCE(a.completed,0) THEN 'queued'
                ELSE 'uploading' END AS task_status
            FROM tasks t
            LEFT JOIN (
                SELECT f.task_id AS task_id,
                       COUNT(f.client_id) AS total,
                       COUNT(CASE WHEN f.upload_status='accepted' THEN 1 END) AS uploaded,
                       COUNT(CASE WHEN d.status IN ('succeeded','failed') THEN 1 END) AS completed,
                       COUNT(CASE WHEN d.status IN ('leased','running') THEN 1 END) AS processing,
                       COUNT(CASE WHEN d.status='failed' THEN 1 END) AS failed
                FROM task_files f
                JOIN tasks owner_task ON owner_task.id=f.task_id AND owner_task.owner=?
                LEFT JOIN documents d ON d.id=f.document_id
                GROUP BY f.task_id
            ) a ON a.task_id = t.id
            WHERE t.owner=?
        """

    @staticmethod
    def _task_order(name_fold, sort):
        if sort in {"name", "name_desc"}:
            return name_fold + (" DESC" if sort == "name_desc" else "") + ", x.id"
        if sort == "newest":
            return "x.created_at DESC, x.id"
        return "x.created_at, x.id"

    def _legacy_descriptors(self, db, owner):
        """Lightweight read-only history rows: one SQL aggregate per batch."""
        rows = db.execute("""SELECT b.id AS batch_id,b.created_at,b.status AS batch_status,
            COUNT(d.id) AS total,
            COUNT(CASE WHEN d.status IN ('succeeded','failed') THEN 1 END) AS completed,
            COUNT(CASE WHEN d.status IN ('leased','running') THEN 1 END) AS processing,
            COUNT(CASE WHEN d.status='failed' THEN 1 END) AS failed
            FROM batches b LEFT JOIN documents d ON d.batch_id=b.id
            WHERE b.owner=? AND NOT EXISTS(SELECT 1 FROM task_batches tb WHERE tb.batch_id=b.id)
            GROUP BY b.id,b.created_at,b.status""", (owner,)).fetchall()
        return [{
            "id": "legacy-" + row["batch_id"],
            "name": "历史任务 · " + datetime.fromtimestamp(row["created_at"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
            "created_at": row["created_at"],
            "task_status": self._task_status(int(row["total"]), int(row["total"]), int(row["completed"]),
                                            int(row["processing"]), int(row["failed"]),
                                            row["batch_status"] == "paused"),
            "guide_version_id": "",
            "_legacy": True,
        } for row in rows]

    def list(self, owner, **filters):
        """Page owner tasks in SQL, then build summaries for the page only.

        First-class tasks are filtered, ordered and limited by SQL.  Retired
        batches (``legacy-*``) have no task rows, so their lightweight
        descriptors are merged at page-selection time; this only happens for
        owners that still have historical batches and keeps ``total`` exact.
        """
        q = filters.get("q") or ""
        state = filters.get("status")
        guide = filters.get("guide_version_id")
        sort = filters.get("sort") or "oldest"
        page = int(filters.get("page") or 1)
        page_size = int(filters.get("page_size") or 50)
        offset = max(0, (page - 1) * page_size)
        clauses, where_params = [], []
        if guide:
            clauses.append("x.guide_version_id = ?")
            where_params.append(guide)
        if state:
            clauses.append("(x.task_status = ? OR (? = 'failed' AND x.task_status = 'completed_with_exceptions'))")
            where_params += [state, state]
        base = self._task_base_sql()
        with self.store._connect() as db:
            name_fold = self._fold(db, "x.name")
            if q:
                clauses.insert(0, f"instr({name_fold}, ?) > 0")
                where_params.insert(0, q.casefold())
            where = "".join(" AND " + clause for clause in clauses)
            order = self._task_order(name_fold, sort)
            legacy = [item for item in self._legacy_descriptors(db, owner)
                      if (not q or q.casefold() in item["name"].casefold())
                      and self._status_matches(item["task_status"], state)
                      and (not guide or item["guide_version_id"] == guide)]
            total = db.execute(f"SELECT COUNT(*) AS n FROM ({base}) x WHERE 1=1{where}",
                               [owner, owner, *where_params]).fetchone()["n"]
            if legacy:
                # Historical rows interleave with task rows, so fetch the
                # prefix that can contain the requested rank, merge, then slice.
                rows = db.execute(f"SELECT * FROM ({base}) x WHERE 1=1{where} ORDER BY {order} LIMIT ?",
                                  [owner, owner, *where_params, page * page_size]).fetchall()
                total += len(legacy)
                combined = [dict(row) for row in rows] + legacy
                key = "name" if sort.startswith("name") else "created_at"
                fold = (lambda value: str(value).casefold()) if key == "name" else (lambda value: value)
                combined.sort(key=lambda item: (fold(item[key]), item["id"]))
                if sort in {"newest", "name_desc"}:
                    combined.sort(key=lambda item: fold(item[key]), reverse=True)
                page_rows = combined[offset:offset + page_size]
                documents = self._summary_documents(
                    db, [item["id"] for item in page_rows if not item.get("_legacy")])
                items = [self._legacy(owner, item["id"])[0] if item.get("_legacy")
                         else self._summary(item, documents.get(item["id"], []))
                         for item in page_rows]
            else:
                rows = db.execute(f"SELECT * FROM ({base}) x WHERE 1=1{where} ORDER BY {order} LIMIT ? OFFSET ?",
                                  [owner, owner, *where_params, page_size, offset]).fetchall()
                documents = self._summary_documents(db, [row["id"] for row in rows])
                items = [self._summary(dict(row), documents.get(row["id"], [])) for row in rows]
        return {"items": items, "total": total, "page": page, "page_size": page_size}

    @staticmethod
    def _page(items, sort="oldest", page=1, page_size=50):
        if sort == "exceptions":
            def exception_rank(d):
                delivery = d["delivery_status"]
                delivery_rank = (2 if delivery == "incomplete" else 3 if delivery == "complete_with_exceptions"
                                 else 4 if (d["eligibility"] or "").startswith("excluded") else 5)
                return (0 if d["job_status"] == "failed" else 1 if d["upload_status"] == "rejected" else delivery_rank,
                        d["ordinal"])
            items.sort(key=exception_rank)
        elif sort == "status":
            stages = {"not_started": 0, "queued": 1, "retry_wait": 2, "leased": 3, "running": 3, "failed": 4, "succeeded": 5}
            items.sort(key=lambda d: (stages.get(d["job_status"], 6), d["ordinal"]))
        else:
            key = "name" if sort.startswith("name") else "created_at" if items and "created_at" in items[0] else "ordinal"
            items.sort(key=lambda x: str(x[key]).casefold() if key == "name" else x[key], reverse=sort in {"newest", "name_desc"})
        return {"items": [{k: v for k, v in d.items() if k != "ordinal"} for d in items[(page-1)*page_size:page*page_size]],
                "total": len(items), "page": page, "page_size": page_size}

    def stats(self, owner: str, month: str | None = None) -> dict:
        """Owner-scoped monthly contract statistics for the overview page.

        ``processed_contracts`` counts terminal documents by ``finished_at``;
        ``pending_contracts`` counts the current backlog. ``average_seconds``
        uses the processing window (claim to terminal), not upload/queue time.
        Historical terminal rows are backfilled by the schema migration.
        """
        cst = timezone(timedelta(hours=8))
        month = month or datetime.now(cst).strftime("%Y-%m")
        try:
            start = datetime.strptime(month, "%Y-%m").replace(tzinfo=cst)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid month") from exc
        if start.strftime("%Y-%m") != month:
            raise ValueError("invalid month")
        end = (start.replace(year=start.year + 1, month=1) if start.month == 12
               else start.replace(month=start.month + 1))
        prev_start = (start - timedelta(days=1)).replace(day=1)
        start_ts, end_ts, prev_ts = start.timestamp(), end.timestamp(), prev_start.timestamp()
        with self.store._connect() as db:
            rows = db.execute("""SELECT tf.task_id,tf.upload_status,
                d.id AS document_id,d.status,d.delivery_status,d.qualification_status,
                d.created_at AS doc_created_at,d.updated_at AS doc_updated_at,d.report_json,
                d.started_at,d.finished_at
                FROM task_files tf JOIN tasks t ON t.id=tf.task_id
                LEFT JOIN documents d ON d.id=tf.document_id
                WHERE t.owner=?""", (owner,)).fetchall()
        processed = completed = previous = failed_contracts = 0
        report_json_errors = 0
        pending = exceptions = 0
        active_tasks: set[str] = set()
        durations: list[float] = []
        for row in rows:
            status = row["status"] or "not_started"
            if row["report_json"] is not None and self._report_error(row["report_json"]):
                report_json_errors += 1
            terminal = status in {"succeeded", "failed"}
            finished = row["finished_at"] if row["finished_at"] is not None else (
                row["doc_updated_at"] if terminal else None)
            started = row["started_at"] if row["started_at"] is not None else (
                row["doc_created_at"] if terminal else None)
            if terminal and finished is not None:
                if start_ts <= float(finished) < end_ts:
                    processed += 1
                    if status == "failed":
                        failed_contracts += 1
                    if status == "succeeded" and row["delivery_status"] in {"complete", "complete_with_exceptions"}:
                        completed += 1
                    if started is not None and float(finished) >= float(started):
                        durations.append(float(finished) - float(started))
                elif prev_ts <= float(finished) < start_ts:
                    previous += 1
            rejected = (row["upload_status"] or "") == "rejected"
            bad_delivery = terminal and (status == "failed" or
                (row["qualification_status"] != "excluded_by_fund_type" and
                 (row["delivery_status"] or "") in {"incomplete", "not_generated"}))
            if rejected or bad_delivery:
                exceptions += 1
            if (row["document_id"] is None and (row["upload_status"] or "pending") == "pending") \
                    or status in {"queued", "retry_wait", "leased", "running"}:
                pending += 1
                active_tasks.add(row["task_id"])
        average = round(sum(durations) / len(durations), 1) if durations else None
        rate = round(completed / processed, 4) if processed else 0.0
        change = round((processed - previous) / previous, 4) if previous else None
        return {"month": month, "processed_contracts": processed,
                "completed_contracts": completed, "completion_rate": rate,
                "pending_contracts": pending, "active_tasks": len(active_tasks),
                "average_seconds": average, "exception_contracts": exceptions,
                "previous_processed_contracts": previous,
                "month_over_month": change, "report_json_errors": report_json_errors,
                "failed_contracts": failed_contracts,
                "generated_at": datetime.now(timezone.utc).isoformat()}

    def documents(self, owner, task_id, **filters):
        """Page one task's contracts with SQL filters, ordering and limits.

        Filters, ordering, ``COUNT``, ``LIMIT``/``OFFSET`` and the artifact
        lookup are one query each (two when the reason-code filter must inspect
        report JSON).  ``reason_options`` intentionally stays task-wide: it is a
        filter vocabulary for the whole contract list, not the current page.
        """
        page = int(filters.get("page") or 1)
        page_size = int(filters.get("page_size") or 50)
        sort = filters.get("sort") or "oldest"
        error_code = filters.get("error_code")
        if task_id.startswith("legacy-"):
            docs = self._legacy(owner, task_id)[1]
            reasons = Counter(code for d in docs for code in d["reason_codes"])
            def matches(d, key):
                value = filters.get(key)
                if key == "job_status" and value == "running":
                    return d[key] in {"leased", "running"}
                return not value or value == (d[key] or "pending")
            docs = [d for d in docs if (filters.get("q") or "").casefold() in d["name"].casefold()
                    and all(matches(d, k) for k in ("eligibility", "job_status", "delivery_status", "upload_status"))
                    and (not error_code or error_code in d["reason_codes"])]
            result = self._page(docs, sort=sort, page=page, page_size=page_size)
            reason_options = [{"code": code, "count": count} for code, count in sorted(reasons.items())]
        else:
            with self.store._connect() as db:
                self._owned(db, owner, task_id)
                views, reason_counts = self._task_views(db, task_id)
                name_fold = self._fold(db, "f.name")
                clauses, params = self._document_filters(name_fold, filters)
                where = "".join(" AND " + clause for clause in clauses)
                if error_code:
                    # Reason codes can live inside report JSON, so the SQL part
                    # is only a safe superset; the exact membership test stays
                    # the unchanged Python one.
                    prefilter, pre_params = self._error_code_filter(error_code)
                    sql = (f"SELECT {_DOCUMENT_COLUMNS} FROM {_DOCUMENT_FROM} "
                           f"WHERE f.task_id=?{where}")
                    args = [task_id, *params]
                    if prefilter:
                        sql += " AND " + prefilter
                        args += pre_params
                    rows = db.execute(sql + f" ORDER BY {self._document_order(name_fold, sort)}", args).fetchall()
                    rows = [row for row in rows if error_code in views[row["client_id"]][0]]
                    total = len(rows)
                    offset = max(0, (page - 1) * page_size)
                    rows = rows[offset:offset + page_size]
                else:
                    total = db.execute(f"SELECT COUNT(*) AS n FROM {_DOCUMENT_FROM} WHERE f.task_id=?{where}",
                                       [task_id, *params]).fetchone()["n"]
                    offset = max(0, (page - 1) * page_size)
                    rows = db.execute(f"SELECT {_DOCUMENT_COLUMNS} FROM {_DOCUMENT_FROM} "
                                      f"WHERE f.task_id=?{where} ORDER BY {self._document_order(name_fold, sort)} "
                                      "LIMIT ? OFFSET ?", [task_id, *params, page_size, offset]).fetchall()
                artifacts = self._artifact_kinds(db, [row["document_id"] for row in rows if row["document_id"]])
            items = [{key: value for key, value in
                      self._document_from_row(row, task_id, artifacts, views[row["client_id"]]).items()
                      if key != "ordinal"} for row in rows]
            result = {"items": items, "total": total, "page": page, "page_size": page_size}
            reason_options = [{"code": code, "count": count} for code, count in sorted(reason_counts.items())]
        result["reason_options"] = reason_options
        return result

    # ------------------------------------------------------------------
    # Admin 任务看板（仅 role=admin 调用路径使用）
    # ------------------------------------------------------------------

    def _admin_audit(self, db, actor: str, action: str, task_id: str = "",
                     document_id: str = "", detail: str = "") -> None:
        db.execute("INSERT INTO admin_audit_log(id,actor,action,task_id,document_id,detail,created_at) "
                   "VALUES(?,?,?,?,?,?,?)",
                   (uuid.uuid4().hex, actor, action, task_id, document_id, detail, time.time()))

    def admin_audit(self, actor: str, action: str, task_id: str = "",
                    document_id: str = "", detail: str = "") -> None:
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._admin_audit(db, actor, action, task_id, document_id, detail)

    def admin_tasks(self, *, q: str = "", status: str | None = None,
                    page: int = 1, page_size: int = 50) -> dict[str, Any]:
        """Admin 全库任务：分页+q+状态筛；执行计数+最近错误码。

        状态筛沿用前端状态口径：status_calc=tasks 行导出的状态。返回历史 legacy
        映射**不混入**（历史数据不主动暴露）。
        """
        clauses, params = [], []
        if q:
            clauses.append("(LOWER(t.name) LIKE ? OR LOWER(t.owner) LIKE ? OR t.id LIKE ?)")
            like = f"%{q.casefold()}%"
            params += [like, like, like]
        where = " AND " + " AND ".join(clauses) if clauses else ""
        aggregate = """(SELECT f.task_id AS oid,
            COUNT(f.client_id) AS total,
            COUNT(CASE WHEN d.status='succeeded' THEN 1 END) AS succeeded,
            COUNT(CASE WHEN d.status='failed' THEN 1 END) AS failed,
            COUNT(CASE WHEN d.status IN ('queued','retry_wait') THEN 1 END) AS queued,
            COUNT(CASE WHEN d.status IN ('leased','running') THEN 1 END) AS running,
            (SELECT COALESCE(NULLIF(d2.error_code,''),NULLIF(f2.error_code,''))
               FROM task_files f2 LEFT JOIN documents d2 ON d2.id=f2.document_id
              WHERE f2.task_id=f.task_id AND COALESCE(d2.error_code,f2.error_code) IS NOT NULL
              ORDER BY COALESCE(d2.updated_at,0) DESC LIMIT 1) AS recent_error
            FROM task_files f LEFT JOIN documents d ON d.id=f.document_id
            GROUP BY f.task_id)"""
        with self.store._connect() as db:
            # 状态筛落在导出状态上：先取候选上限行再在 Python 侧筛——
            # 保持 total/page 与筛选口径严格一致（Admin 面板规模受控 5000）。
            rows = db.execute(
                f"""SELECT t.id,t.owner,t.name,t.engine_id,t.mode,t.sealed,t.paused,t.created_at,
                    a.total,a.succeeded,a.failed,a.queued,a.running,a.recent_error
                FROM tasks t LEFT JOIN {aggregate} a ON a.oid=t.id
                WHERE 1=1{where} ORDER BY t.created_at DESC LIMIT 5000""",
                params).fetchall()
        items = []
        for row in rows:
            of_total = int(row["total"] or 0)
            succeeded = int(row["succeeded"] or 0)
            failed = int(row["failed"] or 0)
            running = int(row["running"] or 0)
            queued = int(row["queued"] or 0)
            if failed and succeeded + failed == of_total:
                task_status = "completed_with_exceptions" if succeeded else "failed"
            elif succeeded + failed == of_total and of_total:
                task_status = "completed"
            elif row["paused"]:
                task_status = "paused"
            elif running:
                task_status = "running"
            elif queued:
                task_status = "queued"
            else:
                task_status = "uploading"
            if status and status != task_status:
                continue
            items.append({
                "id": row["id"], "name": row["name"], "owner": row["owner"],
                "engine_id": row["engine_id"], "mode": row["mode"],
                "status": task_status, "sealed": bool(row["sealed"]), "paused": bool(row["paused"]),
                "progress": {"total": of_total, "succeeded": succeeded, "failed": failed,
                             "queued": queued, "running": running},
                "recent_error_code": row["recent_error"] or "",
                "created_at": datetime.fromtimestamp(row["created_at"], timezone.utc).isoformat(),
            })
        total = len(items)
        if page_size < 1:
            page_size = 50
        start = (page - 1) * page_size
        return {"items": items[start:start + page_size], "total": total,
                "page": page, "page_size": page_size}

    def admin_documents(self, task_id: str) -> dict[str, Any]:
        """Admin 视角单任务文档行：状态/错误码/重试次数/下一步时间/耗时/写回数。"""
        with self.store._connect() as db:
            task = db.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
            if task is None:
                raise NotFound("task not found")
            rows = db.execute(f"""SELECT {_DOCUMENT_COLUMNS} FROM {_DOCUMENT_FROM}
                WHERE f.task_id=? ORDER BY f.ordinal""", (task_id,)).fetchall()
            batch = db.execute(
                f"""SELECT d.id,d.attempt,d.next_attempt_at,d.started_at,d.finished_at
                    FROM task_files f JOIN documents d ON d.id=f.document_id
                    WHERE f.task_id=? ORDER BY f.ordinal""", (task_id,)).fetchall()
        timings = {row["id"]: dict(row) for row in batch}
        artifacts = {}
        with self.store._connect() as db:
            for row in db.execute("SELECT document_id,kind FROM artifacts ORDER BY document_id,kind"):
                artifacts.setdefault(row["document_id"], []).append(row["kind"])
        items = []
        for row in rows:
            view = self._reason_view(row["report_json"], row["document_error"] or row["file_error"])
            extras = self._direct_row_extras(row["report_json"] if row["document_id"] else None)
            base = self._document_from_row(row, task_id, artifacts, view)
            timing = timings.get(row["document_id"] or "", {})
            started, finished = timing.get("started_at"), timing.get("finished_at")
            duration = (round(float(finished) - float(started), 1)
                        if finished and started else None)
            items.append({**base, **extras,
                          "status": base["job_status"],
                          "attempt": timing.get("attempt"),
                          "next_attempt_at": timing.get("next_attempt_at"),
                          "duration_seconds": duration,
                          "edit_count": extras.get("edit_count"),
                          "revision_tier": extras.get("revision_tier")})
        return {"items": items, "total": len(items)}

    def admin_retry_document(self, actor: str, document_id: str) -> dict[str, Any]:
        """管理员强制重试：不查属主、不受 attempt<3；仅 failed/retry_wait 可再排。

        running/succeeded 一律 409 诚实文案；并发回排队在 fencing 下天然安全。
        attempt 数值继续加不重置；审计痕迹落 admin_audit_log + documents 注记。
        """
        now = time.time()
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT d.id,d.status,d.attempt,d.batch_id,d.fencing_token,
                b.status AS batch_status, f.task_id, f.name
                FROM documents d
                JOIN batches b ON b.id=d.batch_id
                JOIN task_files f ON f.document_id=d.id
                WHERE d.id=?""", (document_id,)).fetchone()
            if row is None:
                raise NotFound("document not found")
            if row["status"] in ("leased", "running"):
                raise Conflict("ADMIN_RETRY_RUNNING")
            if row["status"] == "succeeded":
                raise Conflict("ADMIN_RETRY_NO_WORK")
            if row["status"] not in ("failed", "retry_wait"):
                raise Conflict("ADMIN_RETRY_STATE_INVALID")
            db.execute("""UPDATE documents SET status='queued',lease_until=NULL,next_attempt_at=NULL,
                error_code=NULL,admin_requeue_count=admin_requeue_count+1,
                admin_requeued_by=?,admin_requeued_at=?,updated_at=?
                WHERE id=?""", (actor, now, now, document_id))
            db.execute("UPDATE batches SET status=?,updated_at=? WHERE id=?",
                       ("paused" if row["batch_status"] == "paused" else "queued", now, row["batch_id"]))
            self._admin_audit(db, actor, "admin_document_retry", row["task_id"],
                              document_id, f"name={row['name']}")
        return self.admin_document_summary(document_id)

    def _admin_task_owner(self, task_id: str) -> str:
        with self.store._connect() as db:
            row = db.execute("SELECT owner FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise NotFound("task not found")
        return str(row["owner"])

    def admin_pause_task(self, actor: str, task_id: str) -> dict[str, Any]:
        owner = self._admin_task_owner(task_id)
        result = self.control(owner, task_id, "pause")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._admin_audit(db, actor, "admin_task_pause", task_id)
        return result

    def admin_resume_task(self, actor: str, task_id: str) -> dict[str, Any]:
        owner = self._admin_task_owner(task_id)
        result = self.control(owner, task_id, "resume")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._admin_audit(db, actor, "admin_task_resume", task_id)
        return result

    def admin_cancel_task(self, actor: str, task_id: str) -> dict[str, Any]:
        """cancel：未开始的 queued/retry_wait 文档终态失败 ADMIN_CANCELLED；
        running/leased 文档自然终态（不强行中止）。"""
        self._admin_task_owner(task_id)
        now = time.time()
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            affected = db.execute("""UPDATE documents SET status='failed',
                error_code='ADMIN_CANCELLED',lease_until=NULL,next_attempt_at=NULL,
                finished_at=COALESCE(finished_at,?),updated_at=?
                WHERE status IN ('queued','retry_wait') AND batch_id IN
                    (SELECT batch_id FROM task_batches WHERE task_id=?)""",
                (now, now, task_id)).rowcount
            running = db.execute("""SELECT COUNT(*) AS n FROM documents d
                JOIN task_batches tb ON tb.batch_id=d.batch_id
                WHERE tb.task_id=? AND d.status IN ('leased','running')""",
                (task_id,)).fetchone()["n"]
            for bid in db.execute("SELECT batch_id FROM task_batches WHERE task_id=?",
                                  (task_id,)).fetchall():
                StoreSessionHelper = None
                remaining = db.execute("SELECT COUNT(*) FROM documents WHERE batch_id=? AND status NOT IN ('succeeded','failed')",
                                       (bid["batch_id"],)).fetchone()[0]
                db.execute("UPDATE batches SET status=?,updated_at=? WHERE id=?",
                           ("completed" if not remaining else "queued", now, bid["batch_id"]))
            self._admin_audit(db, actor, "admin_task_cancel", task_id,
                              detail=f"cancelled={affected},running_kept={running}")
        return {"task_id": task_id, "cancelled": affected, "running_kept": running,
                "total": self.admin_tasks(q=task_id)["items"][0]["progress"]}

    def admin_model_usage(self, from_ts: float | None, to_ts: float | None,
                          model: str = "", task_type: str = "") -> dict[str, Any]:
        """只读聚合模型账本：调用数/tokens/费用/失败率/均时；filter by from/to/model/task_type。"""
        from .config import local_data_dir
        from .db import Database
        import os as _os
        import sqlite3 as _sq
        ledger = _os.environ.get("FUNDLEX_MODEL_LEDGER",
                                 str(local_data_dir() / "model_budget.sqlite"))
        clauses, params = [], []
        if from_ts:
            clauses.append("started >= ?")
            params.append(from_ts)
        if to_ts:
            clauses.append("started <= ?")
            params.append(to_ts)
        if model:
            clauses.append("json_extract(metadata,'$.configured_model') = ?")
            params.append(model)
        if task_type:
            clauses.append("json_extract(metadata,'$.task_type') = ?")
            params.append(task_type)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        try:
            with _sq.connect(f"file:{ledger}?mode=ro", uri=True) as conn:
                conn.row_factory = _sq.Row
                rows = conn.execute(
                    f"""SELECT json_extract(metadata,'$.configured_model') AS model,
                        json_extract(metadata,'$.task_type') AS task_type,
                        COUNT(*) AS calls,
                        SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END) AS ok,
                        COALESCE(SUM(charged_cost),0) AS cost,
                        COALESCE(SUM(CAST(json_extract(metadata,'$.prompt_tokens') AS INTEGER)),0) AS ptok,
                        COALESCE(SUM(CAST(json_extract(metadata,'$.completion_tokens') AS INTEGER)),0) AS ctok,
                        COALESCE(AVG(CAST(json_extract(metadata,'$.latency_ms') AS REAL)),0) AS avg_ms
                        FROM requests {where}
                        GROUP BY model, task_type ORDER BY cost DESC""", params).fetchall()
        except _sq.Error as exc:
            raise RuntimeError(f"model ledger aggregate failed: {exc}") from exc
        items = [{
            "model": r["model"] or "", "task_type": r["task_type"] or "",
            "calls": r["calls"], "ok": r["ok"], "failed": r["calls"] - r["ok"],
            "failure_rate": round((r["calls"] - r["ok"]) / r["calls"], 4) if r["calls"] else 0,
            "cost_usd": round(float(r["cost"]), 4),
            "prompt_tokens": int(r["ptok"] or 0), "completion_tokens": int(r["ctok"] or 0),
            "avg_latency_ms": round(float(r["avg_ms"] or 0), 1),
        } for r in rows]
        return {"items": items, "total": len(items),
                "from_ts": from_ts, "to_ts": to_ts}

    def admin_system_status(self) -> dict[str, Any]:
        from .config import local_data_dir
        from .store import engine_build, service_build, SCHEMA_VERSION
        from .direct_pipeline import ENGINE_VERSION, ENGINE_ID
        with self.store._connect() as db:
            depths = {r[0] or "": r[1] for r in
                      db.execute("SELECT d.status,COUNT(*) FROM documents d JOIN batches b ON b.id=d.batch_id GROUP BY d.status").fetchall()}
            conv = {r[0]: r[1] for r in
                    db.execute("SELECT conversion_state,COUNT(*) FROM documents GROUP BY conversion_state").fetchall() if r[0]}
            pending_convert = db.execute(
                "SELECT COUNT(*) FROM documents WHERE conversion_state='pending_convert'").fetchone()[0]
        # 队列外的账本最近调用年代（与模型调用账本对齐观测，非模型调用本身）。
        last_model_start = None
        import os as _os, sqlite3 as _sq
        ledger = _os.environ.get("FUNDLEX_MODEL_LEDGER",
                                 str(local_data_dir() / "model_budget.sqlite"))
        try:
            with _sq.connect(f"file:{ledger}?mode=ro", uri=True) as conn:
                r = conn.execute("SELECT MAX(started) FROM requests").fetchone()
                if r and r[0]:
                    last_model_start = datetime.fromtimestamp(r[0], timezone.utc).isoformat()
        except _sq.Error:
            last_model_start = None
        import subprocess as _sp, shutil as _su
        services = {}
        if _su.which("systemctl"):
            for svc in ("fundlex-recall-api", "fundlex-recall-worker",
                        "fundlex-guide-worker", "fundlex-compare-worker",
                        "fundlex-feishu"):
                try:
                    out = _sp.run(["systemctl", "is-active", f"{svc}.service"],
                                  capture_output=True, timeout=5, text=True, check=False)
                    services[svc] = out.stdout.strip() or "unknown"
                except Exception as exc:  # noqa: BLE001 - 观测面
                    services[svc] = f"unavailable:{type(exc).__name__}"
        else:
            services = {s: "unavailable" for s in ("fundlex-recall-api", "fundlex-recall-worker",
                                                    "fundlex-guide-worker", "fundlex-compare-worker",
                                                     "fundlex-feishu")}
        return {"queue_depth": depths, "pending_convert": pending_convert,
                "conversion_states": conv,
                "last_model_call_at": last_model_start,
                "engine": {"id": ENGINE_ID, "version": ENGINE_VERSION},
                "engine_build": engine_build(), "service_build": service_build(),
                "schema_version": SCHEMA_VERSION, "services": services}

    def admin_audit_list(self, *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
        with self.store._connect() as db:
            total = db.execute("SELECT COUNT(*) AS n FROM admin_audit_log").fetchone()["n"]
            rows = db.execute("SELECT actor,action,task_id,document_id,detail,created_at "
                              "FROM admin_audit_log ORDER BY created_at DESC LIMIT ? OFFSET ?",
                              (page_size, (page - 1) * page_size)).fetchall()
        return {"total": total, "page": page, "page_size": page_size,
                "items": [{**dict(r),
                           "created_at": datetime.fromtimestamp(r["created_at"], timezone.utc).isoformat()}
                          for r in rows]}

    def admin_artifacts(self, task_id: str) -> dict[str, Any]:
        self._admin_task_owner(task_id)
        with self.store._connect() as db:
            rows = db.execute("""SELECT f.document_id,f.name AS filename,a.kind,a.sha256,a.size
                FROM task_files f JOIN artifacts a ON a.document_id=f.document_id
                WHERE f.task_id=? ORDER BY f.ordinal,a.kind""", (task_id,)).fetchall()
        return {"task_id": task_id,
                "items": [{**dict(r)} for r in rows]}

    def admin_artifact_download(self, task_id: str, document_id: str, kind: str,
                                 actor: str) -> tuple[bytes, str]:
        owner = self._admin_task_owner(task_id)
        with self.store._connect() as db:
            linked = db.execute("""SELECT f.document_id,d.batch_id FROM task_files f
                JOIN documents d ON d.id=f.document_id WHERE f.task_id=? AND f.document_id=?""",
                (task_id, document_id)).fetchone()
            if linked is None or not linked["document_id"]:
                raise NotFound("document not found")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._admin_audit(db, actor, "admin_artifact_download", task_id, document_id, kind)
        data, digest = self.store.read_artifact(owner, linked["batch_id"], document_id, kind)
        return data, digest

    def admin_delete_task(self, actor: str, task_id: str, *, confirm: str) -> dict[str, Any]:
        """硬删 task/task_files/documents/artifacts/batches 与对象字节；必须
        ``confirm == task_id``。产物先为 oracle 收集，结清后由库内事务负责
        行清按，对象文件单独清理不计进入库失败文明性。"""
        self._admin_task_owner(task_id)
        confirm = (confirm or "").strip()
        if confirm != task_id:
            raise ValueError("CONFIRM_MISMATCH")
        object_keys: set[str] = set()
        with self.store._connect() as db:
            rows = db.execute("""SELECT d.input_key, a.object_key, d.converted_key
                FROM task_files f
                JOIN documents d ON d.id=f.document_id
                LEFT JOIN artifacts a ON a.document_id=d.id
                WHERE f.task_id=?""", (task_id,)).fetchall()
            for r in rows:
                for key in (r["input_key"], r["object_key"], r["converted_key"]):
                    if key:
                        object_keys.add(str(key))
            batch_rows = db.execute("SELECT batch_id FROM task_batches WHERE task_id=?",
                                    (task_id,)).fetchall()
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for brief in batch_rows:
                bid = brief["batch_id"] if isinstance(brief, dict) else brief["batch_id"]
                # FK 顺序：artifacts → task_files 内的文档引用 → documents → task_batches → batches
                db.execute("DELETE FROM artifacts WHERE document_id IN (SELECT id FROM documents WHERE batch_id=?)", (bid,))
                db.execute("UPDATE task_files SET document_id=NULL WHERE document_id IN (SELECT id FROM documents WHERE batch_id=?)", (bid,))
                db.execute("DELETE FROM documents WHERE batch_id=?", (bid,))
                db.execute("DELETE FROM task_batches WHERE batch_id=?", (bid,))
                db.execute("DELETE FROM batches WHERE id=?", (bid,))
            db.execute("DELETE FROM task_files WHERE task_id=?", (task_id,))
            db.execute("DELETE FROM tasks WHERE id=?", (task_id,))
            self._admin_audit(db, actor, "admin_task_delete", task_id,
                              detail=f"objects={len(object_keys)}")
        for key in object_keys:
            try:
                self.store.object_path(key).unlink(missing_ok=True)
            except (OSError, StoreError):
                pass
        return {"task_id": task_id, "deleted": True, "objects_removed": len(object_keys)}

    def admin_document_summary(self, document_id: str) -> dict[str, Any]:
        with self.store._connect() as db:
            row = db.execute("""SELECT d.id,d.status,d.error_code,d.attempt,d.next_attempt_at,
                d.admin_requeue_count,d.admin_requeued_by,d.admin_requeued_at,f.task_id
                FROM documents d JOIN task_files f ON f.document_id=d.id WHERE d.id=?""",
                (document_id,)).fetchone()
        if row is None:
            raise NotFound("document not found")
        return {"document_id": row["id"], "task_id": row["task_id"], "status": row["status"],
                "error_code": row["error_code"], "attempt": row["attempt"],
                "next_attempt_at": row["next_attempt_at"],
                "admin_requeue_count": row["admin_requeue_count"],
                "admin_requeued_by": row["admin_requeued_by"],
                "admin_requeued_at": row["admin_requeued_at"]}

    def retry_document(self, owner: str, task_id: str, document_id: str) -> dict:
        """手动重试一份终端失败的合同：回排队列，错误码清算；attempt 计数不动。

        仅当：当前用户持有任务、文档属于任务、job 终态 failed、attempt 未达
        上限（Worker 默认 3 次技术重试）。其他状态（进行中/已成功/未处理）
        返回状态冲突而非静默重排，避免并发下抢租约。
        """
        if task_id.startswith("legacy-"):
            raise Conflict("HISTORICAL_TASK_READ_ONLY")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            task = self._owned(db, owner, task_id)
            row = db.execute("""SELECT d.id,d.status,d.attempt,d.batch_id,b.status AS batch_status
                FROM task_files f JOIN documents d ON d.id=f.document_id
                JOIN batches b ON b.id=d.batch_id
                WHERE f.task_id=? AND f.document_id=?""", (task_id, document_id)).fetchone()
            if row is None:
                raise NotFound("document not found")
            if row["status"] != "failed":
                raise Conflict("DOCUMENT_RETRY_STATE_INVALID")
            if int(row["attempt"]) >= 3:
                raise Conflict("DOCUMENT_RETRY_EXHAUSTED")
            now = time.time()
            db.execute("""UPDATE documents SET status='queued',lease_until=NULL,next_attempt_at=NULL,
                error_code=NULL,updated_at=? WHERE id=?""", (now, document_id))
            if row["batch_status"] not in {"paused"}:
                db.execute("UPDATE batches SET status='queued',updated_at=? WHERE id=?",
                           (now, row["batch_id"]))
            db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, task_id))
        return self.get(owner, task_id)

    def document(self, owner: str, task_id: str, document_id: str) -> dict:
        """Return one task document without the list endpoint's page limit."""
        if task_id.startswith("legacy-"):
            docs = self._legacy(owner, task_id)[1]
            for item in docs:
                if item.get("document_id") == document_id:
                    return item
            raise NotFound("document not found")
        with self.store._connect() as db:
            self._owned(db, owner, task_id)
            row = db.execute(f"SELECT {_DOCUMENT_COLUMNS} FROM {_DOCUMENT_FROM} "
                             "WHERE f.task_id=? AND f.document_id=?",
                             (task_id, document_id)).fetchone()
            if row is None or not row["document_id"]:
                raise NotFound("document not found")
            view = self._reason_view(row["report_json"], row["document_error"] or row["file_error"])
            artifacts = self._artifact_kinds(db, [document_id])
        item = self._document_from_row(row, task_id, artifacts, view)
        return {key: value for key, value in item.items() if key != "ordinal"}

    def artifact(self, owner: str, task_id: str, document_id: str, kind: str):
        """Return verified bytes and a filename for one published artifact.

        This is the task-scoped facade over ``RunStore.read_artifact``: it adds
        the task/document linkage check, then reuses the same ownership, mode,
        report and paired-artifact gate as HTTP downloads. Feishu must not read
        object files directly.
        """
        if task_id.startswith("legacy-"):
            raise NotFound("artifact not found")
        with self.store._connect() as db:
            self._owned(db, owner, task_id)
            linked = db.execute("""SELECT f.document_id,d.batch_id,d.filename FROM task_files f
                JOIN documents d ON d.id=f.document_id
                WHERE f.task_id=? AND f.document_id=?""", (task_id, document_id)).fetchone()
        if linked is None or not linked["document_id"]:
            raise NotFound("document not found")
        data, _ = self.store.read_artifact(owner, linked["batch_id"], document_id, kind)
        filename = Path(linked["filename"] or "contract.docx").name
        suffix = Path(filename).suffix or ".docx"
        if kind.startswith("report"):
            suffix = ".md" if kind == "report_md" else ".json"
        stem = Path(filename).stem
        return data, f"{stem}-{kind}{suffix}"

    def uploads(self, owner, task_id, uploads):
        """Upload items contain client_id, name, data and validated error_code.

        Validate receipts independently, then stage only accepted candidates.
        The lock resolves simultaneous retries before publishing any document.
        """
        self.get(owner, task_id)
        if task_id.startswith("legacy-"):
            raise Conflict("HISTORICAL_TASK_READ_ONLY")
        staged, committed = [], False
        try:
            for item in uploads:
                entry = dict(item)
                if not entry.get("error_code"):
                    entry["key"], entry["digest"], entry["size"] = self.store.stage(entry["data"])
                    staged.append(entry["key"])
                else:
                    entry["digest"] = hashlib.sha256(entry["data"]).hexdigest()
                    entry["size"] = len(entry["data"])
                item.update(entry)
            build, now, batch_id, receipts, published = engine_build(), time.time(), uuid.uuid4().hex, [], set()
            with self.store._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                task = self._owned(db, owner, task_id)
                ordinal = 0
                for item in uploads:
                    f = db.execute("SELECT * FROM task_files WHERE task_id=? AND client_id=?", (task_id, item["client_id"])).fetchone()
                    error = item.get("error_code")
                    receipt = {"client_id": item["client_id"], "status": "rejected", "document_id": None, "batch_id": None, "error_code": None}
                    if f is None:
                        error = "MANIFEST_ENTRY_NOT_FOUND"
                    elif f["document_id"]:
                        old = db.execute("SELECT * FROM documents WHERE id=?", (f["document_id"],)).fetchone()
                        if item["digest"] == old["source_sha256"] and item["size"] == old["source_size"] and item["name"] == f["name"]:
                            receipt.update(status="already_accepted", document_id=old["id"], batch_id=old["batch_id"])
                            error = None
                        else:
                            error = "UPLOAD_IDENTITY_CONFLICT"
                        receipt["error_code"] = error
                        receipts.append(receipt)
                        continue
                    elif (item["name"] != f["name"]
                          or (int(item.get("original_size") or item["size"]) != f["size"])):
                        # 声明口径=原件字节（manifest），落地口径=归一字节：
                        # .doc 自动转换时两套尺寸天然不同，不判定清单冲突。
                        error = "MANIFEST_FILE_MISMATCH"
                    if error:
                        if f is not None:
                            db.execute("UPDATE task_files SET upload_status='rejected',error_code=? WHERE task_id=? AND client_id=?", (error, task_id, item["client_id"]))
                        receipt["error_code"] = error
                        receipts.append(receipt)
                        continue
                    if ordinal == 0:
                        db.execute("""INSERT INTO batches(id,owner,ruleset_version,ruleset_sha256,mode,status,request_hash,
                            created_at,updated_at,engine_build,schema_version,engine_id,guide_version_id,
                            guide_rules_sha256,guide_schema_version,snapshot_json,disabled_rule_ids,model_preferences)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                   (batch_id, owner, task["ruleset_version"], task["ruleset_sha256"],
                                    task["mode"] or "delivery",
                                    "paused" if task["paused"] else "queued",
                                    uuid.uuid4().hex, now, now, build, SCHEMA_VERSION, task["engine_id"],
                                    task["guide_version_id"], task["guide_rules_sha256"],
                                    (task["guide_schema_version"] or "")
                                    if "guide_schema_version" in task.keys() else "",
                                    (task["snapshot_json"] or "")
                                    if "snapshot_json" in task.keys() else "",
                                    task["disabled_rule_ids"] or "[]", task["model_preferences"] or "{}"))
                        db.execute("INSERT INTO task_batches VALUES(?,?)", (task_id, batch_id))
                    document_id = uuid.uuid4().hex
                    db.execute("""INSERT INTO documents(id,batch_id,ordinal,filename,source_sha256,source_size,input_key,
                        status,conversion_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                               (document_id, batch_id, ordinal, f["name"], item["digest"], item["size"], item["key"],
                                "queued", str(item.get("conversion_state") or ""), now, now))
                    ordinal += 1
                    published.add(item["key"])
                    db.execute("UPDATE task_files SET upload_status='accepted',error_code=NULL,document_id=? WHERE task_id=? AND client_id=?", (document_id, task_id, item["client_id"]))
                    receipt.update(status="accepted", document_id=document_id, batch_id=batch_id)
                    receipts.append(receipt)
                db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, task_id))
                result = {"receipts": receipts, "task": self._snapshot(db, self._owned(db, owner, task_id))}
            committed = True
            for key in staged:
                if key not in published:
                    self.store.object_path(key).unlink(missing_ok=True)
            return result
        except Exception:
            if not committed:
                for key in staged:
                    self.store.object_path(key).unlink(missing_ok=True)
            raise

    def control(self, owner, task_id, operation):
        self.get(owner, task_id)
        if task_id.startswith("legacy-"):
            if operation in {"pause", "resume"}:
                getattr(self.store, operation)(owner, task_id.removeprefix("legacy-"))
                return self.get(owner, task_id)
            raise Conflict("HISTORICAL_TASK_READ_ONLY")
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._owned(db, owner, task_id)
            now = time.time()
            if operation == "seal":
                db.execute("UPDATE tasks SET sealed=1,updated_at=? WHERE id=?", (now, task_id))
            else:
                db.execute("UPDATE tasks SET paused=?,pause_reason=NULL,updated_at=? WHERE id=?", (operation == "pause", now, task_id))
                rows = db.execute("SELECT batch_id FROM task_batches WHERE task_id=?", (task_id,)).fetchall()
                for row in rows:
                    bid = row["batch_id"]
                    pending = db.execute("SELECT COUNT(*) FROM documents WHERE batch_id=? AND status NOT IN ('succeeded','failed')", (bid,)).fetchone()[0]
                    db.execute("UPDATE batches SET status=?,updated_at=? WHERE id=?", ("completed" if not pending else "paused" if operation == "pause" else "queued", now, bid))
                # A pause on a task whose batches are all already terminal must
                # not leave a stale paused bit contradicting completed batches
                # (FL-D553 B14-03).
                self.store._heal_task_pause(db, now)
            return self._snapshot(db, self._owned(db, owner, task_id))

    def report(self, owner, task_id):
        """结果总览.md：面向合同交付的阅读件，不含资格/错误码/引擎标识等技术信息。"""
        summary = self.get(owner, task_id)
        docs = self.documents(owner, task_id, page_size=100000)["items"]
        if summary.get("result_schema") == "direct_edit_v1" and not summary.get("legacy"):
            # 直通任务：结果总览由 direct_report 统一渲染（实际写回对照）。
            from .direct_report import render_overview
            entries = []
            for doc in docs:
                doc_report: dict = {}
                if doc["document_id"]:
                    try:
                        doc_report = self.store.get_report(owner, doc["batch_id"],
                                                           doc["document_id"])
                    except (NotFound, ReportJsonError):
                        doc_report = {}
                entries.append((doc["name"], doc_report, doc))
            return render_overview(summary["name"], entries)

        def safe(value):
            return str(value or "—").replace("|", "\\|").replace("\r", " ").replace("\n", " ")

        reports: dict[str, dict] = {}
        for doc in docs:
            report: dict = {}
            if doc["document_id"]:
                try:
                    report = self.store.get_report(owner, doc["batch_id"], doc["document_id"])
                except (NotFound, ReportJsonError):
                    report = {}
            reports[doc.get("document_id") or f"pending:{doc['name']}"] = report

        outcomes: Counter = Counter()
        for doc in docs:
            key = doc.get("document_id") or f"pending:{doc['name']}"
            outcomes[outcome_label(reports[key], doc)] += 1
        lines = ["# FundLex 合同修改结果总览", "", f"- 任务：{safe(summary['name'])}",
                 f"- 合同总数：{summary['total']}", f"- 已接收：{summary['uploaded']}",
                 f"- 尚未上传：{summary['pending_upload']}", f"- 接收失败：{summary['rejected']}"]
        counts = "；".join(f"{label} {outcomes.get(label, 0)} 份" for label in OUTCOME_LABELS)
        extras = "；".join(f"{label} {outcomes[label]} 份"
                           for label in ("处理进行中", "未接收") if outcomes.get(label))
        lines += [f"- 处理结论：{counts}" + (f"；{extras}" if extras else ""),
                  "", "## 每份合同的修改情况", "",
                  "下表逐份列出合同改了几处、涉及哪些条款；逐处「改了什么地方、改之前 / 改之后、"
                  "对应指引哪一条」的对照见结果包内「逐份修改说明/<合同名>/（修改说明）.csv」。", "",
                  "「版本」列说明交付包里的最终版来自哪里，以及附带几份修订痕迹文件：", "",
                  "- **引擎全量**：未在工作台逐条选择，最终版与引擎结果一致；"
                  "附「（全量痕迹版）」，即引擎打算做的全部改动。",
                  "- **按人工选择**：在工作台把部分修订改成了「不接受」，最终版按该选择生成；"
                  "附「（全量痕迹版）」和「（选择修订版）」两份 —— 后者只保留你接受的修订，"
                  "接受它的全部修订即可得到最终版。", "",
                  "| 合同文件 | 交付完整性 | 版本 | 修改处数 | 涉及条款 |",
                  "| --- | --- | --- | --- | --- |"]
        for doc in docs:
            report = reports[doc.get("document_id") or f"pending:{doc['name']}"]
            count = edit_count(report)
            detail = summary_detail(report) if report else "—"
            downloads = doc.get("downloads") or {}
            # A reviewed contract ships a second revision file only when the review
            # actually turned something down; otherwise the engine redline already
            # is the record of the choice.
            reviewed = "selected_redline" in downloads
            lines.append("| " + " | ".join([
                safe(doc["name"]),
                # 交付完整性走单一事实源的人读映射（未知枚举兜底不透传英文）。
                safe(delivery_text(report, doc)),
                "按人工选择" if reviewed else "引擎全量",
                str(count), safe(detail)]) + " |")
        failed = [doc for doc in docs
                  if outcome_label(reports[doc.get("document_id") or f"pending:{doc['name']}"], doc) == "失败"]
        if failed:
            lines += ["", "## 需要重新提交或人工处理的合同", ""]
            for doc in failed:
                lines.append(f"- 《{safe(doc['name'])}》处理未产出可用结果，未包含可交付文件。"
                             "建议：在工作台重新上传该合同再试一次；若多次失败，"
                             "请联系支持并提供任务名称与该合同文件名。")
        failed_upload = [doc for doc in docs if doc["upload_status"] == "rejected"]
        if failed_upload:
            lines += ["", "## 未接收的文件", ""]
            for doc in failed_upload:
                lines.append(f"- 《{safe(doc['name'])}》未通过接收校验，未进入处理；"
                             "请修正文件后重新上传。")
        return "\n".join(lines) + "\n"
