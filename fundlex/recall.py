"""Recall-first revision engine core.

Code owns structure, addresses, source verification and execution; the model owns
business judgement: fee facts, rule-to-subsection mapping, target inventory and the
composition of replacement text for contract-specific variants. Every model quote is
re-resolved against the real document before it is used.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

from .docx import BARRIER, DocumentInspection, ParagraphSpan, TextSegment
from .model import ModelError
from .recall_prompts import (
    AUDIT_INSTRUCTION, AUDIT_PROMPT_VERSION, AUDIT_SCHEMA,
    COMPOSE_DELETE_INSTRUCTION, COMPOSE_INSTRUCTION, COMPOSE_PROMPT_VERSION, COMPOSE_SCHEMA,
    FACTS_INSTRUCTION, FACTS_PROMPT_VERSION, FACTS_SCHEMA,
    INVENTORY_INSTRUCTION, INVENTORY_PROMPT_VERSION, INVENTORY_SCHEMA,
    PROMPT_VERSIONS, SCOPE_INSTRUCTION, SCOPE_PROMPT_VERSION, SCOPE_SCHEMA,
    SWEEP_INSTRUCTION, SWEEP_PROMPT_VERSION, SWEEP_SCHEMA,
)

ENGINE_ID = "recall_first"
ENGINE_VERSION = "0.1.0"
SCHEMA_VERSION = "3"
BOUNDARY_POLICY = "sentence-span-preserve-v1"
# Character-level similarity required before a reference text counts as a wording
# variant of the contract's own text (FL-D047). Deliberately conservative: the
# negation in "不收取销售服务费" against "费用收取不同" must stay far below it.
FUZZY_MATCH_THRESHOLD = 0.84
# A wording variant only counts as the same clause at a near-verbatim ratio, and
# only for references long enough that the ratio is meaningful.
VARIANT_MATCH_RATIO = 0.95
VARIANT_MIN_CHARS = 24
SURVEY_ZONES = frozenset({"body", "summary"})
# Transport/budget stops that must pause the whole run instead of failing one target.
_STOP_CODES = frozenset({"MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED",
                         "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_CIRCUIT_OPEN",
                         "MODEL_LEDGER_UNAVAILABLE", "MODEL_CONFIG_MISSING",
                         "MODEL_HTTP_ERROR", "MODEL_RETRY_EXHAUSTED"})
# Only long reference texts may be matched as wording variants, and only at a
# near-verbatim ratio (FL-D047).
SURVEY_FUZZY_THRESHOLD = 0.9


class RecallError(RuntimeError):
    def __init__(self, code: str, detail: dict | None = None):
        self.code, self.detail = code, detail or {}
        super().__init__(code)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def display_text(span_text: str) -> tuple[str, list[int]]:
    """Strip read-only barrier markers, keeping a map back to raw offsets."""
    chars: list[str] = []
    index: list[int] = []
    for position, char in enumerate(span_text):
        if char == BARRIER:
            continue
        chars.append(char)
        index.append(position)
    return "".join(chars), index


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def compact_offsets(span_text: str) -> tuple[str, list[int]]:
    """Whitespace-free text plus a map from compact offsets back to raw offsets.

    ``find_old_text_all`` reports offsets into the whitespace-free text while
    ``Target.start``/``Target.end`` are raw document offsets consumed verbatim by the
    planner. Converting one into the other requires knowing exactly which raw
    characters the whitespace removal dropped; deriving it from ``display_text``'s
    index map (which keeps whitespace) silently shifts every offset after the first
    space (FL-D052).
    """
    chars: list[str] = []
    index: list[int] = []
    for position, char in enumerate(span_text):
        if char == BARRIER or char.isspace():
            continue
        chars.append(char)
        index.append(position)
    return "".join(chars), index


def _nfkc_compact(value: str) -> str:
    import unicodedata
    return _compact(unicodedata.normalize("NFKC", value))


def _raw_to_compact(compact_map: list[int], raw: int) -> int:
    """Inverse of ``compact_map``: the compact offset for a raw document offset.

    ``compact_map[i]`` is the raw offset of compact character ``i``, so the number of
    compact characters before ``raw`` is the count of mapped positions below it.
    """
    import bisect
    return bisect.bisect_left(compact_map, raw)


def find_normalized(haystack: str, needle: str) -> tuple[int, int] | None:
    """Locate ``needle`` in ``haystack`` tolerating whitespace and width differences.

    Returns cleaned-text offsets (half open) or None.
    """
    if not needle:
        return None
    position = haystack.find(needle)
    if position >= 0:
        return position, position + len(needle)
    compact_positions = [i for i, char in enumerate(haystack) if not char.isspace()]
    compact = "".join(haystack[i] for i in compact_positions)
    target = _compact(needle)
    if not target:
        return None
    position = compact.find(target)
    if position >= 0:
        start = compact_positions[position]
        end = compact_positions[position + len(target) - 1] + 1
        return start, end
    nfkc_positions = [i for i, char in enumerate(haystack) if not char.isspace()]
    nfkc = _nfkc_compact(haystack)
    position = nfkc.find(_nfkc_compact(needle))
    if position >= 0:
        start = nfkc_positions[position]
        end = nfkc_positions[position + len(_nfkc_compact(needle)) - 1] + 1
        return start, end
    return None


def _character_ngrams(value: str, size: int) -> set[str]:
    if len(value) < size:
        return {value} if value else set()
    return {value[index:index + size] for index in range(len(value) - size + 1)}


def find_fuzzy(cleaned: str, needle: str, *, threshold: float = FUZZY_MATCH_THRESHOLD
               ) -> tuple[int, int, float] | None:
    """Locate ``needle`` in whitespace-free ``cleaned`` text despite small wording edits.

    Used only for bounded legal-text variants ("由于基金费用的不同" against the
    guide's reference wording). Candidate positions are limited to windows sharing
    at least one character bigram with the reference, and the best window must still
    reach a high character-level ratio, otherwise nothing is returned. Every match is
    re-checked against the real document text before it is used.
    """
    target = _compact(needle)
    size = len(target)
    if size < 8 or len(cleaned) < 8:
        return None
    from difflib import SequenceMatcher
    # Candidate starts come from the reference's own n-gram prefixes: a rewritten
    # variant keeps the sentence opening, so its first characters still appear
    # verbatim. This keeps the scan linear per paragraph (FL-D047).
    mount = target[:4]
    candidates: set[int] = set()
    offset = 0
    position = cleaned.find(mount, offset)
    while position >= 0:
        for shift in range(0, 4):
            if position - shift >= 0:
                candidates.add(position - shift)
        offset = position + 1
        position = cleaned.find(mount, offset)
    if not candidates:
        return None
    best: tuple[int, int, float] | None = None
    for start in sorted(candidates):
        window = cleaned[start:start + size]
        if len(window) < size:
            window = cleaned[start:]
        ratio = SequenceMatcher(None, target, window).ratio()
        if ratio < threshold or len(window) < 0.8 * size:
            continue
        end = min(len(cleaned), start + size)
        if best is None or ratio > best[2]:
            best = (start, end, ratio)
    return best


def fuzzy_span(span_text: str, needle: str, *,
               threshold: float = FUZZY_MATCH_THRESHOLD) -> tuple[int, int, float] | None:
    """Fuzzy-locate ``needle`` in one paragraph, returning raw offsets and a ratio."""
    cleaned, index_map = display_text(span_text)
    located = find_fuzzy(cleaned, needle, threshold=threshold)
    if located is None:
        return None
    start_clean, end_clean, ratio = located
    return index_map[start_clean], index_map[end_clean - 1] + 1, ratio


def fuzzy_span_clause(span_text: str, needle: str, *,
                      threshold: float = FUZZY_MATCH_THRESHOLD) -> tuple[int, int, float] | None:
    """``fuzzy_span`` snapped to a sentence boundary.

    ``find_fuzzy`` matches the best character window, so a reference ending in "。" can
    stop a couple of characters short of the paragraph's own full stop ("…比例进行分"
    leaving "配。"). Replacing that window keeps the leftover stub and produces
    "…（如有）。配。" (FL-D079). When the needle itself ends at sentence punctuation, the
    returned span is extended to (or trimmed back to) the paragraph's matching stop so the
    kept suffix starts a fresh sentence.
    """
    span = fuzzy_span(span_text, needle, threshold=threshold)
    if span is None:
        return None
    start_raw, end_raw, ratio = span
    cleaned_needle = _compact(needle)
    if not cleaned_needle or cleaned_needle[-1] not in "。！？；":
        return start_raw, end_raw, ratio
    # Extend forward to the next sentence terminator so the whole clause is covered.
    stop = "。！？；"
    extended = end_raw
    limit = min(len(span_text), end_raw + 12)
    while extended < limit and span_text[extended] not in stop:
        extended += 1
    if extended < limit and span_text[extended] in stop:
        return start_raw, extended + 1, ratio
    # No terminator within reach: trim back to the last complete sentence boundary so a
    # half-clause tail ("配。") is not left behind.
    trimmed = end_raw
    while trimmed > start_raw and span_text[trimmed - 1] not in stop:
        trimmed -= 1
    if trimmed > start_raw:
        return start_raw, trimmed, ratio
    return start_raw, end_raw, ratio


def resolve_quote(span: ParagraphSpan, quote: str) -> tuple[int, int] | None:
    """Resolve a model quote to raw offsets inside one paragraph span.

    Long quotes that span read-only barriers or several sentences are retried
    sentence by sentence, keeping the longest resolvable run, so a faithful but
    imperfectly delimited quote still yields a usable span.
    """
    cleaned, index_map = display_text(span.text)
    located = find_normalized(cleaned, quote)
    if located is not None:
        start_clean, end_clean = located
        return index_map[start_clean], index_map[end_clean - 1] + 1
    parts = [part for part in re.split(r"(?<=[。；;!?！？])", quote) if part.strip()]
    if len(parts) > 1:
        best: tuple[int, int] | None = None
        for part in parts:
            found = find_normalized(cleaned, part)
            if found is None:
                continue
            start_clean, end_clean = found
            candidate = (index_map[start_clean], index_map[end_clean - 1] + 1)
            if best is None or (candidate[1] - candidate[0]) > (best[1] - best[0]):
                best = candidate
        if best is not None:
            return best
    # A faithful quote that merely re-wraps the reference wording (extra prefix or a
    # list of classes) still resolves to the real span as long as one contiguous
    # sentence of the quote matches exactly.
    for sentence in sorted((part for part in re.split(r"(?<=[。；;!?！？])", quote)
                            if len(_compact(part)) >= 6),
                           key=lambda part: -len(_compact(part))):
        found = find_normalized(cleaned, sentence)
        if found is not None:
            start_clean, end_clean = found
            return index_map[start_clean], index_map[end_clean - 1] + 1
    return None


def containing_segment(span: ParagraphSpan, start: int, end: int) -> TextSegment | None:
    for segment in span.segments:
        if segment.start <= start and end <= segment.end:
            return segment
    return None


def text_in(inspection: DocumentInspection, location: str, start: int, end: int) -> str:
    span = inspection.by_location(location)
    return span.text[start:end]


def compact_in(value: str, container: str) -> bool:
    return _compact(value) in _compact(container)


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassFact:
    name: str
    subscription_fee: bool
    service_fee: bool
    current: bool
    rate: str | None
    quote: str


@dataclass(frozen=True)
class Facts:
    fund_type: str
    fund_type_quote: str
    fund_type_basis: str
    classes: tuple[ClassFact, ...]
    floating_management_fee: bool
    floating_quote: str
    floating_basis: str
    notes: str
    quotes_verified: dict[str, bool]
    problems: tuple[str, ...]

    @property
    def current_classes(self) -> tuple[ClassFact, ...]:
        return tuple(item for item in self.classes if item.current)

    @property
    def class_count(self) -> int:
        return len(self.current_classes)

    @property
    def subscription_group(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.current_classes
                     if item.subscription_fee and not item.service_fee)

    @property
    def service_group(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.current_classes if item.service_fee)

    @property
    def has_service_fee(self) -> bool:
        return bool(self.service_group)

    def as_ledger(self) -> dict[str, Any]:
        return {
            "fund_type": self.fund_type,
            "fund_type_quote": self.fund_type_quote,
            "class_count": self.class_count,
            "classes": [
                {"name": item.name, "subscription_fee": item.subscription_fee,
                 "service_fee": item.service_fee, "current": item.current,
                 "rate": item.rate, "quote": item.quote}
                for item in self.classes
            ],
            "subscription_group": list(self.subscription_group),
            "service_group": list(self.service_group),
            "has_service_fee": self.has_service_fee,
            "is_floating_fee": self.floating_management_fee,
            "floating_quote": self.floating_quote,
            "notes": self.notes,
            "quotes_verified": dict(self.quotes_verified),
            "problems": list(self.problems),
        }


_FACTS_SECTION_HINTS = ("释义", "基金的基本情况", "基本情况", "费用", "税收", "申购", "赎回", "清算", "收益")
_FACTS_KEYWORDS = ("份额类别", "销售服务费", "申购费", "认购费", "赎回费", "管理费", "浮动", "或有", "超额", "基金份额分为", "类别")


def facts_context(inspection: DocumentInspection, *, limit: int = 16000) -> str:
    """Bounded evidence: definition/basics/fee sections first, then keyword matches."""
    selected: list[ParagraphSpan] = []
    seen: set[str] = set()
    for span in inspection.paragraphs:
        zone = span.logical_zone or span.zone
        if zone not in {"body", "summary"}:
            continue
        section = span.section_path or ""
        if any(hint in section for hint in _FACTS_SECTION_HINTS):
            selected.append(span)
            seen.add(span.location)
    for span in inspection.paragraphs:
        if span.location in seen:
            continue
        zone = span.logical_zone or span.zone
        if zone not in {"body", "summary"}:
            continue
        text = span.safe_text or ""
        if sum(1 for keyword in _FACTS_KEYWORDS if keyword in text) >= 2:
            selected.append(span)
            seen.add(span.location)
    lines: list[str] = ["CONTRACT_SOURCE"]
    total = 0
    for span in selected:
        cleaned, _ = display_text(span.text)
        line = f"[{span.location}] {cleaned.strip()}"
        if total + len(line) > limit:
            break
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


def _verify_quote(inspection: DocumentInspection, quote: str) -> bool:
    if not quote or len(quote.strip()) < 2:
        return False
    cleaned_quote = _compact(quote)
    if not cleaned_quote:
        return False
    for span in inspection.paragraphs:
        cleaned, _ = display_text(span.text)
        if cleaned_quote in _compact(cleaned):
            return True
    return False


def extract_facts(inspection: DocumentInspection, gateway: Any) -> Facts:
    context = facts_context(inspection, limit=max(4000, gateway.max_context_chars - 2500))
    result = gateway.call(task_type="recall_facts", bounded_context=context,
                          response_schema=FACTS_SCHEMA, instruction=FACTS_INSTRUCTION,
                          prompt_version=FACTS_PROMPT_VERSION)
    value = result.value if isinstance(result.value, dict) else {}
    problems: list[str] = []
    quotes_verified: dict[str, bool] = {}

    fund_type = (value.get("fund_type") or {}) if isinstance(value.get("fund_type"), dict) else {}
    fund_type_value = str(fund_type.get("value") or "other")
    fund_quote = str(fund_type.get("quote") or "")
    quotes_verified["fund_type"] = _verify_quote(inspection, fund_quote)
    if not quotes_verified["fund_type"]:
        problems.append("FUND_TYPE_QUOTE_UNVERIFIED")

    classes: list[ClassFact] = []
    raw_classes = value.get("classes") if isinstance(value.get("classes"), list) else []
    for item in raw_classes:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        quote = str(item.get("quote") or "")
        verified = _verify_quote(inspection, quote)
        quotes_verified[f"class:{name}"] = verified
        if not verified:
            problems.append(f"CLASS_QUOTE_UNVERIFIED:{name}")
        classes.append(ClassFact(
            name=name,
            subscription_fee=bool(item.get("subscription_fee")),
            service_fee=bool(item.get("service_fee")),
            current=bool(item.get("current", True)),
            rate=(str(item["rate"]) if item.get("rate") else None),
            quote=quote,
        ))

    floating = (value.get("floating_management_fee") or {}) if isinstance(value.get("floating_management_fee"), dict) else {}
    floating_value = bool(floating.get("value"))
    floating_quote = str(floating.get("quote") or "")
    quotes_verified["floating"] = _verify_quote(inspection, floating_quote)
    if not quotes_verified["floating"]:
        problems.append("FLOATING_QUOTE_UNVERIFIED")

    return Facts(
        fund_type=fund_type_value,
        fund_type_quote=fund_quote,
        fund_type_basis=str(fund_type.get("basis") or ""),
        classes=tuple(classes),
        floating_management_fee=floating_value,
        floating_quote=floating_quote,
        floating_basis=str(floating.get("basis") or ""),
        notes=str(value.get("notes") or ""),
        quotes_verified=quotes_verified,
        problems=tuple(problems),
    )


# ---------------------------------------------------------------------------
# Structure index and windows
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Section:
    id: str
    title: str
    zone: str
    locations: tuple[str, ...]
    chars: int
    preview: str


def structure_index(inspection: DocumentInspection, *, max_sections: int = 80) -> tuple[Section, ...]:
    """Group readable paragraphs into sections by their running heading."""
    groups: list[list[ParagraphSpan]] = []
    for span in inspection.paragraphs:
        zone = span.logical_zone or span.zone
        if zone not in {"body", "summary"}:
            continue
        if groups and (groups[-1][0].section_path == span.section_path
                       and (groups[-1][0].logical_zone or groups[-1][0].zone) == zone):
            groups[-1].append(span)
        else:
            groups.append([span])
    sections: list[Section] = []
    for position, group in enumerate(groups[:max_sections]):
        first = group[0]
        zone = first.logical_zone or first.zone
        title = first.section_path or ("内容摘要" if zone == "summary" else "前言")
        chars = sum(len(span.text) for span in group)
        preview_span = next((span for span in group if len(span.safe_text.strip()) >= 8), first)
        cleaned, _ = display_text(preview_span.text)
        preview = cleaned.strip()[:80]
        sections.append(Section(id=f"S{position + 1:02d}", title=title, zone=zone,
                                locations=tuple(span.location for span in group),
                                chars=chars, preview=preview))
    return tuple(sections)


def structure_context(sections: Sequence[Section]) -> str:
    lines = ["CONTRACT_STRUCTURE"]
    for section in sections:
        lines.append(f"[{section.id}] zone={section.zone} chars={section.chars} "
                     f"title={section.title!r} preview={section.preview!r} "
                     f"locations={section.locations[0]}..{section.locations[-1]}")
    return "\n".join(lines)


def build_windows(sections: Sequence[Section], inspection: DocumentInspection, section_ids: Iterable[str],
                  *, max_chars: int) -> list["Window"]:
    selected = [section for section in sections if section.id in set(section_ids)]
    windows: list[Window] = []
    current: list[Section] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if current:
            windows.extend(_window_from_sections(current, inspection, max_chars=max_chars, base=len(windows)))
            current, current_chars = [], 0

    for section in selected:
        if current and current_chars + section.chars > max_chars:
            flush()
        current.append(section)
        current_chars += section.chars
    flush()
    return windows


@dataclass(frozen=True)
class Window:
    id: str
    section_ids: tuple[str, ...]
    locations: tuple[str, ...]
    text: str


def _window_from_sections(sections: Sequence[Section], inspection: DocumentInspection, *,
                          max_chars: int, base: int) -> list[Window]:
    chunks: list[Window] = []
    lines: list[str] = []
    total = 0
    current_locations: list[str] = []
    section_ids = tuple(section.id for section in sections)
    base_id = "_".join(section_ids)

    def emit() -> None:
        nonlocal lines, total, current_locations
        if lines:
            chunks.append(Window(id=f"{base_id}#{len(chunks) + 1}", section_ids=section_ids,
                                 locations=tuple(current_locations), text="\n".join(lines)))
            lines, total, current_locations = [], 0, []

    for section in sections:
        for location in section.locations:
            span = inspection.by_location(location)
            cleaned, _ = display_text(span.text)
            line = f"[{location}] {cleaned}"
            if lines and total + len(line) > max_chars:
                emit()
            lines.append(line)
            current_locations.append(location)
            total += len(line)
    emit()
    return chunks


# ---------------------------------------------------------------------------
# Scope mapping
# ---------------------------------------------------------------------------

def plan_windows(sections: Sequence[Section], inspection: DocumentInspection,
                 mapping: dict[str, list[str]], *, max_chars: int) -> list[tuple["Window", list[str]]]:
    """Build the union of mapped sections into windows, each with its applicable rules."""
    selected = sorted({section_id for ids in mapping.values() for section_id in ids})
    windows = build_windows(sections, inspection, selected, max_chars=max_chars)
    planned: list[tuple[Window, list[str]]] = []
    for window in windows:
        window_sections = set(window.section_ids)
        rules = [rule_id for rule_id, ids in mapping.items() if window_sections & set(ids)]
        planned.append((window, rules))
    return planned


def rule_context(rules: Sequence[dict], *, full: bool) -> str:
    lines = ["GUIDE_RULES"]
    for rule in rules:
        lines.append(f"[{rule['rule_id']}] {rule['title']} | section_hint={rule.get('section_hint') or ''}")
        requirement = str(rule.get("requirement") or "")
        if full:
            lines.append(f"  requirement: {requirement}")
            for operation in rule.get("operations") or []:
                kind = operation.get("op")
                if kind == "append":
                    lines.append(f"  append: {_clip(operation.get('new_text') or '', 400)}")
                elif kind == "replace":
                    lines.append(f"  replace: {_clip(operation.get('old_text') or '', 160)} -> "
                                 f"{_clip(operation.get('new_text') or '', 400)}")
                elif kind == "delete":
                    lines.append(f"  delete: {_clip(operation.get('old_text') or '', 240)}")
                elif kind == "noop":
                    lines.append("  no change required by this branch")
        else:
            lines.append(f"  requirement: {_clip(requirement, 300)}")
    return "\n".join(lines)


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


def scope_map(rules: Sequence[dict], sections: Sequence[Section], gateway: Any) -> dict[str, list[str]]:
    context = "\n\n".join([structure_context(sections), rule_context(rules, full=False)])
    if len(context) > gateway.max_context_chars:
        raise RecallError("RECALL_SCOPE_CONTEXT_LIMIT", {"chars": len(context)})
    result = gateway.call(task_type="recall_scope", bounded_context=context,
                          response_schema=SCOPE_SCHEMA, instruction=SCOPE_INSTRUCTION,
                          prompt_version=SCOPE_PROMPT_VERSION)
    value = result.value if isinstance(result.value, dict) else {}
    valid_ids = {section.id for section in sections}
    rule_ids = {rule["rule_id"] for rule in rules}
    mapping: dict[str, list[str]] = {rule_id: [] for rule_id in rule_ids}
    for item in value.get("mappings") or []:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "")
        if rule_id not in rule_ids:
            continue
        ids = [str(section_id) for section_id in (item.get("section_ids") or [])]
        mapping[rule_id] = [section_id for section_id in ids if section_id in valid_ids]
    return mapping


# ---------------------------------------------------------------------------
# Inventory
# ---------------------------------------------------------------------------

@dataclass
class Target:
    target_id: str
    rule_id: str
    location: str
    quote: str
    state: str
    reason: str
    start: int | None = None
    end: int | None = None
    resolution: str = "unresolved"
    segment_ok: bool = False
    # Composite targets carry one operation reference text that runs across several
    # paragraphs (FL-D047): each item is "location:start:end" measured in that
    # paragraph's whitespace-free text.
    composite: tuple[str, ...] = ()
    # Set when the planner judged the rule out of scope for this product (its condition
    # does not hold, or it needs a class group / sales-service-fee wording the product
    # cannot carry). The audit must not re-demand such a target (FL-D056).
    out_of_scope: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "rule_id": self.rule_id, "location": self.location,
            "quote": self.quote, "state": self.state, "reason": self.reason,
            "start": self.start, "end": self.end, "resolution": self.resolution,
            "segment_ok": self.segment_ok, "composite": list(self.composite),
        }


def inventory_window(window: Window, rules: Sequence[dict], facts: Facts, gateway: Any,
                     inspection: DocumentInspection) -> tuple[list[Target], dict[str, Any]]:
    facts_text = json.dumps(facts.as_ledger(), ensure_ascii=False, indent=1)
    context = "\n\n".join([window.text, facts_text, rule_context(rules, full=True)])
    if len(context) > gateway.max_context_chars:
        raise RecallError("RECALL_INVENTORY_CONTEXT_LIMIT",
                          {"window": window.id, "chars": len(context)})
    result = gateway.call(task_type="recall_inventory", bounded_context=context,
                          response_schema=INVENTORY_SCHEMA, instruction=INVENTORY_INSTRUCTION,
                          prompt_version=INVENTORY_PROMPT_VERSION)
    value = result.value if isinstance(result.value, dict) else {}
    window_locations = set(window.locations)
    rule_ids = {rule["rule_id"] for rule in rules}
    targets: list[Target] = []
    dropped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    counter = 0
    for item in value.get("targets") or []:
        if not isinstance(item, dict):
            continue
        rule_id = str(item.get("rule_id") or "")
        location = str(item.get("location") or "")
        quote = str(item.get("quote") or "")
        state = str(item.get("state") or "")
        if rule_id not in rule_ids or location not in window_locations or state not in {"needs_edit", "satisfied", "absent"}:
            dropped.append({"reason": "INVENTORY_ITEM_INVALID", "item": item})
            continue
        key = (rule_id, location, _compact(quote)[:40])
        if key in seen:
            continue
        seen.add(key)
        counter += 1
        target = Target(target_id=f"{window.id}:T{counter:03d}", rule_id=rule_id, location=location,
                        quote=quote, state=state, reason=str(item.get("reason") or ""))
        if quote:
            try:
                span = inspection.by_location(location)
            except KeyError:
                span = None
            if span is not None:
                located = resolve_quote(span, quote)
                if located:
                    target.start, target.end = located
                    target.segment_ok = containing_segment(span, *located) is not None
                    target.resolution = "resolved"
                else:
                    target.resolution = "quote_not_found"
        targets.append(target)
    ledger = {
        "window": window.id, "sections": list(window.section_ids),
        "targets": [target.as_dict() for target in targets],
        "dropped": dropped,
        "counts": {
            "needs_edit": sum(1 for t in targets if t.state == "needs_edit"),
            "satisfied": sum(1 for t in targets if t.state == "satisfied"),
            "absent": sum(1 for t in targets if t.state == "absent"),
            "unresolved": sum(1 for t in targets if t.state == "needs_edit" and t.resolution != "resolved"),
        },
    }
    return targets, ledger


# ---------------------------------------------------------------------------
# Deterministic coverage survey (FL-D047)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SurveyHit:
    rule_id: str
    operation: str
    locations: tuple[str, ...]
    quote: str
    start: int
    end: int
    ratio: float
    index: int = 0

    @property
    def parts(self) -> tuple[tuple[str, int, int], ...]:
        """Per-paragraph slices that make up this occurrence."""
        return getattr(self, "_parts", ()) or ()

    def with_parts(self, parts: tuple[tuple[str, int, int], ...]) -> "SurveyHit":
        object.__setattr__(self, "_parts", parts)
        return self


def operation_search_keys(rule: dict, condition_facts: "Facts | None" = None) -> list[str]:
    """Reference texts that can anchor a deterministic search for a rule's targets.

    The rule's own reference texts are used verbatim. When every applicable
    operation is a deletion, a shorter tail of the reference also qualifies, but
    only when it shares domain wording (a character trigram) with the rule's title
    or requirement — this keeps "并报中国证监会备案" while rejecting fragments that
    coincide with unrelated generic sentences (FL-D047).
    """
    keys: list[str] = []
    delete_only = True
    core = f"{rule.get('title') or ''}{rule.get('requirement') or ''}"
    core_grams = _character_ngrams(_compact(core), 3) if core else set()
    for operation in rule.get("operations") or []:
        if condition_facts is not None and not condition_matches(operation.get("condition"), condition_facts):
            continue
        old_text = _compact(str(operation.get("old_text") or ""))
        if len(old_text) < 8:
            continue
        if old_text not in keys:
            keys.append(old_text)
        if operation.get("op") != "delete":
            delete_only = False
            continue
        for fragment in reference_fragments(str(operation.get("old_text") or "")):
            if fragment in keys:
                continue
            if not _compact(str(operation.get("old_text") or "")).endswith(fragment):
                continue
            if any(fragment in _compact(str(other.get("new_text") or ""))
                   or fragment in _compact(str(other.get("old_text") or ""))
                   for other in rule.get("operations") or []):
                # The fragment also lives in a sibling operation's own text, so that
                # operation (not this one) covers it.
                continue
            if core_grams and not (_character_ngrams(fragment, 3) & core_grams):
                continue
            keys.append(fragment)
        # Contracts spell the same clause with a different lead-in and a different tail:
        # the guide writes "C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金
        # 托管人发送…" while a contract writes "基金销售服务费每日计提，逐日累计至每月月末，
        # 按月支付，经基金管理人与基金托管人核对一致后…". Neither the long reference nor
        # its tail matches, so the rule's leading domain phrase (the reference without its
        # class prefix, up to the first clause boundary) is the anchor that does. Only a
        # delete-only rule takes this path, the phrase must keep eight characters, and it
        # must share domain wording with the rule (FL-D052).
        first_clause = _CLAUSE_SPLIT.split(_strip_class_lead(old_text) or old_text)[0]
        if len(first_clause) >= 8 and first_clause not in keys:
            if any(first_clause in _compact(str(other.get("new_text") or ""))
                   or (other is not operation
                       and first_clause in _compact(str(other.get("old_text") or "")))
                   for other in rule.get("operations") or []):
                continue
            if core_grams and (_character_ngrams(first_clause, 3) & core_grams):
                keys.append(first_clause)
    for variant in rule.get("old_text_variants") or []:
        compact = _compact(str(variant))
        if len(compact) >= 8 and compact not in keys:
            keys.append(compact)
    return keys


_SENTENCE_SPLIT = re.compile(r"[。；;!?！？]")
_CLAUSE_SPLIT = re.compile(r"[，,：:、（）()【】\[\]]")


def bare_tail_keys(rule: dict, condition_facts: "Facts | None" = None) -> list[str]:
    """Search keys that are only a clause TAIL with no lead inside the rule's own text.

    "并报中国证监会备案" is one: the guide names only the deleted tail, so the string
    alone carries no context and also occurs in unrelated clauses (a valuation-error
    correction paragraph closes with the same phrase). Hits from these keys must be
    corroborated by the rule's own context wording (FL-D052).
    """
    bare: list[str] = []
    for operation in rule.get("operations") or []:
        if condition_facts is not None and not condition_matches(operation.get("condition"),
                                                                 condition_facts):
            continue
        if operation.get("op") not in {"delete", "replace"}:
            continue
        old_text = _compact(str(operation.get("old_text") or ""))
        if len(old_text) < 8:
            continue
        # A reference with no internal clause boundary is a bare tail: the guide names
        # only the deleted wording and supplies no lead-in of its own.
        if not _CLAUSE_SPLIT.search(old_text) and old_text not in bare:
            bare.append(old_text)
    return bare


def rule_context_anchors(rule: dict, condition_facts: "Facts | None" = None) -> list[str]:
    """Context strings that prove a bare-tail hit belongs to this rule's clause.

    The rule's non-tail operation references (the fee-adjustment wording "调低赎回费率"
    beside the deleted filing phrase) and its variant texts, filtered to clauses long
    enough to be meaningful.
    """
    anchors: list[str] = []
    tail_keys = set(bare_tail_keys(rule, condition_facts))
    for operation in rule.get("operations") or []:
        if condition_facts is not None and not condition_matches(operation.get("condition"),
                                                                 condition_facts):
            continue
        old_text = str(operation.get("old_text") or "")
        new_text = str(operation.get("new_text") or "")
        for piece in _CLAUSE_SPLIT.split(_compact(old_text)):
            if len(piece) >= 4 and piece not in tail_keys and piece not in anchors:
                anchors.append(piece)
        for piece in _CLAUSE_SPLIT.split(_compact(new_text)):
            if len(piece) >= 6 and piece not in anchors:
                anchors.append(piece)
    for variant in rule.get("old_text_variants") or []:
        compact = _compact(str(variant))
        if compact and compact not in anchors:
            anchors.append(compact)
    return anchors


_NEGATION_MARKERS = ("不", "无需", "免", "取消")
_BOUNDARY_MARKS = frozenset("。，；：！？）＝"
                             ";；！？!?…）)\"】》、")
_PARAGRAPH_GRAMS_CACHE: dict[str, set[str]] = {}


_NEGATION_PREFIXES = ("不", "无须", "无需", "免于", "取消")


def satisfied_by_new_text(rule: dict, facts: Facts, compact_body: str) -> str | None:
    """Replacement text that proves this rule is already carried out in a paragraph.

    Two deterministic signals, both checked against the paragraph's whitespace-free
    text:

    * the whole instantiated new text is present verbatim, or
    * its last sentence (>= 6 characters) is present and carries at least two
      character trigrams from the rule's title or requirement — enough to rule out a
      generic closing formula while still recognising a rewording such as
      "…费用收取不同" (FL-D047).
    """
    if not compact_body or not str(rule.get("requirement") or "").strip():
        return None
    replacements: list[str] = []
    references: list[str] = []
    for operation in rule.get("operations") or []:
        references.append(_compact(str(operation.get("old_text") or "")))
        if not condition_matches(operation.get("condition"), facts):
            continue
        if operation.get("op") not in {"replace", "append"}:
            continue
        instantiated, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        if issues or not instantiated:
            return None
        replacements.append(instantiated)
    if not replacements:
        return None
    combined = "".join(replacements)
    compact_replacement = _compact(combined)
    if compact_replacement and compact_replacement in compact_body:
        return combined
    core = f"{rule.get('title') or ''}{rule.get('requirement') or ''}"
    core_grams = _character_ngrams(_compact(core), 3) if core else set()
    reference_grams: set[str] = set()
    for reference in references:
        reference_grams |= _character_ngrams(reference, 2)
    for candidate in (combined, _policy_suffix(combined)):
        compact = _compact(candidate)
        if len(compact) < 8 or compact not in compact_body:
            continue
        if core_grams and len(_character_ngrams(str(candidate), 3) & core_grams) < 2:
            continue
        # A candidate that merely copies the reference wording proves nothing: the
        # rule asks for a change, so the matched text must differ from the reference
        # by more than a small share of its bigrams (FL-D047).
        grams = _character_ngrams(compact, 2)
        if grams and reference_grams:
            overlap = len(grams & reference_grams) / len(grams)
            if overlap > 0.6:
                continue
        return str(candidate)
    # A rewording that moves the difference clause to another subject: the paragraph
    # carries the guide's own sentence with a leading connector and a following
    # consequence clause ("由于费用收取不同，…将分别计算基金份额净值"). The longest
    # comma clause that precedes the difference must still be intact (FL-D047).
    best: tuple[int, str] | None = None
    for candidate in _final_clause_candidates(_compact(combined)):
        if candidate not in compact_body:
            continue
        prefix = _character_ngrams(candidate, 3) & core_grams
        if len(prefix) < 2:
            continue
        if best is None or len(candidate) > best[0]:
            best = (len(candidate), candidate)
    if best is not None:
        return best[1]
    # A clause that states the SAME policy with its subject and its fee-difference
    # phrase in the opposite order: the guide writes "…A类基金份额和C类基金份额费用
    # 收取不同" while the contract writes "由于基金费用的不同，本基金A类基金份额和C类
    # 基金份额将分别计算…". Both name the classes and the fee difference, so the rule is
    # already carried out here (FL-D052).
    if _policy_phrase_equivalent(compact_replacement, compact_body, references):
        return _policy_excerpt(compact_body, compact_replacement)
    return None


# "费用收取不同" family: the same policy expressed with different word order.
_FEE_DIFFERENCE_MARKERS = ("费用收取不同", "费用的不同", "费用不同", "费率不同", "费用存在差异")


def _policy_phrase_equivalent(compact_new: str, compact_body: str,
                              references: Sequence[str]) -> bool:
    """Does the paragraph state this rule's replacement policy in a reworded form?

    Requires (a) the paragraph not to still carry the operation's own reference text,
    (b) every class token named in the new text to appear in the paragraph, and
    (c) at least one fee-difference marker on both sides.
    """
    if not compact_new or not compact_body:
        return False
    if any(reference and len(reference) >= 8 and reference in compact_body
           for reference in references):
        return False
    new_markers = [marker for marker in _FEE_DIFFERENCE_MARKERS if marker in compact_new]
    body_markers = [marker for marker in _FEE_DIFFERENCE_MARKERS if marker in compact_body]
    if not new_markers or not body_markers:
        return False
    class_tokens = re.findall(r"[A-ZＡ-Ｚ]类(?:基金份额)?", compact_new)
    if class_tokens and not all(token in compact_body for token in class_tokens):
        return False
    return True


def _policy_excerpt(compact_body: str, compact_new: str) -> str:
    """A short, real excerpt of the paragraph that carries the equivalent policy."""
    markers = [marker for marker in _FEE_DIFFERENCE_MARKERS if marker in compact_body]
    if markers:
        position = compact_body.find(markers[0])
        start = max(0, position - 12)
        return compact_body[start:position + len(markers[0]) + 12]
    return compact_body[:40]


def _final_clause_candidates(compact_new_text: str) -> list[str]:
    """The final clause of a new text, longest form first (difference phrasing)."""
    clauses = [part for part in _CLAUSE_SPLIT.split(compact_new_text) if part]
    if len(clauses) < 2:
        return []
    tail = clauses[-1]
    previous = clauses[-2]
    return [previous + tail, tail]


def _policy_suffix(new_text: str) -> str:
    """The last sentence of a replacement text, when it is long enough to be a clause."""
    parts = [part for part in re.split(r"(?<=[。；;!?！？])", new_text) if part.strip()]
    for part in reversed(parts):
        compact = _compact(part)
        if len(compact) >= 6:
            return compact
    return ""


_CLASS_LEAD = re.compile(r"^[A-Za-z0-9]*类基金份额的?")


def _strip_class_lead(text_value: str) -> str:
    """The reference text with its leading class-group phrase removed.

    ``C类基金份额的销售服务费每日计提…`` becomes ``销售服务费每日计提…``. Contracts often name
    the class once in a surrounding sentence and then write the clause without the prefix
    (``基金销售服务费每日计提…``), so the prefix-stripped form is the part that really has to
    match. Returns the compact form, or an empty string when nothing was stripped.
    """
    compact = _compact(text_value)
    stripped = _CLASS_LEAD.sub("", compact, count=1)
    return stripped if stripped != compact else ""


def reference_fragments(text_value: str) -> list[str]:
    """The tail clause of the last sentence of a reference text, when it stands alone.

    A delete requirement often names the tail of a clause ("并报中国证监会备案")
    while the contract spells the same clause with a different lead-in; that verbatim
    tail is what the deletion removes, so it is a valid anchor. Only the last sentence
    is considered, and only its final clause, which keeps generic closing formulas
    ("并在招募说明书中列示") from anchoring unrelated rules (FL-D047).
    """
    target = _compact(text_value)
    sentences = [part for part in _SENTENCE_SPLIT.split(target) if part]
    if len(sentences) < 2:
        return []
    last = sentences[-1]
    clauses = [part for part in _CLAUSE_SPLIT.split(last) if part]
    if len(clauses) < 2:
        return []
    tail = clauses[-1]
    if len(tail) < 8 or tail == target:
        return []
    return [tail]


FRAGMENT_LEAD_GAP = 12




def _lead_nearby(body: str, position: int, lead: str) -> bool:
    """Is the reference's own clause lead just before this fragment occurrence?

    The contract may spell the lead-in differently from the guide ("...同意后变更并公告，
    并报..."), so the longest tail of the lead that sits contiguously before the fragment
    decides. At least six characters are required to avoid accepting a coincidental
    single word (FL-D047).
    """
    candidate = lead
    minimum = max(6, int(len(lead) * 0.6))
    while len(candidate) >= minimum:
        found = body.find(candidate)
        while found >= 0:
            if 0 <= position - (found + len(candidate)) <= FRAGMENT_LEAD_GAP:
                return True
            found = body.find(candidate, found + 1)
        candidate = candidate[1:]
    return False


def find_old_text_all(paragraphs: Sequence[Any], old_text: str, *,
                      threshold: float = FUZZY_MATCH_THRESHOLD
                      ) -> list[tuple[tuple[str, int, int], ...]]:
    """All occurrences of an operation's reference text in the document.

    Each occurrence is a tuple of per-paragraph slices ``(location, start, end)``
    measured in that paragraph's whitespace-free text. The verbatim reference is
    searched first; a tail clause of a pure deletion ("并报中国证监会备案") is also a
    valid anchor, but only where it begins at a clause boundary — never in the middle
    of a word (FL-D047).
    """
    target = _compact(old_text)
    if len(target) < 8:
        return []
    texts = {span.location: re.sub(r"\s+", "", display_text(span.text)[0]) for span in paragraphs}
    order = {span.location: index for index, span in enumerate(paragraphs)}
    found: list[tuple[tuple[str, int, int], ...]] = []
    seen: set[tuple[str, int]] = set()

    def record(parts: tuple[tuple[str, int, int], ...]) -> None:
        key = (parts[0][0], parts[0][1])
        if key in seen:
            return
        seen.add(key)
        found.append(parts)

    fragments = [fragment for fragment in reference_fragments(old_text)
                 if target.endswith(fragment)]
    # A fragment is a valid anchor only when the reference itself leads into it:
    # "并报中国证监会备案" -> tail "报中国证监会备案" has the lead "并" (too short to
    # judge), so that fragment does not anchor a search on its own (FL-D047).
    needles = [(target, None)] + [
        (fragment, target[:target.find(fragment)])
        for fragment in fragments
        if target.find(fragment) >= 8 and target.find(fragment) + len(fragment) == len(target)]
    for needle, lead in needles:
        for span in paragraphs:
            body = texts[span.location]
            position = body.find(needle)
            while position >= 0:
                if needle == target or position == 0 or body[position - 1] in _BOUNDARY_MARKS:
                    if lead is None or _lead_nearby(body, position, lead):
                        record(((span.location, position, position + len(needle)),))
                position = body.find(needle, position + 1)
    if found:
        return found
    # A split occurrence: this paragraph holds the head of the reference and the
    # next paragraph continues with its remainder.
    for span in paragraphs:
        body = texts[span.location]
        if not body:
            continue
        follower_index = order[span.location] + 1
        if follower_index >= len(paragraphs):
            continue
        follower = paragraphs[follower_index]
        follower_text = texts[follower.location]
        if not follower_text:
            continue
        lowest = max(0, len(body) - len(target))
        for position in range(lowest, len(body)):
            head = body[position:]
            if len(head) >= len(target) or len(head) < 8:
                continue
            if not target.startswith(head):
                continue
            remaining = target[len(head):]
            if not follower_text.startswith(remaining):
                continue
            record(((span.location, position, len(body)),
                    (follower.location, 0, len(remaining))))
            break
        if found:
            return found
    if found:
        return found
    # Short reference texts only ever match exactly: a fuzzy ratio over a short
    # string is too easy to satisfy for a different sentence (FL-D047).
    if len(target) < 24 or threshold < 0.9:
        return []
    needle_grams = _character_ngrams(target, 2)
    best: dict[str, tuple[tuple[str, int, int], ...]] = {}
    for span in paragraphs:
        if not (_PARAGRAPH_GRAMS_CACHE.get(span.location, set()) & needle_grams):
            continue
        variant = fuzzy_span(span.text, old_text, threshold=threshold)
        if variant is None:
            continue
        start_raw, end_raw, _ratio = variant
        cleaned, _index_map = display_text(span.text)
        located = find_normalized(cleaned, span.text[start_raw:end_raw])
        compact_start = located[0] if located else 0
        best[span.location] = ((span.location, compact_start, compact_start + len(target)),)
    return list(best.values())


def resolve_old_text(paragraphs: Sequence[Any], old_text: str, *,
                     threshold: float = FUZZY_MATCH_THRESHOLD
                     ) -> tuple[tuple[tuple[str, int, int], ...], float] | None:
    """The first occurrence of an operation's reference text, with its match ratio."""
    occurrences = find_old_text_all(paragraphs, old_text, threshold=threshold)
    if not occurrences:
        return None
    first = occurrences[0]
    by_location = {span.location: re.sub(r"\s+", "", display_text(span.text)[0])
                   for span in paragraphs}
    matched = "".join(by_location[location][start:end] for location, start, end in first)
    ratio = 1.0 if matched == _compact(old_text) else _sequence_ratio(_compact(old_text), matched)
    return first, ratio


def _anchor_present(parts: tuple[tuple[str, int, int], ...], anchors: Sequence[str],
                    compact_text: dict[str, str]) -> bool:
    """Does the hit's paragraph (or a neighbour part) carry the rule's context wording?"""
    if not anchors:
        return True
    for location, _start, _end in parts:
        body = compact_text.get(location) or ""
        if any(anchor in body for anchor in anchors):
            return True
    return False


def survey_targets(inspection: DocumentInspection, rules: Sequence[dict], facts: Facts, *,
                   known: Sequence[tuple[str, str]] = (),
                   threshold: float = FUZZY_MATCH_THRESHOLD,
                   override_rules: frozenset[str] = frozenset()) -> list[SurveyHit]:
    """Find rule targets the windowed inventory never reported (code-driven recall).

    ``known`` holds the (rule_id, location) pairs already covered by model inventory
    or earlier survey passes. A hit is produced only when the rule's own reference
    text still exists verbatim (or as a bounded wording variant) at a location that
    was never reported; nothing is invented, because every hit carries offsets into
    the real document. ``operation="satisfied"`` marks locations where the rule's
    instantiated new text is already in place, so the sweep does not report the
    transformed clause as missing (FL-D047).

    ``override_rules`` names rules whose existing targets must not suppress a new hit.
    A model inventory that judges the clause ``absent`` — which is precisely the
    not-applicable call this pass exists to correct — records a target at the very
    location the reference text still occupies, so the (rule, location) check would
    skip the hit and the obligation is dropped silently (FL-D101).
    """
    existing = {(rule_id, location) for rule_id, location in known
                if rule_id not in override_rules}
    paragraphs = [span for span in inspection.paragraphs if span.text.strip()]
    by_location = {span.location: span for span in paragraphs}
    _PARAGRAPH_GRAMS_CACHE.clear()
    for span in paragraphs:
        cleaned, _index_map = display_text(span.text)
        _PARAGRAPH_GRAMS_CACHE[span.location] = _character_ngrams(_compact(cleaned), 2)
    compact_text = {span.location: re.sub(r"\s+", "", display_text(span.text)[0])
                    for span in paragraphs}
    hits: list[SurveyHit] = []
    counter = 0
    for rule in rules:
        rule_id = str(rule.get("rule_id") or "")
        if not rule_id:
            continue
        for location, body in compact_text.items():
            if (rule_id, location) in existing:
                continue
            matched = satisfied_by_new_text(rule, facts, body)
            if not matched:
                continue
            counter += 1
            hits.append(SurveyHit(rule_id=rule_id, operation="satisfied",
                                  locations=(location,), quote=matched,
                                  start=0, end=0, ratio=1.0, index=counter))
            existing.add((rule_id, location))
        tail_keys = set(bare_tail_keys(rule, facts))
        anchors = rule_context_anchors(rule, facts)
        delete_only_rule = _delete_keyword_bag(rule, facts) != () or all(
            op.get("op") == "delete" for op in (rule.get("operations") or []) if op.get("op") != "noop")
        rule_hits_before = len(hits)
        for key in operation_search_keys(rule, facts):
            occurrences = find_old_text_all(paragraphs, key, threshold=SURVEY_FUZZY_THRESHOLD)
            for parts in occurrences:
                locations = tuple(item[0] for item in parts)
                if all((rule_id, location) in existing for location in locations):
                    continue
                if key in tail_keys and not _anchor_present(parts, anchors, compact_text):
                    # A bare clause tail ("并报中国证监会备案") also closes unrelated
                    # clauses; without the rule's own context wording in the same
                    # paragraph group the hit is not this rule's target (FL-D052).
                    continue
                first = parts[0]
                span = by_location.get(first[0])
                if span is None:
                    continue
                _compact_body, compact_map = compact_offsets(span.text)
                raw_start = (compact_map[first[1]] if first[1] < len(compact_map)
                             else len(span.text))
                raw_end = (compact_map[first[2] - 1] + 1
                           if 0 < first[2] <= len(compact_map) else raw_start)
                raw_end = _extend_to_clause_end(
                    span.text, raw_start, raw_end, key,
                    delete_only=delete_only_rule and key not in tail_keys,
                    sentences=_delete_sentence_span(rule, facts))
                raw_start = _extend_to_clause_start(
                    span.text, raw_start,
                    delete_only=delete_only_rule and key not in tail_keys)
                quote = span.text[raw_start:raw_end]
                # The reference clause can continue into the next paragraph: G17 asks to
                # delete both "…服务费等。" and "销售服务费使用范围不包括…" and a contract
                # splits them across two paragraphs. When the follower opens with the text
                # that follows the matched reference, bind both as one composite target
                # (FL-D063).
                if delete_only_rule and key not in tail_keys and len(parts) == 1:
                    follower_part = _reference_continuation(rule, facts, quote, span,
                                                            compact_text, by_location)
                    if follower_part is not None:
                        # ``parts`` offsets are measured in each paragraph's compact text
                        # (plan_composite_target maps them back through compact_offsets), so
                        # the first part must use the *extended* span from this hit rather
                        # than the raw ``find_old_text_all`` window it started from. The
                        # follower comes back as a full-paragraph raw span and is converted
                        # to that same compact space (FL-D080).
                        first_compact_body, first_map = compact_offsets(span.text)
                        # Map the extended raw span back into compact offsets for part 0.
                        compact_start = _raw_to_compact(first_map, raw_start)
                        compact_end = _raw_to_compact(first_map, raw_end)
                        follower_text = by_location[follower_part[0]].text
                        parts = [(first[0], compact_start, compact_end),
                                 (follower_part[0], 0, len(_compact(follower_text)))]
                        locations = (first[0], follower_part[0])
                counter += 1
                hits.append(SurveyHit(rule_id=rule_id, operation="survey", locations=locations,
                                      quote=quote or key, start=first[1], end=first[2],
                                      ratio=1.0, index=counter).with_parts(parts))
                existing.add((rule_id, locations[0]))
        if len(hits) == rule_hits_before:
            # No reference anchor matched. A pure deletion may still be present under a
            # paraphrase (FL-D062); fall back to the rule's own keyword signature, and only
            # where that signature is fully present in a single paragraph.
            bag = _delete_keyword_bag(rule, facts)
            if bag:
                ordered = list(compact_text.items())
                for index, (location, body) in enumerate(ordered):
                    if (rule_id, location) in existing:
                        continue
                    in_self = _keyword_bag_in_clause(body, bag)
                    follower_location = (ordered[index + 1][0]
                                         if index + 1 < len(ordered) else None)
                    follower = (ordered[index + 1][1]
                                if index + 1 < len(ordered) else "")
                    # A pair is only the owner when the signature is genuinely split: the
                    # follower alone must not already satisfy it, otherwise the follower is
                    # the single paragraph to bind and pairing would drag in the preceding
                    # line (a fee-formula row) as well.
                    in_pair = (not in_self and follower_location is not None
                               and not _keyword_bag_in_clause(follower, bag)
                               and (rule_id, follower_location) not in existing
                               and _keyword_bag_in_clause(body + follower, bag))
                    if not (in_self or in_pair):
                        continue
                    span = by_location.get(location)
                    if span is None:
                        continue
                    counter += 1
                    if in_pair:
                        follower_span = by_location.get(follower_location)
                        if follower_span is None:
                            continue
                        locations = (location, follower_location)
                        parts = [(location, 0, len(span.text)),
                                 (follower_location, 0, len(follower_span.text))]
                    else:
                        locations = (location,)
                        parts = [(location, 0, len(span.text))]
                    hits.append(SurveyHit(rule_id=rule_id, operation="survey",
                                          locations=locations, quote=span.text.strip(),
                                          start=0, end=0, ratio=1.0, index=counter).with_parts(parts))
                    for item in locations:
                        existing.add((rule_id, item))
    return hits


def append_applicability_targets(inspection: DocumentInspection, rules: Sequence[dict],
                                 facts: Facts, sections: Sequence[Section], *,
                                 known: Sequence[tuple[str, str]] = (),
                                 hinted: dict[str, str] | None = None) -> list[SurveyHit]:
    """Deterministic targets for conditional appends the model inventory missed (FL-D060/090).

    An append rule carries no ``old_text`` anchor, so the reference-anchored survey
    cannot find it and the whole decision rests on the windowed model inventory.
    When that judgment says ``not_applicable`` — for instance because the contract
    writes "直销渠道" where the guide writes "直销机构" — the obligation is silently
    dropped even though the section it belongs to plainly exists (D07).

    This pass only fires when every conservative condition holds:

    * the rule has an append operation whose condition is unconditionally true;
    * the section named by the rule's ``section_hint`` exists in the document;
    * the required policy text is **not already present** anywhere in the document;
    * no inventory/survey target for that rule was already recorded.

    It then anchors one target at the last paragraph of that section, so the append
    lands inside the clause the guide names rather than somewhere unrelated.
    """
    existing_rules = {rule_id for rule_id, _location in known}
    paragraphs = [span for span in inspection.paragraphs if span.text.strip()]
    if not paragraphs:
        return []
    document_compact = _compact("".join(display_text(span.text)[0] for span in paragraphs))
    hits: list[SurveyHit] = []
    counter = 0
    for rule in rules:
        rule_id = str(rule.get("rule_id") or "")
        if not rule_id or rule_id in existing_rules:
            continue
        append_ops = [operation for operation in (rule.get("operations") or [])
                      if operation.get("op") == "append"
                      and condition_matches(operation.get("condition"), facts)]
        if not append_ops:
            continue
        # The obligation must not already be satisfied: if a policy sentence is present,
        # the contract already carries it and there is nothing to append (this is what
        # keeps the pass from adding duplicate clauses). Slot instantiation may fail when
        # this product lacks a class group (SERVICE_GROUP_EMPTY on a contract with no
        # service-fee class); the append is still unconditional, so fall back to the raw
        # template wording for the presence test rather than skipping the rule.
        required = ""
        for operation in append_ops:
            template = str(operation.get("new_text") or "")
            instantiated, issues = instantiate_slots(template, facts)
            required = template if issues else instantiated
            if required:
                break
        if not required:
            continue
        if _compact(required.split("。")[0]) in document_compact:
            continue
        section = _section_for_hint(sections, rule.get("section_hint"))
        if section is None:
            continue
        members = [span for span in paragraphs if span.location in set(section.locations)]
        if not members:
            continue
        # Prefer the paragraph the inventory already pointed at (its "absent"/unresolved
        # target names the clause the rule belongs to), and fall back to the section's
        # last paragraph only when there is no such hint.
        prefer = (hinted or {}).get(rule_id)
        anchor = None
        if prefer:
            anchor = next((span for span in members if span.location == prefer), None)
            if anchor is not None and _looks_like_heading(anchor.text):
                # The inventory sometimes points at a section heading; appending directly
                # after "第二部分 释义" would place the clause before the definitions it
                # belongs to. Fall back to the section's last paragraph in that case.
                anchor = None
        if anchor is None:
            anchor = members[-1]
        counter += 1
        hits.append(SurveyHit(rule_id=rule_id, operation="append",
                              locations=(anchor.location,), quote=anchor.text.strip(),
                              start=0, end=0, ratio=1.0, index=counter)
                    .with_parts([(anchor.location, 0, len(_compact(anchor.text)))]))
    return hits


def _looks_like_heading(text: str) -> bool:
    """True for a section/chapter heading rather than body text.

    Headings read like "第二部分释义", "第十五部分基金费用与税收" or "七、基金合同的变更":
    a short ordinal prefix followed by the section name, with no full stop.
    """
    compacted = _compact(display_text(text)[0])
    if not compacted or len(compacted) > 30:
        return False
    if compacted.endswith(("。", "；", "，", "：")) and len(compacted) > 12:
        return False
    if re.match(r"^第[一二三四五六七八九十百零〇\d]+部分", compacted):
        return True
    return bool(re.match(r"^[一二三四五六七八九十]+[、.]", compacted))


def _section_for_hint(sections: Sequence[Section], hint: Any) -> Section | None:
    """The section whose title contains the rule's section hint (longest match wins)."""
    text = str(hint or "").strip()
    if not text:
        return None
    compact_hint = _compact(text)
    best: Section | None = None
    best_length = 0
    for section in sections:
        compact_title = _compact(section.title)
        if compact_hint and compact_hint in compact_title:
            if len(compact_title) > best_length:
                best, best_length = section, len(compact_title)
    return best


def _reference_continuation(rule: dict, facts: "Facts | None", matched_quote: str,
                            span: Any, compact_text: dict[str, str],
                            by_location: dict[str, Any]) -> tuple[str, int, int] | None:
    """The next paragraph, when the rule's delete reference continues into it.

    The matched span closes a sentence; the reference may carry a further sentence that the
    contract placed in the following paragraph ("销售服务费使用范围不包括基金募集期间的
    上述费用。"). Return ``(location, 0, len)`` for that follower so the two paragraphs form
    one composite deletion, or ``None`` when there is no such continuation (FL-D063).
    """
    matched = _compact(matched_quote)
    if not matched or len(matched) < 8:
        return None
    for operation in rule.get("operations") or []:
        if operation.get("op") != "delete":
            continue
        if facts is not None and not condition_matches(operation.get("condition"), facts):
            continue
        reference = _compact(str(operation.get("old_text") or ""))
        position = reference.find(matched[-16:]) if len(matched) >= 16 else -1
        if position < 0:
            continue
        tail = reference[position + len(matched[-16:]):]
        if not tail:
            continue
        # Locate the follower as the next paragraph in document order.
        order = list(compact_text.keys())
        here = span.location
        if here not in order:
            continue
        index = order.index(here)
        if index + 1 >= len(order):
            continue
        follower_location = order[index + 1]
        follower = compact_text[follower_location]
        head = tail[:16]
        # The contract may omit the class lead the guide writes ("C类基金份额的销售服务费
        # 使用范围…" against "销售服务费使用范围…"), so compare on the lead-stripped form.
        for candidate in (head, _strip_class_lead(head), tail[:10], _strip_class_lead(tail[:10])):
            if len(candidate) >= 8 and candidate in follower:
                follower_span = by_location.get(follower_location)
                if follower_span is not None:
                    return (follower_location, 0, len(follower_span.text))
    return None


def _extend_to_clause_start(text: str, start: int, *, delete_only: bool) -> int:
    """Grow a matched span back to the start of the clause it belongs to.

    A reference anchor can match mid-clause: the guide's G15 lead is "基金销售服务费每日计提
    …" and the survey anchor is its class-stripped form, so ``find_old_text_all`` can bind the
    span starting at "销售服务费每日计提" and leave the leading "基金" outside; a delete bound
    that way would strip the clause but leave the orphaned "基金" behind. For a delete-only rule
    move the span start back to the previous sentence terminator — but stop before any other
    domain term, because a malformed paragraph can glue a fee-formula row ("E 为 C 类基金份额
    前一日基金资产净值") onto the clause and that row must not be deleted (FL-D063).
    """
    if not delete_only or start <= 0:
        return start
    if text[start - 1] in "。；;！？!?":
        return start
    boundary = 0
    for index in range(start - 1, -1, -1):
        if text[index] in "。；;！？!?":
            boundary = index + 1
            break
    if boundary >= start:
        return start
    window = text[boundary:start]
    if any(term in window for term in ("资产净值", "＝", "=", "当日天数", "÷", "×")):
        return start
    return boundary


def _delete_sentence_span(rule: dict, facts: "Facts | None" = None) -> int:
    """How many sentence terminators the rule's delete references span (at least one).

    The guide's G15 clause is two sentences ("C类基金份额的销售服务费每日计提，按月支付。 …
    支付日期顺延。"), so a contract's paraphrase is the same two sentences. Binding only the
    first leaves the second behind; the survey extends the span across this many terminators
    (FL-D063).
    """
    references = []
    delete_only = True
    for operation in rule.get("operations") or []:
        if facts is not None and not condition_matches(operation.get("condition"), facts):
            continue
        if operation.get("op") != "delete":
            delete_only = False
            break
        references.append(str(operation.get("old_text") or ""))
    if not delete_only or not references:
        return 1
    body = "".join(references)
    return max(1, len(re.findall(r"[。；;！？!?]", body)))


def _extend_to_clause_end(text: str, start: int, end: int, key: str, *,
                          delete_only: bool, sentences: int = 1) -> int:
    """Grow a matched span to the end of the sentence(s) it starts.

    A reference anchor can be shorter than the obligation it names: the guide's G17 lead
    "C类基金份额的销售服务费主要用于支付销售机构佣金、…" reduces to the leading clause
    "销售服务费主要用于支付销售机构佣金" once the class prefix is stripped, and the survey
    then binds only those seventeen characters. A delete bound to that fragment removes only
    the lead and leaves the rest of the sentence ("、以及基金管理人的基金行销广告费…")
    behind. For a delete-only rule the whole sentence is the material to remove, so extend
    the span to the next sentence terminator (FL-D063); ``sentences`` covers references that
    are themselves several sentences (G15).
    """
    if not delete_only or end <= start or end >= len(text):
        return end
    if text[end - 1] in "。；;！？!?":
        remaining = sentences - 1
    else:
        remaining = sentences
    if remaining <= 0:
        return end
    for index in range(end, len(text)):
        if text[index] in "。；;！？!?":
            remaining -= 1
            if remaining <= 0:
                return index + 1
    return len(text)


def _keyword_bag_in_clause(body: str, bag: tuple[str, ...], window: int = 60) -> bool:
    """True when every keyword appears inside one short window of the paragraph body.

    A paragraph can hold several clauses (a托管费 sentence followed by a销售服务费
    heading); requiring the keywords anywhere in the paragraph lets a neighbouring clause
    satisfy the signature. A bounded window keeps the hit on the clause the rule is about
    while still allowing the fixed wording to span a comma (FL-D062).
    """
    if not bag:
        return False
    positions = [body.find(token) for token in bag]
    if any(position < 0 for position in positions):
        return False
    for start in positions:
        if all(abs(position - start) <= window for position in positions):
            return True
    return False


def _delete_keyword_bag(rule: dict, facts: Facts | None) -> tuple[str, ...]:
    """Closed-class keyword requirements derived from a delete-only rule's references.

    A pure deletion frequently survives in contracts in several paraphrases ("每日计提"
    against "每日计算", "按月支付" against "次月支付"), so no single string anchor covers
    every wording. The rule's own reference text still names the domain terms, the payment
    action and the payment period it is about; requiring those to co-occur in one paragraph
    finds the clause across the paraphrases while staying specific enough not to hit the
    fee-formula or fee-purpose lines (FL-D062).
    """
    domain = ("销售服务费", "申购费", "赎回费", "认购费", "管理费", "托管费", "销售服务费率")
    action = ("支付", "划付", "划出", "划款", "计提", "计算")
    period = ("按月", "次月", "每月", "逐日", "每季")
    references = []
    delete_only = True
    for operation in rule.get("operations") or []:
        if facts is not None and not condition_matches(operation.get("condition"), facts):
            continue
        if operation.get("op") != "delete":
            delete_only = False
            break
        references.append(_compact(str(operation.get("old_text") or "")))
    if not delete_only or not references:
        return ()
    body = "".join(references)
    bag: list[str] = []
    for group in (domain, action, period):
        matched = [token for token in group if token in body]
        if matched:
            bag.append(matched[0])
    # Require the whole signature (a domain term, an action and a period) so the fallback
    # cannot degrade into a generic fee mention.
    return tuple(bag) if len(bag) == 3 else ()


def is_delete_only_rule(rule: dict, facts: "Facts | None" = None) -> bool:
    """True when every applicable operation of the rule is a pure deletion.

    Used to decide which rules get the deterministic delete-applicability override
    (FL-D101). ``noop`` operations do not count against the rule: a branch that
    requires no change alongside a delete still leaves the rule delete-only.
    """
    seen = False
    for operation in rule.get("operations") or []:
        kind = operation.get("op")
        if kind == "noop":
            continue
        if facts is not None and not condition_matches(operation.get("condition"), facts):
            continue
        if kind != "delete":
            return False
        seen = True
    return seen


def _sequence_ratio(left: str, right: str) -> float:
    from difflib import SequenceMatcher
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


def _deterministic_new_text(rule: dict, facts: Facts) -> str | None:
    """The rule's new text when every operation carries a fixed replacement."""
    pieces: list[str] = []
    for operation in rule.get("operations") or []:
        if not condition_matches(operation.get("condition"), facts):
            continue
        if operation.get("op") not in {"replace", "append"}:
            return None
        instantiated, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        if issues or not instantiated:
            return None
        pieces.append(instantiated)
    return "".join(pieces) or None


def composite_fragment(rule: dict, facts: Facts, paragraph: ParagraphSpan,
                       hit_start: int, hit_end: int) -> tuple[str, str] | None:
    """Explain a composite reference slice: (compact prefix, matched slice).

    The prefix is the paragraph text before the reference match (only whitespace is
    dropped, so callers can compare it against the operation's reference text);
    the matched slice is the part of the reference that lives in this paragraph.
    Returns None when the slice cannot be attributed to a deterministic operation.
    """
    cleaned, _ = display_text(paragraph.text)
    compact_prefix = cleaned[:hit_start]
    content = cleaned[hit_start:hit_end]
    for operation in rule.get("operations") or []:
        if not condition_matches(operation.get("condition"), facts):
            continue
        target = _compact(str(operation.get("old_text") or ""))
        if len(target) < 8:
            continue
        if compact_prefix and target.startswith(compact_prefix):
            return compact_prefix, content
    return None


# ---------------------------------------------------------------------------
# Slots, conditions and planning
# ---------------------------------------------------------------------------

_CLASS_NAME_SUFFIXES = ("类基金份额", "类份额", "基金份额", "份额", "类")

# A class name that is not a real identifier (the extractor sometimes writes
# "default" for a contract with a single unnamed class) must never be rendered into
# the document. Such a name is ignored when building the group label (FL-D091).
_PLACEHOLDER_CLASS_NAMES = frozenset({"default", "none", "unknown", "n/a", "na", "其他"})


def class_label(names: Sequence[str]) -> str:
    """Build the guide's class-group label from fact names such as "A", "A类基金份额".

    Contracts name the same class in several ways ("A类基金份额", "A类份额", "A类",
    "A"), so every suffix is stripped before the canonical "A类基金份额" form is
    rebuilt. Missing the "份额" variants produced a doubled label such as
    "A类份额类基金份额" (FL-D091). Placeholder names ("default") are dropped: the
    contract has no such class and the wording must not appear in the document.
    """
    cleaned = []
    for name in names:
        label = name.strip()
        for suffix in _CLASS_NAME_SUFFIXES:
            if label.endswith(suffix) and len(label) > len(suffix):
                label = label[: -len(suffix)]
                break
        if not label or label.lower() in _PLACEHOLDER_CLASS_NAMES:
            continue
        if label not in cleaned:
            cleaned.append(label)
    return "、".join(label + "类" for label in cleaned) + "基金份额"


# The guide expresses the substitution rule with example class letters: the A/B example
# stands for the classes that charge a subscription fee and no service fee, the C/D
# example for the classes that charge a service fee (FL-D042).
_EXAMPLE_GROUP_PATTERNS = (
    (re.compile(r"[AB]类(?:、[AB]类)+基金份额"), "subscription"),
    (re.compile(r"[CD]类(?:、[CD]类)+基金份额"), "service"),
)


def instantiate_slots(text: str, facts: Facts) -> tuple[str, list[str]]:
    issues: list[str] = []
    output = text
    for pattern, group in _EXAMPLE_GROUP_PATTERNS:
        if pattern.search(output):
            names = facts.subscription_group if group == "subscription" else facts.service_group
            if names:
                output = pattern.sub(class_label(names), output)
            else:
                issues.append("SUBSCRIPTION_GROUP_EMPTY" if group == "subscription"
                              else "SERVICE_GROUP_EMPTY")
    if "A类基金份额" in output:
        if facts.subscription_group:
            output = output.replace("A类基金份额", class_label(facts.subscription_group))
        else:
            issues.append("SUBSCRIPTION_GROUP_EMPTY")
    if "C类基金份额" in output:
        if facts.service_group:
            output = output.replace("C类基金份额", class_label(facts.service_group))
        else:
            issues.append("SERVICE_GROUP_EMPTY")
    return output, issues


def _append_without_missing_group(text: str, facts: Facts) -> str | None:
    """Instantiate an append whose wording names a class group the product lacks (FL-D090).

    The guide's append policy mentions the subscription class group and the service-fee
    class group. A product whose classes are A/Y (no service-fee class) still has to
    receive the policy for the classes it does have; the service-fee sentence is simply
    not applicable, so it is dropped rather than aborting the whole append. Returns
    ``None`` when the wording still needs a group after that, so the caller keeps raising
    the original ``RECALL_SLOT_UNRESOLVED``.
    """
    resolved = text
    if "A类基金份额" in resolved:
        if not facts.subscription_group:
            return None
        resolved = resolved.replace("A类基金份额", class_label(facts.subscription_group))
    if "C类基金份额" in resolved:
        if facts.service_group:
            resolved = resolved.replace("C类基金份额", class_label(facts.service_group))
        else:
            # Drop the service-fee sentence(s) that name the missing class and keep the
            # rest, so the appended clause reads as a complete policy for this product.
            kept = [sentence for sentence in re.split(r"(?<=[。；])", resolved)
                    if "C类基金份额" not in sentence]
            resolved = "".join(kept).strip()
            # Removing a trailing clause can leave a dangling separator ("…费用；");
            # close the sentence with a full stop instead.
            resolved = resolved.rstrip("；;，,、") + "。" if resolved else ""
    resolved = resolved.strip()
    return resolved or None


def _missing_slot_groups(rule: dict, operations: Sequence[dict], facts: Facts) -> set[str]:
    """Class groups a rule's required text names but the product does not have.

    The guard is deliberately narrow: only a rule that genuinely substitutes the
    service-fee class group ("C类基金份额") counts, and only when the product has no
    service-fee class at all. A rule whose text needs no group substitution yields an
    empty set, so ordinary rules are never affected.
    """
    missing: set[str] = set()
    if not rule.get("class_substitution"):
        return missing
    for operation in operations:
        text = str(operation.get("new_text") or "")
        if "C类基金份额" in text and not facts.service_group:
            missing.add("service")
    return missing


def _needs_service_class(rule: dict, operations: Sequence[dict], facts: Facts) -> bool:
    """True when a rule's required text introduces sales-service-fee wording.

    Covers both the class-group placeholder ("C类基金份额") and rules that only name the
    fee ("调低…销售服务费率"). Only used to decide out-of-scope when the product has no
    class carrying a sales-service fee, so ordinary fee rules are untouched.
    """
    if facts.service_group:
        return False
    for operation in operations:
        if operation.get("op") != "replace":
            continue
        if "销售服务费" in str(operation.get("new_text") or ""):
            return True
    return False


def _needs_missing_class_group(rule: dict, operations: Sequence[dict], facts: Facts) -> bool:
    """True when the rule cannot be carried out because a class group is missing.

    The class-substitution out-of-scope gate exists because re-writing a class group
    requires that group to exist. A **pure append** does not re-group anything — it adds
    the policy text wholesale, and ``plan_target``'s append path drops the sentence naming
    a class the product lacks — so a rule whose only applicable operation is an append is
    never out of scope on this ground (FL-D090).
    """
    carried = [operation for operation in operations if operation.get("op") != "noop"]
    if carried and all(operation.get("op") == "append" for operation in carried):
        return False
    for operation in operations:
        if operation.get("op") == "append":
            continue
        if "C类基金份额" in str(operation.get("new_text") or ""):
            return True
    return bool(rule.get("class_substitution")) and fee_homogeneous_classes(facts)


def _drop_empty_group_operations(rule: dict, operations: Sequence[dict],
                                 facts: Facts) -> list[dict]:
    """Drop the operations whose replacement needs a class group the product lacks.

    A group-substitution rule normally rewrites the subscription class group and the
    service-fee class group. When the product has no service-fee class there is nothing
    to rewrite on that side, so that operation is dropped and the remaining substitution
    still applies; dropping only affects rules that carry the service-fee placeholder.
    """
    if not rule.get("class_substitution") or facts.service_group:
        return list(operations)
    # An append is never dropped here: ``plan_target``'s append path handles a missing
    # service-fee class by dropping only the sentence that names it (FL-D090), so removing
    # the whole operation would silently lose the obligation.
    kept = [operation for operation in operations
            if operation.get("op") == "append"
            or "C类基金份额" not in str(operation.get("new_text") or "")]
    return kept


def slot_group_missing(rule: dict, operations: Sequence[dict], facts: Facts) -> bool:
    """True when a class-substitution rule needs a class group the product lacks.

    A product with no sales-service-fee class has no C-class clause to rewrite, so the
    sales-service-fee rules do not apply to it. Without this gate ``instantiate_slots``
    reports ``SERVICE_GROUP_EMPTY`` and the run stops with ``RECALL_SLOT_UNRESOLVED`` on
    a rule that should simply be out of scope (FL-D056). A fee-homogeneous product (all
    classes share one fee profile) has no group for the substitution to select either.
    """
    if _missing_slot_groups(rule, operations, facts):
        return True
    if _needs_service_class(rule, operations, facts):
        # The replacement introduces sales-service-fee wording the product cannot carry.
        return True
    return bool(rule.get("class_substitution")) and fee_homogeneous_classes(facts)


def fee_homogeneous_classes(facts: Facts) -> bool:
    """True when every current share class shares the same fee profile.

    Such a product (for example classes divided by sales account rather than by fee rule)
    has no subscription-fee group versus service-fee group split, so the guide's grouping
    substitution cannot select a distinct group. Rewriting the labels would corrupt the
    clause, so the class-substitution rules are treated as out of scope instead.
    """
    profiles = {(bool(item.subscription_fee), bool(item.service_fee))
                for item in facts.current_classes}
    return len(profiles) <= 1


def class_substitution_noop(rule: dict, facts: Facts) -> bool:
    """True when a share-class substitution rule requires no change for this product.

    The guide writes the class-substitution rules (G02/G04) with example letters
    ("A类基金份额" -> "A类、B类基金份额"). ``instantiate_slots`` maps them onto the classes
    the product actually has. When each instantiated replacement equals its reference —
    i.e. the product's own class letters already are the group the rule asks for — the
    clause is already correct and no edit may be planned (FL-D052).
    """
    if not rule.get("class_substitution"):
        return False
    if fee_homogeneous_classes(facts):
        # No fee-rule split exists, so the guide's group substitution selects nothing;
        # leave the clause as it is (FL-D056).
        return True
    checked = False
    for operation in rule.get("operations") or []:
        if not condition_matches(operation.get("condition"), facts):
            continue
        if operation.get("op") not in {"replace", "append"}:
            continue
        instantiated, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        if issues or not instantiated:
            return False
        checked = True
        if _compact(instantiated) != _compact(str(operation.get("old_text") or "")):
            return False
    return checked


def condition_matches(condition: dict | None, facts: Facts) -> bool:
    if not condition:
        return True
    kind = condition.get("kind")
    value = condition.get("value")
    if kind == "none":
        return True
    if kind == "class_count":
        if value == 1:
            return facts.class_count == 1
        if value == "multiple":
            return facts.class_count > 1
        return False
    if kind == "has_service_fee":
        return bool(value) == facts.has_service_fee
    if kind == "is_floating_fee":
        return bool(value) == facts.floating_management_fee
    if kind == "compound":
        return all(condition_matches(part, facts) for part in value or [])
    return False


@dataclass
class PlannedEdit:
    target_id: str
    rule_id: str
    location: str
    start: int
    end: int
    replacement: str
    operation: str
    content_source: str
    evidence: dict[str, Any]
    anchor_sha256: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "rule_id": self.rule_id, "location": self.location,
            "start": self.start, "end": self.end, "replacement": self.replacement,
            "operation": self.operation, "content_source": self.content_source,
            "evidence": self.evidence, "anchor_sha256": self.anchor_sha256,
        }


