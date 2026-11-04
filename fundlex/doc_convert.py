"""Legacy binary Word (.doc) → DOCX conversion via LibreOffice (shared helper).

Contract / compare ingest path shares this single helper:

- one-file-per-run, ``soffice --headless -env:UserInstallation=<isolated profile>
  --convert-to docx --outdir <isolated out dir>`` for a single file at a time;
- every temporary artefact lives under a ``TemporaryDirectory`` rooted in the
  system temp dir (or ``FUNDLEX_TMP_ROOT``), so a crashed or killed run never
  leaves a profile/output shell behind;
- hard gates: ``FUNDLEX_DOC_CONVERT_TIMEOUT_S`` (default 120s, env-tunable) and
  MAX_UPLOAD_BYTES on the converted output; the caller re-runs the normal
  DOCX package safety chain over the result;
- honest failures only: conversion problems raise ``DocConvertError`` with a
  stable code; the code is never used to pass a modified or fallback file off
  as a real conversion.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Final

DEFAULT_TIMEOUT_S = int(os.environ.get("FUNDLEX_DOC_CONVERT_TIMEOUT_S", "120"))
# Converted output must stay an upload-shaped artifact: same ceiling as
# DOCX uploads (and it feeds the normal package safety chain afterwards).
MAX_OUTPUT_BYTES = 100 * 1024 * 1024

LEGACY_DOC_MAGIC: Final[bytes] = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


class DocConvertError(RuntimeError):
    """A .doc conversion failure with a stable, user-safe code."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail

    @property
    def user_message(self) -> str:
        return "该 .doc 无法转换或损坏"


def is_legacy_doc(data: bytes) -> bool:
    return isinstance(data, (bytes, bytearray)) and bytes(data).startswith(LEGACY_DOC_MAGIC)


def _find_output(out_dir: Path, stem: str) -> Path | None:
    direct = out_dir / f"{stem}.docx"
    if direct.is_file() and direct.stat().st_size > 0:
        return direct
    matches = [p for p in out_dir.glob("*.docx") if p.is_file() and p.stat().st_size > 0]
    return matches[0] if matches else None


def _run_soffice(command: list[str], env: dict, timeout_s: int) -> "subprocess.CompletedProcess":
    """Run soffice with a NEW process group so timeout can kill the whole tree.

    ``subprocess.run(timeout=...)`` only kills the wrapper (soffice script);
    the real ``soffice.bin`` grandchild survives and burns CPU.  New session +
    killpg on timeout kills both (cold-home hang proof, FL-D1074).
    """
    proc = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, start_new_session=True)
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        raise
    return subprocess.CompletedProcess(proc.args, proc.returncode)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    try:
        import signal
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _global_convert_lock_path() -> Path:
    """Machine-wide conversion lock file.

    /var/lib/fundlex is shared across services (API/worker PrivateTmp would
    give each service its own /tmp, so a tempdir lock would NOT be global);
    fall back to tempdir only in dev where the shared root is unwritable.
    """
    override = os.environ.get("FUNDLEX_DOC_CONVERT_LOCK_PATH")
    if override:
        return Path(override)
    default = Path("/var/lib/fundlex/locks/soffice-convert.lock")
    try:
        default.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return Path(tempfile.gettempdir()) / "fundlex-soffice-convert.lock"
    return default


