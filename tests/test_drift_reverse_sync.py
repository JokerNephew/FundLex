"""FL-D950 守门片：drift 方向警示（疑似反向同步 → rc=3）的路径穷举。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/deploy/check_publish_drift.sh"

BASE_BODY = "#!/bin/bash\necho publisher\n"
MARKER = "# prune_retained_transactions hardening\n"


def _run(root_path: Path, repo_path: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), "--root-script", str(root_path),
         "--repo-script", str(repo_path), *extra],
        text=True, capture_output=True, timeout=30)


def _write(p: Path, body: str) -> Path:
    p.write_text(body, encoding="utf-8")
    p.chmod(0o755)
    return p


def test_no_drift_rc0(tmp_path: Path) -> None:
    root = _write(tmp_path / "root", BASE_BODY)
    repo = _write(tmp_path / "repo", BASE_BODY)
    result = _run(root, repo)
    assert result.returncode == 0 and "OK" in result.stdout


def test_plain_drift_rc1_when_no_hardening_markers(tmp_path: Path) -> None:
    root = _write(tmp_path / "root", BASE_BODY + "# newer but no hardening marker\n")
    repo = _write(tmp_path / "repo", BASE_BODY)
    result = _run(root, repo)
    assert result.returncode == 1
    assert "DRIFT" in result.stderr and "疑似反向同步" not in result.stderr


def test_suspected_reverse_sync_rc3(tmp_path: Path) -> None:
    root = _write(tmp_path / "root", BASE_BODY + MARKER)
    repo = _write(tmp_path / "repo", BASE_BODY)
    result = _run(root, repo)
    assert result.returncode == 3
    assert "疑似反向同步" in result.stderr
    assert "--ack" in result.stderr


def test_ack_falls_back_to_rc1(tmp_path: Path) -> None:
    root = _write(tmp_path / "root", BASE_BODY + MARKER)
    repo = _write(tmp_path / "repo", BASE_BODY)
    result = _run(root, repo, "--ack")
    assert result.returncode == 1
    assert "DRIFT" in result.stderr and "疑似反向同步" not in result.stderr


def test_marker_on_both_sides_stays_rc1(tmp_path: Path) -> None:
    root = _write(tmp_path / "root", BASE_BODY + MARKER + "# one more line\n")
    repo = _write(tmp_path / "repo", BASE_BODY + MARKER)
    result = _run(root, repo)
    assert result.returncode == 1
    assert "疑似反向同步" not in result.stderr


def test_unreadable_paths_rc2(tmp_path: Path) -> None:
    repo = _write(tmp_path / "repo", BASE_BODY)
    result = _run(tmp_path / "missing-root", repo)
    assert result.returncode == 2
