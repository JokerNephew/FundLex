#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="/var/lib/fundlex-test"
APP_DIR="/opt/fundlex-test"
ENV_FILE="/etc/fundlex-test.env"
SERVICES=(fundlex-test-api.service fundlex-test-worker.service fundlex-test-compare-worker.service)
CREDS_TMP="$DATA_DIR/.fundlex-test-credentials.$$"
die() { echo "ERROR: $*" >&2; exit 1; }
cleanup() { sudo -n rm -f "$CREDS_TMP" 2>/dev/null || true; }
trap cleanup EXIT
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE"
env_value() { sudo -n awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print; exit}' "$ENV_FILE"; }
[[ "$(env_value FUNDLEX_ENV)" == test ]] || die "reset requires FUNDLEX_ENV=test"
[[ "$(env_value FUNDLEX_DATA_DIR)" == "$DATA_DIR" ]] || die "unexpected Test data root"
[[ "$(env_value FUNDLEX_AUTH_DATABASE)" == "$DATA_DIR/auth.sqlite3" ]] || die "unexpected Test auth DB"
[[ -z "$(env_value FUNDLEX_DATABASE_URL)" ]] || die "Test database URL is forbidden for reset"
sudo -n grep -Eq '(/var/lib/fundlex($|/)|/opt/fundlex-recall-first|fundlex-recall-(api|worker)|:8010)' "$ENV_FILE" && die "production path/service/port found in Test env"
[[ -d "$DATA_DIR" && "$DATA_DIR" == /var/lib/fundlex-test ]] || die "refusing to reset non-Test path"

if [[ "${1:-}" != --apply ]]; then
  echo "dry-run: would stop Test services and clear children of $DATA_DIR"
  sudo -n find "$DATA_DIR" -mindepth 1 -maxdepth 1 -printf '%f\n' 2>/dev/null | sort
  exit 0
fi

sudo -n systemctl stop "${SERVICES[@]}"
sudo -n find "$DATA_DIR" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
sudo -n install -d -o fundlex -g fundlex -m 0750 "$DATA_DIR" "$DATA_DIR/traces"
sudo -n rm -f /etc/fundlex-test-credentials
sudo -n -u fundlex bash -c "set -a; . /etc/fundlex-test.env; set +a; export FUNDLEX_TEST_CREDENTIALS_FILE='$CREDS_TMP'; '/opt/fundlex-test/.venv/bin/python' '/opt/fundlex-test/tools/deploy/bootstrap_test_users.py'"
sudo -n chmod 0600 "$DATA_DIR/auth.sqlite3"
sudo -n install -o root -g root -m 0600 "$CREDS_TMP" /etc/fundlex-test-credentials
sudo -n systemctl start "${SERVICES[@]}"
echo "Test environment reset and services restarted"
