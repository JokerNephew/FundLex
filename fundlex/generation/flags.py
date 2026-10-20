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
