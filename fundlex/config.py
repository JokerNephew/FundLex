"""Keep live databases outside document repositories and sync folders."""
from pathlib import Path
import os
import json
import time
from urllib.parse import unquote, urlsplit


PRODUCTION_DATA_ROOTS = (
    Path("/var/lib/fundlex").resolve(),
    Path("/opt/fundlex-recall-first").resolve(),
)


def runtime_environment() -> str:
    """Return the explicit runtime profile used by a FundLex process."""
    value = os.environ.get("FUNDLEX_ENV", "development").strip().lower()
    if value not in {"development", "test", "production"}:
        raise RuntimeError("FUNDLEX_ENV must be development, test, or production")
    return value


def _resolved_path(value: str | Path | None) -> Path | None:
    if value is None or not str(value).strip():
        return None
    if not isinstance(value, (str, Path)):
        return None
    raw = str(value).strip()
    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme not in {"sqlite", "mysql", "mysql+pymysql"}:
            return None
        if parsed.scheme != "sqlite":
            return None
        raw = unquote(parsed.path)
        if parsed.netloc and parsed.netloc != "localhost":
            return None
        if not raw:
            return None
    return Path(raw).expanduser().resolve()


def assert_runtime_isolation(*, environment: str | None = None,
                             data_dir: str | Path | None = None,
                             auth_db: str | Path | None = None,
                             ledger: str | Path | None = None) -> None:
    """Fail closed when a non-production process points at production storage.

    Test deployments call this before starting API/worker/compare processes. The
    check intentionally uses resolved paths so symlinks cannot bypass it.
    """
    env = (environment or runtime_environment()).strip().lower()
    if env not in {"development", "test", "production"}:
        raise RuntimeError("invalid FundLex runtime environment")
    if env == "production":
        return
    if env == "test" and os.environ.get("FUNDLEX_DATABASE_URL", "").strip():
        raise RuntimeError("test runtime cannot use FUNDLEX_DATABASE_URL")
    candidates = [_resolved_path(value) for value in (data_dir, auth_db, ledger)]
    candidates.extend(_resolved_path(os.environ.get(name)) for name in (
        "FUNDLEX_DATA_DIR", "FUNDLEX_AUTH_DATABASE", "FUNDLEX_DATABASE_URL",
        "FUNDLEX_MODEL_LEDGER", "FUNDLEX_TRACE_JSONL", "FUNDLEX_FROZEN_RUN_DIR",
    ))
    for candidate in candidates:
        if candidate is None:
            continue
        if any(candidate == root or root in candidate.parents for root in PRODUCTION_DATA_ROOTS):
            raise RuntimeError(f"{env} runtime points at a production path: {candidate}")
        if env == "test" and str(candidate).startswith("/etc/"):
            raise RuntimeError(f"test runtime cannot use system configuration path: {candidate}")


def write_heartbeat(data_dir: str | Path, *, component: str) -> None:
    """Write a small, non-sensitive liveness marker for service health checks."""
    root = Path(data_dir).resolve()
    assert_runtime_isolation(data_dir=root)
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{component}-heartbeat.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps({"component": component, "environment": runtime_environment(),
                                     "commit": os.environ.get("FUNDLEX_COMMIT", "unknown"),
                                     "timestamp": time.time()}), encoding="utf-8")
    temporary.replace(target)

def local_data_dir() -> Path:
    assert_runtime_isolation()
    if os.environ.get('FUNDLEX_DATA_DIR'):
        return Path(os.environ['FUNDLEX_DATA_DIR']).resolve()
    if os.name=='nt':
        # MSIX hosts may redirect LOCALAPPDATA to a much longer package path.
        # The canonical per-user location avoids both sync and MAX_PATH failures.
        return Path.home()/'AppData'/'Local'/'FundLex'/'runtime'
    return Path.home()/'.local'/'share'/'fundlex'

def auth_db_target(data_dir: str | Path | None = None) -> str:
    """Database target for accounts and sessions.

    ``FUNDLEX_AUTH_DATABASE`` (or the shared ``FUNDLEX_DATABASE_URL``) selects
    an explicit target such as ``mysql://...`` or ``sqlite:///...``. Otherwise a
    dedicated SQLite file lives next to the run store so local data stays
    outside document repositories and sync folders.
    """
    assert_runtime_isolation(data_dir=data_dir)
    for name in ('FUNDLEX_AUTH_DATABASE', 'FUNDLEX_DATABASE_URL'):
        if os.environ.get(name):
            return os.environ[name]
    base = Path(data_dir) if data_dir else local_data_dir()
    return str(base / 'auth.db')
