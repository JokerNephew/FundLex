"""Recovery budget (plan §20).  One configuration, not per-function constants."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping

DEFAULT_RECOVERY_POLICY: dict[str, int] = {
    "fact_primary_retry": 1,
    "fact_review_arbitration": 1,
    "applicability_primary_retry": 1,
    "applicability_review_arbitration": 1,
    "target_deterministic_retry": 1,
    "target_primary_locator": 1,
    "generation_deterministic_retry": 1,
    "generation_primary_compose": 2,
    "generation_review_rounds": 2,
    "joint_compose": 1,
    "execution_rebuild": 1,
    "artifact_recovery": 2,
    "audit_reaudit": 2,
    "global_business_rounds": 3,
    "context_split": 2,
    "infrastructure_pause_resume": 1,
}


class RecoveryPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class RecoveryPolicy:
    values: Mapping[str, int] = field(default_factory=lambda: dict(DEFAULT_RECOVERY_POLICY))

    def limit(self, key: str) -> int:
        if key not in self.values:
            raise RecoveryPolicyError(f"unknown recovery budget key: {key!r}")
        return max(0, int(self.values[key]))

    def with_overrides(self, overrides: Mapping[str, Any]) -> "RecoveryPolicy":
        values = dict(self.values)
        for key, value in overrides.items():
            if key not in values:
                raise RecoveryPolicyError(f"unknown recovery budget key: {key!r}")
            try:
                values[key] = max(0, int(value))
            except (TypeError, ValueError) as exc:
                raise RecoveryPolicyError(f"{key} must be an integer") from exc
        return RecoveryPolicy(values)

    def as_dict(self) -> dict[str, int]:
        return {key: int(value) for key, value in self.values.items()}


def load_policy() -> RecoveryPolicy:
    """Defaults plus ``FUNDLEX_RECOVERY_JSON`` / ``FUNDLEX_RECOVERY_<KEY>`` overrides."""
    policy = RecoveryPolicy()
    raw = os.environ.get("FUNDLEX_RECOVERY_JSON", "").strip()
    if raw:
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise RecoveryPolicyError("FUNDLEX_RECOVERY_JSON must be valid JSON") from exc
        if not isinstance(value, dict):
            raise RecoveryPolicyError("FUNDLEX_RECOVERY_JSON must be an object")
        policy = policy.with_overrides(value)
    overrides: dict[str, int] = {}
    for key in DEFAULT_RECOVERY_POLICY:
        env_name = "FUNDLEX_RECOVERY_" + key.upper()
        raw_value = os.environ.get(env_name, "").strip()
        if raw_value:
            overrides[key] = int(raw_value)
    return policy.with_overrides(overrides) if overrides else policy
