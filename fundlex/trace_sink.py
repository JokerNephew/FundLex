"""Local JSONL trace sink: offline, dependency-free model-call observability.

Why this exists
---------------
The Langfuse Cloud path (``fundlex/observability.py``) is correct on our side —
a local OTLP capture shows every span carrying input/output/usage/cost/metadata
— but both Langfuse regions we tried drop the payload on ingestion (FL-D085),
leaving only structural fields. Evaluation and root-cause analysis need the
payload, so this module writes the same information to a local JSONL file
instead. It is the fallback the user selected.

Design
------
* **No network, no SDK.** Pure stdlib. A sink that cannot fail a revision.
* **Same shape as the Langfuse trace.** One *trace* per document (keyed by
  ``document_id``), one *generation* record per model attempt, plus *score*
  records for evaluation verdicts.
* **Append-only JSONL.** One JSON object per line, so a crashed run still
  leaves every record written before the crash. Consumers filter by
  ``trace_id``.
* **Zero effect when unused.** Nothing is written unless
  ``FUNDLEX_TRACE_JSONL`` points at a path. Existing behaviour is unchanged.

Environment
-----------
``FUNDLEX_TRACE_JSONL``
    Path of the JSONL file to append to. Unset/empty → the sink is off.
``FUNDLEX_TRACE_CAPTURE_TEXT``
    ``1`` (default) records prompt/completion text; ``0`` records only
    hashes and lengths (for runs that must not persist contract text).
``FUNDLEX_TRACE_MAX_BYTES``
    Size cap per active JSONL file, default 64 MiB (B13 F5: traces used to
    grow without bound).  Reached files roll aside as
    ``<name>.jsonl.YYYYmmdd-HHMMSS-ffffff`` in the same directory; ``<= 0``
    disables rotation.
``FUNDLEX_TRACE_KEEP_ROTATED``
    Rotated copies to keep, newest first (default 10).  Only files this
    module itself rotated match the sibling pattern — manually archived
    ``archive-*`` files and any other filename are never touched.

Record kinds
------------
``{"kind": "trace", "trace_id", "document_id", "name", "metadata", "tags", "ts"}``
``{"kind": "generation", "trace_id", "task_type", "prompt_version", "model",
   "input", "output", "usage", "cost", "metadata", "ts"}``
``{"kind": "score", "trace_id", "name", "value", "data_type", "comment",
   "metadata", "ts"}``

The ``trace_id`` is a deterministic hash of the document id, so re-runs of one
document land on one trace group — the same property the Langfuse path has.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

_LOGGER = logging.getLogger("fundlex.trace_sink")

_LOCK = threading.Lock()

# Capture-on/off is per-traced-document, and a worker owns one document per
# thread (same rationale as ``_ACTIVE`` below): thread-local kills the race
# where two concurrent documents crossed each other's redaction flag (FL-D936(2)).
_CAPTURE_TEXT = threading.local()


def _capture_text() -> bool:
    return getattr(_CAPTURE_TEXT, "enabled", True)

_DEFAULT_MAX_BYTES = 64 * 1024 * 1024
_DEFAULT_KEEP_ROTATED = 10
_ROTATED_SUFFIX = re.compile(r"\.\d{8}-\d{6}-\d{6}\Z")

# The document id the current work item belongs to, set by ``trace_document``.
# Model calls deep in the engine do not receive the job record, so the sink
# carries the active seed for them. A worker processes one document per thread,
# hence thread-local rather than a plain module global.
_ACTIVE = threading.local()


def current_seed() -> str | None:
    """Document id of the trace currently open in this thread, if any."""
    return getattr(_ACTIVE, "seed", None)


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


def path() -> str | None:
    """Return the configured JSONL path, or ``None`` when the sink is off."""
    raw = os.environ.get("FUNDLEX_TRACE_JSONL", "").strip()
    return raw or None


def enabled() -> bool:
    return path() is not None


def trace_id_for(document_id: str) -> str:
    """Deterministic per-document trace id (stable across re-runs)."""
    return hashlib.sha256(f"fundlex:{document_id}".encode("utf-8")).hexdigest()[:32]


def digest(text: str | None) -> str | None:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _redact(text: str | None) -> Any:
    if text is None:
        return None
    if _capture_text():
        return text
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "chars": len(text)}


def _rotation_limits() -> tuple[int, int]:
    max_bytes, keep = _DEFAULT_MAX_BYTES, _DEFAULT_KEEP_ROTATED
    raw_max, raw_keep = os.environ.get("FUNDLEX_TRACE_MAX_BYTES"), os.environ.get("FUNDLEX_TRACE_KEEP_ROTATED")
    try:
        if raw_max is not None and raw_max.strip():
            max_bytes = int(raw_max.strip())
    except ValueError:
        _LOGGER.warning("invalid FUNDLEX_TRACE_MAX_BYTES=%r; using default %d", raw_max, _DEFAULT_MAX_BYTES)
    try:
        if raw_keep is not None and raw_keep.strip():
            keep = int(raw_keep.strip())
    except ValueError:
        _LOGGER.warning("invalid FUNDLEX_TRACE_KEEP_ROTATED=%r; using default %d", raw_keep, _DEFAULT_KEEP_ROTATED)
    return max_bytes, keep


def rotate_if_needed(target: str, incoming_bytes: int) -> None:
    """Roll an oversized JSONL aside and bound the rotated copies.

    Called with the write lock held.  Only sibling files whose names carry
    this module's own rotation timestamp are managed, so manually archived
    ``archive-*`` files and any other filename are never touched.  All
    failures degrade to "keep appending": rotation must never break a run
    and must never delete anything unexpected (fail-closed).
    """
    max_bytes, keep = _rotation_limits()
    if max_bytes <= 0:
        return
    try:
        if os.path.getsize(target) + incoming_bytes <= max_bytes:
            return
    except OSError:
        return
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    rotated = f"{target}.{stamp}"
    try:
        os.replace(target, rotated)
    except OSError:
        _LOGGER.warning("jsonl trace rotation failed for %s; file keeps appending", target, exc_info=True)
        return
    try:
        base = os.path.basename(target)
        siblings = sorted(name for name in os.listdir(os.path.dirname(target) or ".")
                          if name.startswith(base) and _ROTATED_SUFFIX.search(name))
    except OSError:
        return
    for stale in siblings[:max(len(siblings) - keep, 0)]:
        try:
            os.remove(os.path.join(os.path.dirname(target), stale))
        except OSError:
            _LOGGER.warning("jsonl trace prune failed for %s", stale, exc_info=True)


def _write(record: dict[str, Any]) -> None:
    """Append one record. Never raises: a trace sink must not break a run."""
    target = path()
    if target is None:
        return
    record.setdefault("ts", time.time())
    line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
    try:
        with _LOCK:
            rotate_if_needed(target, len(line.encode("utf-8")))
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(line)
    except Exception:  # pragma: no cover - defensive: tracing must never break a run
        _LOGGER.warning("jsonl trace write failed for %s", target, exc_info=True)


@contextmanager
def trace_document(*, name: str, document_id: str, metadata: dict | None = None,
                   tags: list[str] | None = None) -> Iterator[str]:
    """Open a document trace. Yields the deterministic trace id (always)."""
    _CAPTURE_TEXT.enabled = _env_flag("FUNDLEX_TRACE_CAPTURE_TEXT", True)
    tid = trace_id_for(document_id)
    if enabled():
        _write({"kind": "trace", "trace_id": tid, "document_id": document_id,
                "name": name, "metadata": metadata or {}, "tags": tags or []})
    previous = getattr(_ACTIVE, "seed", None)
    _ACTIVE.seed = document_id
    try:
        yield tid
    finally:
        _ACTIVE.seed = previous


def record_generation(*, trace_seed: str, task_type: str, prompt_version: str,
                      model: str, prompt_text: str, completion: Any,
                      event: dict) -> None:
    """Record one model attempt. ``trace_seed`` is the document id."""
    if not enabled():
        return
    usage = {}
    for key, field in (("input", "prompt_tokens"), ("output", "completion_tokens"),
                       ("total", "total_tokens")):
        value = event.get(field)
        if value is not None:
            usage[key] = value
    cost: dict[str, Any] = {}
    if event.get("estimated_cost_usd") is not None:
        cost["total"] = event["estimated_cost_usd"]
    _write({
        "kind": "generation",
        "trace_id": trace_id_for(trace_seed),
        "task_type": task_type,
        "prompt_version": prompt_version,
        "model": event.get("actual_model") or event.get("configured_model") or model,
        "input": _redact(prompt_text),
        "output": _redact(completion) if isinstance(completion, str) else completion,
        "usage": usage or None,
        "cost": cost or None,
        "metadata": {
            "attempt": event.get("attempt"),
            "http_status": event.get("http_status"),
            "request_id": event.get("request_id"),
            "finish_reason": event.get("finish_reason"),
            "latency_ms": event.get("latency_ms"),
            "reused_checkpoint": bool(event.get("reused_checkpoint")),
            "context_sha256": event.get("context_sha256"),
            "error_code": event.get("error_code"),
            "schema_failure": event.get("schema_failure"),
        },
    })


def record_score(*, name: str, value: Any, trace_seed: str,
                 comment: str | None = None, data_type: str | None = None,
                 metadata: dict | None = None) -> None:
    """Record an evaluation verdict attached to a document trace."""
    if not enabled():
        return
    _write({"kind": "score", "trace_id": trace_id_for(trace_seed), "name": name,
            "value": value, "data_type": data_type, "comment": comment,
            "metadata": metadata or {}})
