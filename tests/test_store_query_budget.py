"""Query-count pins for the store hot paths (B13 F4 / FL-D557).

``list_batches`` used to cost one query per batch plus one per document
(199 executes at 30 batches x 5 documents) and ``get_document`` materialised
the whole batch before answering (13 executes).  The batch/prefetch rewrite
must keep these paths O(1) in the number of batches and documents; these
tests fail if a future refactor reintroduces per-object fetching.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import fundlex.db as dbmod
from fundlex.store import Conflict, NotFound, RunStore


@pytest.fixture
def execute_counter(monkeypatch):
    calls = {"count": 0}
    original = dbmod.Connection.execute

    def counting(self, sql, params=()):
        calls["count"] += 1
        return original(self, sql, params)

    monkeypatch.setattr(dbmod.Connection, "execute", counting)
    return calls


def _populate(store: RunStore, batches: int, docs: int, *, owner: str = "alice") -> None:
    for index in range(batches):
        uploads = [(f"合同{index}x{number}.docx", b"payload-" + bytes([number % 251]) + str(index).encode())
                   for number in range(docs)]
        store.create_batch(owner=owner, ruleset_version="v1", uploads=uploads)


def test_list_batches_query_count_is_bounded_and_constant(tmp_path, execute_counter):
    store = RunStore(tmp_path / "state")
    _populate(store, batches=12, docs=4)

    execute_counter["count"] = 0
    first = store.list_batches("alice")
    first_count = execute_counter["count"]
    assert 0 < first_count <= 8

    _populate(store, batches=12, docs=6)
    execute_counter["count"] = 0
    second = store.list_batches("alice")
    assert execute_counter["count"] == first_count, "listing must not scale with batch/document count"

    # Content parity: the batched assembly must equal the single-batch path.
    by_id = {batch["id"]: batch for batch in second}
    assert len(by_id) == 24
    assert sum(len(batch["documents"]) for batch in second) == 12 * 4 + 12 * 6
    for batch in second:
        assert batch == store.get_batch("alice", batch["id"])


def test_get_document_query_count_is_bounded(tmp_path, execute_counter):
    store = RunStore(tmp_path / "state")
    _populate(store, batches=3, docs=3)
    batch = store.list_batches("alice")[0]
    document = batch["documents"][0]

    execute_counter["count"] = 0
    fetched = store.get_document("alice", batch["id"], document["id"])
    assert execute_counter["count"] <= 6
    assert fetched["id"] == document["id"]

    # NotFound semantics are unchanged by the joined lookup.
    with pytest.raises(NotFound, match="batch not found"):
        store.get_document("mallory", batch["id"], document["id"])
    with pytest.raises(NotFound, match="batch not found"):
        store.get_document("alice", "nonexistent-batch", document["id"])
    with pytest.raises(NotFound, match="document not found"):
        store.get_document("alice", batch["id"], "nonexistent-doc")


def _recall_complete_setup(tmp_path):
    """One recall-complete document with a real final/redline pair on disk."""
    from fundlex.store import sha256_file

    store = RunStore(tmp_path / "state")
    batch = store.create_batch(owner="alice", ruleset_version="v1",
                               uploads=[("contract.docx", b"source-content")])
    document_id = batch["documents"][0]["id"]
    final = tmp_path / "final.docx"
    redline = tmp_path / "redline.docx"
    final.write_bytes(b"final-bytes-" + b"x" * 4096)
    redline.write_bytes(b"redline-bytes-" + b"y" * 4096)
    report = {"engine_id": "recall_first", "schema_version": "3", "execution_mode": "delivery",
              "delivery_status": "complete",
              "output_validation": {"kind": "recall_validated_edits",
                                    "checks": ["package", "revisions", "final_equivalence", "non_target",
                                               "content_verification", "actual_content_verification"],
                                    "final_sha256": sha256_file(final),
                                    "redline_sha256": sha256_file(redline)}}
    job = store.claim()
    assert job and job["id"] == document_id
    store.finish(document_id, job["fencing_token"], report=report,
                 artifacts={"final": final, "redline": redline})
    return store, batch["id"], document_id


class ReadCounter:
    """Counts full-file scans through sha256_file and Path.read_bytes."""

    def __init__(self, monkeypatch):
        from fundlex import store as store_module
        self.sha256_paths: list[str] = []
        self.read_paths = 0
        original_sha = store_module.sha256_file
        original_read = Path.read_bytes

        def sha_and_count(path):
            self.sha256_paths.append(str(path))
            return original_sha(path)

        def read_and_count(path_self, *args, **kwargs):
            self.read_paths += 1
            return original_read(path_self, *args, **kwargs)

        monkeypatch.setattr(store_module, "sha256_file", sha_and_count)
        monkeypatch.setattr(Path, "read_bytes", read_and_count)


def test_read_artifact_reads_each_file_once(tmp_path, monkeypatch):
    store, batch_id, document_id = _recall_complete_setup(tmp_path)
    counts = ReadCounter(monkeypatch)

    data, digest = store.read_artifact("alice", batch_id, document_id, "final")
    import hashlib
    assert digest == hashlib.sha256(data).hexdigest()
    assert data.startswith(b"final-bytes-")
    # One download = one read of the served file + one scan of the pair
    # partner.  Before the merge the served file alone was scanned 3 times.
    assert counts.read_paths == 1
    assert len(counts.sha256_paths) == 1


def test_download_all_verified_cache_skips_pair_rescan(tmp_path, monkeypatch):
    store, batch_id, document_id = _recall_complete_setup(tmp_path)
    counts = ReadCounter(monkeypatch)

    verified: dict[str, str] = {}
    for kind in ("final", "redline"):
        data, digest = store.read_artifact("alice", batch_id, document_id, kind,
                                           verified_hashes=verified)
        verified[kind] = digest
    assert verified["final"] != verified["redline"]
    assert counts.read_paths == 2
    assert len(counts.sha256_paths) == 1, "second pair validation must reuse verified digests"


def test_read_artifact_integrity_fail_closed_unchanged(tmp_path):
    store, batch_id, document_id = _recall_complete_setup(tmp_path)
    final_path, digest = store.get_artifact("alice", batch_id, document_id, "final")
    original = final_path.read_bytes()

    # Corrupted bytes on disk fail closed at the same error site as before.
    final_path.write_bytes(original + b"corruption")
    with pytest.raises(Conflict, match="artifact integrity check failed"):
        store.read_artifact("alice", batch_id, document_id, "final")
    with pytest.raises(Conflict, match="artifact integrity check failed"):
        store.get_artifact("alice", batch_id, document_id, "final")
    final_path.write_bytes(original)
    data, again = store.read_artifact("alice", batch_id, document_id, "final")
    assert data == original and again == digest
