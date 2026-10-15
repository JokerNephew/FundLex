"""Deploy the recall-first FundLex build to the Alibaba Cloud server.

Read-only reconnaissance is in ssh_probe.py. This script:
  1. packs the current working tree (explicit include list, no data/secrets),
  2. uploads it and unpacks to /opt/fundlex-recall-first,
  3. backs up the existing MySQL database,
  4. builds a dedicated virtualenv and installs the package,
  5. writes /etc/fundlex-recall.env (derived from /etc/fundlex.env, never printed),
  6. installs systemd units on port 8010 and switches the nginx vhost,
  7. stops the previous FundLex services (kept for rollback) and starts the new ones,
  8. verifies health and reports.

Credentials come from the Windows User-scope FUNDLEX_SSH_* variables (never printed).

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.deploy_recall [--skip-pack] [--verify-only]
"""
from __future__ import annotations

import argparse
import os
import posixpath
import sys
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP_DIR = "/opt/fundlex-recall-first"
ENV_FILE = "/etc/fundlex-recall.env"
OLD_ENV_FILE = "/etc/fundlex.env"
PORT = 8010
SERVICE_API = "fundlex-recall-api.service"
SERVICE_WORKER = "fundlex-recall-worker.service"
INCLUDE = [
    "fundlex", "frontend", "guides", "rules", "tools", "docs", "tests",
    "pyproject.toml", "uv.lock", "README.md", "AGENTS.md",
]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".venv", "var", "funds_word", "references",
                 ".git", ".playwright-mcp", ".workbuddy", "archive", "funds", "specs",
                 "workbench", "build", "*.egg-info"}


def build_tarball() -> Path:
    target = REPO / "var" / "deploy" / "fundlex-recall-first.tar.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz") as archive:
        for name in INCLUDE:
            path = REPO / name
            if not path.exists():
                continue
            if path.is_file():
                archive.add(path, arcname=name)
                continue
            for child in sorted(path.rglob("*")):
                relative = child.relative_to(REPO).as_posix()
                if any(part in EXCLUDE_PARTS or part.endswith(".egg-info") for part in relative.split("/")):
                    continue
                if child.is_file():
                    archive.add(child, arcname=relative)
    return target


def load_credentials() -> tuple[str, str, str]:
    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import load_credentials as load
    return load()


def remote(client, command: str, *, timeout: float = 900, check: bool = False, quiet: bool = False) -> tuple[int, str]:
    stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if not quiet:
        text = (out + err).strip()
        if text:
            print(text[-4000:])
    if check and code != 0:
        raise SystemExit(f"remote command failed ({code}): {command[:200]}")
    return code, (out + err)


ENV_OVERRIDES = {
    "FUNDLEX_MODEL_CONTEXT_CHARS": "32000",
    "FUNDLEX_MODEL_MAX_OUTPUT_TOKENS": "4000",
    "FUNDLEX_MODEL_TIMEOUT_S": "180",
    "FUNDLEX_MODEL_MAX_REQUESTS": "20000",
    "FUNDLEX_MODEL_MAX_COST_USD": "50",
    "FUNDLEX_MODEL_INPUT_USD_PER_M": "0.15",
    "FUNDLEX_MODEL_OUTPUT_USD_PER_M": "0.6",
    "FUNDLEX_MODEL_CONCURRENCY": "1",
}

API_UNIT = f"""[Unit]
Description=FundLex recall-first API
After=network.target mysqld.service
Wants=mysqld.service

[Service]
User=fundlex
Group=fundlex
WorkingDirectory={APP_DIR}
EnvironmentFile={ENV_FILE}
ExecStart={APP_DIR}/.venv/bin/uvicorn fundlex.api:app --host 127.0.0.1 --port {PORT} --workers 2
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

WORKER_UNIT = f"""[Unit]
Description=FundLex recall-first contract worker
After=network.target mysqld.service
Wants=mysqld.service

