"""Private model preferences: no endpoint, credential or environment mutation."""
from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .models.config import ModelRoleConfig, RoleConfigError, load_role_config


class ModelSettingsError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class RolePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    model: str = Field(default="", max_length=256)
    timeout_s: float = Field(default=45.0, gt=0, le=600)
    max_tokens: int = Field(default=1500, ge=1, le=200000)
    retries: int = Field(default=1, ge=0, le=10)
    max_context_chars: int = Field(default=12000, ge=1000, le=2000000)
    request_options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError("invalid model")
        return value.strip()

    @field_validator("request_options")
    @classmethod
    def clean_options(cls, value):
        if not set(value).issubset({"reasoning_effort", "thinking", "reasoning"}):
            raise ValueError("unsupported request option")
        if len(json.dumps(value)) > 2048:
            raise ValueError("request options too large")
        return value


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    primary: RolePreferences
    review: RolePreferences | None = None


def ensure_schema(store):
    with store._connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS user_model_settings (
            owner TEXT PRIMARY KEY, settings_json MEDIUMTEXT NOT NULL,
            updated_at REAL NOT NULL)""")


def snapshot(store, owner: str) -> dict:
    """Return validated private choices; malformed stored data fails closed."""
    ensure_schema(store)
    with store._connect() as db:
        row = db.execute("SELECT settings_json FROM user_model_settings WHERE owner=?",
                         (owner,)).fetchone()
    if row is None:
        return {}
    return decode_snapshot(row["settings_json"])


def decode_snapshot(raw) -> dict:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if value == {}:
            return {}
        return Preferences.model_validate(value).model_dump()
    except (ValueError, TypeError, ValidationError):
        raise ModelSettingsError("MODEL_SETTINGS_INVALID") from None


def resolve(preferences: dict):
    configs, task_roles = load_role_config()
    if not preferences:
        return configs, task_roles
    clean = decode_snapshot(preferences)
    for role in ("primary", "review"):
        choice = clean.get(role)
        if choice is None:
            # Inherit the user's primary choices, not its credential. Review
            # transport stays the deployment's independently configured endpoint.
            choice = clean["primary"]
        updates = dict(choice)
        if not updates.get("model"):
            updates.pop("model", None)
        configs[role] = replace(configs[role], **updates)
    return configs, task_roles


def _public_role(role, cfg):
    return {"role": role, "provider": cfg.provider, "model": cfg.model,
            "api_key_set": bool(cfg.api_key), "timeout_s": cfg.timeout_s,
            "max_tokens": cfg.max_tokens, "retries": cfg.retries,
            "max_context_chars": cfg.max_context_chars,
            "request_options": dict(cfg.request_options)}


def public_settings(store, owner):
    preferences = snapshot(store, owner)
    try:
        configs, _ = resolve(preferences)
        error = ""
    except (RoleConfigError, ValueError, TypeError):
        # Do not disclose deployment file paths or exception contents.
        configs = {role: ModelRoleConfig(role=role) for role in ("primary", "review")}
        error = "MODEL_CONFIG_MISSING"
    return {"editable": True, "source": "personal" if preferences else "deployment",
            "config_error": error,
            "primary": _public_role("primary", configs["primary"]),
            "review": _public_role("review", configs["review"]),
            "review_inherits": (preferences.get("review") is None if preferences
                                else configs["review"].same_endpoint(configs["primary"]))}


def save_settings(store, owner, payload):
    clean = decode_snapshot(payload)
    ensure_schema(store)
    with store._connect() as db:
        db.execute("INSERT OR REPLACE INTO user_model_settings"
                   "(owner,settings_json,updated_at) VALUES(?,?,?)",
                   (owner, json.dumps(clean, ensure_ascii=False), time.time()))
    return public_settings(store, owner)


def reset_settings(store, owner):
    ensure_schema(store)
    with store._connect() as db:
        db.execute("DELETE FROM user_model_settings WHERE owner=?", (owner,))
    return public_settings(store, owner)


def gateway_for(preferences):
    from .models.roles import build_role_gateway
    configs, task_roles = resolve(preferences)
    return build_role_gateway(configs=configs, task_roles=task_roles)
