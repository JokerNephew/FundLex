"""Administrator lockout guard on the real ``UserStore`` and HTTP API.

The product decision keeps registration and login rate limiting unchanged. This
module only covers the fail-closed rule for disabling administrators plus the
optional bootstrap recovery path.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("fundlex.db", reason="fundlex.db adapter lands in a parallel change")

from fundlex.api import create_app
from fundlex.auth import (AccountDisabled, LastAdminError, UserStore, bootstrap_admin)
from fundlex.db import Database


ADMIN = ("root", "root-password")
DEPUTY = ("deputy", "deputy-password")
MEMBER = ("member", "member-password")


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


@pytest.fixture(autouse=True)
def _isolated_auth_env(monkeypatch):
    for name in ("FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL", "FUNDLEX_SESSION_HOURS",
                 "FUNDLEX_BOOTSTRAP_ADMIN", "FUNDLEX_AUTH_MODE", "FUNDLEX_ALLOW_REGISTRATION"):
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
    admin = app.state.users.create_user(*ADMIN, "Root", "admin")
    return TestClient(app), admin


def disable_directly(database, user_id):
    """Simulate the pre-guard lockout state for recovery/re-enable tests."""
    with database.connect() as conn:
        conn.execute("UPDATE users SET disabled=1 WHERE id=?", (user_id,))


def test_last_enabled_admin_cannot_be_disabled(users):
    admin = users.create_user(*ADMIN, "Root", "admin")

    with pytest.raises(LastAdminError) as caught:
        users.set_disabled(admin["id"], True)

    assert caught.value.code == "LAST_ADMIN_REQUIRED"
    assert users.get(admin["id"])["disabled"] is False
    assert users.authenticate(*ADMIN)["role"] == "admin"


def test_admin_can_be_disabled_while_another_enabled_admin_remains(users):
    first = users.create_user(*ADMIN, "Root", "admin")
    second = users.create_user(*DEPUTY, "Deputy", "admin")

    assert users.set_disabled(second["id"], True)["disabled"] is True
    assert users.get(first["id"])["disabled"] is False
    # The remaining enabled administrator is now protected.
    with pytest.raises(LastAdminError):
        users.set_disabled(first["id"], True)
    assert users.get(first["id"])["disabled"] is False


def test_disabling_an_already_disabled_admin_is_idempotent(users):
    users.create_user(*ADMIN, "Root", "admin")
    second = users.create_user(*DEPUTY, "Deputy", "admin")
    first_disabled = users.set_disabled(second["id"], True)

    again = users.set_disabled(second["id"], True)

    assert again["disabled"] is True
    assert again["updated_at"] == first_disabled["updated_at"]
    assert users.get(second["id"])["disabled"] is True


def test_disabling_a_non_admin_is_unaffected(users):
    users.create_user(*ADMIN, "Root", "admin")
    member = users.create_user(*MEMBER, "Member")

    assert users.set_disabled(member["id"], True)["disabled"] is True
    assert users.get(member["id"])["disabled"] is True


def test_reenabling_a_disabled_admin_is_unaffected(users, database):
    admin = users.create_user(*ADMIN, "Root", "admin")
    disable_directly(database, admin["id"])
    with pytest.raises(AccountDisabled):
        users.authenticate(*ADMIN)

    assert users.set_disabled(admin["id"], False)["disabled"] is False
    assert users.authenticate(*ADMIN)["disabled"] is False


def test_api_returns_409_and_keeps_the_last_admin_session(password_client):
    client, admin = password_client
    token = login(client, *ADMIN).json()["token"]

    response = client.post(f"/api/admin/users/{admin['id']}/disable", headers=bearer(token))

    assert response.status_code == 409
    body = response.json()
    assert body["error_code"] == "LAST_ADMIN_REQUIRED"
    assert body["detail"] == "LAST_ADMIN_REQUIRED"
    assert client.app.state.users.get(admin["id"])["disabled"] is False
    # The failed request must not revoke the caller's session.
    assert client.get("/api/auth/me", headers=bearer(token)).status_code == 200


def test_api_allows_disabling_one_of_two_admins(password_client):
    client, admin = password_client
    deputy = client.app.state.users.create_user(*DEPUTY, "Deputy", "admin")
    admin_token = login(client, *ADMIN).json()["token"]
    deputy_token = login(client, *DEPUTY).json()["token"]

    response = client.post(f"/api/admin/users/{deputy['id']}/disable", headers=bearer(admin_token))

    assert response.status_code == 200 and response.json()["disabled"] is True
    assert client.get("/api/auth/me", headers=bearer(deputy_token)).status_code == 401
    assert login(client, *DEPUTY).status_code == 403

    last = client.post(f"/api/admin/users/{admin['id']}/disable", headers=bearer(admin_token))
    assert last.status_code == 409
    assert client.get("/api/auth/me", headers=bearer(admin_token)).status_code == 200


def test_api_still_disables_and_reenables_members(password_client):
    client, _admin = password_client
    member = client.app.state.users.create_user(*MEMBER, "Member")
    admin_token = login(client, *ADMIN).json()["token"]
    member_token = login(client, *MEMBER).json()["token"]

    disabled = client.post(f"/api/admin/users/{member['id']}/disable", headers=bearer(admin_token))
    assert disabled.status_code == 200 and disabled.json()["disabled"] is True
    assert client.get("/api/auth/me", headers=bearer(member_token)).status_code == 401

    enabled = client.post(f"/api/admin/users/{member['id']}/disable", headers=bearer(admin_token),
                          json={"disabled": False})
    assert enabled.status_code == 200 and enabled.json()["disabled"] is False
    assert login(client, *MEMBER).status_code == 200


def test_bootstrap_admin_recovers_the_configured_disabled_admin(users, database, monkeypatch):
    admin = users.create_user(*ADMIN, "Root", "admin")
    disable_directly(database, admin["id"])
    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", f"{ADMIN[0]}:{ADMIN[1]}")

    recovered = bootstrap_admin(database, users=users)

    assert recovered["id"] == admin["id"]
    assert recovered["role"] == "admin" and recovered["disabled"] is False
    assert users.authenticate(*ADMIN)["disabled"] is False


def test_bootstrap_admin_recovery_requires_the_configured_password(users, database, monkeypatch):
    admin = users.create_user(*ADMIN, "Root", "admin")
    disable_directly(database, admin["id"])
    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", f"{ADMIN[0]}:wrong-password")

    assert bootstrap_admin(database, users=users) is None
    assert users.get(admin["id"])["disabled"] is True


def test_bootstrap_admin_recovery_requires_the_configured_username(users, database, monkeypatch):
    admin = users.create_user(*ADMIN, "Root", "admin")
    disable_directly(database, admin["id"])
    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", f"someone-else:{ADMIN[1]}")

    assert bootstrap_admin(database, users=users) is None
    assert users.get(admin["id"])["disabled"] is True


def test_bootstrap_admin_recovery_ignores_member_accounts(users, database, monkeypatch):
    member = users.create_user(*ADMIN, "Root")  # member, not administrator
    disable_directly(database, member["id"])
    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", f"{ADMIN[0]}:{ADMIN[1]}")

    assert bootstrap_admin(database, users=users) is None
    record = users.get(member["id"])
    assert record["role"] == "member" and record["disabled"] is True


def test_create_app_recovers_a_locked_out_installation(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "password")
    first = create_app(tmp_path)
    admin = first.state.users.create_user(*ADMIN, "Root", "admin")
    disable_directly(first.state.auth_db, admin["id"])
    assert first.state.users.get(admin["id"])["disabled"] is True

    monkeypatch.setenv("FUNDLEX_BOOTSTRAP_ADMIN", f"{ADMIN[0]}:{ADMIN[1]}")
    second = create_app(tmp_path)

    recovered = second.state.users.get(admin["id"])
    assert recovered["role"] == "admin" and recovered["disabled"] is False
    assert second.state.users.authenticate(*ADMIN)["id"] == admin["id"]

