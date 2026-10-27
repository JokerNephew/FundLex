"""Owner-wide metadata aggregation, without bounded source-list stitching.

Only metadata is read (never contract bodies, reports or corpus text). All source
rows for the owner participate in counts and filtering before pagination. SQL is
deliberately adapter-portable; optional modules are omitted explicitly, while
database failures propagate rather than silently returning partial counts.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from typing import Literal

from fastapi import Depends, HTTPException, Query


def _iso(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _attention(code, label):
    return {"code": code, "label": label}


def _item(row, kind, name, status, phase, count, attention, *, terminal=False):
    group = "attention" if attention else "completed" if terminal else "active"
    return {
        "id": row["id"], "kind": kind, "name": name,
        "status": status, "phase": phase, "status_group": group,
        "created_at": _iso(row["created_at"]), "updated_at": _iso(row["updated_at"]),
        "scale": {"value": count, "unit": {
            "revision": "份合同", "compare": "组合同", "generation": "份法规"}[kind]},
        "attention": attention,
    }


def _revision(row, docs):
    total = len(docs)
    uploaded = sum(d["upload_status"] == "accepted" for d in docs)
    finished = sum(d["job_status"] in {"succeeded", "failed"} for d in docs)
    processing = sum(d["job_status"] in {"leased", "running"} for d in docs)
    status = ("completed" if total and uploaded == finished == total else
              "paused" if row["paused"] else "running" if processing else
              "queued" if uploaded > finished else "uploading")
    attention = []
    if row["paused"]:
        attention.append(_attention("paused", "任务已暂停"))
    if any(d["upload_status"] == "pending" for d in docs):
        attention.append(_attention("upload_pending", "待补传合同"))
    if any(d["upload_status"] == "rejected" for d in docs):
        attention.append(_attention("upload_rejected", "上传被拒绝"))
    if any(d["job_status"] == "failed" for d in docs):
        attention.append(_attention("failed", "存在处理失败"))
    if any(d["job_status"] == "succeeded" and
           d["qualification_status"] != "excluded_by_fund_type" and
           d["delivery_status"] in {"incomplete", "not_generated", "complete_with_exceptions"}
           for d in docs):
        attention.append(_attention("delivery_incomplete", "交付存在未完成事项"))
    # A worker update need not touch tasks.updated_at. Use the newest child
    # update so recent ordering reflects actual processing, not just upload.
    row = dict(row)
    row["updated_at"] = max([row["updated_at"]] + [d["updated_at"] or 0 for d in docs])
    item = _item(row, "revision", row["name"], status, status, total, attention,
                 terminal=status == "completed")
    item["progress"] = {"total": total, "uploaded": uploaded, "completed": finished,
                        "processing": processing}
    return item


def owner_items(store, owner, *, generation_available=True, compare_available=True):
    items = []
    with store._connect() as db:
        # A single read snapshot keeps parent/child rows coherent while workers
        # update tasks. BEGIN is accepted by both SQLite and MySQL.
        db.execute("BEGIN")
        tasks = db.execute("SELECT * FROM tasks WHERE owner=?", (owner,)).fetchall()
        docs = defaultdict(list)
        for row in db.execute("""SELECT f.task_id,f.upload_status,d.status AS job_status,
                d.delivery_status,d.qualification_status,d.updated_at
                FROM task_files f JOIN tasks t ON t.id=f.task_id
                LEFT JOIN documents d ON d.id=f.document_id WHERE t.owner=?""", (owner,)):
            docs[row["task_id"]].append(row)
        items.extend(_revision(row, docs[row["id"]]) for row in tasks)

        # Preserve the existing revision list's unassociated historical batches.
        legacy = db.execute("""SELECT b.* FROM batches b WHERE b.owner=? AND NOT EXISTS
                (SELECT 1 FROM task_batches tb WHERE tb.batch_id=b.id)""", (owner,)).fetchall()
        legacy_docs = defaultdict(list)
        for row in db.execute("""SELECT d.batch_id,'accepted' AS upload_status,
                d.status AS job_status,d.delivery_status,d.qualification_status,d.updated_at
                FROM documents d JOIN batches b ON b.id=d.batch_id WHERE b.owner=?
                AND NOT EXISTS (SELECT 1 FROM task_batches tb WHERE tb.batch_id=b.id)""", (owner,)):
            legacy_docs[row["batch_id"]].append(row)
        for row in legacy:
            source = dict(row)
            source.update(id="legacy-" + row["id"], paused=row["status"] == "paused",
                          name="历史任务 · " + _iso(row["created_at"])[:16].replace("T", " "))
            item = _revision(source, legacy_docs[row["id"]])
            item["legacy"] = True
            items.append(item)

        if compare_available:
            pairs = defaultdict(list)
            for row in db.execute("""SELECT p.task_id,p.status,p.updated_at FROM compare_pairs p
                    JOIN compare_tasks t ON t.id=p.task_id WHERE t.owner=?""", (owner,)):
                pairs[row["task_id"]].append(row)
            for row in db.execute("SELECT * FROM compare_tasks WHERE owner=?", (owner,)):
                children = pairs[row["id"]]
                statuses = {p["status"] for p in children}
                attention = []
                if row["status"] == "uploading":
                    attention.append(_attention("upload_pending", "待补传比对合同"))
                if "failed" in statuses or row["status"] == "failed":
                    attention.append(_attention("failed", "存在比对失败"))
                if "incomplete" in statuses or row["status"] == "incomplete":
                    attention.append(_attention("comparison_incomplete", "比对覆盖不完整"))
                source = dict(row)
                source["updated_at"] = max([row["updated_at"]] + [p["updated_at"] for p in children])
                item = _item(source, "compare", row["name"], row["status"], row["status"],
                             len(children), attention,
                             terminal=bool(children) and statuses == {"succeeded"})
                item["progress"] = {"total": len(children), "completed": sum(
                    p["status"] in {"succeeded", "failed", "incomplete"} for p in children)}
                items.append(item)

        if generation_available:
            for row in db.execute("""SELECT r.id,r.title,r.filename,r.status,r.stage,
                    r.created_at,r.updated_at,c.status AS candidate_status,c.updated_at AS candidate_updated_at
                    FROM gg_runs r LEFT JOIN gg_candidate_guides c ON c.run_id=r.id AND c.owner=r.owner
                    WHERE r.owner=?""", (owner,)):
                terminal = row["status"] in {"complete", "completed", "complete_with_unresolved"}
                attention = []
                if row["status"] in {"failed", "paused", "incomplete", "complete_with_unresolved"}:
                    attention.append(_attention(row["status"], {
                        "failed": "生成失败", "paused": "生成已暂停",
                        "incomplete": "生成未完成", "complete_with_unresolved": "存在待解决问题",
                    }[row["status"]]))
                if terminal and row["candidate_status"] not in {"approved", "published"}:
                    attention.append(_attention("candidate_review", "候选指引待审阅"))
                source = dict(row)
                source["updated_at"] = max(row["updated_at"], row["candidate_updated_at"] or 0)
                item = _item(source, "generation", row["title"] or row["filename"],
                             row["status"], row["stage"], 1, attention, terminal=terminal)
                item["candidate_status"] = row["candidate_status"]
                items.append(item)
    return items


def workspace_tasks(store, owner, *, kind="", q="", status="", date_from=None,
                    date_to=None, sort="updated_desc", page=1, page_size=20,
                    generation_available=True, compare_available=True, now=None):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "DATE_RANGE_INVALID")
    items = owner_items(store, owner, generation_available=generation_available,
                        compare_available=compare_available)
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=7)).isoformat()
    stats = {
        "active": sum(i["status_group"] == "active" for i in items),
        "attention": sum(i["status_group"] == "attention" for i in items),
        "recent_completed": sum(i["status_group"] == "completed" and i["updated_at"] >= cutoff
                                for i in items),
        "recent_window_days": 7,
    }
    start = datetime.combine(date_from, datetime_time.min, timezone.utc).isoformat() if date_from else None
    end = datetime.combine(date_to + timedelta(days=1), datetime_time.min, timezone.utc).isoformat() if date_to else None
    query = q.strip().casefold()
    filtered = [item for item in items if
                (not kind or item["kind"] == kind) and
                (not query or query in item["name"].casefold() or query in item["id"].casefold()) and
                (not status or item["status_group"] == status) and
                (not start or item["created_at"] >= start) and
                (not end or item["created_at"] < end)]
    # Stable secondary keys make page boundaries deterministic across kinds.
    filtered.sort(key=lambda i: (i["kind"], i["id"]))
    filtered.sort(key=lambda i: i["name"].casefold() if sort == "name" else
                  i["created_at"] if sort == "created_desc" else i["updated_at"], reverse=sort != "name")
    offset = (page - 1) * page_size
    return {"items": filtered[offset:offset + page_size], "total": len(filtered),
            "page": page, "page_size": page_size, "stats": stats}


def register_workspace_routes(application, store, user_dependency, *, generation_available=True):
    @application.get("/api/workspace/tasks")
    def list_workspace_tasks(
            kind: Literal["", "revision", "compare", "generation"] = "", q: str = "",
            status: Literal["", "active", "attention", "completed"] = "",
            date_from: date | None = None, date_to: date | None = None,
            sort: Literal["updated_desc", "created_desc", "name"] = "updated_desc",
            page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=200),
            user: str = Depends(user_dependency)):
        # Date.max cannot be incremented for the inclusive end boundary.
        if date_to == date.max:
            raise HTTPException(422, "DATE_RANGE_INVALID")
        return workspace_tasks(store, user, kind=kind, q=q, status=status,
                               date_from=date_from, date_to=date_to, sort=sort,
                               page=page, page_size=page_size,
                               generation_available=generation_available)
