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

import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .docx import (DocxError, DocumentInspection, generate_artifacts,
                   generate_unchanged_artifacts, inspect_docx, validate_edit_plan)
from .guide import guide_document_sha256
from .model import ModelError, ModelGateway
from .recall import (BOUNDARY_POLICY, ENGINE_ID, ENGINE_VERSION, SCHEMA_VERSION,
                     Facts, RecallError, SurveyHit, Target, Window, build_docx_edits,
                     containing_segment, content_check_factory, display_text,
                     extract_facts, inventory_window, plan_edits, plan_windows,
                     condition_matches, find_old_text_all, fuzzy_span, instantiate_slots,
                     resolve_old_text, resolve_quote, rule_context, scope_map,
                     structure_index, survey_targets, compact_offsets,
                     append_applicability_targets, is_delete_only_rule, Section)
from .recall_prompts import (AUDIT_INSTRUCTION, AUDIT_PROMPT_VERSION, AUDIT_SCHEMA,
                             PROMPT_VERSIONS, SWEEP_INSTRUCTION, SWEEP_PROMPT_VERSION,
                             SWEEP_SCHEMA)

STOP_CODES = {"MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED",
              "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_CIRCUIT_OPEN", "MODEL_LEDGER_UNAVAILABLE",
              "MODEL_CONFIG_MISSING", "MODEL_HTTP_ERROR", "MODEL_RETRY_EXHAUSTED"}

DEFAULT_EXCLUDED_TYPES = "etf,money_market,interbank_cd"
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


class RecallPipelineStop(RuntimeError):
    """Recoverable model/transport stop: the worker pauses and resumes later."""

    def __init__(self, code: str, detail: dict | None = None):
        self.code, self.detail = code, detail or {}
        super().__init__(code)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


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
               inspection: DocumentInspection, *, round_number: int) -> None:
    """Inventory one window, optionally carrying a repair note for the model."""
    window = entry.window
    if note:
        window = Window(id=window.id, section_ids=window.section_ids, locations=window.locations,
                        text=window.text + "\n\n[REPAIR_CONTEXT]\n" + _clip(note, MAX_REPAIR_NOTE_CHARS))
    targets, ledger = inventory_window(window, entry.rules, facts, model, inspection)
    entry.targets = list(targets)
    entry.ledgers.append({**ledger, "round": round_number,
                          "repair_context": _clip(note, MAX_REPAIR_NOTE_CHARS) if note else None})


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


def _plan_by_target(planned: dict[str, Any]) -> dict[str, dict[str, Any]]:
    by_target: dict[str, dict[str, Any]] = {}
    for entry in planned.get("ledger") or []:
        by_target[str(entry.get("target_id"))] = dict(entry)
    for edit in planned.get("edits") or []:
        for component in edit.get("components") or []:
            record = by_target.setdefault(str(component.get("target_id")), {
                "target_id": component.get("target_id"), "rule_id": component.get("rule_id"),
                "status": "planned"})
            record["operation"] = component.get("operation")
            record["replacement"] = component.get("replacement")
    return by_target


def _plan_ledger(planned: dict[str, Any], plan: Any) -> dict[str, Any]:
    return {"count": len(planned.get("edits") or []), "sha256": plan.plan_sha256,
            "edits": planned.get("edits") or [], "conflicts": planned.get("conflicts") or [],
            "ledger": planned.get("ledger") or [], "boundary_policy": BOUNDARY_POLICY}


def _target_identity(target: Target) -> tuple[str, str, str]:
    """Stable audit key: re-inventory renumbers target ids but keeps this triple."""
    return (target.rule_id, target.location, _compact(target.quote)[:60])


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


def _collect_targets(entries: Sequence[_WindowState], synthetic: Sequence[Target]) -> list[Target]:
    window_targets = [target for entry in entries for target in entry.targets]
    existing = {(target.rule_id, target.location) for target in window_targets}
    return window_targets + [target for target in synthetic
                             if (target.rule_id, target.location) not in existing]


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
    known: set[tuple[str, str]] = {(target.rule_id, location) for target in existing_targets
                                   for location in _target_locations(target)}
    targets: list[Target] = []
    gaps: list[dict[str, Any]] = []
    counter = start_index
    for hit in hits:
        if hit.operation == "satisfied":
            continue
        if hit.rule_id not in override_rules and (hit.rule_id, hit.locations[0]) in known:
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
                        quote=hit.quote, state="needs_edit", reason=reason)
        target.start, target.end = located
        if len(hit.parts) > 1:
            target.composite = parts
            target.resolution = "composite"
        else:
            target.segment_ok = containing_segment(span, *located) is not None
            target.resolution = "resolved"
        targets.append(target)
        for part_location in hit.locations:
            known.add((hit.rule_id, part_location))
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




