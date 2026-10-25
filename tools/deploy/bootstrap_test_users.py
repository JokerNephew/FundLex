"""Create stable isolated Test accounts without printing their passwords."""
from __future__ import annotations

import json
import os
import secrets
import string
from pathlib import Path

from fundlex.auth import UserStore
from fundlex.config import assert_runtime_isolation, local_data_dir
from fundlex.db import Database


def password() -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^_-"
    return "T-" + "".join(secrets.choice(alphabet) for _ in range(28))


def main() -> int:
    assert_runtime_isolation()
    if os.environ.get("FUNDLEX_ENV") != "test":
        raise SystemExit("refusing to create users outside FUNDLEX_ENV=test")
    data_dir = local_data_dir()
    target = os.environ.get("FUNDLEX_AUTH_DATABASE") or str(data_dir / "auth.sqlite3")
    assert_runtime_isolation(auth_db=target, data_dir=data_dir)
    credentials_path = Path(os.environ.get("FUNDLEX_TEST_CREDENTIALS_FILE", "/etc/fundlex-test-credentials"))
    if credentials_path.is_symlink() or credentials_path.exists():
        raise SystemExit(f"credentials file already exists: {credentials_path}; refusing to replace it")
    credentials_path.parent.mkdir(parents=True, exist_ok=True)
    database = Database(target)
    users = UserStore(database)
    with database.connect() as conn:
        existing = conn.execute("SELECT username FROM users WHERE username IN (?, ?)",
                                ("test-admin", "test-member")).fetchall()
    if existing:
        raise SystemExit("one or more Test users already exist; use the existing credential file")
    admin_password, member_password = password(), password()
    admin = users.create_user("test-admin", admin_password, display_name="Test Administrator", role="admin")
    member = users.create_user("test-member", member_password, display_name="Test Member", role="member")
    payload = {"environment": "test",
               "admin": {"username": admin["username"], "password": admin_password},
               "member": {"username": member["username"], "password": member_password}}
    credentials_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.chmod(credentials_path, 0o600)
    print(f"created isolated Test users; credentials stored at {credentials_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
