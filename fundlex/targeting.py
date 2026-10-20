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
                       *, limit: int, radius: int = 6) -> tuple[str, set[str]]:
    from .recall import display_text, rule_context

    candidates = [str(location) for location in (getattr(target, "site_candidates", ()) or ())]
    locations: list[str] = []
    lines: list[str] = []
    if candidates:
        # Open-obligation recovery: code already narrowed the region to anchored
        # paragraphs; the model may not look anywhere else.
        for location in candidates[:12]:
            try:
                span = inspection.by_location(location)
            except Exception:  # noqa: BLE001 - a vanished candidate is not fatal
                continue
            text, _ = display_text(span.text)
            if not text.strip():
                continue
            locations.append(location)
            lines.append(f"[{location}] {text}")
        if not locations:
            # Open targets must never fall back to a radius window: that would let the
            # model choose a paragraph code did not authorize.
            return "", set()
    if not candidates:
        all_locations = [span.location for span in inspection.paragraphs]
        try:
            index = all_locations.index(target.location)
        except ValueError:
            index = 0
        start = max(0, index - radius)
        end = min(len(all_locations), index + radius + 1)
        for location in all_locations[start:end]:
            span = inspection.by_location(location)
            text, _ = display_text(span.text)
            if text.strip():
                lines.append(f"[{location}] {text}")
                locations.append(location)
    context = "\n\n".join([
        "CANDIDATE_PARAGRAPHS\n" + "\n".join(lines)[:max(1000, limit - 4000)],
        "GUIDE_OPERATION\n" + rule_context([rule], full=True),
        "FACTS\n" + json.dumps(facts.as_ledger() if hasattr(facts, "as_ledger") else {},
                              ensure_ascii=False),
        "FAILED_QUOTE\n" + str(getattr(target, "quote", "") or ""),
    ])
    return context[:limit], set(locations)


def _open_rule_candidates(inspection: Any, rule: dict, section_ids: Sequence[str],
                          section_by_id: dict[str, Any], facts: Any) -> list[str]:
    """Deterministic source search for an applicable rule that has no target.

    The candidate region is code-produced from the scope-mapped sections plus the rule's
    own anchors (topic tokens, class tokens, delete keyword bag, reference fragments).
    No anchor evidence means no candidate and therefore no model call: the obligation
    stays OPEN rather than letting the model pick an arbitrary paragraph.
    """
    from .recall import (_RULE_TOPIC_TOKENS, _compact, _delete_keyword_bag,
                         _keyword_bag_in_clause, condition_status,
                         reference_fragments)

    rule_id = str(rule.get("rule_id") or "")
    topic = tuple(_RULE_TOPIC_TOKENS.get(rule_id, ()))
    fragments: list[str] = []
    class_tokens: list[str] = []
    for operation in rule.get("operations") or []:
        if condition_status(operation.get("condition"), facts) != "TRUE":
            continue
        old_text = _compact(str(operation.get("old_text") or ""))
        if len(old_text) >= 4:
            fragments.append(old_text)
        if rule.get("class_substitution"):
            class_tokens.extend(re.findall(r"[A-ZＡ-Ｚ]\s*类", str(operation.get("old_text") or "")))
    for variant in rule.get("old_text_variants") or []:
        old_text = _compact(str(variant or ""))
        if len(old_text) >= 4:
            fragments.append(old_text)
        fragments.extend(_compact(fragment) for fragment in reference_fragments(str(variant or "")))
    bag = _delete_keyword_bag(rule, facts)
    if not (topic or fragments or bag or class_tokens):
        return []
    found: list[str] = []
    for section_id in section_ids:
        section = section_by_id.get(section_id)
        for location in (getattr(section, "locations", ()) if section is not None else ()):
            try:
                span = inspection.by_location(location)
            except Exception:  # noqa: BLE001
                continue
            text = _compact(str(getattr(span, "text", "")))
            if len(text) < 12:
                continue
            if topic and not all(token in text for token in topic):
                continue
            if class_tokens and not any(token in text for token in class_tokens):
                continue
            if bag and not _keyword_bag_in_clause(text, bag, window=80):
                continue
            if fragments and not bag and not any(fragment in text
                                                 for fragment in fragments):
                # The rule's own wording is the strong anchor.  Delete rules whose
                # keyword bag matched are exempt (G15/G17 real paraphrases do not carry
                # the guide reference verbatim).  A broad topic token alone is never
                # enough to select every fee paragraph in the section.
                continue
            if location not in found:
                found.append(location)
            if len(found) >= 12:
                return found
    return found


