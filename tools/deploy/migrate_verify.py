"""Verify the migrated workspace as the owner user and check pytest availability.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.migrate_verify [--remote-dir DIR]
"""
from __future__ import annotations

import argparse
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
APP_VENV = "/opt/fundlex-recall-first/.venv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the migrated workspace")
    parser.add_argument("--remote-dir", default="/home/opencode/fundlex")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, load_credentials

    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        def remote(command: str, *, timeout: float = 600) -> tuple[int, str]:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            return code, (out + err).strip()

        workspace = args.remote_dir
        print("== git as owner ==")
        code, out = remote(f"su - opencode -c 'cd {workspace} && git rev-parse HEAD && "
                           f"git rev-parse --abbrev-ref HEAD && git status --porcelain=v1 | wc -l'")
        print(out)

        print("== pytest availability ==")
        code, out = remote(f"test -x {APP_VENV}/bin/python && {APP_VENV}/bin/python -c "
                           f"'import pytest; print(pytest.__version__)' 2>&1 || echo no-pytest")
        print("app venv pytest:", out)

        print("== key file hashes ==")
        names = [
            "fundlex/recall.py", "fundlex/recall_pipeline.py", "fundlex/recall_prompts.py",
            "fundlex/model.py", "frontend/app.js", "guides/builtin_guide_v1.json",
            "docs/ACTIVE_HANDOFF.md", "docs/DETAIL_ISSUES_AND_RESOLUTIONS.md",
            "pyproject.toml", "tests/test_recall_pipeline.py",
            "tools/deploy/publish_workspace.sh",
        ]
        import hashlib

        mismatches = 0
        for name in names:
            local = REPO / name
            local_digest = hashlib.sha256(local.read_bytes()).hexdigest() if local.exists() else "-"
            code, out = remote(f"sha256sum {workspace}/{name} 2>/dev/null | awk '{{print $1}}'")
            status = "OK" if out == local_digest else "DIFF"
            if status == "DIFF":
                mismatches += 1
            print(f"  {status} {name}: remote={out[:12]} local={local_digest[:12]}")
        print("mismatches:", mismatches)
        return 0 if mismatches == 0 else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
