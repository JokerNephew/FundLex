"""Coverage Ledger read-only view (plan v4 §16, §22).

A **projection**, not a storage refactor: it maps the existing runtime state
(``targets`` / ``audit`` / ``unresolved`` / delivery) onto the five terminal
states of the plan, so the delivery gate can later read one view while the
modules keep writing their current state. Storage unification is a later phase
and must not be coupled to generation-strategy work.

Terminal states (plan §40-E):

* ``SATISFIED``         — carried out and audited ``completed``;
* ``ARTIFACT_VERIFIED`` — as ``SATISFIED`` plus explicit artifact-level
  verification evidence (filled by the Phase-8 claim replay);
* ``ALREADY_SATISFIED`` — the contract already carried the policy;
* ``NOT_APPLICABLE``    — judged absent/out of scope for this product/rule;
* ``UNRESOLVED``        — needs work or failed verification; blocks ``complete``.
"""
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

TERMINAL_STATES = ("SATISFIED", "ARTIFACT_VERIFIED", "ALREADY_SATISFIED",
                   "NOT_APPLICABLE", "UNRESOLVED")


def _canonical_state(value: Any) -> str:
    """Map every external status onto the five coverage terminal states.

    Coverage is a proof projection.  An UNKNOWN/CONFLICT (or an unrecognised
    status from an older report) is therefore an open item, never a successful
    terminal state and never something that can disappear from counts.
    """
    state = str(value or "").upper()
    return state if state in TERMINAL_STATES else "UNRESOLVED"


def _site_key(location: str, occurrence: int) -> str:
    return (f"{location}#occurrence:{occurrence}" if occurrence >= 0 else location)


@dataclass(frozen=True)
class CoverageEntry:
    rule_id: str
    location: str
    state: str
    basis: str
    target_id: str = ""
    #: Operation identities this entry covers (``G05:0``); empty means location-level.
    #: Kept so a satisfied replace cannot hide a still-open delete (FL-D117; P0-4).
    operation_keys: tuple[str, ...] = ()
    #: Stable obligation identity.  ``counts`` are obligation scoped, while
    #: ``entries`` may contain one row for every physical artifact site.
    obligation_id: str = ""
    #: Replay's physical site identity (may include ``#occurrence:N``).  Keep
    #: ``location`` as the paragraph lookup key for backwards compatibility.
    site_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", _canonical_state(self.state))

    def as_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "location": self.location,
            "state": self.state,
            "basis": self.basis,
            "target_id": self.target_id,
            "site_id": self.site_id,
            "operation_keys": list(self.operation_keys),
            "obligation_id": self.obligation_id,
        }


@dataclass(frozen=True)
class CoverageLedgerView:
    entries: tuple[CoverageEntry, ...]
    counts: Mapping[str, int]
    #: Site-level counts.  Unlike ``counts`` these intentionally count each
    #: physical site entry and are useful for finding a partially proven
    #: obligation (one site PASS, another FAIL).
    site_counts: Mapping[str, int] = field(default_factory=dict)

    def state_of(self, rule_id: str, location: str) -> str | None:
        return _least_complete(entry.state for entry in self.entries
                               if entry.rule_id == rule_id and entry.location == location)

    def state_of_operation(self, rule_id: str, location: str,
                           operation_key: str) -> str | None:
        """State of one operation, requiring an explicit operation identity.

        An unkeyed legacy row is intentionally invisible to this query.  Treating
        it as proof for every operation would reintroduce cross-authorization at the
        projection/delivery boundary.
        """
        return _least_complete(entry.state for entry in self.entries
                               if entry.rule_id == rule_id and entry.location == location
                               and operation_key in entry.operation_keys)

    @property
    def unresolved(self) -> tuple[CoverageEntry, ...]:
        return tuple(entry for entry in self.entries if entry.state == "UNRESOLVED")

    def as_dict(self) -> dict[str, object]:
        return {"entries": [entry.as_dict() for entry in self.entries],
                "counts": dict(self.counts),
                "site_counts": dict(self.site_counts)}


def _iter_targets(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    targets = report.get("targets")
    if isinstance(targets, list):
        return [item for item in targets if isinstance(item, dict)]
    if isinstance(targets, dict):
        inner = targets.get("targets")
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, dict)]
    return []