def _run_survey(model: Any, rules: Sequence[dict], rules_by_id: dict[str, dict], facts: Facts,
                inspection: DocumentInspection, targets: Sequence[Target],
                synthetic: list[Target], origins: dict[str, str], ledger: list[dict[str, Any]],
                gaps: list[dict[str, Any]],
                sections: Sequence[Section] = ()) -> list[SurveyHit]:
    """Code-driven coverage pass: find rule targets the model inventory never reported."""
    known = [(target.rule_id, location) for target in targets for location in _target_locations(target)]
    for item in synthetic:
        for location in _target_locations(item):
            known.append((item.rule_id, location))
    # A delete rule the inventory judged "absent" or left unresolved is exactly the
    # not-applicable call this pass exists to correct: the model recorded a target at the
    # location the reference text still occupies, so that (rule, location) pair would
    # suppress the hit and the deletion is dropped (D04/D08/D17/D19/D20, FL-D101). Rules
    # that already have a resolved needs_edit target keep their coverage.
    resolved_needs_edit = {target.rule_id for target in [*targets, *synthetic]
                           if target.state == "needs_edit" and target.resolution == "resolved"}
    delete_rules = {str(rule.get("rule_id") or "") for rule in rules
                    if is_delete_only_rule(rule, facts)}
    override_rules = frozenset(delete_rules - resolved_needs_edit)
    hits = survey_targets(inspection, rules, facts, known=known, override_rules=override_rules)
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
    append_hits = append_applicability_targets(inspection, rules, facts, sections,
                                               known=editable_known, hinted=hinted)
    hits.extend(append_hits)
    satisfied = [hit for hit in hits if hit.operation == "satisfied"]
    for hit in satisfied:
        target_id = f"Y{len(synthetic) + len(hits) + 1:03d}"
        target = Target(target_id=target_id, rule_id=hit.rule_id, location=hit.locations[0],
                        quote=hit.quote, state="satisfied", reason="survey_new_text_present")
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
        if target.state != "needs_edit":
            continue
        if target.resolution == "composite":
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
                       temp_dir: Path, *, max_compose_calls: int
                       ) -> tuple[dict[str, Any], list[dict[str, Any]], Any, Any, DocumentInspection]:
    """Plan from the ORIGINAL inspection, validate, generate and re-read the final."""
    planned = plan_edits(rules_by_id, targets, inspection, facts, model,
                         max_compose_calls=max_compose_calls)
    edits = build_docx_edits(planned["edits"], inspection)
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
    plan = validate_edit_plan(input_path, edits, {},
                              content_check=content_check_factory(planned["edits"], inspection))
    redline, final = temp_dir / "redline.docx", temp_dir / "final.docx"
    if edits:
        artifacts = generate_artifacts(input_path, plan, redline, final)
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
                   other_edits: Sequence[dict[str, Any]] = ()) -> tuple[str, str, str]:
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
    ledger_text = json.dumps(ledger, ensure_ascii=False, indent=1)
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
        context = "\n\n".join([f"[BEFORE]\n{before_display}", f"[AFTER]\n{after_display}",
                               f"[REQUIREMENTS]\n{requirements}", f"[TARGET_LEDGER]\n{ledger_text}",
                               "[OTHER_AUTHORIZED_EDITS]\n" + json.dumps(list(other_edits),
                                                                           ensure_ascii=False, indent=1)])
        if len(context) <= limit:
            return context, before_text, after_text
    raise RecallError("RECALL_AUDIT_CONTEXT_LIMIT",
                      {"rule": rule["rule_id"], "chars": len(context), "limit": limit})


