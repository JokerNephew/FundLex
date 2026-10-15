"""Migrate the FundLex reference data (contracts and guide originals) to the server.

Uploads to ``/home/opencode/data`` (outside the git workspace):
  * ``funds_word/``  -> ``/home/opencode/data/funds_word/``
  * ``references/``  -> ``/home/opencode/data/references/``

Then fixes ownership/permissions (dirs 750, files 640), generates
``MANIFEST.sha256`` (``sha256  relative_path  bytes`` per line plus totals as
comment lines) and verifies every hash and size against the local copies.

Nothing is copied into ``/home/opencode/fundlex`` and nothing enters git.

Usage:
  .venv\\Scripts\\python.exe -X utf8 -m tools.deploy.migrate_data [--dry-run]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import sys
import tarfile
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
REMOTE_DIR = "/home/opencode/data"
GROUPS = ["funds_word", "references"]
EXPECTED = {"funds_word": 514, "references": 24}
# Office lock files and sync artefacts never travel.
EXCLUDE_PATTERNS = ("~$", ".baiduyun.", "Thumbs.db", "desktop.ini", ".DS_Store")


def relevant(path: pathlib.Path) -> bool:
    name = path.name
    return not any(pattern in name for pattern in EXCLUDE_PATTERNS)


def local_files() -> list[pathlib.Path]:
    names: list[pathlib.Path] = []
    for group in GROUPS:
        root = REPO / group
        names += sorted(path for path in root.rglob("*") if path.is_file() and relevant(path))
    return names


def local_hashes(files: list[pathlib.Path]) -> dict[str, tuple[str, int]]:
    manifest: dict[str, tuple[str, int]] = {}
    for path in files:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        relative = path.relative_to(REPO).as_posix()
        manifest[relative] = (digest.hexdigest(), path.stat().st_size)
    return manifest


def build_tarball(target: pathlib.Path, files: list[pathlib.Path]) -> None:
    with tarfile.open(target, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(REPO).as_posix())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate FundLex reference data")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-upload", action="store_true",
                        help="reuse the already-unpacked data: only regenerate the manifest and verify")
    parser.add_argument("--tar", default="")
    args = parser.parse_args(argv)

    files = local_files()
    manifest = local_hashes(files)
    total_bytes = sum(size for _digest, size in manifest.values())
    counts = {group: sum(1 for name in manifest if name.startswith(group + "/"))
              for group in GROUPS}
    print(f"local files: {len(files)} total_bytes={total_bytes} counts={counts}")
    for group, expected in EXPECTED.items():
        if counts.get(group) != expected:
            print(f"NOTE: {group} has {counts.get(group)} files, expected {expected}")

    tarball = pathlib.Path(args.tar) if args.tar else pathlib.Path(
        os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp") / "fundlex-data.tar.gz"
    build_tarball(tarball, files)
    print(f"packed {tarball} ({tarball.stat().st_size // 1024} KiB)")

    if args.dry_run:
        print("dry run: no upload")
        return 0

    sys.path.insert(0, str(REPO / "tools" / "deploy"))
    from ssh_probe import connect, load_credentials

    host, user, password = load_credentials()
    client = connect(host, user, password, port=22, timeout=30)
    try:
        def remote(command: str, *, timeout: float = 3600) -> tuple[int, str]:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            return stdout.channel.recv_exit_status(), (out + err)

        stamp = time.strftime("%Y%m%d-%H%M%S")
        staging = f"/var/tmp/fundlex-data-{stamp}"
        archive = f"/var/tmp/fundlex-data-{stamp}.tar.gz"

        if not args.skip_upload:
            print("== upload ==")
            sftp = client.open_sftp()
            size = tarball.stat().st_size
            with sftp.file(archive, "wb") as handle:
                handle.set_pipelined(True)
                with tarball.open("rb") as source:
                    sent = 0
                    while True:
                        chunk = source.read(1 << 20)
                        if not chunk:
                            break
                        handle.write(chunk)
                        sent += len(chunk)
                        if sent % (16 << 20) < (1 << 20):
                            print(f"  {sent * 100 // max(size, 1)}%")
            sftp.close()

            print("== unpack ==")
            command = (
                f"set -e; rm -rf {staging}; mkdir -p {staging}; "
                f"tar -xzf {archive} -C {staging}; "
                f"mkdir -p {REMOTE_DIR}; "
                f"rm -rf {REMOTE_DIR}/funds_word {REMOTE_DIR}/references; "
                f"mv {staging}/funds_word {staging}/references {REMOTE_DIR}/; "
                f"chown -R opencode:opencode {REMOTE_DIR}; "
                f"chmod 750 {REMOTE_DIR}; "
                f"find {REMOTE_DIR} -type d -exec chmod 750 {{}} +; "
                f"find {REMOTE_DIR} -type f -exec chmod 640 {{}} +; "
                f"rm -rf {staging} {archive}; "
                f"echo unpacked"
            )
            code, out = remote(command)
            print(out.strip()[-500:])
            if code != 0:
                raise SystemExit("unpack failed")

        print("== generate MANIFEST.sha256 ==")
        manifest_script = """#!/bin/bash