def _same_compact(left: str, right: str) -> bool:
    return _compact(left) == _compact(right)


def _splice_fragment(actual: str, old_text: str, new_text: str) -> str | None:
    """Deterministically replace one fragment inside the actual span, keeping the rest.

    The fragment is spliced in the middle of the span, so the kept lead/suffix may end or
    begin without sentence punctuation. When ``new_text`` is authorized policy prose, glue
    it to the kept text with the same separator the append path uses — otherwise a contract
    that leaves a clause unterminated ("…本基金 A 类基金份额的") runs the two sentences
    together ("…份额的通过直销机构申购…", FL-D067). A deletion (``new_text`` empty) keeps
    the kept text verbatim and inserts nothing.
    """
    cleaned, index_map = display_text(actual)
    located = find_normalized(cleaned, old_text)
    if located is None:
        return None
    start_clean, end_clean = located
    start_raw, end_raw = index_map[start_clean], index_map[end_clean - 1] + 1
    prefix, suffix = actual[:start_raw], actual[end_raw:]
    if not new_text:
        return prefix + suffix
    return (prefix + append_separator(prefix, new_text) + new_text
            + append_separator(new_text, suffix) + suffix)


def _composite_reference(rule: dict, facts: Facts, target: Target,
                         inspection: DocumentInspection) -> tuple[str, tuple[str, ...]] | None:
    """The operation reference text a composite target belongs to, plus its parts."""
    span = inspection.by_location(target.location)
    for operation in rule.get("operations") or []:
        if not condition_matches(operation.get("condition"), facts):
            continue
        old_text = str(operation.get("old_text") or "")
        if len(_compact(old_text)) < 8:
            continue
        if _compact(target.quote) and _compact(target.quote) in _compact(old_text):
            return old_text, target.composite or (target.location,)
    return None


