"""Configuration for the primary and review model roles.

The two roles are configured independently (provider / model / base_url / API key /
timeout / max tokens / retries), while the review role may explicitly inherit any
field from the primary role.  A deployment that only sets ``LLM_*`` therefore keeps
working: both roles resolve to the same endpoint but remain separate roles with
separate task types and call records.

Sources, in increasing priority:

1. defaults / ``LLM_*`` for the primary role;
2. a JSON or YAML file named by ``FUNDLEX_MODEL_ROLES_FILE``::

       models:
         primary: {provider: openai, model: model-a, base_url: ..., api_key_env: ...}
         review:  {provider: openai, model: model-b, base_url: ..., api_key_env: ...}
       task_roles:
         recall_verify: review

3. environment variables ``FUNDLEX_PRIMARY_*`` / ``FUNDLEX_REVIEW_*``.

API key values are never stored in logs or reports; only the variable *name* is
recorded by :meth:`ModelRoleConfig.safe_dict`.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping


class RoleConfigError(ValueError):
    """The role configuration is present but invalid."""


@dataclass(frozen=True)
class ModelRoleConfig:
    """One endpoint plus its transport knobs."""

    role: str
    provider: str = ""
    model: str = ""
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    timeout_s: float = 45.0
    max_tokens: int = 1500
    retries: int = 1
    max_context_chars: int = 12000
    max_calls: int = 16
    request_options: Mapping[str, Any] = field(default_factory=dict)
    extra_headers: Mapping[str, str] = field(default_factory=dict, repr=False)
    user_agent: str = "fundlex/0.3.0"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.model and self.api_key)

    def safe_dict(self) -> dict[str, Any]:
        """Serialisable view without the API key value."""
        data = asdict(self)
        data.pop("api_key", None)
        data.pop("extra_headers", None)
        data["api_key_set"] = bool(self.api_key)
        return data

    def same_endpoint(self, other: "ModelRoleConfig") -> bool:
        return (self.provider, self.model, self.base_url, self.api_key) == \
               (other.provider, other.model, other.base_url, other.api_key)


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int_env(name: str, default: int) -> int:
    value = _env(name)
    try:
        return int(value) if value else default
    except ValueError as exc:
        raise RoleConfigError(f"{name} must be an integer") from exc


def _float_env(name: str, default: float) -> float:
    value = _env(name)
    try:
        return float(value) if value else default
    except ValueError as exc:
        raise RoleConfigError(f"{name} must be a number") from exc


def _json_env(name: str, default: dict[str, Any]) -> dict[str, Any]:
    raw = _env(name)
    if not raw:
        return dict(default)
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise RoleConfigError(f"{name} must be valid JSON") from exc
    if not isinstance(value, dict):
        raise RoleConfigError(f"{name} must be a JSON object")
    return value


def _file_config(path: str) -> dict[str, Any]:
    if not path:
        return {}
    file = Path(path)
    if not file.is_file():
        raise RoleConfigError(f"FUNDLEX_MODEL_ROLES_FILE not found: {file}")
    text = file.read_text(encoding="utf-8")
    if file.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - PyYAML is optional
            raise RoleConfigError("YAML role config requires PyYAML") from exc
        value = yaml.safe_load(text)
    else:
        value = json.loads(text)
    if not isinstance(value, dict):
        raise RoleConfigError("role config must be a mapping")
    models = value.get("models") or {}
    task_roles = value.get("task_roles") or {}
    if not isinstance(models, dict) or not isinstance(task_roles, dict):
        raise RoleConfigError("models and task_roles must be mappings")
    return {"models": models, "task_roles": task_roles}


def _merge_endpoint(entry: Mapping[str, Any], *, role: str,
                    inherited: ModelRoleConfig | None) -> ModelRoleConfig:
    """One role entry from a file, with optional inheritance from the primary."""
    if not isinstance(entry, Mapping):
        raise RoleConfigError(f"models.{role} must be a mapping")
    api_key = str(entry.get("api_key") or "")
    api_key_env = str(entry.get("api_key_env") or "")
    if api_key_env:
        api_key = os.environ.get(api_key_env, "").strip()
    base = inherited
    return ModelRoleConfig(
        role=role,
        provider=str(entry.get("provider") or (base.provider if base else "")),
        model=str(entry.get("model") or (base.model if base else "")),
        base_url=str(entry.get("base_url") or (base.base_url if base else "")),
        api_key=api_key or (base.api_key if base else ""),
        timeout_s=float(entry.get("timeout", entry.get("timeout_s",
                         base.timeout_s if base else 45.0))),
        max_tokens=int(entry.get("max_tokens", base.max_tokens if base else 1500)),
        retries=int(entry.get("retry", entry.get("retries", base.retries if base else 1))),
        max_context_chars=int(entry.get("max_context_chars",
                            base.max_context_chars if base else 12000)),
        max_calls=int(entry.get("max_calls", base.max_calls if base else 16)),
        request_options=dict(entry.get("request_options") or
                             (base.request_options if base else {})),
        extra_headers={str(k): str(v) for k, v in
                       (entry.get("extra_headers") or
                        (base.extra_headers if base else {})).items()},
        user_agent=str(entry.get("user_agent") or
                       (base.user_agent if base else "fundlex/0.3.0")),
    )


def _apply_env(cfg: ModelRoleConfig, prefix: str) -> ModelRoleConfig:
    """Apply ``FUNDLEX_<PREFIX>_*`` overrides to one role."""
    updates: dict[str, Any] = {}
    mapping = {
        "PROVIDER": ("provider", str),
        "MODEL": ("model", str),
        "BASE_URL": ("base_url", str),
        "API_KEY": ("api_key", str),
        "TIMEOUT_S": ("timeout_s", float),
        "MAX_TOKENS": ("max_tokens", int),
        "RETRIES": ("retries", int),
        "MAX_CONTEXT_CHARS": ("max_context_chars", int),
        "MAX_CALLS": ("max_calls", int),
        "USER_AGENT": ("user_agent", str),
    }
    for suffix, (attr, cast) in mapping.items():
        raw = _env(f"FUNDLEX_{prefix}_{suffix}")
        if raw:
            updates[attr] = cast(raw)
    raw_key_env = _env(f"FUNDLEX_{prefix}_API_KEY_ENV")
    if raw_key_env:
        updates["api_key"] = os.environ.get(raw_key_env, "").strip()
    for name, attr in (("FUNDLEX_MODEL_REQUEST_OPTIONS_JSON", "request_options"),
                       ("FUNDLEX_MODEL_EXTRA_HEADERS_JSON", "extra_headers")):
        # Transport-wide JSON knobs are intentionally shared by both roles unless
        # role-specific values were supplied in the file.
        if not updates.get(attr) and not getattr(cfg, attr):
            value = _env(name)
            if value:
                try:
                    parsed = json.loads(value)
                except ValueError as exc:
                    raise RoleConfigError(f"{name} must be valid JSON") from exc
                if not isinstance(parsed, dict):
                    raise RoleConfigError(f"{name} must be a JSON object")
                updates[attr] = parsed
    return replace(cfg, **updates) if updates else cfg


def load_role_config() -> tuple[dict[str, ModelRoleConfig], dict[str, str]]:
    """Resolve both roles and the task-role map.

    The primary role falls back to the existing ``LLM_*`` variables. The review
    role inherits the primary endpoint when it is not configured separately, which
    is explicitly allowed (same model, independent role).
    """
    file_values = _file_config(_env("FUNDLEX_MODEL_ROLES_FILE"))
    models = file_values.get("models") or {}

    primary_entry = models.get("primary") or {}
    primary = _merge_endpoint(primary_entry, role="primary", inherited=None)
    if not primary.configured:
        primary = replace(
            primary,
            provider=primary.provider or _env("LLM_PROVIDER"),
            model=primary.model or _env("LLM_MODEL"),
            base_url=primary.base_url or _env("LLM_BASE_URL"),
            api_key=primary.api_key or _env("LLM_API_KEY"),
            timeout_s=primary.timeout_s or 45.0,
            max_tokens=primary.max_tokens or 1500,
            retries=primary.retries if primary.retries is not None else 1,
        )
        # The generic model knobs describe the primary call path.
        if not primary_entry:
            primary = replace(
                primary,
                max_context_chars=_int_env("FUNDLEX_MODEL_CONTEXT_CHARS",
                                           primary.max_context_chars),
                max_calls=_int_env("FUNDLEX_MODEL_MAX_CALLS", primary.max_calls),
                max_tokens=_int_env("FUNDLEX_MODEL_MAX_OUTPUT_TOKENS", primary.max_tokens),
                timeout_s=_float_env("FUNDLEX_MODEL_TIMEOUT_S", primary.timeout_s),
                retries=_int_env("FUNDLEX_MODEL_RETRIES", primary.retries),
            )
    primary = _apply_env(primary, "PRIMARY")
    replay = _env("FUNDLEX_MODEL_MODE") == "replay"
    if replay:
        primary = replace(primary, base_url="http://localhost", api_key="replay-unused")

    review_entry = models.get("review") or {}
    review = _merge_endpoint(review_entry, role="review", inherited=primary)
    review = _apply_env(review, "REVIEW")
    if replay:
        review = replace(review, base_url="http://localhost", api_key="replay-unused")
    if not review.configured:
        # A partially configured review role must not silently borrow a different
        # endpoint: inherit only when nothing review-specific was supplied.
        if any(_env(f"FUNDLEX_REVIEW_{name}") for name in
               ("PROVIDER", "MODEL", "BASE_URL", "API_KEY", "API_KEY_ENV")) or review_entry:
            raise RoleConfigError("review model role is only partially configured")
        review = replace(primary, role="review")
    elif review.base_url != primary.base_url and review.api_key == primary.api_key:
        # Never forward the primary endpoint's credential to a different host.
        explicit_key = bool(_env("FUNDLEX_REVIEW_API_KEY") or _env("FUNDLEX_REVIEW_API_KEY_ENV")
                            or review_entry.get("api_key") or review_entry.get("api_key_env"))
        if not explicit_key:
            raise RoleConfigError("review model role uses another endpoint without its own API key")

    task_roles = {str(key): str(value) for key, value in
                  (file_values.get("task_roles") or {}).items()}
    return {"primary": primary, "review": review}, task_roles
