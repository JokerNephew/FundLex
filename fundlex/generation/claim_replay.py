"""Phase 8: artifact claim replay (plan v4 §28.2).

Re-runs the deterministic V1/V2 checks against the *written* artifact: the
pipeline passes the inspection of the final DOCX, so an edit that never reached
the file — or reached it mutated — is caught here rather than being assumed
correct from the in-memory replacement. The structural half (hashes, manifest,
fingerprints) stays in ``output_validation``.

Codes: ``CLAIM_LOCATION_MISSING``, ``CLAIM_NO_CHANGE_APPLIED``,
``CLAIM_REPLACEMENT_MISSING``, ``CLAIM_VALIDATION_FAILED``.
"""
import re
from typing import Any, Mapping, Sequence

from .validators import Authorization


def _compact(value: str) -> str:
    return re.sub(r"[\s\u3000\u00a0\u200b]+", "", value or "")


def _g16_duplicate_effects(original: Any, artifact: Any,
                           rules_by_id: Mapping[str, dict], facts: Any,
                           records: Sequence[Any]) -> list[dict[str, Any]]:
    """Count written G16 policy across each complete SOURCE clause (FL-D192).

    Payment/usage paragraphs may be deleted by G15/G17 in the artifact. Source
    addresses therefore define the scope; artifact text cannot redefine its own
    authorization. This also runs for replay callers without an obligation ledger.
    """
    from ..recall import _g16_clause_locations, instantiate_slots
    rule = rules_by_id.get("G16") or {}
    failures = []
    for index, operation in enumerate(rule.get("operations") or ()):
        if operation.get("op") != "append":
            continue
        operation_id = _operation_key(rule, index, operation)
        expected, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        needle = _compact(expected)
        if issues or len(needle) < 20:
            continue  # Independent operation/fact checks retain their own failures.
        record = next((item for item in records
                       if item.spec.operation_id == operation_id), None)
        for locations in _g16_clause_locations(original):
            try:
                before = _compact("".join(original.by_location(loc).text for loc in locations))
                after = _compact("".join(artifact.by_location(loc).text for loc in locations))
            except (KeyError, ValueError, IndexError, AttributeError):
                continue  # Missing paragraphs are independently rejected by replay.
            if after.count(needle) > max(1, before.count(needle)):
                failures.append({
                    "rule_id": "G16", "operation_id": operation_id,
                    "obligation_id": record.obligation_id if record else "",
                    "location": locations[-1], "locations": list(locations),
                    "code": "CLAIM_DUPLICATE_EFFECT",
                    "reason": "the final G16 policy appears more than once in one source fee clause",
                })
    return failures


def _facts_numbers(facts: Any) -> tuple[str, ...]:
    """Numbers whose provenance is a VERIFIED fact (rates etc.)."""
    if facts is None or not hasattr(facts, "as_ledger"):
        return ()
    import json
    try:
        ledger = json.dumps(facts.as_ledger(), ensure_ascii=False)
    except (TypeError, ValueError):
        return ()
    return tuple(dict.fromkeys(re.findall(r"\d+(?:\.\d+)?%?", ledger)))


def _rule_ids(edit: Mapping[str, Any]) -> list[str]:
    ids = [part.strip() for part in str(edit.get("rule_id") or "").split("+")]
    for component in edit.get("components") or []:
        if isinstance(component, dict):
            ids.extend(part.strip()
                       for part in str(component.get("rule_id") or "").split("+"))
    return sorted({rule_id for rule_id in ids if rule_id})


def _operation_keys(edit: Mapping[str, Any],
                    targets_by_id: Mapping[str, Mapping[str, Any]] | None) -> list[str]:
    """Operation identity priority: edit/component own keys, then target, then empty.

    The target is deliberately no longer the primary source: a merged or cloned target
    id can be synthetic, and a target can cover several operations.  The edit itself is
    the execution record (plan §23).
    """
    keys = [str(key) for key in (edit.get("operation_keys") or ()) if str(key).strip()]
    if keys:
        return keys
    evidence = edit.get("evidence") or {}
    keys = [str(key) for key in (evidence.get("operation_keys") or ())
            if str(key).strip()]
    if keys:
        return keys
    target = (targets_by_id or {}).get(str(edit.get("target_id") or ""))
    if isinstance(target, Mapping):
        # A target carrying several operations is a shared planning container, not
        # authorization for an unattributed component.  Let callers with an
        # explicit operation key select the operation; otherwise fail closed rather
        # than allowing a component to borrow its sibling's rights.
        keys = [str(key) for key in (target.get("operations") or []) if str(key).strip()]
        if len(keys) == 1:
            return keys
    return []


def _operation_key(rule: Mapping[str, Any], index: int,
                   operation: Mapping[str, Any] | None = None) -> str:
    """Resolve the guide-declared identity, with legacy fixture compatibility."""
    declared = str((operation or {}).get("operation_id") or "").strip()
    rule_id = str(rule.get("rule_id") or "").strip()
    return declared or f"{rule_id}:{index}"


def _operation_record(rule: Mapping[str, Any], index: int, obligations: Any) -> Any:
    if obligations is None:
        return None
    operations = list(rule.get("operations") or [])
    operation = operations[index] if 0 <= index < len(operations) else None
    return obligations.record(_operation_key(rule, index, operation))


def _validation_status(validation: Any) -> str:
    """Return a conservative validator status.

    Validators historically returned PASS/FAIL.  Newer or injected validators may
    return UNKNOWN/CONFLICT; neither is evidence of a successful artifact claim.
    Keeping this normalization local also protects replay when an older validator
    object is mixed with a newer report.
    """
    status = str(getattr(validation, "verdict", "UNKNOWN") or "UNKNOWN").upper()
    return status if status in {"PASS", "FAIL", "UNKNOWN", "CONFLICT"} else "UNKNOWN"


def _validation_failure_code(validation: Any) -> str:
    status = _validation_status(validation)
    if status == "UNKNOWN":
        return "CLAIM_VALIDATION_UNKNOWN"
    if status == "CONFLICT":
        return "CLAIM_VALIDATION_CONFLICT"
    return "CLAIM_VALIDATION_FAILED"


def _operation_indices(rule: Mapping[str, Any], keys: Sequence[str],
                       obligations: Any) -> tuple[list[int], str]:
    """Operation indices an edit is authorized to execute.

    Returns ``(indices, scope)`` where scope is ``operations`` when the target named
    explicit operation keys, else ``rule`` (legacy: no attribution available).
    """
    operations = list(rule.get("operations") or [])
    indices: set[int] = set()
    for key in keys:
        record = obligations.record(str(key)) if obligations is not None else None
        if record is not None and record.spec.rule_id == rule.get("rule_id"):
            indices.add(int(record.spec.operation_index))
            continue
        rule_id = str(rule.get("rule_id") or "")
        for index, operation in enumerate(operations):
            # The declared guide identity is authoritative.  The helper itself
            # retains RULE:index only for genuinely legacy operations; adding a
            # second derived alias here would let a custom operation borrow a
            # sibling's obligation.
            if str(key) == _operation_key(rule, index, operation):
                indices.add(index)
                break
    valid = {index for index in indices if 0 <= index < len(operations)}
    return sorted(valid), "operations" if valid else "rule"


def _authorization_for_operation(rule: Mapping[str, Any], indices: Sequence[int],
                                 obligations: Any, keys: Sequence[str]) -> Authorization:
    """Authorization derived **only** from the operations this edit executes."""
    operations = list(rule.get("operations") or [])
    selected = [operations[index] for index in indices]
    must_add: list[str] = []
    removals: list[str] = []
    removals_authorized = False
    for operation in selected:
        if operation.get("op") in {"replace", "append"}:
            for part in re.split(r"(?<=[。；])", str(operation.get("new_text") or "")):
                part = part.strip()
                if len(_compact(part)) >= 6:
                    must_add.append(part)
        if operation.get("op") in {"replace", "delete"}:
            old_text = str(operation.get("old_text") or "").strip()
            if old_text:
                removals.append(old_text)
        if operation.get("op") == "delete":
            removals_authorized = True
    # ONE_OF historical wordings are alternatives of the same obligation.
    if obligations is not None:
        for index in indices:
            record = _operation_record(rule, index, obligations)
            if record is not None:
                removals.extend(str(value) for value in record.spec.alternatives if str(value))
    return Authorization(must_add=tuple(must_add), remove_patterns=tuple(removals),
                         removals_authorized=removals_authorized)


def _authorization_for_group(group: Sequence[Mapping[str, Any]],
                             rules_by_id: Mapping[str, dict]) -> Authorization:
    """Union authorization — used only as the explicit JOINT proof, never per operation."""
    must_add: list[str] = []
    removals: list[str] = []
    removals_authorized = False
    for edit in group:
        for rule_id in _rule_ids(edit):
            rule = rules_by_id.get(rule_id)
            if not rule:
                continue
            carried = [op for op in (rule.get("operations") or [])
                       if op.get("op") != "noop"]
            if carried and all(op.get("op") == "delete" for op in carried):
                removals_authorized = True
            for operation in rule.get("operations") or []:
                if operation.get("op") in {"replace", "append"}:
                    for part in re.split(r"(?<=[。；])",
                                         str(operation.get("new_text") or "")):
                        part = part.strip()
                        if len(_compact(part)) >= 6:
                            must_add.append(part)
                if operation.get("op") in {"replace", "delete"}:
                    old_text = str(operation.get("old_text") or "").strip()
                    if old_text:
                        removals.append(old_text)
            for variant in rule.get("old_text_variants") or []:
                removals.append(str(variant))
        evidence = edit.get("evidence") or {}
        if "delete" in str(edit.get("content_source") or ""):
            removals_authorized = True
        fixed = str(evidence.get("fixed_text") or "")
        if fixed:
            must_add.append(fixed)
        for key in ("deleted_quote", "deleted_paragraph", "matched_old_text",
                    "deleted_fragment"):
            value = str(evidence.get(key) or "")
            if value:
                removals.append(value)
    return Authorization(must_add=tuple(must_add), remove_patterns=tuple(removals),
                         removals_authorized=removals_authorized)


