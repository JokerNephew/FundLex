"""Verify the installed launcher through a real PTY hangup, without model calls."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import pty
import signal
import subprocess
import tempfile
import time


def main() -> None:
    launcher = Path.home() / ".local/bin/codex-persistent"
    socket = f"fundlex-codex-check-{os.getpid()}"
    tmux = ["tmux", "-L", socket]

    def run(*args: str) -> str:
        return subprocess.check_output(tmux + list(args), text=True, stderr=subprocess.STDOUT).strip()

    def wait_for(predicate, timeout: float = 12) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.1)
        raise AssertionError("Timed out waiting for persistence evidence")

    def client(env: dict[str, str], *args: str) -> tuple[int, int]:
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(workspace)
            os.execve(str(launcher), [str(launcher), *args], env)
        return pid, fd

    with tempfile.TemporaryDirectory(prefix="fundlex-codex-check-") as directory:
        workspace = Path(directory)
        started = workspace / "started"
        completed = workspace / "completed"
        fake = workspace / "worker"
        fake.write_text(
            "#!/usr/bin/env bash\nset -eu\n"
            "printf '%s' \"$BASHPID\" > \"$CHECK_STARTED\"\n"
            "sleep 3\n"
            "printf completed > \"$CHECK_COMPLETED\"\n"
            "while :; do sleep 1; done\n"
        )
        fake.chmod(0o700)
        env = dict(os.environ)
        env.pop("TMUX", None)
        env.pop("FUNDLEX_CODEX_DIRECT", None)
        env.update({
            "TERM": "xterm-256color",
            "FUNDLEX_CODEX_BINARY": str(fake),
            "FUNDLEX_CODEX_TMUX": "1",
            "FUNDLEX_CODEX_TMUX_SOCKET": socket,
            "CHECK_STARTED": str(started),
            "CHECK_COMPLETED": str(completed),
        })
        session_prefix = "codex-" + hashlib.sha256(str(workspace).encode()).hexdigest()[:12] + "-"
        clients: list[tuple[int, int]] = []
        try:
            clients.append(client(env))
            wait_for(started.exists)
            session = run("list-sessions", "-F", "#{session_name} #{session_created}").splitlines()[-1].split()[0]
            assert session.startswith(session_prefix)
            wait_for(lambda: run("display-message", "-p", "-t", session, "#{session_attached}") == "1")
            worker_pid = run("display-message", "-p", "-t", session, "#{pane_pid}")
            os.close(clients[0][1])  # Closing the PTY master simulates terminal loss / SIGHUP.
            clients[0] = (clients[0][0], -1)
            os.waitpid(clients[0][0], 0)
            wait_for(lambda: run("display-message", "-p", "-t", session, "#{session_attached}") == "0")
            wait_for(completed.exists)
            assert completed.read_text() == "completed"
            assert run("display-message", "-p", "-t", session, "#{pane_pid}") == worker_pid
            clients.append(client(env, "attach"))
            wait_for(lambda: run("display-message", "-p", "-t", session, "#{session_attached}") == "1")
            assert run("display-message", "-p", "-t", session, "#{pane_pid}") == worker_pid
            assert run("show-options", "-gv", "destroy-unattached") == "off"
            print(json.dumps({
                "pty_hangup": "passed", "work_completed_after_disconnect": True,
                "reattached_same_process": True, "destroy_unattached": "off",
                "model_calls": 0,
            }))
        finally:
            subprocess.run(tmux + ["kill-server"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for pid, fd in clients:
                if fd >= 0:
                    os.close(fd)
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    os.waitpid(pid, 0)
                except ChildProcessError:
                    pass


if __name__ == "__main__":
    main()
