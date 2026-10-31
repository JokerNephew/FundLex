#!/bin/bash
# Canonical root-side publisher; install as /usr/local/sbin/fundlex-publish.
# No work happens when sourced: tests source the COMPLETE file and replace only
# the service boundary. Never validate by executing a truncated script.
#
# A release must name an explicit, auditable candidate source:
#   fundlex-publish --source DIR [--commit SHA] [--dry-run]
# --commit verifies the clean git HEAD and binds it in the retained transaction
# record. --dry-run stops after candidate staging/import/hash checks.
#
# Managed paths are renamed, not overlaid or recursively deleted. Transactions
# (including successful backups) remain beside DST for reviewed retention.
# .venv, runtime data, environment files and unit drop-ins are never replaced.
# Schema changes are NOT undone by a code rollback. Only backward-compatible
# migrations are supported; take a separate DB backup before schema releases.
set -euo pipefail

SRC=
DST=/opt/fundlex-recall-first
UNIT_DIR=/etc/systemd/system
ENV_FILE=/etc/fundlex-recall.env
LOCK_FILE=/run/lock/fundlex-publish.lock
TEMP_ROOT=/tmp/opencode
HEALTH_DELAY=4
UNITS=(fundlex-recall-api.service fundlex-recall-worker.service
  fundlex-compare-worker.service fundlex-guide-worker.service
  fundlex-feishu.service)
DIRS=(fundlex frontend guides rules tools docs tests)
FILES=(pyproject.toml uv.lock README.md AGENTS.md)
MARKER=.fundlex-engine-build
SERVICE_MARKER=.fundlex-service-build
SOURCE_COMMIT=
DRY_RUN=0
OLD_ENGINE=
OLD_SERVICE=
OLD_MANIFEST=

fail() { echo "fundlex-publish: $*" >&2; return 1; }

usage() {
  cat >&2 <<'EOF'
usage: fundlex-publish --source DIR [--commit SHA] [--dry-run]
  --source DIR   reviewed release worktree (required; never an implicit tree)
  --commit SHA   require clean tracked source at this commit (resolved by git)
  --dry-run      stage, import and hash only; never stop/replace/start services
EOF
}

# -I ignores caller PYTHONPATH, user site and cwd injection; explicitly prepend
# the checked root. env -i also keeps production DB/model/telemetry credentials
# out of API import-time initialization. All store writes go to temporary SQLite.
import_check() {
  local root=$1 python_bin=$2
  ( cd "$root"
    env -i PATH=/usr/bin:/bin HOME="$TEMP_ROOT" "$python_bin" -I -B - "$root" "$TEMP_ROOT" <<'PY'
import importlib
import os
import sys
import tempfile
from pathlib import Path

root = Path(sys.argv[1]).resolve()
if Path.cwd().resolve() != root:
    raise SystemExit("import cwd mismatch")
sys.path.insert(0, str(root))
with tempfile.TemporaryDirectory(prefix="fundlex-publish-import-", dir=sys.argv[2]) as data:
    os.environ.update(FUNDLEX_DATA_DIR=data, FUNDLEX_AUTH_MODE="dev")
    for name in ("fundlex", "fundlex.api", "fundlex.selective", "fundlex.jobs",
                 "fundlex.compare.worker", "fundlex.guide_generation.worker",
                 "fundlex.integrations.feishu.service_main"):
        module = importlib.import_module(name)
        if not Path(module.__file__).resolve().is_relative_to(root):
            raise SystemExit("module escaped import root: " + name)
    # Include every imported local submodule, not just the entrypoints.
    for name, module in tuple(sys.modules.items()):
        if name.startswith("fundlex.") and getattr(module, "__file__", None):
            if not Path(module.__file__).resolve().is_relative_to(root):
                raise SystemExit("module escaped import root: " + name)
PY
  )
}

engine_hash() {
  local root=$1 python_bin=$2
  ( cd "$root"
    env -i PATH=/usr/bin:/bin HOME="$TEMP_ROOT" "$python_bin" -I -B - "$root" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import fundlex.store as store
if not Path(store.__file__).resolve().is_relative_to(root):
    raise SystemExit("engine module escaped import root")
print(store.engine_build())
PY
  )
}

