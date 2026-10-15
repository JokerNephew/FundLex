"""Migrate the whole FundLex workspace to the cloud development host.

Packs the working tree (including ``.git`` and every uncommitted change, excluding
large data/secrets folders), uploads it, unpacks it over ``/home/opencode/fundlex``,
fixes ownership, and verifies file count, git HEAD and the hashes of the key files
against the local copies.

Credentials come from the Windows User-scope FUNDLEX_SSH_* variables (loaded into
this process only; values are never printed or written to disk).

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.migrate_workspace [--dry-run]
      [--skip-verify] [--remote-dir /home/opencode/fundlex]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tarfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_REMOTE_DIR = "/home/opencode/fundlex"

# Directories that never travel: local data, real contracts, source references,
# the local virtualenv and tool caches.
EXCLUDE_DIRS = {"var", "funds", "funds_word", "references", ".venv", "__pycache__", ".pytest_cache",
                ".ruff_cache", ".mypy_cache", "node_modules", ".playwright-mcp", ".workbuddy",
                "build", "dist", ".idea", ".vscode", "archive"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".egg-info")
# Sync/OS artefacts that may appear or vanish while packing.
EXCLUDE_NAMES = ("Thumbs.db", "desktop.ini", ".DS_Store")
EXCLUDE_PATTERNS = (".baiduyun.", "~$", "tmp_obj_")
# Key files whose hashes are compared after the upload (paths relative to the repo root).
KEY_PATHS = [
    "fundlex/recall.py", "fundlex/recall_pipeline.py", "fundlex/recall_prompts.py",
    "fundlex/guide.py", "fundlex/guide_store.py", "fundlex/api.py", "fundlex/jobs.py",
    "fundlex/model.py", "fundlex/model_budget.py", "fundlex/store.py", "fundlex/tasks.py",
    "frontend/index.html", "frontend/app.js", "frontend/app.css",
    "guides/builtin_guide_v1.json", "pyproject.toml",
    "tests/test_recall_core.py", "tests/test_recall_pipeline.py",
    "tools/deploy/publish_workspace.sh",
    "docs/ACTIVE_HANDOFF.md", "docs/DETAIL_ISSUES_AND_RESOLUTIONS.md",
    "docs/FULL_PROJECT_IMPLEMENTATION_PLAN.md", "AGENTS.md",
]


def excluded(relative: Path) -> bool:
    parts = relative.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    if any(part.endswith(EXCLUDE_SUFFIXES) for part in parts):
        return True
    if any(part in EXCLUDE_NAMES for part in parts):
        return True
    if any(pattern in part for part in parts for pattern in EXCLUDE_PATTERNS):
        return True
    return False


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(REPO.rglob("*")):
        relative = path.relative_to(REPO)
        if excluded(relative):
            continue
        if path.is_file() or path.is_symlink():
            files.append(relative)
    return files


def git_head() -> str:
    head = (REPO / ".git" / "HEAD").read_text(encoding="utf-8").strip()
    if head.startswith("ref:"):
        ref = head.split(" ", 1)[1].strip()
        packed = REPO / ".git" / ref
        if packed.exists():
            return packed.read_text(encoding="utf-8").strip()
        packed_refs = REPO / ".git" / "packed-refs"
        if packed_refs.exists():
            for line in packed_refs.read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + ref):
                    return line.split(" ", 1)[0]
    return head


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_tarball(target: Path) -> tuple[Path, int]:
    """Tar the whole tree with POSIX metadata (keeps the executable bit)."""
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    def _filter(info: tarfile.TarInfo):
        parts = Path(info.name).parts
        if any(part in EXCLUDE_DIRS for part in parts):
            return None
        if any(part.endswith(EXCLUDE_SUFFIXES) for part in parts):
            return None
        if any(part in EXCLUDE_NAMES for part in parts):
            return None
        if any(pattern in part for part in parts for pattern in EXCLUDE_PATTERNS):
            return None
        return info

    with tarfile.open(target, "w:gz", format=tarfile.PAX_FORMAT) as archive:
        for relative in iter_files():
            try:
                archive.add(REPO / relative, arcname=relative.as_posix(), recursive=False,
                            filter=_filter)
            except FileNotFoundError:
                # A sync tool removed the file between listing and packing; skip it.
                continue
            count += 1
    return target, count


def load_credentials() -> tuple[str, str, str]:
    import sys
    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import load_credentials as load
    return load()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate the FundLex workspace to the cloud host")
    parser.add_argument("--dry-run", action="store_true", help="pack and report without uploading")
    parser.add_argument("--skip-verify", action="store_true", help="skip the remote hash comparison")
    parser.add_argument("--remote-dir", default=DEFAULT_REMOTE_DIR)
    parser.add_argument("--tar", default="", help="target tarball (default var/deploy/workspace.tar.gz)")
    args = parser.parse_args(argv)

    tarball = Path(args.tar) if args.tar else Path(
        os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp") / "fundlex-workspace.tar.gz"
    stamp = time.strftime("%Y%m%d-%H%M%S")

    print("== pack ==")
    tarball, count = build_tarball(tarball)
    head = git_head()
    local_hashes = {name: sha256(REPO / name) for name in KEY_PATHS if (REPO / name).exists()}
    manifest = {"files": count, "git_head": head, "hashes": local_hashes,
                "packed_at": stamp, "tarball_bytes": tarball.stat().st_size}
    print(f"files={count} head={head[:12]} bytes={tarball.stat().st_size}")

    if args.dry_run:
        print("dry run: no upload")
        return 0

    host, user, password = load_credentials()
    import sys
    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, run

    client = connect(host, user, password, port=22, timeout=30)
    try:
        code, out, err = run(client, "id -un; test -d /home/opencode && echo home-ok; "
                                     "ls -ld /home/opencode/fundlex 2>/dev/null || echo no-workspace",
                             timeout=60)
        print("remote:", out.strip() or err.strip())

        remote_dir = args.remote_dir
        parent = remote_dir.rsplit("/", 1)[0]
        archive = f"/var/tmp/fundlex-migrate-{stamp}.tar.gz"
        run(client, f"mkdir -p /var/tmp/fundlex-migrate && chmod 777 /var/tmp/fundlex-migrate", timeout=60)

        print("== upload ==")
        sftp = client.open_sftp()
        size = tarball.stat().st_size
        last_report = [0.0]

        def progress(done: int, total: int, *, _=None) -> None:
            percent = done * 100 / max(total, 1)
            if percent - last_report[0] >= 5 or done == total:
                last_report[0] = percent
                print(f"  {percent:5.1f}% ({done // (1 << 20)}/{total // (1 << 20)} MiB)")

        with sftp.file(archive, "wb") as remote_handle:
            remote_handle.set_pipelined(True)
            with tarball.open("rb") as source:
                sent = 0
                while True:
                    chunk = source.read(1 << 20)
                    if not chunk:
                        break
                    remote_handle.write(chunk)
                    sent += len(chunk)
                    progress(sent, size)
        sftp.close()

        print("== unpack ==")
        staging = f"/var/tmp/fundlex-migrate/staging-{stamp}"
        commands = [
            f"rm -rf {staging} && mkdir -p {staging}",
            f"tar -xzf {archive} -C {staging} && echo unpacked",
            f"test -f {staging}/AGENTS.md && test -d {staging}/.git && echo layout-ok",
            f"mkdir -p {remote_dir}",
            # Replace the snapshot content without re-creating the directory itself.
            f"find {remote_dir} -mindepth 1 -maxdepth 1 -exec rm -rf {{}} + 2>/dev/null; true",
            f"cp -a {staging}/. {remote_dir}/",
            f"chown -R opencode:opencode {remote_dir}",
            f"chmod +x {remote_dir}/tools/deploy/*.sh 2>/dev/null; true",
            f"ls -ld {remote_dir}; find {remote_dir} -type f | wc -l",
        ]
        for command in commands:
            code, out, err = run(client, command, timeout=900)
            text = (out + err).strip()
            print(f"$ {command[:70]}\n{text[-1500:]}")
            if code != 0:
                raise SystemExit(f"remote step failed ({code}): {command[:120]}")

        if args.skip_verify:
            print("verification skipped")
            return 0

        print("== verify ==")
        remote_files = int(run(client, f"find {remote_dir} -type f | wc -l", timeout=120)[1].strip())
        remote_head = run(client, f"cd {remote_dir} && git rev-parse HEAD 2>/dev/null || echo no-git",
                          timeout=120)[1].strip()
        print(f"remote files={remote_files} local files={count}")
        print(f"remote head={remote_head[:12]} local head={head[:12]}")

        mismatches: list[str] = []
        if remote_files != count:
            mismatches.append(f"file count {remote_files} != {count}")
        if not remote_head.startswith(head[:12]):
            mismatches.append(f"git head {remote_head[:12]} != {head[:12]}")
        for name, digest in local_hashes.items():
            code, out, err = run(client, f"sha256sum {remote_dir}/{name} 2>/dev/null | awk '{{print $1}}'",
                                 timeout=120)
            remote_digest = out.strip()
            if remote_digest != digest:
                mismatches.append(f"{name}: {remote_digest[:12]} != {digest[:12]}")
        if mismatches:
            print("MISMATCHES:")
            for item in mismatches:
                print("  -", item)
            return 1
        print(f"all {len(local_hashes)} key hashes match")

        print("== cleanup ==")
        run(client, f"rm -rf {staging} {archive}", timeout=120)
        print("== done ==")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
