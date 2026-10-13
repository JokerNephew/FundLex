"""Small database adapter for the SQLite and MySQL backends.

The store layer keeps writing SQLite-flavoured SQL.  ``Database`` opens the
configured backend and, for ``mysql://`` targets, translates the small set of
statements that differ (placeholders, PRAGMAs, ``INSERT OR REPLACE``,
``BEGIN IMMEDIATE``, TEXT column types).  SQLite targets are passed through
untouched so the local profile keeps its exact previous behaviour.
"""

from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import parse_qs, unquote, urlsplit

pymysql = None  # Optional dependency, imported on the first mysql:// use.


class DatabaseError(Exception):
    """Connection or execution failure callers may retry or report."""


class Row:
    """Minimal ``sqlite3.Row`` work-alike shared by both dialects.

    Supports ``row["column"]``, ``row[index]``, ``row[start:stop]``,
    iteration over values, ``keys()``, ``len()`` and ``dict(row)``.
    """

    __slots__ = ("_keys", "_values")

    def __init__(self, keys, values):
        self._keys = tuple(keys)
        self._values = tuple(values)

    def keys(self) -> list[str]:
        return list(self._keys)

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        try:
            return self._values[self._keys.index(key)]
        except ValueError:
            raise IndexError(f"no such column: {key!r}") from None

    def __iter__(self):
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)

    def __contains__(self, value) -> bool:
        return value in self._values

    def __eq__(self, other):
        if isinstance(other, Row):
            return self._values == other._values
        if isinstance(other, tuple):
            return self._values == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._values)

    def __repr__(self) -> str:
        return f"Row({dict(zip(self._keys, self._values))!r})"


class Cursor:
    """Cursor wrapper exposing sqlite3-like row access over either backend."""

    def __init__(self, raw: Any | None = None):
        self._raw = raw

    @property
    def rowcount(self) -> int:
        return 0 if self._raw is None else self._raw.rowcount

    @property
    def description(self):
        return None if self._raw is None else self._raw.description

    @property
    def lastrowid(self):
        return None if self._raw is None else self._raw.lastrowid

    def _wrap(self, value):
        if value is None or isinstance(value, Row):
            return value
        names = [column[0] for column in (self._raw.description or ())]
        return Row(names, value)

    def fetchone(self):
        return None if self._raw is None else self._wrap(self._raw.fetchone())

    def fetchall(self) -> list[Row]:
        return [] if self._raw is None else [self._wrap(item) for item in self._raw.fetchall()]

    def close(self) -> None:
        if self._raw is not None:
            self._raw.close()

    def __iter__(self) -> Iterator[Row]:
        if self._raw is None:
            return
        for item in self._raw:
            yield self._wrap(item)


class Connection:
    """Connection wrapper with ``execute``/``executemany``/``executescript``."""

    def __init__(self, raw, database: "Database"):
        self._raw = raw
        self._database = database

    def _run(self, statement: str, params, *, many: bool):
        raw_cursor = self._raw.cursor()
        try:
            if many:
                raw_cursor.executemany(statement, [tuple(item) for item in params])
            elif self._database.dialect == "mysql":
                raw_cursor.execute(statement, tuple(params) if params else None)
            else:
                raw_cursor.execute(statement, tuple(params))
        except Exception as exc:
            wrapped = self._database.wrap_error(exc)
            if wrapped is exc:
                raise
            raise wrapped from exc
        return Cursor(raw_cursor)

    def execute(self, sql: str, params=()) -> Cursor:
        statement = sql
        if self._database.dialect == "mysql":
            action, payload = self._database.prepare(statement)
            if action == "skip":
                return Cursor()
            if action == "create_index":
                index, table, create = payload
                if self._index_exists(table, index):
                    return Cursor()
                statement = create
            else:
                statement = payload
        return self._run(statement, params, many=False)

    def executemany(self, sql: str, params_seq) -> Cursor:
        statement = sql
        if self._database.dialect == "mysql":
            action, payload = self._database.prepare(statement)
            if action == "skip":
                return Cursor()
            statement = payload if action == "run" else payload[2]
        return self._run(statement, params_seq, many=True)

    def executescript(self, script: str) -> Cursor:
        if self._database.dialect != "mysql":
            return Cursor(self._raw.executescript(script))
        cursor = Cursor()
        for statement in _split_statements(script):
            cursor = self.execute(statement)
        return cursor

    def _index_exists(self, table: str, index: str) -> bool:
        raw_cursor = self._raw.cursor()
        raw_cursor.execute(
            "SELECT 1 FROM information_schema.statistics "
            "WHERE table_schema=DATABASE() AND table_name=%s AND index_name=%s",
            (table, index),
        )
        return raw_cursor.fetchone() is not None

    def commit(self) -> None:
        self._raw.commit()

    def rollback(self) -> None:
        self._raw.rollback()

    def close(self) -> None:
        self._raw.close()


