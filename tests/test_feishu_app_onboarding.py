"""Own-tenant Feishu app onboarding: encryption, diagnostics, state machine, API.

Covers the cross-tenant path: a user whose Feishu account is in another tenant
creates a self-built app, pastes its credentials, and FundLex verifies them
against the real Feishu OpenAPI contract (faked here, no network).
"""
from __future__ import annotations

import logging
import time

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.integrations.feishu import onboarding
from fundlex.integrations.feishu.onboarding import (
    AppOnboardingError,
    FeishuAppOnboarding,
    guide,
)
from fundlex.store import RunStore


SECRET = "s3cr3t-value-do-not-leak-0001"


@pytest.fixture()
def store(tmp_path):
    return RunStore(tmp_path / "data")


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("FUNDLEX_MODEL_SECRETS_KEY", Fernet.generate_key().decode("ascii"))


def _ok_token(*_a, **_k):
    return {"code": 0, "tenant_access_token": "t-fake", "expire": 7200}


def _bot(active=2, name="FundLex"):
    return {"code": 0, "bot": {"activate_status": active, "app_name": name}}


def _app(scopes=None, name="我的 FundLex"):
    keys = [s[0] for s in onboarding.REQUIRED_SCOPES] if scopes is None else list(scopes)
    return {"code": 0, "data": {"app": {"app_name": name,
                                        "scopes": [{"scope": s} for s in keys]}}}


def _tenant(name="示例企业"):
    return {"code": 0, "data": {"tenant": {"name": name}}}


def _fake(monkeypatch, *, token=None, bot=None, app=None, tenant=None):
    """Route _request by path so each Feishu API answer is controlled."""
    calls: list[str] = []
    answers = {
        "token": token or _ok_token,
        "bot": bot or _bot,
        "app": app or _app,
        "tenant": tenant or _tenant,
    }

    def fake_request(method, path, *, body=None, token="", timeout=20.0):
        calls.append(path)
        if "tenant_access_token" in path:
            return answers["token"]()
        if "/bot/v3/info" in path:
            return answers["bot"]()
        if "/application/v6/applications/" in path:
            return answers["app"]()
        if "/tenant/v2/tenant/query" in path:
            return answers["tenant"]()
        raise AssertionError(f"unexpected path {path}")

    monkeypatch.setattr(onboarding, "_request", fake_request)
    return calls


# -- encryption / storage ---------------------------------------------------

def test_secret_is_encrypted_and_never_returned(store, monkeypatch, caplog):
    _fake(monkeypatch)
    caplog.set_level(logging.DEBUG)
    board = FeishuAppOnboarding(store)
    saved = board.save("user-a", "cli_abcdefgh12345", SECRET)
    assert SECRET not in str(saved)

    with store._connect() as db:
        row = db.execute("SELECT secret_cipher FROM feishu_apps WHERE owner='user-a'").fetchone()
    cipher = row["secret_cipher"]
    assert SECRET not in cipher
    assert cipher.startswith("gAAAAA")  # Fernet token

    status = board.status("user-a")
    assert SECRET not in str(status)
    assert "secret" not in {key.lower() for key in status}
    assert SECRET not in caplog.text
    # The secret still round-trips for the runtime.
    assert board.secret_for("cli_abcdefgh12345") == SECRET


def test_state_without_app_is_no_app_and_carries_guide(store):
    board = FeishuAppOnboarding(store)
    status = board.status("user-a")
    assert status["configured"] is False
    assert status["stage"] == "no_app"
    assert status["guide"]["event_name"] == "im.message.receive_v1"
    assert status["guide"]["scopes_text"].splitlines() == [s[0] for s in onboarding.REQUIRED_SCOPES]
    assert status["guide"]["create_app"].startswith("https://open.feishu.cn/")


# -- credential diagnostics -------------------------------------------------

