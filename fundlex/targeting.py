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


def _open_operation_candidates(
        inspection: Any, rule: dict, record: Any, section_ids: Sequence[str],
        section_by_id: dict[str, Any], facts: Any,
        existing_targets: Sequence[Any] = ()) -> list[str]:
    """Operation-specific candidate discovery, strongest evidence first.

    P1 same-rule sibling site, P2 exact operation old_text, P3 variant/reference
    fragment, P4 rule keyword bag + topic/site guard.  The returned paragraphs are the
    only places the bounded locator may choose from; no candidate means the obligation
    stays OPEN instead of searching the whole contract.
    """
    from .recall import (_RULE_TOPIC_TOKENS, _compact, _delete_keyword_bag,
                         _keyword_bag_in_clause, _looks_like_heading,
                         condition_status, reference_fragments, target_operation_keys,
                         _declared_operation_key)

    rule_id = str(rule.get("rule_id") or "")
    operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
    operation = (rule.get("operations") or [])[operation_index]
    old_text = _compact(str(operation.get("old_text") or ""))
    variants = [_compact(str(value)) for value in (rule.get("old_text_variants") or [])
                if _compact(str(value))]
    fragments: list[str] = []
    if len(old_text) >= 4:
        fragments.append(old_text)
    for variant in variants:
        if len(variant) >= 4:
            fragments.append(variant)
        fragments.extend(_compact(fragment) for fragment in reference_fragments(variant))
    topic = tuple(_RULE_TOPIC_TOKENS.get(rule_id, ()))
    bag = _delete_keyword_bag(rule, facts)
    class_rule = bool(rule.get("class_substitution"))
    append_site = (str(operation.get("op") or "") == "append"
                   and rule_id not in {"G01", "G03"})
    class_tokens = ["基金份额类别", "份额类别", "将基金份额分为", "分为A类", "分为C类",
                    "收费方式", "不同类别", "基金份额设置"]
    facts_classes = tuple(f"{item.name}类" if "类" not in item.name else item.name
                         for item in getattr(facts, "current_classes", ()) or ())

    def classify(text: str) -> int:
        """0 = no candidate, 1 = class/topic only, 2 = strong anchor."""
        if len(text) < 12:
            return 0
        if topic and not all(token in text for token in topic):
            return 0
        if rule_id == "G12" and not (
                "赎回费用由" in text and "基金财产" in text):
            return 0
        if rule_id == "G11" and not ("申购费用由" in text and "承担" in text):
            return 0
        if rule_id == "G08" and not ("申购费率" in text and "招募说明书" in text):
            return 0
        if rule_id == "G13" and not (
                "少于7日" in text and "赎回费" in text and
                ("1.5%" in text or "1.50%" in text)):
            return 0
        if append_site:
            # G16 appends into the sales-service-fee accrual/payment clause, not the
            # class-definition paragraph or a fee formula row (its class_substitution
            # is only a slot).  Payment-mechanism wording ranks above a bare accrual
            # mention.
            if "销售服务费" not in text:
                return 0
            if any(token in text for token in ("按月支付", "支付日期", "划出",
                                                "次月", "一次性")):
                return 3
            if any(token in text for token in ("计提", "支付", "按月")):
                return 2
            return 0
        if class_rule:
            has_class = any(token in text for token in class_tokens)
            has_fact_class = (not facts_classes or
                              any(_compact(name) in text for name in facts_classes))
            return 2 if has_class and has_fact_class else 0
        if fragments and any(fragment in text for fragment in fragments):
            return 2
        if bag and _keyword_bag_in_clause(text, bag, window=80):
            return 2
        return 0

    ordered: list[str] = []
    scores: dict[str, int] = {}

    def add(location: str, score: int) -> None:
        if not location or location in scores and scores[location] >= score:
            return
        scores[location] = score
        if location not in ordered:
            ordered.append(location)

    def body_at(location: str) -> str:
        try:
            return _compact(str(getattr(inspection.by_location(location), "text", "")))
        except Exception:  # noqa: BLE001 - a vanished candidate is not fatal
            return ""

    # P1: a sibling operation of the same rule already proved this clause site.
    sibling_locations: list[str] = []
    for target in existing_targets:
        if str(getattr(target, "rule_id", "")) != rule_id:
            continue
        if getattr(target, "out_of_scope", False) or getattr(target, "state", "") not in {
                "needs_edit", "satisfied"}:
            continue
        sibling_keys = set(getattr(target, "operations", ()) or ())
        if not sibling_keys:
            sibling_keys = target_operation_keys(target, rule, inspection)
        current_id = str(getattr(record.spec, "operation_id", "") or
                         _declared_operation_key(rule_id, operation_index, operation))
        if current_id in sibling_keys:
            continue
        for location in ([target.location] if not getattr(target, "composite", ())
                         else [part.rsplit(":", 2)[0] for part in target.composite]):
            if location not in sibling_locations:
                sibling_locations.append(location)
    for location in sibling_locations:
        if classify(body_at(location)) == 2:
            add(location, 3)

    # P2/P3/P4: scan only the scope-mapped sections, strongest anchor first.
    for section_id in section_ids:
        section = section_by_id.get(section_id)
        for location in (getattr(section, "locations", ()) if section is not None else ()):
            text = body_at(location)
            if not text:
                continue
            score = classify(text)
            if score == 0:
                continue
            if class_rule and _looks_like_heading(
                    str(getattr(inspection.by_location(location), "text", ""))):
                continue
            if old_text and old_text in text:
                score = 3
            elif any(fragment and fragment in text for fragment in fragments):
                score = 2
            add(location, score)
    def sort_key(location: str) -> tuple[int, int]:
        return (-scores.get(location, 0), ordered.index(location))
    if append_site:
        strong = [location for location in ordered if scores.get(location, 0) >= 3]
        if strong:
            return sorted(strong, key=sort_key)[:12]
    return sorted(ordered, key=sort_key)[:12]


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
        if not class_tokens:
            # Append-style class guidance (G01/G03): the edit site is the class-
            # definition clause, NOT the new policy wording.  "直销/不收取/销售服务费"
            # are expected artifact effects and must not be required in the source
            # quote (plan §8).  Require a real class-definition/setup site instead.
            if str(rule.get("rule_id")) == "G16":
                if not ("销售服务费" in compact_quote and
                        any(token in compact_quote for token in ("计提", "支付", "按月"))):
                    return False, "quote_sales_service_site_missing"
            else:
                class_site_tokens = ("基金份额类别", "份额类别", "将基金份额分为",
                                     "分为A类", "分为C类", "收费方式", "不同类别",
                                     "基金份额设置")
                if not any(token in compact_quote or token in text
                           for token in class_site_tokens):
                    return False, "quote_class_site_missing"
                fact_classes = tuple(
                    f"{item.name}类" if "类" not in item.name else item.name
                    for item in getattr(facts, "current_classes", ()) or ())
                if fact_classes and not any(_compact(name) in text for name in fact_classes):
                    return False, "class_structure_missing"
            if not compact_quote:
                return False, "quote_too_short"
        if rule.get("rule_id") in {"G02", "G04"}:
            if not any(token in compact_quote for token in
                       ("基金份额类别", "份额类别", "将基金份额分为", "分类")):
                return False, "quote_site_missing"
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


