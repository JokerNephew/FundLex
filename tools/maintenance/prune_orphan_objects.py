"""Report or remove unreachable files below a RunStore objects directory.

The database is the authority: input documents, published artifacts and custom
guide sources are referenced explicitly.  This tool never deletes a referenced
key, never follows symlinks and defaults to a dry run.  Retention is deliberately
manual so a bad deployment cannot silently destroy recoverable evidence.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from fundlex.store import RunStore


def referenced_keys(store: RunStore) -> set[str]:
    """Object-relative keys the database still points at."""
    keys: set[str] = set()
    with store._connect() as db:
        for row in db.execute("SELECT input_key FROM documents"):
            if row["input_key"]:
                keys.add(str(row["input_key"]))
        for row in db.execute("SELECT object_key FROM artifacts"):
            if row["object_key"]:
                keys.add(str(row["object_key"]))
        try:
            guide_rows = db.execute("SELECT id FROM guide_versions WHERE built_in=0").fetchall()
        except Exception:
            # Historical stores may not have the guide tables yet; they cannot
            # reference source objects either.
            guide_rows = []
        for row in guide_rows:
            keys.add(f"guides/{row['id']}.docx")
    return keys


def scan_orphans(store: RunStore, *, min_age_hours: float = 24.0) -> dict[str, Any]:
    """Return unreachable files and missing referenced files without deleting."""
    root = store.objects.resolve()
    referenced = referenced_keys(store)
    cutoff = time.time() - max(min_age_hours, 0.0) * 3600.0
    orphans: list[dict[str, Any]] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            relative = path.resolve().relative_to(root).as_posix()
            stat = path.stat()
        except (OSError, ValueError):
            continue
        if relative in referenced or stat.st_mtime > cutoff:
            continue
        orphans.append({"key": relative, "size": stat.st_size,
                        "mtime": stat.st_mtime})
    existing = {path.resolve().relative_to(root).as_posix()
                for path in root.rglob("*") if path.is_file() and not path.is_symlink()}
    missing = sorted(key for key in referenced if key not in existing)
    return {"orphans": orphans, "missing": missing,
            "orphan_bytes": sum(item["size"] for item in orphans)}


def prune_orphans(store: RunStore, *, min_age_hours: float = 24.0,
                  apply: bool = False) -> dict[str, Any]:
    """Scan, and optionally delete, unreachable objects."""
    result = scan_orphans(store, min_age_hours=min_age_hours)
    deleted: list[str] = []
    if apply:
        root = store.objects.resolve()
        for item in result["orphans"]:
            path = (root / item["key"]).resolve()
            if not path.is_relative_to(root):
                continue
            try:
                path.unlink()
                deleted.append(item["key"])
            except FileNotFoundError:
                pass
    return result | {"deleted": deleted, "applied": bool(apply)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True,
                        help="RunStore data root (contains objects/ and the database)")
    parser.add_argument("--min-age-hours", type=float, default=24.0)
    parser.add_argument("--apply", action="store_true",
                        help="delete reported orphans; default is dry-run")
    args = parser.parse_args(argv)
    store = RunStore(Path(args.data_dir))
    result = prune_orphans(store, min_age_hours=args.min_age_hours,
                           apply=args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
