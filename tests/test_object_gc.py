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


def test_compare_and_guide_generation_artifacts_survive_gc(tmp_path):
    """FL-D948 dual counter-example: live compare/selection/gg artifacts must
    never be deleted by ``--apply``, even when aged past the retention window."""
    store = RunStore(tmp_path / "state")
    # 触建 compare/gg 侧 schema（两类表由各自 Store 惰性建）
    from fundlex.compare.store import CompareStore
    from fundlex.guide_generation.store import GuideGenerationStore
    CompareStore(store)
    GuideGenerationStore(store).ensure_schema()
    sha = "0" * 64
    live_keys: list[str] = []
    binds = {
        "compare_pair_files": ("p1", "left", "c1", "a.docx", 12, "accepted"),
        "compare_artifacts": ("p1", "merged", sha, 12),
        "compare_selection_artifacts": ("p1", 1, "accept", sha, 12, 0, sha, sha, sha, sha, "{}"),
        "gg_artifacts": ("r1", "guide", sha, 12),
    }

    def _sql(table: str, key: str) -> str:
        if table == "compare_pair_files":
            return ("INSERT INTO compare_pair_files(pair_id,side,client_id,filename,size,upload_status,"
                    f"object_key,created_at,updated_at) VALUES(?,?,?,?,?,?,'{key}',0,0)")
        if table == "compare_artifacts":
            return ("INSERT INTO compare_artifacts(pair_id,kind,object_key,sha256,size)"
                    f" VALUES(?,?,'{key}',?,?)")
        if table == "compare_selection_artifacts":
            return ("INSERT INTO compare_selection_artifacts(pair_id,version,kind,object_key,sha256,size,"
                    "selection_epoch,decision_hash,result_sha256,left_source_sha256,right_source_sha256,"
                    f"report_json,created_at) VALUES(?,?,?,'{key}',?,?,?,?,?,?,?,?,0)")
        return ("INSERT INTO gg_artifacts(run_id,kind,object_key,sha256,size,created_at)"
                f" VALUES(?,?,'{key}',?,?,0)")

    with store._connect() as db:
        # FK 父行先行（compare_pairs/gg_runs，及其上层 compare_tasks）
        db.execute("INSERT INTO compare_tasks(id,owner,name,status,sealed,created_at,updated_at,request_hash)"
                   " VALUES('t1','alice','x','done',0,0,0,'h')")
        db.execute("INSERT INTO compare_pairs(id,task_id,ordinal,client_pair_id,label,status,created_at,updated_at)"
                   " VALUES('p1','t1',1,'c','x','done',0,0)")
        db.execute("INSERT INTO gg_runs(id,owner,created_at,updated_at) VALUES('r1','alice',0,0)")
        for table, sql_bind in binds.items():
            key = f"live/{table}.bin"
            (store.objects / key).parent.mkdir(parents=True, exist_ok=True)
            (store.objects / key).write_bytes(b"live-artifact")
            live_keys.append(key)
            db.execute(_sql(table, key), sql_bind)
    import os
    for key in live_keys:
        os.utime(store.object_path(key), (0.0, 0.0))
    orphan_key, _, _ = store.stage(b"orphan")
    os.utime(store.object_path(orphan_key), (0.0, 0.0))

    report = scan_orphans(store, min_age_hours=1)
    assert [item["key"] for item in report["orphans"]] == [orphan_key]
    applied = prune_orphans(store, min_age_hours=1, apply=True)
    assert applied["deleted"] == [orphan_key]
    assert not store.object_path(orphan_key).exists()
    for key in live_keys:
        assert store.object_path(key).is_file(), f"live artifact wrongly deleted: {key}"
