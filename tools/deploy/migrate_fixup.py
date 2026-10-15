"""Set repository-local git config on the migrated workspace and upload the changed docs.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.migrate_fixup
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
REMOTE = "/home/opencode/fundlex"
UPLOAD = [
    "docs/ACTIVE_HANDOFF.md",
    "docs/DETAIL_ISSUES_AND_RESOLUTIONS.md",
    "docs/FULL_PROJECT_IMPLEMENTATION_PLAN.md",
    "tools/deploy/migrate_workspace.py",
    "tools/deploy/remote_workspace_check.py",
    "tools/deploy/migrate_verify.py",
    "tools/deploy/migrate_workspace_diff.py",
]


def main() -> int:
    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, load_credentials

    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        def remote(command: str, *, timeout: float = 600) -> tuple[int, str]:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            return stdout.channel.recv_exit_status(), (out + err).strip()

        print("== local git config ==")
        code, out = remote(
            "su - opencode -c 'cd %s && git config core.autocrlf input && "
            "git config core.quotepath false && "
            "git rev-parse HEAD && git status --porcelain=v1 | wc -l'" % REMOTE)
        print(out)

        print("== upload changed files ==")
        sftp = client.open_sftp()
        for relative in UPLOAD:
            local = REPO / relative
            if not local.exists():
                print(f"  skip (missing locally): {relative}")
                continue
            remote_path = f"{REMOTE}/{relative}"
            with sftp.file(remote_path, "wb") as handle:
                handle.set_pipelined(True)
                handle.write(local.read_bytes())
            print(f"  uploaded {relative}")
        sftp.close()
        code, out = remote(f"chown -R opencode:opencode {REMOTE}/docs {REMOTE}/tools")
        print("chown exit:", code)

        print("== verify uploaded hashes ==")
        import hashlib
        mismatches = 0
        for relative in UPLOAD:
            local = REPO / relative
            if not local.exists():
                continue
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            code, out = remote(f"sha256sum {REMOTE}/{relative} | awk '{{print $1}}'")
            if out != digest:
                mismatches += 1
                print(f"  DIFF {relative}: {out[:12]} != {digest[:12]}")
            else:
                print(f"  OK {relative}")
        print("mismatches:", mismatches)
        return 0 if mismatches == 0 else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