service_hash() {
  local root=$1 python_bin=$2
  ( cd "$root"
    env -i PATH=/usr/bin:/bin HOME="$TEMP_ROOT" "$python_bin" -I -B - "$root" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
import fundlex.store as store
if not Path(store.__file__).resolve().is_relative_to(root):
    raise SystemExit("engine module escaped import root")
print(store.service_build())
PY
  )
}

# Check ALL managed bytes, including assets/units and absent optional files.
# Reject symlinks in the candidate: a root-owned release must not retain links
# into the writable workspace or outside the reviewed release.
tree_manifest() {
  local root=$1 python_bin=$2
  "$python_bin" -I -B - "$root" "${DIRS[@]}" "${FILES[@]}" <<'PY'
import hashlib
import os
import sys
from pathlib import Path
root = Path(sys.argv[1])
digest = hashlib.sha256()
for name in sorted(sys.argv[2:]):
    base = root / name
    paths = [base]
    if base.is_dir() and not base.is_symlink():
        # CPython can create caches while services start or we hash files.
        for parent, dirs, files in os.walk(base, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in
                             {"__pycache__", ".pytest_cache", "node_modules"})
            paths += [Path(parent) / d for d in dirs]
            paths += [Path(parent) / f for f in sorted(files) if not f.endswith(".pyc")]
    for path in paths:
        if path.is_symlink():
            raise SystemExit("managed release contains symlink: " + str(path.relative_to(root)))
        kind = "file" if path.is_file() else "dir" if path.is_dir() else "absent"
        digest.update((str(path.relative_to(root)) + "\0" + kind + "\0").encode())
        if kind == "file":
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
print(digest.hexdigest())
PY
}

# systemd, not this shell, loads the existing secret EnvironmentFile. Runtime
# services must all be stopped before this single process initializes schemas.
# The deployment flock serializes publishers on this host. This does not lock
# manual starts, other hosts or independently running clients: those must be
# quiesced by operations; application-wide/distributed migration locks require
# changes outside this publisher.
migrate_schema() {
  systemd-run --quiet --wait --collect --unit=fundlex-publish-migrate \
    --property=User=fundlex --property=Group=fundlex \
    --property="WorkingDirectory=$DST" --property="EnvironmentFile=$ENV_FILE" \
    "$DST/.venv/bin/python" -I -B -c '
import sys
from pathlib import Path
# argv[-1] 必为 $DST（下方命令尾），生产 cwd 与其一致；显式传入避免隔离
# 环境（无 PYTHONPATH/cwd≠DST）下被 editable pth 回落到其它工作树（FL-D800）。
sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
try:
    from fundlex.config import local_data_dir, auth_db_target
    from fundlex.store import RunStore
    from fundlex.tasks import TaskStore
    from fundlex.integrations import IntegrationStore
    from fundlex.integrations.feishu.onboarding import FeishuAppOnboarding
    from fundlex.compare.store import CompareStore
    from fundlex.guide_generation.store import GuideGenerationStore
    from fundlex import guide_store
    from fundlex.db import Database
    from fundlex.auth import UserStore, SessionStore
    store = RunStore(local_data_dir())
    TaskStore(store)
    IntegrationStore(store)
    FeishuAppOnboarding(store)
    CompareStore(store)
    GuideGenerationStore(store).ensure_schema()
    guide_store._ensure_tables(store)
    auth = Database(auth_db_target())
    UserStore(auth)
    SessionStore(auth)
except Exception:
    # Do not echo database targets, driver errors or configuration values.
    raise SystemExit("fundlex-publish: serial schema initialization failed") from None
' "$DST"
}

stop_services() {
  local unit state
  systemctl stop "${UNITS[@]}" || return 1
  for unit in "${UNITS[@]}"; do
    state=$(systemctl show -p ActiveState --value "$unit") || return 1
    case "$state" in inactive|failed) ;; *) fail "$unit did not stop"; return 1 ;; esac
  done
}

