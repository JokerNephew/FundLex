"""Run the COMPLETE publisher against tmp_path, with every service boundary mocked.

Never invoke the production publisher or execute a prefix cut from its source.
The synthetic package exercises real isolated Python imports and SQLite writes.
"""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import subprocess
import sys
import threading

import pytest


PUBLISHER = Path(__file__).resolve().parents[1] / "tools/deploy/fundlex-publish.sh"
UNITS = (
    "fundlex-recall-api.service",
    "fundlex-recall-worker.service",
    "fundlex-compare-worker.service",
    "fundlex-feishu.service",
)
DIRS = ("fundlex", "frontend", "guides", "rules", "tools", "docs", "tests")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def release(tmp_path: Path) -> dict[str, Path]:
    paths = {name: tmp_path / name for name in ("src", "dst", "units", "temp", "state", "foreign")}
    for path in paths.values():
        path.mkdir()
    for name in DIRS:
        (paths["src"] / name).mkdir()
    # The deployment interpreter works even when the source has no virtualenv.
    python = paths["dst"] / ".venv/bin/python"
    python.parent.mkdir(parents=True)
    python.symlink_to(sys.executable)
    write(paths["src"] / "fundlex/__init__.py", "")
    write(paths["src"] / "fundlex/api.py", '''
import os
import sqlite3
from pathlib import Path
assert "FUNDLEX_DATABASE_URL" not in os.environ
assert "FUNDLEX_AUTH_DATABASE" not in os.environ
assert "FUNDLEX_BOOTSTRAP_ADMIN_PASSWORD" not in os.environ
assert "LLM_API_KEY" not in os.environ
assert os.environ["FUNDLEX_AUTH_MODE"] == "dev"
data = Path(os.environ["FUNDLEX_DATA_DIR"])
assert data.name.startswith("fundlex-publish-import-")
with sqlite3.connect(data / "runs.sqlite3") as db:
    db.execute("CREATE TABLE import_side_effect (id INTEGER)")
''')
    for name in ("selective.py", "jobs.py", "compare/__init__.py", "compare/worker.py",
                 "integrations/__init__.py", "integrations/feishu/__init__.py",
                 "integrations/feishu/service_main.py"):
        write(paths["src"] / "fundlex" / name, "")
    write(paths["src"] / "fundlex/store.py", '''
import hashlib
from pathlib import Path
def engine_build():
    return hashlib.sha256((Path(__file__).parent / "api.py").read_bytes()).hexdigest()
def service_build():
    return hashlib.sha256((Path(__file__).parent / "api.py").read_bytes() + b"service").hexdigest()
''')
    for unit in UNITS:
        write(paths["src"] / f"tools/deploy/{unit}.template", f"candidate {unit}\n")
        write(paths["units"] / unit, f"original {unit}\n")
    # Absent unit must be absent again after rollback, not an empty new unit.
    (paths["units"] / UNITS[-1]).unlink()
    # A normal checkout may have this directory; a delivery worktree may have
    # it as a symlink. It is build input, not a release path.
    (paths["src"] / "frontend/node_modules").symlink_to(paths["foreign"])
    write(paths["src"] / "README.md", "new readme\n")
    write(paths["dst"] / "README.md", "old readme\n")
    write(paths["dst"] / "AGENTS.md", "old optional file\n")
    write(paths["dst"] / ".fundlex-engine-build", "old marker\n")
    write(paths["dst"] / "fundlex/stale.py", "original module\n")
    write(paths["dst"] / "runtime/keep", "runtime survives\n")
    write(paths["foreign"] / "fundlex/__init__.py", "raise RuntimeError('wrong cwd package')\n")
    paths["env"] = tmp_path / "secret.env"
    write(paths["env"], "NEVER_READ_BY_PUBLISHER=sentinel\n")
    paths["lock"] = tmp_path / "publisher.lock"
    return paths


