#!/bin/bash
# Read-only drift check between the reviewed repository publisher and the
# installed root publisher (and, optionally, installed unit files).
#
# Exit 0: no differences. Exit 1: drift found. Exit 2: usage/read error.
# Exit 3: suspected reverse sync — the root side contains known hardening
#         markers the repository side lost (FL-D950); pass --ack to apply the
#         classic exit-1 drift verdict when the removal is intentional.
# "Root side" is defined as the operational publisher installed on the
# production machine ($ROOT_SCRIPT, default /usr/local/sbin/fundlex-publish).
# This script never copies, chmods, restarts or publishes anything.
set -euo pipefail

ROOT_SCRIPT=${FUNDLEX_ROOT_PUBLISHER:-/usr/local/sbin/fundlex-publish}
REPO_SCRIPT=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fundlex-publish.sh
UNIT_DIR=${FUNDLEX_UNIT_DIR:-/etc/systemd/system}
CHECK_UNITS=0
ACK=0
UNITS=(fundlex-recall-api.service fundlex-recall-worker.service
  fundlex-compare-worker.service fundlex-guide-worker.service
  fundlex-feishu.service)

#: Known root-side hardening markers (FL-D950): if the operational publisher
#: carries one of these strings while the repository publisher does not, the
#: repository lost productive hardening instead of inheriting it — that shape
#: matches a carelessly reverse-synced (older) tree overwriting the hardening.
HARDENING_MARKERS=(prune_retained_transactions FeishuAppOnboarding)

usage() {
  cat >&2 <<'EOF'
usage: check_publish_drift.sh [--root-script PATH] [--repo-script PATH]
                              [--units [--unit-dir DIR]] [--ack]
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --root-script) [ "$#" -ge 2 ] || { usage; exit 2; }; ROOT_SCRIPT=$2; shift 2 ;;
    --repo-script) [ "$#" -ge 2 ] || { usage; exit 2; }; REPO_SCRIPT=$2; shift 2 ;;
    --unit-dir) [ "$#" -ge 2 ] || { usage; exit 2; }; UNIT_DIR=$2; shift 2 ;;
    --units) CHECK_UNITS=1; shift ;;
    --ack) ACK=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) usage; exit 2 ;;
  esac
done

[ -r "$ROOT_SCRIPT" ] || { echo "drift-check: cannot read $ROOT_SCRIPT" >&2; exit 2; }
[ -r "$REPO_SCRIPT" ] || { echo "drift-check: cannot read $REPO_SCRIPT" >&2; exit 2; }

root_hash=$(sha256sum "$ROOT_SCRIPT" | awk '{print $1}')
repo_hash=$(sha256sum "$REPO_SCRIPT" | awk '{print $1}')
echo "root publisher: $root_hash"
echo "repo publisher: $repo_hash"
if [ "$root_hash" != "$repo_hash" ]; then
  reverse_hits=0
  for marker in "${HARDENING_MARKERS[@]}"; do
    if grep -qF "$marker" "$ROOT_SCRIPT" && ! grep -qF "$marker" "$REPO_SCRIPT"; then
      reverse_hits=$((reverse_hits + 1))
    fi
  done
  if [ "$reverse_hits" -gt 0 ] && [ "$ACK" = 0 ]; then
    echo "drift-check: 疑似反向同步——root 侧含 ${reverse_hits} 个已知加固标记的更新而镜像侧已丢；" \
      "请核对 root 侧 $(basename "$ROOT_SCRIPT") 与发布树谁更新，确认反向同步后方可传 --ack 复跑" >&2
    exit 3
  fi
  echo "drift-check: DRIFT root publisher differs from repository" >&2
  exit 1
fi

if [ "$CHECK_UNITS" = 1 ]; then
  template_dir=$(cd "$(dirname "$REPO_SCRIPT")" && pwd)
  drift=0
  for unit in "${UNITS[@]}"; do
    template="$template_dir/$unit.template"
    installed="$UNIT_DIR/$unit"
    if [ ! -r "$template" ] || [ ! -r "$installed" ]; then
      echo "drift-check: missing unit template or installed unit: $unit" >&2
      drift=1
      continue
    fi
    if ! cmp -s "$template" "$installed"; then
      echo "drift-check: DRIFT unit differs: $unit" >&2
      drift=1
    fi
  done
  [ "$drift" = 0 ] || exit 1
fi
echo "drift-check: OK"
