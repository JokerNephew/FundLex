"""The TLS trust store is a shipped security dependency, not an incidental pin."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIMUM = (2026, 10, 19)


def _release(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", version)
    assert match, version
    return tuple(int(part) for part in match.groups())


def test_certifi_lock_is_at_least_the_fixed_release():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    entries = [item for item in lock["package"] if item["name"] == "certifi"]
    assert len(entries) == 1, entries
    assert _release(entries[0]["version"]) >= MINIMUM
    assert entries[0]["wheels"][0]["hash"].startswith("sha256:")


def test_pyproject_declares_the_certifi_floor():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["dependencies"]
    certifi = [item for item in dependencies if item.startswith("certifi")]
    assert certifi == ["certifi>=2026.10.19,<2027"]
