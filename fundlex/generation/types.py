"""Shared types for the generation strategy layer.

The first version of this module exposed a rule-level ``StrategySpec``.  The
runtime, however, generates operations, and two operations in one rule can
have different preconditions and executors.  The newer types below add that
level without changing the original positional ``StrategySpec`` constructor.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

#: Fact tri-state (plan §20, §24): only VERIFIED facts may drive generation.
FACT_STATUSES = ("VERIFIED", "UNKNOWN", "CONFLICT")


class GenerationTier(str, Enum):
    """Generation tiers of the plan (plus the deterministic delete path)."""

    TEMPLATE = "tier1_template"
    SPLICE = "tier2_minimal_splice"
    COMPOSE = "tier3_model_compose"
    DELETE = "deterministic_delete"


@dataclass(frozen=True)
class StrategySpec:
    """Rule-level compatibility specification.

    The spec is *advisory documentation plus routing input* in Phase 1; later
    phases wire it into the planner. It must never invent policy — policy lives
    in the guide (``guides/builtin_guide_v1.json``).
    """

    rule_id: str
    default_tier: GenerationTier
    allowed_tiers: tuple[GenerationTier, ...]
    mode: str = "replace"  # replace | append | delete | class_substitution | noop
    #: Fact field names that must be VERIFIED before any generation happens
    #: (plan §3.3: an UNKNOWN fact may not fall through to Tier3).
    required_fact_status: tuple[str, ...] = ()
    #: Component ids the policy must add / preserve (filled in later phases).
    required_components: tuple[str, ...] = ()
    preserve_policy: tuple[str, ...] = ()
    note: str = ""
    #: Optional stable operation identity for adapters that construct a
    #: StrategySpec directly.  Concrete registry entries use OperationSpec.
    operation_key: str = ""
    #: Executor name is explicit in operation entries and optional on legacy
    #: rule entries.
    executor: str = ""
    #: The operation-level policy compiled for this rule, when available.
    #: It is metadata only; routing always uses ``OperationSpec``.
    policy_components: "PolicyComponents | None" = None


@dataclass(frozen=True)
class OperationSpec(StrategySpec):
    """Strategy for one concrete guide operation.

    ``operation_key`` is stable (for example ``G11:1``) and is deliberately
    separate from ``rule_id``.  This prevents a sibling operation with a
    different condition or executor from inheriting the first operation's
    strategy.
    """

    operation_index: int = 0
    condition_kind: str = ""
    condition_value: Any = None


@dataclass(frozen=True)
class ComponentRequirement:
    """A structured policy component required by one operation."""

    id: str
    kind: str = "policy"
    properties: Mapping[str, Any] = field(default_factory=dict)
    terms: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind,
                "properties": dict(self.properties), "terms": list(self.terms)}


@dataclass(frozen=True)
class PreserveRequirement:
    """A literal or semantic contract element that generation must preserve."""

    id: str
    kind: str = "semantic"
    properties: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "kind": self.kind,
                "properties": dict(self.properties)}


@dataclass(frozen=True)
class PolicyComponents:
    """Compiled policy boundary passed to template, splice and compose.

    This object contains policy structure, never a conclusion inferred from an
    unverified contract fact.  ``fact_dependencies`` is the explicit gate used
    by the router and validators before a compose request can be made.
    """

    operation_key: str
    must_add: tuple[ComponentRequirement, ...] = ()
    must_remove: tuple[ComponentRequirement, ...] = ()
    must_preserve: tuple[PreserveRequirement, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    authorized_spans: tuple[Any, ...] = ()
    protected_literals: tuple[Any, ...] = ()
    rewrite_scope: str = "minimal"
    preserve_original_qualifiers: bool = True
    fact_dependencies: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_key": self.operation_key,
            "must_add": [item.as_dict() for item in self.must_add],
            "must_remove": [item.as_dict() for item in self.must_remove],
            "must_preserve": [item.as_dict() for item in self.must_preserve],
            "parameters": dict(self.parameters),
            "authorized_spans": list(self.authorized_spans),
            "protected_literals": list(self.protected_literals),
            "rewrite_scope": self.rewrite_scope,
            "preserve_original_qualifiers": self.preserve_original_qualifiers,
            "fact_dependencies": list(self.fact_dependencies),
        }


@dataclass(frozen=True)
class RouteDecision:
    operation_key: str
    requested_tier: GenerationTier
    actual_tier: GenerationTier | None
    fallback_reason: str | None = None
    blocked: bool = False
    #: Concrete executor selected for this operation (template/splice/compose/delete).
    selected_executor: str | None = None
    #: Fact fields which prevented generation.  Empty means no fact block.
    fact_blocking: tuple[str, ...] = ()
    #: Statuses are retained for diagnostics and recovery evidence.
    fact_status: tuple[tuple[str, str], ...] = ()

    @property
    def executor(self) -> str | None:
        """Alias used by callers that call the selected executor simply ``executor``."""
        return self.selected_executor

    @property
    def blocked_facts(self) -> tuple[str, ...]:
        """Compatibility/readability alias for the fact gate evidence."""
        return self.fact_blocking

    @property
    def requested_executor(self) -> str | None:
        """Executor implied by the requested tier, before structural fallback."""
        return {
            GenerationTier.DELETE: "delete",
            GenerationTier.TEMPLATE: "template",
            GenerationTier.SPLICE: "splice",
            GenerationTier.COMPOSE: "compose",
        }.get(self.requested_tier)

    @property
    def resolved(self) -> bool:
        return not self.blocked and self.actual_tier is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation_key": self.operation_key,
            "requested_tier": self.requested_tier.value,
            "actual_tier": self.actual_tier.value if self.actual_tier else None,
            "selected_executor": self.selected_executor,
            "fallback_reason": self.fallback_reason,
            "blocked": self.blocked,
            "fact_blocking": list(self.fact_blocking),
            "fact_status": {name: status for name, status in self.fact_status},
        }
