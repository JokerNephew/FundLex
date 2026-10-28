#!/usr/bin/env python3
"""Create and verify a FundLex database + object-store backup.

The tool never starts or stops services and never restores the live database.
Operator procedure:

  sudo -n /opt/fundlex-recall-first/.venv/bin/python tools/ops/fundlex_backup.py \
      create --backup-root /var/backups/fundlex --data-dir /var/lib/fundlex

Run it while the workers are quiesced (or in a maintenance window) and pass
``--quiesced`` only when that is true.  The manifest records the DB and object
hashes and the observation window so an isolated restore can be tied to one
snapshot instead of a loose collection of files.

  ... fundlex_backup.py verify /var/backups/fundlex/fundlex-...
  ... fundlex_backup.py verify /var/backups/fundlex/fundlex-... \
      --extract-objects /tmp/opencode/fundlex-restore-objects

``verify`` checks sizes/hashes, gzip/tar integrity and that the dump contains
table definitions.  It does not import a dump into MySQL; do that only in a
separate, empty database and compare counts with the manifest.  The production
restore decision remains with the operator.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn
from urllib.parse import unquote, urlsplit

FORMAT = "fundlex-backup-v1"
LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def fail(message: str) -> NoReturn:
    raise SystemExit("fundlex-backup: " + message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def secure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path, 0o700)
    return path


def secure_file(path: Path) -> Path:
    os.chmod(path, 0o600)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_mysql(url: str) -> dict[str, str]:
    parts = urlsplit(url)
    if parts.scheme not in {"mysql", "mysql+pymysql"}:
        fail("unsupported database URL scheme")
    if not parts.username or not parts.path or not parts.path.lstrip("/"):
        fail("database URL is missing a user or database name")
    try:
        port = str(parts.port or 3306)
    except ValueError:
        fail("database URL has an invalid port")
    return {
        "user": unquote(parts.username),
        "password": unquote(parts.password or ""),
        "host": parts.hostname or "127.0.0.1",
        "port": port,
        "database": unquote(parts.path.lstrip("/")),
    }


def dump_mysql(url: str, target: Path) -> dict[str, object]:
    config = parse_mysql(url)
    descriptor, name = tempfile.mkstemp(prefix=".fundlex-db-", suffix=".cnf",
                                       dir=str(target.parent))
    os.close(descriptor)
    config_path = Path(name)
    try:
        os.chmod(config_path, 0o600)
        with config_path.open("w", encoding="utf-8") as handle:
            handle.write("[client]\n")
            for key in ("user", "password", "host", "port"):
                handle.write(f"{key}={config[key]}\n")
        try:
            with target.open("wb") as output:
                result = subprocess.run(
                    ["mysqldump", f"--defaults-extra-file={config_path}",
                     "--no-tablespaces", "--single-transaction", "--quick",
                     config["database"]],
                    stdout=output, stderr=subprocess.PIPE)
        except OSError:
            target.unlink(missing_ok=True)
            fail("mysqldump is unavailable; no SQL dump was published")
        if result.returncode:
            target.unlink(missing_ok=True)
            fail("mysqldump failed; no SQL dump was published")
    finally:
        config_path.unlink(missing_ok=True)
    secure_file(target)
    return {"format": "mysqldump-gzip", "dialect": "mysql"}


def dump_sqlite(path: Path, target: Path) -> dict[str, object]:
    if not path.is_file():
        fail("SQLite database does not exist")
    descriptor, name = tempfile.mkstemp(prefix=".fundlex-sqlite-", suffix=".sqlite3",
                                       dir=str(target.parent))
    os.close(descriptor)
    temporary = Path(name)
    try:
        source = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            destination = sqlite3.connect(str(temporary))
            try:
                source.backup(destination)
            finally:
                destination.close()
        finally:
            source.close()
        with temporary.open("rb") as source_handle, gzip.open(target, "wb") as output:
            shutil.copyfileobj(source_handle, output)
    finally:
        temporary.unlink(missing_ok=True)
    secure_file(target)
    return {"format": "sqlite-gzip", "dialect": "sqlite"}


def archive_objects(objects: Path, target: Path) -> dict[str, object]:
    if not objects.is_dir():
        fail("object store directory does not exist")
    count = 0
    with tarfile.open(target, "w:gz") as archive:
        for path in sorted(objects.rglob("*")):
            if path.is_symlink():
                fail("object store contains a symlink")
            if path.is_dir():
                continue
            archive.add(path, arcname=str(path.relative_to(objects)), recursive=False)
            count += 1
    secure_file(target)
    return {"format": "tar-gzip", "files": count}


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, sort_keys=True, indent=2)
        handle.write("\n")
    secure_file(path)


def create(args: argparse.Namespace) -> int:
    os.umask(0o077)
    backup_root = secure_dir(Path(args.backup_root).expanduser())
    data_dir = Path(args.data_dir).expanduser().resolve()
    database_url = args.database_url or os.environ.get("FUNDLEX_DATABASE_URL", "")
    auth_database = os.environ.get("FUNDLEX_AUTH_DATABASE", "")
    if auth_database and auth_database != database_url:
        fail("separate FUNDLEX_AUTH_DATABASE is not covered by this single-database backup")
    if not data_dir.is_dir():
        fail("data directory does not exist")
    label = args.label or ""
    if label and not LABEL.fullmatch(label):
        fail("label must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
    name = f"fundlex-{stamp}" + (f"-{label}" if label else "")
    destination = backup_root / name
    if destination.exists():
        fail("backup destination already exists")
    secure_dir(destination)

    started = now_iso()
    db_started = now_iso()
    database_file = destination / ("database.sql.gz" if database_url else "database.sqlite3.gz")
    if database_url:
        database = dump_mysql(database_url, database_file)
    else:
        database = dump_sqlite(data_dir / "runs.sqlite3", database_file)
    db_finished = now_iso()
    objects_started = now_iso()
    objects_file = destination / "objects.tar.gz"
    objects = archive_objects(data_dir / "objects", objects_file)
    objects_finished = now_iso()

    database.update({"file": database_file.name, "sha256": sha256_file(database_file),
                     "size": database_file.stat().st_size})
    objects.update({"file": objects_file.name, "sha256": sha256_file(objects_file),
                    "size": objects_file.stat().st_size})
    manifest = {
        "format": FORMAT,
        "created_at": started,
        "data_dir": str(data_dir),
        "database": database,
        "objects": objects,
        "consistency": {
            "quiesced": bool(args.quiesced),
            "database_started_at": db_started,
            "database_finished_at": db_finished,
            "objects_started_at": objects_started,
            "objects_finished_at": objects_finished,
        },
    }
    write_manifest(destination / "manifest.json", manifest)
    print(f"backup: {destination}")
    print(f"database: {database_file.name} {database['sha256']}")
    print(f"objects: {objects_file.name} {objects['sha256']} ({objects['files']} files)")
    if not args.quiesced:
        print("warning: services were not declared quiesced; the DB/object window "
              "may not be transactionally consistent", file=sys.stderr)
    return 0


def verify_archive(path: Path, manifest: dict[str, object]) -> None:
    expected = manifest.get("sha256")
    if not isinstance(expected, str) or sha256_file(path) != expected:
        fail(f"hash mismatch: {path.name}")
    if path.stat().st_size != manifest.get("size"):
        fail(f"size mismatch: {path.name}")


def verify_database(path: Path, manifest: dict[str, object]) -> None:
    verify_archive(path, manifest)
    try:
        with gzip.open(path, "rb") as handle:
            if manifest.get("format") == "mysqldump-gzip":
                found = False
                tail = b""
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    if b"CREATE TABLE" in tail + chunk:
                        found = True
                        break
                    tail = chunk[-32:]
                if not found:
                    fail("database dump contains no CREATE TABLE")
                return
            with tempfile.NamedTemporaryFile(suffix=".sqlite3") as temporary:
                shutil.copyfileobj(handle, temporary)
                temporary.flush()
                connection = sqlite3.connect(temporary.name)
                try:
                    tables = connection.execute(
                        "SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
                finally:
                    connection.close()
    except (OSError, EOFError, sqlite3.Error):
        fail("database archive is not readable")
    if not tables:
        fail("SQLite database archive contains no tables")


def verify_objects(path: Path, manifest: dict[str, object], extract: str | None) -> None:
    verify_archive(path, manifest)
    try:
        with tarfile.open(path, "r:gz") as archive:
            members = archive.getmembers()
            if any(member.name.startswith("/") or ".." in Path(member.name).parts
                   or member.issym() or member.islnk()
                   for member in members):
                fail("object archive contains an unsafe path or link")
            if len(members) != manifest.get("files"):
                fail("object archive member count differs from the manifest")
            if extract:
                target = Path(extract).expanduser().resolve()
                if target.exists() and (not target.is_dir() or any(target.iterdir())):
                    fail("object extraction target must be absent or empty")
                secure_dir(target)
                archive.extractall(target, members=members)
    except (OSError, EOFError, tarfile.TarError):
        fail("object archive is not valid tar.gz")


def verify(args: argparse.Namespace) -> int:
    backup = Path(args.backup).expanduser().resolve()
    manifest_path = backup / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        fail("manifest.json is missing or invalid")
    if manifest.get("format") != FORMAT:
        fail("unsupported backup format")
    database = manifest.get("database")
    objects = manifest.get("objects")
    if not isinstance(database, dict) or not isinstance(objects, dict):
        fail("manifest is missing database/object entries")
    database_path = backup / str(database.get("file", ""))
    objects_path = backup / str(objects.get("file", ""))
    if not database_path.is_file() or not objects_path.is_file():
        fail("backup file is missing")
    verify_database(database_path, database)
    verify_objects(objects_path, objects, args.extract_objects)
    print("verify: hashes, gzip/tar integrity and archive structure OK")
    print("verify: database import/restore was not executed")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="fundlex_backup.py")
    commands = root.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create", help="create a DB + object backup")
    create_parser.add_argument("--backup-root", default="/var/backups/fundlex")
    create_parser.add_argument("--data-dir", default=os.environ.get("FUNDLEX_DATA_DIR", ""))
    create_parser.add_argument("--database-url", default="")
    create_parser.add_argument("--label", default="")
    create_parser.add_argument("--quiesced", action="store_true",
                               help="assert that workers were stopped for this window")
    create_parser.set_defaults(func=create)
    verify_parser = commands.add_parser("verify", help="verify hashes and archive integrity")
    verify_parser.add_argument("backup")
    verify_parser.add_argument("--extract-objects", default="")
    verify_parser.set_defaults(func=verify)
    return root


def main(argv: list[str] | None = None) -> int:
    os.umask(0o077)
    args = parser().parse_args(argv)
    if args.command == "create" and not args.data_dir:
        fail("--data-dir or FUNDLEX_DATA_DIR is required")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
