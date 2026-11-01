"""Bounded-retention sweeps only touch their own namespace (B13 F5 / FL-D557)."""

from __future__ import annotations

import os
import time
from pathlib import Path

from fundlex import retention


def _checkpoint(root: Path, doc_dir: str, name: str, *, age_days: float = 1.0, size: int = 16) -> Path:
    path = root / "checkpoints" / doc_dir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    mtime = time.time() - age_days * 86400
    os.utime(path, (mtime, mtime))
    return path


DOC_A = "a" * 32
DOC_B = "b" * 32
FILE_1 = "1" * 64 + ".json"
FILE_2 = "2" * 64 + ".json"
FILE_3 = "3" * 64 + ".json"


def test_age_based_pruning_removes_only_old_checkpoint_files(tmp_path):
    old = _checkpoint(tmp_path, DOC_A, FILE_1, age_days=90)
    fresh = _checkpoint(tmp_path, DOC_A, FILE_2, age_days=1)
    foreign_dir = tmp_path / "checkpoints" / "not-a-document-id"
    foreign_dir.mkdir(parents=True)
    foreign_file = foreign_dir / "keep.txt"
    foreign_file.write_text("foreign", encoding="utf-8")
    stray = tmp_path / "checkpoints" / DOC_B / "notes.txt"
    stray.parent.mkdir(parents=True)
    stray.write_text("stray", encoding="utf-8")

    stats = retention.prune_checkpoints(tmp_path, max_age_days=45, max_files=0)
    assert not old.exists() and fresh.exists()
    assert foreign_file.exists() and stray.exists()
    # DOC_A still holds the fresh checkpoint; the stray filename keeps DOC_B.
    assert (tmp_path / "checkpoints" / DOC_A).is_dir()
    assert (tmp_path / "checkpoints" / DOC_B).is_dir()
    assert stats["removed_files"] == 1 and stats["removed_bytes"] == 16
    assert stats["skipped"] >= 2  # foreign dir + stray file


def test_empty_checkpoint_dirs_are_removed_but_foreign_dirs_stay(tmp_path):
    old = _checkpoint(tmp_path, DOC_A, FILE_1, age_days=90)
    stats = retention.prune_checkpoints(tmp_path, max_age_days=45, max_files=0)
    assert not old.exists()
    assert not (tmp_path / "checkpoints" / DOC_A).exists()
    assert stats["removed_dirs"] == 1


def test_count_cap_removes_oldest_first(tmp_path):
    paths = [_checkpoint(tmp_path, DOC_A, f"{number:064x}.json", age_days=50 - number)
             for number in range(6)]
    # Ages 45..50 days: all fresh enough; the cap keeps the 2 newest (mtime).
    stats = retention.prune_checkpoints(tmp_path, max_age_days=60, max_files=2)
    surviving = {path.name for path in paths if path.exists()}
    assert surviving == {paths[4].name, paths[5].name}
    assert stats["removed_files"] == 4


def test_disabled_dimensions_delete_nothing(tmp_path):
    old = _checkpoint(tmp_path, DOC_A, FILE_1, age_days=9000)
    stats = retention.prune_checkpoints(tmp_path, max_age_days=0, max_files=0)
    assert old.exists() and stats["removed_files"] == 0


def test_symlinks_are_never_touched(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("outside", encoding="utf-8")
    link_dir = tmp_path / "checkpoints" / DOC_A
    link_dir.mkdir(parents=True)
    doc_link = tmp_path / "checkpoints" / DOC_B
    doc_link.symlink_to(link_dir, target_is_directory=True)
    file_link = link_dir / FILE_1
    file_link.symlink_to(outside)

    stats = retention.prune_checkpoints(tmp_path, max_age_days=1, max_files=1)
    assert outside.exists() and file_link.is_symlink() and doc_link.is_symlink()
    assert stats["removed_files"] == 0


def test_per_entry_filesystem_error_is_fail_closed(tmp_path, monkeypatch):
    doomed = _checkpoint(tmp_path, DOC_A, FILE_1, age_days=90)
    keep = _checkpoint(tmp_path, DOC_A, FILE_2, age_days=1)
    original_stat = Path.stat
    state = {"armed": True}

    def flaky_stat(self, *args, **kwargs):
        if state["armed"] and str(self) == str(doomed):
            raise OSError("simulated")
        return original_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", flaky_stat)
    try:
        stats = retention.prune_checkpoints(tmp_path, max_age_days=45, max_files=0)
    finally:
        state["armed"] = False
    assert doomed.exists() and keep.exists()
    assert stats["skipped"] >= 1 and stats["removed_files"] == 0


def test_env_policy_defaults_and_overrides(monkeypatch):
    for name in ("FUNDLEX_CHECKPOINT_MAX_AGE_DAYS", "FUNDLEX_CHECKPOINT_MAX_FILES"):
        monkeypatch.delenv(name, raising=False)
    assert retention.checkpoint_retention_policy() == (45, 50000)
    monkeypatch.setenv("FUNDLEX_CHECKPOINT_MAX_AGE_DAYS", "7")
    monkeypatch.setenv("FUNDLEX_CHECKPOINT_MAX_FILES", "abc")
    assert retention.checkpoint_retention_policy() == (7, 50000)


def test_worker_sweep_interval_gating(tmp_path, monkeypatch):
    from fundlex.jobs import Worker
    from fundlex.store import RunStore

    store = RunStore(tmp_path / "state")
    worker = Worker(store)
    old = _checkpoint(store.root, DOC_A, FILE_1, age_days=90)

    monkeypatch.setenv("FUNDLEX_RETENTION_INTERVAL_SECONDS", "3600")
    now = time.time()
    worker._prune_storage(now)
    assert not old.exists()
    second = _checkpoint(store.root, DOC_A, FILE_2, age_days=90)
    worker._prune_storage(now + 10)  # inside the interval: no sweep
    assert second.exists()
    worker._prune_storage(now + 3601)
    assert not second.exists()


def test_worker_sweep_failure_does_not_break_loop(tmp_path, monkeypatch):
    from fundlex.jobs import Worker
    from fundlex.store import RunStore

    worker = Worker(RunStore(tmp_path / "state"))
    monkeypatch.setattr("fundlex.retention.prune_checkpoints",
                        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setenv("FUNDLEX_RETENTION_INTERVAL_SECONDS", "0")
    worker._prune_storage(time.time())  # must not raise
    assert worker._last_retention_sweep > 0