@pytest.mark.parametrize("app_id,code", [
    ("bad-id", "FEISHU_APP_ID_INVALID"),
    ("cli_abcdefgh12345", "FEISHU_APP_SECRET_INVALID"),
])
def test_local_format_validation_saves_nothing(store, app_id, code):
    board = FeishuAppOnboarding(store)
    with pytest.raises(AppOnboardingError) as info:
        board.save("user-a", app_id, "short")
    assert info.value.code == code
    assert board.status("user-a")["configured"] is False


def test_wrong_secret_maps_to_actionable_error_and_saves_nothing(store, monkeypatch):
    _fake(monkeypatch, token=lambda: {"code": 10014, "msg": "invalid param"})
    board = FeishuAppOnboarding(store)
    with pytest.raises(AppOnboardingError) as info:
        board.save("user-a", "cli_abcdefgh12345", SECRET)
    assert info.value.code == "FEISHU_APP_CREDENTIALS_INVALID"
    assert info.value.link.startswith("https://open.feishu.cn/app")
    assert board.status("user-a")["configured"] is False


def test_network_failure_is_502_not_a_saved_app(store, monkeypatch):
    def boom(*_a, **_k):
        raise AppOnboardingError("FEISHU_APP_VERIFY_UNAVAILABLE", "暂时连不上", http_status=502)

    monkeypatch.setattr(onboarding, "_request", boom)
    board = FeishuAppOnboarding(store)
    with pytest.raises(AppOnboardingError) as info:
        board.save("user-a", "cli_abcdefgh12345", SECRET)
    assert info.value.http_status == 502
    assert board.status("user-a")["configured"] is False


# -- verification + state machine ------------------------------------------

def test_missing_scope_and_bot_disabled_become_needs_attention(store, monkeypatch):
    _fake(monkeypatch,
          bot=lambda: _bot(active=0),
          app=lambda: _app(scopes=["im:message:send_as_bot"]))
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)

    status = board.status("user-a")
    assert status["stage"] == "needs_attention"
    assert status["missing_scopes"] == ["im:message.p2p_msg:readonly", "im:resource"]
    assert status["error"]["code"] == "FEISHU_APP_SCOPE_MISSING"
    checks = {c["key"]: c["ok"] for c in status["checks"]}
    assert checks["im:message:send_as_bot"] is True
    assert checks["im:resource"] is False
    assert checks["bot"] is False
    assert checks["message"] is False


def test_scope_check_unavailable_degrades_without_blocking(store, monkeypatch):
    denied = {"code": 99991672,
              "msg": "Access denied",
              "error": {"permission_violations": [
                  {"type": "action_scope_required",
                   "subject": "application:application:self_manage"}]}}
    _fake(monkeypatch, app=lambda: denied)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    status = board.status("user-a")
    assert status["scopes_checked"] is False
    assert status["missing_scopes"] == []
    assert status["stage"] == "ready"
    assert status["warnings"] == ["scope_check_unavailable"]
    # Unverified must never render as granted.
    assert {c["ok"] for c in status["checks"] if c["key"].startswith("im:")} == {None}


def test_optional_read_failure_does_not_block_onboarding(store, monkeypatch):
    """A blip on the scope/tenant lookups must not reject valid credentials."""
    answers = {"token": _ok_token, "bot": _bot}

    def fake_request(method, path, *, body=None, token="", timeout=20.0):
        if "tenant_access_token" in path:
            return answers["token"]()
        if "/bot/v3/info" in path:
            return answers["bot"]()
        raise AppOnboardingError("FEISHU_APP_VERIFY_UNAVAILABLE", "network", http_status=502)

    monkeypatch.setattr(onboarding, "_request", fake_request)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    status = board.status("user-a")
    assert status["stage"] == "ready"
    assert status["scopes_checked"] is False
    assert status["warnings"] == ["scope_check_unavailable"]


