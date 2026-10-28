"""Orphan object maintenance is dry-run by default and never deletes live keys."""
from __future__ import annotations

from fundlex.store import RunStore
from tools.maintenance.prune_orphan_objects import prune_orphans, scan_orphans


def test_prune_orphans_keeps_referenced_objects_and_deletes_only_unreachable(tmp_path):
    store = RunStore(tmp_path / "state")
    batch = store.create_batch(owner="alice", ruleset_version="v1",
                               uploads=[("合同.docx", b"contract")])
    with store._connect() as db:
        input_key = db.execute("SELECT input_key FROM documents WHERE batch_id=?",
                               (batch["id"],)).fetchone()["input_key"]
    orphan_key, _, _ = store.stage(b"orphan")
    old = 0.0
    (store.object_path(orphan_key)).touch()
    import os
    os.utime(store.object_path(orphan_key), (old, old))

    report = scan_orphans(store, min_age_hours=1)
    assert [item["key"] for item in report["orphans"]] == [orphan_key]
    assert report["missing"] == []
    assert store.object_path(input_key).is_file()

    dry = prune_orphans(store, min_age_hours=1, apply=False)
    assert dry["applied"] is False and dry["deleted"] == []
    assert store.object_path(orphan_key).is_file()

    applied = prune_orphans(store, min_age_hours=1, apply=True)
    assert applied["deleted"] == [orphan_key]
    assert not store.object_path(orphan_key).exists()
    assert store.object_path(input_key).is_file()