def _open_rule_quote_ok(rule: dict, facts: Any, paragraph_text: str, quote: str,
                        span: Any = None, inspection: Any = None) -> tuple[bool, str]:
    """Code verification of the locator's quote for an open obligation.

    The quote itself must carry the rule's own wording (class token / delete keyword bag
    / reference fragment), not just appear somewhere in an anchored paragraph.  A bare
    topic token such as ``销售服务费`` is not a locatable edit site.
    """
    from .recall import (_RULE_TOPIC_TOKENS, _compact, _delete_keyword_bag,
                         _keyword_bag_in_clause, condition_status, target_site_ok)

    text = _compact(paragraph_text)
    compact_quote = _compact(quote)
    if len(compact_quote) < 6:
        return False, "quote_too_short"
    if span is not None and inspection is not None:
        if not target_site_ok(str(rule.get("rule_id") or ""), span, inspection):
            return False, "target_site_mismatch"
    topic = tuple(_RULE_TOPIC_TOKENS.get(str(rule.get("rule_id") or ""), ()))
    if topic and not all(token in text for token in topic):
        return False, "topic_missing"
    operations = [operation for operation in rule.get("operations") or []
                  if condition_status(operation.get("condition"), facts) == "TRUE"]
    fragments = [_compact(str(operation.get("old_text") or ""))
                 for operation in operations
                 if len(_compact(str(operation.get("old_text") or ""))) >= 4]
    class_tokens = [token
                    for operation in operations
                    for token in re.findall(r"[A-ZＡ-Ｚ]\s*类",
                                            str(operation.get("old_text") or ""))]
    if rule.get("class_substitution"):
        if class_tokens and not any(token in compact_quote for token in class_tokens):
            return False, "quote_class_missing"
    bag = _delete_keyword_bag(rule, facts)
    if bag and not _keyword_bag_in_clause(compact_quote, bag, window=80):
        return False, "quote_keyword_bag_missing"
    if not rule.get("class_substitution") and not bag and fragments:
        if not any(fragment in compact_quote for fragment in fragments):
            # No generic topic fallback: "调低...费率" also matches the management-fee
            # clause next to G05's redemption-fee clause.
            return False, "quote_anchor_missing"
    return True, ""


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
        context, allowed_locations = _candidate_context(
            inspection, target, rule, facts, limit=gateway.max_context_chars)
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
        if location not in allowed_locations:
            record["status"] = "rejected"
            record["reject_reason"] = "location_outside_candidate_window"
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
        open_rule = bool(getattr(target, "site_candidates", ()))
        if open_rule:
            from .recall import _compact
            if _compact(span.text).count(_compact(quote)) != 1:
                record["status"] = "rejected"
                record["reject_reason"] = "ambiguous_occurrence"
                records.append(record)
                continue
            anchor_ok, anchor_reason = _open_rule_quote_ok(
                rule, facts, span.text, quote, span=span, inspection=inspection)
            if not anchor_ok:
                record["status"] = "rejected"
                record["reject_reason"] = f"anchor_mismatch:{anchor_reason}"
                records.append(record)
                continue
        target.location = location
        target.start, target.end = start, end
        target.quote = quote
        target.resolution = "resolved"
        target.segment_ok = containing_segment(span, start, end) is not None
        target.reason = f"{target.reason}|locator:{str(value.get('semantic_role') or '')}".strip("|")
        record["status"] = "bound"
        duplicates = 0
        if open_rule and isinstance(targets, list):
            # Identical clause copies (body and contract summary) must be edited too;
            # otherwise the same obligation is only half carried out.
            from .recall import Target
            for other_location in getattr(target, "site_candidates", ()):
                if other_location == location or duplicates >= 4:
                    continue
                try:
                    other_span = inspection.by_location(other_location)
                except DocxError:
                    continue
                if _compact(other_span.text) != _compact(span.text):
                    # Only a byte-identical clause copy (body vs contract summary) may be
                    # cloned; a paragraph that merely contains the same short phrase is
                    # not the same obligation site.
                    continue
                other_offsets = resolve_quote(other_span, quote)
                if other_offsets is None:
                    continue
                if _compact(other_span.text).count(_compact(quote)) != 1:
                    continue
                other_start, other_end = other_offsets
                clone = Target(
                    target_id=f"{target.target_id}-D{duplicates + 1}", rule_id=target.rule_id,
                    location=other_location, quote=quote, state="needs_edit",
                    reason=f"T3_open_rule_duplicate_copy|locator:{target.reason}",
                    start=other_start, end=other_end, resolution="resolved",
                    segment_ok=containing_segment(other_span, other_start, other_end) is not None,
                    operations=tuple(target.operations), site_candidates=(other_location,))
                targets.append(clone)
                duplicates += 1
        if duplicates:
            record["duplicates"] = duplicates
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
    # Open-obligation recovery (external review 2026-10-20 P1): "auto" enables the
    # locator only for applicable rules whose candidate paragraphs were narrowed by code
    # anchors; no anchor evidence means no model call and the obligation stays OPEN.
    # "1"/"on" keeps the legacy section-first candidate for debugging; "0" disables.
    mode = os.environ.get("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto").strip().lower()
    if mode in {"0", "false", "off", "no"}:
        return []
    auto = mode in {"", "auto", "default"}
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
        if auto:
            from .recall import _compact as _compact_rule, condition_status
            applicable = [operation for operation in rule.get("operations") or []
                          if condition_status(operation.get("condition"), facts) == "TRUE"]
            strong = bool(rule.get("class_substitution")) or any(
                len(_compact_rule(str(operation.get("old_text") or ""))) >= 4
                for operation in applicable)
            if not strong:
                continue
        candidates = _open_rule_candidates(inspection, rule, section_ids, section_by_id, facts)
        if not candidates:
            if auto:
                # The system found the missed obligation but cannot prove where it is;
                # do not let a model search the whole contract.
                continue
            candidates = [section_by_id[section_id].locations[0]
                          for section_id in section_ids
                          if section_id in section_by_id
                          and getattr(section_by_id[section_id], "locations", ())][:1]
        if not candidates:
            continue
        created.append(Target(target_id=f"T3{len(created) + 1:03d}", rule_id=rule_id,
                              location=candidates[0], quote="", state="needs_edit",
                              reason=f"T3_open_rule:candidates={len(candidates)}",
                              resolution="unresolved",
                              site_candidates=tuple(candidates)))
    return created
