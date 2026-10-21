"""Combine independently validated paragraph transforms on ORIGINAL coordinates."""
from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence


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
    return "".join(result)
