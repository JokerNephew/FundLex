"""Read-only SSH reconnaissance for the FundLex deployment target.

Credentials come from the Windows User-scope variables FUNDLEX_SSH_HOST / FUNDLEX_SSH_USER /
FUNDLEX_SSH_PASSWORD (loaded into this process only; values are never printed or logged).

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.ssh_probe [--json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PROBES: list[tuple[str, str]] = [
    ("identity", "whoami; id -un; hostname; uptime"),
    ("os", "cat /etc/os-release 2>/dev/null | head -4; uname -srm"),
    ("cpu_mem", "nproc; free -m | head -3; swapon --show 2>/dev/null | head -3"),
    ("disk", "df -h / /opt /var 2>/dev/null"),
    ("python", "python3 --version 2>&1; python3 -c 'import venv,sys;print(\"venv-ok\")' 2>&1"),
    ("services", "systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null | awk '{print $1}' | head -40"),
    ("listening", "ss -tlnp 2>/dev/null | head -30 || netstat -tlnp 2>/dev/null | head -30"),
    ("mysql", "mysql --version 2>&1; systemctl is-active mysql 2>&1; systemctl is-active mysqld 2>&1"),
    ("nginx", "nginx -v 2>&1; systemctl is-active nginx 2>&1"),
    ("docker", "docker --version 2>&1 | head -1; systemctl is-active docker 2>&1"),
    ("dirs", "ls -la /opt 2>/dev/null | head -20; ls -la /var/www 2>/dev/null | head -10"),
    ("firewall", "ufw status 2>/dev/null | head -12; iptables -S 2>/dev/null | head -12"),
    ("ports_env", "echo SELINUX=$(getenforce 2>/dev/null); echo TIMEZONE=$(timedatectl show -p Timezone --value 2>/dev/null)"),
]


def load_credentials() -> tuple[str, str, str]:
    host = os.environ.get("FUNDLEX_SSH_HOST") or _user_env("FUNDLEX_SSH_HOST")
    user = os.environ.get("FUNDLEX_SSH_USER") or _user_env("FUNDLEX_SSH_USER")
    password = os.environ.get("FUNDLEX_SSH_PASSWORD") or _user_env("FUNDLEX_SSH_PASSWORD")
    missing = [name for name, value in (("FUNDLEX_SSH_HOST", host), ("FUNDLEX_SSH_USER", user),
                                        ("FUNDLEX_SSH_PASSWORD", password)) if not value]
    if missing:
        raise SystemExit("missing credential variables: " + ", ".join(missing))
    return host, user, password


def _user_env(name: str) -> str:
    if sys.platform != "win32":
        return ""
    import subprocess
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"[Environment]::GetEnvironmentVariable('{name}','User')"],
        capture_output=True, text=True, timeout=30)
    return result.stdout.strip()


def connect(host: str, user: str, password: str, *, port: int = 22, timeout: float = 20):
    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(hostname=host, port=port, username=user, password=password,
                   timeout=timeout, banner_timeout=timeout, auth_timeout=timeout)
    return client


def run(client, command: str, *, timeout: float = 60) -> tuple[int, str, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    return stdout.channel.recv_exit_status(), out, err


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only SSH probe of the FundLex server")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--cmd", action="append", default=[], help="extra read-only command (repeatable)")
    args = parser.parse_args(argv)

    host, user, password = load_credentials()
    client = connect(host, user, password, port=args.port)
    probes = PROBES + [(f"cmd{index + 1}", command) for index, command in enumerate(args.cmd)]
    results: dict[str, str] = {}
    try:
        for name, command in probes:
            code, out, err = run(client, command)
            text = out.strip() or err.strip()
            results[name] = text
            if not args.json:
                print(f"### {name} (exit {code})")
                print(text)
                print()
    finally:
        client.close()
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
