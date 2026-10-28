"""OAuth QR binding API checks with a fake Feishu exchange."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.integrations.feishu.oauth import FeishuOAuthIdentity


class FakeOAuthClient:
    def __init__(self):
        self.state = ""

    @classmethod
    def from_env(cls):
        return cls()

    def authorization_url(self, state):
        self.state = state
        return f"https://feishu.example/authorize?state={state}"

    @staticmethod
    def qr_svg(value):
        return "<svg data-test='qr'></svg>"

    @staticmethod
    def qr_png(value):
        return "data:image/png;base64,iVBORw0KGgo="

    def exchange_identity(self, code):
        if code != "valid-code":
            from fundlex.integrations.feishu.oauth import FeishuOAuthError
            raise FeishuOAuthError("FEISHU_OAUTH_REJECTED")
        return FeishuOAuthIdentity(open_id="ou-oauth", tenant_key="tenant-oauth", name="测试用户")


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    monkeypatch.setenv("FUNDLEX_FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FUNDLEX_FEISHU_APP_SECRET", "test-secret")
    monkeypatch.setenv("FUNDLEX_PUBLIC_BASE_URL", "https://fundlex.example")
    application = create_app(tmp_path / "data", auth_db=tmp_path / "auth.sqlite3")
    application.state.users.create_user("oauth-member", "password-123", "OAuth 用户", "member")
    return application


def _login(client):
    response = client.post("/api/auth/login", json={"username": "oauth-member", "password": "password-123"})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["token"]}


def test_oauth_start_and_callback_bind_current_account(tmp_path, monkeypatch):
    application = _app(tmp_path, monkeypatch)
    monkeypatch.setattr("fundlex.api.FeishuOAuthClient", FakeOAuthClient)
    client = TestClient(application)
    headers = _login(client)
    assert client.post("/api/integrations/feishu/oauth/start").status_code == 401
    started = client.post("/api/integrations/feishu/oauth/start", headers=headers)
    assert started.status_code == 200
    payload = started.json()
    assert payload["qr_svg"] == "<svg data-test='qr'></svg>"
    assert payload["qr_png"].startswith("data:image/png;base64,")
    state = re.search(r"state=([^&]+)", payload["authorization_url"]).group(1)

    callback = client.get("/api/integrations/feishu/oauth/callback", params={"code": "valid-code", "state": state})
    assert callback.status_code == 200
    assert "绑定成功" in callback.text
    binding = client.get("/api/integrations/feishu/binding", headers=headers)
    assert binding.json()["bound"] is True

    replay = client.get("/api/integrations/feishu/oauth/callback", params={"code": "valid-code", "state": state})
    assert "绑定链接无效" in replay.text
    assert client.get("/api/integrations/feishu/oauth/callback", params={"code": "bad", "state": "bad"}).status_code == 200


def test_oauth_callback_rejects_invalid_exchange_and_denied(tmp_path, monkeypatch):
    application = _app(tmp_path, monkeypatch)
    monkeypatch.setattr("fundlex.api.FeishuOAuthClient", FakeOAuthClient)
    client = TestClient(application)
    headers = _login(client)
    payload = client.post("/api/integrations/feishu/oauth/start", headers=headers).json()
    state = re.search(r"state=([^&]+)", payload["authorization_url"]).group(1)
    rejected = client.get("/api/integrations/feishu/oauth/callback", params={"code": "bad", "state": state})
    assert "飞书授权未完成" in rejected.text
    denied = client.get("/api/integrations/feishu/oauth/callback", params={"error": "access_denied", "state": state})
    assert "未完成绑定" in denied.text


def test_denied_oauth_state_is_consumed(tmp_path, monkeypatch):
    application = _app(tmp_path, monkeypatch)
    monkeypatch.setattr("fundlex.api.FeishuOAuthClient", FakeOAuthClient)
    client = TestClient(application)
    headers = _login(client)
    payload = client.post("/api/integrations/feishu/oauth/start", headers=headers).json()
    state = re.search(r"state=([^&]+)", payload["authorization_url"]).group(1)

    denied = client.get("/api/integrations/feishu/oauth/callback",
                        params={"error": "access_denied", "state": state})
    assert denied.status_code == 200 and "未完成绑定" in denied.text
    replay = client.get("/api/integrations/feishu/oauth/callback",
                        params={"code": "valid-code", "state": state})
    assert "绑定链接无效" in replay.text