def _expected_after(before: str, group: Sequence[Mapping[str, Any]]) -> str | None:
    """Apply the planned span edits (descending offsets) to reconstruct the target text."""
    spans: list[tuple[int, int, str]] = []
    for edit in group:
        # The writer executes final parent edits. Components retain independent
        # authorization spans, which may overlap and must never be applied twice.
        candidates = [edit]
        for item in candidates:
            try:
                start, end = int(item.get("start")), int(item.get("end"))
            except (TypeError, ValueError):
                return None
            if start < 0 or end < start or end > len(before):
                return None
            spans.append((start, end, str(item.get("replacement") or "")))
    if not spans:
        return None
    expected = before
    for start, end, replacement in sorted(spans, key=lambda item: item[0], reverse=True):
        expected = expected[:start] + replacement + expected[end:]
    return expected


def _units_for_edit(edit: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    components = [component for component in (edit.get("components") or [])
                  if isinstance(component, Mapping)]
    return components or [edit]


def _describe_operation(rule: Mapping[str, Any], indices: Sequence[int],
                        obligations: Any) -> tuple[str, str]:
    rule_id = str(rule.get("rule_id") or "")
    operations = list(rule.get("operations") or [])
    operation_ids = [_operation_key(rule, index, operations[index] if index < len(operations) else None)
                     for index in indices] or [f"{rule_id}:?"]
    obligation_ids: list[str] = []
    if obligations is not None:
        for index in indices:
            record = _operation_record(rule, index, obligations)
            if record is not None:
                obligation_ids.append(record.obligation_id)
    return ",".join(operation_ids), ",".join(sorted(set(obligation_ids)))


def _evidence_texts(unit: Mapping[str, Any], edit: Mapping[str, Any]) -> list[str]:
    """Wording carried by the planner's evidence (fragments/compose fixed text)."""
    evidence = dict(unit.get("evidence") or {})
    if not evidence:
        evidence = dict(edit.get("evidence") or {})
    texts: list[str] = []
    for fragment in evidence.get("fragments") or []:
        if isinstance(fragment, Mapping):
            texts.extend([str(fragment.get("old_text") or ""),
                          str(fragment.get("new_text") or "")])
    for key in ("fixed_text", "matched_old_text", "deleted_quote", "deleted_fragment",
                "composed_text"):
        value = evidence.get(key)
        if isinstance(value, str) and value:
            texts.append(value)
    for key in ("delete_texts", "deleted_texts"):
        values = evidence.get(key)
        if isinstance(values, (list, tuple)):
            texts.extend(str(value) for value in values if value)
    return texts


def _occurrence_positions(text: str, needle: str) -> list[tuple[int, int]]:
    """Raw positions of ``needle`` after whitespace normalization."""
    compact_chars: list[str] = []
    raw_index: list[int] = []
    for index, char in enumerate(text or ""):
        if char.isspace() or char in {"\u3000", "\u00a0", "\u200b"}:
            continue
        compact_chars.append(char)
        raw_index.append(index)
    compact_text = "".join(compact_chars)
    needle_compact = _compact(needle)
    if not needle_compact:
        return []
    found: list[tuple[int, int]] = []
    cursor = 0
    while True:
        position = compact_text.find(needle_compact, cursor)
        if position < 0:
            break
        found.append((raw_index[position],
                      raw_index[position + len(needle_compact) - 1] + 1))
        cursor = position + 1
    return found


def _occurrence_index(target: Mapping[str, Any]) -> int:
    try:
        value = int(target.get("occurrence_index", -1))
    except (TypeError, ValueError):
        return -1
    return value if value >= 0 else -1


def operations_for(rule: Mapping[str, Any], indices: Sequence[int]) -> list[Mapping[str, Any]]:
    operations = list(rule.get("operations") or [])
    return [operations[index] for index in indices
            if 0 <= index < len(operations)]


def _own_effect_errors(rule: Mapping[str, Any], indices: Sequence[int],
                       obligations: Any, *, explicit_span: bool,
                       is_component: bool, before_unit: str,
                       replacement: str, validation: Any,
                       content_source: str = "", facts: Any = None,
                       evidence: Mapping[str, Any] | None = None,
                        expected_old_text: str = "", original: Any = None,
                        location: str = "", start: int = 0, end: int = 0) -> list[str]:
    """Prove the operation used its own authorization, not a sibling's.

    For a multi-operation rule each selected operation must carry its own required
    wording (the old wording it replaces is present in the unit) and every removed
    segment must belong to that operation's own ``old_text``/variant wording.  A unit
    may no longer swallow a sibling sentence under a rule-wide delete authorization,
    and a replacement may no longer borrow a sibling operation's ``new_text``.
    """
    operations = list(rule.get("operations") or [])
    if not indices:
        return []
    errors: set[str] = set()
    selected = [operations[index] for index in indices
                if 0 <= index < len(operations)]
    own_kinds = {str(operation.get("op") or "") for operation in selected}
    sibling_texts = [
        _compact(str(operation.get("new_text") or ""))
        for index, operation in enumerate(operations)
        if index not in set(indices) and operation.get("op") in {"replace", "append"}
        and len(_compact(str(operation.get("new_text") or ""))) >= 3
    ]
    own_texts = [
        _compact(str(operation.get("new_text") or ""))
        for operation in selected
        if operation.get("op") in {"replace", "append"}
        and len(_compact(str(operation.get("new_text") or ""))) >= 3
    ]
    own_old_texts = [_compact(str(operation.get("old_text") or ""))
                     for operation in selected]
    owned_removals = list(own_old_texts)
    # Real contracts often paraphrase the guide reference; the planner records the
    # wording it actually matched (variant, evidence, component source). Those are the
    # operation's own authorized removals, not sibling text.
    owned_removals.extend(_compact(str(value))
                          for value in rule.get("old_text_variants") or [] if value)
    if expected_old_text:
        owned_removals.append(_compact(expected_old_text))
    evidence = evidence or {}
    if (str(rule.get("rule_id") or "") == "G11" and len(selected) == 1
            and not replacement and (content_source == "composite_delete"
                                      or evidence.get("composite_tail"))):
        # Do not trust a composite's supplied parts or expected_old_text to grant
        # permission over the next independent class policy. Re-read both source
        # paragraphs and require precisely the bearer sentence's continuation.
        from ..recall import _g11_bearer_end
        paragraphs = list(getattr(original, "paragraphs", ()))
        position = next((index for index, span in enumerate(paragraphs)
                         if str(span.location) == location), -1)
        if position <= 0:
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
        previous = str(paragraphs[position - 1].text)
        current = str(paragraphs[position].text)
        boundary = _g11_bearer_end(previous + current, selected[0])
        if (boundary is None or boundary <= len(previous) or start != 0
                or end != boundary - len(previous)):
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
    if str(rule.get("rule_id") or "") == "G12" and len(selected) == 1:
        from ..recall import _g12_allocation_end, _g12_source_effect_owned
        if _g12_allocation_end(before_unit, selected[0]) is not None:
            return ([] if _g12_source_effect_owned(before_unit, replacement, selected[0])
                    else ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"])
    if str(rule.get("rule_id") or "") == "G13" and len(selected) == 1:
        from ..recall import _g13_short_holding_end
        short_end = _g13_short_holding_end(before_unit, selected[0])
        if short_end is not None:
            return ([] if replacement == before_unit[short_end:]
                    else ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"])
    if str(rule.get("rule_id") or "") == "G17" and own_kinds == {"delete"}:
        from ..recall import _g17_source_effect_owned
        if original is None or not _g17_source_effect_owned(
                original, location, start, end, replacement, selected):
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
        # The independent source check has proved all removals and preservation.
        # Do not let claimed provenance add any further deletion permission.
        owned_removals = [_compact(before_unit)]
    if (str(rule.get("rule_id") or "") == "G15" and own_kinds == {"delete"}
            and explicit_span and not replacement.strip()):
        from ..recall import _g15_payment_source_owned, _g15_delay_continuation
        if (len(selected) != 1 or not (
                _g15_payment_source_owned(before_unit, selected[0]) or
                (original is not None and
                 _g15_delay_continuation(original, location, selected[0]) == (start, end)))):
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
    if (str(rule.get("rule_id") or "") in {"G01", "G03"}
            and own_kinds == {"append"} and explicit_span and original is not None):
        from ..recall import _definition_next_entry_start, _split_definition_end
        source_span = original.by_location(location)
        split_end = _split_definition_end(source_span, original)
        if split_end is not None and split_end.location != location:
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
        boundary = _definition_next_entry_start(str(source_span.text))
        if boundary is not None and (start, end) != (boundary, boundary):
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
    if str(rule.get("rule_id") or "") == "G15" and (
            _compact(before_unit).startswith("若遇") or content_source == "g15_delay_delete"):
        from ..recall import _g15_delay_continuation
        if (original is None or len(selected) != 1 or replacement != ""
                or _g15_delay_continuation(original, location, selected[0]) != (start, end)):
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
        owned_removals.append(_compact(before_unit))
    if content_source == "bounded_delete":
        # Recompute this executor's source boundary and own authorization; a
        # recorded slice or strategy string cannot grant deletion permission.
        from ..recall import _g15_payment_clause_end, _g15_payment_delete_authorized
        if (str(rule.get("rule_id") or "") != "G15" or len(selected) != 1
                or not _g15_payment_delete_authorized(selected[0])
                or replacement != ""
                or _g15_payment_clause_end(before_unit, 0, len(before_unit)) != len(before_unit)):
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
    fixed_text = ""
    if evidence.get("mode") == "g09_bounded_splice":
        # A mode/fixed_text field is a claim, not authorization. Recreate the
        # bounded splice from this unit's original slice and selected operation;
        # this also supports old reports that did not record fixed_text.
        from .template import plan_g09_splice, splice_pairs
        from ..recall import instantiate_policy_text

        pairs: list[tuple[str, str]] = []
        if (rule.get("rule_id") == "G09" and len(selected) == 1
                and selected[0].get("op") == "replace"):
            operation = selected[0]
            policy = str(operation.get("new_text") or "")
            issues: list[str] = []
            if facts is not None:
                policy, issues = instantiate_policy_text("G09", operation, facts)
            if not issues and policy:
                pairs = splice_pairs(str(operation.get("old_text") or ""), policy)
        result = plan_g09_splice(before_unit, pairs) if pairs else None
        if (result is None or result.replacement != replacement
                or (evidence.get("fixed_text") is not None
                    and evidence["fixed_text"] != result.replacement)):
            return ["CLAIM_OPERATION_SPAN_UNAUTHORIZED"]
        # Replay must independently require the complete G09 effect.  A
        # reproducible partial splice (for example, only adding 的 to the NAV
        # phrase) is still an incomplete policy execution.
        result_compact = _compact(result.replacement)
        if ("扣除或加上相应的费用" not in result_compact
                or "当日该类基金份额的基金份额净值" not in result_compact):
            return ["CLAIM_OPERATION_EFFECT_MISSING"]
        fixed_text = _compact(result.replacement)
        own_texts.append(fixed_text)
    for key in ("matched_old_text", "deleted_quote", "deleted_paragraph",
                "expected_old_text", "old_text", "deleted_fragment"):
        value = evidence.get(key)
        if isinstance(value, str) and value:
            owned_removals.append(_compact(value))
    for key in ("delete_texts", "deleted_texts"):
        values = evidence.get(key)
        if isinstance(values, (list, tuple)):
            owned_removals.extend(_compact(str(value)) for value in values if value)
    for fragment in evidence.get("fragments") or []:
        if isinstance(fragment, Mapping):
            value = fragment.get("old_text")
            if value:
                owned_removals.append(_compact(str(value)))
    if obligations is not None:
        for index in indices:
            record = _operation_record(rule, index, obligations)
            if record is not None:
                owned_removals.extend(_compact(str(value))
                                      for value in record.spec.alternatives if str(value))
    before_compact = _compact(before_unit)
    replacement_compact = _compact(replacement)
    if str(rule.get("rule_id") or "") in {"G08", "G11"} and "replace" in own_kinds:
        # Clause numbers belong to source structure, not to the policy wording
        # authorized for replacement. Re-read the original slice; do not trust
        # a planner's preservation claim or a counterfeit replacement number.
        from .template import clause_number_prefix
        number = clause_number_prefix(before_unit)
        if number and not replacement.startswith(number):
            errors.add("CLAIM_OPERATION_SPAN_UNAUTHORIZED")
    if own_kinds == {"delete"}:
        # A deletion can retain source text, but cannot add or duplicate it.
        # The source slice excludes any prefix/suffix preserved by the executor.
        remaining = iter(before_compact)
        if not all(any(char == source_char for source_char in remaining)
                   for char in replacement_compact):
            errors.add("CLAIM_OPERATION_SPAN_UNAUTHORIZED")
    # A composite replace has one anchor part carrying the new policy and later
    # parts that only delete the remainder of the old sentence.  The tail must not be
    # required to contain the new_text again (D16 p222).
    composite_tail = bool(evidence.get("composite_tail") or (
        evidence.get("composite") and int(evidence.get("part_index") or 0) > 0))

    # 1. Own required wording.  Composed edits are validated by the same validator
    #    with components/required terms, so they may re-word the sentence; deterministic
    #    fragment/guide edits must carry every selected operation's own new wording.
    composed = "compose" in content_source.lower()
    if not composed:
        from ..recall import instantiate_policy_text
        for operation in selected:
            if composite_tail:
                # The new policy is anchored in part 0; this part only carries the
                # authorized removal.  Its old-text check still runs below.
                break
            if operation.get("op") not in {"replace", "append"}:
                continue
            raw_new = str(operation.get("new_text") or "")
            new_text = _compact(raw_new)
            if len(new_text) < 3:
                continue
            expected = {new_text}
            if evidence.get("mode") == "g09_bounded_splice" and fixed_text:
                expected.add(fixed_text)
            try:
                instantiated, issues = instantiate_policy_text(
                    str(rule.get("rule_id") or ""), operation, facts)
                if not issues and instantiated:
                    expected.add(_compact(instantiated))
            except Exception:  # noqa: BLE001 - instantiation is an extra tolerance
                pass
            if not any(value in replacement_compact for value in expected):
                # Append guidance often has fact-driven class lists; the fixed lead is
                # still enough to prove this operation (not a sibling) was carried out.
                lead = next(iter(expected))
                if operation.get("op") == "append" and len(lead) >= 12 and \
                        lead[:12] in replacement_compact:
                    continue
                errors.add("CLAIM_OPERATION_EFFECT_MISSING")
        for operation in selected:
            if operation.get("op") not in {"delete", "replace"}:
                continue
            old_text = _compact(str(operation.get("old_text") or ""))
            new_text = _compact(str(operation.get("new_text") or ""))
            if not old_text or old_text not in before_compact:
                continue
            if old_text in new_text:
                continue  # the replacement legitimately retains the old wording
            if old_text in replacement_compact:
                # Keeping the old sentence and appending the new policy is not a replace.
                errors.add("CLAIM_OPERATION_EFFECT_MISSING")

    # Composed output is re-worded by the composer validator, but it still may not
    # remove source text its own operation does not own.  Only the sibling-add wording
    # checks below are skipped for composed units.
    if composed:
        residual = before_compact
        for owned in sorted((value for value in owned_removals if value),
                            key=len, reverse=True):
            residual = residual.replace(owned, "")

        def _meaningful_composed(value: str) -> str:
            return re.sub(r"[，,。；;：:、\s]", "", value)

        if _meaningful_composed(residual) and _meaningful_composed(
                residual) not in _meaningful_composed(replacement_compact):
            errors.add("CLAIM_OPERATION_SPAN_UNAUTHORIZED")
        return sorted(errors)

    # 2. Everything in the source slice that is not one of the selected operations'
    #    own old wordings must survive in the replacement.  This is a residual-text
    #    proof, not a diff-segment filter: character-level SequenceMatcher alignment can
    #    otherwise hide a deleted sibling sentence as one-character replacements.
    residual = before_compact
    for owned in sorted((value for value in owned_removals if value),
                        key=len, reverse=True):
        residual = residual.replace(owned, "")
    def _meaningful(value: str) -> str:
        return re.sub(r"[，,。；;：:、\s]", "", value)

    residual_meaningful = _meaningful(residual)
    if residual_meaningful and residual_meaningful not in _meaningful(replacement_compact):
        errors.add("CLAIM_OPERATION_SPAN_UNAUTHORIZED")

    # 3. An inserted segment that carries a sibling's wording (including concatenated
    #    additions) is borrowing that sibling's add permission.
    for record in getattr(validation, "changes", ()):
        if record.kind not in {"insert", "replace"}:
            continue
        segment = _compact(record.after)
        if len(segment) < 3:
            continue
        for sibling in sibling_texts:
            if sibling and (sibling in segment or segment in sibling) and not any(
                    sibling in own or own in sibling for own in own_texts):
                errors.add("CLAIM_OPERATION_EFFECT_MISSING")

    # 4. An append/rewrite-only operation may not consume existing sentence text.
    if (explicit_span and not (own_kinds & {"replace", "delete"})
            and len(before_compact) >= 4
            and before_compact not in replacement_compact):
        errors.add("CLAIM_OPERATION_SPAN_UNAUTHORIZED")
    return sorted(errors)


def _joint_operation_effects(unit: Mapping[str, Any],
                             rules_by_id: Mapping[str, dict], obligations: Any,
                             before: str, after: str,
                             location: str) -> list[dict[str, Any]]:
    """Every unit in a joint paragraph must still carry its own operation's effect.

    Required additions are all selected operations (any one for a ONE_OF alternative
    group); a delete/replace removal whose old wording occurs once in the source must
    no longer survive in the joint result.  ``any()`` over all operations would let one
    sibling mask another's missing effect.
    """
    rule = rules_by_id.get(str(unit.get("rule_id") or ""))
    indices = list(unit.get("indices") or ())
    evidence = unit.get("evidence") or {}
    if evidence.get("composite_tail") or (
            evidence.get("composite") and int(evidence.get("part_index") or 0) > 0):
        return []
    if rule is None or not indices or len(rule.get("operations") or []) < 2:
        return []
    operations = list(rule.get("operations") or [])
    texts: list[str] = []
    removals: list[str] = []
    one_of = False
    for index in indices:
        if not (0 <= index < len(operations)):
            continue
        operation = operations[index]
        record = _operation_record(rule, index, obligations)
        if record is not None and record.spec.one_of_group:
            one_of = True
        if operation.get("op") in {"replace", "append"}:
            value = _compact(str(operation.get("new_text") or ""))
            if len(value) >= 3:
                texts.append(value)
        old_text = _compact(str(operation.get("old_text") or ""))
        new_text = _compact(str(operation.get("new_text") or ""))
        if (operation.get("op") in {"replace", "delete"} and old_text
                and old_text not in new_text and before.count(old_text) == 1):
            removals.append(old_text)
    compact_after = _compact(after)
    missing = False
    if texts:
        if one_of:
            missing = not any(value in compact_after for value in texts)
        else:
            missing = not all(value in compact_after for value in texts)
    if not missing and any(value in compact_after for value in removals):
        missing = True
    if not missing:
        return []
    return [{"rule_id": unit.get("rule_id", ""), "location": location,
             "target_id": unit.get("target_id", ""),
             "operation_id": unit.get("operation_id", ""),
             "obligation_id": unit.get("obligation_id", ""),
             "joint": True,
             "code": "CLAIM_JOINT_OPERATION_EFFECT_MISSING",
             "reason": "the joint result does not carry this operation's own effect"}]


def _operation_units(group: Sequence[Mapping[str, Any]],
                     rules_by_id: Mapping[str, dict],
                     targets_by_id: Mapping[str, Mapping[str, Any]] | None,
                     obligations: Any, before: str, after: str,
                     components_by_rule: Mapping[str, Sequence[Mapping[str, Any]]] | None,
                     required_terms_by_rule: Mapping[str, Sequence[str]] | None,
                     facts_numbers: tuple[str, ...], facts: Any = None,
                     original: Any = None, location: str = "",
                     ) -> list[dict[str, Any]]:
    """Build one authorization unit per operation-level edit/component."""
    from .validators import validate_edit
    units: list[dict[str, Any]] = []
    for edit in group:
        for unit in _units_for_edit(edit):
            rule_ids = _rule_ids(unit) or _rule_ids(edit)
            for rule_id in rule_ids:
                rule = rules_by_id.get(rule_id)
                if rule is None:
                    continue
                explicit_span = (unit.get("start") is not None
                                 and unit.get("end") is not None)
                if explicit_span:
                    try:
                        start, end = int(unit.get("start")), int(unit.get("end"))
                    except (TypeError, ValueError):
                        units.append({"rule_id": rule_id,
                                      "error": "CLAIM_UNIT_SPAN_INVALID",
                                      "target_id": str(unit.get("target_id") or "")})
                        continue
                    if start < 0 or end < start or end > len(before):
                        units.append({"rule_id": rule_id,
                                      "error": "CLAIM_UNIT_SPAN_INVALID",
                                      "target_id": str(unit.get("target_id") or "")})
                        continue
                else:
                    # Legacy/paragraph-scoped edits (fixtures and pre-plan callers): the
                    # whole paragraph is the authorized unit, still validated with the
                    # operation's own authorization rather than the location union.
                    start, end = 0, len(before)
                # A component owns its own identity. Parent keys cover siblings and
                # cannot authorize an unattributed component.
                keys = _operation_keys(unit, targets_by_id)
                indices, scope = _operation_indices(rule, keys, obligations)
                attribution_errors: list[str] = []
                if keys and not indices:
                    # The target named operation keys that do not resolve.  Never fall
                    # back to a rule-wide union: that is exactly how a sibling could
                    # lend its authorization.
                    attribution_errors.append("CLAIM_OPERATION_KEYS_INVALID")
                elif not indices:
                    attribution_errors.append("CLAIM_OPERATION_UNATTRIBUTED")
                before_unit = before[start:end] if explicit_span else before
                after_unit = (str(unit.get("replacement") or "")
                              if explicit_span else after)
                is_joint_unit = str(unit.get("content_source") or
                                    edit.get("content_source") or "") == "joint_compose"
                if attribution_errors:
                    # Fail-closed: validate with no borrowed authorization at all.
                    auth = Authorization()
                elif is_joint_unit:
                    # The joint composer rewrote one shared span for several operations;
                    # the union authorization is the explicitly documented exception.
                    # Each operation still has to prove its own effect through
                    # ``_joint_operation_effects`` below.
                    auth = _authorization_for_group(group, rules_by_id)
                else:
                    auth = _authorization_for_operation(rule, indices, obligations, keys)
                    if rule_id == "G12" and len(indices) == 1:
                        from dataclasses import replace
                        from ..recall import _g12_allocation_end, _g12_source_effect_owned
                        operation = rule["operations"][indices[0]]
                        if _g12_source_effect_owned(before_unit, after_unit, operation):
                            allocation_end = _g12_allocation_end(before_unit, operation)
                            auth = replace(auth, remove_patterns=(
                                *auth.remove_patterns, before_unit[:allocation_end]))
                components = tuple((components_by_rule or {}).get(rule_id) or ())
                terms = tuple(dict.fromkeys((required_terms_by_rule or {}).get(rule_id) or ()))
                # G02/G04 required class labels belong to the target paragraph, not to
                # the narrowed single-occurrence unit; keep only terms that are absent
                # from the whole paragraph (a genuine missing class).
                after_compact_full = _compact(after)
                terms = tuple(term for term in terms
                              if _compact(term) not in after_compact_full)
                validation = validate_edit(before_unit, after_unit, auth=auth,
                                           components=components, required_terms=terms,
                                           authorized_numbers=facts_numbers)
                effect_errors = attribution_errors + ([] if is_joint_unit else _own_effect_errors(
                    rule, indices, obligations, explicit_span=explicit_span,
                    is_component=bool(edit.get("components")),
                    before_unit=before_unit, replacement=after_unit,
                    validation=validation,
                    content_source=str(unit.get("content_source")
                                      or edit.get("content_source") or ""),
                    facts=facts,
                    evidence=dict(unit.get("evidence") or edit.get("evidence") or {}),
                    expected_old_text=str(unit.get("expected_old_text") or ""),
                    original=original, location=location, start=start, end=end))
                if rule_id == "G08" and explicit_span and len(indices) == 1 and facts is not None:
                    from ..recall import _g08_fee_clause_start
                    expanded = _g08_fee_clause_start(before, start, end,
                        rule["operations"][indices[0]], facts)
                    if expanded < start and _compact(before[expanded:start]) in _compact(after):
                        effect_errors.append("CLAIM_DUPLICATE_EFFECT")
                target_id = str(unit.get("target_id") or edit.get("target_id") or "")
                target = (targets_by_id or {}).get(target_id)
                if isinstance(target, Mapping) and indices:
                    occurrence_index = _occurrence_index(target)
                    old_text = str(operations_for(rule, indices)[0].get("old_text") or "")
                    if occurrence_index >= 0 and old_text:
                        positions = _occurrence_positions(before, old_text)
                        if occurrence_index >= len(positions):
                            effect_errors.append("CLAIM_OCCURRENCE_MISMATCH")
                        else:
                            expected = positions[occurrence_index]
                            # A whole-paragraph span covers every occurrence and cannot
                            # prove which one changed.  The narrowed span must be the
                            # authorized occurrence itself.
                            if not explicit_span or (start, end) != expected:
                                effect_errors.append("CLAIM_OCCURRENCE_MISMATCH")
                            anchor = str(target.get("occurrence_anchor") or "")
                            if anchor:
                                from types import SimpleNamespace

                                from ..recall import resolve_occurrence
                                resolved = resolve_occurrence(
                                    SimpleNamespace(text=before), old_text, anchor=anchor)
                                if resolved != expected:
                                    effect_errors.append("CLAIM_OCCURRENCE_MISMATCH")
                operation_id, obligation_id = _describe_operation(rule, indices, obligations)
                units.append({
                    "rule_id": rule_id,
                    "target_id": str(unit.get("target_id") or edit.get("target_id") or ""),
                    "operation_id": operation_id,
                    "obligation_id": obligation_id,
                    "start": start, "end": end,
                    "before": before_unit, "replacement": after_unit,
                    "scope": scope if explicit_span else "paragraph",
                    "indices": list(indices),
                    "validation": validation,
                    "effect_errors": effect_errors,
                    "verdict": ("FAIL" if effect_errors or _validation_status(validation) != "PASS"
                                 else "PASS"),
                    "components": components,
                    "required_terms": terms,
                    "evidence": dict(unit.get("evidence") or edit.get("evidence") or {}),
                    "expected_old_text": str(unit.get("expected_old_text") or ""),
                })
    return units


def replay_claims(edits: Sequence[Mapping[str, Any]], before_inspection: Any,
                  after_inspection: Any, *, rules_by_id: Mapping[str, dict],
                  facts: Any = None, max_failures: int = 40,
                  components_by_rule: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
                  required_terms_by_rule: Mapping[str, Sequence[str]] | None = None,
                  target_rules: Mapping[str, Sequence[str]] | None = None,
                  targets_by_id: Mapping[str, Mapping[str, Any]] | None = None,
                  obligations: Any = None) -> dict:
    """Replay every edit's claim against the actual artifact paragraphs.

    Two proof layers (external review 2026-10-20, P0-1):

    * **paragraph**: the written paragraph equals the planned edits applied to the
      source (no change outside the authorized spans; duplicate body/summary copies
      consistent), and the UNION proof validates the combined result;
    * **operation/obligation**: every edit/component is validated with the
      authorization of the operations it actually executes (operation keys from the
      target, else inferred from the edit's own wording), so sibling operations can
      never lend each other delete or add rights.
    """
    from .validators import validate_edit
    by_location: dict[str, list[Mapping[str, Any]]] = {}
    for edit in edits:
        by_location.setdefault(str(edit.get("location") or ""), []).append(edit)

    facts_numbers = _facts_numbers(facts)
    failures: list[dict[str, Any]] = []
    checked = 0
    units_checked = 0
    operation_records: list[dict[str, Any]] = []
    allowed_locations = set(by_location)
    # Detect duplicate target claims before any edit is evaluated.  This check must
    # also run for direct replay callers without an obligation ledger; otherwise a
    # paragraph-level edit can accidentally stand in for two same-operation sites.
    duplicate_target_failures: list[dict[str, Any]] = []
    targets = list((targets_by_id or {}).values())
    duplicate_target_groups: dict[str, list[Mapping[str, Any]]] = {}
    for target in targets:
        if not isinstance(target, Mapping) or target.get("out_of_scope"):
            continue
        # An inventory ``absent``/not-applicable alias at the same source site is
        # a stale negative assertion, not a second editable occurrence.  It must
        # not make the real survey target's occurrence ambiguous (G17 p846/p1326).
        if str(target.get("state") or "") in {"absent", "not_applicable"}:
            continue
        for key in target.get("operations") or ():
            duplicate_target_groups.setdefault(str(key), []).append(target)
    for operation_id, group in sorted(duplicate_target_groups.items()):
        if len(group) < 2:
            continue
        locations = {str(item.get("location") or "") for item in group}
        # A missing location is itself ambiguous when an operation has more than
        # one target.  Multiple targets at one known location are equally unsafe
        # unless occurrence_index distinguishes them.
        location_counts: dict[str, int] = {}
        for item in group:
            location = str(item.get("location") or "")
            location_counts[location] = location_counts.get(location, 0) + 1
        ambiguous_locations = sorted(location for location, count in location_counts.items()
                                     if count > 1 or not location)
        if not ambiguous_locations:
            continue
        occurrence_unresolved = False
        for location in ambiguous_locations:
            candidates = [item for item in group
                          if str(item.get("location") or "") == location]
            occurrences = [_occurrence_index(item) for item in candidates]
            if (any(value < 0 for value in occurrences)
                    or len(set(occurrences)) != len(occurrences)):
                occurrence_unresolved = True
                break
        if occurrence_unresolved:
            duplicate_target_failures.append({
                "rule_id": operation_id.split(":", 1)[0],
                "operation_id": operation_id,
                "location": next((location for location in ambiguous_locations if location),
                                 next(iter(locations), "")),
                "code": "CLAIM_SITE_OCCURRENCE_UNRESOLVED",
                "reason": "multiple targets for one operation/site lack occurrence identity",
            })
    failures.extend(duplicate_target_failures)
    # Duplicate clause copies (body and contract summary) must not diverge: if an
    # identical source paragraph exists elsewhere and is left untouched, the same
    # clause now has two different dispositions (D01 G15 p758 vs p1221).
    duplicate_groups: dict[str, list[str]] = {}
    for span in getattr(before_inspection, "paragraphs", ()):
        text = _compact(str(getattr(span, "text", "")))
        if len(text) >= 20:
            duplicate_groups.setdefault(text, []).append(str(span.location))
    duplicate_failures: list[dict[str, Any]] = []
    location_rules = {location: {rule_id for edit in group for rule_id in _rule_ids(edit)}
                      for location, group in by_location.items()}
    for location in allowed_locations:
        span = before_inspection.by_location(location)
        text = _compact(str(getattr(span, "text", "")))
        duplicates = []
        for item in duplicate_groups.get(text, []):
            if item == location or item in allowed_locations:
                continue
            duplicate_rule_ids = set((target_rules or {}).get(item) or ())
            # Only a copy that another rule target actually owns can be required here;
            # an untargeted identical paragraph may belong to a different section.
            if not duplicate_rule_ids:
                continue
            if duplicate_rule_ids and not (duplicate_rule_ids & location_rules.get(location, set())):
                continue
            duplicates.append(item)
        if duplicates:
            duplicate_failures.append({
                "rule_id": "", "location": duplicates[0],
                "code": "DUPLICATE_SITE_UNEDITED",
                "reason": "an identical clause copy was left unedited"})
    for text_value, locations in duplicate_groups.items():
        edited_copies = [item for item in locations if item in allowed_locations]
        if len(edited_copies) < 2:
            continue
        # Identical source paragraphs can have different authorized sibling
        # operations after clause rebinding.  Their final text may therefore
        # differ for a reason proved by the operation ledger (D20 p804/p1259:
        # G15/G17 own the body copy while G16 also owns the summary copy).
        # Keep the strict divergence check for ordinary copies and for direct
        # callers without operation-scoped target evidence.
        target_operation_sets = {
            location: frozenset(str(key) for target in (targets_by_id or {}).values()
                                 if str(target.get("location") or "") == location
                                 for key in (target.get("operations") or ()))
            for location in edited_copies
        }
        if all(target_operation_sets.get(location) for location in edited_copies) \
                and len(set(target_operation_sets.values())) > 1:
            continue
        after_values = set()
        for item in edited_copies:
            try:
                after_values.add(_compact(
                    str(getattr(after_inspection.by_location(item), "text", ""))))
            except Exception:  # noqa: BLE001 - missing copy reported separately
                continue
        if len(after_values) > 1:
            duplicate_failures.append({
                "rule_id": "", "location": edited_copies[0],
                "locations": edited_copies,
                "code": "DUPLICATE_SITE_DIVERGED",
                "reason": "identical clause copies were edited to different content"})
    failures.extend(duplicate_failures)
    # Document-level boundary: no paragraph outside the authorized target locations may
    # change. This is the proof behind G02/G04 ("outside the target paragraph diff = 0").
    before_spans = {span.location: span.text
                    for span in getattr(before_inspection, "paragraphs", ())}
    after_spans = {span.location: span.text
                   for span in getattr(after_inspection, "paragraphs", ())}
    for location, before_text in before_spans.items():
        if location in allowed_locations:
            continue
        if location not in after_spans:
            failures.append({"rule_id": "", "location": location,
                             "code": "CLAIM_OUTSIDE_SPAN_CHANGED",
                             "reason": "paragraph disappeared outside the authorized targets"})
            continue
        if _compact(before_text) != _compact(after_spans[location]):
            failures.append({"rule_id": "", "location": location,
                             "code": "CLAIM_OUTSIDE_SPAN_CHANGED",
                             "reason": "paragraph text changed outside the authorized targets"})
    for location in after_spans:
        if location not in before_spans:
            failures.append({"rule_id": "", "location": location,
                             "code": "CLAIM_UNEXPECTED_PARAGRAPH",
                             "reason": "a paragraph was added outside the authorized targets"})
    for location, group in by_location.items():
        rule_label = "+".join(_rule_ids(group[0])) or str(group[0].get("rule_id") or "")
        try:
            before_span = before_inspection.by_location(location)
            after_span = after_inspection.by_location(location)
        except Exception:
            failures.append({"rule_id": rule_label, "location": location,
                             "code": "CLAIM_LOCATION_MISSING",
                             "reason": "location not found in the artifact"})
            continue
        checked += 1
        before, after = before_span.text, after_span.text
        if _compact(before) == _compact(after):
            failures.append({"rule_id": rule_label, "location": location,
                             "code": "CLAIM_NO_CHANGE_APPLIED",
                             "reason": "the planned edit did not reach the artifact"})
            continue
        # Operation-level authorization units (never a per-location union).
        units = _operation_units(group, rules_by_id, targets_by_id, obligations, before,
                                 after, components_by_rule, required_terms_by_rule,
                                 facts_numbers, facts, original=before_inspection, location=location)
        overlap = False
        spans = sorted((unit.get("start"), unit.get("end")) for unit in units
                       if unit.get("error") is None)
        for (prev_start, prev_end), (next_start, next_end) in zip(spans, spans[1:]):
            if next_start < prev_end:
                overlap = True
                break
        for unit in units:
            if unit.get("error"):
                failures.append({"rule_id": unit["rule_id"], "location": location,
                                 "target_id": unit.get("target_id", ""),
                                 "code": unit["error"],
                                 "reason": "the edit span is invalid"})
                unit["verdict"] = "FAIL"
        if overlap:
            # Overlapping edits are a JOINT result: the combined paragraph is validated
            # with an explicit union authorization, and every unit must still carry its
            # own operation's required effect.  Individual span replays would be unsound
            # because the joint composer rewrites the overlapping region.
            auth = _authorization_for_group(group, rules_by_id)
            rule_ids = {rule_id for edit in group for rule_id in _rule_ids(edit)}
            joint_components: list[Mapping[str, Any]] = []
            for rule_id in rule_ids:
                joint_components.extend((components_by_rule or {}).get(rule_id) or [])
            required_terms: list[str] = []
            for rule_id in rule_ids:
                required_terms.extend((required_terms_by_rule or {}).get(rule_id) or [])
            validation = validate_edit(before, after, auth=auth,
                                       components=tuple(joint_components),
                                       required_terms=tuple(dict.fromkeys(required_terms)),
                                       authorized_numbers=facts_numbers)
            # UNKNOWN and CONFLICT are not successful artifact proofs.
            joint_ok = _validation_status(validation) == "PASS"
            if joint_ok:
                # Any text introduced by the joint result must be one of the selected
                # operations' own new wording; UNEXPLAINED_SOFT is not enough here.
                allowed_additions: list[str] = []
                # The merged edit's own components carry the instantiated replacement
                # (including class-slot substitution).  The raw guide new_text is not
                # enough for a C/F multi-class product and left a real G16 segment
                # unexplained in a G17 delete + G16 append merge.
                for edit in group:
                    for component in edit.get("components") or [edit]:
                        value = _compact(str(component.get("replacement") or ""))
                        if len(value) >= 2:
                            allowed_additions.append(value)
                        fixed = _compact(str((component.get("evidence") or {}).get("fixed_text") or ""))
                        if len(fixed) >= 2:
                            allowed_additions.append(fixed)
                for unit in units:
                    if unit.get("error"):
                        continue
                    unit_rule = rules_by_id.get(str(unit.get("rule_id") or ""))
                    if unit_rule is None:
                        continue
                    for operation in operations_for(unit_rule, unit.get("indices") or ()):
                        value = _compact(str(operation.get("new_text") or ""))
                        if value:
                            allowed_additions.append(value)
                for record in validation.changes:
                    if record.kind not in {"insert", "replace"}:
                        continue
                    segment = _compact(record.after)
                    if len(segment) < 2:
                        continue
                    if not any(segment in allowed or allowed in segment
                               for allowed in allowed_additions):
                        failures.append({
                            "rule_id": rule_label, "location": location,
                            "code": "CLAIM_JOINT_UNEXPLAINED_TEXT", "joint": True,
                            "reason": "joint result introduced text not authorized "
                                      "by any selected operation"})
                        joint_ok = False
                        break
            if joint_ok and spans:
                # Gaps between disjoint authorized components must survive unchanged.
                ordered = sorted(spans)
                merged = [list(ordered[0])]
                for span_start, span_end in ordered[1:]:
                    if span_start <= merged[-1][1]:
                        merged[-1][1] = max(merged[-1][1], span_end)
                    else:
                        merged.append([span_start, span_end])
                for (_, left_end), (right_start, _) in zip(merged, merged[1:]):
                    gap = before[left_end:right_start]
                    if gap and gap not in after:
                        failures.append({
                            "rule_id": rule_label, "location": location,
                            "code": "CLAIM_OUTSIDE_SPAN_CHANGED", "joint": True,
                            "reason": "a gap between authorized spans changed"})
                        joint_ok = False
                        break
            if not joint_ok:
                codes = sorted({finding.code for finding in validation.findings})
                hard = [record.reason for record in validation.changes
                        if record.explanation == "UNEXPLAINED_HARD"]
                failures.append({"rule_id": rule_label, "location": location,
                                 "code": "CLAIM_JOINT_VALIDATION_FAILED",
                                 "joint": True,
                                 "reason": ",".join(codes or hard or ["UNEXPLAINED_CHANGE"]),
                                 "validator": validation.as_dict()})
            for unit in units:
                if unit.get("error"):
                    continue
                units_checked += 1
                for failure in _joint_operation_effects(
                        unit, rules_by_id, obligations, before, after, location):
                    failures.append(failure)
                    joint_ok = False
                    unit["verdict"] = "FAIL"
                validation = unit.get("validation")
                effect_errors = list(unit.get("effect_errors") or ())
                if validation is not None and _validation_status(validation) != "PASS":
                    codes = sorted({finding.code for finding in validation.findings}
                                   | set(effect_errors))
                    failures.append({
                        "rule_id": unit["rule_id"], "location": location,
                        "target_id": unit.get("target_id", ""),
                        "operation_id": unit.get("operation_id", ""),
                        "obligation_id": unit.get("obligation_id", ""),
                        "authorized_span": [unit["start"], unit["end"]],
                        "joint": True,
                        "code": _validation_failure_code(validation),
                        "reason": ",".join(codes or ["UNEXPLAINED_CHANGE"])})
                    joint_ok = False
                    unit["verdict"] = "FAIL"
                for code in effect_errors:
                    failures.append({
                        "rule_id": unit["rule_id"], "location": location,
                        "target_id": unit.get("target_id", ""),
                        "operation_id": unit.get("operation_id", ""),
                        "obligation_id": unit.get("obligation_id", ""),
                        "authorized_span": [unit["start"], unit["end"]],
                        "joint": True, "code": code,
                        "reason": "the operation did not use its own authorization"})
                    joint_ok = False
                    unit["verdict"] = "FAIL"
                if unit.get("verdict") != "FAIL":
                    unit["verdict"] = "PASS" if joint_ok else "FAIL"
            # Boundary proof for an overlapping plan: the union of the authorized spans
            # is the only region allowed to change; prefix/suffix must be byte-identical.
            if spans:
                union_start = min(span[0] for span in spans)
                union_end = max(span[1] for span in spans)
                prefix, suffix = before[:union_start], before[union_end:]
                if (prefix and not after.startswith(prefix)) or \
                        (suffix and not after.endswith(suffix)):
                    failures.append({
                        "rule_id": rule_label, "location": location,
                        "code": "CLAIM_OUTSIDE_SPAN_CHANGED", "joint": True,
                        "reason": "text outside the union of authorized spans changed"})
                    joint_ok = False
        else:
            for unit in units:
                if unit.get("error"):
                    continue
                units_checked += 1
                replacement = unit["replacement"]
                if replacement.strip() and _compact(replacement) not in _compact(after):
                    failures.append({"rule_id": unit["rule_id"], "location": location,
                                     "target_id": unit.get("target_id", ""),
                                     "operation_id": unit.get("operation_id", ""),
                                     "obligation_id": unit.get("obligation_id", ""),
                                     "authorized_span": [unit["start"], unit["end"]],
                                     "code": "CLAIM_REPLACEMENT_MISSING",
                                     "reason": "the written paragraph does not carry the "
                                               "operation's planned replacement"})
                    unit["verdict"] = "FAIL"
                validation = unit["validation"]
                effect_errors = list(unit.get("effect_errors") or ())
                if _validation_status(validation) != "PASS":
                    codes = sorted({finding.code for finding in validation.findings}
                                   | set(effect_errors))
                    hard = [record.reason for record in validation.changes
                            if record.explanation == "UNEXPLAINED_HARD"]
                    failures.append({
                        "rule_id": unit["rule_id"], "location": location,
                        "target_id": unit.get("target_id", ""),
                        "operation_id": unit.get("operation_id", ""),
                        "obligation_id": unit.get("obligation_id", ""),
                        "authorized_span": [unit["start"], unit["end"]],
                        "scope": unit.get("scope", ""),
                        "code": _validation_failure_code(validation),
                        "reason": ",".join(codes or hard or ["UNEXPLAINED_CHANGE"]),
                        "validator": validation.as_dict()})
                    unit["verdict"] = "FAIL"
                for code in effect_errors:
                    failures.append({
                        "rule_id": unit["rule_id"], "location": location,
                        "target_id": unit.get("target_id", ""),
                        "operation_id": unit.get("operation_id", ""),
                        "obligation_id": unit.get("obligation_id", ""),
                        "authorized_span": [unit["start"], unit["end"]],
                        "scope": unit.get("scope", ""),
                        "code": code,
                        "reason": "the operation did not use its own authorization"})
                    unit["verdict"] = "FAIL"
        for unit in units:
            operation_records.append({
                "location": location,
                "rule_id": unit["rule_id"],
                "target_id": unit.get("target_id", ""),
                "operation_id": unit.get("operation_id", ""),
                "obligation_id": unit.get("obligation_id", ""),
                "start": unit.get("start"), "end": unit.get("end"),
                "before": unit.get("before", ""),
                "replacement": unit.get("replacement", ""),
                "scope": unit.get("scope", ""),
                "effect_errors": list(unit.get("effect_errors") or
                                      ([unit["error"]] if unit.get("error") else [])),
                "verdict": unit.get("verdict", "FAIL"),
            })
        # Paragraph-level reconstruction (non-overlapping plans only): the plan applied
        # to the source must equal the artifact.  Overlapping plans are proven by the
        # explicit joint validation above instead of per-edit offset arithmetic.
        if not overlap or (len(group) == 1 and group[0].get("content_source") == "atomic_paragraph"):
            expected = _expected_after(before, group)
            if expected is not None and _compact(expected) != _compact(after):
                failures.append({"rule_id": rule_label, "location": location,
                                 "code": "CLAIM_OUTSIDE_SPAN_CHANGED",
                                 "reason": "the written paragraph differs outside "
                                           "the authorized span"})
        if len(failures) >= max_failures:
            break
    # Every TRUE obligation receives a site-scoped proof from the shared evaluator.
    # The integrity/authorization checks above remain mandatory and independent.
    from .effects import evaluate_operation_effect, operation_site_bound
    effect_edits = []
    for edit in edits:
        enriched = dict(edit)
        if not enriched.get("operation_keys") and targets_by_id:
            target = targets_by_id.get(str(edit.get("target_id") or ""))
            if isinstance(target, Mapping):
                enriched["operation_keys"] = list(target.get("operations") or ())
        effect_edits.append(enriched)
    records = getattr(obligations, "records", None)
    if records is None:
        records = list((getattr(obligations, "_records", {}) or {}).values())
    clause_duplicates = _g16_duplicate_effects(
        before_inspection, after_inspection, rules_by_id, facts, records)
    failures.extend(clause_duplicates)
    # A deletion may legitimately remove a sentence that another certified
    # operation reintroduces in its NEW policy at this same site. Only a validated
    # final component and its complete guide text can provide that authorization.
    from ..recall import instantiate_policy_text
    new_texts = {}
    for record in records:
        if record.spec.op not in {"append", "replace"}:
            continue
        value = str(record.spec.new_text or "")
        try:
            instantiated, issues = instantiate_policy_text(
                record.spec.rule_id, {"op": record.spec.op, "new_text": value}, facts)
            if issues:
                continue
            value = instantiated
        except (AttributeError, TypeError):
            continue
        if value:
            new_texts[record.spec.operation_id] = value
    # An operation's fixed policy may occur at most once per paragraph unless it
    # already occurred there in the source.  Without this, a second full-clause
    # insertion can pass the span reconstruction (D16 p221 R+R repro).
    duplicate_seen: set[tuple[str, str]] = set()
    for location in by_location:
        try:
            before_text = str(before_inspection.by_location(location).text)
            after_text = str(after_inspection.by_location(location).text)
        except (KeyError, ValueError, IndexError, AttributeError):
            continue
        before_compact = _compact(before_text)
        after_compact = _compact(after_text)
        for record in records:
            value = new_texts.get(record.spec.operation_id)
            needle = _compact(value or "")
            if len(needle) < 20:
                continue
            key = (location, needle)
            if key in duplicate_seen:
                continue
            duplicate_seen.add(key)
            if after_compact.count(needle) > max(1, before_compact.count(needle)):
                failures.append({
                    "rule_id": record.spec.rule_id,
                    "operation_id": record.spec.operation_id,
                    "obligation_id": record.obligation_id,
                    "location": location,
                    "code": "CLAIM_DUPLICATE_EFFECT",
                    "reason": "an authorized final clause appears more than once in the same paragraph",
                })
    authorized_new_texts: dict[str, list[str]] = {}
    for unit in operation_records:
        if unit.get("verdict") != "PASS":
            continue
        for key in str(unit.get("operation_id") or "").split(","):
            value = new_texts.get(key.strip())
            if value and _compact(value) in _compact(str(unit.get("replacement") or "")):
                authorized_new_texts.setdefault(str(unit.get("location") or ""), []).append(value)
    targets = list((targets_by_id or {}).values())
    obligation_state: dict[str, dict[str, Any]] = {}
    for record in records:
        applicability = getattr(record, "applicability", None)
        if applicability is not None and applicability.status != "TRUE":
            continue
        operation_id = str(record.spec.operation_id)
        sites: list[dict[str, Any]] = []
        # Two targets for the same operation and paragraph must carry occurrence
        # identity.  Collapsing them to ``pN`` makes a single successful edit look
        # like proof for both targets and makes replay dependent on target order.
        same_location_targets: dict[str, list[Mapping[str, Any]]] = {}
        for candidate in targets:
            candidate_keys = {str(key) for key in (candidate.get("operations") or ())}
            if (operation_id in candidate_keys and not candidate.get("out_of_scope")
                    and str(candidate.get("state") or "") not in {"absent", "not_applicable"}
                    and str(candidate.get("location") or "")):
                same_location_targets.setdefault(str(candidate.get("location")), []).append(candidate)
        ambiguous_locations = set()
        for location, candidates in same_location_targets.items():
            occurrences = [_occurrence_index(candidate) for candidate in candidates]
            if (len(candidates) > 1 and
                    (any(value < 0 for value in occurrences)
                     or len(set(occurrences)) != len(occurrences))):
                ambiguous_locations.add(location)
        for location in sorted(ambiguous_locations):
            failures.append({"rule_id": record.spec.rule_id,
                             "operation_id": operation_id,
                             "obligation_id": record.obligation_id,
                             "location": location,
                             "code": "CLAIM_SITE_OCCURRENCE_UNRESOLVED",
                             "reason": "multiple targets for one operation/site lack occurrence identity"})
        for target in targets:
            # Inventory ``absent`` is a window-level negative assertion, not a
            # verified business site.  A generic heading (for example a summary
            # heading) must never prove a delete's VERIFIED_ABSENT state or add a
            # required site that can make a valid operation fail.  A real business
            # paragraph can, however, prove that an independent literal is already
            # absent (G05:2 at the class-setup clause); use that paragraph's own
            # body as the site quote and let the rule/site guard reject headings.
            # ``claimed_operations`` remains an attribution failure marker; only the
            # target's operation binding is authoritative for effect proof.
            if target.get("attribution_error"):
                continue
            keys = {str(key) for key in (target.get("operations") or ())}
            if operation_id not in keys or target.get("out_of_scope"):
                continue
            location = str(target.get("location") or "")
            if location in ambiguous_locations:
                continue
            try:
                before_text = str(before_inspection.by_location(location).text)
            except (KeyError, ValueError, IndexError, AttributeError):
                continue
            state = str(target.get("state") or "")
            if state in {"absent", "satisfied"}:
                from ..recall import _looks_like_heading
                if _looks_like_heading(before_text):
                    continue
                # A satisfied target's quote is the matched new-policy excerpt, not
                # a source binding.  Use the whole business paragraph so the proof
                # can verify the reworded policy and class tokens (G18 p139).
                quote = before_text
            else:
                quote = str(target.get("quote") or "")
                # Use the real source delimiter for a fully bound quote before
                # testing literal site evidence. A terminal semicolon/full-stop
                # difference must neither drop the site nor reduce it to a prefix.
                from ..recall import resolve_quote
                span = before_inspection.by_location(location)
                bound = resolve_quote(span, quote) if quote else None
                if bound is not None:
                    actual_quote = before_text[bound[0]:bound[1]]
                    if (_compact(quote).rstrip("。；;") ==
                            _compact(actual_quote).rstrip("。；;")):
                        quote = actual_quote
            parts = []
            for part in target.get("composite") or []:
                from ..recall import compact_offsets
                try:
                    part_location, start, end = str(part).rsplit(":", 2)
                    part_span = before_inspection.by_location(part_location)
                    normalized, _ = compact_offsets(part_span.text)
                    parts.append({"location": part_location,
                                  "quote": normalized[int(start):int(end)]})
                except (KeyError, ValueError, IndexError, AttributeError):
                    continue
            if not operation_site_bound(record.spec, quote, before_inspection,
                                        location, facts, parts=parts,
                                        occurrence_index=_occurrence_index(target)):
                continue
            identity = {"state": ("satisfied" if state == "absent"
                                   else target.get("state")),
                        "operation_id": operation_id,
                        "obligation_id": record.obligation_id,
                        "target_id": target.get("target_id")}
            if quote and _compact(quote) in _compact(before_text):
                sites.append({"location": location, "quote": quote,
                              "occurrence_index": _occurrence_index(target),
                              **identity})
            sites.extend({**part, **identity} for part in parts)
        superseded_site = any(
            target.get("out_of_scope") and (
                operation_id in (target.get("operations") or ())
                or str(target.get("rule_id") or "") == str(record.spec.rule_id))
            for target in targets)
        if not sites and superseded_site:
            # A composite/merged edit can carry a delete operation whose target was
            # later marked out of scope (D16 G13 p221/p222).  The edit's own
            # operation key and expected source slice are still artifact evidence;
            # use them instead of falling back to a zero-site document scan.
            for edit in effect_edits:
                for component in edit.get("components") or [edit]:
                    location = str(component.get("location") or edit.get("location") or "")
                    if not location:
                        continue
                    try:
                        before_text = str(before_inspection.by_location(location).text)
                    except (KeyError, ValueError, IndexError, AttributeError):
                        continue
                    quote = before_text
                    if not operation_site_bound(record.spec, quote, before_inspection,
                                                location, facts):
                        continue
                    sites.append({"location": location, "quote": quote,
                                  "state": "needs_edit", "operation_id": operation_id,
                                  "obligation_id": record.obligation_id,
                                  "target_id": str(component.get("target_id") or "")})
                if sites:
                    break
        # A model may locate the body copy but miss the contract-summary copy.
        # For replace/delete operations, a paragraph sharing the verified site's
        # normalized opening and passing the same operation site guard is a
        # required duplicate copy; it cannot be hidden by a PASS on the body copy.
        # The prefix requirement prevents unrelated fee-rate/formula paragraphs
        # from becoming required sites merely because they mention the same domain.
        if sites and str(getattr(record.spec, "op", "")) in {"replace", "delete"}:
            from ..recall import _looks_like_heading
            seed = next((str(site.get("quote") or "") for site in sites
                         if str(site.get("quote") or "")), "")
            prefix = _compact(seed)[:16]
            seen_locations = {str(site.get("location") or "") for site in sites}
            if len(prefix) >= 10:
                for span in getattr(before_inspection, "paragraphs", ()):
                    location = str(getattr(span, "location", ""))
                    text = str(getattr(span, "text", ""))
                    if not location or location in seen_locations or _looks_like_heading(text):
                        continue
                    if prefix not in _compact(text):
                        continue
                    if not operation_site_bound(record.spec, text, before_inspection,
                                                location, facts, occurrence_index=-1):
                        continue
                    sites.append({"location": location, "quote": text,
                                  "state": "satisfied",
                                  "operation_id": operation_id,
                                  "obligation_id": record.obligation_id,
                                  "target_id": f"duplicate-site:{location}"})
                    seen_locations.add(location)
        own_records = []
        for unit in operation_records:
            keys = {key.strip() for key in str(unit.get("operation_id") or "").split(",")}
            if operation_id not in keys:
                continue
            own_records.append(unit)
            location = str(unit.get("location") or "")
            try:
                before_text = str(before_inspection.by_location(location).text)
            except (KeyError, ValueError, IndexError, AttributeError):
                continue
            sites.append({"location": location, "quote": before_text})
        result = evaluate_operation_effect(record, before_inspection, after_inspection,
            sites, effect_edits, facts, validated_units=own_records,
            authorized_new_texts=authorized_new_texts)
        obligation_state[record.obligation_id] = result.as_dict()
        duplicates = [item for item in clause_duplicates
                      if item["operation_id"] == record.spec.operation_id]
        if duplicates:
            # Coverage/delivery must receive the same failure as document replay;
            # do not leave individual operation/site effects marked PASS.
            item = obligation_state[record.obligation_id]
            item.update(state="FAIL", artifact_status="WRONG_EFFECT",
                        failure_code="CLAIM_DUPLICATE_EFFECT",
                        reason=duplicates[0]["reason"])
            locations = {loc for duplicate in duplicates for loc in duplicate["locations"]}
            for site in item.get("site_effects") or ():
                if site.get("location") in locations:
                    site.update(state="FAIL", artifact_status="WRONG_EFFECT",
                                failure_code="CLAIM_DUPLICATE_EFFECT")

    # Explicit ONE_OF wording alternatives share only their verified BUSINESS SITE.
    # No global text absence, rule-level success or sibling independent operation closes it.
    groups: dict[str, list[Any]] = {}
    for record in records:
        if record.spec.one_of_group and record.obligation_id in obligation_state:
            groups.setdefault(record.spec.one_of_group, []).append(record)
    for group in groups.values():
        passed = [record for record in group
                  if obligation_state[record.obligation_id].get("state") == "PASS"]
        if not passed:
            continue
        group_sites = list(dict.fromkeys(location for record in group
            for location in obligation_state[record.obligation_id].get("sites") or []))
        for record in group:
            item = obligation_state[record.obligation_id]
            if item.get("state") == "PASS" or not group_sites:
                continue
            # An alternative may have a target site but not use it successfully.
            # For a ONE_OF historical wording group the shared certified business
            # site is still the right place to prove this alternative; the evaluator
            # rejects it if its own old wording survives there.
            shared_sites = [{"location": location,
                             "quote": str(before_inspection.by_location(location).text)}
                            for location in group_sites]
            # Historical alternatives can share their certified business sites, not
            # independent siblings. The same evaluator must prove this alternative.
            proof = evaluate_operation_effect(record, before_inspection, after_inspection,
                                              shared_sites, effect_edits, facts)
            if proof.state == "PASS":
                obligation_state[record.obligation_id] = proof.as_dict()
            else:
                # A historical ONE_OF wording that is genuinely absent from the
                # whole source is not a missing edit; the passing alternative has
                # already replaced the clause.  Keep the alternative's own wording
                # check: if it survives anywhere, it must still fail.
                old_wording = _compact(str(record.spec.old_text or ""))
                source_body = _compact("\n".join(
                    str(getattr(span, "text", ""))
                    for span in getattr(before_inspection, "paragraphs", ())))
                if old_wording and old_wording not in source_body:
                    evidence = [{"rule_id": record.spec.rule_id,
                                 "operation_id": record.spec.operation_id,
                                 "obligation_id": record.obligation_id,
                                 "proof_kind": "alternative_wording_absent",
                                 "site_id": shared_sites[0]["location"],
                                 "location": shared_sites[0]["location"],
                                 "searched_literals": [str(record.spec.old_text or "")],
                                 "match_count": 0,
                                 "document_sha256": str(getattr(
                                     before_inspection, "source_sha256", ""))}]
                    obligation_state[record.obligation_id] = {
                        "state": "PASS", "artifact_status": "NOT_REQUIRED",
                        "rule_id": record.spec.rule_id,
                        "operation_id": record.spec.operation_id,
                        "obligation_id": record.obligation_id,
                        "sites": [site["location"] for site in shared_sites],
                        "edit_ids": [], "failure_code": "",
                        "reason": "one_of_alternative_absent",
                        "evidence": evidence, "site_effects": []}

    for record in records:
        item = obligation_state.get(record.obligation_id)
        if not item or item.get("state") == "PASS":
            continue
        failure_code = str(item.get("failure_code") or "CLAIM_OPERATION_UNPROVEN")
        failed_site = next((site for site in item.get("site_effects") or []
                            if site.get("state") != "PASS"), {})
        failures.append({"rule_id": record.spec.rule_id,
                         "operation_id": record.spec.operation_id,
                         "obligation_id": record.obligation_id,
                         "location": failed_site.get("location") or
                                     next(iter(item.get("sites") or []), ""),
                         "code": failure_code, "reason": item.get("reason") or
                         "operation effect is not proven at every verified site"})
    from .effects import effect_proof_passed
    return {"verified": not failures and all(
                effect_proof_passed(item) for item in obligation_state.values()),
            "checked": checked, "units_checked": units_checked,
            "operations": operation_records, "obligations": obligation_state,
            "failures": failures[:max_failures]}


def _similar(left: str, right: str) -> bool:
    from difflib import SequenceMatcher
    if not left or not right:
        return False
    if left in right or right in left:
        return True
    return SequenceMatcher(None, left, right).ratio() >= 0.85


def check_delete_residuals(rules_by_id: Mapping[str, dict], after_inspection: Any,
                           edits: Sequence[Mapping[str, Any]] | None = None,
                           max_failures: int = 40, *, original: Any = None,
                           targets: Sequence[Mapping[str, Any]] = (), facts: Any = None,
                           obligations: Any = None) -> list[dict[str, Any]]:
    """Probe verified operation sites first, then classify full-document candidates.

    A literal match elsewhere is only a candidate. It becomes a blocking residual
    after the rule's business-site classifier accepts it. A sibling's policy text
    can explain a retained sentence only at the site where that policy was applied.
    """
    from ..recall import target_site_ok, resolve_quote, condition_status
    from .effects import operation_site_bound
    from types import SimpleNamespace
    spans = list(getattr(after_inspection, "paragraphs", ()))
    source = original or after_inspection
    source_spans = list(getattr(source, "paragraphs", ()))
    source_by_location = {str(span.location): span for span in source_spans}
    failures: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    edits = list(edits or [])
    for rule_id, rule in rules_by_id.items():
        site_specs = {}
        if str(rule_id) == "G05":
            from ..obligations import compile_obligations
            # The same business-site boundary applies to callers without a runtime
            # ledger. Compile only the static operation identity, not applicability.
            site_specs = {item.spec.operation_id: item.spec for item in compile_obligations(
                {"groups": [{**rule, "rule_id": rule_id}]}).records}
        operations = list(rule.get("operations") or [])
        for index, operation in enumerate(operations):
            if operation.get("op") != "delete":
                continue
            if facts is not None and condition_status(operation.get("condition"), facts) != "TRUE":
                continue
            operation_id = _operation_key(rule, index, operation)
            record = obligations.record(operation_id) if obligations is not None else None
            if record is not None and record.applicability.status != "TRUE":
                continue
            known = {str(target.get("location") or "") for target in targets
                     if operation_id in target.get("operations", ()) and not target.get("out_of_scope")}
            from .effects import operation_units
            known.update(str(unit.get("location") or edit.get("location") or "")
                         for edit, unit in operation_units(edits, operation_id))
            texts = [str(operation.get("old_text") or "")]
            texts.extend(str(value) for value in (record.spec.alternatives if record is not None
                                                  else operation.get("old_text_variants") or []))
            probes: set[str] = set()
            for text in texts:
                for sentence in re.split(r"(?<=[。；;])", text):
                    for probe in (sentence.strip(), re.sub(
                            r"^[A-ZＡ-Ｚ]\s*类(?:基金份额)?的?", "", sentence).strip()):
                        if len(_compact(probe)) >= 8:
                            probes.add(probe)
            # The known site order is deterministic; remaining literal matches are
            # assessed individually instead of borrowing a document-wide absence.
            ordered = sorted(enumerate(spans), key=lambda pair: (
                str(getattr(pair[1], "location", "")) not in known, pair[0]))
            for span_index, span in ordered:
                location = str(getattr(span, "location", ""))
                source_span = source_by_location.get(location)
                if source_span is None:
                    continue
                semantic = location in known or target_site_ok(str(rule_id), source_span, source)
                site_quote = str(source_span.text)
                site_parts = ()
                if not semantic:
                    # Delete residuals may be the continuation sentence of a known
                    # clause and therefore lack the target anchor (for example G15's
                    # "使用范围" tail). The operation's own wording is the bounded
                    # business signature; it still must be an exact local quote.
                    semantic = any(anchor and anchor in str(span.text)
                                   for anchor in (str(rule_id) in {"G15", "G17"} and
                                                  ("销售服务费",) or ()))
                continuation_text = _compact(str(source_span.text)).strip("。；;，, ")
                is_reference_continuation = len(continuation_text) >= 8 and any(
                    continuation_text in _compact(text) for text in texts if text)
                if not semantic and span_index > 0 and is_reference_continuation:
                    previous = source_spans[span_index - 1]
                    continuation = SimpleNamespace(text=str(previous.text) + str(source_span.text),
                                                   location=location)
                    semantic = target_site_ok(str(rule_id), continuation, source)
                    site_quote = continuation.text
                    site_parts = ({"location": str(previous.location), "quote": str(previous.text)},
                                  {"location": location, "quote": str(source_span.text)})
                if semantic and str(rule_id) == "G05":
                    # Bind WHERE to the original site: a sibling operation can
                    # legitimately change the artifact paragraph while leaving this
                    # delete's exact residual. Artifact text is checked below only
                    # for that residual, never used as a source quote. Apply this
                    # guard after continuation handling so it cannot be bypassed.
                    spec = record.spec if record is not None else site_specs[operation_id]
                    semantic = operation_site_bound(spec, site_quote, source, location,
                                                    facts, parts=site_parts)
                if not semantic:
                    continue
                for probe in sorted(probes):
                    if _compact(probe) not in _compact(str(span.text)):
                        continue
                    located = resolve_quote(span, probe)
                    if located is None:
                        continue
                    compact_probe = _compact(probe)
                    authorized = False
                    for edit in edits:
                        if str(edit.get("location") or "") != location:
                            continue
                        if compact_probe not in _compact(str(edit.get("replacement") or "")):
                            continue
                        # Only explicit final components can lend an authorized NEW
                        # sentence; nearby or document-wide sibling text cannot.
                        for unit in edit.get("components") or [edit]:
                            for key in _operation_keys(unit, None):
                                for new_rule in rules_by_id.values():
                                    indices, _ = _operation_indices(new_rule, [key], obligations)
                                    if any(compact_probe in _compact(str(
                                            new_rule["operations"][i].get("new_text") or ""))
                                           for i in indices):
                                        authorized = True
                    identity = (operation_id, location, compact_probe)
                    if authorized or identity in seen:
                        continue
                    seen.add(identity)
                    failures.append({"rule_id": rule_id, "operation_id": operation_id,
                        "obligation_id": record.obligation_id if record is not None else "",
                        "location": location, "code": "RESIDUAL_OLD_TEXT",
                        "proof_kind": "RESIDUAL_CONFIRMED", "scan": "known_site" if location in known else "semantic_site",
                        "reason": "exact old effect survives at this operation's business site",
                        "quote": str(span.text)[located[0]:located[1]]})
                    if len(failures) >= max_failures:
                        return failures
    return failures
