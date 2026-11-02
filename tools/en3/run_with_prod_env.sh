#!/usr/bin/env bash
# Load /etc/fundlex-recall.env (root-readable only) into the environment and
# run one tools/en3 script.  Values are parsed line-wise; nothing is echoed.
set -euo pipefail
ENV_COPY=$(mktemp /tmp/opencode/en3-env.XXXXXX)
trap 'rm -f "$ENV_COPY"' EXIT
sudo -n cat /etc/fundlex-recall.env > "$ENV_COPY"
chmod 600 "$ENV_COPY"
export FUNDLEX_MODEL_LEDGER=${FUNDLEX_MODEL_LEDGER:-/tmp/opencode/en3_model_budget.sqlite}
export FUNDLEX_DATA_DIR=${FUNDLEX_DATA_DIR:-/tmp/opencode/en3_data}
mkdir -p "$FUNDLEX_DATA_DIR"
python_args=("$@")
exec /home/opencode/.local/share/opencode/worktree/29a9a9/qa-engine-tracked/.venv/bin/python - "$ENV_COPY" "${python_args[@]}" <<'PYEOF'
import os, sys, subprocess
envfile, script, *rest = sys.argv[1], sys.argv[2], *sys.argv[3:]
env = dict(os.environ)
with open(envfile) as fh:
    for line in fh:
        line = line.rstrip("\n")
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        env[k.strip()] = v
# The production ledger path is root-owned; probes use a scratch ledger so
# the production budget DB is never touched read-write.
env["FUNDLEX_MODEL_LEDGER"] = os.environ.get(
    "FUNDLEX_MODEL_LEDGER", "/tmp/opencode/en3_model_budget.sqlite")
env["FUNDLEX_DATA_DIR"] = os.environ.get("FUNDLEX_DATA_DIR", "/tmp/opencode/en3_data")
proc = subprocess.run([sys.executable, script, *rest], env=env)
sys.exit(proc.returncode)
PYEOF