MOCKS = r'''
# Root, ownership and system services are all mocked, even when pytest runs as root.
id() { if [ "$1" = -u ]; then echo 0; else command id "$@"; fi; }
chown() { :; }
install() {
  local args=()
  while [ "$#" -gt 0 ]; do
    case "$1" in -o|-g) shift 2 ;; *) args+=("$1"); shift ;; esac
  done
  command install "${args[@]}"
}
systemctl() {
  printf 'systemctl %s\n' "$*" >> "$STATE/events"
  case "$1" in
    is-enabled) echo disabled ;;
    stop) : > "$STATE/stopped" ;;
    start)
      test -f "$STATE/stopped" || return 92
      if [ "$SCENARIO" = pycache-output ] && [ "$2" = fundlex-recall-api.service ]; then
        mkdir -p "$DST/fundlex/__pycache__"
        : > "$DST/fundlex/__pycache__/runtime.cpython-311.pyc"
      fi
      if [ "$SCENARIO" = runtime-tree-output ] && [ "$2" = fundlex-recall-api.service ] && [ ! -f "$STATE/runtime-used" ]; then
        : > "$STATE/runtime-used"
        : > "$DST/fundlex/runtime-output.log"
      fi
      if [ "$SCENARIO" = post-start-failure ] && [ "$2" = fundlex-compare-worker.service ] && [ ! -f "$STATE/fault-used" ]; then
        : > "$STATE/fault-used"
        return 1
      fi ;;
    show)
      case "$3" in
        ActiveState) echo inactive ;;
        NRestarts) echo 3 ;;
        MainPID) echo $$ ;;
        WorkingDirectory) echo "$DST" ;;
        *) return 93 ;;
      esac ;;
    is-active|daemon-reload) : ;;
    *) return 94 ;;
  esac
}
readlink() {
  if [ "$SCENARIO" = cwd-conflict ] && [ ! -f "$STATE/fault-used" ]; then
    : > "$STATE/fault-used"
    echo "$FOREIGN"
  else
    echo "$DST"
  fi
}
systemd-run() {
  printf 'migration %s\n' "$*" >> "$STATE/events"
  test -f "$STATE/stopped" || return 95
  test -f "$DST/fundlex/api.py" || return 96
  if [ "$SCENARIO" = migration-failure ]; then return 1; fi
}
curl() { echo 200; }
journalctl() { :; }
sleep() { :; }
'''


def run_publish(release: dict[str, Path], scenario: str = "success") -> subprocess.CompletedProcess[str]:
    # Sourcing is inert; override fixed paths before calling the complete main.
    assignments = "\n".join(
        f"{name}={shlex.quote(str(release[key]))}"
        for name, key in (("SRC", "src"), ("DST", "dst"), ("UNIT_DIR", "units"),
                          ("TEMP_ROOT", "temp"), ("ENV_FILE", "env"), ("LOCK_FILE", "lock"),
                          ("STATE", "state"), ("FOREIGN", "foreign"))
    )
    script = f"source {shlex.quote(str(PUBLISHER))}\n{assignments}\nSCENARIO={shlex.quote(scenario)}\n{MOCKS}\nmain\n"
    env = {**os.environ, "PYTHONPATH": str(release["foreign"]),
           "FUNDLEX_DATABASE_URL": "must-never-use", "FUNDLEX_AUTH_DATABASE": "must-never-use",
           "FUNDLEX_BOOTSTRAP_ADMIN_PASSWORD": "must-never-use", "LLM_API_KEY": "must-never-use"}
    return subprocess.run(["bash", "-c", script], cwd=release["foreign"], env=env,
                          text=True, capture_output=True, timeout=30)


