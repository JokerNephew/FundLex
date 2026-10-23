"""Conservative text normalization for comparison.

``raw_text`` remains untouched for display and offsets. ``match_text`` only
removes representation noise; punctuation, numbers, case and wording remain
significant. ``diff_text`` canonicalizes runs of horizontal whitespace solely so
spacing-count changes do not create a textual diff.
"""
from __future__ import annotations

import re
import unicodedata

_HSPACE = " \t\u00a0\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u202f\u205f\u3000"
_HSPACE_RE = re.compile(f"[{re.escape(_HSPACE)}]+")


def normalize_match(text: str) -> str:
    value = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ").replace("\t", " ")
    value = _HSPACE_RE.sub(" ", value)
    return value.strip(" ")


def normalize_diff(text: str) -> str:
    """Return a conservative comparison form preserving all visible symbols."""
    value = unicodedata.normalize("NFC", text).replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\u00a0", " ").replace("\t", " ")
    return _HSPACE_RE.sub(" ", value)


def equivalent_text(left: str, right: str) -> bool:
    return normalize_diff(left) == normalize_diff(right)


def tokenize(text: str) -> list[tuple[str, int, int, str]]:
    """Tokenize while retaining raw offsets.

    Chinese characters, words, numbers and punctuation are naturally stable
    under character-level tokenization. ASCII words and number runs are kept as
    units to produce useful highlights. Horizontal whitespace is one canonical
    token regardless of its run length.
    """
    import re
    tokens: list[tuple[str, int, int, str]] = []
    pattern = re.compile(r"[ \t\u00a0\u2000-\u200a\u202f\u205f\u3000]+|[A-Za-z]+(?:['’][A-Za-z]+)*|\d+(?:[.,:/-]\d+)*%?|\n|.", re.S)
    for m in pattern.finditer(text):
        raw = m.group(0)
        kind = "space" if raw.isspace() and raw != "\n" else ("word" if re.fullmatch(r"[A-Za-z]+(?:['’][A-Za-z]+)*", raw) else "number" if re.fullmatch(r"\d+(?:[.,:/-]\d+)*%?", raw) else "char")
        value = " " if kind == "space" else raw
        tokens.append((kind, m.start(), m.end(), value))
    return tokens

# Descriptive aliases retained for callers and fixture builders.
normalize_match_text = normalize_match
normalize_diff_text = normalize_diff
