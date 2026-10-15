"""Langfuse tracing must be a strict no-op unless explicitly configured.

These tests pin the safety properties that matter for production:

* with no keys configured, nothing is emitted and behaviour is unchanged;
* the prompt/completion text is redacted to a hash+length when capture is off;
* the trace seed is deterministic per document (retries land on one trace).
"""

import json

import httpx
import pytest

from fundlex import observability
from fundlex.model import ModelGateway


@pytest.fixture(autouse=True)
def _reset_client(monkeypatch):
    for name in ("FUNDLEX_LANGFUSE_PUBLIC_KEY", "FUNDLEX_LANGFUSE_SECRET_KEY",
                 "FUNDLEX_LANGFUSE_HOST", "FUNDLEX_LANGFUSE_CAPTURE_TEXT"):
        monkeypatch.delenv(name, raising=False)
    observability.reset_for_tests()
    yield
    observability.reset_for_tests()


def test_disabled_without_keys():
    assert observability.enabled() is False
    # Every public entry point must be safe to call while disabled.
    observability.record_generation(task_type="t", prompt_version="v", model="m",
                                    prompt_text="p", completion="c", event={})
    observability.record_score(name="s", value=1, trace_seed="doc")
    observability.flush()
    with observability.trace_document(name="n", document_id="doc"):
        pass


def test_enabled_requires_both_keys(monkeypatch):
    monkeypatch.setenv("FUNDLEX_LANGFUSE_PUBLIC_KEY", "pk")
    observability.reset_for_tests()
    assert observability.enabled() is False
    monkeypatch.setenv("FUNDLEX_LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_HOST", "http://127.0.0.1:1")  # never contacted
    observability.reset_for_tests()
    assert observability.enabled() is True


def test_text_redaction_hashes_when_capture_disabled(monkeypatch):
    monkeypatch.setenv("FUNDLEX_LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_HOST", "http://127.0.0.1:1")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_CAPTURE_TEXT", "0")
    observability.reset_for_tests()
    # Force initialisation so the capture flag is read.
    observability.enabled()

    captured = {}

    class FakeClient:
        def start_observation(self, **kwargs):
            captured.update(kwargs)
            return self

        def end(self):
            pass

    monkeypatch.setattr(observability, "_client", lambda: FakeClient())
    observability.record_generation(task_type="recall_facts", prompt_version="facts_v1",
                                    model="m", prompt_text="secret contract text",
                                    completion='{"ok":true}', event={"prompt_tokens": 5})
    assert captured["input"]["chars"] == len("secret contract text")
    assert "secret contract text" not in json.dumps(captured["input"])


def test_router_call_emits_generation_when_enabled(monkeypatch):
    """A real ModelGateway.call must publish a generation span."""
    monkeypatch.setenv("FUNDLEX_LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_HOST", "http://127.0.0.1:1")
    observability.reset_for_tests()
    observability.enabled()

    seen = []

    class FakeClient:
        def start_observation(self, **kwargs):
            seen.append(kwargs)
            return self

        def end(self):
            pass

    monkeypatch.setattr(observability, "_client", lambda: FakeClient())

    def handler(request):
        return httpx.Response(200, json={"model": "actual",
                                         "choices": [{"message": {"content": json.dumps({"fund_type": "open_regular"})}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}})

    gateway = ModelGateway(base_url="https://model.invalid", model="test", api_key="k",
                           client=httpx.Client(transport=httpx.MockTransport(handler)), retries=0)
    gateway.call(task_type="recall_facts", bounded_context="contract body",
                 response_schema={"type": "object"}, instruction="i", prompt_version="facts_v1")
    assert len(seen) == 1
    assert seen[0]["name"] == "recall_facts"
    assert seen[0]["as_type"] == "generation"
    assert seen[0]["version"] == "facts_v1"
    assert seen[0]["usage_details"] == {"input": 10, "output": 2, "total": 12}


def test_trace_seed_is_deterministic(monkeypatch):
    monkeypatch.setenv("FUNDLEX_LANGFUSE_PUBLIC_KEY", "pk")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_SECRET_KEY", "sk")
    monkeypatch.setenv("FUNDLEX_LANGFUSE_HOST", "http://127.0.0.1:1")
    observability.reset_for_tests()
    client = observability._client()
    assert client.create_trace_id(seed="fundlex:doc-1") == client.create_trace_id(seed="fundlex:doc-1")
    assert client.create_trace_id(seed="fundlex:doc-1") != client.create_trace_id(seed="fundlex:doc-2")
