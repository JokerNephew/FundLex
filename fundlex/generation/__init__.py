"""Generation strategy layer (FL-D120 plan v4: deterministic-first, model-fallback).

Phase 1 delivers the code-side Strategy Registry, routing decisions and the
read-only Coverage Ledger view. Nothing in this package changes generation
behavior unless the feature flag is enabled:

    FUNDLEX_GENERATION_STRATEGY = legacy | registry_shadow | registry

The default is ``legacy`` — with the flag off, none of this code is consulted
by the pipeline, so behavior (and evaluation output) is unchanged (plan §22).
"""
from .coverage import CoverageEntry, CoverageLedgerView, build_coverage_view
from .flags import STRATEGY_MODES, strategy_mode
from .registry import STRATEGY_REGISTRY, registry_coverage_gaps, strategy_for
from .router import (
    EscalationDecision,
    FailureTaxonomy,
    RecoveryStrategy,
    classify_failure,
    route_operation,
    strategy_for_failure,
)
from .types import (
    FACT_STATUSES,
    GenerationTier,
    RouteDecision,
    StrategySpec,
)

__all__ = [
    "CoverageEntry",
    "CoverageLedgerView",
    "FACT_STATUSES",
    "GenerationTier",
    "RouteDecision",
    "STRATEGY_MODES",
    "STRATEGY_REGISTRY",
    "StrategySpec",
    "build_coverage_view",
    "registry_coverage_gaps",
    "route_operation",
    "EscalationDecision",
    "FailureTaxonomy",
    "RecoveryStrategy",
    "classify_failure",
    "strategy_for_failure",
    "strategy_for",
    "strategy_mode",
]