set -e
cd /home/opencode/data
tmp=$(mktemp)
find funds_word references -type f | LC_ALL=C sort | while IFS= read -r path; do
  sha256sum "$path" | awk '{print $1}' > "$tmp.sha"
  read -r sha < "$tmp.sha"
  bytes=$(stat -c%s "$path")
  printf '%s  %s  %s\\n' "$sha" "$path" "$bytes" >> "$tmp"
done
rm -f "$tmp.sha"
files=$(wc -l < "$tmp")
total=$(awk '{s+=$3} END {print s+0}' "$tmp")
stamp=$(date -Iseconds)
{
  printf '### files: %s\\n' "$files"
  printf '### total_bytes: %s\\n' "$total"
  printf '### generated_at: %s\\n' "$stamp"
  printf '### host: %s\\n' "$(hostname)"
} >> "$tmp"
install -m 640 -o opencode -g opencode "$tmp" MANIFEST.sha256
rm -f "$tmp"
echo "manifest files=$files total_bytes=$total"
"""
        script_path = pathlib.Path(
            os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp") / "fundlex_gen_manifest.sh"
        script_path.write_text(manifest_script, encoding="utf-8", newline="\n")
        sftp = client.open_sftp()
        sftp.put(str(script_path), "/tmp/fundlex_gen_manifest.sh")
        sftp.close()
        code, out = remote("bash /tmp/fundlex_gen_manifest.sh; rm -f /tmp/fundlex_gen_manifest.sh")
        print(out.strip()[-500:])
        if code != 0:
            raise SystemExit("manifest generation failed")

        print("== verify all hashes against local ==")
        stdin, stdout, stderr = client.exec_command(
            f"su - opencode -c 'cat {REMOTE_DIR}/MANIFEST.sha256'", timeout=600)
        text = stdout.read().decode("utf-8", "replace")
        remote_manifest: dict[str, tuple[str, int]] = {}
        remote_files = remote_total = None
        for line in text.splitlines():
            if line.startswith("###"):
                if line.startswith("### files:"):
                    remote_files = int(line.split(":", 1)[1].strip())
                elif line.startswith("### total_bytes:"):
                    remote_total = int(line.split(":", 1)[1].strip())
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            remote_manifest[parts[1]] = (parts[0], int(parts[2]))

        mismatches: list[str] = []
        for name, (digest, bytes_) in manifest.items():
            got = remote_manifest.get(name)
            if got is None:
                mismatches.append(f"missing {name}")
            elif got[0] != digest or got[1] != bytes_:
                mismatches.append(f"{name}: remote={got[0][:12]}/{got[1]} local={digest[:12]}/{bytes_}")
        extra = sorted(set(remote_manifest) - set(manifest))
        print(f"remote manifest entries={len(remote_manifest)} files={remote_files} "
              f"total_bytes={remote_total}")
        print(f"mismatches={len(mismatches)} extra={len(extra)}")
        for item in mismatches[:10]:
            print("  -", item)
        for item in extra[:10]:
            print("  +", item)

        print("== sizes ==")
        code, out = remote(f"du -sb {REMOTE_DIR}/funds_word {REMOTE_DIR}/references; "
                           f"ls -la {REMOTE_DIR}; "
                           f"find {REMOTE_DIR}/funds_word -type f | wc -l; "
                           f"find {REMOTE_DIR}/references -type f | wc -l")
        print(out.strip())
        return 0 if not mismatches and not extra else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
