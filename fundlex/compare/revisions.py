"""Accept existing Word revisions on a private Compare input copy.

The user's upload is never modified in place.  The returned bytes are a
separately written DOCX which has passed the same package and OOXML checks as
the original input.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
import zipfile

from lxml import etree

from ..docx import (
    DOCUMENT,
    Q,
    REVISION_TAGS,
    W,
    DocxError,
    ZipLimits,
    _read_parts,
    _validate_package,
    _write_package,
    _xml,
)


_DELETE_WRAPPERS = {"del", "moveFrom"}
_INSERT_WRAPPERS = {"ins", "moveTo"}
_DELETE_CONTENT = {"delText", "delInstrText"}
_RANGE_MARKERS = {
    "moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd",
    "customXmlInsRangeStart", "customXmlInsRangeEnd", "customXmlDelRangeStart",
    "customXmlDelRangeEnd", "customXmlMoveFromRangeStart", "customXmlMoveFromRangeEnd",
    "customXmlMoveToRangeStart", "customXmlMoveToRangeEnd",
}
_PROPERTY_CHANGES = {
    "trPrChange", "tcPrChange", "pPrChange", "rPrChange", "tblPrChange",
    "sectPrChange", "numberingChange", "tblGridChange",
}
_MARKERS = _RANGE_MARKERS | _PROPERTY_CHANGES | {"cellIns", "cellDel"}


@dataclass(frozen=True)
class PreparedInput:
    data: bytes
    original_sha256: str
    original_size: int
    revisions_accepted: int


def _local(node: etree._Element) -> str:
    return etree.QName(node).localname if isinstance(node.tag, str) else ""


def _remove(node: etree._Element) -> None:
    parent = node.getparent()
    if parent is None:
        raise DocxError("REVISION_STRUCTURE_INVALID")
    parent.remove(node)


def _unwrap(node: etree._Element) -> None:
    parent = node.getparent()
    if parent is None:
        raise DocxError("REVISION_STRUCTURE_INVALID")
    index = parent.index(node)
    for child in list(node):
        node.remove(child)
        parent.insert(index, child)
        index += 1
    parent.remove(node)


def _remove_deleted_rows_and_cells(root: etree._Element) -> None:
    for row in list(root.iter(Q("tr"))):
        tr_pr = row.find(Q("trPr"))
        if tr_pr is not None and (tr_pr.find(Q("del")) is not None
                                 or tr_pr.find(Q("moveFrom")) is not None):
            _remove(row)
    for cell in list(root.iter(Q("tc"))):
        tc_pr = cell.find(Q("tcPr"))
        if tc_pr is not None and tc_pr.find(Q("cellDel")) is not None:
            _remove(cell)


def _accept_deleted_paragraph_marks(root: etree._Element) -> None:
    """Join paragraphs whose paragraph mark was deleted.

    Word represents this as ``pPr/rPr/del``.  When there is a following
    paragraph in the same story, accepting the deletion moves the first
    paragraph's content into that paragraph.  A final paragraph has no
    following target, so its marker is simply removed.
    """
    for paragraph in list(root.iter(Q("p"))):
        p_pr = paragraph.find(Q("pPr"))
        r_pr = p_pr.find(Q("rPr")) if p_pr is not None else None
        marker = None
        if r_pr is not None:
            marker = r_pr.find(Q("del"))
            if marker is None:
                marker = r_pr.find(Q("moveFrom"))
        if marker is None:
            continue
        following = paragraph.getnext()
        if following is None:
            _remove(marker)
            continue
        if following.tag == Q("sectPr") and following.getnext() is None:
            _remove(marker)
            continue
        if following.tag != Q("p") or p_pr.find(Q("sectPr")) is not None:
            raise DocxError("REVISION_PARAGRAPH_MERGE_UNSUPPORTED")
        target_index = 1 if len(following) and following[0].tag == Q("pPr") else 0
        for child in list(paragraph):
            if child.tag == Q("pPr"):
                continue
            paragraph.remove(child)
            following.insert(target_index, child)
            target_index += 1
        _remove(paragraph)


def _transform(parent: etree._Element) -> None:
    for node in list(parent):
        if not isinstance(node.tag, str):
            continue
        if not node.tag.startswith("{" + W + "}"):
            _transform(node)
            continue
        local = _local(node)
        if local == "cellMerge":
            if parent.tag != Q("tcPr"):
                raise DocxError("REVISION_STRUCTURE_INVALID")
            value = node.get(Q("vMerge"))
            if value not in {"cont", "rest"}:
                raise DocxError("REVISION_CELL_MERGE_UNSUPPORTED")
            merge = parent.find(Q("vMerge"))
            if merge is None:
                merge = etree.SubElement(parent, Q("vMerge"))
            merge.set(Q("val"), "continue" if value == "cont" else "restart")
            _remove(node)
            continue
        if local in _DELETE_WRAPPERS:
            _remove(node)
            continue
        if local in _INSERT_WRAPPERS:
            if parent.tag in {Q("rPr"), Q("trPr")}:
                # Row/paragraph-mark insertion markers are properties, not
                # containers of visible content.  Accepting them keeps the
                # current paragraph/row and removes only the marker.
                _remove(node)
                continue
            _transform(node)
            _unwrap(node)
            continue
        if local in _DELETE_CONTENT or local in _MARKERS:
            _remove(node)
            continue
        _transform(node)


def _accept_revisions(root: etree._Element) -> int:
    # Count every Word revision marker, including markers nested in a
    # historical property snapshot.  The snapshot is discarded as a whole, but
    # the markers are still part of what was accepted and must make the input
    # normalization observable.
    revision_nodes = [
        node for node in root.iter()
        if isinstance(node.tag, str)
        and node.tag.startswith("{" + W + "}")
        and _local(node) in REVISION_TAGS
    ]
    # Apply row/cell deletion before discarding the marker itself.
    _remove_deleted_rows_and_cells(root)

    # Historical property snapshots and deleted content can themselves contain
    # structural markers. Discard them before interpreting paragraph marks.
    def discard(parent):
        for node in list(parent):
            if node.tag in {Q(tag) for tag in _PROPERTY_CHANGES}:
                _remove(node)
            elif node.tag in {Q("del"), Q("moveFrom")} and parent.tag not in {Q("rPr"), Q("trPr")}:
                _remove(node)
            else:
                discard(node)
    discard(root)
    _accept_deleted_paragraph_marks(root)
    _transform(root)
    return len(revision_nodes)


def _write_normalized_package(path: Path, parts: dict[str, bytes], document_xml: bytes) -> None:
    """Write a stable ZIP representation for retry-safe normalized hashes."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o600 << 16
            output.writestr(info, document_xml if name == DOCUMENT else data)


