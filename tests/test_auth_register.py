"""Self-service registration checks on isolated SQLite via TestClient.

Covers the password-mode contract: register creates a member account with a
working session, duplicates and invalid input are rejected, and the switch
(``FUNDLEX_ALLOW_REGISTRATION``) plus the capabilities flag behave.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fundlex.db", reason="fundlex.db adapter lands in a parallel change")

from fundlex.api import create_app


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _isolated_auth_env(monkeypatch):
    for name in ("FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL", "FUNDLEX_SESSION_HOURS",
                 "FUNDLEX_BOOTSTRAP_ADMIN", "FUNDLEX_AUTH_MODE", "FUNDLEX_ALLOW_REGISTRATION"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def password_client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    return TestClient(create_app(tmp_path))


def test_register_creates_member_and_returns_session(password_client):
    response = password_client.post("/api/auth/register", json={
        "username": "newuser", "password": "password-123", "display_name": "新用户"})
    assert response.status_code == 201
    payload = response.json()
    assert payload["user"]["username"] == "newuser" and payload["user"]["role"] == "member"
    assert payload["user"]["display_name"] == "新用户"
    tasks = password_client.get("/api/tasks", headers=bearer(payload["token"]))
    assert tasks.status_code == 200 and tasks.json()["total"] == 0
    login = password_client.post("/api/auth/login", json={
        "username": "newuser", "password": "password-123"})
    assert login.status_code == 200 and login.json()["user"]["username"] == "newuser"


def test_register_rejects_duplicate_and_invalid_input(password_client):
    first = password_client.post("/api/auth/register", json={
        "username": "dupuser", "password": "password-123"})
    assert first.status_code == 201
    duplicate = password_client.post("/api/auth/register", json={
        "username": "dupuser", "password": "password-456"})
    assert duplicate.status_code == 409
    short = password_client.post("/api/auth/register", json={
        "username": "shorty", "password": "short12"})
    assert short.status_code == 422
    bad_name = password_client.post("/api/auth/register", json={
        "username": "bad name!", "password": "password-123"})
    assert bad_name.status_code == 422
    bad_role = password_client.post("/api/auth/register", json={
        "username": "roleuser", "password": "password-123", "role": "admin"})
    assert bad_role.status_code == 422  # extra fields are forbidden


def test_capabilities_expose_registration_flag(password_client):
    body = password_client.get("/api/capabilities").json()
    assert body["auth_mode"] == "password" and body["registration_open"] is True


def test_registration_can_be_closed_with_env(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    monkeypatch.setenv("FUNDLEX_ALLOW_REGISTRATION", "0")
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/auth/register", json={
        "username": "closeduser", "password": "password-123"})
    assert response.status_code == 403
    assert client.get("/api/capabilities").json()["registration_open"] is False


def test_registration_is_absent_in_dev_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    client = TestClient(create_app(tmp_path))
    response = client.post("/api/auth/register", json={
        "username": "devuser", "password": "password-123"})
    assert response.status_code == 404
    capabilities = client.get("/api/capabilities", headers={"X-FundLex-User": "local-user"}).json()
    assert capabilities["registration_open"] is False
