"""Character/token level deterministic diff for aligned block groups."""
from __future__ import annotations

from dataclasses import replace
from difflib import SequenceMatcher
from typing import Sequence

from .align import align_documents
from .models import AlignmentGroup, CompareDocument, CompareResult, DiffItem, TextSpan
from .normalize import equivalent_text, tokenize
from .parser import parse_compare_document


def _segments(blocks: Sequence, start: int, end: int) -> tuple[TextSpan, ...]:
    result: list[TextSpan] = []
    cursor = 0
    for block in blocks:
        length = len(block.raw_text)
        lo, hi = max(start, cursor), min(end, cursor + length)
        if lo < hi:
            local_start, local_end = lo - cursor, hi - cursor
            result.append(TextSpan(block.block_id, local_start, local_end, block.raw_text[local_start:local_end]))
        cursor += length
    return tuple(result)


def _primary(spans: tuple[TextSpan, ...]) -> TextSpan | None:
    return spans[0] if spans else None


def _anchor(blocks: Sequence, side: str, offset: int = 0) -> TextSpan:
    if blocks:
        cursor = 0
        for block in blocks:
            if offset <= cursor + len(block.raw_text):
                local = max(0, offset - cursor)
                return TextSpan(block.block_id, local, local, "")
            cursor += len(block.raw_text)
        last = blocks[-1]
        return TextSpan(last.block_id, len(last.raw_text), len(last.raw_text), "")
    return TextSpan(f"{side}-virtual", 0, 0, "")


def _symmetric_opcodes(left_values: list[str], right_values: list[str]):
    """Return deterministic opcodes whose semantic result is swap-symmetric.

    ``SequenceMatcher`` has direction-dependent tie breaking when several
    longest matches are possible.  That is useful for a display diff, but it
    can make ``compare(A, B)`` select different changed text from
    ``compare(B, A)``.  Choose one canonical orientation for the matcher and
    invert its opcodes when the caller supplied the other orientation.  This
    only affects the chosen alignment; every non-equal token is still emitted.
    """
    if tuple(left_values) <= tuple(right_values):
        matcher = SequenceMatcher(None, left_values, right_values, autojunk=False)
        return list(matcher.get_opcodes())

    matcher = SequenceMatcher(None, right_values, left_values, autojunk=False)
    inverted = []
    inverse_tag = {"equal": "equal", "replace": "replace", "delete": "insert", "insert": "delete"}
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        inverted.append((inverse_tag[tag], j1, j2, i1, i2))
    return inverted
    return TextSpan(f"{side}-virtual", 0, 0, "")


def diff_group(group: AlignmentGroup, *, id_start: int = 1) -> tuple[list[DiffItem], int]:
    """Diff one alignment group and return items plus next deterministic ID."""
    left = tuple(group.left)
    right = tuple(group.right)
    lt = "".join(b.raw_text for b in left)
    rt = "".join(b.raw_text for b in right)
    if equivalent_text(lt, rt):
        return [], id_start
    ltok = tokenize(lt)
    rtok = tokenize(rt)
    opcodes = _symmetric_opcodes([x[3] for x in ltok], [x[3] for x in rtok])
    out: list[DiffItem] = []
    next_id = id_start
    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            continue
        ls = ltok[i1][1] if i1 < len(ltok) else len(lt)
        le = ltok[i2 - 1][2] if i2 > i1 else ls
        rs = rtok[j1][1] if j1 < len(rtok) else len(rt)
        re = rtok[j2 - 1][2] if j2 > j1 else rs
        # An opcode made solely from whitespace is ignored by the contract's
        # repeated-horizontal-space rule. Other visible punctuation/numbers stay.
        lraw, rraw = lt[ls:le], rt[rs:re]
        if tag == "replace" and equivalent_text(lraw, rraw):
            continue
        left_spans = _segments(left, ls, le)
        right_spans = _segments(right, rs, re)
        dtype = "modify" if tag == "replace" else "delete" if tag == "delete" else "insert"
        item = DiffItem(
            diff_id=f"D{next_id:04d}", type=dtype,
            left=_primary(left_spans), right=_primary(right_spans),
            left_anchor=None if left_spans else _anchor(left, "L", ls),
            right_anchor=None if right_spans else _anchor(right, "R", rs),
            left_spans=left_spans, right_spans=right_spans,
            group_id=group.group_id,
            section=(left[0].section_path if left else right[0].section_path if right else ""),
        )
        out.append(item)
        next_id += 1
    return out, next_id