class Database:
    """Open a SQLite file/URL or a MySQL URL behind one sqlite3-like API."""

    def __init__(self, target: str | Path, *, timeout: float = 30.0):
        if isinstance(target, Path):
            target = str(target)
        if not isinstance(target, str) or not target.strip():
            raise DatabaseError("database target must be a file path or URL")
        target = target.strip()
        self.target = target
        self.timeout = timeout
        self.dialect = "sqlite"
        self.path: Path | None = None
        self._sqlite_target: str | None = None
        self._mysql: dict[str, Any] | None = None
        lowered = target.lower()
        if lowered.startswith(("mysql://", "mysql+pymysql://")):
            self.dialect = "mysql"
            self._mysql = _parse_mysql_url(target)
        elif lowered.startswith("sqlite://"):
            self._sqlite_target = _sqlite_target(target)
            if self._sqlite_target != ":memory:":
                self.path = Path(self._sqlite_target).expanduser().resolve()
        else:
            if "://" in target:
                raise DatabaseError(f"unsupported database URL scheme: {target.split('://', 1)[0]}://")
            if target == ":memory:":
                self._sqlite_target = ":memory:"
            else:
                self.path = Path(target).expanduser().resolve()
                self._sqlite_target = str(self.path)

    @classmethod
    def from_env(cls, default: str | Path) -> "Database":
        """Use ``FUNDLEX_DATABASE_URL`` when set, else the caller's default path."""
        return cls(os.environ.get("FUNDLEX_DATABASE_URL") or default)

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        """Commit on success, roll back on error, always close."""
        raw = self._open()
        try:
            connection = Connection(raw, self)
            try:
                yield connection
            except BaseException:
                raw.rollback()
                raise
            else:
                raw.commit()
        finally:
            raw.close()

    def _open(self):
        if self.dialect == "mysql":
            module = _pymysql_module()
            config = self._mysql or {}
            try:
                return module.connect(
                    host=config.get("host", "127.0.0.1"), port=config.get("port", 3306),
                    user=config.get("user", ""), password=config.get("password", ""),
                    database=config.get("database", ""), charset=config.get("charset", "utf8mb4"),
                    autocommit=False, connect_timeout=int(self.timeout),
                )
            except module.MySQLError as exc:
                raise DatabaseError(str(exc)) from exc
        return sqlite3.connect(self._sqlite_target or ":memory:", timeout=self.timeout)

    def wrap_error(self, exc: Exception) -> Exception:
        """Map driver errors to ``DatabaseError``; SQLite errors pass through."""
        if self.dialect == "mysql":
            module = _pymysql_module()
            if isinstance(exc, module.MySQLError):
                return DatabaseError(f"{exc.__class__.__name__}: {exc}")
        return exc

    def prepare(self, sql: str) -> tuple[str, Any]:
        """Translate one SQLite-flavoured statement for the active dialect.

        Returns ``("run", statement)``, ``("skip", None)`` for no-op PRAGMAs,
        or ``("create_index", (index, table, statement))`` when existence must
        be checked first (MySQL lacks ``CREATE INDEX IF NOT EXISTS``).
        """
        if self.dialect != "mysql":
            return ("run", sql)
        statement = sql.strip()
        if _PRAGMA.match(statement):
            table_info = _PRAGMA_TABLE_INFO.match(statement)
            if table_info:
                table = table_info.group(1)
                return ("run", "SELECT column_name AS name FROM information_schema.columns "
                               f"WHERE table_schema=DATABASE() AND table_name='{table}'")
            # foreign_keys/journal_mode and other SQLite PRAGMAs have no MySQL equivalent.
            return ("skip", None)
        index = _CREATE_INDEX_IF_NOT_EXISTS.match(statement)
        if index:
            create = _IF_NOT_EXISTS.sub("", statement, count=1)
            return ("create_index", (index.group(1), index.group(2), create))
        if statement.upper().startswith(("CREATE TABLE", "ALTER TABLE")):
            statement = _translate_text_columns(statement)
        statement = _INSERT_OR_REPLACE.sub("REPLACE INTO", statement)
        statement = _BEGIN_IMMEDIATE.sub("START TRANSACTION", statement)
        statement = _SQLITE_MASTER.sub(_sqlite_master_replacement, statement)
        return ("run", statement.replace("?", "%s"))

    def __repr__(self) -> str:
        return f"Database({self.dialect!r}, {self.target!r})"


