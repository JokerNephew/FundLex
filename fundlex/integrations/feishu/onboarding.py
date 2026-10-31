"""Self-service own-tenant Feishu app onboarding.

A FundLex deployment belongs to one Feishu tenant.  A user whose Feishu account
is in another tenant cannot authorize the deployment's self-built app (Feishu
rejects the authorization page before any FundLex callback runs).  This module
lets such a user create a self-built app *inside their own tenant*, then verifies
and stores its credentials so the same FundLex account can use their own bot.

Design rules:

* The app secret is encrypted at rest with the deployment secret key
  (``FUNDLEX_MODEL_SECRETS_KEY``) and is never returned, logged or traced.
* Verification is real: tenant access token, app metadata/scopes and bot status
  are read from Feishu's OpenAPI before anything is saved.
* A saved app still has to prove end-to-end delivery: the user sends one message
  to their bot and the long-connection runtime records that first event.  Only
  then is onboarding reported as active.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

FEISHU_BASE = "https://open.feishu.cn/open-apis"
OPEN_PLATFORM = "https://open.feishu.cn"
APP_ID_RE = re.compile(r"^cli_[A-Za-z0-9]{6,64}$")
SECRET_MIN, SECRET_MAX = 16, 256

# Scopes the FundLex bot actually needs in the user's tenant. Each entry is
# (scope key, human label, what breaks without it).
REQUIRED_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("im:message:send_as_bot", "以应用身份发消息",
     "任务卡、状态更新和结果文件都发不出来"),
    ("im:message.p2p_msg:readonly", "读取用户发给机器人的单聊消息",
     "机器人收不到你发的合同和指令"),
    ("im:resource", "获取消息中的资源文件",
     "无法下载你发送的 DOCX/PDF 附件"),
)
OPTIONAL_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("im:message.pins:write_only", "置顶任务卡（可选）",
     "只是置顶入口不可用，不影响任务"),
)
# The routing/verification APIs below do not need this scope, but reading an
# app's own scope list does; when absent we fall back to the test-message check.
APP_INFO_SCOPE = "application:application:self_manage"

STATUS_NO_APP = "no_app"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_READY = "ready"
STATUS_WAITING_MESSAGE = "waiting_message"
STATUS_ACTIVE = "active"

HEARTBEAT_STALE_SECONDS = 45


class AppOnboardingError(RuntimeError):
    """User-actionable failure; ``code`` is a stable FEISHU_APP_* identifier."""

    def __init__(self, code: str, message: str = "", *, detail: str = "",
                 link: str = "", http_status: int = 422):
        self.code = code
        self.message = message or code
        self.detail = detail
        self.link = link
        self.http_status = http_status
        super().__init__(self.message)

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail,
                "link": self.link}


def _secret_cipher() -> Fernet:
    raw = os.environ.get("FUNDLEX_MODEL_SECRETS_KEY", "").strip()
    if not raw:
        raise AppOnboardingError(
            "FEISHU_APP_SECRET_STORAGE_UNAVAILABLE",
            "服务器尚未配置密钥加密存储，暂时无法保存应用 Secret。",
            detail="请联系管理员配置 FUNDLEX_MODEL_SECRETS_KEY。", http_status=503)
    try:
        return Fernet(raw.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise AppOnboardingError(
            "FEISHU_APP_SECRET_STORAGE_UNAVAILABLE",
            "服务器密钥加密配置无效，暂时无法保存应用 Secret。",
            detail="请联系管理员检查 FUNDLEX_MODEL_SECRETS_KEY。", http_status=503) from exc


def _request(method: str, path: str, *, body: dict[str, Any] | None = None,
             token: str = "", timeout: float = 20.0) -> dict[str, Any]:
    url = path if path.startswith("https://") else FEISHU_BASE + path
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    if token:
        request.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Feishu returns a JSON error body on 4xx; the body never contains the
        # submitted secret, so it is safe to parse. Only the code/scope is kept.
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (ValueError, OSError):
            raise AppOnboardingError(
                "FEISHU_APP_VERIFY_UNAVAILABLE",
                "暂时连不上飞书开放平台，请稍后重试。", http_status=502) from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AppOnboardingError(
            "FEISHU_APP_VERIFY_UNAVAILABLE",
            "暂时连不上飞书开放平台，请检查服务器网络后重试。",
            detail=type(exc).__name__, http_status=502) from None
    except ValueError:
        raise AppOnboardingError(
            "FEISHU_APP_VERIFY_BAD_RESPONSE",
            "飞书返回了无法识别的内容，请稍后重试。", http_status=502) from None
    if not isinstance(payload, dict):
        raise AppOnboardingError("FEISHU_APP_VERIFY_BAD_RESPONSE",
                                 "飞书返回了无法识别的内容，请稍后重试。", http_status=502)
    return payload


def _feishu_error_code(payload: dict[str, Any]) -> int | None:
    try:
        return int(payload.get("code"))
    except (TypeError, ValueError):
        return None


def _scope_violations(payload: dict[str, Any]) -> list[str]:
    error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    items = error.get("permission_violations") or []
    scopes = [str(item.get("subject") or "") for item in items if isinstance(item, dict)]
    return [scope for scope in scopes if scope]


def _permission_link(app_id: str, scope: str = "") -> str:
    if not app_id:
        return f"{OPEN_PLATFORM}/app"
    suffix = f"&q={scope}" if scope else ""
    return f"{OPEN_PLATFORM}/app/{app_id}/auth?lang=zh-CN{suffix}"


def _bot_link(app_id: str) -> str:
    return f"{OPEN_PLATFORM}/app/{app_id}/bot?lang=zh-CN"


def _event_link(app_id: str) -> str:
    return f"{OPEN_PLATFORM}/app/{app_id}/event?lang=zh-CN"


def _version_link(app_id: str) -> str:
    return f"{OPEN_PLATFORM}/app/{app_id}/version?lang=zh-CN"


def guide(app_id: str = "") -> dict[str, Any]:
    """Deep links and the copyable scope list used by the onboarding wizard."""
    return {
        "create_app": f"{OPEN_PLATFORM}/app?lang=zh-CN",
        "permission": _permission_link(app_id),
        "bot": _bot_link(app_id) if app_id else f"{OPEN_PLATFORM}/app",
        "event": _event_link(app_id) if app_id else f"{OPEN_PLATFORM}/app",
        "version": _version_link(app_id) if app_id else f"{OPEN_PLATFORM}/app",
        "required_scopes": [{"key": key, "label": label, "why": why}
                            for key, label, why in REQUIRED_SCOPES],
        "optional_scopes": [{"key": key, "label": label, "why": why}
                            for key, label, why in OPTIONAL_SCOPES],
        "scopes_text": "\n".join(key for key, _, _ in REQUIRED_SCOPES),
        "event_name": "im.message.receive_v1",
    }


def _credential_diagnosis(payload: dict[str, Any]) -> AppOnboardingError:
    code = _feishu_error_code(payload)
    if code in (10003, 10014, 99991663, 99991668):
        return AppOnboardingError(
            "FEISHU_APP_CREDENTIALS_INVALID",
            "App ID 或 App Secret 不正确。",
            detail="请到飞书开放平台「凭证与基础信息」复制最新的 App Secret；Secret 只显示一次，重装应用会重置。",
            link=f"{OPEN_PLATFORM}/app")
    if code in (10012, 10013, 10015):
        return AppOnboardingError(
            "FEISHU_APP_NOT_FOUND",
            "飞书没有找到这个应用，请确认 App ID 复制完整且属于你的企业。",
            link=f"{OPEN_PLATFORM}/app")
    return AppOnboardingError(
        "FEISHU_APP_CREDENTIALS_REJECTED",
        "飞书拒绝了这个应用凭证，请确认 App ID 与 App Secret 属于同一个应用。",
        detail=f"飞书错误码：{code}" if code is not None else "",
        link=f"{OPEN_PLATFORM}/app")


def verify_app_credentials(app_id: str, app_secret: str) -> dict[str, Any]:
    """Ask Feishu whether these credentials work; never echoes the secret."""
    token_payload = _request(
        "POST", "/auth/v3/tenant_access_token/internal",
        body={"app_id": app_id, "app_secret": app_secret})
    if _feishu_error_code(token_payload) != 0:
        raise _credential_diagnosis(token_payload)
    token = str(token_payload.get("tenant_access_token") or "")
    if not token:
        raise AppOnboardingError(
            "FEISHU_APP_CREDENTIALS_REJECTED",
            "飞书没有返回访问令牌，请确认应用已启用且 App Secret 正确。",
            link=f"{OPEN_PLATFORM}/app")

    result: dict[str, Any] = {
        "app_id": app_id, "app_name": "", "bot_name": "", "bot_enabled": False,
        "scopes_checked": False, "missing_scopes": [], "optional_scopes": [],
        "tenant_name": "", "warnings": [], "diagnoses": [],
    }

    # Bot capability: without an enabled bot the user cannot chat with FundLex.
    bot_payload = _request("GET", "/bot/v3/info", token=token)
    if _feishu_error_code(bot_payload) == 0:
        bot = bot_payload.get("bot") if isinstance(bot_payload.get("bot"), dict) else {}
        result["bot_name"] = str(bot.get("app_name") or "")[:128]
        # Feishu reports 2 for an enabled, published bot (verified against the
        # production app); 0/1 mean it has not been enabled/published yet.
        result["bot_enabled"] = int(bot.get("activate_status") or 0) == 2

    # App metadata + granted scopes. This needs the app-self-manage scope; when
    # the user's app does not grant it we keep going and let the real message
    # test prove connectivity instead of blocking onboarding.
    # Optional reads must not fail onboarding: a transient error or a missing
    # self-manage scope only means we cannot auto-check, not that the user's
    # credentials are wrong.
    try:
        app_payload = _request("GET", f"/application/v6/applications/{app_id}?lang=zh_cn", token=token)
    except AppOnboardingError:
        app_payload = {"code": -1}
    if _feishu_error_code(app_payload) == 0:
        app = app_payload.get("data", {}).get("app") if isinstance(app_payload.get("data"), dict) else {}
        app = app if isinstance(app, dict) else {}
        result["app_name"] = str(app.get("app_name") or "")[:128]
        scopes = {str(item.get("scope")) for item in app.get("scopes") or []
                  if isinstance(item, dict)}
        result["scopes_checked"] = True
        result["missing_scopes"] = [key for key, _, _ in REQUIRED_SCOPES if key not in scopes]
        result["optional_scopes"] = [key for key, _, _ in OPTIONAL_SCOPES if key not in scopes]
    else:
        violations = _scope_violations(app_payload)
        if APP_INFO_SCOPE not in violations:
            result["warnings"].append("scope_check_unavailable")

    # Tenant name is cosmetic; it also needs a scope, so a failure is ignored.
    try:
        tenant_payload = _request("GET", "/tenant/v2/tenant/query", token=token)
    except AppOnboardingError:
        tenant_payload = {"code": -1}
    if _feishu_error_code(tenant_payload) == 0:
        tenant = (tenant_payload.get("data") or {}).get("tenant") if isinstance(tenant_payload.get("data"), dict) else {}
        if isinstance(tenant, dict):
            result["tenant_name"] = str(tenant.get("name") or "")[:128]

    if result["missing_scopes"]:
        result["diagnoses"].append({
            "code": "FEISHU_APP_SCOPE_MISSING",
            "message": "应用还缺少必需权限：" + "、".join(result["missing_scopes"]),
            "link": _permission_link(app_id),
        })
    if not result["bot_enabled"]:
        result["diagnoses"].append({
            "code": "FEISHU_APP_BOT_DISABLED",
            "message": "机器人能力还未启用或版本未发布。",
            "link": _bot_link(app_id),
        })
    return result


def _now() -> float:
    return time.time()


class FeishuAppOnboarding:
    """Durable per-user own-tenant app credentials and onboarding state."""

    def __init__(self, store):
        self.store = store
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS feishu_apps (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL,
                    app_id TEXT NOT NULL UNIQUE, secret_cipher MEDIUMTEXT NOT NULL,
                    app_name TEXT NOT NULL DEFAULT '', bot_name TEXT NOT NULL DEFAULT '',
                    bot_enabled INTEGER NOT NULL DEFAULT 0,
                    tenant_key TEXT NOT NULL DEFAULT '', tenant_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'ready',
                    scopes_checked INTEGER NOT NULL DEFAULT 0,
                    missing_scopes_json MEDIUMTEXT NOT NULL DEFAULT '[]',
                    last_error_code TEXT NOT NULL DEFAULT '',
                    last_error_json MEDIUMTEXT NOT NULL DEFAULT '',
                    last_verified_at REAL,
                    runtime_connected INTEGER NOT NULL DEFAULT 0,
                    runtime_heartbeat REAL NOT NULL DEFAULT 0,
                    first_event_at REAL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_feishu_apps_owner ON feishu_apps(owner);
            """)

    # -- read ---------------------------------------------------------
    def _row_for_owner(self, owner: str) -> dict[str, Any] | None:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM feishu_apps WHERE owner=? ORDER BY created_at DESC LIMIT 1",
                             (owner,)).fetchone()
        return dict(row) if row else None

    def _row_for_app(self, app_id: str) -> dict[str, Any] | None:
        with self.store._connect() as db:
            row = db.execute("SELECT * FROM feishu_apps WHERE app_id=?", (app_id,)).fetchone()
        return dict(row) if row else None

    def secret_for(self, app_id: str) -> str:
        row = self._row_for_app(app_id)
        if row is None:
            raise AppOnboardingError("FEISHU_APP_NOT_CONFIGURED", "应用不存在。", http_status=404)
        try:
            return _secret_cipher().decrypt(str(row["secret_cipher"]).encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, UnicodeError):
            raise AppOnboardingError(
                "FEISHU_APP_SECRET_UNREADABLE",
                "保存的应用凭证无法解密，请重新填写 App Secret。",
                detail="服务器加密密钥可能已更换。", http_status=409) from None

    def status(self, owner: str) -> dict[str, Any]:
        row = self._row_for_owner(owner)
        if row is None:
            return {"configured": False, "stage": STATUS_NO_APP, "warnings": [],
                    "checks": self._checklist(None), "guide": guide()}
        connected = bool(row["runtime_connected"]) and (
            _now() - float(row["runtime_heartbeat"] or 0) < HEARTBEAT_STALE_SECONDS)
        try:
            _secret_cipher().decrypt(str(row["secret_cipher"]).encode("ascii"))
            secret_readable = True
        except Exception:  # rotation, missing key or corrupt ciphertext
            secret_readable = False
        if row["status"] == STATUS_NEEDS_ATTENTION or not secret_readable:
            stage = STATUS_NEEDS_ATTENTION
        elif row["first_event_at"]:
            stage = STATUS_ACTIVE
        elif not connected:
            stage = STATUS_READY
        else:
            stage = STATUS_WAITING_MESSAGE
        return {
            "configured": True,
            "stage": stage,
            "app_id": row["app_id"],
            "app_name": row["app_name"],
            "bot_name": row["bot_name"],
            "bot_enabled": bool(row["bot_enabled"]),
            "tenant_name": row["tenant_name"],
            "scopes_checked": bool(row["scopes_checked"]),
            "missing_scopes": json.loads(row["missing_scopes_json"] or "[]"),
            "runtime_connected": connected,
            "first_event_at": row["first_event_at"],
            "verified_at": row["last_verified_at"],
            "created_at": row["created_at"],
            "error": ({"code": "FEISHU_APP_SECRET_UNREADABLE",
                       "message": "保存的应用凭证无法解密，请重新填写 App Secret。",
                       "detail": "服务器加密密钥可能已更换。",
                       "link": guide(row["app_id"])["create_app"]}
                      if not secret_readable else
                      (json.loads(row["last_error_json"] or "{}") if row["last_error_json"] else None)),
            "warnings": [] if row["scopes_checked"] else ["scope_check_unavailable"],
            "checks": self._checklist(row),
            "guide": guide(row["app_id"]),
        }

    def _checklist(self, row: dict[str, Any] | None) -> list[dict[str, Any]]:
        if row is None:
            return [{"key": key, "label": label, "why": why, "ok": False}
                    for key, label, why in REQUIRED_SCOPES]
        checks: list[dict[str, Any]] = []
        if row["scopes_checked"]:
            missing = set(json.loads(row["missing_scopes_json"] or "[]"))
            for key, label, why in REQUIRED_SCOPES:
                checks.append({"key": key, "label": label, "why": why, "ok": key not in missing})
        else:
            # Without the app-self-manage scope we cannot read the granted list.
            # Report "unknown" instead of guessing "granted": a green checklist
            # would tell the user their permissions are fine when nobody checked.
            for key, label, why in REQUIRED_SCOPES:
                checks.append({"key": key, "label": label, "why": why, "ok": None})
        checks.append({"key": "bot", "label": "机器人能力已启用", "why": "没有机器人，飞书里找不到 FundLex",
                       "ok": bool(row["bot_enabled"])})
        checks.append({"key": "runtime", "label": "长连接已建立",
                       "why": "长连接断开时收不到消息", "ok": bool(row["runtime_connected"])})
        checks.append({"key": "message", "label": "已收到你的测试消息",
                       "why": "证明事件订阅、发布和机器人都已生效",
                       "ok": bool(row["first_event_at"])})
        return checks

    def apps_for_runtime(self) -> list[dict[str, Any]]:
        with self.store._connect() as db:
            rows = db.execute("SELECT app_id,tenant_key FROM feishu_apps WHERE status<>'removed'").fetchall()
        return [dict(row) for row in rows]

    # -- write --------------------------------------------------------
    def save(self, owner: str, app_id: str, app_secret: str) -> dict[str, Any]:
        app_id = (app_id or "").strip()
        app_secret = (app_secret or "").strip()
        if not APP_ID_RE.match(app_id):
            raise AppOnboardingError(
                "FEISHU_APP_ID_INVALID",
                "App ID 格式不对，应以 cli_ 开头。",
                detail="请从开放平台「凭证与基础信息」整段复制。", link=f"{OPEN_PLATFORM}/app")
        if not (SECRET_MIN <= len(app_secret) <= SECRET_MAX) or any(ch.isspace() for ch in app_secret):
            raise AppOnboardingError(
                "FEISHU_APP_SECRET_INVALID",
                "App Secret 格式不对，请整段复制（不要带空格）。",
                link=f"{OPEN_PLATFORM}/app")
        existing = self._row_for_owner(owner)
        conflict = self._row_for_app(app_id)
        if conflict and conflict["owner"] != owner:
            raise AppOnboardingError(
                "FEISHU_APP_ALREADY_ONBOARDED",
                "这个应用已被另一个 FundLex 账号接入。", http_status=409)

        verified = verify_app_credentials(app_id, app_secret)
        cipher = _secret_cipher().encrypt(app_secret.encode("utf-8")).decode("ascii")
        attention = bool(verified["missing_scopes"]) or not verified["bot_enabled"]
        error = None
        if verified["missing_scopes"]:
            error = {"code": "FEISHU_APP_SCOPE_MISSING",
                     "message": "还缺少必需权限：" + "、".join(verified["missing_scopes"]),
                     "link": _permission_link(app_id)}
        elif not verified["bot_enabled"]:
            error = {"code": "FEISHU_APP_BOT_DISABLED",
                     "message": "机器人能力还未启用或版本未发布。",
                     "link": _bot_link(app_id)}
        now = _now()
        # A different app means a different tenant: keep no routing/heartbeat
        # residue from the app it replaces, and let the first message prove it.
        replaced = bool(existing) and existing["app_id"] != app_id
        with self.store._connect() as db:
            if existing:
                db.execute("""UPDATE feishu_apps SET app_id=?,secret_cipher=?,app_name=?,bot_name=?,
                    bot_enabled=?,status=?,scopes_checked=?,missing_scopes_json=?,last_error_code=?,
                    last_error_json=?,last_verified_at=?,runtime_connected=0,runtime_heartbeat=0,
                    tenant_name=?,tenant_key=?,first_event_at=?,updated_at=? WHERE owner=?""",
                           (app_id, cipher, verified.get("app_name") or "",
                            verified.get("bot_name") or "", 1 if verified["bot_enabled"] else 0,
                            STATUS_NEEDS_ATTENTION if attention else STATUS_READY,
                            1 if verified["scopes_checked"] else 0,
                            json.dumps(verified["missing_scopes"]),
                            (error or {}).get("code", ""), json.dumps(error or {}),
                            now, verified.get("tenant_name") or "",
                            "" if replaced else existing["tenant_key"],
                            None if replaced else existing["first_event_at"],
                            now, owner))
            else:
                db.execute("""INSERT INTO feishu_apps(id,owner,app_id,secret_cipher,app_name,bot_name,
                    bot_enabled,tenant_name,status,scopes_checked,missing_scopes_json,last_error_code,
                    last_error_json,last_verified_at,created_at,updated_at)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                           (uuid.uuid4().hex, owner, app_id, cipher,
                            verified.get("app_name") or "", verified.get("bot_name") or "",
                            1 if verified["bot_enabled"] else 0, verified.get("tenant_name") or "",
                            STATUS_NEEDS_ATTENTION if attention else STATUS_READY,
                            1 if verified["scopes_checked"] else 0,
                            json.dumps(verified["missing_scopes"]),
                            (error or {}).get("code", ""), json.dumps(error or {}),
                            now, now, now))
        # Never return the verification's raw payload: it contains only public
        # metadata, but the response is assembled explicitly to keep that true.
        return {
            "app_id": app_id,
            "app_name": verified.get("app_name") or "",
            "bot_name": verified.get("bot_name") or "",
            "bot_enabled": verified["bot_enabled"],
            "tenant_name": verified.get("tenant_name") or "",
            "scopes_checked": verified["scopes_checked"],
            "missing_scopes": verified["missing_scopes"],
            "warnings": verified["warnings"],
            "stage": self.status(owner)["stage"],
        }

    def revalidate(self, owner: str) -> dict[str, Any]:
        row = self._row_for_owner(owner)
        if row is None:
            raise AppOnboardingError("FEISHU_APP_NOT_CONFIGURED", "还没有保存应用凭证。", http_status=404)
        return self.save(owner, row["app_id"], self.secret_for(row["app_id"]))

    def remove(self, owner: str) -> None:
        with self.store._connect() as db:
            db.execute("DELETE FROM feishu_apps WHERE owner=?", (owner,))

    def record_event(self, app_id: str, tenant_key: str) -> None:
        now = _now()
        with self.store._connect() as db:
            db.execute("""UPDATE feishu_apps SET first_event_at=COALESCE(first_event_at,?),
                tenant_key=CASE WHEN tenant_key='' THEN ? ELSE tenant_key END,
                status=?,runtime_connected=1,runtime_heartbeat=?,updated_at=? WHERE app_id=?""",
                       (now, tenant_key, STATUS_ACTIVE, now, now, app_id))

    def mark_runtime(self, app_id: str, connected: bool, *, tenant_key: str = "") -> None:
        now = _now()
        with self.store._connect() as db:
            if tenant_key:
                db.execute("""UPDATE feishu_apps SET runtime_connected=?,runtime_heartbeat=?,
                    tenant_key=CASE WHEN tenant_key='' THEN ? ELSE tenant_key END,updated_at=?
                    WHERE app_id=?""", (1 if connected else 0, now, tenant_key, now, app_id))
            else:
                db.execute("""UPDATE feishu_apps SET runtime_connected=?,runtime_heartbeat=?,updated_at=?
                    WHERE app_id=?""", (1 if connected else 0, now, now, app_id))
