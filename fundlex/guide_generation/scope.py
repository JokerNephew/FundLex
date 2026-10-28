"""Guide scope derived from the local built-in revision guide.

The fund-clearing department does not need a generated guide to cover every
contract chapter.  The built-in revision guide is the reference: only the
chapters its rules declare (``section_hint``) are in scope.  A requirement or
contract chapter outside that set must be reported as ``out_of_scope`` rather
than as a gap, unresolved impact or uncertain coverage row.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

DEFAULT_GUIDE_SCOPE = [
    "释义",
    "基金的基本情况",
    "基金份额的申购与赎回",
    "基金费用与税收",
    "基金的收益与分配",
    "基金财产的清算",
]

_BUILTIN_GUIDE = (Path(__file__).resolve().parent.parent.parent
                  / "guides" / "builtin_guide_v1.json")


def load_builtin_guide_scope(path: Path | None = None) -> list[str]:
    target = path or _BUILTIN_GUIDE
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        hints = sorted({
            str(group.get("section_hint") or "").strip()
            for group in data.get("groups") or []
            if str(group.get("section_hint") or "").strip()
        })
        return hints or list(DEFAULT_GUIDE_SCOPE)
    except (OSError, ValueError):
        return list(DEFAULT_GUIDE_SCOPE)


def normalise_section(text: str) -> str:
    value = re.sub(r"^第[一二三四五六七八九十百零〇\d]+(?:部分|章)",
                   "", str(text or "").strip())
    return re.sub(r"[\s\-—_:：、，,。；;（）()]+", "", value)


def section_in_scope(text: str, scope: Iterable[str]) -> bool:
    scopes = [normalise_section(item) for item in scope if normalise_section(item)]
    if not scopes:
        return True
    candidate = normalise_section(text)
    if not candidate:
        return False
    return any(item in candidate or candidate in item for item in scopes)


def texts_in_scope(values: Iterable[str], scope: Iterable[str]) -> bool:
    return any(section_in_scope(value, scope) for value in values if str(value or "").strip())
