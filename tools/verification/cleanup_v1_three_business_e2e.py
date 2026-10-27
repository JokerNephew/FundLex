#!/usr/bin/env python3
"""Precisely remove one recorded e2e-v1ws account. Dry-run unless --execute.

Run with the project's Python (sudo when the deployment env is root-only).
Only the supplied account and its verified ownership graph are eligible. Shared
corpus/index/snapshot tables are never changed. No credential/payload is printed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sqlite3
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit


class UnsafeCleanup(RuntimeError):
    pass


PROTECTED = frozenset({
    "gg_contracts", "gg_contract_versions", "gg_clauses", "gg_snapshots",
    "gg_snapshot_members", "gg_corpus_state", "integration_events",
})
ACTIVE = frozenset({"queued", "running", "leased", "retry_wait", "uploading", "pending", "parsing"})
NAME = re.compile(r"e2e-v1ws-[a-z0-9]{12,32}(?:-other)?\Z")


def read_env(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        # Parse quoting without shell evaluation or environment expansion.
        if value.lstrip().startswith(('{', '[')):
            result[key.strip()] = value.strip()
            continue
        parts = shlex.split(value, comments=True)
        if len(parts) > 1:
            raise UnsafeCleanup("ENV_VALUE_INVALID")
        result[key.strip()] = parts[0] if parts else ""
    return result


class Database:
    def __init__(self, conn, *, mysql=False):
        self.conn, self.mysql = conn, mysql
        self.schema = {}
        if mysql:
            rows = self.query("SELECT TABLE_NAME t,COLUMN_NAME c FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()")
        else:
            conn.row_factory = sqlite3.Row
            rows = []
            for row in self.query("SELECT name FROM sqlite_master WHERE type='table'"):
                name = row["name"]
                if re.fullmatch(r"[a-zA-Z0-9_]+", name):
                    rows += [{"t": name, "c": item["name"]} for item in self.query(f"PRAGMA table_info(`{name}`)")]
        for row in rows:
            if re.fullmatch(r"[a-zA-Z0-9_]+", row["t"]):
                self.schema.setdefault(row["t"], set()).add(row["c"])

    def query(self, sql, args=()):
        cur = self.conn.cursor()
        try:
            cur.execute(sql.replace("?", "%s") if self.mysql else sql, tuple(args))
            return [dict(row) for row in cur.fetchall()] if cur.description else []
        finally:
            cur.close()

    def begin(self):
        if self.mysql:
            self.conn.begin()
        else:
            self.conn.execute("BEGIN IMMEDIATE")

    def rows(self, table, where="1=0", args=(), *, lock=False):
        if table not in self.schema:
            return []
        suffix = " FOR UPDATE" if lock and self.mysql else ""
        return self.query(f"SELECT * FROM `{table}` WHERE {where}" + suffix, args)


def connect(raw: dict[str, str]) -> Database:
    parsed = urlsplit(raw.get("FUNDLEX_DATABASE_URL", ""))
    if parsed.scheme not in {"mysql", "mysql+pymysql"} or not parsed.hostname or not parsed.path.lstrip("/"):
        raise UnsafeCleanup("MYSQL_DSN_REQUIRED")
    import pymysql
    conn = pymysql.connect(
        host=parsed.hostname, port=parsed.port or 3306,
        user=unquote(parsed.username or ""), password=unquote(parsed.password or ""),
        database=unquote(parsed.path.lstrip("/")), charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
        connect_timeout=10, read_timeout=30, write_timeout=30,
    )
    return Database(conn, mysql=True)


def condition(column, values):
    values = sorted(set(values))
    return (f"`{column}` IN ({','.join('?' for _ in values)})", values) if values else ("1=0", [])


def safe_object(root: Path, key: str) -> Path:
    pure = PurePosixPath(key)
    if not key or pure.is_absolute() or ".." in pure.parts or "\\" in key or ":" in key:
        raise UnsafeCleanup("OBJECT_PATH_REJECTED")
    target = root.joinpath(*pure.parts)
    if not target.resolve().is_relative_to(root) or target == root:
        raise UnsafeCleanup("OBJECT_PATH_ESCAPE")
    current = root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeCleanup("OBJECT_SYMLINK_REJECTED")
    return target


def cleanup(db: Database, *, username: str, evidence: dict, objects: Path, execute=False) -> dict:
    if not NAME.fullmatch(username) or evidence.get("username") != username:
        raise UnsafeCleanup("EXACT_E2E_USERNAME_REQUIRED")
    if not objects.is_dir() or objects.is_symlink():
        raise UnsafeCleanup("OBJECT_ROOT_REQUIRED")
    objects = objects.resolve()
    db.begin()
    try:
        users = db.rows("users", "username=?", [username], lock=True)
        if not users:
            db.conn.rollback()
            return {"username_present": False, "executed": False, "second_check": {"users": 0}}
        if len(users) != 1 or users[0]["role"] != "member":
            raise UnsafeCleanup("MEMBER_ACCOUNT_REQUIRED")
        uid = users[0]["id"]
        if evidence.get("uid") != uid:
            raise UnsafeCleanup("UID_EVIDENCE_MISMATCH")
        scopes, selected = {}, {}

        def add(table, column, values):
            if table in PROTECTED:
                raise UnsafeCleanup("SHARED_TABLE_REJECTED")
            if table not in db.schema:
                return []
            where, args = condition(column, values)
            rows = db.rows(table, where, args, lock=True)
            scopes[table], selected[table] = (where, args), rows
            for row in rows:
                for field in ("owner", "owner_user_id", "user_id"):
                    if field in row and row[field] not in (uid, "", None):
                        raise UnsafeCleanup("CHILD_OWNERSHIP_MISMATCH")
            return rows

        tasks = add("tasks", "owner", [uid])
        compares = add("compare_tasks", "owner", [uid])
        runs = add("gg_runs", "owner", [uid])
        task_ids = [r["id"] for r in tasks]
        compare_ids = [r["id"] for r in compares]
        run_ids = [r["id"] for r in runs]
        for kind, ids in (("revision", task_ids), ("compare", compare_ids), ("generation", run_ids)):
            if set(evidence.get("task_ids", {}).get(kind, [])) != set(ids):
                raise UnsafeCleanup("TASK_EVIDENCE_MISMATCH")
        batches = add("batches", "owner", [uid])
        batch_ids = [r["id"] for r in batches]
        links = add("task_batches", "task_id", task_ids)
        if any(r["batch_id"] not in batch_ids for r in links):
            raise UnsafeCleanup("BATCH_OWNERSHIP_MISMATCH")
        for row in db.rows("task_batches", *condition("batch_id", batch_ids), lock=True):
            if row["task_id"] not in task_ids:
                raise UnsafeCleanup("BATCH_SHARED_WITH_OTHER_TASK")
        docs = add("documents", "batch_id", batch_ids)
        doc_ids = [r["id"] for r in docs]
        files = add("task_files", "task_id", task_ids)
        if any(r.get("document_id") and r["document_id"] not in doc_ids for r in files):
            raise UnsafeCleanup("DOCUMENT_OWNERSHIP_MISMATCH")
        for row in db.rows("task_files", *condition("document_id", doc_ids), lock=True):
            if row["task_id"] not in task_ids:
                raise UnsafeCleanup("DOCUMENT_SHARED_WITH_OTHER_TASK")
        add("artifacts", "document_id", doc_ids)
        pairs = add("compare_pairs", "task_id", compare_ids)
        pair_ids = [r["id"] for r in pairs]
        for table in ("compare_selection_artifacts", "compare_selection_drafts", "compare_artifacts", "compare_pair_files"):
            add(table, "pair_id", pair_ids)
        guides = add("guide_versions", "owner", [uid])
        if any(r.get("built_in") for r in guides):
            raise UnsafeCleanup("BUILTIN_GUIDE_REJECTED")
        guide_ids = [r["id"] for r in guides]
        add("guide_jobs", "guide_version_id", guide_ids)
        add("guide_config", "owner", [uid])
        for table, columns in db.schema.items():
            if table.startswith("gg_") and table not in PROTECTED and "run_id" in columns:
                add(table, "run_id", run_ids)
        candidate_ids = [r["candidate_guide_id"] for r in selected.get("gg_candidate_guides", [])]
        for row in db.rows("gg_candidate_guides", "owner=?", [uid], lock=True):
            if row["run_id"] not in run_ids:
                raise UnsafeCleanup("CANDIDATE_OWNERSHIP_MISMATCH")
        for row in db.rows("gg_candidate_versions", *condition("candidate_guide_id", candidate_ids), lock=True):
            if row["run_id"] not in run_ids:
                raise UnsafeCleanup("CANDIDATE_VERSION_OWNERSHIP_MISMATCH")
        drafts = add("feishu_drafts", "owner_user_id", [uid])
        draft_ids = [r["id"] for r in drafts]
        for row in db.rows("feishu_drafts", *condition("task_id", task_ids), lock=True):
            if row["id"] not in draft_ids:
                raise UnsafeCleanup("DRAFT_OWNERSHIP_MISMATCH")
        add("feishu_draft_files", "draft_id", draft_ids)
        add("task_channels", "task_id", task_ids)
        add("integration_outbox", "aggregate_id", task_ids + draft_ids)
        for table in ("integration_binding_codes", "integration_oauth_states", "external_identities", "sessions"):
            add(table, "user_id", [uid])
        add("users", "id", [uid])

        for table in ("documents", "batches", "compare_tasks", "compare_pairs", "gg_runs", "gg_jobs", "gg_steps", "guide_jobs", "integration_outbox"):
            if any(r.get("status") in ACTIVE for r in selected.get(table, [])):
                raise UnsafeCleanup("ACTIVE_JOBS_REFUSE_CLEANUP")

        keys = {f"guides/{gid}.docx" for gid in guide_ids}
        for rows in selected.values():
            for row in rows:
                for field in ("object_key", "input_key", "storage_key"):
                    if row.get(field):
                        keys.add(row[field])
        # Artifacts from immutable/human candidate versions may no longer be in
        # gg_artifacts. Enumerate only this exact, verified run directory.
        run_dirs, directories = [], []
        for run_id in run_ids:
            if not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", run_id):
                raise UnsafeCleanup("RUN_ID_REJECTED")
            run_dir = safe_object(objects, f"guide_generation/{run_id}")
            run_dirs.append(run_dir)
            if run_dir.exists():
                for directory, dirs, filenames in os.walk(run_dir, followlinks=False):
                    for name in dirs + filenames:
                        item = Path(directory) / name
                        if item.is_symlink():
                            raise UnsafeCleanup("OBJECT_SYMLINK_REJECTED")
                    directories.append(Path(directory))
                    keys.update(str((Path(directory) / name).relative_to(objects)) for name in filenames)
        paths = []
        for key in sorted(keys):
            pure = PurePosixPath(key)
            if pure.parts and (pure.parts[0] in {"corpus", "snapshots", "contract_index"}
                               or (pure.parts[0] == "guide_generation" and (len(pure.parts) < 3 or pure.parts[1] not in run_ids))):
                raise UnsafeCleanup("SHARED_OBJECT_REJECTED")
            path = safe_object(objects, key)
            if path.exists() and not path.is_file():
                raise UnsafeCleanup("OBJECT_NOT_REGULAR_FILE")
            # Refuse even an accidentally shared object key referenced elsewhere.
            for table, columns in db.schema.items():
                for column in {"object_key", "input_key", "storage_key"} & columns:
                    where, args = scopes.get(table, ("1=0", []))
                    if db.rows(table, f"`{column}`=? AND NOT ({where})", [key, *args], lock=True):
                        raise UnsafeCleanup("OBJECT_REFERENCED_BY_OTHER_OWNER")
            paths.append(path)
        counts = {table: len(rows) for table, rows in selected.items()}
        summary = {"username_present": True, "executed": bool(execute), "counts": counts,
                   "object_files": sum(path.is_file() for path in paths),
                   "protected_tables_modified": 0}
        if not execute:
            db.conn.rollback()
            return summary
        # Child-first order, with parents deferred until all dependent rows go.
        tail = ["gg_candidate_versions", "gg_candidate_guides", "gg_runs", "task_files", "task_batches",
                "documents", "batches", "tasks", "compare_pairs", "compare_tasks", "feishu_drafts", "guide_versions", "users"]
        order = [t for t in scopes if t not in tail] + [t for t in tail if t in scopes]
        for table in order:
            where, args = scopes[table]
            db.query(f"DELETE FROM `{table}` WHERE {where}", args)
        remaining = {table: len(db.rows(table, *scope)) for table, scope in scopes.items()}
        if any(remaining.values()):
            raise UnsafeCleanup("DATABASE_SECOND_CHECK_FAILED")
        db.conn.commit()
        removed = 0
        for path in paths:
            # Revalidate after DB commit, immediately before every unlink.
            safe_object(objects, str(path.relative_to(objects)))
            if path.is_file():
                path.unlink()
                removed += 1
        for directory in sorted(set(directories), key=lambda p: len(p.parts), reverse=True):
            safe_object(objects, str(directory.relative_to(objects)))
            directory.rmdir()  # only empty, enumerated run-owned directories
        summary.update(objects_removed=removed, second_check=remaining,
                       object_files_remaining=sum(p.exists() for p in paths),
                       run_directories_remaining=sum(p.exists() for p in run_dirs))
        return summary
    except BaseException:
        db.conn.rollback()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True)
    parser.add_argument("--evidence", type=Path, required=True, help="Runner result.json (uid and exact task IDs required)")
    parser.add_argument("--env-file", type=Path, default=Path("/etc/fundlex-recall.env"))
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    db = None
    try:
        raw = read_env(args.env_file)
        if not raw.get("FUNDLEX_DATA_DIR"):
            raise UnsafeCleanup("DATA_DIR_REQUIRED")
        evidence = json.loads(args.evidence.read_text())
        db = connect(raw)
        print(json.dumps(cleanup(db, username=args.username, evidence=evidence,
                                 objects=Path(raw["FUNDLEX_DATA_DIR"]) / "objects", execute=args.execute), sort_keys=True))
    except Exception as exc:
        # Database/URL exceptions can contain credentials. Never print them.
        code = str(exc) if isinstance(exc, UnsafeCleanup) else type(exc).__name__
        print(json.dumps({"executed": False, "error_code": code}))
        return 1
    finally:
        if db is not None:
            db.conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
