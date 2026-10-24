"""Install a reversible, user-scoped interactive Codex launcher."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
import shlex
import shutil


def main() -> None:
    user_home = Path.home()
    source = Path(__file__).resolve().parent
    codex_binary = user_home / ".local/bin/codex"
    launcher = user_home / ".local/bin/codex-persistent"
    config = user_home / ".config/fundlex/codex-tmux.conf"
    bashrc = user_home / ".bashrc"
    if not codex_binary.is_file() or not os.access(codex_binary, os.X_OK):
        raise SystemExit("Expected the existing executable at ~/.local/bin/codex")
    if shutil.which("tmux") is None:
        raise SystemExit("Install tmux before running this installer")

    begin = "# >>> FundLex persistent Codex >>>"
    end = "# <<< FundLex persistent Codex <<<"
    original = bashrc.read_text() if bashrc.exists() else ""
    block = (
        f"{begin}\n"
        'if [[ $- == *i* ]]; then\n'
        f"    codex() {{ {shlex.quote(str(launcher))} \"$@\"; }}\n"
        "fi\n"
        f"{end}"
    )
    if (begin in original) != (end in original):
        raise SystemExit("Incomplete existing startup block; refusing to overwrite it")
    if begin in original:
        start = original.index(begin)
        stop = original.index(end, start) + len(end)
        updated = original[:start] + block + original[stop:]
    else:
        updated = original.rstrip("\n") + "\n\n" + block + "\n"

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    for destination, data, mode in (
        (launcher, (source / "codex_persistent.sh").read_bytes(), 0o755),
        (config, (source / "codex-tmux.conf").read_bytes(), 0o644),
        (bashrc, updated.encode(), 0o644),
    ):
        if destination.exists() and destination.read_bytes() == data:
            print(f"Already configured: {destination}")
            continue
        if destination.exists():
            backup = destination.with_name(destination.name + f".bak-fundlex-persistent-{timestamp}")
            shutil.copy2(destination, backup)
            print(f"Backup: {backup}")
            mode = destination.stat().st_mode & 0o777
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + f".tmp-{os.getpid()}")
        try:
            with temporary.open("xb") as stream:
                stream.write(data)
            temporary.chmod(mode)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
        print(f"Installed: {destination}")
    print("New interactive Bash shells now use the app-server daemon (tmux fallback).")


if __name__ == "__main__":
    main()
