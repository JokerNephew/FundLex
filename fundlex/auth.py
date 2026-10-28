"""Account and session persistence for FundLex.

Standard library only. Passwords use ``hashlib.scrypt`` (n=2**14, r=8, p=1,
dklen=32) with a 16-byte random salt and are stored as
``scrypt$n$r$p$salt_b64$hash_b64``. Session tokens are
``secrets.token_urlsafe(32)`` values; the database only keeps their SHA-256
digest, so a leaked database row cannot be replayed as a bearer token.

The module relies on the shared :mod:`fundlex.db` adapter so the same code
path works for SQLite (local runtime) and MySQL (production) targets.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import re
import secrets
import time
import uuid

from .db import Database, Row


class AuthError(Exception):
    """Base class for account and session failures."""


class ValidationError(AuthError, ValueError):
    """A username, password, display name or role violates the local policy."""


class UserExists(AuthError):
    """The requested username is already taken."""


class UserNotFound(AuthError):
    """The referenced account does not exist."""


class InvalidCredentials(AuthError):
    """The supplied username or password is wrong."""


class AccountDisabled(AuthError):
    """The account exists but an administrator disabled it."""


class LastAdminError(AuthError):
    """Disabling the target would leave no enabled administrator.

    ``code`` is the stable HTTP error code; the argument carries the target
    account id for operator diagnostics and is never exposed by the API.
    """

    code = "LAST_ADMIN_REQUIRED"


USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 1024
DISPLAY_NAME_MAX_LENGTH = 128
ROLES = ("admin", "member")

SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32
SALT_BYTES = 16
MAX_SCRYPT_N = 2**20

DEFAULT_SESSION_HOURS = 12.0
SESSION_HOURS_ENV = "FUNDLEX_SESSION_HOURS"
BOOTSTRAP_ADMIN_ENV = "FUNDLEX_BOOTSTRAP_ADMIN"

USERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'member',
    disabled INTEGER NOT NULL DEFAULT 0,
    created_at DOUBLE NOT NULL,
    updated_at DOUBLE NOT NULL
)
"""

SESSIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    created_at DOUBLE NOT NULL,
    expires_at DOUBLE NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
)
"""

_USER_COLUMNS = "id, username, display_name, role, disabled, created_at, updated_at"

_DUMMY_HASH: str | None = None


def hash_password(password: str) -> str:
    """Hash a plaintext password with scrypt and a fresh 16-byte salt."""
    if not isinstance(password, str):
        raise ValidationError("password must be a string")
    salt = os.urandom(SALT_BYTES)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R,
                            p=SCRYPT_P, dklen=SCRYPT_DKLEN)
    return "scrypt${}${}${}${}${}".format(
        SCRYPT_N, SCRYPT_R, SCRYPT_P,
        base64.b64encode(salt).decode("ascii"), base64.b64encode(digest).decode("ascii"))


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash using a constant-time compare."""
    if not isinstance(password, str) or not isinstance(stored, str):
        return False
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4], validate=True)
        expected = base64.b64decode(parts[5], validate=True)
    except (ValueError, TypeError, binascii.Error):
        return False
    if not salt or not expected or not 2 <= n <= MAX_SCRYPT_N or not 1 <= r <= 64 or not 1 <= p <= 16:
        return False
    try:
        digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=len(expected))
    except (ValueError, OverflowError):
        return False
    return hmac.compare_digest(digest, expected)


