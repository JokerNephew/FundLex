#!/usr/bin/env bash
set -euo pipefail

# Deploy only to the fixed Test installation. Production paths, services and
# ports are rejected before any write or restart occurs.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_DIR="/opt/fundlex-test"
DATA_DIR="/var/lib/fundlex-test"
ENV_FILE="/etc/fundlex-test.env"
PORT="8110"
SERVICES=(fundlex-test-api.service fundlex-test-worker.service fundlex-test-compare-worker.service)
ENV_INSTALL_TMP="${ENV_FILE}.deploy.$$"
CREDS_TMP="$DATA_DIR/.fundlex-test-credentials.$$"
PYTHON_BIN="${REPO}/.venv/bin/python"
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="/home/opencode/fundlex/.venv/bin/python"
fi
if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="/usr/bin/python3.11"
fi

cleanup() {
  sudo -n rm -f "$ENV_INSTALL_TMP" 2>/dev/null || true
  sudo -n rm -f "$CREDS_TMP" 2>/dev/null || true
}
trap cleanup EXIT

die() { echo "ERROR: $*" >&2; exit 1; }
[[ "${FUNDLEX_ENV:-}" != production ]] || die "deploy_test.sh cannot run with FUNDLEX_ENV=production"
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE; provision a Test-only environment file first"