check_process() {
  local unit=$1 main_pid configured_cwd actual_cwd
  systemctl is-active --quiet "$unit" || return 1
  main_pid=$(systemctl show -p MainPID --value "$unit") || return 1
  [[ "$main_pid" =~ ^[1-9][0-9]*$ ]] || { fail "$unit has no MainPID"; return 1; }
  configured_cwd=$(systemctl show -p WorkingDirectory --value "$unit") || return 1
  actual_cwd=$(readlink -e "/proc/$main_pid/cwd") || return 1
  [ "$configured_cwd" = "$DST" ] && [ "$actual_cwd" = "$DST" ] || {
    fail "$unit working directory mismatch"; return 1;
  }
  [ "$(systemctl show -p NRestarts --value "$unit")" = "${restart_baseline[$unit]}" ] || {
    fail "$unit restarted during startup"; return 1;
  }
}

capture_restart_baselines() {
  local unit
  for unit in "${UNITS[@]}"; do
    restart_baseline[$unit]=$(systemctl show -p NRestarts --value "$unit") || return 1
    [[ "${restart_baseline[$unit]}" =~ ^[0-9]+$ ]] || {
      fail "invalid restart count for $unit"; return 1;
    }
  done
}

check_api() {
  local code attempt
  # Fresh trees cold-import under production load; uvicorn child workers can
  # take far longer than a single probe to become ready. Retry the liveness
  # endpoint for up to ~120 seconds instead of failing the whole release on
  # one early probe.
  for attempt in $(seq 1 24); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 \
      http://127.0.0.1:8010/api/capabilities || true)
    if [[ "$code" = 2?? ]]; then return 0; fi
    sleep 5
  done
  fail "API capabilities check failed ($code)"
  return 1
}

start_services() {
  local unit pid
  for unit in "${UNITS[@]}"; do
    systemctl start "$unit" || return 1
    sleep "$HEALTH_DELAY"
    check_process "$unit" || return 1
    pid=$(systemctl show -p MainPID --value "$unit") || return 1
    sleep "$HEALTH_DELAY"
    check_process "$unit" || return 1
    [ "$pid" = "$(systemctl show -p MainPID --value "$unit")" ] || return 1
    echo "  $unit: active, cwd verified"
    if [ "$unit" = fundlex-recall-api.service ]; then check_api || return 1; fi
  done
}

check_logs() {
  local unit
  for unit in "${UNITS[@]}"; do
    # Drain the stream without printing or saving potentially sensitive logs.
    if ! journalctl --no-pager --since "$started_at" -u "$unit" -o cat |
      awk '/DATABASE_OPERATION_FAILED|DATABASE_CONNECTION_FAILED|Traceback|ImportError|ModuleNotFoundError/ {bad=1} END {exit bad}'; then
      fail "$unit has startup errors (inspect journal securely)"; return 1
    fi
  done
}

verify_source_commit() {
  local head
  [ -n "$SOURCE_COMMIT" ] || return 0
  command -v git >/dev/null 2>&1 || { fail "--commit requires git"; return 1; }
  head=$(git -C "$SRC" rev-parse --verify "${SOURCE_COMMIT}^{commit}" 2>/dev/null) || {
    fail "unknown source commit"; return 1;
  }
  [ "$head" = "$(git -C "$SRC" rev-parse --verify HEAD 2>/dev/null)" ] || {
    fail "source HEAD does not match --commit"; return 1;
  }
  [ -z "$(git -C "$SRC" status --porcelain 2>/dev/null)" ] || {
    fail "source has uncommitted or untracked changes"; return 1;
  }
  SOURCE_COMMIT=$head
}

write_release_record() {
  "$python_bin" -I -B - "$transaction/release-record.json" "$SRC" "${SOURCE_COMMIT:-unknown}" \
    "$manifest" "$expected" "$expected_service" "$DRY_RUN" <<'PY'
import json
import os
import sys

path, source, commit, manifest, engine, service, dry_run = sys.argv[1:]
with open(path, "w", encoding="utf-8") as handle:
    json.dump({"source": source, "commit": commit, "manifest": manifest,
               "engine": engine, "service": service, "dry_run": dry_run == "1"},
              handle, ensure_ascii=False, sort_keys=True)
    handle.write("\n")
os.chmod(path, 0o600)
PY
}

