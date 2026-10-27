"""Contract DOCX segmentation into sections and traceable ClauseUnits.

This is deliberately independent of the strict contract-editing parser: the
corpus sweep must accept the whole historical archive, including documents that
the editing engine would reject for an unsupported OOXML feature.  Paragraph
anchors are still native OOXML paragraph indices, not token chunks.
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from lxml import etree

from ..guide_generation.models import ClauseUnit, stable_id

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda local: f"{{{W}}}{local}"
PARSER_VERSION = "contract-segmenter-1"
MAX_FILE_BYTES = 80 * 1024 * 1024
MAX_PART_BYTES = 64 * 1024 * 1024
MAX_CLAUSE_CHARS = 1400
MIN_CLAUSE_CHARS = 12

_PART = re.compile(r"^第[一二三四五六七八九十百零〇\d]+部分")
_CHAPTER = re.compile(r"^第[一二三四五六七八九十百零〇\d]+章")
_CN_ITEM = re.compile(r"^[一二三四五六七八九十百零〇]+、")
_CN_PAREN = re.compile(r"^[（(][一二三四五六七八九十百零〇]+[）)]")
_NUM_ITEM = re.compile(r"^\d+[、．.]\s*")
_NUM_PAREN = re.compile(r"^[（(]\d+[）)]")
_DOTTED = re.compile(r"^\d+(?:\.\d+)+")
_TOC_LINE = re.compile(r"(?:…{2,}|\.{4,}|·{4,})\s*\d*\s*$")
_SENTENCE_END = re.compile(r"[。！？；：]$")
_CONTINUATION_START = re.compile(r"^[，、；。）)\]】》”’]|^[a-z]")


@dataclass
class RawBlock:
    ordinal: int
    text: str
    kind: str  # heading|paragraph|table
    level: int = 0
    section_path_before: list[str] = field(default_factory=list)
    section_path_after: list[str] = field(default_factory=list)
    anchor: dict = field(default_factory=dict)


@dataclass
class SegmentedContract:
    paragraphs: list[RawBlock]
    clauses: list[ClauseUnit]
    title: str
    manager: str
    custodian: str
    fund_identity_hint: str
    parser_version: str = PARSER_VERSION
    stats: dict = field(default_factory=dict)


class ContractParseError(ValueError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def _run_bold(properties: etree._Element | None) -> bool:
    if properties is None:
        return False
    node = properties.find(Q("b"))
    if node is None:
        return False
    value = node.get(Q("val"))
    return value is None or value.strip().lower() not in {"0", "false", "off"}


def _paragraph_bold(paragraph: etree._Element) -> bool:
    runs = paragraph.findall(".//" + Q("r"))
    if not runs:
        return False
    flags = [_run_bold(run.find(Q("rPr"))) for run in runs]
    return sum(flags) * 2 > len(flags)


def _paragraph_text(paragraph: etree._Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag == Q("t") and node.text:
            pieces.append(node.text)
        elif node.tag in {Q("tab"), Q("br"), Q("cr")}:
            pieces.append(" ")
    return "".join(pieces).strip()


def _table_text(table: etree._Element) -> str:
    rows: list[str] = []
    for row in table.iter(Q("tr")):
        cells = []
        for cell in row.findall(Q("tc")):
            text = "".join((node.text or "") for node in cell.iter(Q("t"))).strip()
            cells.append(" ".join(text.split()))
        if any(cells):
            rows.append(" | ".join(cells))
    return "\n".join(rows).strip()


def _style_level(paragraph: etree._Element) -> int:
    properties = paragraph.find(Q("pPr"))
    if properties is None:
        return 0
    outline = properties.find(Q("outlineLvl"))
    if outline is not None:
        try:
            return max(1, min(6, int(outline.get(Q("val")) or 0) + 1))
        except (TypeError, ValueError):
            pass
    style = properties.find(Q("pStyle"))
    if style is not None:
        name = (style.get(Q("val")) or "").strip().lower()
        if name in {"1", "heading1", "标题1"}:
            return 1
        if name in {"2", "heading2", "标题2"}:
            return 2
        if name in {"3", "heading3", "标题3"}:
            return 3
    return 0


def _heading_level(text: str, style_level: int, bold: bool) -> int:
    stripped = text.strip()
    if not stripped:
        return 0
    if _PART.match(stripped) or _CHAPTER.match(stripped):
        return 1
    if _CN_ITEM.match(stripped) and len(stripped) <= 80:
        return 2
    if _CN_PAREN.match(stripped) and len(stripped) <= 80:
        return 3
    if _NUM_ITEM.match(stripped) and len(stripped) <= 80:
        return 3
    if _NUM_PAREN.match(stripped) and len(stripped) <= 80:
        return 4
    if _DOTTED.match(stripped) and len(stripped) <= 80:
        return 3
    if style_level:
        return max(1, min(6, style_level))
    if bold and len(stripped) <= 60 and not _SENTENCE_END.search(stripped) \
            and not re.search(r"[，,]", stripped):
        return 3
    return 0


def _is_toc(text: str) -> bool:
    stripped = text.strip()
    if stripped in {"目录", "目 录", "目    录"}:
        return True
    return len(stripped) < 140 and bool(_TOC_LINE.search(stripped))


def _split_long(text: str) -> list[str]:
    if len(text) <= MAX_CLAUSE_CHARS:
        return [text]
    pieces: list[str] = []
    remaining = text
    while len(remaining) > MAX_CLAUSE_CHARS:
        window = remaining[:MAX_CLAUSE_CHARS]
        cut = max(window.rfind(mark) for mark in ("。", "；", "！", "？", "\n"))
        if cut < MAX_CLAUSE_CHARS // 2:
            cut = MAX_CLAUSE_CHARS
        else:
            cut += 1
        pieces.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return [piece for piece in pieces if piece]


def segment_contract(path: str | Path, *, contract_version_id: str = "",
                     source_sha256: str = "") -> SegmentedContract:
    target = Path(path)
    if target.suffix.lower() != ".docx":
        raise ContractParseError("CONTRACT_NOT_DOCX")
    try:
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ContractParseError("CONTRACT_FILE_LIMIT")
        with zipfile.ZipFile(target) as archive:
            if "word/document.xml" not in archive.namelist():
                raise ContractParseError("CONTRACT_DOCX_PART_MISSING")
            data = archive.read("word/document.xml")
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        raise ContractParseError("CONTRACT_DOCX_INVALID", {"reason": type(exc).__name__}) from exc
    if len(data) > MAX_PART_BYTES:
        raise ContractParseError("CONTRACT_DOCX_PART_LIMIT")
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise ContractParseError("CONTRACT_DOCX_XML_INVALID") from exc
    body = root.find(Q("body"))
    if body is None:
        raise ContractParseError("CONTRACT_DOCX_EMPTY")

    title = ""
    manager = ""
    custodian = ""
    raw: list[RawBlock] = []
    section_stack: list[tuple[int, str]] = []
    in_toc = False
    toc_seen = False
    ordinal = 0
    for element in body:
        if element.tag == Q("tbl"):
            text = _table_text(element)
            if not text:
                continue
            raw.append(RawBlock(ordinal=ordinal, text=text, kind="table",
                                section_path_before=[name for _, name in section_stack],
                                section_path_after=[name for _, name in section_stack],
                                anchor={"part": "word/document.xml", "table_index": ordinal,
                                        "xml_path": f"body/tbl[{ordinal}]"}))
            ordinal += 1
            continue
        if element.tag != Q("p"):
            continue
        text = _paragraph_text(element)
        if not text:
            continue
        if _is_toc(text):
            in_toc = True
            toc_seen = True
            continue
        style_level = _style_level(element)
        bold = _paragraph_bold(element)
        level = _heading_level(text, style_level, bold)
        if in_toc:
            if level == 1 and (_PART.match(text) or _CHAPTER.match(text)):
                in_toc = False
            else:
                continue
        if not title and len(text) <= 200:
            if text.endswith("基金合同") or "基金合同" in text and len(text) <= 80:
                title = text
        if not manager and text.startswith("基金管理人"):
            manager = re.sub(r"^基金管理人[：:]\s*", "", text).strip()
        if not custodian and text.startswith("基金托管人"):
            custodian = re.sub(r"^基金托管人[：:]\s*", "", text).strip()
        before = [name for _, name in section_stack]
        if level:
            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()
            section_stack.append((level, text.strip()))
        after = [name for _, name in section_stack]
        raw.append(RawBlock(
            ordinal=ordinal, text=text, kind="heading" if level else "paragraph",
            level=level, section_path_before=before, section_path_after=after,
            anchor={"part": "word/document.xml", "paragraph_index": ordinal,
                    "xml_path": f"body/p[{ordinal}]"},
        ))
        ordinal += 1

    if not raw:
        raise ContractParseError("CONTRACT_EMPTY")

    # Group ordinary paragraphs into clause units; headings are boundaries and
    # are never emitted as clauses.
    clauses: list[ClauseUnit] = []
    current: dict | None = None
    clause_ordinal = 0

    def flush() -> None:
        nonlocal current, clause_ordinal
        if not current:
            return
        text = current["text"].strip()
        if len(text) >= MIN_CLAUSE_CHARS and not (current["kind"] == "table" and len(text) < 20):
            for piece in _split_long(text):
                clause_id = stable_id(
                    "CL", contract_version_id or source_sha256, current["start"],
                    current["end"], piece[:120], clause_ordinal, length=20)
                clauses.append(ClauseUnit(
                    clause_id=clause_id, contract_version_id=contract_version_id,
                    section_path=current["section"],
                    paragraph_start=current["start"], paragraph_end=current["end"],
                    text=piece,
                    metadata={"kind": current["kind"], "headings": current["headings"]},
                    source_anchor={"part": "word/document.xml",
                                   "paragraph_start": current["start"],
                                   "paragraph_end": current["end"],
                                   "xml_paths": current["xml_paths"]},
                ))
                clause_ordinal += 1
        current = None

    for block in raw:
        if block.kind == "heading":
            flush()
            continue
        if current is None:
            current = {"text": block.text, "start": block.ordinal, "end": block.ordinal,
                       "section": block.section_path_after or block.section_path_before,
                       "kind": block.kind, "headings": block.section_path_after,
                       "xml_paths": [block.anchor.get("xml_path", "")]}
            continue
        same_section = current["section"] == (block.section_path_after or block.section_path_before)
        # Merge a short fragment or an explicit continuation into the current unit.
        should_merge = same_section and (
            not _SENTENCE_END.search(current["text"]) or
            (len(current["text"]) < 80 and not _NUM_ITEM.match(block.text) and not _CN_ITEM.match(block.text)) or
            _CONTINUATION_START.match(block.text)
        ) and len(current["text"]) + len(block.text) <= MAX_CLAUSE_CHARS
        if should_merge:
            current["text"] += "\n" + block.text
            current["end"] = block.ordinal
            current["xml_paths"].append(block.anchor.get("xml_path", ""))
            if block.kind == "table":
                current["kind"] = "table"
        else:
            flush()
            current = {"text": block.text, "start": block.ordinal, "end": block.ordinal,
                       "section": block.section_path_after or block.section_path_before,
                       "kind": block.kind, "headings": block.section_path_after,
                       "xml_paths": [block.anchor.get("xml_path", "")]}
    flush()

    # Add surrounding context once clause order is final.
    for index, clause in enumerate(clauses):
        clause.before_context = clauses[index - 1].text[-500:] if index else ""
        clause.after_context = clauses[index + 1].text[:500] if index + 1 < len(clauses) else ""

    identity_hint = ""
    if title:
        identity_hint = re.sub(r"基金合同.*$", "", title).strip()
    return SegmentedContract(
        paragraphs=raw, clauses=clauses, title=title or target.stem,
        manager=manager, custodian=custodian, fund_identity_hint=identity_hint,
        stats={"paragraphs": len(raw), "clauses": len(clauses),
               "sections": len({tuple(clause.section_path) for clause in clauses})},
    )
