"""Optional Langfuse tracing for model calls and evaluation runs.

Design goals
------------
* **Zero effect when unused.** Everything here is inert unless the Langfuse
  credentials are present in the environment. Existing behaviour, tests and
  the production API/worker are unchanged when tracing is off.
* **One integration seam.** The only call sites are
  :meth:`ModelGateway.call` (one generation span per model request) and the
  pipeline entry (:func:`trace_document`) that opens a trace per document.
* **Never break a revision.** All Langfuse interaction is best-effort: any
  import, configuration or network error degrades to "tracing off" and is
  swallowed. Observability must never turn a contract run into a failure.
* **Public contract data.** The contracts processed here are public material
  (see AGENTS.md), so prompt and completion text may be sent to Langfuse.
  Credentials are still never written anywhere.

Environment
-----------
``FUNDLEX_LANGFUSE_PUBLIC_KEY`` / ``FUNDLEX_LANGFUSE_SECRET_KEY``
    Langfuse project keys. Both are required to enable tracing.
``FUNDLEX_LANGFUSE_HOST``
    Defaults to ``https://cloud.langfuse.com``.
``FUNDLEX_LANGFUSE_CAPTURE_TEXT``
    ``1`` (default) sends prompt/completion text; ``0`` sends only hashes,
    lengths and metadata.

The double-underscore module functions are intentionally tiny; the heavy
lifting (batching, retries) is done by the Langfuse SDK in a background
thread, so a slow or unreachable Langfuse never blocks a revision.
"""

from __future__ import annotations

import hashlib
import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

_LOGGER = logging.getLogger("fundlex.observability")

_CLIENT: Any = None
_CLIENT_READY = False
_CAPTURE_TEXT = True


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def enabled() -> bool:
    """True when Langfuse keys are configured and the SDK is importable."""
    return _client() is not None


def _client() -> Any:
    """Lazily build the Langfuse client; return ``None`` when unavailable."""
    global _CLIENT, _CLIENT_READY, _CAPTURE_TEXT
    if _CLIENT_READY:
        return _CLIENT
    _CLIENT_READY = True
    public_key = os.environ.get("FUNDLEX_LANGFUSE_PUBLIC_KEY", "").strip()
    secret_key = os.environ.get("FUNDLEX_LANGFUSE_SECRET_KEY", "").strip()
    if not public_key or not secret_key:
        return None
    host = os.environ.get("FUNDLEX_LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
    _CAPTURE_TEXT = _env_flag("FUNDLEX_LANGFUSE_CAPTURE_TEXT", True)
    try:
        from langfuse import Langfuse
        _CLIENT = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    except Exception:  # pragma: no cover - defensive: tracing must never break a run
        _LOGGER.warning("langfuse disabled: client initialisation failed", exc_info=True)
        _CLIENT = None
    return _CLIENT


def _redact(text: str | None) -> Any:
    """Return the text, or a hash+length digest when capture is disabled."""
    if text is None:
        return None
    if _CAPTURE_TEXT:
        return text
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "chars": len(text)}


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@contextmanager
def trace_document(*, name: str, document_id: str, metadata: dict | None = None,
                   tags: list[str] | None = None) -> Iterator[Any]:
    """Open one Langfuse trace for a document revision.

    The trace id is a deterministic function of ``document_id`` so retries and
    re-runs of the same document land on the same trace instead of scattering
    duplicates. Yields the root span (or ``None`` when tracing is off) so the
    caller can attach scores.
    """
    client = _client()
    if client is None:
        yield None
        return
    root: Any = None
    try:
        trace_id = client.create_trace_id(seed=f"fundlex:{document_id}")
        with client.start_as_current_observation(
                name=name, as_type="span", trace_context={"trace_id": trace_id},
                metadata=metadata or {}) as root:
            try:
                from langfuse import propagate_attributes
                with propagate_attributes(session_id=document_id, tags=tags or [],
                                          trace_name=name, metadata=metadata or {}):
                    yield root
            except ImportError:  # pragma: no cover - older SDK without propagate_attributes
                yield root
    except Exception:  # pragma: no cover - defensive: tracing must never break a run
        _LOGGER.warning("langfuse trace failed for %s", name, exc_info=True)
        yield root if root is not None else None


def record_generation(*, task_type: str, prompt_version: str, model: str,
                      prompt_text: str, completion: Any, event: dict,
                      result: Any | None = None) -> None:
    """Emit one generation span for a model call. Best-effort, never raises."""
    client = _client()
    if client is None:
        return
    try:
        usage = {}
        if event.get("prompt_tokens") is not None:
            usage["input"] = event["prompt_tokens"]
        if event.get("completion_tokens") is not None:
            usage["output"] = event["completion_tokens"]
        if event.get("total_tokens") is not None:
            usage["total"] = event["total_tokens"]
        cost = {}
        if event.get("estimated_cost_usd") is not None:
            cost["total"] = event["estimated_cost_usd"]
        level = "ERROR" if event.get("error_code") else "DEFAULT"
        gen = client.start_observation(
            name=task_type, as_type="generation", model=model,
            input=_redact(prompt_text),
            output=_redact(completion) if isinstance(completion, str) else completion,
            version=prompt_version, level=level,
            status_message=event.get("error_code"),
            usage_details=usage or None, cost_details=cost or None,
            metadata={
                "attempt": event.get("attempt"),
                "http_status": event.get("http_status"),
                "request_id": event.get("request_id"),
                "finish_reason": event.get("finish_reason"),
                "latency_ms": event.get("latency_ms"),
                "reused_checkpoint": bool(event.get("reused_checkpoint")),
                "context_sha256": event.get("context_sha256"),
                "error_code": event.get("error_code"),
                "schema_failure": event.get("schema_failure"),
            })
        try:
            gen.end()
        except Exception:  # pragma: no cover
            pass
    except Exception:  # pragma: no cover - defensive: tracing must never break a run
        _LOGGER.warning("langfuse generation emit failed for %s", task_type, exc_info=True)


def record_score(*, name: str, value: Any, trace_seed: str, comment: str | None = None,
                 data_type: str | None = None, metadata: dict | None = None) -> None:
    """Attach a score (e.g. a P6 verdict) to a document trace. Best-effort."""
    client = _client()
    if client is None:
        return
    try:
        trace_id = client.create_trace_id(seed=f"fundlex:{trace_seed}")
        client.create_score(name=name, value=value, trace_id=trace_id,
                            comment=comment, data_type=data_type, metadata=metadata)
    except Exception:  # pragma: no cover - defensive
        _LOGGER.warning("langfuse score emit failed for %s", name, exc_info=True)


def flush() -> None:
    """Flush buffered spans. Safe to call when tracing is off."""
    client = _client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:  # pragma: no cover
        _LOGGER.warning("langfuse flush failed", exc_info=True)


def reset_for_tests() -> None:
    """Drop the cached client so tests can re-evaluate the environment."""
    global _CLIENT, _CLIENT_READY
    _CLIENT, _CLIENT_READY = None, False