def plan_composite_target(rule: dict, target: Target, inspection: DocumentInspection, facts: Facts,
                          *, new_text: str) -> list[PlannedEdit]:
    """Turn a composite (multi-paragraph) reference into one edit per paragraph.

    ``target.composite`` holds ``location:start:end`` items measured in each
    paragraph's whitespace-free text (the survey found them deterministically), so
    each part deletes or replaces only its own slice and keeps the rest verbatim.
    """
    if not target.composite:
        raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
    parts: list[tuple[str, int, int]] = []
    for item in target.composite:
        try:
            location, start_text, end_text = item.rsplit(":", 2)
            parts.append((location, int(start_text), int(end_text)))
        except ValueError:
            raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
    edits: list[PlannedEdit] = []
    for index, (location, start_clean, end_clean) in enumerate(parts):
        span = inspection.by_location(location)
        # ``composite`` offsets are measured in the paragraph's whitespace-free text
        # (find_old_text_all), so they must be mapped back through the compact index,
        # not through display_text's raw map (FL-D052).
        compact_body, compact_map = compact_offsets(span.text)
        if start_clean < 0 or end_clean > len(compact_body) or start_clean >= end_clean:
            raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
        start_raw = compact_map[start_clean]
        end_raw = compact_map[end_clean - 1] + 1
        # A deletion keeps everything outside this part's slice of the reference; a
        # replacement inserts the new text at the anchor and keeps the rest verbatim.
        if new_text and index == 0:
            # The kept prefix or suffix may end/begin without sentence punctuation (a
            # contract often leaves a clause like "…称为 C 类基金份额" unterminated);
            # joining the authorized policy text directly would run the words together.
            # Put the same separator the append path uses between the kept text and the
            # new text so the result reads as separate sentences (FL-D067).
            prefix, suffix = span.text[:start_raw], span.text[end_raw:]
            replacement = (prefix + append_separator(prefix, new_text) + new_text
                           + append_separator(new_text, suffix) + suffix)
            content_source = "composite_replace"
        else:
            replacement = span.text[:start_raw] + span.text[end_raw:]
            content_source = "composite_delete"
        edits.append(PlannedEdit(
            target_id=target.target_id, rule_id=target.rule_id, location=location,
            start=start_raw, end=end_raw, replacement=replacement, operation="replace",
            content_source=content_source,
            evidence={"composite": True, "unit": target.rule_id, "parts": list(target.composite),
                      "part_index": index}))
    if not edits:
        raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
    return edits