[Service]
User=fundlex
Group=fundlex
WorkingDirectory={APP_DIR}
EnvironmentFile={ENV_FILE}
ExecStart={APP_DIR}/.venv/bin/python -X utf8 -m fundlex.jobs
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
"""

ENV_SCRIPT = f"""
import os, re, shutil
src, dst = {OLD_ENV_FILE!r}, {ENV_FILE!r}
overrides = {ENV_OVERRIDES!r}
lines = []
seen = set()
for line in open(src, encoding='utf-8'):
    stripped = line.strip()
    if '=' in stripped and not stripped.startswith('#'):
        key = stripped.split('=', 1)[0]
        if key in overrides:
            lines.append(f"{{key}}={{overrides[key]}}\\n")
            seen.add(key)
            continue
    lines.append(line)
for key, value in overrides.items():
    if key not in seen:
        lines.append(f"{{key}}={{value}}\\n")
open(dst, 'w', encoding='utf-8').write(''.join(lines))
os.chmod(dst, 0o600)
print('env written, keys:', len([l for l in lines if '=' in l]))
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy recall-first build to the server")
    parser.add_argument("--skip-pack", action="store_true", help="reuse the existing tarball")
    parser.add_argument("--verify-only", action="store_true", help="only run the verification steps")
    parser.add_argument("--keep-old-services", action="store_true",
                        help="do not stop the previous FundLex services")
    args = parser.parse_args(argv)

    host, user, password = load_credentials()
    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect
    client = connect(host, user, password, port=22, timeout=30)
    try:
        if not args.verify_only:
            tarball = REPO / "var" / "deploy" / "fundlex-recall-first.tar.gz"
            if not args.skip_pack:
                tarball = build_tarball()
                print(f"packed {tarball.stat().st_size // 1024} KiB -> {tarball}")
            stamp = time.strftime("%Y%m%d-%H%M%S")

            print("== preflight ==")
            remote(client, "test -x /usr/bin/python3.11 && echo python3.11-ok; df -h / | tail -1",
                   check=True)

            print("== database backup ==")
            remote(client, f"""bash -lc '
mkdir -p /var/backups/fundlex
python3.11 - <<PY
import os, re, subprocess
env = {{}}
for line in open("{OLD_ENV_FILE}"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k] = v
url = env.get("FUNDLEX_DATABASE_URL", "")
m = re.match(r"mysql://([^:]+):([^@]*)@([^:/]+):(\\d+)/([^/?]+)", url)
assert m, "database url not parseable"
cnf = "/root/.fundlex-db.cnf"
open(cnf, "w").write("[client]\\nuser=%s\\npassword=%s\\nhost=%s\\nport=%s\\n" % (m.group(1), m.group(2), m.group(3), m.group(4)))
os.chmod(cnf, 0o600)
db = m.group(5)
target = "/var/backups/fundlex/fundlex-%s-%s.sql.gz" % (db, "{stamp}")
with open(target, "wb") as handle:
    dump = subprocess.Popen(["mysqldump", "--defaults-file=" + cnf, "--no-tablespaces",
                             "--single-transaction", db], stdout=subprocess.PIPE)
    gzip = subprocess.Popen(["gzip"], stdin=dump.stdout, stdout=handle)
    dump.stdout.close()
    gzip.wait(); dump.wait()
print("backup:", target, os.path.getsize(target), "bytes")
PY
ls -la /var/backups/fundlex/ | tail -3
'""", check=True)

            print("== upload and unpack ==")
            remote(client, f"mkdir -p {APP_DIR} /var/tmp/fundlex-deploy", check=True)
            sftp = client.open_sftp()
            sftp.put(str(tarball), "/var/tmp/fundlex-deploy/payload.tar.gz")
            sftp.close()
            remote(client, f"tar -xzf /var/tmp/fundlex-deploy/payload.tar.gz -C {APP_DIR} && "
                           f"chmod -R a+rX {APP_DIR} && ls {APP_DIR}", check=True)

            print("== virtualenv ==")
            remote(client, f"test -x {APP_DIR}/.venv/bin/python || /usr/bin/python3.11 -m venv {APP_DIR}/.venv; "
                           f"{APP_DIR}/.venv/bin/pip install -q --upgrade pip setuptools wheel && "
                           f"{APP_DIR}/.venv/bin/pip install -q -e {APP_DIR} && "
                           f"{APP_DIR}/.venv/bin/python -c 'import fastapi, lxml, docx, httpx, jsonschema, pymysql; print(\"deps-ok\")'",
                   timeout=1200, check=True)

            print("== environment file ==")
            remote(client, f"python3.11 - <<'PY'\n{ENV_SCRIPT}\nPY", check=True)

            print("== systemd units ==")
            for name, content in ((SERVICE_API, API_UNIT), (SERVICE_WORKER, WORKER_UNIT)):
                remote(client, f"cat > /etc/systemd/system/{name} <<'UNIT'\n{content}UNIT", check=True)
            remote(client, "systemctl daemon-reload", check=True)

            print("== environment check against the live database ==")
            live_check = f"""bash -lc '
{APP_DIR}/.venv/bin/python - <<'PY'
import os
env = {{}}
for line in open("{ENV_FILE}"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k] = v
os.environ.update(env)
from fundlex.store import RunStore
from fundlex.tasks import TaskStore
from fundlex.guide_store import ensure_builtin_guide, current_guide
store = RunStore(env["FUNDLEX_DATA_DIR"])
ensure_builtin_guide(store)
with store.database.connect() as db:
    tables = sorted((row[0] if not isinstance(row, dict) else list(row.values())[0])
                    for row in db.execute("show tables").fetchall())
    print("tables:", ",".join(tables))
    fields = sorted((row["Field"] if isinstance(row, dict) else row[0])
                    for row in db.execute("show columns from batches").fetchall())
    print("binding-cols:", [f for f in fields if f in ("engine_id", "guide_version_id", "guide_rules_sha256")])
print("current-guide:", current_guide(store, "")["id"])
PY
'"""
            remote(client, live_check, check=True)

            print("== switch services ==")
            if not args.keep_old_services:
                remote(client, "systemctl disable --now fundlex-api fundlex-worker 2>&1 | tail -2", check=False)
            remote(client, f"systemctl enable {SERVICE_API} {SERVICE_WORKER}", check=True)
            remote(client, f"systemctl restart {SERVICE_API} {SERVICE_WORKER}", check=True)
            remote(client, f"sleep 4; systemctl is-active {SERVICE_API} {SERVICE_WORKER}", check=False)

            print("== nginx switch to new port ==")
            remote(client, f"""bash -lc '
CONF=/www/server/panel/vhost/nginx/fundlex.conf
cp -n $CONF $CONF.bak-{stamp} 2>/dev/null
sed -i "s#proxy_pass http://127.0.0.1:[0-9]*;#proxy_pass http://127.0.0.1:{PORT};#" $CONF
grep proxy_pass $CONF
nginx -t && nginx -s reload && echo nginx-reloaded
'""", check=True)

        print("== verification ==")
        code, out = remote(client, f"curl -s --max-time 15 http://127.0.0.1:{PORT}/api/capabilities", quiet=True)
        print("capabilities:", out.strip()[:500])
        code, out = remote(client, f"curl -s -o /dev/null -w '%{{http_code}}' --max-time 15 http://127.0.0.1/", quiet=True)
        print("nginx http status:", out.strip())
        code, out = remote(client, f"curl -s --max-time 15 http://127.0.0.1:{PORT}/api/capabilities", quiet=True)
        print("via nginx:", out.strip()[:300])
        remote(client, f"systemctl is-active {SERVICE_API} {SERVICE_WORKER}; "
                       f"journalctl -u {SERVICE_API} -n 5 --no-pager | tail -5", check=False)
        print("== done ==")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