def test_stage_progresses_from_ready_to_waiting_to_active(store, monkeypatch):
    _fake(monkeypatch)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    assert board.status("user-a")["stage"] == "ready"

    board.mark_runtime("cli_abcdefgh12345", True, tenant_key="tenant-ext")
    status = board.status("user-a")
    assert status["stage"] == "waiting_message"
    assert status["runtime_connected"] is True
    assert [r["tenant_key"] for r in board.apps_for_runtime()] == ["tenant-ext"]

    board.record_event("cli_abcdefgh12345", "tenant-ext")
    status = board.status("user-a")
    assert status["stage"] == "active"
    assert status["first_event_at"]


def test_stale_heartbeat_is_reported_disconnected(store, monkeypatch):
    _fake(monkeypatch)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    board.mark_runtime("cli_abcdefgh12345", True)
    with store._connect() as db:
        db.execute("UPDATE feishu_apps SET runtime_heartbeat=? WHERE app_id=?",
                   (time.time() - onboarding.HEARTBEAT_STALE_SECONDS - 5, "cli_abcdefgh12345"))
    status = board.status("user-a")
    assert status["runtime_connected"] is False
    assert status["stage"] == "ready"


def test_same_app_cannot_be_claimed_by_two_accounts(store, monkeypatch):
    _fake(monkeypatch)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    with pytest.raises(AppOnboardingError) as info:
        board.save("user-b", "cli_abcdefgh12345", SECRET)
    assert info.value.code == "FEISHU_APP_ALREADY_ONBOARDED"
    assert info.value.http_status == 409


def test_switching_apps_clears_previous_tenant_state(store, monkeypatch):
    """Replacing an app must not keep routing or first-event state of the old one."""
    _fake(monkeypatch)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    board.mark_runtime("cli_abcdefgh12345", True, tenant_key="tenant-old")
    board.record_event("cli_abcdefgh12345", "tenant-old")
    assert board.status("user-a")["stage"] == "active"

    board.save("user-a", "cli_zzzzzzzz99999", SECRET)
    status = board.status("user-a")
    assert status["app_id"] == "cli_zzzzzzzz99999"
    assert status["stage"] == "ready"
    assert status["first_event_at"] is None
    assert board.apps_for_runtime()[0]["tenant_key"] == ""

    # Re-saving the same app keeps its history, so a revalidation is not a reset.
    board.record_event("cli_zzzzzzzz99999", "tenant-new")
    board.save("user-a", "cli_zzzzzzzz99999", SECRET)
    assert board.status("user-a")["stage"] == "active"


def test_unreadable_cipher_is_reported_not_crashed(store, monkeypatch):
    _fake(monkeypatch)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    with store._connect() as db:
        db.execute("UPDATE feishu_apps SET secret_cipher='not-a-token' WHERE owner='user-a'")
    with pytest.raises(AppOnboardingError) as info:
        board.secret_for("cli_abcdefgh12345")
    assert info.value.code == "FEISHU_APP_SECRET_UNREADABLE"
    # The status page must not keep claiming everything is fine either.
    status = board.status("user-a")
    assert status["stage"] == "needs_attention"
    assert status["error"]["code"] == "FEISHU_APP_SECRET_UNREADABLE"


# -- tenant routing ---------------------------------------------------------

def test_service_routes_by_tenant_and_falls_back_to_deployment_bot(store):
    from fundlex.integrations.feishu.service import FeishuService

    class Client:
        def __init__(self, name):
            self.name = name

    class Tasks:
        pass

    deployment = Client("deployment")
    other = Client("other")
    service = FeishuService(store, Tasks(), Tasks(), deployment,
                            app_clients=lambda tenant: other if tenant == "tenant-ext" else None)
    assert service._client("tenant-ext") is other
    assert service._client("tenant-home") is deployment
    assert service._client("") is deployment
    assert FeishuService(store, Tasks(), Tasks(), deployment)._client("tenant-ext") is deployment

    def broken(_tenant):
        raise RuntimeError("resolver down")

    service.set_app_clients(broken)
    assert service._client("tenant-ext") is deployment


