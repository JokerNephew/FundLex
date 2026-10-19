"""Route one operation to a generation tier (plan v4 §6, §18).

Two hard rules from the plan:

1. **Fact preconditions are a gate, never a fall-through** — an UNKNOWN or
   CONFLICT fact blocks the operation (``unresolved``); it must not be pushed
   down to Tier3 to let the model guess (plan §3.3);
2. Only *text-structure* reasons may degrade a tier:
   ``clean`` may upgrade to Tier1, ``mixed`` degrades Tier1→Tier2,
   ``unsafe`` degrades to Tier3 when allowed.
"""
from typing import Mapping

from .registry import strategy_for
from .types import GenerationTier as T, RouteDecision, StrategySpec


def route_operation(operation_key: str, *,
                    fact_status: Mapping[str, str] | None = None,
                    structure: str | None = None,
                    spec: StrategySpec | None = None) -> RouteDecision:
    """Decide the tier for ``operation_key``.

    ``fact_status`` maps fact field names to ``VERIFIED | UNKNOWN | CONFLICT``;
    ``structure`` is ``"clean" | "mixed" | "unsafe" | None`` (text-structure
    analysis, performed by later phases).
    """
    spec = spec or strategy_for(operation_key)
    fact_status = fact_status or {}

    missing = [name for name in spec.required_fact_status
               if fact_status.get(name) != "VERIFIED"]
    if missing:
        return RouteDecision(operation_key, spec.default_tier, None,
                             fallback_reason="FACT_NOT_VERIFIED:" + ",".join(sorted(missing)),
                             blocked=True)

    tier = spec.default_tier
    reason: str | None = None
    if structure == "clean" and T.TEMPLATE in spec.allowed_tiers:
        if tier is not T.TEMPLATE:
            tier, reason = T.TEMPLATE, "clean_single_sentence"
    elif structure == "mixed" and tier is T.TEMPLATE and T.SPLICE in spec.allowed_tiers:
        tier, reason = T.SPLICE, "complex_mixed_clause"
    elif structure == "unsafe" and T.COMPOSE in spec.allowed_tiers:
        if tier is not T.COMPOSE:
            tier, reason = T.COMPOSE, "structure_unsafe_for_splice"

    return RouteDecision(operation_key, spec.default_tier, tier, fallback_reason=reason)
