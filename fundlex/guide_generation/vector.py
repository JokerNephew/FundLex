"""Versioned dense retrieval for the contract clause corpus.

The relational ``gg_clauses`` table remains the source of truth.  This module
stores only rebuildable embedding derivatives and keeps a manifest describing
the exact corpus and embedding version used to create them.  A failed rebuild
never changes the active manifest, so callers can safely fall back to the
lexical index.

No local fake embedding is provided.  Tests may inject a small provider, while
production uses an OpenAI-compatible ``/embeddings`` endpoint supplied by
configuration.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import httpx

from .models import ClauseUnit, canonical_json, sha256_text


VECTOR_SCHEMA_VERSION = "guide-vector-1"


class EmbeddingProvider(Protocol):
    model: str
    version: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """Return one finite, non-empty vector for each input text."""


class VectorIndexError(RuntimeError):
    """A vector derivative cannot be used safely."""


@dataclass(frozen=True)
class VectorHit:
    clause_id: str
    contract_version_id: str
    score: float
    source_sha256: str
    embedding_version: str


class HttpEmbeddingProvider:
    """OpenAI-compatible embedding client with bounded request payloads."""

    def __init__(self, base_url: str, model: str, *, api_key: str = "",
                 version: str = "", timeout_s: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.version = version or model
        self.api_key = api_key
        self.timeout_s = timeout_s

    @classmethod
    def from_env(cls, *, base_url: str = "", model: str = "",
                 api_key_env: str = "EMBEDDING_API_KEY", version: str = "",
                 timeout_s: float = 120.0) -> "HttpEmbeddingProvider":
        endpoint = base_url or os.environ.get("FUNDLEX_EMBEDDING_BASE_URL", "")
        selected_model = model or os.environ.get("FUNDLEX_EMBEDDING_MODEL", "")
        if not endpoint or not selected_model:
            raise VectorIndexError("VECTOR_EMBEDDING_NOT_CONFIGURED")
        return cls(endpoint, selected_model,
                   api_key=os.environ.get(api_key_env, ""), version=version,
                   timeout_s=timeout_s)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        endpoint = self.base_url
        if not endpoint.endswith("/embeddings"):
            endpoint += "/embeddings"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        try:
            response = httpx.post(endpoint, headers=headers,
                                   json={"model": self.model, "input": list(texts)},
                                   timeout=self.timeout_s)
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VectorIndexError("VECTOR_EMBEDDING_REQUEST_FAILED") from exc
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list) or len(data) != len(texts):
            raise VectorIndexError("VECTOR_EMBEDDING_RESPONSE_INVALID")
        try:
            ordered = sorted(data, key=lambda item: int(item.get("index", 0)))
            vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise VectorIndexError("VECTOR_EMBEDDING_RESPONSE_INVALID") from exc
        _validate_vectors(vectors, expected=len(texts))
        return vectors


def _validate_vectors(vectors: Sequence[Sequence[float]], *, expected: int | None = None,
                      dimension: int | None = None) -> int:
    if expected is not None and len(vectors) != expected:
        raise VectorIndexError("VECTOR_DIMENSION_MISMATCH")
    actual = 0
    for vector in vectors:
        if not vector:
            raise VectorIndexError("VECTOR_EMPTY")
        if actual and len(vector) != actual:
            raise VectorIndexError("VECTOR_DIMENSION_MISMATCH")
        actual = len(vector)
        if any(not math.isfinite(float(value)) for value in vector):
            raise VectorIndexError("VECTOR_NON_FINITE")
    if dimension is not None and actual != dimension:
        raise VectorIndexError("VECTOR_DIMENSION_MISMATCH")
    return actual


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise VectorIndexError("VECTOR_DIMENSION_MISMATCH")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _text_hash(text: str) -> str:
    return sha256_text(text or "")


def _corpus_hash(clauses: Sequence[ClauseUnit], source_hashes: dict[str, str]) -> str:
    rows = [{"clause_id": clause.clause_id,
             "contract_version_id": clause.contract_version_id,
             "text_sha256": _text_hash(clause.text),
             "source_sha256": source_hashes.get(clause.contract_version_id, "")}
            for clause in clauses]
    return hashlib.sha256(canonical_json(rows).encode("utf-8")).hexdigest()


class SQLiteVectorIndex:
    """A small persistent vector database with atomic manifest activation."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self):
        db = sqlite3.connect(str(self.path))
        db.row_factory = sqlite3.Row
        return db

    def _ensure_schema(self) -> None:
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS vector_manifests (
                    manifest_id TEXT PRIMARY KEY, schema_version TEXT NOT NULL,
                    corpus_snapshot_id TEXT NOT NULL, corpus_hash TEXT NOT NULL,
                    embedding_model TEXT NOT NULL, embedding_version TEXT NOT NULL,
                    dimension INTEGER NOT NULL, entry_count INTEGER NOT NULL,
                    status TEXT NOT NULL, parent_manifest_id TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL, manifest_hash TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS vector_manifests_active
                    ON vector_manifests(status, created_at);
                CREATE TABLE IF NOT EXISTS vector_entries (
                    manifest_id TEXT NOT NULL, clause_id TEXT NOT NULL,
                    contract_version_id TEXT NOT NULL, source_sha256 TEXT NOT NULL,
                    text_sha256 TEXT NOT NULL, vector_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(manifest_id, clause_id),
                    FOREIGN KEY(manifest_id) REFERENCES vector_manifests(manifest_id)
                );
                CREATE INDEX IF NOT EXISTS vector_entries_manifest_contract
                    ON vector_entries(manifest_id, contract_version_id);
                CREATE TABLE IF NOT EXISTS vector_current (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    manifest_id TEXT NOT NULL
                );
            """)

    def current_manifest(self) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("""SELECT m.* FROM vector_current c
                JOIN vector_manifests m ON m.manifest_id=c.manifest_id
                WHERE c.singleton=1 AND m.status='active'""").fetchone()
            return dict(row) if row else None

    def rebuild(self, clauses: Sequence[ClauseUnit], source_hashes: dict[str, str],
                snapshot_id: str, provider: EmbeddingProvider, *, batch_size: int = 32,
                payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ordered = list(clauses)
        corpus_hash = _corpus_hash(ordered, source_hashes)
        current = self.current_manifest()
        payload = {"backend": "sqlite", **(payload or {})}
        current_payload = _json_object(current.get("payload_json", "")) if current else {}
        if (current and current_payload.get("backend") == payload.get("backend")
                and current["corpus_snapshot_id"] == snapshot_id
                and current["corpus_hash"] == corpus_hash
                and current["embedding_model"] == provider.model
                and current["embedding_version"] == provider.version):
            return current
        if not ordered:
            raise VectorIndexError("VECTOR_CORPUS_EMPTY")
        batch_size = max(1, min(int(batch_size), 256))
        vectors: list[list[float]] = []
        for start in range(0, len(ordered), batch_size):
            vectors.extend(provider.embed([item.text for item in ordered[start:start + batch_size]]))
        dimension = _validate_vectors(vectors, expected=len(ordered))
        return self._activate(ordered, source_hashes, snapshot_id, provider, vectors,
                              payload=payload, parent=current)

    def _activate(self, ordered: Sequence[ClauseUnit], source_hashes: dict[str, str],
                  snapshot_id: str, provider: EmbeddingProvider,
                  vectors: Sequence[Sequence[float]], *, payload: dict[str, Any],
                  parent: dict[str, Any] | None = None,
                  manifest_id: str = "") -> dict[str, Any]:
        dimension = _validate_vectors(vectors, expected=len(ordered))
        corpus_hash = _corpus_hash(ordered, source_hashes)
        manifest_id = manifest_id or "vm-" + uuid.uuid4().hex
        parent_id = str(parent["manifest_id"]) if parent else ""
        descriptor = {
            "schema_version": VECTOR_SCHEMA_VERSION, "manifest_id": manifest_id,
            "snapshot_id": snapshot_id, "corpus_hash": corpus_hash,
            "embedding_model": provider.model, "embedding_version": provider.version,
            "dimension": dimension, "entry_count": len(ordered), "parent_manifest_id": parent_id,
            "payload": payload,
        }
        manifest_hash = hashlib.sha256(canonical_json(descriptor).encode("utf-8")).hexdigest()
        with self._connect() as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO vector_manifests
                    (manifest_id,schema_version,corpus_snapshot_id,corpus_hash,
                     embedding_model,embedding_version,dimension,entry_count,status,
                     parent_manifest_id,created_at,manifest_hash,payload_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (manifest_id, VECTOR_SCHEMA_VERSION, snapshot_id, corpus_hash,
                     provider.model, provider.version, dimension, len(ordered), "building",
                     parent_id, time.time(), manifest_hash, json.dumps(payload, ensure_ascii=False)))
                db.executemany("""INSERT INTO vector_entries
                    (manifest_id,clause_id,contract_version_id,source_sha256,text_sha256,vector_json)
                    VALUES (?,?,?,?,?,?)""",
                    [(manifest_id, clause.clause_id, clause.contract_version_id,
                      source_hashes.get(clause.contract_version_id, ""), _text_hash(clause.text),
                      json.dumps(vector, separators=(",", ":")))
                     for clause, vector in zip(ordered, vectors)])
                db.execute("UPDATE vector_manifests SET status='retired' WHERE status='active'")
                db.execute("UPDATE vector_manifests SET status='active' WHERE manifest_id=?", (manifest_id,))
                db.execute("INSERT OR REPLACE INTO vector_current(singleton,manifest_id) VALUES(1,?)",
                           (manifest_id,))
                db.commit()
            except Exception:
                db.rollback()
                raise
        result = dict(descriptor)
        result.update({"status": "active", "manifest_hash": manifest_hash,
                       "payload_json": json.dumps(payload, ensure_ascii=False)})
        return result

    def rollback(self, manifest_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM vector_manifests WHERE manifest_id=?", (manifest_id,)).fetchone()
            if not row or row["status"] == "building":
                raise VectorIndexError("VECTOR_MANIFEST_NOT_ROLLBACKABLE")
            db.execute("UPDATE vector_manifests SET status='retired' WHERE status='active'")
            db.execute("UPDATE vector_manifests SET status='active' WHERE manifest_id=?", (manifest_id,))
            db.execute("INSERT OR REPLACE INTO vector_current(singleton,manifest_id) VALUES(1,?)",
                       (manifest_id,))
            result = dict(row)
            result["status"] = "active"
            return result

    def search(self, vector: Sequence[float], *, top_k: int = 30,
               per_contract: int = 1, max_candidates: int = 60) -> list[VectorHit]:
        manifest = self.current_manifest()
        if not manifest:
            return []
        _validate_vectors([vector], dimension=int(manifest["dimension"]))
        with self._connect() as db:
            rows = db.execute("SELECT * FROM vector_entries WHERE manifest_id=?",
                              (manifest["manifest_id"],)).fetchall()
        ranked: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            values = json.loads(row["vector_json"])
            ranked.append((_cosine(vector, values), row))
        ranked.sort(key=lambda item: (-item[0], item[1]["clause_id"]))
        selected: list[VectorHit] = []
        per: dict[str, int] = {}
        for score, row in ranked:
            contract = row["contract_version_id"]
            if per.get(contract, 0) >= max(1, per_contract):
                continue
            per[contract] = per.get(contract, 0) + 1
            selected.append(VectorHit(row["clause_id"], contract, score,
                                      row["source_sha256"], manifest["embedding_version"]))
            if len(selected) >= max(1, min(top_k, max_candidates)):
                break
        return selected


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


class QdrantVectorIndex:
    """Qdrant REST backend using SQLite only for manifest/provenance state.

    Each rebuild gets a new collection.  The SQLite active pointer is changed
    only after all points are accepted by Qdrant; old collections remain
    available for explicit rollback and can be garbage-collected separately.
    """

    def __init__(self, url: str, metadata_path: str | Path, *, api_key: str = "",
                 collection_prefix: str = "fundlex-clauses", timeout_s: float = 120.0):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.collection_prefix = collection_prefix.strip("-") or "fundlex-clauses"
        self.timeout_s = timeout_s
        self.metadata = SQLiteVectorIndex(metadata_path)

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        try:
            response = httpx.request(method, self.url + path, headers=headers,
                                     json=body, timeout=self.timeout_s)
            response.raise_for_status()
            value = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise VectorIndexError("VECTOR_BACKEND_UNAVAILABLE") from exc
        if not isinstance(value, dict) or value.get("status") == "error":
            raise VectorIndexError("VECTOR_BACKEND_RESPONSE_INVALID")
        return value

    def current_manifest(self) -> dict[str, Any] | None:
        return self.metadata.current_manifest()

    def rebuild(self, clauses: Sequence[ClauseUnit], source_hashes: dict[str, str],
                snapshot_id: str, provider: EmbeddingProvider, *, batch_size: int = 32,
                payload: dict[str, Any] | None = None) -> dict[str, Any]:
        ordered = list(clauses)
        if not ordered:
            raise VectorIndexError("VECTOR_CORPUS_EMPTY")
        corpus_hash = _corpus_hash(ordered, source_hashes)
        current = self.current_manifest()
        current_payload = _json_object(current.get("payload_json", "")) if current else {}
        requested_payload = {"backend": "qdrant", **(payload or {})}
        if (current and current_payload.get("backend") == "qdrant"
                and current["corpus_snapshot_id"] == snapshot_id
                and current["corpus_hash"] == corpus_hash
                and current["embedding_model"] == provider.model
                and current["embedding_version"] == provider.version):
            return current
        vectors: list[list[float]] = []
        batch_size = max(1, min(int(batch_size), 256))
        for start in range(0, len(ordered), batch_size):
            vectors.extend(provider.embed([item.text for item in ordered[start:start + batch_size]]))
        dimension = _validate_vectors(vectors, expected=len(ordered))
        manifest_id = "vm-" + uuid.uuid4().hex
        collection = f"{self.collection_prefix}-{manifest_id[3:]}"
        self._request("PUT", f"/collections/{collection}", {
            "vectors": {"size": dimension, "distance": "Cosine"},
        })
        points = []
        for clause, vector in zip(ordered, vectors):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{manifest_id}:{clause.clause_id}"))
            points.append({"id": point_id, "vector": list(vector), "payload": {
                "manifest_id": manifest_id, "clause_id": clause.clause_id,
                "contract_version_id": clause.contract_version_id,
                "source_sha256": source_hashes.get(clause.contract_version_id, ""),
                "text_sha256": _text_hash(clause.text),
            }})
        for start in range(0, len(points), 128):
            self._request("PUT", f"/collections/{collection}/points?wait=true",
                          {"points": points[start:start + 128]})
        requested_payload["collection"] = collection
        return self.metadata._activate(ordered, source_hashes, snapshot_id, provider, vectors,
                                       payload=requested_payload, parent=current, manifest_id=manifest_id)

    def rollback(self, manifest_id: str) -> dict[str, Any]:
        with self.metadata._connect() as db:
            row = db.execute("SELECT * FROM vector_manifests WHERE manifest_id=?", (manifest_id,)).fetchone()
        if not row:
            raise VectorIndexError("VECTOR_MANIFEST_NOT_ROLLBACKABLE")
        manifest = dict(row)
        payload = _json_object(manifest.get("payload_json", ""))
        if payload.get("backend") != "qdrant" or not payload.get("collection"):
            raise VectorIndexError("VECTOR_MANIFEST_BACKEND_MISMATCH")
        self._request("GET", f"/collections/{payload['collection']}")
        return self.metadata.rollback(manifest_id)

    def search(self, vector: Sequence[float], *, top_k: int = 30,
               per_contract: int = 1, max_candidates: int = 60) -> list[VectorHit]:
        manifest = self.current_manifest()
        if not manifest:
            return []
        payload = _json_object(manifest.get("payload_json", ""))
        collection = payload.get("collection")
        if payload.get("backend") != "qdrant" or not collection:
            raise VectorIndexError("VECTOR_MANIFEST_BACKEND_MISMATCH")
        _validate_vectors([vector], dimension=int(manifest["dimension"]))
        limit = max(1, min(max_candidates, top_k) * max(1, per_contract) * 4)
        response = self._request("POST", f"/collections/{collection}/points/search", {
            "vector": list(vector), "limit": limit, "with_payload": True,
            "filter": {"must": [{"key": "manifest_id", "match": {"value": manifest["manifest_id"]}}]},
        })
        rows = response.get("result")
        if not isinstance(rows, list):
            raise VectorIndexError("VECTOR_BACKEND_RESPONSE_INVALID")
        selected: list[VectorHit] = []
        per: dict[str, int] = {}
        for row in rows:
            data = row.get("payload") if isinstance(row, dict) else None
            if not isinstance(data, dict):
                continue
            clause_id = str(data.get("clause_id") or "")
            contract = str(data.get("contract_version_id") or "")
            if not clause_id or not contract or per.get(contract, 0) >= max(1, per_contract):
                continue
            per[contract] = per.get(contract, 0) + 1
            selected.append(VectorHit(clause_id, contract, float(row.get("score") or 0.0),
                                      str(data.get("source_sha256") or ""), manifest["embedding_version"]))
            if len(selected) >= max(1, min(top_k, max_candidates)):
                break
        return selected


class DenseRetriever:
    """Embeds a query and delegates persisted similarity search."""

    def __init__(self, index: SQLiteVectorIndex | QdrantVectorIndex, provider: EmbeddingProvider):
        self.index = index
        self.provider = provider

    def search(self, text: str, *, top_k: int, per_contract: int,
               max_candidates: int) -> list[VectorHit]:
        vectors = self.provider.embed([text])
        if len(vectors) != 1:
            raise VectorIndexError("VECTOR_QUERY_RESPONSE_INVALID")
        return self.index.search(vectors[0], top_k=top_k, per_contract=per_contract,
                                 max_candidates=max_candidates)


def build_dense_retriever(config: Any, root: str | Path) -> DenseRetriever | None:
    """Build the explicitly enabled retriever, or return ``None``.

    The default remains lexical-only.  A vector endpoint must be configured by
    the operator; silently constructing a deterministic pseudo-embedding would
    make retrieval metrics and provenance claims invalid.
    """
    if not bool(getattr(config, "vector_enabled", False)):
        return None
    provider = HttpEmbeddingProvider.from_env(
        base_url=str(getattr(config, "vector_embedding_base_url", "") or ""),
        model=str(getattr(config, "vector_embedding_model", "") or ""),
        api_key_env=str(getattr(config, "vector_embedding_api_key_env", "EMBEDDING_API_KEY") or "EMBEDDING_API_KEY"),
        version=str(getattr(config, "vector_embedding_version", "") or ""),
        timeout_s=float(getattr(config, "vector_embedding_timeout_s", 120.0)),
    )
    path = str(getattr(config, "vector_index_path", "") or "")
    index_path = Path(path) if path else Path(root) / "guide_vectors.sqlite3"
    backend = str(getattr(config, "vector_backend", "sqlite") or "sqlite").lower()
    if backend == "qdrant":
        url = str(getattr(config, "vector_qdrant_url", "") or "") or os.environ.get("FUNDLEX_VECTOR_QDRANT_URL", "")
        if not url:
            raise VectorIndexError("VECTOR_QDRANT_NOT_CONFIGURED")
        key_env = str(getattr(config, "vector_qdrant_api_key_env", "QDRANT_API_KEY") or "QDRANT_API_KEY")
        key = os.environ.get(key_env, "")
        prefix = str(getattr(config, "vector_qdrant_collection_prefix", "fundlex-clauses") or "fundlex-clauses")
        return DenseRetriever(QdrantVectorIndex(url, index_path, api_key=key,
                                                collection_prefix=prefix,
                                                timeout_s=float(getattr(config, "vector_embedding_timeout_s", 120.0))), provider)
    if backend != "sqlite":
        raise VectorIndexError("VECTOR_BACKEND_UNSUPPORTED")
    return DenseRetriever(SQLiteVectorIndex(index_path), provider)
