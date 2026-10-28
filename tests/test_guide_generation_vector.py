from __future__ import annotations

from dataclasses import dataclass

import pytest

from fundlex.guide_generation.models import ClauseUnit
from fundlex.guide_generation.models import PolicyRequirement
from fundlex.guide_generation.discovery import DiscoveryConfig, path_a_requirement_retrieval
from fundlex.guide_generation.vector import (
    QdrantVectorIndex,
    SQLiteVectorIndex,
    VectorIndexError,
)


@dataclass
class FakeEmbeddingProvider:
    model: str = "test-embedding"
    version: str = "test-embedding-v1"
    fail: bool = False

    def embed(self, texts):
        if self.fail:
            raise VectorIndexError("VECTOR_EMBEDDING_REQUEST_FAILED")
        result = []
        for text in texts:
            result.append([
                float("fee" in text.lower()),
                float("申购" in text),
                float("赎回" in text),
                float("服务费" in text),
            ])
        return result


def _clauses():
    return [
        ClauseUnit("clause-fee", "version-1", ["费用"], 1, 1, "申购费用由投资人承担。"),
        ClauseUnit("clause-service", "version-1", ["费用"], 2, 2, "销售服务费按年费率计提。"),
        ClauseUnit("clause-redemption", "version-2", ["费用"], 3, 3, "赎回费用由持有人承担。"),
    ]


def test_vector_rebuild_persists_provenance_and_searches(tmp_path):
    index = SQLiteVectorIndex(tmp_path / "vectors.sqlite3")
    clauses = _clauses()
    provider = FakeEmbeddingProvider()
    manifest = index.rebuild(clauses, {"version-1": "source-1", "version-2": "source-2"},
                             "snapshot-1", provider, batch_size=2)

    assert manifest["status"] == "active"
    assert manifest["entry_count"] == 3
    assert index.current_manifest()["manifest_id"] == manifest["manifest_id"]
    hits = index.search(provider.embed(["销售服务费"])[0], top_k=3, per_contract=2, max_candidates=3)
    assert hits[0].clause_id == "clause-service"
    assert hits[0].source_sha256 == "source-1"
    assert hits[0].embedding_version == "test-embedding-v1"


def test_failed_rebuild_keeps_previous_active_manifest(tmp_path):
    index = SQLiteVectorIndex(tmp_path / "vectors.sqlite3")
    clauses = _clauses()
    first = index.rebuild(clauses[:2], {"version-1": "source-1"}, "snapshot-1", FakeEmbeddingProvider())
    with pytest.raises(VectorIndexError):
        index.rebuild(clauses, {"version-1": "changed", "version-2": "source-2"},
                      "snapshot-2", FakeEmbeddingProvider(fail=True))
    assert index.current_manifest()["manifest_id"] == first["manifest_id"]


def test_rollback_switches_to_a_previous_manifest(tmp_path):
    index = SQLiteVectorIndex(tmp_path / "vectors.sqlite3")
    provider = FakeEmbeddingProvider()
    first = index.rebuild(_clauses()[:2], {"version-1": "source-1"}, "snapshot-1", provider)
    second = index.rebuild(_clauses(), {"version-1": "source-1", "version-2": "source-2"},
                           "snapshot-2", provider)
    assert index.current_manifest()["manifest_id"] == second["manifest_id"]
    index.rollback(first["manifest_id"])
    assert index.current_manifest()["manifest_id"] == first["manifest_id"]


class _FakeQdrant(QdrantVectorIndex):
    def __init__(self, metadata_path):
        super().__init__("http://qdrant.test", metadata_path)
        self.collections = {}

    def _request(self, method, path, body=None):
        parts = path.split("/")
        if method == "PUT" and path.startswith("/collections/") and "/points" not in path:
            self.collections[parts[2]] = []
            return {"status": "ok"}
        if method == "PUT" and "/points" in path:
            self.collections[parts[2]].extend(body["points"])
            return {"status": "ok"}
        if method == "GET" and path.startswith("/collections/"):
            if parts[2] not in self.collections:
                raise VectorIndexError("VECTOR_BACKEND_UNAVAILABLE")
            return {"status": "ok"}
        if method == "POST" and path.endswith("/points/search"):
            rows = self.collections[parts[2]]
            return {"status": "ok", "result": [
                {"score": 0.99, "payload": row["payload"]} for row in rows
            ]}
        raise AssertionError((method, path, body))


def test_qdrant_backend_keeps_same_manifest_and_provenance_contract(tmp_path):
    index = _FakeQdrant(tmp_path / "qdrant-metadata.sqlite3")
    provider = FakeEmbeddingProvider()
    manifest = index.rebuild(_clauses(), {"version-1": "source-1", "version-2": "source-2"},
                             "snapshot-q", provider)

    payload = __import__("json").loads(manifest["payload_json"])
    assert payload["backend"] == "qdrant"
    assert payload["collection"] in index.collections
    hits = index.search(provider.embed(["销售服务费"])[0], top_k=3, per_contract=2, max_candidates=3)
    assert hits
    assert hits[0].clause_id == "clause-fee"
    assert hits[0].source_sha256 == "source-1"
    assert hits[0].embedding_version == "test-embedding-v1"
    index.rollback(manifest["manifest_id"])


class _DenseHit:
    def __init__(self, clause_id, contract_version_id="version-1", source_sha256="source-1"):
        self.clause_id = clause_id
        self.contract_version_id = contract_version_id
        self.score = 0.9
        self.source_sha256 = source_sha256
        self.embedding_version = "test-embedding-v1"


class _DenseRetriever:
    def __init__(self, hit):
        self.hit = hit

    def search(self, text, *, top_k, per_contract, max_candidates):
        return [self.hit]


class _NoIntentRouter:
    def call(self, **kwargs):
        raise RuntimeError("intent unavailable")


def test_hybrid_discovery_keeps_vector_only_recall_and_rejects_stale_source():
    clauses = [ClauseUnit("clause-semantic", "version-1", ["费用"], 1, 1, "销售机构承担相关成本。")]
    requirement = PolicyRequirement(
        requirement_id="R-1", source_block_ids=["B-1"], source_quote="收费安排",
        article="第一条", norm_type="obligation", subject="投资人",
        object="收费安排", requirement="应当明确收费安排", disposition="modify_contract",
    )
    config = DiscoveryConfig(path_a_max_intent_calls=0, path_a_max_candidates=3)
    impacts, _, _, _ = path_a_requirement_retrieval(
        _NoIntentRouter(), None, [requirement], clauses, config,
        dense=_DenseRetriever(_DenseHit("clause-semantic")),
        source_hashes={"version-1": "source-1"},
    )
    assert len(impacts) == 1
    assert impacts[0].discovery_sources == ["lexical+vector"]
    assert impacts[0].metadata["retrieval"]["vector"] is True

    stale, _, _, notes = path_a_requirement_retrieval(
        _NoIntentRouter(), None, [requirement], clauses, config,
        dense=_DenseRetriever(_DenseHit("clause-semantic", source_sha256="old-source")),
        source_hashes={"version-1": "source-1"},
    )
    assert stale == []
    assert any("source hash rejected" in note for note in notes)
