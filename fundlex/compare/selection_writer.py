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


def _build_operations(left_doc, right_doc, diffs: Sequence[Mapping[str, Any]], decisions: Mapping[str, str],
                      alignment) -> tuple[_Operation, ...]:
    operations: list[_Operation] = []
    groups = {group.group_id: group for group in alignment}
    for diff in diffs:
        diff_id = str(diff.get("id", ""))
        choice = decisions[diff_id]
        kind = str(diff.get("type", ""))
        if kind in {"insert", "delete"}:
            raise DocxError("SELECTION_STRUCTURAL_DIFF_UNSUPPORTED")
        group = groups.get(diff.get("group_id"))
        left_span = _span(diff, "left", required=kind != "insert")
        right_span = _span(diff, "right", required=kind != "delete")
        if kind == "modify":
            if not _modify_group_compatible(group, left_span, right_span):
                raise DocxError("SELECTION_STRUCTURAL_DIFF_UNSUPPORTED")
            left_block, left_text = _span_text(left_doc, left_span)
            _, right_text = _span_text(right_doc, right_span)
            if choice == "right":
                operations.append(_Operation(diff_id, choice, left_block.location,
                                              int(left_span["start"]), int(left_span["end"]),
                                              left_text, right_text))
        elif kind == "insert":
            # The left side has no visible text. Its empty anchor is the only
            # accepted insertion address and must already be bound to a real
            # left paragraph by the compare result.
            anchor = _anchor(diff, "left")
            left_block = _validate_span(left_doc, anchor, anchor=True)
            _, right_text = _span_text(right_doc, right_span)
            if choice == "right":
                operations.append(_Operation(diff_id, choice, left_block.location,
                                              int(anchor["start"]), int(anchor["end"]),
                                              "", right_text))
        elif kind == "delete":
            left_block, left_text = _span_text(left_doc, left_span)
            if choice == "right":
                operations.append(_Operation(diff_id, choice, left_block.location,
                                              int(left_span["start"]), int(left_span["end"]),
                                              left_text, ""))
        else:
            raise DocxError("SELECTION_RESULT_INVALID")
    by_location: dict[str, list[_Operation]] = {}
    for operation in operations:
        by_location.setdefault(operation.location, []).append(operation)
    for location, values in by_location.items():
        ordered = sorted(values, key=lambda item: (item.start, item.end, item.diff_id))
        previous: _Operation | None = None
        for current in ordered:
            if previous is not None:
                overlaps = (current.start < previous.end and previous.start < current.end)
                same_insertion = current.start == current.end == previous.start == previous.end
                touches_operation = (
                    current.start == current.end and previous.start <= current.start <= previous.end
                ) or (
                    previous.start == previous.end and current.start <= previous.start <= current.end
                )
                if overlaps or same_insertion or touches_operation:
                    raise DocxError("SELECTION_OPERATION_OVERLAP", location)
            previous = current
    return tuple(operations)


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


def _apply_operations(root: etree._Element, operations: Sequence[_Operation], *, redline: bool) -> None:
    locations = sorted({operation.location for operation in operations})
    next_id = 1
    when = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    for location in locations:
        paragraph = _paragraph_element(root, location)
        next_id = _rewrite_paragraph(paragraph, [item for item in operations if item.location == location],
                                     redline=redline, revision_start=next_id, when=when)


def _expected_texts(left_doc, operations: Sequence[_Operation]) -> dict[str, str]:
    expected = {block.location: block.raw_text for block in left_doc.blocks}
    for location in {item.location for item in operations}:
        value = expected[location]
        for operation in sorted((item for item in operations if item.location == location),
                                key=lambda item: (item.start, item.end), reverse=True):
            value = value[:operation.start] + operation.new_text + value[operation.end:]
        expected[location] = value
    return expected


def _validate_outputs(source_parts: Mapping[str, bytes], final_path: Path, redline_path: Path,
                      left_doc, expected: Mapping[str, str], *, limits: ZipLimits) -> tuple[str, str]:
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
    actual = {block.location: block.raw_text for block in final_doc.blocks}
    if actual != dict(expected):
        raise DocxError("SELECTION_FINAL_TEXT_MISMATCH")
    redline_root = _xml(redline_parts[DOCUMENT], limits)
    final_root = _xml(final_parts[DOCUMENT], limits)
    accepted = deepcopy(redline_root)
    for node in list(accepted.iter()):
        if node.tag not in {Q("ins"), Q("del")}:
            continue
        parent = node.getparent()
        if parent is None:
            raise DocxError("SELECTION_REDLINE_INVALID")
        index = parent.index(node)
        if node.tag == Q("del"):
            parent.remove(node)
        else:
            children = list(node)
            parent.remove(node)
            for offset, child in enumerate(children):
                parent.insert(index + offset, child)
    if etree.tostring(accepted, method="c14n") != etree.tostring(final_root, method="c14n"):
        raise DocxError("SELECTION_REDLINE_FINAL_MISMATCH")
    # An all-left selection is a valid zero-operation artifact and is
    # intentionally revision-free.
    return _digest_bytes(final_path.read_bytes()), _digest_bytes(redline_path.read_bytes())


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
    if left_doc.coverage.status != "complete" or right_doc.coverage.status != "complete":
        raise DocxError("SELECTION_COVERAGE_INCOMPLETE")
    try:
        snapshot = make_snapshot(result, decisions, selection_epoch=selection_epoch, result_sha256=result_sha256)
    except SelectionError as exc:
        raise DocxError(exc.code) from exc
    diffs = result.get("diffs")
    if not isinstance(diffs, list):
        raise DocxError("SELECTION_RESULT_INVALID")
    operations = _build_operations(left_doc, right_doc, diffs, dict(snapshot.decisions), recomputed.alignment)
    expected = _expected_texts(left_doc, operations)
    source_parts = _read_parts(left_source, limits)
    _validate_package(source_parts, limits, full=True)
    original = _xml(source_parts[DOCUMENT], limits)
    final_root, redline_root = deepcopy(original), deepcopy(original)
    try:
        _apply_operations(final_root, operations, redline=False)
        _apply_operations(redline_root, operations, redline=True)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        redline_path.parent.mkdir(parents=True, exist_ok=True)
        _write_package(final_path, source_parts, etree.tostring(final_root, encoding="UTF-8", xml_declaration=True))
        _write_package(redline_path, source_parts, etree.tostring(redline_root, encoding="UTF-8", xml_declaration=True))
        final_hash, redline_hash = _validate_outputs(source_parts, final_path, redline_path,
                                                     left_doc, expected, limits=limits)
        limitations = tuple(dict.fromkeys(
            list(left_doc.coverage.warnings) + list(right_doc.coverage.warnings)))
        manifest = tuple({
            "diff_id": item.diff_id,
            "decision": item.decision,
            "location": item.location,
            "start": item.start,
            "end": item.end,
            "left_text": item.old_text,
            "right_text": item.new_text,
            "selected_text": item.new_text,
        } for item in operations)
        return SelectionArtifactValidation(final_hash, redline_hash, snapshot.selection_epoch,
                                           snapshot.decision_hash, snapshot.binding_hash, manifest,
                                           ("package", "source_binding", "result_binding", "selection_binding",
                                            "final_docx_reopen", "redline_reopen", "selected_text"), limitations)
    except Exception:
        final_path.unlink(missing_ok=True)
        redline_path.unlink(missing_ok=True)
        raise


__all__ = ["SelectionArtifactValidation", "generate_selection_artifacts"]
