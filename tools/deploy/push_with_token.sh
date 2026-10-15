#!/usr/bin/env bash
# Push the current branch to origin using a GitHub token read from a file.
#
# The token is never printed, echoed into a command line, or written to the repo:
# it is passed to git through an ephemeral credential helper that reads the same
# file. The file itself is expected outside the repo with 600 permissions.
#
#   usage: bash tools/deploy/push_with_token.sh [/path/to/token_file]
#   default token file: /home/opencode/.github_token
#
# Token file format: either a bare token, or a line "https://<user>:<token>@github.com"
# (i.e. a .git-credentials line). Only the token/user parts are used.
set -euo pipefail

TOKEN_FILE="${1:-/home/opencode/.github_token}"
REMOTE="${REMOTE:-origin}"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "token file not found: $TOKEN_FILE" >&2
  echo "create it (chmod 600) with your GitHub PAT, then rerun." >&2
  exit 2
fi

# Read and normalise without echoing. Support both a bare token and a credentials line.
RAW="$(tr -d '\r\n' < "$TOKEN_FILE")"
if [[ "$RAW" == *"@"* ]]; then
  # https://user:token@github.com  ->  user / token
  CREDS="${RAW#*://}"
  USERPART="${CREDS%%@*}"
  GH_USER="${USERPART%%:*}"
  GH_TOKEN="${USERPART#*:}"
else
  GH_USER="${GH_USER:-x-access-token}"
  GH_TOKEN="$RAW"
fi

if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "no token parsed from $TOKEN_FILE" >&2
  exit 3
fi

# Ephemeral helper: the token only ever lives inside the helper's reply, not argv.
GIT_ASKPASS_SCRIPT="$(mktemp)"
chmod 700 "$GIT_ASKPASS_SCRIPT"
trap 'rm -f "$GIT_ASKPASS_SCRIPT"' EXIT
cat > "$GIT_ASKPASS_SCRIPT" <<'ASKPASS'
#!/usr/bin/env bash
case "$1" in
  *Username*) printf '%s\n' "$GH_USER" ;;
  *Password*) printf '%s\n' "$GH_TOKEN" ;;
  *) printf '\n' ;;
esac
ASKPASS
chmod +x "$GIT_ASKPASS_SCRIPT"

echo "pushing $BRANCH to $REMOTE (token from $TOKEN_FILE, not printed)..."
GH_USER="$GH_USER" GH_TOKEN="$GH_TOKEN" \
  GIT_ASKPASS="$GIT_ASKPASS_SCRIPT" GIT_TERMINAL_PROMPT=0 \
  git push -u "$REMOTE" "$BRANCH"
echo "push complete."
