"""Regression checks for the isolated Test runtime contract."""
from __future__ import annotations

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from fundlex.config import assert_runtime_isolation, write_heartbeat


def test_non_production_rejects_production_paths(monkeypatch):
    monkeypatch.setenv("FUNDLEX_ENV", "test")
    with pytest.raises(RuntimeError, match="production path"):
        assert_runtime_isolation(data_dir="/var/lib/fundlex/tasks")
    with pytest.raises(RuntimeError, match="production path"):
        assert_runtime_isolation(auth_db="sqlite:////var/lib/fundlex/auth.sqlite3")
    with pytest.raises(RuntimeError, match="production path"):
        assert_runtime_isolation(ledger="/opt/fundlex-recall-first/model.sqlite")
    monkeypatch.setenv("FUNDLEX_DATABASE_URL", "mysql://test:test@127.0.0.1/fundlex_test")
    with pytest.raises(RuntimeError, match="FUNDLEX_DATABASE_URL"):
        assert_runtime_isolation(data_dir="/var/lib/fundlex-test")


def test_test_runtime_rejects_system_configuration_paths(monkeypatch):
    monkeypatch.setenv("FUNDLEX_ENV", "test")
    with pytest.raises(RuntimeError, match="system configuration path"):
        assert_runtime_isolation(data_dir="/etc/fundlex-test")


def test_production_profile_is_explicitly_allowed(monkeypatch):
    monkeypatch.setenv("FUNDLEX_ENV", "production")
    assert_runtime_isolation(data_dir="/var/lib/fundlex", auth_db="/var/lib/fundlex/auth.sqlite3")


def test_heartbeat_is_atomic_and_contains_non_sensitive_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_ENV", "test")
    monkeypatch.setenv("FUNDLEX_COMMIT", "abc123")
    write_heartbeat(tmp_path, component="worker")
    heartbeat = tmp_path / "worker-heartbeat.json"
    assert heartbeat.is_file()
    payload = json.loads(heartbeat.read_text(encoding="utf-8"))
    assert payload["component"] == "worker"
    assert payload["environment"] == "test"
    assert payload["commit"] == "abc123"
    assert isinstance(payload["timestamp"], float)
    assert not (tmp_path / "worker-heartbeat.tmp").exists()


def test_capabilities_and_health_expose_test_identity(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_ENV", "test")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_COMMIT", "test-commit")
    monkeypatch.setenv("LLM_BASE_URL", "https://model.test.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    from fundlex.api import create_app

    app = create_app(tmp_path / "data", auth_db=str(tmp_path / "auth.sqlite3"))
    client = TestClient(app)
    headers = {"X-FundLex-User": "test-user"}
    capabilities = client.get("/api/capabilities", headers=headers)
    assert capabilities.status_code == 200
    assert capabilities.json()["environment"] == "test"
    assert capabilities.json()["commit"] == "test-commit"

    write_heartbeat(tmp_path / "data", component="worker")
    write_heartbeat(tmp_path / "data", component="compare-worker")
    health = client.get("/api/health", headers=headers)
    assert health.status_code == 200
    body = health.json()
    assert body["environment"] == "test"
    assert body["status"] == "ok"
    assert body["components"] == {
        "task_store": "ok", "auth_store": "ok", "compare_store": "ok",
        "worker": "ok", "compare": "ok", "model_config": "ok",
    }


def test_health_reports_missing_heartbeat_and_model(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_ENV", "test")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    from fundlex.api import create_app

    client = TestClient(create_app(tmp_path / "data", auth_db=str(tmp_path / "auth.sqlite3")))
    body = client.get("/api/health", headers={"X-FundLex-User": "test-user"}).json()
    assert body["status"] == "degraded"
    assert body["components"]["worker"] == "missing"
    assert body["components"]["compare"] == "missing"
    assert body["components"]["model_config"] == "missing"


def test_health_reports_stale_heartbeat(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_ENV", "test")
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    monkeypatch.setenv("FUNDLEX_HEARTBEAT_MAX_AGE_S", "1")
    monkeypatch.setenv("LLM_BASE_URL", "https://model.test.invalid/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    from fundlex.api import create_app

    data_dir = tmp_path / "data"
    write_heartbeat(data_dir, component="worker")
    write_heartbeat(data_dir, component="compare-worker")
    old = time.time() - 10
    for name in ("worker-heartbeat.json", "compare-worker-heartbeat.json"):
        os.utime(data_dir / name, (old, old))
    client = TestClient(create_app(data_dir, auth_db=str(tmp_path / "auth.sqlite3")))
    body = client.get("/api/health", headers={"X-FundLex-User": "test-user"}).json()
    assert body["status"] == "degraded"
    assert body["components"]["worker"] == "stale"
    assert body["components"]["compare"] == "stale"