# A rollback is not complete until the restored tree and both build markers
# match the pre-deploy state. Old deployments may predate the service marker.
verify_rollback() {
  local actual
  [ -n "$OLD_MANIFEST" ] || { fail "missing pre-deploy manifest"; return 1; }
  [ "$(tree_manifest "$DST" "$python_bin")" = "$OLD_MANIFEST" ] || {
    fail "restored tree does not match pre-deploy manifest"; return 1;
  }
  if [ -n "$OLD_ENGINE" ]; then
    [ "$(cat "$DST/$MARKER" 2>/dev/null)" = "$OLD_ENGINE" ] || {
      fail "restored engine marker mismatch"; return 1;
    }
    if [[ "$OLD_ENGINE" =~ ^[a-f0-9]{64}$ ]]; then
      actual=$(engine_hash "$DST" "$python_bin") || return 1
      [ "$actual" = "$OLD_ENGINE" ] || { fail "restored engine hash mismatch"; return 1; }
    fi
  else
    [ ! -e "$DST/$MARKER" ] || { fail "unexpected restored engine marker"; return 1; }
  fi
  if [ -n "$OLD_SERVICE" ]; then
    [ "$(cat "$DST/$SERVICE_MARKER" 2>/dev/null)" = "$OLD_SERVICE" ] || {
      fail "restored service marker mismatch"; return 1;
    }
    if [[ "$OLD_SERVICE" =~ ^[a-f0-9]{64}$ ]]; then
      actual=$(service_hash "$DST" "$python_bin") || return 1
      [ "$actual" = "$OLD_SERVICE" ] || { fail "restored service hash mismatch"; return 1; }
    fi
  else
    [ ! -e "$DST/$SERVICE_MARKER" ] || { fail "unexpected restored service marker"; return 1; }
  fi
}