def convert_doc_to_docx(data: bytes, *, timeout_s: int | None = None,
                        max_output_bytes: int = MAX_OUTPUT_BYTES) -> bytes:
    """Convert one legacy .doc byte string into DOCX bytes, or fail honestly.

    Raises ``DocConvertError``.  The caller is responsible for the normal
    DOCX package safety checks on the returned bytes (same gate as uploads).
    """
    if not data:
        raise DocConvertError("LEGACY_DOC_CONVERT_FAILED", "empty input")
    if len(data) > MAX_OUTPUT_BYTES:
        raise DocConvertError("LEGACY_DOC_CONVERT_TOO_LARGE")
    soffice = shutil.which(os.environ.get("FUNDLEX_SOFFICE_BIN", "soffice"))
    if soffice is None:
        raise DocConvertError("LEGACY_DOC_CONVERT_UNAVAILABLE", "soffice not installed")
    timeout_s = timeout_s or DEFAULT_TIMEOUT_S
    temp_root = os.environ.get("FUNDLEX_TMP_ROOT") or None
    # FL-D1126 第三层：soffice 单实例 RSS 300-500MB；本机 7.3G 无 swap，
    # 并发转换（线程池化后 API 可多开+孤儿残留）直接挤爆内存→集体 300s 超时
    # （实证：同一份文件独立转换 3.4s，产线并发下 300s 跑不完）。
    # 全机串行化转换：flock 跨服务（API/各 worker）互斥，排队代替挤兑。
    lock_file = None
    try:
        lock_file = open(_global_convert_lock_path(), "a+b")
        import fcntl
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
    except OSError:  # dev/受限环境拿不到锁文件时退化为无锁（旧行为）
        if lock_file is not None:
            try:
                lock_file.close()
            except OSError:
                pass
            lock_file = None
    try:
        return _convert_locked(data, soffice, timeout_s, max_output_bytes, temp_root)
    finally:
        if lock_file is not None:
            lock_file.close()


def _convert_locked(data: bytes, soffice: str, timeout_s: int,
                    max_output_bytes: int, temp_root: str | None) -> bytes:
    """Body of :func:`convert_doc_to_docx`, run under the global lock."""
    with tempfile.TemporaryDirectory(prefix="fundlex-docconv-", dir=temp_root) as temp_dir:
        work = Path(temp_dir)
        src = work / "input.doc"
        out_dir = work / "out"
        profile = work / "profile"
        src.write_bytes(data)
        out_dir.mkdir()
        command = [
            soffice, "--headless", "--nologo", "--nodefault", "--norestore",
            f"-env:UserInstallation={profile.as_uri()}",
            "--convert-to", "docx", "--outdir", str(out_dir), str(src),
        ]
        env = dict(os.environ)
        # 冷身份挂死根因（FL-D1074）：HOME 不可写/无缓存时 LO 字体链初始化
        # 高 CPU 长挂。worker 给出持久 warm HOME（FUNDLEX_SOFFICE_HOME），
        # UserInstallation 仍逐 attempt 隔离，避免单实例串行。
        soffice_home = os.environ.get("FUNDLEX_SOFFICE_HOME")
        if soffice_home:
            Path(soffice_home).mkdir(parents=True, exist_ok=True)
            env["HOME"] = soffice_home
        try:
            proc = _run_soffice(command, env, timeout_s)
        except subprocess.TimeoutExpired as exc:
            raise DocConvertError("LEGACY_DOC_CONVERT_TIMEOUT") from exc
        except OSError as exc:
            raise DocConvertError("LEGACY_DOC_CONVERT_UNAVAILABLE", str(exc)[:200]) from exc
        output = _find_output(out_dir, "input")
        if proc.returncode != 0 or output is None:
            raise DocConvertError("LEGACY_DOC_CONVERT_FAILED", f"soffice rc={proc.returncode}")
        converted = output.read_bytes()
    if not converted:
        raise DocConvertError("LEGACY_DOC_CONVERT_FAILED")
    if len(converted) > max_output_bytes:
        raise DocConvertError("LEGACY_DOC_CONVERT_TOO_LARGE")
    return converted


def warm_up(soffice: str | None = None) -> bool:
    """进程启动预热一次：触发 LibreOffice 字体/模块缓存建立（冷身份 120s> 整改）。

    子进程级失败只返回 ``False``，绝不影响 worker 启动（FL-D1074）。
    """
    try:
        if not is_legacy_doc(LEGACY_DOC_MAGIC):
            pass
        convert_doc_to_docx(LEGACY_DOC_MAGIC, timeout_s=DEFAULT_TIMEOUT_S)
        return True
    except Exception:  # noqa: BLE001 - 预热失败不影响工作路径
        return False


__all__ = [
    "DocConvertError", "MAX_OUTPUT_BYTES", "LEGACY_DOC_MAGIC",
    "convert_doc_to_docx", "is_legacy_doc", "warm_up",
]
