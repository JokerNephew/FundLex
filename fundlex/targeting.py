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
            if isinstance(exc, ModelError):
                from .recovery import FailureClass, classify
                if classify(exc.code) in {FailureClass.INFRASTRUCTURE,
                                          FailureClass.RESOURCE}:
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


def targets_for_open_rules(obligations: Any, targets: Sequence[Any], rules_by_id: dict[str, dict],
                           facts: Any, inspection: Any, mapping: dict[str, list[str]],
                           sections: Sequence[Any], *, limit: int = 12) -> list[Any]:
    """Create T3 locate candidates for applicable rules with no target at all.

    A rule that the scope pass mapped to a real section but the inventory/survey never
    found is exactly where T3 is needed. Rules whose policy text is already present
    (or whose class substitution is a no-op) are skipped with code evidence.
    """
    from .recall import Target, _compact, class_substitution_noop, satisfied_by_new_text

    if not _enabled():
        return []
    # Creating a locator task for a rule with no target is opt-in: a model can bind an
    # unrelated clause, so production keeps T3 for already-identified unresolved targets.
    if os.environ.get("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "0").strip().lower() not in {
            "1", "true", "on", "yes"}:
        return []
    covered_rules = {str(target.rule_id) for target in targets}
    section_by_id = {section.id: section for section in sections}
    body = _compact("\n".join(str(getattr(span, "text", ""))
                              for span in getattr(inspection, "paragraphs", ())))
    created: list[Any] = []
    seen_rules: set[str] = set()
    for record in getattr(obligations, "records", ()):
        rule_id = record.spec.rule_id
        if rule_id in seen_rules or rule_id in covered_rules:
            continue
        if record.applicability.status != "TRUE":
            continue
        section_ids = mapping.get(rule_id) or []
        if not section_ids:
            continue
        seen_rules.add(rule_id)
        if len(created) >= limit:
            break
        rule = rules_by_id.get(rule_id)
        if rule is None:
            continue
        if satisfied_by_new_text(rule, facts, body) or class_substitution_noop(rule, facts):
            continue
        location = ""
        for section_id in section_ids:
            section = section_by_id.get(section_id)
            if section is not None and section.locations:
                location = section.locations[0]
                break
        if not location:
            continue
        created.append(Target(target_id=f"T3{len(created) + 1:03d}", rule_id=rule_id,
                              location=location, quote="", state="needs_edit",
                              reason="T3_open_rule", resolution="unresolved"))
    return created
