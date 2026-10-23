"""Deterministic block alignment with conservative high-recall semantics."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Sequence
from functools import lru_cache

from .models import AlignmentGroup, CompareBlock, CompareDocument
from .normalize import equivalent_text, normalize_match

MAX_GROUP = 3


def _scope(block: CompareBlock) -> tuple[object, ...]:
    if block.container == "table" or block.table_index is not None:
        return ("cell", block.table_index, block.row_index, block.cell_index)
    return ("body",)


def _anchor_scope(block: CompareBlock) -> tuple[object, ...]:
    # Row insertion shifts row indices. Column identity remains semantic.
    if block.table_index is not None:
        return ("table", block.table_index, block.cell_index)
    return ("body",)


@lru_cache(maxsize=50000)
def _sim_text(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if max(len(a), len(b)) > 256:
        # Alignment is allowed to be approximate, but running difflib over
        # thousands of characters for every 1..3 by 1..3 DP candidate makes
        # long contracts needlessly quadratic.  Cheap boundary evidence is
        # deterministic and deliberately only controls pairing; text_diff is
        # still authoritative for every paired group.
        ratio = min(len(a), len(b)) / max(len(a), len(b))
        width = min(48, len(a), len(b))
        prefix = sum(x == y for x, y in zip(a[:width], b[:width])) / max(width, 1)
        suffix = sum(x == y for x, y in zip(a[-width:], b[-width:])) / max(width, 1)
        return 0.55 * ratio + 0.25 * prefix + 0.20 * suffix
    # This score only chooses a candidate pairing; text_diff remains the
    # source of truth.  ``quick_ratio`` is linear-ish and deterministic, while
    # running full Ratcliff/Obershelp for every 1..3 by 1..3 DP candidate makes
    # long contracts quadratic in both blocks and characters.  It is also
    # conservative for recall: a false pairing still enters text diff and
    # cannot suppress a visible character difference.
    return SequenceMatcher(None, a, b, autojunk=False).quick_ratio()


def _sim(left: Sequence[CompareBlock], right: Sequence[CompareBlock]) -> float:
    return _sim_text("".join(b.match_text for b in left), "".join(c.match_text for c in right))


def _lis(anchors: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not anchors:
        return []
    # Standard deterministic LIS; ties preserve earliest anchor.
    tails: list[int] = []
    prev = [-1] * len(anchors)
    for i, (_, b) in enumerate(anchors):
        lo, hi = 0, len(tails)
        while lo < hi:
            mid = (lo + hi) // 2
            if anchors[tails[mid]][1] < b:
                lo = mid + 1
            else:
                hi = mid
        if lo:
            prev[i] = tails[lo - 1]
        if lo == len(tails):
            tails.append(i)
        else:
            tails[lo] = i
    result: list[tuple[int, int]] = []
    index = tails[-1] if tails else -1
    while index >= 0:
        result.append(anchors[index])
        index = prev[index]
    return list(reversed(result))


def _strong_anchors(left: Sequence[CompareBlock], right: Sequence[CompareBlock]) -> list[tuple[int, int]]:
    lmap: dict[tuple[object, ...], list[int]] = {}
    rmap: dict[tuple[object, ...], list[int]] = {}
    for i, b in enumerate(left):
        if b.match_text:
            lmap.setdefault((_anchor_scope(b), b.match_text), []).append(i)
    for j, b in enumerate(right):
        if b.match_text:
            rmap.setdefault((_anchor_scope(b), b.match_text), []).append(j)
    candidates = [(li[0], ri[0]) for key, li in lmap.items() if len(li) == 1 and len(rmap.get(key, ())) == 1 for ri in [rmap[key]]]
    return _lis(sorted(candidates))


def _compatible(left: Sequence[CompareBlock], right: Sequence[CompareBlock]) -> bool:
    if not left or not right:
        return True
    # Grouping must stay inside one physical cell independently on each side.
    # Pairing can span row offsets caused by insertion/deletion, while retaining
    # a matching column within the same table.
    lscopes = {_scope(b) for b in left}
    rscopes = {_scope(b) for b in right}
    return len(lscopes) == len(rscopes) == 1 and _anchor_scope(left[0]) == _anchor_scope(right[0])


def _safe_group(left: Sequence[CompareBlock], right: Sequence[CompareBlock]) -> bool:
    """Do not let a multi-block fuzzy pair swallow an exact neighbour.

    A deleted paragraph next to an unchanged paragraph can otherwise score as
    a plausible 2:1 merge.  The resulting character diff may then classify
    part of the deleted paragraph as context and lose recall.  True paragraph
    merges/splits have no constituent that is itself the complete counterpart,
    so this guard preserves those cases while forcing the ambiguous case into
    an exact pair plus insert/delete.
    """
    if len(left) == 1 and len(right) == 1:
        return True
    if len(left) > 1 or len(right) > 1:
        # Any exact constituent is a stronger explanation than a fuzzy
        # multi-block pairing. Split it out so an adjacent deletion/insertion
        # cannot be absorbed into a long merged group.
        left_texts = {b.match_text for b in left if b.match_text}
        right_texts = {b.match_text for b in right if b.match_text}
        if left_texts & right_texts:
            return False
    return True


def _window(left: Sequence[CompareBlock], right: Sequence[CompareBlock], start_l: int, end_l: int,
            start_r: int, end_r: int, counter: list[int]) -> list[AlignmentGroup]:
    a = left[start_l:end_l]
    b = right[start_r:end_r]
    n, m = len(a), len(b)
    if a and b and _compatible(a, b) and equivalent_text(
            "".join(x.raw_text for x in a), "".join(x.raw_text for x in b)):
        counter[0] += 1
        return [AlignmentGroup(f"G{counter[0]:04d}", tuple(a), tuple(b))]
    if n * m > 40000:
        # Unbounded quadratic fuzzy alignment is unnecessary for an ambiguous
        # huge gap. Explicit delete+insert preserves every changed character.
        result = []
        for lb, rb in [(tuple([x]), ()) for x in a] + [((), tuple([y])) for y in b]:
            counter[0] += 1
            result.append(AlignmentGroup(f"G{counter[0]:04d}", lb, rb))
        return result
    # dp[i][j] is minimum alignment cost from suffixes. Operations are
    # delete/insert or a 1..3 block group. Fuzzy score only chooses pairing.
    dp = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    op: list[list[tuple[str, int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    dp[n][m] = 0.0
    for i in range(n, -1, -1):
        for j in range(m, -1, -1):
            if i == n and j == m:
                continue
            if i < n and dp[i + 1][j] + 1.0 < dp[i][j]:
                dp[i][j], op[i][j] = dp[i + 1][j] + 1.0, ("del", 1, 0)
            if j < m and dp[i][j + 1] + 1.0 < dp[i][j]:
                dp[i][j], op[i][j] = dp[i][j + 1] + 1.0, ("ins", 0, 1)
            for ai in range(1, min(MAX_GROUP, n - i) + 1):
                for bj in range(1, min(MAX_GROUP, m - j) + 1):
                    if not _compatible(a[i:i + ai], b[j:j + bj]):
                        continue
                    if not _safe_group(a[i:i + ai], b[j:j + bj]):
                        continue
                    score = _sim(a[i:i + ai], b[j:j + bj])
                    # Pairing must have meaningful evidence. Exact normalized
                    # equality always pairs; otherwise conservative threshold
                    # avoids swallowing unrelated clauses as one modification.
                    if score < 0.82 and score < 0.999:
                        continue
                    cost = (1.0 - score) + 0.005 * (ai + bj - 2)
                    if dp[i + ai][j + bj] + cost < dp[i][j]:
                        dp[i][j] = dp[i + ai][j + bj] + cost
                        op[i][j] = ("pair", ai, bj)
    groups: list[AlignmentGroup] = []
    i = j = 0
    while i < n or j < m:
        choice = op[i][j]
        if choice is None:
            # Defensive fail-safe; every remainder becomes explicit insert/delete.
            if i < n:
                choice = ("del", 1, 0)
            else:
                choice = ("ins", 0, 1)
        kind, ai, bj = choice
        counter[0] += 1
        gid = f"G{counter[0]:04d}"
        if kind == "pair":
            groups.append(AlignmentGroup(gid, tuple(a[i:i + ai]), tuple(b[j:j + bj])))
            i += ai; j += bj
        elif kind == "del":
            groups.append(AlignmentGroup(gid, tuple(a[i:i + ai]), ()))
            i += ai
        else:
            groups.append(AlignmentGroup(gid, (), tuple(b[j:j + bj])))
            j += bj
    return groups


def _align_ordered(la: tuple[CompareBlock, ...], rb: tuple[CompareBlock, ...]):
    """Align two documents, returning ordered groups and diagnostics."""
    # Whole structural runs may differ only in paragraph boundaries. Check this
    # before exact anchors: a short constituent could otherwise become an anchor
    # that cuts a legitimate split/merge into false inserts and deletes.
    def runs(blocks):
        result = []
        for block in blocks:
            if result and _scope(result[-1][-1]) == _scope(block):
                result[-1].append(block)
            else:
                result.append([block])
        return result
    lr, rr = runs(la), runs(rb)
    regroup = len(lr) == len(rr) and all(
        _compatible(a, b) and equivalent_text("".join(x.raw_text for x in a), "".join(x.raw_text for x in b))
        for a, b in zip(lr, rr))
    if regroup:
        groups = tuple(AlignmentGroup(f"G{i:04d}", tuple(a), tuple(b))
                       for i, (a, b) in enumerate(zip(lr, rr), 1))
        return groups, _diagnostics(la, rb, groups, 0)
    anchors = _strong_anchors(la, rb)
    groups: list[AlignmentGroup] = []
    counter = [0]
    li = ri = 0
    for ai, bj in anchors:
        groups.extend(_window(la, rb, li, ai, ri, bj, counter))
        counter[0] += 1
        groups.append(AlignmentGroup(f"G{counter[0]:04d}", (la[ai],), (rb[bj],)))
        li, ri = ai + 1, bj + 1
    groups.extend(_window(la, rb, li, len(la), ri, len(rb), counter))
    return tuple(groups), _diagnostics(la, rb, groups, len(anchors))


def _diagnostics(la, rb, groups, strong_anchors):
    return {
        "left_blocks": len(la), "right_blocks": len(rb),
        "strong_anchors": strong_anchors, "aligned_groups": sum(bool(g.left and g.right) for g in groups),
        "one_to_many": sum(bool(g.left) and len(g.left) == 1 and len(g.right) > 1 for g in groups),
        "many_to_one": sum(bool(g.right) and len(g.right) == 1 and len(g.left) > 1 for g in groups),
        "unmatched_left": sum(len(g.left) for g in groups if not g.right),
        "unmatched_right": sum(len(g.right) for g in groups if not g.left),
    }


def align_documents(left: CompareDocument | Sequence[CompareBlock], right: CompareDocument | Sequence[CompareBlock]) -> tuple[tuple[AlignmentGroup, ...], dict[str, int]]:
    """Choose anchor/DP ties in one orientation, then restore caller sides."""
    la = tuple(left.blocks if isinstance(left, CompareDocument) else left)
    rb = tuple(right.blocks if isinstance(right, CompareDocument) else right)
    def key(blocks):
        return tuple((b.raw_text, b.container, str(b.table_index), str(b.row_index), str(b.cell_index)) for b in blocks)
    if key(la) <= key(rb):
        return _align_ordered(la, rb)
    groups, diagnostics = _align_ordered(rb, la)
    swapped = tuple(AlignmentGroup(g.group_id, g.right, g.left) for g in groups)
    return swapped, _diagnostics(la, rb, swapped, diagnostics["strong_anchors"])


align = align_documents

# Public name used in design notes.
sequence_align = align_documents
