"""Account and session authentication checks on isolated SQLite via TestClient.

``fundlex.db`` is delivered by a parallel change; this module skips until the
adapter is importable and then runs directly against its documented contract
(``Database(target)`` plus ``with db.connect() as conn`` transactions).
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fundlex.db", reason="fundlex.db adapter lands in a parallel change")

from fundlex.api import create_app
from fundlex.auth import (AccountDisabled, InvalidCredentials, SessionStore, UserExists,
                          UserNotFound, ValidationError, UserStore, bootstrap_admin,
                          hash_password, verify_password)
from fundlex.db import Database


ALICE = ("alice", "alice-password")
BOB = ("bob", "bob-password")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture(autouse=True)
def _isolated_auth_env(monkeypatch):
    for name in ("FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL", "FUNDLEX_SESSION_HOURS",
                 "FUNDLEX_BOOTSTRAP_ADMIN", "FUNDLEX_AUTH_MODE"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def database(tmp_path):
    return Database(str(tmp_path / "auth.db"))


@pytest.fixture
def users(database):
    return UserStore(database)


@pytest.fixture
def password_client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    app = create_app(tmp_path)
    app.state.users.create_user(*ALICE, "Alice", "admin")
    app.state.users.create_user(*BOB, "Bob", "member")
    return TestClient(app)


def test_password_hash_roundtrip_and_storage_format():
    stored = hash_password("correct horse battery")
    assert stored.startswith("scrypt$16384$8$1$")
    assert len(stored.split("$")) == 6
    assert verify_password("correct horse battery", stored) is True
    assert verify_password("correct horse battery ", stored) is False
    assert verify_password("", stored) is False
    assert verify_password("anything", stored[:-4] + "AAAA") is False
    assert verify_password("anything", "plaintext") is False
    assert verify_password("anything", "scrypt$16384$8$1$not-base64$hash") is False
    assert verify_password("anything", "scrypt$99999999$8$1$AA==$AA==") is False
    assert hash_password("same input") != hash_password("same input")


def test_user_creation_validation_and_listing(users):
    record = users.create_user("alice", "password-123", "Alice", "admin")
    assert record["username"] == "alice" and record["role"] == "admin" and record["disabled"] is False
    assert record["id"] and record["created_at"] > 0
    assert users.get(record["id"]) == record
    assert [u["username"] for u in users.list_users()] == ["alice"]
    with pytest.raises(UserExists):
        users.create_user("alice", "another-password")
    for username in ("ab", "a" * 65, "bad user", "bad@user", "", None):
        with pytest.raises(ValidationError):
            users.create_user(username, "password-123")
    with pytest.raises(ValidationError):
        users.create_user("carol", "short")
    with pytest.raises(ValidationError):
        users.create_user("carol", "password-123", role="owner")
    with pytest.raises(ValidationError):
        users.create_user("carol", "password-123", display_name="x" * 200)
    with pytest.raises(UserNotFound):
        users.set_disabled("missing", True)


def test_authenticate_rejects_wrong_password_unknown_user_and_disabled(users):
    record = users.create_user("alice", "password-123", "Alice")
    authenticated = users.authenticate("alice", "password-123")
    assert authenticated["id"] == record["id"] and "password_hash" not in authenticated
    with pytest.raises(InvalidCredentials):
        users.authenticate("alice", "password-124")
    with pytest.raises(InvalidCredentials):
        users.authenticate("unknown", "password-123")
    users.set_disabled(record["id"], True)
    assert users.get(record["id"])["disabled"] is True
    with pytest.raises(AccountDisabled):
        users.authenticate("alice", "password-123")
    users.set_disabled(record["id"], False)
    assert users.authenticate("alice", "password-123")["disabled"] is False


def test_change_password_requires_current_password(users):
    record = users.create_user("alice", "password-123")
    with pytest.raises(InvalidCredentials):
        users.change_password(record["id"], "wrong-password", "new-password-1")
    updated = users.change_password(record["id"], "password-123", "new-password-1")
    assert updated["updated_at"] >= record["updated_at"]
    with pytest.raises(InvalidCredentials):
        users.authenticate("alice", "password-123")
    assert users.authenticate("alice", "new-password-1")["id"] == record["id"]
    with pytest.raises(UserNotFound):
        users.change_password("missing", "password-123", "new-password-2")


def test_session_tokens_are_hashed_and_expire(database, users, monkeypatch):
    monkeypatch.setenv("FUNDLEX_SESSION_HOURS", "2")
    sessions = SessionStore(database)
    assert sessions.hours == 2.0
    record = users.create_user("alice", "password-123")
    token = sessions.login(record["id"])
    assert len(token) >= 32
    with database.connect() as conn:
        rows = conn.execute("SELECT token_hash, user_id, expires_at FROM sessions").fetchall()
    assert len(rows) == 1
    assert rows[0]["token_hash"] == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert rows[0]["user_id"] == record["id"]
    assert rows[0]["expires_at"] > 0
    assert sessions.resolve(token) == record["id"]
    assert sessions.resolve(token + "x") is None
    assert sessions.resolve("") is None
    sessions.logout(token)
    assert sessions.resolve(token) is None

    clock = {"now": 1000.0}
    timed = SessionStore(database, hours=1, clock=lambda: clock["now"])
    expiring = timed.login(record["id"])
    assert timed.resolve(expiring) == record["id"]
    clock["now"] += 3600.5
    assert timed.resolve(expiring) is None


def test_session_hours_default_and_invalid_override(database, monkeypatch):
    assert SessionStore(database).hours == 12.0
    monkeypatch.setenv("FUNDLEX_SESSION_HOURS", "0.5")
    assert SessionStore(database).hours == 0.5
    monkeypatch.setenv("FUNDLEX_SESSION_HOURS", "not-a-number")
    with pytest.raises(ValidationError):
        SessionStore(database)
    monkeypatch.setenv("FUNDLEX_SESSION_HOURS", "0")
    with pytest.raises(ValidationError):
        SessionStore(database)


def test_login_me_logout_and_capabilities(password_client):
    client = password_client
    anonymous = client.get("/api/capabilities")
    assert anonymous.status_code == 200
    assert anonymous.json()["auth_mode"] == "password"
    assert anonymous.json()["login_required"] is True
    assert "upload_limits" not in anonymous.json()
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/tasks").status_code == 401

    assert login(client, "alice", "wrong-password").status_code == 401
    assert login(client, "unknown", "whatever-123").status_code == 401

    response = login(client, *ALICE)
    assert response.status_code == 200
    token, user = response.json()["token"], response.json()["user"]
    assert set(user) == {"id", "username", "display_name", "role"}
    assert user["username"] == "alice" and user["role"] == "admin"
    assert user["display_name"] == "Alice"

    me = client.get("/api/auth/me", headers=bearer(token))
    assert me.status_code == 200 and me.json() == user
    full = client.get("/api/capabilities", headers=bearer(token)).json()
    assert full["login_required"] is True and "upload_limits" in full

    assert client.post("/api/auth/logout", headers=bearer(token)).json() == {"ok": True}
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401
    assert client.get("/api/tasks", headers=bearer("not-a-token")).status_code == 401


def test_expired_session_is_rejected(password_client):
    client = password_client
    token = login(client, *ALICE).json()["token"]
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 200
    with client.app.state.auth_db.connect() as conn:
        conn.execute("UPDATE sessions SET expires_at=0")
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401
    assert client.get("/api/tasks", headers=bearer(token)).status_code == 401


def test_owner_isolation_between_password_users(password_client):
    client = password_client
    alice = login(client, *ALICE).json()["token"]
    bob = login(client, *BOB).json()["token"]
    manifest = [{"client_id": "file-1", "name": "合同.docx", "size": 128}]
    created = client.post("/api/tasks", headers=bearer(alice),
                          json={"name": "Alice 任务", "engine_id": "recall_first", "files": manifest})
    assert created.status_code == 201
    task_id = created.json()["id"]
    assert client.get(f"/api/tasks/{task_id}", headers=bearer(alice)).status_code == 200
    for suffix in ("", "/documents", "/report"):
        assert client.get(f"/api/tasks/{task_id}{suffix}", headers=bearer(bob)).status_code == 404
    assert client.get("/api/tasks", headers=bearer(bob)).json()["items"] == []
    assert client.get("/api/tasks", headers=bearer(alice)).json()["total"] == 1

    second = client.post("/api/tasks", headers=bearer(bob),
                         json={"name": "Bob 任务", "engine_id": "recall_first", "files": manifest})
    assert second.status_code == 201
    assert client.get(f"/api/tasks/{second.json()['id']}", headers=bearer(alice)).status_code == 404
    assert client.get("/api/tasks", headers=bearer(alice)).json()["total"] == 1


def test_dev_mode_regression_and_account_surface_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    app = create_app(tmp_path)
    client = TestClient(app)
    assert client.get("/api/tasks").status_code == 401
    assert client.get("/api/tasks", headers={"X-FundLex-User": "alice"}).status_code == 200
    assert client.get("/api/capabilities").status_code == 401
    caps = client.get("/api/capabilities", headers={"X-FundLex-User": "alice"}).json()
    assert caps["auth_mode"] == "dev" and caps["login_required"] is False
    assert login(client, "alice", "password-123").status_code == 404
    assert client.get("/api/auth/me", headers={"X-FundLex-User": "alice"}).status_code == 404
    assert client.post("/api/auth/logout", headers={"X-FundLex-User": "alice"}).status_code == 404
    assert client.get("/api/admin/users", headers={"X-FundLex-User": "alice"}).status_code == 404


def test_bootstrap_admin_seeds_once_without_plaintext(tmp_path, monkeypatch):
    secret = "bootstrap-secret-1"
    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", f"root:{secret}")
    app = create_app(tmp_path)
    admins = [u for u in app.state.users.list_users() if u["role"] == "admin"]
    assert len(admins) == 1 and admins[0]["username"] == "root"
    with app.state.auth_db.connect() as conn:
        stored = conn.execute("SELECT password_hash FROM users WHERE username='root'").fetchone()[0]
    assert secret not in stored and stored.startswith("scrypt$")
    again = create_app(tmp_path)
    assert len(again.state.users.list_users()) == 1


def test_bootstrap_admin_rejects_malformed_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", "root-without-password")
    with pytest.raises(ValidationError):
        create_app(tmp_path)


def test_bootstrap_admin_skipped_when_users_exist(database, users, monkeypatch):
    users.create_user("existing", "password-123")
    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", "root:another-secret")
    assert bootstrap_admin(database) is None
    assert [u["username"] for u in users.list_users()] == ["existing"]


def test_admin_endpoints_permissions_and_disable(password_client):
    client = password_client
    admin = login(client, *ALICE).json()["token"]
    member = login(client, *BOB).json()["token"]
    assert client.get("/api/admin/users").status_code == 404
    assert client.get("/api/admin/users", headers=bearer(member)).status_code == 404
    assert client.post("/api/admin/users", headers=bearer(member),
                       json={"username": "carol", "password": "carol-password"}).status_code == 404
    assert client.post("/api/admin/users/x/disable", headers=bearer(member)).status_code == 404

    listed = client.get("/api/admin/users", headers=bearer(admin)).json()["users"]
    assert {u["username"] for u in listed} == {"alice", "bob"}
    created = client.post("/api/admin/users", headers=bearer(admin),
                          json={"username": "carol", "password": "carol-password", "display_name": "Carol"})
    assert created.status_code == 201
    carol = created.json()
    assert carol["role"] == "member" and carol["display_name"] == "Carol"
    assert client.post("/api/admin/users", headers=bearer(admin),
                       json={"username": "carol", "password": "carol-password"}).status_code == 409
    assert client.post("/api/admin/users", headers=bearer(admin),
                       json={"username": "carol", "password": "short"}).status_code == 422

    carol_token = login(client, "carol", "carol-password").json()["token"]
    assert client.get("/api/auth/me", headers=bearer(carol_token)).status_code == 200
    disabled = client.post(f"/api/admin/users/{carol['id']}/disable", headers=bearer(admin), json={})
    assert disabled.status_code == 200 and disabled.json()["disabled"] is True
    assert client.get("/api/auth/me", headers=bearer(carol_token)).status_code == 401
    assert login(client, "carol", "carol-password").status_code == 403
    assert client.post(f"/api/admin/users/{carol['id']}/disable", headers=bearer(admin),
                       json={"disabled": False}).json()["disabled"] is False
    assert login(client, "carol", "carol-password").status_code == 200
    assert client.post("/api/admin/users/does-not-exist/disable", headers=bearer(admin)).status_code == 404


def test_disable_invalidates_existing_session_even_without_revoke(password_client):
    client = password_client
    token = login(client, *BOB).json()["token"]
    bob_id = next(u["id"] for u in client.app.state.users.list_users() if u["username"] == "bob")
    client.app.state.users.set_disabled(bob_id, True)  # bypass the admin revoke path
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 401


def test_password_change_revokes_other_sessions(password_client):
    client = password_client
    first = login(client, *ALICE).json()["token"]
    second = login(client, *ALICE).json()["token"]
    assert client.post("/api/auth/password", headers=bearer(first),
                       json={"old_password": "wrong-password",
                             "new_password": "alice-password-2"}).status_code == 401
    assert client.post("/api/auth/password", headers=bearer(first),
                       json={"old_password": "alice-password",
                             "new_password": "alice-password-2"}).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(first)).status_code == 200
    assert client.get("/api/auth/me", headers=bearer(second)).status_code == 401
    assert login(client, "alice", "alice-password").status_code == 401
    assert login(client, "alice", "alice-password-2").status_code == 200
