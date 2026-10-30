"""BYOK safety/role/snapshot tests. All credentials are synthetic; no live requests."""
import json
import socket
import threading

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from types import SimpleNamespace

from fundlex import model_settings as settings, user_model_connections as connections
from fundlex.store import RunStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_MODEL_SECRETS_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("LLM_MODEL", "system-model")
    monkeypatch.setenv("LLM_BASE_URL", "https://system.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "system-fixture-secret")
    return RunStore(tmp_path / "state")


def choice(provider="openai", model="execute", key="fixture-user-key", **kwargs):
    return {"source": "personal", "provider": provider, "model": model, "api_key": key, **kwargs}


def payload():
    return {"primary": choice(), "review": choice("deepseek", "check", "fixture-review-key")}


def test_keys_encrypted_owner_private_and_two_real_roles(store, monkeypatch):
    saved = settings.save_settings(store, "alice", payload())
    assert saved["primary"]["provider"] == "openai"
    assert saved["review"]["provider"] == "deepseek"
    assert settings.public_settings(store, "bob")["primary"]["source"] == "system"
    snapshot = settings.snapshot(store, "alice")
    assert "fixture-user-key" not in json.dumps(snapshot)
    assert "fixture-review-key" not in json.dumps(saved)
    with store._connect() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM user_model_connections")]
    assert len(rows) == 2
    assert "fixture-user-key" not in json.dumps(rows)
    assert "fixture-review-key" not in json.dumps(rows)
    configs, task_roles = settings.resolve(snapshot, store=store, owner="alice")
    assert configs["primary"].api_key == "fixture-user-key"
    assert configs["review"].api_key == "fixture-review-key"
    assert configs["primary"].extra_headers == {}
    assert task_roles == {}
    with pytest.raises(connections.ConnectionError):
        settings.resolve(snapshot, store=store, owner="bob")
    gateway = settings.gateway_for(snapshot, store=store, owner="alice")
    assert gateway.primary.model == "execute"
    assert gateway.review.model == "check"
    assert isinstance(gateway.primary._client._transport, connections.PublicHTTPSTransport)
    assert isinstance(gateway.review._client._transport, connections.PublicHTTPSTransport)
    calls = []
    from fundlex.model import ModelGateway
    monkeypatch.setattr(ModelGateway, "call", lambda self, *, task_type, **kwargs: (
        calls.append((task_type, self.model)) or SimpleNamespace(model=self.model, attempts=1)))
    gateway.call(task_type="recall_compose")
    gateway.call(task_type="recall_verify")
    assert calls == [("recall_compose", "execute"), ("recall_verify", "check")]
    assert [item.role for item in gateway.calls] == ["primary", "review"]
    gateway.primary.close(); gateway.review.close()


def test_saved_key_reuse_copy_and_task_snapshot_survive_rotation_reset(store):
    first = settings.save_settings(store, "alice", payload())
    frozen = settings.snapshot(store, "alice")
    previous = first["primary"]["connection_id"]
    reuse = choice(key="", connection_id=previous)
    settings.save_settings(store, "alice", {"primary": reuse, "review": reuse})
    configs, _ = settings.resolve(settings.snapshot(store, "alice"), store=store, owner="alice")
    assert configs["review"].api_key == "fixture-user-key"
    settings.save_settings(store, "alice", {"primary": choice(key="replacement"), "review": {"source": "system"}})
    settings.reset_settings(store, "alice")
    configs, _ = settings.resolve(frozen, store=store, owner="alice")
    assert configs["primary"].api_key == "fixture-user-key"
    assert configs["review"].api_key == "fixture-review-key"
    assert settings.snapshot(store, "alice") == {}


def test_system_role_never_forwards_secret_to_custom_endpoint(store):
    with pytest.raises(connections.ConnectionError):
        settings.save_settings(store, "alice", {"primary": choice("custom", key="", base_url="https://other.example/v1"), "review": {"source": "system"}})
    saved = settings.save_settings(store, "alice", payload())
    reuse = choice("custom", key="", connection_id=saved["primary"]["connection_id"], base_url="https://other.example/v1")
    with pytest.raises(connections.ConnectionError):
        settings.save_settings(store, "alice", {"primary": reuse, "review": {"source": "system"}})
    with pytest.raises(connections.ConnectionError):
        settings.save_settings(store, "bob", {"primary": {**reuse, "provider": "openai", "base_url": ""}, "review": {"source": "system"}})


def test_custom_endpoint_connection_test_uses_only_owner_key(store, monkeypatch):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    monkeypatch.setattr(connections, "client", lambda: httpx.Client(transport=httpx.MockTransport(handle)))
    result = connections.test_connection(store, "alice", choice(
        "custom", key="fixture-user-key", base_url="https://service.example/v1"))
    assert result["ok"]
    assert seen[0].headers["authorization"] == "Bearer fixture-user-key"
    assert "system-fixture-secret" not in seen[0].headers["authorization"]


def test_missing_master_key_and_tampering_fail_closed(store, monkeypatch):
    monkeypatch.delenv("FUNDLEX_MODEL_SECRETS_KEY")
    with pytest.raises(connections.ConnectionError):
        settings.save_settings(store, "alice", payload())
    assert settings.snapshot(store, "alice") == {}
    monkeypatch.setenv("FUNDLEX_MODEL_SECRETS_KEY", Fernet.generate_key().decode())
    settings.save_settings(store, "alice", payload())
    frozen = settings.snapshot(store, "alice")
    frozen["primary"]["base_url"] = "https://other.example/v1"
    with pytest.raises(connections.ConnectionError):
        settings.resolve(frozen, store=store, owner="alice")
    frozen = settings.snapshot(store, "alice")
    monkeypatch.setenv("FUNDLEX_MODEL_SECRETS_KEY", Fernet.generate_key().decode())
    with pytest.raises(connections.ConnectionError):
        settings.resolve(frozen, store=store, owner="alice")


@pytest.mark.parametrize("url", ["http://example.com/v1", "https://127.0.0.1", "https://[::1]", "https://100.100.100.200", "https://localhost", "https://a:b@example.com", "https://example.com:0/v1", "https://example.com:bad/v1", "https://example.com?key=fixture", "https://example.com/#fragment", "https://10.0.0.1", "https://169.254.169.254", "https://224.0.0.1"])
def test_unsafe_endpoints_rejected(url):
    with pytest.raises(connections.ConnectionError):
        connections.endpoint(url)


def test_dns_all_answers_checked_and_connect_ip_pinned(monkeypatch):
    resolved = []
    def resolve(host, port, **kwargs):
        resolved.append((host, port))
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", port))]
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    seen = []
    transport = connections.PublicHTTPSTransport()
    transport.transport.close()
    transport.transport = httpx.MockTransport(lambda request: (seen.append(request) or httpx.Response(200, json={})))
    with httpx.Client(transport=transport, trust_env=False) as client:
        client.post("https://service.example:8443/v1/chat/completions", headers={"Authorization": "Bearer fixture"})
    assert seen[0].url.host == "8.8.8.8"
    assert seen[0].url.port == 8443
    assert seen[0].headers["Host"] == "service.example:8443"
    assert seen[0].extensions["sni_hostname"] == "service.example"
    assert resolved == [("service.example", 8443)]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **kw: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("8.8.8.8", "127.0.0.1")])
    with pytest.raises(connections.ConnectionError):
        connections.public_addresses("service.example")


