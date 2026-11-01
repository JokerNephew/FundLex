"""Feature flag for the generation strategy layer.

The plan (v4 §22) requires that the new logic is unreachable unless the flag is
switched on, so that Phase 1 proves "behavior diff = 0" by construction:

* ``registry``         — default: deterministic-first routing and validation;
* ``registry_shadow``  — routing/telemetry computed for observation only;
* ``legacy``           — compatibility escape hatch; safety gates still run.
"""
import os

STRATEGY_MODES = ("legacy", "registry_shadow", "registry")

_ENV_VAR = "FUNDLEX_GENERATION_STRATEGY"


def strategy_mode() -> str:
    """Current strategy mode; unknown values fall back to the safe default."""
    value = os.environ.get(_ENV_VAR, "registry").strip().lower()
    return value if value in STRATEGY_MODES else "registry"


def observe_registry_shadow(facet: str, decision: str, *, operation_key: str = "") -> None:
    """Emit one registry-shadow observation through the local trace sink.

    ``registry_shadow`` keeps the legacy/production path but records what the
    registry-tier-1 decision *would have been* (FL-D934): the flag's docstring
    promised exactly this observation channel.  Failure of the observation must
    never change the shadow outcome, so every sink interaction is a no-op path
    when the sink is off.
    """
    try:
        from ..trace_sink import record_event
        record_event("registry_shadow", facet=facet, decision=decision,
                     operation_key=operation_key)
    except Exception:  # pragma: no cover - observation must never affect routing
        pass
