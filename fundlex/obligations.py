"""Operation / Obligation IR and the Obligation-first ledger (plan §6, §10).

A guide rule is no longer an unstructured list of operations.  Every operation has a
stable obligation identity and explicit group semantics:

* ``ALL_OF``       — every obligation in the branch must complete;
* ``ONE_OF``       — only one alternative old-text variant must be handled (a rule
                     may carry several historical wordings that never coexist);
* ``BRANCH``       — conditional branches; an ``UNKNOWN`` condition runs no branch;
* ``INDEPENDENT``  — a single obligation without a sibling.

The ledger is the single view the delivery gate reads.  It is built *before* target
discovery and updated from the real run state, so an applicable obligation cannot
disappear silently when the inventory finds no target for it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .applicability import ApplicabilityDecision, branch_key, describe_condition, evaluate


class GroupKind(str, Enum):
    ALL_OF = "ALL_OF"
    ONE_OF = "ONE_OF"
    BRANCH = "BRANCH"
    INDEPENDENT = "INDEPENDENT"


COMPLETION_STATES = (
    "SATISFIED",
    "ARTIFACT_VERIFIED",
    "ALREADY_SATISFIED",
    "NOT_APPLICABLE",
    "UNRESOLVED",
)
CLOSED_STATES = frozenset({"SATISFIED", "ARTIFACT_VERIFIED", "ALREADY_SATISFIED",
                           "NOT_APPLICABLE"})


@dataclass(frozen=True)
class ObligationSpec:
    obligation_id: str
    rule_id: str
    operation_id: str          # existing engine identity, e.g. G05:1
    operation_index: int
    branch_id: str
    group_kind: GroupKind
    op: str
    condition: Mapping[str, Any] | None
    old_text: str = ""
    new_text: str = ""
    requirement: str = ""
    expected_site: str = ""
    required_facts: tuple[str, ...] = ()
    alternatives: tuple[str, ...] = ()
    one_of_group: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "rule_id": self.rule_id,
            "operation_id": self.operation_id,
            "operation_index": self.operation_index,
            "branch_id": self.branch_id,
            "group_kind": self.group_kind.value,
            "op": self.op,
            "old_text": self.old_text,
            "new_text": self.new_text,
            "condition": dict(self.condition or {}),
            "condition_text": describe_condition(self.condition),
            "requirement": self.requirement,
            "expected_site": self.expected_site,
            "required_facts": list(self.required_facts),
            "alternatives": list(self.alternatives),
            "one_of_group": self.one_of_group,
        }


@dataclass
class ObligationRecord:
    spec: ObligationSpec
    applicability: ApplicabilityDecision
    targets: tuple[str, ...] = ()
    statuses: dict[str, str] = field(default_factory=dict)
    completion: str = "UNRESOLVED"
    completion_evidence: str = ""
    attempt_history: list[dict[str, Any]] = field(default_factory=list)
    # Final execution evidence: the edit(s) that actually carry this obligation and
    # the artifact proof produced by Claim Replay.  Keeping these on the record makes
    # the report traceable from obligation -> edit -> artifact paragraph.
    edit_ids: tuple[str, ...] = ()
    artifact_evidence: list[dict[str, Any]] = field(default_factory=list)

    @property
    def obligation_id(self) -> str:
        return self.spec.obligation_id

    @property
    def closed(self) -> bool:
        return self.completion in CLOSED_STATES

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.spec.as_dict(),
            "applicability": self.applicability.as_dict(),
            "targets": list(self.targets),
            "statuses": dict(self.statuses),
            "completion": self.completion,
            "completion_evidence": self.completion_evidence,
            "attempt_history": list(self.attempt_history),
            "edit_ids": list(self.edit_ids),
            "artifact_evidence": list(self.artifact_evidence),
        }


@dataclass(frozen=True)
class RuleObligationGroup:
    rule_id: str
    group_kind: GroupKind
    branch_ids: tuple[str, ...]
    obligation_ids: tuple[str, ...]
    variant_alternatives: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "group_kind": self.group_kind.value,
            "branch_ids": list(self.branch_ids),
            "obligation_ids": list(self.obligation_ids),
            "variant_alternatives": list(self.variant_alternatives),
        }


@dataclass
class ObligationLedger:
    records: list[ObligationRecord]
    groups: dict[str, RuleObligationGroup]
    aliases: dict[str, str] = field(default_factory=dict)

    def record(self, obligation_id: str) -> ObligationRecord | None:
        for item in self.records:
            if item.obligation_id == obligation_id:
                return item
        canonical = self.aliases.get(obligation_id)
        if canonical:
            return self.record(canonical)
        return None

    def for_rule(self, rule_id: str) -> tuple[ObligationRecord, ...]:
        return tuple(item for item in self.records if item.spec.rule_id == rule_id)

    def unresolved(self) -> tuple[ObligationRecord, ...]:
        return tuple(item for item in self.records if item.completion == "UNRESOLVED")

    @property
    def counts(self) -> dict[str, int]:
        counts = {state: 0 for state in COMPLETION_STATES}
        for item in self.records:
            counts[item.completion] = counts.get(item.completion, 0) + 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "records": [item.as_dict() for item in self.records],
            "groups": [group.as_dict() for group in self.groups.values()],
            "aliases": dict(self.aliases),
            "counts": self.counts,
            "open_obligations": [
                {"obligation_id": item.obligation_id,
                 "rule_id": item.spec.rule_id,
                 "operation_id": item.spec.operation_id,
                 "applicability": item.applicability.status,
                 "reason": item.completion_evidence}
                for item in self.unresolved()
            ],
        }


#: Condition kinds imply the fact that must be VERIFIED before either branch can run.
_CONDITION_FACTS = {
    "class_count": ("share_class_structure",),
    "has_service_fee": ("share_class_structure", "subscription_fee_group", "service_fee_group"),
    "is_floating_fee": ("floating_management_fee",),
}


def _required_facts(condition: Mapping[str, Any] | None,
                    rule_required: Sequence[str]) -> tuple[str, ...]:
    names = list(rule_required)
    if condition:
        kind = str(condition.get("kind") or "")
        names.extend(_CONDITION_FACTS.get(kind, ()))
        if kind == "compound":
            for part in condition.get("value") or []:
                names.extend(_required_facts(part, ()))
    return tuple(sorted({name for name in names if name}))


def compile_obligations(guide_document: Mapping[str, Any]) -> ObligationLedger:
    """Compile every guide operation into the Obligation IR (before any target work)."""
    from .generation.registry import strategy_for

    records: list[ObligationRecord] = []
    groups: dict[str, RuleObligationGroup] = {}
    aliases: dict[str, str] = {}
    for rule in guide_document.get("groups") or []:
        if not isinstance(rule, Mapping):
            continue
        rule_id = str(rule.get("rule_id") or "").strip().upper()
        if not rule_id:
            continue
        operations = [operation for operation in (rule.get("operations") or [])
                      if isinstance(operation, Mapping)]
        if not operations:
            continue
        # Group the operations by condition: distinct conditions are branches, the
        # operations inside one condition form an ALL_OF set.
        branch_order: list[str] = []
        branch_operations: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
        for index, operation in enumerate(operations):
            condition = operation.get("condition") or {"kind": "none"}
            key = branch_key(condition)
            if key not in branch_operations:
                branch_order.append(key)
                branch_operations[key] = []
            branch_operations[key].append((index, operation))
        spec = strategy_for(rule_id)
        variants = tuple(str(value) for value in (rule.get("old_text_variants") or []))
        rule_groups: list[str] = []
        one_of_seen = False
        for branch_index, key in enumerate(branch_order, start=1):
            branch_id = f"B{branch_index}"
            rule_groups.append(branch_id)
            entries = branch_operations[key]
            branch_kind = GroupKind.ALL_OF if len(entries) > 1 else GroupKind.INDEPENDENT
            one_of_by_index: dict[int, str] = {}
            for index, operation in entries:
                # ONLY certified, explicit historical-alternative metadata creates
                # ONE_OF. Wording lists, equal replacements and locations are not
                # business relationships (G05 filing deletion stays independent).
                group_id = str(operation.get("one_of_group") or "")
                if group_id:
                    if operation.get("group_kind") != GroupKind.ONE_OF.value:
                        raise ValueError("GUIDE_ONE_OF_SEMANTICS_INVALID")
                    one_of_seen = True
                    one_of_by_index[index] = group_id
            for position, (index, operation) in enumerate(entries, start=1):
                obligation_id = f"{rule_id}:{branch_id}:O{position}"
                alias = str(operation.get("operation_id") or f"{rule_id}:{index}")
                if alias != f"{rule_id}:{index}" or alias in aliases:
                    raise ValueError("GUIDE_OPERATION_ID_INVALID")
                condition = operation.get("condition") or {"kind": "none"}
                variant_group = one_of_by_index.get(index, "")
                spec_item = ObligationSpec(
                    obligation_id=obligation_id,
                    rule_id=rule_id,
                    operation_id=alias,
                    operation_index=index,
                    branch_id=branch_id,
                    group_kind=(GroupKind.ONE_OF if one_of_by_index.get(index)
                                else GroupKind(operation.get("group_kind") or branch_kind)),
                    op=str(operation.get("op") or ""),
                    condition=condition,
                    old_text=str(operation.get("old_text") or ""),
                    new_text=str(operation.get("new_text") or ""),
                    requirement=str(rule.get("requirement") or ""),
                    expected_site=str(rule.get("section_hint") or ""),
                    required_facts=_required_facts(condition, spec.required_fact_status),
                    alternatives=tuple(dict.fromkeys(
                        [str(value) for value in operation.get("old_text_variants") or []]
                        + [str(other.get("old_text") or "") for _, other in entries
                           if variant_group and other.get("one_of_group") == variant_group
                           and other.get("old_text")])),
                    one_of_group=variant_group,
                )
                records.append(ObligationRecord(
                    spec=spec_item,
                    applicability=evaluate(condition, _EMPTY_FACTS,
                                           rule_id=rule_id,
                                           operation_id=alias),
                    statuses={"applicability": "UNKNOWN", "target": "PENDING",
                              "generation": "PENDING", "execution": "PENDING",
                              "validation": "PENDING", "review": "PENDING",
                              "artifact": "PENDING", "audit": "PENDING",
                              "sweep": "PENDING"},
                ))
                aliases[alias] = obligation_id
                aliases[obligation_id] = obligation_id
        if len(branch_order) > 1:
            group_kind = GroupKind.BRANCH
        elif one_of_seen:
            group_kind = GroupKind.ONE_OF
        elif any(len(items) > 1 for items in branch_operations.values()):
            group_kind = GroupKind.ALL_OF
        else:
            group_kind = GroupKind.INDEPENDENT
        groups[rule_id] = RuleObligationGroup(
            rule_id=rule_id,
            group_kind=group_kind,
            branch_ids=tuple(rule_groups),
            obligation_ids=tuple(item.obligation_id for item in records
                                 if item.spec.rule_id == rule_id),
            variant_alternatives=variants,
        )
    return ObligationLedger(records=records, groups=groups, aliases=aliases)


class _EmptyFacts:
    """Compile-time placeholder: facts are not known when the IR is built."""

    fact_status: dict[str, str] = {}
    quotes_verified: dict[str, bool] = {}
    class_count = 0
    has_service_fee = False
    floating_management_fee = False

    def status_of(self, name: str) -> str:
        return "UNKNOWN"


_EMPTY_FACTS = _EmptyFacts()


def apply_facts(ledger: ObligationLedger, facts: Any, *,
                gateway: Any = None, evidence: str = "",
                inspection: Any = None, resolve_unknown: bool = False) -> None:
    """Attach tri-state applicability; optionally recover UNKNOWN via the models."""
    for item in ledger.records:
        missing = [name for name in item.spec.required_facts
                   if (not facts.quotes_verified.get("floating", False)
                       if name == "floating_management_fee"
                       else facts.status_of(name) != "VERIFIED")]
        if missing:
            decision = ApplicabilityDecision(
                "UNKNOWN", condition=item.spec.condition, rule_id=item.spec.rule_id,
                operation_id=item.spec.operation_id,
                reason="FACT_PREREQUISITE_UNVERIFIED:" + ",".join(missing))
        elif resolve_unknown and gateway is not None and inspection is not None:
            decision = __import__("fundlex.applicability", fromlist=["resolve"]).resolve(
                item.spec.condition, facts, gateway=gateway, evidence=evidence,
                inspection=inspection, rule_id=item.spec.rule_id,
                operation_id=item.spec.operation_id)
        else:
            decision = evaluate(item.spec.condition, facts,
                                rule_id=item.spec.rule_id,
                                operation_id=item.spec.operation_id)
        item.applicability = decision
        item.statuses["applicability"] = decision.status
        if decision.status == "FALSE":
            item.completion = "NOT_APPLICABLE"
            item.completion_evidence = f"applicability_false:{decision.reason}"
        elif decision.status == "UNKNOWN":
            item.completion = "UNRESOLVED"
            item.completion_evidence = f"applicability_unknown:{decision.reason}"
        else:
            # A newly TRUE obligation cannot retain an old FALSE completion.
            item.completion = "UNRESOLVED"
            item.completion_evidence = "OPEN_OBLIGATION:applicability_true"


def _audit_verdicts(node: Any, depth: int = 0) -> Iterable[tuple[str, str]]:
    if depth > 6:
        return
    if isinstance(node, Mapping):
        target_id = node.get("target_id")
        verdict = node.get("verdict")
        if isinstance(target_id, str) and isinstance(verdict, str):
            yield target_id, verdict
        for value in node.values():
            yield from _audit_verdicts(value, depth + 1)
    elif isinstance(node, list):
        for value in node:
            yield from _audit_verdicts(value, depth + 1)


def _iter_targets(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    targets = report.get("targets")
    if isinstance(targets, list):
        return [item for item in targets if isinstance(item, Mapping)]
    if isinstance(targets, Mapping):
        inner = targets.get("targets")
        if isinstance(inner, list):
            return [item for item in inner if isinstance(item, Mapping)]
    return []


def _plan_by_target(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    plan = report.get("plan") or {}
    return {str(entry.get("target_id")): entry
            for entry in (plan.get("ledger") or []) if isinstance(entry, Mapping)}


def _target_covers_operation(target: Mapping[str, Any], record: ObligationRecord) -> bool:
    operations = tuple(str(value) for value in (target.get("operations") or []))
    if not operations:
        # An unknown operation attribution is NOT coverage of the whole rule.  A
        # location-level target must be assigned an operation before it can close an
        # obligation (plan §2: unknown attribution != covers entire rule).  Leaving
        # this as False keeps the obligation OPEN and lets the operation recovery
        # path create a properly attributed target instead of silently dropping a
        # sibling operation.
        return False
    return (record.spec.operation_id in operations
            or record.obligation_id in operations
            or record.spec.obligation_id in operations)


def project(ledger: ObligationLedger, report: Mapping[str, Any], *,
            rules_by_id: Mapping[str, Mapping[str, Any]] | None = None,
            scoped_rules: set[str] | None = None,
            scope_gaps: set[str] | None = None,
            artifact_text: str | None = None) -> None:
    """Project only per-obligation artifact proof; scope/target absence never waives TRUE."""
    from .generation.effects import effect_proof_passed
    targets = _iter_targets(report)
    plans = _plan_by_target(report)
    replay = report.get("artifact_claim_replay") or {}
    proofs = replay.get("obligations") or {}
    failures = replay.get("failures") or []
    scope = report.get("scope_mapping") or {}
    if scoped_rules is None and isinstance(scope.get("mappings"), Mapping):
        scoped_rules = {str(key) for key, locations in scope["mappings"].items() if locations}
    for item in ledger.records:
        item.edit_ids = ()
        item.artifact_evidence = []
        if item.applicability.status == "FALSE":
            item.completion = "NOT_APPLICABLE"
            item.completion_evidence = "applicability_false:" + item.applicability.reason
            item.statuses.update(artifact="NOT_REQUIRED", validation="NOT_REQUIRED")
            continue
        item.completion = "UNRESOLVED"
        if item.applicability.status != "TRUE":
            item.completion_evidence = "applicability_unknown:" + item.applicability.reason
            item.statuses.update(artifact="UNPROVEN", validation="BLOCKED")
            continue
        relevant = [target for target in targets if not target.get("out_of_scope")
                    and _target_covers_operation(target, item)]
        item.targets = tuple(str(target.get("target_id") or "") for target in relevant)
        item.statuses["target"] = "FOUND" if relevant else "MISSING"
        proof = proofs.get(item.obligation_id)
        locations = {str(target.get("location") or "") for target in relevant}
        conflicting = [failure for failure in failures
                       if str(failure.get("obligation_id") or "") == item.obligation_id
                       or (item.spec.rule_id in str(failure.get("rule_id") or "").split("+")
                           and str(failure.get("location") or "") in locations
                           and (not failure.get("operation_id") or
                                failure.get("operation_id") == item.spec.operation_id))]
        if conflicting:
            item.completion_evidence = "CLAIM_REPLAY_FAILED"
            item.statuses.update(artifact="FAIL", validation="FAIL")
        elif effect_proof_passed(proof, operation_id=item.spec.operation_id,
                                 obligation_id=item.obligation_id):
            item.completion = ("ARTIFACT_VERIFIED" if proof.get("edit_ids") or
                proof.get("artifact_status") == "EXPECTED_EFFECT_PRESENT" else "ALREADY_SATISFIED")
            item.completion_evidence = "claim_replay:" + str(proof.get("artifact_status"))
            item.edit_ids = tuple(str(value) for value in proof.get("edit_ids") or [])
            item.artifact_evidence = list(proof.get("evidence") or [])
            item.statuses.update(artifact="VERIFIED", validation="PASS")
        else:
            failed_plan = next((plans[target_id] for target_id in item.targets
                               if target_id in plans and plans[target_id].get("status") == "unresolved"), None)
            if failed_plan:
                item.completion_evidence = "plan:" + str(failed_plan.get("reason") or "unresolved")
            elif isinstance(proof, Mapping):
                item.completion_evidence = str(proof.get("failure_code") or "CLAIM_REPLAY_UNPROVEN")
            elif scope_gaps and item.spec.rule_id in scope_gaps:
                item.completion_evidence = "SCOPE_RULE_OMITTED"
            elif scoped_rules is not None and item.spec.rule_id not in scoped_rules:
                item.completion_evidence = "TARGET_COVERAGE_GAP"
            else:
                item.completion_evidence = "OPEN_OBLIGATION:applicable_without_site_proof"
            item.statuses.update(artifact="UNPROVEN", validation="BLOCKED")
    validate_completion_invariants(ledger)


def validate_completion_invariants(ledger: ObligationLedger) -> None:
    for item in ledger.records:
        allowed = ({"NOT_APPLICABLE"} if item.applicability.status == "FALSE" else
                   {"UNRESOLVED"} if item.applicability.status == "UNKNOWN" else
                   {"ARTIFACT_VERIFIED", "ALREADY_SATISFIED", "UNRESOLVED"})
        if item.completion not in allowed:
            raise ValueError("OBLIGATION_COMPLETION_INVARIANT:" + item.obligation_id)


def open_obligations(ledger: ObligationLedger) -> list[dict[str, Any]]:
    """Unresolved records in report form (for the delivery gate and the user summary)."""
    items: list[dict[str, Any]] = []
    for record in ledger.unresolved():
        items.append({
            "kind": "obligation",
            "code": "OPEN_OBLIGATION",
            "rule_id": record.spec.rule_id,
            "obligation_id": record.obligation_id,
            "operation_id": record.spec.operation_id,
            "branch_id": record.spec.branch_id,
            "applicability": record.applicability.status,
            "failure_class": ("APPLICABILITY"
                              if record.applicability.status == "UNKNOWN" else "TARGET"),
            "reason": record.completion_evidence,
            "expected_site": record.spec.expected_site,
        })
    return items
