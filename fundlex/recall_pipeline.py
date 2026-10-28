"""Recall-first orchestration pipeline (handoff §7 A–F).

The engine core in :mod:`fundlex.recall` owns structure, addresses, source
verification and edit geometry; this module owns the business flow:
qualification, window inventory, the write/audit/repair loop, the final artifact
sweep and the delivery decision.

Two invariants are enforced here on top of the core:

* a model answer is never trusted with offsets — every quote returned by an
  audit/sweep call is re-checked against the exact region that was supplied and
  re-resolved against the real document before it is used;
* a repair round always rebuilds the whole plan from the ORIGINAL inspection and
  regenerates the artifact from the original source instead of stacking edits on
  a previous artifact, so independent correct units survive a repair.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from .docx import (DocxError, DocumentInspection, generate_artifacts,
                   generate_unchanged_artifacts, inspect_docx, validate_edit_plan)
from .generation.flags import strategy_mode
from .frozen import FrozenError
from .guide import guide_document_sha256
from .model import ModelError, ModelGateway
from .models.config import RoleConfigError
from .models.roles import build_role_gateway
from .recall import (BOUNDARY_POLICY, ENGINE_ID, ENGINE_VERSION, SCHEMA_VERSION,
                     Facts, RecallError, SurveyHit, Target, Window, build_docx_edits,
                     containing_segment, content_check_factory, display_text,
                     extract_facts, inventory_window, plan_edits, plan_windows,
                     condition_matches, condition_status, find_old_text_all, fuzzy_span, instantiate_slots,
                      resolve_old_text, resolve_quote, resolve_source_quote, rule_context, scope_map,
                     expand_class_definition_scope, structure_index, survey_targets, compact_offsets,
                      append_applicability_targets, is_delete_only_rule, Section,
                      rule_scope_locations,
                     known_operations_from_targets, operations_cover_hit,
                      target_operation_keys, _add_operation_coverage,
                      assign_target_operations, duplicate_copy_targets,
                      _declared_operation_key,
                      _expand_fee_rate_reference,
                      dedupe_operation_targets,
                      source_parts_contiguous)
from .recall_prompts import (AUDIT_INSTRUCTION, AUDIT_PROMPT_VERSION, AUDIT_SCHEMA,
                             PROMPT_VERSIONS, SWEEP_INSTRUCTION, SWEEP_PROMPT_VERSION,
                             SWEEP_SCHEMA)
from .rule_scope import (RuleScope, build_leaf_sections, resolve_rule_scopes,
                         scope_locations, scope_locations_for_window)

STOP_CODES = {"MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED",
              "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_CIRCUIT_OPEN", "MODEL_LEDGER_UNAVAILABLE",
              "MODEL_CONFIG_MISSING", "MODEL_HTTP_ERROR", "MODEL_RETRY_EXHAUSTED",
              "MODEL_CHECKPOINT_UNAVAILABLE", "MODEL_REPLAY_MISS", "MODEL_CASSETTE_UNAVAILABLE",
              "MODEL_CONCURRENCY_LIMIT", "MODEL_RESERVATION_EXPIRED"}
VERIFICATION_BLOCKED_CODES = {
    "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED",
    "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_LEDGER_UNAVAILABLE",
    "MODEL_CHECKPOINT_UNAVAILABLE", "MODEL_REPLAY_MISS",
    "MODEL_CASSETTE_UNAVAILABLE",
}

# Global exclusions (product rulings 2026-10-19/20: ETF / money-market / interbank-CD /
# REITs (including closed-end commercial real estate) stay out of the modification scope;
# rationale and provenance recorded in DETAIL FL-D130).
DEFAULT_EXCLUDED_TYPES = "etf,money_market,interbank_cd,reits"
DEFAULT_MAX_COMPOSE_CALLS = 8
SWEEP_ISSUES = {"residual_old_text", "missing_new_text", "wrong_text", "unaddressed_requirement"}
READABLE_ZONES = {"body", "summary"}
MIN_WINDOW_CHARS = 4000
MIN_CHUNK_CHARS = 1500
# Fixed headings and separators added around the three sweep context parts.
_SWEEP_CONTEXT_OVERHEAD = 200
MAX_REPAIR_NOTE_CHARS = 1400
# A malformed or mis-quoted model answer is recoverable: pausing and resuming from the
# checkpoint is better than failing the contract on one bad response.
SOFT_STOP_CODES = {"MODEL_SCHEMA_INVALID", "MODEL_QUOTE_MISMATCH",
                   "MODEL_EVIDENCE_UNKNOWN", "MODEL_RESPONSE_LIMIT",
                   # A response cut off at the provider's output cap (FL-D108): recoverable,
                   # so pause and resume rather than failing the contract outright.
                   "MODEL_OUTPUT_TRUNCATED"}


def _default_gateway() -> Any:
    """Build the primary/review role gateway (plan §4).

    A deployment that only sets ``LLM_*`` resolves both roles to that endpoint; the
    review role remains a separate task role with its own call records.  Invalid role
    configuration stops the run as an infrastructure error instead of silently
    falling back to a single model.

    When no endpoint is configured at all, defer to ``ModelGateway.from_env`` so
    existing worker/test seams (which may monkeypatch that classmethod) keep working.
    """
    configured = any(os.environ.get(name) for name in
                     ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY",
                      "FUNDLEX_MODEL_ROLES_FILE", "FUNDLEX_PRIMARY_MODEL",
                      "FUNDLEX_REVIEW_MODEL"))
    if not configured:
        return ModelGateway.from_env()
    try:
        return build_role_gateway()
    except RoleConfigError as exc:
        raise ModelError("MODEL_CONFIG_MISSING", {"detail": str(exc)}) from exc


class RecallPipelineStop(RuntimeError):
    """Recoverable model/transport stop: the worker pauses and resumes later."""

    def __init__(self, code: str, detail: dict | None = None, *, report: dict | None = None):
        self.code, self.detail = code, detail or {}
        self.report = report
        super().__init__(code)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


def _qualification_status(facts: Facts, excluded_types: Sequence[str]) -> tuple[str, bool]:
    """Qualification decision plus whether the contract may stop here.

    A whole-contract exclusion is irreversible, so it needs verified evidence. An
    unverified excluded type is not allowed to end the run; it continues and the
    delivery gate marks it incomplete (FL-D114).
    """
    excluded = facts.fund_type in excluded_types
    verified = bool(facts.quotes_verified.get("fund_type"))
    certified = facts.fund_type_certification.get("status") == "CERTIFIED"
    if excluded and verified and certified:
        return "excluded_by_fund_type", True
    if excluded:
        return "eligible_fund_type_unverified", False
    return "eligible", False


def _excluded_types() -> tuple[str, ...]:
    raw = os.environ.get("FUNDLEX_RECALL_EXCLUDED_TYPES", DEFAULT_EXCLUDED_TYPES)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _guide_rules(guide_document: dict) -> list[dict[str, Any]]:
    """Flatten the guide document's groups; both rule lists and grouped rules work."""
    groups = guide_document.get("groups") if isinstance(guide_document, dict) else None
    rules: list[dict[str, Any]] = []
    for item in groups or []:
        if not isinstance(item, dict):
            continue
        nested = item.get("rules")
        if isinstance(nested, list):
            rules.extend(rule for rule in nested
                         if isinstance(rule, dict) and rule.get("rule_id"))
        elif item.get("rule_id"):
            rules.append(item)
    return rules


def _guide_sha(guide_document: dict) -> str:
    document_sha = str((guide_document or {}).get("document_sha256") or "")
    if document_sha:
        return document_sha
    try:
        return guide_document_sha256(guide_document)
    except Exception:  # noqa: BLE001 - a missing hash must not abort qualification
        return ""


@dataclass
class _WindowState:
    """One mapped window with its rules and its per-round inventory history."""

    window: Window
    rules: tuple[dict[str, Any], ...]
    targets: list[Target] = field(default_factory=list)
    ledgers: list[dict[str, Any]] = field(default_factory=list)

    @property
    def rule_ids(self) -> list[str]:
        return [rule["rule_id"] for rule in self.rules]


def _inventory(entry: _WindowState, note: str | None, facts: Facts, model: Any,
               inspection: DocumentInspection, *, round_number: int,
               rule_locations: Mapping[str, Sequence[str]] | None = None,
               scope_audit: dict[str, Any] | None = None) -> None:
    """Inventory one window, optionally carrying a repair note for the model."""
    window = entry.window
    if note:
        window = Window(id=window.id, section_ids=window.section_ids, locations=window.locations,
                        text=window.text + "\n\n[REPAIR_CONTEXT]\n" + _clip(note, MAX_REPAIR_NOTE_CHARS))

    def _sub_window(source: Window, locations: Sequence[str], suffix: str) -> Window:
        lines: list[str] = []
        for location in locations:
            span = inspection.by_location(location)
            cleaned, _ = display_text(span.text)
            lines.append(f"[{location}] {cleaned}")
        return Window(id=f"{source.id}{suffix}", section_ids=source.section_ids,
                      locations=tuple(locations), text="\n".join(lines))

    def _run(source: Window) -> tuple[list[Target], list[dict[str, Any]]]:
        try:
            targets, ledger = inventory_window(
                source, entry.rules, facts, model, inspection,
                rule_locations=rule_locations)
            return list(targets), [ledger]
        except ModelError as exc:
            # A provider can return a syntactically incomplete inventory even when the
            # request fits the context limit.  Treat output truncation like the
            # deterministic context split: divide the bounded window on paragraph
            # addresses and retry each half.  This is a bounded recovery, not another
            # retry of the same request, and therefore cannot hide a missing operation.
            if exc.code != "MODEL_OUTPUT_TRUNCATED" or len(source.locations) < 2:
                raise
            middle = len(source.locations) // 2
            left = _sub_window(source, source.locations[:middle], "~a")
            right = _sub_window(source, source.locations[middle:], "~b")
            left_targets, left_ledgers = _run(left)
            right_targets, right_ledgers = _run(right)
            return left_targets + right_targets, [
                {"window": source.id, "split": 2, "reason": exc.code,
                 "parts": [left.id, right.id],
                 "targets": [target.as_dict() for target in left_targets + right_targets]},
                *left_ledgers, *right_ledgers,
            ]
        except RecallError as exc:
            # Context-limit recovery (plan §31): split the window and retry, never end
            # the contract because one inventory call was too large.
            if exc.code != "RECALL_INVENTORY_CONTEXT_LIMIT" or len(source.locations) < 2:
                raise
            middle = len(source.locations) // 2
            left = _sub_window(source, source.locations[:middle], "~a")
            right = _sub_window(source, source.locations[middle:], "~b")
            left_targets, left_ledgers = _run(left)
            right_targets, right_ledgers = _run(right)
            return left_targets + right_targets, [
                {"window": source.id, "split": 2,
                 "parts": [left.id, right.id],
                 "targets": [target.as_dict() for target in left_targets + right_targets]},
                *left_ledgers, *right_ledgers,
            ]

    targets, ledgers = _run(window)
    entry.targets = targets
    for ledger in ledgers:
        entry.ledgers.append({**ledger, "round": round_number,
                              "repair_context": _clip(note, MAX_REPAIR_NOTE_CHARS) if note else None})
        if scope_audit is None:
            continue
        for dropped in ledger.get("dropped") or []:
            if dropped.get("reason") != "INVENTORY_ITEM_OUT_OF_RULE_SCOPE":
                continue
            item = dropped.get("item") or {}
            _record_scope_drop(scope_audit, stage="inventory",
                               rule_id=str(item.get("rule_id") or ""),
                               location=str(item.get("location") or ""))


def _window_ledger(entry: _WindowState) -> dict[str, Any]:
    coverage: dict[str, dict[str, int]] = {}
    for rule_id in entry.rule_ids:
        rule_targets = [target for target in entry.targets if target.rule_id == rule_id]
        coverage[rule_id] = {
            "targets": len(rule_targets),
            "needs_edit": sum(1 for t in rule_targets if t.state == "needs_edit"),
            "satisfied": sum(1 for t in rule_targets if t.state == "satisfied"),
            "absent": sum(1 for t in rule_targets if t.state == "absent"),
            "resolved_quotes": sum(1 for t in rule_targets if t.resolution == "resolved"),
        }
    return {
        "window": entry.window.id,
        "sections": list(entry.window.section_ids),
        "locations": list(entry.window.locations),
        "rules": entry.rule_ids,
        "chars": len(entry.window.text),
        "rounds": entry.ledgers,
        "targets": [target.as_dict() for target in entry.targets],
        "coverage": coverage,
    }


def _scope_mapping_ledger(mapping: dict[str, list[str]], sections: Sequence[Any],
                          entries: Sequence[_WindowState], rules: Sequence[dict]) -> dict[str, Any]:
    coverage: list[dict[str, Any]] = []
    for rule in rules:
        rule_id = rule["rule_id"]
        rule_targets = [target for entry in entries for target in entry.targets
                        if target.rule_id == rule_id]
        item: dict[str, Any] = {
            "rule_id": rule_id,
            "sections": list(mapping.get(rule_id) or []),
            "mapped": bool(mapping.get(rule_id)),
        }
        if rule_targets:
            item["coverage"] = "targets_found"
            item["counts"] = {
                "targets": len(rule_targets),
                "needs_edit": sum(1 for t in rule_targets if t.state == "needs_edit"),
                "satisfied": sum(1 for t in rule_targets if t.state == "satisfied"),
                "absent": sum(1 for t in rule_targets if t.state == "absent"),
                "unresolved_quotes": sum(1 for t in rule_targets if t.resolution != "resolved"),
            }
            item["windows"] = sorted({entry.window.id for entry in entries
                                      for target in entry.targets if target.rule_id == rule_id})
        else:
            # No target in any window is recorded explicitly; the final sweep is
            # the document-wide safety net for these rules (never silent success).
            item["coverage"] = "no_target_found"
            item["counts"] = {"targets": 0, "needs_edit": 0, "satisfied": 0, "absent": 0,
                              "unresolved_quotes": 0}
        coverage.append(item)
    return {
        "sections": [{"id": section.id, "title": section.title, "zone": section.zone,
                      "chars": section.chars,
                      "locations": [section.locations[0], section.locations[-1]] if section.locations else []}
                     for section in sections],
        "mappings": {rule_id: list(ids) for rule_id, ids in mapping.items()},
        "coverage": coverage,
        "no_target_rules": [item["rule_id"] for item in coverage
                            if item["coverage"] == "no_target_found"],
    }


def _rule_evidence(mapping: dict[str, list[str]], sections: Sequence[Section],
                   inspection: DocumentInspection, rule_ids: set[str],
                   *, limit: int = 9000,
                   scopes: Mapping[str, Any] | None = None) -> dict[str, str]:
    """Section or rule-scope text for applicability recovery, one bounded string per rule."""
    if not rule_ids:
        return {}
    by_id = {section.id: section for section in sections}

    def _order(location: str) -> tuple[str, int, str]:
        match = re.match(r"^([A-Za-z]*)(\d+)$", str(location))
        return (match.group(1), int(match.group(2)), "") if match else (str(location), -1, "")

    evidence: dict[str, str] = {}
    for rule_id in rule_ids:
        parts: list[str] = []
        if scopes is not None:
            # A rule may only be judged from the physical paragraphs in its own scope;
            # a sibling clause in the mapped chapter is not evidence for this rule.
            scope = scopes.get(rule_id)
            locations = sorted(getattr(scope, "locations", ()) or (), key=_order) \
                if scope is not None else []
        else:
            locations = [location for section_id in mapping.get(rule_id) or []
                         if (section := by_id.get(section_id)) is not None
                         for location in section.locations]
        for location in locations:
            try:
                span = inspection.by_location(location)
            except DocxError:
                continue
            text, _ = display_text(span.text)
            if text.strip():
                parts.append(f"[{location}] {text}")
            if sum(len(part) for part in parts) >= limit:
                break
        if parts:
            evidence[rule_id] = "\n".join(parts)[:limit]
    return evidence


def _applicability_recovery_enabled() -> bool:
    return os.environ.get("FUNDLEX_APPLICABILITY_RECOVERY", "1").strip().lower() not in {
        "0", "false", "off", "no"}


def _recovery_snapshot(targets: Sequence[Target], planned: dict[str, Any],
                       actual: DocumentInspection, replay: dict[str, Any], *,
                       facts: Facts | None = None, obligations: Any = None,
                       scope: dict | None = None) -> str:
    """Stable fingerprint of everything a recovery action could change.

    Two consecutive rounds with the same target set, plan, artifact text and unresolved
    claim failures cannot produce a different result by rebuilding the same inputs.
    """
    material = {
        "targets": [
            (target.rule_id, target.location, target.start, target.end,
             tuple(target.operations), target.quote, target.state, target.resolution, target.out_of_scope)
            for target in targets],
        "plan": sorted(
            (tuple(edit.get("operation_keys") or []), str(edit.get("location")),
             int(edit.get("start") or 0), int(edit.get("end") or 0),
             str(edit.get("replacement") or ""))
            for edit in planned.get("edits") or []),
        "artifact": [str(getattr(span, "text", ""))
                     for span in getattr(actual, "paragraphs", ())],
        "failures": sorted(
            (str(item.get("code") or ""), str(item.get("operation_id") or ""),
             str(item.get("location") or ""))
            for item in replay.get("failures") or []),
    }
    material["facts"] = facts.as_ledger() if facts is not None else {}
    material["applicability"] = {record.spec.operation_id: record.applicability.as_dict()
                                  for record in obligations.records} if obligations is not None else {}
    material["scope"] = scope or {}
    material["operation_coverage"] = sorted(
        (target.location, key) for target in targets for key in target.operations
        if not target.out_of_scope)
    material["targets"].sort(key=lambda row: json.dumps(row, ensure_ascii=False))
    from .frozen import digest
    # Keep the individual boundaries inspectable in every recovery round.
    hashes = {name + "_hash": digest(value) for name, value in material.items()}
    hashes["final_edit_hash"] = digest(planned.get("edits") or [])
    replay["recovery_state_hashes"] = hashes
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True)
                          .encode("utf-8")).hexdigest()


def _artifact_text_signature(actual: DocumentInspection) -> str:
    """Fingerprint the semantic artifact state, excluding DOCX container bytes.

    A DOCX write refreshes ZIP entry timestamps and can therefore change
    ``source_sha256`` even when every paragraph is byte-for-byte identical. Sweep
    recovery must only be allowed to perform a second pass after a meaningful
    artifact text/structure change.
    """
    from .frozen import digest
    paragraphs = [(str(span.location), str(span.text), str(getattr(span, "zone", "")),
                   str(getattr(span, "part_uri", "")), str(getattr(span, "section_path", "")))
                  for span in actual.paragraphs]
    return digest({"paragraphs": paragraphs, "parts": list(getattr(actual, "parts", ()) or ()),
                   "has_toc_field": bool(getattr(actual, "has_toc_field", False))})


def _sweep_recovery_contexts(pending: Sequence[dict[str, Any]], targets: Sequence[Target],
                             planned: dict[str, Any], replay: dict[str, Any],
                             rules_by_id: dict[str, dict] | None = None) -> list[Any]:
    """Route a sweep candidate by the missing layer at its own business site.

    A model's GENERATION/TARGET hint cannot make an existing, attributed target
    disappear. Reuse the same operation-specific root-cause classifier as Audit;
    only a genuinely unbound site needs target discovery.
    """
    from .recovery import FailureClass, RecoveryContext
    contexts = []
    seen = set()
    for finding in pending:
        rule_id = str(finding.get("rule_id") or "")
        location = str(finding.get("location") or "")
        own = [target for target in targets if target.rule_id == rule_id
               and target.location == location and not target.out_of_scope
               and target.operations and target.state != "absent"]
        if own:
            operation_id = str(finding.get("operation_id") or "")
            if not operation_id and rules_by_id:
                quote = _compact(str(finding.get("quote") or ""))
                rule = rules_by_id.get(rule_id) or {}
                matches = [_declared_operation_key(rule_id, index, operation)
                           for index, operation in
                           enumerate(rule.get("operations") or [])
                           if _compact(str(operation.get("old_text") or ""))
                           and (_compact(str(operation.get("old_text") or "")) in quote
                                or quote in _compact(str(operation.get("old_text") or "")))]
                if len(matches) == 1:
                    operation_id = matches[0]
            target = next((item for item in own if operation_id in item.operations), None)
            if target is None and len(own) == 1 and len(own[0].operations) == 1:
                target, operation_id = own[0], own[0].operations[0]
            if target is None or not operation_id:
                routed = [RecoveryContext(stage="sweep", rule_id=rule_id, site_id=location,
                    target_id=own[0].target_id, error_code="SWEEP_OPERATION_UNBOUND",
                    failure_class=FailureClass.TARGET,
                    reason=str(finding.get("reason") or ""),
                    metadata={"finding_id": str(finding.get("finding_id") or "")})]
            else:
                matching_failure = next((failure for failure in replay.get("failures") or []
                    if str(failure.get("operation_id") or "") == operation_id
                    and str(failure.get("location") or "") == location), None)
                if matching_failure:
                    # Claim failures carry the authoritative root cause. In
                    # particular, CLAIM_OPERATION_NOT_PLANNED/UNPROVEN with an
                    # existing target is TARGET_EXISTS_NO_PLAN and therefore
                    # Generation recovery; classify(code) alone would incorrectly
                    # route it back to Target discovery.
                    failure = {**matching_failure,
                               "rule_id": matching_failure.get("rule_id") or rule_id,
                               "location": matching_failure.get("location") or location,
                               "target_id": matching_failure.get("target_id") or target.target_id,
                               "operation_id": operation_id,
                               "reason": matching_failure.get("reason") or finding.get("reason")}
                    routed_context = _claim_failure_context(
                        failure, targets, planned.get("edits") or [])
                    routed_context.stage = "sweep"
                    routed_context.metadata = {
                        **routed_context.metadata,
                        "finding_id": str(finding.get("finding_id") or ""),
                        "source_span": f"{target.start}:{target.end}",
                    }
                    routed = [routed_context]
                else:
                    routed = [RecoveryContext(stage="sweep", rule_id=rule_id,
                        operation_id=operation_id, obligation_id=operation_id,
                        target_id=target.target_id, site_id=location,
                        error_code="SWEEP_EFFECT_UNRESOLVED",
                        failure_class=FailureClass.GENERATION,
                        reason=str(finding.get("reason") or ""),
                        metadata={"finding_id": str(finding.get("finding_id") or ""),
                                  "source_span": f"{target.start}:{target.end}"})]
        else:
            routed = [RecoveryContext(stage="sweep", rule_id=rule_id, site_id=location,
                operation_id=str(finding.get("operation_id") or ""),
                error_code="SWEEP_TARGET_UNBOUND", failure_class=FailureClass.TARGET,
                reason=str(finding.get("reason") or ""),
                metadata={"finding_id": str(finding.get("finding_id") or "")})]
        for context in routed:
            key = _audit_context_key(context)
            if key not in seen:
                seen.add(key)
                contexts.append(context)
    return contexts


def _claim_failure_context(failure: dict, targets: Sequence[Target], edits: Sequence[dict], *,
                           strategy_escalation: bool | None = None,
                           content_source: str | None = None,
                           mode: str | None = None) -> Any:
    """Route the missing layer, retaining the dirty operation and business site.

    ``strategy_escalation`` is an explicit opt-in hook for callers that can execute
    generation-router methods.  Keeping it off by default preserves the legacy
    claim-replay recovery path while allowing a failure producer to carry the
    concrete strategy cursor through to :class:`RecoveryOrchestrator`.
    """
    from .generation.effects import operation_units
    from .recovery import RecoveryContext, FailureClass, classify
    operation_id = str(failure.get("operation_id") or "")
    location = str(failure.get("location") or "")
    code = str(failure.get("code") or "CLAIM_REPLAY_FAILED")
    own_targets = [target for target in targets if not target.out_of_scope
                   and (not location or target.location == location)
                   and (operation_id in target.operations if operation_id else
                        target.target_id == failure.get("target_id"))]
    own_plan = [(edit, unit) for edit, unit in operation_units(edits, operation_id)
                if not location or str(unit.get("location") or edit.get("location")) == location]
    failure_class = classify(code)
    layer = failure_class.value
    if code in {"CLAIM_OPERATION_NOT_PLANNED", "CLAIM_OPERATION_UNPROVEN"}:
        failure_class = FailureClass.GENERATION if own_targets else FailureClass.TARGET
        layer = "TARGET_EXISTS_NO_PLAN" if own_targets else "NO_TARGET"
    elif code == "CLAIM_PLANNED_EFFECT_MISSING":
        failure_class, layer = FailureClass.GENERATION, "PLAN_EFFECT_WRONG"
    elif code in {"CLAIM_EXECUTION_EFFECT_MISSING", "CLAIM_OUTSIDE_SPAN_CHANGED",
                  "CLAIM_NO_CHANGE_APPLIED", "CLAIM_REPLACEMENT_MISSING"} and own_plan:
        failure_class, layer = FailureClass.EXECUTION, "ARTIFACT_EFFECT_WRONG"
    metadata = {"root_cause": layer, "target_exists": bool(own_targets),
                "plan_exists": bool(own_plan)}
    if strategy_escalation is None:
        strategy_escalation = bool(failure.get("strategy_escalation"))
    if strategy_escalation:
        metadata["strategy_escalation"] = True
        if content_source is None:
            content_source = failure.get("content_source")
        if mode is None:
            mode = failure.get("mode")
        if content_source:
            metadata["content_source"] = str(content_source)
        if mode:
            metadata["mode"] = str(mode)
    return RecoveryContext(stage="claim_replay", failure_class=failure_class,
        error_code=code, reason=str(failure.get("reason") or ""),
        rule_id=str(failure.get("rule_id") or ""), operation_id=operation_id,
        obligation_id=str(failure.get("obligation_id") or ""), site_id=location,
        target_id=str(failure.get("target_id") or (own_targets[0].target_id if own_targets else "")),
        metadata=metadata)