def _run_audit(model: Any, rules_by_id: dict[str, dict], targets: Sequence[Target],
               planned: dict[str, Any], original: DocumentInspection, actual: DocumentInspection,
               *, only_rules: set[str] | None = None, facts: Facts | None = None) -> dict[str, Any]:
    plan_by_target = _plan_by_target(planned)
    # A target the planner already judged out of scope (its rule's condition does not
    # hold, or it needs a class group / sales-service-fee wording this product cannot
    # carry) must not be re-demanded by the audit; auditing it would report a gap the
    # engine deliberately did not fill (FL-D056).
    out_of_scope = {target.target_id for target in targets if target.out_of_scope}
    auditable = [target for target in targets
                 if target.state == "needs_edit" and target.target_id not in out_of_scope]
    rule_ids = sorted({target.rule_id for target in auditable})
    if only_rules is not None:
        rule_ids = [rule_id for rule_id in rule_ids if rule_id in only_rules]
    results: list[dict[str, Any]] = []
    missed: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for rule_id in rule_ids:
        rule = rules_by_id.get(rule_id)
        if rule is None:
            continue
        rule_targets = [target for target in auditable if target.rule_id == rule_id]
        ledger_ids = {target.target_id for target in rule_targets}
        supplied = {target.location for target in rule_targets}
        other_edits = []
        for other_id, other_targets in _targets_by_rule(auditable).items():
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
            limit=model.max_context_chars, other_edits=other_edits)
        call = model.call(task_type="recall_audit", bounded_context=context, response_schema=AUDIT_SCHEMA,
                          instruction=AUDIT_INSTRUCTION, prompt_version=AUDIT_PROMPT_VERSION)
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
            verified = bool(evidence) and (_compact(evidence) in _compact(after_text)
                                           or _compact(evidence) in _compact(before_text))
            deletion_evidence = False
            if not verified and verdict == "completed":
                # A deletion leaves no AFTER text to quote: the target's own source
                # quote still present in BEFORE is accepted as the deletion evidence.
                target = next((entry for entry in rule_targets if entry.target_id == target_id), None)
                if target is not None and target.quote:
                    after_empty = all(
                        not _region_text(actual, location, rule_targets, 1200).strip()
                        for location in {target.location})
                    if after_empty and _compact(target.quote) in _compact(before_text):
                        verified, deletion_evidence = True, True
                        evidence = evidence or target.quote
            deterministic = False
            if verdict != "completed" and facts is not None:
                # A merged append+delete span can look "wrong" to the model although the
                # append text is present and the loss was authorised by another rule.
                plan_entry = plan_by_target.get(target_id) or {}
                node = next((entry for entry in rule_targets if entry.target_id == target_id), None)
                confirmed = (_confirm_merged_append(rule, plan_entry, node.location, actual,
                                                    facts, rules_by_id, other_edits)
                             if node is not None else None)
                if confirmed:
                    verdict, evidence, verified, deterministic = "completed", confirmed, True, True
            if not verified:
                dropped.append({"code": "AUDIT_EVIDENCE_UNVERIFIED", "rule_id": rule_id,
                                "target_id": target_id, "evidence_quote": _clip(evidence, 80)})
            results.append({"target_id": target_id, "rule_id": rule_id, "verdict": verdict,
                            "reason": str(item.get("reason") or ""),
                            "evidence_quote": evidence, "evidence_verified": verified,
                            "deletion_evidence": deletion_evidence,
                            "deterministic": deterministic})
        for item in value.get("missed_targets") or []:
            if not isinstance(item, dict):
                dropped.append({"code": "AUDIT_MISSED_ITEM_INVALID", "rule_id": rule_id})
                continue
            missed_rule = str(item.get("rule_id") or "")
            location = str(item.get("location") or "")
            quote = str(item.get("quote") or "")
            verified = bool(quote) and (_compact(quote) in _compact(after_text)
                                        or _compact(quote) in _compact(before_text))
            if missed_rule not in rules_by_id or location not in supplied or not verified:
                dropped.append({"code": "AUDIT_MISSED_INVALID", "rule_id": missed_rule,
                                "location": location, "quote": _clip(quote, 80)})
                continue
            missed.append({"rule_id": missed_rule, "location": location, "quote": quote,
                           "reason": str(item.get("reason") or "")})
    return {"rules": rule_ids, "results": results, "missed_targets": missed, "dropped": dropped}


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
    if not any(operation.get("op") == "delete" for operation in rule.get("operations") or []):
        return None
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


def _audit_issues(state: dict[str, Any], targets: Sequence[Target]) -> list[dict[str, Any]]:
    """Current unresolved audit problems: missing/incomplete verdicts and missed targets."""
    issues: list[dict[str, Any]] = []
    results = state.get("results") or {}
    for target in targets:
        if target.state != "needs_edit" or target.out_of_scope:
            continue
        result = results.get(_target_identity(target))
        if result is None:
            issues.append({"code": "AUDIT_VERDICT_MISSING", "rule_id": target.rule_id,
                           "target_id": target.target_id, "location": target.location})
        elif result["verdict"] != "completed" or not result["evidence_verified"]:
            issues.append({"code": "AUDIT_NOT_COMPLETED", "rule_id": target.rule_id,
                           "target_id": target.target_id, "location": target.location,
                           "verdict": result["verdict"], "reason": result["reason"],
                           "evidence_verified": result["evidence_verified"]})
    for rule_id in sorted(state.get("missed") or {}):
        for item in state["missed"][rule_id]:
            issues.append({"code": "AUDIT_MISSED_TARGET", "rule_id": rule_id,
                           "location": item["location"], "quote": item["quote"],
                           "reason": item["reason"]})
    return issues


def _stale_rules(audit_state: dict[str, Any], targets: Sequence[Target]) -> set[str]:
    """Rules whose auditable target set changed since their last verdict."""
    current: dict[str, set[tuple[str, str, str]]] = {}
    for target in targets:
        if target.state == "needs_edit" and not target.out_of_scope:
            current.setdefault(target.rule_id, set()).add(_target_identity(target))
    audited: dict[str, set[tuple[str, str, str]]] = {}
    for identity, result in (audit_state.get("results") or {}).items():
        audited.setdefault(result["rule_id"], set()).add(identity)
    stale = {rule_id for rule_id, identities in current.items()
             if identities != audited.get(rule_id, set())}
    stale |= {rule_id for rule_id in audited if rule_id not in current}
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
                           inspection: DocumentInspection) -> int:
    """Promote verified missed-target reports into source-bound repair targets."""
    existing = {(target.rule_id, target.location) for target in targets}
    existing |= {(target.rule_id, target.location) for target in synthetic}
    added = 0
    for rule_id, items in sorted((audit_state.get("missed") or {}).items()):
        for item in items:
            key = (rule_id, item["location"])
            if key in existing or len(_compact(str(item.get("quote") or ""))) < 4:
                continue
            target = _make_synthetic_target(f"A{len(synthetic) + 1:03d}", rule_id, item["location"],
                                            item["quote"],
                                            f"audit_missed:{_clip(str(item.get('reason') or ''), 80)}",
                                            inspection)
            if target is None:
                continue
            synthetic.append(target)
            origins[target.target_id] = "audit_missed"
            existing.add(key)
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
    existing = {(target.rule_id, target.location) for target in targets}
    existing |= {(target.rule_id, target.location) for target in synthetic}
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
        matched = next((target for target in targets
                        if target.rule_id == rule_id and target.location == finding["location"]),
                       None)
        if matched is not None:
            if rebind(matched, rule, quote):
                added += 1
            continue
        key = (rule_id, finding["location"])
        if key in existing:
            continue
        target = _make_synthetic_target(f"A{len(synthetic) + 1:03d}", rule_id,
                                        finding["location"], quote,
                                        f"sweep:{finding['issue']}", inspection)
        if target is None:
            continue
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


