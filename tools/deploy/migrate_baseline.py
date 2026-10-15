"""Focused post-migration check: workspace facts, venv, pytest baseline.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.migrate_baseline
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
REMOTE = "/home/opencode/fundlex"
VENV = f"{REMOTE}/.venv"


def main() -> int:
    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, load_credentials

    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        def remote(command: str, *, timeout: float = 3600) -> tuple[int, str]:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            return stdout.channel.recv_exit_status(), (out + err).strip()

        print("== workspace facts ==")
        code, out = remote(f"su - opencode -c 'cd {REMOTE} && "
                           f"echo files=$(find . -type f | wc -l) && "
                           f"git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && "
                           f"git status --porcelain=v1 | wc -l && "
                           f"{VENV}/bin/python -c \"import pytest,sys;print(\\\"pytest\\\",pytest.__version__,\\\"python\\\",sys.version.split()[0])\"'")
        print(out)

        print("== pytest baseline ==")
        code, out = remote(f"su - opencode -c 'cd {REMOTE} && {VENV}/bin/python -X utf8 -m pytest tests -q 2>&1 | tail -12'",
                           timeout=3600)
        print(out)
        print("pytest exit:", code)
        return 0 if code == 0 else code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