def _burn_password_check(password: str) -> None:
    """Spend the same scrypt work for unknown usernames to avoid user enumeration."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(secrets.token_urlsafe(24))
    verify_password(password if isinstance(password, str) else "", _DUMMY_HASH)


def _validate_username(username: str) -> str:
    if not isinstance(username, str) or not USERNAME_PATTERN.fullmatch(username):
        raise ValidationError("username must be 3-64 characters of letters, digits, '_', '.' or '-'")
    return username


def _validate_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < PASSWORD_MIN_LENGTH:
        raise ValidationError(f"password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > PASSWORD_MAX_LENGTH:
        raise ValidationError(f"password must be at most {PASSWORD_MAX_LENGTH} characters")
    return password


def _validate_role(role: str) -> str:
    if not isinstance(role, str) or role not in ROLES:
        raise ValidationError("role must be 'admin' or 'member'")
    return role


def _validate_display_name(display_name: str) -> str:
    if display_name is None:
        return ""
    if not isinstance(display_name, str) or len(display_name.strip()) > DISPLAY_NAME_MAX_LENGTH:
        raise ValidationError(f"display name must be at most {DISPLAY_NAME_MAX_LENGTH} characters")
    return display_name.strip()


def _record(row: Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "display_name": row["display_name"] or "",
        "role": row["role"] or "member",
        "disabled": bool(row["disabled"]),
        "created_at": float(row["created_at"]),
        "updated_at": float(row["updated_at"]),
    }


class UserStore:
    """Accounts persisted through the shared database adapter."""

    def __init__(self, db: Database, *, clock=None):
        self.db = db
        self._clock = clock or time.time
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(USERS_SCHEMA)

    def _fetch(self, column: str, value) -> Row | None:
        with self.db.connect() as conn:
            return conn.execute(f"SELECT * FROM users WHERE {column}=?", (value,)).fetchone()

    def get(self, user_id: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id=?", (user_id,)).fetchone()
        return _record(row) if row is not None else None

    def list_users(self) -> list[dict]:
        with self.db.connect() as conn:
            rows = conn.execute(
                f"SELECT {_USER_COLUMNS} FROM users ORDER BY created_at, username").fetchall()
        return [_record(row) for row in rows]

    def create_user(self, username: str, password: str, display_name: str = "", role: str = "member") -> dict:
        username = _validate_username(username)
        _validate_password(password)
        display_name = _validate_display_name(display_name)
        role = _validate_role(role)
        now = float(self._clock())
        user_id = uuid.uuid4().hex
        with self.db.connect() as conn:
            if conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone() is not None:
                raise UserExists(username)
            try:
                conn.execute(
                    "INSERT INTO users (id, username, password_hash, display_name, role, disabled,"
                    " created_at, updated_at) VALUES (?,?,?,?,?,0,?,?)",
                    (user_id, username, hash_password(password), display_name, role, now, now))
            except Exception as exc:
                # SQLite raises IntegrityError directly; MySQL errors are wrapped
                # into DatabaseError by the adapter. Both mention the constraint.
                message = str(exc).lower()
                if "unique" in message or "duplicate" in message:
                    raise UserExists(username) from exc
                raise
        record = self.get(user_id)
        if record is None:  # pragma: no cover - the row was committed in this call
            raise AuthError("account was not persisted")
        return record

    def authenticate(self, username: str, password: str) -> dict:
        """Return the account record or raise; disabled accounts are rejected."""
        lookup = username.strip() if isinstance(username, str) else ""
        row = self._fetch("username", lookup)
        if row is None:
            _burn_password_check(password)
            raise InvalidCredentials("invalid username or password")
        if not verify_password(password if isinstance(password, str) else "", row["password_hash"]):
            raise InvalidCredentials("invalid username or password")
        if row["disabled"]:
            raise AccountDisabled("account is disabled")
        return _record(row)

    def change_password(self, user_id: str, old_password: str, new_password: str) -> dict:
        _validate_password(new_password)
        row = self._fetch("id", user_id)
        if row is None:
            raise UserNotFound(user_id)
        if not verify_password(old_password if isinstance(old_password, str) else "", row["password_hash"]):
            raise InvalidCredentials("current password is incorrect")
        now = float(self._clock())
        with self.db.connect() as conn:
            conn.execute("UPDATE users SET password_hash=?, updated_at=? WHERE id=?",
                         (hash_password(new_password), now, user_id))
        record = self.get(user_id)
        if record is None:  # pragma: no cover - the row exists in this call
            raise UserNotFound(user_id)
        return record

    def set_disabled(self, user_id: str, disabled: bool) -> dict:
        """Enable or disable an account, never leaving zero enabled admins.

        Disabling the last enabled administrator raises :class:`LastAdminError`.
        The account lookup, the administrator count and the update run in one
        transaction: SQLite takes the write lock up front (``BEGIN IMMEDIATE``)
        and MySQL locks the enabled administrator rows, so two concurrent
        requests cannot each observe the other's administrator as available.
        Re-enabling, disabling a non-administrator and disabling an account
        that is already disabled are unaffected.
        """
        now = float(self._clock())
        with self.db.connect() as conn:
            if disabled and self.db.dialect != "mysql":
                conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                f"SELECT {_USER_COLUMNS} FROM users WHERE id=?", (user_id,)).fetchone()
            if row is None:
                raise UserNotFound(user_id)
            if bool(row["disabled"]) == bool(disabled):
                return _record(row)
            if disabled and row["role"] == "admin":
                admins = "SELECT id FROM users WHERE role='admin' AND disabled=0"
                if self.db.dialect == "mysql":
                    admins += " FOR UPDATE"
                if len(conn.execute(admins).fetchall()) <= 1:
                    raise LastAdminError(user_id)
            conn.execute("UPDATE users SET disabled=?, updated_at=? WHERE id=?",
                         (1 if disabled else 0, now, user_id))
            updated = conn.execute(
                f"SELECT {_USER_COLUMNS} FROM users WHERE id=?", (user_id,)).fetchone()
        if updated is None:  # pragma: no cover - the row exists in this call
            raise UserNotFound(user_id)
        return _record(updated)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SessionStore:
    """Bearer sessions persisted as SHA-256 token digests."""

    def __init__(self, db: Database, *, hours: float | None = None, clock=None):
        self.db = db
        self._clock = clock or time.time
        if hours is None:
            try:
                hours = float(os.environ.get(SESSION_HOURS_ENV, "") or DEFAULT_SESSION_HOURS)
            except ValueError:
                raise ValidationError(f"{SESSION_HOURS_ENV} must be a number") from None
        if hours <= 0:
            raise ValidationError("session lifetime must be positive")
        self.hours = float(hours)
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.db.connect() as conn:
            conn.executescript(SESSIONS_SCHEMA)

    def login(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        now = float(self._clock())
        with self.db.connect() as conn:
            conn.execute("INSERT INTO sessions (token_hash, user_id, created_at, expires_at, revoked)"
                         " VALUES (?,?,?,?,0)",
                         (_token_hash(token), user_id, now, now + self.hours * 3600.0))
        return token

    def resolve(self, token: str) -> str | None:
        """Return the user id for a live token, or None when revoked/expired."""
        if not isinstance(token, str) or not token or len(token) > 512:
            return None
        with self.db.connect() as conn:
            row = conn.execute("SELECT user_id, expires_at, revoked FROM sessions WHERE token_hash=?",
                               (_token_hash(token),)).fetchone()
        if row is None or row["revoked"]:
            return None
        if float(row["expires_at"]) <= float(self._clock()):
            return None
        return row["user_id"]

    def logout(self, token: str) -> bool:
        if not isinstance(token, str) or not token:
            return False
        with self.db.connect() as conn:
            conn.execute("UPDATE sessions SET revoked=1 WHERE token_hash=? AND revoked=0",
                         (_token_hash(token),))
        return True

    def revoke_user_sessions(self, user_id: str, *, keep_token: str | None = None) -> None:
        """Revoke every session of an account; optionally keep the current token."""
        keep_hash = _token_hash(keep_token) if isinstance(keep_token, str) and keep_token else None
        with self.db.connect() as conn:
            if keep_hash is None:
                conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND revoked=0", (user_id,))
            else:
                conn.execute("UPDATE sessions SET revoked=1 WHERE user_id=? AND revoked=0 AND token_hash<>?",
                             (user_id, keep_hash))


def bootstrap_admin(db: Database, users: UserStore | None = None) -> dict | None:
    """Seed the first administrator from ``FUNDLEX_BOOTSTRAP_ADMIN``.

    The environment value has the form ``username:password``. It is read once,
    never logged and never persisted; only the scrypt hash reaches the database.

    When accounts exist but every administrator is disabled, the configured
    account recovers the installation only if all of the following hold: the
    username is exactly the configured one, it is still an administrator, and
    the configured password matches its stored hash. No other account is
    touched, so a stale or unrelated secret cannot re-enable anyone.
    """
    raw = os.environ.get(BOOTSTRAP_ADMIN_ENV)
    if not raw:
        return None
    store = users if users is not None else UserStore(db)
    with db.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        enabled_admins = conn.execute(
            "SELECT COUNT(*) FROM users WHERE role='admin' AND disabled=0").fetchone()[0]
    if total and enabled_admins:
        return None
    username, separator, password = raw.partition(":")
    if not separator:
        raise ValidationError(f"{BOOTSTRAP_ADMIN_ENV} must be formatted as 'username:password'")
    if total:
        return _recover_bootstrap_admin(store, username, password)
    try:
        return store.create_user(username, password, display_name="Bootstrap Administrator", role="admin")
    except UserExists:
        return None


def _recover_bootstrap_admin(store: UserStore, username: str, password: str) -> dict | None:
    """Re-enable the configured administrator after an out-of-band lockout."""
    row = store._fetch("username", username)
    if row is None or row["role"] != "admin" or not row["disabled"]:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return store.set_disabled(row["id"], False)
