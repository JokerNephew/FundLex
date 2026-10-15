"""Full hash verification of the migrated workspace against the local copies.

Checks every file under fundlex/*.py, frontend/*, guides/builtin_guide_v1.json and
docs/*.md (the groups the user asked for), plus the overall file count.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.migrate_verify_full
"""
from __future__ import annotations

import hashlib
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
REMOTE = "/home/opencode/fundlex"


def local_targets() -> list[str]:
    names: list[str] = []
    names += sorted(str(path.relative_to(REPO)).replace("\\", "/")
                    for path in (REPO / "fundlex").glob("*.py"))
    names += sorted(str(path.relative_to(REPO)).replace("\\", "/")
                    for path in (REPO / "frontend").rglob("*") if path.is_file())
    names += sorted(str(path.relative_to(REPO)).replace("\\", "/")
                    for path in (REPO / "guides").glob("*.json"))
    names += sorted(str(path.relative_to(REPO)).replace("\\", "/")
                    for path in (REPO / "docs").glob("*.md"))
    names.append("tools/deploy/publish_workspace.sh")
    return names


def main() -> int:
    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, load_credentials

    names = local_targets()
    print(f"files to verify: {len(names)}")

    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        def remote(command: str, *, timeout: float = 600) -> tuple[int, str]:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            return stdout.channel.recv_exit_status(), (out + err).strip()

        # One remote sha256sum invocation for all files, then compare locally.
        listing = "\n".join(f"{REMOTE}/{name}" for name in names)
        remote_hashes: dict[str, str] = {}
        # Batch in groups to stay well under the command line limit.
        batch = 100
        for start in range(0, len(names), batch):
            chunk = names[start:start + batch]
            command = "sha256sum " + " ".join(f"'{REMOTE}/{name}'" for name in chunk)
            code, out = remote(command)
            for line in out.splitlines():
                parts = line.split("  ", 1)
                if len(parts) != 2:
                    continue
                digest, path = parts[0].strip(), parts[1].strip()
                relative = path[len(REMOTE) + 1:]
                remote_hashes[relative] = digest

        mismatches: list[str] = []
        missing: list[str] = []
        for name in names:
            local = REPO / name
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            got = remote_hashes.get(name)
            if got is None:
                missing.append(name)
            elif got != digest:
                mismatches.append(f"{name}: {got[:12]} != {digest[:12]}")

        code, out = remote(f"find {REMOTE} -type f -not -path '*/{'.venv'}/*' -not -path '*/__pycache__/*' "
                           f"-not -path '*/.pytest_cache/*' | wc -l")
        remote_files = out.strip()
        code, out = remote(f"su - opencode -c 'cd {REMOTE} && git rev-parse HEAD'")
        remote_head = out.strip()

        print(f"remote files (excl .venv/caches): {remote_files}")
        print(f"remote HEAD: {remote_head}")
        print(f"hash match: {len(names) - len(mismatches) - len(missing)}/{len(names)}")
        for name in missing:
            print("  MISSING:", name)
        for name in mismatches:
            print("  DIFF:", name)
        return 0 if not mismatches and not missing else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
