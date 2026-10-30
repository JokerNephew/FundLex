"""Private model choices never modify deployment endpoints or credentials."""
import json

import pytest
from fastapi.testclient import TestClient

from fundlex import model_settings
from fundlex.store import RunStore


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    from fundlex.api import create_app
    return TestClient(create_app(tmp_path / "state"))


def test_private_settings_are_isolated_and_resettable(client):
    alice = {"X-FundLex-User": "alice"}
    bob = {"X-FundLex-User": "bob"}
    original = client.get("/api/settings/model", headers=bob).json()
    saved = client.put("/api/settings/model", headers=alice,
                       json={"primary": {"model": "private-model"}, "review": None})
    assert saved.status_code == 200, saved.text
    assert saved.json()["primary"]["model"] == "private-model"
    assert saved.json()["editable"] is True
    assert client.get("/api/settings/model", headers=bob).json() == original
    for key in ("api_key", "api_key_env", "base_url", "extra_headers"):
        assert key not in saved.json()["primary"]
    assert client.delete("/api/settings/model", headers=alice).status_code == 200
    assert client.get("/api/settings/model", headers=alice).json() == original


@pytest.mark.parametrize("field", ["base_url", "api_key_env", "api_key", "extra_headers", "provider"])
def test_no_user_can_redirect_service_or_choose_credentials(client, field):
    response = client.put("/api/settings/model", headers={"X-FundLex-User": "alice"},
                          json={"primary": {"model": "m", field: "forbidden"}})
    assert response.status_code == 422


def test_choices_only_override_safe_role_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "deployment-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "fixture-key")
    store = RunStore(tmp_path / "state")
    model_settings.save_settings(store, "alice", {"primary": {"model": "my-model"}})
    snap = model_settings.snapshot(store, "alice")
    configs, _ = model_settings.resolve(snap)
    assert configs["primary"].model == "my-model"
    assert configs["primary"].api_key == "fixture-key"
    assert configs["primary"].base_url == "https://example.invalid/v1"
    assert "fixture-key" not in json.dumps(snap)
    model_settings.reset_settings(store, "alice")
    assert model_settings.resolve(snap)[0]["primary"].model == "my-model"
    assert model_settings.snapshot(store, "alice") == {}


def test_invalid_snapshots_fail_closed():
    for value in ('{"primary":{"api_key":"x"}}', "null", "broken"):
        with pytest.raises(model_settings.ModelSettingsError):
            model_settings.decode_snapshot(value)


def test_password_member_can_change_own_settings_only(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    monkeypatch.delenv("FUNDLEX_BOOTSTRAP_ADMIN", raising=False)
    from fundlex.api import create_app
    app = create_app(tmp_path / "state", auth_db=str(tmp_path / "auth.db"))
    client = TestClient(app)
    headers = []
    for name in ("alice", "bob"):
        app.state.users.create_user(name, "fixture-password", role="member")
        session = client.post("/api/auth/login", json={"username": name, "password": "fixture-password"})
        headers.append({"Authorization": "Bearer " + session.json()["token"]})
    saved = client.put("/api/settings/model", headers=headers[0],
                       json={"primary": {"model": "alice-model"}})
    assert saved.status_code == 200, saved.text
    assert client.get("/api/settings/model", headers=headers[1]).json()["source"] == "deployment"
    assert client.get("/api/settings/model").status_code == 401
