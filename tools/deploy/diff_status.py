"""Compare local and remote git status lists to explain the count difference."""
import pathlib
import subprocess
import sys

sys.path.insert(0, r"D:\Desktop\FundLex\tools\deploy")
from ssh_probe import connect, load_credentials  # noqa: E402

REPO = pathlib.Path(r"D:\Desktop\FundLex")
local = subprocess.run(["git", "status", "--porcelain=v1"], cwd=REPO,
                       capture_output=True, text=True).stdout.splitlines()
local = [line for line in local if line.strip()]

host, user, password = load_credentials()
client = connect(host, user, password, port=22, timeout=30)
CONF = "/home/opencode/fundlex"
command = f"cd {CONF} && git status --porcelain=v1"
stdin, stdout, stderr = client.exec_command(
    f"su - opencode -c '{command}'", timeout=300)
remote = [line for line in stdout.read().decode("utf-8", "replace").splitlines() if line.strip()]
client.close()

remote_set, local_set = set(remote), set(local)
print(f"local={len(local)} remote={len(remote)}")
print(f"remote-only ({len(remote_set - local_set)}):")
for line in sorted(remote_set - local_set)[:40]:
    print("  +", line)
print(f"local-only ({len(local_set - remote_set)}):")
for line in sorted(local_set - remote_set)[:25]:
    print("  -", line)