def test_mysql_ddl_keeps_connection_keys_and_settings_columns_compatible():
    from fundlex.db import Database
    database = Database("mysql://fixture:fixture@db.invalid/fundlex")
    statements = [
        """CREATE TABLE IF NOT EXISTS user_model_connections (
            id TEXT PRIMARY KEY, owner TEXT NOT NULL, settings_json MEDIUMTEXT NOT NULL,
            key_cipher MEDIUMTEXT NOT NULL, created_at REAL NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS user_model_settings (
            owner TEXT PRIMARY KEY, settings_json MEDIUMTEXT NOT NULL, updated_at REAL NOT NULL)""",
    ]
    for statement in statements:
        kind, sql = database.prepare(statement)
        assert kind == "run"
        assert "id VARCHAR(255) PRIMARY KEY" in sql or "owner VARCHAR(255) PRIMARY KEY" in sql
        assert "MEDIUMTEXT NOT NULL" in sql


def test_system_role_keeps_distinct_deployment_models_and_internal_limits(store, monkeypatch):
    monkeypatch.setenv("FUNDLEX_REVIEW_PROVIDER", "review-provider")
    monkeypatch.setenv("FUNDLEX_REVIEW_MODEL", "system-check")
    monkeypatch.setenv("FUNDLEX_REVIEW_BASE_URL", "https://review.invalid/v1")
    monkeypatch.setenv("FUNDLEX_REVIEW_API_KEY", "system-review-secret")
    prefs = settings.save_settings(store, "alice", {
        "primary": {"source": "system"},
        "review": choice("deepseek", "personal-check", "user-review-key")})
    snapshot = settings.snapshot(store, "alice")
    configs, _ = settings.resolve(snapshot, store=store, owner="alice")
    assert configs["primary"].model == "system-model"
    assert configs["primary"].api_key == "system-fixture-secret"
    assert configs["review"].model == "personal-check"
    assert configs["review"].api_key == "user-review-key"
    assert configs["review"].max_tokens == 1500
    assert prefs["primary"]["system_model"] == "system-model"


