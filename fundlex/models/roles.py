"""Primary / review role gateway.

The pipeline talks to one gateway object. :class:`RoleGateway` routes every model
task to the configured role, keeps per-role call records, and shares a single budget
ledger.  A review call never receives the primary model's reasoning: it gets its own
task type, instruction and bounded context, exactly like the pipeline builds today.
"""
from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from typing import Any, Mapping

from ..model import ModelBudget, ModelGateway, ModelError
from .config import ModelRoleConfig, RoleConfigError, load_role_config

ROLES = ("primary", "review")

#: Business task → role.  Review owns every semantic check that must be independent
#: of the producing model (plan §4.4, §5).
DEFAULT_TASK_ROLES: dict[str, str] = {
    "recall_facts": "primary",
    "recall_fact_recover": "primary",
    "recall_scope": "primary",
    "recall_inventory": "primary",
    "recall_applicability": "primary",
    "recall_locate": "primary",
    "recall_compose": "primary",
    "recall_joint_compose": "primary",
    "recall_verify": "review",
    "recall_audit": "review",
    "recall_sweep": "review",
    "recall_arbitrate": "review",
    "recall_compose_review": "review",
}

#: Configuration aliases used by a role file / product terminology.
TASK_ALIASES: dict[str, tuple[str, ...]] = {
    "facts": ("recall_facts",),
    "fact_recovery": ("recall_fact_recover",),
    "facts_recovery": ("recall_fact_recover",),
    "applicability": ("recall_applicability",),
    "inventory": ("recall_inventory",),
    "target_locator": ("recall_locate",),
    "compose": ("recall_compose",),
    "joint_compose": ("recall_joint_compose",),
    "compose_review": ("recall_verify", "recall_compose_review"),
    "verify": ("recall_verify",),
    "audit": ("recall_audit",),
    "sweep": ("recall_sweep",),
    "fact_arbitration": ("recall_arbitrate",),
    "applicability_arbitration": ("recall_arbitrate",),
    "arbitration": ("recall_arbitrate",),
}


def _normalise_task_roles(overrides: Mapping[str, str] | None) -> dict[str, str]:
    mapping = dict(DEFAULT_TASK_ROLES)
    for key, value in (overrides or {}).items():
        role = str(value).strip().lower()
        if role not in ROLES:
            raise RoleConfigError(f"task role for {key!r} must be primary or review")
        targets = TASK_ALIASES.get(str(key))
        if targets:
            for task in targets:
                mapping[task] = role
        else:
            mapping[str(key)] = role
    return mapping


def role_for_task(task_type: str, task_roles: Mapping[str, str] | None = None) -> str:
    """Role for one gateway task type; unknown tasks stay on the primary role."""
    return (task_roles or DEFAULT_TASK_ROLES).get(task_type, "primary")


def _make_gateway(cfg: ModelRoleConfig, budget: ModelBudget | None) -> ModelGateway:
    return ModelGateway(
        base_url=cfg.base_url,
        model=cfg.model,
        api_key=cfg.api_key,
        max_context_chars=cfg.max_context_chars,
        max_calls=cfg.max_calls,
        max_completion_tokens=cfg.max_tokens,
        timeout_s=cfg.timeout_s,
        retries=cfg.retries,
        budget=budget,
        provider=cfg.provider,
        request_options=dict(cfg.request_options),
        extra_headers=dict(cfg.extra_headers),
        user_agent=cfg.user_agent,
    )


def _budget_from_env() -> ModelBudget:
    from ..config import local_data_dir
    return ModelBudget(
        os.environ.get("FUNDLEX_MODEL_LEDGER", str(local_data_dir() / "model_budget.sqlite")),
        max_requests=int(os.environ.get("FUNDLEX_MODEL_MAX_REQUESTS", "16")),
        max_cost_usd=float(os.environ.get("FUNDLEX_MODEL_MAX_COST_USD", "1")),
        concurrency=int(os.environ.get("FUNDLEX_MODEL_CONCURRENCY", "1")),
        input_usd_per_million=float(os.environ.get("FUNDLEX_MODEL_INPUT_USD_PER_M", "1")),
        output_usd_per_million=float(os.environ.get("FUNDLEX_MODEL_OUTPUT_USD_PER_M", "5")),
    )


@dataclass
class RoleCall:
    role: str
    task_type: str
    model: str
    reused_checkpoint: bool