def compare_documents(left: CompareDocument, right: CompareDocument) -> CompareResult:
    groups, diagnostics = align_documents(left, right)
    diffs: list[DiffItem] = []
    next_id = 1
    for group_index, group in enumerate(groups):
        current, next_id = diff_group(group, id_start=next_id)
        for item in current:
            # Bind empty-side markers to the nearest real block so the renderer
            # can materialize a DOM anchor and draw a line even for insertion or
            # deletion groups. Boundary anchors use start=0/end=len(block).
            if not group.left and item.left is None and not item.left_spans:
                anchor = None
                for k in range(group_index - 1, -1, -1):
                    if groups[k].left:
                        b = groups[k].left[-1]; anchor = TextSpan(b.block_id, len(b.raw_text), len(b.raw_text), ""); break
                if anchor is None:
                    for k in range(group_index + 1, len(groups)):
                        if groups[k].left:
                            b = groups[k].left[0]; anchor = TextSpan(b.block_id, 0, 0, ""); break
                if anchor is None:
                    anchor = item.left_anchor
                item = replace(item, left_anchor=anchor)
            if not group.right and item.right is None and not item.right_spans:
                anchor = None
                for k in range(group_index - 1, -1, -1):
                    if groups[k].right:
                        b = groups[k].right[-1]; anchor = TextSpan(b.block_id, len(b.raw_text), len(b.raw_text), ""); break
                if anchor is None:
                    for k in range(group_index + 1, len(groups)):
                        if groups[k].right:
                            b = groups[k].right[0]; anchor = TextSpan(b.block_id, 0, 0, ""); break
                if anchor is None:
                    anchor = item.right_anchor
                item = replace(item, right_anchor=anchor)
            diffs.append(item)
    diagnostics = dict(diagnostics)
    diagnostics["processing_version"] = "contract-compare-v1"
    diagnostics["coverage_warnings"] = len(left.coverage.warnings) + len(right.coverage.warnings)
    status = "incomplete" if left.coverage.status != "complete" or right.coverage.status != "complete" else "complete"
    from .models import Coverage
    coverage = Coverage(status, tuple(dict.fromkeys(left.coverage.warnings + right.coverage.warnings)))
    return CompareResult("contract-compare-v1", left, right, groups, tuple(diffs), coverage, diagnostics)


def compare_docx(left, right, *, left_filename: str = "", right_filename: str = "") -> CompareResult:
    ldoc = left if isinstance(left, CompareDocument) else parse_compare_document(left, filename=left_filename, side="L")
    rdoc = right if isinstance(right, CompareDocument) else parse_compare_document(right, filename=right_filename, side="R")
    return compare_documents(ldoc, rdoc)


compare = compare_documents

def diff_text(left, right=None, *, id_start: int = 1):
    """Diff an :class:`AlignmentGroup` or two plain strings.

    Plain-string mode is convenient for algorithm tests and returns
    :class:`DiffItem` objects with synthetic ``left``/``right`` block IDs;
    document comparison always uses :func:`diff_group` so real locations are
    preserved.
    """
    if isinstance(left, AlignmentGroup):
        return diff_group(left, id_start=id_start)
    if right is None:
        raise TypeError("right text is required")
    lblock = type("_Block", (), {"block_id": "L-text", "raw_text": str(left), "section_path": ""})()
    rblock = type("_Block", (), {"block_id": "R-text", "raw_text": str(right), "section_path": ""})()
    return diff_group(AlignmentGroup("G-text", (lblock,), (rblock,)), id_start=id_start)[0]


compute_text_diff = diff_text
