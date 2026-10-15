"""Guide DOCX extraction, model-assisted rule parsing and independent verification.

The guide document is the only source of new policy text for the recall-first
engine. This module extracts its paragraphs deterministically from OOXML, has the
model group them into executable rules, validates every text field against the
extracted source and runs an independent verification call over the candidate
groups. Nothing here writes contract text or edits documents.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lxml import etree

from .model import ModelError

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
Q = lambda local: f"{{{W}}}{local}"

GUIDE_SCHEMA_VERSION = "guide-rules-v1"
PARSER_VERSION = "guide-parse-1"
GUIDE_PARSE_PROMPT_VERSION = "guide_parse_v1"
GUIDE_VERIFY_PROMPT_VERSION = "guide_verify_v1"

EMPHASIS_VALUES = ("plain", "red", "bold")
CONDITION_KINDS = ("none", "class_count", "has_service_fee", "is_floating_fee", "compound")
OPERATIONS = ("append", "replace", "delete", "noop")
FINDING_KINDS = ("missing_group", "wrong_condition", "wrong_text", "wrong_operation",
                 "missing_reference", "ambiguous_branch")

# Business domains named by the guide's own group headings. Only used to keep a
# heading-only paragraph out of the deterministic coverage-gap list.
GUIDE_DOMAINS = ("释义", "基金的基本情况", "基金份额的申购与赎回", "基金费用与税收",
                 "基金合同的变更", "基金合同", "基金的收益与分配", "基金财产清算")
_HEADING_PREFIX = re.compile("^(?:" + "|".join(re.escape(name) for name in GUIDE_DOMAINS) + r")[-－—,，:：]")
_WS = re.compile(r"\s+")
_MISSING = object()

_SKIPPED_TEXT_TAGS = frozenset({Q("instrText"), Q("delText")})
_SKIPPED_ANCESTORS = frozenset({Q("del"), Q("moveFrom")})


class GuideError(ValueError):
    def __init__(self, code: str, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


@dataclass(frozen=True)
class GuideParagraph:
    index: int
    text: str
    emphasis: str


@dataclass(frozen=True)
class GuideSource:
    path: str
    source_sha256: str
    paragraphs: tuple[GuideParagraph, ...]
    full_text: str


# ---------------------------------------------------------------------------
# DOCX extraction
# ---------------------------------------------------------------------------

def _hex_red(value: str | None) -> bool:
    """Red-ish run colour: strong red channel, weak green/blue (FF0000, C00000, ...)."""
    if not value:
        return False
    raw = value.strip().lstrip("#")
    if raw.lower() in {"auto", "none"} or not re.fullmatch(r"[0-9A-Fa-f]{6}", raw):
        return False
    red, green, blue = (int(raw[offset:offset + 2], 16) for offset in (0, 2, 4))
    return red >= 0xB0 and green <= 0x60 and blue <= 0x60


def _run_bold(properties: Any) -> bool:
    if properties is None:
        return False
    node = properties.find(Q("b"))
    if node is None:
        return False
    value = node.get(Q("val"))
    return value is None or value.strip().lower() not in {"0", "false", "off"}


def _run_emphasis(properties: Any) -> str:
    if properties is None:
        return "plain"
    color = properties.find(Q("color"))
    if color is not None and _hex_red(color.get(Q("val"))):
        return "red"
    return "bold" if _run_bold(properties) else "plain"


def _excluded_text(node: Any, paragraph: Any) -> bool:
    """True for field/deleted text: instructions and rejected revisions are not guide text."""
    if node.tag in _SKIPPED_TEXT_TAGS:
        return True
    parent = node.getparent()
    while parent is not None and parent is not paragraph:
        if parent.tag in _SKIPPED_ANCESTORS:
            return True
        parent = parent.getparent()
    return False


def _paragraph_text_emphasis(paragraph: Any) -> tuple[str, str]:
    pieces: list[tuple[str, str]] = []
    for node in paragraph.iter(Q("t")):
        if _excluded_text(node, paragraph):
            continue
        run = node.getparent()
        while run is not None and run.tag != Q("r"):
            run = run.getparent()
        properties = run.find(Q("rPr")) if run is not None else None
        pieces.append((node.text or "", _run_emphasis(properties)))
    text = "".join(piece for piece, _kind in pieces)
    counts = {"red": 0, "bold": 0, "plain": 0}
    for piece, kind in pieces:
        counts[kind] += len(piece)
    total = sum(counts.values())
    if not total:
        return text, "plain"
    if counts["red"] * 2 > total:
        return text, "red"
    if counts["bold"] * 2 > total:
        return text, "bold"
    return text, "plain"


def extract_guide_source(path: str | Path) -> GuideSource:
    target = Path(path)
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise GuideError("GUIDE_SOURCE_UNREADABLE",
                         {"path": str(target), "reason": type(exc).__name__}) from exc
    source_sha256 = hashlib.sha256(raw).hexdigest()
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            document = archive.read("word/document.xml")
    except (zipfile.BadZipFile, KeyError, OSError) as exc:
        raise GuideError("GUIDE_SOURCE_UNREADABLE",
                         {"path": str(target), "reason": type(exc).__name__}) from exc
    try:
        root = etree.fromstring(document, parser=etree.XMLParser(resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError as exc:
        raise GuideError("GUIDE_SOURCE_UNREADABLE",
                         {"path": str(target), "reason": "XMLSyntaxError"}) from exc
    paragraphs: list[GuideParagraph] = []
    body = root.find(Q("body"))
    if body is not None:
        for element in body:
            if element.tag != Q("p"):
                continue
            text, emphasis = _paragraph_text_emphasis(element)
            paragraphs.append(GuideParagraph(index=len(paragraphs), text=text, emphasis=emphasis))
    if not any(paragraph.text.strip() for paragraph in paragraphs):
        raise GuideError("GUIDE_SOURCE_EMPTY",
                         {"path": str(target), "paragraphs": len(paragraphs)})
    full_text = "\n".join(f"[{paragraph.index}] {paragraph.text}" for paragraph in paragraphs)
    return GuideSource(path=str(target), source_sha256=source_sha256,
                       paragraphs=tuple(paragraphs), full_text=full_text)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def _compact(text: str) -> str:
    return _WS.sub("", text)


def _normalized_source(source: GuideSource) -> str:
    """Whitespace-stripped concatenation of the paragraph texts.

    The ``[n]`` index markers are address labels, not source text, so a verbatim
    multi-paragraph append still resolves against contiguous guide paragraphs.
    """
    return "".join(_compact(paragraph.text) for paragraph in source.paragraphs)


def _verbatim(text: str, normalized: str) -> bool:
    needle = _compact(text)
    return bool(needle) and needle in normalized


def _clip(text: str, limit: int = 80) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def _issue(code: str, rule_id: str, detail: str) -> dict[str, Any]:
    return {"code": code, "rule_id": rule_id, "detail": detail}


def _string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    if any(not isinstance(item, str) for item in value):
        return None
    return value


def _condition_error(condition: Any) -> str | None:
    """Deterministic condition contract: returns an error detail or None."""
    if not isinstance(condition, dict):
        return "must be an object with kind and value"
    kind = condition.get("kind")
    if kind not in CONDITION_KINDS:
        return f"kind {kind!r} is not one of {', '.join(CONDITION_KINDS)}"
    value = condition.get("value", _MISSING)
    if kind == "none":
        if value is not None:
            return "kind none requires value null"
    elif kind == "class_count":
        if isinstance(value, bool) or not (value == 1 or value == "multiple"):
            return "kind class_count requires value 1 or \"multiple\""
    elif kind == "compound":
        if not isinstance(value, list) or not value:
            return "kind compound requires a non-empty value list of conditions"
        for part in value:
            detail = _condition_error(part)
            if detail:
                return f"compound part invalid: {detail}"
            if isinstance(part, dict) and part.get("kind") == "compound":
                return "compound parts must not nest"
    else:
        if not isinstance(value, bool):
            return f"kind {kind} requires a boolean value"
    return None


def _heading_only(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    return len(stripped) <= 64 and bool(_HEADING_PREFIX.match(stripped))


# ---------------------------------------------------------------------------
# Deterministic validation
# ---------------------------------------------------------------------------

def validate_parsed_guide(source: GuideSource, parsed: dict) -> dict:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    paragraph_count = len(source.paragraphs)
    valid_indices = set(range(paragraph_count))
    normalized = _normalized_source(source)
    covered: set[int] = set()
    operations_by_kind = {kind: 0 for kind in OPERATIONS}
    conditions_by_kind = {kind: 0 for kind in CONDITION_KINDS}
    groups: list[Any] = []
    if isinstance(parsed, dict) and isinstance(parsed.get("groups"), list):
        groups = parsed["groups"]
    else:
        errors.append(_issue("GUIDE_GROUP_INVALID", "", "parsed document has no groups array"))
    seen_rule_ids: dict[str, int] = {}
    for position, group in enumerate(groups):
        expected_id = f"G{position + 1:02d}"
        if not isinstance(group, dict):
            errors.append(_issue("GUIDE_GROUP_INVALID", expected_id, f"group #{position} is not an object"))
            continue
        rule_id = group.get("rule_id")
        if not isinstance(rule_id, str) or not re.fullmatch(r"G\d{2}", rule_id):
            errors.append(_issue("GUIDE_RULE_ID_INVALID", expected_id, f"rule_id {rule_id!r} is not Gnn"))
            rule_id = expected_id
        elif rule_id in seen_rule_ids:
            errors.append(_issue("GUIDE_RULE_ID_INVALID", rule_id,
                                 f"rule_id duplicated (first at group #{seen_rule_ids[rule_id]})"))
        elif rule_id != expected_id:
            errors.append(_issue("GUIDE_RULE_ID_INVALID", rule_id,
                                 f"rule_id {rule_id} is not sequential; expected {expected_id}"))
        seen_rule_ids.setdefault(rule_id, position)
        for field in ("title", "requirement"):
            value = group.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, f"{field} must be a non-empty string"))
        section_hint = group.get("section_hint")
        if not isinstance(section_hint, str):
            errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, "section_hint must be a string"))
        elif not section_hint.strip():
            warnings.append(_issue("GUIDE_SECTION_HINT_EMPTY", rule_id, "section_hint is empty"))
        for field in ("old_text_variants", "slot_tokens", "references"):
            if _string_list(group.get(field)) is None:
                errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, f"{field} must be a list of strings"))
        if not isinstance(group.get("class_substitution"), bool):
            errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, "class_substitution must be a boolean"))
        operations = group.get("operations")
        if not isinstance(operations, list) or not operations:
            errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, "operations must be a non-empty list"))
            operations = []
        new_texts: list[str] = []
        for op_index, operation in enumerate(operations):
            label = f"operations[{op_index}]"
            if not isinstance(operation, dict):
                errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, f"{label} is not an object"))
                continue
            kind = operation.get("op")
            if kind not in OPERATIONS:
                errors.append(_issue("GUIDE_GROUP_INVALID", rule_id,
                                     f"{label}.op {kind!r} is not append/replace/delete/noop"))
                continue
            operations_by_kind[kind] += 1
            required = {"append": ("new_text",), "replace": ("old_text", "new_text"),
                        "delete": ("old_text",), "noop": ("text",)}[kind]
            for field in required:
                value = operation.get(field)
                if not isinstance(value, str) or not value.strip():
                    errors.append(_issue("GUIDE_GROUP_INVALID", rule_id,
                                         f"{label}.{field} must be a non-empty string"))
                elif not _verbatim(value, normalized):
                    errors.append(_issue("GUIDE_TEXT_NOT_VERBATIM", rule_id,
                                         f"{label}.{field} is not a verbatim guide substring: {_clip(value)}"))
                if field == "new_text" and isinstance(value, str):
                    new_texts.append(value)
            condition_error = _condition_error(operation.get("condition"))
            if condition_error:
                errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, f"{label}.condition {condition_error}"))
            else:
                conditions_by_kind[operation["condition"]["kind"]] += 1
        joined_new_text = "".join(_compact(text) for text in new_texts)
        for token in _string_list(group.get("slot_tokens")) or []:
            if not token.strip():
                errors.append(_issue("GUIDE_GROUP_INVALID", rule_id, "slot_tokens contains an empty token"))
            elif _compact(token) not in joined_new_text:
                errors.append(_issue("GUIDE_SLOT_NOT_IN_TEXT", rule_id,
                                     f"slot token {_clip(token)} does not occur in any new_text"))
        indices = group.get("source_paragraphs")
        if not isinstance(indices, list) or not indices:
            errors.append(_issue("GUIDE_PARAGRAPH_RANGE_INVALID", rule_id,
                                 "source_paragraphs must be a non-empty list"))
        else:
            bad = [value for value in indices
                   if not isinstance(value, int) or isinstance(value, bool) or value not in valid_indices]
            if bad:
                errors.append(_issue("GUIDE_PARAGRAPH_RANGE_INVALID", rule_id,
                                     f"source_paragraphs outside 0..{paragraph_count - 1}: {_clip(str(bad))}"))
            else:
                covered.update(indices)
                if sorted(set(indices)) != indices:
                    warnings.append(_issue("GUIDE_PARAGRAPH_ORDER", rule_id,
                                           "source_paragraphs is not sorted and unique"))
    coverage_gaps = [paragraph.index for paragraph in source.paragraphs
                     if paragraph.index not in covered and not _heading_only(paragraph.text)]
    stats = {
        "paragraphs": paragraph_count,
        "groups": len(groups),
        "operations": sum(operations_by_kind.values()),
        "operations_by_kind": operations_by_kind,
        "conditions_by_kind": conditions_by_kind,
        "covered_paragraphs": len(covered),
        "coverage_gaps": len(coverage_gaps),
        "red_paragraphs": sum(1 for paragraph in source.paragraphs if paragraph.emphasis == "red"),
        "bold_paragraphs": sum(1 for paragraph in source.paragraphs if paragraph.emphasis == "bold"),
        "errors": len(errors),
        "warnings": len(warnings),
    }
    return {"errors": errors, "warnings": warnings, "coverage_gaps": coverage_gaps, "stats": stats}


# ---------------------------------------------------------------------------
# Model instructions and JSON schemas
# ---------------------------------------------------------------------------

_PARSE_INSTRUCTION = (
    "Read the complete guide in [GUIDE_TEXT] before answering; the leading [n] markers are guide paragraph "
    "indices, not part of the text. Return one group per distinct business requirement of the guide, in "
    "document order. rule_id is sequential: G01, G02, ... . title copies the guide's own group heading. "
    "section_hint names the business domain, one of 释义, 基金的基本情况, 基金份额的申购与赎回, "
    "基金费用与税收, 基金的收益与分配, 基金财产的清算. requirement is a faithful natural-language "
    "description of what must change; it never adds policy the guide does not state. operations contains one "
    "or more executable operations: op append needs new_text; op replace needs old_text and new_text; op "
    "delete needs old_text; op noop with a text field is only for a guide branch that explicitly requires no "
    "change. Every new_text, old_text and delete text must be copied verbatim from the guide: "
    "no paraphrase, no added or removed characters or punctuation, and no merging of text from unrelated "
    "paragraphs; a multi-paragraph append may join contiguous guide paragraphs by concatenating them with "
    "nothing between them. old_text_variants lists the guide's reference old texts for locating and may be "
    "empty. slot_tokens lists the class tokens inside new_text that must later be instantiated from the "
    "product's actual share classes (for example A类基金份额, C类基金份额) and may be empty. "
    "class_substitution is true when the guide's share-class substitution rule applies to this group's "
    "new_text. references lists guide-internal references such as 同前述说明. source_paragraphs lists every "
    "guide paragraph index the group derives from, including its heading and all of its text. Every "
    "operation carries a condition object: kind none with value null; kind class_count with value 1 or "
    "\"multiple\" (single vs multiple share classes); kind has_service_fee with a boolean value; kind "
    "is_floating_fee with a boolean value. Keep the guide's conditions faithful, including mutually "
    "exclusive branches; never collapse two branches into one or invent a branch. Put ambiguity notes in "
    "notes. Keep requirement to one or two sentences and notes to a brief phrase, using an empty string when "
    "nothing is ambiguous; old_text_variants copies only the guide sentences that locate the target, not whole "
    "paragraphs when a shorter contiguous sentence exists. The 15-group human reading of this guide is a "
    "reference only: derive the groups from the source itself."
)

_PARSE_REPAIR_INSTRUCTION = (
    "The previous answer failed validation. Re-read the guide and return the complete corrected JSON "
    "document with the same schema. [REPAIR_CONTEXT] lists the deterministic validation errors and the "
    "independent verifier findings with their evidence. Fix every listed error; keep the groups that were "
    "already correct."
)

_VERIFY_INSTRUCTION = (
    "Read the guide in [GUIDE_TEXT] independently before answering; the leading [n] markers are guide "
    "paragraph indices. [PARSED_GUIDE_JSON] is a candidate parse to be checked, never a source of truth. "
    "Report only real mismatches between the candidate and the guide, with a verbatim evidence_quote copied "
    "from the guide and the paragraph indices it comes from. Check explicitly: (a) every distinct business "
    "requirement of the guide has a group and no group invents a requirement; (b) every operation and "
    "condition is faithful, including mutually exclusive branches such as single vs multiple share classes, "
    "products with a sales service fee and floating management fee products; (c) every new_text, old_text "
    "and delete text is copied verbatim from the guide; (d) guide-internal references such as 同前述说明 are "
    "resolved rather than left dangling; (e) genuinely ambiguous branch wording is flagged instead of "
    "silently guessed. kind is one of missing_group, wrong_condition, wrong_text, wrong_operation, "
    "missing_reference, ambiguous_branch. coverage_explanation states how the guide's paragraphs are covered "
    "by the candidate groups and which paragraphs no group uses. Return an empty findings list when the "
    "candidate is faithful."
)

_CONDITION_SCHEMA = {
    "type": "object",
    "required": ["kind", "value"],
    "properties": {
        "kind": {"enum": list(CONDITION_KINDS)},
        "value": {"anyOf": [{"type": "null"}, {"type": "boolean"},
                            {"type": "integer", "enum": [1]},
                            {"type": "string", "enum": ["multiple"]},
                            {"type": "array", "items": {"type": "object"}}]},
    },
}

_OPERATION_SCHEMA = {
    "type": "object",
    "required": ["op", "condition"],
    "properties": {
        "op": {"enum": list(OPERATIONS)},
        "old_text": {"type": "string"},
        "new_text": {"type": "string"},
        "text": {"type": "string"},
        "condition": _CONDITION_SCHEMA,
    },
}

_GROUP_SCHEMA = {
    "type": "object",
    "required": ["rule_id", "title", "section_hint", "requirement", "operations", "old_text_variants",
                 "slot_tokens", "class_substitution", "references", "source_paragraphs"],
    "properties": {
        "rule_id": {"type": "string", "minLength": 1},
        "title": {"type": "string", "minLength": 1},
        "section_hint": {"type": "string"},
        "requirement": {"type": "string", "minLength": 1},
        "operations": {"type": "array", "minItems": 1, "maxItems": 12, "items": _OPERATION_SCHEMA},
        "old_text_variants": {"type": "array", "maxItems": 12, "items": {"type": "string"}},
        "slot_tokens": {"type": "array", "maxItems": 12, "items": {"type": "string"}},
        "class_substitution": {"type": "boolean"},
        "references": {"type": "array", "maxItems": 8, "items": {"type": "string"}},
        "source_paragraphs": {"type": "array", "minItems": 1, "maxItems": 60,
                              "items": {"type": "integer", "minimum": 0}},
        "notes": {"type": "string"},
    },
}

_PARSE_SCHEMA = {
    "type": "object",
    "required": ["groups"],
    "properties": {
        "groups": {"type": "array", "minItems": 1, "maxItems": 40, "items": _GROUP_SCHEMA},
        "notes": {"type": "string"},
    },
}

_FINDING_SCHEMA = {
    "type": "object",
    "required": ["kind", "description", "evidence_quote", "paragraphs"],
    "properties": {
        "kind": {"enum": list(FINDING_KINDS)},
        "description": {"type": "string", "minLength": 1},
        "evidence_quote": {"type": "string"},
        "paragraphs": {"type": "array", "maxItems": 12, "items": {"type": "integer", "minimum": 0}},
        "rule_id": {"type": "string"},
    },
}

_VERIFY_SCHEMA = {
    "type": "object",
    "required": ["findings", "coverage_explanation"],
    "properties": {
        "findings": {"type": "array", "maxItems": 30, "items": _FINDING_SCHEMA},
        "coverage_explanation": {"type": "string"},
    },
}


# ---------------------------------------------------------------------------
# Model calls
# ---------------------------------------------------------------------------

def _model_call(gateway: Any, *, task_type: str, bounded_context: str, response_schema: dict,
                instruction: str, prompt_version: str) -> Any:
    try:
        return gateway.call(task_type=task_type, bounded_context=bounded_context,
                            response_schema=response_schema, instruction=instruction,
                            prompt_version=prompt_version)
    except ModelError as exc:
        raise GuideError(f"GUIDE_MODEL_FAILED:{exc.code}",
                         {"model_error": exc.code, "metrics": exc.metrics}) from exc


def _context_limit(gateway: Any) -> int:
    return max(1000, int(getattr(gateway, "max_context_chars", 12000)) - 200)


def _index_list(values: list[int], *, limit: int = 40) -> str:
    if not values:
        return "[]"
    if len(values) <= limit:
        return "[" + ", ".join(str(value) for value in values) + "]"
    return "[" + ", ".join(str(value) for value in values[:limit]) + f", ...+{len(values) - limit}]"


def _source_header(source: GuideSource) -> str:
    red = [paragraph.index for paragraph in source.paragraphs if paragraph.emphasis == "red"]
    bold = [paragraph.index for paragraph in source.paragraphs if paragraph.emphasis == "bold"]
    return "\n".join([
        "GUIDE_SOURCE",
        f"source_path_hint: {Path(source.path).name}",
        f"source_sha256: {source.source_sha256}",
        f"paragraph_count: {len(source.paragraphs)}",
        f"red_paragraphs: {_index_list(red)}",
        f"bold_paragraphs: {_index_list(bold)}",
    ])


def _parse_context(source: GuideSource, repair_context: str | None) -> str:
    parts = [_source_header(source), "", "GUIDE_TEXT", source.full_text]
    if repair_context:
        parts += ["", "REPAIR_CONTEXT", repair_context]
    return "\n".join(parts)


def _candidate_variants(parsed: dict):
    """Candidate parse only, then a trimmed copy, so a long parse still fits the context.

    The document's own provenance and previous validation/verification records are
    stripped: feeding earlier findings back to the independent verifier makes it
    echo them instead of re-reading the guide (FL-D039).
    """
    groups = parsed.get("groups") if isinstance(parsed, dict) else None
    yield {"groups": groups or []}
    trimmed = {"groups": copy.deepcopy(groups or [])}
    for group in trimmed["groups"]:
        if not isinstance(group, dict):
            continue
        group.pop("notes", None)
        requirement = group.get("requirement")
        if isinstance(requirement, str) and len(requirement) > 200:
            group["requirement"] = requirement[:200] + "…"
    yield trimmed


def _verify_context(source: GuideSource, parsed: dict, limit: int) -> str:
    base = [_source_header(source), "", "GUIDE_TEXT", source.full_text, "", "PARSED_GUIDE_JSON"]
    for candidate in _candidate_variants(parsed):
        body = json.dumps(candidate, ensure_ascii=False, separators=(",", ":"))
        context = "\n".join(base + [body])
        if len(context) <= limit:
            return context
    raise GuideError("GUIDE_CONTEXT_LIMIT",
                     {"limit": limit, "source_chars": len(source.full_text)})


# ---------------------------------------------------------------------------
# Parse, validate, verify
# ---------------------------------------------------------------------------

def parse_guide(source: GuideSource, gateway: Any, *, repair_context: str | None = None) -> dict:
    context = _parse_context(source, repair_context)
    limit = _context_limit(gateway)
    if len(context) > limit:
        raise GuideError("GUIDE_CONTEXT_LIMIT", {"context_chars": len(context), "limit": limit})
    instruction = _PARSE_INSTRUCTION if not repair_context \
        else _PARSE_INSTRUCTION + "\n" + _PARSE_REPAIR_INSTRUCTION
    result = _model_call(gateway, task_type="guide_parse", bounded_context=context,
                         response_schema=_PARSE_SCHEMA, instruction=instruction,
                         prompt_version=GUIDE_PARSE_PROMPT_VERSION)
    value = result.value
    if not isinstance(value, dict) or not isinstance(value.get("groups"), list):
        raise GuideError("GUIDE_PARSE_INVALID", {"reason": "response has no groups array"})
    return value


def _validate_findings(source: GuideSource, value: Any) -> tuple[list[dict[str, Any]], int]:
    normalized = _normalized_source(source)
    findings = value.get("findings") if isinstance(value, dict) else None
    if not isinstance(findings, list):
        return [], 0
    valid: list[dict[str, Any]] = []
    invalid = 0
    for finding in findings:
        if not isinstance(finding, dict):
            invalid += 1
            continue
        kind = finding.get("kind")
        quote = finding.get("evidence_quote")
        paragraphs = finding.get("paragraphs")
        if kind not in FINDING_KINDS or not isinstance(quote, str) or not _verbatim(quote, normalized):
            invalid += 1
            continue
        if not isinstance(paragraphs, list) or any(
                not isinstance(value, int) or isinstance(value, bool)
                or value < 0 or value >= len(source.paragraphs) for value in paragraphs):
            invalid += 1
            continue
        item = {"kind": kind, "description": str(finding.get("description") or ""),
                "evidence_quote": quote, "paragraphs": list(paragraphs)}
        if isinstance(finding.get("rule_id"), str) and finding["rule_id"].strip():
            item["rule_id"] = finding["rule_id"]
        valid.append(item)
    return valid, invalid


def verify_guide(source: GuideSource, parsed: dict, gateway: Any) -> dict:
    context = _verify_context(source, parsed, _context_limit(gateway))
    result = _model_call(gateway, task_type="guide_verify", bounded_context=context,
                         response_schema=_VERIFY_SCHEMA, instruction=_VERIFY_INSTRUCTION,
                         prompt_version=GUIDE_VERIFY_PROMPT_VERSION)
    value = result.value if isinstance(result.value, dict) else {}
    findings, invalid = _validate_findings(source, value)
    coverage = value.get("coverage_explanation")
    return {"findings": findings, "coverage_explanation": coverage if isinstance(coverage, str) else "",
            "invalid_findings": invalid}


def _render_repair_context(validation: dict, verification: dict) -> str:
    lines: list[str] = []
    errors = validation.get("errors") or []
    if errors:
        lines.append("DETERMINISTIC_VALIDATION_ERRORS")
        for error in errors[:40]:
            lines.append(f"- [{error.get('code')}] rule {error.get('rule_id') or '-'}: {error.get('detail')}")
    warnings = validation.get("warnings") or []
    if warnings:
        lines.append("DETERMINISTIC_VALIDATION_WARNINGS")
        for warning in warnings[:10]:
            lines.append(f"- [{warning.get('code')}] rule {warning.get('rule_id') or '-'}: {warning.get('detail')}")
    gaps = validation.get("coverage_gaps") or []
    if gaps:
        lines.append(f"UNCOVERED_PARAGRAPHS: {_index_list(list(gaps))}")
    findings = verification.get("findings") or []
    if findings:
        lines.append("INDEPENDENT_VERIFIER_FINDINGS")
        for finding in findings[:20]:
            lines.append(f"- [{finding.get('kind')}] paragraphs {finding.get('paragraphs')}: "
                         f"{finding.get('description')} | evidence: {_clip(str(finding.get('evidence_quote')), 120)}")
    if verification.get("invalid_findings"):
        lines.append(f"INVALID_EVIDENCE_FINDINGS_DROPPED: {verification['invalid_findings']}")
    return "\n".join(lines)


def _model_summary(gateway: Any, rounds: int) -> dict:
    events = [{key: event.get(key) for key in (
        "task_type", "prompt_version", "configured_model", "actual_model", "request_id", "latency_ms",
        "prompt_tokens", "completion_tokens", "total_tokens", "estimated_cost_usd", "http_status",
        "error_code", "reused_checkpoint")} for event in getattr(gateway, "events", [])]
    summary: dict[str, Any] = {"configured_model": getattr(gateway, "model", None),
                               "parse_rounds": rounds, "logical_calls": getattr(gateway, "calls", None),
                               "events": events}
    metrics = getattr(gateway, "metrics", None)
    if callable(metrics):
        try:
            snapshot = metrics()
        except Exception:
            snapshot = None
        if isinstance(snapshot, dict):
            summary["metrics"] = {key: snapshot.get(key) for key in (
                "logical_calls", "http_attempts", "checkpoint_reuses", "prompt_tokens", "completion_tokens",
                "total_tokens", "latency_ms", "rate_limit_count", "error_count", "estimated_cost_usd")}
    budget = getattr(gateway, "budget", None)
    if budget is not None and callable(getattr(budget, "snapshot", None)):
        try:
            summary["budget"] = budget.snapshot()
        except Exception:
            pass
    return summary


def build_guide_document(source: GuideSource, gateway: Any, *, max_repair_rounds: int = 2) -> dict:
    if max_repair_rounds < 0:
        raise GuideError("GUIDE_BUILD_ARGUMENT_INVALID", {"max_repair_rounds": max_repair_rounds})
    repair_context: str | None = None
    rounds = 0
    rounds_detail: list[dict[str, Any]] = []
    parsed: dict = {}
    validation: dict = {}
    verification: dict = {}
    clean = False
    while True:
        parsed = parse_guide(source, gateway, repair_context=repair_context)
        validation = validate_parsed_guide(source, parsed)
        verification = verify_guide(source, parsed, gateway)
        rounds += 1
        clean = not validation["errors"] and not verification["findings"]
        rounds_detail.append({
            "round": rounds,
            "repair_context_used": repair_context is not None,
            "errors": len(validation["errors"]),
            "warnings": len(validation["warnings"]),
            "coverage_gaps": len(validation["coverage_gaps"]),
            "findings": len(verification["findings"]),
            "invalid_findings": verification["invalid_findings"],
            "clean": clean,
        })
        if clean or rounds > max_repair_rounds:
            break
        repair_context = _render_repair_context(validation, verification)
    return {
        "schema_version": GUIDE_SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "source_sha256": source.source_sha256,
        "source_path_hint": Path(source.path).name,
        "prompt_versions": {"guide_parse": GUIDE_PARSE_PROMPT_VERSION,
                            "guide_verify": GUIDE_VERIFY_PROMPT_VERSION},
        "groups": parsed.get("groups", []),
        "notes": parsed.get("notes", ""),
        "validation": {
            "errors": validation["errors"],
            "warnings": validation["warnings"],
            "coverage_gaps": validation["coverage_gaps"],
            "verification": {"findings": verification["findings"],
                             "invalid_findings": verification["invalid_findings"],
                             "coverage_explanation": verification["coverage_explanation"]},
            "rounds": rounds,
            "rounds_detail": rounds_detail,
            "stats": validation["stats"],
            "clean": clean,
        },
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": _model_summary(gateway, rounds),
    }


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def guide_document_sha256(doc: dict) -> str:
    payload = {key: value for key, value in doc.items() if key not in {"built_at", "model"}}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def save_guide_document(doc: dict, path: str | Path) -> str:
    if not isinstance(doc, dict) or doc.get("schema_version") != GUIDE_SCHEMA_VERSION:
        raise GuideError("GUIDE_DOCUMENT_SCHEMA_UNSUPPORTED",
                         {"schema_version": doc.get("schema_version") if isinstance(doc, dict) else None})
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, target)
    except OSError as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise GuideError("GUIDE_DOCUMENT_UNWRITABLE",
                         {"path": str(target), "reason": type(exc).__name__}) from exc
    return str(target)


def load_guide_document(path: str | Path) -> dict:
    target = Path(path)
    try:
        doc = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise GuideError("GUIDE_DOCUMENT_UNREADABLE",
                         {"path": str(target), "reason": type(exc).__name__}) from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != GUIDE_SCHEMA_VERSION:
        raise GuideError("GUIDE_DOCUMENT_SCHEMA_UNSUPPORTED",
                         {"path": str(target),
                          "schema_version": doc.get("schema_version") if isinstance(doc, dict) else None})
    return doc