def target_for_claim_site(record: Any, location: str, targets: Sequence[Any],
                          rules_by_id: dict[str, dict], facts: Any, inspection: Any,
                          *, target_id: str = "") -> Any | None:
    """Create the repair target for a Claim-discovered required occurrence.

    Claim Replay can prove that a duplicate body/summary site must carry the
    operation even when an active target already exists elsewhere.  That evidence
    is stronger than the old "one active target covers the operation" shortcut;
    it authorizes a site-specific repair target, not a global fuzzy clone.
    """
    from .recall import Target, resolve_quote
    from .generation.effects import operation_site_bound

    rule_id = str(getattr(record.spec, "rule_id", "") or "")
    operation_id = str(getattr(record.spec, "operation_id", "") or "")
    if not rule_id or not operation_id or not location:
        return None
    rule = rules_by_id.get(rule_id)
    if rule is None:
        return None
    active = [target for target in targets
              if operation_id in (getattr(target, "operations", ()) or ())
              and getattr(target, "state", "") == "needs_edit"
              and not getattr(target, "out_of_scope", False)]
    if any(getattr(target, "location", "") == location for target in active):
        return None
    if not active:
        return None
    source = active[0]
    try:
        span = inspection.by_location(location)
    except Exception:  # noqa: BLE001 - vanished location is not a repair site
        return None
    quote = str(getattr(source, "quote", "") or "")
    located = resolve_quote(span, quote) if quote else None
    if located is None:
        for reference in [str(getattr(record.spec, "old_text", "") or ""),
                          *tuple(getattr(record.spec, "alternatives", ()) or ())]:
            if not reference:
                continue
            candidate = resolve_quote(span, reference)
            if candidate is not None:
                quote, located = reference, candidate
                break
    if located is None:
        return None
    if not operation_site_bound(record.spec, quote, inspection, location, facts):
        return None
    start, end = located
    return Target(
        target_id=target_id or f"R{len(targets) + 1:03d}", rule_id=rule_id,
        location=location, quote=quote, state="needs_edit",
        reason=f"claim_required_site:{operation_id}", start=start, end=end,
        resolution="resolved", segment_ok=True, operations=(operation_id,))