def _plan_by_target(planned: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_target: dict[str, dict[str, Any]] = {}
    for entry in planned.get("ledger") or []:
        by_target[str(entry.get("target_id"))] = dict(entry)
    for edit in planned.get("edits") or []:
        for component in edit.get("components") or []:
            # A component without a ledger entry is an invariant violation, not a
            # successful plan: the delivery gate treats "planned" as resolved, so the
            # old default could turn a missing record into a false ``complete``
            # (FL-D110). Keep it unresolved so it blocks delivery honestly.
            record = by_target.setdefault(str(component.get("target_id")), {
                "target_id": component.get("target_id"), "rule_id": component.get("rule_id"),
                "status": "unresolved", "reason": "LEDGER_MISSING"})
            record["operation"] = component.get("operation")
            record["replacement"] = component.get("replacement")
    return by_target


def _plan_ledger(planned: dict[str, Any], plan: Any) -> dict[str, Any]:
    # The planner's parent edit is intentionally a business record, while
    # ``validate_edit_plan`` owns the final source slice used by the DOCX writer.
    # Persist that validated expected text as well: selective Review reconstructs
    # revision manifests from this report, and an atomic paragraph edit otherwise
    # has no parent-level expected_old_text (FL-D275).
    planned_edits = [dict(item) for item in (planned.get("edits") or [])]
    validated = {}
    for edit in getattr(plan, "edits", ()):
        key = (str(edit.get("rule_id") or ""), str(edit.get("target_id") or ""),
               str(edit.get("location") or ""), int(edit.get("start") or 0),
               int(edit.get("end") or 0), str(edit.get("replacement") or ""))
        validated[key] = edit
    for item in planned_edits:
        key = (str(item.get("rule_id") or ""), str(item.get("target_id") or ""),
               str(item.get("location") or ""), int(item.get("start") or 0),
               int(item.get("end") or 0), str(item.get("replacement") or ""))
        source = validated.get(key)
        if source is not None:
            item["expected_old_text"] = source.get("expected_old_text", "")
            item["expected_old_hash"] = source.get("expected_old_hash", "")
    return {"count": len(planned_edits), "sha256": plan.plan_sha256,
            "edits": planned_edits, "conflicts": planned.get("conflicts") or [],
            "ledger": planned.get("ledger") or [], "boundary_policy": BOUNDARY_POLICY}


def _target_identity(target: Target) -> tuple[str, str, str]:
    """Stable audit key: rule + paragraph + exact source span.

    The quote is evidence, not identity. The old key truncated it to 60 characters,
    so a repair that only changed the tail kept the identity and the stale
    ``completed`` verdict survived (FL-D110). Hash the full span (and the composite
    parts) instead; any content change re-opens the audit.
    """
    material = "\x1f".join((
        str(target.start), str(target.end), _compact(target.quote),
        "|".join(target.composite),
        "|".join(sorted(target.operations)), str(target.occurrence_index),
    ))
    return (target.rule_id, target.location,
            hashlib.sha256(material.encode("utf-8")).hexdigest())


def _operation_terminal_proof(target: Target, replay: Mapping[str, Any],
                              obligations: Any) -> bool:
    """True when every operation claimed by a candidate target is already proven.

    A candidate target may be discovered early and remain in the ledger after another
    target/artifact proof has made it redundant.  Obligation proof is authoritative;
    a stale candidate must not block delivery merely because it has no plan entry.
    """
    if obligations is None or not target.operations:
        return False
    from .generation.effects import effect_proof_passed
    states = replay.get("obligations") or {}
    for operation_id in target.operations:
        record = obligations.record(operation_id)
        if record is None or record.applicability.status != "TRUE":
            return False
        proof = states.get(record.obligation_id)
        if not isinstance(proof, Mapping) or not effect_proof_passed(
                proof, operation_id=record.spec.operation_id,
                obligation_id=record.obligation_id):
            return False
    return True


def _target_matches_operation_proof(target: Target, replay: Mapping[str, Any],
                                    obligations: Any) -> bool:
    """Require terminal proof for this target's physical site.

    Operation-level completion is insufficient for a sibling occurrence.  A
    post-proof candidate may be retired only when every source location it owns
    is represented by the operation's artifact proof, including occurrence ids.
    """
    if not _operation_terminal_proof(target, replay, obligations):
        return False
    for operation_id in target.operations:
        record = obligations.record(operation_id) if obligations is not None else None
        if record is None:
            return False
        proof = (replay.get("obligations") or {}).get(record.obligation_id)
        if not isinstance(proof, Mapping):
            return False
        # Each operation must prove the candidate's site itself. A union across
        # siblings lets a proof at p0 retire another operation's unproven p0 target
        # merely because that other operation completed at p1.
        sites: set[str] = set()
        sites.update(str(site) for site in proof.get("sites") or () if str(site).strip())
        for evidence in proof.get("evidence") or ():
            if isinstance(evidence, Mapping):
                site = str(evidence.get("site_id") or evidence.get("location") or "")
                if site:
                    sites.add(site)
        for effect in proof.get("site_effects") or ():
            if isinstance(effect, Mapping):
                site = str(effect.get("site_id") or effect.get("location") or "")
                if site:
                    sites.add(site)
        required = list(target.composite) or [target.location]
        for part in required:
            raw_part = str(part)
            location = raw_part
            if target.composite:
                # Composite parts are location:start:end.  Locations themselves may
                # contain punctuation, so split from the right rather than at the
                # first colon.
                fields = raw_part.rsplit(":", 2)
                if len(fields) == 3 and fields[1].isdigit() and fields[2].isdigit():
                    location = fields[0]
            # Composite strings are location:start:end; occurrence proof may use the
            # location only when no explicit occurrence was assigned to the target.
            candidates = {site for site in sites if site == location or
                          site.split("#occurrence:", 1)[0] == location}
            if not candidates:
                return False
            if target.occurrence_index >= 0 and not any(
                    site.endswith(f"#occurrence:{target.occurrence_index}") for site in candidates):
                return False
    return True


def _reconcile_candidate_targets(targets: Sequence[Target], planned: dict[str, Any],
                                 replay: Mapping[str, Any], obligations: Any) -> int:
    """Mark post-proof redundant candidate targets nonblocking (D16 T3001)."""
    by_target = _plan_by_target(planned)
    reconciled = 0
    for target in targets:
        if target.state != "needs_edit" or target.out_of_scope:
            continue
        status = (by_target.get(target.target_id) or {}).get("status")
        if status in {"planned", "satisfied", "not_applicable"}:
            continue
        if not _target_matches_operation_proof(target, replay, obligations):
            continue
        target.out_of_scope = True
        target.reason = f"{target.reason}|POST_PROOF_SUPERSEDED"
        reconciled += 1
    return reconciled


def _target_ledger(targets: Sequence[Target], planned: dict[str, Any],
                   audit_state: dict[str, Any], origins: dict[str, str]) -> list[dict[str, Any]]:
    by_target = _plan_by_target(planned)
    results = audit_state.get("results") or {}
    records: list[dict[str, Any]] = []
    for target in targets:
        record = target.as_dict()
        plan_entry = by_target.get(target.target_id) or {}
        record["status"] = plan_entry.get("status", "not_planned")
        record["plan_reason"] = plan_entry.get("reason")
        result = results.get(_target_identity(target))
        record["audit"] = ({"verdict": result["verdict"], "evidence_verified": result["evidence_verified"],
                            "reason": result["reason"]} if result else None)
        record["origin"] = origins.get(target.target_id, "inventory")
        records.append(record)
    return records



_COLLECTION_MISSING = object()


def _collection_covered(known: dict[tuple[str, str], set[str] | None], rule_id: str,
                        location: str, operations: Sequence[str]) -> bool:
    """Operation-aware duplicate suppression for the collection step.

    Unlike the survey fail-open rule, the collection step is fail-closed on an unknown
    coverage state: an inventory target whose operation could not be determined must
    not let a duplicate synthetic target through, or overlapping edits conflict and the
    real obligation is lost (round14-08: RECALL_EDIT_OVERLAP 66 vs 8).
    """
    state = known.get((rule_id, location), _COLLECTION_MISSING)
    if state is _COLLECTION_MISSING:
        return False
    if state is None:
        return True
    if not state:
        return False
    if operations:
        return bool(set(operations) & state)
    return True


def _collect_targets(entries: Sequence[_WindowState], synthetic: Sequence[Target],
                     rules_by_id: dict[str, dict], inspection: DocumentInspection) -> list[Target]:
    """Merge inventory and survey targets with operation-aware duplicate suppression.

    A synthetic target is kept when its own operation is not already covered at every
    location (for example the delete hit for G05:1 where inventory reported G05:0).
    Exact duplicates and unknown-coverage duplicates are dropped. A wildcard synthetic
    target (the deterministic append pass) is only suppressed by a ``needs_edit``
    inventory target that will actually plan that operation; an ``absent`` inventory
    judgment must not swallow the append the pass just located (FL-D118).
    """
    window_targets = [target for entry in entries for target in entry.targets]
    known = known_operations_from_targets(window_targets, rules_by_id, inspection)
    # A wildcard synthetic target (the deterministic append pass) is suppressed by an
    # inventory target that will plan the operation or that already satisfies it. An
    # ``absent`` judgment is exactly what the pass corrects, so it must not block.
    blocking_locations = {(target.rule_id, location) for target in window_targets
                          if target.state in {"needs_edit", "satisfied"}
                          for location in _target_locations(target)}
    collected = list(window_targets)
    for target in synthetic:
        rule = rules_by_id.get(target.rule_id)
        operations = tuple(getattr(target, "operations", ()) or ()) or tuple(
            target_operation_keys(target, rule, inspection))
        locations = _target_locations(target)
        if operations:
            if all(_collection_covered(known, target.rule_id, location, operations)
                   for location in locations):
                continue
        elif all((target.rule_id, location) in blocking_locations for location in locations):
            continue
        collected.append(target)
        if operations:
            for location in locations:
                _add_operation_coverage(known, target.rule_id, location, operations)
        else:
            for location in locations:
                known[(target.rule_id, location)] = None
    return collected


def _survey_targets_from_hits(hits: Sequence[SurveyHit], rules_by_id: dict[str, dict],
                              inspection: DocumentInspection, existing_targets: Sequence[Target],
                              *, start_index: int,
                              override_rules: frozenset[str] = frozenset()
                              ) -> tuple[list[Target], list[dict[str, Any]]]:
    """Turn deterministic survey hits into source-bound targets and coverage gaps.

    A hit whose reference runs across paragraphs becomes ONE target that lists every
    paragraph in ``composite`` ("location:start:end" per part); the planner edits each
    paragraph separately and keeps the rest of each paragraph verbatim (FL-D047).
    Hits whose text no longer resolves are reported as coverage gaps instead of being
    silently dropped.

    ``override_rules`` names rules whose existing targets must not suppress a new hit —
    the append pass uses it so an inventory judgment of "absent" cannot mask the clause
    the pass just located (FL-D090).
    """
    known = known_operations_from_targets(existing_targets, rules_by_id, inspection)
    targets: list[Target] = []
    gaps: list[dict[str, Any]] = []
    counter = start_index
    for hit in hits:
        if hit.operation == "satisfied":
            continue
        if hit.rule_id not in override_rules and operations_cover_hit(
                known, hit.rule_id, hit.locations, hit.operation_keys):
            continue
        counter += 1
        target_id = f"Y{counter:03d}"
        reason = f"survey_reference:{hit.ratio:.2f}"
        location, start, end = hit.parts[0]
        parts = tuple(f"{part_location}:{part_start}:{part_end}"
                      for part_location, part_start, part_end in hit.parts)
        try:
            span = inspection.by_location(location)
        except DocxError:
            gaps.append({"code": "SURVEY_LOCATION_MISSING", "rule_id": hit.rule_id,
                         "location": location, "quote": _clip(hit.quote, 80)})
            continue
        located = (start, end) if len(hit.parts) > 1 else resolve_quote(span, hit.quote)
        if located is None:
            gaps.append({"code": "SURVEY_QUOTE_UNRESOLVED", "rule_id": hit.rule_id,
                         "location": location, "quote": _clip(hit.quote, 80)})
            continue
        target = Target(target_id=target_id, rule_id=hit.rule_id, location=location,
                        quote=hit.quote, state="needs_edit", reason=reason,
                        operations=hit.operation_keys)
        target.start, target.end = located
        if len(hit.parts) > 1:
            target.composite = parts
            target.resolution = "composite"
        else:
            target.segment_ok = containing_segment(span, *located) is not None
            target.resolution = "resolved"
        targets.append(target)
        if hit.operation_keys:
            for part_location in hit.locations:
                _add_operation_coverage(known, hit.rule_id, part_location, hit.operation_keys)
        else:
            for part_location in hit.locations:
                known[(hit.rule_id, part_location)] = None
    return targets, gaps


def _operation_fingerprints(reference: str) -> list[str]:
    """Progressively simpler forms of a reference text, longest first.

    A contract may reword a clause mid-sentence ("…按月支付。由基金管理人…" against
    "…按月支付，由基金管理人与基金托管人核对一致后…"); the leading fragments still
    identify the clause, so rebinding tries the full text and then its leading
    sentences and clauses (FL-D047).
    """
    compact = _compact(reference)
    candidates: list[str] = [compact]
    # G14 contracts often repeat the noun before each fee item
    # ("基金申购费率、基金赎回费率和转换费率").  The repeated noun does not change
    # the policy, but an exact document search needs the expanded form.
    expanded = _expand_fee_rate_reference(compact)
    if expanded != compact and expanded not in candidates:
        candidates.append(expanded)
    for separator in ("。", "；", "，", "、"):  # noqa: B007 - ordered by strength
        head, _, _tail = compact.partition(separator)
        if 4 <= len(head) < len(compact) and head not in candidates:
            candidates.append(head)
    return candidates


def _target_locations(target: Target) -> list[str]:
    """Every paragraph this target touches (composite parts included)."""
    if target.composite:
        return [part.rsplit(":", 2)[0] for part in target.composite]
    return [target.location]


# ---------------------------------------------------------------------------
# Rule scope gate (plan/audit)
# ---------------------------------------------------------------------------

SCOPE_DROP_CODE = "OUT_OF_RULE_SCOPE"
# Rules whose guide policy names one fee clause. A compact contract may carry the
# whole 基金费用与税收 chapter as one leaf with no numbered subheading; there the
# mapped section's single leaf IS the physical site, and the widest accepted
# fallback stays the mapped section (never the document). The leaf text must still
# carry the rule's business anchor.
_FEE_SCOPE_RULES = frozenset({"G15", "G16", "G17"})


def _apply_single_leaf_fee_fallback(scopes: dict[str, Any], sections: Sequence[Any],
                                    inspection: DocumentInspection,
                                    mapping: Mapping[str, Sequence[str]]) -> dict[str, Any]:
    """Give G15-G17 their mapped section's sole fee leaf when no subheading exists.

    ``rule_scope._resolve_fee_tax`` resolves only a leaf whose title names
    销售服务费.  A compact contract with no subsection headings would otherwise be
    unresolved for every fee rule even though its single mapped leaf contains the
    clause.  The widening stays bounded to that one leaf and requires the business
    anchor in its own text, so sibling clauses of a structured chapter can never be
    admitted.
    """
    pending = [rule_id for rule_id, scope in scopes.items()
               if rule_id in _FEE_SCOPE_RULES
               and getattr(scope, "resolution", "") == "unresolved"
               and not getattr(scope, "locations", ())]
    if not pending:
        return scopes
    leaves = build_leaf_sections(inspection, sections)
    span_map = {str(getattr(span, "location", "")): span
                for span in getattr(inspection, "paragraphs", ())}
    for rule_id in pending:
        mapped = {str(section_id) for section_id in (mapping.get(rule_id) or ())}
        body_leaves = [leaf for leaf in leaves
                       if leaf.parent_section_id in mapped and leaf.zone == "body"]
        if len(body_leaves) != 1:
            continue
        leaf = body_leaves[0]
        text = "".join(_compact(str(getattr(span_map[location], "text", "")))
                       for location in leaf.locations if location in span_map)
        if "销售服务费" not in text:
            continue
        scopes[rule_id] = RuleScope(
            rule_id=rule_id, leaf_ids=frozenset({leaf.id}),
            locations=frozenset(leaf.locations), zone="body",
            include_summary_copies=False, copy_keys=frozenset({"销售服务费"}),
            resolution="section_fallback",
            evidence=(*scopes[rule_id].evidence, "fallback=single_leaf_mapped_fee_section",
                      f"leaf={leaf.id}:{leaf.title[:36]}"))
    return scopes


def _scope_audit_ledger(scopes: Mapping[str, Any]) -> dict[str, Any]:
    """Report projection of every resolved rule scope, for business review."""
    resolved = {str(rule_id): scope for rule_id, scope in (scopes or {}).items()}
    return {
        "rules": [scope.as_dict() for scope in resolved.values()],
        "unresolved_rules": sorted(rule_id for rule_id, scope in resolved.items()
                                   if scope.resolution == "unresolved"
                                   or not scope.locations),
        "dropped": [],
        "dropped_counts": {},
    }


def _record_scope_drop(audit: dict[str, Any] | None, *, stage: str, rule_id: str,
                       location: str, reason: str = SCOPE_DROP_CODE) -> None:
    """Record one out-of-scope candidate without letting the sample list grow unbounded."""
    if audit is None:
        return
    counts = audit.setdefault("dropped_counts", {})
    key = f"{stage}:{reason}:{rule_id}"
    seen = int(counts.get(key, 0))
    counts[key] = seen + 1
    if seen < 50:
        audit.setdefault("dropped", []).append(
            {"stage": stage, "code": reason, "rule_id": rule_id, "location": location})


def _scope_id_for(target: Target, scope: Any) -> str:
    leaves = "+".join(sorted(getattr(scope, "leaf_ids", ()) or ()))
    return f"{target.rule_id}:{leaves}" if leaves else f"{target.rule_id}@{target.location}"


def _target_scope_ok(target: Target, scopes: Mapping[str, Any] | None
                     ) -> tuple[bool, Any]:
    """Whether every physical location of ``target`` is inside its rule's scope."""
    if scopes is None:
        return True, None
    scope = scopes.get(str(target.rule_id))
    if scope is None or getattr(scope, "resolution", "") == "unresolved":
        return False, scope
    locations = _target_locations(target)
    if not locations or not getattr(scope, "locations", ()):
        return False, scope
    return all(scope.contains(location) for location in locations), scope


def _apply_scope_gate(targets: Sequence[Target], scopes: Mapping[str, Any] | None,
                      audit: dict[str, Any] | None = None, *, stage: str = "plan"
                      ) -> list[Target]:
    """Mark every target outside its rule's physical scope and stamp the scope id.

    An out-of-scope target is never handed to the planner or the audit; it keeps its
    ledger row (``out_of_scope`` + reason) so the drop is visible instead of silent.
    """
    if scopes is None:
        return list(targets)
    for target in targets:
        ok, scope = _target_scope_ok(target, scopes)
        if not ok:
            if not target.out_of_scope:
                target.out_of_scope = True
                target.reason = f"{target.reason}|RECALL_TARGET_OUT_OF_SCOPE"
                _record_scope_drop(audit, stage=stage, rule_id=str(target.rule_id),
                                   location=target.location)
            continue
        if not target.scope_id:
            target.scope_id = _scope_id_for(target, scope)
    return list(targets)


def _composite_parts_gone(target: Target, original: DocumentInspection,
                          actual: DocumentInspection) -> bool:
    """True when every deleted composite slice is absent from its own paragraph.

    A composite deletion removes one slice per paragraph. The old deletion evidence
    only looked at ``target.location`` (the first paragraph), so deleting part one and
    leaving part two could be accepted as complete (FL-D110). Each part is checked
    against the original slice it was supposed to remove.
    """
    if not target.composite:
        return False
    for part in target.composite:
        try:
            location, start_text, end_text = part.rsplit(":", 2)
            start_clean, end_clean = int(start_text), int(end_text)
        except (ValueError, AttributeError):
            return False
        try:
            before = original.by_location(location)
            after = actual.by_location(location)
        except DocxError:
            return False
        compact_before, _map = compact_offsets(before.text)
        if start_clean < 0 or end_clean > len(compact_before) or start_clean >= end_clean:
            return False
        deleted = _compact(compact_before[start_clean:end_clean])
        if not deleted:
            return False
        after_clean, _ = display_text(after.text)
        if deleted in _compact(after_clean):
            return False
    return True




def _run_survey(model: Any, rules: Sequence[dict], rules_by_id: dict[str, dict], facts: Facts,
                inspection: DocumentInspection, targets: Sequence[Target],
                synthetic: list[Target], origins: dict[str, str], ledger: list[dict[str, Any]],
                gaps: list[dict[str, Any]],
                sections: Sequence[Section] = (), *,
                mapping: Mapping[str, Sequence[str]] | None = None,
                scopes: Mapping[str, Any] | None = None) -> list[SurveyHit]:
    """Code-driven coverage pass: find rule targets the model inventory never reported."""
    # RuleScope is the single source of truth for "where may this rule look".  The
    # section-level projection remains only as a compatibility fallback for callers
    # that do not have a resolved scope set yet.
    allowed_locations = (scope_locations(scopes) if scopes is not None
                         else (rule_scope_locations(sections, mapping)
                               if mapping is not None else None))
    known = known_operations_from_targets([*targets, *synthetic], rules_by_id, inspection)
    # A delete rule the inventory judged "absent" or left unresolved is exactly the
    # not-applicable call this pass exists to correct: the model recorded a target at the
    # location the reference text still occupies, so that (rule, location) pair would
    # suppress the hit and the deletion is dropped (D04/D08/D17/D19/D20, FL-D101). Rules
    # that already have a resolved needs_edit target keep their coverage.
    resolved_needs_edit = {target.rule_id for target in [*targets, *synthetic]
                           if target.state == "needs_edit" and target.resolution == "resolved"}
    delete_rules = {str(rule.get("rule_id") or "") for rule in rules
                    if is_delete_only_rule(rule, facts)}
    # A resolved delete target at one location must not suppress the survey at a
    # different copy of the same clause (D01 p758 vs p1221). Coverage is tracked per
    # (rule, location) by ``known``, so every delete rule may override here.
    override_rules = frozenset(delete_rules)
    hits = survey_targets(inspection, rules, facts, known=known, override_rules=override_rules,
                          allowed_locations=allowed_locations)
    # Append rules have no reference anchor, so the survey above cannot see them.
    # Add the deterministic append pass so a conditional append the model inventory
    # wrongly called not_applicable still gets an executable target (FL-D060/090).
    # It is gated on targets that will actually be edited and could bind to real text
    # (needs_edit with a resolved quote): an inventory judgment of "absent" — or a
    # needs_edit target whose model quote never resolved — is exactly the not-applicable
    # call this pass exists to override, so neither may count as coverage here.
    editable_known = [(target.rule_id, location)
                      for target in [*targets, *synthetic]
                      if target.state == "needs_edit" and target.resolution == "resolved"
                      for location in _target_locations(target)]
    # The inventory's own "absent" or unresolved targets name the clause each rule belongs
    # to; reuse that location as the append anchor instead of guessing the section end.
    hinted: dict[str, str] = {}
    for target in [*targets, *synthetic]:
        if target.state == "needs_edit":
            continue
        if target.location and target.rule_id not in hinted:
            hinted[target.rule_id] = target.location
    append_hits = append_applicability_targets(
        inspection, rules, facts, sections, known=editable_known, hinted=hinted,
        allowed_locations=allowed_locations)
    hits.extend(append_hits)
    satisfied = [hit for hit in hits if hit.operation == "satisfied"]
    for hit in satisfied:
        # ``SurveyHit.quote`` is a matched excerpt in compact/display text.  A
        # satisfied target still needs the same source binding as an editable
        # target: Claim Replay proves an unchanged policy at this physical site,
        # never at an arbitrary paragraph carrying the operation key.  Keep the
        # target out of coverage when the excerpt cannot be resolved.
        hit_parts = hit.parts
        location = hit_parts[0][0] if hit_parts else hit.locations[0]
        try:
            span = inspection.by_location(location)
        except DocxError:
            gaps.append({"code": "SURVEY_LOCATION_MISSING", "rule_id": hit.rule_id,
                         "location": location, "quote": _clip(hit.quote, 80)})
            continue
        located = resolve_source_quote(span, hit.quote)
        if located is None and hit.operation == "satisfied":
            # The semantic survey may return a short policy excerpt (for example
            # the first 12 characters around a fee marker), while source proof
            # must use a complete physical sentence.  Expand that unique excerpt
            # to its sentence boundaries here; resolve_source_quote itself stays
            # strict and continues to reject sentence prefixes.
            excerpt = resolve_quote(span, hit.quote)
            if excerpt is not None:
                normalize = lambda value: re.sub(r"[\s\u200b\ufeff]+", "", value)
                needle = normalize(hit.quote)
                body = normalize(str(span.text))
                first = body.find(needle) if needle else -1
                if (first < 0 or body.find(needle, first + 1) >= 0
                        or normalize(str(span.text)[excerpt[0]:excerpt[1]]) != needle):
                    excerpt = None
            if excerpt is not None:
                start, end = excerpt
                text = str(span.text)
                while start > 0 and text[start - 1] not in "。；;！？!?":
                    start -= 1
                terminal = re.search(r"[。；;！？!?]", text[end:])
                end = end + terminal.end() if terminal else len(text)
                candidate = text[start:end]
                located = resolve_source_quote(span, candidate)
        if located is None and hit.operation == "satisfied":
            # Class-substitution survey proofs are often intentionally concise
            # (for example ``F类基金份额``), while the same class label can occur
            # several times in one paragraph.  The short proof is still useful
            # because ``satisfied_by_new_text`` already established that the
            # complete replacement policy is present.  Bind the whole physical
            # paragraph as the smallest unambiguous source site instead of
            # turning an already satisfied policy into a blocking orphan gap.
            paragraph_quote = str(span.text or "")
            if (hit.rule_id in {"G02", "G04"}
                    and paragraph_quote.strip()
                    and resolve_source_quote(span, paragraph_quote) is not None):
                located = (0, len(paragraph_quote))
        if located is None:
            gaps.append({"code": "SURVEY_QUOTE_UNRESOLVED", "rule_id": hit.rule_id,
                         "location": location, "quote": _clip(hit.quote, 80)})
            continue
        target_id = f"Y{len(synthetic) + len(hits) + 1:03d}"
        target = Target(target_id=target_id, rule_id=hit.rule_id, location=location,
                        quote=span.text[located[0]:located[1]], state="satisfied", reason="survey_new_text_present",
                        start=located[0], end=located[1], resolution="resolved",
                        segment_ok=containing_segment(span, *located) is not None,
                        operations=hit.operation_keys)
        synthetic.append(target)
        origins[target_id] = "survey_satisfied"
    discovered, new_gaps = _survey_targets_from_hits(
        hits, rules_by_id, inspection, [*targets, *synthetic], start_index=len(synthetic),
        override_rules=frozenset(hit.rule_id for hit in append_hits) | override_rules)
    synthetic.extend(discovered)
    for target in discovered:
        origins[target.target_id] = "survey"
    gaps.extend(new_gaps)
    ledger.append({
        "round": "survey", "hits": len(hits), "discovered": len(discovered),
        "satisfied": len(satisfied), "gaps": new_gaps,
        "records": [{"rule_id": hit.rule_id, "operation": hit.operation,
                     "locations": list(hit.locations), "ratio": hit.ratio,
                     "quote": _clip(hit.quote, 120)} for hit in hits],
    })
    return hits




_SPLIT_CLAUSE_TERMINATORS = "。；！？!?;."


def _adjacent_paragraphs(inspection: DocumentInspection, location: str):
    paragraphs = inspection.paragraphs
    for index, span in enumerate(paragraphs):
        if span.location == location:
            return (paragraphs[index - 1] if index > 0 else None,
                    paragraphs[index + 1] if index + 1 < len(paragraphs) else None)
    return (None, None)


def _trim_split_quote_prefix(target: Target, current,
                             inspection: DocumentInspection) -> dict[str, Any] | None:
    """Trim the half of a quote that lives in the preceding split paragraph.

    The inventory may reconstruct ``在投资`` + ``者申购…`` as one quote while
    placing it on the second paragraph.  The strict resolver then fails because
    the reconstructed prefix is not in that physical paragraph.  Keep only the
    remainder that is actually at the start of the current paragraph, require it
    to be unique and to resolve to a complete boundary there, and leave the
    paragraph location unchanged.  The preceding paragraph must itself be an
    unterminated split, same zone and section.
    """
    previous, _following = _adjacent_paragraphs(inspection, target.location)
    if previous is None or previous.zone != current.zone:
        return None
    if previous.section_path != current.section_path:
        return None
    previous_text = str(previous.text)
    if previous_text.rstrip().endswith(tuple(_SPLIT_CLAUSE_TERMINATORS)):
        return None
    quote = compact_offsets(target.quote)[0]
    previous_compact = compact_offsets(previous_text)[0]
    current_compact, current_positions = compact_offsets(str(current.text))
    if not quote or not previous_compact or not current_compact:
        return None
    for cut in range(1, len(quote)):
        prefix, remainder = quote[:cut], quote[cut:]
        if len(remainder) < 8:
            break
        if not previous_compact.endswith(prefix):
            continue
        if not current_compact.startswith(remainder):
            continue
        if current_compact.count(remainder) != 1:
            continue
        start = current_positions[0]
        end = current_positions[len(remainder) - 1] + 1
        candidate = str(current.text)[start:end]
        bound = resolve_source_quote(current, candidate)
        if bound is None:
            continue
        target.quote = candidate
        target.start, target.end = bound
        target.segment_ok = containing_segment(current, *bound) is not None
        target.resolution = "resolved"
        target.reason = f"{target.reason}|rebind:split_quote_prefix"
        return {"location": current.location, "start": bound[0], "end": bound[1]}
    return None


def _rebind_split_satisfied_target(target: Target, inspection: DocumentInspection
                                   ) -> dict[str, Any] | None:
    """Bind a satisfied quote that the inventory placed on the wrong side of a split.

    D04 G04 reports ``A 类基金份额`` at the paragraph that ends mid-sentence
    (``在投资``); the definition continues in the next paragraph. The target is
    satisfied (no edit), but its audit evidence cannot be verified because the
    quote is not in that physical paragraph. Rebind only when the current
    paragraph is an unterminated split and the quote occurs exactly once in
    exactly one adjacent paragraph of the same zone and section. Never search
    further, never pick the first of several occurrences, and never alter a
    needs_edit target's write site.
    """
    if (target.state != "satisfied" or target.resolution != "quote_not_found"
            or not target.quote):
        return None
    try:
        current = inspection.by_location(target.location)
    except (KeyError, DocxError):
        return None
    text = str(current.text)
    if not text.strip() or text.rstrip().endswith(tuple(_SPLIT_CLAUSE_TERMINATORS)):
        return None
    previous, following = _adjacent_paragraphs(inspection, target.location)
    candidates = []
    for span in (previous, following):
        if span is None or span.zone != current.zone:
            continue
        if span.section_path != current.section_path:
            continue
        compact_text = compact_offsets(str(span.text))[0]
        compact_quote = compact_offsets(target.quote)[0]
        if not compact_quote or compact_text.count(compact_quote) != 1:
            continue
        located = resolve_quote(span, target.quote)
        if located is None:
            continue
        candidates.append((span, located))
    if len(candidates) != 1:
        return None
    span, (start, end) = candidates[0]
    target.location = span.location
    target.start, target.end = start, end
    target.segment_ok = containing_segment(span, start, end) is not None
    target.resolution = "resolved"
    target.reason = f"{target.reason}|rebind:split_paragraph"
    return {"location": span.location, "start": start, "end": end}


def _rebind_unresolved_targets(targets: Sequence[Target], origins: dict[str, str],
                               inspection: DocumentInspection, *, rules_by_id: dict[str, dict],
                               facts: Facts, extend_resolved: bool = False) -> list[dict[str, Any]]:
    """Re-bind inventory targets whose model quote never resolved (FL-D052).

    The windowed inventory resolves a quote against ONE paragraph, so a faithful quote
    that runs across two paragraphs (the sales-service-fee payment clause: "…按月支付，"
    ends p806 while its continuation opens p807) is recorded as ``quote_not_found`` and
    the planner then stops with ``RECALL_TARGET_UNRESOLVED`` — even though the clause is
    present verbatim. The same deterministic resolver the sweep uses is applied here:
    the target's own quote is matched document-wide (cross-paragraph included), and the
    rule's operation reference text is tried through progressively simpler fingerprints.
    A target is only re-bound to real document text; anything else stays unresolved and
    is recorded with the reason.

    With ``extend_resolved`` the pass also revisits targets the inventory already bound to
    a single paragraph: when an applicable delete/replace reference covers a longer,
    cross-paragraph stretch of the same clause, the fuller binding replaces the fragment
    (the inventory's "…按月支付，" head cannot satisfy a deletion that continues into the
    next paragraph).
    """
    paragraphs = [span for span in inspection.paragraphs if span.text.strip()]
    records: list[dict[str, Any]] = []
    for target in targets:
        if target.state == "satisfied" and target.resolution == "quote_not_found":
            split = _rebind_split_satisfied_target(target, inspection)
            if split is None:
                try:
                    current = inspection.by_location(target.location)
                except (KeyError, DocxError):
                    current = None
                if current is not None:
                    split = _trim_split_quote_prefix(target, current, inspection)
            if split is not None:
                origins[target.target_id] = "rebind_split_paragraph"
                records.append({"target_id": target.target_id, "rule_id": target.rule_id,
                                "source": "split_paragraph", **split})
            continue
        if target.state != "needs_edit":
            continue
        if target.resolution == "composite":
            continue
        if getattr(target, "site_candidates", ()):
            # Open-obligation targets are bound only by the anchored locator; the generic
            # operation-reference rebind has no anchor/candidate verification.
            continue
        if target.resolution == "resolved" and not extend_resolved:
            continue
        if target.resolution not in {"resolved", "unresolved", "quote_not_found"}:
            continue
        rule = rules_by_id.get(target.rule_id)
        if rule is None:
            continue
        current_cover = 0
        if target.resolution == "resolved" and target.start is not None and target.end is not None:
            current_cover = target.end - target.start
        order: list[tuple[str, str]] = []
        if _compact(target.quote):
            order.append(("target_quote", target.quote))
        for operation in rule.get("operations") or []:
            if operation.get("op") not in {"delete", "replace"}:
                continue
            if not condition_matches(operation.get("condition"), facts):
                continue
            reference = str(operation.get("old_text") or "")
            if len(_compact(reference)) < 8:
                continue
            for fingerprint in _operation_fingerprints(reference):
                order.append(("operation_reference", fingerprint))
        # Every candidate that matches this location is considered; the binding that
        # covers the most document text wins. The inventory often quotes only the head
        # of a clause ("…按月支付，") while the rule's deletion spans its continuation in
        # the next paragraph ("由基金管理人与基金托管人核对一致后…支付日期顺延。"); taking
        # the first match left the target bound to a fragment no operation could satisfy
        # (FL-D052).
        best: tuple[int, str, list[tuple[str, int, int]], bool] | None = None
        for source, needle in order:
            for parts in find_old_text_all(paragraphs, needle):
                locations = [item[0] for item in parts]
                if target.location not in locations:
                    continue
                resized = list(parts)
                if len(parts) == 1:
                    span = inspection.by_location(parts[0][0])
                    located = resolve_quote(span, needle)
                    if located is None:
                        continue
                    resized = [(parts[0][0], located[0], located[1])]
                covered = sum(end - start for _location, start, end in resized)
                if covered <= current_cover:
                    continue
                if target.resolution == "resolved" and not len(parts) > 1:
                    # An already-resolved single-paragraph binding is authoritative: only a
                    # binding that spans paragraphs (the clause continues in the next one)
                    # may replace it (FL-D052).
                    continue
                if best is None or covered > best[0]:
                    best = (covered, source, resized, len(parts) > 1)
        if best is None and target.resolution == "resolved":
            best = _clause_continuation_binding(target, rule, inspection)
        if best is not None:
            _covered, source, parts, split = best
            if split:
                target.composite = tuple(f"{location}:{start}:{end}"
                                         for location, start, end in parts)
                target.resolution = "composite"
            else:
                span = inspection.by_location(parts[0][0])
                target.start, target.end = parts[0][1], parts[0][2]
                target.segment_ok = containing_segment(span, target.start, target.end) is not None
                target.resolution = "resolved"
            target.reason = f"{target.reason}|rebind:{source}"
            origins[target.target_id] = f"rebind_{source}"
            records.append({"target_id": target.target_id, "rule_id": target.rule_id,
                            "source": source, "parts": list(target.composite) or
                            [f"{target.location}:{target.start}:{target.end}"]})
        elif target.resolution == "resolved":
            records.append({"target_id": target.target_id, "rule_id": target.rule_id,
                            "source": "target_quote",
                            "parts": [f"{target.location}:{target.start}:{target.end}"]})
        else:
            records.append({"target_id": target.target_id, "rule_id": target.rule_id,
                            "source": "none", "reason": "RECALL_TARGET_REBIND_FAILED"})
    return records


_CLAUSE_TERMINATORS = "。；！？!?;."


def _clause_continuation_binding(target: Target, rule: dict, inspection: DocumentInspection
                                 ) -> tuple[int, str, list[tuple[str, int, int]], bool] | None:
    """A delete/replace clause the inventory bound to the first of two paragraphs.

    The contract splits one sales-service-fee clause across two docx paragraphs: the first
    ends with a comma ("…按月支付，") and the second continues it ("由基金管理人与基金托管
    人核对一致后…支付日期顺延。"). The guide's own wording differs, so no reference text
    matches, and the inventory binds only the first paragraph — a fragment no deletion can
    satisfy. When the target covers its WHOLE paragraph (offset 0 to the end), the paragraph
    ends with a comma, and the rule removes material rather than appending, the following
    paragraph is the clause's continuation (FL-D052).
    """
    if target.start != 0 or target.end is None:
        return None
    if any(operation.get("op") == "append" for operation in (rule.get("operations") or [])):
        return None
    if not any(operation.get("op") in {"delete", "replace"}
               for operation in (rule.get("operations") or [])):
        return None
    paragraphs = [span for span in inspection.paragraphs if span.text.strip()]
    index = next((position for position, span in enumerate(paragraphs)
                  if span.location == target.location), None)
    if index is None or index + 1 >= len(paragraphs):
        return None
    span = paragraphs[index]
    compact_body, _map = compact_offsets(span.text)
    if target.end < len(compact_body):
        return None
    if span.text.rstrip()[-1:] in _CLAUSE_TERMINATORS:
        return None
    follower = paragraphs[index + 1]
    if not follower.text.strip():
        return None
    if not source_parts_contiguous(inspection, [span.location, follower.location]):
        return None
    follower_compact, _fmap = compact_offsets(follower.text)
    parts = [(span.location, 0, len(compact_body)),
             (follower.location, 0, len(follower_compact))]
    covered = sum(end - start for _location, start, end in parts)
    return (covered, "clause_continuation", parts, True)


def _make_synthetic_target(target_id: str, rule_id: str, location: str, quote: str, reason: str,
                           inspection: DocumentInspection) -> Target | None:
    """Turn a verified audit/sweep quote into a source-bound target (or None)."""
    try:
        span = inspection.by_location(location)
    except DocxError:
        return None
    located = resolve_quote(span, quote)
    if located is None:
        return None
    target = Target(target_id=target_id, rule_id=rule_id, location=location, quote=quote,
                    state="needs_edit", reason=reason)
    target.start, target.end = located
    target.segment_ok = containing_segment(span, *located) is not None
    target.resolution = "resolved"
    return target


# ---------------------------------------------------------------------------
# Planning, writing and inspection
# ---------------------------------------------------------------------------

def _plan_and_generate(model: Any, rules_by_id: dict[str, dict], targets: Sequence[Target],
                       inspection: DocumentInspection, facts: Facts, input_path: Path,
                       temp_dir: Path, *, max_compose_calls: int,
                       obligations: Any = None, existing_plan: dict | None = None,
                       dirty_locations: set[str] | None = None,
                       frozen_run: Any = None,
                       scopes: Mapping[str, Any] | None = None,
                       scope_audit: dict[str, Any] | None = None
                       ) -> tuple[dict[str, Any], list[dict[str, Any]], Any, Any, DocumentInspection]:
    """Plan from the ORIGINAL inspection, validate, generate and re-read the final."""
    from .recall import (append_site_ok, duplicate_copy_targets,
                         ensure_unique_target_ids, target_site_ok,
                         rebind_g16_clause_targets, rebind_split_append_targets,
                         guard_g17_deletes_against_g16,
                         g15_delay_continuation_targets)
    # Final scope gate: no target outside its rule's physical scope may reach the
    # planner.  Out-of-scope targets keep a ledger row but are never planned.
    _apply_scope_gate(targets, scopes, scope_audit, stage="plan")
    # Final exact-copy closure immediately before planning. Survey/rebind can add a
    # source target after the earlier passes; an uneditable body/summary copy must not
    # survive merely because of that ordering (D01 p758/p1221 G15). G16 must first be
    # bound to its clause end, otherwise an identical payment head can borrow the
    # operation from a different physical clause (D20 p804/p806 vs p1259).
    rebind_g16_clause_targets(targets, inspection)
    for copy in duplicate_copy_targets(targets, rules_by_id, inspection,
                                       scopes=scopes):
        for old in targets:
            if old is not copy and old.rule_id == copy.rule_id \
                    and old.location == copy.location \
                    and set(old.operations) == set(copy.operations):
                old.out_of_scope = True
                old.reason = f"{old.reason}|SUPERSEDED_BY_FINAL_COPY"
        targets.append(copy)
    targets.extend(g15_delay_continuation_targets(targets, rules_by_id, inspection))
    ensure_unique_target_ids(targets)
    rebind_split_append_targets(targets, inspection)
    # Build one code-verified approval per attributable target.  Every later stage
    # (site guard, planner, effect proof, Claim Replay) consumes this record, so a
    # rule-specific word list cannot reject a target whose source, operation
    # identity, guide version and physical scope were already verified.  A raw
    # inventory claim never becomes an approval by itself (R01-R03).
    from .recall import approval_book_for
    approvals = approval_book_for(rules_by_id, targets, inspection)
    if scope_audit is not None:
        scope_audit["approvals"] = {"count": len(approvals),
                                    "ids": [item.approval_id for item in approvals.values()]}
    for target in targets:
        if (target.state == "needs_edit" and not target.out_of_scope
                and target.resolution in {"resolved", "composite"}):
            # Composite quotes still need the rule-specific business-site guard.
            # Structural cross-paragraph resolution alone must not turn a sibling
            # clause into a valid target (for example G06 versus generic business
            # rule text); G16/G17 fee composites pass their own anchors.
            try:
                span = inspection.by_location(target.location)
            except DocxError:
                continue
            if target.composite:
                # Use only the bound source slices, including an anchor split
                # across paragraphs, rather than borrowing a neighbour's clause.
                from types import SimpleNamespace
                pieces = []
                try:
                    for part in target.composite:
                        location, start, end = part.rsplit(":", 2)
                        body, _ = compact_offsets(inspection.by_location(location).text)
                        pieces.append(body[int(start):int(end)])
                except (ValueError, DocxError):
                    continue  # The planner retains its structural failure diagnosis.
                span = SimpleNamespace(location=target.location, text="".join(pieces))
            rule = rules_by_id.get(target.rule_id) or {}
            append_rule = any(operation.get("op") == "append"
                              for operation in rule.get("operations") or ())
            # Append rules resolve their anchor through append_site_ok (which also
            # understands a G16 clause-end site and split definitions); the plain
            # target-site guard would mark the resolved target out of scope before
            # the planner can use it.
            site_ok = (append_site_ok(target.rule_id, span, inspection)
                       if append_rule
                       else target_site_ok(target.rule_id, span, inspection))
            if (not site_ok and target.rule_id == "G16"
                    and target.state == "needs_edit"
                    and "G16_PARTIAL_CLAUSE" in str(target.reason or "")):
                # A partial G16 tail is intentionally not an append anchor; the
                # planner replaces that tail with the complete instantiated clause.
                # Keep it actionable instead of marking it target-source mismatch.
                site_ok = True
            if not site_ok:
                check = approvals.allows(target, inspection)
                if check.ok:
                    # The model's site selection was already verified against the
                    # real quote, the operation identity and the physical scope.
                    # A different keyword bag is a recall fast path, not a second
                    # semantic trial (弘利 G17 "可用于", FL-D394/R01).
                    site_ok = True
                    target.reason = f"{target.reason}|SITE_GUARD_WAIVED_BY_APPROVAL"
            if not site_ok:
                target.out_of_scope = True
                target.reason = f"{target.reason}|TARGET_SOURCE_MISMATCH"
    # Locators and split-definition recovery run after the early dedupe passes.
    # Reconcile their final source bindings before they become plan/replay claims.
    dedupe_operation_targets(targets, rules_by_id, inspection)
    # Recovery passes above may append targets (delay continuations, copies); re-run
    # the scope gate immediately before planning so none of them can widen the scope.
    _apply_scope_gate(targets, scopes, scope_audit, stage="plan")
    if existing_plan is None or dirty_locations:
        if frozen_run is not None:
            frozen_run.boundary("plan", {"targets": [target.as_dict() for target in targets],
                "facts": facts.as_ledger(), "max_context_chars": model.max_context_chars,
                "max_compose_calls": max_compose_calls,
                "existing_plan": existing_plan, "dirty_locations": sorted(dirty_locations or [])})
        if existing_plan is not None and dirty_locations:
            from .recall import replan_sites
            planned = replan_sites(existing_plan, dirty_locations, rules_by_id, targets, inspection,
                facts, model, max_compose_calls=max_compose_calls, obligations=obligations)
            # A recovery replan can leave a retained edit unbound after target
            # aliases/state were reconciled.  If a live target still owns that
            # operation, falling back to a full plan is safer than silently dropping
            # a real body/summary occurrence (D01 p758 G15/G16).
            unbound = [entry for entry in planned.get("ledger") or []
                       if entry.get("reason") == "RECALL_PLAN_REFERENCE_UNBOUND"]
            if unbound:
                live_target = any(
                    not target.out_of_scope and target.state in {"needs_edit", "satisfied"}
                    and (target.location == str(entry.get("location") or "")
                         or set(target.operations) & set(entry.get("operation_keys") or ()))
                    for entry in unbound for target in targets)
                if live_target:
                    planned = plan_edits(
                        rules_by_id, targets, inspection, facts, model,
                        max_compose_calls=max_compose_calls, obligations=obligations,
                        reuse_edits=existing_plan.get("edits") or (),
                        approvals=approvals)
        else:
            planned = plan_edits(rules_by_id, targets, inspection, facts, model,
                                 max_compose_calls=max_compose_calls,
                                 obligations=obligations, approvals=approvals)
    else:
        from copy import deepcopy
        planned = deepcopy(existing_plan)
    g17_blocks = guard_g17_deletes_against_g16(planned, targets, inspection)
    if g17_blocks:
        planned.setdefault("business_notices", []).extend(g17_blocks)
    edits = build_docx_edits(planned["edits"], inspection)
    content_check = content_check_factory(planned["edits"], inspection)
    # A generated edit whose content record does not bind the source must not be
    # published. Drop just that edit and keep the target unresolved, the same way an
    # unexecutable edit is handled below; failing the whole contract over one bad
    # component would discard otherwise valid edits (FL-D112).
    rejected = [edit for edit in edits if content_check(edit) is False]
    if rejected:
        rejected_keys = {(str(edit.get("target_id")), str(edit.get("location")),
                          int(edit.get("start", -1)), int(edit.get("end", -2)))
                         for edit in rejected}
        removed: set[str] = set()
        kept_records: list[dict[str, Any]] = []
        for record in planned["edits"]:
            key = (str(record.get("target_id")), str(record.get("location")),
                   int(record.get("start", -1)), int(record.get("end", -2)))
            if key in rejected_keys:
                removed.add(str(record.get("target_id")))
                removed.update(str(component.get("target_id"))
                               for component in record.get("components") or [])
                continue
            kept_records.append(record)
        planned["edits"] = kept_records
        edits = [edit for edit in edits if (
            str(edit.get("target_id")), str(edit.get("location")),
            int(edit.get("start", -1)), int(edit.get("end", -2))) not in rejected_keys]
        for entry in planned["ledger"]:
            if entry.get("target_id") in removed and entry.get("status") == "planned":
                entry["status"] = "unresolved"
                entry["reason"] = "RECALL_EDIT_CONTENT_UNVERIFIED"
    present = {str(edit.get("edit_id")) for edit in edits}
    not_executable: set[str] = set()
    for record in planned["edits"]:
        if f"{record['rule_id']}:{record['target_id']}" not in present:
            not_executable.update(str(record["target_id"]).split("+"))
    if not_executable:
        for entry in planned["ledger"]:
            if entry.get("target_id") in not_executable and entry.get("status") == "planned":
                entry["status"] = "unresolved"
                entry["reason"] = "RECALL_EDIT_NOT_EXECUTABLE"
        planned["edits"] = [record for record in planned["edits"]
                            if f"{record['rule_id']}:{record['target_id']}" in present]
    from .recall import _reconcile_final_plan_ledger
    _reconcile_final_plan_ledger(planned["ledger"], planned["edits"],
                                 planned.get("conflicts") or [], [], [])
    plan = validate_edit_plan(input_path, edits, {}, content_check=content_check,
                              allow_existing_revisions=True)
    redline, final = temp_dir / "redline.docx", temp_dir / "final.docx"
    if edits:
        artifacts = generate_artifacts(input_path, plan, redline, final,
                                       allow_existing_revisions=True)
    else:
        artifacts = generate_unchanged_artifacts(input_path, plan, redline, final)
    actual = inspect_docx(final, full=True)
    return planned, edits, plan, artifacts, actual


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

def _region_text(inspection: DocumentInspection, location: str, targets: Sequence[Target],
                 clip: int) -> str:
    try:
        span = inspection.by_location(location)
    except DocxError:
        return ""
    cleaned, _ = display_text(span.text)
    if len(cleaned) <= clip:
        return cleaned
    center = 0
    for target in targets:
        if target.location == location and target.start is not None:
            center = len(display_text(span.text[:target.start])[0])
            break
        if location in _target_locations(target) and target.start is not None:
            center = 0
            break
    start = max(0, min(center - clip // 4, len(cleaned) - clip))
    return "…" + cleaned[start:start + clip] + "…"


def _targets_by_rule(targets: Sequence[Target]) -> dict[str, list[Target]]:
    grouped: dict[str, list[Target]] = {}
    for target in targets:
        grouped.setdefault(target.rule_id, []).append(target)
    return grouped


def _audit_context(rule: dict, rule_targets: Sequence[Target], plan_by_target: dict[str, dict],
                    original: DocumentInspection, actual: DocumentInspection, *, limit: int,
                    other_edits: Sequence[dict[str, Any]] = (),
                    facts: Facts | None = None) -> tuple[str, str, str]:
    locations: list[str] = []
    for target in rule_targets:
        for location in _target_locations(target):
            if location not in locations:
                locations.append(location)
    ledger = []
    for target in rule_targets:
        plan_entry = plan_by_target.get(target.target_id) or {}
        ledger.append({
            "target_id": target.target_id, "rule_id": target.rule_id, "location": target.location,
            "state": target.state, "quote": target.quote, "reason": target.reason,
            "plan_status": plan_entry.get("status"), "operation": plan_entry.get("operation"),
            "replacement": _clip(str(plan_entry.get("replacement") or ""), 300),
        })
    requirements = rule_context([rule], full=True)
    applicable_policies = []
    if facts is not None:
        from .recall import instantiate_policy_text
        for index, operation in enumerate(rule.get("operations") or []):
            if not operation.get("new_text"):
                continue
            status = condition_status(operation.get("condition"), facts)
            policy, issues = instantiate_policy_text(str(rule.get("rule_id") or ""),
                                                      operation, facts)
            # A usable slot value is not itself proof of its fee group. Supply
            # unresolved facts explicitly instead of an apparently final policy.
            for token, fact_name in (("A类基金份额", "subscription_fee_group"),
                                     ("C类基金份额", "service_fee_group")):
                if token in str(operation["new_text"]):
                    for required in ("share_class_structure", fact_name):
                        if facts.status_of(required) != "VERIFIED":
                            issues.append(f"FACT_UNVERIFIED:{required}")
            applicable_policies.append({
                "operation_id": _declared_operation_key(str(rule.get("rule_id") or ""),
                                                         index, operation),
                "condition_status": status,
                "policy_status": ("NOT_APPLICABLE" if status == "FALSE" else
                                  "READY" if status == "TRUE" and not issues else "UNRESOLVED"),
                "applicable_new_text": policy if status == "TRUE" and not issues else "",
                "issues": sorted(set(issues)),
            })
    ledger_text = json.dumps(ledger, ensure_ascii=False, indent=1)
    facts_context = (["[FACTS]\n" + json.dumps(facts.as_ledger(), ensure_ascii=False, indent=1)]
                     if facts is not None else [])
    context = ""
    for clip in (1200, 800, 500, 300, 150):
        before_text = "\n".join(f"[{location}] {_region_text(original, location, rule_targets, clip)}"
                                for location in locations)
        after_text = "\n".join(f"[{location}] {_region_text(actual, location, rule_targets, clip)}"
                               for location in locations)
        before_display = "\n".join(
            f"[{location}] {_region_text(original, location, rule_targets, clip) or '（该位置无文本）'}"
            for location in locations)
        after_display = "\n".join(
            f"[{location}] {_region_text(actual, location, rule_targets, clip) or '（该位置内容已删除）'}"
            for location in locations)
        context = "\n\n".join(facts_context + [f"[BEFORE]\n{before_display}", f"[AFTER]\n{after_display}",
                                f"[REQUIREMENTS]\n{requirements}", f"[TARGET_LEDGER]\n{ledger_text}",
                                "[APPLICABLE_POLICIES]\n" + json.dumps(applicable_policies,
                                                                       ensure_ascii=False, indent=1),
                                "[OTHER_AUTHORIZED_EDITS]\n" + json.dumps(list(other_edits),
                                                                           ensure_ascii=False, indent=1)])
        if len(context) <= limit:
            return context, before_text, after_text
    raise RecallError("RECALL_AUDIT_CONTEXT_LIMIT",
                      {"rule": rule["rule_id"], "chars": len(context), "limit": limit})


def _review_concurrency(model: Any, rule_count: int) -> int:
    """Requested review concurrency bounded by the model budget's hard limit."""
    try:
        requested = int(os.environ.get("FUNDLEX_REVIEW_CONCURRENCY", "4"))
    except (TypeError, ValueError):
        requested = 4
    budget = getattr(model, "budget", None)
    if budget is None:
        budget_limit = requested
    else:
        try:
            budget_limit = int(getattr(budget, "concurrency", 1) or 1)
        except (TypeError, ValueError):
            budget_limit = 1
    return max(1, min(requested, budget_limit, max(1, rule_count)))


def _local_operation_proofs(proof: Any, operation_id: str, obligation_id: str,
                            location: str) -> list[dict[str, Any]]:
    """Select one operation's actual site; an aggregate PASS cannot lend a site."""
    if not isinstance(proof, dict) or proof.get("operation_id") != operation_id \
            or proof.get("obligation_id") != obligation_id:
        return []
    evidence = [item for item in proof.get("evidence") or []
                if str(item.get("location") or item.get("site_id") or "") == location
                and item.get("operation_id") == operation_id
                and item.get("obligation_id") == obligation_id]
    if not evidence:
        return []
    effects = proof.get("site_effects") or []
    local = [effect for effect in effects
             if str(effect.get("location") or effect.get("site_id") or "") == location]
    if local:
        return [{**proof, **effect, "sites": [effect.get("site_id") or location], "evidence": evidence,
                 "site_effects": [effect]} for effect in local]
    # Older fixtures have no per-site coordinates. Their aggregate proof is
    # usable only when it explicitly includes the requested site's evidence.
    if not any(effect.get("location") or effect.get("site_id") for effect in effects):
        return [proof]
    return []


def _quote_is_expected_effect(quote: str, record: Any, facts: Facts | None, *,
                              edits: Sequence[dict[str, Any]] = (), location: str,
                              before_text: str = "", actual_text: str = "",
                              target_id: str = "", obligations: Any = None,
                              proofs: dict[str, Any] | None = None) -> bool:
    """An exact quote of authorized new wording is not contradictory evidence.

    Only the quoted operation's instantiated policy or final component may
    authorize it. Unchanged source wording and sibling components cannot do so.
    The caller separately requires this operation/site's complete effect proof.
    """
    from .generation.effects import effect_proof_passed, operation_units
    compact = _compact(quote)
    if not compact or record.spec.op not in {"append", "replace"}:
        return False
    expected = str(record.spec.new_text or "")
    if facts is not None:
        expected, issues = instantiate_slots(expected, facts)
        if issues:
            expected = ""
    elif "{" in expected:
        expected = ""
    if expected and compact in _compact(expected):
        # An exact authorized final policy is conclusive even when that policy
        # preserves the source's first sentence (G12 keeps the fee-bearer sentence).
        return True
    expected_compact = _compact(expected)
    if (expected_compact and actual_text and compact in _compact(actual_text)
            and compact.rstrip("。；;！？!?")
            .endswith(expected_compact.rstrip("。；;！？!?"))):
        # A sweep can quote the complete final sentence with its preserved source
        # prefix ("某类基金份额的…") instead of the bare policy component.  The
        # quote is present in the artifact and ends with the operation's complete
        # instantiated policy; the caller separately requires this operation/site's
        # effect proof.  This is not evidence that the old effect survived, and a
        # quote with extra unauthorized text after the policy does not qualify.
        return True
    if expected and actual_text:
        from .recall import _policy_phrase_equivalent
        references = [_compact(str(value)) for value in
                      [getattr(record.spec, "old_text", ""),
                       *getattr(record.spec, "alternatives", ())] if _compact(str(value))]
        if _policy_phrase_equivalent(_compact(expected), _compact(actual_text), references):
            # The policy is already present with reordered subjects ("由于基金费用的
            # 不同，A/C类…" vs "A/C类…费用收取不同").  The model quoting that real
            # sentence as an error is not contradictory evidence (G18 p139).
            return True
    if getattr(record.spec, "rule_id", "") in {"G02", "G04", "G08", "G11"} and expected:
        # The real contract may write "A类及D类" while the instantiated guide
        # group is "A类、D类".  Same certified class set, not an invented class.
        from .generation.effects import _class_group_equivalent
        if _class_group_equivalent(expected, compact):
            return True
        if (getattr(record.spec, "rule_id", "") in {"G02", "G04"}
                and actual_text
                and not any(token in compact for token in
                            ("申购费", "认购费", "销售服务费"))
                and any(token in compact for token in ("基金份额类别", "份额类别", "分为"))
                and _class_group_equivalent(expected, actual_text)):
            # A sweep may quote the introductory class enumeration instead of the
            # fee-group sentence that follows it in the same paragraph. The
            # enumeration is not an independently editable G02/G04 site; an exact
            # local operation proof for the full paragraph already proves the
            # authorized group. Do not let that stale scope quote block delivery.
            return True
    if (getattr(record.spec, "rule_id", "") in {"G02", "G04", "G08", "G11", "G18"}
            and actual_text and proofs and obligations is not None):
        local = _local_operation_proofs(proofs.get(record.obligation_id),
                                        record.spec.operation_id,
                                        record.obligation_id, location)
        if local and all(effect_proof_passed(proof) for proof in local):
            # Class-substitution rules (G18) may add a real D class to the guide's
            # A/C template.  The final authorized edit, not the literal template, is
            # the effect at this site.  Claim proof already rules out unapproved
            # residual text, so an exact final replacement is safe evidence.
            for parent, component in operation_units(edits, record.spec.operation_id):
                if str(component.get("location") or parent.get("location") or "") != location:
                    continue
                replacement = _compact(str(component.get("replacement")
                                           or parent.get("replacement") or ""))
                if replacement and compact in replacement:
                    return True
    references = [str(record.spec.old_text or ""), *record.spec.alternatives]
    old_parts = [_compact(sentence) for reference in references
                 for sentence in re.split(r"(?<=[。；;])", reference)
                 if len(_compact(sentence)) >= 8]
    if any(part in compact or compact in part for part in old_parts):
        return False
    if getattr(record.spec, "rule_id", "") in {"G02", "G04"} and expected and re.fullmatch(
            r"称为" + re.escape(_compact(expected)) + r"[。；;]?", compact):
        # A definition's grammatical label prefix is preserved source wording.
        # Its instantiated class group is already proven at this exact operation
        # and site by the caller; an unchanged correct group is not evidence that
        # a model's example-only extra classes should have been inserted.
        return True
    authorized_units = [(parent, component) for parent, component in
                        operation_units(edits, record.spec.operation_id)
                        if str(component.get("location") or parent.get("location") or "") == location
                        and (not target_id or str(component.get("target_id") or "") == target_id)]
    # A paragraph quote may include preserved source or an authorized sibling.
    # Rebuild it only from components whose replacement is exactly guide policy
    # (or an exact bounded splice). Merely appearing in compose output, fixed_text
    # evidence, or the final parent edit does not authorize an extra assertion.
    if len(_compact(expected)) >= 8 and _compact(expected) in compact and actual_text \
            and authorized_units and before_text and obligations is not None and proofs:
        from .generation.atomic import compose_paragraph
        components = []
        for parent in edits:
            if str(parent.get("location") or "") != location:
                continue
            for component in parent.get("components") or [parent]:
                keys = list(component.get("operation_keys") or
                            (component.get("evidence") or {}).get("operation_keys") or [])
                if len(keys) != 1:
                    return False
                owner = obligations.record(keys[0])
                if owner is None or owner.applicability.status != "TRUE":
                    return False
                local = _local_operation_proofs(proofs.get(owner.obligation_id),
                    owner.spec.operation_id, owner.obligation_id, location)
                if not local or not all(effect_proof_passed(proof) for proof in local):
                    return False
                try:
                    start, end = int(component["start"]), int(component["end"])
                except (KeyError, TypeError, ValueError):
                    return False
                if not 0 <= start <= end <= len(before_text):
                    return False
                source = before_text[start:end]
                replacement = str(component.get("replacement") or "")
                fixed = str(owner.spec.new_text or "")
                if facts is not None:
                    fixed, issues = instantiate_slots(fixed, facts)
                    if issues:
                        return False
                authorized = owner.spec.op == "delete" and not replacement
                if owner.spec.op in {"replace", "append"}:
                    authorized = _compact(replacement) == _compact(fixed)
                    old = str(owner.spec.old_text or "")
                    if old and source.count(old) == 1:
                        authorized |= source.replace(old, fixed, 1) == replacement
                if not authorized:
                    return False
                components.append({**component, "expected_old_text": source})
        rebuilt = compose_paragraph(before_text, components) if components else None
        return rebuilt is not None and rebuilt == actual_text and compact in _compact(rebuilt)
    return False


def _quote_confirms_class_facts(quote: str, facts: Facts | None) -> bool:
    """Recognize literal class-set/fee evidence that agrees with certified Facts.

    Exact source presence alone cannot prove a review's contrary interpretation.
    This bounded grammar accepts only explicit enumeration and fee statements;
    unfamiliar semantics stay reviewable instead of being guessed.
    """
    from .fact_evidence import class_labels
    if facts is None or not facts.value_verified or not facts.set_complete_verified \
            or any(facts.status_of(name) != "VERIFIED" for name in (
                "share_class_structure", "subscription_fee_group", "service_fee_group")):
        return False
    current = list(facts.current_classes)
    if not current or any(not facts.quotes_verified.get(f"class:{item.name}", False)
                          for item in current):
        return False
    entries = {next(iter(labels)): item for item in current
               if len(labels := class_labels(item.name)) == 1}
    if len(entries) != len(current):
        return False

    def flag(text: str, pattern: str) -> bool | None:
        negative = bool(re.search("不" + pattern, text))
        positive = bool(re.search(pattern, re.sub("不" + pattern, "", text)))
        return None if positive == negative else positive

    clauses = [part for part in re.split(r"[。；;]", _compact(quote)) if part]
    if not clauses:
        return False
    for clause in clauses:
        labels = class_labels(clause)
        if not labels or not labels <= set(entries):
            return False
        if re.search(r"分为|分设|设置|设立|分成", clause):
            if labels != set(entries) or re.search(r"收取|计提", clause):
                return False
            continue
        subscription = flag(clause, r"收取(?:认购[、及和/])?申购(?:费用|费)")
        service = flag(clause, r"(?:收取|计提)销售服务费")
        if subscription is None or service is None or any(
                item.subscription_fee != subscription or item.service_fee != service
                for label, item in entries.items() if label in labels):
            return False
    return True


def _delete_opinion_scope_unproven(evidence: str, owned: Sequence[Any],
                                 actual: DocumentInspection, location: str) -> bool:
    """An audit may not turn a sibling replacement into a delete obligation.

    For a delete operation the only business question is whether its own old text
    remains.  If every owned operation is a delete, its old text is absent from the
    actual site, and the review quotes neither that old text nor a residual, the
    negative opinion is outside the operation scope.  The caller still requires a
    complete local effect proof; this helper never manufactures PASS by itself.
    """
    if not owned or not location:
        return False
    compact_evidence = _compact(evidence)
    try:
        actual_text = _compact(str(actual.by_location(location).text))
    except (KeyError, ValueError, AttributeError):
        return False
    for record in owned:
        if getattr(record.spec, "op", "") != "delete":
            return False
        old = _compact(str(getattr(record.spec, "old_text", "") or ""))
        if not old or old in compact_evidence or old in actual_text:
            return False
    return True


def _site_record_quotes_expected_effect(
        quote: str, location: str, targets: Sequence[Target], rules_by_id: dict[str, dict],
        planned: dict[str, Any], original: DocumentInspection, actual: DocumentInspection,
        facts: Facts | None, obligations: Any, artifact_proofs: Mapping[str, Any]) -> bool:
    """Is this quote an authorized new effect at the same business site?

    The audit may quote a sibling rule's final wording (G12 replacing the paragraph
    that G13 deletes from).  That is not evidence that G13's deletion was missed.
    Only a local, effect-proven operation may authorize the quote.
    """
    if obligations is None:
        return False
    for target in targets:
        if target.location != location or target.out_of_scope:
            continue
        for operation_id in target.operations:
            record = obligations.record(operation_id)
            if record is None or record.applicability.status != "TRUE":
                continue
            if not _quote_is_expected_effect(
                    quote, record, facts, edits=planned.get("edits") or [],
                    location=location,
                    before_text=str(getattr(original.by_location(location), "text", "")),
                    actual_text=str(getattr(actual.by_location(location), "text", "")),
                    target_id=target.target_id, obligations=obligations,
                    proofs=artifact_proofs):
                continue
            from .generation.effects import effect_proof_passed
            local = _local_operation_proofs(artifact_proofs.get(record.obligation_id),
                                            record.spec.operation_id,
                                            record.obligation_id, location)
            if local and all(effect_proof_passed(proof,
                                                 operation_id=record.spec.operation_id,
                                                 obligation_id=record.obligation_id)
                            for proof in local):
                return True
    return False


def _sibling_expected_effect(quote: str, location: str, obligations: Any,
                             states: Mapping[str, Any], *, facts: Facts | None,
                             edits: Sequence[dict[str, Any]], original: DocumentInspection,
                             actual: DocumentInspection) -> bool:
    """True when a finding quotes an authorized final effect at this site."""
    if obligations is None:
        return False
    from .generation.effects import effect_proof_passed
    try:
        before_text = str(original.by_location(location).text)
        actual_text = str(actual.by_location(location).text)
    except (KeyError, ValueError, AttributeError):
        return False
    for obligation_id, state in states.items():
        record = obligations.record(obligation_id)
        if record is None or record.applicability.status != "TRUE":
            continue
        local = _local_operation_proofs(state, record.spec.operation_id,
                                        record.obligation_id, location)
        if not local or not all(effect_proof_passed(proof) for proof in local):
            continue
        if _quote_is_expected_effect(
                quote, record, facts, edits=edits, location=location,
                before_text=before_text, actual_text=actual_text,
                obligations=obligations, proofs=states):
            return True
    return False


def _quote_is_authorized_removal(quote: str, location: str, before_text: str,
                                 edits: Sequence[dict[str, Any]], obligations: Any,
                                 proofs: Mapping[str, Any], failures: Sequence[dict[str, Any]]) -> bool:
    """Prove a BEFORE-only citation belongs wholly to certified removed spans.

    A sibling may own the deletion (G17 at G16's append site). Its own operation
    proof is mandatory; a matched plan or a proven append grants no removal rights.
    """
    from .generation.effects import effect_proof_passed, operation_units
    compact = _compact(quote)
    if not compact or obligations is None or any(
            failure.get("location") == location for failure in failures):
        return False
    intervals = []
    for record in obligations.records:
        if record.applicability.status != "TRUE" or record.spec.op not in {"delete", "replace"}:
            continue
        local = _local_operation_proofs(proofs.get(record.obligation_id),
            record.spec.operation_id, record.obligation_id, location)
        if not local or not all(effect_proof_passed(proof) for proof in local):
            continue
        for parent, unit in operation_units(edits, record.spec.operation_id):
            if str(unit.get("location") or parent.get("location") or "") != location:
                continue
            try:
                start, end = int(unit["start"]), int(unit["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if 0 <= start < end <= len(before_text):
                intervals.append((len(_compact(before_text[:start])), len(_compact(before_text[:end]))))
    source = _compact(before_text)
    positions = [match.start() for match in re.finditer(re.escape(compact), source)]
    # Ambiguous repeated quotes remain reviewable unless every occurrence is owned.
    return bool(positions) and all(all(any(start <= index < end for start, end in intervals)
        for index in range(position, position + len(compact))) for position in positions)


def _run_audit(model: Any, rules_by_id: dict[str, dict], targets: Sequence[Target],
               planned: dict[str, Any], original: DocumentInspection, actual: DocumentInspection,
               *, only_rules: set[str] | None = None, facts: Facts | None = None,
               obligations: Any = None,
               scopes: Mapping[str, Any] | None = None,
               scope_audit: dict[str, Any] | None = None) -> dict[str, Any]:
    plan_by_target = _plan_by_target(planned)
    # A target outside its rule's physical scope is not audit evidence either: drop it
    # before it can become coverage or an unresolved business finding.
    _apply_scope_gate(targets, scopes, scope_audit, stage="audit")
    # A target the planner already judged out of scope (its rule's condition does not
    # hold, or it needs a class group / sales-service-fee wording this product cannot
    # carry) must not be re-demanded by the audit; auditing it would report a gap the
    # engine deliberately did not fill (FL-D056).
    out_of_scope = {target.target_id for target in targets if target.out_of_scope}
    # Independently review already-satisfied targets as well as open edits.  A model
    # inventory can misclassify a real obligation as ``satisfied``; restricting the
    # audit input to ``needs_edit`` made that false closure invisible to every later
    # gate.  ``absent`` remains a qualification decision and is handled by the
    # deterministic semantic sweep/obligation proof instead of being silently turned
    # into a business edit candidate here.
    auditable = [target for target in targets
                 if target.state in {"needs_edit", "satisfied"}
                 and target.target_id not in out_of_scope
                 and not target.attribution_error]
    rule_ids = sorted({target.rule_id for target in auditable})
    if only_rules is not None:
        rule_ids = [rule_id for rule_id in rule_ids if rule_id in only_rules]
    results: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    prepared: list[dict[str, Any]] = []
    artifact_proofs: dict[str, Any] = {}
    artifact_failures: list[dict[str, Any]] = []
    if obligations is not None:
        # Audit is a semantic review; the shared replay/effect evaluator owns
        # completion proof. An unsupported opinion cannot undo that proof.
        from .generation.claim_replay import replay_claims
        from .recall import approval_book_for
        # Build approvals BEFORE serializing targets: the book stamps
        # target.approval_id, and the replayed target dict must carry it.
        approval_book = approval_book_for(rules_by_id, targets, original)
        replay = replay_claims(planned.get("edits") or [], original, actual,
                              rules_by_id=rules_by_id, facts=facts,
                              targets_by_id={target.target_id: target.as_dict() for target in targets},
                              obligations=obligations, scopes=scopes,
                              approvals=approval_book)
        artifact_proofs = replay["obligations"]
        artifact_failures = replay["failures"]
    auditable_by_rule = _targets_by_rule(auditable)
    for rule_id in rule_ids:
        rule = rules_by_id.get(rule_id)
        if rule is None:
            continue
        rule_targets = [target for target in auditable if target.rule_id == rule_id]
        ledger_ids = {target.target_id for target in rule_targets}
        supplied = {target.location for target in rule_targets}
        other_edits = []
        for other_id, other_targets in auditable_by_rule.items():
            if other_id == rule_id:
                continue
            for other in other_targets:
                if other.location not in supplied:
                    continue
                entry = plan_by_target.get(other.target_id) or {}
                if entry.get("status") not in {"planned", "satisfied"}:
                    continue
                other_edits.append({
                    "rule_id": other_id, "location": other.location,
                    "operation": entry.get("operation") or "",
                    "replacement": _clip(str(entry.get("replacement") or ""), 200),
                })
        context, before_text, after_text = _audit_context(
            rule, rule_targets, plan_by_target, original, actual,
            limit=model.max_context_chars, other_edits=other_edits, facts=facts)
        prepared.append({"rule_id": rule_id, "rule": rule, "rule_targets": rule_targets,
                         "ledger_ids": ledger_ids, "supplied": supplied,
                         "other_edits": other_edits, "context": context,
                         "before_text": before_text, "after_text": after_text})

    def _invoke(entry: dict[str, Any]) -> Any:
        return model.call(task_type="recall_audit", bounded_context=entry["context"],
                          response_schema=AUDIT_SCHEMA,
                          instruction=AUDIT_INSTRUCTION,
                          prompt_version=AUDIT_PROMPT_VERSION)

    concurrency = _review_concurrency(model, len(prepared))
    if concurrency > 1 and len(prepared) > 1:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            calls = list(executor.map(_invoke, prepared))
    else:
        calls = [_invoke(entry) for entry in prepared]

    for entry, call in zip(prepared, calls):
        rule_id = str(entry["rule_id"])
        rule = entry["rule"]
        rule_targets = entry["rule_targets"]
        ledger_ids = entry["ledger_ids"]
        supplied = entry["supplied"]
        other_edits = entry["other_edits"]
        before_text = entry["before_text"]
        after_text = entry["after_text"]
        value = call.value if isinstance(call.value, dict) else {}
        for item in value.get("results") or []:
            if not isinstance(item, dict):
                dropped.append({"code": "AUDIT_ITEM_INVALID", "rule_id": rule_id})
                continue
            target_id = str(item.get("target_id") or "")
            verdict = str(item.get("verdict") or "")
            if target_id not in ledger_ids or verdict not in {"completed", "incomplete", "wrong"}:
                dropped.append({"code": "AUDIT_TARGET_UNKNOWN", "rule_id": rule_id,
                                "target_id": target_id, "verdict": verdict})
                continue
            evidence = str(item.get("evidence_quote") or "")
            node = next((candidate for candidate in rule_targets
                         if candidate.target_id == target_id), None)
            evidence_before = evidence_after = ""
            if node is not None:
                try:
                    evidence_before = str(original.by_location(node.location).text)
                    evidence_after = str(actual.by_location(node.location).text)
                except (KeyError, ValueError, AttributeError):
                    pass
            quote_in_before = bool(_compact(evidence)) and _compact(evidence) in _compact(evidence_before)
            quote_in_after = bool(_compact(evidence)) and _compact(evidence) in _compact(evidence_after)
            # A loss must be quoted from BEFORE: requiring AFTER silently discarded
            # the very evidence of unauthorized removal (FL-D224). Presence proves
            # the citation, not that the model's interpretation is correct.
            verified = quote_in_before or quote_in_after
            deletion_evidence = False
            if not verified and verdict == "completed":
                # A deletion leaves no AFTER text to quote: the target's own source
                # quote still present in BEFORE is accepted as the deletion evidence.
                target = node
                if target is not None and target.quote:
                    if target.composite:
                        after_empty = _composite_parts_gone(target, original, actual)
                    else:
                        after_empty = not _region_text(
                            actual, target.location, rule_targets, 1200).strip()
                    if after_empty and _compact(target.quote) in _compact(before_text):
                        verified, deletion_evidence = True, True
                        evidence = evidence or target.quote
            deterministic = False
            if not verified:
                dropped.append({"code": "AUDIT_EVIDENCE_UNVERIFIED", "rule_id": rule_id,
                                "target_id": target_id, "evidence_quote": _clip(evidence, 80)})
            results.append({"target_id": target_id, "rule_id": rule_id, "verdict": verdict,
                            "reason": str(item.get("reason") or ""),
                             "evidence_quote": evidence, "evidence_verified": verified,
                             "evidence_in_before": quote_in_before,
                             "evidence_in_after": quote_in_after,
                            "deletion_evidence": deletion_evidence,
                            "deterministic": deterministic,
                            "failure_class": str(item.get("failure_class") or ""),
                            "affected_fact": str(item.get("affected_fact") or ""),
                            "affected_obligation": str(item.get("affected_obligation") or "")})
            result = results[-1]
            result["site_signature"] = _audit_site_signature(rule_id, targets, planned, actual)
            if not verified or verdict in {"wrong", "incomplete"}:
                from .generation.effects import effect_proof_passed
                owned = [record for record in (obligations.records if obligations is not None else [])
                         if node is not None and record.spec.operation_id in node.operations
                         and record.applicability.status == "TRUE"]
                local = {record.obligation_id: _local_operation_proofs(
                    artifact_proofs.get(record.obligation_id), record.spec.operation_id,
                    record.obligation_id, node.location) for record in owned}
                proven = bool(owned) and all(local[record.obligation_id] and all(
                    effect_proof_passed(proof, operation_id=record.spec.operation_id,
                                        obligation_id=record.obligation_id)
                    for proof in local[record.obligation_id]) for record in owned)
                contradicted = any(
                    str(failure.get("location") or "") == (node.location if node else "")
                    and failure.get("operation_id") in {record.spec.operation_id for record in owned}
                    for failure in artifact_failures)
                expected_quote = bool(quote_in_after and node is not None and any(
                    _quote_is_expected_effect(evidence, record, facts,
                        edits=planned.get("edits") or [], location=node.location,
                        before_text=evidence_before, actual_text=evidence_after,
                        target_id=node.target_id, obligations=obligations,
                        proofs=artifact_proofs)
                    for record in owned))
                certified_fact_quote = ((quote_in_after or str(item.get("failure_class") or "").upper()
                    in {"FACT", "APPLICABILITY"}) and verified and _quote_confirms_class_facts(
                    evidence, facts))
                delete_scope_unproven = bool(
                    proven and not contradicted and quote_in_after and node is not None and
                    _delete_opinion_scope_unproven(evidence, owned, actual, node.location) and
                    _site_record_quotes_expected_effect(
                        evidence, node.location, targets, rules_by_id, planned,
                        original, actual, facts, obligations, artifact_proofs))
                authorized_removal = bool(
                    quote_in_before and not quote_in_after and node is not None and
                    _quote_is_authorized_removal(evidence, node.location, evidence_before,
                        planned.get("edits") or [], obligations, artifact_proofs, artifact_failures))
                if not verified or expected_quote or certified_fact_quote or delete_scope_unproven or authorized_removal:
                    result["review_status"] = "REVIEW_UNPROVEN"
                    result["artifact_proven"] = proven and not contradicted
                    if expected_quote:
                        result["review_evidence_status"] = "EXPECTED_EFFECT_QUOTED_AS_ERROR"
                    elif certified_fact_quote:
                        result["review_evidence_status"] = "CERTIFIED_FACT_QUOTED_AS_ERROR"
                    elif delete_scope_unproven:
                        result["review_evidence_status"] = "OPERATION_SCOPED_DELETE_PROOF"
                    elif authorized_removal:
                        result["review_evidence_status"] = "AUTHORIZED_REMOVAL_QUOTED_AS_ERROR"
        for item in value.get("missed_targets") or []:
            if not isinstance(item, dict):
                dropped.append({"code": "AUDIT_MISSED_ITEM_INVALID", "rule_id": rule_id})
                continue
            missed_rule = str(item.get("rule_id") or "")
            location = str(item.get("location") or "")
            quote = str(item.get("quote") or "")
            try:
                missed_before = str(original.by_location(location).text)
                missed_after = str(actual.by_location(location).text)
            except (KeyError, ValueError, AttributeError):
                missed_before = missed_after = ""
            verified = bool(quote) and (_compact(quote) in _compact(missed_after)
                                        or _compact(quote) in _compact(missed_before))
            if missed_rule not in rules_by_id or location not in supplied or not verified:
                dropped.append({"code": "AUDIT_MISSED_INVALID", "rule_id": missed_rule,
                                "location": location, "quote": _clip(quote, 80)})
                continue
            missed_item = {"rule_id": missed_rule, "location": location, "quote": quote,
                           "operation_id": str(item.get("operation_id") or ""),
                           "obligation_id": str(item.get("obligation_id") or ""),
                           "target_id": str(item.get("target_id") or ""),
                           "reason": str(item.get("reason") or "")}
            if verified and obligations is not None and \
                    _site_record_quotes_expected_effect(
                        quote, location, targets, rules_by_id, planned,
                        original, actual, facts, obligations, artifact_proofs):
                missed_item["review_status"] = "REVIEW_UNPROVEN"
                missed_item["review_evidence_status"] = "EXPECTED_EFFECT_QUOTED_AS_MISSED"
                missed_item["artifact_proven"] = True
            missed.append(missed_item)
    return {"rules": rule_ids, "results": results, "missed_targets": missed, "dropped": dropped,
            "artifact_failures": artifact_failures}


def _confirm_merged_append(rule: dict, plan_entry: dict[str, Any], location: str,
                           actual: DocumentInspection, facts: Facts, rules_by_id: dict[str, dict],
                           other_edits: Sequence[dict[str, Any]]) -> str | None:
    """Deterministically confirm an append whose base clause a sibling rule deletes.

    G03 appends a new clause "after the original 份额类别设置 clause" while G06 deletes
    that very clause (the conversion sentence); G16 appends the daily-accrual clause
    while G17 deletes the usage-scope sentence. The merge writes the append text into
    the freed span, so the audit often judges the append "wrong" because its base text
    is gone — even though the deletion is an authorised change by another rule and the
    append text is present verbatim. The confirmation is evidence-based: the append
    text must be in AFTER and the sibling operation must itself be a deletion.
    """
    if plan_entry.get("operation") not in {"insert", "append"}:
        return None
    if not any(operation.get("op") == "append"
               and condition_matches(operation.get("condition"), facts)
               for operation in rule.get("operations") or []):
        return None
    # The base clause may be deleted by a SIBLING rule at the same site (G03+G06,
    # G16+G17), not only by another operation of the same rule. The evidence check
    # below still requires a real append text and a real delete edit at this location;
    # the sibling's own rule definition is used to prove that operation is a delete.
    try:
        span = actual.by_location(location)
    except DocxError:
        return None
    after = _compact(display_text(span.text)[0])
    fixed = str(plan_entry.get("replacement") or "")
    if not fixed or _compact(fixed) not in after:
        return None
    sibling_deletes = [entry.get("rule_id") for entry in other_edits
                       if entry.get("operation") in {"replace", "delete"}
                       and any(operation.get("op") == "delete"
                               for operation in (rules_by_id.get(str(entry.get("rule_id")), {})
                                                 .get("operations") or []))]
    if not sibling_deletes:
        return None
    return fixed


def _merge_audit_state(state: dict[str, Any], round_ledger: dict[str, Any],
                       targets: Sequence[Target]) -> None:
    """Re-audited rules replace their previous verdicts; other rules stay untouched."""
    audited = set(round_ledger.get("rules") or [])
    for identity in [key for key in state["results"] if key[0] in audited]:
        del state["results"][identity]
    by_id = {target.target_id: target for target in targets}
    for result in round_ledger["results"]:
        target = by_id.get(result["target_id"])
        if target is None:
            continue
        state["results"][_target_identity(target)] = result
    for rule_id in audited:
        state["missed"][rule_id] = []
    for item in round_ledger["missed_targets"]:
        state["missed"].setdefault(item["rule_id"], []).append(item)


def _audit_issue_key(issue: Mapping[str, Any]) -> str:
    """Stable identity of one audit issue across repair rounds."""
    return "|".join(str(issue.get(name) or "") for name in
                    ("code", "rule_id", "location", "affected_obligation"))


def _audit_context_key(context: Any) -> str:
    return "|".join((str(context.error_code or ""), str(context.rule_id or ""),
                     str(context.site_id or ""), str(context.operation_id or ""),
                     str(context.metadata.get("source_span") or "")))


def _audit_recovery_contexts(issues: Sequence[dict[str, Any]], *,
                             targets: Sequence[Target] = (), planned: dict | None = None,
                             artifact_failures: Sequence[dict] = ()) -> list[Any]:
    """Classify audit/review issues into root-cause recovery contexts.

    One context per (code, rule, target, location, obligation): two targets of one rule
    must each get their own decision/history.  The caller bounds how many decisions are
    taken per round and records the overflow as ``skipped`` instead of dropping it.
    """
    from .recovery import FailureClass, RecoveryContext

    contexts: list[Any] = []
    seen: set[str] = set()
    for issue in issues:
        code = str(issue.get("code") or "")
        declared = str(issue.get("failure_class") or "").upper()
        if code in {"AUDIT_VERDICT_MISSING", "REVIEW_UNPROVEN"}:
            failure_class = FailureClass.VERIFICATION
        elif declared in FailureClass.__members__:
            failure_class = FailureClass(declared)
        elif code == "AUDIT_MISSED_TARGET":
            failure_class = FailureClass.TARGET
        elif code in {"AUDIT_VERDICT_MISSING", "REVIEW_UNPROVEN"}:
            # The audit itself has not produced a verdict yet; re-generating a new
            # artifact is not a recovery for that.  Fail closed and re-audit next round.
            failure_class = FailureClass.VERIFICATION
        else:
            # A negative verdict without a declared class is re-proved against a changed
            # artifact; generation is the only safe executable route.
            failure_class = FailureClass.GENERATION
        target = next((target for target in targets
                       if target.target_id == issue.get("target_id")), None)
        owned = [failure for failure in artifact_failures
                 if failure.get("location") == issue.get("location")
                 and (not target or failure.get("operation_id") in target.operations)]
        operation_id = str(issue.get("operation_id") or
                           (",".join(target.operations) if target else ""))
        context = RecoveryContext(
            rule_id=str(issue.get("rule_id") or ""),
            target_id=str(issue.get("target_id") or ""),
            operation_id=operation_id,
            obligation_id=operation_id,
            site_id=str(issue.get("location") or ""),
            stage="audit",
            failure_class=failure_class,
            error_code=code or "AUDIT_NOT_COMPLETED",
            reason=str(issue.get("reason") or issue.get("issue") or "audit incomplete"),
            metadata={"route_class": (declared if declared in FailureClass.__members__
                                      and declared != "VERIFICATION" else ""),
                      "source_span": (f"{target.start}:{target.end}" if target else str(issue.get("quote") or "")),
                      "affected_fact": str(issue.get("affected_fact") or "")})
        from dataclasses import replace
        for operation in (target.operations if target and target.operations else (operation_id,)):
            owned_class = failure_class
            if target is not None and failure_class in {FailureClass.EXECUTION, FailureClass.GENERATION}:
                # Root cause is operation-specific even in a same-site atomic edit.
                own_failure = next((failure for failure in owned
                                    if failure.get("operation_id") == operation), None)
                owned_class = (_claim_failure_context(own_failure, targets,
                    (planned or {}).get("edits") or []).resolved_class if own_failure
                    else FailureClass.GENERATION)
            owned_context = replace(context, operation_id=operation, obligation_id=operation,
                                    failure_class=owned_class)
            key = _audit_context_key(owned_context)
            if key not in seen:
                seen.add(key)
                contexts.append(owned_context)
    return contexts


def _audit_issues(state: dict[str, Any], targets: Sequence[Target]) -> list[dict[str, Any]]:
    """Current unresolved audit problems: missing/incomplete verdicts and missed targets."""
    issues: list[dict[str, Any]] = []
    results = state.get("results") or {}
    for target in targets:
        if target.state not in {"needs_edit", "satisfied"} or target.out_of_scope:
            continue
        result = results.get(_target_identity(target))
        if result is None:
            issues.append({"code": "AUDIT_VERDICT_MISSING", "rule_id": target.rule_id,
                           "target_id": target.target_id, "location": target.location})
        elif not result.get("artifact_proven") and (
                result["verdict"] != "completed" or not result["evidence_verified"]):
            # A model can quote the target's old text, correctly report that it is
            # present in BEFORE and absent in AFTER, yet still write an
            # "incomplete" verdict.  The evidence is the deterministic proof for
            # a removal/replacement; do not let the contradictory prose reopen an
            # obligation that the artifact already closed.
            evidence_quote = _compact(str(result.get("evidence_quote") or ""))
            target_quote = _compact(target.quote)
            if (result.get("evidence_verified") and result.get("evidence_in_before")
                    and not result.get("evidence_in_after")
                    and target_quote and target_quote in evidence_quote):
                continue
            issues.append({"code": "AUDIT_NOT_COMPLETED" if result["evidence_verified"]
                           else "REVIEW_UNPROVEN", "rule_id": target.rule_id,
                           "target_id": target.target_id, "location": target.location,
                           "verdict": result["verdict"], "reason": result["reason"],
                           "evidence_verified": result["evidence_verified"],
                           "failure_class": result.get("failure_class") or "",
                           "affected_fact": result.get("affected_fact") or "",
                           "affected_obligation": result.get("affected_obligation") or ""})
    for rule_id in sorted(state.get("missed") or {}):
        for item in state["missed"][rule_id]:
            if item.get("artifact_proven") or \
                    item.get("review_status") == "REVIEW_UNPROVEN":
                continue
            issues.append({"code": "AUDIT_MISSED_TARGET", "rule_id": rule_id,
                           "operation_id": item.get("operation_id", ""),
                           "obligation_id": item.get("obligation_id", ""),
                           "target_id": item.get("target_id", ""),
                           "location": item["location"], "quote": item["quote"],
                           "reason": item["reason"]})
    return issues


def _audit_site_signature(rule_id: str, targets: Sequence[Target], planned: dict,
                          actual: DocumentInspection) -> str:
    from .frozen import digest
    sites = sorted({target.location for target in targets if target.rule_id == rule_id})
    paragraphs = []
    for location in sites:
        try:
            paragraphs.append((location, actual.by_location(location).text))
        except (DocxError, KeyError, ValueError):
            paragraphs.append((location, None))
    return digest({"targets": [target.as_dict() for target in targets if target.rule_id == rule_id],
                   "sites": paragraphs, "edits": [edit for edit in planned.get("edits") or []
                                                   if edit.get("location") in sites]})


def _stale_rules(audit_state: dict[str, Any], targets: Sequence[Target],
                 planned: dict | None = None, actual: DocumentInspection | None = None) -> set[str]:
    """Rules whose auditable target set changed since their last verdict."""
    current: dict[str, set[tuple[str, str, str]]] = {}
    for target in targets:
        if target.state in {"needs_edit", "satisfied"} and not target.out_of_scope \
                and not target.attribution_error:
            current.setdefault(target.rule_id, set()).add(_target_identity(target))
    audited: dict[str, set[tuple[str, str, str]]] = {}
    for identity, result in (audit_state.get("results") or {}).items():
        audited.setdefault(result["rule_id"], set()).add(identity)
    stale = {rule_id for rule_id, identities in current.items()
             if identities != audited.get(rule_id, set())}
    stale |= {rule_id for rule_id in audited if rule_id not in current}
    if planned is not None and actual is not None:
        for result in (audit_state.get("results") or {}).values():
            rule_id = result["rule_id"]
            if result.get("site_signature") != _audit_site_signature(rule_id, targets, planned, actual):
                stale.add(rule_id)
    return stale


# ---------------------------------------------------------------------------
# Repair notes and synthetic targets
# ---------------------------------------------------------------------------

def _location_windows(entries: Sequence[_WindowState]) -> dict[str, str]:
    return {location: entry.window.id for entry in entries for location in entry.window.locations}


def _affected_windows(entries: Sequence[_WindowState], notes: dict[str, str]) -> list[_WindowState]:
    return [entry for entry in entries if entry.window.id in notes]


def _audit_repair_notes(issues: Sequence[dict[str, Any]], targets: Sequence[Target],
                        entries: Sequence[_WindowState]) -> dict[str, str]:
    by_target = {target.target_id: target for target in targets}
    location_windows = _location_windows(entries)
    notes: dict[str, list[str]] = {}
    for issue in issues[:10]:
        if issue["code"] in {"AUDIT_NOT_COMPLETED", "AUDIT_VERDICT_MISSING"}:
            target = by_target.get(str(issue.get("target_id")))
            if target is None:
                continue
            window_id = location_windows.get(target.location)
            if window_id is None:
                continue
            notes.setdefault(window_id, []).append(
                f"- 目标 {target.target_id}（规则 {target.rule_id}，位置 {target.location}）："
                f"{issue['code']}；结论 {issue.get('verdict') or '未返回'}；"
                f"原因：{_clip(str(issue.get('reason') or ''), 120)}")
        elif issue["code"] == "AUDIT_MISSED_TARGET":
            window_id = location_windows.get(str(issue.get("location") or ""))
            if window_id is None:
                continue
            notes.setdefault(window_id, []).append(
                f"- 复核另报未登记目标：规则 {issue['rule_id']}，位置 {issue['location']}；"
                f"引文：{_clip(str(issue.get('quote') or ''), 80)}；"
                f"原因：{_clip(str(issue.get('reason') or ''), 120)}")
    header = ("上一轮独立复核对实际产物给出以下未通过结论，请在窗口内重新完整盘点并给出修正后的目标，"
              "不要只重复上一轮引文：\n")
    return {window_id: header + "\n".join(lines) for window_id, lines in notes.items()}


def _finding_repair_notes(pending: Sequence[dict[str, Any]],
                          entries: Sequence[_WindowState]) -> dict[str, str]:
    location_windows = _location_windows(entries)
    notes: dict[str, list[str]] = {}
    for finding in pending[:10]:
        window_id = location_windows.get(finding["location"])
        if window_id is None:
            continue
        notes.setdefault(window_id, []).append(
            f"- 规则 {finding['rule_id']}，位置 {finding['location']}（{finding['issue']}）："
            f"产物引文：{_clip(str(finding.get('quote') or ''), 80)}；"
            f"原因：{_clip(str(finding.get('reason') or ''), 120)}")
    header = "最终查漏在实际产物中发现以下未落实项，请在窗口内重新完整盘点并给出修正后的目标：\n"
    return {window_id: header + "\n".join(lines) for window_id, lines in notes.items()}


def _absorb_missed_targets(audit_state: dict[str, Any], targets: Sequence[Target],
                           synthetic: list[Target], origins: dict[str, str],
                           inspection: DocumentInspection, *,
                           rules_by_id: dict[str, dict], facts: Facts,
                           obligations: Any = None) -> int:
    """Promote verified missed-target reports into source-bound repair targets."""
    def identity(target: Target, operation_id: str) -> tuple:
        return (target.rule_id, operation_id, target.location, target.start, target.end)
    existing = {identity(target, operation_id)
                for target in [*targets, *synthetic] if not target.out_of_scope
                for operation_id in target.operations}
    added = 0
    for rule_id, items in sorted((audit_state.get("missed") or {}).items()):
        for item in items:
            if len(_compact(str(item.get("quote") or ""))) < 4:
                continue
            target = _make_synthetic_target(f"A{len(synthetic) + 1:03d}", rule_id, item["location"],
                                            item["quote"],
                                            f"audit_missed:{_clip(str(item.get('reason') or ''), 80)}",
                                            inspection)
            if target is None:
                continue
            claimed = str(item.get("operation_id") or "")
            if claimed:
                target.operations = (claimed,)
            # A model's rule/location is a candidate, never rule-wide coverage.
            # Rebind the quote and operation before deduplicating siblings.
            assign_target_operations([target], rules_by_id, inspection, facts, obligations)
            if claimed and claimed not in target.operations:
                continue
            target.operations = tuple(operation_id for operation_id in target.operations
                if identity(target, operation_id) not in existing)
            if not target.operations:
                continue
            synthetic.append(target)
            origins[target.target_id] = "audit_missed"
            existing.update(identity(target, operation_id)
                            for operation_id in target.operations)
            added += 1
    return added


def _absorb_sweep_findings(pending: Sequence[dict[str, Any]], targets: Sequence[Target],
                           synthetic: list[Target], origins: dict[str, str],
                           inspection: DocumentInspection, *, rules_by_id: dict[str, dict],
                           facts: Facts) -> int:
    """Fold sweep findings into the repair plan (FL-D047).

    A finding at a location the guide already covers re-binds that target to the
    operation's own reference text: the deterministic resolver recovers the exact
    clause (including one that runs across paragraphs), which the generic model quote
    may have missed. A finding at an unregistered location still becomes a synthetic
    target, as before.
    """
    def finding_operation(rule: dict, quote: str) -> str:
        blob = _compact(quote)
        for index, operation in enumerate(rule.get("operations") or []):
            old_text = _compact(str(operation.get("old_text") or ""))
            if old_text and (old_text in blob or blob in old_text):
                return _declared_operation_key(
                    str(rule.get("rule_id") or ""), index, operation)
        return ""

    def unique_applicable_operation(rule: dict) -> str:
        """Return the only executable text operation when a variant has no exact key.

        Sweep findings are source-bound evidence, but a contract variant may contain
        neither the guide's ``old_text`` nor its declared variants.  In that case the
        finding cannot be mapped by literal overlap.  A single applicable delete or
        replace operation is still an unambiguous operation identity; multiple such
        operations remain fail-closed and must go through ordinary target discovery.
        """
        candidates = []
        for index, operation in enumerate(rule.get("operations") or []):
            if operation.get("op") not in {"delete", "replace"}:
                continue
            if not condition_matches(operation.get("condition"), facts):
                continue
            candidates.append(_declared_operation_key(
                str(rule.get("rule_id") or ""), index, operation))
        return candidates[0] if len(candidates) == 1 else ""

    def identity(rule_id: str, operation_id: str, location: str) -> tuple[str, str, str]:
        return (rule_id, operation_id, location)

    existing = {identity(target.rule_id, key, target.location)
                for target in targets for key in (target.operations or ("",))}
    existing |= {identity(target.rule_id, key, target.location)
                 for target in synthetic for key in (target.operations or ("",))}
    paragraphs = [span for span in inspection.paragraphs if span.text.strip()]
    added = 0

    def rebind(target: Target, rule: dict, quote: str) -> bool:
        keys = [str(operation.get("old_text") or "")
                for operation in rule.get("operations") or []
                if operation.get("op") in {"delete", "replace"}
                and condition_matches(operation.get("condition"), facts)
                and len(_compact(str(operation.get("old_text") or ""))) >= 8]
        if _compact(quote):
            keys.sort(key=lambda value: (0 if _compact(value) == _compact(quote) else 1,
                                         -len(_compact(value))))
        unique_keys: list[str] = []
        for key in keys:
            if _compact(key) not in {_compact(item) for item in unique_keys}:
                unique_keys.append(key)
        for key in unique_keys:
            for candidate in _operation_fingerprints(key):
                occurrences = find_old_text_all(paragraphs, candidate)
                for parts in occurrences:
                    locations = [item[0] for item in parts]
                    if target.location not in locations or len(locations) == 1:
                        continue
                    target.composite = tuple(f"{location}:{start}:{end}"
                                             for location, start, end in parts)
                    target.resolution = "composite"
                    target.start, target.end = parts[0][1], parts[0][2]
                    target.reason = f"sweep:{quote[:40]}" if quote else target.reason
                    origins[target.target_id] = "sweep_rebind"
                    return True
        return False

    for finding in pending:
        rule_id = str(finding.get("rule_id") or "")
        quote = str(finding.get("quote") or "")
        if len(_compact(quote)) < 4:
            continue
        rule = rules_by_id.get(rule_id)
        if rule is None:
            continue
        operation_id = finding_operation(rule, quote)
        if not operation_id:
            operation_id = unique_applicable_operation(rule)
        key = identity(rule_id, operation_id, finding["location"])
        matched = next((target for target in targets
                        if target.rule_id == rule_id
                        and target.location == finding["location"]
                        and not target.out_of_scope
                        and (not operation_id or not target.operations
                             or operation_id in target.operations)),
                        None)
        if matched is not None:
            if operation_id and not matched.operations:
                matched.operations = (operation_id,)
            if matched.state == "needs_edit" and rebind(matched, rule, quote):
                added += 1
                continue
            # An inventory target may have been marked absent/not_applicable because
            # its quote differs from the guide wording.  The sweep has now supplied a
            # verified source quote at this exact site.  Preserve the old ledger row
            # for traceability, but create an executable operation-specific target.
            if operation_id and matched.state == "absent":
                repair = _make_synthetic_target(
                    f"A{len(synthetic) + 1:03d}", rule_id, finding["location"], quote,
                    f"sweep_variant:{finding['issue']}", inspection)
                if repair is not None:
                    repair.operations = (operation_id,)
                    matched.out_of_scope = True
                    matched.reason = f"{matched.reason}|SUPERSEDED_BY_SWEEP_VARIANT"
                    synthetic.append(repair)
                    origins[repair.target_id] = "sweep_variant"
                    existing.add(identity(rule_id, operation_id, finding["location"]))
                    added += 1
            continue
        if key in existing:
            continue
        if operation_id and identity(rule_id, operation_id,
                                     finding["location"]) in existing:
            continue
        # Different operations/rules at the same paragraph are independent.  The old
        # location-only dedupe prevented G17 from creating a repair target merely
        # because G16 already owned p822; operation identity is now part of the key.
        target = _make_synthetic_target(f"A{len(synthetic) + 1:03d}", rule_id,
                                        finding["location"], quote,
                                        f"sweep:{finding['issue']}", inspection)
        if target is None:
            continue
        if operation_id:
            target.operations = (operation_id,)
        rebind(target, rule, quote)
        synthetic.append(target)
        origins[target.target_id] = "sweep"
        existing.add(key)
        added += 1
    return added


# ---------------------------------------------------------------------------
# Final sweep
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Chunk:
    id: str
    locations: tuple[str, ...]
    text: str


def _artifact_chunks(actual: DocumentInspection, *, max_chars: int) -> list[_Chunk]:
    chunks: list[_Chunk] = []
    lines: list[str] = []
    locations: list[str] = []
    total = 0

    def emit() -> None:
        nonlocal lines, locations, total
        if lines:
            chunks.append(_Chunk(id=f"C{len(chunks) + 1:03d}", locations=tuple(locations),
                                 text="\n".join(lines)))
            lines, locations, total = [], [], 0

    for span in actual.paragraphs:
        zone = span.logical_zone or span.zone
        if zone not in READABLE_ZONES:
            continue
        cleaned, _ = display_text(span.text)
        line = f"[{span.location}] {cleaned}"
        if lines and total + len(line) + 1 > max_chars:
            emit()
        lines.append(line)
        locations.append(span.location)
        total += len(line) + 1
    emit()
    return chunks


def _section_aware_chunks(actual: DocumentInspection, sections: Sequence[Any],
                          *, max_chars: int) -> list[_Chunk]:
    """Chunk the artifact by section first, char-splitting only when a section overflows.

    The final sweep used a pure character window (``_artifact_chunks``), so one window
    could straddle several unrelated sections — the model was asked to judge "收益分配"
    paragraphs against 清算 rules, and a clause cut across two windows lost its context
    (FL-D109 step 2). Section-aligned windows make the unit of judgement the business unit.

    Two properties keep this from opening the coverage hole that a naive section split
    would create:

    * a section longer than ``max_chars`` is split **inside** the section, so no section
      ever exceeds the context budget;
    * paragraphs that belong to **no** section (``structure_index`` caps at 80 sections,
      so trailing content can be unassigned) are collected into character windows at the
      end, so no readable paragraph is ever left unswept.
    """
    section_of: dict[str, str] = {}
    order: list[str] = []
    for section in sections:
        for location in section.locations:
            if location not in section_of:
                section_of[location] = section.id
        order.append(section.id)

    def spans_for(locations: Sequence[str]) -> list[tuple[str, str]]:
        out = []
        for location in locations:
            try:
                span = actual.by_location(location)
            except DocxError:
                continue
            if (span.logical_zone or span.zone) not in READABLE_ZONES:
                continue
            cleaned, _ = display_text(span.text)
            out.append((location, cleaned))
        return out

    def emit_section(section_id: str, spans: list[tuple[str, str]]) -> list[_Chunk]:
        """Split one section's paragraphs into windows no longer than max_chars."""
        out: list[_Chunk] = []
        lines: list[str] = []
        locations: list[str] = []
        total = 0

        def flush() -> None:
            nonlocal lines, locations, total
            if lines:
                out.append(_Chunk(id=section_id, locations=tuple(locations),
                                  text="\n".join(lines)))
                lines, locations, total = [], [], 0

        for location, cleaned in spans:
            line = f"[{location}] {cleaned}"
            if lines and total + len(line) + 1 > max_chars:
                flush()
            lines.append(line)
            locations.append(location)
            total += len(line) + 1
        flush()
        return out

    # Pack whole sections into a window until the next section would overflow the budget.
    # This keeps section boundaries intact (a window never splits a section unless that
    # section alone is too big) while avoiding one model call per small section.
    by_section: dict[str, list[tuple[str, str]]] = {section_id: [] for section_id in order}
    unassigned: list[tuple[str, str]] = []
    for span in actual.paragraphs:
        zone = span.logical_zone or span.zone
        if zone not in READABLE_ZONES:
            continue
        cleaned, _ = display_text(span.text)
        section_id = section_of.get(span.location)
        if section_id is None:
            unassigned.append((span.location, cleaned))
        else:
            by_section[section_id].append((span.location, cleaned))

    grouped: list[tuple[list[str], list[tuple[str, str]]]] = []
    current_ids: list[str] = []
    current_spans: list[tuple[str, str]] = []
    current_chars = 0
    for section_id in order:
        spans = by_section[section_id]
        if not spans:
            continue
        section_chars = sum(len(cleaned) + len(location) + 4 for location, cleaned in spans)
        if current_spans and current_chars + section_chars > max_chars:
            grouped.append((current_ids, current_spans))
            current_ids, current_spans, current_chars = [], [], 0
        current_ids.append(section_id)
        current_spans.extend(spans)
        current_chars += section_chars
    if current_spans:
        grouped.append((current_ids, current_spans))

    chunks: list[_Chunk] = []
    for _ids, spans in grouped:
        chunks.extend(emit_section("C", spans))
    if unassigned:
        chunks.extend(emit_section("unassigned", unassigned))
    for index, chunk in enumerate(chunks, start=1):
        chunks[index - 1] = _Chunk(id=f"C{index:03d}", locations=chunk.locations,
                                   text=chunk.text)
    return chunks


def _sweep_requirements(rules: Sequence[dict]) -> str:
    lines = ["GUIDE_REQUIREMENTS"]
    for rule in rules:
        lines.append(f"[{rule['rule_id']}] {rule.get('title') or ''} | "
                     f"section_hint={rule.get('section_hint') or ''}")
        lines.append(f"  requirement: {_clip(str(rule.get('requirement') or ''), 400)}")
        for operation in rule.get("operations") or []:
            kind = operation.get("op")
            if kind == "append":
                lines.append(f"  append: {_clip(str(operation.get('new_text') or ''), 400)}")
            elif kind == "replace":
                lines.append(f"  replace: {_clip(str(operation.get('old_text') or ''), 160)} -> "
                             f"{_clip(str(operation.get('new_text') or ''), 400)}")
            elif kind == "delete":
                lines.append(f"  delete: {_clip(str(operation.get('old_text') or ''), 240)}")
            elif kind == "noop":
                lines.append("  no change required by this branch")
    return "\n".join(lines)


def _sweep_chunk_chars(model: Any, requirements: str, facts_text: str = "") -> int:
    """Chunk budget: the spec's context-4000, tightened by everything else in the call.

    The sweep context is ``[GUIDE_REQUIREMENTS] + [FACTS] + [ARTIFACT_WINDOW]`` joined with
    separators, so the window budget must subtract the requirements, the facts block and
    the fixed headings. Ignoring the facts block let long contracts build a context above
    ``max_context_chars`` and fail the whole run closed with MODEL_CONTEXT_LIMIT.
    """
    limit = model.max_context_chars
    overhead = len(requirements) + len(facts_text) + _SWEEP_CONTEXT_OVERHEAD
    if overhead + MIN_CHUNK_CHARS > limit:
        raise RecallError("RECALL_SWEEP_CONTEXT_LIMIT",
                          {"requirements_chars": len(requirements),
                           "facts_chars": len(facts_text), "limit": limit})
    return max(MIN_CHUNK_CHARS, min(limit - 4000, limit - overhead))


def _take_batch(chunks: Sequence[_Chunk], remaining: int, gaps: list[dict[str, Any]],
                *, planned: int) -> list[_Chunk]:
    def record_gap(skipped: Sequence[_Chunk]) -> None:
        if any(gap["code"] == "SWEEP_CHUNK_LIMIT" for gap in gaps):
            return  # one gap record is enough; the cap itself is the finding
        gaps.append({"code": "SWEEP_CHUNK_LIMIT", "planned_chunks": planned, "remaining": remaining,
                     "skipped_chunks": len(skipped),
                     "skipped_locations": [loc for chunk in skipped for loc in chunk.locations][:40]})

    if remaining <= 0:
        if chunks:
            record_gap(chunks)
        return []
    batch = list(chunks[:remaining])
    if len(chunks) > remaining:
        record_gap(chunks[remaining:])
    return batch


def weak_rule_signals(rule: dict, facts: Facts, operations: Sequence[dict]) -> list[str]:
    """Semantic (non-hard-fact) reasons the engine would once have called a rule out of scope.

    These deliberately **do not** drop a target or a model finding (FL-D106). They are
    surfaced as ``weak:<signal>`` flags so a later review step can see where the guide's
    class model did not fit the product — the very cases that need human adjudication.
    """
    from .recall import (class_substitution_letter_stable, class_substitution_noop,
                         fee_homogeneous_classes, slot_group_missing)
    signals: list[str] = []
    if slot_group_missing(rule, operations, facts):
        signals.append("slot_group_missing")
    if class_substitution_noop(rule, facts) and not class_substitution_letter_stable(rule, facts):
        signals.append("class_substitution_noop")
    if fee_homogeneous_classes(facts):
        signals.append("fee_homogeneous_classes")
    return signals


_DOCUMENT_COMPACT_CACHE: dict[int, str] = {}


def _document_compact(actual: DocumentInspection) -> str:
    """Whitespace-free artifact text for diagnostics and deterministic projection."""
    key = id(actual)
    cached = _DOCUMENT_COMPACT_CACHE.get(key)
    if cached is None:
        cached = "".join(_compact(display_text(span.text)[0]) for span in actual.paragraphs)
        _DOCUMENT_COMPACT_CACHE.clear()
        _DOCUMENT_COMPACT_CACHE[key] = cached
    return cached


def _rule_mapped_locations(rule_id: str, mapping: dict[str, list[str]],
                           sections: Sequence[Any]) -> set[str]:
    """Every paragraph location of the sections a rule is mapped to (FL-D052)."""
    by_id = {section.id: section for section in sections}
    found: set[str] = set()
    for section_id in mapping.get(rule_id) or []:
        section = by_id.get(section_id)
        if section is not None:
            found.update(section.locations)
    return found


# Split a window that provably cannot be swept in one answer (FL-D108). The sweep's
# output (findings) scales with how many violations the window holds, not with its input
# size, so a dense stretch of a long contract can exhaust the output cap even though the
# context fits. Halving the window narrows both the search space and the answer.
_SWEEP_MIN_SPLIT_CHARS = 400


def _split_chunk(chunk: _Chunk, *, min_chars: int = _SWEEP_MIN_SPLIT_CHARS) -> list[_Chunk]:
    """Halve a sweep window on whole paragraphs, keeping paragraph addresses stable.

    Returns one or two chunks; a window that is already a single paragraph, or shorter
    than ``min_chars``, cannot be usefully reduced and is returned unchanged — which lets
    the caller record a real gap instead of splitting forever.
    """
    lines = chunk.text.split("\n")
    if len(lines) < 2 or len(chunk.text) <= min_chars:
        return [chunk]
    cut = max(1, len(lines) // 2)
    pieces = [lines[:cut], lines[cut:]]
    out: list[_Chunk] = []
    for part in pieces:
        locations = tuple(line.split("]", 1)[0][1:] for line in part if line.startswith("["))
        out.append(_Chunk(id=chunk.id, locations=locations, text="\n".join(part)))
    return out


def _sweep_chunks(actual: DocumentInspection, sections: Sequence[Any], *, max_chars: int) -> list[_Chunk]:
    """The one chunking the sweep uses, initial and incremental (FL-D109).

    Both sweep passes must window the artifact the same way: the incremental re-sweep
    decides which windows are "changed" by comparing chunk text against what was already
    swept, so a second chunker would make an unchanged window look new (or a changed one
    look unchanged). Keeping the choice in one place also keeps the section-first switch
    honest for re-sweeps.
    """
    if os.environ.get("FUNDLEX_SWEEP_SECTION_WINDOWS", "0") == "1":
        return _section_aware_chunks(actual, sections, max_chars=max_chars)
    return _artifact_chunks(actual, max_chars=max_chars)


def _sweep_requirements_for(rules: Sequence[dict], rule_ids: set[str]) -> str:
    """Requirements block restricted to the rules a window can actually be about."""
    subset = [rule for rule in rules if str(rule.get("rule_id")) in rule_ids]
    return _sweep_requirements(subset)


def _window_rule_scope(chunks: Sequence[_Chunk], *, mapping: dict[str, list[str]],
                       sections: Sequence[Any], rules: Sequence[dict],
                       mandatory: set[str],
                       blind_windows: list[dict[str, Any]] | None = None,
                       scopes: Mapping[str, Any] | None = None
                       ) -> list[tuple[_Chunk, set[str]]]:
    """Pair each sweep window with the guide rules that can apply inside it (FL-D109).

    The final sweep used to hand **every** guide rule to **every** window: a window over
    the 收益分配 section was asked to judge 清算 and 申购费 rules too, so the model
    reported noise the code then discarded (round 9: ``SWEEP_LOCATION_OUT_OF_SCOPE`` 362
    times) and the requirements block was re-sent once per window (D09: 10 times).

    A window only needs the rules whose mapped sections it contains. Two guards keep that
    scoping from opening a hole in the "不能漏判" requirement:

    * ``mandatory`` — a rule that still has an unmet target anywhere in the document is
      forced into every window its mapped sections touch, even if the target ledger and
      the section mapping disagree (the mapping is model-produced and can be wrong);
    * a rule whose mapped sections no window touches is attached to **every** window, so
      a mapping miss degrades to the old behaviour instead of silently skipping the rule.

    When ``scopes`` (``rule_id -> RuleScope``) is supplied, a rule is attached only to a
    window that physically overlaps its resolved scope. The section-mapping fallbacks —
    including blind and unreachable windows — are **not** applied: those windows are
    recorded as skipped instead of receiving rules they cannot legally judge. This keeps
    the sweep from turning a mapping error into an out-of-scope finding.
    """
    if scopes is not None:
        by_rule = {str(rule_id): scope for rule_id, scope in scopes.items()}
        scoped: list[tuple[_Chunk, set[str]]] = []
        for chunk in chunks:
            chunk_locations = {str(location) for location in chunk.locations}
            ids = {rule_id for rule_id, scope in by_rule.items()
                   if set(getattr(scope, "locations", ()) or ()) & chunk_locations}
            if not ids and blind_windows is not None:
                blind_windows.append({"chunk": chunk.id, "locations": list(chunk.locations),
                                      "skipped": "OUT_OF_RULE_SCOPE"})
            scoped.append((chunk, ids))
        return scoped

    by_section = {section.id: section for section in sections}
    location_to_section: dict[str, str] = {}
    for section in sections:
        for location in section.locations:
            location_to_section.setdefault(location, section.id)

    covered: set[str] = set()
    scoped: list[tuple[_Chunk, set[str]]] = []
    for chunk in chunks:
        window_sections = {location_to_section[loc] for loc in chunk.locations
                           if loc in location_to_section}
        ids = {rule_id for rule_id, mapped in mapping.items() if set(mapped) & window_sections}
        # A rule with an outstanding target is forced in whenever this window overlaps
        # the sections it is mapped to, even if the window's own section set and the
        # mapping disagree about the finer boundaries.
        ids |= {rule_id for rule_id in mandatory if set(mapping.get(rule_id) or []) & window_sections}
        covered.update(ids)
        if not ids:
            # A window whose sections no rule is mapped to used to be swept with an
            # empty requirements block; every finding in it was then dropped as
            # out-of-window (FL-D113). The final sweep exists to find unknown misses,
            # so a zero-rule window falls back to the full guide rather than only the
            # rules that already have a known unmet target. Only these windows pay the
            # cost; mapped windows keep the FL-D109 scoping.
            all_rule_ids = {str(rule.get("rule_id")) for rule in rules}
            if blind_windows is not None:
                blind_windows.append({"chunk": chunk.id, "locations": list(chunk.locations),
                                      "fallback_rules": sorted(all_rule_ids)})
            ids = all_rule_ids
        scoped.append((chunk, ids))

    unreachable = {str(rule.get("rule_id")) for rule in rules} - covered
    if unreachable:
        scoped = [(chunk, ids | unreachable) for chunk, ids in scoped]
    # A mandatory rule the section mapping never reaches anywhere must still be asked:
    # losing it would drop a known unmet obligation, so attach it to every window.
    still_missing = mandatory - {rule_id for _, ids in scoped for rule_id in ids}
    if still_missing:
        scoped = [(chunk, ids | still_missing) for chunk, ids in scoped]
    return scoped


def _sweep_scope_plan(chunks: Sequence[_Chunk], *, scopes: Mapping[str, Any] | None,
                      mapping: dict[str, list[str]], sections: Sequence[Any],
                      rules: Sequence[dict], mandatory: set[str],
                      blind_windows: list[dict[str, Any]] | None
                      ) -> tuple[list[_Chunk], dict[str, str], dict[str, set[str]]]:
    """Window plan for the scope-aware sweep.

    With ``scopes`` supplied, windows no rule is scoped into are dropped from the batch
    (recorded in ``blind_windows``) instead of being sent the whole guide.
    """
    scoped = _window_rule_scope(chunks, mapping=mapping, sections=sections, rules=rules,
                                mandatory=mandatory, blind_windows=blind_windows,
                                scopes=scopes)
    if scopes is None:
        return (list(chunks),
                {chunk.id: _sweep_requirements_for(rules, ids) for chunk, ids in scoped},
                {chunk.id: ids for chunk, ids in scoped})
    live = [chunk for chunk, ids in scoped if ids]
    return (live,
            {chunk.id: _sweep_requirements_for(rules, ids) for chunk, ids in scoped if ids},
            {chunk.id: ids for chunk, ids in scoped if ids})


def _scope_correction_valid(rule: dict, span: Any, quote: str,
                            actual: DocumentInspection) -> bool:
    """Scope is routing only; prove an outside candidate against its business rule."""
    from .recall import target_site_ok
    rule_id = str(rule.get("rule_id") or "")
    if not target_site_ok(rule_id, span, actual):
        return False
    if rule_id in {"G01", "G03", "G16"}:
        return True
    quoted = _compact(quote)
    references = [str(operation.get("old_text") or "")
                  for operation in rule.get("operations") or []]
    references.extend(str(value) for value in rule.get("old_text_variants") or [])
    return any(len(_compact(reference)) >= 8 and
               (_compact(reference) in quoted or
                len(quoted) >= 8 and quoted in _compact(reference)) for reference in references)


def _sweep_batch(model: Any, rules_by_id: dict[str, dict], requirements: str,
                 chunks: Sequence[_Chunk], actual: DocumentInspection, *,
                 round_number: int, counter: list[int], facts: Facts | None = None,
                 facts_text: str = "", rule_locations: dict[str, set[str]] | None = None,
                 requirements_by_chunk: dict[str, str] | None = None,
                 scope_by_chunk: dict[str, set[str]] | None = None,
                 scopes: Mapping[str, Any] | None = None,
                 scope_audit: dict[str, Any] | None = None
                 ) -> dict[str, Any]:
    """Sweep every window, splitting a window whose answer hits the output cap (FL-D108).

    Each window is swept independently; a window the provider cut off at the output limit
    is replaced by two smaller windows and swept again, so a dense stretch of a long
    contract yields partial findings instead of failing the whole contract. A window that
    is already a single paragraph cannot be split and is recorded as an honest gap.
    """
    ledger: dict[str, Any] = {"round": round_number, "chunks": [], "findings": [],
                              "dropped": [], "calls": 0}
    seen: set[tuple[str, str, str]] = set()
    pending: list[_Chunk] = list(chunks)
    while pending:
        chunk = pending.pop(0)
        window_requirements = (requirements_by_chunk or {}).get(chunk.id, requirements)
        window_scope = (scope_by_chunk or {}).get(chunk.id)
        preamble = [f"[GUIDE_REQUIREMENTS]\n{window_requirements}"]
        if facts_text:
            preamble.append(f"[FACTS]\n{facts_text}")
        context = "\n\n".join(preamble + [f"[ARTIFACT_WINDOW]\n{chunk.text}"])
        try:
            call = model.call(task_type="recall_sweep", bounded_context=context,
                              response_schema=SWEEP_SCHEMA,
                              instruction=SWEEP_INSTRUCTION, prompt_version=SWEEP_PROMPT_VERSION)
        except ModelError as exc:
            if exc.code != "MODEL_OUTPUT_TRUNCATED":
                raise
            pieces = _split_chunk(chunk)
            if len(pieces) == 1:
                # A single paragraph already exhausts the output cap: splitting cannot
                # help. Record an honest gap instead of looping or dropping it silently.
                ledger.setdefault("truncated", []).append(
                    {"chunk": chunk.id, "locations": list(chunk.locations)})
                continue
            ledger.setdefault("splits", []).append(
                {"chunk": chunk.id, "locations": list(chunk.locations),
                 "into": [list(piece.locations) for piece in pieces]})
            pending = pieces + pending
            continue
        ledger["calls"] += 1
        value = call.value if isinstance(call.value, dict) else {}
        chunk_locations = set(chunk.locations)
        chunk_ledger: dict[str, Any] = {"chunk": chunk.id, "locations": list(chunk.locations),
                                        "findings": [], "dropped": []}
        for item in value.get("findings") or []:
            if not isinstance(item, dict):
                chunk_ledger["dropped"].append({"code": "SWEEP_ITEM_INVALID", "chunk": chunk.id})
                continue
            rule_id = str(item.get("rule_id") or "")
            location = str(item.get("location") or "")
            quote = str(item.get("quote") or "")
            issue = str(item.get("issue") or "")
            key = (rule_id, location, _compact(quote))
            outside_window = window_scope is not None and rule_id not in window_scope
            if rule_id not in rules_by_id or location not in chunk_locations or issue not in SWEEP_ISSUES:
                chunk_ledger["dropped"].append({"code": "SWEEP_FINDING_INVALID", "chunk": chunk.id,
                                                "rule_id": rule_id, "location": location, "issue": issue})
                continue
            if not quote or _compact(quote) not in _compact(chunk.text):
                chunk_ledger["dropped"].append({"code": "SWEEP_QUOTE_NOT_IN_WINDOW", "chunk": chunk.id,
                                                "rule_id": rule_id, "location": location,
                                                "quote": _clip(quote, 80)})
                continue
            if key in seen:
                continue
            try:
                span = actual.by_location(location)
            except DocxError:
                span = None
            located = (resolve_quote(span, quote) if span is not None and
                       _compact(quote) in _compact(span.text) else None)
            if located is None:
                chunk_ledger["dropped"].append({"code": "SWEEP_QUOTE_NOT_RESOLVED", "chunk": chunk.id,
                                                "rule_id": rule_id, "location": location,
                                                "quote": _clip(quote, 80)})
                continue
            seen.add(key)
            rule = rules_by_id.get(rule_id) or {}
            paragraph_text = span.text if span is not None else ""
            if scopes is not None:
                # Fail closed: a finding outside the rule's resolved physical scope is
                # discarded, never accepted through the section-mapping correction path.
                scope = scopes.get(rule_id)
                if scope is None or not scope.contains(location):
                    chunk_ledger["dropped"].append({
                        "code": "OUT_OF_RULE_SCOPE",
                        "subcode": "SWEEP_LOCATION_OUT_OF_SCOPE",
                        "chunk": chunk.id, "rule_id": rule_id,
                        "location": location, "quote": _clip(quote, 80)})
                    _record_scope_drop(scope_audit, stage="sweep", rule_id=rule_id,
                                       location=location)
                    continue
                scope_correction = False
            else:
                allowed = (rule_locations or {}).get(rule_id)
                scope_correction = outside_window or (
                    allowed is not None and location not in allowed)
            # A mapped window is not proof that the quote carries this rule's
            # business clause. Keep unknown wording candidates when the semantic
            # site anchor fits; outside-scope candidates still need the stronger
            # existing reference/variant check before correcting the routing.
            from .recall import target_site_ok
            if not target_site_ok(rule_id, span, actual):
                chunk_ledger["dropped"].append({"code": "SWEEP_SEMANTIC_SITE_INVALID",
                                                "chunk": chunk.id, "rule_id": rule_id,
                                                "location": location, "quote": _clip(quote, 80)})
                continue
            if scope_correction and not _scope_correction_valid(rule, span, quote, actual):
                chunk_ledger["dropped"].append({"code": "SWEEP_LOCATION_OUT_OF_SCOPE",
                                                "chunk": chunk.id, "rule_id": rule_id,
                                                "location": location, "quote": _clip(quote, 80)})
                continue
            if facts is not None:
                applicable = [operation for operation in (rule.get("operations") or [])
                              if condition_matches(operation.get("condition"), facts)]
                statuses = [condition_status(operation.get("condition"), facts)
                            for operation in rule.get("operations") or []]
                if statuses and all(status == "FALSE" for status in statuses) or (
                        applicable and all(operation.get("op") == "noop" for operation in applicable)):
                    chunk_ledger["dropped"].append({"code": "SWEEP_RULE_NOT_APPLICABLE",
                                                    "chunk": chunk.id, "rule_id": rule_id,
                                                    "location": location, "quote": _clip(quote, 80)})
                    continue
            counter[0] += 1
            chunk_ledger["findings"].append({
                "finding_id": f"SW{counter[0]:03d}", "rule_id": rule_id, "location": location,
                "source_location": location, "quote": quote, "issue": issue,
                "reason": str(item.get("reason") or ""), "artifact_start": located[0],
                "artifact_end": located[1], "chunk": chunk.id, "round": round_number,
                "failure_class": str(item.get("failure_class") or ""),
                "routing_status": "SCOPE_CORRECTION_TARGET" if scope_correction else "MAPPED_TARGET",
                "status": "pending",
            })
        ledger["chunks"].append(chunk_ledger)
        ledger["findings"].extend(chunk_ledger["findings"])
        ledger["dropped"].extend(chunk_ledger["dropped"])
    return ledger


_DELIVERY_BLOCKER_CODES = frozenset({
    "RESIDUAL_OLD_TEXT", "CLAIM_NO_CHANGE_APPLIED", "CLAIM_LOCATION_MISSING",
    "CLAIM_REPLACEMENT_MISSING", "CLAIM_VALIDATION_FAILED",
    "MODEL_RETRY_EXHAUSTED", "MODEL_SCHEMA_INVALID", "MODEL_ERROR",
    "DOCUMENT_PROTECTED", "OUTPUT_WRITE_FAILED", "REPORT_WRITE_FAILED",
    "FINAL_HASH_MISMATCH", "RECALL_EDIT_OVERLAP", "EDIT_OVERLAP",
})
_DELIVERY_BLOCKER_REASON_MARKERS = (
    "RESIDUAL_CONFIRMED", "CLASS_SET_INCOMPLETE",
)
_BUSINESS_PENDING_MARKERS = (
    "FACT_PREREQUISITE_UNVERIFIED", "RECALL_FACT_UNVERIFIED", "FUND_TYPE_UNVERIFIED",
)
_BUSINESS_PENDING_RULES = frozenset({"G14", "G18"})
#: Final omission issues that prove a missing/duplicated effect.  Coverage rows for
#: an unfinished audit or a capped sweep stay review items under review_assisted.
_FINAL_OMISSION_BLOCKER_CODES = frozenset({
    "FINAL_OPERATION_UNPROVEN", "FINAL_RESIDUAL_OLD_TEXT",
})


def _final_omission_issue_blocks(issue: Mapping[str, Any]) -> bool:
    """Whether one final omission issue is a provable delivery failure."""
    code = str(issue.get("code") or "")
    reason = str(issue.get("reason") or "")
    if code in _FINAL_OMISSION_BLOCKER_CODES:
        return True
    # A coverage row that says a Claim Replay failure left an operation unresolved is
    # a proof failure, not an unfinished review.  Audit/sweep-cap rows stay reviewable.
    return code == "FINAL_COVERAGE_UNRESOLVED" and "CLAIM_" in reason


def _delivery_policy() -> str:
    value = os.environ.get("FUNDLEX_DELIVERY_POLICY", "review_assisted")
    return "strict" if value.strip().lower() == "strict" else "review_assisted"


def _classify_delivery_items(unresolved: Sequence[dict[str, Any]]
                             ) -> tuple[list[dict[str, Any]], list[dict[str, Any]],
                                        list[dict[str, Any]]]:
    """Split the unresolved projection into blockers, review items and business items.

    ``review_assisted`` delivery publishes the pair when nothing is provably wrong:
    unproven sites, audit gaps and orphan evidence become an explicit human-review
    list instead of a refusal.  A residual old sentence at an edited site, a missing
    change, or a failed model/write call still blocks.  Business-undecided rules are
    kept in their own bucket and never auto-applied.
    """
    blockers: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    business: list[dict[str, Any]] = []
    for item in unresolved:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "")
        code = str(item.get("code") or item.get("kind") or "")
        reason = str(item.get("reason") or "")
        if (rule_id in _BUSINESS_PENDING_RULES
                or any(marker in reason for marker in _BUSINESS_PENDING_MARKERS)):
            business.append(item)
        elif (bool(item.get("claim_replay_failed"))
              or str(item.get("kind") or "") == "claim_replay"
              or (str(item.get("kind") or "") == "final_omission"
                  and _final_omission_issue_blocks(item))
              or code in _DELIVERY_BLOCKER_CODES or reason in _DELIVERY_BLOCKER_CODES
              or any(marker in reason for marker in _DELIVERY_BLOCKER_REASON_MARKERS)):
            # A failed Claim Replay or a proven final omission is not a human-review
            # opinion.  It must block delivery in every policy (D06 false-complete).
            blockers.append(item)
        else:
            review.append(item)
    return blockers, review, business


def _delivery_complete(unresolved: Sequence[dict[str, Any]], *, ledger: Any = None,
                       policy: str | None = None,
                       claim_replay_verified: bool | None = None,
                       final_omission_blocking: bool | None = None) -> bool:
    """Whether the produced pair may be published.

    ``strict`` keeps the historical rule: every unresolved item blocks.  The default
    ``review_assisted`` policy only blocks items that are provably wrong (residual old
    text at an edited site, missing change, failed model/write call); everything else
    is delivered together with a human-review list.

    Independent proof layers always block, whatever the policy: a failed Claim Replay,
    a proven final omission, or an open obligation whose own evidence is a Claim
    Replay failure.  An unfinished audit/sweep or an unverified fact stays a review
    item under ``review_assisted``; it is still an open Ledger record and blocks
    ``strict`` delivery.
    """
    mode = policy or _delivery_policy()
    if ledger is not None:
        from .obligations import open_obligations
        # The Ledger owns business completion.  The unresolved argument is only
        # its diagnostic projection plus orphan/resource blockers, so it may
        # never close an open record and it still blocks an unbound evidence row.
        open_items = open_obligations(ledger)
        if open_items:
            if mode == "strict":
                return False
            if any("CLAIM_" in str(item.get("reason") or "") for item in open_items):
                return False
    if claim_replay_verified is False:
        return False
    if final_omission_blocking:
        return False
    if mode == "strict":
        return not unresolved
    blockers, _review, _business = _classify_delivery_items(unresolved)
    return not blockers


def _final_omission_review(*, rules_by_id: Mapping[str, dict], rules: Sequence[dict],
                           original: DocumentInspection, actual: DocumentInspection,
                           planned: Mapping[str, Any], targets: Sequence[Target],
                           facts: Facts, obligations: Any, replay: Mapping[str, Any],
                           findings: Sequence[Mapping[str, Any]],
                           coverage_view: Any | None = None,
                           scopes: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Run the last independent, operation-scoped omission review.

    The model sweep deliberately reads the final artifact without the target ledger;
    this deterministic pass is its fail-closed companion.  It checks every applicable
    operation, each artifact proof, and every business-site delete residual.  A rule
    level ``G16 processed`` flag can therefore never hide an unproven ``G16:2`` at a
    second site.
    """
    from .generation.effects import effect_proof_passed
    from .generation.claim_replay import check_delete_residuals

    issues: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    proofs = replay.get("obligations") or {}
    for record in getattr(obligations, "records", ()):
        if getattr(record.applicability, "status", "") != "TRUE":
            continue
        operation_id = str(record.spec.operation_id)
        proof = proofs.get(record.obligation_id)
        sites = tuple(str(site) for site in (proof or {}).get("sites") or ())
        checked.append({"rule_id": record.spec.rule_id,
                        "operation_id": operation_id,
                        "obligation_id": record.obligation_id,
                        "sites": list(sites),
                        "completion": getattr(record, "completion", "UNRESOLVED")})
        if not effect_proof_passed(proof, operation_id=operation_id,
                                   obligation_id=record.obligation_id):
            issues.append({"code": "FINAL_OPERATION_UNPROVEN",
                           "rule_id": record.spec.rule_id,
                           "operation_id": operation_id,
                           "obligation_id": record.obligation_id,
                           "locations": list(sites),
                           "reason": str((proof or {}).get("reason") or
                                           (proof or {}).get("failure_code") or
                                           "operation effect is not proven at every site")})

    residuals = check_delete_residuals(
        rules_by_id, actual, edits=planned.get("edits") or (), original=original,
        targets=[target.as_dict() for target in targets], facts=facts,
        obligations=obligations, scopes=scopes)
    for residual in residuals:
        issues.append({"code": "FINAL_RESIDUAL_OLD_TEXT", **dict(residual)})
    if getattr(residuals, "truncated", False):
        # A capped residual scan is not proof that nothing is left (FL-D441).
        issues.append({"code": "FINAL_RESIDUAL_SCAN_TRUNCATED",
                       "remaining": getattr(residuals, "remaining", None),
                       "next_cursor": getattr(residuals, "next_cursor", None)})

    # Findings from the independent review model remain visible even when a later
    # artifact proof can explain one of them.  _apply_artifact_proof_to_findings has
    # already marked expected effects as resolved; only pending/unresolved findings
    # are omissions that can block delivery.
    for finding in findings:
        if str(finding.get("status") or "") in {"pending", "unresolved"}:
            issues.append({"code": "FINAL_MODEL_SWEEP_FINDING",
                           "rule_id": str(finding.get("rule_id") or ""),
                           "operation_id": str(finding.get("operation_id") or ""),
                           "location": str(finding.get("location") or ""),
                           "finding_id": str(finding.get("finding_id") or ""),
                           "issue": str(finding.get("issue") or ""),
                           "reason": str(finding.get("reason") or "")})

    if coverage_view is not None:
        for entry in getattr(coverage_view, "unresolved", ()):
            issues.append({"code": "FINAL_COVERAGE_UNRESOLVED",
                           "rule_id": entry.rule_id,
                           "operation_id": (entry.operation_keys[0]
                                             if entry.operation_keys else ""),
                           "location": entry.location,
                           "reason": entry.basis})

    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for issue in issues:
        key = (str(issue.get("code") or ""), str(issue.get("rule_id") or ""),
               str(issue.get("operation_id") or ""), str(issue.get("location") or
                                                          issue.get("obligation_id") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(issue)
    return {"status": "PASS" if not unique else "FAIL",
            "basis": "independent_model_sweep+deterministic_operation_replay",
            "checked_operations": checked,
            "checked_operation_count": len(checked),
            "model_sweep_findings": sum(
                str(item.get("code") or "") == "FINAL_MODEL_SWEEP_FINDING" for item in unique),
            "issues": unique}


def _apply_artifact_proof_to_findings(findings: list[dict[str, Any]], replay: dict[str, Any],
                                      actual: DocumentInspection, obligations: Any,
                                      rules_by_id: dict[str, dict], *, facts: Facts | None = None,
                                      edits: Sequence[dict[str, Any]] = (),
                                      original: DocumentInspection | None = None) -> None:
    """Arbitrate sweep opinions against the same operation's local artifact proof.

    Exact old-effect residuals block. An unsupported removal opinion or a quote of
    authorized new wording cannot overturn a conclusive proof at that same site.
    """
    states = {str(key): value for key, value in (replay.get("obligations") or {}).items()
              if isinstance(value, dict)}
    from .generation.effects import effect_proof_passed
    for finding in findings:
        if finding.get("status") not in {"pending", "unresolved"}:
            continue
        rule_id = str(finding.get("rule_id") or "")
        location = str(finding.get("location") or "")
        operation_id = str(finding.get("operation_id") or "")
        related = []
        related_records = []
        for obligation_id, state in states.items():
            record = obligations.record(obligation_id) if obligations is not None else None
            if (record is not None and record.spec.rule_id == rule_id
                    and (not operation_id or operation_id == record.spec.operation_id)
                    and state.get("operation_id") == record.spec.operation_id
                    and state.get("obligation_id") == record.obligation_id
                    and getattr(getattr(record, "applicability", None), "status", "UNKNOWN") == "TRUE"):
                local = _local_operation_proofs(state, record.spec.operation_id,
                                                record.obligation_id, location)
                if local:
                    related.extend(local)
                    related_records.append(record)
        quote = _compact(str(finding.get("quote") or ""))
        body = artifact_text = source_text = ""
        try:
            artifact_text = str(actual.by_location(location).text)
            body = _compact(artifact_text)
            if original is not None:
                source_text = str(original.by_location(location).text)
        except Exception:  # noqa: BLE001
            body = ""
        residual = bool(quote and quote in body)
        rule = rules_by_id.get(rule_id) or {}
        old_sentences = []
        for operation in rule.get("operations") or []:
            if operation.get("op") not in {"replace", "delete"}:
                continue
            for sentence in re.split(r"(?<=[。；;])",
                                     str(operation.get("old_text") or "")):
                compact = _compact(sentence)
                if len(compact) >= 8:
                    old_sentences.append(compact)
        quote_matches_old = any(
            sentence in quote or (len(quote) >= 8 and quote in sentence)
            for sentence in old_sentences)
        expected_quote = residual and any(_quote_is_expected_effect(
            str(finding.get("quote") or ""), record, facts, edits=edits,
            location=location, before_text=source_text, actual_text=artifact_text, obligations=obligations,
            proofs=states) for record in related_records)
        if residual and quote_matches_old and not expected_quote:
            finding["proof_kind"] = "RESIDUAL_CONFIRMED"
            continue
        if related and all(effect_proof_passed(state) for state in related) \
                and quote and not (residual and quote_matches_old) and _sibling_expected_effect(
                str(finding.get("quote") or ""), location, obligations, states,
                facts=facts, edits=edits, original=original, actual=actual):
            # The finding quotes a sibling operation's authorized final text at the
            # same site; it is not evidence that this rule's old effect survived.
            finding["status"] = "resolved"
            finding["resolution"] = "artifact_proof"
            finding["proof_kind"] = "REVIEW_UNPROVEN"
            finding["resolution_evidence"] = "sibling_authorized_effect"
            continue
        if not related:
            # A sweep can quote a complete policy written by a sibling operation at
            # this physical site. G15 has no surviving source site after its old
            # clause is replaced, while G16 owns and proves the new payment policy.
            if rule_id == "G15" and _sibling_expected_effect(
                    str(finding.get("quote") or ""), location, obligations, states,
                    facts=facts, edits=edits, original=original, actual=actual):
                finding["status"] = "resolved"
                finding["resolution"] = "artifact_proof"
                finding["proof_kind"] = "sibling_authorized_effect"
                finding["resolution_evidence"] = "sibling_operation_site_proof"
                continue
            # An orphan finding can quote authorized new policy and then claim an
            # old clause survived. Check its own quoted old clause against the
            # artifact instead of trusting the prose: if every quoted old fragment
            # is absent, the finding contradicts the file and is not residual
            # evidence. Findings without a quoted old clause, or with any quoted
            # fragment still present, remain blocking.
            claimed = [match.strip() for pattern in (
                r"“([^”]{8,})”", r"「([^」]{8,})」",
                r"'([^']{8,})'", r'"([^"]{8,})"')
                for match in re.findall(pattern, str(finding.get("reason") or ""))]
            # The sweep is free to quote the old clause with any of the four quote
            # styles; a finding that quoted it with ASCII quotes used to fall through
            # to SEMANTIC_UNCERTAIN and become an orphan blocker (恒裕 G15 SW002).
            # Contract text is Chinese, so only claims carrying real CJK characters
            # can be residual evidence.
            claimed = [value for value in claimed if len(_compact(value)) >= 12
                       and len(re.findall(r"[\u4e00-\u9fff]", value)) >= 6]
            # A false positive often quotes the old clause and then also quotes a
            # surviving *new* policy phrase. The longest quoted segment is the
            # claimed old effect; only that one is the residual evidence.
            claimed.sort(key=lambda value: len(_compact(value)), reverse=True)
            if claimed and _compact(claimed[0]) not in body:
                finding["status"] = "resolved"
                finding["resolution"] = "artifact_proof"
                finding["proof_kind"] = "REMOVAL_UNCONFIRMED"
                finding["resolution_evidence"] = "claimed_residual_absent"
                continue
            finding["proof_kind"] = "SEMANTIC_UNCERTAIN"
            continue
        if not all(effect_proof_passed(state) for state in related):
            finding["proof_kind"] = "SEMANTIC_UNCERTAIN"
            continue
        if finding.get("issue") == "wrong_text" and residual and not expected_quote:
            finding["proof_kind"] = "SEMANTIC_UNCERTAIN"
            continue
        statuses = sorted({str(state.get("artifact_status") or "") for state in related})
        finding["status"] = "resolved"
        finding["resolution"] = "artifact_proof"
        finding["resolution_evidence"] = ",".join(statuses)
        finding["proof_kind"] = "REVIEW_UNPROVEN" if expected_quote else "REMOVAL_UNCONFIRMED"


def _resolve_pending(findings: list[dict[str, Any]], batch_ledger: dict[str, Any], *,
                     actual: DocumentInspection | None = None,
                     rules_by_id: dict[str, dict] | None = None,
                     facts: Facts | None = None) -> None:
    """A silent re-sweep is not proof; the shared operation evaluator adjudicates.

    Retain every finding until _apply_artifact_proof_to_findings consumes the new
    artifact's operation/site proofs. Neither the first replacement of a rule nor
    a missing old quote alone can close all its independent requirements.
    """
    for chunk_ledger in batch_ledger.get("chunks") or []:
        locations = set(chunk_ledger["locations"])
        reported = {(item["rule_id"], item["location"]) for item in chunk_ledger["findings"]}
        for finding in findings:
            if finding["status"] != "pending" or finding["location"] not in locations:
                continue
            if (finding["rule_id"], finding["location"]) in reported:
                finding["status"] = "unresolved"
                finding["resolution"] = "still_reported"
            else:
                finding["resolution"] = "model_clean_but_evidence_missing"


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------

def _publish(temp_dir: Path, output_dir: Path, mapping: dict[str, str],
             published: list[Path]) -> None:
    for source_name, target_name in mapping.items():
        target = output_dir / target_name
        os.replace(temp_dir / source_name, target)
        published.append(target)


def _finalize_failure(report: dict[str, Any], published: Sequence[Path]) -> None:
    """Never leave a `final` pair after an error; keep a produced pair as working files."""
    names = {path.name: path for path in published}
    if "final.docx" in names or "redline.docx" in names:
        output_dir = next(iter(names.values())).parent
        for final_name, working_name in (("final.docx", "working_final.docx"),
                                         ("redline.docx", "working_redline.docx")):
            source = names.get(final_name)
            if source is not None and source.exists():
                os.replace(source, source.with_name(working_name))
        artifacts: dict[str, str] = {}
        for key, name in (("working_final", "working_final.docx"),
                          ("working_redline", "working_redline.docx")):
            if (output_dir / name).exists():
                artifacts[key] = name
        report["artifacts"] = artifacts
        report["output_validation"] = {**(report.get("output_validation") or {}),
                                       "kind": "recall_working_edits"}
        report["delivery_status"] = "incomplete"
    elif "working_final.docx" in names:
        report["delivery_status"] = "incomplete"
    else:
        for path in published:
            if path.exists():
                path.unlink(missing_ok=True)
        report["artifacts"] = {}
        report["output_validation"] = {"kind": None, "checks": [], "final_sha256": None,
                                       "redline_sha256": None}
        report["delivery_status"] = "not_generated"


def _target_disposition_counts(targets: Sequence[dict[str, Any]]) -> dict[str, int]:
    """Final, mutually exclusive user-facing target buckets."""
    needs = 0
    satisfied = 0
    absent = 0
    for target in targets:
        status = str(target.get("status") or "")
        state = str(target.get("state") or "")
        out_of_scope = bool(target.get("out_of_scope"))
        if out_of_scope or status == "not_applicable" or state == "absent":
            absent += 1
        elif status in {"planned", "unresolved", "not_planned"}:
            needs += 1
        elif status == "satisfied" or state == "satisfied":
            satisfied += 1
        else:
            # Unknown/no-plan is work still requiring a disposition, never success.
            needs += 1
    return {"targets": len(targets), "needs_edit": needs,
            "satisfied": satisfied, "absent": absent}


def _short_text(value: Any, limit: int = 600) -> str:
    text_value = str(value or "").strip()
    if len(text_value) <= limit:
        return text_value
    return text_value[:limit] + f"…（共 {len(text_value)} 字）"


def _rule_meta(guide_groups: Mapping[str, Mapping[str, Any]], rule_id: str) -> tuple[str, str]:
    titles: list[str] = []
    requirements: list[str] = []
    for part in str(rule_id or "").split("+"):
        group = guide_groups.get(part) or {}
        title = str(group.get("title") or "").strip()
        requirement = str(group.get("requirement") or "").strip()
        if title:
            titles.append(title)
        if requirement:
            requirements.append(requirement)
    return "；".join(titles) or str(rule_id or ""), " ".join(requirements)


def _edit_proof_label(replay: Mapping[str, Any], edit: Mapping[str, Any]) -> str:
    obligations = replay.get("obligations") or {}
    states = [obligations[key] for key in (edit.get("obligation_ids") or ())
              if isinstance(obligations.get(key), Mapping)]
    if not states:
        return "未绑定证明（列入人工复核）"
    if all(state.get("state") == "PASS" for state in states):
        status = "、".join(sorted({str(state.get("artifact_status") or "") for state in states}))
        return f"已证明（{status or 'PASS'}）"
    status = "、".join(sorted({str(state.get("artifact_status") or "UNPROVEN") for state in states}))
    return f"未证明（{status}，列入人工复核）"


def _readable_reason(value: Any) -> str:
    text = str(value or "")
    if text.startswith(("T3_open_operation", "survey_reference", "claim_residual",
                        "duplicate_copy")) or "locator:" in text:
        return "已满足，无需修改"
    return _short_text(text, 160)


def _readable_item(item: Mapping[str, Any]) -> str:
    from .delivery import failure_reason
    rule_id = str(item.get("rule_id") or "")
    location = str(item.get("location") or "")
    if not location:
        sites = item.get("sites") or item.get("locations") or []
        location = "、".join(str(site) for site in sites) or "（整条规则）"
    code = str(item.get("code") or item.get("kind") or "")
    operation = str(item.get("operation_id") or "")
    reason = item.get("reason") or item.get("issue") or item.get("message") or ""
    label = f"{rule_id} {operation}".strip() if operation else rule_id
    concise = failure_reason(code) or failure_reason(reason) or code
    return f"{label} {location}：{concise} — {_short_text(reason, 200)}"


def _report_markdown(report: dict[str, Any]) -> str:
    plan = report.get("plan") or {}
    edits = [dict(item) for item in (plan.get("edits") or []) if isinstance(item, Mapping)]
    targets = [item for item in (report.get("targets") or []) if isinstance(item, Mapping)]
    guide_groups = {str(group.get("rule_id")): group
                    for group in ((report.get("guide") or {}).get("groups") or [])
                    if isinstance(group, Mapping)}
    replay = report.get("artifact_claim_replay") or {}
    unresolved = [item for item in (report.get("unresolved") or []) if isinstance(item, Mapping)]
    qualification = report.get("qualification") or {}
    facts = report.get("facts") or {}
    audit = report.get("audit") or {}
    sweep = report.get("sweep") or {}
    model = report.get("model") or {}

    lines = [
        "# FundLex 合同修改说明", "",
        f"- 引擎：{report.get('engine_id')} {report.get('engine_version')}"
        f"（schema {report.get('schema_version')}）",
        f"- 执行模式：{report.get('execution_mode')}",
        f"- 源文件 SHA-256：{report.get('source_sha256') or '（未读取）'}",
        f"- 指引文档 SHA-256：{(report.get('guide') or {}).get('document_sha256') or '（未提供）'}",
        f"- 交付状态：{report.get('delivery_status')}",
    ]
    from .delivery import failure_reason
    for error in (report.get("errors") or []):
        if isinstance(error, Mapping):
            lines.append(f"- 失败原因：{failure_reason(error.get('code')) or error.get('code')}")
    if qualification:
        lines.append(f"- 资格：{qualification.get('status')}（fund_type={qualification.get('fund_type')}；"
                     f"引文核验={qualification.get('fund_type_quote_verified')}）")
    if facts:
        classes = "、".join(str(item.get("name")) for item in facts.get("classes") or [])
        lines.append(f"- 事实：份额类别 {facts.get('class_count')}（{classes or '无'}）；"
                     f"销售服务费类别：{'、'.join(facts.get('service_group') or []) or '无'}；"
                     f"浮动管理费：{'是' if facts.get('is_floating_fee') else '否'}")
    disposition = _target_disposition_counts(targets)
    lines.append(f"- 目标计数：应改 {disposition['needs_edit']}，已符合 {disposition['satisfied']}，"
                 f"不适用 {disposition['absent']}；计划修改 {len(edits)}")
    lines.append(f"- 模型调用：{model.get('logical_calls', 0)}；"
                 f"估算费用：{model.get('estimated_cost_usd', 0)}")
    policy = str(report.get("delivery_policy") or "review_assisted")
    blockers = report.get("delivery_blockers")
    review_items = report.get("review_items")
    business_items = report.get("business_pending")
    if blockers is None or review_items is None or business_items is None:
        blockers, review_items, business_items = _classify_delivery_items(unresolved)
    lines.append(f"- 交付策略：{policy}；阻断 {len(blockers)} 项；"
                 f"人工复核 {len(review_items)} 项；业务待定 {len(business_items)} 项")

    by_rule: dict[str, int] = {}
    for edit in edits:
        rule_id = str(edit.get("rule_id") or "")
        by_rule[rule_id] = by_rule.get(rule_id, 0) + 1
    if by_rule:
        lines.append("- 修改分布：" + "；".join(
            f"{rule_id} {count} 处" for rule_id, count in sorted(by_rule.items())))
    if unresolved:
        codes: dict[str, int] = {}
        for item in unresolved:
            code = str(item.get("code") or item.get("kind") or "UNKNOWN")
            codes[code] = codes.get(code, 0) + 1
        lines.append("- 未决项（阻断+复核+业务）：" + "；".join(
            f"{code} {count}" for code, count in sorted(codes.items(), key=lambda kv: -kv[1])))

    # 1. Every applied change, with the guide requirement and the real before/after.
    lines.extend(["", "## 一、逐处修改", ""])
    if not edits:
        lines.append("- （本次没有生成任何修改）")
    operation_labels = {"replace": "替换", "delete": "删除", "insert": "新增", "append": "追加"}
    for index, edit in enumerate(edits, 1):
        rule_id = str(edit.get("rule_id") or "")
        title, requirement = _rule_meta(guide_groups, rule_id)
        operation = operation_labels.get(str(edit.get("operation")), str(edit.get("operation") or ""))
        before = str(edit.get("expected_old_text") or "")
        after = str(edit.get("replacement") or "")
        lines.append(f"### {index}. {rule_id} {title}")
        lines.append("")
        lines.append(f"- 位置：{edit.get('location')}")
        lines.append(f"- 操作：{operation}")
        if requirement:
            lines.append(f"- 指引要求：{_short_text(requirement, 300)}")
        lines.append(f"- 修改前：{('「' + _short_text(before) + '」') if before else '（无，新增内容）'}")
        lines.append(f"- 修改后：{('「' + _short_text(after) + '」') if after else '（删除，无保留内容）'}")
        lines.append(f"- 证明：{_edit_proof_label(replay, edit)}")
        lines.append("")

    # 2. Already-correct clauses: what the guide asked and why no change was needed.
    satisfied = [target for target in targets
                 if not target.get("out_of_scope")
                 and (target.get("state") == "satisfied"
                      or target.get("status") == "satisfied")]
    lines.extend(["## 二、已符合、无需修改", ""])
    if not satisfied:
        lines.append("- （无）")
    for target in satisfied:
        rule_id = str(target.get("rule_id") or "")
        title, _requirement = _rule_meta(guide_groups, rule_id)
        lines.append(f"- {rule_id} {title} {target.get('location')}："
                     f"「{_short_text(target.get('quote'), 160)}」— {_readable_reason(target.get('reason'))}")

    # 3. Business items that need a product decision (never auto-applied).
    notices = [item for item in (report.get("business_notices") or []) if isinstance(item, Mapping)]
    business_unresolved = [item for item in business_items if item not in notices]
    lines.extend(["", "## 三、业务待定（不自动修改）", ""])
    if not notices and not business_unresolved:
        lines.append("- （无）")
    for notice in notices:
        lines.append(f"- [{notice.get('code')}] {notice.get('rule_id')} {notice.get('location')}："
                     f"{_short_text(notice.get('message'), 240)}")
    seen_business: set[tuple[str, str, str]] = set()
    for item in business_unresolved:
        key = (str(item.get("rule_id") or ""), str(item.get("code") or ""),
               str(item.get("operation_id") or item.get("obligation_id") or ""))
        if key in seen_business:
            continue
        seen_business.add(key)
        lines.append(f"- {_readable_item(item)}")

    # 4. Blockers prevent delivery; review items are delivered but need a human check.
    lines.extend(["", "## 四、阻断项（未交付原因）", ""])
    if not blockers:
        lines.append("- （无）")
    for item in blockers:
        lines.append(f"- {_readable_item(item)}")
    lines.extend(["", "## 五、人工复核清单（已交付，需确认）", ""])
    if not review_items:
        lines.append("- （无）")
    for item in review_items:
        lines.append(f"- {_readable_item(item)}")

    lines.extend(["", "## 六、处理概览", ""])
    lines.append(f"- 审计轮次：{len(audit.get('rounds') or [])}；"
                 f"未决问题 {len(audit.get('issues') or [])}")
    lines.append(f"- 查漏：块 {sweep.get('chunks', 0)}，发现 {len(sweep.get('findings') or [])}，"
                 f"缺口 {len(sweep.get('gaps') or [])}")
    if report.get("errors"):
        lines.append(f"- 错误：{'; '.join(str(item.get('code')) for item in report['errors'])}")
    lines.extend(["", f"**交付状态：{report.get('delivery_status')}**"])
    return "\n".join(lines) + "\n"


def _write_report_markdown(path: Path, report: dict[str, Any]) -> None:
    path.write_text(_report_markdown(report), encoding="utf-8")


def _write_edits(path: Path, report: dict[str, Any]) -> None:
    payload = {
        "schema_version": report.get("schema_version"), "engine_id": report.get("engine_id"),
        "engine_version": report.get("engine_version"), "source_sha256": report.get("source_sha256"),
        "guide_document_sha256": (report.get("guide") or {}).get("document_sha256"),
        "delivery_status": report.get("delivery_status"), "plan": report.get("plan"),
        "targets": report.get("targets"),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _residual_delete_indices(rule_id: str, rule: Mapping[str, Any], facts: Facts,
                             operation_id: str) -> list[int]:
    """Select only the applicable delete operation identified by replay."""
    candidates = [index for index, operation in enumerate(rule.get("operations") or [])
                  if operation.get("op") == "delete"
                  and condition_matches(operation.get("condition"), facts)
                  and (not operation_id or operation_id == _declared_operation_key(
                      rule_id, index, operation))]
    # A legacy failure without an identity is actionable only when unambiguous.
    return candidates if operation_id or len(candidates) == 1 else []


def process_recall_first(input_path: str | Path, output_dir: str | Path, *,
                         guide_document: dict, gateway: Any = None,
                         execution_mode: str = "delivery", checkpoint_dir: str | Path | None = None,
                         max_business_rounds: int = 3, max_sweep_chunks: int = 40) -> dict[str, Any]:
    """Run the recall-first engine for one contract and return its report.

    Raises :class:`RecallPipelineStop` for recoverable model/transport stops so the
    worker can pause and resume; every other failure is captured in the report.
    """
    input_path, output_dir = Path(input_path), Path(output_dir)
    started = time.monotonic()
    stage = "inspect"
    model: Any = gateway
    frozen_run = None
    published: list[Path] = []
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "engine_id": ENGINE_ID, "engine_version": ENGINE_VERSION,
        "execution_mode": execution_mode, "source_sha256": "",
        "guide": {"document_sha256": _guide_sha(guide_document),
                  "groups": (guide_document or {}).get("groups") or [],
                  "prompt_versions": dict(PROMPT_VERSIONS)},
        "qualification": {}, "facts": {}, "scope_mapping": {}, "windows": [], "targets": [],
        "plan": {"count": 0, "sha256": None, "edits": [], "conflicts": [],
                 "boundary_policy": BOUNDARY_POLICY},
        "audit": {"rounds": [], "issues": []},
        "survey": [], "rebind": [],
        "sweep": {"chunks": 0, "findings": [], "rounds": [], "gaps": []},
        "unresolved": [], "delivery_status": "not_generated",
        "output_validation": {"kind": None, "checks": [], "final_sha256": None, "redline_sha256": None},
        "artifacts": {}, "model": {}, "errors": [], "duration_ms": 0, "edit_plan": None,
        "limits": {"max_business_rounds": max_business_rounds, "max_sweep_chunks": max_sweep_chunks,
                   "business_rounds_used": 0},
    }
    timings: dict[str, int] = {}
    _last_stage = [started]

    def mark_stage(name: str) -> None:
        now = time.monotonic()
        timings[name] = round((now - _last_stage[0]) * 1000)
        _last_stage[0] = now

    inventory_rerun_count = 0
    full_sweep_count = 0
    incremental_audit_count = 0
    full_audit_count = 0
    no_progress_stop_count = 0
    try:
        from .guide import GuideError, validate_runtime_guide
        try:
            report["guide"]["certification"] = validate_runtime_guide(guide_document)
        except GuideError as exc:
            raise RecallError(exc.code, exc.details) from exc
        if os.environ.get("FUNDLEX_MODEL_MODE") == "record":
            from .frozen import FrozenRun
            frozen_directory = os.environ.get("FUNDLEX_FROZEN_RUN_DIR")
            if not frozen_directory:
                raise RecallError("FROZEN_RUN_CONFIG_MISSING", {})
            frozen_run = FrozenRun(Path(frozen_directory))
            frozen_run.start(input_path, guide_document)
        inspection = inspect_docx(input_path, full=True,
                                  allow_existing_revisions=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        report["source_sha256"] = inspection.source_sha256
        if inspection.revisions:
            # Existing tracked changes from another department: keep them visible
            # and separate from FundLex revisions in the report/UI.
            report["source_revisions"] = {
                "count": len(inspection.revisions),
                "authors": sorted({item["author"] for item in inspection.revisions}),
                "items": list(inspection.revisions),
            }
        rules = _guide_rules(guide_document)
        if not rules:
            raise RecallError("RECALL_GUIDE_EMPTY", {})
        for rule in rules:
            if not isinstance(rule.get("title"), str):
                raise RecallError("RECALL_GUIDE_RULE_INVALID",
                                  {"rule_id": rule.get("rule_id"), "missing": "title"})
        rules_by_id = {str(rule["rule_id"]): rule for rule in rules if rule.get("rule_id")}
        if len(rules_by_id) != len(rules):
            raise RecallError("RECALL_GUIDE_DUPLICATE_RULE",
                              {"rules": len(rules), "unique": len(rules_by_id)})
        from .obligations import (apply_facts, compile_obligations, open_obligations,
                                  project, project_unresolved)
        obligation_ledger = compile_obligations(guide_document)
        report["obligations"] = obligation_ledger.as_dict()
        model = gateway or _default_gateway()
        if checkpoint_dir is not None and hasattr(model, "bind_checkpoints"):
            model.bind_checkpoints(Path(checkpoint_dir), {
                "source_sha256": inspection.source_sha256,
                "guide_document_sha256": report["guide"]["document_sha256"],
                "prompt_versions": dict(PROMPT_VERSIONS),
                "engine_id": ENGINE_ID, "engine_version": ENGINE_VERSION,
                "boundary_policy": BOUNDARY_POLICY,
            })
        stage = "facts"
        facts = extract_facts(inspection, model)
        # Focused fact recovery (plan §8): UNKNOWN/CONFLICT fee facts get one focused
        # resolver pass and, if still undecided, independent review arbitration. The
        # recovered values pass the same code quote verification as the first answer.
        from .facts_recovery import recover_fee_facts
        facts, fact_recovery = recover_fee_facts(inspection, facts, model)
        if fact_recovery.get("attempts"):
            report["fact_recovery"] = fact_recovery
            report["facts"] = facts.as_ledger()
        report["facts"] = facts.as_ledger()
        excluded_types = _excluded_types()
        from .qualification import certify_exclusion
        facts = certify_exclusion(inspection, facts, model, excluded_types)
        report["facts"] = facts.as_ledger()
        qualification_status, excluded_now = _qualification_status(facts, excluded_types)
        qualification_gap = qualification_status == "eligible_fund_type_unverified"
        report["qualification"] = {
            "status": qualification_status,
            "fund_type": facts.fund_type, "fund_type_quote": facts.fund_type_quote,
            "fund_type_basis": facts.fund_type_basis,
            "fund_type_quote_verified": bool(facts.quotes_verified.get("fund_type")),
            "excluded_types": list(excluded_types), "basis": "facts.fund_type",
            "problems": list(facts.problems),
            "certification": dict(facts.fund_type_certification),
        }
        if excluded_now:
            report["delivery_status"] = "excluded"
            return report

        apply_facts(obligation_ledger, facts)
        report["obligations"] = obligation_ledger.as_dict()
        if frozen_run is not None:
            frozen_run.boundary("facts", {"facts": facts.as_ledger()})
        mark_stage("facts")

        stage = "scope"
        sections = structure_index(inspection)
        scope_gaps: list[dict[str, Any]] = []
        mapping = scope_map(rules, sections, model, gaps=scope_gaps)
        mapping = expand_class_definition_scope(mapping, sections, inspection)
        # RuleScope is the single physical boundary for every recall path below
        # (inventory, survey, append, delete, sweep, audit, planning).  Default policy:
        # the G15/G16/G17 summary fee copies are excluded; G18/G19-G22 include a copy
        # only when its copy_key matches the body clause.
        scopes = resolve_rule_scopes(rules, sections, inspection, mapping)
        scopes = _apply_single_leaf_fee_fallback(scopes, sections, inspection, mapping)
        scope_audit = _scope_audit_ledger(scopes)
        report["scope_audit"] = scope_audit
        if scope_gaps:
            report["scope_gaps"] = scope_gaps
        if frozen_run is not None:
            frozen_run.boundary("scope", {
                "mapping": {rule_id: list(ids) for rule_id, ids in mapping.items()},
                "scope_audit": {key: scope_audit[key]
                                for key in ("rules", "unresolved_rules")},
            })
        # Applicability recovery (plan §9): only scoped rules with an UNKNOWN
        # condition are sent to the primary judge / review arbitration. UNKNOWN never
        # executes a branch either before or after this pass.
        from .applicability import resolve_ledger
        unknown_rules = {record.spec.rule_id for record in obligation_ledger.records
                         if record.applicability.status == "UNKNOWN"}
        evidence_by_rule = _rule_evidence(mapping, sections, inspection,
                                          unknown_rules & set(mapping), scopes=scopes)
        if evidence_by_rule and _applicability_recovery_enabled():
            history = resolve_ledger(obligation_ledger.records, gateway=model,
                                     inspection=inspection, facts=facts,
                                     evidence_by_rule=evidence_by_rule)
            if history:
                report["applicability_recovery"] = history
            report["obligations"] = obligation_ledger.as_dict()

        facts_text = json.dumps(facts.as_ledger(), ensure_ascii=False, indent=1)
        if frozen_run is not None:
            frozen_run.boundary("applicability", {"facts": facts.as_ledger()})
        rules_text = rule_context(rules, full=True)
        window_chars = max(MIN_WINDOW_CHARS,
                           model.max_context_chars - len(facts_text) - len(rules_text) - 2000)
        entries: list[_WindowState] = []
        for window, window_rule_ids in plan_windows(sections, inspection, mapping, max_chars=window_chars):
            window_rules = tuple(rules_by_id[rule_id] for rule_id in window_rule_ids
                                 if rule_id in rules_by_id)
            entries.append(_WindowState(window=window, rules=window_rules))
        stage = "inventory"
        for entry in entries:
            _inventory(entry, None, facts, model, inspection, round_number=0,
                       rule_locations=scope_locations_for_window(scopes, entry.window),
                       scope_audit=scope_audit)
        synthetic: list[Target] = []
        origins: dict[str, str] = {}
        stage = "survey"
        survey_ledger: list[dict[str, Any]] = []
        coverage_gaps: list[dict[str, Any]] = []
        _run_survey(model, rules, rules_by_id, facts, inspection, _collect_targets(entries, synthetic, rules_by_id, inspection),
                    synthetic, origins, survey_ledger, coverage_gaps, sections, mapping=mapping,
                    scopes=scopes)
        targets = _collect_targets(entries, synthetic, rules_by_id, inspection)
        from .recall import assign_target_operations, ensure_delete_targets
        if os.environ.get("FUNDLEX_DELETE_RESIDUAL_TARGETS", "1").strip().lower() in {
                "1", "true", "on", "yes"}:
            # Page through residual delete candidates so a long contract cannot
            # lose its tail to the per-call safety limit (FL-D441).
            cursor = 0
            for _page in range(10):
                info: dict[str, Any] = {}
                page = ensure_delete_targets(targets, rules_by_id, inspection,
                                             scopes=scopes, cursor=cursor,
                                             page_info=info)
                for target in page:
                    synthetic.append(target)
                    targets.append(target)
                    origins[target.target_id] = "delete_residual_copy"
                if not info.get("has_more"):
                    break
                cursor = int(info.get("next_cursor") or 0)
            else:
                coverage_gaps.append({"pass": "delete_targets",
                                      "limit_reached": "delete_targets_pages",
                                      "cursor": cursor})
        if frozen_run is not None:
            frozen_run.boundary("targets", {"facts": facts.as_ledger(),
                "targets": [target.as_dict() for target in targets]})
        # Attribution happens before open-obligation discovery: a target without an
        # operation identity covers nothing, and the open pass must see exactly which
        # sibling operations are still uncovered.
        report["target_attribution"] = assign_target_operations(
            targets, rules_by_id, inspection, facts, obligation_ledger)
        targets, duplicate_targets = dedupe_operation_targets(
            targets, rules_by_id, inspection)
        if duplicate_targets:
            report["duplicate_targets"] = duplicate_targets
        # G16 target identity is the physical clause end, not the payment head.
        # Rebind before exact-copy closure so a body clause with a continuation (p804-
        # p806) cannot be treated as an identical copy of a standalone summary clause
        # (p1259) merely because their payment paragraphs have equal text.
        from .recall import rebind_g16_clause_targets
        g16_rebinds = rebind_g16_clause_targets(targets, inspection)
        if g16_rebinds:
            report["g16_clause_rebinds"] = g16_rebinds
        copy_targets = duplicate_copy_targets(targets, rules_by_id, inspection,
                                              scopes=scopes)
        for target in copy_targets:
            for old in targets:
                if old is not target and old.rule_id == target.rule_id \
                        and old.location == target.location \
                        and set(old.operations) == set(target.operations):
                    old.out_of_scope = True
                    old.reason = f"{old.reason}|SUPERSEDED_BY_DUPLICATE_COPY"
            targets.append(target)
            synthetic.append(target)
            origins[target.target_id] = "duplicate_copy"
            report["target_attribution"].extend(assign_target_operations(
                [target], rules_by_id, inspection, facts, obligation_ledger))
        from .targeting import locate_unresolved_targets, targets_for_open_rules
        open_targets = targets_for_open_rules(obligation_ledger, targets, rules_by_id, facts,
                                              inspection, mapping, sections, scopes=scopes)
        for target in open_targets:
            targets.append(target)
            synthetic.append(target)
            origins[target.target_id] = "T3_open_rule"
        report["target_attribution"].extend(assign_target_operations(
            open_targets, rules_by_id, inspection, facts, obligation_ledger))
        # Open-obligation recovery can add an append target after the initial duplicate
        # pass (for example G16 on the body payment clause).  Clone those late targets
        # too, otherwise only the body copy receives the required new clause and the
        # identical summary copy diverges at final replay.
        from .recall import rebind_split_class_definition_targets
        split_rebinds = rebind_split_class_definition_targets(targets, inspection)
        if split_rebinds:
            report["split_class_definition_rebinds"] = split_rebinds
        from .recall import resolve_absent_site_targets
        absent_target_ids = {id(target) for target in targets}
        absent_sites = resolve_absent_site_targets(targets, rules_by_id, inspection, facts)
        if absent_sites:
            report["absent_site_targets"] = absent_sites
            # resolve_absent_site_targets appends an operation-specific clone to
            # ``targets``.  Keep that clone in the synthetic source list as well;
            # the next operation-aware _collect_targets call rebuilds its result
            # from window targets + synthetic targets (D06 G05:2).
            for target in targets:
                if id(target) not in absent_target_ids and target not in synthetic:
                    synthetic.append(target)
                    origins[target.target_id] = "absent_site_clone"
        # The absent-site pass can add an operation-specific G05:2 proof and the open
        # pass can add a G16 target.  Rebind those late targets before cloning so every
        # clone inherits its own physical clause identity.
        g16_rebinds = rebind_g16_clause_targets(targets, inspection)
        if g16_rebinds:
            report.setdefault("g16_clause_rebinds", []).extend(g16_rebinds)
        open_copies = duplicate_copy_targets(targets, rules_by_id, inspection,
                                             scopes=scopes)
        for copy in open_copies:
            for old in targets:
                if old is not copy and old.rule_id == copy.rule_id \
                        and old.location == copy.location \
                        and set(old.operations) == set(copy.operations):
                    old.out_of_scope = True
                    old.reason = f"{old.reason}|SUPERSEDED_BY_DUPLICATE_COPY"
            targets.append(copy)
            synthetic.append(copy)
            origins[copy.target_id] = "duplicate_copy"
            report["target_attribution"].extend(assign_target_operations(
                [copy], rules_by_id, inspection, facts, obligation_ledger))
        from .recall import ensure_unique_target_ids
        ensure_unique_target_ids(targets, origins)
        rebinds = _rebind_unresolved_targets(targets, origins, inspection,
                                             rules_by_id=rules_by_id, facts=facts,
                                             extend_resolved=True)
        report["target_attribution"].extend(assign_target_operations(
            targets, rules_by_id, inspection, facts, obligation_ledger))
        g16_rebinds = rebind_g16_clause_targets(targets, inspection)
        if g16_rebinds:
            report.setdefault("g16_clause_rebinds", []).extend(g16_rebinds)
        # Rebinding fills offsets on survey targets after the first duplicate-copy
        # pass.  Re-run exact-copy closure now that every source target is geometric;
        # otherwise a body/summary pair (D01 p758/p1221 G15) is planned only once.
        late_copies = duplicate_copy_targets(targets, rules_by_id, inspection,
                                             scopes=scopes)
        for copy in late_copies:
            for old in targets:
                if old is not copy and old.rule_id == copy.rule_id \
                        and old.location == copy.location \
                        and set(old.operations) == set(copy.operations):
                    old.out_of_scope = True
                    old.reason = f"{old.reason}|SUPERSEDED_BY_DUPLICATE_COPY"
            targets.append(copy)
            synthetic.append(copy)
            origins[copy.target_id] = "duplicate_copy_late"
            report["target_attribution"].extend(assign_target_operations(
                [copy], rules_by_id, inspection, facts, obligation_ledger))
        if late_copies:
            ensure_unique_target_ids(targets, origins)
        from .recall import approval_book_for
        locator_records = locate_unresolved_targets(
            targets, inspection, rules_by_id, facts, model, scopes=scopes,
            approvals=approval_book_for(rules_by_id, targets, inspection))
        for target in targets:
            origins.setdefault(target.target_id, "T3_open_rule")
        if locator_records:
            report["target_locator"] = locator_records
        report["rebind"] = rebinds
        report["survey"] = survey_ledger
        report["scope_mapping"] = _scope_mapping_ledger(mapping, sections, entries, rules)
        report["windows"] = [_window_ledger(entry) for entry in entries]
        mark_stage("scope_inventory_survey")

        stage = "write"
        compose_calls = max(DEFAULT_MAX_COMPOSE_CALLS, len(rules))
        with tempfile.TemporaryDirectory(prefix=".recall-", dir=output_dir) as temporary:
            temp_dir = Path(temporary)
            planned, edits, plan, artifacts, actual = _plan_and_generate(
                model, rules_by_id, targets, inspection, facts, input_path, temp_dir,
                max_compose_calls=compose_calls, obligations=obligation_ledger,
                    frozen_run=frozen_run, scopes=scopes, scope_audit=scope_audit)
            report["plan"] = _plan_ledger(planned, plan)
            report["targets"] = _target_ledger(targets, planned, {}, origins)
            mark_stage("planning_generation")

            # --- audit + repair loop (business rounds) -----------------------
            stage = "audit"
            audit_state: dict[str, Any] = {"results": {}, "missed": {}}
            audit_rounds: list[dict[str, Any]] = []
            rounds_used = 0
            round_number = 0
            # Unified business-failure recovery (external review 2026-10-20 P0-2): every
            # audit failure is classified and routed by RecoveryOrchestrator; the report
            # keeps the root-cause history instead of an untraceable round counter.
            from .recovery import (FailureClass, RecoveryAction, RecoveryContext,
                                   RecoveryDecision, RecoveryHistory,
                                   RecoveryOrchestrator)
            audit_recovery = RecoveryHistory()
            audit_orchestrator = RecoveryOrchestrator()
            audit_pending: list[tuple[RecoveryContext, RecoveryDecision, str]] = []
            terminal_keys: set[str] = set()
            audit_dirty: set[str] | None = None
            full_audit_count = 0
            incremental_audit_count = 0
            previous_audit_snapshot = None
            while True:
                round_ledger = _run_audit(model, rules_by_id, targets, planned, inspection,
                                          actual, facts=facts, only_rules=audit_dirty,
                                          obligations=obligation_ledger,
                                          scopes=scopes, scope_audit=scope_audit)
                scope = "incremental" if audit_dirty is not None else "full"
                if audit_dirty is None:
                    full_audit_count += 1
                else:
                    incremental_audit_count += 1
                round_ledger.update(round=round_number, scope=scope)
                audit_rounds.append(round_ledger)
                _merge_audit_state(audit_state, round_ledger, targets)
                issues = _audit_issues(audit_state, targets)
                round_ledger["issues"] = issues
                report["audit"] = {"rounds": audit_rounds, "issues": issues}
                report["targets"] = _target_ledger(targets, planned, audit_state, origins)
                contexts = _audit_recovery_contexts(issues, targets=targets, planned=planned,
                    artifact_failures=round_ledger.get("artifact_failures") or [])
                current_keys = {_audit_context_key(context) for context in contexts}
                state = {"failures": [{"code": context.error_code,
                    "operation_id": context.operation_id, "location": context.site_id}
                    for context in contexts]}
                audit_snapshot = _recovery_snapshot(targets, planned, actual, state,
                    facts=facts, obligations=obligation_ledger, scope=mapping)
                round_ledger["recovery_state_hashes"] = state["recovery_state_hashes"]
                stalled = bool(audit_pending) and audit_snapshot == previous_audit_snapshot
                if audit_pending:
                    # Honest per-obligation outcome: succeeded only when the exact issue
                    # this action targeted disappeared, not when some unrelated count fell.
                    for context, decision, key in audit_pending:
                        succeeded = key not in current_keys
                        audit_orchestrator.record(
                            audit_recovery, context, decision,
                            outcome="succeeded" if succeeded else "failed",
                            detail=("issue_resolved" if succeeded else "issue_remains")
                                   + f";issues={len(issues)}")
                    audit_pending = []
                if stalled:
                    no_progress_stop_count += 1
                    for context in contexts:
                        audit_orchestrator.record(audit_recovery, context,
                            RecoveryDecision(RecoveryAction.MARK_UNRESOLVED, "RECOVERY_NO_PROGRESS"),
                            outcome="unresolved", detail="RECOVERY_NO_PROGRESS:unchanged audit state")
                    break
                previous_audit_snapshot = audit_snapshot
                if not issues:
                    break
                decisions: list[tuple[RecoveryContext, RecoveryDecision, str]] = []
                for index, context in enumerate(contexts):
                    key = _audit_context_key(context)
                    if key in terminal_keys:
                        continue
                    if index >= 8:
                        skipped = RecoveryDecision(RecoveryAction.MARK_UNRESOLVED,
                                                   "audit_context_budget", "", 0)
                        audit_orchestrator.record(audit_recovery, context, skipped,
                                                  outcome="skipped",
                                                  detail="audit_context_budget")
                        # Deferred, not terminal: a later round may decide this context
                        # once the earlier ones resolve.
                        continue
                    decision = audit_orchestrator.decide(context, audit_recovery)
                    if decision.terminal:
                        audit_orchestrator.record(audit_recovery, context, decision,
                                                  outcome="unresolved",
                                                  detail="no further safe recovery layer")
                        terminal_keys.add(key)
                    else:
                        decisions.append((context, decision, key))
                if not decisions:
                    break
                actions = {decision.action for _, decision, _ in decisions}
                classes = {context.resolved_class for context, _, _ in decisions}
                fact_changed = False
                if FailureClass.FACT in classes or actions & {
                        RecoveryAction.FOCUSED_FACT_RESOLVE,
                        RecoveryAction.FACT_ARBITRATION}:
                    # Audit FACT failure returns to the fact layer (plan §22.2), not to
                    # another inventory retry. The forced pass still needs review
                    # arbitration and verified quotes before it changes anything.
                    from .facts_recovery import recover_fee_facts
                    names = tuple(sorted({str(issue.get("affected_fact") or "")
                                          for issue in issues
                                          if str(issue.get("failure_class") or "").upper() == "FACT"
                                          and issue.get("affected_fact")}))
                    recovered, summary = recover_fee_facts(
                        inspection, facts, model,
                        force_names=names or ("share_class_structure",
                                              "subscription_fee_group",
                                              "service_fee_group"))
                    report.setdefault("fact_recovery_rounds", []).append(summary)
                    if recovered is not facts:
                        facts = recovered
                        report["facts"] = facts.as_ledger()
                        apply_facts(obligation_ledger, facts)
                        report["obligations"] = obligation_ledger.as_dict()
                        fact_changed = True
                applicability_changed = False
                if FailureClass.APPLICABILITY in classes or \
                        RecoveryAction.APPLICABILITY_ARBITRATION in actions:
                    from .applicability import resolve_ledger
                    unknown_rules = {record.spec.rule_id
                                     for record in obligation_ledger.records
                                     if record.applicability.status == "UNKNOWN"}
                    evidence_by_rule = _rule_evidence(mapping, sections, inspection,
                                                      unknown_rules & set(mapping))
                    if evidence_by_rule:
                        history = resolve_ledger(obligation_ledger.records, gateway=model,
                                                 inspection=inspection, facts=facts,
                                                 evidence_by_rule=evidence_by_rule)
                        if history:
                            report.setdefault("applicability_recovery", []).extend(history)
                        report["obligations"] = obligation_ledger.as_dict()
                        applicability_changed = True
                target_repair = FailureClass.TARGET in classes
                if target_repair:
                    _absorb_missed_targets(audit_state, targets, synthetic, origins, inspection,
                                          rules_by_id=rules_by_id, facts=facts,
                                          obligations=obligation_ledger)
                notes = _audit_repair_notes(issues, targets, entries)
                reaudit_only = bool(decisions) and all(
                    context.resolved_class is FailureClass.VERIFICATION
                    for context, _, _ in decisions)
                executable = (fact_changed or applicability_changed or target_repair
                              or reaudit_only
                              or bool(classes & {FailureClass.GENERATION,
                                                 FailureClass.EXECUTION}))
                if rounds_used >= max_business_rounds or not executable:
                    breaker = rounds_used >= max_business_rounds
                    for context, decision, _ in decisions:
                        if breaker:
                            terminal = RecoveryDecision(
                                RecoveryAction.MARK_UNRESOLVED,
                                "global_business_rounds", "", decision.attempt)
                            audit_orchestrator.record(
                                audit_recovery, context, terminal, outcome="unresolved",
                                detail="global_business_rounds")
                        else:
                            audit_orchestrator.record(
                                audit_recovery, context, decision, outcome="skipped",
                                detail="no_executable_action")
                    audit_pending = []
                    break
                executable_classes = {FailureClass.FACT, FailureClass.APPLICABILITY,
                                      FailureClass.TARGET, FailureClass.GENERATION,
                                      FailureClass.EXECUTION}
                audit_pending = []
                for context, decision, key in decisions:
                    if (context.resolved_class in executable_classes
                            or context.resolved_class is FailureClass.VERIFICATION) and \
                            decision.action not in {RecoveryAction.SPLIT_CONTEXT,
                                                    RecoveryAction.PAUSE_RESUME}:
                        audit_pending.append((context, decision, key))
                    else:
                        audit_orchestrator.record(
                            audit_recovery, context, decision, outcome="skipped",
                            detail="action_not_executable_in_audit_stage")
                rounds_used += 1
                round_number += 1
                if reaudit_only:
                    # No artifact change: the next loop iteration re-runs the audit and
                    # records whether the transient missing verdict cleared.
                    audit_dirty = {str(issue.get("rule_id") or "") for issue in issues
                                   if issue.get("rule_id")}
                    continue
                needs_discovery = target_repair or fact_changed or applicability_changed
                affected = _affected_windows(entries, notes) if needs_discovery else []
                # Only rules whose artifact site / plan / verdict changed are re-audited.
                audit_dirty = {context.rule_id for context, _, _ in decisions if context.rule_id}
                inventory_rerun_count += len(affected)
                for entry in affected:
                    _inventory(entry, notes[entry.window.id], facts, model, inspection,
                               round_number=round_number,
                               rule_locations=scope_locations_for_window(scopes, entry.window),
                               scope_audit=scope_audit)
                if needs_discovery:
                    targets = _collect_targets(entries, synthetic, rules_by_id, inspection)
                    _run_survey(model, rules, rules_by_id, facts, inspection, targets,
                                synthetic, origins, survey_ledger, coverage_gaps, sections,
                                mapping=mapping, scopes=scopes)
                if needs_discovery:
                    targets = _collect_targets(entries, synthetic, rules_by_id, inspection)
                report["rebind"] = _rebind_unresolved_targets(
                    targets, origins, inspection, rules_by_id=rules_by_id, facts=facts)
                report.setdefault("target_attribution", []).extend(
                    assign_target_operations(targets, rules_by_id, inspection, facts,
                                             obligation_ledger))
                targets, duplicates = dedupe_operation_targets(
                    targets, rules_by_id, inspection)
                if duplicates:
                    report.setdefault("duplicate_targets", []).extend(duplicates)
                if needs_discovery:
                    from .recall import approval_book_for
                    report.setdefault("target_locator", []).extend(
                        locate_unresolved_targets(
                            targets, inspection, rules_by_id, facts, model,
                            scopes=scopes,
                            approvals=approval_book_for(rules_by_id, targets,
                                                        inspection)))
                for target in targets:
                    origins.setdefault(target.target_id, "T3_open_rule")
                planned, edits, plan, artifacts, actual = _plan_and_generate(
                    model, rules_by_id, targets, inspection, facts, input_path, temp_dir,
                    max_compose_calls=compose_calls, obligations=obligation_ledger,
                    frozen_run=frozen_run,
                    scopes=scopes, scope_audit=scope_audit,
                    existing_plan=planned,
                    dirty_locations=({target.location for target in targets
                        if fact_changed or applicability_changed}
                        | {context.site_id for context, _, _ in decisions
                        if context.site_id and context.resolved_class is not FailureClass.EXECUTION}
                        if needs_discovery or FailureClass.GENERATION in classes else None))
                report["plan"] = _plan_ledger(planned, plan)
                report["targets"] = _target_ledger(targets, planned, audit_state, origins)
                report["windows"] = [_window_ledger(entry) for entry in entries]
                report["survey"] = survey_ledger
                report["limits"]["business_rounds_used"] = rounds_used
            if audit_pending:
                for context, decision, _ in audit_pending:
                    audit_orchestrator.record(
                        audit_recovery, context, decision, outcome="skipped",
                        detail="repair_round_not_executed")
                audit_pending = []
            report.setdefault("recovery", {})["business_rounds"] = \
                audit_recovery.as_list()
            mark_stage("audit_recovery")

            # Replay/recovery precedes the one final sweep. These boundary
            # ledgers are populated after claim recovery, before delivery.
            findings: list[dict[str, Any]] = []
            gaps: list[dict[str, Any]] = []
            # --- delivery decision -------------------------------------------
            stage = "deliver"
            plan_by_target = _plan_by_target(planned)
            # Business notices (user ruling 2026-10-19): G15 deletions whose clause
            # deviates from the guide reference are reported as "the original contract
            # may be in error". They are warnings only — never validation errors, never
            # part of ``unresolved``, and they never affect completion.
            notices: list[dict[str, Any]] = []
            seen_notices: set[tuple] = set()
            for edit in planned.get("edits") or []:
                candidates = [edit, *(edit.get("components") or [])]
                for candidate in candidates:
                    for notice in (candidate.get("evidence") or {}).get("business_notices") or []:
                        rule_label = candidate.get("rule_id") or edit.get("rule_id")
                        location_label = candidate.get("location") or edit.get("location")
                        key = (notice.get("code"), notice.get("message"),
                               rule_label, location_label)
                        if key in seen_notices:
                            continue
                        seen_notices.add(key)
                        notices.append({
                            "rule_id": rule_label,
                            "location": location_label,
                            **notice,
                        })
            if notices:
                report["business_notices"] = notices
            unresolved_targets = [target for target in targets if target.state == "needs_edit"
                                  and not target.out_of_scope
                                  and plan_by_target.get(target.target_id, {}).get("status")
                                  not in {"planned", "satisfied", "not_applicable"}]
            audit_issues = _audit_issues(audit_state, targets)
            pending_findings = [finding for finding in findings
                                if finding["status"] in {"pending", "unresolved"}]
            unresolved: list[dict[str, Any]] = []
            for target in unresolved_targets:
                entry = plan_by_target.get(target.target_id) or {}
                unresolved.append({"kind": "target", "rule_id": target.rule_id,
                                   "target_id": target.target_id, "location": target.location,
                                   "reason": entry.get("reason") or "RECALL_TARGET_UNRESOLVED",
                                   "quote": _clip(target.quote, 120)})
            for issue in audit_issues:
                unresolved.append({"kind": "audit", **issue})
            for finding in pending_findings:
                unresolved.append({"kind": "sweep", **{key: finding[key] for key in
                                                       ("finding_id", "rule_id", "location", "issue",
                                                        "status", "reason", "failure_class")}})
            for gap in [*gaps, *coverage_gaps]:
                unresolved.append({"kind": "coverage", **gap})
            # --- artifact claim replay (hard gate, always on) -----------------
            if True:
                from .generation.claim_replay import (check_delete_residuals,
                                                      replay_claims)
                from .generation.components import claim_components_for_rules
                from .recovery import (RecoveryContext, RecoveryHistory,
                                       RecoveryOrchestrator, RecoveryAction)

                def _claim_maps(plan: dict[str, Any]) -> tuple[dict, dict]:
                    rule_ids: set[str] = set()
                    for edit in plan.get("edits") or []:
                        rule_ids.update(part.strip()
                                        for part in str(edit.get("rule_id") or "").split("+")
                                        if part.strip())
                        for component in edit.get("components") or []:
                            rule_ids.update(
                                part.strip() for part in
                                str(component.get("rule_id") or "").split("+")
                                if part.strip())
                    components = {rule_id: claim_components_for_rules([rule_id], rules_by_id)
                                  for rule_id in rule_ids}
                    terms: dict[str, tuple[str, ...]] = {}
                    if facts.status_of("subscription_fee_group") == "VERIFIED" and \
                            facts.status_of("service_fee_group") == "VERIFIED":
                        class_terms = tuple(
                            name if "类" in name else f"{name}类"
                            for name in (*facts.subscription_group, *facts.service_group))
                        # Only G02/G04 require every group label in the target paragraph.
                        for rule_id in rule_ids & {"G02", "G04"}:
                            terms[rule_id] = class_terms
                    return components, terms

                components_by_rule, required_terms_by_rule = _claim_maps(planned)

                def _replay(plan: dict[str, Any]) -> dict[str, Any]:
                    if frozen_run is not None:
                        import shutil
                        artifact_name = "artifacts/" + actual.source_sha256 + ".docx"
                        destination = frozen_run.directory / artifact_name
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        if not destination.exists():
                            shutil.copyfile(temp_dir / "final.docx", destination)
                        frozen_run.boundary("claim_replay", {"facts": facts.as_ledger(),
                            "targets": [target.as_dict() for target in targets],
                            "plan": plan, "artifact": artifact_name,
                            "components_by_rule": components_by_rule,
                            "required_terms_by_rule": required_terms_by_rule,
                            "target_rules": target_rules})
                    from .recall import approval_book_for
                    approval_book = approval_book_for(rules_by_id, targets, inspection)
                    result = replay_claims(
                        plan.get("edits") or [], inspection, actual,
                        rules_by_id=rules_by_id, facts=facts,
                        components_by_rule=components_by_rule,
                        required_terms_by_rule=required_terms_by_rule,
                        target_rules=target_rules,
                        targets_by_id={target.target_id: target.as_dict()
                                       for target in targets},
                        obligations=obligation_ledger,
                        scopes=scopes,
                        approvals=approval_book)
                    residuals = check_delete_residuals(
                        rules_by_id, actual, edits=plan.get("edits") or [], original=inspection,
                        targets=[target.as_dict() for target in targets], facts=facts,
                        obligations=obligation_ledger, scopes=scopes)
                    if residuals:
                        result["failures"].extend(residuals)
                        result["verified"] = False
                    if getattr(residuals, "truncated", False):
                        result["truncated"] = True
                        result["remaining"] = getattr(residuals, "remaining", None)
                        result["next_cursor"] = getattr(residuals, "next_cursor", None)
                        result["verified"] = False
                    return result

                target_rules: dict[str, list[str]] = {}
                for target in targets:
                    target_rules.setdefault(target.location, []).append(target.rule_id)
                replay = _replay(planned)
                # Claim replay is a recoverable stage (plan §24): a failed replay
                # rebuilds the plan from the ORIGINAL source and replays again before
                # the obligation is allowed to become unresolved.
                recovery = RecoveryOrchestrator()
                recovery_history = RecoveryHistory()
                recovery_attempts = 0
                artifact_recovery_used = False
                recovery_sweep_unverified = False
                terminal_recorded = False
                no_progress_rounds = 0
                previous_snapshot = _recovery_snapshot(targets, planned, actual, replay,
                    facts=facts, obligations=obligation_ledger, scope=mapping)

                def _failure_key(item: dict[str, Any]) -> tuple[str, ...]:
                    return (str(item.get("code") or ""), str(item.get("rule_id") or ""),
                            str(item.get("operation_id") or ""),
                            str(item.get("obligation_id") or ""),
                            str(item.get("location") or ""))

                terminal_failures: set[tuple[str, ...]] = set()
                # A single unrepairable obligation must not starve the rest of the
                # claim failures.  The global cap is a safety circuit breaker; the
                # per-failure key below prevents re-attempting the same terminal item.
                recovery_budget = max(recovery.policy.limit("artifact_recovery"),
                                       min(8, len(replay.get("failures") or [])))
                while replay.get("failures") and recovery_attempts < recovery_budget:
                    # Duplicate-copy divergence is repaired by generating the missing
                    # copy, not by rebuilding the same plan; process an actionable
                    # operation/residual failure first when both exist.
                    actionable = [item for item in replay["failures"]
                                  if _failure_key(item) not in terminal_failures]
                    if not actionable:
                        break
                    failure = next(
                        (item for item in actionable
                         if str(item.get("code") or "") not in {
                             "DUPLICATE_SITE_DIVERGED", "DUPLICATE_SITE_UNEDITED"}),
                        actionable[0])
                    code = str(failure.get("code") or "CLAIM_REPLAY_FAILED")
                    context = _claim_failure_context(failure, targets, planned.get("edits") or [])
                    context.validator_findings = tuple(replay.get("failures") or ())
                    operation_added = False
                    if code in {"DUPLICATE_SITE_DIVERGED", "DUPLICATE_SITE_UNEDITED"} \
                            and failure.get("locations"):
                        duplicate_locations = [str(value) for value in
                                               failure.get("locations") or ()]
                        edited_locations = {str(edit.get("location") or "")
                                            for edit in planned.get("edits") or []}
                        for missing_location in duplicate_locations:
                            if missing_location in edited_locations:
                                continue
                            for source_target in list(targets):
                                if source_target.location not in edited_locations:
                                    continue
                                if not source_target.operations:
                                    continue
                                for clone in duplicate_copy_targets(
                                        [source_target], rules_by_id, inspection,
                                        scopes=scopes):
                                    if clone.location != missing_location:
                                        continue
                                    for old_target in targets:
                                        if old_target.location == missing_location and \
                                                old_target.rule_id == clone.rule_id:
                                            old_target.out_of_scope = True
                                            old_target.reason = (
                                                f"{old_target.reason}|"
                                                "SUPERSEDED_BY_DUPLICATE_REPAIR")
                                    targets.append(clone)
                                    synthetic.append(clone)
                                    origins[clone.target_id] = "duplicate_repair"
                                    report.setdefault("target_attribution", []).extend(
                                        assign_target_operations(
                                            [clone], rules_by_id, inspection, facts,
                                            obligation_ledger))
                                    operation_added = True
                                    break
                                if operation_added:
                                    break
                    if code == "RESIDUAL_OLD_TEXT" and failure.get("quote") \
                            and failure.get("location"):
                        from .recall import resolve_quote
                        location = str(failure.get("location"))
                        quote = str(failure.get("quote") or "")
                        try:
                            span = inspection.by_location(location)
                            located = resolve_quote(span, quote)
                        except Exception:  # noqa: BLE001
                            located = None
                        rule_id = str(failure.get("rule_id") or "")
                        rule = rules_by_id.get(rule_id) or {}
                        operation_id = str(failure.get("operation_id") or "")
                        delete_indices = _residual_delete_indices(
                            rule_id, rule, facts, operation_id)
                        selected_key = (
                            _declared_operation_key(
                                rule_id, delete_indices[0],
                                (rule.get("operations") or [])[delete_indices[0]])
                            if delete_indices else ""
                        )
                        existing = {(target.rule_id, key, target.location)
                                    for target in targets if not target.out_of_scope
                                    for key in target.operations}
                        from .generation.effects import operation_units
                        location_planned = any(
                            str(unit.get("location") or edit.get("location") or "") == location
                            for edit, unit in operation_units(planned.get("edits") or [], selected_key))
                        if located is not None and delete_indices and \
                                ((rule_id, selected_key, location) not in existing
                                 or not location_planned):
                            for old_target in targets:
                                if old_target.rule_id == rule_id and \
                                        old_target.location == location and \
                                        selected_key in old_target.operations and \
                                        not location_planned:
                                    old_target.out_of_scope = True
                                    old_target.reason = (f"{old_target.reason}|"
                                                         "SUPERSEDED_BY_RESIDUAL_TARGET")
                            repair_target = Target(
                                target_id=f"R{len(targets) + 1:03d}", rule_id=rule_id,
                                location=location, quote=quote, state="needs_edit",
                                reason=f"claim_residual:{code}", start=located[0],
                                end=located[1], resolution="resolved",
                                segment_ok=True,
                                operations=(selected_key,))
                            targets.append(repair_target)
                            synthetic.append(repair_target)
                            origins[repair_target.target_id] = "claim_residual"
                            report.setdefault("target_attribution", []).extend(
                                assign_target_operations([repair_target], rules_by_id,
                                                         inspection, facts,
                                                         obligation_ledger))
                            operation_added = True
                    if code == "CLAIM_PLANNED_EFFECT_MISSING":
                        # The target and plan already exist.  Route directly to
                        # generation/artifact recovery; asking the locator for a new
                        # target loses the real root cause and can duplicate work.
                        operation_added = True
                    if code in {"CLAIM_OPERATION_NOT_PLANNED", "CLAIM_OPERATION_UNPROVEN"} \
                            and context.resolved_class is FailureClass.TARGET:
                        from .targeting import (target_for_claim_site,
                                                target_for_missing_operation)
                        record = None
                        if failure.get("obligation_id"):
                            record = obligation_ledger.record(
                                str(failure.get("obligation_id")))
                        if record is None and failure.get("operation_id"):
                            record = obligation_ledger.record(
                                str(failure.get("operation_id")))
                        if record is not None:
                            site = str(failure.get("location") or "")
                            site_active = bool(site) and any(
                                target.location == site and not target.out_of_scope
                                and target.state == "needs_edit"
                                and record.spec.operation_id in target.operations
                                for target in targets)
                            if site_active:
                                # The target already exists at the proved site but its
                                # plan entry is missing (late survey/duplicate target).
                                # Replan this site instead of declaring a new target.
                                operation_added = True
                            else:
                                # Claim Replay has already verified this exact duplicate
                                # site. An active target at another copy must not
                                # suppress the required occurrence repair.
                                rule_sections = set((mapping or {}).get(
                                    record.spec.rule_id, ()))
                                rule_scope = (scopes.get(record.spec.rule_id)
                                              if scopes is not None else None)
                                allowed = ({str(location) for location in
                                            getattr(rule_scope, "locations", ()) or ()}
                                           if rule_scope is not None else
                                           {loc for section in sections
                                            if section.id in rule_sections
                                            for loc in section.locations})
                                repair_target = target_for_claim_site(
                                    record, site, targets, rules_by_id, facts, inspection,
                                    target_id=f"R{len(targets) + 1:03d}",
                                    allowed_locations=(allowed if rule_scope is not None
                                                       else (allowed or None)))
                                if repair_target is not None:
                                    for old_target in targets:
                                        if old_target is not repair_target \
                                                and old_target.rule_id == repair_target.rule_id \
                                                and old_target.location == repair_target.location \
                                                and set(old_target.operations) & set(
                                                    repair_target.operations):
                                            old_target.out_of_scope = True
                                            old_target.reason = (f"{old_target.reason}|"
                                                                 "SUPERSEDED_BY_CLAIM_SITE_REPAIR")
                                    targets.append(repair_target)
                                    synthetic.append(repair_target)
                                    origins[repair_target.target_id] = "claim_site_repair"
                                    report.setdefault("target_attribution", []).extend(
                                        assign_target_operations(
                                            [repair_target], rules_by_id, inspection, facts,
                                            obligation_ledger))
                                    operation_added = True
                        if record is not None and not operation_added:
                            repair_target = target_for_missing_operation(
                                record, targets, rules_by_id, facts, inspection,
                                mapping, sections,
                                target_id=f"R{len(targets) + 1:03d}",
                                scopes=scopes)
                            if repair_target is not None:
                                targets.append(repair_target)
                                origins[repair_target.target_id] = "claim_operation_recovery"
                                report.setdefault("target_attribution", []).extend(
                                    assign_target_operations(
                                        [repair_target], rules_by_id, inspection, facts,
                                        obligation_ledger))
                                recovery_copies = duplicate_copy_targets(
                                    targets, rules_by_id, inspection, scopes=scopes)
                                for copy in recovery_copies:
                                    for old in targets:
                                        if old is not copy \
                                                and old.rule_id == copy.rule_id \
                                                and old.location == copy.location \
                                                and set(old.operations) == set(copy.operations):
                                            old.out_of_scope = True
                                            old.reason = (f"{old.reason}|"
                                                          "SUPERSEDED_BY_DUPLICATE_COPY")
                                    targets.append(copy)
                                    synthetic.append(copy)
                                    origins[copy.target_id] = "duplicate_copy"
                                    report.setdefault("target_attribution", []).extend(
                                        assign_target_operations(
                                            [copy], rules_by_id, inspection, facts,
                                            obligation_ledger))
                                from .targeting import locate_unresolved_targets
                                from .recall import approval_book_for
                                report.setdefault("target_locator", []).extend(
                                    locate_unresolved_targets(
                                        [repair_target], inspection, rules_by_id, facts,
                                        model, scopes=scopes,
                                        approvals=approval_book_for(
                                            rules_by_id, [repair_target], inspection)))
                                operation_added = True
                        if not operation_added:
                            recovery.record(
                                recovery_history, context,
                                RecoveryDecision(RecoveryAction.REBUILD_PLAN,
                                                 "no_operation_target", "", recovery_attempts + 1),
                                outcome="failed",
                                detail="CLAIM_OPERATION_NOT_PLANNED:no_code_proven_site")
                            terminal_failures.add(_failure_key(failure))
                            recovery_attempts += 1
                            continue
                    executable = {RecoveryAction.REGENERATE_ARTIFACT,
                                  RecoveryAction.REBUILD_PLAN,
                                  RecoveryAction.RETRY_DETERMINISTIC}
                    decision = recovery.decide(context, recovery_history)
                    # Actions owned by a later business stage (LLM_COMPOSE/LLM_LOCATE)
                    # cannot run inside delivery; record them as skipped and continue to
                    # the next executable candidate instead of stopping the whole loop.
                    while not decision.terminal and decision.action not in executable:
                        recovery.record(recovery_history, context, decision,
                                        outcome="skipped",
                                        detail="action_requires_later_business_stage")
                        decision = recovery.decide(context, recovery_history)
                    if decision.action is RecoveryAction.MARK_UNRESOLVED:
                        recovery.record(recovery_history, context, decision,
                                        outcome="unresolved",
                                        detail="recovery budget exhausted")
                        terminal_failures.add(_failure_key(failure))
                        recovery_attempts += 1
                        continue
                    try:
                        dirty_locations = ({context.site_id} if context.site_id else {
                            target.location for target in targets
                            if context.operation_id in target.operations})
                        planned, edits, plan, artifacts, actual = _plan_and_generate(
                            model, rules_by_id, targets, inspection, facts, input_path,
                            temp_dir, max_compose_calls=compose_calls,
                            obligations=obligation_ledger,
                            existing_plan=planned if context.resolved_class is FailureClass.EXECUTION
                                or dirty_locations else None,
                            dirty_locations=dirty_locations if context.resolved_class is not FailureClass.EXECUTION
                                else None,
                            frozen_run=frozen_run, scopes=scopes, scope_audit=scope_audit)
                        artifact_recovery_used = True
                        report["plan"] = _plan_ledger(planned, plan)
                        components_by_rule, required_terms_by_rule = _claim_maps(planned)
                        replay = _replay(planned)
                        current_snapshot = _recovery_snapshot(targets, planned, actual, replay,
                            facts=facts, obligations=obligation_ledger, scope=mapping)
                        if current_snapshot == previous_snapshot:
                            no_progress_rounds += 1
                            no_progress_stop_count += 1
                            recovery.record(
                                recovery_history, context,
                                RecoveryDecision(RecoveryAction.MARK_UNRESOLVED,
                                                 "RECOVERY_NO_PROGRESS", "",
                                                 recovery_attempts + 1),
                                outcome="unresolved",
                                detail="targets/plan/artifact/unresolved are unchanged")
                            terminal_failures.add(_failure_key(failure))
                            recovery_attempts += 1
                            continue
                        previous_snapshot = current_snapshot
                        no_progress_rounds = 0
                        # Reuse a review only when all of its relevant artifact sites
                        # and plan components are unchanged.
                        recovery_audit = _run_audit(model, rules_by_id, targets, planned,
                                                    inspection, actual, facts=facts,
                                                    only_rules=_stale_rules(audit_state, targets, planned, actual),
                                                    obligations=obligation_ledger,
                                                    scopes=scopes, scope_audit=scope_audit)
                        recovery_audit.update(round=round_number + 1,
                                              scope="artifact_recovery")
                        incremental_audit_count += 1
                        audit_rounds.append(recovery_audit)
                        _merge_audit_state(audit_state, recovery_audit, targets)
                        report["audit"] = {"rounds": audit_rounds,
                                           "issues": _audit_issues(audit_state, targets)}
                        report["targets"] = _target_ledger(targets, planned, audit_state,
                                                           origins)
                    except (RecallError, ModelError) as exc:
                        if isinstance(exc, ModelError) and (
                                exc.code in STOP_CODES or exc.code in SOFT_STOP_CODES):
                            raise
                        recovery.record(recovery_history, context, decision,
                                        outcome="failed", detail=f"{type(exc).__name__}:"
                                        f"{getattr(exc, 'code', '')}")
                        break
                    recovery.record(recovery_history, context, decision,
                                    outcome="succeeded" if replay.get("verified") else "failed",
                                    detail=f"checked={replay.get('checked')}")
                    recovery_attempts += 1
                if replay.get("failures") and not terminal_recorded:
                    # The loop cap is a circuit breaker, but the history must still state
                    # that the obligation ended unresolved rather than simply stopping.
                    failure = replay["failures"][0]
                    context = RecoveryContext(
                        stage="deliver", failure_class=None,
                        error_code=str(failure.get("code") or "CLAIM_REPLAY_FAILED"),
                        reason=str(failure.get("reason") or ""),
                        rule_id=str(failure.get("rule_id") or ""),
                        operation_id=str(failure.get("operation_id") or ""),
                        obligation_id=str(failure.get("obligation_id") or ""),
                        target_id=str(failure.get("target_id") or ""),
                        site_id=str(failure.get("location") or ""))
                    recovery.record(recovery_history, context,
                                    RecoveryDecision(RecoveryAction.MARK_UNRESOLVED,
                                                     "artifact_recovery_budget"),
                                    outcome="unresolved",
                                    detail="artifact recovery circuit breaker")
                if artifact_recovery_used:
                    # Replace every audit/sweep/claim verdict tied to the old artifact
                    # with the verdicts of the regenerated one.
                    unresolved[:] = [item for item in unresolved
                                     if item.get("kind") not in {"audit", "sweep",
                                                                 "claim_replay"}]
                    for issue in _audit_issues(audit_state, targets):
                        unresolved.append({"kind": "audit", **issue})
                    for finding in findings:
                        if finding.get("status") in {"pending", "unresolved"}:
                            unresolved.append({"kind": "sweep",
                                               **{key: finding[key] for key in
                                                  ("finding_id", "rule_id", "location",
                                                   "issue", "status", "reason",
                                                   "failure_class")}})
                    report["audit"] = {"rounds": audit_rounds,
                                       "issues": _audit_issues(audit_state, targets)}
                    report["targets"] = _target_ledger(targets, planned, audit_state,
                                                       origins)
                    if recovery_sweep_unverified:
                        unresolved.append({"kind": "coverage",
                                           "code": "SWEEP_RECOVERY_UNVERIFIED",
                                           "reason": "artifact was regenerated but the "
                                                     "sweep budget could not re-check it"})
                # The recovery loop may have regenerated the artifact. Every target,
                # audit and sweep verdict is recomputed from the CURRENT plan so the
                # report cannot present a pre-recovery verdict as final.
                plan_by_target = _plan_by_target(planned)
                _reconcile_candidate_targets(targets, planned, replay, obligation_ledger)
                unresolved_targets = [
                    target for target in targets if target.state == "needs_edit"
                    and not target.out_of_scope
                    and plan_by_target.get(target.target_id, {}).get("status")
                    not in {"planned", "satisfied", "not_applicable"}]
                audit_issues = _audit_issues(audit_state, targets)
                _apply_artifact_proof_to_findings(findings, replay, actual,
                                                  obligation_ledger, rules_by_id,
                                                  facts=facts, edits=planned.get("edits") or [], original=inspection)
                pending_findings = [finding for finding in findings
                                    if finding["status"] in {"pending", "unresolved"}]
                unresolved[:] = [item for item in unresolved
                                 if item.get("kind") not in {"target", "audit", "sweep"}]
                for target in unresolved_targets:
                    entry = plan_by_target.get(target.target_id) or {}
                    unresolved.append({"kind": "target", "rule_id": target.rule_id,
                                       "target_id": target.target_id,
                                       "location": target.location,
                                       "reason": entry.get("reason") or "RECALL_TARGET_UNRESOLVED",
                                       "quote": _clip(target.quote, 120)})
                for issue in audit_issues:
                    unresolved.append({"kind": "audit", **issue})
                for finding in pending_findings:
                    unresolved.append({"kind": "sweep", **{key: finding[key] for key in
                                                           ("finding_id", "rule_id", "location",
                                                            "issue", "status", "reason",
                                                            "failure_class")}})
                report["audit"] = {"rounds": audit_rounds, "issues": audit_issues}
                report["artifact_claim_replay"] = replay
                claim_summary = recovery_history.summary()
                audit_attempts = report.get("recovery", {}).get("business_rounds", [])
                combined_history = [*audit_attempts, *recovery_history.as_list()]
                final_outcome = "not_started"
                if combined_history:
                    final_outcome = str(combined_history[-1].get("outcome") or "")
                report["recovery"] = {
                    "attempts": len(combined_history),
                    "actions": [item.get("action") for item in combined_history],
                    "final": final_outcome,
                    "subject": claim_summary.get("subject") or {},
                    "claim_replay": claim_summary,
                    "business_rounds": audit_attempts,
                    "history": combined_history,
                }
                for failure in replay["failures"]:
                    code = str(failure.get("code") or "CLAIM_REPLAY_FAILED")
                    unresolved.append({"kind": "claim_replay",
                                       "code": code,
                                       "claim_code": code,
                                       "claim_replay_failed": True,
                                       **failure})
            mark_stage("claim_replay_recovery")
            # --- final sweep on the actual artifact --------------------------
            stage = "sweep"
            sweep_rounds: list[dict[str, Any]] = []
            findings: list[dict[str, Any]] = []
            gaps: list[dict[str, Any]] = []
            blind_windows: list[dict[str, Any]] = []
            swept_texts: set[str] = set()
            swept_calls = 0
            counter = [0]
            requirements = _sweep_requirements(rules)
            chunk_chars = _sweep_chunk_chars(model, requirements, facts_text)
            # Section-first windowing is available but OFF by default: measured over two
            # full dev batches it showed no metric gain and raised the sweep call count
            # (~26 windows vs ~19), so the character chunker stays the default (FL-D109).
            # Set FUNDLEX_SWEEP_SECTION_WINDOWS=1 to switch it on and re-measure.
            chunks = _sweep_chunks(actual, sections, max_chars=chunk_chars)
            # Rules with an obligation the run still has to carry out must be asked about
            # in every window their sections touch, whatever the mapping says (FL-D109).
            mandatory = {str(target.rule_id) for target in targets
                         if target.state == "needs_edit" and not target.out_of_scope}
            mandatory |= {str(target.rule_id) for target in synthetic}
            # With RuleScope the sweep accepts a finding only inside the rule's physical
            # scope; windows no rule is scoped into are skipped and recorded.
            chunks, requirements_by_chunk, scope_by_chunk = _sweep_scope_plan(
                chunks, scopes=scopes, mapping=mapping, sections=sections, rules=rules,
                mandatory=mandatory, blind_windows=blind_windows)
            batch = _take_batch(chunks, max_sweep_chunks - swept_calls, gaps, planned=len(chunks))
            batch_ledger = _sweep_batch(model, rules_by_id, requirements, batch, actual,
                                        round_number=0, counter=counter, facts=facts,
                                        facts_text=facts_text,
                                        requirements_by_chunk=requirements_by_chunk,
                                        scope_by_chunk=scope_by_chunk,
                                        scopes=scopes, scope_audit=scope_audit)
            swept_calls += len(batch)
            full_sweep_count += 1
            swept_texts.update(chunk.text for chunk in batch)
            findings.extend(batch_ledger["findings"])
            sweep_rounds.append(batch_ledger)
            report["sweep"] = {"chunks": swept_calls, "findings": findings,
                               "rounds": sweep_rounds, "gaps": gaps,
                               "blind_windows": blind_windows}
            sweep_recovery = RecoveryHistory([*audit_recovery.attempts,
                                               *recovery_history.attempts])
            sweep_history_start = len(sweep_recovery.attempts)
            while len(sweep_rounds) < 2:
                _apply_artifact_proof_to_findings(findings, replay, actual,
                                                  obligation_ledger, rules_by_id,
                                                  facts=facts, edits=planned.get("edits") or [], original=inspection)
                pending = [finding for finding in findings if finding["status"] == "pending"]
                if not pending or rounds_used >= max_business_rounds:
                    break
                contexts = _sweep_recovery_contexts(pending, targets, planned, replay,
                                                    rules_by_id=rules_by_id)
                decisions = []
                for context in contexts:
                    stalled = any(
                        item.action is RecoveryAction.MARK_UNRESOLVED
                        and "unchanged" in item.detail
                        and RecoveryHistory._same_subject(item, context)
                        for item in sweep_recovery.attempts)
                    if stalled and context.resolved_class is not FailureClass.TARGET:
                        audit_orchestrator.record(sweep_recovery, context,
                            RecoveryDecision(RecoveryAction.MARK_UNRESOLVED,
                                             "RECOVERY_NO_PROGRESS"),
                            outcome="unresolved", detail="RECOVERY_NO_PROGRESS:known unchanged operation/site")
                        continue
                    decision = audit_orchestrator.decide(context, sweep_recovery)
                    if decision.terminal:
                        audit_orchestrator.record(sweep_recovery, context, decision,
                            outcome="unresolved", detail="no safe sweep repair layer")
                    else:
                        decisions.append((context, decision))
                if not decisions:
                    break
                affected_rules = {context.rule_id for context, _ in decisions}
                dirty_locations = {context.site_id for context, _ in decisions if context.site_id}
                target_sites = {(context.rule_id, context.site_id) for context, _ in decisions
                                if context.resolved_class is FailureClass.TARGET}
                target_findings = [finding for finding in pending
                    if (finding["rule_id"], finding["location"]) in target_sites]
                absorbed = _absorb_sweep_findings(target_findings, targets, synthetic, origins,
                    inspection, rules_by_id=rules_by_id, facts=facts) if target_findings else 0
                if absorbed:
                    targets = _collect_targets(entries, synthetic, rules_by_id, inspection)
                    report.setdefault("target_attribution", []).extend(
                        assign_target_operations(targets, rules_by_id, inspection, facts,
                                                 obligation_ledger))
                # A code-bound sweep target is already usable. Only still-unbound
                # sites need an inventory window, and that window may replace only
                # the dirty operation/sites, preserving every unaffected target.
                undiscovered = [finding for finding in target_findings if not any(
                    target.rule_id == finding["rule_id"] and target.location == finding["location"]
                    and not target.out_of_scope and target.operations
                    and target.resolution in {"resolved", "composite"} for target in targets)]
                notes = _finding_repair_notes(undiscovered, entries)
                rounds_used += 1
                round_number += 1
                sweep_affected = _affected_windows(entries, notes)
                inventory_rerun_count += len(sweep_affected)
                for entry in sweep_affected:
                    _inventory(entry, notes[entry.window.id], facts, model, inspection,
                               round_number=round_number,
                               rule_locations=scope_locations_for_window(scopes, entry.window),
                               scope_audit=scope_audit)
                if sweep_affected:
                    discovered = _collect_targets(entries, synthetic, rules_by_id, inspection)
                    targets = [target for target in targets
                               if (target.rule_id, target.location) not in target_sites]
                    targets.extend(target for target in discovered
                                   if (target.rule_id, target.location) in target_sites)
                dirty_targets = [target for target in targets if target.location in dirty_locations]
                report["rebind"] = _rebind_unresolved_targets(
                    dirty_targets, origins, inspection, rules_by_id=rules_by_id, facts=facts)
                report.setdefault("target_attribution", []).extend(
                    assign_target_operations(dirty_targets, rules_by_id, inspection, facts,
                                             obligation_ledger))
                targets, duplicates = dedupe_operation_targets(
                    targets, rules_by_id, inspection)
                if duplicates:
                    report.setdefault("duplicate_targets", []).extend(duplicates)
                from .recall import approval_book_for
                locator_targets = [target for target in dirty_targets
                                   if (target.rule_id, target.location) in target_sites]
                report.setdefault("target_locator", []).extend(
                    locate_unresolved_targets(
                        locator_targets, inspection, rules_by_id, facts, model,
                        scopes=scopes,
                        approvals=approval_book_for(rules_by_id, locator_targets,
                                                    inspection)))
                for target in targets:
                    origins.setdefault(target.target_id, "T3_open_rule")
                before_repair_signature = _artifact_text_signature(actual)
                planned, edits, plan, artifacts, actual = _plan_and_generate(
                    model, rules_by_id, targets, inspection, facts, input_path, temp_dir,
                    max_compose_calls=compose_calls, obligations=obligation_ledger,
                    frozen_run=frozen_run, existing_plan=planned,
                    scopes=scopes, scope_audit=scope_audit,
                    dirty_locations=dirty_locations if any(
                        context.resolved_class is not FailureClass.EXECUTION
                        for context, _ in decisions) else None)
                report["plan"] = _plan_ledger(planned, plan)
                components_by_rule, required_terms_by_rule = _claim_maps(planned)
                replay = _replay(planned)
                report["artifact_claim_replay"] = replay
                if _artifact_text_signature(actual) == before_repair_signature:
                    no_progress_stop_count += 1
                    for context, decision in decisions:
                        audit_orchestrator.record(sweep_recovery, context, decision,
                            outcome="unresolved", detail="RECOVERY_NO_PROGRESS:unchanged artifact")
                    break
                for context, decision in decisions:
                    own_failures = [failure for failure in replay.get("failures") or []
                        if failure.get("location") == context.site_id
                        and (not context.operation_id
                             or failure.get("operation_id") == context.operation_id)]
                    audit_orchestrator.record(sweep_recovery, context, decision,
                        outcome="failed" if own_failures else "pending",
                        detail="artifact changed; operation proof rechecked; awaiting final sweep")
                report["windows"] = [_window_ledger(entry) for entry in entries]
                report["survey"] = survey_ledger
                report["limits"]["business_rounds_used"] = rounds_used
                # Affected rules plus any rule whose target set changed while the
                # plan was rebuilt; unaffected identical rules keep their verdict.
                reaudit = affected_rules | _stale_rules(audit_state, targets, planned, actual)
                if reaudit:
                    round_ledger = _run_audit(model, rules_by_id, targets, planned, inspection,
                                              actual, only_rules=reaudit, facts=facts,
                                              obligations=obligation_ledger,
                                              scopes=scopes, scope_audit=scope_audit)
                    round_ledger.update(round=round_number, scope="sweep_repair")
                    audit_rounds.append(round_ledger)
                    _merge_audit_state(audit_state, round_ledger, targets)
                    round_ledger["issues"] = [issue for issue in _audit_issues(audit_state, targets)
                                              if issue.get("rule_id") in reaudit]
                changed = [chunk for chunk in _sweep_chunks(actual, sections, max_chars=chunk_chars)
                           if chunk.text not in swept_texts]
                # Re-scope the changed windows exactly as the initial pass does, so a
                # re-sweep is not asked a different question than the window it revisits
                # (FL-D109): same chunker, same per-window rule subset, same enforcement.
                changed, requirements_by_chunk, scope_by_chunk = _sweep_scope_plan(
                    changed, scopes=scopes, mapping=mapping, sections=sections,
                    rules=rules, mandatory=mandatory, blind_windows=blind_windows)
                batch = _take_batch(changed, max_sweep_chunks - swept_calls, gaps, planned=len(changed))
                if not batch:
                    break  # nothing re-swept: the findings stay pending and block complete
                batch_ledger = _sweep_batch(model, rules_by_id, requirements, batch, actual,
                                            round_number=round_number, counter=counter,
                                            facts=facts, facts_text=facts_text,
                                            requirements_by_chunk=requirements_by_chunk,
                                            scope_by_chunk=scope_by_chunk,
                                            scopes=scopes, scope_audit=scope_audit)
                swept_calls += len(batch)
                full_sweep_count += 1
                swept_texts.update(chunk.text for chunk in batch)
                _resolve_pending(findings, batch_ledger, actual=actual,
                                 rules_by_id=rules_by_id, facts=facts)
                findings.extend(batch_ledger["findings"])
                sweep_rounds.append(batch_ledger)
                report["sweep"] = {"chunks": swept_calls, "findings": findings,
                                   "rounds": sweep_rounds, "gaps": gaps,
                                   "blind_windows": blind_windows}

            sweep_attempts = sweep_recovery.as_list()[sweep_history_start:]
            if sweep_attempts:
                summary = report.setdefault("recovery", {})
                summary["sweep"] = sweep_attempts
                summary["history"] = [*(summary.get("history") or []), *sweep_attempts]
                summary["attempts"] = len(summary["history"])
                summary["actions"] = [item.get("action") for item in summary["history"]]
                summary["final"] = sweep_attempts[-1]["outcome"]

            mark_stage("sweep")
            _apply_artifact_proof_to_findings(findings, replay, actual,
                                              obligation_ledger, rules_by_id,
                                              facts=facts, edits=planned.get("edits") or [], original=inspection)
            report["artifact_claim_replay"] = replay
            unresolved[:] = [item for item in unresolved if item.get("kind") not in {
                "target", "audit", "sweep", "claim_replay", "coverage"}]
            # A late sweep/claim repair can prove an operation after the earlier
            # reconciliation pass. Reconcile candidate targets again against the
            # final artifact so a stale T3/open-rule placeholder (for example a G12
            # candidate in a neighbouring G09 paragraph) cannot block delivery.
            _reconcile_candidate_targets(targets, planned, replay, obligation_ledger)
            plan_by_target = _plan_by_target(planned)
            for target in targets:
                entry = plan_by_target.get(target.target_id) or {}
                if target.state == "needs_edit" and not target.out_of_scope and entry.get("status") not in {
                        "planned", "satisfied", "not_applicable"}:
                    unresolved.append({"kind": "target", "rule_id": target.rule_id,
                                       "target_id": target.target_id, "location": target.location,
                                       "reason": entry.get("reason") or "RECALL_TARGET_UNRESOLVED"})
            audit_issues = _audit_issues(audit_state, targets)
            unresolved.extend({"kind": "audit", **issue} for issue in audit_issues)
            unresolved.extend({"kind": "sweep", **finding} for finding in findings
                              if finding.get("status") in {"pending", "unresolved"})
            unresolved.extend({"kind": "coverage", **gap} for gap in [*gaps, *coverage_gaps])
            unresolved.extend({"kind": "claim_replay", "claim_replay_failed": True, **failure}
                              for failure in replay.get("failures") or [])
            if qualification_gap:
                unresolved.append({
                    "kind": "qualification", "code": "FUND_TYPE_UNVERIFIED",
                    "fund_type": facts.fund_type,
                    "message": "fund_type is an excluded type but its quote could not be verified; "
                               "the run continues but delivery must not be complete"})
            # Repair rounds can append the same failure several times; keep one entry per
            # (kind, rule, location, code) so the report and the coverage view agree.
            deduped: list[dict[str, Any]] = []
            seen_unresolved: set[tuple] = set()
            from .recovery import classify
            for item in unresolved:
                code = str(item.get("code") or item.get("reason") or item.get("issue") or "")
                item.setdefault("failure_class", classify(code).value)
                key = (item.get("kind"), item.get("rule_id"), item.get("location"),
                       item.get("code") or item.get("reason") or item.get("issue"))
                if key in seen_unresolved:
                    continue
                seen_unresolved.add(key)
                deduped.append(item)
            unresolved[:] = deduped
            report["unresolved"] = unresolved
            report["audit"] = {"rounds": audit_rounds, "issues": audit_issues}
            report["targets"] = _target_ledger(targets, planned, audit_state, origins)
            report["windows"] = [_window_ledger(entry) for entry in entries]
            # Operation-level coverage projection (P0-4): the delivery gate reads the
            # same view and fails closed on a disagreement instead of completing silently.
            if frozen_run is not None:
                frozen_run.boundary("obligations", {"facts": facts.as_ledger(),
                    "report": report, "scope_gaps": sorted(str(item.get("rule_id")) for item in scope_gaps)})
            blocking_evidence = list(unresolved)
            project(obligation_ledger, report,
                    scope_gaps={str(item.get("rule_id")) for item in scope_gaps},
                    rules_by_id=rules_by_id, artifact_text=_document_compact(actual),
                    blocking_evidence=blocking_evidence)
            report["obligations"] = obligation_ledger.as_dict()
            from .generation.coverage import build_coverage_view
            coverage_view = build_coverage_view(report)
            # Preserve the full site × operation projection in the report.  Counts
            # alone cannot prove that two occurrences of one operation were both
            # verified, and made the UI/diagnostics unable to distinguish partial
            # completion from a rule-level aggregate.
            report["operation_coverage"] = coverage_view.as_dict()
            # The first projection above is the canonical Ledger update.  Do not
            # project the same stale evidence a second time: a second pass can only
            # reapply the same blockers and makes the coverage projection look like
            # an independent completion source.  Omission evidence is projected
            # below after it has been added to the same evidence set.
            unresolved[:] = project_unresolved(obligation_ledger,
                                               evidence=blocking_evidence)
            # Final independent omission review is operation/site scoped and runs
            # after the final DOCX has been reread.  Its result is part of the
            # delivery gate; a successful rule aggregate or audit opinion cannot
            # suppress a missing physical occurrence.
            final_omission_review = _final_omission_review(
                rules_by_id=rules_by_id, rules=rules, original=inspection, actual=actual,
                planned=planned, targets=targets, facts=facts,
                obligations=obligation_ledger, replay=replay, findings=findings,
                coverage_view=coverage_view, scopes=scopes)
            report["final_omission_review"] = final_omission_review
            final_omission_evidence = [
                {"kind": "final_omission", **issue}
                for issue in final_omission_review.get("issues") or []
            ]
            if final_omission_evidence:
                blocking_evidence.extend(final_omission_evidence)
                project(obligation_ledger, report,
                        scope_gaps={str(item.get("rule_id")) for item in scope_gaps},
                        rules_by_id=rules_by_id,
                        artifact_text=_document_compact(actual),
                        blocking_evidence=blocking_evidence)
                report["obligations"] = obligation_ledger.as_dict()
                unresolved[:] = project_unresolved(obligation_ledger,
                                                   evidence=blocking_evidence)
            # Keep one deterministic report entry per omission identity, since the
            # same operation may be reported by claim replay, sweep and coverage.
            final_unique: list[dict[str, Any]] = []
            final_seen: set[tuple[str, str, str, str]] = set()
            for item in unresolved:
                key = (str(item.get("kind") or ""), str(item.get("rule_id") or ""),
                       str(item.get("operation_id") or item.get("obligation_id") or ""),
                       str(item.get("location") or ""))
                if key in final_seen:
                    continue
                final_seen.add(key)
                final_unique.append(item)
            unresolved[:] = final_unique
            report["unresolved"] = unresolved
            report["delivery_gate"] = {
                "basis": "obligation_ledger",
                "counts": obligation_ledger.counts,
                "open_obligations": len(open_obligations(obligation_ledger)),
                "blocking_unresolved": len(unresolved),
            }
            class_counts: dict[str, int] = {}
            for item in unresolved:
                label = str(item.get("failure_class") or "VERIFICATION")
                class_counts[label] = class_counts.get(label, 0) + 1
            report["failure_classes"] = class_counts
            checks = [*artifacts.checks, "actual_content_verification"]
            hashes = {"final_sha256": artifacts.final_sha256, "redline_sha256": artifacts.redline_sha256}
            policy = _delivery_policy()
            blockers, review_items, business_items = _classify_delivery_items(unresolved)
            report["delivery_policy"] = policy
            report["delivery_blockers"] = blockers
            report["review_items"] = review_items
            report["business_pending"] = business_items
            report["review_required"] = bool(review_items)
            if isinstance(report.get("delivery_gate"), dict):
                report["delivery_gate"].update({
                    "policy": policy,
                    "blocking_unresolved": len(blockers),
                    "review_items": len(review_items),
                    "business_pending": len(business_items),
                })
            final_omission_blocking = any(
                _final_omission_issue_blocks(issue)
                for issue in final_omission_review.get("issues") or [])
            complete = _delivery_complete(
                unresolved, ledger=obligation_ledger, policy=policy,
                claim_replay_verified=replay.get("verified"),
                final_omission_blocking=final_omission_blocking)
            if isinstance(report.get("recovery"), dict):
                # ``final`` describes the run, not merely the last attempted action.
                report["recovery"]["last_outcome"] = report["recovery"].get("final")
                if not complete and unresolved:
                    report["recovery"]["final"] = "unresolved"
            if complete:
                _publish(temp_dir, output_dir, {"redline.docx": "redline.docx", "final.docx": "final.docx"},
                         published)
                report["output_validation"] = {
                    "kind": "recall_validated_edits" if edits else "recall_validated_unchanged",
                    "checks": checks, **hashes}
                report["artifacts"] = {"final": "final.docx", "redline": "redline.docx"}
                report["delivery_status"] = "complete"
            elif edits:
                # A valid produced pair exists but the gate is not met: keep it as a
                # working pair, never under the final names.
                _publish(temp_dir, output_dir,
                         {"redline.docx": "working_redline.docx", "final.docx": "working_final.docx"},
                         published)
                report["output_validation"] = {"kind": "recall_working_edits", "checks": checks, **hashes}
                report["artifacts"] = {"working_final": "working_final.docx",
                                       "working_redline": "working_redline.docx"}
                report["delivery_status"] = "incomplete"
            else:
                report["output_validation"] = {"kind": None, "checks": [], "final_sha256": None,
                                               "redline_sha256": None}
                report["artifacts"] = {}
                report["delivery_status"] = "not_generated"
            mark_stage("delivery")
            events = []
            try:
                events = list(getattr(model, "events", ()) or ())
                if not events and hasattr(model, "metrics"):
                    events = list(model.metrics().get("events") or ())
            except Exception:  # noqa: BLE001 - metrics must not break the report
                events = []
            by_task: dict[str, dict[str, Any]] = {}
            for event in events:
                task = str(event.get("task_type") or "")
                if not task:
                    continue
                item = by_task.setdefault(task, {"call_count": 0, "prompt_tokens": 0,
                                                 "completion_tokens": 0,
                                                 "total_latency_ms": 0,
                                                 "max_latency_ms": 0})
                item["call_count"] += 1
                item["prompt_tokens"] += int(event.get("prompt_tokens") or 0)
                item["completion_tokens"] += int(event.get("completion_tokens") or 0)
                latency = int(event.get("latency_ms") or 0)
                item["total_latency_ms"] += latency
                item["max_latency_ms"] = max(item["max_latency_ms"], latency)
            for item in by_task.values():
                item["avg_latency_ms"] = (round(item["total_latency_ms"] /
                                                item["call_count"], 1)
                                          if item["call_count"] else 0)
            report["performance"] = {
                "wall_ms": {**timings, "total": round((time.monotonic() - started) * 1000)},
                "model_by_task": by_task,
                "full_audit_count": full_audit_count,
                "incremental_audit_count": incremental_audit_count,
                "full_sweep_count": full_sweep_count,
                "inventory_rerun_count": inventory_rerun_count,
                "no_progress_stop_count": no_progress_stop_count,
            }
            return report
    except ModelError as exc:
        if exc.code in STOP_CODES or exc.code in SOFT_STOP_CODES:
            # A transport/budget stop and a malformed model answer both pause the run:
            # the worker keeps the source and the ledger and resumes the same stage.
            _finalize_failure(report, published)
            report["error_code"] = exc.code
            report.setdefault("errors", []).append({"code": exc.code, "stage": stage,
                                                      "message": exc.code})
            if exc.code in VERIFICATION_BLOCKED_CODES:
                report["verification_status"] = "verification_blocked"
                report["verification_blockers"] = [{"code": exc.code, "stage": stage,
                    **(getattr(exc, "detail", {}) or {})}]
            raise RecallPipelineStop(exc.code, {"stage": stage, "metrics": exc.metrics},
                                     report=report) from exc
        report["errors"].append({"code": exc.code, "stage": stage, "message": exc.code})
        _finalize_failure(report, published)
        return report
    except (RecallError, DocxError, FrozenError, OSError) as exc:
        code = getattr(exc, "code", None) or "OUTPUT_IO_ERROR"
        report["errors"].append({"code": code, "stage": stage, "message": code})
        _finalize_failure(report, published)
        return report
    except Exception as exc:  # noqa: BLE001 - preserve metering on unexpected failures
        report["error_code"] = "PROCESSING_FAILED"
        report["qualification_status"] = "failed"
        report["errors"].append({"code": "PROCESSING_FAILED", "stage": stage,
                                 "message": type(exc).__name__})
        _finalize_failure(report, published)
        return report
    finally:
        if model is not None and hasattr(model, "metrics"):
            try:
                report["model"] = {"configured_model": getattr(model, "model", ""),
                                   "prompt_versions": dict(PROMPT_VERSIONS), **model.metrics()}
            except Exception:  # noqa: BLE001 - metrics must never break the report
                pass
        if gateway is None and model is not None and hasattr(model, "close"):
            try:
                model.close()
            except Exception:  # noqa: BLE001
                pass
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
        report["edit_plan"] = report["plan"]
        if frozen_run is not None:
            try:
                frozen_run.snapshot(report, output_dir, edits=locals().get("edits"))
            except (OSError, ValueError) as exc:
                report["errors"].append({"code": "FROZEN_RUN_WRITE_FAILED", "stage": "record",
                                          "message": type(exc).__name__})
                _finalize_failure(report, published)
        try:
            from .delivery import build_user_summary
            report["user_summary"] = build_user_summary(report)
        except Exception:  # noqa: BLE001 - the summary must never break the report
            pass
        # Surface the first engine error as the document-level error code so the
        # workbench can show a short reason even when the run stopped before the
        # delivery gate (for example EXISTING_REVISION_UNSUPPORTED at inspect).
        if not report.get("error_code") and report.get("errors"):
            report["error_code"] = str(report["errors"][0].get("code") or "")
        try:
            _write_report_markdown(output_dir / "report.md", report)
            _write_edits(output_dir / "edits.json", report)
        except OSError as exc:
            report["errors"].append({"code": "REPORT_WRITE_FAILED", "stage": "report",
                                     "message": type(exc).__name__})
            if published:
                _finalize_failure(report, published)