def append_separator(left: str, right: str) -> str:
    """Separate an appended sentence without altering the authorized policy text."""
    left, right = left.rstrip(), right.lstrip()
    if not left or not right:
        return ""
    # Sentence punctuation inside a closing quote/bracket already terminates it.
    tail = left.rstrip('”’」』）)】]》')
    if tail and tail[-1] in '。！？；：，、.!?;:,':
        return ""
    if right[0] in '。！？；：，、.!?;:,':
        return ""
    return "。"


def plan_target(rule: dict, target: Target, inspection: DocumentInspection, facts: Facts,
                gateway: Any, *, compose_budget: list[int]) -> PlannedEdit | None:
    """Turn one needs_edit target into a concrete edit, or raise RecallError."""
    operations = [operation for operation in (rule.get("operations") or [])
                  if condition_matches(operation.get("condition"), facts)]
    if not operations:
        # The rule's own condition does not hold for this product (a single-class
        # branch on a multi-class contract, a floating-fee branch on a fixed-fee one):
        # the rule does not apply here, which is not a failure.
        raise RecallError("RECALL_RULE_NOT_APPLICABLE", {"rule": rule["rule_id"]})
    if slot_group_missing(rule, operations, facts) and _needs_missing_class_group(rule, operations, facts):
        # A group-substitution rule needs both groups to re-group the classes. When the
        # product lacks the service-fee group (or all its classes share one fee profile)
        # there is no grouping to apply, so the rule is out of scope as a whole; keeping
        # its remaining half would call instantiate_slots on the C-class placeholder and
        # fail with RECALL_SLOT_UNRESOLVED (FL-D056).
        #
        # A **pure append** is different: the policy text is added wholesale and no
        # existing class is re-grouped, so a contract whose classes are A/Y (no C
        # service-fee class) still has to receive the appended clause. Aborting there
        # dropped the obligation entirely (FL-D090, D07).
        raise RecallError("RECALL_RULE_NOT_APPLICABLE",
                          {"rule": rule["rule_id"],
                           "groups": sorted(_missing_slot_groups(rule, operations, facts))})
    if slot_group_missing(rule, operations, facts):
        operations = _drop_empty_group_operations(rule, operations, facts)
    if not operations:
        # Every operation needed a class group this product does not have.
        raise RecallError("RECALL_RULE_NOT_APPLICABLE",
                          {"rule": rule["rule_id"], "groups": sorted(_missing_slot_groups(
                              rule, rule.get("operations") or [], facts))})
    if target.resolution != "resolved" or target.start is None or target.end is None:
        # Out-of-scope rules are decided above; a resolved-scope target that cannot bind
        # to the contract text is a genuine unresolved failure.
        raise RecallError("RECALL_TARGET_UNRESOLVED", {"target": target.target_id})
    span = inspection.by_location(target.location)
    if not containing_segment(span, target.start, target.end) and not (target.start == target.end):
        raise RecallError("RECALL_TARGET_STRUCTURE", {"target": target.target_id})
    actual = span.text[target.start:target.end]
    append_ops = [operation for operation in operations if operation.get("op") == "append"]
    delete_ops = [operation for operation in operations if operation.get("op") == "delete"]
    replace_ops = [operation for operation in operations if operation.get("op") == "replace"]
    noop_ops = [operation for operation in operations if operation.get("op") == "noop"]
    if noop_ops and not (append_ops or delete_ops or replace_ops):
        return None  # branch explicitly requires no change
    if append_ops:
        operation = append_ops[0]
        new_text, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        if issues or not new_text.strip():
            # The guide's append wording names an assumed class group ("C类基金份额"). A
            # product with no service-fee class still receives the appended policy — the
            # sentence is added wholesale and names no existing class it must re-group —
            # so an unfillable class placeholder must not abort the append (FL-D090).
            fallback = _append_without_missing_group(str(operation.get("new_text") or ""), facts)
            if fallback is None:
                raise RecallError("RECALL_SLOT_UNRESOLVED", {"rule": rule["rule_id"], "issues": issues})
            new_text, issues = fallback, []
        prefix = append_separator(span.text[:target.end], new_text)
        return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"], location=target.location,
                           start=target.end, end=target.end, replacement=prefix + new_text, operation="insert",
                           content_source="guide_text",
                           evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                     "slots": list(rule.get("slot_tokens") or []),
                                     "fixed_text": new_text,
                                     "join_separator": prefix,
                                     "issues": issues})
    # Several operations of one rule can apply to the SAME span: G05 both replaces
    # "调低赎回费率" with "调低销售服务费率" and deletes "并报中国证监会备案" inside one
    # sentence. Applying only the first match silently dropped the replacement (FL-D052),
    # so every deterministic fragment operation is accumulated onto one replacement.
    spliced = actual
    applied: list[str] = []
    for operation in [*delete_ops, *replace_ops]:
        op_kind = operation.get("op")
        old_text = str(operation.get("old_text") or "")
        if op_kind == "delete":
            new_fragment = ""
        else:
            new_fragment, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
            if issues:
                raise RecallError("RECALL_SLOT_UNRESOLVED", {"rule": rule["rule_id"], "issues": issues})
        if _same_compact(old_text, spliced):
            spliced = new_fragment
            applied.append(f"{op_kind}:full")
            continue
        updated = _splice_fragment(spliced, old_text, new_fragment)
        if updated is not None:
            spliced = updated
            applied.append(f"{op_kind}:fragment")
    if applied:
        if _same_compact(spliced, actual):
            return None  # already satisfied
        sources = {item.split(":", 1)[0] for item in applied}
        content_source = ("fragment_delete" if sources == {"delete"}
                          else "fragment_replace" if sources == {"replace"}
                          else "fragment_mixed")
        return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"], location=target.location,
                           start=target.start, end=target.end, replacement=spliced,
                           operation="replace", content_source=content_source,
                           evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                     "applied": applied})
    # A delete-only rule whose reference text runs across several sentences or
    # paragraphs (G17 concatenates "…基金份额持有人服务费等。" with "…不包括基金募集期间
    # 的上述费用。"): one target carries one sentence of it verbatim and nothing else.
    # The reference can never match that single-sentence span, so the composer is asked to
    # trim a span it can only leave unchanged and fails with DELETE_NOT_SHRINKING. When the
    # target span is exactly the target quote and that quote is a genuine part of the
    # rule's delete reference, the whole span is the material to remove (FL-D052).
    if delete_ops and not replace_ops and not append_ops:
        quote_compact = _compact(target.quote)
        reference_compact = "".join(_compact(str(operation.get("old_text") or ""))
                                    for operation in delete_ops)
        if (quote_compact and len(quote_compact) >= VARIANT_MIN_CHARS
                and quote_compact == _compact(actual)
                and quote_compact in reference_compact):
            return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"],
                               location=target.location, start=target.start, end=target.end,
                               replacement="", operation="replace", content_source="variant_delete",
                               evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                         "deleted_quote": target.quote})
    # A bounded wording variant of the reference text ("由于基金费用的不同" against the
    # guide's "由于本基金A类基金份额不收取销售服务费，而C类基金份额收取销售服务费"):
    # the variant span itself is deleted. The engine edits only real document text and
    # records the similarity ratio as evidence (FL-D047).
    for operation in delete_ops:
        old_text = str(operation.get("old_text") or "")
        if _same_compact(old_text, actual) or len(_compact(old_text)) < VARIANT_MIN_CHARS:
            continue
        variant = fuzzy_span_clause(actual, old_text, threshold=VARIANT_MATCH_RATIO)
        if variant is None:
            continue
        start_raw, end_raw, ratio = variant
        replacement = actual[:start_raw] + actual[end_raw:]
        if _same_compact(replacement, actual):
            continue
        return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"], location=target.location,
                           start=target.start, end=target.end, replacement=replacement,
                           operation="replace", content_source="variant_delete",
                           evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                     "matched_old_text": old_text, "variant_ratio": round(ratio, 3)})
    for operation in replace_ops:
        old_text = str(operation.get("old_text") or "")
        instantiated, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        if issues:
            raise RecallError("RECALL_SLOT_UNRESOLVED", {"rule": rule["rule_id"], "issues": issues})
        if len(_compact(old_text)) < VARIANT_MIN_CHARS:
            continue
        variant = fuzzy_span_clause(actual, old_text, threshold=VARIANT_MATCH_RATIO)
        if variant is None:
            continue
        start_raw, end_raw, ratio = variant
        replacement = actual[:start_raw] + instantiated + actual[end_raw:]
        if _same_compact(replacement, actual):
            continue
        return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"], location=target.location,
                           start=target.start, end=target.end, replacement=replacement,
                           operation="replace", content_source="variant_replace",
                           evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                     "matched_old_text": old_text, "fixed_text": instantiated,
                                     "variant_ratio": round(ratio, 3)})
    variants = [str(value) for value in (rule.get("old_text_variants") or [])]
    for operation in replace_ops:
        variants.append(str(operation.get("old_text") or ""))
    if compose_budget[0] <= 0:
        raise RecallError("RECALL_COMPOSE_BUDGET_EXHAUSTED", {"target": target.target_id})
    compose_budget[0] -= 1
    if replace_ops:
        # The contract's wording differs from the guide reference: compose text that
        # keeps the fixed policy text verbatim and preserves the untouched elements.
        base = replace_ops[0]
        instantiated, issues = instantiate_slots(str(base.get("new_text") or ""), facts)
        if issues:
            raise RecallError("RECALL_SLOT_UNRESOLVED", {"rule": rule["rule_id"], "issues": issues})
        composed = compose_variant(span, target, rule, actual, instantiated, facts, gateway,
                                   mode="replace", variants=variants)
        return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"], location=target.location,
                           start=target.start, end=target.end, replacement=composed["replacement"],
                           operation="replace", content_source="composed",
                           evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                     "fixed_text": instantiated, "preserved": composed["preserved"],
                                     "basis": composed["basis"]})
    if delete_ops:
        # A deletion whose reference text differs from the contract's wording: the model
        # trims the actual span down to what the guide keeps (often nothing).
        try:
            composed = compose_variant(span, target, rule, actual, "", facts, gateway,
                                       mode="delete", variants=variants)
        except RecallError as exc:
            # The survey bound the whole clause as this target and the contract's wording
            # differs from the guide reference ("C类基金份额的销售服务费每日计提…" against
            # "基金销售服务费每日计提…"), so the composer cannot match the text to trim and
            # reports DELETE_NOT_SHRINKING. When the whole paragraph body is that clause and
            # the rule only deletes, the paragraph is the material to remove (FL-D052).
            if (exc.code == "RECALL_COMPOSE_DELETE_NOT_SHRINKING"
                    and _same_compact(actual, span.text) and _compact(actual)):
                return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"],
                                   location=target.location, start=target.start, end=target.end,
                                   replacement="", operation="replace",
                                   content_source="whole_paragraph_delete",
                                   evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                             "deleted_paragraph": _clip(target.quote, 120)})
            # Only part of the paragraph is this clause (a fee paragraph that also carries
            # the appended policy text). The survey already bound exactly the material to
            # remove, so drop that sub-span and keep the rest verbatim (FL-D063). The
            # composer could not match the reference wording to trim it, but the bound span
            # is authoritative.
            if (exc.code == "RECALL_COMPOSE_DELETE_NOT_SHRINKING"
                    and 0 <= target.start < target.end <= len(span.text)):
                remainder = span.text[:target.start] + span.text[target.end:]
                if _compact(remainder) != _compact(span.text):
                    return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"],
                                       location=target.location, start=target.start,
                                       end=target.end, replacement="",
                                       operation="replace", content_source="target_span_delete",
                                       evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                                 "deleted_span": _clip(target.quote, 120)})
            raise
        return PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"], location=target.location,
                           start=target.start, end=target.end, replacement=composed["replacement"],
                           operation="replace", content_source="composed_delete",
                           evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                     "delete_texts": [str(op.get("old_text") or "") for op in delete_ops],
                                     "preserved": composed["preserved"], "basis": composed["basis"]})
    raise RecallError("RECALL_TARGET_VARIANT_UNMATCHED", {"target": target.target_id,
                                                          "actual": _clip(actual, 120)})


