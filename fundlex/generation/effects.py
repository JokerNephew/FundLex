"""One operation's effect, proven at every verified business site.

No document-wide text is accepted as a substitute for a missing site. Source offsets
are used only on the source; the final paragraph is reconstructed from the final edit
set, including all sibling components, before its own effect is considered.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


@dataclass(frozen=True)
class OperationEffect:
    state: str
    artifact_status: str
    rule_id: str
    operation_id: str
    obligation_id: str
    sites: tuple[str, ...] = ()
    edit_ids: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    failure_code: str = ""
    reason: str = ""
    site_effects: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "sites": list(self.sites), "edit_ids": list(self.edit_ids),
                "evidence": list(self.evidence), "site_effects": list(self.site_effects),
                "operations": [self.operation_id]}


def _keys(edit: Mapping[str, Any]) -> set[str]:
    evidence = edit.get("evidence") or {}
    result = {str(value) for value in edit.get("operation_keys") or ()}
    result.update(str(value) for value in evidence.get("operation_keys") or ())
    result.update(value.strip() for value in str(edit.get("operation_id") or "").split(",")
                  if value.strip())
    return result


def operation_units(edits: Sequence[Mapping[str, Any]], operation_id: str
                    ) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """A merged parent cannot lend its sibling's span to a component operation."""
    units = []
    for edit in edits:
        components = edit.get("components") or []
        for unit in components or [edit]:
            if isinstance(unit, Mapping) and operation_id in _keys(unit):
                units.append((edit, unit))
    return units


def effect_proof_passed(proof: Mapping[str, Any] | None, *, operation_id: str = "",
                        obligation_id: str = "") -> bool:
    """Shared consumer gate for replay, projection, sweep and delivery."""
    if not isinstance(proof, Mapping) or proof.get("state") != "PASS":
        return False
    if operation_id and proof.get("operation_id") != operation_id:
        return False
    if obligation_id and proof.get("obligation_id") != obligation_id:
        return False
    if proof.get("artifact_status") == "NOT_REQUIRED":
        return bool(proof.get("evidence"))
    sites = set(proof.get("sites") or ())
    evidence = proof.get("evidence") or ()
    proven_sites = {item.get("site_id") for item in evidence if isinstance(item, Mapping)
                    and item.get("proof_kind") and item.get("operation_id") == proof.get("operation_id")
                    and item.get("obligation_id") == proof.get("obligation_id")}
    effects = proof.get("site_effects") or ()
    return bool(sites) and sites <= proven_sites and not proof.get("failure_code") and all(
        item.get("state") == "PASS" for item in effects)