def _iter_audit_verdicts(node: Any, depth: int = 0) -> Iterable[tuple[str, str]]:
    """Yield ``(target_id, verdict)`` from the nested audit ledger (tolerant walk)."""
    if depth > 6:
        return
    if isinstance(node, dict):
        target_id = node.get("target_id")
        verdict = node.get("verdict")
        if isinstance(target_id, str) and isinstance(verdict, str):
            yield target_id, verdict
        for value in node.values():
            yield from _iter_audit_verdicts(value, depth + 1)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_audit_verdicts(item, depth + 1)


def _least_complete(states: Iterable[str]) -> str | None:
    values = {_canonical_state(state) for state in states}
    # A location query must not hide one failed occurrence/operation behind a
    # sibling PASS.  All consumers see the same conservative aggregation.
    return next((state for state in ("UNRESOLVED", "SATISFIED", "NOT_APPLICABLE",
                                     "ALREADY_SATISFIED", "ARTIFACT_VERIFIED")
                 if state in values), None)


def _state_counts(states: Iterable[str]) -> dict[str, int]:
    result = {state: 0 for state in TERMINAL_STATES}
    for state in states:
        if state in result:
            result[state] += 1
    return result


def _site_counts(entries: Iterable[CoverageEntry]) -> dict[str, int]:
    # The empty-location row describes a global obligation, not a physical site.
    states: dict[tuple[str, str, tuple[str, ...]], list[str]] = {}
    for entry in entries:
        if entry.location:
            identity = (entry.obligation_id or entry.rule_id,
                        entry.site_id or entry.location, entry.operation_keys)
            states.setdefault(identity, []).append(entry.state)
    return _state_counts(_least_complete(values) or "UNRESOLVED" for values in states.values())


def _terminal_counts(entries: Iterable[CoverageEntry], *, unique: bool) -> dict[str, int]:
    """Count obligation states once, or physical site rows when ``unique`` is false."""
    rows = list(entries)
    if not unique:
        return _state_counts(entry.state for entry in rows)
    grouped: dict[tuple[str, str, tuple[str, ...]], list[str]] = {}
    for entry in rows:
        identity = (entry.obligation_id or entry.rule_id,
                    entry.rule_id, entry.operation_keys)
        grouped.setdefault(identity, []).append(entry.state)
    return _state_counts(_least_complete(states) or "UNRESOLVED"
                         for states in grouped.values())


def _replay_obligations(report: Mapping[str, Any]) -> Mapping[str, Any]:
    replay = report.get("artifact_claim_replay") or report.get("claim_replay") or {}
    value = replay.get("obligations") if isinstance(replay, Mapping) else None
    return value if isinstance(value, Mapping) else {}


def _legacy_replay_provenance(report: Mapping[str, Any]) -> bool:
    """Identify reports written before ALREADY_SATISFIED provenance existed.

    The frozen recall-first reports at engine version 0.1.0 contain valid
    historical coverage counts but cannot be upgraded in place with the new
    source-side evidence.  Keep those stored counts stable while requiring
    every unversioned or newer report to satisfy the current provenance gate.
    """
    return (report.get("engine_id") == "recall_first"
            and report.get("schema_version") == "3"
            and report.get("engine_version") == "0.1.0")


