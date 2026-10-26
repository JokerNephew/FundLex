#!/bin/bash
# Read-only verification for the version-controlled production unit templates.
# This script never writes /etc, calls the publisher, or starts/stops a unit.
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
CHECK_DIR=$(mktemp -d /tmp/opencode/fundlex-sandbox-units.XXXXXX)
trap 'rm -rf "$CHECK_DIR"' EXIT
declare -a TEMPLATES=(
  "$CHECK_DIR/fundlex-recall-api.service"
  "$CHECK_DIR/fundlex-recall-worker.service"
  "$CHECK_DIR/fundlex-compare-worker.service"
)
cp "$ROOT/tools/deploy/fundlex-recall-api.service.template" "${TEMPLATES[0]}"
cp "$ROOT/tools/deploy/fundlex-recall-worker.service.template" "${TEMPLATES[1]}"
cp "$ROOT/tools/deploy/fundlex-compare-worker.service.template" "${TEMPLATES[2]}"

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
