"""Owner-private, immutable BYOK connections and restricted public HTTPS transport."""
from __future__ import annotations

import ipaddress
import json
import os
import socket
import time
import uuid
from dataclasses import replace
from urllib.parse import urlsplit

import httpx
from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from .user_agent import USER_AGENT
from .models.config import ModelRoleConfig


PROVIDERS = {
    "openai": {"label": "OpenAI（兼容接口）", "base_url": "https://api.openai.com/v1",
               "models": ["gpt-4.1", "gpt-4.1-mini"]},
    "deepseek": {"label": "DeepSeek（兼容接口）", "base_url": "https://api.deepseek.com/v1",
                 "models": ["deepseek-chat", "deepseek-reasoner"]},
    "alibaba": {"label": "阿里云百炼（兼容接口）",
                "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "models": ["qwen-plus", "qwen-max", "qwen-turbo"]},
    "moonshot": {"label": "月之暗面 Kimi（兼容接口）", "base_url": "https://api.moonshot.cn/v1",
                 "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]},
    "siliconflow": {"label": "硅基流动（兼容接口）", "base_url": "https://api.siliconflow.cn/v1",
                    "models": ["Qwen/Qwen3-8B", "deepseek-ai/DeepSeek-V3"]},
    "zhipu": {"label": "智谱 AI（兼容接口）", "base_url": "https://open.bigmodel.cn/api/paas/v4",
              "models": ["glm-4-flash", "glm-4-plus", "glm-4.5"]},
    "custom": {"label": "其他 OpenAI 兼容服务", "base_url": "", "models": []},
}


class ConnectionError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class RoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source: str = "system"
    provider: str = ""
    model: str = Field(default="", max_length=256)
    base_url: str = Field(default="", max_length=1024)
    api_key: SecretStr = Field(default=SecretStr(""), max_length=4096)
    connection_id: str = Field(default="", max_length=64)


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    primary: RoleInput
    review: RoleInput


def ensure_schema(store):
    with store._connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS user_model_connections (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, settings_json MEDIUMTEXT NOT NULL,
            key_cipher MEDIUMTEXT NOT NULL, created_at REAL NOT NULL)""")


def cipher():
    # Fail closed; never derive encryption material from a user's password or key.
    try:
        return Fernet(os.environ["FUNDLEX_MODEL_SECRETS_KEY"].encode("ascii"))
    except (KeyError, ValueError, UnicodeError):
        raise ConnectionError("MODEL_SECRET_STORAGE_UNAVAILABLE") from None


def endpoint(value: str) -> str:
    try:
        u = urlsplit(value.strip())
        if (u.scheme != "https" or not u.hostname or u.username is not None
                or u.password is not None
                or u.query or u.fragment or any(ord(c) < 33 for c in value)
                or "\\" in value or "%" in u.netloc):
            raise ValueError()
        if u.port == 0:
            raise ValueError()
        host = u.hostname.encode("idna").decode("ascii")
        # Numeric hosts are allowed only if publicly routable.
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if host.lower() == "localhost" or "." not in host:
                raise ValueError()
        else:
            if not address.is_global or address.is_multicast:
                raise ValueError()
        return value.strip().rstrip("/")
    except (ValueError, UnicodeError):
        raise ConnectionError("MODEL_ENDPOINT_INVALID") from None


def public_addresses(host: str, port: int = 443) -> list[str]:
    try:
        addresses = sorted({row[4][0] for row in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})
        if not addresses or any(not ipaddress.ip_address(ip).is_global
                                or ipaddress.ip_address(ip).is_multicast for ip in addresses):
            raise ConnectionError("MODEL_ENDPOINT_BLOCKED")
        return addresses
    except (OSError, ValueError):
        raise ConnectionError("MODEL_CONNECTION_UNAVAILABLE") from None


class PublicHTTPSTransport(httpx.BaseTransport):
    """Resolve, validate ALL answers, then pin the connection IP (preserving TLS SNI).

    No proxy environment, no redirects, no DNS re-resolution between check/connect.
    Recheck DNS on every request, including pooled connections.
    """
    def __init__(self):
        self.transport = httpx.HTTPTransport(trust_env=False, retries=0)

    def handle_request(self, request):
        try:
            endpoint(str(request.url))
            host = request.url.host
            address = public_addresses(host, request.url.port or 443)[0]
        except ConnectionError:
            raise httpx.ConnectError("Model service address unavailable") from None
        headers = request.headers.copy()
        host_header = host if ":" not in host else f"[{host}]"
        if request.url.port:
            host_header += f":{request.url.port}"
        headers["Host"] = host_header
        pinned = httpx.Request(request.method, request.url.copy_with(host=address),
                               headers=headers, stream=request.stream,
                               extensions={**request.extensions, "sni_hostname": host})
        return self.transport.handle_request(pinned)

    def close(self):
        self.transport.close()


def client():
    return httpx.Client(transport=PublicHTTPSTransport(), trust_env=False,
                        follow_redirects=False, timeout=httpx.Timeout(30, connect=10))


def _stored(db, owner, connection_id):
    row = db.execute("SELECT * FROM user_model_connections WHERE id=? AND owner=?",
                     (connection_id, owner)).fetchone()
    if row is None:
        raise ConnectionError("MODEL_CONNECTION_NOT_FOUND")
    return row


def _decrypt(row):
    try:
        # The authenticated envelope binds ciphertext to owner and immutable id.
        value = json.loads(cipher().decrypt(row["key_cipher"].encode()))
        if value["owner"] != row["owner"] or value["id"] != row["id"]:
            raise ValueError()
        return value["key"]
    except (InvalidToken, ValueError, KeyError, TypeError):
        raise ConnectionError("MODEL_SECRET_STORAGE_UNAVAILABLE") from None


def _snapshot_connection_ids(raw):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(value, dict):
            return None
        if value.get("version") != 2:
            # Unversioned model preferences are the legacy model-name format.
            # Unknown versions or any credential reference must be retained
            # conservatively until their schema is understood.
            if value.get("version") is not None or any(
                    isinstance(value.get(role), dict) and "connection_id" in value[role]
                    for role in ("primary", "review")):
                return None
            return set()
        validate_snapshot(value)
        return {choice["connection_id"] for role in ("primary", "review")
                if isinstance((choice := value.get(role)), dict)
                and choice.get("source") == "personal" and choice.get("connection_id")}
    except (TypeError, ValueError, KeyError):
        # Corrupt historical snapshots must never cause credential deletion.
        return None


def _collect_unreferenced(db):
    retained = set()
    for query in ("SELECT settings_json FROM user_model_settings",
                  "SELECT model_preferences FROM tasks",
                  "SELECT model_preferences FROM batches"):
        try:
            rows = db.execute(query).fetchall()
        except Exception:
            # Old schemas or DB outages: retain ciphertext rather than risk a
            # queued/paused task losing the key it was created with.
            return
        for row in rows:
            raw = row[0]
            ids = _snapshot_connection_ids(raw)
            if ids is None:
                return
            retained.update(ids)
    try:
        rows = db.execute("SELECT id FROM user_model_connections").fetchall()
        for row in rows:
            if row[0] not in retained:
                db.execute("DELETE FROM user_model_connections WHERE id=?", (row[0],))
    except Exception:
        # GC is best-effort and may not interfere with settings changes.
        return


def prepare(db, owner, choice: RoleInput):
    if choice.source == "system":
        if choice.api_key.get_secret_value() or choice.connection_id or choice.base_url or choice.provider:
            raise ConnectionError("MODEL_SETTINGS_INVALID")
        return {"source": "system"}
    if choice.source != "personal" or choice.provider not in PROVIDERS:
        raise ConnectionError("MODEL_SETTINGS_INVALID")
    model = choice.model.strip()
    if not model or any(ord(c) < 32 for c in model):
        raise ConnectionError("MODEL_NAME_REQUIRED")
    provider = PROVIDERS[choice.provider]
    base_url = endpoint(provider["base_url"] or choice.base_url)
    if choice.provider != "custom" and choice.base_url and endpoint(choice.base_url) != base_url:
        raise ConnectionError("MODEL_ENDPOINT_INVALID")
    key = choice.api_key.get_secret_value().strip()
    if not key and choice.connection_id:
        row = _stored(db, owner, choice.connection_id)
        old = json.loads(row["settings_json"])
        # Never send an old (or system) secret to a changed provider/address.
        if (old["provider"], old["base_url"]) != (choice.provider, base_url):
            raise ConnectionError("MODEL_KEY_REQUIRED")
        key = _decrypt(row)
    if not key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        raise ConnectionError("MODEL_KEY_REQUIRED")
    return {"source": "personal", "provider": choice.provider, "model": model,
            "base_url": base_url, "key": key}


def parse(payload):
    try:
        return SettingsInput.model_validate(payload)
    except ValidationError:
        # Never return Pydantic's input echo: it could contain an API key.
        raise ConnectionError("MODEL_SETTINGS_INVALID") from None


def save(db, owner, payload):
    choices = parse(payload)
    prepared = {role: prepare(db, owner, getattr(choices, role)) for role in ("primary", "review")}
    result = {"version": 2}
    for role, value in prepared.items():
        if value["source"] == "system":
            result[role] = value
            continue
        key = value.pop("key")
        connection_id = uuid.uuid4().hex
        envelope = json.dumps({"owner": owner, "id": connection_id, "key": key}).encode()
        encrypted = cipher().encrypt(envelope).decode()
        db.execute("INSERT INTO user_model_connections(id,owner,settings_json,key_cipher,created_at)"
                   " VALUES(?,?,?,?,?)", (connection_id, owner, json.dumps(value), encrypted, time.time()))
        result[role] = {**value, "connection_id": connection_id}
    return result


def validate_snapshot(value):
    if set(value) != {"version", "primary", "review"} or value["version"] != 2:
        raise ConnectionError("MODEL_SETTINGS_INVALID")
    for role in ("primary", "review"):
        choice = value[role]
        if not isinstance(choice, dict):
            raise ConnectionError("MODEL_SETTINGS_INVALID")
        if choice == {"source": "system"}:
            continue
        if (set(choice) != {"source", "provider", "model", "base_url", "connection_id"}
                or choice["source"] != "personal" or choice["provider"] not in PROVIDERS
                or not all(isinstance(v, str) and v for v in choice.values())):
            raise ConnectionError("MODEL_SETTINGS_INVALID")
        endpoint(choice["base_url"])
    return value


def resolve(store, owner, snapshot, configs):
    validate_snapshot(snapshot)
    if store is None or not owner:
        raise ConnectionError("MODEL_CONNECTION_NOT_FOUND")
    ensure_schema(store)
    with store._connect() as db:
        for role in ("primary", "review"):
            choice = snapshot[role]
            if choice["source"] == "system":
                continue
            row = _stored(db, owner, choice["connection_id"])
            expected = {k: v for k, v in choice.items() if k != "connection_id"}
            if json.loads(row["settings_json"]) != expected:
                raise ConnectionError("MODEL_SETTINGS_INVALID")
            # Never inherit deployment credentials, headers or provider options.
            # These transport defaults are system-owned, not user form fields.
            configs[role] = replace(configs[role], role=role, provider=choice["provider"],
                model=choice["model"], base_url=choice["base_url"], api_key=_decrypt(row),
                request_options={}, extra_headers={}, user_agent=USER_AGENT)
    return configs


def gateway(cfg, budget):
    from .models.roles import _make_gateway
    # Inject the pinned transport into all private-role clones, too.
    result = _make_gateway(cfg, budget)
    if result._client is not None:
        result._client.close()
    if result.mode != "replay":
        result._client = client()
    return result


def test_connection(store, owner, payload):
    """Explicit, minimal user-triggered request; no contract or raw errors returned."""
    try:
        choice = RoleInput.model_validate(payload)
    except ValidationError:
        raise ConnectionError("MODEL_SETTINGS_INVALID") from None
    ensure_schema(store)
    with store._connect() as db:
        prepared = prepare(db, owner, choice)
    if prepared["source"] == "system":
        raise ConnectionError("MODEL_TEST_PERSONAL_ONLY")
    try:
        with client() as transport:
            with transport.stream("POST", prepared["base_url"] + "/chat/completions",
                    headers={"Authorization": "Bearer " + prepared["key"]},
                    json={"model": prepared["model"], "messages": [{"role": "user", "content": "Reply OK."}],
                          "max_tokens": 16}) as response:
                status = response.status_code
                if status in (401, 403):
                    return {"ok": False, "message": "访问密钥无效或没有使用该模型的权限。"}
                if status == 402:
                    return {"ok": False, "message": "供应商账户余额不足。"}
                if status == 404:
                    return {"ok": False, "message": "模型或服务地址不可用，请核对供应商信息。"}
                if status == 429:
                    return {"ok": False, "message": "服务繁忙或账户额度不足，请稍后重试或检查供应商账户。"}
                if status != 200:
                    return {"ok": False, "message": "供应商暂时无法完成请求，请核对模型和服务地址。"}
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 64000:
                        raise ValueError()
                    chunks.append(chunk)
                body = json.loads(b"".join(chunks))
                if not body["choices"][0]["message"].get("content"):
                    raise ValueError()
        return {"ok": True, "message": "连接正常，模型可以响应。实际合同处理能力仍需任务验证。"}
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return {"ok": False, "message": "无法连接或读取模型响应，请检查服务地址和网络后重试。"}
