"""Safe OOXML reader for compare documents.

The parser intentionally reads visible text directly from ``word/document.xml``
and emits ordinary paragraphs and table-cell paragraphs. It is read-only and
never applies the revision-pipeline's editable-zone restrictions.
"""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping
import io
import os
import tempfile
import zipfile

from lxml import etree

from ..docx import DOCUMENT, Q, W, REVISION_TAGS, DocxError, ZipLimits, _read_parts, _validate_package, _xml
from .models import CompareBlock, CompareDocument, Coverage
from .normalize import normalize_diff, normalize_match

MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"


def _text(element: etree._Element) -> str:
    # ``w:t`` is visible text; delText is retained defensively for input files
    # containing existing revisions, although compare's normal contract forbids
    # them. fld instructions are deliberately excluded.
    out: list[str] = []
    for node in element.iter():
        if node.tag in {Q("t"), Q("delText")}:
            out.append(node.text or "")
        elif node.tag in {Q("br"), Q("cr")}:
            out.append("\n")
        elif node.tag == Q("tab"):
            out.append("\t")
        elif node.tag in {Q("noBreakHyphen")}:
            out.append("\u2011")
    return "".join(out)


def _style(paragraph: etree._Element) -> str:
    ppr = paragraph.find(Q("pPr"))
    if ppr is None:
        return ""
    style = ppr.find(Q("pStyle"))
    return style.get(Q("val"), "") if style is not None else ""


def _is_heading(style: str, text: str) -> bool:
    low = style.casefold()
    if low.startswith("heading") or low in {"title", "subtitle"}:
        return True
    compact = "".join(text.split())
    return len(compact) <= 80 and (compact.startswith(tuple(f"第{x}" for x in "一二三四五六七八九十")) or compact.startswith(tuple(f"{x}." for x in range(1, 20))))


def _cell_key(table: int | None, row: int | None, cell: int | None) -> tuple[Any, ...]:
    return ("body",) if table is None else ("cell", table, row, cell)


def _block(block_id: str, ordinal: int, location: str, kind: str, raw: str,
           section: str, *, container: str = "body", table: int | None = None,
           row: int | None = None, cell: int | None = None,
           paragraph: int | None = None, style: str = "", warnings: tuple[str, ...] = ()) -> CompareBlock:
    return CompareBlock(block_id=block_id, ordinal=ordinal, location=location, kind=kind,
                        section_path=section, raw_text=raw,
                        match_text=normalize_match(raw), diff_text=normalize_diff(raw),
                        container=container, table_index=table, row_index=row,
                        cell_index=cell, paragraph_index=paragraph, style=style,
                        warnings=warnings)