def _site_projection(record: Mapping[str, Any], targets: Mapping[str, Mapping[str, Any]],
                     replay: Mapping[str, Any]) -> list[tuple[str, str, str, str, str]]:
    """Return ``(location, site_id, target_id, state, basis)`` from site proofs.

    Replay site effects are authoritative.  Target inventory is only a fallback
    for legacy reports which predate site effects/evidence.  Negative/placeholder
    inventory rows are deliberately ignored: an ``absent`` summary heading is a
    window assertion, not a business site (D11/D02 false completion regression).
    """
    operation_id = str(record.get("operation_id") or "")
    global_state = _canonical_state(record.get("completion"))
    evidence_by_site: dict[str, list[dict[str, Any]]] = {}
    effects_by_site: dict[str, list[dict[str, Any]]] = {}
    for item in replay.get("site_effects") or ():
        if not isinstance(item, Mapping):
            continue
        if operation_id and str(item.get("operation_id") or operation_id) != operation_id:
            continue
        site_id = str(item.get("site_id") or item.get("location") or "")
        if site_id:
            effects_by_site.setdefault(site_id, []).append(dict(item))
    for item in replay.get("evidence") or ():
        if not isinstance(item, Mapping):
            continue
        if operation_id and str(item.get("operation_id") or operation_id) != operation_id:
            continue
        site_id = str(item.get("site_id") or item.get("location") or "")
        if site_id:
            evidence_by_site.setdefault(site_id, []).append(dict(item))
    for item in record.get("artifact_evidence") or ():
        if not isinstance(item, Mapping):
            continue
        site_id = str(item.get("site_id") or item.get("location") or "")
        if site_id:
            evidence_by_site.setdefault(site_id, []).append(dict(item))

    site_ids = set(effects_by_site) | set(evidence_by_site)
    proof_locations = {str(item.get("location") or str(site_id).split("#occurrence:", 1)[0])
                       for site_id, values in (*evidence_by_site.items(), *effects_by_site.items())
                       for item in values}
    target_for_location: dict[str, str] = {}
    target_for_site: dict[str, str] = {}
    for target_id in record.get("targets") or ():
        target = targets.get(str(target_id))
        if not target or target.get("out_of_scope") or target.get("attribution_error"):
            continue
        # ``absent`` is only a valid site when replay explicitly produced site
        # evidence.  Never manufacture one from a heading/window placeholder.
        if str(target.get("state") or "") in {"absent", "out_of_scope", "not_applicable"}:
            continue
        location = str(target.get("location") or "")
        if location:
            target_for_location.setdefault(location, str(target_id))
            try:
                occurrence = int(target.get("occurrence_index", -1))
            except (TypeError, ValueError):
                occurrence = -1
            target_for_site[_site_key(location, occurrence)] = str(target_id)
            target_state = str(target.get("state") or "")
            # A needs_edit target without a matching replay site is itself an
            # unresolved physical obligation, even when a sibling site passed.
            # Satisfied survey targets are only hints and must not manufacture a
            # failure site (D02 G05 Y010 regression). Absent/out-of-scope rows
            # were filtered above.
            site_key = _site_key(location, occurrence)
            missing_site = (site_key not in site_ids if occurrence >= 0
                            else location not in proof_locations)
            if (target_state not in {"satisfied", "already_satisfied"}
                    and missing_site
                    and global_state != "NOT_APPLICABLE"):
                site_ids.add(site_key)
    for site_id, values in evidence_by_site.items():
        item = values[0]
        location = str(item.get("location") or site_id.split("#occurrence:", 1)[0])
        target_id = str(item.get("target_id") or target_for_location.get(location) or "")
        target_for_location[location] = target_id
        target_for_site.setdefault(site_id, target_id)

    projected: list[tuple[str, str, str, str, str]] = []
    for site_id in sorted(site_ids):
        effect_items = effects_by_site.get(site_id, [])
        evidence_items = evidence_by_site.get(site_id, [])
        # Multiple proof rows for one operation/site are not last-write-wins.
        # A single UNKNOWN/CONFLICT/failed row keeps the site unresolved; this
        # prevents a later PASS from masking an earlier failed occurrence.
        bad_effect = next((item for item in effect_items if
                           str(item.get("state") or "").upper() != "PASS" or
                           item.get("failure_code") or not item.get("proof_kind") or
                           str(item.get("artifact_status") or "").upper()
                           in {"UNKNOWN", "CONFLICT"}), None)
        bad_evidence = next((item for item in evidence_items if
                             ("state" in item and
                              str(item.get("state") or "").upper() != "PASS") or
                             item.get("failure_code") or
                             str(item.get("artifact_status") or "").upper()
                             in {"UNKNOWN", "CONFLICT"}), None)
        bad_proof = bad_effect or bad_evidence
        effect = bad_effect or (effect_items[0] if effect_items else None)
        evidence = evidence_items[0] if evidence_items else None
        item = effect or evidence or {}
        location = str(item.get("location") or site_id.split("#occurrence:", 1)[0])
        if bad_proof is not None:
            state = "UNRESOLVED"
            basis = "claim_replay:" + str(bad_proof.get("failure_code") or
                                           "CLAIM_OPERATION_UNPROVEN")
        elif effect is not None:
            # A PASS site is independently artifact-proven even when another
            # site keeps the obligation globally UNRESOLVED (D11 G18 p800/p1207).
            state = ("ALREADY_SATISFIED" if effect.get("artifact_status") == "ALREADY_SATISFIED"
                     or (effect.get("artifact_status") == "VERIFIED_ABSENT"
                         and effect.get("proof_kind") == "site_literal_effect")
                     else "ARTIFACT_VERIFIED")
            basis = "claim_replay:" + str(effect.get("artifact_status") or "site_pass")
        elif evidence is not None and global_state in {
                "ARTIFACT_VERIFIED", "ALREADY_SATISFIED", "SATISFIED"}:
            # Compatibility with reports predating site_effects: a canonical
            # artifact evidence row is a proof; inventory completion is not. Older
            # records only carried a location, so retain that explicit artifact
            # evidence as a site proof even without a proof_kind field.
            state = _canonical_state(global_state)
            basis = "artifact_evidence:" + str(evidence.get("proof_kind") or "site")
        else:
            state = "UNRESOLVED"
            basis = "site_evidence_missing"
        projected.append((location, site_id,
                          target_for_site.get(site_id, target_for_location.get(location, "")),
                          state, basis))
    return projected