def _rule_already_satisfied(rule: dict, facts: Facts, paragraph_text: str, quote: str) -> bool:
    """Deterministic false-positive filter: the artifact already meets the rule here.

    A finding is dropped (and recorded) when every applicable operation is already
    carried out in the paragraph: the deleted text is gone, or the instantiated
    replacement text is present while the reference old text is gone.

    **Hard-fact-only (FL-D106).** The weaker signals the engine uses — ``slot_group_missing``
    (the product lacks a class group / sales-service-fee wording the rule names) and
    ``class_substitution_noop`` (the product's own letters already read as the target group)
    — are *semantic* judgments about whether the clause applies. They must not silently
    drop a finding the model reported: a product whose classes do not fit the guide's A/C
    model is exactly the case where an edit is most likely needed (可以错杀不能漏判). Such
    findings are kept and flagged through ``weak_rule_signals`` for review instead.
    """
    from .recall import condition_matches, instantiate_slots
    region = _compact(paragraph_text)
    quoted = _compact(quote)
    if not region and not quoted:
        return False
    from .recall import class_substitution_letter_stable
    if class_substitution_letter_stable(rule, facts):
        # Hard fact: the product's own letters already instantiate to the guide's target,
        # so the substitution yields identical text and there is nothing to change.
        return True
    haystack = quoted or region
    operations = [operation for operation in (rule.get("operations") or [])
                  if condition_matches(operation.get("condition"), facts)]
    if not operations:
        return False
    for operation in operations:
        kind = operation.get("op")
        if kind == "noop":
            continue
        if kind == "delete":
            old = _compact(str(operation.get("old_text") or ""))
            if old and old not in region:
                return True
            continue
        new_text, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        if issues or not new_text:
            continue
        new_compact = _compact(new_text)
        old_compact = _compact(str(operation.get("old_text") or ""))
        if kind == "append":
            if new_compact and new_compact in region:
                return True
            continue
        if kind == "replace":
            if new_compact and new_compact in haystack and (not old_compact or old_compact not in region):
                return True
    from .recall import satisfied_by_new_text
    if satisfied_by_new_text(rule, facts, region):
        return True
    return False


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


def _rule_location_absent(rule: dict, facts: Facts, paragraph_text: str,
                          document_text: str) -> bool:
    """The finding's paragraph is not this rule's clause at all (FL-D052).

    A sweep often reports ``unaddressed_requirement`` at every paragraph of the section
    it searched ("收益分配方式分两种…" for the G18 收益分配 rule) even though the rule's
    own reference or variant clause never occurs there. When the paragraph carries none
    of the rule's reference texts — and the rule's required change is already carried out
    somewhere in the artifact — the finding is noise, not a real gap.

    **Hard-fact-only (FL-D106).** The "carries none of the reference texts" test is a
    semantic judgment (a paraphrase has none of them yet is the same clause), so on its
    own it may not discard a model finding. The finding is dropped as noise only when the
    required change is already present **and** the document provably lacks the rule's topic
    (F1 hard fact); otherwise it is kept and the mismatch is recorded as a weak signal.
    """
    from .recall import condition_matches, hard_fact_topic_absent, satisfied_by_new_text
    region = _compact(paragraph_text)
    if not region:
        return False
    operations = [operation for operation in (rule.get("operations") or [])
                  if condition_matches(operation.get("condition"), facts)]
    if not operations:
        return False
    references = [str(operation.get("old_text") or "")
                  for operation in operations if operation.get("op") in {"delete", "replace"}]
    references += [str(variant) for variant in (rule.get("old_text_variants") or [])]
    references = [value for value in references if len(_compact(value)) >= 8]
    if any(_compact(value) in region for value in references):
        return False
    if not document_text:
        return False
    # The requirement must already be met in the produced document for this to be noise.
    if not satisfied_by_new_text(rule, facts, _compact(document_text)):
        return False
    # Even then, only a hard fact ("the contract never mentions this rule's topic") may
    # discard the finding; a paraphrase of the reference is a semantic judgment and the
    # finding stays for review (FL-D106).
    return hard_fact_topic_absent(rule, _compact(document_text))


_DOCUMENT_COMPACT_CACHE: dict[int, str] = {}


