"""Single source of truth for the outbound user-agent string (FL-D937(6)).

Five call sites previously hard-coded ``fundlex/0.3.0`` while the package is
actually versioned from ``pyproject.toml``.  Resolve the version from package
metadata once, falling back last-resort if metadata is unavailable (unpacked
source tree without installation data).
"""
from __future__ import annotations

import importlib.metadata

_FALLBACK_VERSION = "0.1.0"


def package_version() -> str:
    try:
        return importlib.metadata.version("fundlex")
    except Exception:  # pragma: no cover - metadata lookup must never break a run
        return _FALLBACK_VERSION


USER_AGENT = f"fundlex/{package_version()}"