def target_for_missing_operation(
        record: Any, targets: Sequence[Any], rules_by_id: dict[str, dict], facts: Any,
        inspection: Any, mapping: dict[str, list[str]], sections: Sequence[Any],
        *, target_id: str = "") -> Any | None:
    """Recovery target for one applicable operation Claim Replay proved missing.

    Candidate discovery is the same operation-first ladder as open-obligation recovery
    (sibling site -> operation old_text -> variants -> keyword bag).  No code-proven
    candidate means no model location guess; the operation stays unresolved.
    """
    if not _enabled():
        return None
    from .recall import Target, _declared_operation_key

    rule_id = str(getattr(record.spec, "rule_id", "") or "")
    operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
    rule = rules_by_id.get(rule_id)
    if rule is None:
        return None
    operations = rule.get("operations") or []
    operation = operations[operation_index] if 0 <= operation_index < len(operations) else {}
    operation_id = str(getattr(record.spec, "operation_id", "") or
                       _declared_operation_key(rule_id, operation_index, operation))
    for target in targets:
        keys = set(getattr(target, "operations", ()) or ())
        if operation_id in keys and getattr(target, "state", "") == "needs_edit" \
                and not getattr(target, "out_of_scope", False):
            return None
    section_ids = mapping.get(rule_id) or []
    section_by_id = {section.id: section for section in sections}
    candidates = _open_operation_candidates(
        inspection, rule, record, section_ids, section_by_id, facts,
        existing_targets=targets)
    if not candidates:
        return None
    return Target(target_id=target_id or f"R{operation_index + 1:03d}",
                  rule_id=rule_id, location=candidates[0], quote="",
                  state="needs_edit",
                  reason=f"recovery_missing_operation:{operation_id}:"
                         f"candidates={len(candidates)}",
                  resolution="unresolved", operations=(operation_id,),
                  site_candidates=tuple(candidates))