def _is_subsequence(shorter: str, longer: str) -> bool:
    iterator = iter(longer)
    return all(char in iterator for char in shorter)


def compose_variant(span: ParagraphSpan, target: Target, rule: dict, actual: str,
                    fixed_text: str, facts: Facts, gateway: Any, *, mode: str = "replace",
                    variants: Sequence[str] | None = None) -> dict[str, Any]:
    window_start = max(0, target.start - 400)
    window_end = min(len(span.text), (target.end or 0) + 400)
    cleaned_before, _ = display_text(span.text[window_start:target.start])
    cleaned_target, _ = display_text(actual)
    cleaned_after, _ = display_text(span.text[target.end:window_end])
    operation: dict[str, Any] = {
        "rule_id": rule["rule_id"], "title": rule["title"], "requirement": rule.get("requirement"),
        "reference_old_texts": (list(variants) if variants else (rule.get("old_text_variants") or []))[:6],
    }
    if mode == "replace":
        operation["fixed_policy_text"] = fixed_text
        operation["slots"] = rule.get("slot_tokens") or []
        instruction = COMPOSE_INSTRUCTION
    else:
        operation["delete_texts"] = [str(op.get("old_text") or "")
                                     for op in (rule.get("operations") or []) if op.get("op") == "delete"]
        instruction = COMPOSE_DELETE_INSTRUCTION
    base_context = "\n\n".join([
        f"CONTRACT_TARGET\n[{target.location}] {cleaned_target}",
        f"CONTRACT_SURROUNDING\nBEFORE: {cleaned_before}\nAFTER: {cleaned_after}",
        "GUIDE_OPERATION\n" + json.dumps(operation, ensure_ascii=False, indent=1),
        "FACTS\n" + json.dumps(facts.as_ledger(), ensure_ascii=False, indent=1),
    ])
    attempts = 2 if mode == "delete" else 1
    last_error: RecallError | None = None
    for attempt in range(attempts):
        context = base_context
        if attempt:
            context = base_context + (
                "\n\n[RETRY_NOTE]\n上一次回答没有删减目标文本。请删除指引要求删除的内容，只保留"
                "指引不要求删除的部分；整句删除时 replacement 必须为空字符串。")
        if len(context) > gateway.max_context_chars:
            raise RecallError("RECALL_COMPOSE_CONTEXT_LIMIT", {"target": target.target_id})
        result = gateway.call(task_type="recall_compose", bounded_context=context,
                              response_schema=COMPOSE_SCHEMA, instruction=instruction,
                              prompt_version=COMPOSE_PROMPT_VERSION)
        value = result.value if isinstance(result.value, dict) else {}
        replacement = str(value.get("replacement") or "").strip()
        preserved = [str(item) for item in (value.get("preserved") or []) if isinstance(item, str)]
        basis = str(value.get("basis") or "")
        verified_preserved = [item for item in preserved
                              if item.strip() and (compact_in(item, actual) or compact_in(item, replacement))]
        unverified_preserved = [item for item in preserved if item.strip() and item not in verified_preserved]
        new_digits = set(re.findall(r"\d+(?:\.\d+)?%?", replacement)) \
            - set(re.findall(r"\d+(?:\.\d+)?%?", actual)) \
            - set(re.findall(r"\d+(?:\.\d+)?%?", fixed_text))
        if mode == "delete":
            if replacement:
                if not _is_subsequence(_compact(replacement), _compact(actual)):
                    last_error = RecallError("RECALL_COMPOSE_DELETE_ADDED_TEXT",
                                             {"target": target.target_id,
                                              "replacement": _clip(replacement, 80)})
                elif len(_compact(replacement)) >= len(_compact(actual)):
                    last_error = RecallError("RECALL_COMPOSE_DELETE_NOT_SHRINKING",
                                             {"target": target.target_id})
            if new_digits:
                last_error = RecallError("RECALL_COMPOSE_NEW_NUMBERS",
                                         {"target": target.target_id,
                                          "numbers": sorted(new_digits)[:6]})
            if last_error is None:
                return {"replacement": replacement, "preserved": verified_preserved,
                        "preserved_unverified": unverified_preserved, "basis": basis}
            if attempt + 1 >= attempts:
                raise last_error
            continue
        if not replacement:
            raise RecallError("RECALL_COMPOSE_EMPTY", {"target": target.target_id})
        if not compact_in(fixed_text, replacement):
            raise RecallError("RECALL_COMPOSE_FIXED_TEXT_MISSING",
                              {"target": target.target_id, "fixed_text": _clip(fixed_text, 80)})
        if new_digits:
            raise RecallError("RECALL_COMPOSE_NEW_NUMBERS",
                              {"target": target.target_id, "numbers": sorted(new_digits)[:6]})
        return {"replacement": replacement, "preserved": verified_preserved,
                "preserved_unverified": unverified_preserved, "basis": basis}
    raise last_error or RecallError("RECALL_COMPOSE_EMPTY", {"target": target.target_id})


