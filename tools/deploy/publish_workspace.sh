#!/bin/bash
# Publish an explicitly reviewed FundLex candidate into the deployment and
# stop/start all five runtime services (API, Recall, Compare, Guide and Feishu).
#
# The real logic is root-owned at /usr/local/sbin/fundlex-publish so that the
# opencode user cannot escalate through a writable script; this wrapper only
# calls it through the installed root-side publisher. Operations must keep
# /usr/local/sbin/fundlex-publish synchronized with
# tools/deploy/fundlex-publish.sh from the reviewed candidate, and verify the
# install with tools/deploy/check_publish_drift.sh before any release.
#
# No implicit source tree is accepted: pass a reviewed release worktree and
# optional commit. Use --dry-run first.
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: $0 --source DIR [--commit SHA] [--dry-run]" >&2
  exit 2
fi
exec sudo -n /usr/local/sbin/fundlex-publish "$@"
