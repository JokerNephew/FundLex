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


def _authorization_for_group(group: Sequence[Mapping[str, Any]],
                             rules_by_id: Mapping[str, dict]) -> Authorization:
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
        candidates = edit.get("components") or [edit]
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


def replay_claims(edits: Sequence[Mapping[str, Any]], before_inspection: Any,
                  after_inspection: Any, *, rules_by_id: Mapping[str, dict],
                  facts: Any = None, max_failures: int = 40,
                  components_by_rule: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
                  required_terms_by_rule: Mapping[str, Sequence[str]] | None = None
                  ) -> dict:
    """Replay every edit's claim against the actual artifact paragraphs.

    ``components_by_rule`` supplies the required policy components for a rule (plan
    §16.1).  They are verified inside the paragraph that carries the edit, never by
    searching the whole document.
    """
    from .validators import validate_edit
    by_location: dict[str, list[Mapping[str, Any]]] = {}
    for edit in edits:
        by_location.setdefault(str(edit.get("location") or ""), []).append(edit)

    failures: list[dict[str, Any]] = []
    checked = 0
    allowed_locations = set(by_location)
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
        missing_replacement = False
        for edit in group:
            replacement = str(edit.get("replacement") or "")
            if replacement.strip() and _compact(replacement) not in _compact(after):
                failures.append({"rule_id": rule_label, "location": location,
                                 "code": "CLAIM_REPLACEMENT_MISSING",
                                 "reason": "the written paragraph does not carry the planned replacement"})
                missing_replacement = True
                break
        if missing_replacement:
            continue
        expected = _expected_after(before, group)
        if expected is not None and _compact(expected) != _compact(after):
            failures.append({"rule_id": rule_label, "location": location,
                             "code": "CLAIM_OUTSIDE_SPAN_CHANGED",
                             "reason": "the written paragraph differs outside the authorized span"})
            continue
        auth = _authorization_for_group(group, rules_by_id)
        rule_ids = {rule_id for edit in group for rule_id in _rule_ids(edit)}
        components: list[Mapping[str, Any]] = []
        for rule_id in rule_ids:
            components.extend((components_by_rule or {}).get(rule_id) or [])
        required_terms: list[str] = []
        for rule_id in rule_ids:
            required_terms.extend((required_terms_by_rule or {}).get(rule_id) or [])
        validation = validate_edit(before, after, auth=auth,
                                   components=tuple(components),
                                   required_terms=tuple(dict.fromkeys(required_terms)),
                                   authorized_numbers=_facts_numbers(facts))
        if validation.verdict == "FAIL":
            codes = sorted({finding.code for finding in validation.findings})
            hard = [record.reason for record in validation.changes
                    if record.explanation == "UNEXPLAINED_HARD"]
            failures.append({"rule_id": rule_label, "location": location,
                             "code": "CLAIM_VALIDATION_FAILED",
                             "reason": ",".join(codes or hard or ["UNEXPLAINED_CHANGE"]),
                             "validator": validation.as_dict()})
        if len(failures) >= max_failures:
            break
    return {"verified": not failures, "checked": checked,
            "failures": failures[:max_failures]}