def _component(edit: PlannedEdit, inspection: DocumentInspection) -> dict[str, Any]:
    span = inspection.by_location(edit.location)
    return {
        "target_id": edit.target_id, "rule_id": edit.rule_id, "location": edit.location,
        "start": edit.start, "end": edit.end, "replacement": edit.replacement,
        "operation": edit.operation, "content_source": edit.content_source,
        "evidence": edit.evidence,
        "expected_old_text": span.text[edit.start:edit.end],
    }


def _component_covered(component: dict[str, Any], outer_replacement: str) -> bool:
    """True when the outer edit's replacement already carries out the inner operation."""
    evidence = component.get("evidence") or {}
    fixed = str(evidence.get("fixed_text") or "")
    if fixed:
        return compact_in(fixed, outer_replacement)
    if component.get("content_source") in {"guide_text", "composed_delete"}:
        expected = str(component.get("expected_old_text") or "")
        if expected and not compact_in(expected, outer_replacement):
            return True
    return False


def merge_edits(edits: Sequence[PlannedEdit], inspection: DocumentInspection
                ) -> tuple[list[tuple[PlannedEdit, list[dict[str, Any]]]], list[dict[str, Any]],
                           list[str]]:
    """Merge adjacent edits per location; absorb contained edits; flag real overlaps.

    Merged edits keep their original components so the content check can still
    verify every piece against the source text. A contained edit whose operation is
    already carried out by the outer replacement is recorded as covered, not dropped.
    """
    conflicts: list[dict[str, Any]] = []
    covered: list[str] = []
    merged: list[tuple[PlannedEdit, list[dict[str, Any]]]] = []
    by_location: dict[str, list[PlannedEdit]] = {}
    for edit in edits:
        by_location.setdefault(edit.location, []).append(edit)
    for location, items in by_location.items():
        items = sorted(items, key=lambda item: (item.start, item.end))
        current: PlannedEdit | None = None
        current_components: list[dict[str, Any]] = []
        for item in items:
            if current is None:
                current = item
                current_components = [_component(item, inspection)]
                continue
            if item.start > current.end:
                merged.append((current, current_components))
                current = item
                current_components = [_component(item, inspection)]
                continue
            if item.start == current.end:
                merged_start, merged_end = current.start, item.end
                current_components = current_components + [_component(item, inspection)]
                current = PlannedEdit(
                    target_id=current.target_id + "+" + item.target_id,
                    rule_id=current.rule_id + "+" + item.rule_id,
                    location=location, start=merged_start, end=merged_end,
                    replacement=current.replacement + item.replacement,
                    operation="insert" if merged_start == merged_end else "replace",
                    content_source="merged",
                    evidence={"merged": [current.evidence, item.evidence]},
                )
                continue
            item_component = _component(item, inspection)
            if item.start >= current.start and item.end <= current.end:
                # contained edit: keep the outer replacement when it already covers it
                if _component_covered(item_component, current.replacement):
                    covered.append(item.target_id)
                    continue
            current_component = _component(current, inspection)
            if current.start >= item.start and current.end <= item.end:
                if _component_covered(current_component, item.replacement):
                    covered.append(current.target_id)
                    current = item
                    current_components = [item_component]
                    continue
            conflicts.append({"code": "RECALL_EDIT_OVERLAP", "location": location,
                              "targets": [current.target_id, item.target_id],
                              "spans": [[current.start, current.end], [item.start, item.end]]})
            merged.append((current, current_components))
            current = item
            current_components = [item_component]
        if current is not None:
            merged.append((current, current_components))
    return merged, conflicts, covered


