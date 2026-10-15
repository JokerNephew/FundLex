"""Prepare the migrated workspace on the server and run the test baseline.

Chooses a Python environment for ``/home/opencode/fundlex``:
  1. the workspace's own ``.venv`` when it can be created/updated, else
  2. the read-only application venv at ``/opt/fundlex-recall-first/.venv``.

Then runs ``pytest tests -q`` inside the workspace and reports the summary, the git
HEAD, the uncommitted file list and the workspace file count.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.remote_workspace_check [--remote-dir DIR]
      [--create-venv] [--pytest-args "-q"]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_REMOTE_DIR = "/home/opencode/fundlex"
APP_VENV = "/opt/fundlex-recall-first/.venv"


def _is_root(client) -> bool:
    stdin, stdout, stderr = client.exec_command("id -u")
    return stdout.read().decode().strip() == "0"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set up and test the migrated workspace")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR)
    parser.add_argument("--create-venv", action="store_true",
                        help="create/update the workspace .venv (needs network for pip)")
    parser.add_argument("--pytest-args", default="-q")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, load_credentials

    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        def remote(command: str, *, timeout: float = 1800, quiet: bool = False) -> tuple[int, str]:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            if not quiet:
                text = (out + err).strip()
                if text:
                    print(text[-6000:])
            return code, out + err

        workspace = args.remote_dir
        print("== workspace facts ==")
        remote(f"su - opencode -c 'cd {workspace} && "
               f"echo files=$(find . -type f | wc -l) && "
               f"git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && "
               f"git status --porcelain=v1 | wc -l'")

        print("== python environment ==")
        venv = f"{workspace}/.venv"
        app_ok = False
        code, out = remote(f"test -x {APP_VENV}/bin/python && {APP_VENV}/bin/python -c "
                           f"'import pytest, fastapi, lxml, docx, httpx, jsonschema; print(\"app-venv-ok\")'",
                           quiet=True)
        app_ok = code == 0 and "app-venv-ok" in out
        print("app venv usable for pytest:", app_ok)

        if args.create_venv or not app_ok:
            print("== create workspace venv ==")
            remote(f"test -x {venv}/bin/python || /usr/bin/python3.11 -m venv {venv}; "
                   f"chown -R opencode:opencode {venv}; "
                   f"su - opencode -c '{venv}/bin/pip install -q --upgrade pip >/dev/null && "
                   f"{venv}/bin/pip install -q -e \"{workspace}[test]\" 2>&1 | tail -5; "
                   f"{venv}/bin/python -c '\\''import pytest, fastapi, lxml, docx, httpx, jsonschema; "
                   f"print(\"workspace-venv-ok\", pytest.__version__)'\\'''",
                   timeout=2400)
            python = f"{venv}/bin/python"
        else:
            python = f"{APP_VENV}/bin/python"

        print("== pytest baseline ==")
        # Run as the workspace owner so caches stay writable for the resident agent.
        command = (f"cd {workspace} && {python} -X utf8 -m pytest tests {args.pytest_args} "
                   f"2>&1 | tail -25")
        quoted = command.replace("'", "'\"'\"'")
        code, out = remote(f"su - opencode -c '{quoted}'", timeout=3600)
        print("pytest exit:", code)

        print("== uncommitted summary ==")
        remote(f"su - opencode -c 'cd {workspace} && git status --porcelain=v1 | head -80; "
               f"echo tracked-modified=$(git status --porcelain=v1 | grep -c \"^ M\")'")
        return 0 if code == 0 else code
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
