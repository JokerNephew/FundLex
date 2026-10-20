"""T3 primary-model target locator (plan §11).

T1 exact and T2 deterministic semantic binding stay the default.  Only when both
fail does the primary model see a bounded candidate window and propose a location and
literal quote.  The model never supplies offsets: code re-resolves the quote against
the real document and re-checks the containing segment.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Sequence

LOCATE_SCHEMA = {
    "type": "object",
    "required": ["location", "quote", "semantic_role", "reason"],
    "properties": {
        "location": {"type": "string"},
        "quote": {"type": "string"},
        "semantic_role": {"type": "string"},
        "reason": {"type": "string"},
    },
}

LOCATE_INSTRUCTION = (
    "The deterministic resolver could not bind this obligation to the contract. Read the "
    "candidate paragraphs and return the ONE paragraph location plus an exact contiguous "
    "quote from that paragraph that carries the obligation. Do not paraphrase, do not "
    "merge two paragraphs, and do not return offsets. If no paragraph carries it, return "
    "an empty quote and explain why. semantic_role states what the clause does (for "
    "example class_definition, subscription_fee, payment_mechanism)."
)

LOCATE_PROMPT_VERSION = "recall_locate_v1"


def _enabled() -> bool:
    return os.environ.get("FUNDLEX_TARGET_LOCATOR", "1").strip().lower() not in {
        "0", "false", "off", "no"}


def _candidate_context(inspection: Any, target: Any, rule: dict, facts: Any,
                       *, limit: int, radius: int = 6) -> str:
    from .recall import display_text, rule_context

    locations = [span.location for span in inspection.paragraphs]
    try:
        index = locations.index(target.location)
    except ValueError:
        index = 0
    start = max(0, index - radius)
    end = min(len(locations), index + radius + 1)
    lines: list[str] = []
    for location in locations[start:end]:
        span = inspection.by_location(location)
        text, _ = display_text(span.text)
        if text.strip():
            lines.append(f"[{location}] {text}")
    context = "\n\n".join([
        "CANDIDATE_PARAGRAPHS\n" + "\n".join(lines)[:max(1000, limit - 4000)],
        "GUIDE_OPERATION\n" + rule_context([rule], full=True),
        "FACTS\n" + json.dumps(facts.as_ledger() if hasattr(facts, "as_ledger") else {},
                              ensure_ascii=False),
        "FAILED_QUOTE\n" + str(getattr(target, "quote", "") or ""),
    ])
    return context[:limit]


def locate_unresolved_targets(targets: Sequence[Any], inspection: Any,
                              rules_by_id: dict[str, dict], facts: Any, gateway: Any
                              ) -> list[dict[str, Any]]:
    """Try the model locator for every still-unresolved target; record every attempt."""
    if not _enabled():
        return []
    from .docx import DocxError
    from .recall import containing_segment, resolve_quote

    records: list[dict[str, Any]] = []
    for target in targets:
        if target.state != "needs_edit" or target.resolution in {"resolved", "composite"}:
            continue
        rule = rules_by_id.get(target.rule_id)
        if rule is None:
            continue
        context = _candidate_context(inspection, target, rule, facts,
                                     limit=gateway.max_context_chars)
        record = {"target_id": target.target_id, "rule_id": target.rule_id}
        try:
            result = gateway.call(task_type="recall_locate", bounded_context=context,
                                  response_schema=LOCATE_SCHEMA,
                                  instruction=LOCATE_INSTRUCTION,
                                  prompt_version=LOCATE_PROMPT_VERSION)
        except Exception as exc:  # noqa: BLE001 - recorded; deterministic failure remains
            from .model import ModelError
            if isinstance(exc, ModelError) and exc.code in {
                    "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED",
                    "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_CIRCUIT_OPEN",
                    "MODEL_LEDGER_UNAVAILABLE", "MODEL_CONFIG_MISSING",
                    "MODEL_HTTP_ERROR", "MODEL_RETRY_EXHAUSTED"}:
                raise
            record.update(status="error", reason=f"{type(exc).__name__}:"
                          f"{getattr(exc, 'code', '')}")
            records.append(record)
            continue
        value = result.value if isinstance(result.value, dict) else {}
        location = str(value.get("location") or "").strip()
        quote = str(value.get("quote") or "").strip()
        record.update(location=location, quote=quote,
                      semantic_role=str(value.get("semantic_role") or ""),
                      reason=str(value.get("reason") or ""))
        if not location or not quote:
            record["status"] = "rejected"
            record["reject_reason"] = "empty_location_or_quote"
            records.append(record)
            continue
        try:
            span = inspection.by_location(location)
        except DocxError:
            record["status"] = "rejected"
            record["reject_reason"] = "location_not_found"
            records.append(record)
            continue
        located = resolve_quote(span, quote)
        if located is None:
            record["status"] = "rejected"
            record["reject_reason"] = "quote_not_found"
            records.append(record)
            continue
        start, end = located
        if not containing_segment(span, start, end) and start != end:
            record["status"] = "rejected"
            record["reject_reason"] = "segment_invalid"
            records.append(record)
            continue
        target.location = location
        target.start, target.end = start, end
        target.quote = quote
        target.resolution = "resolved"
        target.segment_ok = containing_segment(span, start, end) is not None
        target.reason = f"{target.reason}|locator:{str(value.get('semantic_role') or '')}".strip("|")
        record["status"] = "bound"
        records.append(record)
    return records
