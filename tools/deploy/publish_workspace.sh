#!/bin/bash
# Publish this workspace into the FundLex deployment and restart its services.
#
# The real logic is root-owned at /usr/local/sbin/fundlex-publish so that the
# opencode user cannot escalate through a writable script; this wrapper only
# calls it through the narrowly scoped sudo rule.
set -euo pipefail
exec sudo -n /usr/local/sbin/fundlex-publish "$@"
