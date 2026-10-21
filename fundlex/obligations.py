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
    "has_service_fee": ("share_class_structure",),
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
            # Operations with the same replacement text and the same condition are
            # alternative historical wordings (G11/G12/G14 old_text variants), not
            # independent obligations: only the variant actually present in the
            # contract must be handled (plan §6.3, §27).
            variant_groups: dict[tuple[str, str], list[tuple[int, Mapping[str, Any]]]] = {}
            for index, operation in entries:
                identity = (str(operation.get("op") or ""),
                            re.sub(r"\s+", "", str(operation.get("new_text") or "")))
                variant_groups.setdefault(identity, []).append((index, operation))
            one_of_by_index: dict[int, str] = {}
            for group_number, group in enumerate(variant_groups.values(), start=1):
                if len(group) < 2:
                    continue
                if len({str(op.get("old_text") or "") for _index, op in group}) < 2:
                    continue
                group_id = f"{rule_id}:{branch_id}:ONE{group_number}"
                one_of_seen = True
                for index, _operation in group:
                    one_of_by_index[index] = group_id
            for position, (index, operation) in enumerate(entries, start=1):
                obligation_id = f"{rule_id}:{branch_id}:O{position}"
                alias = f"{rule_id}:{index}"
                condition = operation.get("condition") or {"kind": "none"}
                variant_group = (one_of_by_index.get(index) or
                                 (f"{rule_id}:{branch_id}:VARIANTS" if variants else ""))
                spec_item = ObligationSpec(
                    obligation_id=obligation_id,
                    rule_id=rule_id,
                    operation_id=alias,
                    operation_index=index,
                    branch_id=branch_id,
                    group_kind=(GroupKind.ONE_OF if one_of_by_index.get(index)
                                else branch_kind),
                    op=str(operation.get("op") or ""),
                    condition=condition,
                    old_text=str(operation.get("old_text") or ""),
                    new_text=str(operation.get("new_text") or ""),
                    requirement=str(rule.get("requirement") or ""),
                    expected_site=str(rule.get("section_hint") or ""),
                    required_facts=_required_facts(condition, spec.required_fact_status),
                    alternatives=variants,
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
        elif variants or one_of_seen:
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
        if resolve_unknown and gateway is not None and inspection is not None:
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


def _satisfied_rules(report: Mapping[str, Any]) -> set[str]:
    """Rules the deterministic filters proved already satisfied (no edit needed)."""
    rules: set[str] = set()
    for round_ledger in (report.get("sweep") or {}).get("rounds") or []:
        for dropped in round_ledger.get("dropped") or []:
            if isinstance(dropped, Mapping) and \
                    str(dropped.get("code") or "") in {"SWEEP_ALREADY_SATISFIED",
                                                       "SWEEP_RULE_NOT_APPLICABLE"}:
                rule_id = str(dropped.get("rule_id") or "")
                if rule_id:
                    rules.add(rule_id)
    return rules


def _satisfied_operations(report: Mapping[str, Any]) -> set[str]:
    """Operation keys for which the contract already carries the policy text."""
    satisfied: set[str] = set()
    for entry in report.get("survey") or []:
        if not isinstance(entry, Mapping):
            continue
        for record in entry.get("records") or []:
            if not isinstance(record, Mapping):
                continue
            if str(record.get("operation") or "") == "satisfied":
                satisfied.update(str(key) for key in record.get("operation_keys") or [])
    for target in _iter_targets(report):
        if str(target.get("state") or "") == "satisfied":
            satisfied.update(str(key) for key in target.get("operations") or [])
    return satisfied


def project(ledger: ObligationLedger, report: Mapping[str, Any], *,
            rules_by_id: Mapping[str, Mapping[str, Any]] | None = None,
            scoped_rules: set[str] | None = None,
            scope_gaps: set[str] | None = None,
            artifact_text: str | None = None) -> None:
    """Derive each obligation's completion from the *actual* run state."""
    targets = _iter_targets(report)
    plan_by_target = _plan_by_target(report)
    verdicts: dict[str, str] = {}
    for target_id, verdict in _audit_verdicts(report.get("audit")):
        verdicts[target_id] = verdict
    replay = report.get("artifact_claim_replay") or {}
    replay_obligations = (replay.get("obligations") or {}
                          if isinstance(replay, Mapping) else {})
    if not isinstance(replay_obligations, Mapping):
        replay_obligations = {}
    replay_failures = {(str(item.get("rule_id") or ""), str(item.get("location") or ""))
                       for item in replay.get("failures") or [] if isinstance(item, Mapping)}
    unresolved_items = [item for item in (report.get("unresolved") or [])
                        if isinstance(item, Mapping)]
    satisfied_operations = _satisfied_operations(report)
    satisfied_rules = _satisfied_rules(report)
    import re as _re
    authorized_new = _re.sub(r"\s+", "", "".join(
        str(record.spec.new_text or "") for record in ledger.records))
    if scoped_rules is None:
        scope = report.get("scope_mapping")
        if isinstance(scope, Mapping) and isinstance(scope.get("mappings"), Mapping):
            scoped_rules = {str(rule_id) for rule_id, ids in scope["mappings"].items() if ids}
        # No scope information at all: do not invent a document-level exclusion.

    for record in ledger.records:
        item = record
        if item.applicability.status == "FALSE":
            item.completion = "NOT_APPLICABLE"
            item.completion_evidence = item.completion_evidence or "applicability_false"
            item.statuses.update(target="NOT_REQUIRED", generation="NOT_REQUIRED",
                                 validation="NOT_REQUIRED", review="NOT_REQUIRED",
                                 artifact="NOT_REQUIRED", audit="NOT_REQUIRED",
                                 sweep="NOT_REQUIRED")
            continue
        if item.applicability.status == "UNKNOWN":
            item.completion = "UNRESOLVED"
            item.completion_evidence = item.completion_evidence or "applicability_unknown"
            item.statuses["validation"] = "BLOCKED"
            continue

        if artifact_text is not None and item.spec.one_of_group:
            import re as _re
            probe = _re.sub(r"\s+", "", item.spec.old_text)
            if probe and probe not in authorized_new and \
                    probe in _re.sub(r"\s+", "", artifact_text):
                # The alternative's own wording still exists in the artifact and is
                # not part of any authorized new policy text: a different sibling's
                # success cannot close it (plan §6.3).
                item.completion = "UNRESOLVED"
                item.completion_evidence = "ONE_OF_VARIANT_RESIDUAL"
                item.statuses["validation"] = "FAIL"
                continue

        relevant = [target for target in targets
                    if str(target.get("rule_id") or "") == item.spec.rule_id
                    and not target.get("out_of_scope")
                    and _target_covers_operation(target, item)]
        relevant_ids = tuple(str(target.get("target_id") or "") for target in relevant)
        item.targets = relevant_ids
        item.statuses["target"] = "FOUND" if relevant else "MISSING"

        if not relevant:
            # Claim Replay may have closed the operation at its own site even when the
            # planner's target was judged out of scope (for example a delete whose old
            # wording is already absent).  Its operation-scoped PASS is authoritative.
            replay_item = replay_obligations.get(item.obligation_id)
            if isinstance(replay_item, Mapping) and replay_item.get("state") == "PASS" \
                    and str(replay_item.get("artifact_status") or "") in {
                        "ALREADY_SATISFIED", "VERIFIED_ABSENT",
                        "EXPECTED_EFFECT_PRESENT", "NOT_REQUIRED",
                        "ALTERNATIVE_NOT_SELECTED"}:
                item.completion = ("ARTIFACT_VERIFIED"
                                   if replay_item.get("artifact_status") ==
                                   "EXPECTED_EFFECT_PRESENT" else "ALREADY_SATISFIED")
                item.completion_evidence = "claim_replay:" + str(
                    replay_item.get("artifact_status"))
                item.statuses.update(target="SATISFIED", generation="NOT_REQUIRED",
                                     validation="PASS", artifact="VERIFIED")
                item.edit_ids = tuple(str(value) for value in
                                      (replay_item.get("edit_ids") or []) if value)
                item.artifact_evidence = [dict(value) for value in
                                          (replay_item.get("evidence") or [])
                                          if isinstance(value, Mapping)]
                continue
            rule_absent_targets = [target for target in targets
                                   if str(target.get("rule_id") or "") == item.spec.rule_id
                                   and str(target.get("state") or "") == "absent"
                                   and not target.get("out_of_scope")]
            rule_satisfied_targets = [target for target in targets
                                      if str(target.get("rule_id") or "") == item.spec.rule_id
                                      and str(target.get("state") or "") == "satisfied"
                                      and not target.get("out_of_scope")]
            if rule_satisfied_targets and artifact_text is not None and \
                    item.spec.op in {"delete", "replace"}:
                import re as _re
                compact_artifact = _re.sub(r"\s+", "", artifact_text)
                probes = [_re.sub(r"\s+", "", _re.sub(
                              r"^[A-ZＡ-Ｚ]\s*类(?:基金份额)?的?", "", sentence).strip())
                          for sentence in _re.split(r"(?<=[。；;])", item.spec.old_text)]
                if any(probe and probe in compact_artifact for probe in probes):
                    item.completion = "UNRESOLVED"
                    item.completion_evidence = "SATISFIED_TARGET_RESIDUAL_DELETE"
                    item.statuses.update(target="SATISFIED", generation="FAIL",
                                         validation="FAIL")
                    continue
            if rule_absent_targets and artifact_text is not None:
                # An "absent" verdict is coverage only for the operation whose reference
                # is genuinely absent.  It is not a rule-wide waiver.
                import re as _re
                compact_artifact = _re.sub(r"\s+", "", artifact_text)
                probes: list[str] = []
                for sentence in _re.split(r"(?<=[。；;])", item.spec.old_text):
                    probe = _re.sub(r"^[A-ZＡ-Ｚ]\s*类(?:基金份额)?的?", "",
                                    sentence).strip()
                    if len(_re.sub(r"\s+", "", probe)) >= 8:
                        probes.append(_re.sub(r"\s+", "", probe))
                residual = any(probe in compact_artifact for probe in probes)
                if item.spec.op in {"delete", "replace"} and residual:
                    item.completion = "UNRESOLVED"
                    item.completion_evidence = "ABSENT_TARGET_RESIDUAL_OLD_TEXT"
                    item.statuses.update(target="ABSENT", generation="FAIL",
                                         validation="FAIL")
                    continue
                if item.spec.op == "delete":
                    item.completion = "NOT_APPLICABLE"
                    item.completion_evidence = "target_absent_reference_absent"
                    item.statuses.update(target="ABSENT", generation="NOT_REQUIRED",
                                         validation="PASS", audit="NOT_REQUIRED")
                    continue
                if item.spec.op == "replace":
                    new_compact = _re.sub(r"\s+", "", item.spec.new_text)
                    if new_compact and new_compact in compact_artifact:
                        item.completion = "ALREADY_SATISFIED"
                        item.completion_evidence = "target_absent_new_effect_present"
                        item.statuses.update(target="ABSENT", generation="NOT_REQUIRED",
                                             validation="PASS", audit="NOT_REQUIRED")
                        continue
            if item.spec.rule_id in satisfied_rules:
                item.completion = "ALREADY_SATISFIED"
                item.completion_evidence = "deterministic_rule_already_satisfied"
                item.statuses.update(target="SATISFIED", generation="NOT_REQUIRED",
                                     validation="PASS", audit="NOT_REQUIRED")
                continue
            if item.spec.operation_id in satisfied_operations or \
                    item.obligation_id in satisfied_operations:
                if item.spec.op == "delete" and artifact_text is not None:
                    import re as _re
                    compact_artifact = _re.sub(r"\s+", "", artifact_text)
                    probes = [_re.sub(r"\s+", "", _re.sub(
                                  r"^[A-ZＡ-Ｚ]\s*类(?:基金份额)?的?", "", sentence).strip())
                              for sentence in _re.split(r"(?<=[。；;])", item.spec.old_text)]
                    if any(probe and probe in compact_artifact for probe in probes):
                        item.completion = "UNRESOLVED"
                        item.completion_evidence = "SURVEY_SATISFIED_RESIDUAL_DELETE"
                        item.statuses["validation"] = "FAIL"
                        continue
                item.completion = "ALREADY_SATISFIED"
                item.completion_evidence = "survey_new_text_present"
                item.statuses.update(target="SATISFIED", generation="NOT_REQUIRED",
                                     validation="PASS", audit="NOT_REQUIRED")
                continue
            rule_targets = [entry for entry in targets
                            if str(entry.get("rule_id") or "") == item.spec.rule_id]
            rule_plan = [plan_by_target.get(str(entry.get("target_id") or ""))
                         for entry in rule_targets]
            rule_plan = [entry for entry in rule_plan if entry]
            sibling_satisfied = (
                rule_targets
                and not any(str(entry.get("state") or "") == "needs_edit"
                            for entry in rule_targets)
                and any(str(entry.get("state") or "") == "satisfied"
                        for entry in rule_targets))
            plan_satisfied = (
                rule_plan
                and all(str(entry.get("status") or "") in {"satisfied", "not_applicable"}
                        for entry in rule_plan))
            if item.spec.op in {"replace", "append"} and (sibling_satisfied or plan_satisfied):
                # One rule-level target/plan already satisfies the clause and no sibling
                # still needs an edit: the other replacement of the same rule is part of
                # that satisfied clause, not an open obligation.
                item.completion = "ALREADY_SATISFIED"
                item.completion_evidence = ("plan_satisfied" if plan_satisfied
                                            else "sibling_target_satisfied")
                item.statuses.update(target="SATISFIED", generation="NOT_REQUIRED",
                                     validation="PASS", audit="NOT_REQUIRED")
                continue
            if item.spec.op == "delete" and artifact_text is not None:
                import re as _re
                compact_artifact = _re.sub(r"\s+", "", artifact_text)
                probes: list[str] = []
                for sentence in _re.split(r"(?<=[。；;])", item.spec.old_text):
                    probe = _re.sub(r"^[A-ZＡ-Ｚ]\s*类(?:基金份额)?的?", "",
                                    sentence).strip()
                    if len(_re.sub(r"\s+", "", probe)) >= 8:
                        probes.append(_re.sub(r"\s+", "", probe))
                if probes and not any(probe in compact_artifact for probe in probes):
                    item.completion = "NOT_APPLICABLE"
                    item.completion_evidence = "delete_reference_absent"
                    item.statuses.update(target="ABSENT", generation="NOT_REQUIRED",
                                         validation="PASS", audit="NOT_REQUIRED")
                    continue
            rule_unresolved = [entry for entry in unresolved_items
                               if str(entry.get("rule_id") or "") == item.spec.rule_id]
            if rule_unresolved:
                item.completion = "UNRESOLVED"
                item.completion_evidence = ("unresolved:" +
                                            str(rule_unresolved[0].get("code") or
                                                rule_unresolved[0].get("reason") or "rule"))
            elif item.spec.op == "noop":
                item.completion = "NOT_APPLICABLE"
                item.completion_evidence = "noop_operation"
            elif scope_gaps is not None and item.spec.rule_id in scope_gaps:
                # The model omitted this rule from its scope answer even after a
                # focused retry. That is a coverage gap, never proof of absence.
                item.completion = "UNRESOLVED"
                item.completion_evidence = "SCOPE_RULE_OMITTED"
            elif scoped_rules is not None and item.spec.rule_id not in scoped_rules:
                # The scope answer explicitly mapped no section for this rule. That is
                # a recorded document-level decision, but an append has no old-text
                # absence proof: an empty mapping cannot close it.
                if item.spec.op == "append":
                    item.completion = "UNRESOLVED"
                    item.completion_evidence = "SCOPE_EMPTY_APPEND_UNPROVEN"
                else:
                    item.completion = "NOT_APPLICABLE"
                    item.completion_evidence = "scope_explicitly_empty"
            else:
                # Plan §10.2: applicable but no target is an OPEN obligation.
                item.completion = "UNRESOLVED"
                item.completion_evidence = "OPEN_OBLIGATION:applicable_without_target"
            item.statuses["validation"] = ("PASS" if item.completion == "NOT_APPLICABLE"
                                           else "FAIL")
            continue

        states = {str(target.get("state") or "") for target in relevant}
        replay_item = replay_obligations.get(item.obligation_id)
        if isinstance(replay_item, Mapping) and replay_item.get("state") == "PASS" \
                and states <= {"satisfied", "absent", "out_of_scope"}:
            item.completion = ("ARTIFACT_VERIFIED"
                               if replay_item.get("artifact_status") ==
                               "EXPECTED_EFFECT_PRESENT" else "ALREADY_SATISFIED")
            item.completion_evidence = "claim_replay:" + str(
                replay_item.get("artifact_status"))
            item.statuses.update(target="SATISFIED", generation="NOT_REQUIRED",
                                 validation="PASS", artifact="VERIFIED")
            item.edit_ids = tuple(str(value) for value in
                                  (replay_item.get("edit_ids") or []) if value)
            item.artifact_evidence = [dict(value) for value in
                                      (replay_item.get("evidence") or [])
                                      if isinstance(value, Mapping)]
            continue
        if states and states <= {"absent", "out_of_scope"}:
            item.completion = "NOT_APPLICABLE"
            item.completion_evidence = "target_absent_or_out_of_scope"
            item.statuses.update(target="ABSENT", generation="NOT_REQUIRED",
                                 validation="PASS", audit="NOT_REQUIRED")
            continue
        if states and states <= {"satisfied"}:
            if item.spec.op == "delete" and artifact_text is not None:
                import re as _re
                compact_artifact = _re.sub(r"\s+", "", artifact_text)
                probes = [_re.sub(r"\s+", "", _re.sub(
                              r"^[A-ZＡ-Ｚ]\s*类(?:基金份额)?的?", "", sentence).strip())
                          for sentence in _re.split(r"(?<=[。；;])", item.spec.old_text)]
                if any(probe and probe in compact_artifact for probe in probes):
                    item.completion = "UNRESOLVED"
                    item.completion_evidence = "SATISFIED_TARGET_RESIDUAL_DELETE"
                    item.statuses.update(target="SATISFIED", generation="FAIL",
                                         validation="FAIL")
                    continue
            item.completion = "ALREADY_SATISFIED"
            item.completion_evidence = "target_satisfied"
            item.statuses.update(target="SATISFIED", generation="NOT_REQUIRED",
                                 validation="PASS", audit="NOT_REQUIRED")
            continue

        planned = [plan_by_target.get(target_id) for target_id in relevant_ids
                   if plan_by_target.get(target_id)]
        plan_statuses = {str(entry.get("status") or "") for entry in planned}
        if "unresolved" in plan_statuses:
            entry = next(entry for entry in planned if entry.get("status") == "unresolved")
            item.completion = "UNRESOLVED"
            item.completion_evidence = "plan:" + str(entry.get("reason") or "unresolved")
            item.statuses.update(generation="FAIL", validation="FAIL")
            continue
        if "planned" not in plan_statuses:
            if plan_statuses and plan_statuses <= {"satisfied", "not_applicable"}:
                if "not_applicable" in plan_statuses and item.applicability.status != "FALSE":
                    # A plan-level not-applicable cannot override an obligation whose
                    # applicability is TRUE/UNKNOWN; that contradiction is unresolved.
                    item.completion = "UNRESOLVED"
                    item.completion_evidence = "plan_not_applicable_but_applicability_" + \
                        item.applicability.status.lower()
                    item.statuses.update(generation="FAIL", validation="FAIL")
                    continue
                item.completion = "ALREADY_SATISFIED" \
                    if "satisfied" in plan_statuses else "NOT_APPLICABLE"
                item.completion_evidence = "plan:" + ",".join(sorted(plan_statuses))
                item.statuses.update(generation="NOT_REQUIRED", validation="PASS")
                continue
            item.completion = "UNRESOLVED"
            item.completion_evidence = "no_plan_record"
            item.statuses.update(generation="FAIL", validation="FAIL")
            continue

        item.statuses["generation"] = "PLANNED"
        audit_verdicts = {verdicts.get(target_id, "") for target_id in relevant_ids}
        planned_ids = {target_id for target_id in relevant_ids
                       if str((plan_by_target.get(target_id) or {}).get("status") or "")
                       == "planned"}
        all_planned_completed = bool(planned_ids) and all(
            verdicts.get(target_id) == "completed" for target_id in planned_ids)
        if all_planned_completed and not (audit_verdicts & {"wrong", "incomplete"}):
            item.statuses["audit"] = "COMPLETED"
            item.statuses["validation"] = "PASS"
            item.completion = "SATISFIED"
            item.completion_evidence = "audit_completed"
            replay_item = replay_obligations.get(item.obligation_id)
            if isinstance(replay_item, Mapping) and replay_item.get("state") == "PASS":
                item.statuses["artifact"] = "VERIFIED"
                item.completion = "ARTIFACT_VERIFIED"
                item.completion_evidence = (
                    "claim_replay:" + str(replay_item.get("artifact_status")
                                          or "EXPECTED_EFFECT_PRESENT"))
                item.edit_ids = tuple(str(value) for value in
                                      (replay_item.get("edit_ids") or []) if value)
                item.artifact_evidence = [dict(value) for value in
                                          (replay_item.get("evidence") or [])
                                          if isinstance(value, Mapping)]
            else:
                # A whole-document replay PASS is not proof for this obligation.  It
                # must carry its own operation/obligation artifact record (plan §29).
                item.statuses["artifact"] = "UNVERIFIED"
                item.completion = "UNRESOLVED"
                item.completion_evidence = (
                    "CLAIM_REPLAY_OBLIGATION_MISSING"
                    if not isinstance(replay_item, Mapping)
                    else "CLAIM_REPLAY_" + str(replay_item.get("state") or "FAIL"))
            failure = any(str(target.get("location") or "") in
                          {location for _rule, location in replay_failures}
                          for target in relevant)
            if failure:
                item.completion = "UNRESOLVED"
                item.completion_evidence = "CLAIM_REPLAY_FAILED"
                item.statuses["artifact"] = "FAIL"
            continue
        if audit_verdicts & {"wrong", "incomplete"}:
            item.statuses["audit"] = "FAILED"
            item.completion = "UNRESOLVED"
            item.completion_evidence = "audit_" + sorted(audit_verdicts & {"wrong", "incomplete"})[0]
            continue
        item.completion = "UNRESOLVED"
        item.completion_evidence = "audit_pending"
        item.statuses["audit"] = "PENDING"

    # ONE_OF alternatives: if any alternative actually present in the contract was
    # carried out (or the rule resolves as not applicable), its siblings are closed by
    # that evidence. They are not independent obligations (plan §6.3).
    groups: dict[str, list[ObligationRecord]] = {}
    for record in ledger.records:
        if record.spec.one_of_group:
            groups.setdefault(record.spec.one_of_group, []).append(record)
    priority = {"ARTIFACT_VERIFIED": 4, "SATISFIED": 3, "ALREADY_SATISFIED": 2,
                "NOT_APPLICABLE": 1}
    for group in groups.values():
        closed = [record for record in group if record.completion in priority]
        if not closed:
            continue
        best = max(closed, key=lambda record: priority[record.completion])
        for record in group:
            if record.completion != "UNRESOLVED":
                continue
            old_text = ""
            # A variant may still exist in another copy of the clause. Only a sibling
            # whose own old wording is gone (or was itself handled) may inherit closure.
            if artifact_text is not None:
                import re as _re
                probe = _re.sub(r"\s+", "", record.spec.old_text)
                if probe and probe not in authorized_new and \
                        probe in _re.sub(r"\s+", "", artifact_text):
                    record.completion_evidence = "ONE_OF_VARIANT_RESIDUAL"
                    continue
            record.completion = best.completion
            record.completion_evidence = (f"ONE_OF_ALTERNATIVE:{best.obligation_id}:"
                                          f"{best.completion_evidence}")

    # Final artifact-proof gate (plan §25–§29): a TRUE obligation may only remain
    # closed when Claim Replay produced its OWN PASS record.  A closed state derived
    # from audit/survey/target heuristics is downgraded here if the artifact proof is
    # missing, so "all actual edits passed" can never stand in for "every required
    # obligation is proven".
    for record in ledger.records:
        if record.applicability.status != "TRUE":
            continue
        if record.completion not in {"SATISFIED", "ARTIFACT_VERIFIED",
                                     "ALREADY_SATISFIED"}:
            continue
        replay_item = replay_obligations.get(record.obligation_id)
        if isinstance(replay_item, Mapping) and replay_item.get("state") == "PASS":
            record.statuses["artifact"] = "VERIFIED"
            record.edit_ids = tuple(str(value) for value in
                                    (replay_item.get("edit_ids") or []) if value)
            record.artifact_evidence = [dict(value) for value in
                                        (replay_item.get("evidence") or [])
                                        if isinstance(value, Mapping)]
            continue
        record.completion = "UNRESOLVED"
        record.statuses["artifact"] = "UNVERIFIED"
        record.completion_evidence = (
            "CLAIM_REPLAY_OBLIGATION_MISSING"
            if not isinstance(replay_item, Mapping)
            else "CLAIM_REPLAY_" + str(replay_item.get("state") or "FAIL"))


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
