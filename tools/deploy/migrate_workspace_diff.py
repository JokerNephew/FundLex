"""Fetch the server-only workspace files and compare the remote file list with the local package.

Read-only: downloads ``tools/deploy/publish_workspace.sh`` (which exists only on the
server) into the local workspace and prints the remote-vs-local file list difference.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.migrate_workspace_diff
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "deploy"))

from migrate_workspace import iter_files, load_credentials  # noqa: E402
from ssh_probe import connect, run  # noqa: E402

REMOTE_DIR = "/home/opencode/fundlex"
FETCH = ["tools/deploy/publish_workspace.sh"]
IGNORED_PREFIXES = ("docs/superpowers/",)


def main() -> int:
    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        code, out, err = run(client, f"cd {REMOTE_DIR} && find . -type f | sed 's|^\\./||' | sort",
                             timeout=120)
        remote_files = {line for line in out.splitlines() if line.strip()}
        print(f"remote files: {len(remote_files)}")

        print("== fetching server-only files ==")
        sftp = client.open_sftp()
        for relative in FETCH:
            target = REPO / relative
            if target.exists():
                print(f"local already has {relative}; comparing")
                local = target.read_bytes()
                remote = sftp.open(f"{REMOTE_DIR}/{relative}").read()
                if local == remote:
                    print(f"  identical ({len(local)} bytes)")
                else:
                    print(f"  DIFFERENT: local {len(local)} bytes, remote {len(remote)} bytes")
                    target.write_bytes(remote)
                    print("  local replaced with the remote copy (remote is authoritative here)")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(sftp.open(f"{REMOTE_DIR}/{relative}").read())
            print(f"  fetched {relative} -> local")
        sftp.close()

        local_files = {path.as_posix() for path in iter_files()}
        server_only = sorted(name for name in remote_files - local_files
                             if not name.startswith(IGNORED_PREFIXES))
        local_only = len(local_files - remote_files)
        print(f"local package files: {len(local_files)}")
        print(f"server-only files ({len(server_only)}):")
        for name in server_only:
            print("  -", name)
        print(f"local-only files: {local_only} (expected: the migration adds .git and uncommitted work)")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
