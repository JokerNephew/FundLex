"""generation 域冰封开关（FL-D1085）：默认 off；与 upload_guard 共用。"""
from __future__ import annotations

import os

GENERATION_ENABLED_KEY = "FUNDLEX_GUIDE_GENERATION_ENABLED"
_GENERATION_ENABLED_VALUES = {"1", "true", "on", "yes"}


def generation_enabled() -> bool:
    return os.environ.get(GENERATION_ENABLED_KEY, "").strip().lower() in _GENERATION_ENABLED_VALUES
