"""Route one operation to a generation tier (plan v4 §6, §18).

Two hard rules from the plan:

1. **Fact preconditions are a gate, never a fall-through** — an UNKNOWN or
   CONFLICT fact blocks the operation (``unresolved``); it must not be pushed
   down to Tier3 to let the model guess (plan §3.3);
2. Only *text-structure* reasons may degrade a tier:
   ``clean`` may upgrade to Tier1, ``mixed`` degrades Tier1→Tier2,
   ``unsafe`` degrades to Tier3 when allowed.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .registry import operation_for
from .types import GenerationTier as T, RouteDecision, StrategySpec


class FailureTaxonomy(str, Enum):
    """Stable root-cause names for generation failures.

    The planner and artifact layers use many concrete error codes.  This small
    vocabulary lets recovery choose a *different* method based on what failed,
    rather than retrying the same model prompt.  Keep these values independent
    of user-facing report wording; they are an internal routing contract.
    """

    SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
    RANGE_INVALID = "RANGE_INVALID"
    PROTECTED_TEXT_CHANGED = "PROTECTED_TEXT_CHANGED"
    REQUIREMENT_MISSING = "REQUIREMENT_MISSING"
    DUPLICATE_CONTENT = "DUPLICATE_CONTENT"
    TEMPLATE_NOT_APPLICABLE = "TEMPLATE_NOT_APPLICABLE"
    SPLICE_FAILED = "SPLICE_FAILED"
    COMPOSE_VALIDATION_FAILED = "COMPOSE_VALIDATION_FAILED"
    WRITEBACK_FAILED = "WRITEBACK_FAILED"
    ARTIFACT_MISMATCH = "ARTIFACT_MISMATCH"
    UNKNOWN = "UNKNOWN"


class RecoveryStrategy(str, Enum):
    """Concrete generation/rebind methods used by escalation.

    ``NORMALIZED`` and ``FUZZY`` are source rebind methods, not text generators.
    Keeping them separate from :class:`GenerationTier` makes it impossible for a
    caller to mistake a failed rebind for a successful edit tier.
    """

    DELETE = "delete"
    EXACT = "exact_replace"
    NORMALIZED = "normalized_rebind"
    FUZZY = "fuzzy_span_rebind"
    TEMPLATE = "template"
    SPLICE = "splice"
    COMPOSE = "compose"
    REPAIR_COMPOSE = "compose_repair"
    ARTIFACT_REBIND = "artifact_rebind"


@dataclass(frozen=True)
class EscalationDecision:
    """One reasoned next step after a generation or artifact failure."""

    taxonomy: FailureTaxonomy
    strategy: RecoveryStrategy | None
    reason: str
    attempt: int = 0

    @property
    def terminal(self) -> bool:
        return self.strategy is None

    def as_dict(self) -> dict[str, object]:
        return {
            "taxonomy": self.taxonomy.value,
            "strategy": self.strategy.value if self.strategy else None,
            "reason": self.reason,
            "attempt": self.attempt,
            "terminal": self.terminal,
        }


# Concrete planner and validator codes grouped by the failure they describe.
# Prefix matching below handles newly introduced variants while this table keeps
# the common codes explicit and reviewable.
_FAILURE_TAXONOMY: dict[str, FailureTaxonomy] = {
    # Accept taxonomy names as input as well as concrete engine codes.  This is
    # useful when a recovery event has already been normalized by another stage.
    **{item.value: item for item in FailureTaxonomy},
    "RECALL_TARGET_UNRESOLVED": FailureTaxonomy.SOURCE_NOT_FOUND,
    "RECALL_TARGET_REBIND_FAILED": FailureTaxonomy.SOURCE_NOT_FOUND,
    "CLAIM_LOCATION_MISSING": FailureTaxonomy.SOURCE_NOT_FOUND,
    "RECALL_TARGET_VARIANT_UNMATCHED": FailureTaxonomy.SPLICE_FAILED,
    "RECALL_TARGET_STRUCTURE": FailureTaxonomy.RANGE_INVALID,
    "RECALL_VARIANT_CLAUSE_INCOMPLETE": FailureTaxonomy.RANGE_INVALID,
    "RECALL_EDIT_OVERLAP": FailureTaxonomy.DUPLICATE_CONTENT,
    "DUPLICATE_SITE_UNEDITED": FailureTaxonomy.DUPLICATE_CONTENT,
    "RECALL_PLAN_COMPONENT_DROPPED": FailureTaxonomy.DUPLICATE_CONTENT,
    "MISSING_REQUIRED_TERM": FailureTaxonomy.REQUIREMENT_MISSING,
    "COMPONENT_MISSING": FailureTaxonomy.REQUIREMENT_MISSING,
    "COMPONENT_OUTSIDE_SITE": FailureTaxonomy.REQUIREMENT_MISSING,
    "TOPIC_LOST": FailureTaxonomy.REQUIREMENT_MISSING,
    "RECALL_APPEND_CLAUSE_INCOMPLETE": FailureTaxonomy.TEMPLATE_NOT_APPLICABLE,
    "RECALL_SLOT_UNRESOLVED": FailureTaxonomy.TEMPLATE_NOT_APPLICABLE,
    "RECALL_COMPOSE_FIXED_TEXT_MISSING": FailureTaxonomy.TEMPLATE_NOT_APPLICABLE,
    "RECALL_COMPOSE_UNVERIFIED": FailureTaxonomy.COMPOSE_VALIDATION_FAILED,
    "RECALL_COMPOSE_NEW_NUMBERS": FailureTaxonomy.COMPOSE_VALIDATION_FAILED,
    "RECALL_COMPOSE_DELETE_ADDED_TEXT": FailureTaxonomy.COMPOSE_VALIDATION_FAILED,
    "RECALL_COMPOSE_DELETE_NOT_SHRINKING": FailureTaxonomy.COMPOSE_VALIDATION_FAILED,
    "RECALL_EDIT_CONTENT_UNVERIFIED": FailureTaxonomy.COMPOSE_VALIDATION_FAILED,
    "UNAUTHORIZED_NUMBER": FailureTaxonomy.PROTECTED_TEXT_CHANGED,
    "LOST_PROTECTED_LITERAL": FailureTaxonomy.PROTECTED_TEXT_CHANGED,
    "OUTSIDE_SPAN_CHANGED": FailureTaxonomy.PROTECTED_TEXT_CHANGED,
    "UNEXPLAINED_HARD": FailureTaxonomy.PROTECTED_TEXT_CHANGED,
    "WRITEBACK_FAILED": FailureTaxonomy.WRITEBACK_FAILED,
    "OUTPUT_IO_ERROR": FailureTaxonomy.WRITEBACK_FAILED,
    "RECALL_EDIT_NOT_EXECUTABLE": FailureTaxonomy.WRITEBACK_FAILED,
    "CLAIM_NO_CHANGE_APPLIED": FailureTaxonomy.ARTIFACT_MISMATCH,
    "CLAIM_REPLACEMENT_MISSING": FailureTaxonomy.ARTIFACT_MISMATCH,
    "CLAIM_EXECUTION_EFFECT_MISSING": FailureTaxonomy.ARTIFACT_MISMATCH,
    "CLAIM_PLANNED_EFFECT_MISSING": FailureTaxonomy.ARTIFACT_MISMATCH,
    "CLAIM_VALIDATION_FAILED": FailureTaxonomy.ARTIFACT_MISMATCH,
    "CLAIM_REPLAY_FAILED": FailureTaxonomy.ARTIFACT_MISMATCH,
}

_FAILURE_PREFIXES: tuple[tuple[str, FailureTaxonomy], ...] = (
    ("RECALL_TARGET_", FailureTaxonomy.SOURCE_NOT_FOUND),
    ("RECALL_VARIANT_", FailureTaxonomy.RANGE_INVALID),
    ("RECALL_COMPOSE_", FailureTaxonomy.COMPOSE_VALIDATION_FAILED),
    ("CLAIM_", FailureTaxonomy.ARTIFACT_MISMATCH),
    ("OUTPUT_", FailureTaxonomy.WRITEBACK_FAILED),
)


def classify_failure(code: str | FailureTaxonomy) -> FailureTaxonomy:
    """Map a concrete failure code to a stable generation taxonomy."""
    if isinstance(code, FailureTaxonomy):
        return code
    normalized = str(code or "").strip().upper()
    if normalized in _FAILURE_TAXONOMY:
        return _FAILURE_TAXONOMY[normalized]
    for prefix, taxonomy in _FAILURE_PREFIXES:
        if normalized.startswith(prefix):
            return taxonomy
    return FailureTaxonomy.UNKNOWN


def _coerce_strategy(value: object) -> RecoveryStrategy | None:
    if value is None:
        return None
    if isinstance(value, RecoveryStrategy):
        return value
    if isinstance(value, T):
        return {
            T.DELETE: RecoveryStrategy.DELETE,
            T.TEMPLATE: RecoveryStrategy.TEMPLATE,
            T.SPLICE: RecoveryStrategy.SPLICE,
            T.COMPOSE: RecoveryStrategy.COMPOSE,
        }[value]
    text = str(value).strip().lower()
    aliases = {
        "delete": RecoveryStrategy.DELETE,
        "deterministic_delete": RecoveryStrategy.DELETE,
        "exact": RecoveryStrategy.EXACT,
        "exact_replace": RecoveryStrategy.EXACT,
        "normalized": RecoveryStrategy.NORMALIZED,
        "normalized_rebind": RecoveryStrategy.NORMALIZED,
        "fuzzy": RecoveryStrategy.FUZZY,
        "fuzzy_span": RecoveryStrategy.FUZZY,
        "fuzzy_span_rebind": RecoveryStrategy.FUZZY,
        "template": RecoveryStrategy.TEMPLATE,
        "tier1_template": RecoveryStrategy.TEMPLATE,
        "tier1": RecoveryStrategy.TEMPLATE,
        "splice": RecoveryStrategy.SPLICE,
        "tier1_splice": RecoveryStrategy.SPLICE,
        "tier2_minimal_splice": RecoveryStrategy.SPLICE,
        "fragment_replace": RecoveryStrategy.SPLICE,
        "fragment_delete": RecoveryStrategy.SPLICE,
        "variant_replace": RecoveryStrategy.SPLICE,
        "variant_delete": RecoveryStrategy.SPLICE,
        "compose": RecoveryStrategy.COMPOSE,
        "composed": RecoveryStrategy.COMPOSE,
        "composed_delete": RecoveryStrategy.COMPOSE,
        "joint_compose": RecoveryStrategy.COMPOSE,
        "compose_repair": RecoveryStrategy.REPAIR_COMPOSE,
        "artifact_rebind": RecoveryStrategy.ARTIFACT_REBIND,
    }
    return aliases.get(text)


def _strategy_sequence(taxonomy: FailureTaxonomy, *, mode: str = "replace") -> tuple[RecoveryStrategy, ...]:
    """Return an ordered, finite escalation path for one root cause."""
    is_delete = str(mode or "").strip().lower() in {"delete", "remove"}
    if taxonomy is FailureTaxonomy.SOURCE_NOT_FOUND:
        return ((RecoveryStrategy.DELETE,) if is_delete else ()) + (
            RecoveryStrategy.EXACT, RecoveryStrategy.NORMALIZED,
            RecoveryStrategy.FUZZY, RecoveryStrategy.TEMPLATE,
            RecoveryStrategy.SPLICE, RecoveryStrategy.COMPOSE)
    if taxonomy is FailureTaxonomy.RANGE_INVALID:
        return (RecoveryStrategy.NORMALIZED, RecoveryStrategy.FUZZY,
                RecoveryStrategy.SPLICE)
    if taxonomy is FailureTaxonomy.TEMPLATE_NOT_APPLICABLE:
        return (RecoveryStrategy.SPLICE, RecoveryStrategy.COMPOSE)
    if taxonomy is FailureTaxonomy.SPLICE_FAILED:
        return (RecoveryStrategy.COMPOSE,)
    if taxonomy is FailureTaxonomy.COMPOSE_VALIDATION_FAILED:
        # Retry compose only through a distinct repair prompt carrying the
        # concrete validator/reviewer finding. Reusing the original compose
        # prompt would reproduce the same candidate and failure.
        return (RecoveryStrategy.REPAIR_COMPOSE,)
    if taxonomy is FailureTaxonomy.PROTECTED_TEXT_CHANGED:
        return (RecoveryStrategy.SPLICE, RecoveryStrategy.COMPOSE)
    if taxonomy is FailureTaxonomy.REQUIREMENT_MISSING:
        return (RecoveryStrategy.TEMPLATE, RecoveryStrategy.SPLICE,
                RecoveryStrategy.COMPOSE)
    if taxonomy is FailureTaxonomy.DUPLICATE_CONTENT:
        return (RecoveryStrategy.EXACT, RecoveryStrategy.NORMALIZED,
                RecoveryStrategy.SPLICE, RecoveryStrategy.COMPOSE)
    if taxonomy in {FailureTaxonomy.WRITEBACK_FAILED,
                    FailureTaxonomy.ARTIFACT_MISMATCH}:
        return (RecoveryStrategy.ARTIFACT_REBIND,)
    return (RecoveryStrategy.EXACT, RecoveryStrategy.NORMALIZED,
            RecoveryStrategy.TEMPLATE, RecoveryStrategy.SPLICE,
            RecoveryStrategy.COMPOSE)


def strategy_for_failure(code: str | FailureTaxonomy, current_tier: object = None,
                         content_source: object = None, attempt: int = 0,
                         mode: str = "replace") -> EscalationDecision:
    """Choose the next *different* strategy after a concrete failure.

    ``current_tier`` and ``content_source`` are aliases accepted from the two
    planner layers.  If either identifies a strategy, escalation starts after
    that strategy.  Otherwise ``attempt`` indexes the ordered path.  Thus a
    caller can record each decision and cannot accidentally issue the same
    failed retry unchanged.
    """
    taxonomy = classify_failure(code)
    try:
        attempt_number = max(0, int(attempt or 0))
    except (TypeError, ValueError):
        attempt_number = 0
    sequence = _strategy_sequence(taxonomy, mode=mode)
    current = _coerce_strategy(current_tier) or _coerce_strategy(content_source)
    if current is not None and current in sequence:
        start = sequence.index(current) + 1
    else:
        start = attempt_number
    if start < len(sequence):
        strategy = sequence[start]
        return EscalationDecision(taxonomy, strategy,
                                  f"{taxonomy.value.lower()}->{strategy.value}",
                                  attempt=attempt_number)
    return EscalationDecision(taxonomy, None,
                              f"{taxonomy.value.lower()}_recovery_exhausted",
                              attempt=attempt_number)


def route_operation(operation_key: str, *,
                    fact_status: Mapping[str, str] | None = None,
                    structure: str | None = None,
                    spec: StrategySpec | None = None) -> RouteDecision:
    """Decide the tier for ``operation_key``.

    ``fact_status`` maps fact field names to ``VERIFIED | UNKNOWN | CONFLICT``;
    ``structure`` is ``"clean" | "mixed" | "unsafe" | None`` (text-structure
    analysis, performed by later phases).
    """
    # An explicitly supplied spec is supported for old callers and custom
    # adapters.  Otherwise resolve the operation entry, never just its rule.
    spec = spec or operation_for(operation_key)
    raw_fact_status = fact_status or {}
    normalized_facts = {
        str(name): str(status).strip().upper()
        for name, status in raw_fact_status.items()
    }

    dependencies = tuple(dict.fromkeys(
        (*spec.required_fact_status,
         *(spec.policy_components.fact_dependencies
           if spec.policy_components is not None else ()))
    ))
    missing = [name for name in dependencies
               if normalized_facts.get(name) != "VERIFIED"]
    if missing:
        statuses = tuple(sorted((name, normalized_facts.get(name, "UNKNOWN"))
                                for name in missing))
        reason = "FACT_NOT_VERIFIED:" + ",".join(
            f"{name}={status}" for name, status in statuses)
        return RouteDecision(
            operation_key, spec.default_tier, None, fallback_reason=reason,
            blocked=True, selected_executor=None,
            fact_blocking=tuple(name for name, _ in statuses),
            fact_status=statuses,
        )

    tier = spec.default_tier
    reason: str | None = None
    allowed = tuple(spec.allowed_tiers)
    if structure == "clean" and T.TEMPLATE in allowed:
        if tier is not T.TEMPLATE:
            tier, reason = T.TEMPLATE, "clean_single_sentence"
    elif structure == "mixed":
        if tier is T.TEMPLATE and T.SPLICE in allowed:
            tier, reason = T.SPLICE, "complex_mixed_clause"
        elif tier is T.TEMPLATE and T.COMPOSE in allowed:
            tier, reason = T.COMPOSE, "mixed_clause_requires_compose"
    elif structure == "unsafe":
        # Unsafe structure means that a safe splice boundary is unavailable;
        # when compose is authorized it is the only valid fallback.  Do not
        # route through Tier2 merely because it appears earlier in the list.
        if tier in {T.DELETE, T.COMPOSE}:
            candidate = tier
        elif T.COMPOSE in allowed:
            candidate = T.COMPOSE
        elif T.SPLICE in allowed and tier is T.TEMPLATE:
            candidate = T.SPLICE
        else:
            candidate = None
        if candidate is None:
            return RouteDecision(
                operation_key, spec.default_tier, None,
                fallback_reason="STRUCTURE_UNSUPPORTED:" + str(structure),
                blocked=True, selected_executor=None,
                fact_status=tuple(sorted(normalized_facts.items())),
            )
        if candidate is not tier:
            tier, reason = candidate, "structure_unsafe_for_splice"

    executor = {
        T.DELETE: "delete",
        T.TEMPLATE: "template",
        T.SPLICE: "splice",
        T.COMPOSE: "compose",
    }[tier]
    return RouteDecision(
        operation_key, spec.default_tier, tier, fallback_reason=reason,
        blocked=False, selected_executor=executor,
        fact_status=tuple(sorted(normalized_facts.items())),
    )