def _parse_parts(parts: Mapping[str, bytes], *, filename: str = "", side: str = "B",
                 limits: ZipLimits | None = None, source_sha256: str = "") -> CompareDocument:
    limits = limits or ZipLimits()
    _validate_package(parts, limits, full=False)
    root = _xml(parts[DOCUMENT], limits)
    if root.tag != Q("document"):
        raise DocxError("MAIN_DOCUMENT_INVALID")
    # WordprocessingML revision tags are namespace qualified.  DrawingML has
    # unrelated local names such as ``a:moveTo`` and must remain readable.
    if any(node.tag in {Q("ins"), Q("del"), Q("moveFrom"), Q("moveTo")} for node in root.iter()):
        raise DocxError("EXISTING_REVISION_UNSUPPORTED")
    body = root.find(Q("body"))
    if body is None:
        raise DocxError("BODY_MISSING")
    blocks: list[CompareBlock] = []
    warnings: list[str] = []
    current_section = ""
    body_para = 0
    table_index = 0

    # The first compare scope is the main document body.  Story parts are
    # deliberately not compared, but visible text in them must not be
    # mistaken for a complete comparison.  Empty default headers/footers are
    # common and do not create noise; non-empty supported Word story parts do.
    for part_name, data in parts.items():
        if part_name == DOCUMENT or not part_name.endswith(".xml"):
            continue
        story = None
        for marker, label in (("word/header", "header"), ("word/footer", "footer"),
                              ("word/footnotes", "footnote"), ("word/endnotes", "endnote"),
                              ("word/comments", "comment")):
            if marker in part_name:
                story = label
                break
        if story is None:
            continue
        try:
            story_root = _xml(data, limits)
            story_text = _text(story_root)
        except Exception:
            story_text = ""
        if story_text.strip():
            warning = f"UNSUPPORTED_VISIBLE_CONTENT:{story}"
            if warning not in warnings:
                warnings.append(warning)

    def report_unsupported(node: etree._Element) -> None:
        local = etree.QName(node).localname if isinstance(node.tag, str) else "unknown"
        if local in {"drawing", "pict", "object", "AlternateContent", "txbxContent", "sym"}:
            warning = f"UNSUPPORTED_VISIBLE_CONTENT:{local}"
            if warning not in warnings:
                warnings.append(warning)

    def walk_unsupported(node: etree._Element) -> None:
        for child in node.iter():
            report_unsupported(child)

    def append_para(p: etree._Element, location: str, *, kind: str, table: int | None,
                    row: int | None, cell: int | None, paragraph: int | None) -> None:
        nonlocal current_section
        walk_unsupported(p)
        raw = _text(p)
        style = _style(p)
        if _is_heading(style, raw) and normalize_match(raw):
            current_section = normalize_match(raw)
        blocks.append(_block(f"{side}{len(blocks):06d}", len(blocks), location, kind, raw,
                             current_section, container="table" if table is not None else "body",
                             table=table, row=row, cell=cell, paragraph=paragraph, style=style))

    def append_table(tbl: etree._Element, ti: int) -> None:
        nonlocal current_section
        for ri, tr in enumerate(tbl.findall(Q("tr"))):
            for ci, tc in enumerate(tr.findall(Q("tc"))):
                pi = 0
                for node in tc:
                    if node.tag == Q("p"):
                        append_para(node, f"tbl{ti}/r{ri}/c{ci}/p{pi}", kind="table_paragraph",
                                    table=ti, row=ri, cell=ci, paragraph=pi)
                        pi += 1
                    elif node.tag == Q("sdt"):
                        append_sdt(node, table=ti, row=ri, cell=ci, paragraph_start=pi)
                        pi += 1
                    elif node.tag == Q("tbl"):
                        warning = "UNSUPPORTED_NESTED_TABLE"
                        if warning not in warnings:
                            warnings.append(warning)
                    elif _text(node).strip():
                        # A customXml/unknown wrapper can contain ordinary
                        # paragraphs.  Do not silently claim complete
                        # coverage while the direct-cell traversal skips it.
                        local = etree.QName(node).localname if isinstance(node.tag, str) else "unknown"
                        warning = f"UNSUPPORTED_VISIBLE_CONTENT:table-wrapper:{local}"
                        if warning not in warnings:
                            warnings.append(warning)

    def append_sdt(sdt: etree._Element, *, table: int | None = None,
                   row: int | None = None, cell: int | None = None,
                   paragraph_start: int = 0) -> None:
        """Treat content controls as transparent, including nested controls."""
        nonlocal body_para, table_index
        content = sdt.find(Q("sdtContent"))
        if content is None:
            content = sdt
        paragraph_no = paragraph_start
        for node in content:
            if node.tag == Q("p"):
                if table is None:
                    location = f"sdt{len(blocks)}/p{body_para}"
                    paragraph = body_para
                    body_para += 1
                    kind = "paragraph"
                else:
                    location = f"tbl{table}/r{row}/c{cell}/sdt{len(blocks)}/p{paragraph_no}"
                    paragraph = paragraph_no
                    paragraph_no += 1
                    kind = "table_paragraph"
                append_para(node, location, kind=kind, table=table, row=row, cell=cell,
                            paragraph=paragraph)
            elif node.tag == Q("tbl"):
                append_table(node, table_index)
                table_index += 1
            elif node.tag == Q("sdt"):
                append_sdt(node, table=table, row=row, cell=cell, paragraph_start=paragraph_no)
            elif _text(node).strip():
                walk_unsupported(node)
                warning = "UNSUPPORTED_VISIBLE_CONTENT:sdt"
                if warning not in warnings:
                    warnings.append(warning)

    for child in body:
        walk_unsupported(child)
        if child.tag == Q("p"):
            append_para(child, f"p{body_para}", kind="paragraph", table=None, row=None, cell=None, paragraph=body_para)
            body_para += 1
        elif child.tag == Q("tbl"):
            append_table(child, table_index)
            table_index += 1
        elif child.tag == Q("sdt"):
            append_sdt(child)
        elif _text(child).strip():
            warning = "UNSUPPORTED_VISIBLE_CONTENT:body"
            if warning not in warnings:
                warnings.append(warning)
    coverage = Coverage("incomplete" if warnings else "complete", tuple(warnings))
    return CompareDocument(tuple(blocks), source_sha256 or sha256(parts[DOCUMENT]).hexdigest(), filename, coverage)


def parse_compare_document(source: str | Path | bytes | bytearray, *, filename: str = "",
                           side: str = "B", limits: ZipLimits | None = None) -> CompareDocument:
    """Parse a DOCX path or bytes into a :class:`CompareDocument`.

    ``side`` is only used as a deterministic block-id prefix (``L``/``R`` for
    the viewer); changing it does not affect alignment or hashes.
    """
    limits = limits or ZipLimits()
    if isinstance(source, (bytes, bytearray)):
        data = bytes(source)
        if not filename:
            filename = "document.docx"
        if len(data) > limits.max_file_bytes:
            raise DocxError("ZIP_FILE_LIMIT")
        # Route bytes through the same complete package validator as paths.
        # Keeping one ZIP security implementation prevents ratio, traversal,
        # duplicate and content-type checks from diverging.
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as temp:
            temp.write(data)
            temp_path = Path(temp.name)
        try:
            parts = _read_parts(temp_path, limits)
            return _parse_parts(parts, filename=filename, side=side, limits=limits,
                                source_sha256=sha256(data).hexdigest())
        finally:
            temp_path.unlink(missing_ok=True)
    path = Path(source)
    if not filename:
        filename = path.name
    parts = _read_parts(path, limits)
    return _parse_parts(parts, filename=filename, side=side, limits=limits,
                        source_sha256=sha256(path.read_bytes()).hexdigest())


parse_docx = parse_compare_document

# Explicit descriptive alias for callers that do not know the DOCX-specific name.
parse_document = parse_compare_document