def prepare_compare_input(data: bytes, *, limits: ZipLimits | None = None) -> PreparedInput:
    """Return a validated DOCX with all existing Word revisions accepted."""
    limits = limits or ZipLimits()
    original_sha256 = sha256(data).hexdigest()
    with TemporaryDirectory(prefix="fundlex-compare-revisions-") as directory:
        source = Path(directory) / "source.docx"
        source.write_bytes(data)
        parts = _read_parts(source, limits)
        _validate_package(parts, limits, full=True, allow_existing_revisions=True)
        changed = dict(parts)
        accepted = 0
        touched = False
        for name, content in parts.items():
            if not name.endswith(".xml"):
                continue
            root = _xml(content, limits)
            has_revisions = any(
                isinstance(node.tag, str)
                and node.tag.startswith("{" + W + "}")
                and _local(node) in REVISION_TAGS
                for node in root.iter()
            )
            if not has_revisions:
                continue
            touched = True
            accepted += _accept_revisions(root)
            changed[name] = etree.tostring(root, encoding="UTF-8", xml_declaration=True)

        if not touched:
            return PreparedInput(data, original_sha256, len(data), 0)

        # Full validation rejects any Word revision tags left behind and also
        # retains the package, relationship, macro, signature and coverage
        # safety checks already used by Compare.
        _validate_package(changed, limits, full=True)
        output = Path(directory) / "accepted.docx"
        _write_normalized_package(output, changed, changed[DOCUMENT])
        reopened = _read_parts(output, limits)
        _validate_package(reopened, limits, full=True)
        if reopened != changed:
            raise DocxError("REVISION_NORMALIZATION_MISMATCH")
        return PreparedInput(output.read_bytes(), original_sha256, len(data), accepted)
