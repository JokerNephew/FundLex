"""Keep live databases outside document repositories and sync folders."""
from pathlib import Path
import os

def local_data_dir() -> Path:
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
    for name in ('FUNDLEX_AUTH_DATABASE', 'FUNDLEX_DATABASE_URL'):
        if os.environ.get(name):
            return os.environ[name]
    base = Path(data_dir) if data_dir else local_data_dir()
    return str(base / 'auth.db')
