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
    from . import user_model_connections
    user_model_connections.ensure_schema(store)
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


def snapshot_in_task_transaction(db, owner: str, *, mysql: bool = False) -> dict:
    """Read model settings while holding the task-creation transaction lock.

    The row lock prevents a concurrent settings save/reset from collecting an
    immutable credential after a task has snapshotted it but before that task
    row becomes visible to the collector.
    """
    sql = "SELECT settings_json FROM user_model_settings WHERE owner=?"
    if mysql:
        sql += " FOR UPDATE"
    row = db.execute(sql, (owner,)).fetchone()
    return decode_snapshot(row["settings_json"]) if row else {}


def decode_snapshot(raw) -> dict:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if value == {}:
            return {}
        if isinstance(value, dict) and value.get("version") == 2:
            from .user_model_connections import validate_snapshot
            return validate_snapshot(value)
        return Preferences.model_validate(value).model_dump()
    except (ValueError, TypeError, ValidationError):
        raise ModelSettingsError("MODEL_SETTINGS_INVALID") from None


def resolve(preferences: dict, *, store=None, owner=None):
    configs, task_roles = load_role_config()
    if not preferences:
        return configs, task_roles
    clean = decode_snapshot(preferences)
    if clean.get("version") == 2:
        from . import user_model_connections
        return user_model_connections.resolve(store, owner, clean, configs), {}
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
            "api_key_set": bool(cfg.api_key)}


def public_settings(store, owner):
    preferences = snapshot(store, owner)
    try:
        if preferences.get("version") == 2:
            configs, _ = resolve(preferences, store=store, owner=owner)
            system_configs, _ = load_role_config()
        else:
            configs, _ = resolve(preferences)
            system_configs, _ = load_role_config()
        error = ""
    except (RoleConfigError, ValueError, TypeError) as exc:
        # Do not disclose deployment file paths or exception contents.
        try:
            configs, _ = load_role_config()
        except (RoleConfigError, ValueError, TypeError):
            configs = {role: ModelRoleConfig(role=role) for role in ("primary", "review")}
        system_configs = configs
        code = getattr(exc, "code", "")
        error = code if code in {"MODEL_SECRET_STORAGE_UNAVAILABLE", "MODEL_CONNECTION_NOT_FOUND",
                                "MODEL_SETTINGS_INVALID"} else "MODEL_CONFIG_MISSING"
    result = {"editable": True, "source": "personal" if preferences else "deployment",
            "config_error": error,
            "primary": _public_role("primary", configs["primary"]),
            "review": _public_role("review", configs["review"]),
            "review_inherits": (preferences.get("review") is None if preferences
                                else configs["review"].same_endpoint(configs["primary"]))}
    from .user_model_connections import PROVIDERS
    result["providers"] = [{"id": key, **value} for key, value in PROVIDERS.items()]
    for role in ("primary", "review"):
        choice = preferences.get(role) or {}
        if preferences.get("version") == 2 and choice.get("source") == "personal":
            result[role] = {**choice, "api_key_set": True, "role": role}
        else:
            result[role]["source"] = "system"
            result[role]["connection_id"] = ""
            result[role]["base_url"] = ""
            legacy_choice = choice or (preferences.get("primary") if preferences
                                       and preferences.get("version") != 2 else None)
            if legacy_choice:
                result[role]["legacy_model"] = legacy_choice.get("model", "")
        result[role]["system_model"] = system_configs[role].model
    result["source"] = ("personal" if any((preferences.get(role) or {}).get("source") == "personal"
                                            for role in ("primary", "review")) else "deployment")
    result["legacy_preferences"] = bool(preferences and preferences.get("version") != 2)
    return result


def save_settings(store, owner, payload):
    if isinstance(payload, dict) and isinstance(payload.get("primary"), dict) and "source" in payload["primary"]:
        from . import user_model_connections
        ensure_schema(store)
        with store._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            clean = user_model_connections.save(db, owner, payload)
            db.execute("INSERT OR REPLACE INTO user_model_settings"
                       "(owner,settings_json,updated_at) VALUES(?,?,?)",
                       (owner, json.dumps(clean, ensure_ascii=False), time.time()))
            user_model_connections._collect_unreferenced(db)
        return public_settings(store, owner)
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
        from . import user_model_connections
        user_model_connections._collect_unreferenced(db)
    return public_settings(store, owner)


def gateway_for(preferences, *, store=None, owner=None):
    from .models.roles import build_role_gateway, _make_gateway
    from . import user_model_connections
    configs, task_roles = resolve(preferences, store=store, owner=owner)
    def factory(cfg, budget):
        if preferences.get("version") == 2 and preferences[cfg.role]["source"] == "personal":
            return user_model_connections.gateway(cfg, budget)
        return _make_gateway(cfg, budget)
    return build_role_gateway(configs=configs, task_roles=task_roles, gateway_factory=factory)
