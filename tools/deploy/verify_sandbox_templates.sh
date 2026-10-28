#!/bin/bash
# Read-only verification for the version-controlled production unit templates.
# This script never writes /etc, calls the publisher, or starts/stops a unit.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CHECK_DIR=$(mktemp -d /tmp/opencode/fundlex-sandbox-units.XXXXXX)
trap 'rm -rf "$CHECK_DIR"' EXIT
UNITS=(
  fundlex-recall-api.service
  fundlex-recall-worker.service
  fundlex-compare-worker.service
  fundlex-guide-worker.service
  fundlex-feishu.service
)
TEMPLATES=()
for unit in "${UNITS[@]}"; do
  cp "$ROOT/tools/deploy/$unit.template" "$CHECK_DIR/$unit"
  TEMPLATES+=("$CHECK_DIR/$unit")
done

systemd-analyze verify "${TEMPLATES[@]}"
for template in "${TEMPLATES[@]}"; do
  grep -Fqx 'NoNewPrivileges=true' "$template"
  grep -Fqx 'PrivateTmp=true' "$template"
  grep -Fqx 'ProtectHome=true' "$template"
  grep -Fqx 'ProtectSystem=strict' "$template"
  grep -Fqx 'ReadWritePaths=/var/lib/fundlex' "$template"
  grep -Fqx 'RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6' "$template"
  grep -Fqx 'UMask=0077' "$template"
done
printf 'sandbox templates: verify-ok (%s units)\n' "${#TEMPLATES[@]}"
