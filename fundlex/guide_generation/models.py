"""Core data model for regulation-driven candidate guide generation.

The model is intentionally provider-neutral.  Every object that participates in
the evidence chain has a deterministic identifier, a canonical JSON form and a
SHA-256 digest so a later reader can prove that the persisted chain was not
edited between stages.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping


# ---------------------------------------------------------------------------
# Canonical serialisation and hashes
# ---------------------------------------------------------------------------

def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_text(canonical_json(value))


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_id(prefix: str, *parts: Any, length: int = 16) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return f"{prefix}-{sha256_text(raw)[:length]}"


_WS = re.compile(r"\s+")


def normalize_space(value: str) -> str:
    return _WS.sub("", value or "")


def compact_for_match(value: str) -> str:
    """Whitespace/punctuation-insensitive form used for quote containment.

    Chinese legal text frequently differs only by full-width punctuation or
    inserted line breaks.  Evidence matching must not fail for those harmless
    differences, but it must still fail for paraphrased or invented text.
    """
    return re.sub(r"[\s\u3000,，。;；:：、\.．!！?？\"'“”‘’（）()\[\]【】《》<>—\-_/]+", "", value or "")


def quote_in_text(quote: str, text: str) -> bool:
    needle = compact_for_match(quote)
    return bool(needle) and needle in compact_for_match(text)


# ---------------------------------------------------------------------------
# Regulation document
# ---------------------------------------------------------------------------

@dataclass
class SourceAnchor:
    part: str = "word/document.xml"
    block_index: int = 0
    page: int | None = None
    xml_path: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RegulationBlock:
    block_id: str
    ordinal: int
    type: str  # heading|paragraph|table
    text: str
    article_no: str = ""
    heading_level: int = 0
    page: int | None = None
    source_anchor: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RegulationDocument:
    document_id: str
    source_type: str
    source_sha256: str
    title: str
    blocks: list[RegulationBlock]
    filename: str = ""
    page_count: int = 0
    parser_version: str = ""
    created_at: str = field(default_factory=utc_now)
    document_sha256: str = ""

    def __post_init__(self) -> None:
        if not self.document_sha256:
            self.document_sha256 = sha256_json({
                "source_sha256": self.source_sha256,
                "source_type": self.source_type,
                "title": self.title,
                "blocks": [block.to_dict() for block in self.blocks],
            })

    def block_map(self) -> dict[str, RegulationBlock]:
        return {block.block_id: block for block in self.blocks}

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["blocks"] = [block.to_dict() for block in self.blocks]
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RegulationDocument":
        return cls(
            document_id=str(data.get("document_id") or ""),
            source_type=str(data.get("source_type") or ""),
            source_sha256=str(data.get("source_sha256") or ""),
            title=str(data.get("title") or ""),
            filename=str(data.get("filename") or ""),
            page_count=int(data.get("page_count") or 0),
            parser_version=str(data.get("parser_version") or ""),
            created_at=str(data.get("created_at") or utc_now()),
            document_sha256=str(data.get("document_sha256") or ""),
            blocks=[RegulationBlock(**item) for item in data.get("blocks") or []],
        )


# ---------------------------------------------------------------------------
# Policy requirements
# ---------------------------------------------------------------------------

DISPOSITIONS = (
    "modify_contract",
    "no_contract_change",
    "out_of_contract_scope",
    "uncertain",
    "needs_external_baseline",
)

NORM_TYPES = ("prohibition", "obligation", "permission", "definition", "transition", "other")


@dataclass
class PolicyRequirement:
    requirement_id: str
    source_block_ids: list[str]
    source_quote: str
    article: str
    norm_type: str
    subject: str
    object: str
    requirement: str
    conditions: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    applicable_scope: dict[str, Any] = field(default_factory=dict)
    effective_time: str = ""
    candidate_contract_domains: list[str] = field(default_factory=list)
    external_dependencies: list[str] = field(default_factory=list)
    disposition: str = "uncertain"
    disposition_reason: str = ""
    discovery_pass: str = "A"
    adjudication_status: str = "baseline"
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.disposition not in DISPOSITIONS:
            self.disposition = "uncertain"
        if self.norm_type not in NORM_TYPES:
            self.norm_type = "other"

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.update(self.payload or {})
        data["requirement_id"] = self.requirement_id
        data["disposition"] = self.disposition
        data["adjudication_status"] = self.adjudication_status
        data["discovery_pass"] = self.discovery_pass
        data["payload"] = self.payload
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "PolicyRequirement":
        known = {name for name in cls.__dataclass_fields__}
        values = {key: data[key] for key in data if key in known and key != "payload"}
        values.setdefault("requirement_id", str(data.get("requirement_id") or ""))
        values.setdefault("source_block_ids", list(data.get("source_block_ids") or []))
        values.setdefault("source_quote", str(data.get("source_quote") or ""))
        values.setdefault("article", str(data.get("article") or ""))
        values.setdefault("norm_type", str(data.get("norm_type") or "other"))
        values.setdefault("subject", str(data.get("subject") or ""))
        values.setdefault("object", str(data.get("object") or ""))
        values.setdefault("requirement", str(data.get("requirement") or ""))
        values.setdefault("disposition", str(data.get("disposition") or "uncertain"))
        values["payload"] = dict(data)
        return cls(**values)


# ---------------------------------------------------------------------------
# Corpus objects
# ---------------------------------------------------------------------------

@dataclass
class ContractVersion:
    contract_version_id: str
    contract_id: str
    fund_identity: str
    display_name: str
    version_date: str = ""
    previous_version_id: str = ""
    latest_known_version: bool = False
    version_relation: str = "resolved"  # resolved|unresolved
    source_sha256: str = ""
    source_path: str = ""
    source_size: int = 0
    parser_version: str = ""
    status: str = "pending"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ContractVersion":
        known = set(cls.__dataclass_fields__)
        return cls(**{key: data[key] for key in data if key in known})


@dataclass
class ClauseUnit:
    clause_id: str
    contract_version_id: str
    section_path: list[str]
    paragraph_start: int
    paragraph_end: int
    text: str
    before_context: str = ""
    after_context: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    source_anchor: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CorpusSnapshot:
    snapshot_id: str
    contract_version_ids: list[str]
    contract_hashes: dict[str, str]
    latest_version_ids: list[str]
    historical_version_ids: list[str]
    parser_version: str
    index_version: str
    created_at: str = field(default_factory=utc_now)
    counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Impact and guide objects
# ---------------------------------------------------------------------------

@dataclass
class ImpactCandidate:
    impact_id: str
    requirement_id: str
    contract_version_id: str
    clause_ids: list[str]
    source_text: str
    context: str
    impact_status: str  # definite|possible|unlikely
    impact_dimensions: list[str] = field(default_factory=list)
    impact_reason: str = ""
    discovery_sources: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    disposition: str = ""
    disposition_reason: str = ""
    guide_item_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.impact_status not in {"definite", "possible", "unlikely"}:
            self.impact_status = "possible"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LocalGuideCandidate:
    local_id: str
    impact_ids: list[str]
    requirement_ids: list[str]
    needs_modification: str  # yes|no|uncertain
    section: str = ""
    business_goal: str = ""
    semantic_changes: list[str] = field(default_factory=list)
    applicability: str = ""
    conditions: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    old_text_patterns: list[str] = field(default_factory=list)
    new_text: str = ""
    new_text_origin: str = "model_drafted"
    notes: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GuideItem:
    guide_item_id: str
    requirement_ids: list[str]
    impact_ids: list[str]
    clause_family_ids: list[str]
    section: str
    title: str
    business_requirement: str
    instruction: str
    applicability: str = ""
    conditions: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    old_text_patterns: list[str] = field(default_factory=list)
    new_text: str = ""
    new_text_origin: str = "model_drafted"
    evidence_ids: list[str] = field(default_factory=list)
    status: str = "candidate"
    version: int = 1
    quality_status: str = "not_run"
    coverage_status: str = "not_run"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.new_text_origin not in {"regulation_verbatim", "model_drafted", "contract_pattern_adapted"}:
            self.new_text_origin = "model_drafted"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Small helpers used by many stages
# ---------------------------------------------------------------------------

def unique(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def merge_strings(*groups: Iterable[str]) -> list[str]:
    return unique(item.strip() for group in groups for item in group if item and item.strip())


def count_by(items: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items()))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