def _document_compact(actual: DocumentInspection) -> str:
    """Whitespace-free text of the produced artifact, cached per inspection object."""
    key = id(actual)
    cached = _DOCUMENT_COMPACT_CACHE.get(key)
    if cached is None:
        cached = "".join(_compact(display_text(span.text)[0]) for span in actual.paragraphs)
        _DOCUMENT_COMPACT_CACHE.clear()
        _DOCUMENT_COMPACT_CACHE[key] = cached
    return cached


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


def _sweep_batch(model: Any, rules_by_id: dict[str, dict], requirements: str,
                 chunks: Sequence[_Chunk], actual: DocumentInspection, *,
                 round_number: int, counter: list[int], facts: Facts | None = None,
                 facts_text: str = "", rule_locations: dict[str, set[str]] | None = None
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
    parts = [f"[GUIDE_REQUIREMENTS]\n{requirements}"]
    if facts_text:
        parts.append(f"[FACTS]\n{facts_text}")
    pending: list[_Chunk] = list(chunks)
    while pending:
        chunk = pending.pop(0)
        context = "\n\n".join(parts + [f"[ARTIFACT_WINDOW]\n{chunk.text}"])
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
            located = resolve_quote(span, quote) if span is not None else None
            if located is None:
                chunk_ledger["dropped"].append({"code": "SWEEP_QUOTE_NOT_RESOLVED", "chunk": chunk.id,
                                                "rule_id": rule_id, "location": location,
                                                "quote": _clip(quote, 80)})
                continue
            seen.add(key)
            rule = rules_by_id.get(rule_id) or {}
            paragraph_text = span.text if span is not None else ""
            if rule_locations is not None:
                allowed = rule_locations.get(rule_id)
                if allowed and location not in allowed:
                    # The rule's own section does not contain this paragraph (the sweep
                    # searched by section hint and landed elsewhere): not a real gap.
                    chunk_ledger["dropped"].append({"code": "SWEEP_LOCATION_OUT_OF_SCOPE",
                                                    "chunk": chunk.id, "rule_id": rule_id,
                                                    "location": location, "quote": _clip(quote, 80)})
                    continue
            if facts is not None:
                applicable = [operation for operation in (rule.get("operations") or [])
                              if condition_matches(operation.get("condition"), facts)]
                if not applicable or all(operation.get("op") == "noop" for operation in applicable):
                    chunk_ledger["dropped"].append({"code": "SWEEP_RULE_NOT_APPLICABLE",
                                                    "chunk": chunk.id, "rule_id": rule_id,
                                                    "location": location, "quote": _clip(quote, 80)})
                    continue
                if _rule_already_satisfied(rule, facts, paragraph_text, quote):
                    chunk_ledger["dropped"].append({"code": "SWEEP_ALREADY_SATISFIED", "chunk": chunk.id,
                                                    "rule_id": rule_id, "location": location,
                                                    "quote": _clip(quote, 80)})
                    continue
                if _rule_location_absent(rule, facts, paragraph_text, _document_compact(actual)):
                    chunk_ledger["dropped"].append({"code": "SWEEP_LOCATION_NOT_RULE", "chunk": chunk.id,
                                                    "rule_id": rule_id, "location": location,
                                                    "quote": _clip(quote, 80)})
                    continue
            counter[0] += 1
            chunk_ledger["findings"].append({
                "finding_id": f"SW{counter[0]:03d}", "rule_id": rule_id, "location": location,
                "source_location": location, "quote": quote, "issue": issue,
                "reason": str(item.get("reason") or ""), "artifact_start": located[0],
                "artifact_end": located[1], "chunk": chunk.id, "round": round_number,
                "status": "pending",
            })
        ledger["chunks"].append(chunk_ledger)
        ledger["findings"].extend(chunk_ledger["findings"])
        ledger["dropped"].extend(chunk_ledger["dropped"])
    return ledger


def _resolve_pending(findings: list[dict[str, Any]], batch_ledger: dict[str, Any]) -> None:
    """A re-swept chunk clears pending findings it no longer reports."""
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
                finding["status"] = "resolved"
                finding["resolution"] = f"re-sweep round {batch_ledger['round']} clean"


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


def _write_report_markdown(path: Path, report: dict[str, Any]) -> None:
    plan = report.get("plan") or {}
    audit = report.get("audit") or {}
    sweep = report.get("sweep") or {}
    model = report.get("model") or {}
    targets = report.get("targets") or []
    qualification = report.get("qualification") or {}
    facts = report.get("facts") or {}
    pending_findings = [item for item in sweep.get("findings") or []
                        if item.get("status") in {"pending", "unresolved"}]
    lines = [
        "# FundLex 召回优先处理报告", "",
        f"- 引擎：{report.get('engine_id')} {report.get('engine_version')}"
        f"（schema {report.get('schema_version')}）",
        f"- 执行模式：{report.get('execution_mode')}",
        f"- 源文件 SHA-256：{report.get('source_sha256') or '（未读取）'}",
        f"- 指引文档 SHA-256：{(report.get('guide') or {}).get('document_sha256') or '（未提供）'}",
        f"- 交付状态：{report.get('delivery_status')}",
    ]
    if qualification:
        lines.append(f"- 资格：{qualification.get('status')}（fund_type={qualification.get('fund_type')}；"
                     f"引文核验={qualification.get('fund_type_quote_verified')}）")
    if facts:
        classes = "、".join(str(item.get("name")) for item in facts.get("classes") or [])
        lines.append(f"- 事实：份额类别 {facts.get('class_count')}（{classes or '无'}）；"
                     f"销售服务费类别：{'、'.join(facts.get('service_group') or []) or '无'}；"
                     f"浮动管理费：{'是' if facts.get('is_floating_fee') else '否'}")
    lines.append(f"- 目标计数：应改 {sum(1 for t in targets if t.get('state') == 'needs_edit')}，"
                 f"已符合 {sum(1 for t in targets if t.get('state') == 'satisfied')}，"
                 f"不适用 {sum(1 for t in targets if t.get('state') == 'absent')}；"
                 f"计划修改 {plan.get('count', 0)}")
    lines.append(f"- 审计轮次：{len(audit.get('rounds') or [])}；未决问题 {len(audit.get('issues') or [])}")
    lines.append(f"- 查漏：块 {sweep.get('chunks', 0)}，发现 {len(sweep.get('findings') or [])}，"
                 f"未解决 {len(pending_findings)}，缺口 {len(sweep.get('gaps') or [])}")
    lines.append(f"- 模型调用：{model.get('logical_calls', 0)}；"
                 f"估算费用：{model.get('estimated_cost_usd', 0)}")
    if report.get("errors"):
        lines.append(f"- 错误：{'; '.join(str(item.get('code')) for item in report['errors'])}")

    coverage = ((report.get("scope_mapping") or {}).get("coverage") or [])
    if coverage:
        audit_by_rule: dict[str, dict[str, int]] = {}
        for target in targets:
            result = target.get("audit") or {}
            bucket = audit_by_rule.setdefault(str(target.get("rule_id")), {"completed": 0, "total": 0})
            if target.get("state") == "needs_edit":
                bucket["total"] += 1
                if result.get("verdict") == "completed" and result.get("evidence_verified"):
                    bucket["completed"] += 1
        lines.extend(["", "## 每规则处置", ""])
        for item in coverage:
            counts = item.get("counts") or {}
            rule_id = str(item.get("rule_id"))
            audit_counts = audit_by_rule.get(rule_id, {"completed": 0, "total": 0})
            lines.append(f"- {rule_id}：覆盖 {item.get('coverage')}；"
                         f"目标 {counts.get('targets', 0)}（应改 {counts.get('needs_edit', 0)} / "
                         f"已符合 {counts.get('satisfied', 0)} / 不适用 {counts.get('absent', 0)}）；"
                         f"审计完成 {audit_counts['completed']}/{audit_counts['total']}；"
                         f"章节 {item.get('sections') or '（未映射）'}")
    if audit.get("rounds"):
        lines.extend(["", "## 审计轮次", ""])
        for round_ledger in audit["rounds"]:
            issues = round_ledger.get("issues") or []
            lines.append(f"- 第 {round_ledger.get('round')} 轮（{round_ledger.get('scope', 'full')}）："
                         f"规则 {len(round_ledger.get('rules') or [])}，"
                         f"结论 {len(round_ledger.get('results') or [])}，"
                         f"另报 {len(round_ledger.get('missed_targets') or [])}，"
                         f"丢弃 {len(round_ledger.get('dropped') or [])}，"
                         f"问题 {len(issues)}")
    if sweep.get("rounds"):
        lines.extend(["", "## 查漏轮次", ""])
        for round_ledger in sweep["rounds"]:
            lines.append(f"- 第 {round_ledger.get('round')} 轮：块 {len(round_ledger.get('chunks') or [])}，"
                         f"发现 {len(round_ledger.get('findings') or [])}，"
                         f"丢弃 {len(round_ledger.get('dropped') or [])}")
    for finding in sweep.get("findings") or []:
        lines.append(f"  - {finding.get('finding_id')}：{finding.get('rule_id')} "
                     f"{finding.get('location')} {finding.get('issue')} → {finding.get('status')}")
    unresolved = report.get("unresolved") or []
    lines.extend(["", "## 未完成清单", ""])
    if not unresolved:
        lines.append("- （无）")
    for item in unresolved:
        lines.append(f"- [{item.get('kind')}] {json.dumps(item, ensure_ascii=False)}")
    lines.extend(["", f"**交付状态：{report.get('delivery_status')}**"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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
    try:
        inspection = inspect_docx(input_path, full=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        report["source_sha256"] = inspection.source_sha256
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
        model = gateway or ModelGateway.from_env()
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
        report["facts"] = facts.as_ledger()
        excluded_types = _excluded_types()
        report["qualification"] = {
            "status": "excluded_by_fund_type" if facts.fund_type in excluded_types else "eligible",
            "fund_type": facts.fund_type, "fund_type_quote": facts.fund_type_quote,
            "fund_type_basis": facts.fund_type_basis,
            "fund_type_quote_verified": bool(facts.quotes_verified.get("fund_type")),
            "excluded_types": list(excluded_types), "basis": "facts.fund_type",
            "problems": list(facts.problems),
        }
        if facts.fund_type in excluded_types:
            report["delivery_status"] = "excluded"
            return report

        stage = "scope"
        sections = structure_index(inspection)
        mapping = scope_map(rules, sections, model)
        facts_text = json.dumps(facts.as_ledger(), ensure_ascii=False, indent=1)
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
            _inventory(entry, None, facts, model, inspection, round_number=0)
        synthetic: list[Target] = []
        origins: dict[str, str] = {}
        stage = "survey"
        survey_ledger: list[dict[str, Any]] = []
        coverage_gaps: list[dict[str, Any]] = []
        _run_survey(model, rules, rules_by_id, facts, inspection, _collect_targets(entries, synthetic),
                    synthetic, origins, survey_ledger, coverage_gaps, sections)
        targets = _collect_targets(entries, synthetic)
        rebinds = _rebind_unresolved_targets(targets, origins, inspection,
                                             rules_by_id=rules_by_id, facts=facts,
                                             extend_resolved=True)
        report["rebind"] = rebinds
        report["survey"] = survey_ledger
        report["scope_mapping"] = _scope_mapping_ledger(mapping, sections, entries, rules)
        report["windows"] = [_window_ledger(entry) for entry in entries]

        stage = "write"
        compose_calls = max(DEFAULT_MAX_COMPOSE_CALLS, len(rules))
        with tempfile.TemporaryDirectory(prefix=".recall-", dir=output_dir) as temporary:
            temp_dir = Path(temporary)
            planned, edits, plan, artifacts, actual = _plan_and_generate(
                model, rules_by_id, targets, inspection, facts, input_path, temp_dir,
                max_compose_calls=compose_calls)
            report["plan"] = _plan_ledger(planned, plan)
            report["targets"] = _target_ledger(targets, planned, {}, origins)

            # --- audit + repair loop (business rounds) -----------------------
            stage = "audit"
            audit_state: dict[str, Any] = {"results": {}, "missed": {}}
            audit_rounds: list[dict[str, Any]] = []
            rounds_used = 0
            round_number = 0
            while True:
                round_ledger = _run_audit(model, rules_by_id, targets, planned, inspection, actual,
                                          facts=facts)
                round_ledger.update(round=round_number, scope="full")
                audit_rounds.append(round_ledger)
                _merge_audit_state(audit_state, round_ledger, targets)
                issues = _audit_issues(audit_state, targets)
                round_ledger["issues"] = issues
                report["audit"] = {"rounds": audit_rounds, "issues": issues}
                report["targets"] = _target_ledger(targets, planned, audit_state, origins)
                if not issues:
                    break
                absorbed = _absorb_missed_targets(audit_state, targets, synthetic, origins, inspection)
                notes = _audit_repair_notes(issues, targets, entries)
                if rounds_used >= max_business_rounds or (not notes and not absorbed):
                    break
                rounds_used += 1
                round_number += 1
                for entry in _affected_windows(entries, notes):
                    _inventory(entry, notes[entry.window.id], facts, model, inspection,
                               round_number=round_number)
                targets = _collect_targets(entries, synthetic)
                _run_survey(model, rules, rules_by_id, facts, inspection, targets,
                            synthetic, origins, survey_ledger, coverage_gaps, sections)
                targets = _collect_targets(entries, synthetic)
                report["rebind"] = _rebind_unresolved_targets(
                    targets, origins, inspection, rules_by_id=rules_by_id, facts=facts)
                planned, edits, plan, artifacts, actual = _plan_and_generate(
                    model, rules_by_id, targets, inspection, facts, input_path, temp_dir,
                    max_compose_calls=compose_calls)
                report["plan"] = _plan_ledger(planned, plan)
                report["targets"] = _target_ledger(targets, planned, audit_state, origins)
                report["windows"] = [_window_ledger(entry) for entry in entries]
                report["survey"] = survey_ledger
                report["limits"]["business_rounds_used"] = rounds_used

            # --- final sweep on the actual artifact --------------------------
            stage = "sweep"
            sweep_rounds: list[dict[str, Any]] = []
            findings: list[dict[str, Any]] = []
            gaps: list[dict[str, Any]] = []
            swept_texts: set[str] = set()
            swept_calls = 0
            counter = [0]
            requirements = _sweep_requirements(rules)
            chunk_chars = _sweep_chunk_chars(model, requirements, facts_text)
            chunks = _artifact_chunks(actual, max_chars=chunk_chars)
            rule_locations = {rule_id: _rule_mapped_locations(rule_id, mapping, sections)
                              for rule_id in rules_by_id}
            batch = _take_batch(chunks, max_sweep_chunks - swept_calls, gaps, planned=len(chunks))
            batch_ledger = _sweep_batch(model, rules_by_id, requirements, batch, actual,
                                        round_number=0, counter=counter, facts=facts,
                                        facts_text=facts_text, rule_locations=rule_locations)
            swept_calls += len(batch)
            swept_texts.update(chunk.text for chunk in batch)
            findings.extend(batch_ledger["findings"])
            sweep_rounds.append(batch_ledger)
            report["sweep"] = {"chunks": swept_calls, "findings": findings,
                               "rounds": sweep_rounds, "gaps": gaps}
            while True:
                pending = [finding for finding in findings if finding["status"] == "pending"]
                if not pending or rounds_used >= max_business_rounds:
                    break
                affected_rules = {finding["rule_id"] for finding in pending}
                absorbed = _absorb_sweep_findings(pending, targets, synthetic, origins, inspection,
                                                  rules_by_id=rules_by_id, facts=facts)
                notes = _finding_repair_notes(pending, entries)
                if not notes and not absorbed:
                    break
                rounds_used += 1
                round_number += 1
                for entry in _affected_windows(entries, notes):
                    _inventory(entry, notes[entry.window.id], facts, model, inspection,
                               round_number=round_number)
                targets = _collect_targets(entries, synthetic)
                _run_survey(model, rules, rules_by_id, facts, inspection, targets,
                            synthetic, origins, survey_ledger, coverage_gaps, sections)
                targets = _collect_targets(entries, synthetic)
                report["rebind"] = _rebind_unresolved_targets(
                    targets, origins, inspection, rules_by_id=rules_by_id, facts=facts)
                planned, edits, plan, artifacts, actual = _plan_and_generate(
                    model, rules_by_id, targets, inspection, facts, input_path, temp_dir,
                    max_compose_calls=compose_calls)
                report["plan"] = _plan_ledger(planned, plan)
                report["windows"] = [_window_ledger(entry) for entry in entries]
                report["survey"] = survey_ledger
                report["limits"]["business_rounds_used"] = rounds_used
                # Affected rules plus any rule whose target set changed while the
                # plan was rebuilt; unaffected identical rules keep their verdict.
                reaudit = affected_rules | _stale_rules(audit_state, targets)
                if reaudit:
                    round_ledger = _run_audit(model, rules_by_id, targets, planned, inspection,
                                              actual, only_rules=reaudit, facts=facts)
                    round_ledger.update(round=round_number, scope="sweep_repair")
                    audit_rounds.append(round_ledger)
                    _merge_audit_state(audit_state, round_ledger, targets)
                    round_ledger["issues"] = [issue for issue in _audit_issues(audit_state, targets)
                                              if issue.get("rule_id") in reaudit]
                changed = [chunk for chunk in _artifact_chunks(actual, max_chars=chunk_chars)
                           if chunk.text not in swept_texts]
                batch = _take_batch(changed, max_sweep_chunks - swept_calls, gaps, planned=len(changed))
                if not batch:
                    break  # nothing re-swept: the findings stay pending and block complete
                batch_ledger = _sweep_batch(model, rules_by_id, requirements, batch, actual,
                                            round_number=round_number, counter=counter,
                                            facts=facts, facts_text=facts_text,
                                            rule_locations=rule_locations)
                swept_calls += len(batch)
                swept_texts.update(chunk.text for chunk in batch)
                _resolve_pending(findings, batch_ledger)
                findings.extend(batch_ledger["findings"])
                sweep_rounds.append(batch_ledger)
                report["sweep"] = {"chunks": swept_calls, "findings": findings,
                                   "rounds": sweep_rounds, "gaps": gaps}

            # --- delivery decision -------------------------------------------
            stage = "deliver"
            plan_by_target = _plan_by_target(planned)
            unresolved_targets = [target for target in targets if target.state == "needs_edit"
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
                                                        "status", "reason")}})
            for gap in [*gaps, *coverage_gaps]:
                unresolved.append({"kind": "coverage", **gap})
            report["unresolved"] = unresolved
            report["audit"] = {"rounds": audit_rounds, "issues": audit_issues}
            report["targets"] = _target_ledger(targets, planned, audit_state, origins)
            report["windows"] = [_window_ledger(entry) for entry in entries]
            checks = [*artifacts.checks, "actual_content_verification"]
            hashes = {"final_sha256": artifacts.final_sha256, "redline_sha256": artifacts.redline_sha256}
            complete = (not unresolved_targets and not audit_issues and not pending_findings and not gaps)
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
            return report
    except ModelError as exc:
        if exc.code in STOP_CODES or exc.code in SOFT_STOP_CODES:
            # A transport/budget stop and a malformed model answer both pause the run:
            # the worker keeps the source and the ledger and resumes the same stage.
            raise RecallPipelineStop(exc.code, {"stage": stage, "metrics": exc.metrics}) from exc
        report["errors"].append({"code": exc.code, "stage": stage, "message": exc.code})
        _finalize_failure(report, published)
        return report
    except (RecallError, DocxError, OSError) as exc:
        code = getattr(exc, "code", None) or "OUTPUT_IO_ERROR"
        report["errors"].append({"code": code, "stage": stage, "message": code})
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
        try:
            _write_report_markdown(output_dir / "report.md", report)
            _write_edits(output_dir / "edits.json", report)
        except OSError as exc:
            report["errors"].append({"code": "REPORT_WRITE_FAILED", "stage": "report",
                                     "message": type(exc).__name__})
            if published:
                _finalize_failure(report, published)
