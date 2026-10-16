"""Persistent business tasks over the existing worker's technical batches.

The immutable manifest is the source of task size. Document publication and
task association share one transaction, so workers cannot see orphan batches.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from collections import Counter
from datetime import datetime, timezone

from .recall import ENGINE_ID as RECALL_ENGINE_ID
from .store import Conflict, NotFound, RunStore, SCHEMA_VERSION, engine_build


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
            for name, definition in {"engine_id": "TEXT NOT NULL DEFAULT ''",
                                     "guide_version_id": "TEXT NOT NULL DEFAULT ''",
                                     "guide_rules_sha256": "TEXT NOT NULL DEFAULT ''"}.items():
                if name not in {row["name"] for row in db.execute("PRAGMA table_info(tasks)")}:
                    db.execute(f"ALTER TABLE tasks ADD COLUMN {name} {definition}")

    @staticmethod
    def _owned(db, owner, task_id):
        row = db.execute("SELECT * FROM tasks WHERE id=? AND owner=?", (task_id, owner)).fetchone()
        if row is None:
            raise NotFound("task not found")
        return row

    def create(self, owner, name, source, files, idempotency_key=None,
               engine_id="", guide_version_id="", guide_rules_sha256=""):
        """Create a task bound to a rule source.

        ``source`` is the bound guide version for the recall-first engine; the
        retired rulesets provide a ``version``/``sha256`` pair instead. Either
        way the binding is part of the request fingerprint.
        """
        binding = [engine_id, guide_version_id, guide_rules_sha256]
        source_version = _source_field(source, "version")
        source_sha256 = _source_field(source, "sha256")
        payload = [name, source_version, source_sha256, files]
        if any(binding):
            # Legacy requests keep their previous fingerprint; a bound engine is
            # part of the identity of a new-style task.
            payload.append(binding)
        fingerprint = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        with self.store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if idempotency_key:
                old = db.execute("SELECT id,request_hash FROM tasks WHERE owner=? AND idempotency_key=?",
                                 (owner, idempotency_key)).fetchone()
                if old:
                    if old["request_hash"] != fingerprint:
                        raise Conflict("TASK_IDEMPOTENCY_CONFLICT")
                    return self._snapshot(db, self._owned(db, owner, old["id"]))
            task_id, now = uuid.uuid4().hex, time.time()
            db.execute("""INSERT INTO tasks(id,owner,name,ruleset_version,ruleset_sha256,engine_id,
                guide_version_id,guide_rules_sha256,idempotency_key,request_hash,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (task_id, owner, name, source_version, source_sha256, engine_id,
                        guide_version_id, guide_rules_sha256, idempotency_key, fingerprint, now, now))
            db.executemany("INSERT INTO task_files(task_id,client_id,ordinal,name,size) VALUES(?,?,?,?,?)",
                           [(task_id, item["client_id"], i, item["name"], item["size"]) for i, item in enumerate(files)])
            return self._snapshot(db, self._owned(db, owner, task_id))

    def _files(self, db, task_id, *, details=True):
        rows = db.execute("""SELECT f.*,d.batch_id,d.status,d.qualification_status,d.delivery_status,
            d.error_code AS document_error,d.source_sha256,d.report_json FROM task_files f
            LEFT JOIN documents d ON d.id=f.document_id WHERE f.task_id=? ORDER BY f.ordinal""", (task_id,)).fetchall()
        result = []
        for row in rows:
            doc = None
            if row["document_id"] and details:
                doc = self.store._document_dict(db, db.execute("SELECT * FROM documents WHERE id=?", (row["document_id"],)).fetchone())
            result.append({"batch_id": row["batch_id"], "document_id": row["document_id"],
                           "client_id": row["client_id"], "name": row["name"], "size": row["size"],
                           "job_status": row["status"] or "not_started", "upload_status": row["upload_status"],
                           "eligibility": row["qualification_status"], "delivery_status": row["delivery_status"] or "not_generated",
                           "execution_mode": (doc or {}).get("execution_mode", "") if doc else "",
                           "error_code": row["document_error"] or row["error_code"],
                           "report_url": doc["report_url"] if doc and row["report_json"] else None,
                           "downloads": doc["download_urls"] if doc else {}, "source_sha256": row["source_sha256"],
                           "reason_codes": self._reasons(row["report_json"], row["document_error"] or row["error_code"]) if details else [],
                           "ordinal": row["ordinal"]})
        return result

    @staticmethod
    def _reasons(raw, error):
        reasons = {error} if error else set()
        report = json.loads(raw) if raw else {}
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
    def _summary(row, docs, *, legacy=False):
        total = len(docs)
        uploaded = sum(d["upload_status"] == "accepted" for d in docs)
        completed = sum(d["job_status"] in {"succeeded", "failed"} for d in docs)
        processing = sum(d["job_status"] in {"leased", "running"} for d in docs)
        status = "completed" if uploaded == total and completed == total else ("paused" if row["paused"] else
                  "running" if processing else "queued" if uploaded > completed else "uploading")
        # A task is legacy once it was produced by a retired engine. The runtime
        # serves the guide-bound engine only, so anything else is read-only
        # history even when it still has a first-class task row.
        legacy = legacy or (row["engine_id"] or "") != RECALL_ENGINE_ID
        return {"id": row["id"], "name": row["name"], "legacy": legacy, "ruleset_version": row["ruleset_version"],
                "ruleset_sha256": row["ruleset_sha256"], "status": status,
                "engine_id": row["engine_id"],
                "guide_snapshot": {"version_id": row["guide_version_id"],
                                   "rules_sha256": row["guide_rules_sha256"]},
                "upload_status": "complete" if uploaded == total else "sealed_incomplete" if row["sealed"] else "partial" if uploaded else "pending",
                "total": total, "uploaded": uploaded, "pending_upload": sum(d["upload_status"] == "pending" for d in docs),
                "rejected": sum(d["upload_status"] == "rejected" for d in docs),
                "queued": sum(d["job_status"] in {"queued", "retry_wait"} for d in docs),
                "processing": processing, "completed": completed, "failed": sum(d["job_status"] == "failed" for d in docs),
                "qualification_counts": dict(Counter(d["eligibility"] or "pending" for d in docs)),
                "delivery_counts": dict(Counter(d["delivery_status"] for d in docs)),
                "created_at": datetime.fromtimestamp(row["created_at"], timezone.utc).isoformat(),
                "updated_at": datetime.fromtimestamp(row["updated_at"], timezone.utc).isoformat(),
                "pause_reason": row["pause_reason"], "summary_url": f"/api/tasks/{row['id']}/report"}

    def _snapshot(self, db, row):
        return self._summary(row, self._files(db, row["id"], details=False))

    def _legacy(self, owner, task_id):
        batch_id = task_id.removeprefix("legacy-")
        with self.store._connect() as db:
            batch = db.execute("""SELECT * FROM batches WHERE id=? AND owner=?
                AND NOT EXISTS(SELECT 1 FROM task_batches WHERE batch_id=batches.id)""", (batch_id, owner)).fetchone()
            if batch is None:
                raise NotFound("task not found")
            docs = []
            for row in db.execute("SELECT * FROM documents WHERE batch_id=? ORDER BY ordinal", (batch_id,)):
                d = self.store._document_dict(db, row)
                docs.append({"batch_id": batch_id, "document_id": row["id"], "client_id": row["id"],
                             "name": row["filename"], "size": row["source_size"], "job_status": row["status"],
                             "upload_status": "accepted", "eligibility": row["qualification_status"],
                             "delivery_status": row["delivery_status"], "error_code": row["error_code"],
                             "report_url": d["report_url"] if row["report_json"] else None, "downloads": d["download_urls"],
                             "source_sha256": row["source_sha256"], "ordinal": row["ordinal"]})
                docs[-1]["reason_codes"] = self._reasons(row["report_json"], row["error_code"])
            task = dict(batch) | {"id": task_id, "name": "历史任务 · " + datetime.fromtimestamp(batch["created_at"], timezone.utc).strftime("%Y-%m-%d %H:%M"),
                                  "paused": batch["status"] == "paused", "sealed": True, "pause_reason": None}
            return self._summary(task, docs, legacy=True), docs

    def get(self, owner, task_id):
        if task_id.startswith("legacy-"):
            return self._legacy(owner, task_id)[0]
        with self.store._connect() as db:
            return self._snapshot(db, self._owned(db, owner, task_id))

    def list(self, owner, **filters):
        with self.store._connect() as db:
            items = [self._snapshot(db, row) for row in db.execute("SELECT * FROM tasks WHERE owner=?", (owner,))]
            legacy_ids = [r["id"] for r in db.execute("SELECT id FROM batches WHERE owner=? AND NOT EXISTS(SELECT 1 FROM task_batches WHERE batch_id=batches.id)", (owner,))]
        items.extend(self._legacy(owner, "legacy-" + bid)[0] for bid in legacy_ids)
        q, state = filters.get("q", "").casefold(), filters.get("status")
        items = [d for d in items if q in d["name"].casefold() and (not state or state == d["status"])]
        return self._page(items, **{k: v for k, v in filters.items() if k in {"sort", "page", "page_size"}})

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

    def documents(self, owner, task_id, **filters):
        if task_id.startswith("legacy-"):
            docs = self._legacy(owner, task_id)[1]
        else:
            with self.store._connect() as db:
                self._owned(db, owner, task_id)
                docs = self._files(db, task_id)
        q = filters.get("q", "").casefold()
        reasons = Counter(code for d in docs for code in d["reason_codes"])
        docs = [d for d in docs if q in d["name"].casefold() and all(not filters.get(k) or
                filters[k] == (d[k] or "pending") for k in ("eligibility", "job_status", "delivery_status", "upload_status"))
                and (not filters.get("error_code") or filters["error_code"] in d["reason_codes"])]
        result = self._page(docs, **{k: v for k, v in filters.items() if k in {"sort", "page", "page_size"}})
        result["reason_options"] = [{"code": code, "count": count} for code, count in sorted(reasons.items())]
        return result

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
                    elif item["name"] != f["name"] or item["size"] != f["size"]:
                        error = "MANIFEST_FILE_MISMATCH"
                    if error:
                        if f is not None:
                            db.execute("UPDATE task_files SET upload_status='rejected',error_code=? WHERE task_id=? AND client_id=?", (error, task_id, item["client_id"]))
                        receipt["error_code"] = error
                        receipts.append(receipt)
                        continue
                    if ordinal == 0:
                        db.execute("""INSERT INTO batches(id,owner,ruleset_version,ruleset_sha256,status,request_hash,
                            created_at,updated_at,engine_build,schema_version,engine_id,guide_version_id,
                            guide_rules_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                   (batch_id, owner, task["ruleset_version"], task["ruleset_sha256"],
                                    "paused" if task["paused"] else "queued",
                                    uuid.uuid4().hex, now, now, build, SCHEMA_VERSION, task["engine_id"],
                                    task["guide_version_id"], task["guide_rules_sha256"]))
                        db.execute("INSERT INTO task_batches VALUES(?,?)", (task_id, batch_id))
                    document_id = uuid.uuid4().hex
                    db.execute("""INSERT INTO documents(id,batch_id,ordinal,filename,source_sha256,source_size,input_key,
                        status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                               (document_id, batch_id, ordinal, f["name"], item["digest"], item["size"], item["key"], "queued", now, now))
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
            return self._snapshot(db, self._owned(db, owner, task_id))

    def report(self, owner, task_id):
        summary = self.get(owner, task_id)
        docs = self.documents(owner, task_id, page_size=100000)["items"]
        def safe(value):
            return str(value or "—").replace("|", "\\|").replace("\r", " ").replace("\n", " ")
        lines = ["# FundLex 任务汇总", "", f"- 任务：{safe(summary['name'])}", f"- 规则版本：{summary['ruleset_version']}",
                 f"- 合同总数：{summary['total']}", f"- 已接收：{summary['uploaded']}", f"- 尚未上传：{summary['pending_upload']}",
                 f"- 接收失败：{summary['rejected']}", f"- 处理结束：{summary['completed']}", f"- 失败关闭：{summary['failed']}",
                 f"- 资格统计：{summary['qualification_counts']}", f"- 交付统计：{summary['delivery_counts']}",
                 "", "处理结束、资格符合和合同可直接使用分别记录；仅交付完整并通过验证的合同开放下载。", "",
                 "| 文件 | 上传 | 处理 | 资格 | 交付 | 原因码 |", "|---|---|---|---|---|---|"]
        lines.extend("| " + " | ".join(safe(d[k]) for k in ("name", "upload_status", "job_status", "eligibility", "delivery_status"))
                     + " | " + safe(", ".join(d["reason_codes"])) + " |" for d in docs)
        actions, candidates = Counter(), Counter()
        for d in docs:
            if not d["document_id"]:
                continue
            try:
                report = self.store.get_report(owner, d["batch_id"], d["document_id"])
            except NotFound:
                continue
            for action in report.get("actions", []):
                if isinstance(action, dict):
                    actions[action.get("status") or action.get("processing_status") or "unknown"] += 1
                    for candidate in action.get("candidates", []):
                        if isinstance(candidate, dict):
                            candidates[candidate.get("status") or candidate.get("result") or "unknown"] += 1
        lines.extend(["", "## 规则与候选核验汇总", "", f"- action 状态：{dict(actions)}", f"- 候选位置状态：{dict(candidates)}"])
        return "\n".join(lines) + "\n"