def plan_edits(rules_by_id: dict[str, dict], targets: Sequence[Target], inspection: DocumentInspection,
               facts: Facts, gateway: Any, *, max_compose_calls: int = 6) -> dict[str, Any]:
    """Build the edit list, isolating per-target failures into the ledger."""
    planned: list[PlannedEdit] = []
    ledger: list[dict[str, Any]] = []
    compose_budget = [max_compose_calls]
    for target in targets:
        if target.state != "needs_edit":
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": "satisfied" if target.state == "satisfied" else "not_applicable",
                           "reason": target.reason})
            continue
        rule = rules_by_id.get(target.rule_id)
        if rule is None:
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": "unresolved", "reason": "RULE_NOT_FOUND"})
            continue
        try:
            if target.composite:
                replacement = ""
                applicable_ops = [operation for operation in rule.get("operations") or []
                                  if operation.get("op") == "replace"
                                  and condition_matches(operation.get("condition"), facts)]
                if slot_group_missing(rule, applicable_ops, facts):
                    raise RecallError("RECALL_RULE_NOT_APPLICABLE",
                                      {"rule": rule["rule_id"], "groups": ["service"]})
                for operation in applicable_ops:
                    replacement, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
                    if issues:
                        raise RecallError("RECALL_SLOT_UNRESOLVED",
                                          {"rule": rule["rule_id"], "issues": issues})
                    break
                composite_edits = plan_composite_target(rule, target, inspection, facts,
                                                        new_text=replacement)
                planned.extend(composite_edits)
                ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                               "status": "planned",
                               "operation": composite_edits[0].operation,
                               "parts": [edit.location for edit in composite_edits]})
                continue
            edit = plan_target(rule, target, inspection, facts, gateway, compose_budget=compose_budget)
        except RecallError as exc:
            status = "not_applicable" if exc.code == "RECALL_RULE_NOT_APPLICABLE" else "unresolved"
            if status == "not_applicable":
                target.out_of_scope = True
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": status, "reason": exc.code, "detail": exc.detail})
            continue
        except ModelError as exc:
            if exc.code in _STOP_CODES:
                # A transport/budget stop must pause the whole run, not silently mark
                # one target unresolved (the worker resumes from the checkpoint).
                from .recall_pipeline import RecallPipelineStop
                raise RecallPipelineStop(exc.code, {"stage": "plan", "rule": target.rule_id}) from exc
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": "unresolved", "reason": f"MODEL:{exc.code}"})
            continue
        if edit is None:
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": "satisfied", "reason": "already_satisfied"})
            continue
        planned.append(edit)
        ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                       "status": "planned", "operation": edit.operation})
    merged, conflicts, covered = merge_edits(planned, inspection)
    conflict_ids = {target_id for conflict in conflicts for target_id in conflict["targets"]}
    for entry in ledger:
        if entry.get("target_id") in conflict_ids:
            entry["status"] = "unresolved"
            entry["reason"] = "RECALL_EDIT_OVERLAP"
        elif entry.get("target_id") in covered and entry.get("status") == "planned":
            entry["status"] = "satisfied"
            entry["reason"] = "RECALL_COVERED_BY_OUTER"
    def _conflicted(edit: PlannedEdit, components: list[dict[str, Any]]) -> bool:
        ids = {str(component.get("target_id")) for component in components}
        ids.add(edit.target_id)
        return any(identifier in conflict_ids for identifier in ids)
    merged = [(edit, components) for edit, components in merged if not _conflicted(edit, components)]
    records: list[dict[str, Any]] = []
    for edit, components in merged:
        records.append({**edit.as_dict(), "components": components})
    return {"edits": records, "ledger": ledger, "conflicts": conflicts,
            "covered": sorted(covered)}


