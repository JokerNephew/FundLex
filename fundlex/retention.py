"""Bounded retention for the local store's derived-data namespaces (B13 F5).

Model checkpoints (``<root>/checkpoints/<document id>/<query sha256>.json``)
and JSONL trace files previously grew without any bound: on the production
host that meant 26,700 checkpoint files / 207 MB and 184 MB of traces with no
rotation (FL-D557).  This module is the safety policy:

* **Only our own filenames are touched.**  A checkpoint file must live in a
  32-hex directory (store document ids) and match the 64-hex ``*.json``
  naming of ``ModelCheckpoints._path``.  Everything else — other shapes,
  symlinks, other namespaces — is skipped.  Deleting the wrong thing is
  impossible; *not* deleting is always acceptable.
* **Fail-closed.**  A filesystem error on one entry skips that entry; nothing
  escalates, so a pruning failure can never damage a running job.
* **Env-configurable with conservative defaults.**  Each dimension can be
  disabled independently.

Scheduling happens lazily inside the recall worker loop
(``jobs.Worker._prune_storage``), next to the established
``_reap_stale_workspaces`` cleanup.  No extra systemd unit is required, the
same behaviour covers the dev profile, and an exception can never take the
worker down.  Ops notes: ``docs/DEPLOYMENT_PARAMETERS.md`` § 检查点与 trace
保留策略.

Environment
-----------
``FUNDLEX_CHECKPOINT_MAX_AGE_DAYS`` (default ``45``; ``<= 0`` disables)
    Remove checkpoint JSON files older than this many days by mtime.
``FUNDLEX_CHECKPOINT_MAX_FILES`` (default ``50000``; ``<= 0`` disables)
    Hard cap on surviving checkpoint files; beyond the cap the oldest files
    (by mtime) are removed first.
``FUNDLEX_RETENTION_INTERVAL_SECONDS`` (default ``21600`` = 6 h)
    Minimum interval between sweeps inside the worker loop.  ``0`` forces a
    sweep on every loop turn (useful for one-shot ops runs).
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Any

_LOGGER = logging.getLogger("fundlex.retention")

_CHECKPOINT_DOC_DIR = re.compile(r"[0-9a-f]{32}\Z")
_CHECKPOINT_FILE = re.compile(r"[0-9a-f]{64}\.json\Z")

DEFAULT_MAX_AGE_DAYS = 45
DEFAULT_MAX_FILES = 50000
DEFAULT_INTERVAL_SECONDS = 6 * 60 * 60


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw.strip())
    except ValueError:
        _LOGGER.warning("invalid %s=%r; falling back to %d", name, raw, default)
        return default


def checkpoint_retention_policy() -> tuple[int, int]:
    """``(max age days, max file count)``; each value ``<= 0`` is disabled."""
    return (_env_int("FUNDLEX_CHECKPOINT_MAX_AGE_DAYS", DEFAULT_MAX_AGE_DAYS),
            _env_int("FUNDLEX_CHECKPOINT_MAX_FILES", DEFAULT_MAX_FILES))


def retention_interval_seconds() -> float:
    return float(_env_int("FUNDLEX_RETENTION_INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS))


def prune_checkpoints(root: Path, *, now: float | None = None,
                      max_age_days: int | None = None, max_files: int | None = None) -> dict[str, Any]:
    """Apply the checkpoint retention policy under ``root``.

    Returns simple counters; never raises for an unreadable or undeletable
    entry — a pruning miss costs disk, not correctness.
    """
    stats: dict[str, Any] = {"scanned": 0, "removed_files": 0, "removed_dirs": 0,
                             "removed_bytes": 0, "skipped": 0}
    root = Path(root)
    base = root / "checkpoints"
    if max_age_days is None or max_files is None:
        policy_age, policy_files = checkpoint_retention_policy()
        if max_age_days is None:
            max_age_days = policy_age
        if max_files is None:
            max_files = policy_files
    try:
        if not base.is_dir():
            return stats
        doc_dirs = sorted(base.iterdir())
    except OSError:
        return stats
    now = time.time() if now is None else now
    cutoff = (now - max_age_days * 86400) if max_age_days and max_age_days > 0 else None
    survivors: list[tuple[float, Path]] = []
    for doc_dir in doc_dirs:
        try:
            if doc_dir.is_symlink() or not doc_dir.is_dir() or not _CHECKPOINT_DOC_DIR.fullmatch(doc_dir.name):
                stats["skipped"] += 1
                continue
            entries = list(doc_dir.iterdir())
        except OSError:
            stats["skipped"] += 1
            continue
        for entry in entries:
            try:
                if entry.is_symlink() or not entry.is_file() or not _CHECKPOINT_FILE.fullmatch(entry.name):
                    stats["skipped"] += 1
                    continue
                mtime = entry.stat().st_mtime
            except OSError:
                # Vanished or unreadable between listdir and stat: skip, never delete.
                stats["skipped"] += 1
                continue
            stats["scanned"] += 1
            if cutoff is not None and mtime < cutoff:
                _remove(entry, stats)
            else:
                survivors.append((mtime, entry))
    if max_files and max_files > 0 and len(survivors) > max_files:
        survivors.sort()
        for _, entry in survivors[:len(survivors) - max_files]:
            _remove(entry, stats)
    # Clean up only directories that are ours and are now empty.
    try:
        doc_dirs = sorted(base.iterdir())
    except OSError:
        return stats
    for doc_dir in doc_dirs:
        try:
            if doc_dir.is_symlink() or not doc_dir.is_dir() or not _CHECKPOINT_DOC_DIR.fullmatch(doc_dir.name):
                continue
            next(doc_dir.iterdir())
            continue
        except StopIteration:
            pass
        except OSError:
            continue
        try:
            doc_dir.rmdir()
            stats["removed_dirs"] += 1
        except OSError:
            continue
    return stats


def _remove(entry: Path, stats: dict[str, Any]) -> None:
    try:
        size = entry.stat().st_size
        entry.unlink()
    except OSError:
        stats["skipped"] += 1
        return
    stats["removed_files"] += 1
    stats["removed_bytes"] += size
