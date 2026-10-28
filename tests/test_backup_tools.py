"""Backup permission, manifest and non-destructive verification checks."""
from __future__ import annotations

import io
import json
import os
import sqlite3
import stat
import subprocess
import sys
import tarfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools/ops/fundlex_backup.py"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    environment = {key: value for key, value in os.environ.items()
                   if key not in {"FUNDLEX_DATABASE_URL", "FUNDLEX_AUTH_DATABASE",
                                  "FUNDLEX_DATA_DIR"}}
    return subprocess.run([sys.executable, str(SCRIPT), *args], env=environment,
                          text=True, capture_output=True, timeout=60)


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    data = tmp_path / "data"
    (data / "objects").mkdir(parents=True)
    (data / "objects" / "sha").mkdir()
    (data / "objects" / "sha" / "contract.docx").write_bytes(b"object bytes")
    database = data / "runs.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO tasks VALUES ('t1')")
    return data, tmp_path / "backups"


def test_backup_uses_private_permissions_and_consistent_manifest(tmp_path):
    data, root = _fixture(tmp_path)
    # An existing directory with broad permissions is narrowed by the tool.
    root.mkdir()
    os.chmod(root, 0o755)
    result = _run("create", "--backup-root", str(root), "--data-dir", str(data),
                  "--label", "unit-test", "--quiesced")
    assert result.returncode == 0, result.stdout + result.stderr
    backups = list(root.glob("fundlex-*"))
    assert len(backups) == 1
    backup = backups[0]
    assert _mode(root) == 0o700
    assert _mode(backup) == 0o700
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["format"] == "fundlex-backup-v1"
    assert manifest["consistency"]["quiesced"] is True
    assert manifest["database"]["dialect"] == "sqlite"
    assert manifest["objects"]["files"] == 1
    for name in ("database.sqlite3.gz", "objects.tar.gz", "manifest.json"):
        path = backup / name
        assert path.is_file()
        assert _mode(path) == 0o600
    assert not list(backup.glob(".fundlex-*"))

    verified = _run("verify", str(backup))
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "database import/restore was not executed" in verified.stdout

    extracted = tmp_path / "restored-objects"
    restored = _run("verify", str(backup), "--extract-objects", str(extracted))
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert (extracted / "sha" / "contract.docx").read_bytes() == b"object bytes"
    assert _mode(extracted) == 0o700


def test_backup_without_quiesced_is_marked_and_warned(tmp_path):
    data, root = _fixture(tmp_path)
    result = _run("create", "--backup-root", str(root), "--data-dir", str(data))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "not declared quiesced" in result.stderr
    backup = next(root.glob("fundlex-*"))
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["consistency"]["quiesced"] is False


def test_verify_rejects_corrupted_or_unsafe_archives(tmp_path):
    data, root = _fixture(tmp_path)
    assert _run("create", "--backup-root", str(root), "--data-dir", str(data),
                "--quiesced").returncode == 0
    backup = next(root.glob("fundlex-*"))
    objects = backup / "objects.tar.gz"
    objects.write_bytes(objects.read_bytes() + b"corrupt")
    corrupted = _run("verify", str(backup))
    assert corrupted.returncode != 0
    assert "hash mismatch" in corrupted.stderr

    # Rebuild a superficially valid archive with an unsafe member and update the
    # manifest hashes; verification must still reject the member path.
    unsafe = io.BytesIO()
    with tarfile.open(fileobj=unsafe, mode="w:gz") as archive:
        payload = b"escape"
        member = tarfile.TarInfo("../escape.txt")
        member.size = len(payload)
        archive.addfile(member, io.BytesIO(payload))
    objects.write_bytes(unsafe.getvalue())
    manifest_path = backup / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    import hashlib
    manifest["objects"]["sha256"] = hashlib.sha256(objects.read_bytes()).hexdigest()
    manifest["objects"]["size"] = objects.stat().st_size
    manifest["objects"]["files"] = 1
    manifest_path.write_text(json.dumps(manifest))
    rejected = _run("verify", str(backup))
    assert rejected.returncode != 0
    assert "unsafe path" in rejected.stderr
