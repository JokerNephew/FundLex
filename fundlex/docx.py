"""Conservative, auditable DOCX inspection and OOXML edit primitives.

The editor deliberately supports a small subset of Transitional WordprocessingML.
Unknown structure is reported as a typed failure before any output is published.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping, Sequence
from urllib.parse import unquote
import io
import os
import posixpath
import re
import unicodedata
import zipfile

from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NS = {"w": W}
Q = lambda local: f"{{{W}}}{local}"
DOCUMENT = "word/document.xml"
MAPPING_VERSION = "docx-projection-1"
BARRIER = "\ufff9"
REVISION_TAGS = {
    "ins", "del", "moveFrom", "moveTo", "moveFromRangeStart", "moveFromRangeEnd",
    "moveToRangeStart", "moveToRangeEnd", "cellIns", "cellDel", "cellMerge",
    "trPrChange", "tcPrChange", "pPrChange", "rPrChange", "tblPrChange",
    "sectPrChange", "numberingChange", "customXmlInsRangeStart", "customXmlDelRangeStart",
    "tblGridChange", "customXmlInsRangeEnd", "customXmlDelRangeEnd",
    "customXmlMoveFromRangeStart", "customXmlMoveFromRangeEnd",
    "customXmlMoveToRangeStart", "customXmlMoveToRangeEnd", "delText", "delInstrText",
}
BOUNDARY_TAGS = {
    "bookmarkStart", "bookmarkEnd", "commentRangeStart", "commentRangeEnd",
    "commentReference", "permStart", "permEnd", "proofErr", "fldChar", "instrText",
    "tab", "br", "cr", "lastRenderedPageBreak", "drawing", "object", "sym",
    "noBreakHyphen", "softHyphen", "footnoteReference", "endnoteReference",
}


class DocxError(ValueError):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        super().__init__(message or code)


@dataclass(frozen=True)
class ZipLimits:
    max_file_bytes: int = 64 * 1024 * 1024
    max_uncompressed_bytes: int = 256 * 1024 * 1024
    max_part_bytes: int = 64 * 1024 * 1024
    max_ratio: float = 200.0
    max_entries: int = 3000
    max_xml_depth: int = 128
    max_xml_nodes: int = 2_000_000


@dataclass(frozen=True)
class TextSegment:
    start: int
    end: int
    node_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParagraphSpan:
    location: str
    zone: str
    section_path: str
    text: str
    segments: tuple[TextSegment, ...]
    fingerprint: str
    part_uri: str = DOCUMENT
    mapping_version: str = MAPPING_VERSION
    reasons: tuple[str, ...] = ()
    logical_zone: str | None = None

    @property
    def editable(self) -> bool:
        return self.zone in {"body", "summary"} and bool(self.segments)

    @property
    def safe_text(self) -> str:
        """Visible text from ordinary runs, keeping structural gaps explicit."""
        return " | ".join(self.text[segment.start:segment.end] for segment in self.segments)


@dataclass(frozen=True)
class DocumentInspection:
    source_sha256: str
    paragraphs: tuple[ParagraphSpan, ...]
    has_toc_field: bool
    full_precheck: bool
    parts: tuple[str, ...]
    mapping_version: str = MAPPING_VERSION

    @property
    def spans(self) -> tuple[ParagraphSpan, ...]:
        return self.paragraphs

    @property
    def evidence_paragraphs(self) -> tuple[ParagraphSpan, ...]:
        return tuple(p for p in self.paragraphs if p.zone in {"body", "summary"} and not p.reasons)

    def by_location(self, location: str) -> ParagraphSpan:
        for paragraph in self.paragraphs:
            if paragraph.location == location:
                return paragraph
        raise DocxError("LOCATION_NOT_FOUND", location)

    def evidence_text(self, max_chars: int = 8000) -> str:
        return "\n".join(p.safe_text for p in self.evidence_paragraphs)[:max_chars]


@dataclass(frozen=True)
class ValidatedPlan:
    source_sha256: str
    edits: tuple[dict[str, Any], ...]
    plan_sha256: str
    has_toc_field: bool
    templates: Mapping[str, str] = field(default_factory=dict)
    # Generated-content edits are re-verified by a trusted server-side closure
    # at every validation boundary; the model cannot self-assert verification.
    content_check: Any = None


@dataclass(frozen=True)
class ArtifactValidation:
    redline_sha256: str
    final_sha256: str
    manifest: tuple[dict[str, Any], ...]
    checks: tuple[str, ...]
    has_toc_field: bool
    toc_update_status: str


def _sha(data: bytes) -> str:
    return sha256(data).hexdigest()


def _xml(data: bytes, limits: ZipLimits) -> etree._Element:
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)", data, re.I):
        raise DocxError("XML_DTD_UNSUPPORTED")
    try:
        root = etree.fromstring(data, parser=etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False))
    except etree.XMLSyntaxError as exc:
        raise DocxError("XML_INVALID", str(exc)) from exc
    count = 0
    stack = [(root, 1)]
    while stack:
        node, depth = stack.pop()
        count += 1
        if depth > limits.max_xml_depth or count > limits.max_xml_nodes:
            raise DocxError("XML_LIMIT")
        stack.extend((child, depth + 1) for child in node)
    return root


def _part_name(name: str) -> str:
    if not name or name.startswith("/") or "\\" in name or "?" in name or "#" in name or ":" in name:
        raise DocxError("OPC_URI_INVALID", name)
    if any(ord(char) < 32 for char in name):
        raise DocxError("OPC_URI_INVALID", name)
    if re.search(r"%(?![0-9A-Fa-f]{2})", name):
        raise DocxError("OPC_URI_INVALID", name)
    decoded = unquote(name)
    if any(ord(char) < 32 for char in decoded) or any(char in decoded for char in {":", "?", "#"}):
        raise DocxError("OPC_URI_INVALID", name)
    if any("/" in unquote(segment) or "\\" in unquote(segment) for segment in name.split("/")):
        raise DocxError("OPC_URI_INVALID", name)
    segments = decoded.split("/")
    if any(s in {"", ".", ".."} for s in segments) or decoded.startswith("/"):
        raise DocxError("OPC_URI_INVALID", name)
    if posixpath.normpath(decoded) != decoded:
        raise DocxError("OPC_URI_INVALID", name)
    return unicodedata.normalize("NFC", decoded).casefold()


def _relationship_source(rels: str) -> str:
    if rels == "_rels/.rels":
        return ""
    directory, name = posixpath.split(rels)
    if not directory.endswith("/_rels") or not name.endswith(".rels"):
        raise DocxError("RELATIONSHIP_PATH_INVALID", rels)
    return posixpath.join(directory[:-6], name[:-5])


def _validate_package(parts: Mapping[str, bytes], limits: ZipLimits, *, full: bool) -> None:
    if "[Content_Types].xml" not in parts or "_rels/.rels" not in parts or DOCUMENT not in parts:
        raise DocxError("DOCX_REQUIRED_PART_MISSING")
    content = _xml(parts["[Content_Types].xml"], limits)
    if content.tag != f"{{{CT}}}Types":
        raise DocxError("CONTENT_TYPES_INVALID")
    overrides = {item.get("PartName"): item.get("ContentType") for item in content if item.tag == f"{{{CT}}}Override"}
    defaults = {item.get("Extension", "").casefold(): item.get("ContentType")
                for item in content if item.tag == f"{{{CT}}}Default"}
    seen_content: set[tuple[str, str]] = set()
    for item in content:
        if item.tag == f"{{{CT}}}Override":
            uri = item.get("PartName", "")
            if not uri.startswith("/"):
                raise DocxError("CONTENT_TYPES_INVALID")
            key = ("override", _part_name(uri[1:]))
        elif item.tag == f"{{{CT}}}Default":
            key = ("default", item.get("Extension", "").casefold())
            if not key[1]:
                raise DocxError("CONTENT_TYPES_INVALID")
        else:
            raise DocxError("CONTENT_TYPES_INVALID")
        if key in seen_content:
            raise DocxError("CONTENT_TYPE_DUPLICATE")
        seen_content.add(key)
    if overrides.get("/" + DOCUMENT) != "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml":
        raise DocxError("MAIN_CONTENT_TYPE_INVALID")
    for name in parts:
        if name == "[Content_Types].xml":
            continue
        extension = name.rsplit(".", 1)[-1].casefold() if "." in name else ""
        if not (overrides.get("/" + name) or defaults.get(extension)):
            raise DocxError("PART_CONTENT_TYPE_MISSING", name)
    for item in content:
        mime = item.get("ContentType", "")
        if "macroEnabled" in mime or "vbaProject" in mime:
            raise DocxError("MACRO_UNSUPPORTED")
        if full and "digital-signature" in mime:
            raise DocxError("SIGNED_OR_MACRO_UNSUPPORTED")
    main_rel_count = 0
    for name, data in parts.items():
        if not name.endswith(".rels"):
            continue
        relroot = _xml(data, limits)
        if relroot.tag != f"{{{R}}}Relationships":
            raise DocxError("RELATIONSHIP_INVALID", name)
        source = _relationship_source(name)
        if source and source not in parts:
            raise DocxError("RELATIONSHIP_SOURCE_MISSING", source)
        seen_ids: set[str] = set()
        for rel in relroot:
            if rel.tag != f"{{{R}}}Relationship":
                raise DocxError("RELATIONSHIP_INVALID", name)
            rel_id = rel.get("Id", "")
            if not rel_id or rel_id in seen_ids:
                raise DocxError("RELATIONSHIP_DUPLICATE_ID", name)
            seen_ids.add(rel_id)
            rel_type = rel.get("Type", "")
            target = rel.get("Target", "")
            if rel.get("TargetMode") == "External":
                if rel_type != OFFICE_REL + "/hyperlink":
                    raise DocxError("EXTERNAL_RELATIONSHIP_UNSUPPORTED", rel_type)
                continue
            if not target or target.startswith("/") or "\\" in target or "?" in target or "#" in target:
                raise DocxError("RELATIONSHIP_TARGET_INVALID", target)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), unquote(target)))
            _part_name(resolved)
            if resolved not in parts:
                raise DocxError("RELATIONSHIP_TARGET_MISSING", resolved)
            if source == "" and rel_type == OFFICE_REL + "/officeDocument":
                main_rel_count += 1
                if resolved != DOCUMENT:
                    raise DocxError("MAIN_DOCUMENT_URI_UNSUPPORTED", resolved)
    if main_rel_count != 1:
        raise DocxError("MAIN_DOCUMENT_RELATIONSHIP_INVALID")
    if full:
        for name in parts:
            if name.startswith("_xmlsignatures/") or name.endswith("vbaProject.bin"):
                raise DocxError("SIGNED_OR_MACRO_UNSUPPORTED")
        for name, data in parts.items():
            if not name.endswith(".xml"):
                continue
            root = _xml(data, limits)
            if root.tag.startswith("{http://purl.oclc.org/ooxml/wordprocessingml/main}"):
                raise DocxError("STRICT_OOXML_UNSUPPORTED")
            # Story parts can have arbitrary OPC URIs. Namespace, not directory,
            # determines whether retained XML can contain Word revisions.
            if any(element.tag == Q("documentProtection") or
                   (isinstance(element.tag, str) and element.tag.startswith("{" + W + "}"))
                   for element in root.iter()):
                for element in root.iter():
                    if not isinstance(element.tag, str):
                        continue
                    local = etree.QName(element).localname
                    if element.tag.startswith("{" + W + "}") and local in REVISION_TAGS:
                        raise DocxError("EXISTING_REVISION_UNSUPPORTED", name)
                    if element.tag == Q("documentProtection"):
                        raise DocxError("DOCUMENT_PROTECTED")
            for element in root.iter():
                if not isinstance(element.tag, str):
                    continue
                if element.tag == "{http://www.w3.org/2001/XInclude}include":
                    raise DocxError("XML_XINCLUDE_UNSUPPORTED")
                if element.tag.startswith("{http://purl.oclc.org/ooxml/wordprocessingml/main}"):
                    raise DocxError("STRICT_OOXML_UNSUPPORTED")
                required = element.get("{http://schemas.openxmlformats.org/markup-compatibility/2006}MustUnderstand")
                if required:
                    raise DocxError("REQUIRED_EXTENSION_UNSUPPORTED")


def _read_parts(path: str | Path, limits: ZipLimits) -> dict[str, bytes]:
    path = Path(path)
    if path.suffix.lower() != ".docx":
        raise DocxError("DOCX_ONLY")
    try:
        if path.stat().st_size > limits.max_file_bytes:
            raise DocxError("ZIP_FILE_LIMIT")
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > limits.max_entries:
                raise DocxError("ZIP_ENTRY_LIMIT")
            seen: set[str] = set()
            total = 0
            parts: dict[str, bytes] = {}
            for info in infos:
                canonical = _part_name(info.filename)
                if canonical in seen:
                    raise DocxError("ZIP_DUPLICATE_PART", info.filename)
                seen.add(canonical)
                if info.flag_bits & 1:
                    raise DocxError("ZIP_ENCRYPTED")
                if info.is_dir():
                    raise DocxError("ZIP_DIRECTORY_ENTRY_UNSUPPORTED")
                total += info.file_size
                if info.file_size > limits.max_part_bytes or total > limits.max_uncompressed_bytes:
                    raise DocxError("ZIP_EXPANSION_LIMIT")
                if info.file_size and info.file_size / max(info.compress_size, 1) > limits.max_ratio:
                    raise DocxError("ZIP_RATIO_LIMIT")
                parts[info.filename] = archive.read(info)
            return parts
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise DocxError("ZIP_INVALID", str(exc)) from exc


def _local(element: etree._Element) -> str:
    return etree.QName(element).localname if isinstance(element.tag, str) else ""


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join("\n" if node.tag in {Q("br"), Q("cr")} else (node.text or "")
                   for node in paragraph.iter()
                   if node.tag in {Q("t"), Q("br"), Q("cr")}
                   and next(node.iterancestors(Q("p")), None) is paragraph)


def _fingerprint(location: str, text: str, zone: str) -> str:
    return _sha((location + "\0" + zone + "\0" + text).encode("utf-8"))


def _plain_contract_heading(text: str) -> bool:
    """Recognize complete alternate chapter labels, never directory page entries."""
    compact = re.sub(r'\s+', '', text)
    match = re.fullmatch(r'(?:[一二三四五六七八九十百零〇]+[、．.]|\d+(?:\.\d+)+[、．.]?)(.+)', compact)
    titles = {'前言','绪言','释义','基金的基本情况','基金的募集','基金的历史沿革',
        '基金的存续','基金合同的生效','基金备案','基金份额的申购与赎回','基金份额的申购和赎回','基金份额的申购、赎回与转换',
        '基金合同当事人及权利义务','基金份额持有人大会','基金的投资','基金的托管',
        '基金管理人、基金托管人的更换条件和程序','基金份额的登记','基金份额的注册登记',
        '基金的财产','基金资产估值','基金费用与税收','基金的费用与税收','基金的收益与分配',
        '基金的会计与审计','基金的信息披露','基金合同的变更、终止与基金财产的清算',
        '违约责任','争议的处理和适用的法律','基金合同的效力','其他事项'}
    return bool(match and match.group(1) in titles)


def _protected_text_nodes(root: etree._Element) -> set[etree._Element]:
    """Track ranges in document order, including readonly wrapper paragraphs."""
    active: set[tuple[str, str]] = set()
    protected: set[etree._Element] = set()
    for node in root.iter():
        name = _local(node)
        if name in {"bookmarkStart", "commentRangeStart", "permStart"} and node.tag == Q(name):
            active.add((name.removesuffix("Start"), node.get(Q("id"), "")))
        elif name in {"bookmarkEnd", "commentRangeEnd", "permEnd"} and node.tag == Q(name):
            active.discard((name.removesuffix("End"), node.get(Q("id"), "")))
        elif node.tag == Q("t") and active:
            protected.add(node)
    return protected


def _project(paragraph: etree._Element, location: str, zone: str, section: str,
             field_active: int, limits: ZipLimits,
             protected_ranges: set[tuple[str, str]] | None = None,
             protected_nodes: set[etree._Element] | None = None) -> tuple[ParagraphSpan, int, bool]:
    chunks: list[str] = []
    spans: list[tuple[int, int, tuple[str, ...]]] = []
    position = 0
    toc = False
    reasons: list[str] = []
    protected_ranges = protected_ranges if protected_ranges is not None else set()
    if protected_nodes is None:
        protected_nodes = _protected_text_nodes(paragraph.getroottree().getroot())

    def barrier() -> None:
        nonlocal position
        if not chunks or chunks[-1] != BARRIER:
            chunks.append(BARRIER)
            position += 1

    def add_text(node: etree._Element, writable: bool) -> None:
        nonlocal position
        value = node.text or ""
        if not value:
            return
        if not writable:
            barrier()
            chunks.append(value)
            position += len(value)
            barrier()
            return
        start = position
        chunks.append(value)
        position += len(value)
        spans.append((start, position, (node.getroottree().getpath(node),)))

    def visit(node: etree._Element, blocked: bool = False) -> None:
        nonlocal field_active, toc, position
        name = _local(node)
        if node.tag in {Q("br"), Q("cr")}:
            chunks.append("\n")
            position += 1
            return
        if name in {"bookmarkStart", "bookmarkEnd", "commentRangeStart", "commentRangeEnd", "permStart", "permEnd"} and node.tag == Q(name):
            ending = name.endswith("End")
            category = name.removesuffix("End") if ending else name.removesuffix("Start")
            key = (category, node.get(Q("id"), ""))
            if ending:
                if key not in protected_ranges:
                    reasons.append("malformed_range")
                protected_ranges.discard(key)
            else:
                protected_ranges.add(key)
            barrier()
            return
        if node.tag == Q("fldChar"):
            kind = node.get(Q("fldCharType"))
            if kind == "begin":
                field_active += 1
            elif kind == "end":
                if field_active == 0:
                    reasons.append("malformed_field")
                else:
                    field_active -= 1
            elif kind != "separate" or field_active == 0:
                reasons.append("malformed_field")
            barrier()
            return
        if node.tag == Q("instrText"):
            if "TOC" in (node.text or "").upper():
                toc = True
            barrier()
            return
        if node.tag == Q("t"):
            run = node.getparent()
            ordinary = run is not None and run.tag == Q("r") and run.getparent() is paragraph
            ordinary = ordinary and [child.tag for child in run if child.tag != Q("rPr")] == [Q("t")]
            add_text(node, ordinary and node not in protected_nodes and not blocked and not field_active and not protected_ranges and zone in {"body", "summary"})
            return
        if node.tag.startswith("{" + W + "}") and name in BOUNDARY_TAGS:
            barrier()
            return
        # Only direct ordinary runs are writable. Unknown extensions and wrappers
        # may carry alternate or hidden views; never flatten them into candidates.
        newly_blocked = blocked or node.tag != Q("r")
        if node.tag == Q("fldSimple") and "TOC" in (node.get(Q("instr"), "")).upper():
            toc = True
        if newly_blocked and not blocked:
            barrier()
        if node.tag.startswith("{" + W + "}") and name in REVISION_TAGS:
            reasons.append("revision_content")
            newly_blocked = True
        for child in node:
            if child.tag == Q("rPr") or child.tag == Q("pPr"):
                continue
            visit(child, newly_blocked)
        if newly_blocked and not blocked:
            barrier()

    for child in paragraph:
        if child.tag != Q("pPr"):
            visit(child)
    text = "".join(chunks)
    merged: list[TextSegment] = []
    for start, end, paths in spans:
        if merged and merged[-1].end == start:
            previous = merged[-1]
            merged[-1] = TextSegment(previous.start, end, previous.node_paths + paths)
        else:
            merged.append(TextSegment(start, end, paths))
    if field_active:
        reasons.append("open_field")
    return ParagraphSpan(location, zone, section, text, tuple(merged), _fingerprint(location, text, zone), reasons=tuple(reasons)), field_active, toc


def _enumerate_paragraphs(root: etree._Element, limits: ZipLimits) -> tuple[tuple[ParagraphSpan, ...], bool]:
    body = root.find(Q("body"))
    if body is None:
        raise DocxError("BODY_MISSING")
    result: list[ParagraphSpan] = []
    zone = "body"
    section = ""
    in_toc = False
    field_active = 0
    has_toc = False
    p_index = 0
    protected_ranges: set[tuple[str, str]] = set()
    protected_nodes = _protected_text_nodes(root)
    indexed: set[etree._Element] = set()

    def add(p: etree._Element, location: str, inherited: str) -> None:
        nonlocal zone, section, in_toc, field_active, has_toc
        indexed.add(p)
        plain = _paragraph_text(p).strip().replace(" ", "")
        style = p.find("./" + Q("pPr") + "/" + Q("pStyle"))
        style_value = style.get(Q("val"), "") if style is not None else ""
        plain_heading = _plain_contract_heading(plain)
        if not inherited and re.fullmatch(r"(?:第[一二三四五六七八九十\d]+(?:部分|章)|[一二三四五六七八九十]+[、．.]|\d+(?:\.\d+)+[、．.]?)?(?:基金合同(?:的)?)?内容摘要", plain):
            zone, section = "summary", plain
        elif not inherited and re.fullmatch(r"(?:附录|附件)(?:[一二三四五六七八九十\d].*)?", plain):
            zone, section = "appendix", plain
        elif not inherited and plain and (plain_heading or style_value.lower().startswith("heading") or re.match(r"^第[一二三四五六七八九十\d]+(?:部分|章|节)", plain)):
            section = plain[:120]
        if style_value.lower().startswith("toc") or plain == "目录":
            in_toc = True
        elif in_toc and (plain_heading or style_value.lower().startswith("heading") or re.match(r"^第[一二三四五六七八九十\d]+(?:部分|章)", plain)):
            in_toc = False
        effective = inherited or ("toc" if in_toc or field_active else zone)
        projected, field_active, toc = _project(p, location, effective, section, field_active, limits, protected_ranges, protected_nodes)
        # A static directory label is protected, but is not a TOC field.
        has_toc |= toc
        if "revision_content" in projected.reasons:
            projected = ParagraphSpan(projected.location, "revision", projected.section_path,
                                      projected.text, (), projected.fingerprint, reasons=projected.reasons)
        elif field_active or "malformed_field" in projected.reasons or "malformed_range" in projected.reasons:
            projected = ParagraphSpan(projected.location, "field", projected.section_path,
                                      projected.text, (), projected.fingerprint, reasons=("open_field",))
        projected = replace(projected, logical_zone="toc" if in_toc or field_active else zone,
                            reasons=projected.reasons + (("unsupported_table_structure",) if inherited == "unsupported_table" else ()))
        result.append(projected)

    for element in body:
        if element.tag == Q("p"):
            add(element, f"p{p_index}", "")
            p_index += 1
        elif element.tag == Q("tbl"):
            table_index = sum(1 for previous in body[:body.index(element)] if previous.tag == Q("tbl"))
            for row_index, row in enumerate(element.findall(Q("tr"))):
                for cell_index, cell in enumerate(row.findall(Q("tc"))):
                    unsupported = cell.find(".//" + Q("tbl")) is not None or cell.find("./" + Q("tcPr") + "/" + Q("gridSpan")) is not None or cell.find("./" + Q("tcPr") + "/" + Q("vMerge")) is not None
                    for cell_p_index, paragraph in enumerate(cell.findall(Q("p"))):
                        add(paragraph, f"tbl{table_index}/r{row_index}/c{cell_index}/p{cell_p_index}", "unsupported_table" if unsupported else "")
                    if unsupported:
                        for nested_p in cell.iter(Q("p")):
                            if nested_p not in indexed:
                                add(nested_p, "readonly:" + nested_p.getroottree().getpath(nested_p), "unsupported_table")
    for paragraph in body.iter(Q("p")):
        if paragraph not in indexed:
            location = "readonly:" + paragraph.getroottree().getpath(paragraph)
            projected, _, toc = _project(paragraph, location, "unsupported_structure", "", 0, limits,
                                       protected_nodes=protected_nodes)
            result.append(projected)
            has_toc |= toc
    return tuple(result), has_toc


def inspect_docx(path: str | Path, *, full: bool = False, limits: ZipLimits | None = None) -> DocumentInspection:
    limits = limits or ZipLimits()
    parts = _read_parts(path, limits)
    source = Path(path).read_bytes()
    _validate_package(parts, limits, full=full)
    root = _xml(parts[DOCUMENT], limits)
    if root.tag != Q("document"):
        raise DocxError("MAIN_DOCUMENT_INVALID")
    paragraphs, has_toc = _enumerate_paragraphs(root, limits)
    return DocumentInspection(_sha(source), paragraphs, has_toc, full, tuple(parts))


def _safe_grapheme_boundary(text: str, index: int) -> bool:
    if index <= 0 or index >= len(text):
        return True
    previous, current = text[index - 1], text[index]
    # Conservative extended-cluster boundaries. Reject uncertain script joins
    # rather than splitting an emoji, spacing mark or Indic conjunct.
    if (unicodedata.category(current).startswith("M") or
        current in {"\u200d", "\n"} and previous in {"\u200d", "\r"} or
        current == "\u200d" or previous == "\u200d" or
        unicodedata.combining(previous) == 9 or
        0x1F3FB <= ord(current) <= 0x1F3FF or
        0xE0020 <= ord(current) <= 0xE007F or
        0x1F1E6 <= ord(previous) <= 0x1F1FF and 0x1F1E6 <= ord(current) <= 0x1F1FF):
        return False

    def hangul(char: str) -> str:
        code = ord(char)
        if 0x1100 <= code <= 0x115F or 0xA960 <= code <= 0xA97C:
            return "L"
        if 0x1160 <= code <= 0x11A7 or 0xD7B0 <= code <= 0xD7C6:
            return "V"
        if 0x11A8 <= code <= 0x11FF or 0xD7CB <= code <= 0xD7FB:
            return "T"
        if 0xAC00 <= code <= 0xD7A3:
            return "LV" if (code - 0xAC00) % 28 == 0 else "LVT"
        return ""

    left, right = hangul(previous), hangul(current)
    if left == "L" and right in {"L", "V", "LV", "LVT"} or left in {"LV", "V"} and right in {"V", "T"} or left in {"LVT", "T"} and right == "T":
        return False
    # Format controls can implement Prepend or invisible script joins. Their
    # boundary semantics are outside the current writable subset.
    return (previous == BARRIER or unicodedata.category(previous) != "Cf") and (current == BARRIER or unicodedata.category(current) != "Cf")


def validate_edit_plan(source: str | Path, edits: Sequence[Mapping[str, Any]],
                       templates: Mapping[str, str], *, limits: ZipLimits | None = None,
                       content_check: Any = None) -> ValidatedPlan:
    """Validate edit geometry, source binding and content provenance.

    ``content_check`` is a trusted closure supplied by the caller for edits whose
    text was generated under the v2 content-verification pipeline. It must raise
    ``DocxError`` when the server-side verification record does not bind the
    edit; edits without a check are rejected rather than published.
    """
    inspection = inspect_docx(source, full=True, limits=limits)
    validated: list[dict[str, Any]] = []
    occupied: dict[str, list[tuple[int, int]]] = {}
    for incoming in edits:
        edit = dict(incoming)
        if edit.get("source_sha256") != inspection.source_sha256:
            raise DocxError("SOURCE_HASH_MISMATCH")
        if edit.get("verified") is not True:
            raise DocxError("EDIT_UNVERIFIED")
        location = str(edit.get("location", ""))
        paragraph = inspection.by_location(location)
        if edit.get("zone") != paragraph.zone or not paragraph.editable:
            raise DocxError("REGION_NOT_EDITABLE", location)
        if edit.get("mapping_version", MAPPING_VERSION) != MAPPING_VERSION:
            raise DocxError("MAPPING_VERSION_MISMATCH")
        if edit.get("fingerprint", paragraph.fingerprint) != paragraph.fingerprint:
            raise DocxError("PARAGRAPH_DRIFT")
        content_source = str(edit.get("content_source", "template"))
        if content_source == "template":
            template_id = str(edit.get("template_id", ""))
            if template_id not in templates or edit.get("replacement") != templates[template_id]:
                raise DocxError("TEMPLATE_MISMATCH")
        elif content_source == "generated":
            if not callable(content_check):
                raise DocxError("GENERATED_CONTENT_UNVERIFIED")
            content_check(edit)
        else:
            raise DocxError("CONTENT_SOURCE_INVALID")
        start, end = edit.get("start"), edit.get("end")
        insertion = edit.get("operation") == "insert"
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start <= end <= len(paragraph.text)) or (start == end) != insertion:
            raise DocxError("EDIT_RANGE_INVALID")
        if insertion:
            anchor = edit.get("anchor", {})
            anchor_start, anchor_end = anchor.get("start"), anchor.get("end")
            if not isinstance(anchor_start, int) or not isinstance(anchor_end, int) or not (0 <= anchor_start < anchor_end == start):
                raise DocxError("INSERT_ANCHOR_INVALID")
            anchor_text = paragraph.text[anchor_start:anchor_end]
            if anchor_text != anchor.get("text") or _sha(anchor_text.encode("utf-8")) != anchor.get("sha256"):
                raise DocxError("INSERT_ANCHOR_MISMATCH")
            if not any(s.start <= anchor_start and anchor_end <= s.end for s in paragraph.segments):
                raise DocxError("INSERT_ANCHOR_UNSAFE")
        old = paragraph.text[start:end]
        if old != edit.get("expected_old_text") or _sha(old.encode("utf-8")) != edit.get("expected_old_hash"):
            raise DocxError("EXPECTED_TEXT_MISMATCH")
        if not any(segment.start <= start and end <= segment.end for segment in paragraph.segments):
            raise DocxError("EDIT_CROSSES_BARRIER")
        if not _safe_grapheme_boundary(paragraph.text, start) or not _safe_grapheme_boundary(paragraph.text, end):
            raise DocxError("GRAPHEME_BOUNDARY_INVALID")
        for existing_start, existing_end in occupied.setdefault(location, []):
            if not (end < existing_start or start > existing_end):
                raise DocxError("EDIT_OVERLAP_OR_ADJACENT")
        occupied[location].append((start, end))
        edit["fingerprint"] = paragraph.fingerprint
        edit["mapping_version"] = MAPPING_VERSION
        validated.append(edit)
    import json
    serialized = json.dumps(validated, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ValidatedPlan(inspection.source_sha256, tuple(validated), _sha(serialized),
                         inspection.has_toc_field, dict(templates), content_check)


def _paragraph_element(root: etree._Element, location: str) -> etree._Element:
    body = root.find(Q("body"))
    if body is None:
        raise DocxError("BODY_MISSING")
    direct = re.fullmatch(r"p(\d+)", location)
    if direct:
        paragraphs = [child for child in body if child.tag == Q("p")]
        index = int(direct.group(1))
        if index >= len(paragraphs):
            raise DocxError("LOCATION_NOT_FOUND", location)
        return paragraphs[index]
    table = re.fullmatch(r"tbl(\d+)/r(\d+)/c(\d+)/p(\d+)", location)
    if table:
        tables = [child for child in body if child.tag == Q("tbl")]
        try:
            t = tables[int(table.group(1))]
            row = t.findall(Q("tr"))[int(table.group(2))]
            cell = row.findall(Q("tc"))[int(table.group(3))]
            return cell.findall(Q("p"))[int(table.group(4))]
        except IndexError as exc:
            raise DocxError("LOCATION_NOT_FOUND", location) from exc
    raise DocxError("LOCATION_NOT_FOUND", location)


def _make_text_run(template_run: etree._Element, value: str, *, deleted: bool = False) -> etree._Element:
    run = etree.Element(Q("r"))
    properties = template_run.find(Q("rPr"))
    if properties is not None:
        run.append(deepcopy(properties))
    text_node = etree.SubElement(run, Q("delText") if deleted else Q("t"))
    if value.startswith(" ") or value.endswith(" "):
        text_node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    text_node.text = value
    return run


def _revision(tag: str, revision_id: int, author: str, when: str,
              runs: Sequence[etree._Element]) -> etree._Element:
    wrapper = etree.Element(Q(tag))
    wrapper.set(Q("id"), str(revision_id))
    wrapper.set(Q("author"), author)
    wrapper.set(Q("date"), when)
    wrapper.extend(runs)
    return wrapper


def _inserted_runs(template_run: etree._Element, value: str) -> list[etree._Element]:
    runs: list[etree._Element] = []
    for number, line in enumerate(value.split("\n")):
        if number:
            break_run = etree.Element(Q("r"))
            etree.SubElement(break_run, Q("br"))
            runs.append(break_run)
        runs.append(_make_text_run(template_run, line))
    return runs


def _apply_one(root: etree._Element, edit: Mapping[str, Any], del_id: int,
               ins_id: int, author: str, when: str, limits: ZipLimits) -> None:
    paragraph = _paragraph_element(root, str(edit["location"]))
    projection, _, _ = _project(paragraph, str(edit["location"]), str(edit["zone"]), "", 0, limits)
    start, end = int(edit["start"]), int(edit["end"])
    segment = next((s for s in projection.segments if s.start <= start and end <= s.end), None)
    if segment is None:
        raise DocxError("EDIT_CROSSES_BARRIER")
    nodes: list[tuple[etree._Element, int, int]] = []
    cursor = segment.start
    for xpath in segment.node_paths:
        found = root.xpath(xpath, namespaces={"w": W})
        if len(found) != 1:
            raise DocxError("XML_MAPPING_DRIFT")
        node = found[0]
        node_end = cursor + len(node.text or "")
        nodes.append((node, cursor, node_end))
        cursor = node_end
    selected = [(node, lo, hi) for node, lo, hi in nodes if hi > start and lo < end]
    if start == end:
        selected = next(([item] for item in nodes if item[1] < start <= item[2]), [])
    if not selected:
        raise DocxError("XML_MAPPING_DRIFT")
    runs: list[etree._Element] = []
    deleted_runs: list[etree._Element] = []
    for node, lo, hi in selected:
        run = node.getparent()
        if run is None or run.tag != Q("r") or run.getparent() is not paragraph:
            raise DocxError("RUN_STRUCTURE_UNSUPPORTED")
        if [child.tag for child in run if child.tag != Q("rPr")] != [Q("t")]:
            raise DocxError("RUN_STRUCTURE_UNSUPPORTED")
        runs.append(run)
        left, right = max(start - lo, 0), min(end - lo, hi - lo)
        deleted_runs.append(_make_text_run(run, (node.text or "")[left:right], deleted=True))
    first, last = selected[0], selected[-1]
    first_run = runs[0]
    last_run = runs[-1]
    if len({id(run) for run in runs}) != len(runs):
        raise DocxError("RUN_STRUCTURE_UNSUPPORTED")
    indexes = [paragraph.index(run) for run in runs]
    if indexes != list(range(indexes[0], indexes[-1] + 1)):
        raise DocxError("EDIT_CROSSES_BARRIER")
    prefix = (first[0].text or "")[:start - first[1]]
    suffix = (last[0].text or "")[end - last[1]:]
    replacement: list[etree._Element] = []
    if prefix:
        replacement.append(_make_text_run(first_run, prefix))
    replacement.append(_revision("del", del_id, author, when, deleted_runs))
    replacement.append(_revision("ins", ins_id, author, when,
                                 _inserted_runs(first_run, str(edit["replacement"])) ))
    if suffix:
        replacement.append(_make_text_run(last_run, suffix))
    insert_at = indexes[0]
    for run in runs:
        paragraph.remove(run)
    for offset, node in enumerate(replacement):
        paragraph.insert(insert_at + offset, node)


def _accept_our_revisions(root: etree._Element, manifests: Sequence[Mapping[str, Any]]) -> None:
    ins_ids = {str(item["ins_id"]) for item in manifests}
    del_ids = {str(item["del_id"]) for item in manifests}
    found_ins: set[str] = set()
    found_del: set[str] = set()
    for node in list(root.iter()):
        if node.tag not in {Q("ins"), Q("del")}:
            continue
        rid = node.get(Q("id"), "")
        parent = node.getparent()
        if parent is None:
            raise DocxError("REVISION_STRUCTURE_INVALID")
        index = parent.index(node)
        if node.tag == Q("del"):
            if rid not in del_ids or rid in found_del:
                raise DocxError("REVISION_ID_UNEXPECTED")
            found_del.add(rid)
            parent.remove(node)
        else:
            if rid not in ins_ids or rid in found_ins:
                raise DocxError("REVISION_ID_UNEXPECTED")
            found_ins.add(rid)
            for offset, run in enumerate(list(node)):
                node.remove(run)
                parent.insert(index + offset, run)
            parent.remove(node)
    if found_ins != ins_ids or found_del != del_ids:
        raise DocxError("REVISION_COUNT_MISMATCH")


def _write_package(path: Path, parts: Mapping[str, bytes], document_xml: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix=".fundlex-", suffix=".docx", dir=path.parent, delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
            for name, data in parts.items():
                output.writestr(name, document_xml if name == DOCUMENT else data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _paragraph_texts(root: etree._Element, limits: ZipLimits) -> dict[str, str]:
    spans, _ = _enumerate_paragraphs(root, limits)
    return {span.location: span.text for span in spans}


def _non_target_snapshot(root: etree._Element, edited: set[str]) -> dict[str, bytes]:
    body = root.find(Q("body"))
    if body is None:
        raise DocxError("BODY_MISSING")
    snapshot: dict[str, bytes] = {}
    direct = 0
    table = 0
    for element in body:
        if element.tag == Q("p"):
            location = f"p{direct}"
            direct += 1
            if location not in edited:
                snapshot[location] = etree.tostring(element, method="c14n")
        elif element.tag == Q("tbl"):
            for ri, row in enumerate(element.findall(Q("tr"))):
                for ci, cell in enumerate(row.findall(Q("tc"))):
                    for pi, paragraph in enumerate(cell.findall(Q("p"))):
                        location = f"tbl{table}/r{ri}/c{ci}/p{pi}"
                        if location not in edited:
                            snapshot[location] = etree.tostring(paragraph, method="c14n")
            table += 1
    return snapshot


def _structure_snapshot(root: etree._Element, edited: set[str]) -> bytes:
    """Keep the complete document topology, including target paragraph properties.

    Only ordinary text runs in edited paragraphs can be split by the editor.
    Everything else (including nested stories, fields and table properties) is
    compared canonically across independently reopened packages.
    """
    clone = deepcopy(root)
    for location in edited:
        paragraph = _paragraph_element(clone, location)
        for node in list(paragraph):
            if node.tag in {Q("ins"), Q("del")}:
                paragraph.remove(node)
            elif node.tag == Q("r") and [c.tag for c in node if c.tag != Q("rPr")] == [Q("t")]:
                paragraph.remove(node)
            elif node.tag == Q("r") and len(node) == 1 and node[0].tag == Q("br") and not node.attrib and not node[0].attrib:
                # Template newlines create plain break runs; their positions and
                # count are checked by the full expected text projection.
                paragraph.remove(node)
    return etree.tostring(clone, method="c14n")


def _validate_revision_manifest(root: etree._Element, manifests: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    expected = {str(item[key]): (item, tag) for item in manifests
                for key, tag in (("del_id", "del"), ("ins_id", "ins"))}
    for node in root.iter():
        if node.tag not in {Q("ins"), Q("del")}:
            continue
        rid = node.get(Q("id"), "")
        if rid not in expected or rid in seen:
            raise DocxError("REVISION_ID_UNEXPECTED")
        seen.add(rid)
        item, tag = expected[rid]
        if node.tag != Q(tag) or node.getparent() is not _paragraph_element(root, str(item["location"])):
            raise DocxError("REVISION_STRUCTURE_INVALID")
        if not node.get(Q("author"), "").strip():
            raise DocxError("REVISION_METADATA_INVALID")
        try:
            stamp = datetime.fromisoformat(node.get(Q("date"), "").replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError("missing timezone")
        except ValueError as exc:
            raise DocxError("REVISION_METADATA_INVALID") from exc
        text_tag = Q("delText") if tag == "del" else Q("t")
        for run in node:
            content_tags = [c.tag for c in run if c.tag != Q("rPr")]
            if run.tag != Q("r") or content_tags not in ([[text_tag], [Q("br")]] if tag == "ins" else [[text_tag]]):
                raise DocxError("REVISION_STRUCTURE_INVALID")
        actual = "".join("\n" if t.tag == Q("br") else t.text or ""
                         for t in node.iter() if t.tag in {text_tag, Q("br")})
        if actual != item["expected_old_text" if tag == "del" else "replacement"]:
            raise DocxError("REVISION_TEXT_MISMATCH")
    if seen != set(expected):
        raise DocxError("REVISION_COUNT_MISMATCH")


def _text_formats(root: etree._Element, location: str, limits: ZipLimits) -> list[bytes | None]:
    spans, _ = _enumerate_paragraphs(root, limits)
    paragraph = next(p for p in spans if p.location == location)
    formats: list[bytes | None] = [None] * len(paragraph.text)
    for segment in paragraph.segments:
        cursor = segment.start
        for path in segment.node_paths:
            text = root.xpath(path, namespaces=NS)[0]
            properties = text.getparent().find(Q("rPr"))
            value = etree.tostring(properties, method="c14n") if properties is not None else b""
            end = cursor + len(text.text or "")
            formats[cursor:end] = [value] * (end - cursor)
            cursor = end
    return formats


def generate_artifacts(source: str | Path, plan: ValidatedPlan, redline_path: str | Path,
                       final_path: str | Path, *, author: str = "FundLex",
                       limits: ZipLimits | None = None) -> ArtifactValidation:
    """Generate both artifacts from one validated plan and independently verify them.

    ``plan`` must be the result of :func:`validate_edit_plan`; action publication
    policy belongs to the caller and defaults to disabled at the rules layer.
    """
    limits = limits or ZipLimits()
    source = Path(source)
    redline_path, final_path = Path(redline_path), Path(final_path)
    if redline_path.resolve() == final_path.resolve() or source.resolve() in {redline_path.resolve(), final_path.resolve()}:
        raise DocxError("OUTPUT_PATH_INVALID")
    if not isinstance(plan, ValidatedPlan) or not plan.edits:
        raise DocxError("PLAN_EMPTY_OR_UNVALIDATED")
    if _sha(source.read_bytes()) != plan.source_sha256:
        raise DocxError("SOURCE_HASH_MISMATCH")
    # A caller might retain and mutate a dict after validation. Revalidate both
    # template provenance and source mapping at the publication boundary.
    checked = validate_edit_plan(source, plan.edits, plan.templates, limits=limits,
                                 content_check=plan.content_check)
    if checked.plan_sha256 != plan.plan_sha256 or checked.has_toc_field != plan.has_toc_field:
        raise DocxError("PLAN_DRIFT")
    parts = _read_parts(source, limits)
    _validate_package(parts, limits, full=True)
    original = _xml(parts[DOCUMENT], limits)
    root = deepcopy(original)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    manifest: list[dict[str, Any]] = []
    try:
        for number, edit in enumerate(sorted(plan.edits, key=lambda e: (e["location"], -e["start"])), start=1):
            del_id, ins_id = number * 2 - 1, number * 2
            _apply_one(root, edit, del_id, ins_id, author, now, limits)
            manifest.append({"edit_id": edit.get("edit_id", f"edit-{number}"), "location": edit["location"],
                             "start": edit["start"], "end": edit["end"], "expected_old_text": edit["expected_old_text"],
                             "replacement": edit["replacement"], "template_id": edit.get("template_id", ""),
                             "del_id": del_id, "ins_id": ins_id})
        redline_xml = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
        final_root = deepcopy(root)
        _accept_our_revisions(final_root, manifest)
        final_xml = etree.tostring(final_root, encoding="UTF-8", xml_declaration=True)
        _write_package(redline_path, parts, redline_xml)
        _write_package(final_path, parts, final_xml)
        # Independent re-open is part of publication, not an optional test.
        red_parts, final_parts = _read_parts(redline_path, limits), _read_parts(final_path, limits)
        _validate_package(red_parts, limits, full=False)
        _validate_package(final_parts, limits, full=True)
        if set(red_parts) != set(parts) or set(final_parts) != set(parts):
            raise DocxError("PACKAGE_MEMBER_DRIFT")
        if any(red_parts[name] != data or final_parts[name] != data for name, data in parts.items() if name != DOCUMENT):
            raise DocxError("NON_DOCUMENT_PART_CHANGED")
        red_reopen = _xml(red_parts[DOCUMENT], limits)
        final_reopen = _xml(final_parts[DOCUMENT], limits)
        _validate_revision_manifest(red_reopen, manifest)
        accepted = deepcopy(red_reopen)
        _accept_our_revisions(accepted, manifest)
        if etree.tostring(accepted, method="c14n") != etree.tostring(final_reopen, method="c14n"):
            raise DocxError("FINAL_REVISION_MISMATCH")
        edited = {str(edit["location"]) for edit in plan.edits}
        skeleton = _structure_snapshot(original, edited)
        if skeleton != _structure_snapshot(red_reopen, edited) or skeleton != _structure_snapshot(final_reopen, edited):
            raise DocxError("NON_TARGET_STRUCTURE_CHANGED")
        source_snapshot = _non_target_snapshot(original, edited)
        if source_snapshot != _non_target_snapshot(red_reopen, edited) or source_snapshot != _non_target_snapshot(final_reopen, edited):
            raise DocxError("NON_TARGET_CHANGED")
        source_texts, final_texts = _paragraph_texts(original, limits), _paragraph_texts(final_reopen, limits)
        for location, old_text in source_texts.items():
            expected = old_text
            for edit in sorted((e for e in plan.edits if e["location"] == location), key=lambda e: -e["start"]):
                expected = expected[:edit["start"]] + str(edit["replacement"]) + expected[edit["end"]:]
            if final_texts.get(location) != expected:
                raise DocxError("FINAL_TEXT_MISMATCH", location)
        for location in edited:
            expected_formats = _text_formats(original, location, limits)
            for edit in sorted((e for e in plan.edits if e["location"] == location), key=lambda e: -e["start"]):
                inherited = expected_formats[edit["start"] - 1 if edit["start"] == edit["end"] else edit["start"]]
                expected_formats[edit["start"]:edit["end"]] = [None if char == "\n" else inherited for char in str(edit["replacement"])]
            if _text_formats(final_reopen, location, limits) != expected_formats:
                raise DocxError("RUN_FORMAT_CHANGED", location)
        return ArtifactValidation(_sha(redline_path.read_bytes()), _sha(final_path.read_bytes()),
                                  tuple(manifest), ("package", "revisions", "final_equivalence", "non_target",
                                                    "template_text") + (("content_verification",) if plan.content_check is not None else ()),
                                  plan.has_toc_field, "not_updated" if plan.has_toc_field else "not_present")
    except Exception:
        redline_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def _generate_identical_artifacts(source: str | Path, redline_path: str | Path,
                                       final_path: str | Path,
                                       *, limits: ZipLimits | None = None) -> ArtifactValidation:
    """Write and independently validate byte-identical supported DOCX copies."""
    limits = limits or ZipLimits()
    source = Path(source)
    redline_path, final_path = Path(redline_path), Path(final_path)
    if redline_path.resolve() == final_path.resolve() or source.resolve() in {redline_path.resolve(), final_path.resolve()}:
        raise DocxError("OUTPUT_PATH_INVALID")
    inspection = inspect_docx(source, full=True, limits=limits)
    original = source.read_bytes()
    try:
        for target in (redline_path, final_path):
            target.parent.mkdir(parents=True, exist_ok=True)
            with NamedTemporaryFile(prefix=".fundlex-eval-", suffix=".docx", dir=target.parent, delete=False) as temp:
                temporary = Path(temp.name)
                temp.write(original)
            try:
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        for target in (redline_path, final_path):
            if target.read_bytes() != original:
                raise DocxError("EVALUATION_COPY_MISMATCH")
            inspect_docx(target, full=True, limits=limits)
        return ArtifactValidation(inspection.source_sha256, inspection.source_sha256, (),
                                  ("package", "zero_edit", "byte_identity"), inspection.has_toc_field,
                                  "not_updated" if inspection.has_toc_field else "not_present")
    except Exception:
        redline_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def generate_noop_evaluation_artifacts(source: str | Path, redline_path: str | Path,
                                       final_path: str | Path, *, limits: ZipLimits | None = None) -> ArtifactValidation:
    """Diagnostic copies for unreleased rules; not final contract delivery."""
    return _generate_identical_artifacts(source, redline_path, final_path, limits=limits)


def generate_unchanged_artifacts(source: str | Path, plan: ValidatedPlan, redline_path: str | Path,
                                 final_path: str | Path, *, limits: ZipLimits | None = None) -> ArtifactValidation:
    """Deliver an unchanged contract from a validated empty released-rule plan.

    The caller verifies action publication and complete candidate decisions.
    """
    if not isinstance(plan, ValidatedPlan) or plan.edits:
        raise DocxError("PLAN_NOT_EMPTY_OR_UNVALIDATED")
    checked = validate_edit_plan(source, (), plan.templates, limits=limits, content_check=plan.content_check)
    if checked.source_sha256 != plan.source_sha256 or checked.plan_sha256 != plan.plan_sha256:
        raise DocxError("PLAN_DRIFT")
    return _generate_identical_artifacts(source, redline_path, final_path, limits=limits)
