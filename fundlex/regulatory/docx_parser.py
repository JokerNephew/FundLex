"""Native OOXML parser for a regulation DOCX.

The parser reads the main document part only.  It preserves headings, ordinary
paragraphs and table rows as separate blocks; it never converts through another
document format.  Tables are flattened with an explicit row separator so a
requirement quote can still be traced to the table block and its page/anchor.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree

from ..guide_generation.models import (
    RegulationBlock,
    RegulationDocument,
    SourceAnchor,
    sha256_bytes,
    sha256_text,
)
from .anchors import article_number, heading_level, is_article_heading

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda local: f"{{{W}}}{local}"
PARSER_VERSION = "regulation-docx-1"
MAX_PART_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 80 * 1024 * 1024


class RegulationParseError(ValueError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def _style_level(paragraph: etree._Element) -> int:
    properties = paragraph.find(Q("pPr"))
    if properties is None:
        return 0
    style = properties.find(Q("pStyle"))
    outline = properties.find(Q("outlineLvl"))
    level = 0
    if outline is not None:
        try:
            level = int(outline.get(Q("val")) or 0) + 1
        except (TypeError, ValueError):
            level = 0
    if style is not None:
        name = (style.get(Q("val")) or "").strip().lower()
        if name in {"heading1", "1", "标题1"}:
            level = max(level, 1)
        elif name in {"heading2", "2", "标题2"}:
            level = max(level, 2)
        elif name in {"heading3", "3", "标题3"}:
            level = max(level, 3)
        elif name.startswith("heading"):
            digits = "".join(ch for ch in name if ch.isdigit())
            if digits:
                level = max(level, min(6, int(digits)))
    return level


def _paragraph_text(paragraph: etree._Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag == Q("t") and node.text:
            pieces.append(node.text)
        elif node.tag in {Q("tab"), Q("br"), Q("cr")}:
            pieces.append("\n")
    return "".join(pieces).strip()


def _table_rows(table: etree._Element) -> list[str]:
    rows: list[str] = []
    for row in table.iter(Q("tr")):
        cells: list[str] = []
        for cell in row.findall(Q("tc")):
            text = "".join((node.text or "") for node in cell.iter(Q("t"))).strip()
            cells.append(" ".join(text.split()))
        if any(cells):
            rows.append(" | ".join(cells))
    return rows


def _body_elements(root: etree._Element):
    body = root.find(Q("body"))
    if body is None:
        return
    for element in body:
        if element.tag in {Q("p"), Q("tbl")}:
            yield element


def _is_toc_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped in {"目录", "目 录", "目    录"}:
        return True
    # Dot leaders or page-number suffixes are navigation entries, not content.
    if "……" in stripped and len(stripped) < 160:
        return True
    if stripped.count(".") >= 4 and len(stripped) < 120:
        return True
    return False


def parse_regulation_docx(path: str | Path, *, source_sha256: str = "") -> RegulationDocument:
    target = Path(path)
    if target.suffix.lower() != ".docx":
        raise RegulationParseError("REGULATION_NOT_DOCX")
    if target.stat().st_size > MAX_FILE_BYTES:
        raise RegulationParseError("REGULATION_FILE_LIMIT")
    try:
        raw = target.read_bytes()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            if "word/document.xml" not in archive.namelist():
                raise RegulationParseError("REGULATION_DOCX_PART_MISSING")
            data = archive.read("word/document.xml")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise RegulationParseError("REGULATION_DOCX_INVALID", {"reason": type(exc).__name__}) from exc
    if len(data) > MAX_PART_BYTES:
        raise RegulationParseError("REGULATION_DOCX_PART_LIMIT")
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise RegulationParseError("REGULATION_DOCX_XML_INVALID") from exc

    digest = source_sha256 or sha256_bytes(raw)
    blocks: list[RegulationBlock] = []
    title = ""
    in_toc = False
    toc_seen = False
    for ordinal, element in enumerate(_body_elements(root)):
        if element.tag == Q("tbl"):
            rows = _table_rows(element)
            if not rows:
                continue
            text = "\n".join(rows)
            blocks.append(RegulationBlock(
                block_id=f"B{len(blocks) + 1:04d}", ordinal=len(blocks), type="table", text=text,
                article_no=article_number(text),
                source_anchor=SourceAnchor(block_index=ordinal, xml_path=f"body/tbl[{ordinal}]").to_dict(),
            ))
            continue
        text = _paragraph_text(element)
        if not text:
            continue
        if _is_toc_text(text):
            in_toc = True
            toc_seen = True
            continue
        level = heading_level(text, _style_level(element))
        # After the table of contents, a real part/heading ends TOC mode.
        if in_toc and level and not _is_toc_text(text):
            in_toc = False
        if in_toc and not level:
            # Navigation entries are normally short; keep long prose just in case.
            if len(text) < 120:
                continue
        if not title and len(text) < 180 and ("规定" in text or "办法" in text or "通知" in text or "指引" in text):
            title = text
        block_type = "heading" if level else "paragraph"
        blocks.append(RegulationBlock(
            block_id=f"B{len(blocks) + 1:04d}", ordinal=len(blocks), type=block_type, text=text,
            article_no=article_number(text), heading_level=level,
            source_anchor=SourceAnchor(block_index=ordinal, xml_path=f"body/p[{ordinal}]").to_dict(),
        ))
    if not blocks:
        raise RegulationParseError("REGULATION_DOCX_EMPTY")
    if not title:
        for block in blocks:
            if block.text and len(block.text) < 120:
                title = block.text
                break
    return RegulationDocument(
        document_id=f"REG-{digest[:16]}", source_type="docx", source_sha256=digest,
        title=title or target.stem, filename=target.name, blocks=blocks,
        parser_version=PARSER_VERSION,
    )


def docx_block_text_sha(blocks: list[RegulationBlock]) -> str:
    return sha256_text("\n".join(f"{block.block_id}\t{block.text}" for block in blocks))
