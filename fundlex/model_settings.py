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


_SYSTEM_DEFAULT_OWNER = "__system_default_model__"


def snapshot_system_default(store) -> dict:
    """系统级默认模型（管理员设，所有用户 apply）。读取失败不冒称已配置。"""
    return snapshot(store, _SYSTEM_DEFAULT_OWNER)


def save_system_default(store, payload) -> dict:
    """保存系统默认模型：与 /api/settings/model 同形（RolePreferences），
    保存前网关冒烟（联通失败拒存）。api_key 继续走环境密钥面，不落库。

    ``payload`` = flat RolePreferences dict（{model,timeout_s,...}）。
    """
    payload = {"primary": payload}
    # 先留旧值：smoke 失败必须回滚到原配置，不能因一次保存失败覆盖/清空既有默认。
    ensure_schema(store)
    with store._connect() as db:
        prior = db.execute("SELECT settings_json FROM user_model_settings WHERE owner=?",
                           (_SYSTEM_DEFAULT_OWNER,)).fetchone()
    prior_json = prior["settings_json"] if prior else None
    result = save_settings(store, _SYSTEM_DEFAULT_OWNER, payload)
    snap = snapshot_system_default(store)
    if not snap:
        raise ModelSettingsError("SYSTEM_MODEL_EMPTY")
    smoke = _smoke_gateway(snap, store=store)
    if smoke is not True:
        with store._connect() as db:
            if prior_json is None:
                db.execute("DELETE FROM user_model_settings WHERE owner=?",
                           (_SYSTEM_DEFAULT_OWNER,))
            else:
                db.execute("INSERT OR REPLACE INTO user_model_settings"
                           "(owner,settings_json,updated_at) VALUES(?,?,?)",
                           (_SYSTEM_DEFAULT_OWNER, prior_json, time.time()))
        raise ModelSettingsError(f"SYSTEM_MODEL_SMOKE_FAILED:{smoke}")
    return result


def reset_system_default(store) -> dict:
    return reset_settings(store, _SYSTEM_DEFAULT_OWNER)


def _smoke_gateway(preferences: dict, *, store) -> "bool | str":
    """轻量上联烟：GET {base_url}/models 15s 超时；失败即返错码/原因。"""
    api = resolve(preferences, store=store)[0].get("primary")
    base_url = str(getattr(api, "base_url", "") or "").rstrip("/")
    model = str(getattr(api, "model", "") or "")
    if not base_url or not model:
        return "SYSTEM_MODEL_INCOMPLETE"
    import os
    import urllib.request
    import urllib.error
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        return "SYSTEM_MODEL_SECRET_MISSING"
    path = "/models" if base_url.rstrip("/").endswith("/v1") else "/v1/models"
    req = urllib.request.Request(base_url + path,
                                 headers={"Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return f"SYSTEM_MODEL_SMOKE_HTTP_{resp.status}"
    except urllib.error.HTTPError as exc:
        return f"SYSTEM_MODEL_SMOKE_HTTP_{exc.code}"
    except Exception:
        return "SYSTEM_MODEL_SMOKE_UNREACHABLE"
    return True


def resolve_for_owner(store, owner: str, *, mysql: bool = False) -> dict:
    """任务创建时冻结快照的解析序：用户 > 系统默认 > env。"""
    mine = snapshot(store, owner)
    if mine:
        return mine
    return snapshot_system_default(store)


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