def targets_for_open_rules(obligations: Any, targets: Sequence[Any], rules_by_id: dict[str, dict],
                           facts: Any, inspection: Any, mapping: dict[str, list[str]],
                           sections: Sequence[Any], *, limit: int = 12) -> list[Any]:
    """Create T3 locate candidates for applicable OPERATIONS with no target.

    Coverage is operation-first: ``G05:0`` having a target does not cover ``G05:2``.
    The function keeps its historical name for callers, but no rule-level
    ``seen_rules``/``covered_rules`` shortcut remains.
    """
    from .recall import (Target, _compact, _append_obligation_present,
                         class_substitution_noop, instantiate_slots,
                         satisfied_operation_keys, target_operation_keys,
                         _declared_operation_key, condition_status)

    if not _enabled():
        return []
    mode = os.environ.get("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto").strip().lower()
    if mode in {"0", "false", "off", "no"}:
        return []
    auto = mode in {"", "auto", "default"}
    section_by_id = {section.id: section for section in sections}
    body = _compact("\n".join(str(getattr(span, "text", ""))
                              for span in getattr(inspection, "paragraphs", ())))
    covered_operations: set[str] = set()

    def target_body(target: Any) -> str:
        locations = ([target.location] if not getattr(target, "composite", ())
                     else [part.rsplit(":", 2)[0] for part in target.composite])
        chunks: list[str] = []
        for location in locations:
            try:
                chunks.append(_compact(str(getattr(inspection.by_location(location), "text", ""))))
            except Exception:  # noqa: BLE001
                continue
        return "".join(chunks)

    for target in targets:
        rule_id = str(target.rule_id)
        rule = rules_by_id.get(rule_id) or {}
        keys = set(getattr(target, "operations", ()) or ())
        if not keys:
            keys = target_operation_keys(target, rule, inspection)
        if target.state == "needs_edit" and not target.out_of_scope:
            covered_operations.update(keys)
        elif target.state == "satisfied":
            operations = list(rule.get("operations") or ())
            statuses = [condition_status(operation.get("condition"), facts)
                        for operation in operations]
            applicable = [operation for operation, status in zip(operations, statuses)
                          if status == "TRUE"]
            # A satisfied applicable noop is a valid obligation proof, while its
            # target is excluded from audit so a sibling (G22) may edit the same
            # paragraph.  Preserve operation coverage here without making that target
            # an editable/auditable site (G21/G22).
            if target.out_of_scope and not (
                    applicable and all(operation.get("op") == "noop"
                                       for operation in applicable)):
                continue
            if keys:
                covered_operations.update(keys)
            else:
                covered_operations.update(
                    satisfied_operation_keys(rule, facts, target_body(target)))
        elif target.state == "absent" and not target.out_of_scope:
            # An "absent" verdict belongs only to the operation explicitly attributed
            # to that target.  In particular, an absent G05:0 replace source does not
            # prove the replacement exists, and must not also close G05:2 merely because
            # that sibling's literal is absent from the same paragraph (D19 p130).
            # Site-bound negative proofs for a delete are added later by
            # resolve_absent_site_targets(); until then, an un-attributed absent target
            # cannot close any operation.
            for operation_key in keys:
                try:
                    index = int(str(operation_key).split(":", 1)[1])
                except (IndexError, ValueError):
                    continue
                operations = rule.get("operations") or []
                if not 0 <= index < len(operations):
                    continue
                operation = operations[index]
                old_text = _compact(str(operation.get("old_text") or ""))
                new_text = str(operation.get("new_text") or "")
                if operation.get("op") == "replace":
                    instantiated, issues = instantiate_slots(new_text, facts)
                    required = _compact(instantiated if not issues else new_text)
                    if required and required in body and (not old_text or old_text not in body):
                        covered_operations.add(str(operation_key))
                elif (operation.get("op") == "delete"
                      and str(rule_id) != "G05"
                      and old_text and old_text not in body):
                    # G05's independent filing deletion requires the class-setup site
                    # proof below; other rules retain the legacy absent-delete path.
                    covered_operations.add(str(operation_key))

    def operation_closed(rule: dict, record: Any) -> bool:
        operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
        operation = (rule.get("operations") or [])[operation_index]
        old_text = _compact(str(operation.get("old_text") or ""))
        new_text = str(operation.get("new_text") or "")
        if operation.get("op") == "append":
            instantiated, issues = instantiate_slots(new_text, facts)
            required = new_text if issues else instantiated
            return bool(required) and _append_obligation_present(
                str(rule.get("rule_id") or ""), required, body)
        if operation.get("op") == "delete":
            if str(rule.get("rule_id") or "") == "G05":
                # G05:2 is an independent filing deletion.  Document-wide absence is
                # insufficient because the same phrase may occur in an unrelated
                # amendment clause; require the class-setup operation site to prove
                # the negative (resolve_absent_site_targets).
                return False
            return bool(old_text) and old_text not in body
        if operation.get("op") == "replace":
            instantiated, issues = instantiate_slots(new_text, facts)
            required = _compact(instantiated if not issues else new_text)
            # New policy present and old wording gone: already satisfied.  An absent
            # source old wording with the new effect present is also already satisfied
            # (the inventory/survey may discover it after the applicable branch ran).
            return bool(required) and required in body and (
                not old_text or old_text not in body or
                _compact(new_text).find(old_text) >= 0)
        return False

    created: list[Any] = []
    seen_operations: set[str] = set()
    for record in getattr(obligations, "records", ()):
        rule_id = str(getattr(record.spec, "rule_id", "") or "")
        rule = rules_by_id.get(rule_id) or {}
        operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
        operations = rule.get("operations") or []
        operation = (operations[operation_index]
                      if 0 <= operation_index < len(operations) else None)
        operation_id = str(getattr(record.spec, "operation_id", "") or
                           _declared_operation_key(
                               rule_id, operation_index, operation))
        if operation_id in seen_operations or operation_id in covered_operations:
            continue
        if record.applicability.status != "TRUE":
            continue
        section_ids = mapping.get(rule_id) or []
        if not section_ids:
            continue
        seen_operations.add(operation_id)
        if len(created) >= limit:
            break
        if rule is None or operation_closed(rule, record):
            continue
        if rule.get("class_substitution") and all(
                operation.get("op") == "replace"
                for operation in rule.get("operations") or []) and \
                class_substitution_noop(rule, facts):
            continue

        if auto:
            from .recall import _compact as _compact_rule
            operation = (rule.get("operations") or [])[operation_index]
            strong = bool(rule.get("class_substitution")) or (
                condition_status(operation.get("condition"), facts) == "TRUE"
                and len(_compact_rule(str(operation.get("old_text") or ""))) >= 4)
            if not strong:
                continue
        candidates = _open_operation_candidates(
            inspection, rule, record, section_ids, section_by_id, facts,
            existing_targets=targets)
        if not candidates:
            if auto:
                # The missed operation has no code-proven site; keep it OPEN rather
                # than letting the model search the whole contract.
                continue
            candidates = [section_by_id[section_id].locations[0]
                          for section_id in section_ids
                          if section_id in section_by_id
                          and getattr(section_by_id[section_id], "locations", ())][:1]
        if not candidates:
            continue
        created.append(Target(target_id=f"T3{len(created) + 1:03d}", rule_id=rule_id,
                              location=candidates[0], quote="", state="needs_edit",
                              reason=f"T3_open_operation:{operation_id}:"
                                     f"candidates={len(candidates)}",
                              resolution="unresolved",
                              operations=(operation_id,),
                              site_candidates=tuple(candidates)))
    return created