def build_coverage_view(report: Mapping[str, Any]) -> CoverageLedgerView:
    """Project one report into the Coverage Ledger view."""
    # The runtime's canonical operation ledger already consumes the shared effect
    # proofs. Never derive a conflicting completion state from model opinions.
    records = (report.get("obligations") or {}).get("records")
    if isinstance(records, list):
        targets = {str(item.get("target_id") or ""): item
                   for item in _iter_targets(report)}
        replay_obligations = _replay_obligations(report)
        canonical: list[CoverageEntry] = []
        obligation_states: dict[str, str] = {}
        from .effects import effect_proof_passed
        for record in records:
            if not isinstance(record, Mapping):
                continue
            rule_id = str(record.get("rule_id") or "")
            operation_id = str(record.get("operation_id") or "")
            state = _canonical_state(record.get("completion"))
            basis = str(record.get("completion_evidence") or "operation_ledger")
            obligation_id = str(record.get("obligation_id") or "")
            obligation_key = obligation_id or f"{rule_id}:{operation_id}"
            replay = replay_obligations.get(obligation_id, {})
            if not isinstance(replay, Mapping):
                replay = {}
            if (state == "ALREADY_SATISFIED" and replay
                    and not _legacy_replay_provenance(report)
                    and not effect_proof_passed(replay, operation_id=operation_id,
                                                obligation_id=obligation_id)):
                # A stale ledger row cannot preserve a successful coverage state when
                # its replay proof lacks operation-owned source provenance.
                state = "UNRESOLVED"
                basis = "claim_replay:ALREADY_SATISFIED_PROVENANCE"
                replay = {}
            previous_state = obligation_states.get(obligation_key)
            obligation_states[obligation_key] = (
                _least_complete((previous_state, state)) or "UNRESOLVED"
                if previous_state is not None else state)
            site_rows = _site_projection(record, targets, replay)
            # If no site-level replay exists, retain one global row.  This keeps
            # legacy reports queryable without pretending that every inventory
            # target was independently verified.
            if not site_rows:
                location = str(record.get("location") or "")
                site_rows = [(location, location, "", state, basis)]
            for location, site_id, location_target_id, site_state, site_basis in site_rows:
                canonical.append(CoverageEntry(
                    rule_id, location, site_state, site_basis or basis,
                    target_id=location_target_id,
                    site_id=site_id,
                    operation_keys=((operation_id,) if operation_id else ()),
                    obligation_id=obligation_id,
                ))
        # Keep unresolved findings visible, but do not count a second copy when the
        # canonical obligation already represents the same target/site.  This avoids
        # inflating the unresolved count while retaining genuinely extra findings.
        canonical_keys = {(entry.rule_id, entry.location, entry.operation_keys)
                          for entry in canonical}
        for item in report.get("unresolved") or []:
            if not isinstance(item, Mapping):
                continue
            rule_id = str(item.get("rule_id") or "")
            location = str(item.get("location") or "")
            target_id = str(item.get("target_id") or "")
            operation_id = str(item.get("operation_id") or "")
            operation_keys = ((operation_id,) if operation_id else ())
            key = (rule_id, location, operation_keys)
            same_open_operation = bool(operation_id) and any(
                entry.state == "UNRESOLVED" and entry.rule_id == rule_id and
                operation_id in entry.operation_keys for entry in canonical)
            same_open_site = (not operation_id) and any(
                entry.state == "UNRESOLVED" and entry.rule_id == rule_id and
                entry.location == location for entry in canonical)
            if (key in canonical_keys or (same_open_operation and not location)
                    or same_open_site) and any(
                    entry.state == "UNRESOLVED" and
                    entry.rule_id == rule_id and entry.location == location and
                    (not operation_id or operation_id in entry.operation_keys)
                    for entry in canonical):
                continue
            if (same_open_operation and not location) or same_open_site:
                continue
            canonical.append(CoverageEntry(
                rule_id, location, "UNRESOLVED",
                "unresolved:" + str(item.get("code") or item.get("kind") or "unknown"),
                target_id=target_id, operation_keys=((operation_id,) if operation_id else ()),
                obligation_id=str(item.get("obligation_id") or ""),
            ))
        return CoverageLedgerView(
            tuple(canonical),
            _state_counts(obligation_states.values()),
            _site_counts(canonical),
        )
    # The last audit verdict for a target wins (repair rounds overwrite).
    verdicts: dict[str, str] = {}
    for target_id, verdict in _iter_audit_verdicts(report.get("audit")):
        verdicts[target_id] = verdict
    artifact_verified = bool(
        (report.get("artifact_claim_replay") or {}).get("verified"))
    plan_status = {str(entry.get("target_id")): str(entry.get("status") or "")
                   for entry in ((report.get("plan") or {}).get("ledger") or [])
                   if isinstance(entry, dict)}

    entries: list[CoverageEntry] = []
    for target in _iter_targets(report):
        rule_id = str(target.get("rule_id") or "")
        location = str(target.get("location") or "")
        target_id = str(target.get("target_id") or "")
        state = str(target.get("state") or target.get("status") or "")
        verdict = verdicts.get(target_id, "")
        status = plan_status.get(target_id, "")
        operation_keys = tuple(str(key) for key in (target.get("operations") or []))
        if state == "satisfied" or str(target.get("reason") or "").startswith("survey_new_text_present"):
            entries.append(CoverageEntry(rule_id, location, "ALREADY_SATISFIED",
                                         "engine_satisfied", target_id, operation_keys))
        elif state in ("absent", "out_of_scope", "not_applicable") or \
                status in ("satisfied", "not_applicable"):
            entries.append(CoverageEntry(rule_id, location, "NOT_APPLICABLE",
                                         f"engine_{state or status}", target_id,
                                         operation_keys))
        elif verdict == "completed":
            state_value = "ARTIFACT_VERIFIED" if artifact_verified else "SATISFIED"
            entries.append(CoverageEntry(rule_id, location, state_value,
                                         "audit_completed", target_id, operation_keys))
        elif verdict in ("wrong", "incomplete"):
            entries.append(CoverageEntry(rule_id, location, "UNRESOLVED",
                                         f"audit_{verdict}", target_id, operation_keys))
        else:
            entries.append(CoverageEntry(rule_id, location, "UNRESOLVED",
                                         "no_audit_record", target_id, operation_keys))

    for item in report.get("unresolved") or []:
        if not isinstance(item, dict):
            continue
        entries.append(CoverageEntry(
            str(item.get("rule_id") or ""),
            str(item.get("location") or ""),
            "UNRESOLVED",
            "unresolved:" + str(item.get("code") or item.get("kind") or "unknown"),
            str(item.get("target_id") or ""),
        ))

    return CoverageLedgerView(entries=tuple(entries),
                              counts=_terminal_counts(entries, unique=True),
                              site_counts=_site_counts(entries))