def test_unused_encrypted_keys_collected_but_task_snapshot_keys_retained(store):
    with store._connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS tasks (model_preferences TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS batches (model_preferences TEXT)")
    first = settings.save_settings(store, "alice", payload())
    frozen = settings.snapshot(store, "alice")
    with store._connect() as db:
        db.execute("INSERT INTO tasks(model_preferences) VALUES(?)", (json.dumps(frozen),))
    settings.save_settings(store, "alice", {"primary": choice(key="new-key"), "review": {"source": "system"}})
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM user_model_connections").fetchone()[0] == 3
    settings.reset_settings(store, "alice")
    with store._connect() as db:
        remaining = {row[0] for row in db.execute("SELECT id FROM user_model_connections")}
    assert remaining == {first["primary"]["connection_id"], first["review"]["connection_id"]}
    assert settings.resolve(frozen, store=store, owner="alice")[0]["primary"].api_key == "fixture-user-key"


def test_unknown_or_corrupt_versioned_snapshot_prevents_credential_gc(store):
    saved = settings.save_settings(store, "alice", payload())
    with store._connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS tasks (model_preferences TEXT)")
        db.execute("CREATE TABLE IF NOT EXISTS batches (model_preferences TEXT)")
        db.execute("INSERT INTO tasks(model_preferences) VALUES(?)",
                   (json.dumps({"version": 3, "primary": {"connection_id": saved["primary"]["connection_id"]}}),))
    settings.reset_settings(store, "alice")
    with store._connect() as db:
        retained = {row[0] for row in db.execute("SELECT id FROM user_model_connections")}
    assert retained == {saved["primary"]["connection_id"], saved["review"]["connection_id"]}


def test_task_snapshot_transaction_serializes_against_key_rotation(store):
    from concurrent.futures import ThreadPoolExecutor
    from fundlex.tasks import TaskStore

    saved = settings.save_settings(store, "alice", payload())
    snapshot_ready = threading.Event()
    continue_create = threading.Event()
    tasks = TaskStore(store)

    def snapshot_factory(db):
        value = settings.snapshot_in_task_transaction(db, "alice")
        snapshot_ready.set()
        assert continue_create.wait(5)
        return value

    with ThreadPoolExecutor(max_workers=2) as pool:
        create_future = pool.submit(tasks.create, "alice", "atomic snapshot",
            {"version": "guide-v1", "sha256": "guide-hash"}, [],
            engine_id="recall_first", model_preferences_factory=snapshot_factory)
        assert snapshot_ready.wait(5)
        save_started = threading.Event()

        def rotate():
            save_started.set()
            return settings.save_settings(store, "alice", {
                "primary": choice(key="rotated-key"), "review": {"source": "system"}})

        save_future = pool.submit(rotate)
        assert save_started.wait(5)
        continue_create.set()
        task = create_future.result(10)
        save_future.result(10)

    assert task["model_preferences"]["primary"]["connection_id"] == saved["primary"]["connection_id"]
    assert task["model_preferences"]["review"]["connection_id"] == saved["review"]["connection_id"]
    resolved, _ = settings.resolve(task["model_preferences"], store=store, owner="alice")
    assert resolved["primary"].api_key == "fixture-user-key"
    assert resolved["review"].api_key == "fixture-review-key"


@pytest.mark.parametrize("status,ok", [(200, True), (302, False), (401, False), (402, False), (404, False), (429, False), (503, False)])
def test_explicit_test_connection_redacts_provider_error(store, monkeypatch, status, ok):
    def handler(request):
        assert b"contract" not in request.content
        return httpx.Response(status, json={"choices": [{"message": {"content": "OK"}}], "error": "fixture-user-key"})
    monkeypatch.setattr(connections, "client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    result = connections.test_connection(store, "alice", choice())
    assert result["ok"] is ok
    assert "fixture-user-key" not in json.dumps(result)


def test_api_does_not_echo_secret_on_invalid_input(store, tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    from fundlex.api import create_app
    client = TestClient(create_app(tmp_path / "api"))
    headers = {"X-FundLex-User": "alice"}
    value = payload()
    value["primary"]["bad_field"] = "fixture-user-key"
    response = client.put("/api/settings/model", headers=headers, json=value)
    assert response.status_code == 422
    assert "fixture-user-key" not in response.text
    response = client.post("/api/settings/model/test", headers=headers, json=value["primary"])
    assert response.status_code == 422
    assert "fixture-user-key" not in response.text


def test_api_saves_both_roles_without_returning_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_MODEL_SECRETS_KEY", Fernet.generate_key().decode())
    from fundlex.api import create_app
    client = TestClient(create_app(tmp_path / "api"))
    headers = {"X-FundLex-User": "alice"}
    request = payload()
    response = client.put("/api/settings/model", headers=headers, json=request)
    assert response.status_code == 200, response.text
    assert response.json()["primary"]["model"] == "execute"
    assert response.json()["review"]["model"] == "check"
    assert response.json()["primary"]["source"] == "personal"
    assert response.json()["review"]["provider"] == "deepseek"
    assert "fixture-user-key" not in response.text and "fixture-review-key" not in response.text
    assert "timeout_s" not in response.text and "max_tokens" not in response.text
    readback = client.get("/api/settings/model", headers=headers)
    assert readback.json()["review"]["model"] == "check"
    assert "fixture-review-key" not in readback.text
