"""Safe, bounded OOXML generation for Compare selections.

The first writer supports ordinary single-paragraph edits in the main body,
including ordinary table-cell paragraphs.  It starts from the left DOCX and
copies only selected right-side text into the corresponding left-side range.
Anything that cannot be mapped to one safe paragraph is rejected before an
output file is published.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from lxml import etree

from ..docx import (
    DOCUMENT,
    Q,
    DocxError,
    ZipLimits,
    _read_parts,
    _validate_package,
    _write_package,
    _xml,
    _paragraph_element,
    _safe_grapheme_boundary,
    _structure_snapshot,
    _non_target_snapshot,
)
from .parser import parse_compare_document
from .selection import SelectionError, make_snapshot
from .text_diff import compare_documents


def _digest_bytes(data: bytes) -> str:
    return sha256(data).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest_json(value: Any) -> str:
    return _digest_bytes(_canonical(value))


@dataclass(frozen=True)
class SelectionArtifactValidation:
    final_sha256: str
    redline_sha256: str
    selection_epoch: int
    decision_hash: str
    binding_hash: str
    manifest: tuple[Mapping[str, Any], ...]
    checks: tuple[str, ...]
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_sha256": self.final_sha256,
            "redline_sha256": self.redline_sha256,
            "selection_epoch": self.selection_epoch,
            "decision_hash": self.decision_hash,
            "binding_hash": self.binding_hash,
            "manifest": [dict(item) for item in self.manifest],
            "checks": list(self.checks),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class _Operation:
    diff_id: str
    decision: str
    location: str
    start: int
    end: int
    old_text: str
    new_text: str


@dataclass(frozen=True)
class _BlockOperation:
    """A whole-paragraph insert/delete or a paragraph-range replacement.

    ``left_ids``/``right_ids`` refer to Compare blocks in the left/right
    documents.  Block operations are applied only after all ordinary
    single-paragraph operations, so their original paragraph indices remain
    stable.
    """

    diff_id: str
    decision: str
    kind: str  # insert | delete | replace
    left_ids: tuple[str, ...] = ()
    right_ids: tuple[str, ...] = ()
    anchor_id: str = ""
    anchor_position: str = ""  # before | after
    left_text: str = ""
    right_text: str = ""


def _span(diff: Mapping[str, Any], side: str, *, required: bool = True) -> Mapping[str, Any] | None:
    values = diff.get(f"{side}_spans")
    if values is not None:
        if not isinstance(values, list):
            raise DocxError("SELECTION_RESULT_INVALID")
        if required and len(values) != 1:
            raise DocxError("SELECTION_MULTI_BLOCK_UNSUPPORTED")
        return values[0] if values else None
    value = diff.get(side)
    if required and value is None:
        raise DocxError("SELECTION_SPAN_MISSING")
    return value


def _anchor(diff: Mapping[str, Any], side: str) -> Mapping[str, Any] | None:
    value = diff.get(f"{side}_anchor")
    return value if isinstance(value, Mapping) else None


def _text(value: Mapping[str, Any] | None) -> str:
    return str(value.get("text", "")) if value else ""


def _validate_span(document, value: Mapping[str, Any] | None, *, anchor: bool = False) -> Any:
    if not isinstance(value, Mapping):
        raise DocxError("SELECTION_SPAN_MISSING")
    block_id = value.get("block_id")
    block = next((item for item in document.blocks if item.block_id == block_id), None)
    if block is None:
        raise DocxError("SELECTION_BLOCK_NOT_FOUND")
    start, end, text = value.get("start"), value.get("end"), value.get("text")
    if type(start) is not int or type(end) is not int or not isinstance(text, str):
        raise DocxError("SELECTION_SPAN_INVALID")
    if anchor:
        if start != end or text or not 0 <= start <= len(block.raw_text):
            raise DocxError("SELECTION_ANCHOR_INVALID")
    elif start < 0 or end <= start or end > len(block.raw_text):
        raise DocxError("SELECTION_SPAN_INVALID")
    if not anchor and block.raw_text[start:end] != text:
        raise DocxError("SELECTION_SPAN_MISMATCH")
    if block.kind not in {"paragraph", "table_paragraph"}:
        raise DocxError("SELECTION_BLOCK_UNSUPPORTED")
    if block.table_cell_continuation or block.table_colspan != 1 or block.table_rowspan != 1:
        raise DocxError("SELECTION_MERGED_CELL_UNSUPPORTED")
    if block.location.startswith("sdt") or "/sdt" in block.location:
        raise DocxError("SELECTION_CONTENT_CONTROL_UNSUPPORTED")
    return block


def _span_text(document, value: Mapping[str, Any] | None, *, required: bool = True) -> tuple[Any, str]:
    if value is None and not required:
        return None, ""
    block = _validate_span(document, value)
    return block, _text(value)


def _modify_group_compatible(group, left_span: Mapping[str, Any],
                             right_span: Mapping[str, Any]) -> bool:
    """Return True when a modify stays within corresponding group blocks.

    A paragraph-by-paragraph comparison commonly groups several consecutive
    modified paragraphs into one alignment group (for example 2 left blocks
    against 2 right blocks).  Such a group is safe when each diff is still a
    single-block edit and its left block has the same ordinal as its right
    block.  The previous ``(1, 1)`` shape check rejected these ordinary edits
    even though no cross-paragraph structure was involved.
    """
    if group is None or not getattr(group, "left", ()) or not getattr(group, "right", ()):
        return False
    if len(group.left) != len(group.right):
        return False
    left_id, right_id = left_span.get("block_id"), right_span.get("block_id")
    left_ids = [block.block_id for block in group.left]
    right_ids = [block.block_id for block in group.right]
    if left_id not in left_ids or right_id not in right_ids:
        return False
    return left_ids.index(left_id) == right_ids.index(right_id)


def _spans_for_side(diff: Mapping[str, Any], side: str) -> tuple[Mapping[str, Any], ...]:
    values = diff.get(f"{side}_spans")
    if values is not None:
        if not isinstance(values, list):
            raise DocxError("SELECTION_RESULT_INVALID")
        return tuple(value for value in values if isinstance(value, Mapping))
    value = diff.get(side)
    return (value,) if isinstance(value, Mapping) else ()


def _blocks_for_spans(document, spans: Sequence[Mapping[str, Any]], *, side: str) -> tuple[Any, ...]:
    blocks: list[Any] = []
    for span in spans:
        block = _validate_span(document, span)
        if not blocks or blocks[-1].block_id != block.block_id:
            blocks.append(block)
    if not blocks:
        raise DocxError("SELECTION_BLOCK_RANGE_UNSUPPORTED", f"{side} side has no paragraph")
    ordinals = [block.ordinal for block in blocks]
    if ordinals != list(range(ordinals[0], ordinals[0] + len(ordinals))):
        raise DocxError("SELECTION_BLOCK_RANGE_UNSUPPORTED", f"{side} side is not contiguous")
    return tuple(blocks)


def _block_scope(block) -> tuple[Any, ...]:
    if block.container == "table" or block.kind == "table_paragraph":
        return ("table", block.table_index, block.row_index, block.cell_index)
    return ("body",)


def _check_block(block) -> None:
    if block.kind not in {"paragraph", "table_paragraph"}:
        raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
    if block.table_cell_continuation or block.table_colspan != 1 or block.table_rowspan != 1:
        raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
    if block.location.startswith("sdt") or "/sdt" in block.location:
        raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
    if block.container == "table" and (
            block.table_index is None or block.row_index is None or block.cell_index is None):
        raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)


def _full_block_coverage(blocks: Sequence[Any], spans: Sequence[Mapping[str, Any]]) -> bool:
    by_block: dict[str, list[Mapping[str, Any]]] = {}
    for span in spans:
        by_block.setdefault(str(span.get("block_id", "")), []).append(span)
    for block in blocks:
        values = by_block.get(block.block_id, [])
        if len(values) != 1:
            return False
        value = values[0]
        if value.get("start") != 0 or value.get("end") != len(block.raw_text):
            return False
    return True


def _diff_touch_map(diffs: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    touches: dict[str, set[str]] = {}
    for diff in diffs:
        diff_id = str(diff.get("id", ""))
        for side in ("left", "right"):
            for span in _spans_for_side(diff, side):
                block_id = span.get("block_id")
                if isinstance(block_id, str):
                    touches.setdefault(block_id, set()).add(diff_id)
    return touches


def _no_other_diff(touches: Mapping[str, set[str]], diff_id: str, blocks: Sequence[Any]) -> None:
    for block in blocks:
        others = sorted(touches.get(block.block_id, set()) - {diff_id})
        if others:
            raise DocxError("SELECTION_BLOCK_OVERLAP", f"{block.block_id}:{','.join(others)}")


def _make_block_operation(*, diff_id: str, kind: str, left_blocks: Sequence[Any],
                          right_blocks: Sequence[Any], anchor_block=None, anchor_position: str = "",
                          touches: Mapping[str, set[str]]) -> _BlockOperation:
    if kind in {"replace", "delete"}:
        if not left_blocks:
            raise DocxError("SELECTION_BLOCK_RANGE_UNSUPPORTED", diff_id)
        for block in left_blocks:
            _check_block(block)
        scopes = {_block_scope(block) for block in left_blocks}
        if len(scopes) != 1:
            raise DocxError("SELECTION_BLOCK_SCOPE_UNSUPPORTED", diff_id)
        _no_other_diff(touches, diff_id, left_blocks)
    if kind in {"replace", "insert"}:
        if not right_blocks:
            raise DocxError("SELECTION_BLOCK_RANGE_UNSUPPORTED", diff_id)
        for block in right_blocks:
            _check_block(block)
        right_scopes = {_block_scope(block) for block in right_blocks}
        if len(right_scopes) != 1:
            raise DocxError("SELECTION_BLOCK_SCOPE_UNSUPPORTED", diff_id)
        _no_other_diff(touches, diff_id, right_blocks)
    if kind == "replace":
        if scopes != right_scopes:
            raise DocxError("SELECTION_BLOCK_SCOPE_UNSUPPORTED", diff_id)
    if kind == "insert":
        if anchor_block is None or anchor_position not in {"before", "after"}:
            raise DocxError("SELECTION_BLOCK_ANCHOR_UNSUPPORTED", diff_id)
        _check_block(anchor_block)
        if _block_scope(anchor_block) != right_scopes.copy().pop():
            raise DocxError("SELECTION_BLOCK_SCOPE_UNSUPPORTED", diff_id)
    return _BlockOperation(
        diff_id=diff_id, decision="right", kind=kind,
        left_ids=tuple(block.block_id for block in left_blocks),
        right_ids=tuple(block.block_id for block in right_blocks),
        anchor_id=anchor_block.block_id if anchor_block is not None else "",
        anchor_position=anchor_position,
        left_text="".join(block.raw_text for block in left_blocks),
        right_text="".join(block.raw_text for block in right_blocks),
    )


def _build_plan(left_doc, right_doc, diffs: Sequence[Mapping[str, Any]], decisions: Mapping[str, str],
                alignment) -> tuple[tuple[_Operation, ...], tuple[_BlockOperation, ...]]:
    inline: list[_Operation] = []
    blocks: list[_BlockOperation] = []
    groups = {group.group_id: group for group in alignment}
    touches = _diff_touch_map(diffs)
    for diff in diffs:
        diff_id = str(diff.get("id", ""))
        decision = decisions[diff_id]
        if decision != "right":
            continue
        kind = str(diff.get("type", ""))
        group = groups.get(diff.get("group_id"))
        left_spans = _spans_for_side(diff, "left")
        right_spans = _spans_for_side(diff, "right")
        if kind == "modify":
            if len(left_spans) <= 1 and len(right_spans) <= 1:
                left_span = _span(diff, "left")
                right_span = _span(diff, "right")
                if not _modify_group_compatible(group, left_span, right_span):
                    raise DocxError("SELECTION_STRUCTURAL_DIFF_UNSUPPORTED")
                left_block, left_text = _span_text(left_doc, left_span)
                _, right_text = _span_text(right_doc, right_span)
                inline.append(_Operation(diff_id, decision, left_block.location,
                                         int(left_span["start"]), int(left_span["end"]),
                                         left_text, right_text))
            else:
                left_blocks = _blocks_for_spans(left_doc, left_spans, side="left")
                right_blocks = _blocks_for_spans(right_doc, right_spans, side="right")
                blocks.append(_make_block_operation(
                    diff_id=diff_id, kind="replace", left_blocks=left_blocks,
                    right_blocks=right_blocks, touches=touches))
        elif kind == "insert":
            if group is not None and group.left:
                # Inline insertion inside an existing paragraph.
                if len(right_spans) != 1:
                    raise DocxError("SELECTION_STRUCTURAL_DIFF_UNSUPPORTED")
                anchor = _anchor(diff, "left")
                left_block = _validate_span(left_doc, anchor, anchor=True)
                _, right_text = _span_text(right_doc, _span(diff, "right"))
                inline.append(_Operation(diff_id, decision, left_block.location,
                                         int(anchor["start"]), int(anchor["end"]), "", right_text))
            else:
                right_blocks = _blocks_for_spans(right_doc, right_spans, side="right")
                if not _full_block_coverage(right_blocks, right_spans):
                    raise DocxError("SELECTION_BLOCK_PARTIAL_UNSUPPORTED", diff_id)
                anchor = _anchor(diff, "left")
                anchor_block = _validate_span(left_doc, anchor, anchor=True)
                if anchor["start"] == len(anchor_block.raw_text):
                    position = "after"
                elif anchor["start"] == 0:
                    position = "before"
                else:
                    raise DocxError("SELECTION_BLOCK_ANCHOR_UNSUPPORTED", diff_id)
                blocks.append(_make_block_operation(
                    diff_id=diff_id, kind="insert", left_blocks=(),
                    right_blocks=right_blocks, anchor_block=anchor_block,
                    anchor_position=position, touches=touches))
        elif kind == "delete":
            if group is not None and group.right:
                # Inline deletion inside an existing paragraph.
                if len(left_spans) != 1:
                    raise DocxError("SELECTION_STRUCTURAL_DIFF_UNSUPPORTED")
                left_span = _span(diff, "left")
                left_block, left_text = _span_text(left_doc, left_span)
                inline.append(_Operation(diff_id, decision, left_block.location,
                                         int(left_span["start"]), int(left_span["end"]),
                                         left_text, ""))
            else:
                left_blocks = _blocks_for_spans(left_doc, left_spans, side="left")
                if not _full_block_coverage(left_blocks, left_spans):
                    raise DocxError("SELECTION_BLOCK_PARTIAL_UNSUPPORTED", diff_id)
                blocks.append(_make_block_operation(
                    diff_id=diff_id, kind="delete", left_blocks=left_blocks,
                    right_blocks=(), touches=touches))
        else:
            raise DocxError("SELECTION_RESULT_INVALID")
    # Cross-block operations must not share a parent with each other.  The
    # selection contract already rejects overlapping visible spans; this is a
    # second, structural guard for malicious result payloads.
    return tuple(inline), tuple(blocks)


def _run_text(run: etree._Element) -> str:
    children = [child for child in run if child.tag != Q("rPr")]
    if len(children) != 1 or children[0].tag != Q("t"):
        raise DocxError("SELECTION_RUN_UNSUPPORTED")
    return children[0].text or ""


def _copy_run(template: etree._Element | None, value: str, *, deleted: bool = False) -> etree._Element:
    run = etree.Element(Q("r"))
    if template is not None:
        properties = template.find(Q("rPr"))
        if properties is not None:
            run.append(deepcopy(properties))
    text = etree.SubElement(run, Q("delText") if deleted else Q("t"))
    if value.startswith(" ") or value.endswith(" "):
        text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text.text = value
    return run


def _text_runs(template: etree._Element | None, value: str, *, deleted: bool = False) -> list[etree._Element]:
    result: list[etree._Element] = []
    for index, line in enumerate(value.split("\n")):
        if index:
            result.append(etree.Element(Q("r")))
            etree.SubElement(result[-1], Q("br"))
        if line:
            result.append(_copy_run(template, line, deleted=deleted))
    return result


def _revision(tag: str, revision_id: int, runs: Sequence[etree._Element], when: str) -> etree._Element:
    wrapper = etree.Element(Q(tag))
    wrapper.set(Q("id"), str(revision_id))
    wrapper.set(Q("author"), "FundLex Compare")
    wrapper.set(Q("date"), when)
    wrapper.extend(runs)
    return wrapper


def _direct_runs(paragraph: etree._Element) -> tuple[list[etree._Element], str]:
    runs: list[etree._Element] = []
    values: list[str] = []
    for child in paragraph:
        if child.tag == Q("pPr"):
            continue
        if child.tag != Q("r"):
            raise DocxError("SELECTION_PARAGRAPH_UNSUPPORTED")
        value = _run_text(child)
        runs.append(child)
        values.append(value)
    return runs, "".join(values)


def _template_at(runs: Sequence[etree._Element], starts: Sequence[int], offset: int) -> etree._Element | None:
    for run, start in zip(runs, starts):
        end = start + len(_run_text(run))
        if start <= offset < end:
            return run
    return runs[-1] if runs else None


def _plain_range(runs: Sequence[etree._Element], starts: Sequence[int], start: int, end: int) -> list[etree._Element]:
    result: list[etree._Element] = []
    for run, run_start in zip(runs, starts):
        value = _run_text(run)
        run_end = run_start + len(value)
        lo, hi = max(start, run_start), min(end, run_end)
        if lo < hi:
            result.extend(_text_runs(run, value[lo - run_start:hi - run_start]))
    return result


def _rewrite_paragraph(paragraph: etree._Element, operations: Sequence[_Operation], *, redline: bool,
                       revision_start: int, when: str) -> int:
    runs, source_text = _direct_runs(paragraph)
    starts: list[int] = []
    cursor = 0
    for run in runs:
        starts.append(cursor)
        cursor += len(_run_text(run))
    if not operations and source_text:
        return revision_start
    ordered = sorted(operations, key=lambda item: (item.start, item.end, item.diff_id))
    if any(item.start < 0 or item.end < item.start or item.end > len(source_text)
           or source_text[item.start:item.end] != item.old_text for item in ordered):
        raise DocxError("SELECTION_SOURCE_TEXT_MISMATCH")
    if any(not _safe_grapheme_boundary(source_text, position)
           for item in ordered for position in (item.start, item.end)):
        raise DocxError("GRAPHEME_BOUNDARY_INVALID")
    output: list[etree._Element] = []
    cursor = 0
    revision_id = revision_start
    for operation in ordered:
        output.extend(_plain_range(runs, starts, cursor, operation.start))
        template = _template_at(runs, starts, operation.start)
        if redline:
            if operation.old_text:
                deleted = _plain_range(runs, starts, operation.start, operation.end)
                deleted_runs = []
                for node in deleted:
                    # _plain_range already copied a plain run. Convert its
                    # visible text into a deleted run while retaining rPr.
                    deleted_runs.extend(_text_runs(node, _run_text(node), deleted=True))
                output.append(_revision("del", revision_id, deleted_runs, when))
                revision_id += 1
            if operation.new_text:
                output.append(_revision("ins", revision_id, _text_runs(template, operation.new_text), when))
                revision_id += 1
        else:
            output.extend(_text_runs(template, operation.new_text))
        cursor = operation.end
    output.extend(_plain_range(runs, starts, cursor, len(source_text)))
    ppr = paragraph.find(Q("pPr"))
    for child in list(paragraph):
        if child.tag == Q("r"):
            paragraph.remove(child)
    insert_at = paragraph.index(ppr) + 1 if ppr is not None else 0
    for offset, node in enumerate(output):
        paragraph.insert(insert_at + offset, node)
    return revision_id


def _apply_operations(root: etree._Element, operations: Sequence[_Operation], *, redline: bool,
                      revision_start: int = 1, when: str | None = None) -> int:
    locations = sorted({operation.location for operation in operations})
    next_id = revision_start
    when = when or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for location in locations:
        paragraph = _paragraph_element(root, location)
        next_id = _rewrite_paragraph(paragraph, [item for item in operations if item.location == location],
                                     redline=redline, revision_start=next_id, when=when)
    return next_id


def _simple_paragraph(document, block) -> etree._Element:
    """Return a paragraph element only when its direct structure is safe."""
    element = _paragraph_element(document, block.location)
    if element.tag != Q("p"):
        raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
    ppr = element.find(Q("pPr"))
    if ppr is not None:
        if ppr.find(Q("sectPr")) is not None:
            raise DocxError("SELECTION_BLOCK_SECTION_UNSUPPORTED", block.block_id)
        if ppr.find(Q("pPrChange")) is not None:
            raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
    for child in list(element):
        if child.tag in {Q("pPr"), Q("bookmarkStart"), Q("bookmarkEnd"),
                         Q("proofErr"), Q("lastRenderedPageBreak")}:
            continue
        if child.tag != Q("r"):
            raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
        texts = 0
        for value in child:
            if value.tag == Q("rPr"):
                continue
            if value.tag == Q("t"):
                texts += 1
                if texts > 1:
                    raise DocxError("SELECTION_BLOCK_RUN_UNSUPPORTED", block.block_id)
            elif value.tag not in {Q("br"), Q("tab")}:
                raise DocxError("SELECTION_BLOCK_RUN_UNSUPPORTED", block.block_id)
    return element


def _clone_paragraph(element: etree._Element, block) -> etree._Element:
    clone = deepcopy(element)
    # Navigation anchors and proofing hints are not business content and can
    # collide with existing bookmark IDs in the left package.  Drop them from
    # inserted paragraphs; the surrounding document keeps its own anchors.
    for node in list(clone):
        if node.tag in {Q("bookmarkStart"), Q("bookmarkEnd"), Q("proofErr"),
                        Q("lastRenderedPageBreak")}:
            clone.remove(node)
    _simple_paragraph_element(clone, block)
    return clone


def _simple_paragraph_element(element: etree._Element, block) -> None:
    if element.tag != Q("p"):
        raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
    ppr = element.find(Q("pPr"))
    if ppr is not None and ppr.find(Q("sectPr")) is not None:
        raise DocxError("SELECTION_BLOCK_SECTION_UNSUPPORTED", block.block_id)
    for child in list(element):
        if child.tag in {Q("pPr"), Q("bookmarkStart"), Q("bookmarkEnd"),
                         Q("proofErr"), Q("lastRenderedPageBreak")}:
            continue
        if child.tag != Q("r"):
            raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block.block_id)
        texts = 0
        for value in child:
            if value.tag == Q("rPr"):
                continue
            if value.tag == Q("t"):
                texts += 1
                if texts > 1:
                    raise DocxError("SELECTION_BLOCK_RUN_UNSUPPORTED", block.block_id)
            elif value.tag not in {Q("br"), Q("tab")}:
                raise DocxError("SELECTION_BLOCK_RUN_UNSUPPORTED", block.block_id)


def _paragraph_mark(element: etree._Element, tag: str, revision_id: int, when: str) -> None:
    ppr = element.find(Q("pPr"))
    if ppr is None:
        ppr = etree.Element(Q("pPr"))
        element.insert(0, ppr)
    rpr = ppr.find(Q("rPr"))
    if rpr is None:
        rpr = etree.SubElement(ppr, Q("rPr"))
    rpr.append(_revision(tag, revision_id, (), when))


def _mark_inserted_paragraph(element: etree._Element, block, revision_start: int, when: str) -> int:
    _simple_paragraph_element(element, block)
    next_id = revision_start
    _paragraph_mark(element, "ins", next_id, when)
    next_id += 1
    for child in list(element):
        if child.tag == Q("r"):
            index = element.index(child)
            wrapper = _revision("ins", next_id, [child], when)
            element.insert(index, wrapper)
            next_id += 1
    return next_id


def _mark_deleted_paragraph(element: etree._Element, block, revision_start: int, when: str) -> int:
    _simple_paragraph_element(element, block)
    next_id = revision_start
    _paragraph_mark(element, "del", next_id, when)
    next_id += 1
    for child in list(element):
        if child.tag != Q("r"):
            continue
        for text in child.findall(Q("t")):
            text.tag = Q("delText")
        index = element.index(child)
        wrapper = _revision("del", next_id, [child], when)
        element.insert(index, wrapper)
        next_id += 1
    return next_id


def _left_blocks_by_id(left_doc) -> dict[str, Any]:
    return {block.block_id: block for block in left_doc.blocks}


def _right_blocks_by_id(right_doc) -> dict[str, Any]:
    return {block.block_id: block for block in right_doc.blocks}


def _apply_block_operations(root: etree._Element, left_doc, right_doc,
                            block_operations: Sequence[_BlockOperation], right_root: etree._Element,
                            *, redline: bool, revision_start: int, when: str) -> int:
    left_by_id = _left_blocks_by_id(left_doc)
    right_by_id = _right_blocks_by_id(right_doc)
    entries: dict[int, list[tuple[Any, int, _BlockOperation, list[etree._Element]]]] = {}
    for operation in block_operations:
        if operation.kind == "insert":
            anchor = left_by_id.get(operation.anchor_id)
            if anchor is None:
                raise DocxError("SELECTION_BLOCK_ANCHOR_UNSUPPORTED", operation.diff_id)
            anchor_element = _simple_paragraph(root, anchor)
            parent = anchor_element.getparent()
            if parent is None:
                raise DocxError("SELECTION_BLOCK_ANCHOR_UNSUPPORTED", operation.diff_id)
            index = parent.index(anchor_element) + (1 if operation.anchor_position == "after" else 0)
            entries.setdefault(id(parent), []).append((parent, index, operation, []))
            continue
        left_elements: list[etree._Element] = []
        for block_id in operation.left_ids:
            block = left_by_id.get(block_id)
            if block is None:
                raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", operation.diff_id)
            left_elements.append(_simple_paragraph(root, block))
        if not left_elements:
            raise DocxError("SELECTION_BLOCK_RANGE_UNSUPPORTED", operation.diff_id)
        parent = left_elements[0].getparent()
        if parent is None or any(element.getparent() is not parent for element in left_elements):
            raise DocxError("SELECTION_BLOCK_SCOPE_UNSUPPORTED", operation.diff_id)
        index = parent.index(left_elements[0])
        if [parent.index(element) for element in left_elements] != list(range(index, index + len(left_elements))):
            raise DocxError("SELECTION_BLOCK_RANGE_UNSUPPORTED", operation.diff_id)
        if (parent.tag == Q("tc") and len(parent.findall(Q("p"))) <= len(left_elements)
                and operation.kind == "delete"):
            raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", operation.diff_id)
        entries.setdefault(id(parent), []).append((parent, index, operation, left_elements))
    next_id = revision_start
    for group in entries.values():
        group.sort(key=lambda item: (item[1], 1 if item[2].kind == "insert" else 0, item[2].diff_id), reverse=True)
        for parent, index, operation, left_elements in group:
            right_elements = [
                _clone_paragraph(_simple_paragraph(right_root, right_by_id[block_id]), right_by_id[block_id])
                for block_id in operation.right_ids
            ] if operation.right_ids else []
            if operation.kind == "insert":
                insert_at = index
                for offset, (element, block_id) in enumerate(zip(right_elements, operation.right_ids)):
                    if redline:
                        next_id = _mark_inserted_paragraph(element, right_by_id[block_id], next_id, when)
                    parent.insert(insert_at + offset, element)
                continue
            if operation.kind == "delete":
                if redline:
                    for element, block_id in zip(left_elements, operation.left_ids):
                        next_id = _mark_deleted_paragraph(element, left_by_id[block_id], next_id, when)
                else:
                    for element in left_elements:
                        parent.remove(element)
                continue
            if operation.kind == "replace":
                if redline:
                    for element, block_id in zip(left_elements, operation.left_ids):
                        next_id = _mark_deleted_paragraph(element, left_by_id[block_id], next_id, when)
                    insert_at = index + len(left_elements)
                    for offset, (element, block_id) in enumerate(zip(right_elements, operation.right_ids)):
                        next_id = _mark_inserted_paragraph(element, right_by_id[block_id], next_id, when)
                        parent.insert(insert_at + offset, element)
                else:
                    for element in left_elements:
                        parent.remove(element)
                    for offset, element in enumerate(right_elements):
                        parent.insert(index + offset, element)
                continue
            raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", operation.diff_id)
    return next_id


def _expected_sequence(left_doc, right_doc, inline: Sequence[_Operation],
                       block_operations: Sequence[_BlockOperation]) -> list[tuple[str, str]]:
    """Build the expected block text sequence after applying all operations."""
    items = [{"id": block.block_id, "container": block.container, "text": block.raw_text}
             for block in left_doc.blocks]
    by_location = {block.location: block.block_id for block in left_doc.blocks}
    by_id = {item["id"]: item for item in items}
    for operation in inline:
        item = by_id.get(by_location.get(operation.location, ""))
        if item is None:
            raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", operation.diff_id)
        item["text"] = item["text"][:operation.start] + operation.new_text + item["text"][operation.end:]
    right_by_id = {block.block_id: block for block in right_doc.blocks}
    index_by_id = {item["id"]: index for index, item in enumerate(items)}
    def _operation_index(operation: _BlockOperation) -> int:
        if operation.kind == "insert":
            return index_by_id.get(operation.anchor_id, 10**9)
        return index_by_id.get(operation.left_ids[0], 10**9) if operation.left_ids else 10**9

    ordered = sorted(block_operations, key=lambda operation: (
        _operation_index(operation), 1 if operation.kind == "insert" else 0, operation.diff_id), reverse=True)
    for operation in ordered:
        right_items = [{"id": block_id, "container": right_by_id[block_id].container,
                        "text": right_by_id[block_id].raw_text} for block_id in operation.right_ids]
        if operation.kind == "insert":
            position = index_by_id.get(operation.anchor_id)
            if position is None:
                raise DocxError("SELECTION_BLOCK_ANCHOR_UNSUPPORTED", operation.diff_id)
            position += 1 if operation.anchor_position == "after" else 0
            items[position:position] = right_items
        else:
            first = index_by_id.get(operation.left_ids[0])
            if first is None or any(index_by_id.get(block_id) != first + offset
                                    for offset, block_id in enumerate(operation.left_ids)):
                raise DocxError("SELECTION_BLOCK_RANGE_UNSUPPORTED", operation.diff_id)
            end = first + len(operation.left_ids)
            if operation.kind == "delete":
                del items[first:end]
            else:
                items[first:end] = right_items
        index_by_id = {item["id"]: index for index, item in enumerate(items)}
    return [(item["container"], item["text"]) for item in items]


def _accept_revisions_copy(root: etree._Element) -> etree._Element:
    """Accept all inserted/deleted revisions, including paragraph marks."""
    clone = deepcopy(root)
    benign = {Q("pPr"), Q("bookmarkStart"), Q("bookmarkEnd"), Q("proofErr"),
              Q("lastRenderedPageBreak")}
    for paragraph in list(clone.iter(Q("p"))):
        ppr = paragraph.find(Q("pPr"))
        rpr = ppr.find(Q("rPr")) if ppr is not None else None
        mark_deleted = rpr is not None and rpr.find(Q("del")) is not None
        # Remove deleted content and unwrap inserted content.  The pPr/rPr
        # markers are not content and are removed separately.
        for node in list(paragraph.iter(Q("del"))):
            parent = node.getparent()
            if parent is not None and parent is not rpr:
                parent.remove(node)
        for node in list(paragraph.iter(Q("ins"))):
            parent = node.getparent()
            if parent is None or parent is rpr:
                continue
            index = parent.index(node)
            for child in list(node):
                node.remove(child)
                parent.insert(index, child)
                index += 1
            parent.remove(node)
        if rpr is not None:
            for tag in (Q("ins"), Q("del")):
                for marker in list(rpr.findall(tag)):
                    rpr.remove(marker)
            if len(rpr) == 0:
                ppr.remove(rpr)
        if ppr is not None and len(ppr) == 0:
            paragraph.remove(ppr)
        if mark_deleted:
            if any(child.tag not in benign for child in list(paragraph)):
                raise DocxError("SELECTION_REDLINE_INVALID")
            parent = paragraph.getparent()
            if parent is not None:
                parent.remove(paragraph)
    return clone


def _validate_outputs(source_parts: Mapping[str, bytes], final_path: Path, redline_path: Path,
                      left_doc, expected: Sequence[tuple[str, str]], *, limits: ZipLimits) -> tuple[str, str]:
    final_parts = _read_parts(final_path, limits)
    redline_parts = _read_parts(redline_path, limits)
    _validate_package(final_parts, limits, full=True)
    # The redline intentionally contains the newly created w:ins/w:del
    # wrappers.  Package checks still cover ZIP/XML/relationship integrity;
    # existing-revision rejection is only applicable to source and final.
    _validate_package(redline_parts, limits, full=False)
    if set(final_parts) != set(source_parts) or set(redline_parts) != set(source_parts):
        raise DocxError("PACKAGE_MEMBER_DRIFT")
    if any(final_parts[name] != value or redline_parts[name] != value
           for name, value in source_parts.items() if name != DOCUMENT):
        raise DocxError("NON_DOCUMENT_PART_CHANGED")
    final_doc = parse_compare_document(final_path, filename=left_doc.filename, side="L")
    actual = [(block.container, block.raw_text) for block in final_doc.blocks]
    if actual != list(expected):
        raise DocxError("SELECTION_FINAL_TEXT_MISMATCH")
    redline_root = _xml(redline_parts[DOCUMENT], limits)
    final_root = _xml(final_parts[DOCUMENT], limits)
    accepted = _accept_revisions_copy(redline_root)
    if etree.tostring(accepted, method="c14n") != etree.tostring(final_root, method="c14n"):
        raise DocxError("SELECTION_REDLINE_FINAL_MISMATCH")
    # An all-left selection is a valid zero-operation artifact and is
    # intentionally revision-free.
    return _digest_bytes(final_path.read_bytes()), _digest_bytes(redline_path.read_bytes())


def _validate_block_references(left_parts: Mapping[str, bytes], right_parts: Mapping[str, bytes],
                               right_root: etree._Element, right_doc,
                               block_operations: Sequence[_BlockOperation]) -> None:
    """Ensure cloned paragraphs do not reference styles missing on the left."""
    def ids(parts: Mapping[str, bytes], name: str, tag: str, attribute: str) -> set[str]:
        data = parts.get(name)
        if not data:
            return set()
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
        return {str(node.get(Q(attribute))) for node in root.iter(Q(tag)) if node.get(Q(attribute))}

    styles = ids(left_parts, "word/styles.xml", "style", "styleId")
    numbers = ids(left_parts, "word/numbering.xml", "num", "numId")
    for operation in block_operations:
        for block_id in operation.right_ids:
            block = next((item for item in right_doc.blocks if item.block_id == block_id), None)
            if block is None:
                raise DocxError("SELECTION_BLOCK_STRUCTURE_UNSUPPORTED", block_id)
            element = _paragraph_element(right_root, block.location)
            ppr = element.find(Q("pPr"))
            if ppr is not None:
                style = ppr.find(Q("pStyle"))
                if style is not None and style.get(Q("val")) not in styles:
                    raise DocxError("SELECTION_BLOCK_STYLE_UNSUPPORTED", block_id)
                numpr = ppr.find(Q("numPr"))
                numid = numpr.find(Q("numId")) if numpr is not None else None
                if numid is not None and numid.get(Q("val")) not in {None, "0"} and numid.get(Q("val")) not in numbers:
                    raise DocxError("SELECTION_BLOCK_STYLE_UNSUPPORTED", block_id)
            for run in element.findall(Q("r")):
                rpr = run.find(Q("rPr"))
                style = rpr.find(Q("rStyle")) if rpr is not None else None
                if style is not None and style.get(Q("val")) not in styles:
                    raise DocxError("SELECTION_BLOCK_STYLE_UNSUPPORTED", block_id)


def generate_selection_artifacts(
    left_source: str | Path,
    right_source: str | Path,
    result: Mapping[str, Any],
    decisions: Mapping[str, str],
    final_path: str | Path,
    redline_path: str | Path,
    *,
    selection_epoch: int,
    result_sha256: str,
    limits: ZipLimits | None = None,
) -> SelectionArtifactValidation:
    """Generate and independently re-read a selected final and redline DOCX."""
    limits = limits or ZipLimits()
    left_source, right_source = Path(left_source), Path(right_source)
    final_path, redline_path = Path(final_path), Path(redline_path)
    outputs = {final_path.resolve(), redline_path.resolve()}
    if (len(outputs) != 2 or {left_source.resolve(), right_source.resolve()} & outputs
            or final_path.exists() or redline_path.exists()):
        raise DocxError("OUTPUT_PATH_INVALID")
    if not isinstance(result, Mapping) or not result_sha256:
        raise DocxError("SELECTION_RESULT_INVALID")
    if _digest_json(result) != result_sha256:
        raise DocxError("SELECTION_RESULT_HASH_MISMATCH")
    left_bytes, right_bytes = left_source.read_bytes(), right_source.read_bytes()
    left_hash, right_hash = _digest_bytes(left_bytes), _digest_bytes(right_bytes)
    result_left = result.get("left") or {}
    result_right = result.get("right") or {}
    if result_left.get("sha256") != left_hash or result_right.get("sha256") != right_hash:
        raise DocxError("SELECTION_SOURCE_HASH_MISMATCH")
    left_doc = parse_compare_document(left_bytes, filename=str(result_left.get("filename", left_source.name)), side="L")
    right_doc = parse_compare_document(right_bytes, filename=str(result_right.get("filename", right_source.name)), side="R")
    recomputed = compare_documents(left_doc, right_doc)
    if result.get("diffs") != recomputed.to_dict()["diffs"]:
        raise DocxError("SELECTION_RESULT_DIFF_MISMATCH")
    # Coverage warnings are retained as artifact limitations instead of
    # blocking the whole selection.  The writer validates every selected
    # operation against a real body paragraph/table paragraph and rejects
    # drawings, fields, content controls, merged cells and other structures
    # it cannot safely rewrite.  Warnings for headers/footers, comments or
    # unsupported content outside the selected paragraphs therefore do not
    # make an otherwise safe body edit unusable.  The report must still show
    # the limitations and must not present the result as complete coverage.
    try:
        snapshot = make_snapshot(result, decisions, selection_epoch=selection_epoch, result_sha256=result_sha256)
    except SelectionError as exc:
        raise DocxError(exc.code) from exc
    diffs = result.get("diffs")
    if not isinstance(diffs, list):
        raise DocxError("SELECTION_RESULT_INVALID")
    inline_operations, block_operations = _build_plan(
        left_doc, right_doc, diffs, dict(snapshot.decisions), recomputed.alignment)
    expected = _expected_sequence(left_doc, right_doc, inline_operations, block_operations)
    source_parts = _read_parts(left_source, limits)
    right_parts = _read_parts(right_source, limits)
    _validate_package(source_parts, limits, full=True)
    original = _xml(source_parts[DOCUMENT], limits)
    right_root = _xml(right_parts[DOCUMENT], limits)
    if block_operations:
        _validate_block_references(source_parts, right_parts, right_root, right_doc, block_operations)
    final_root, redline_root = deepcopy(original), deepcopy(original)
    when = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    try:
        _apply_operations(final_root, inline_operations, redline=False, revision_start=1, when=when)
        next_revision = _apply_operations(redline_root, inline_operations, redline=True, revision_start=1, when=when)
        if block_operations:
            _apply_block_operations(final_root, left_doc, right_doc, block_operations, right_root,
                                    redline=False, revision_start=1, when=when)
            _apply_block_operations(redline_root, left_doc, right_doc, block_operations, right_root,
                                    redline=True, revision_start=next_revision, when=when)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        redline_path.parent.mkdir(parents=True, exist_ok=True)
        _write_package(final_path, source_parts, etree.tostring(final_root, encoding="UTF-8", xml_declaration=True))
        _write_package(redline_path, source_parts, etree.tostring(redline_root, encoding="UTF-8", xml_declaration=True))
        final_hash, redline_hash = _validate_outputs(source_parts, final_path, redline_path,
                                                     left_doc, expected, limits=limits)
        limitations = tuple(dict.fromkeys(
            list(left_doc.coverage.warnings) + list(right_doc.coverage.warnings)))
        manifest_items = [{
            "diff_id": item.diff_id,
            "decision": item.decision,
            "location": item.location,
            "start": item.start,
            "end": item.end,
            "left_text": item.old_text,
            "right_text": item.new_text,
            "selected_text": item.new_text,
        } for item in inline_operations]
        manifest_items.extend({
            "diff_id": item.diff_id,
            "decision": item.decision,
            "location": (f"{item.left_ids[0]}..{item.left_ids[-1]}" if item.left_ids
                         else item.anchor_id),
            "start": 0,
            "end": len(item.left_text),
            "left_text": item.left_text,
            "right_text": item.right_text,
            "selected_text": item.right_text,
        } for item in block_operations)
        manifest = tuple(sorted(manifest_items, key=lambda item: item["diff_id"]))
        checks = ["package", "source_binding", "result_binding", "selection_binding"]
        if block_operations:
            checks.append("block_structure")
        checks.extend(["final_docx_reopen", "redline_reopen", "selected_text"])
        return SelectionArtifactValidation(final_hash, redline_hash, snapshot.selection_epoch,
                                           snapshot.decision_hash, snapshot.binding_hash, manifest,
                                           tuple(checks), limitations)
    except Exception:
        final_path.unlink(missing_ok=True)
        redline_path.unlink(missing_ok=True)
        raise


__all__ = ["SelectionArtifactValidation", "generate_selection_artifacts"]
