"""Shared types for the generation strategy layer (plan v4 §5–§6, §17–§18)."""
from dataclasses import dataclass
from enum import Enum

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
    """Code-side registry entry: one rule id, shared by all its operations.

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


@dataclass(frozen=True)
class RouteDecision:
    operation_key: str
    requested_tier: GenerationTier
    actual_tier: GenerationTier | None
    fallback_reason: str | None = None
    blocked: bool = False

    @property
    def resolved(self) -> bool:
        return not self.blocked and self.actual_tier is not None