def evaluate_operation_effect(obligation: Any, original: Any, artifact: Any,
                              sites: Sequence[Mapping[str, Any]],
                              edits: Sequence[Mapping[str, Any]], facts: Any,
                              *, validated_units: Sequence[Mapping[str, Any]] = ()
                              ) -> OperationEffect:
    spec = obligation.spec
    rule_id, operation_id = spec.rule_id, spec.operation_id
    obligation_id = obligation.obligation_id
    base = dict(rule_id=rule_id, operation_id=operation_id, obligation_id=obligation_id)
    applicability = obligation.applicability.status
    if applicability == "FALSE":
        return OperationEffect("NOT_APPLICABLE", "NOT_REQUIRED", **base)
    if applicability != "TRUE":
        return OperationEffect("OPEN", "UNPROVEN", **base,
                               failure_code="APPLICABILITY_UNKNOWN")
    if spec.op == "noop":
        return OperationEffect("PASS", "NOT_REQUIRED", **base, evidence=({
            "proof_kind": "certified_noop_branch", "operation_id": operation_id,
            "obligation_id": obligation_id},))
    if not sites:
        return OperationEffect("OPEN", "UNPROVEN", **base,
                               failure_code="CLAIM_OPERATION_UNPROVEN", reason="verified site missing")
    from ..recall import instantiate_slots
    from .claim_replay import _expected_after
    expected = str(spec.new_text or "")
    try:
        instantiated, issues = instantiate_slots(expected, facts)
        if not issues and instantiated:
            expected = instantiated
    except (AttributeError, TypeError):
        pass
    own_units = operation_units(edits, operation_id)
    evidence: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    edit_ids: list[str] = []
    seen: set[str] = set()
    for site in sites:
        location = str(site.get("location") or site.get("site_id") or "")
        occurrence = int(site.get("occurrence_index", -1))
        site_id = f"{location}#occurrence:{occurrence}" if occurrence >= 0 else location
        if not location or site_id in seen:
            continue
        seen.add(site_id)
        item = {"site_id": site_id, "location": location, **base,
                "state": "OPEN", "artifact_status": "UNPROVEN",
                "failure_code": "CLAIM_OPERATION_UNPROVEN"}
        try:
            before = str(original.by_location(location).text)
            after = str(artifact.by_location(location).text)
        except (KeyError, ValueError, AttributeError, IndexError):
            results.append(item)
            continue
        quote = str(site.get("quote") or "")
        if not quote or _compact(quote) not in _compact(before):
            results.append(item)
            continue
        parent_edits = [edit for edit in edits if str(edit.get("location") or "") == location]
        own = [(edit, unit) for edit, unit in own_units
               if str(unit.get("location") or edit.get("location") or "") == location
               and (occurrence < 0 or unit.get("target_id") == site.get("target_id"))]
        actual_expected = _expected_after(before, parent_edits) if parent_edits else before
        planned_matches = actual_expected is not None and actual_expected == after
        unit_proofs = [unit for unit in validated_units
                       if str(unit.get("location") or "") == location
                       and (occurrence < 0 or unit.get("target_id") == site.get("target_id"))
                       and operation_id in {value.strip() for value in
                                            str(unit.get("operation_id") or "").split(",")}]
        validated = bool(unit_proofs) and all(unit.get("verdict") == "PASS" for unit in unit_proofs)
        expected_present = bool(expected) and _compact(expected) in _compact(after)
        if occurrence >= 0 and spec.op == "replace":
            from .claim_replay import _occurrence_positions
            positions = _occurrence_positions(before, str(spec.old_text or ""))
            expected_present = False
            if occurrence < len(positions):
                left, right = positions[occurrence]
                shift = 0
                bounded = True
                for edit in sorted(parent_edits, key=lambda value: int(value.get("start") or 0)):
                    start, end = int(edit["start"]), int(edit["end"])
                    replacement = str(edit.get("replacement") or "")
                    if end <= left:
                        shift += len(replacement) - (end - start)
                    elif start < right:
                        if start == left and end == right:
                            right = left + len(replacement)
                        else:
                            bounded = False
                        break
                expected_present = bounded and _compact(after[left + shift:right + shift]) == _compact(expected)
        old_wordings = [str(spec.old_text or ""), *getattr(spec, "alternatives", ())]
        # Residual is evaluated in this verified site. Source offsets never slice AFTER.
        residual = any(_compact(old) and _compact(old) in _compact(after)
                       and _compact(old) not in _compact(expected) for old in old_wordings)
        if own:
            edit_ids.extend(str(edit.get("edit_id") or
                                f"{edit.get('rule_id')}:{edit.get('target_id')}")
                            for edit, _ in own)
            if spec.op == "delete" and validated and not residual and all(
                    not _compact(str(unit.get("before") or "")) or
                    _compact(str(unit.get("before") or "")) not in _compact(after)
                    for unit in unit_proofs):
                # An independently proven deletion stays proven when another
                # component has an execution failure. Paragraph integrity still
                # blocks the document separately in Claim Replay.
                item.update(state="PASS", artifact_status="VERIFIED_ABSENT", failure_code="")
            elif not planned_matches:
                item.update(state="FAIL", artifact_status="WRONG_EFFECT",
                            failure_code="CLAIM_EXECUTION_EFFECT_MISSING")
            elif not validated:
                item.update(state="FAIL", artifact_status="WRONG_EFFECT",
                            failure_code="CLAIM_PLANNED_EFFECT_MISSING")
            elif spec.op == "delete" and residual:
                item.update(state="FAIL", artifact_status="RESIDUAL_OLD_TEXT",
                            failure_code="RESIDUAL_OLD_TEXT")
            elif spec.op == "replace" and residual and rule_id not in {"G02", "G04"}:
                item.update(state="FAIL", artifact_status="RESIDUAL_OLD_TEXT",
                            failure_code="RESIDUAL_OLD_TEXT")
            else:
                # Validated unit proof covers semantic compose as well as exact
                # templates; it has passed operation authorization and hard validators.
                item.update(state="PASS", artifact_status=("VERIFIED_ABSENT"
                            if spec.op == "delete" else "EXPECTED_EFFECT_PRESENT"), failure_code="")
        elif spec.op == "delete" and not residual:
            item.update(state="PASS", artifact_status="VERIFIED_ABSENT", failure_code="")
        elif spec.op in {"replace", "append"} and expected_present and not residual:
            item.update(state="PASS", artifact_status="ALREADY_SATISFIED", failure_code="")
        else:
            item.update(state="FAIL", artifact_status=("RESIDUAL_OLD_TEXT" if residual
                        else "MISSING_EFFECT"), failure_code="CLAIM_OPERATION_NOT_PLANNED")
        item.update(before_quote=quote, after_quote=after,
                    proof_kind="site_final_plan_reconstruction" if own else "site_literal_effect")
        evidence.append({key: item[key] for key in ("rule_id", "operation_id", "obligation_id",
            "site_id", "location", "before_quote", "after_quote", "proof_kind")})
        results.append(item)
    if not results:
        return OperationEffect("OPEN", "UNPROVEN", **base,
                               failure_code="CLAIM_OPERATION_UNPROVEN")
    failure = next((item for item in results if item["state"] == "FAIL"), None)
    unproven = next((item for item in results if item["state"] == "OPEN"), None)
    worst = failure or unproven
    status = worst["artifact_status"] if worst else (
        "VERIFIED_ABSENT" if spec.op == "delete" else
        "EXPECTED_EFFECT_PRESENT" if own_units else "ALREADY_SATISFIED")
    return OperationEffect(worst["state"] if worst else "PASS", status, **base,
        sites=tuple(sorted(seen)), edit_ids=tuple(dict.fromkeys(edit_ids)), evidence=tuple(evidence),
        failure_code=worst["failure_code"] if worst else "", site_effects=tuple(results))
