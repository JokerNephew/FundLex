"""The local JSONL trace sink must be a strict no-op unless configured.

These tests pin the properties that make the fallback trustworthy:

* nothing is written when ``FUNDLEX_TRACE_JSONL`` is unset;
* one document trace + its generations + scores land in one file, grouped by a
  deterministic trace id;
* capture can be turned off so contract text is only hashed, not stored;
* a model call inside a document trace is recorded automatically.
"""

import json

import httpx
import pytest

from fundlex import trace_sink
from fundlex.model import ModelGateway


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    for name in ("FUNDLEX_TRACE_JSONL", "FUNDLEX_TRACE_CAPTURE_TEXT"):
        monkeypatch.delenv(name, raising=False)
    yield


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_disabled_without_path(tmp_path):
    assert trace_sink.enabled() is False
    # Every entry point must be safe to call while disabled.
    trace_sink.record_generation(trace_seed="doc", task_type="t", prompt_version="v",
                                 model="m", prompt_text="p", completion="c", event={})
    trace_sink.record_score(name="s", value=1, trace_seed="doc")
    with trace_sink.trace_document(name="n", document_id="doc"):
        pass
    assert not (tmp_path / "unused.jsonl").exists()


def test_trace_id_is_deterministic_and_per_document():
    assert trace_sink.trace_id_for("doc-1") == trace_sink.trace_id_for("doc-1")
    assert trace_sink.trace_id_for("doc-1") != trace_sink.trace_id_for("doc-2")


def test_document_trace_generation_and_score_share_one_file(tmp_path, monkeypatch):
    target = tmp_path / "trace.jsonl"
    monkeypatch.setenv("FUNDLEX_TRACE_JSONL", str(target))
    with trace_sink.trace_document(name="recall-first:c.docx", document_id="doc-9",
                                   metadata={"engine_id": "recall_first"}) as tid:
        assert tid == trace_sink.trace_id_for("doc-9")
        assert trace_sink.current_seed() == "doc-9"
        trace_sink.record_generation(
            trace_seed=trace_sink.current_seed(), task_type="recall_facts",
            prompt_version="facts_v1", model="deepseek-v4.1-flash",
            prompt_text="system\n合同正文", completion='{"fund_type":"open_regular"}',
            event={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150,
                   "estimated_cost_usd": 0.001, "attempt": 1, "http_status": 200,
                   "latency_ms": 420, "context_sha256": "abc"})
    assert trace_sink.current_seed() is None
    trace_sink.record_score(name="target_verdict", value="completed", trace_seed="doc-9",
                            data_type="CATEGORICAL", metadata={"rule_id": "G01"})

    records = _records(target)
    kinds = [r["kind"] for r in records]
    assert kinds == ["trace", "generation", "score"]
    assert all(r["trace_id"] == trace_sink.trace_id_for("doc-9") for r in records)
    gen = records[1]
    assert gen["input"] == "system\n合同正文"          # text captured by default
    assert gen["output"] == '{"fund_type":"open_regular"}'
    assert gen["usage"] == {"input": 120, "output": 30, "total": 150}
    assert gen["cost"] == {"total": 0.001}
    assert gen["metadata"]["http_status"] == 200
    assert records[2]["value"] == "completed"


def test_capture_off_stores_hash_not_text(tmp_path, monkeypatch):
    target = tmp_path / "trace.jsonl"
    monkeypatch.setenv("FUNDLEX_TRACE_JSONL", str(target))
    monkeypatch.setenv("FUNDLEX_TRACE_CAPTURE_TEXT", "0")
    with trace_sink.trace_document(name="n", document_id="doc-1"):
        trace_sink.record_generation(trace_seed="doc-1", task_type="t", prompt_version="v",
                                     model="m", prompt_text="secret contract text",
                                     completion="out", event={})
    gen = [r for r in _records(target) if r["kind"] == "generation"][0]
    assert gen["input"]["chars"] == len("secret contract text")
    assert "secret contract text" not in json.dumps(gen)


def test_model_call_inside_document_trace_is_recorded(tmp_path, monkeypatch):
    """A real ModelGateway.call inside a document trace lands in the JSONL sink."""
    target = tmp_path / "trace.jsonl"
    monkeypatch.setenv("FUNDLEX_TRACE_JSONL", str(target))

    def handler(request):
        return httpx.Response(200, json={"model": "actual",
                                         "choices": [{"message": {"content": json.dumps({"fund_type": "open_regular"})}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})

    gateway = ModelGateway(base_url="https://model.invalid", model="test", api_key="k",
                           client=httpx.Client(transport=httpx.MockTransport(handler)), retries=0)
    with trace_sink.trace_document(name="recall-first:c.docx", document_id="doc-42"):
        gateway.call(task_type="recall_facts", bounded_context="contract body",
                     response_schema={"type": "object"}, instruction="i", prompt_version="facts_v1")

    generations = [r for r in _records(target) if r["kind"] == "generation"]
    assert len(generations) == 1
    gen = generations[0]
    assert gen["trace_id"] == trace_sink.trace_id_for("doc-42")
    assert gen["task_type"] == "recall_facts"
    assert gen["usage"]["total"] == 12