env_value() { sudo -n awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"; }
[[ "$(env_value FUNDLEX_ENV)" == test ]] || die "$ENV_FILE must declare FUNDLEX_ENV=test"
[[ "$(env_value FUNDLEX_DATA_DIR)" == "$DATA_DIR" ]] || die "Test data root must be $DATA_DIR"
[[ "$(env_value FUNDLEX_AUTH_DATABASE)" == "$DATA_DIR/auth.sqlite3" ]] || die "Test auth DB must be $DATA_DIR/auth.sqlite3"
[[ -z "$(env_value FUNDLEX_DATABASE_URL)" ]] || die "Test must not set FUNDLEX_DATABASE_URL"
for value in "$(env_value FUNDLEX_DATA_DIR)" "$(env_value FUNDLEX_AUTH_DATABASE)" "$(env_value FUNDLEX_MODEL_LEDGER)" "$(env_value FUNDLEX_TRACE_JSONL)"; do
  [[ "$value" == "$DATA_DIR" || "$value" == "$DATA_DIR"/* ]] || die "Test runtime path escapes $DATA_DIR: $value"
done
sudo -n grep -Eq '(/var/lib/fundlex($|/)|/opt/fundlex-recall-first|fundlex-recall-(api|worker)|:8010)' "$ENV_FILE" && die "production path/service/port found in Test env"

command -v npm >/dev/null || die "npm is required for the production frontend build"
command -v rsync >/dev/null || die "rsync is required"
[[ -x "$PYTHON_BIN" ]] || die "Python 3.11 is required for backend checks"
cd "$REPO"
COMMIT="$(git rev-parse HEAD)"
DIRTY="$(git status --porcelain=v1 | wc -l | tr -d ' ')"

echo "== frontend checks =="
(cd frontend && npm ci && npm run typecheck && npm run lint && npm test && VITE_BASE_PATH=/test/ npm run build)
echo "== backend targeted checks =="
"$PYTHON_BIN" -m pytest tests/test_auth.py tests/test_tasks_api.py tests/test_guide_api.py tests/test_compare_api.py -q

echo "== install isolated code =="
sudo -n systemctl stop "${SERVICES[@]}" 2>/dev/null || true
sudo -n install -d -o fundlex -g fundlex -m 0750 "$APP_DIR" "$DATA_DIR" "$DATA_DIR/traces" "$APP_DIR/var"
sudo -n rsync -a --delete --exclude .venv --exclude var --exclude node_modules --exclude frontend/dist "$REPO/" "$APP_DIR/"
sudo -n rsync -a frontend/dist/ "$APP_DIR/frontend/dist/"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  sudo -n /usr/bin/python3.11 -m venv "$APP_DIR/.venv"
fi
sudo -n "$APP_DIR/.venv/bin/pip" install -q --upgrade pip setuptools wheel
sudo -n "$APP_DIR/.venv/bin/pip" install -q -e "$APP_DIR"
sudo -n chown -R fundlex:fundlex "$APP_DIR" "$DATA_DIR"

echo "== install Test services =="
for pair in \
  "fundlex-test-api.service tools/deploy/fundlex-test-api.service.template" \
  "fundlex-test-worker.service tools/deploy/fundlex-test-worker.service.template" \
  "fundlex-test-compare-worker.service tools/deploy/fundlex-test-compare-worker.service.template"; do
  service="${pair%% *}"; template="${pair#* }"
  sudo -n install -o root -g root -m 0644 "$template" "/etc/systemd/system/$service"
done
sudo -n install -o root -g fundlex -m 0640 "$ENV_FILE" "$ENV_INSTALL_TMP"
sudo -n sed -i "s/^FUNDLEX_COMMIT=.*/FUNDLEX_COMMIT=$COMMIT/" "$ENV_INSTALL_TMP"
if ! sudo -n grep -q '^FUNDLEX_COMMIT=' "$ENV_INSTALL_TMP"; then
  echo "FUNDLEX_COMMIT=$COMMIT" | sudo -n tee -a "$ENV_INSTALL_TMP" >/dev/null
fi
sudo -n chown root:fundlex "$ENV_INSTALL_TMP"
sudo -n chmod 0640 "$ENV_INSTALL_TMP"
sudo -n mv -f "$ENV_INSTALL_TMP" "$ENV_FILE"
sudo -n systemctl daemon-reload
sudo -n systemctl enable "${SERVICES[@]}"

if ! sudo -n test -s /etc/fundlex-test-credentials; then
  sudo -n -u fundlex bash -c "set -a; . /etc/fundlex-test.env; set +a; export FUNDLEX_TEST_CREDENTIALS_FILE='$CREDS_TMP'; '$APP_DIR/.venv/bin/python' '$APP_DIR/tools/deploy/bootstrap_test_users.py'"
  sudo -n chmod 0600 "$DATA_DIR/auth.sqlite3"
  sudo -n install -o root -g root -m 0600 "$CREDS_TMP" /etc/fundlex-test-credentials
else
  sudo -n chown fundlex:fundlex "$DATA_DIR/auth.sqlite3" 2>/dev/null || true
  sudo -n chmod 0600 "$DATA_DIR/auth.sqlite3" 2>/dev/null || true
fi
sudo -n systemctl start "${SERVICES[@]}"

echo "== Test health =="
for attempt in {1..20}; do
  if curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/capabilities" >/tmp/fundlex-test-capabilities.json; then break; fi
  sleep 1
done
[[ -s /tmp/fundlex-test-capabilities.json ]] || die "Test API did not become ready"
grep -q '"environment":"test"' /tmp/fundlex-test-capabilities.json || die "API did not identify as Test"
sudo -n systemctl is-active --quiet "${SERVICES[@]}" || die "a Test service is not active"

MANIFEST_DIR="$DATA_DIR/deployments"
sudo -n install -d -o fundlex -g fundlex -m 0750 "$MANIFEST_DIR"
sudo -n env APP_DIR="$APP_DIR" DATA_DIR="$DATA_DIR" COMMIT="$COMMIT" DIRTY="$DIRTY" \
  "$APP_DIR/.venv/bin/python" - <<'PY'
import hashlib, json, os, platform, subprocess, time
from pathlib import Path
root = Path(os.environ["APP_DIR"])
dist = root / "frontend" / "dist"
files = sorted(p for p in dist.rglob("*") if p.is_file())
build_hash = hashlib.sha256(b"".join(hashlib.sha256(p.read_bytes()).digest() for p in files)).hexdigest()
fingerprint = subprocess.check_output([str(root / ".venv/bin/pip"), "freeze"], text=True)
manifest = {"environment": "test", "commit": os.environ["COMMIT"], "dirty": bool(int(os.environ["DIRTY"])),
            "frontend_build_sha256": build_hash, "python": platform.python_version(),
            "dependency_fingerprint": hashlib.sha256(fingerprint.encode()).hexdigest(),
            "services": ["fundlex-test-api.service", "fundlex-test-worker.service", "fundlex-test-compare-worker.service"],
            "api": "127.0.0.1:8110", "data_dir": os.environ["DATA_DIR"],
            "model": os.environ.get("LLM_MODEL", "configured-in-environment-file"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
target = Path(os.environ["DATA_DIR"]) / "deployments" / (time.strftime("%Y%m%dT%H%M%SZ") + ".json")
target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
echo "Test deployment ready: http://127.0.0.1:$PORT (public path: https://fundlex.club/test/)"
