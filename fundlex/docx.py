"""Conservative, auditable DOCX inspection and OOXML edit primitives.

The editor deliberately supports a small subset of Transitional WordprocessingML.
Unknown structure is reported as a typed failure before any output is published.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
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
    main_rel_count = 0
    for name, data in parts.items():
        if not name.endswith(".rels"):
            continue
        relroot = _xml(data, limits)
        if relroot.tag != f"{{{R}}}Relationships":
            raise DocxError("RELATIONSHIP_INVALID", name)
        source = _relationship_source(name)
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
            if name.startswith("word/"):
                for element in root.iter():
                    local = etree.QName(element).localname
                    if element.tag.startswith("{" + W + "}") and local in REVISION_TAGS:
                        raise DocxError("EXISTING_REVISION_UNSUPPORTED", name)
                    if element.tag == Q("documentProtection"):
                        raise DocxError("DOCUMENT_PROTECTED")


def _read_parts(path: str | Path, limits: ZipLimits) -> dict[str, bytes]:
    path = Path(path)
    if path.suffix.lower() != ".docx":
        raise DocxError("DOCX_ONLY")
    if path.stat().st_size > limits.max_file_bytes:
        raise DocxError("ZIP_FILE_LIMIT")
    try:
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
    return etree.QName(element).localname


def _paragraph_text(paragraph: etree._Element) -> str:
    return "".join((node.text or "") for node in paragraph.iter(Q("t")))


def _fingerprint(location: str, text: str, zone: str) -> str:
    return _sha((location + "\0" + zone + "\0" + text).encode("utf-8"))


def _project(paragraph: etree._Element, location: str, zone: str, section: str,
             field_active: int, limits: ZipLimits) -> tuple[ParagraphSpan, int, bool]:
    chunks: list[str] = []
    spans: list[tuple[int, int, tuple[str, ...]]] = []
    position = 0
    toc = False
    reasons: list[str] = []

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
        nonlocal field_active, toc
        name = _local(node)
        if node.tag == Q("fldChar"):
            kind = node.get(Q("fldCharType"))
            if kind == "begin":
                field_active += 1
            elif kind == "end":
                if field_active == 0:
                    reasons.append("malformed_field")
                else:
                    field_active -= 1
            barrier()
            return
        if node.tag == Q("instrText"):
            if "TOC" in (node.text or "").upper():
                toc = True
            barrier()
            return
        if node.tag == Q("t"):
            add_text(node, not blocked and not field_active and zone in {"body", "summary"})
            return
        if node.tag.startswith("{" + W + "}") and name in BOUNDARY_TAGS:
            barrier()
            return
        newly_blocked = blocked or node.tag in {Q("hyperlink"), Q("sdt"), Q("fldSimple"), Q("txbxContent"), Q("smartTag"), Q("customXml")}
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

    def add(p: etree._Element, location: str, inherited: str) -> None:
        nonlocal zone, section, in_toc, field_active, has_toc
        plain = _paragraph_text(p).strip().replace(" ", "")
        style = p.find("./" + Q("pPr") + "/" + Q("pStyle"))
        style_value = style.get(Q("val"), "") if style is not None else ""
        if re.fullmatch(r"(?:基金合同)?内容摘要", plain):
            zone, section = "summary", plain
        elif re.fullmatch(r"(?:附录|附件)(?:[一二三四五六七八九十\d].*)?", plain):
            zone, section = "appendix", plain
        elif plain and (style_value.lower().startswith("heading") or re.match(r"^第[一二三四五六七八九十\d]+(?:部分|章|节)", plain)):
            section = plain[:120]
        if style_value.lower().startswith("toc") or plain == "目录":
            in_toc = True
        elif in_toc and (style_value.lower().startswith("heading") or re.match(r"^第[一二三四五六七八九十\d]+(?:部分|章)", plain)):
            in_toc = False
        effective = "unsupported_table" if inherited == "unsupported_table" else ("toc" if in_toc or field_active else zone)
        projected, field_active, toc = _project(p, location, effective, section, field_active, limits)
        has_toc |= toc or in_toc
        if "revision_content" in projected.reasons:
            projected = ParagraphSpan(projected.location, "revision", projected.section_path,
                                      projected.text, (), projected.fingerprint, reasons=projected.reasons)
        elif (field_active or "malformed_field" in projected.reasons) and projected.zone != "toc":
            projected = ParagraphSpan(projected.location, "field", projected.section_path,
                                      projected.text, (), projected.fingerprint, reasons=("open_field",))
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
    return tuple(result), has_toc


def inspect_docx(path: str | Path, *, full: bool = False, limits: ZipLimits | None = None) -> DocumentInspection:
    limits = limits or ZipLimits()
    source = Path(path).read_bytes()
    parts = _read_parts(path, limits)
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
    return not (unicodedata.combining(current) or current in {"\ufe0e", "\ufe0f", "\u200d"} or previous == "\u200d")


def validate_edit_plan(source: str | Path, edits: Sequence[Mapping[str, Any]],
                       templates: Mapping[str, str], *, limits: ZipLimits | None = None) -> ValidatedPlan:
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
        template_id = str(edit.get("template_id", ""))
        if template_id not in templates or edit.get("replacement") != templates[template_id]:
            raise DocxError("TEMPLATE_MISMATCH")
        start, end = edit.get("start"), edit.get("end")
        if not isinstance(start, int) or not isinstance(end, int) or not (0 <= start < end <= len(paragraph.text)):
            raise DocxError("EDIT_RANGE_INVALID")
        old = paragraph.text[start:end]
        if old != edit.get("expected_old_text") or _sha(old.encode("utf-8")) != edit.get("expected_old_hash"):
            raise DocxError("EXPECTED_TEXT_MISMATCH")
        if not _safe_grapheme_boundary(paragraph.text, start) or not _safe_grapheme_boundary(paragraph.text, end):
            raise DocxError("GRAPHEME_BOUNDARY_INVALID")
        if not any(segment.start <= start and end <= segment.end for segment in paragraph.segments):
            raise DocxError("EDIT_CROSSES_BARRIER")
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
                         inspection.has_toc_field, dict(templates))


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
                                 [_make_text_run(first_run, str(edit["replacement"]))]))
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
    checked = validate_edit_plan(source, plan.edits, plan.templates, limits=limits)
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
                             "replacement": edit["replacement"], "template_id": edit["template_id"],
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
        accepted = deepcopy(red_reopen)
        _accept_our_revisions(accepted, manifest)
        if etree.tostring(accepted, method="c14n") != etree.tostring(final_reopen, method="c14n"):
            raise DocxError("FINAL_REVISION_MISMATCH")
        edited = {str(edit["location"]) for edit in plan.edits}
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
        return ArtifactValidation(_sha(redline_path.read_bytes()), _sha(final_path.read_bytes()),
                                  tuple(manifest), ("package", "revisions", "final_equivalence", "non_target", "template_text"),
                                  plan.has_toc_field, "not_updated" if plan.has_toc_field else "not_present")
    except Exception:
        redline_path.unlink(missing_ok=True)
        final_path.unlink(missing_ok=True)
        raise


def generate_noop_evaluation_artifacts(source: str | Path, redline_path: str | Path,
                                       final_path: str | Path,
                                       *, limits: ZipLimits | None = None) -> ArtifactValidation:
    """Write byte-identical evaluation copies for a validated zero-edit decision.

    These copies are diagnostic work products. The caller must not publish them as
    a final revised contract or claim that a rule action has been applied.
    """
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
