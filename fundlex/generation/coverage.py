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
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

TERMINAL_STATES = ("SATISFIED", "ARTIFACT_VERIFIED", "ALREADY_SATISFIED",
                   "NOT_APPLICABLE", "UNRESOLVED")


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


@dataclass(frozen=True)
class CoverageLedgerView:
    entries: tuple[CoverageEntry, ...]
    counts: Mapping[str, int]

    def state_of(self, rule_id: str, location: str) -> str | None:
        for entry in self.entries:
            if entry.rule_id == rule_id and entry.location == location:
                return entry.state
        return None

    def state_of_operation(self, rule_id: str, location: str,
                           operation_key: str) -> str | None:
        """State of one operation; falls back to location-level entries when unkeyed."""
        for entry in self.entries:
            if entry.rule_id != rule_id or entry.location != location:
                continue
            if not entry.operation_keys or operation_key in entry.operation_keys:
                return entry.state
        return None

    @property
    def unresolved(self) -> tuple[CoverageEntry, ...]:
        return tuple(entry for entry in self.entries if entry.state == "UNRESOLVED")


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


def build_coverage_view(report: Mapping[str, Any]) -> CoverageLedgerView:
    """Project one report into the Coverage Ledger view."""
    # The last audit verdict for a target wins (repair rounds overwrite).
    verdicts: dict[str, str] = {}
    for target_id, verdict in _iter_audit_verdicts(report.get("audit")):
        verdicts[target_id] = verdict
    artifact_verified = bool(
        (report.get("artifact_claim_replay") or {}).get("verified"))

    entries: list[CoverageEntry] = []
    for target in _iter_targets(report):
        rule_id = str(target.get("rule_id") or "")
        location = str(target.get("location") or "")
        target_id = str(target.get("target_id") or "")
        state = str(target.get("state") or target.get("status") or "")
        verdict = verdicts.get(target_id, "")
        operation_keys = tuple(str(key) for key in (target.get("operations") or []))
        if state == "satisfied" or str(target.get("reason") or "").startswith("survey_new_text_present"):
            entries.append(CoverageEntry(rule_id, location, "ALREADY_SATISFIED",
                                         "engine_satisfied", target_id, operation_keys))
        elif state in ("absent", "out_of_scope", "not_applicable"):
            entries.append(CoverageEntry(rule_id, location, "NOT_APPLICABLE",
                                         f"engine_{state}", target_id, operation_keys))
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

    counts = {state: 0 for state in TERMINAL_STATES}
    for entry in entries:
        counts[entry.state] = counts.get(entry.state, 0) + 1
    return CoverageLedgerView(entries=tuple(entries), counts=counts)
