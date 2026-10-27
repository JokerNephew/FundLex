"""Structured PDF parser using the document's native text layer (PyMuPDF).

No OCR, no PDF-to-Word conversion and no image interpretation.  A PDF without a
usable text layer is rejected.  The parser reconstructs paragraphs from line
geometry and font information and preserves page/line anchors for every block.
"""
from __future__ import annotations

import re
from pathlib import Path

from ..guide_generation.models import (
    RegulationBlock,
    RegulationDocument,
    SourceAnchor,
    sha256_bytes,
)
from .anchors import article_number, clean_line, heading_level, is_article_heading

PARSER_VERSION = "regulation-pdf-1"
MIN_TEXT_CHARS = 200
MAX_PAGES = 400

try:  # PyMuPDF is an optional runtime dependency for DOCX-only deployments.
    import pymupdf  # type: ignore
except ImportError:  # pragma: no cover - exercised only without the dependency
    pymupdf = None


class RegulationParseError(ValueError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def _is_page_number(text: str) -> bool:
    return bool(re.fullmatch(r"[-—–\s]*\d{1,4}[-—–\s]*", text or ""))


def _heading_font(font: str, size: float, body_size: float, text: str) -> bool:
    if size >= body_size + 1.2:
        return True
    upper = (font or "").upper()
    if any(marker in upper for marker in ("HEITI", "HEI", "FZHT", "BOLD", "SIMHEI")):
        return True
    if is_article_heading(text):
        return True
    return bool(re.match(r"第[一二三四五六七八九十百零〇\d]+[章节]", text or ""))


def _line_text(line: dict) -> str:
    return clean_line("".join(span.get("text", "") for span in line.get("spans") or []))


def _line_font(line: dict) -> tuple[str, float]:
    spans = line.get("spans") or []
    if not spans:
        return "", 0.0
    # The dominant span determines the line's role.
    span = max(spans, key=lambda item: len(item.get("text", "")))
    return str(span.get("font") or ""), float(span.get("size") or 0.0)


def parse_regulation_pdf(path: str | Path, *, source_sha256: str = "") -> RegulationDocument:
    if pymupdf is None:
        raise RegulationParseError("PDF_PARSER_DEPENDENCY_MISSING", {"dependency": "pymupdf"})
    target = Path(path)
    if target.suffix.lower() != ".pdf":
        raise RegulationParseError("REGULATION_NOT_PDF")
    try:
        raw = target.read_bytes()
        document = pymupdf.open(stream=raw, filetype="pdf")
    except Exception as exc:
        raise RegulationParseError("REGULATION_PDF_INVALID", {"reason": type(exc).__name__}) from exc
    if document.page_count <= 0 or document.page_count > MAX_PAGES:
        raise RegulationParseError("REGULATION_PDF_PAGE_LIMIT", {"pages": document.page_count})

    # Determine body font size from the most common span size in the first pages.
    sizes: dict[float, int] = {}
    for page in document:
        for block in page.get_text("dict", sort=True).get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if text.strip():
                        size = round(float(span.get("size") or 0), 1)
                        sizes[size] = sizes.get(size, 0) + len(text)
    body_size = max(sizes, key=sizes.get) if sizes else 12.0

    lines: list[dict] = []
    total_text = 0
    for page_number, page in enumerate(document, start=1):
        page_width = float(page.rect.width)
        blocks = page.get_text("dict", sort=True).get("blocks", [])
        page_lines: list[dict] = []
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = _line_text(line)
                if not text or _is_page_number(text):
                    continue
                bbox = line.get("bbox") or block.get("bbox") or (0, 0, 0, 0)
                # Ignore running headers/footers: very small text near page edges.
                size = float((line.get("spans") or [{}])[0].get("size") or 0)
                y0, y1 = float(bbox[1]), float(bbox[3])
                if size and size < body_size - 1.5 and (y0 < 40 or y1 > page.rect.height - 35):
                    continue
                font, font_size = _line_font(line)
                page_lines.append({
                    "text": text, "bbox": tuple(float(value) for value in bbox),
                    "font": font, "size": font_size or size, "page": page_number,
                    "x0": float(bbox[0]), "x1": float(bbox[2]),
                    "y0": y0, "y1": y1, "page_width": page_width,
                })
                total_text += len(text)
        lines.extend(page_lines)

    if total_text < MIN_TEXT_CHARS:
        raise RegulationParseError("REGULATION_PDF_NO_TEXT_LAYER", {"text_chars": total_text})

    # Group lines into blocks.  A new body paragraph starts on an indented first
    # line after a terminator, a heading, or a large vertical gap.  Continuation
    # lines from the next page are appended when the previous paragraph is open.
    paragraphs: list[dict] = []
    current: dict | None = None
    last_line: dict | None = None

    def flush() -> None:
        nonlocal current
        if current and current["lines"]:
            text = ""
            for item in current["lines"]:
                piece = item["text"]
                if not text:
                    text = piece
                elif re.search(r"[A-Za-z0-9]$", text) and re.match(r"[A-Za-z0-9]", piece):
                    text += " " + piece
                else:
                    text += piece
            current["text"] = text.strip()
            if current["text"]:
                paragraphs.append(current)
        current = None

    for line in lines:
        text = line["text"]
        is_heading = _heading_font(line["font"], line["size"], body_size, text)
        new_heading = bool(
            is_article_heading(text)
            or re.match(r"第[一二三四五六七八九十百零〇\d]+[章节]", text)
            or (is_heading and len(text) <= 45)
        )
        if new_heading:
            flush()
            paragraphs.append({"lines": [line], "heading": True, "page": line["page"],
                               "bbox": line["bbox"], "text": text})
            last_line = line
            continue
        # Merge a multi-line short heading such as 第一章 / 总 / 则.
        if paragraphs and paragraphs[-1].get("heading") and paragraphs[-1]["page"] == line["page"]:
            prior = paragraphs[-1]
            prior_text = prior["text"]
            if (len(prior_text) <= 12 and len(text) <= 8
                    and not re.search(r"[。！？；]$", text)
                    and line["x0"] >= prior["lines"][-1]["x0"] - 5):
                prior["lines"].append(line)
                prior["text"] = prior_text + text
                last_line = line
                continue
        starts_indented = bool(
            last_line and line["x0"] > last_line["x0"] + 12
            and re.search(r"[。！？；]$", last_line["text"] or "")
        )
        gap = bool(last_line and line["page"] == last_line["page"] and line["y0"] - last_line["y1"] > 14)
        same_page = bool(last_line and line["page"] == last_line["page"])
        if current is None or starts_indented or gap or (not same_page and last_line
                                                         and re.search(r"[。！？；]$", last_line["text"] or "")):
            flush()
            current = {"lines": [line], "heading": False, "page": line["page"],
                       "bbox": line["bbox"]}
        else:
            current["lines"].append(line)
        last_line = line
    flush()

    blocks: list[RegulationBlock] = []
    title = ""
    skip_toc = False
    for item in paragraphs:
        text = item["text"].strip()
        if not text:
            continue
        if text in {"目录", "目 录", "目    录"}:
            skip_toc = True
            continue
        level = 1 if item.get("heading") else heading_level(text)
        if skip_toc:
            if level and not re.search(r"…|\.{4,}", text):
                skip_toc = False
            else:
                continue
        if not title and len(text) <= 100 and item["page"] == 1:
            title = text
        blocks.append(RegulationBlock(
            block_id=f"B{len(blocks) + 1:04d}", ordinal=len(blocks),
            type="heading" if level else "paragraph", text=text,
            article_no=article_number(text), heading_level=level, page=item["page"],
            source_anchor=SourceAnchor(
                part="pdf", block_index=len(blocks), page=item["page"],
                xml_path=f"page[{item['page']}]/line[{item['lines'][0].get('y0', 0):.0f}]",
                extra={"bbox": list(item["bbox"])},
            ).to_dict(),
        ))
    if not blocks:
        raise RegulationParseError("REGULATION_PDF_EMPTY")
    digest = source_sha256 or sha256_bytes(raw)
    return RegulationDocument(
        document_id=f"REG-{digest[:16]}", source_type="pdf", source_sha256=digest,
        title=title or target.stem, filename=target.name, blocks=blocks,
        page_count=document.page_count, parser_version=PARSER_VERSION,
    )
