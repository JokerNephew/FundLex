"""Role-based model routing for guide generation.

The existing revision engine exposes two roles (primary/review).  Guide
generation needs finer separation: a regulation analyst, an independent
requirement reviewer, discovery workers, guide authors, guide reviewers and a
coverage auditor.  Every role may point at a different model, but an
unconfigured role inherits the primary endpoint and is explicitly recorded as
such.  The router also records the exact model identity, prompt/schema hashes
and usage for every call so an evidence package can be reproduced.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from .models import canonical_json, sha256_json, utc_now
from ..model import ModelError, ModelGateway, ModelResult
from ..models.config import ModelRoleConfig, RoleConfigError, load_role_config
from ..models.roles import _budget_from_env, _make_gateway

ROLES = (
    "regulation_analyst",
    "requirement_reviewer",
    "discovery",
    "guide_author",
    "guide_reviewer",
    "coverage_auditor",
)

ROLE_ENV = {role: role.upper() for role in ROLES}
TASK_DEFAULT_ROLE = {
    "guide_req_extract": "regulation_analyst",
    "guide_req_review": "requirement_reviewer",
    "guide_intent": "discovery",
    "guide_impact_sweep": "discovery",
    "guide_batch_resolve": "discovery",
    "guide_impact_adjudicate": "discovery",
    "guide_local_candidate": "guide_author",
    "guide_merge": "guide_author",
    "guide_quality_review": "guide_reviewer",
    "guide_coverage_audit": "coverage_auditor",
    "guide_topic_coverage": "coverage_auditor",
    "guide_residual_sweep": "coverage_auditor",
    "guide_applicability": "coverage_auditor",
    "guide_engine_map": "guide_reviewer",
    "guide_repair": "guide_author",
}


class GuideModelConfigError(ValueError):
    pass


@dataclass
class ModelCallRecord:
    role: str
    task_type: str
    prompt_version: str
    model: str
    provider: str
    context_sha256: str
    instruction_sha256: str
    schema_sha256: str
    prompt_bundle_sha256: str
    request_options_sha256: str
    context_chars: int
    latency_ms: int
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    attempts: int
    reused_checkpoint: bool
    created_at: str = field(default_factory=utc_now)
    error_code: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "task_type": self.task_type,
            "prompt_version": self.prompt_version,
            "model": self.model,
            "provider": self.provider,
            "context_sha256": self.context_sha256,
            "instruction_sha256": self.instruction_sha256,
            "schema_sha256": self.schema_sha256,
            "prompt_bundle_sha256": self.prompt_bundle_sha256,
            "request_options_sha256": self.request_options_sha256,
            "context_chars": self.context_chars,
            "latency_ms": self.latency_ms,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.estimated_cost_usd,
            "attempts": self.attempts,
            "reused_checkpoint": self.reused_checkpoint,
            "created_at": self.created_at,
            "error_code": self.error_code,
        }


def _role_config(primary: ModelRoleConfig, role: str) -> ModelRoleConfig:
    """Resolve one role from guide-specific environment variables."""
    prefix = f"FUNDLEX_GUIDE_{ROLE_ENV[role]}_"
    model = os.environ.get(prefix + "MODEL", "").strip()
    base_url = os.environ.get(prefix + "BASE_URL", "").strip()
    api_key = os.environ.get(prefix + "API_KEY", "").strip()
    key_env = os.environ.get(prefix + "API_KEY_ENV", "").strip()
    if key_env:
        api_key = os.environ.get(key_env, "").strip()
    if not any((model, base_url, api_key)):
        return replace(primary, role=role)
    return replace(
        primary,
        role=role,
        model=model or primary.model,
        base_url=base_url or primary.base_url,
        api_key=api_key or primary.api_key,
        max_tokens=int(os.environ.get(prefix + "MAX_TOKENS", "8000")),
        max_context_chars=int(os.environ.get(prefix + "MAX_CONTEXT_CHARS", "32000")),
        max_calls=int(os.environ.get(prefix + "MAX_CALLS", "10000")),
        timeout_s=float(os.environ.get(prefix + "TIMEOUT_S", "90")),
        retries=int(os.environ.get(prefix + "RETRIES", "2")),
        provider=os.environ.get(prefix + "PROVIDER", "").strip() or primary.provider,
        request_options=(json.loads(os.environ[prefix + "REQUEST_OPTIONS_JSON"])
                          if os.environ.get(prefix + "REQUEST_OPTIONS_JSON") else dict(primary.request_options)),
        extra_headers=(json.loads(os.environ[prefix + "EXTRA_HEADERS_JSON"])
                       if os.environ.get(prefix + "EXTRA_HEADERS_JSON") else dict(primary.extra_headers)),
        user_agent=os.environ.get(prefix + "USER_AGENT", primary.user_agent),
    )


def _file_role_config(primary: ModelRoleConfig) -> dict[str, ModelRoleConfig]:
    path = os.environ.get("FUNDLEX_GUIDE_MODEL_ROLES_FILE", "").strip()
    if not path:
        return {}
    file = Path(path)
    if not file.is_file():
        raise GuideModelConfigError("GUIDE_MODEL_ROLES_FILE_NOT_FOUND")
    try:
        data = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GuideModelConfigError("GUIDE_MODEL_ROLES_FILE_INVALID") from exc
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        raise GuideModelConfigError("GUIDE_MODEL_ROLES_FILE_INVALID")
    result: dict[str, ModelRoleConfig] = {}
    for role, entry in models.items():
        if role not in ROLES or not isinstance(entry, dict):
            continue
        result[role] = replace(
            primary,
            role=role,
            model=str(entry.get("model") or primary.model),
            base_url=str(entry.get("base_url") or primary.base_url),
            api_key=str(entry.get("api_key") or (os.environ.get(entry.get("api_key_env", ""), "") if entry.get("api_key_env") else "") or primary.api_key),
            provider=str(entry.get("provider") or primary.provider),
            max_tokens=int(entry.get("max_tokens", 8000)),
            max_context_chars=int(entry.get("max_context_chars", 32000)),
            max_calls=int(entry.get("max_calls", 10000)),
            timeout_s=float(entry.get("timeout", 90)),
            retries=int(entry.get("retries", 2)),
            request_options=dict(entry.get("request_options") or primary.request_options),
            extra_headers=({str(k): str(v) for k, v in (entry.get("extra_headers") or primary.extra_headers).items()}),
            user_agent=str(entry.get("user_agent") or primary.user_agent),
        )
    return result


class GuideModelRouter:
    """Dispatch guide tasks to role-specific gateways and record every call."""

    def __init__(self, gateways: Mapping[str, ModelGateway], configs: Mapping[str, ModelRoleConfig] | None = None,
                 *, task_roles: Mapping[str, str] | None = None):
        self.gateways = dict(gateways)
        if "primary" not in self.gateways:
            raise GuideModelConfigError("GUIDE_MODEL_PRIMARY_MISSING")
        self.configs = dict(configs or {})
        self.task_roles = dict(TASK_DEFAULT_ROLE)
        if task_roles:
            self.task_roles.update(task_roles)
        self.records: list[ModelCallRecord] = []
        self._record_lock = threading.Lock()
        self._on_call = None
        # Stage workers default to four parallel calls, while the shared budget
        # may allow only one.  Without an in-process gate the extra workers
        # lose the reservation race, wait for the concurrency slot and then
        # surface MODEL_CONCURRENCY_LIMIT as a model failure.  Bound in-process
        # parallelism to the budget limit so stages queue instead of failing.
        limit = self._budget_concurrency()
        self._call_gate = (threading.BoundedSemaphore(limit) if limit > 0 else None)
        # Soft per-run cap on top of the shared ledger.  The shared ledger
        # remains the hard cost boundary; this prevents one low-frequency guide
        # run from consuming the whole remaining project budget silently.
        self.run_max_calls = int(os.environ.get("FUNDLEX_GUIDE_RUN_MAX_CALLS", "6000"))
        self.run_max_cost = float(os.environ.get("FUNDLEX_GUIDE_RUN_MAX_COST_USD", "12"))

    @classmethod
    def from_env(cls, *, budget: Any = None) -> "GuideModelRouter":
        configs, _task_roles = load_role_config()
        primary_cfg = configs["primary"]
        if not primary_cfg.configured:
            raise ModelError("MODEL_CONFIG_MISSING")
        # Guide generation deliberately allows long, batched analysis; these
        # gateway-level limits are independent from the shared cost ledger.
        primary_cfg = replace(
            primary_cfg,
            max_tokens=int(os.environ.get("FUNDLEX_GUIDE_MAX_TOKENS", "8000")),
            max_context_chars=int(os.environ.get("FUNDLEX_GUIDE_CONTEXT_CHARS", "32000")),
            max_calls=int(os.environ.get("FUNDLEX_GUIDE_MAX_CALLS", "10000")),
            timeout_s=float(os.environ.get("FUNDLEX_GUIDE_TIMEOUT_S", "90")),
            retries=int(os.environ.get("FUNDLEX_GUIDE_RETRIES", "2")),
        )
        role_configs = {role: _role_config(primary_cfg, role) for role in ROLES}
        role_configs.update(_file_role_config(primary_cfg))
        if os.environ.get("FUNDLEX_MODEL_MODE") == "replay":
            role_configs = {role: replace(cfg, base_url="http://localhost", api_key="replay-unused")
                            for role, cfg in role_configs.items()}
        shared_budget = None if os.environ.get("FUNDLEX_MODEL_MODE") == "replay" else (
            budget if budget is not None else _budget_from_env())
        gateways: dict[str, ModelGateway] = {"primary": _make_gateway(primary_cfg, shared_budget)}
        configs_out: dict[str, ModelRoleConfig] = {"primary": primary_cfg}
        for role, cfg in role_configs.items():
            if cfg.same_endpoint(primary_cfg) and cfg.max_tokens == primary_cfg.max_tokens \
                    and cfg.max_context_chars == primary_cfg.max_context_chars:
                gateways[role] = gateways["primary"]
            else:
                gateways[role] = _make_gateway(cfg, shared_budget)
            configs_out[role] = cfg
        return cls(gateways, configs_out)

    def set_call_callback(self, callback) -> None:
        self._on_call = callback

    # -- compatibility surface for fundlex.guide.build_guide_document --------
    @property
    def max_context_chars(self) -> int:
        return min(getattr(gateway, "max_context_chars", 12000)
                   for gateway in self.gateways.values())

    @property
    def max_calls(self) -> int:
        return sum(getattr(gateway, "max_calls", 0) for gateway in set(self.gateways.values()))

    @property
    def model(self) -> str:
        return getattr(self.gateways["primary"], "model", "")

    @property
    def calls(self) -> int:
        return len(self.records)

    @property
    def events(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records]

    @property
    def budget(self) -> Any:
        return getattr(self.gateways["primary"], "budget", None)

    def identity(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for role in ROLES:
            cfg = self.configs.get(role)
            gateway = self.gateways.get(role) or self.gateways["primary"]
            result[role] = {
                "role": role,
                "provider": getattr(gateway, "provider", "") or (cfg.provider if cfg else ""),
                "model": getattr(gateway, "model", "") or (cfg.model if cfg else ""),
                "max_context_chars": getattr(gateway, "max_context_chars", 0),
                "max_output_tokens": getattr(gateway, "max_completion_tokens", 0),
                "temperature": 0,
                "request_options_sha256": hashlib.sha256(canonical_json(
                    dict(getattr(gateway, "request_options", {}) or {})).encode()).hexdigest(),
                "configured": bool(cfg.configured) if cfg else True,
                "shares_primary_endpoint": gateway is self.gateways["primary"],
                "same_model_as_author": (
                    role == "guide_author" or
                    getattr(gateway, "model", "") == getattr(self.gateways.get("guide_author", self.gateways["primary"]), "model", "")
                ),
            }
        author = result.get("guide_author", {}).get("model", "")
        reviewer = result.get("guide_reviewer", {}).get("model", "")
        result["independent_model_review"] = bool(author and reviewer and author != reviewer)
        result["independent_model_review_status"] = (
            "qualified" if result["independent_model_review"] else "independent_model_review_not_qualified"
        )
        return result

    def _gateway_for(self, task_type: str, role: str | None) -> tuple[str, ModelGateway]:
        selected = role or self.task_roles.get(task_type, "regulation_analyst")
        if selected not in ROLES:
            raise GuideModelConfigError(f"GUIDE_MODEL_ROLE_INVALID:{selected}")
        return selected, self.gateways.get(selected) or self.gateways["primary"]

    def _invoke_gateway(self, gateway: ModelGateway, **kwargs: Any) -> ModelResult:
        try:
            return gateway.call(**kwargs)
        except ModelError as exc:
            if str(exc.code) == "MODEL_CIRCUIT_OPEN":
                # The shared budget circuit opens after three provider errors
                # and cools down for 120 seconds.  A stage that hits it should
                # wait once, not mark the whole stage as blocked.
                time.sleep(125)
                return gateway.call(**kwargs)
            raise

    def _budget_concurrency(self) -> int:
        for gateway in self.gateways.values():
            budget = getattr(gateway, "budget", None)
            if budget is None:
                continue
            try:
                return max(1, int(getattr(budget, "concurrency", 0) or 0))
            except (TypeError, ValueError):
                return 1
        return 0

    def _record(self, record: ModelCallRecord) -> None:
        with self._record_lock:
            self.records.append(record)
            if self._on_call:
                self._on_call(record)

    def call(self, *, task_type: str, bounded_context: str, response_schema: dict,
             instruction: str, prompt_version: str = "v1", role: str | None = None) -> ModelResult:
        with self._record_lock:
            call_count = len(self.records)
            current_cost = sum(record.estimated_cost_usd or 0 for record in self.records)
        if call_count >= self.run_max_calls:
            raise ModelError("GUIDE_RUN_CALL_BUDGET_EXCEEDED", self.metrics())
        if current_cost >= self.run_max_cost:
            raise ModelError("GUIDE_RUN_COST_BUDGET_EXCEEDED", self.metrics())
        selected, gateway = self._gateway_for(task_type, role)
        context_sha = hashlib.sha256(bounded_context.encode("utf-8")).hexdigest()
        instruction_sha = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
        schema_sha = sha256_json(response_schema)
        prompt_bundle = sha256_json({
            "role": selected, "task_type": task_type, "prompt_version": prompt_version,
            "instruction_sha256": instruction_sha, "schema_sha256": schema_sha,
            "model": getattr(gateway, "model", ""),
        })
        try:
            kwargs = dict(task_type=task_type, bounded_context=bounded_context,
                          response_schema=response_schema, instruction=instruction,
                          prompt_version=prompt_version)
            if self._call_gate is None:
                result = self._invoke_gateway(gateway, **kwargs)
            else:
                with self._call_gate:
                    result = self._invoke_gateway(gateway, **kwargs)
            reused = int(getattr(result, "attempts", 1)) == 0
            record = ModelCallRecord(
                role=selected, task_type=task_type, prompt_version=prompt_version,
                model=result.model, provider=getattr(gateway, "provider", "") or "",
                context_sha256=context_sha, instruction_sha256=instruction_sha,
                schema_sha256=schema_sha, prompt_bundle_sha256=prompt_bundle,
                request_options_sha256=hashlib.sha256(canonical_json(
                    dict(getattr(gateway, "request_options", {}) or {})).encode()).hexdigest(),
                context_chars=len(bounded_context), latency_ms=result.latency_ms,
                prompt_tokens=result.prompt_tokens, completion_tokens=result.completion_tokens,
                total_tokens=result.total_tokens, estimated_cost_usd=result.estimated_cost_usd,
                attempts=result.attempts, reused_checkpoint=reused,
            )
        except ModelError as exc:
            record = ModelCallRecord(
                role=selected, task_type=task_type, prompt_version=prompt_version,
                model=getattr(gateway, "model", ""), provider=getattr(gateway, "provider", "") or "",
                context_sha256=context_sha, instruction_sha256=instruction_sha,
                schema_sha256=schema_sha, prompt_bundle_sha256=prompt_bundle,
                request_options_sha256="", context_chars=len(bounded_context),
                latency_ms=0, prompt_tokens=None, completion_tokens=None, total_tokens=None,
                estimated_cost_usd=None, attempts=0, reused_checkpoint=False,
                error_code=exc.code,
            )
            self._record(record)
            raise
        self._record(record)
        return result

    def metrics(self) -> dict[str, Any]:
        by_role: dict[str, dict[str, Any]] = {}
        for record in self.records:
            item = by_role.setdefault(record.role, {"calls": 0, "http_attempts": 0,
                                                    "prompt_tokens": 0, "completion_tokens": 0,
                                                    "estimated_cost_usd": 0.0, "errors": 0})
            item["calls"] += 1
            item["http_attempts"] += record.attempts
            item["prompt_tokens"] += record.prompt_tokens or 0
            item["completion_tokens"] += record.completion_tokens or 0
            item["estimated_cost_usd"] += record.estimated_cost_usd or 0.0
            if record.error_code:
                item["errors"] += 1
        return {"by_role": by_role, "calls": len(self.records),
                "estimated_cost_usd": round(sum(r.estimated_cost_usd or 0 for r in self.records), 8),
                "error_count": sum(1 for r in self.records if r.error_code)}

    def close(self) -> None:
        closed = set()
        for gateway in self.gateways.values():
            if id(gateway) in closed:
                continue
            closed.add(id(gateway))
            gateway.close()