def build_docx_edits(planned: Sequence[Any], inspection: DocumentInspection) -> list[dict[str, Any]]:
    """Convert planned edits into docx.validate_edit_plan edit dictionaries.

    ``planned`` may hold either the plain dictionaries produced by the planner or the
    ``PlannedEdit`` objects from ``plan_target`` (the tests pass the latter directly), so
    both are accepted and normalised here.
    """
    edits: list[dict[str, Any]] = []
    for item in planned:
        if not isinstance(item, dict):
            item = item.as_dict()
        span = inspection.by_location(item["location"])
        start, end = int(item["start"]), int(item["end"])
        replacement = str(item["replacement"])
        edit: dict[str, Any] = {
            "edit_id": f"{item['rule_id']}:{item['target_id']}",
            "location": item["location"],
            "zone": span.zone,
            "mapping_version": span.mapping_version,
            "fingerprint": span.fingerprint,
            "source_sha256": inspection.source_sha256,
            "start": start,
            "end": end,
            "expected_old_text": span.text[start:end],
            "expected_old_hash": _sha256(span.text[start:end]),
            "replacement": replacement,
            "content_source": "generated",
            "verified": True,
            "rule_id": item["rule_id"],
            "target_id": item["target_id"],
            "operation": item["operation"],
            "components": item.get("components") or [],
        }
        if item["operation"] == "insert":
            anchor_start = max(0, start - 1)
            anchor_text = span.text[anchor_start:start]
            if not anchor_text:
                continue
            edit["anchor"] = {
                "start": anchor_start, "end": start, "text": anchor_text,
                "sha256": _sha256(anchor_text),
            }
        edits.append(edit)
    return edits


def _sha256(value: str) -> str:
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _composite_part_slice(component: dict[str, Any], span: ParagraphSpan
                         ) -> tuple[int, int] | None:
    """Raw offsets of this composite part's slice inside its own paragraph."""
    evidence = component.get("evidence") or {}
    parts = evidence.get("parts") or []
    index = evidence.get("part_index")
    if not isinstance(index, int) or index < 0 or index >= len(parts):
        return None
    try:
        _location, start_text, end_text = str(parts[index]).rsplit(":", 2)
        start_clean, end_clean = int(start_text), int(end_text)
    except (ValueError, AttributeError):
        return None
    _cleaned, index_map = display_text(span.text)
    if start_clean < 0 or end_clean > len(index_map) or start_clean >= end_clean:
        return None
    return index_map[start_clean], index_map[end_clean - 1] + 1


def _component_ok(component: dict[str, Any], inspection: DocumentInspection) -> bool:
    try:
        span = inspection.by_location(str(component.get("location")))
    except KeyError:
        return False
    start, end = int(component.get("start", -1)), int(component.get("end", -1))
    if start < 0 or end < start or end > len(span.text):
        return False
    expected = component.get("expected_old_text")
    if isinstance(expected, str) and expected != span.text[start:end]:
        return False
    replacement = str(component.get("replacement") or "")
    evidence = component.get("evidence") or {}
    content_source = component.get("content_source")
    if content_source == "fragment_delete":
        deleted = str(evidence.get("deleted_fragment") or "")
        if deleted and compact_in(deleted, replacement):
            return False
        if len(_compact(replacement)) >= len(_compact(expected or "")):
            return False
        if _splice_fragment(expected or "", deleted, "") != replacement:
            return False
        return True
    if content_source == "fragment_replace":
        fixed = str(evidence.get("fixed_text") or "")
        matched = str(evidence.get("matched_old_text") or "")
        if not fixed or not matched:
            return False
        if _splice_fragment(expected or "", matched, fixed) != replacement:
            return False
        return True
    if content_source == "composed_delete":
        if replacement:
            if not _is_subsequence(_compact(replacement), _compact(expected or "")):
                return False
            if len(_compact(replacement)) >= len(_compact(expected or "")):
                return False
        return True
    if content_source in {"variant_delete", "variant_replace"}:
        # The whole variant span is the target span: verify the recorded ratio by
        # re-running the same bounded fuzzy match (FL-D047).
        matched = str(evidence.get("matched_old_text") or "")
        actual = expected or ""
        if len(_compact(matched)) < VARIANT_MIN_CHARS:
            return False
        variant = fuzzy_span_clause(actual, matched, threshold=VARIANT_MATCH_RATIO) if matched and actual else None
        if variant is None:
            return False
        recorded = evidence.get("variant_ratio")
        if isinstance(recorded, (int, float)) and abs(variant[2] - float(recorded)) > 0.01:
            return False
        start_raw, end_raw, _ratio = variant
        fixed = str(evidence.get("fixed_text") or "")
        if content_source == "variant_replace":
            if not fixed:
                return False
            return actual[:start_raw] + fixed + actual[end_raw:] == replacement
        return actual[:start_raw] + actual[end_raw:] == replacement
    if content_source in {"composite_delete", "composite_replace"}:
        # A composite part deletes only its own slice of the reference text inside one
        # paragraph and keeps the rest of that paragraph verbatim (FL-D047).
        if not expected or replacement == expected:
            return False
        unit = str(evidence.get("unit") or "")
        anchor = str((component.get("parts") or [None])[0] or "")
        if unit and anchor and str(component.get("location")) != anchor.split(":")[0]:
            # follower parts carry no prefix of their own before the reference
            return replacement == "" or replacement == expected
        deleted = _composite_part_slice(component, span)
        if deleted is None or not deleted:
            return False
        start_offset, end_offset = deleted
        prefix, suffix = expected[:start_offset], expected[end_offset:]
        if content_source == "composite_delete":
            return replacement == prefix + suffix
        fixed = str(evidence.get("fixed_text") or "")
        if not fixed or not compact_in(fixed, replacement) and fixed not in replacement:
            return False
        return replacement.startswith(prefix) and replacement.endswith(suffix)
    if content_source in {"guide_text", "composed"}:
        fixed = str(evidence.get("fixed_text") or "")
        if fixed:
            if not compact_in(fixed, replacement):
                return False
        elif content_source == "composed":
            return False
    return True


def content_check_factory(planned: Sequence[dict], inspection: DocumentInspection):
    """docx.validate_edit_plan content_check: re-verify generated/composed text."""
    by_id = {f"{item['rule_id']}:{item['target_id']}": item for item in planned}

    def check(edit: dict[str, Any]) -> bool:
        item = by_id.get(edit.get("edit_id"))
        if item is None:
            return False
        if edit.get("replacement") != item.get("replacement"):
            return False
        if edit.get("location") != item.get("location"):
            return False
        if int(edit.get("start", -1)) != int(item.get("start", -2)) or \
                int(edit.get("end", -1)) != int(item.get("end", -2)):
            return False
        if edit.get("source_sha256") != inspection.source_sha256:
            return False
        span = inspection.by_location(item["location"])
        start, end = int(item["start"]), int(item["end"])
        if edit.get("expected_old_text") != span.text[start:end]:
            return False
        components = item.get("components") or []
        if components:
            if "".join(str(component.get("replacement") or "") for component in components) != str(item["replacement"]):
                return False
            return all(_component_ok(component, inspection) for component in components)
        return _component_ok({**item, "expected_old_text": span.text[start:end]}, inspection)

    return check