restore_paths() {
  local name
  # Reverse recorded intents. A failed candidate is moved aside, never deleted.
  for ((i=${#touched_paths[@]}-1; i>=0; i--)); do
    name=${touched_paths[i]}
    if [ -e "$transaction/old/$name" ] || [ -L "$transaction/old/$name" ]; then
      if [ -e "$DST/$name" ] || [ -L "$DST/$name" ]; then
        mv -T -- "$DST/$name" "$transaction/failed/$name" || return 1
      fi
      mv -T -- "$transaction/old/$name" "$DST/$name" || return 1
    elif [ -f "$transaction/absent/$name" ] && { [ -e "$DST/$name" ] || [ -L "$DST/$name" ]; }; then
      mv -T -- "$DST/$name" "$transaction/failed/$name" || return 1
    fi
  done
  for ((i=${#touched_units[@]}-1; i>=0; i--)); do
    name=${touched_units[i]}
    if [ -e "$UNIT_DIR/$name" ] || [ -L "$UNIT_DIR/$name" ]; then
      mv -T -- "$UNIT_DIR/$name" "$transaction/units-failed/$name" || return 1
    fi
    if [ -f "$transaction/units-old/$name" ]; then
      cp -p -- "$transaction/units-old/$name" "$UNIT_DIR/$name" || return 1
    fi
  done
}

publish_exit() {
  local status=$? rollback_status=0
  trap - EXIT INT TERM
  set +e
  if [ "$status" -ne 0 ] && [ "$services_touched" = 1 ]; then
    echo "fundlex-publish: failure; recovering from $transaction" >&2
    # Never rewrite code under a process that failed to stop. Leave the entire
    # journal/old/candidate trees available for an operator if recovery fails.
    stop_services
    rollback_status=$?
    if [ "$rollback_status" = 0 ]; then
      capture_restart_baselines
      rollback_status=$?
    fi
    if [ "$rollback_status" = 0 ]; then
      restore_paths
      rollback_status=$?
    fi
    if [ "$rollback_status" = 0 ]; then
      systemctl daemon-reload
      rollback_status=$?
    fi
    if [ "$rollback_status" = 0 ]; then
      start_services
      rollback_status=$?
    fi
    if [ "$rollback_status" = 0 ]; then
      verify_rollback
      rollback_status=$?
    fi
    if [ "$rollback_status" = 0 ]; then
      printf '%s\n' recovered > "$transaction/status"
      echo "fundlex-publish: code/units restored, five services and build markers verified; DB changes retained" >&2
    else
      printf '%s\n' recovery-failed > "$transaction/status"
      echo "fundlex-publish: RECOVERY FAILED; retain $transaction for manual recovery" >&2
    fi
  elif [ "$status" != 0 ] && [ -n "$transaction" ]; then
    printf '%s\n' preflight-failed > "$transaction/status"
  fi
  [ -z "$transaction" ] || echo "fundlex-publish: retained transaction $transaction"
  exit "$status"
}

main() {
  local source_arg="" name unit expected actual manifest
  while [ "$#" -gt 0 ]; do
    case "$1" in
      --source)
        [ "$#" -ge 2 ] && [ -n "$2" ] || { usage; return 1; }
        source_arg=$2
        shift 2
        ;;
      --commit)
        [ "$#" -ge 2 ] && [ -n "$2" ] || { usage; return 1; }
        SOURCE_COMMIT=$2
        shift 2
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      --help|-h)
        usage
        return 0
        ;;
      *)
        fail "unsupported argument: $1"
        usage
        return 1
        ;;
    esac
  done
  [ -n "$source_arg" ] || { fail "explicit --source is required"; usage; return 1; }
  [ "$(id -u)" = 0 ] || { fail "must run as root"; return 1; }
  # Resolve cwd-independent roots; refuse ambiguous tree and unit symlinks.
  [ -d "$source_arg" ] && [ -d "$DST" ] && [ ! -L "$DST" ] || { fail "invalid source/deployment root"; return 1; }
  SRC=$(realpath -e "$source_arg")
  DST=$(realpath -e "$DST")
  [[ "$SRC/" != "$DST/"* && "$DST/" != "$SRC/"* ]] || { fail "source/deployment overlap"; return 1; }
  [ -f "$ENV_FILE" ] && [ -d "$UNIT_DIR" ] || { fail "missing environment file/unit directory"; return 1; }
  verify_source_commit
  exec 9>"$LOCK_FILE"
  flock -n 9 || { fail "another publisher holds the deployment lock"; return 1; }
  python_bin="$DST/.venv/bin/python"
  [ -x "$python_bin" ] || { fail "missing deployment Python"; return 1; }
  for name in "${DIRS[@]}"; do
    [ -d "$SRC/$name" ] && [ ! -L "$SRC/$name" ] || { fail "missing/linked source directory $name"; return 1; }
  done
  for unit in "${UNITS[@]}"; do
    [ -f "$SRC/tools/deploy/$unit.template" ] || { fail "missing unit template $unit"; return 1; }
    [ ! -L "$UNIT_DIR/$unit" ] || { fail "linked/masked unit $unit unsupported"; return 1; }
    # Enabled state is preserved (publisher does not enable/disable services).
    case "$(systemctl is-enabled "$unit" 2>/dev/null || true)" in
      enabled|disabled|static|not-found) ;;
      *) fail "unsupported enable state for $unit"; return 1 ;;
    esac
  done

  transaction=""
  services_touched=0
  touched_paths=()
  touched_units=()
  declare -A restart_baseline=()
  trap publish_exit EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  umask 077
  transaction=$(mktemp -d "$(dirname "$DST")/.fundlex-publish-XXXXXX")
  mkdir "$transaction"/{candidate,old,absent,failed,units-old,units-new,units-failed}
  printf '%s\n' staging > "$transaction/status"
  echo "fundlex-publish: staging candidate in $transaction"
  for name in "${DIRS[@]}"; do
    ( cd "$SRC"; tar -cf - --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' --exclude='node_modules' "$name" ) |
      ( cd "$transaction/candidate"; tar -xf - )
  done
  for name in "${FILES[@]}"; do
    if [ -f "$SRC/$name" ]; then install -o root -g root -m 0644 "$SRC/$name" "$transaction/candidate/$name"; fi
  done
  chown -R root:root "$transaction/candidate"
  # A root publisher's umask must not make newly created directories unreadable
  # to the service user. Preserve executable files, normalize directory access.
  find "$transaction/candidate" -type d -exec chmod 0755 {} +
  find "$transaction/candidate" -type f -exec chmod a+r {} +
  manifest=$(tree_manifest "$transaction/candidate" "$python_bin")
  import_check "$transaction/candidate" "$python_bin"
  [ "$manifest" = "$(tree_manifest "$transaction/candidate" "$python_bin")" ] || { fail "candidate bytes changed during imports"; return 1; }
  expected=$(engine_hash "$transaction/candidate" "$python_bin")
  expected_service=$(service_hash "$transaction/candidate" "$python_bin")
  [[ "$expected" =~ ^[a-f0-9]{64}$ ]] || { fail "invalid candidate engine hash"; return 1; }
  [[ "$expected_service" =~ ^[a-f0-9]{64}$ ]] || { fail "invalid candidate service hash"; return 1; }
  printf '%s\n' "$expected" > "$transaction/candidate/$MARKER"
  printf '%s\n' "$expected_service" > "$transaction/candidate/$SERVICE_MARKER"
  chmod 0644 "$transaction/candidate/$MARKER" "$transaction/candidate/$SERVICE_MARKER"
  printf '%s\n' "$manifest" > "$transaction/candidate.manifest"
  for unit in "${UNITS[@]}"; do
    install -o root -g root -m 0644 "$transaction/candidate/tools/deploy/$unit.template" "$transaction/units-new/$unit"
    if [ -f "$UNIT_DIR/$unit" ]; then cp -p -- "$UNIT_DIR/$unit" "$transaction/units-old/$unit"; fi
  done
  OLD_MANIFEST=$(tree_manifest "$DST" "$python_bin") || { fail "cannot snapshot deployed tree"; return 1; }
  if [ -f "$DST/$MARKER" ]; then OLD_ENGINE=$(cat "$DST/$MARKER"); fi
  if [ -f "$DST/$SERVICE_MARKER" ]; then OLD_SERVICE=$(cat "$DST/$SERVICE_MARKER"); fi
  write_release_record
  printf '%s\n' prepared > "$transaction/status"
  if [ "$DRY_RUN" = 1 ]; then
    printf '%s\n' dry-run > "$transaction/status"
    echo "fundlex-publish: dry-run complete engine=$expected service=$expected_service"
    echo "fundlex-publish: candidate=$transaction/candidate record=$transaction/release-record.json"
    return 0
  fi
  # Only this point begins the deployment outage; imports above use the actual
  # deployment interpreter before modifying any production-tree bytes.
  capture_restart_baselines
  services_touched=1
  stop_services
  for name in "${DIRS[@]}" "${FILES[@]}" "$MARKER" "$SERVICE_MARKER"; do
    touched_paths+=("$name")
    printf 'path %s\n' "$name" >> "$transaction/journal"
    if [ -e "$DST/$name" ] || [ -L "$DST/$name" ]; then
      mv -T -- "$DST/$name" "$transaction/old/$name"
    else
      : > "$transaction/absent/$name"
    fi
    if [ -e "$transaction/candidate/$name" ]; then mv -T -- "$transaction/candidate/$name" "$DST/$name"; fi
  done
  for unit in "${UNITS[@]}"; do
    touched_units+=("$unit")
    printf 'unit %s\n' "$unit" >> "$transaction/journal"
    install -o root -g root -m 0644 "$transaction/units-new/$unit" "$UNIT_DIR/$unit"
  done
  systemctl daemon-reload
  [ "$manifest" = "$(tree_manifest "$DST" "$python_bin")" ] || { fail "deployed manifest mismatch"; return 1; }
  [ "$(cat "$DST/$MARKER" 2>/dev/null)" = "$expected" ] || { fail "deployed engine marker mismatch"; return 1; }
  [ "$(cat "$DST/$SERVICE_MARKER" 2>/dev/null)" = "$expected_service" ] || { fail "deployed service marker mismatch"; return 1; }
  import_check "$DST" "$python_bin"
  actual=$(engine_hash "$DST" "$python_bin")
  actual_service=$(service_hash "$DST" "$python_bin")
  [ "$expected" = "$actual" ] || { fail "deployed engine mismatch"; return 1; }
  [ "$expected_service" = "$actual_service" ] || { fail "deployed service mismatch"; return 1; }
  migrate_schema
  # journalctl --since accepts a local date/time, not the ISO T/Z form on
  # this host; use the same local clock as systemd.
  started_at=$(date '+%Y-%m-%d %H:%M:%S')
  start_services
  check_logs
  [ "$manifest" = "$(tree_manifest "$DST" "$python_bin")" ] || { fail "deployed bytes changed after startup"; return 1; }
  printf '%s\n' committed > "$transaction/status"
  echo "fundlex-publish: done engine=$actual service=$actual_service"
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
