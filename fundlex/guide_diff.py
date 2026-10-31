"""Deterministic diff between two parsed guide documents.

This module never calls a model: the same two inputs always produce the same
output.  Rules are compared on ``rule_id`` with field-level changes; group
structure, meta information and validation summaries are compared separately.
"""
from __future__ import annotations

import json
from typing import Any

ALGORITHM = "guide-diff-v1"

# Field-level comparison for rules with the same rule_id.  Only fields whose
# value actually changed are recorded.
RULE_FIELDS = ("title", "requirement", "operations", "old_text_variants",
               "slot_tokens", "class_substitution", "references")

_META_FIELDS = ("parser_version", "schema_version", "source_sha256",
                "prompt_versions")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _flatten_rules(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """rule_id -> rule mapping, accepting flat rules and nested groups."""
    rules: dict[str, dict[str, Any]] = {}
    for group in (document or {}).get("groups") or []:
        if not isinstance(group, dict):
            continue
        nested = group.get("rules")
        if isinstance(nested, list):
            for rule in nested:
                if isinstance(rule, dict) and rule.get("rule_id"):
                    rules[str(rule["rule_id"])] = rule
        elif group.get("rule_id"):
            rules[str(group["rule_id"])] = group
    return rules


def _group_key(group: dict[str, Any], index: int) -> str:
    nested = group.get("rules")
    if isinstance(nested, list):
        base = str(group.get("group_id") or group.get("title") or f"group#{index}")
        members = ",".join(str(rule.get("rule_id")) for rule in nested
                           if isinstance(rule, dict) and rule.get("rule_id"))
        return f"{base}({members})"
    return str(group.get("rule_id") or group.get("title") or f"group#{index}")


def _groups_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_keys = [_group_key(group, index)
                   for index, group in enumerate((before or {}).get("groups") or [])
                   if isinstance(group, dict)]
    after_keys = [_group_key(group, index)
                  for index, group in enumerate((after or {}).get("groups") or [])
                  if isinstance(group, dict)]
    before_set, after_set = set(before_keys), set(after_keys)
    shared = before_set & after_set
    order_changed = ([key for key in before_keys if key in shared]
                     != [key for key in after_keys if key in shared])
    return {"added": sorted(after_set - before_set),
            "removed": sorted(before_set - after_set),
            "order_changed": bool(order_changed)}


def _meta_diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for field in _META_FIELDS:
        old = (before or {}).get(field)
        new = (after or {}).get(field)
        if _canonical(old) != _canonical(new):
            diff[field] = {"old": old if old is not None else None,
                           "new": new if new is not None else None}
    return diff


def _validation_summary(document: dict[str, Any]) -> dict[str, Any]:
    validation = (document or {}).get("validation")
    validation = validation if isinstance(validation, dict) else {}
    verification = validation.get("verification")
    verification = verification if isinstance(verification, dict) else {}
    errors = validation.get("errors")
    warnings = validation.get("warnings")
    gaps = validation.get("coverage_gaps")
    findings = verification.get("findings")
    invalid = verification.get("invalid_findings")
    return {"clean": bool(validation.get("clean")),
            "errors": len(errors) if isinstance(errors, list) else 0,
            "warnings": len(warnings) if isinstance(warnings, list) else 0,
            "coverage_gaps": len(gaps) if isinstance(gaps, list) else 0,
            "findings": len(findings) if isinstance(findings, list) else 0,
            "invalid_findings": int(invalid) if isinstance(invalid, int) else 0,
            "rounds": int(validation.get("rounds") or 0)}


def diff_guide_documents(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Deterministic rule/structural diff; ``before`` is the base version."""
    before_rules = _flatten_rules(before)
    after_rules = _flatten_rules(after)
    before_ids, after_ids = set(before_rules), set(after_rules)
    added = sorted(after_ids - before_ids)
    removed = sorted(before_ids - after_ids)
    changed: list[dict[str, Any]] = []
    for rule_id in sorted(before_ids & after_ids):
        fields: dict[str, Any] = {}
        for field in RULE_FIELDS:
            old = before_rules[rule_id].get(field)
            new = after_rules[rule_id].get(field)
            if _canonical(old) != _canonical(new):
                fields[field] = {"old": old if old is not None else None,
                                 "new": new if new is not None else None}
        if fields:
            changed.append({"rule_id": rule_id, "fields": fields})
    groups = _groups_diff(before, after)
    meta = _meta_diff(before, after)
    validation = {"before": _validation_summary(before), "after": _validation_summary(after)}
    summary = {"rules_before": len(before_rules), "rules_after": len(after_rules),
               "added": len(added), "removed": len(removed), "changed": len(changed),
               "groups_added": len(groups["added"]), "groups_removed": len(groups["removed"]),
               "groups_order_changed": bool(groups["order_changed"]),
               "meta_fields_changed": len(meta),
               "identical": not (added or removed or changed or groups["added"]
                                 or groups["removed"] or groups["order_changed"] or meta)}
    return {"algorithm": ALGORITHM,
            "summary": summary,
            "rules": {"added": [{"rule_id": rule_id, "rule": after_rules[rule_id]} for rule_id in added],
                      "removed": [{"rule_id": rule_id, "rule": before_rules[rule_id]} for rule_id in removed],
                      "changed": changed},
            "groups": groups,
            "meta": meta,
            "validation": validation}