def snapshot(root: Path) -> dict[str, bytes | str]:
    return {str(path.relative_to(root)): (os.readlink(path) if path.is_symlink() else path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def transaction(release: dict[str, Path]) -> Path:
    transactions = list(release["dst"].parent.glob(".fundlex-publish-*"))
    assert len(transactions) == 1
    return transactions[0]


def test_publish_success_stages_with_deployment_python_and_preserves_backup(release):
    result = run_publish(release)
    assert result.returncode == 0, result.stdout + result.stderr
    dst = release["dst"]
    assert (dst / "README.md").read_text() == "new readme\n"
    assert not (dst / "AGENTS.md").exists()
    assert not (dst / "fundlex/stale.py").exists()
    assert (dst / "runtime/keep").read_text() == "runtime survives\n"
    tx = transaction(release)
    assert (tx / "status").read_text().strip() == "committed"
    assert (tx / "old/fundlex/stale.py").read_text() == "original module\n"
    assert (tx / "old/.fundlex-engine-build").read_text() == "old marker\n"
    assert not list(release["temp"].iterdir())  # Temporary SQLite stores cleaned.
    assert not list(dst.rglob("*.sqlite3"))
    events = (release["state"] / "events").read_text()
    assert events.index("systemctl stop") < events.index("migration ") < events.index("systemctl start")
    starts = [line for line in events.splitlines() if line.startswith("systemctl start ")]
    assert starts == [f"systemctl start {unit}" for unit in UNITS]
    assert "--property=EnvironmentFile=" in events
    assert "NEVER_READ_BY_PUBLISHER=sentinel" not in result.stdout + result.stderr + events
    assert "systemctl enable" not in events


def test_candidate_import_failure_leaves_deployment_and_units_untouched(release):
    write(release["src"] / "fundlex/api.py", "raise ImportError('candidate missing dependency')\n")
    before, units_before = snapshot(release["dst"]), snapshot(release["units"])
    result = run_publish(release)
    assert result.returncode != 0
    assert "candidate missing dependency" in result.stderr
    assert snapshot(release["dst"]) == before
    assert snapshot(release["units"]) == units_before
    assert "systemctl stop" not in (release["state"] / "events").read_text()
    assert (transaction(release) / "status").read_text().strip() == "preflight-failed"
    assert not list(release["temp"].iterdir())


@pytest.mark.parametrize("scenario", ["post-start-failure", "migration-failure", "cwd-conflict", "runtime-tree-output"])
def test_failure_after_switch_restores_exact_old_tree_units_and_absences(release, scenario):
    before, units_before = snapshot(release["dst"]), snapshot(release["units"])
    result = run_publish(release, scenario)
    assert result.returncode != 0
    assert snapshot(release["dst"]) == before, result.stdout + result.stderr
    assert snapshot(release["units"]) == units_before
    tx = transaction(release)
    assert (tx / "status").read_text().strip() == "recovered", result.stdout + result.stderr
    assert (tx / "failed/fundlex/api.py").exists()
    assert (tx / "units-failed/fundlex-feishu.service").exists()
    events = (release["state"] / "events").read_text()
    assert events.count("systemctl stop ") == 2
    assert events.rstrip().endswith("systemctl show -p MainPID --value fundlex-feishu.service")
    if scenario == "cwd-conflict":
        assert "working directory mismatch" in result.stderr


def test_manifest_ignores_runtime_python_cache_and_excludes_node_modules(release):
    result = run_publish(release, "pycache-output")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (release["dst"] / "fundlex/__pycache__/runtime.cpython-311.pyc").exists()
    assert not (release["dst"] / "frontend/node_modules").exists()


def test_source_package_symlink_is_rejected_before_stop(release):
    (release["src"] / "fundlex/escaped.py").symlink_to(release["foreign"] / "outside.py")
    result = run_publish(release)
    assert result.returncode != 0
    assert "managed release contains symlink" in result.stderr
    assert "systemctl stop" not in (release["state"] / "events").read_text()


def test_sourcing_complete_publisher_has_no_side_effects(tmp_path):
    result = subprocess.run(["bash", "-c", f"source {shlex.quote(str(PUBLISHER))}"],
                            cwd=tmp_path, text=True, capture_output=True, timeout=10)
    assert result.returncode == 0
    assert result.stdout == result.stderr == ""
    assert list(tmp_path.iterdir()) == []


def test_real_entrypoint_imports_and_serial_migration_use_isolated_sqlite(tmp_path):
    """Exercise actual project imports/migrations, never systemd or live config."""
    root = PUBLISHER.parents[2]
    temp = tmp_path / "imports"
    temp.mkdir()
    data = tmp_path / "migration-data"
    script = f'''
source {shlex.quote(str(PUBLISHER))}
TEMP_ROOT={shlex.quote(str(temp))}
import_check {shlex.quote(str(root))} {shlex.quote(sys.executable)}
DST={shlex.quote(str(root))}
systemd-run() {{
  while [[ "$1" = --* ]]; do shift; done
  env -i PATH=/usr/bin:/bin FUNDLEX_DATA_DIR={shlex.quote(str(data))} "$@"
}}
migrate_schema
'''
    result = subprocess.run(["bash", "-c", script], cwd=tmp_path,
                            text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert list(temp.iterdir()) == []
    import sqlite3
    with sqlite3.connect(data / "runs.sqlite3") as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"batches", "documents", "tasks", "guide_versions", "external_identities", "compare_tasks"} <= tables
    with sqlite3.connect(data / "auth.db") as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "sessions"} <= tables


def test_manifest_is_stable_while_python_cache_is_written(release):
    cache = release["src"] / "fundlex/__pycache__"
    cache.mkdir()
    stop = threading.Event()
    started = threading.Event()

    def write_caches():
        while not stop.is_set():
            cache_file = cache / "changing.cpython-311.pyc"
            cache_file.write_bytes(os.urandom(128))
            cache_file.unlink()
            started.set()

    thread = threading.Thread(target=write_caches)
    thread.start()
    try:
        assert started.wait(5)
        script = f"source {shlex.quote(str(PUBLISHER))}\ntree_manifest {shlex.quote(str(release['src']))} {shlex.quote(sys.executable)}\n"
        result = subprocess.run(["bash", "-c", script], text=True, capture_output=True, timeout=10)
        assert result.returncode == 0, result.stderr
    finally:
        stop.set()
        thread.join(timeout=5)
    baseline = subprocess.run(["bash", "-c", script], text=True, capture_output=True, timeout=10)
    assert baseline.returncode == 0, baseline.stderr
    assert baseline.stdout == result.stdout
