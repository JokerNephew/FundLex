#!/bin/bash
# Canonical root-side publisher. Install this file as
# /usr/local/sbin/fundlex-publish after review by operations.
#
# It synchronizes the application and all three runtime units, then restarts
# and verifies API, Recall Worker and Compare Worker as one build. It never
# reads or rewrites the secret environment file and never touches MySQL data.
set -euo pipefail

SRC=/home/opencode/fundlex
DST=/opt/fundlex-recall-first
UNIT_DIR=/etc/systemd/system
ENV_FILE=/etc/fundlex-recall.env
UNITS=(
  fundlex-recall-api.service
  fundlex-recall-worker.service
  fundlex-compare-worker.service
)
DIRS=(fundlex frontend guides rules tools docs tests)
FILES=(pyproject.toml uv.lock README.md AGENTS.md)

if [ "$(id -u)" -ne 0 ]; then
  echo "fundlex-publish: must run as root" >&2
  exit 1
fi
for d in "${DIRS[@]}"; do
  [ -d "$SRC/$d" ] || { echo "fundlex-publish: missing $SRC/$d" >&2; exit 1; }
done
[ -f "$ENV_FILE" ] || { echo "fundlex-publish: missing $ENV_FILE" >&2; exit 1; }

echo "fundlex-publish: synchronizing $SRC -> $DST"
mkdir -p "$DST"
for d in "${DIRS[@]}"; do
  ( cd "$SRC" && tar -cf - --exclude='__pycache__' --exclude='.pytest_cache' --exclude='*.pyc' "$d" ) \
    | ( cd "$DST" && tar -xf - )
done
for f in "${FILES[@]}"; do
  [ -f "$SRC/$f" ] && install -o root -g root -m 0644 "$SRC/$f" "$DST/$f"
done
for d in "${DIRS[@]}"; do chown -R root:root "$DST/$d"; done

install -o root -g root -m 0644 "$SRC/tools/deploy/fundlex-recall-api.service.template" \
  "$UNIT_DIR/fundlex-recall-api.service"
install -o root -g root -m 0644 "$SRC/tools/deploy/fundlex-recall-worker.service.template" \
  "$UNIT_DIR/fundlex-recall-worker.service"
install -o root -g root -m 0644 "$SRC/tools/deploy/fundlex-compare-worker.service.template" \
  "$UNIT_DIR/fundlex-compare-worker.service"
systemctl daemon-reload

engine_hash() {
  local root=$1
  local python_bin="$root/.venv/bin/python"
  [ -x "$python_bin" ] || python_bin="$DST/.venv/bin/python"
  ( cd "$root" && PYTHONPATH="$root" "$python_bin" -c \
    'from fundlex.store import engine_build; print(engine_build())' )
}

expected_hash=$(engine_hash "$SRC")
actual_hash=$(engine_hash "$DST")
if [ "$expected_hash" != "$actual_hash" ]; then
  echo "fundlex-publish: engine hash mismatch before restart" >&2
  echo "  source=$expected_hash deployed=$actual_hash" >&2
  exit 1
fi
printf '%s\n' "$actual_hash" > "$DST/.fundlex-engine-build"
chown root:root "$DST/.fundlex-engine-build"
chmod 0644 "$DST/.fundlex-engine-build"

echo "fundlex-publish: restarting API, Recall Worker and Compare Worker"
systemctl enable "${UNITS[@]}"
systemctl restart "${UNITS[@]}"
sleep 4
for unit in "${UNITS[@]}"; do
  if systemctl is-active --quiet "$unit"; then
    echo "  $unit: active"
  else
    echo "  $unit: NOT ACTIVE" >&2
    systemctl --no-pager -n 20 status "$unit" >&2 || true
    exit 1
  fi
done

running_hash=$(engine_hash "$DST")
if [ "$running_hash" != "$actual_hash" ]; then
  echo "fundlex-publish: deployed engine hash changed after restart" >&2
  exit 1
fi
for unit in "${UNITS[@]}"; do
  main_pid=$(systemctl show -p MainPID --value "$unit")
  [ "$main_pid" != 0 ] || { echo "fundlex-publish: $unit has no MainPID" >&2; exit 1; }
  [ -r "/proc/$main_pid/root$DST/fundlex/store.py" ] || {
    echo "fundlex-publish: $unit is not running from $DST" >&2
    exit 1
  }
  echo "  $unit: build=$running_hash pid=$main_pid"
done

code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:8010/api/capabilities || true)
case "$code" in
  2??) echo "  API /api/capabilities -> $code" ;;
  *) echo "fundlex-publish: API capabilities check failed ($code)" >&2; exit 1 ;;
esac
echo "fundlex-publish: done build=$running_hash"
