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
from .components import (
    COMPONENT_KINDS,
    COMPONENT_TERMS,
    component_requirements,
    policy_components_for_operation,
)
from .registry import (
    OPERATION_REGISTRY,
    STRATEGY_REGISTRY,
    operation_for,
    operation_registry_coverage_gaps,
    register_operation,
    registry_coverage_gaps,
    strategy_for,
)
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
    ComponentRequirement,
    GenerationTier,
    OperationSpec,
    PolicyComponents,
    PreserveRequirement,
    RouteDecision,
    StrategySpec,
)
from .validators import fact_blocking, validate_policy_components

__all__ = [
    "CoverageEntry",
    "CoverageLedgerView",
    "FACT_STATUSES",
    "COMPONENT_KINDS",
    "COMPONENT_TERMS",
    "ComponentRequirement",
    "GenerationTier",
    "OperationSpec",
    "PolicyComponents",
    "PreserveRequirement",
    "RouteDecision",
    "STRATEGY_MODES",
    "STRATEGY_REGISTRY",
    "OPERATION_REGISTRY",
    "StrategySpec",
    "build_coverage_view",
    "registry_coverage_gaps",
    "operation_registry_coverage_gaps",
    "operation_for",
    "register_operation",
    "component_requirements",
    "policy_components_for_operation",
    "fact_blocking",
    "validate_policy_components",
    "route_operation",
    "EscalationDecision",
    "FailureTaxonomy",
    "RecoveryStrategy",
    "classify_failure",
    "strategy_for_failure",
    "strategy_for",
    "strategy_mode",
]