class RoleGateway:
    """Dispatch model calls to the primary or the independent review endpoint."""

    def __init__(self, primary: ModelGateway, review: ModelGateway | None = None, *,
                 configs: Mapping[str, ModelRoleConfig] | None = None,
                 task_roles: Mapping[str, str] | None = None):
        self.primary = primary
        self.review = review or primary
        self.task_roles = _normalise_task_roles(task_roles)
        self.configs = dict(configs or {})
        self.calls: list[RoleCall] = []
        self._calls_lock = threading.Lock()

    # -- pipeline-facing surface ------------------------------------------------
    @property
    def max_context_chars(self) -> int:
        return min(self.primary.max_context_chars, self.review.max_context_chars)

    @property
    def max_calls(self) -> int:
        return self.primary.max_calls + (0 if self.review is self.primary else self.review.max_calls)

    @property
    def model(self) -> str:
        if self.review is self.primary or self.primary.model == self.review.model:
            return self.primary.model
        return f"{self.primary.model}+{self.review.model}"

    @property
    def budget(self) -> Any:
        return self.primary.budget

    @property
    def roles(self) -> dict[str, dict[str, Any]]:
        values: dict[str, dict[str, Any]] = {}
        for role, gateway in (("primary", self.primary), ("review", self.review)):
            cfg = self.configs.get(role)
            values[role] = {
                "model": gateway.model,
                "provider": getattr(gateway, "provider", ""),
                "configured": bool(cfg.configured) if cfg else True,
                "same_endpoint_as_primary": gateway is self.primary,
                "calls": sum(1 for item in self.calls if item.role == role),
            }
        return values

    def call(self, *, task_type: str, **kwargs: Any) -> Any:
        role = role_for_task(task_type, self.task_roles)
        gateway = self.primary if role == "primary" else self.review
        result = gateway.call(task_type=task_type, **kwargs)
        # ``ModelResult.attempts == 0`` is the checkpoint-reuse contract.  The old
        # ``events[before:]`` slice assumed one call at a time and would attribute a
        # concurrent thread's event to this call (plan §46).
        reused = int(getattr(result, "attempts", 1)) == 0
        with self._calls_lock:
            self.calls.append(RoleCall(role=role, task_type=task_type,
                                       model=getattr(result, "model", gateway.model),
                                       reused_checkpoint=reused))
        return result

    def bind_checkpoints(self, directory: Any, dependencies: dict) -> None:
        targets = [("primary", self.primary)]
        if self.review is not self.primary:
            targets.append(("review", self.review))
        for role, gateway in targets:
            if hasattr(gateway, "bind_checkpoints"):
                gateway.bind_checkpoints(directory, {
                    **dependencies,
                    "model_role": role,
                    "configured_model": gateway.model,
                    "task_roles_sha256": _task_roles_digest(self.task_roles),
                })

    def metrics(self) -> dict:
        base = dict(self.primary.metrics())
        if self.review is not self.primary:
            other = self.review.metrics()
            for key in ("logical_calls", "http_attempts", "checkpoint_reuses",
                        "checkpoint_invalidations", "prompt_tokens", "completion_tokens",
                        "total_tokens", "latency_ms", "rate_limit_count", "error_count",
                        "estimated_cost_usd"):
                base[key] = base.get(key, 0) + other.get(key, 0)
            base["events"] = list(self.primary.events) + list(self.review.events)
        for event in base.get("events") or []:
            task = event.get("task_type")
            if task:
                event["role"] = role_for_task(task, self.task_roles)
        base["roles"] = {
            role: {"model": gateway.model,
                   "calls": sum(1 for item in self.calls if item.role == role),
                   "task_types": sorted({item.task_type for item in self.calls
                                         if item.role == role})}
            for role, gateway in (("primary", self.primary), ("review", self.review))
        }
        base["role_calls"] = [item.__dict__ for item in self.calls]
        return base

    def close(self) -> None:
        self.primary.close()
        if self.review is not self.primary:
            self.review.close()

    def __enter__(self) -> "RoleGateway":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


def _task_roles_digest(task_roles: Mapping[str, str]) -> str:
    import hashlib
    raw = json.dumps(dict(sorted(task_roles.items())), separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_role_gateway(*, budget: ModelBudget | None = None,
                       gateway_factory: Any = None) -> RoleGateway:
    """Build the role gateway from the environment / role file.

    ``gateway_factory`` is a test seam with the :func:`_make_gateway` signature.
    """
    configs, overrides = load_role_config()
    primary_cfg, review_cfg = configs["primary"], configs["review"]
    if not primary_cfg.configured:
        raise ModelError("MODEL_CONFIG_MISSING")
    if not review_cfg.configured:
        raise RoleConfigError("review model role is not configured")
    factory = gateway_factory or _make_gateway
    shared_budget = budget if budget is not None else _budget_from_env()
    primary = factory(primary_cfg, shared_budget)
    review = primary if review_cfg.same_endpoint(primary_cfg) else \
        factory(review_cfg, shared_budget)
    return RoleGateway(primary, review, configs={**configs,
                                                 **({"review": review_cfg} if review is primary
                                                    else {})},
                       task_roles=overrides)
