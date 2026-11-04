"""Guide DOCX extraction and guide document persistence helpers.

The old business pipeline (slot schema, fixed condition/section enums,
verbatim-copy validation, independent verification rounds and the
certification repair loop) has been removed; ``build_guide_document`` is now a
signature-compatible adapter over the direct-through atomic card parser in
:mod:`fundlex.guide_cards` (schema ``guide_card_v1``).

Kept for other lines until their migration completes: the pure OOXML
extraction (``extract_guide_source``), document hash/persist helpers, and the
legacy ``validate_runtime_guide``/``certify_guide_document`` runtime contract
that still serves frozen ``guide-rules-v1`` documents (including the built-in
guide).  New code must not route ``guide_card_v1`` documents through the
legacy runtime validator; use ``guide_cards.validate_card_document``.
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
from pathlib import Path
from typing import Any

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W}
Q = lambda local: f"{{{W}}}{local}"

GUIDE_SCHEMA_VERSION = "guide-rules-v1"

# Legacy operation/condition vocabularies kept only for validate_runtime_guide
# (frozen guide-rules-v1 documents).  New card documents use
# guide_cards.CARD_ACTIONS and free natural-language conditions.
CONDITION_KINDS = ("none", "class_count", "has_service_fee", "is_floating_fee", "compound")
OPERATIONS = ("append", "replace", "delete", "noop")
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
# Direct-through adapter
# ---------------------------------------------------------------------------

def build_guide_document(source: GuideSource, gateway: Any, *, max_repair_rounds: int = 2) -> dict:
    """Parse a guide DOCX into a guide_card_v1 atomic-rule-card package.

    Signature-compatible adapter over fundlex.guide_cards.build_guide_card_document.
    The old slot/enum/verbatim schema, independent verification rounds and the
    certification repair loop are gone; ``max_repair_rounds`` is accepted for
    call-site compatibility and has no effect.  Zero executable cards raise
    ``GuideError("GUIDE_NO_EXECUTABLE_CARDS")``; per-segment failures are
    recorded in ``unparsed_segments`` without failing the rest of the guide.
    """
    if max_repair_rounds < 0:
        raise GuideError("GUIDE_BUILD_ARGUMENT_INVALID", {"max_repair_rounds": max_repair_rounds})
    from .guide_cards import build_guide_card_document
    return build_guide_card_document(source, gateway)


# ---------------------------------------------------------------------------
# 历史展示标签(纯常量,不含任何认证/校验逻辑)
# 旧 guide-rules-v1 文档的发现/条件中文名,仅服务历史只读呈现;直通卡包不产出。
# ---------------------------------------------------------------------------
CONDITION_KINDS = ("none", "class_count", "has_service_fee", "is_floating_fee", "compound")
OPERATIONS = ("append", "replace", "delete", "noop")
CONDITION_KIND_LABELS = {"none": "无条件", "class_count": "份额类别数量",
                         "has_service_fee": "是否收取销售服务费",
                         "is_floating_fee": "是否浮动管理费", "compound": "组合条件"}
FINDING_KINDS = ("missing_group", "wrong_condition", "wrong_text", "wrong_operation",
                 "missing_reference", "ambiguous_branch")
FINDING_KIND_LABELS = {"missing_group": "规则缺失", "wrong_condition": "适用条件不符",
                       "wrong_text": "条款文本不符", "wrong_operation": "修改操作不符",
                       "missing_reference": "引用未解析", "ambiguous_branch": "分支表述歧义"}

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def guide_document_sha256(doc: dict) -> str:
    # Certification and display hashes are envelopes, never part of their own digest.
    payload = {key: value for key, value in doc.items()
               if key not in {"built_at", "model", "document_sha256", "certification"}}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def finding_id(finding: dict) -> str:
    payload = {key: value for key, value in finding.items() if key != "finding_id"}
    return "finding-" + hashlib.sha256(json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()[:24]


def validate_runtime_guide(doc: dict, *, approved_source_sha256: str | None = None,
                           approved_document_sha256: str | None = None) -> dict:
    """Validate the actual payload against its approved envelope before model work.

    A parsed/clean flag is not certification. Finding dispositions bind both immutable
    source and payload digests. No runtime path creates or upgrades an approval.
    """
    failures: list[str] = []
    if not isinstance(doc, dict):
        raise GuideError("GUIDE_NOT_CERTIFIED", {"failures": ["document_invalid"]})
    source_sha = str(doc.get("source_sha256") or "")
    document_sha = guide_document_sha256(doc)
    certificate = doc.get("certification") or {}
    if not isinstance(certificate, dict):
        certificate = {}
    if doc.get("schema_version") != GUIDE_SCHEMA_VERSION:
        failures.append("schema_unsupported")
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        failures.append("source_sha_invalid")
    if certificate.get("approved") is not True:
        failures.append("approval_missing")
    for key, actual, expected in (
            ("source_sha256", source_sha, approved_source_sha256),
            ("guide_document_sha256", document_sha, approved_document_sha256)):
        if certificate.get(key) != actual or (expected is not None and expected != actual):
            failures.append(key + "_mismatch")
    if doc.get("document_sha256") not in (None, document_sha):
        failures.append("stored_document_sha_mismatch")
    validation = doc.get("validation")
    if not isinstance(validation, dict):
        failures.append("validation_missing")
        validation = {}
    if validation.get("errors") != []:
        failures.append("deterministic_errors")
    if validation.get("coverage_gaps") != []:
        failures.append("coverage_gaps")
    verification = validation.get("verification") or {}
    if not isinstance(verification, dict) or verification.get("invalid_findings") != 0:
        failures.append("invalid_verifier_findings")
        verification = verification if isinstance(verification, dict) else {}
    findings = verification.get("findings")
    if not isinstance(findings, list):
        failures.append("verification_missing")
        findings = []
    dispositions = certificate.get("finding_dispositions") or []
    disposition_map = {item.get("finding_id"): item for item in dispositions
                       if isinstance(item, dict)}
    if len(disposition_map) != len(dispositions):
        failures.append("duplicate_disposition")
    for finding in findings:
        if not isinstance(finding, dict):
            failures.append("finding_invalid")
            continue
        stable_id = finding_id(finding)
        decision = disposition_map.get(stable_id, {})
        if finding.get("finding_id") != stable_id or decision.get("approved") is not True \
                or not decision.get("disposition") or not decision.get("reason") \
                or decision.get("source_sha256") != source_sha \
                or decision.get("guide_document_sha256") != document_sha:
            failures.append("finding_uncertified:" + stable_id)
    groups = doc.get("groups") or []
    if not isinstance(groups, list) or not groups or certificate.get("rule_count") != len(groups):
        failures.append("rule_count_mismatch")
    seen_rules: set[str] = set()
    seen_operations: set[str] = set()
    operation_count = 0
    for rule in groups if isinstance(groups, list) else []:
        if not isinstance(rule, dict):
            failures.append("rule_invalid")
            continue
        rule_id = str(rule.get("rule_id") or "")
        if not rule_id or rule_id in seen_rules:
            failures.append("rule_id_duplicate_or_missing")
        seen_rules.add(rule_id)
        operations = rule.get("operations") or []
        if not operations:
            failures.append("operations_missing:" + rule_id)
        one_of: dict[str, list[dict]] = {}
        for index, operation in enumerate(operations):
            operation_count += 1
            if not isinstance(operation, dict):
                failures.append("operation_invalid")
                continue
            operation_id = operation.get("operation_id")
            if not isinstance(operation_id, str) or not operation_id.strip() \
                    or operation_id.split(":", 1)[0].strip() != rule_id \
                    or operation_id in seen_operations:
                failures.append("operation_id_invalid_or_duplicate")
            seen_operations.add(str(operation_id))
            if operation.get("op") not in OPERATIONS or _condition_error(operation.get("condition")):
                failures.append("operation_compile_invalid:" + str(operation_id))
            kind = operation.get("group_kind")
            if kind not in {"INDEPENDENT", "ALL_OF", "ONE_OF", "BRANCH"}:
                failures.append("group_semantics_missing:" + str(operation_id))
            group = operation.get("one_of_group")
            if (kind == "ONE_OF") != bool(group):
                failures.append("one_of_semantics_invalid:" + str(operation_id))
            if group:
                one_of.setdefault(str(group), []).append(operation)
        for name, alternatives in one_of.items():
            if len(alternatives) < 2 or any(item.get("op") != "replace" for item in alternatives) \
                    or len({branch_key_for_guide(item.get("condition"))
                            for item in alternatives}) != 1 \
                    or len({item.get("new_text") for item in alternatives}) != 1:
                failures.append("one_of_not_historical_alternatives:" + name)
    if certificate.get("operation_count") != operation_count:
        failures.append("operation_count_mismatch")
    if not failures:
        try:
            from .obligations import compile_obligations
            compiled = compile_obligations(doc)
            if len(compiled.records) != operation_count:
                failures.append("operation_compile_count_mismatch")
        except (ValueError, TypeError, KeyError, IndexError):
            failures.append("operation_compile_failed")
    if failures:
        raise GuideError("GUIDE_NOT_CERTIFIED", {"failures": sorted(set(failures))})
    return {"state": "CERTIFIED", "source_sha256": source_sha,
            "guide_document_sha256": document_sha, "rule_count": len(groups),
            "operation_count": operation_count}


def branch_key_for_guide(condition: Any) -> str:
    return json.dumps(condition, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bind_operation_identities(doc: dict) -> None:
    """Assign stable indices; never infer ONE_OF from text similarity."""
    for rule in doc.get("groups") or []:
        for index, operation in enumerate(rule.get("operations") or []):
            if not operation.get("operation_id"):
                operation["operation_id"] = f"{rule['rule_id']}:{index}"
                # Keep compatibility with parsed legacy documents explicit.  A
                # generated positional id is not a publisher-supplied Registry
                # contract; routed execution still remains legacy-compatible for
                # known built-in rules, while unknown rules fail closed.
                operation["operation_id_generated"] = True


def certify_guide_document(doc: dict, *, source_sha256: str,
                           finding_dispositions: list[dict] | None = None) -> dict:
    """Bind a completed source review to its exact payload, then validate it.

    Findings require pre-existing approved dispositions; this function never approves
    findings or repairs validation data. Call only after independent source review.
    """
    certificate = {
        "approved": True, "source_sha256": source_sha256,
        "guide_document_sha256": guide_document_sha256(doc),
        "rule_count": len(doc.get("groups") or []),
        "operation_count": sum(len(rule.get("operations") or [])
                               for rule in doc.get("groups") or []),
        "finding_dispositions": copy.deepcopy(finding_dispositions or []),
    }
    candidate = {**doc, "certification": certificate}
    candidate["document_sha256"] = certificate["guide_document_sha256"]
    validate_runtime_guide(candidate, approved_source_sha256=source_sha256)
    return candidate


def _supported_document_schemas() -> set[str]:
    from .guide_cards import CARD_SCHEMA_VERSION
    return {GUIDE_SCHEMA_VERSION, CARD_SCHEMA_VERSION}


def save_guide_document(doc: dict, path: str | Path) -> str:
    if not isinstance(doc, dict) or doc.get("schema_version") not in _supported_document_schemas():
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
    if not isinstance(doc, dict) or doc.get("schema_version") not in _supported_document_schemas():
        raise GuideError("GUIDE_DOCUMENT_SCHEMA_UNSUPPORTED",
                         {"path": str(target),
                          "schema_version": doc.get("schema_version") if isinstance(doc, dict) else None})
    return doc