def test_runtime_client_lookup_and_accounting(store, monkeypatch):
    from fundlex.integrations.feishu.runtime import FeishuAppRuntime

    _fake(monkeypatch)
    board = FeishuAppOnboarding(store)
    board.save("user-a", "cli_abcdefgh12345", SECRET)
    runtime = FeishuAppRuntime(board, service=None)
    sentinel = object()
    runtime._apps["cli_abcdefgh12345"] = {"client": sentinel, "tenant_key": "tenant-ext", "thread": None}
    assert runtime.client_for("tenant-ext") is sentinel
    assert runtime.client_for("tenant-home") is None
    assert runtime.connected_tenants() == ["tenant-ext"]

    # The event hook records the first real message and learns the tenant.
    runtime._seen("cli_abcdefgh12345", {"header": {"event_id": "ev_1", "tenant_key": "tenant-ext"},
                                       "event": {"message": {"message_id": "om_1",
                                                             "chat_id": "oc_1",
                                                             "chat_type": "p2p",
                                                             "message_type": "text",
                                                             "content": "{\"text\":\"你好\"}"},
                                                 "sender": {"sender_id": {"open_id": "ou_1"}}}})
    assert board.status("user-a")["stage"] == "active"


# -- guide ------------------------------------------------------------------

def test_guide_links_target_app_pages_and_scope_copy_is_plain():
    info = guide("cli_abcdefgh12345")
    for key in ("permission", "bot", "event", "version"):
        assert "cli_abcdefgh12345" in info[key]
        assert info[key].startswith("https://open.feishu.cn/app/cli_abcdefgh12345/")
    assert guide("")["bot"].startswith("https://open.feishu.cn/")
    assert info["scopes_text"] == "im:message:send_as_bot\nim:message.p2p_msg:readonly\nim:resource"


# -- API --------------------------------------------------------------------

def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    monkeypatch.setenv("FUNDLEX_FEISHU_APP_ID", "cli_test")
    monkeypatch.setenv("FUNDLEX_FEISHU_APP_SECRET", "test-secret")
    monkeypatch.setenv("FUNDLEX_PUBLIC_BASE_URL", "https://fundlex.example")
    application = create_app(tmp_path / "api-data", auth_db=tmp_path / "auth.sqlite3")
    application.state.users.create_user("member-a", "password-123", "成员 A", "member")
    client = TestClient(application)
    token = client.post("/api/auth/login",
                        json={"username": "member-a", "password": "password-123"}).json()["token"]
    return client, {"Authorization": "Bearer " + token}


def test_api_requires_login_before_disclosing_state(tmp_path, monkeypatch):
    client, _headers = _client(tmp_path, monkeypatch)
    assert client.get("/api/integrations/feishu/app").status_code == 401
    assert client.post("/api/integrations/feishu/app/credentials",
                       json={"app_id": "cli_abcdefgh12345", "app_secret": SECRET}).status_code == 401


