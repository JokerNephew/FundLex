"""Feishu OAuth helpers for one-scan account binding.

The browser is redirected to Feishu's authorization page with a short-lived,
one-time ``state`` value.  Only the state hash is persisted; the callback
exchanges the authorization code for a user access token, reads the Feishu
identity, and binds it to the FundLex user that created the state.

No token, app secret, or authorization code is logged by this module.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"
TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"
OAUTH_SCOPE = "contact:user.base:readonly"


class FeishuOAuthError(RuntimeError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class FeishuOAuthIdentity:
    open_id: str
    tenant_key: str
    name: str = ""


def _json_request(url: str, *, data: dict[str, Any] | None = None,
                  headers: dict[str, str] | None = None, timeout: float = 15.0) -> dict[str, Any]:
    body = None if data is None else json.dumps(data, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST" if data is not None else "GET")
    request.add_header("Accept", "application/json")
    if data is not None:
        request.add_header("Content-Type", "application/json; charset=utf-8")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise FeishuOAuthError("FEISHU_OAUTH_HTTP_ERROR") from exc
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise FeishuOAuthError("FEISHU_OAUTH_UNAVAILABLE") from exc
    if not isinstance(payload, dict):
        raise FeishuOAuthError("FEISHU_OAUTH_INVALID_RESPONSE")
    code = payload.get("code")
    if code not in (None, 0, "0"):
        raise FeishuOAuthError("FEISHU_OAUTH_REJECTED", str(payload.get("msg") or "")[:200])
    return payload


class FeishuOAuthClient:
    def __init__(self, app_id: str, app_secret: str, redirect_uri: str):
        if not app_id.strip() or not app_secret.strip() or not redirect_uri.strip():
            raise FeishuOAuthError("FEISHU_OAUTH_NOT_CONFIGURED")
        self.app_id = app_id.strip()
        self._app_secret = app_secret.strip()
        self.redirect_uri = redirect_uri.strip()

    @classmethod
    def from_env(cls) -> "FeishuOAuthClient":
        base = os.environ.get("FUNDLEX_PUBLIC_BASE_URL", "").rstrip("/")
        return cls(os.environ.get("FUNDLEX_FEISHU_APP_ID", ""),
                   os.environ.get("FUNDLEX_FEISHU_APP_SECRET", ""),
                   f"{base}/api/integrations/feishu/oauth/callback" if base else "")

    def authorization_url(self, state: str) -> str:
        query = urllib.parse.urlencode({
            "app_id": self.app_id,
            "redirect_uri": self.redirect_uri,
            "state": state,
            "scope": OAUTH_SCOPE,
        })
        return f"{AUTHORIZE_URL}?{query}"

    def exchange_identity(self, code: str) -> FeishuOAuthIdentity:
        if not code or len(code) > 4096:
            raise FeishuOAuthError("FEISHU_OAUTH_CODE_INVALID")
        payload = _json_request(TOKEN_URL, data={
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self._app_secret,
            "code": code,
            "redirect_uri": self.redirect_uri,
        })
        data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
        token = str(data.get("access_token") or "")
        if not token:
            raise FeishuOAuthError("FEISHU_OAUTH_TOKEN_MISSING")
        info = _json_request(USER_INFO_URL, headers={"Authorization": f"Bearer {token}"})
        identity = info.get("data") if isinstance(info.get("data"), dict) else info
        open_id = str(identity.get("open_id") or "")
        tenant_key = str(identity.get("tenant_key") or "")
        if not open_id or not tenant_key:
            raise FeishuOAuthError("FEISHU_OAUTH_IDENTITY_MISSING")
        return FeishuOAuthIdentity(open_id=open_id, tenant_key=tenant_key,
                                   name=str(identity.get("name") or "")[:128])

    @staticmethod
    def qr_svg(value: str) -> str | None:
        """Render a QR SVG with the deployment's qrencode binary.

        The frontend still receives the authorization URL when the binary is
        unavailable, so QR rendering is a presentation concern rather than a
        binding prerequisite.
        """
        try:
            binary = shutil.which("qrencode") or "/usr/bin/qrencode"
            result = subprocess.run(
                [binary, "-t", "SVG", "-o", "-", value],
                capture_output=True, timeout=5, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        svg = result.stdout.decode("utf-8", errors="replace")
        if "<svg" not in svg or len(svg) > 300_000:
            return None
        return svg


def oauth_available() -> bool:
    return bool(os.environ.get("FUNDLEX_FEISHU_APP_ID")
                and os.environ.get("FUNDLEX_FEISHU_APP_SECRET")
                and os.environ.get("FUNDLEX_PUBLIC_BASE_URL"))
