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
        keys = [str(key) for key in (target.get("operations") or []) if str(key).strip()]
        if keys:
            return keys
    return []


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
        if str(key).startswith(rule_id + ":"):
            tail = str(key).split(":", 1)[1]
            if tail.isdigit():
                indices.add(int(tail))
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
            record = obligations.record(f"{rule.get('rule_id')}:{index}")
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
    operation_ids = [f"{rule_id}:{index}" for index in indices] or [f"{rule_id}:?"]
    obligation_ids: list[str] = []
    if obligations is not None:
        for index in indices:
            record = obligations.record(f"{rule_id}:{index}")
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
                       expected_old_text: str = "") -> list[str]:
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
            record = obligations.record(f"{rule.get('rule_id')}:{index}")
            if record is not None:
                owned_removals.extend(_compact(str(value))
                                      for value in record.spec.alternatives if str(value))
    before_compact = _compact(before_unit)
    replacement_compact = _compact(replacement)

    # 1. Own required wording.  Composed edits are validated by the same validator
    #    with components/required terms, so they may re-word the sentence; deterministic
    #    fragment/guide edits must carry every selected operation's own new wording.
    composed = "compose" in content_source.lower()
    if not composed:
        from ..recall import instantiate_slots
        for operation in selected:
            if operation.get("op") not in {"replace", "append"}:
                continue
            raw_new = str(operation.get("new_text") or "")
            new_text = _compact(raw_new)
            if len(new_text) < 3:
                continue
            expected = {new_text}
            try:
                instantiated, issues = instantiate_slots(raw_new, facts)
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
        record = (obligations.record(f"{rule.get('rule_id')}:{index}")
                  if obligations is not None else None)
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
                    expected_old_text=str(unit.get("expected_old_text") or "")))
                target_id = str(unit.get("target_id") or edit.get("target_id") or "")
                target = (targets_by_id or {}).get(target_id)
                if isinstance(target, Mapping) and indices:
                    raw_occurrence = target.get("occurrence_index")
                    occurrence_index = (int(raw_occurrence)
                                        if raw_occurrence is not None else -1)
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
                    "verdict": ("FAIL" if effect_errors or validation.verdict == "FAIL"
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
                                 facts_numbers, facts)
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
            joint_ok = validation.verdict != "FAIL"
            if joint_ok:
                # Any text introduced by the joint result must be one of the selected
                # operations' own new wording; UNEXPLAINED_SOFT is not enough here.
                allowed_additions: list[str] = []
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
                if validation is not None and validation.verdict == "FAIL":
                    codes = sorted({finding.code for finding in validation.findings}
                                   | set(effect_errors))
                    failures.append({
                        "rule_id": unit["rule_id"], "location": location,
                        "target_id": unit.get("target_id", ""),
                        "operation_id": unit.get("operation_id", ""),
                        "obligation_id": unit.get("obligation_id", ""),
                        "authorized_span": [unit["start"], unit["end"]],
                        "joint": True,
                        "code": "CLAIM_VALIDATION_FAILED",
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
                if validation.verdict == "FAIL":
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
                        "code": "CLAIM_VALIDATION_FAILED",
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
    from .effects import evaluate_operation_effect
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
    # A deletion may legitimately remove a sentence that another certified
    # operation reintroduces in its NEW policy at this same site. Only a validated
    # final component and its complete guide text can provide that authorization.
    from ..recall import instantiate_slots
    new_texts = {}
    for record in records:
        if record.spec.op not in {"append", "replace"}:
            continue
        value = str(record.spec.new_text or "")
        try:
            instantiated, issues = instantiate_slots(value, facts)
            if issues:
                continue
            value = instantiated
        except (AttributeError, TypeError):
            continue
        if value:
            new_texts[record.spec.operation_id] = value
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
        for target in targets:
            keys = {str(key) for key in (target.get("operations") or ())}
            keys.update(str(key) for key in (target.get("claimed_operations") or ()))
            if operation_id not in keys or target.get("out_of_scope"):
                continue
            location = str(target.get("location") or "")
            try:
                before_text = str(before_inspection.by_location(location).text)
            except (KeyError, ValueError, IndexError, AttributeError):
                continue
            quote = str(target.get("quote") or "")
            if quote and _compact(quote) in _compact(before_text):
                sites.append({"location": location, "quote": quote,
                              "occurrence_index": target.get("occurrence_index", -1),
                              "target_id": target.get("target_id")})
            for part in target.get("composite") or []:
                from ..recall import display_text
                part_location, start, end = str(part).rsplit(":", 2)
                try:
                    part_span = before_inspection.by_location(part_location)
                    normalized, _ = display_text(part_span.text)
                    sites.append({"location": part_location,
                                  "quote": normalized[int(start):int(end)]})
                except (KeyError, ValueError, IndexError, AttributeError):
                    continue
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
            if item.get("state") == "PASS" or item.get("sites") or not group_sites:
                continue
            shared_sites = [{"location": location,
                             "quote": str(before_inspection.by_location(location).text)}
                            for location in group_sites]
            # Historical alternatives can share their certified business sites, not
            # independent siblings. The same evaluator must prove this alternative.
            proof = evaluate_operation_effect(record, before_inspection, after_inspection,
                                              shared_sites, effect_edits, facts)
            if proof.state == "PASS":
                obligation_state[record.obligation_id] = proof.as_dict()

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
    from types import SimpleNamespace
    spans = list(getattr(after_inspection, "paragraphs", ()))
    source = original or after_inspection
    source_spans = list(getattr(source, "paragraphs", ()))
    failures: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    edits = list(edits or [])
    for rule_id, rule in rules_by_id.items():
        operations = list(rule.get("operations") or [])
        for index, operation in enumerate(operations):
            if operation.get("op") != "delete":
                continue
            if facts is not None and condition_status(operation.get("condition"), facts) != "TRUE":
                continue
            operation_id = str(operation.get("operation_id") or f"{rule_id}:{index}")
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
                source_span = source_spans[span_index] if span_index < len(source_spans) else span
                semantic = location in known or target_site_ok(str(rule_id), source_span, source)
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
