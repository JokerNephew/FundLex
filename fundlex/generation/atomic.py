"""Combine independently validated paragraph transforms on ORIGINAL coordinates."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

_ORPHAN_TAIL = re.compile(r"(?:[，,、；;：:]\s*)?(?:其中|以及|并且|同时|另外)\s*[，,：:]?$")
_DANGLING_TAIL = re.compile(r"[，,、；;：:]$")


def _trim_orphan_tail(result: str, original: str) -> str:
    """Drop a connector left dangling by a deletion at the paragraph end.

    Deleting ``其中，本基金对…`` or a trailing clause after ``其中，`` must not
    leave ``…列示。其中，`` in the artifact.  The trim only fires when the source
    paragraph did not already end that way, so authored trailing punctuation is
    never rewritten.
    """
    source = original.rstrip()
    if _ORPHAN_TAIL.search(source) or _DANGLING_TAIL.search(source):
        return result
    stripped = _ORPHAN_TAIL.sub("", result.rstrip())
    stripped = _DANGLING_TAIL.sub("", stripped.rstrip())
    return stripped if stripped else result


def compose_paragraph(original: str, components: Sequence[Mapping[str, Any]]) -> str | None:
    """Keep every component's own effect; decline incompatible changed intervals.

    A broad candidate span may overlap a sibling while the actual changes are
    disjoint. Only the changed intervals are combined. No text or operation identity
    is inferred here, and callers must validate each original component separately.
    """
    changes: list[tuple[int, int, str, int]] = []
    for order, component in enumerate(components):
        try:
            start, end = int(component["start"]), int(component["end"])
            replacement = str(component["replacement"])
        except (KeyError, TypeError, ValueError):
            return None
        if not 0 <= start <= end <= len(original):
            return None
        if component.get("expected_old_text") != original[start:end]:
            return None
        for kind, left, right, new_left, new_right in SequenceMatcher(
                None, original[start:end], replacement, autojunk=False).get_opcodes():
            if kind != "equal":
                changes.append((start + left, start + right, replacement[new_left:new_right], order))
    changes.sort(key=lambda item: (item[0], item[1], item[3]))
    for index, (start, end, _, _) in enumerate(changes):
        for other_start, other_end, _, _ in changes[index + 1:]:
            if other_start > end:
                break
            # Two inserts at the same point are ordered by the component ledger.
            if start == end == other_start == other_end:
                continue
            if other_start < end or start < other_end and other_start == start:
                return None
    result: list[str] = []
    cursor = 0
    for start, end, replacement, _ in changes:
        result.extend((original[cursor:start], replacement))
        cursor = end
    result.append(original[cursor:])
    composed = "".join(result)
    if composed != original:
        composed = _trim_orphan_tail(composed, original)
    return composed
