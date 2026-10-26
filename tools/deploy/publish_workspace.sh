#!/bin/bash
# Publish this workspace into the FundLex deployment and restart all runtime
# services (API, Recall Worker and Compare Worker).
#
# The real logic is root-owned at /usr/local/sbin/fundlex-publish so that the
# opencode user cannot escalate through a writable script; this wrapper only
# calls it through the installed root-side publisher. Operations must keep
# /usr/local/sbin/fundlex-publish synchronized with
# tools/deploy/fundlex-publish.sh from this repository.
set -euo pipefail
exec sudo -n /usr/local/sbin/fundlex-publish "$@"