def _pymysql_module():
    global pymysql
    if pymysql is None:
        try:
            import pymysql as module
        except ImportError as exc:  # pragma: no cover - dependency is declared
            raise DatabaseError(
                "pymysql is required for mysql:// targets; install 'pymysql>=1.1'"
            ) from exc
        pymysql = module
    return pymysql


def _parse_mysql_url(target: str) -> dict[str, Any]:
    parts = urlsplit(target)
    query = {key: values[-1] for key, values in parse_qs(parts.query).items()}
    try:
        port = parts.port or 3306
    except ValueError as exc:
        raise DatabaseError(f"invalid mysql port in target: {exc}") from None
    return {
        "host": parts.hostname or "127.0.0.1",
        "port": port,
        "user": unquote(parts.username) if parts.username else "",
        "password": unquote(parts.password) if parts.password else "",
        "database": unquote(parts.path.lstrip("/")),
        "charset": query.get("charset") or "utf8mb4",
    }


def _sqlite_target(target: str) -> str:
    rest = target[len("sqlite://"):]
    if rest.startswith("//"):
        rest = rest[1:]  # sqlite:////absolute/path
    elif rest.startswith("/"):
        rest = rest[1:]  # sqlite:///relative/path or sqlite:///C:/path
    return rest or ":memory:"


def _split_statements(script: str) -> list[str]:
    """Split a multi-statement script on semicolons outside quoted literals."""
    statements: list[str] = []
    current: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(script):
        char = script[index]
        if quote:
            current.append(char)
            if char == quote:
                if index + 1 < len(script) and script[index + 1] == quote:
                    current.append(script[index + 1])
                    index += 1
                else:
                    quote = None
        elif char in ("'", '"', "`"):
            quote = char
            current.append(char)
        elif char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
        index += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


_PRAGMA = re.compile(r"^PRAGMA\b", re.IGNORECASE)
_PRAGMA_TABLE_INFO = re.compile(r"^PRAGMA\s+table_info\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)\s*;?\s*$", re.IGNORECASE)
_CREATE_INDEX_IF_NOT_EXISTS = re.compile(
    r"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+IF\s+NOT\s+EXISTS\s+([A-Za-z_][A-Za-z0-9_]*)\s+ON\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)
_IF_NOT_EXISTS = re.compile(r"\bIF\s+NOT\s+EXISTS\s+", re.IGNORECASE)
_INSERT_OR_REPLACE = re.compile(r"\bINSERT\s+OR\s+REPLACE\s+INTO\b", re.IGNORECASE)
_BEGIN_IMMEDIATE = re.compile(r"\bBEGIN\s+IMMEDIATE\b", re.IGNORECASE)
_SQLITE_MASTER = re.compile(
    r"FROM\s+sqlite_master\s+WHERE\s+type\s*=\s*'table'\s+AND\s+name\s*=\s*'([A-Za-z_][A-Za-z0-9_]*)'",
    re.IGNORECASE,
)
_TEXT_COLUMN = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s+TEXT\b", re.IGNORECASE)
_MEDIUMTEXT_DEFAULT = re.compile(
    r"MEDIUMTEXT(\s+NOT\s+NULL)?\s+DEFAULT\s+('(?:[^']|'')*')", re.IGNORECASE
)
_MEDIUMTEXT_COLUMNS = frozenset({"report_json", "metadata"})
# Human-facing names may exceed 255 characters (upload manifest allows longer);
# MySQL's unique-key limit still applies because these columns are not keyed.
_WIDE_VARCHAR_COLUMNS = frozenset({"filename", "name", "display_name"})


def _sqlite_master_replacement(match: re.Match) -> str:
    return ("FROM information_schema.tables WHERE table_schema=DATABASE() "
            f"AND table_name='{match.group(1)}'")


def _translate_text_columns(statement: str) -> str:
    """MySQL keys need bounded VARCHAR columns; report/metadata keep full text."""
    def replace(match: re.Match) -> str:
        name = match.group(1)
        lowered = name.lower()
        if lowered in _MEDIUMTEXT_COLUMNS:
            kind = "MEDIUMTEXT"
        elif lowered in _WIDE_VARCHAR_COLUMNS:
            kind = "VARCHAR(768)"
        else:
            kind = "VARCHAR(255)"
        return f"{name} {kind}"

    translated = _TEXT_COLUMN.sub(replace, statement)
    # MySQL only accepts TEXT defaults as parenthesised expressions.
    return _MEDIUMTEXT_DEFAULT.sub(
        lambda match: f"MEDIUMTEXT{match.group(1) or ''} DEFAULT ({match.group(2)})", translated
    )
