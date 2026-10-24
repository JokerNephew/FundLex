"""Apply the user's explicit full-access preference without exposing auth config."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import os
import re
import shutil
import tomllib


def main() -> None:
    config = Path.home() / ".codex/config.toml"
    original = config.read_text()
    before = tomllib.loads(original)
    if "sandbox_mode" in before or "sandbox_workspace_write" in before:
        raise SystemExit("Remove conflicting legacy sandbox settings before selecting a permissions profile")
    table = re.search(r"(?m)^\s*\[", original)
    boundary = table.start() if table else len(original)
    root = re.sub(
        r"(?m)^(?:approval_policy|default_permissions)\s*=.*(?:\n|$)",
        "",
        original[:boundary],
    )
    updated = (
        'approval_policy = "never"\n'
        'default_permissions = ":danger-full-access"\n'
        + root + original[boundary:]
    )
    after = tomllib.loads(updated)
    for data in (before, after):
        data.pop("approval_policy", None)
        data.pop("default_permissions", None)
    if before != after:
        raise SystemExit("Unexpected change outside the two authorized permission settings")
    if original != updated:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup = config.with_name(config.name + f".bak-full-access-{stamp}")
        shutil.copy2(config, backup)
        backup.chmod(0o600)
        temporary = config.with_name(config.name + f".tmp-{os.getpid()}")
        try:
            with temporary.open("x") as stream:
                stream.write(updated)
            temporary.chmod(0o600)
            temporary.replace(config)
        finally:
            if temporary.exists():
                temporary.unlink()
        print(f"Backup: {backup}")
    print(json.dumps({"approval_policy": "never", "default_permissions": ":danger-full-access"}))


if __name__ == "__main__":
    main()
