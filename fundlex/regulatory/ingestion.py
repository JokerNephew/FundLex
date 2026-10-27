"""Regulation ingestion: DOCX/PDF validation and parser dispatch."""
from __future__ import annotations

import re
from pathlib import Path

from ..guide_generation.models import RegulationDocument, sha256_bytes
from .docx_parser import RegulationParseError as DocxParseError
from .docx_parser import parse_regulation_docx
from .pdf_parser import RegulationParseError as PdfParseError
from .pdf_parser import parse_regulation_pdf

SUPPORTED_EXTENSIONS = {".docx", ".pdf"}
MAX_REGULATION_BYTES = 80 * 1024 * 1024


class RegulationIngestError(ValueError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def _guess_type(filename: str, data: bytes) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix in SUPPORTED_EXTENSIONS:
        return suffix[1:]
    if data.startswith(b"PK\x03\x04"):
        return "docx"
    if data.startswith(b"%PDF"):
        return "pdf"
    raise RegulationIngestError("REGULATION_TYPE_UNSUPPORTED", {"filename": filename})


def ingest_regulation(path: str | Path, *, original_filename: str = "", title_hint: str = "") -> RegulationDocument:
    target = Path(path)
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise RegulationIngestError("REGULATION_FILE_UNREADABLE", {"reason": type(exc).__name__}) from exc
    if len(data) > MAX_REGULATION_BYTES:
        raise RegulationIngestError("REGULATION_FILE_LIMIT", {"size": len(data)})
    source_type = _guess_type(original_filename or target.name, data)
    digest = sha256_bytes(data)
    try:
        if source_type == "docx":
            document = parse_regulation_docx(target, source_sha256=digest)
            # DOCX parsers often produce the complete title in one paragraph.
            if len(document.blocks) >= 2 and document.blocks[0].type == "heading" \
                    and len(document.blocks[0].text) <= 40:
                merged = document.blocks[0].text
                consumed = 1
                while consumed < len(document.blocks) and consumed < 4:
                    block = document.blocks[consumed]
                    if block.type != "heading" or block.article_no or len(block.text) > 30:
                        break
                    merged += block.text
                    consumed += 1
                if consumed > 1 and any(token in merged for token in ("规定", "办法", "通知", "指引", "准则", "规则")):
                    document.title = merged
                    for block in document.blocks[:consumed]:
                        block.text = merged
                        break
                    document.blocks = document.blocks[consumed:]
            return document
        document = parse_regulation_pdf(target, source_sha256=digest)
    except (DocxParseError, PdfParseError) as exc:
        raise RegulationIngestError(exc.code, exc.details) from exc
    # PDF title often spans two heading lines; merge them for display only.
    if len(document.blocks) >= 2:
        first = document.blocks[0]
        second = document.blocks[1]
        if first.type == "heading" and second.type == "heading" and not first.article_no \
                and not second.article_no and len(second.text) <= 30 \
                and any(token in second.text for token in ("规定", "办法", "通知", "指引", "准则", "规则")):
            first.text = first.text + second.text
            document.title = first.text
            document.blocks = document.blocks[1:]
    if title_hint:
        document.title = title_hint
    return document


def validate_regulation_document(document: RegulationDocument) -> None:
    if not document.blocks:
        raise RegulationIngestError("REGULATION_EMPTY")
    text = "\n".join(block.text for block in document.blocks)
    if len(re.sub(r"\s+", "", text)) < 100:
        raise RegulationIngestError("REGULATION_TOO_SHORT")
    if document.source_type == "pdf" and len(re.sub(r"\s+", "", text)) < 300:
        raise RegulationIngestError("REGULATION_PDF_NO_TEXT_LAYER")
