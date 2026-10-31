"""The module-level compact cache stays bounded and exact (B13 F5)."""

from __future__ import annotations

from types import SimpleNamespace

from fundlex import recall_pipeline
from fundlex.recall_pipeline import _document_compact


def _inspection(label: str):
    span = SimpleNamespace(text=f"第 一 条 {label}")
    return SimpleNamespace(paragraphs=(span,))


def test_document_compact_cache_is_bounded_and_precise(monkeypatch):
    monkeypatch.setattr(recall_pipeline, "_DOCUMENT_COMPACT_CACHE", {})
    cache = recall_pipeline._DOCUMENT_COMPACT_CACHE
    docs = [_inspection(label) for label in "abcdef"]
    first = _document_compact(docs[0])
    assert len(cache) == 1
    for doc in docs[1:]:
        _document_compact(doc)
    assert len(cache) == recall_pipeline._DOCUMENT_COMPACT_CACHE_MAX

    # Cached value is the compact of its own document, never a neighbour's.
    assert _document_compact(docs[5]) == "第一条f"
    # A recomputation for an evicted document yields the same value (pure function).
    assert _document_compact(_inspection("a")) == first == "第一条a"
    # Entries hold their inspection, so id() cannot alias a different object.
    for key, (owner, _value) in cache.items():
        assert id(owner) == key