def test_api_saves_verifies_and_deletes_without_echoing_secret(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    _fake(monkeypatch)

    initial = client.get("/api/integrations/feishu/app", headers=headers).json()
    assert initial["stage"] == "no_app"
    assert initial["binding"]["bound"] is False

    saved = client.post("/api/integrations/feishu/app/credentials", headers=headers,
                        json={"app_id": "cli_abcdefgh12345", "app_secret": SECRET})
    assert saved.status_code == 200
    payload = saved.json()
    assert SECRET not in saved.text
    assert payload["configured"] is True
    assert payload["stage"] == "ready"
    assert payload["verification"]["bot_name"] == "FundLex"
    assert payload["app_id"] == "cli_abcdefgh12345"

    revalidated = client.post("/api/integrations/feishu/app/verify", headers=headers)
    assert revalidated.status_code == 200
    assert SECRET not in revalidated.text

    removed = client.delete("/api/integrations/feishu/app", headers=headers)
    assert removed.status_code == 200
    assert removed.json()["stage"] == "no_app"


def test_api_reports_credential_error_with_stable_code(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    _fake(monkeypatch, token=lambda: {"code": 10014, "msg": "invalid param"})
    response = client.post("/api/integrations/feishu/app/credentials", headers=headers,
                           json={"app_id": "cli_abcdefgh12345", "app_secret": SECRET})
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "FEISHU_APP_CREDENTIALS_INVALID"
    assert body["message"].startswith("App ID 或 App Secret")
    assert body["detail"]
    assert body["link"].startswith("https://open.feishu.cn/app")
    assert body["correlation_id"]
    assert SECRET not in response.text


def test_api_reports_missing_secret_key_as_503(tmp_path, monkeypatch):
    client, headers = _client(tmp_path, monkeypatch)
    _fake(monkeypatch)
    monkeypatch.delenv("FUNDLEX_MODEL_SECRETS_KEY", raising=False)
    response = client.post("/api/integrations/feishu/app/credentials", headers=headers,
                           json={"app_id": "cli_abcdefgh12345", "app_secret": SECRET})
    assert response.status_code == 503
    assert response.json()["error_code"] == "FEISHU_APP_SECRET_STORAGE_UNAVAILABLE"
    assert client.get("/api/integrations/feishu/app", headers=headers).status_code == 200


# -- cross-tenant delivery ------------------------------------------------

def test_external_tenant_binding_replies_through_its_own_app(store):
    """A message in another tenant must be answered by that tenant's app.

    This is the payoff of onboarding: the user's own bot receives the binding
    code and the confirmation is sent back through the same app, never through
    the deployment bot (which cannot reach that tenant).
    """
    from fundlex.integrations.feishu.service import FeishuService
    from fundlex.integrations.store import IntegrationStore

    class Client:
        def __init__(self):
            self.cards = []

        def send_card(self, chat_id, card):
            self.cards.append(card)
            return "om-card"

        def update_card(self, message_id, card):
            self.cards.append(card)

        def pin_message(self, message_id):
            pass

        def unpin_message(self, message_id):
            pass

    deployment, external = Client(), Client()
    integrations = IntegrationStore(store)
    code = integrations.create_binding_code("feishu", "owner-a")["code"]
    service = FeishuService(store, object(), object(), deployment,
                            app_clients=lambda tenant: external if tenant == "tenant-ext" else None)
    service.install()
    service.handle_message_event({
        "header": {"event_id": "ev-ext-1", "event_type": "im.message.receive_v1",
                   "tenant_key": "tenant-ext"},
        "event": {"sender": {"sender_id": {"open_id": "ou-ext"}},
                  "message": {"message_id": "om-ext-1", "chat_id": "oc-ext",
                              "chat_type": "p2p", "message_type": "text",
                              "content": {"text": f"绑定 {code}"}}},
    })
    assert integrations.identity("feishu", "tenant-ext", "ou-ext")["user_id"] == "owner-a"
    titles = [card["header"]["title"]["content"] for card in external.cards]
    assert "绑定成功" in titles
    assert deployment.cards == []


# -- production schema compatibility --------------------------------------

def test_schema_translates_to_valid_mysql_ddl():
    """Production runs MySQL; the SQLite-flavoured DDL must survive translation.

    ``TEXT`` becomes ``VARCHAR(255)`` there, which would silently truncate the
    encrypted secret and the diagnostic JSON.  This guards both columns.
    """
    import inspect

    from fundlex.db import Database, _split_statements

    source = inspect.getsource(FeishuAppOnboarding.ensure_schema)
    script = source.split('executescript("""')[1].split('"""')[0]
    database = Database("mysql://user:pass@127.0.0.1:3307/example")
    statements = []
    for statement in _split_statements(script):
        action, payload = database.prepare(statement)
        if action == "create_index":
            statements.append(payload[2])
        elif payload:
            statements.append(payload)
    ddl = " ".join(" ".join(item.split()) for item in statements)
    assert "secret_cipher MEDIUMTEXT NOT NULL" in ddl
    assert "missing_scopes_json MEDIUMTEXT" in ddl
    assert "last_error_json MEDIUMTEXT" in ddl
    assert not any("TEXT DEFAULT" in part for part in ddl.split(","))
