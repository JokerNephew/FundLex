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
