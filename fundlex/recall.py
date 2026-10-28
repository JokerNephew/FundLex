"""Recall-first revision engine core.

Code owns structure, addresses, source verification and execution; the model owns
business judgement: fee facts, rule-to-subsection mapping, target inventory and the
composition of replacement text for contract-specific variants. Every model quote is
re-resolved against the real document before it is used.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from .docx import BARRIER, DocumentInspection, ParagraphSpan, TextSegment
from .generation.flags import strategy_mode
from .model import ModelError
from .recall_prompts import (
    AUDIT_INSTRUCTION, AUDIT_PROMPT_VERSION, AUDIT_SCHEMA,
    COMPOSE_DELETE_INSTRUCTION, COMPOSE_INSTRUCTION, COMPOSE_PROMPT_VERSION, COMPOSE_SCHEMA,
    FACTS_INSTRUCTION, FACTS_PROMPT_VERSION, FACTS_SCHEMA,
    INVENTORY_INSTRUCTION, INVENTORY_PROMPT_VERSION, INVENTORY_SCHEMA,
    PROMPT_VERSIONS, SCOPE_INSTRUCTION, SCOPE_PROMPT_VERSION, SCOPE_SCHEMA,
    SWEEP_INSTRUCTION, SWEEP_PROMPT_VERSION, SWEEP_SCHEMA,
    VERIFY_INSTRUCTION, VERIFY_PROMPT_VERSION, VERIFY_SCHEMA,
)

ENGINE_ID = "recall_first"
ENGINE_VERSION = "0.1.1"
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


# G14's fee-adjustment list appears in contracts both with and without the
# repeated noun "基金" before each fee item:
#   指引: 调低基金申购费率、赎回费率和转换费率
#   合同: 调低基金申购费率、基金赎回费率和转换费率
# The noun does not change the policy.  Normalisation is only used for operation
# identity/site matching; the guide and the artifact keep their original text.
_FEE_RATE_ITEM = r"(?:申购|赎回|转换|销售服务)费率"


def _normalise_fee_rate_reference(value: str) -> str:
    return re.sub(rf"、基金(?={_FEE_RATE_ITEM})", "、", _compact(value))


def _expand_fee_rate_reference(value: str) -> str:
    """Insert the optional repeated noun so an exact document search can find it."""
    return re.sub(rf"、(?={_FEE_RATE_ITEM})", "、基金", _compact(value))


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


def find_fuzzy(cleaned: str, needle: str, *, threshold: float = FUZZY_MATCH_THRESHOLD,
               variable_length: bool = False
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
        # Wording variants can insert or omit a short connector.  The public matcher
        # keeps its historical fixed-size span; deterministic recall opts into the
        # bounded variable-length mode so its occurrence parts cover the real clause.
        if variable_length:
            lower = max(8, int(size * 0.75))
            upper = min(len(cleaned) - start, int(size * 1.35) + 1)
            local: tuple[int, float] | None = None
            for length in range(lower, upper + 1):
                window = cleaned[start:start + length]
                ratio = SequenceMatcher(None, target, window).ratio()
                if local is None or ratio > local[1] + 1e-9 \
                        or (abs(ratio - local[1]) <= 1e-9
                            and abs(length - size) < abs(local[0] - size)):
                    local = (length, ratio)
        else:
            window = cleaned[start:start + size]
            if len(window) < size:
                window = cleaned[start:]
            local = (len(window), SequenceMatcher(None, target, window).ratio())
        if local is None:
            continue
        length, ratio = local
        if ratio < threshold or length < 0.8 * size:
            continue
        end = min(len(cleaned), start + length)
        if best is None or ratio > best[2] \
                or (abs(ratio - best[2]) <= 1e-9
                    and abs(length - size) < abs((best[1] - best[0]) - size)):
            best = (start, end, ratio)
    return best


def fuzzy_span(span_text: str, needle: str, *,
               threshold: float = FUZZY_MATCH_THRESHOLD,
               variable_length: bool = False) -> tuple[int, int, float] | None:
    """Fuzzy-locate ``needle`` in one paragraph, returning raw offsets and a ratio."""
    cleaned, index_map = display_text(span_text)
    located = find_fuzzy(cleaned, needle, threshold=threshold,
                         variable_length=variable_length)
    if located is None:
        return None
    start_clean, end_clean, ratio = located
    return index_map[start_clean], index_map[end_clean - 1] + 1, ratio


def fuzzy_span_clause(span_text: str, needle: str, *,
                      threshold: float = FUZZY_MATCH_THRESHOLD,
                      variable_length: bool = False) -> tuple[int, int, float] | None:
    """``fuzzy_span`` snapped to a sentence boundary.

    ``find_fuzzy`` matches the best character window, so a reference ending in "。" can
    stop a couple of characters short of the paragraph's own full stop ("…比例进行分"
    leaving "配。"). Replacing that window keeps the leftover stub and produces
    "…（如有）。配。" (FL-D079). When the needle itself ends at sentence punctuation, the
    returned span is extended to (or trimmed back to) the paragraph's matching stop so the
    kept suffix starts a fresh sentence.
    """
    span = fuzzy_span(span_text, needle, threshold=threshold,
                      variable_length=variable_length)
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


def resolve_source_quote(span: ParagraphSpan, quote: str) -> tuple[int, int] | None:
    """Bind a complete quote uniquely in one writable source segment.

    Ignore whitespace and Word's zero-width formatting characters. Only the final
    full-stop/semicolon may differ or be absent at the paragraph end; never accept
    a sentence fragment, a second occurrence or text across a protected barrier.
    """
    def compact(value: str) -> tuple[str, list[int]]:
        positions = [i for i, char in enumerate(value)
                     if not char.isspace() and char not in "\u200b\ufeff"]
        return "".join(value[i] for i in positions), positions

    body, positions = compact(span.text)
    needle, _ = compact(quote)
    if not needle or BARRIER in needle:
        return None
    stops = "。；;"
    terminated = needle[-1] in stops
    core = needle[:-1] if terminated else needle
    if not core:
        return None
    candidates: set[tuple[int, int]] = set()
    cursor = 0
    while (start := body.find(core, cursor)) >= 0:
        end = start + len(core)
        if not terminated:
            # A quote without its final delimiter is acceptable only when the
            # source reaches a real sentence boundary (or the paragraph ends).
            # Otherwise it is a prefix and cannot close a source obligation.
            if end == len(body) or body[end] in stops:
                if end < len(body):
                    end += 1
                candidates.add((positions[start], positions[end - 1] + 1))
        elif end == len(body) or body[end] in stops:
            if end < len(body):
                end += 1
            candidates.add((positions[start], positions[end - 1] + 1))
        cursor = start + 1
    if len(candidates) != 1:
        return None
    bound = next(iter(candidates))
    if BARRIER in span.text[bound[0]:bound[1]]:
        return None
    segments = getattr(span, "segments", None)
    if segments is None:
        # Lightweight replay/effect fixtures predate physical segment metadata.
        # Keep their ordinary source resolution usable; real DocumentInspection
        # spans always expose ``segments`` and therefore take the strict branch.
        return bound
    return bound if containing_segment(span, *bound) is not None else None


def resolve_quote(span: ParagraphSpan, quote: str) -> tuple[int, int] | None:
    """Resolve a model quote to raw offsets inside one paragraph span.

    Long quotes that span read-only barriers or several sentences fail closed when
    the complete source quote cannot be bound.  A sentence from a larger quote is
    not enough evidence for an edit: it may belong to a sibling operation in the
    same paragraph.
    """
    cleaned, index_map = display_text(span.text)
    located = find_normalized(cleaned, quote)
    if located is not None:
        start_clean, end_clean = located
        return index_map[start_clean], index_map[end_clean - 1] + 1
    source_bound = resolve_source_quote(span, quote)
    if source_bound is not None:
        return source_bound
    # A locator may render the last clause's semicolon as a full stop (or vice
    # versa). Bind the complete otherwise-verbatim quote before trying individual
    # sentences; a prefix-only binding can omit the very policy being replaced.
    # Only the terminal delimiter may differ. The following sibling clause is
    # outside this quote and retains its own operation authorization.
    if quote.rstrip().endswith(("。", "；", ";")):
        body = quote.rstrip()[:-1]
        located = find_normalized(cleaned, body)
        if located is not None:
            start_clean, end_clean = located
            terminal = end_clean
            while terminal < len(cleaned) and cleaned[terminal].isspace():
                terminal += 1
            if terminal < len(cleaned) and cleaned[terminal] in "。；;":
                return index_map[start_clean], index_map[terminal] + 1
    return None


def _compact_positions(text: str, needle: str) -> list[tuple[int, int]]:
    """Raw occurrences of ``needle`` after whitespace normalization.

    Real DOCX text often renders ``A 类基金份额`` with a space; the guide token has
    none.  Both sides are compacted and the start/end are mapped back to raw offsets.
    """
    compact_chars: list[str] = []
    raw_index: list[int] = []
    for index, char in enumerate(text or ""):
        if char.isspace() or char in {"\u3000", "\u00a0", "\u200b"}:
            continue
        compact_chars.append(char)
        raw_index.append(index)
    compact_text = "".join(compact_chars)
    needle_compact = _compact(needle)
    if not needle_compact or not compact_text:
        return []
    found: list[tuple[int, int]] = []
    cursor = 0
    while True:
        position = compact_text.find(needle_compact, cursor)
        if position < 0:
            break
        start = raw_index[position]
        end = raw_index[position + len(needle_compact) - 1] + 1
        found.append((start, end))
        cursor = position + 1
    return found


def _occurrence_index(text: str, needle: str, start: int) -> int:
    """Index of the occurrence whose raw start is ``start`` (-1 when not exact)."""
    positions = [position for position, _ in _compact_positions(text, needle)]
    try:
        return positions.index(start)
    except ValueError:
        return -1


def resolve_occurrence(span: ParagraphSpan, needle: str, *, anchor: str = "",
                      window: int = 24) -> tuple[int, int] | None:
    """Resolve one occurrence of ``needle`` using the target's original context.

    Multiple identical tokens in one paragraph (``A类基金份额`` twice) cannot be told
    apart by :func:`resolve_quote`, which returns the first match.  The inventory quote
    is the occurrence identity: score every exact occurrence by how much of its local
    lead/tail appears in that quote.  A tie (or no anchor) returns ``None`` — the caller
    must leave the target unresolved rather than edit the wrong occurrence.
    """
    if not needle:
        return None
    text = str(getattr(span, "text", ""))
    positions = _compact_positions(text, needle)
    if not positions:
        return resolve_quote(span, needle)
    if len(positions) == 1:
        return positions[0]
    anchor_compact = _compact(anchor)
    if not anchor_compact:
        return None
    # An exact, unique source quote containing one token is stronger than a
    # similarity score. A nearby occurrence's context window can otherwise
    # include the start of this very quote and tie with the intended occurrence.
    anchors = _compact_positions(text, anchor)
    if len(anchors) == 1:
        start, end = anchors[0]
        contained = [position for position in positions
                     if start <= position[0] and position[1] <= end]
        if len(contained) == 1:
            return contained[0]
    from difflib import SequenceMatcher

    def overlap(value: str) -> float:
        value = _compact(value)
        if not value:
            return 0.0
        match = SequenceMatcher(None, value, anchor_compact).find_longest_match(
            0, len(value), 0, len(anchor_compact))
        return match.size / len(value)

    scored: list[tuple[float, tuple[int, int]]] = []
    for start, end in positions:
        lead = text[max(0, start - window):start]
        tail = text[end:end + window]
        scored.append((max(overlap(lead), overlap(tail)), (start, end)))
    scored.sort(reverse=True)
    if scored[0][0] <= 0.0:
        return None
    if len(scored) > 1 and scored[0][0] - scored[1][0] < 0.1:
        return None
    return scored[0][1]


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
    subscription_quote: str = ""
    service_quote: str = ""


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
    #: Plan §24/§20: channel facts must be *verified* tri-state, never guessed.
    direct_sales_exempt_group: tuple[str, ...] = ()
    other_sales_charged_group: tuple[str, ...] = ()
    #: Per-fact tri-state: VERIFIED | UNKNOWN | CONFLICT (missing means UNKNOWN).
    fact_status: dict[str, str] = field(default_factory=dict)
    #: Applicability decisions recovered from literal evidence (condition key -> TRUE/FALSE).
    #: They are branch decisions, not new fee facts; planning must obey them.
    condition_overrides: dict[str, str] = field(default_factory=dict)
    class_set_quote: str = ""
    class_set_evidence: dict[str, Any] = field(default_factory=dict)
    value_verified: bool = False
    set_complete_verified: bool = False
    fund_type_certification: dict[str, Any] = field(default_factory=dict)
    channel_evidence: dict[str, str] = field(default_factory=dict)
    #: Deterministic fee polarity recovered from each class quote. ``None`` means
    #: the quote establishes the class but not that fee fact (FL-D209/FL-D208).
    fee_polarities: dict[str, dict[str, bool | None]] = field(default_factory=dict)
    #: A contract with no share-class labels/currency classes and no enumeration
    #: is a single-class product. Keep this explicit: an empty class list alone is
    #: UNKNOWN, never "single".
    single_class_verified: bool = False

    @property
    def share_class_structure(self) -> str:
        """SINGLE | MULTIPLE | UNKNOWN — the plan's replacement for bare class_count."""
        current = len(self.current_classes)
        if current == 1 or (current == 0 and self.single_class_verified):
            return "SINGLE"
        if current > 1:
            return "MULTIPLE"
        return "UNKNOWN"

    def status_of(self, name: str) -> str:
        """Tri-state of one fact; an unrecorded fact is UNKNOWN, never VERIFIED."""
        if name == "floating_management_fee":
            return "VERIFIED" if self.quotes_verified.get("floating") else "UNKNOWN"
        return self.fact_status.get(name, "UNKNOWN")

    @property
    def current_classes(self) -> tuple[ClassFact, ...]:
        return tuple(item for item in self.classes if item.current)

    @property
    def class_count(self) -> int:
        current = len(self.current_classes)
        if current == 0 and self.single_class_verified:
            return 1
        return current

    @property
    def subscription_group(self) -> tuple[str, ...]:
        # Guide definition: charges subscription/purchase fees AND accrues no service fee.
        return tuple(item.name for item in self.current_classes
                     if item.subscription_fee and not item.service_fee)

    @property
    def service_group(self) -> tuple[str, ...]:
        # Guide definition: charges no subscription/purchase fee AND accrues the
        # service fee. A class carrying both flags is ambiguous, not a service class
        # (external review 2026-10-19, P0-B) — see ``ambiguous_classes``.
        return tuple(item.name for item in self.current_classes
                     if item.service_fee and not item.subscription_fee)

    @property
    def ambiguous_classes(self) -> tuple[str, ...]:
        """Classes carrying both fee flags: neither group can claim them."""
        return tuple(item.name for item in self.current_classes
                     if item.subscription_fee and item.service_fee)

    @property
    def has_service_fee(self) -> bool:
        return any(item.service_fee for item in self.current_classes)

    def as_ledger(self) -> dict[str, Any]:
        return {
            "fund_type": self.fund_type,
            "fund_type_quote": self.fund_type_quote,
            "fund_type_basis": self.fund_type_basis,
            "class_count": self.class_count,
            "classes": [
                {"name": item.name, "subscription_fee": item.subscription_fee,
                 "service_fee": item.service_fee, "current": item.current,
                  "rate": item.rate, "quote": item.quote,
                  "subscription_quote": item.subscription_quote,
                  "service_quote": item.service_quote}
                for item in self.classes
            ],
            "subscription_group": list(self.subscription_group),
            "service_group": list(self.service_group),
            "share_class_structure": self.share_class_structure,
            "direct_sales_exempt_group": list(self.direct_sales_exempt_group),
            "other_sales_charged_group": list(self.other_sales_charged_group),
            "fact_status": dict(self.fact_status),
            "condition_overrides": dict(self.condition_overrides),
            "has_service_fee": self.has_service_fee,
            "is_floating_fee": self.floating_management_fee,
            "floating_quote": self.floating_quote,
            "floating_basis": self.floating_basis,
            "notes": self.notes,
            "quotes_verified": dict(self.quotes_verified),
            "class_set_quote": self.class_set_quote,
            "class_set_evidence": dict(self.class_set_evidence),
            "value_verified": self.value_verified,
            "set_complete_verified": self.set_complete_verified,
            "fund_type_certification": dict(self.fund_type_certification),
            "channel_evidence": dict(self.channel_evidence),
            "fee_polarities": {name: dict(values) for name, values in self.fee_polarities.items()},
            "single_class_verified": self.single_class_verified,
            "problems": list(self.problems),
        }


def derive_fact_statuses(*, fund_type_ok: bool, classes: Sequence[ClassFact],
                         class_quotes: dict[str, bool],
                         direct_classes: Sequence[str], direct_ok: bool,
                         other_classes: Sequence[str], other_ok: bool,
                         set_complete_verified: bool = False,
                         fee_polarities: dict[str, dict[str, bool | None]] | None = None,
                         single_class_verified: bool = False) -> dict[str, str]:
    """Tri-state statuses for the phase-3 fact schema (plan v4 §24, §20).

    * ``VERIFIED`` — backed by a verified quote and internally consistent;
    * ``UNKNOWN``  — no verified evidence; callers must not treat this as "empty"
      (a missing direct-sales exemption may never be inferred from a failed
      extraction — the plan's VERIFIED_EMPTY ≠ UNKNOWN rule);
    * ``CONFLICT`` — the evidence names a class the contract does not define.
    """
    statuses: dict[str, str] = {"fund_type": "VERIFIED" if fund_type_ok else "UNKNOWN"}
    class_names = {item.name for item in classes}
    current_ok = bool([item for item in classes if item.current]) and set_complete_verified and all(
        class_quotes.get(item.name, False) for item in classes if item.current)
    statuses["share_class_structure"] = ("VERIFIED"
                                         if current_ok or single_class_verified
                                         else "UNKNOWN")
    current_names = [item.name for item in classes if item.current]
    duplicate_names = len(current_names) != len(set(current_names))
    ambiguous = [item for item in classes
                 if item.current and item.subscription_fee and item.service_fee]

    def family_conflict(key: str) -> bool:
        if not current_ok:
            return False
        if ambiguous or duplicate_names:
            # A class carrying both fee flags cannot be placed in either group.
            return True
        if fee_polarities is None:
            return False
        return any(fee_polarities.get(item.name, {}).get(key) is not None
                   and fee_polarities[item.name][key] is not getattr(item, key)
                   for item in classes if item.current)

    # A literal contradiction is a class-set integrity failure and poisons both
    # groups; a merely UNKNOWN family is independent and must not erase a proven
    # sibling (FL-D440).
    any_conflict = family_conflict("subscription_fee") or family_conflict("service_fee")

    def fee_group_status(key: str) -> str:
        if not current_ok:
            return "UNKNOWN"
        if any_conflict:
            return "CONFLICT"
        if fee_polarities is not None and any(
                fee_polarities.get(item.name, {}).get(key) is None
                for item in classes if item.current):
            return "UNKNOWN"
        return "VERIFIED"

    statuses["subscription_fee_group"] = fee_group_status("subscription_fee")
    statuses["service_fee_group"] = fee_group_status("service_fee")

    def channel_status(names: Sequence[str], quote_ok: bool) -> str:
        if not quote_ok:
            return "UNKNOWN"
        unknown = [name for name in names if name not in class_names]
        if unknown:
            return "CONFLICT"
        # An empty, verified list still cannot prove VERIFIED_EMPTY offline; the
        # hard-fact topic check in the generator upgrades it later (plan §20).
        return "VERIFIED" if names else "UNKNOWN"

    statuses["direct_sales_exempt_group"] = channel_status(direct_classes, direct_ok)
    statuses["other_sales_charged_group"] = channel_status(other_classes, other_ok)
    return statuses


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
            # One oversized paragraph must not hide every later short piece of
            # evidence: skip it (with an explicit marker) and keep scanning.
            if not any(item.startswith(f"[{span.location}]") for item in lines):
                marker = f"[{span.location}] <omitted: exceeds facts context budget>"
                if total + len(marker) <= limit:
                    lines.append(marker)
                    total += len(marker)
            continue
        lines.append(line)
        total += len(line)
    return "\n".join(lines)


_ELLIPSIS_RE = re.compile(r"…+|\.{3,}")


def _quote_present(inspection: DocumentInspection, fragment: str) -> bool:
    """True when a compact fragment appears in one paragraph or across a boundary."""
    cleaned = _compact(fragment)
    if not cleaned:
        return False
    texts: list[str] = []
    for span in inspection.paragraphs:
        text, _ = display_text(span.text)
        compact_text = _compact(text)
        if cleaned in compact_text:
            return True
        texts.append(compact_text)
    # Facts are often quoted with a heading/paragraph boundary inside the quote
    # (D14: "基金的运作方式\n契约型开放式"). Only accept a cross-boundary match if
    # the fragment actually straddles a boundary, not merely appears in both.  A
    # definition can span three paragraphs ("…基金\n业务实施细则》…Exchange\nTraded
    # Fund）"), so check bounded consecutive windows rather than only pairs.
    for size in (2, 3, 4):
        for start in range(0, len(texts) - size + 1):
            window = texts[start:start + size]
            if any(not item for item in window):
                continue
            joined = "".join(window)
            index = joined.find(cleaned)
            if index == -1:
                continue
            prefix_len = sum(len(item) for item in window[:-1])
            if index < prefix_len < index + len(cleaned):
                return True
    return False


def _repair_fee_quote(inspection: DocumentInspection, quote: str, field: str,
                      class_name: str, expected: bool) -> str:
    """Recover one narrowly malformed fee quote from the source paragraph.

    Models sometimes prepend ``本基金`` to a numbered fee item (for example,
    answering ``本基金 A类...`` for source text ``4、A类...``).  The resulting
    answer is not an exact quote and must not be accepted as-is.  We may recover
    the source text only when the suffix beginning at the named class is an exact
    contiguous source match, the omitted prefix is the harmless ``本基金``
    phrase, and the recovered source slice independently proves the requested
    fee polarity.  This keeps the repair source-bound and fail-closed.
    """
    if not isinstance(quote, str) or not quote or field not in {
            "subscription_fee", "sales_service_fee"}:
        return ""
    compact_quote = _compact(quote)
    if not compact_quote.startswith("本基金"):
        return ""
    class_token = re.search(r"[A-ZＡ-Ｚ]类(?:基金)?份额?", compact_quote)
    if class_token is None:
        return ""
    prefix = compact_quote[:class_token.start()]
    if prefix != "本基金":
        return ""
    suffix = compact_quote[class_token.start():]
    from .fee_evidence import fee_value
    for span in inspection.paragraphs:
        displayed, _ = display_text(span.text)
        compact_source, source_map = compact_offsets(displayed)
        start = compact_source.find(suffix)
        while start >= 0:
            end = start + len(suffix)
            if end > len(source_map):
                break
            # Start at the nearest sentence/clause boundary so a numbered item
            # such as ``4、`` is retained in the repaired quote.
            # Try the complete numbered item and, for a later class in a
            # semicolon-linked item, the individual clause.  Both boundaries
            # must be source boundaries; neither is inferred from the model.
            sentence_boundary = max((compact_source.rfind(mark, 0, start)
                                     for mark in "。！？"), default=-1) + 1
            boundaries = [sentence_boundary]
            for mark in "；;":
                clause_boundary = compact_source.rfind(mark, 0, start) + 1
                if clause_boundary not in boundaries:
                    boundaries.append(clause_boundary)
            raw_end = source_map[end - 1] + 1
            for boundary in boundaries:
                prefix_text = compact_source[boundary:start]
                if prefix_text and not re.fullmatch(r"\d+[、.．)]", prefix_text):
                    continue
                raw_start = source_map[boundary] if boundary < len(source_map) else 0
                candidate = displayed[raw_start:raw_end]
                if (candidate and _verify_quote(inspection, candidate)
                        and fee_value(candidate, field, class_name[0]) is expected):
                    return candidate
            start = compact_source.find(suffix, start + 1)
    return ""


def _verify_quote(inspection: DocumentInspection, quote: str) -> bool:
    if not quote or len(quote.strip()) < 2:
        return False
    # A model may abbreviate a long quote with an ellipsis; every retained fragment
    # is still literal source text and must be verifiable. Treating the whole string
    # as one quote made those evidence records fail verification even when correct
    # (FL-D114).
    fragments = [fragment for fragment in _ELLIPSIS_RE.split(quote)
                 if len(_compact(fragment)) >= 2]
    if not fragments:
        return False
    return all(_quote_present(inspection, fragment) for fragment in fragments)


def _is_etf_feeder(inspection: DocumentInspection) -> bool:
    """True when the contract is an ETF feeder fund (联接基金), not the ETF itself.

    The cover/title paragraph names both the product and the document, for example
    ``…交易型开放式指数证券投资基金发起式联接基金基金合同``. A true ETF contract's
    title has no ``联接基金``; a body reference to the ETF's feeder does not carry
    ``基金合同`` in the same paragraph. Business ruling 2026-10-20 (FL-D132): feeder
    funds are ordinary open-ended contracts and must be revised.
    """
    for span in inspection.paragraphs[:30]:
        text, _ = display_text(span.text)
        if "联接基金" in text and "基金合同" in text:
            return True
    return False


def extract_facts(inspection: DocumentInspection, gateway: Any) -> Facts:
    context = facts_context(inspection, limit=max(4000, gateway.max_context_chars - 2500))
    result = gateway.call(task_type="recall_facts", bounded_context=context,
                          response_schema=FACTS_SCHEMA, instruction=FACTS_INSTRUCTION,
                          prompt_version=FACTS_PROMPT_VERSION)
    value = result.value if isinstance(result.value, dict) else {}
    return facts_from_value(inspection, value)


def single_class_structure_verified(inspection: DocumentInspection) -> bool:
    """A contract with no share-class labels/enumeration is a single-class product.

    This is the missing hard fact behind D09/D13: empty ``classes`` alone is
    UNKNOWN, but a contract that never names an A/B/C class and never enumerates
    multiple share classes cannot support class-substitution branches. Currency
    share classes are excluded from this shortcut because they are a real
    multi-class structure without letter labels.
    """
    from .fact_evidence import class_labels
    text = "".join(str(span.text) for span in inspection.paragraphs)
    if class_labels(text):
        return False
    compact = _compact(text)
    if re.search(r"(?:人民币|美元|港币|英镑|欧元|现汇|现钞)份额", compact):
        return False
    if re.search(r"(?:两|二|三|四|五|六|多)(?:种|类|个)?(?:不同)?(?:的)?(?:基金)?份额类别", compact):
        return False
    return True


def single_class_fee_evidence(inspection: DocumentInspection) -> tuple[str, bool]:
    """Return source-bound evidence for an unnamed single class.

    Some contracts describe the only class through the ordinary fee clause rather
    than naming it.  The relevant evidence is the paragraph that says investors
    bear the subscription fee, together with a bounded neighbourhood around that
    clause that contains no sales-service-fee clause.  References to fees charged
    by underlying funds elsewhere in an FOF contract therefore do not change the
    product's own class facts.
    """
    paragraphs = list(inspection.paragraphs)
    for index, span in enumerate(paragraphs):
        text = str(span.text or "")
        if not re.search(r"申购费用?由[^。；;\n]{0,30}承担", _compact(text)):
            continue
        left = max(0, index - 12)
        right = min(len(paragraphs), index + 13)
        nearby = "".join(str(item.text or "") for item in paragraphs[left:right])
        if "销售服务费" not in nearby:
            return text, True
    return "", False


def facts_from_value(inspection: DocumentInspection, value: dict[str, Any]) -> Facts:
    """Parse one FACTS_SCHEMA answer and verify every quote against the source.

    Shared by the generic extraction and the focused fact-recovery resolver, so a
    recovered fact passes exactly the same code verification as the first answer.
    """
    problems: list[str] = []
    quotes_verified: dict[str, bool] = {}

    fund_type = (value.get("fund_type") or {}) if isinstance(value.get("fund_type"), dict) else {}
    fund_type_value = str(fund_type.get("value") or "other")
    fund_basis = str(fund_type.get("basis") or "")
    fund_quote = str(fund_type.get("quote") or "")
    if fund_type_value == "etf" and _is_etf_feeder(inspection):
        # The model occasionally treats an ETF feeder contract as an ETF because the
        # title contains "ETF … 联接基金" (D02 vs D06, FL-D132). Only the ETF itself
        # is excluded; the feeder is an ordinary open-end fund and is revised.
        fund_type_value = "open_regular"
        fund_basis = "etf_feeder_is_open_regular"
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
        subscription_quote = str(item.get("subscription_quote") or "")
        service_quote = str(item.get("service_quote") or "")
        if subscription_quote and not _verify_quote(inspection, subscription_quote):
            repaired = _repair_fee_quote(
                inspection, subscription_quote, "subscription_fee", name,
                bool(item.get("subscription_fee")))
            if repaired:
                subscription_quote = repaired
        if service_quote and not _verify_quote(inspection, service_quote):
            repaired = _repair_fee_quote(
                inspection, service_quote, "sales_service_fee", name,
                bool(item.get("service_fee")))
            if repaired:
                service_quote = repaired
        classes.append(ClassFact(
            name=name,
            subscription_fee=bool(item.get("subscription_fee")),
            service_fee=bool(item.get("service_fee")),
            current=bool(item.get("current", True)),
            rate=(str(item["rate"]) if item.get("rate") else None),
            quote=quote,
            subscription_quote=subscription_quote,
            service_quote=service_quote,
        ))

    # A model may use an invented label such as ``默认份额类别`` when the
    # contract has one unnamed class.  It is evidence-free as a literal class
    # name and must not leave the whole fact set UNKNOWN.  Rebuild it from the
    # contract's own subscription clause and a bounded proof that the class has
    # no sales-service fee.
    single_structure = single_class_structure_verified(inspection)
    class_set_evidence: dict[str, Any] = {}
    single_class_no_service_verified = False
    placeholder_names = {"default", "none", "unknown", "n/a", "na",
                         "其他", "默认份额类别", "__single__"}
    real_classes = [item for item in classes
                    if item.current and re.sub(r"\s+", "", item.name).lower()
                    not in placeholder_names]
    if single_structure and not real_classes:
        subscription_quote = ""
        for item in classes:
            candidate = item.subscription_quote or item.quote
            if candidate and _verify_quote(inspection, candidate):
                subscription_quote = candidate
                break
        if not subscription_quote:
            subscription_quote, _ = single_class_fee_evidence(inspection)
        from .fee_evidence import fee_value
        subscription_proven = bool(subscription_quote and _verify_quote(
            inspection, subscription_quote)
            and fee_value(subscription_quote, "subscription_fee", "__single__",
                          single_bound=True) is True)
        detected_quote, no_service = single_class_fee_evidence(inspection)
        if not subscription_proven and detected_quote:
            subscription_quote = detected_quote
            subscription_proven = fee_value(
                detected_quote, "subscription_fee", "__single__",
                single_bound=True) is True
        if subscription_proven and no_service:
            single_class_no_service_verified = True
            classes = [ClassFact(
                name="__single__", subscription_fee=True, service_fee=False,
                current=True, rate=None, quote=subscription_quote,
                subscription_quote=subscription_quote, service_quote="")]
            class_set_evidence = {
                "quote_verified": True, "set_complete_verified": True,
                "parsed_classes": ["__single__"],
                "reason": "SINGLE_CLASS_STRUCTURALLY_VERIFIED",
            }
        elif not real_classes:
            classes = []

    floating = (value.get("floating_management_fee") or {}) if isinstance(value.get("floating_management_fee"), dict) else {}
    floating_value = bool(floating.get("value"))
    floating_quote = str(floating.get("quote") or "")
    quotes_verified["floating"] = _verify_quote(inspection, floating_quote)
    if not quotes_verified["floating"]:
        problems.append("FLOATING_QUOTE_UNVERIFIED")

    def _channel(key: str) -> tuple[list[str], bool]:
        raw = value.get(key) if isinstance(value.get(key), dict) else {}
        names = [str(name).strip() for name in (raw.get("classes") or []) if str(name).strip()]
        quote = str(raw.get("quote") or "")
        ok = _verify_quote(inspection, quote) if quote else False
        if quote:
            # Record only claimed facts: "not stated" stays absent (UNKNOWN),
            # keeping ``quotes_verified`` semantics unchanged (back-compat).
            quotes_verified[key] = ok
        if names and not ok:
            problems.append(f"CHANNEL_QUOTE_UNVERIFIED:{key}")
        return names, ok

    direct_names, direct_ok = _channel("direct_sales_exempt")
    other_names, other_ok = _channel("other_sales_charged")
    class_quotes = {name.split(":", 1)[1]: ok
                    for name, ok in quotes_verified.items() if name.startswith("class:")}
    if any(item.name == "__single__" and item.current for item in classes):
        class_quotes["__single__"] = True
        quotes_verified["class:__single__"] = True
    from .fact_evidence import verify_class_set
    class_set_quote = str(value.get("class_set_quote") or "")
    if not (classes and classes[0].name == "__single__"
            and class_set_evidence.get("set_complete_verified")):
        class_set_evidence = verify_class_set(inspection, classes, class_set_quote)
    set_complete = bool(class_set_evidence["set_complete_verified"])
    from .fee_evidence import fee_value
    fee_polarities: dict[str, dict[str, bool | None]] = {}
    for item in classes:
        fee_polarities[item.name] = {}
        for key, field_name, specific in (
                ("subscription_fee", "subscription_fee", item.subscription_quote),
                ("service_fee", "sales_service_fee", item.service_quote)):
            quote = specific or item.quote
            if (item.name == "__single__" and key == "service_fee"
                    and single_class_no_service_verified):
                # The absence proof is the bounded fee neighbourhood returned by
                # single_class_fee_evidence(), not a fabricated quote. Keep this
                # as a separate verified polarity so a missing service-fee clause
                # is not confused with an extraction failure.
                quote_ok = True
                fee_polarities[item.name][key] = False
                quotes_verified[f"{key}:{item.name}"] = True
                continue
            quote_ok = _verify_quote(inspection, quote) if specific else class_quotes.get(item.name, False)
            quotes_verified[f"{key}:{item.name}"] = bool(quote_ok)
            fee_polarities[item.name][key] = (fee_value(
                                                        quote, field_name,
                                                        "__single__" if item.name == "__single__" else item.name[0],
                                                        single_bound=item.name == "__single__")
                                              if quote_ok else None)
        for field_name, expected in fee_polarities[item.name].items():
            if expected is None:
                problems.append(f"FEE_QUOTE_UNPROVEN:{item.name}:{field_name}")
            elif expected is not getattr(item, field_name):
                problems.append(f"FEE_QUOTE_CONFLICT:{item.name}:{field_name}")
    value_verified = bool([item for item in classes if item.current]) and all(
        class_quotes.get(item.name, False) and all(
            fee_polarities[item.name][key] is getattr(item, key)
            for key in ("subscription_fee", "service_fee")) for item in classes if item.current)
    quotes_verified["class_set"] = bool(class_set_evidence["quote_verified"])
    if not set_complete:
        problems.append(str(class_set_evidence["reason"]))
    single_class_verified = (
        (not [item for item in classes if item.current]
         and single_structure)
        or any(item.name == "__single__" and item.current for item in classes))
    if single_class_verified:
        quotes_verified["single_class"] = True
    fact_status = derive_fact_statuses(
        fund_type_ok=quotes_verified["fund_type"], classes=classes,
        class_quotes=class_quotes,
        direct_classes=direct_names, direct_ok=direct_ok,
        other_classes=other_names, other_ok=other_ok,
        set_complete_verified=set_complete, fee_polarities=fee_polarities,
        single_class_verified=single_class_verified)

    return Facts(
        fund_type=fund_type_value,
        fund_type_quote=fund_quote,
        fund_type_basis=fund_basis,
        classes=tuple(classes),
        floating_management_fee=floating_value,
        floating_quote=floating_quote,
        floating_basis=str(floating.get("basis") or ""),
        notes=str(value.get("notes") or ""),
        quotes_verified=quotes_verified,
        problems=tuple(problems),
        direct_sales_exempt_group=tuple(direct_names),
        other_sales_charged_group=tuple(other_names),
        fact_status=fact_status,
        class_set_quote=class_set_quote, class_set_evidence=class_set_evidence,
        value_verified=value_verified, set_complete_verified=set_complete,
        channel_evidence={key: str((value.get(key) or {}).get("quote") or "")
                          for key in ("direct_sales_exempt", "other_sales_charged")
                          if isinstance(value.get(key), dict)},
        fee_polarities=fee_polarities,
        single_class_verified=single_class_verified,
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


def structure_index(inspection: DocumentInspection, *,
                    max_sections: int | None = None) -> tuple[Section, ...]:
    """Group readable paragraphs into sections by their running heading.

    ``max_sections=None`` indexes the whole document.  A caller may still pass an
    explicit limit, but that limit must then be reported as a coverage gap: the
    previous default of 80 silently dropped every later section, so the tail of a
    long contract never reached inventory while the run could still look complete
    (FL-D441).
    """
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
    indexed = groups if max_sections is None else groups[:max_sections]
    for position, group in enumerate(indexed):
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


# G06 is authored against the ``基金的基本情况-份额类别设置`` subsection.  The
# document inspector currently exposes only the running part/chapter path, so a
# rule mapped to ``基金的基本情况`` would otherwise receive the whole chapter.
# Keep this boundary deterministic and source based: subsection headings are the
# numbered Chinese headings that occur inside the chapter, and the next heading
# ends the physical site.  A missing heading is deliberately represented by an
# empty scope; callers must fail closed instead of falling back to a document-wide
# semantic sweep.
_G06_SUBSECTION_RE = re.compile(
    r"^(?:[一二三四五六七八九十百零〇]+、|\d+[、.])"
    r"(?:基金)?(?:份额类别|份额的类别|基金份额类别)(?:设置)?$"
)


def g06_scope_locations(inspection: DocumentInspection) -> frozenset[str]:
    """Return the physical ``份额类别设置`` subsection locations for G06.

    The helper also accepts unnumbered headings used by compact fixtures.  It
    never infers a scope from a body sentence containing ``份额类别设置``; that
    phrase is common in amendment clauses outside the subsection.
    """
    paragraphs = tuple(inspection.paragraphs)
    has_structure_metadata = any(hasattr(span, "section_path") for span in paragraphs)
    if not has_structure_metadata:
        # Legacy unit inspections predate section_path/zone metadata. Preserve
        # their isolated-document semantics; real DOCX inspections always carry
        # structure metadata and therefore remain fail-closed.
        return frozenset(span.location for span in paragraphs)
    for index, span in enumerate(paragraphs):
        if (getattr(span, "logical_zone", None) or getattr(span, "zone", "body")) not in {"body", "summary"}:
            continue
        section_path = str(getattr(span, "section_path", ""))
        if section_path and "基本情况" not in section_path:
            continue
        text = _compact(display_text(span.text)[0])
        if not text:
            continue
        heading = bool(_G06_SUBSECTION_RE.fullmatch(text)) or text in {
            "份额类别设置", "基金份额类别设置", "基金份额类别",
        }
        if not heading:
            continue
        end = len(paragraphs)
        for candidate_index, candidate in enumerate(paragraphs[index + 1:], index + 1):
            candidate_text = _compact(display_text(candidate.text)[0])
            if getattr(candidate, "section_path", "") != section_path:
                end = candidate_index
                break
            if (candidate_text and (
                    _G06_SUBSECTION_RE.fullmatch(candidate_text)
                    or bool(re.match(r"^[一二三四五六七八九十百零〇]+、", candidate_text))
                    or bool(re.match(r"^\d+[、.]", candidate_text)))):
                end = candidate_index
                break
        return frozenset(
            item.location for item in paragraphs[index:end]
            if (getattr(item, "logical_zone", None) or getattr(item, "zone", "body"))
            in {"body", "summary"}
            and str(getattr(item, "section_path", "")) == section_path
        )
    # Small unit fixtures often contain only the clause under test and no
    # numbered headings at all.  Preserve their isolated behaviour, while a
    # real structured contract with headings but no class subsection remains
    # fail-closed.
    has_numbered_heading = any(
        re.match(r"^[一二三四五六七八九十百零〇]+、", _compact(display_text(span.text)[0]))
        or re.match(r"^\d+[、.]", _compact(display_text(span.text)[0]))
        for span in paragraphs
    )
    if not has_numbered_heading:
        return frozenset(
            span.location for span in paragraphs
            if (getattr(span, "logical_zone", None) or getattr(span, "zone", "body"))
            in {"body", "summary"}
            and (not getattr(span, "section_path", "")
                 or "基本情况" in str(span.section_path))
        )
    # Older contracts and compact fixtures may place the canonical prohibition
    # directly in the basics chapter without a separate numbered subsection.
    # Keep this fallback exact and paragraph-bound: it does not authorize a
    # semantic sweep over the chapter and therefore cannot admit the D06 p280
    # one-way Y-class sentence.
    fallback = frozenset(
        span.location for span in paragraphs
        if "不同基金份额类别之间不得互相转换。" in _compact(str(span.text))
        and ("基本情况" in str(getattr(span, "section_path", ""))
             or not hasattr(span, "section_path"))
    )
    if fallback:
        return fallback
    return frozenset()


def g06_scoped_text(inspection: DocumentInspection) -> str:
    """Return only source text inside G06's physical subsection scope."""
    locations = g06_scope_locations(inspection)
    if not locations:
        return ""
    return "".join(
        str(span.text) for span in inspection.paragraphs
        if span.location in locations
    )


def g06_scope_present(inspection: DocumentInspection, location: str) -> bool:
    """Whether a physical paragraph belongs to the G06 subsection scope."""
    return location in g06_scope_locations(inspection)


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
    current_section_ids: list[str] = []
    section_ids = tuple(section.id for section in sections)
    base_id = "_".join(section_ids)

    def emit() -> None:
        nonlocal lines, total, current_locations, current_section_ids
        if lines:
            chunks.append(Window(id=f"{base_id}#{len(chunks) + 1}", section_ids=tuple(current_section_ids),
                                  locations=tuple(current_locations), text="\n".join(lines)))
            lines, total, current_locations = [], 0, []
            current_section_ids = []

    for section in sections:
        for location in section.locations:
            span = inspection.by_location(location)
            cleaned, _ = display_text(span.text)
            line = f"[{location}] {cleaned}"
            if lines and total + len(line) > max_chars:
                emit()
            lines.append(line)
            current_locations.append(location)
            if section.id not in current_section_ids:
                current_section_ids.append(section.id)
            total += len(line)
    emit()
    return chunks


def rule_locations_for_window(window: Window, sections: Sequence[Section],
                              mapping: Mapping[str, Sequence[str]]) -> dict[str, frozenset[str]]:
    """Return the physical locations each rule may inspect in one window.

    A window can contain several mapped sections and may be split into multiple
    character chunks. Its section membership is not the scope of every rule in
    that batch. Keeping this distinction explicit prevents
    a rule from borrowing a matching clause from a sibling section merely because
    both sections share a model request.
    """
    by_id = {section.id: section for section in sections}
    locations = set(window.locations)
    result: dict[str, frozenset[str]] = {}
    for rule_id, section_ids in mapping.items():
        allowed = {
            location
            for section_id in section_ids
            if (section := by_id.get(str(section_id))) is not None
            for location in section.locations
        }
        result[str(rule_id)] = frozenset(allowed & locations)
    return result


def rule_scope_locations(sections: Sequence[Section],
                         mapping: Mapping[str, Sequence[str]]) -> dict[str, frozenset[str]]:
    """Return only physical locations in sections explicitly mapped to each rule.

    A summary counterpart is eligible when the scope model maps its summary section
    for that rule.  The helper deliberately does not add every summary paragraph to
    every rule: summary is a zone, not a business subsection.
    """
    by_id = {section.id: section for section in sections}
    return {str(rule_id): frozenset({
        location for section_id in section_ids
        if (section := by_id.get(str(section_id))) is not None
        for location in section.locations}) for rule_id, section_ids in mapping.items()}


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


def expand_class_definition_scope(mapping: dict[str, list[str]],
                                  sections: Sequence[Section],
                                  inspection: DocumentInspection) -> dict[str, list[str]]:
    """Add the 释义 class-definition section to G04's mapped locations.

    The guide hints G04 at 基金的基本情况, but real contracts often put the
    complete A/C class definition in 释义 and only a fee-adjustment paragraph
    under 份额类别设置.  Without the definition section the inventory can only
    report an absent target at the fee paragraph.  This is a bounded anchor
    expansion, not a document-wide semantic sweep.
    """
    current = mapping.get("G04")
    if current is None:
        return mapping

    def _definition_anchor(text: str) -> bool:
        return (("基金份额类别" in text or "将基金份额分为" in text)
                and "称为" in text
                and len(set(re.findall(r"[A-ZＡ-Ｚ]类", text))) >= 2
                and any(token in text for token in ("申购费", "认购费", "销售服务费")))

    # G04's own sections may already carry the complete definition (纳斯达克
    # p169).  Expanding to 释义 in that case makes G04 and G02 edit the same
    # paragraph and their class substitutions overlap; G02 owns the 释义 copy.
    glossary_ids = {section.id for section in sections
                    if "释义" in str(getattr(section, "title", ""))}
    own_locations = {location for section in sections
                     if section.id in current and section.id not in glossary_ids
                     for location in section.locations}
    if any(_definition_anchor(_compact(display_text(span.text)[0]))
           for span in inspection.paragraphs
           if str(span.location) in own_locations):
        if any(section_id in glossary_ids for section_id in current):
            mapping["G04"] = [section_id for section_id in current
                              if section_id not in glossary_ids]
        return mapping
    by_location = {location: section.id for section in sections
                   for location in section.locations}
    for span in inspection.paragraphs:
        zone = getattr(span, "logical_zone", None) or getattr(span, "zone", "body")
        if zone not in {"body", "summary"}:
            continue
        text = _compact(display_text(span.text)[0])
        if not _definition_anchor(text):
            continue
        section_id = by_location.get(str(span.location))
        if section_id and section_id not in current:
            current.append(section_id)
        break
    return mapping


def rule_context(rules: Sequence[dict], *, full: bool) -> str:
    lines = ["GUIDE_RULES"]
    for rule in rules:
        lines.append(f"[{rule['rule_id']}] {rule['title']} | section_hint={rule.get('section_hint') or ''}")
        requirement = str(rule.get("requirement") or "")
        if full:
            lines.append(f"  requirement: {requirement}")
            for index, operation in enumerate(rule.get("operations") or []):
                kind = operation.get("op")
                identity = f"{rule['rule_id']}:{index}"
                if kind == "append":
                    lines.append(f"  [{identity}] append: "
                                 f"{_clip(operation.get('new_text') or '', 400)}")
                elif kind == "replace":
                    lines.append(f"  [{identity}] replace: "
                                 f"{_clip(operation.get('old_text') or '', 160)} -> "
                                 f"{_clip(operation.get('new_text') or '', 400)}")
                elif kind == "delete":
                    lines.append(f"  [{identity}] delete: "
                                 f"{_clip(operation.get('old_text') or '', 240)}")
                elif kind == "noop":
                    lines.append(f"  [{identity}] no change required by this branch")
        else:
            lines.append(f"  requirement: {_clip(requirement, 300)}")
    return "\n".join(lines)


def _clip(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit] + "…"


def scope_map(rules: Sequence[dict], sections: Sequence[Section], gateway: Any,
              gaps: list[dict[str, Any]] | None = None) -> dict[str, list[str]]:
    structure = structure_context(sections)
    valid_ids = {section.id for section in sections}
    # Preserve guide order when constructing the mapping.  The previous set based
    # comprehension made the insertion order depend on PYTHONHASHSEED, so a
    # record run and a fresh replay could build the same scope with different
    # rule ordering.  That changed inventory window prompt bytes and caused a
    # cassette miss even though all semantic inputs were identical.
    mapping: dict[str, list[str]] = {
        str(rule["rule_id"]): [] for rule in rules if rule.get("rule_id")
    }
    mentioned: set[str] = set()

    def _run(batch: Sequence[dict]) -> None:
        context = "\n\n".join([structure, rule_context(batch, full=False)])
        if len(context) > gateway.max_context_chars:
            if len(batch) > 1:
                # Context-limit recovery (plan §31): split the rule set, never end the
                # contract because one scope call was too large.
                middle = len(batch) // 2
                _run(batch[:middle])
                _run(batch[middle:])
                return
            raise RecallError("RECALL_SCOPE_CONTEXT_LIMIT",
                              {"chars": len(context), "rule": batch[0].get("rule_id")})
        result = gateway.call(task_type="recall_scope", bounded_context=context,
                              response_schema=SCOPE_SCHEMA, instruction=SCOPE_INSTRUCTION,
                              prompt_version=SCOPE_PROMPT_VERSION)
        value = result.value if isinstance(result.value, dict) else {}
        batch_ids = {rule["rule_id"] for rule in batch}
        for item in value.get("mappings") or []:
            if not isinstance(item, dict):
                continue
            rule_id = str(item.get("rule_id") or "")
            if rule_id not in batch_ids:
                continue
            mentioned.add(rule_id)
            ids = [str(section_id) for section_id in (item.get("section_ids") or [])
                   if str(section_id) in valid_ids]
            current = mapping.get(rule_id) or []
            for section_id in ids:
                if section_id not in current:
                    current.append(section_id)
            mapping[rule_id] = current

    _run(list(rules))
    omitted = [rule for rule in rules if str(rule.get("rule_id")) not in mentioned]
    if omitted:
        # One bounded retry with only the omitted rules. A model answer that silently
        # drops a rule is not evidence that the clause is absent (plan §32).
        _run(omitted)
        still_omitted = [rule for rule in omitted
                         if str(rule.get("rule_id")) not in mentioned]
        if gaps is not None:
            for rule in still_omitted:
                gaps.append({"rule_id": str(rule.get("rule_id")),
                             "code": "SCOPE_RULE_OMITTED",
                             "reason": "scope answer omitted the rule after a focused retry"})
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
    # Operation identities this target covers (``G05:0`` = rule G05, operation index 0).
    # Inventory targets usually leave this empty; survey targets and satisfied hits set
    # it so coverage is operation-aware (FL-D117).
    operations: tuple[str, ...] = ()
    # Inventory/model claimed identity that failed code attribution.  Kept for report
    # traceability and site-scoped Claim Replay, but never used for planning/coverage.
    claimed_operations: tuple[str, ...] = ()
    # Set when the target's claimed operation identity could not be proven on the bound
    # span.  Such a target must not be planned or audited; the operation recovery layer
    # may create a correct operation-specific target instead.
    attribution_error: str = ""
    # Deterministic paragraph candidates for an open-obligation T3 locate (each one
    # passed the code anchor gate).  The locator may only choose inside this set.
    site_candidates: tuple[str, ...] = ()
    # Which exact occurrence of the operation's old_text this target owns, and the
    # inventory quote that identifies it (G02/G04 same-paragraph occurrences).
    occurrence_index: int = -1
    occurrence_anchor: str = ""
    # Physical rule-scope identity the target was admitted under (``G06:S04:L05``).
    # Empty on legacy/frozen replays; the planning gate stamps it for new runs.
    scope_id: str = ""
    # Code-verified semantic approval for this target's operation (see
    # ``semantic_evidence.SemanticApproval``).  When present and valid, later
    # stages consume this one record instead of re-deciding the same semantic
    # question with their own word list (R01-R03).  The raw inventory claim stays
    # in ``claimed_operations`` and is never treated as an approval.
    approval_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "rule_id": self.rule_id, "location": self.location,
            "quote": self.quote, "state": self.state, "reason": self.reason,
            "start": self.start, "end": self.end, "resolution": self.resolution,
            "segment_ok": self.segment_ok, "composite": list(self.composite),
            "operations": list(self.operations),
            "claimed_operations": list(self.claimed_operations),
            "attribution_error": self.attribution_error,
            "site_candidates": list(self.site_candidates),
            "occurrence_index": self.occurrence_index,
            "occurrence_anchor": self.occurrence_anchor,
            "out_of_scope": self.out_of_scope,
            "scope_id": self.scope_id,
            "approval_id": self.approval_id,
        }


def inventory_window(window: Window, rules: Sequence[dict], facts: Facts, gateway: Any,
                     inspection: DocumentInspection, *,
                     rule_locations: Mapping[str, Iterable[str]] | None = None
                     ) -> tuple[list[Target], dict[str, Any]]:
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
        if rule_locations is not None and location not in set(rule_locations.get(rule_id, ())):
            dropped.append({"reason": "INVENTORY_ITEM_OUT_OF_RULE_SCOPE", "item": item})
            continue
        key = (rule_id, location, _compact(quote))
        if key in seen:
            continue
        seen.add(key)
        counter += 1
        target = Target(target_id=f"{window.id}:T{counter:03d}", rule_id=rule_id, location=location,
                        quote=quote, state=state, reason=str(item.get("reason") or ""))
        operation_id = str(item.get("operation_id") or "").strip()
        if re.fullmatch(re.escape(rule_id) + r":\d+", operation_id):
            target.operations = (operation_id,)
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
    operation_keys: tuple[str, ...] = ()

    @property
    def parts(self) -> tuple[tuple[str, int, int], ...]:
        """Per-paragraph slices that make up this occurrence."""
        return getattr(self, "_parts", ()) or ()

    def with_parts(self, parts: tuple[tuple[str, int, int], ...]) -> "SurveyHit":
        object.__setattr__(self, "_parts", parts)
        return self


def operation_search_key_pairs(rule: dict, condition_facts: "Facts | None" = None
                               ) -> list[tuple[str, str]]:
    """Search keys paired with the operation identity that produced them.

    ``G05:1`` identifies the second operation of rule G05 (zero-based array index).
    The key drives the deterministic search; the identity lets coverage be tracked per
    operation, so a satisfied replacement cannot hide a still-present deletion
    (FL-D117). Variants not tied to one operation use ``"*"``.
    """
    rule_id = str(rule.get("rule_id") or "")
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def add(key: str, operation_key: str) -> None:
        compact = _compact(key)
        if compact and (operation_key, compact) not in seen:
            seen.add((operation_key, compact))
            pairs.append((operation_key, compact))

    core = f"{rule.get('title') or ''}{rule.get('requirement') or ''}"
    core_grams = _character_ngrams(_compact(core), 3) if core else set()
    operations = list(rule.get("operations") or [])
    for index, operation in enumerate(operations):
        if condition_facts is not None and not condition_matches(operation.get("condition"), condition_facts):
            continue
        operation_key = _rule_operation_key(rule, index)
        old_raw = str(operation.get("old_text") or "")
        old_text = _compact(old_raw)
        if len(old_text) < 8:
            continue
        add(old_text, operation_key)
        if operation.get("op") != "delete":
            continue
        for fragment in reference_fragments(old_raw):
            if not old_text.endswith(fragment):
                continue
            if any(fragment in _compact(str(other.get("new_text") or ""))
                   or fragment in _compact(str(other.get("old_text") or ""))
                   for other in operations):
                # The fragment also lives in a sibling operation's own text, so that
                # operation (not this one) covers it.
                continue
            if core_grams and not (_character_ngrams(fragment, 3) & core_grams):
                continue
            add(fragment, operation_key)
        # Contracts spell the same clause with a different lead-in and a different tail:
        # the guide writes "C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金
        # 托管人发送…" while a contract writes "基金销售服务费每日计提，逐日累计至每月月末，
        # 按月支付，经基金管理人与基金托管人核对一致后…". Neither the long reference nor
        # its tail matches, so the rule's leading domain phrase (the reference without its
        # class prefix, up to the first clause boundary) is the anchor that does (FL-D052).
        first_clause = _CLAUSE_SPLIT.split(_strip_class_lead(old_text) or old_text)[0]
        if len(first_clause) >= 8:
            if any(first_clause in _compact(str(other.get("new_text") or ""))
                   or (other is not operation
                       and first_clause in _compact(str(other.get("old_text") or "")))
                   for other in operations):
                continue
            if core_grams and (_character_ngrams(first_clause, 3) & core_grams):
                add(first_clause, operation_key)
    for variant in rule.get("old_text_variants") or []:
        compact = _compact(str(variant))
        if len(compact) >= 8:
            add(compact, "*")
    return pairs


def operation_search_keys(rule: dict, condition_facts: "Facts | None" = None) -> list[str]:
    """Reference texts that can anchor a deterministic search for a rule's targets.

    The rule's own reference texts are used verbatim. When every applicable
    operation is a deletion, a shorter tail of the reference also qualifies, but
    only when it shares domain wording (a character trigram) with the rule's title
    or requirement — this keeps "并报中国证监会备案" while rejecting fragments that
    coincide with unrelated generic sentences (FL-D047).
    """
    keys: list[str] = []
    for _operation_key, key in operation_search_key_pairs(rule, condition_facts):
        if key not in keys:
            keys.append(key)
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

# Stable business-word variants used by the deterministic delete fallback.  The guide
# wording is often ``每日计提、按月支付`` while contracts write ``每日计算、次月支付``;
# treating those as unrelated leaves a whole payment clause invisible to recall.  These
# aliases are deliberately narrow and remain inside the same fee/payment topic.
_KEYWORD_VARIANTS: dict[str, tuple[str, ...]] = {
    "计提": ("计提", "计算"),
    "计算": ("计算", "计提"),
    "按月": ("按月", "每月", "次月", "月末"),
    "每月": ("每月", "按月", "次月", "月末"),
    "次月": ("次月", "按月", "每月", "月末"),
    "逐日": ("逐日", "每日"),
    "每日": ("每日", "逐日"),
    "支付": ("支付", "划付", "划款"),
    "划付": ("划付", "支付", "划款"),
    "划款": ("划款", "支付", "划付"),
}


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
    topic_tokens = _RULE_TOPIC_TOKENS.get(str(rule.get("rule_id") or ""), ())
    best: tuple[int, str] | None = None
    for candidate in _final_clause_candidates(_compact(combined)):
        if candidate not in compact_body:
            continue
        # A generic closing formula ("并在招募说明书中列示。") shares trigrams with the
        # requirement but proves nothing about this rule: the candidate must carry the
        # rule's own topic wording, otherwise a neighbouring clause that happens to end
        # the same way reads as "already satisfied" (FL-D119).
        if topic_tokens and not any(token in candidate for token in topic_tokens):
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
_FEE_DIFFERENCE_MARKERS = (
    "费用收取不同", "费用收取上不同", "费用的不同", "费用不同",
    "费率不同", "费用存在差异")


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
    if ("费用收取不同" in compact_new
            and "各基金份额类别在费用收取上不同" in compact_body
            and any(token in compact_body for token in ("可分配收益", "分别计算"))):
        return True
    # A generic ``由于基金费用的不同`` sentence is insufficient for G18.  The
    # instantiated policy names two fee groups, so the same physical sentence must
    # carry those class groups in that order.  Checking the ordered labels also
    # rejects D06 p132, where all five classes are listed as one undifferentiated
    # set (FL-D06-G18).
    expected_groups = re.findall(
        r"((?:[A-ZＡ-Ｚ]类)(?:、[A-ZＡ-Ｚ]类)*)基金份额"
        r"(?:和|及|与)((?:[A-ZＡ-Ｚ]类)(?:、[A-ZＡ-Ｚ]类)*)基金份额",
        compact_new)
    if expected_groups:
        def group_is_contiguous(sentence: str, labels: Sequence[str], start: int = 0
                                ) -> int | None:
            cursor = start
            for label in labels:
                match = re.search(re.escape(label), sentence[cursor:])
                if match is None:
                    return None
                between = sentence[cursor:cursor + match.start()]
                if re.search(r"[A-ZＡ-Ｚ]类", between):
                    return None
                cursor += match.end()
            return cursor

        for sentence in re.split(r"[。；;！？!?]", compact_body):
            # ``expected_groups`` already contains the literal ``A类`` tokens;
            # no unrelated class label may fill a group slot.
            first = re.findall(r"[A-ZＡ-Ｚ]类", expected_groups[0][0])
            second = re.findall(r"[A-ZＡ-Ｚ]类", expected_groups[0][1])
            first_end = group_is_contiguous(sentence, first)
            if first_end is not None and group_is_contiguous(sentence, second, first_end) is not None:
                return True
        return False
    expected_labels = re.findall(r"[A-ZＡ-Ｚ]类", compact_new)
    if expected_labels and not all(label in compact_body for label in expected_labels):
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


def _g17_usage_exclusion_matches(quote: str, references: Sequence[str]) -> bool:
    """Match one complete usage-exclusion sentence to this operation's own text.

    Class leads and the optional possessive in ``销售服务费的使用范围`` do not
    change the exclusion. Fee subject, negation, period and the rest of the
    sentence must still match; neither a topic keyword nor proximity authorizes it.
    """
    def normalize(value: str) -> str:
        compact = _compact(value)
        compact = _strip_class_lead(compact) or compact
        if compact.startswith("基金销售服务费"):
            compact = compact[2:]
        return compact.replace("销售服务费的使用范围", "销售服务费使用范围", 1)

    expected = "销售服务费使用范围不包括基金募集期间的上述费用"
    actual = normalize(quote)
    if not re.fullmatch(re.escape(expected) + r"[。；;]", actual):
        return False
    return any(normalize(sentence).rstrip("。；;") == expected
               for reference in references
               for sentence in re.split(r"(?<=[。；;])", _compact(reference))
               if sentence)


def _g17_source_sentence_parts(inspection: Any, operations: Sequence[Mapping[str, Any]],
                               *, locations: Iterable[str] | None = None
                               ) -> list[tuple[tuple[str, int, int], ...]]:
    """Find complete operation-owned sentences, in compact source coordinates.

    ``locations`` restricts the scan to one rule's physical scope, so a G17
    deletion can never be proven from a paragraph outside that scope.
    """
    allowed = {str(location) for location in locations} if locations is not None else None
    paragraphs = [span for span in inspection.paragraphs
                  if allowed is None or str(span.location) in allowed]
    body, coordinates, boundaries = "", [], {0}
    for span in paragraphs:
        compact, _ = compact_offsets(str(span.text))
        boundaries.add(len(body))
        body += compact
        coordinates.extend((str(span.location), index) for index in range(len(compact)))
    occurrences: list[tuple[tuple[str, int, int], ...]] = []
    for operation in operations:
        if operation.get("op") != "delete":
            continue
        for sentence in re.findall(r"[^。；;！？!?]+[。；;！？!?]", _compact(
                str(operation.get("old_text") or ""))):
            normalized = _strip_class_lead(sentence) or sentence
            if normalized.startswith("基金销售服务费"):
                normalized = normalized[2:]
            if normalized.startswith("销售服务费"):
                pattern = r"(?:[A-Z]类基金份额的?)?(?:基金)?" + re.escape(normalized)
                # Finite equivalent wording from source contracts; preserve every
                # fee subject, predicate, polarity, period and complete sentence.
                pattern = pattern.replace("、以及", r"[、，,](?:以及|及)")
                pattern = pattern.replace("基金份额持有人服务费", "(?:基金份额)?持有人服务费")
                pattern = pattern.replace("销售服务费的使用范围不包括", "销售服务费(?:的?使用范围)?不包括")
                pattern = pattern.replace("销售服务费使用范围不包括", "销售服务费(?:的?使用范围)?不包括")
                if pattern[-1:] in "。；;":
                    pattern = pattern[:-1] + r"[。；;]"
            else:
                pattern = re.escape(sentence)
            for match in re.finditer(pattern, body):
                if match.start() not in boundaries and body[match.start() - 1] not in "。；;！？!?":
                    continue
                parts: list[tuple[str, int, int]] = []
                for loc, index in coordinates[match.start():match.end()]:
                    if parts and parts[-1][0] == loc:
                        parts[-1] = (loc, parts[-1][1], index + 1)
                    else:
                        parts.append((loc, index, index + 1))
                occurrence = tuple(parts)
                if occurrence and occurrence not in occurrences:
                    occurrences.append(occurrence)
    return occurrences


def _g17_source_effect_owned(inspection: Any, location: str, start: int, end: int,
                             replacement: str, operations: Sequence[Mapping[str, Any]],
                             *, locations: Iterable[str] | None = None) -> bool:
    """Prove deletions from complete source sentences, never planner provenance."""
    if any(operation.get("op") != "delete" for operation in operations):
        return False
    intervals = [(left, right)
                 for occurrence in _g17_source_sentence_parts(
                     inspection, operations, locations=locations)
                 for loc, left, right in occurrence if loc == location]
    try:
        source = str(inspection.by_location(location).text)
    except (KeyError, ValueError, AttributeError):
        return False
    if not 0 <= start < end <= len(source):
        return False
    compact_start, compact_end = len(_compact(source[:start])), len(_compact(source[:end]))
    owned = sorted(set((left, right) for left, right in intervals
                       if compact_start <= left < right <= compact_end))
    if not owned:
        return False
    compact = _compact(source)
    kept, cursor = [], compact_start
    for left, right in owned:
        if left < cursor:
            continue
        kept.append(compact[cursor:left])
        cursor = right
    kept.append(compact[cursor:compact_end])
    return _compact(replacement) == "".join(kept)


_SENTENCE_TERMINATORS = "。！？；!?;"


def _approved_span_is_complete_clause(text: str, target: Any) -> bool:
    """Whether the approved span is a whole sentence (or the rest of a paragraph).

    Deleting a mid-sentence slice would leave an unreadable fragment; the approved
    delete path is therefore limited to complete clauses.  The quote itself was
    already verified against the source when the approval was created.
    """
    start, end = getattr(target, "start", None), getattr(target, "end", None)
    if start is None or end is None or not text:
        return False
    start, end = int(start), int(end)
    if not 0 <= start < end <= len(text):
        return False
    quote = text[start:end]
    if not quote.strip():
        return False
    if quote.rstrip().endswith(tuple(_SENTENCE_TERMINATORS)):
        return True
    return not text[end:].strip()


def _approved_delete_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Extend an approved clause span over its terminator and adjacent spaces."""
    if not 0 <= start < end <= len(text):
        return start, end
    while start > 0 and text[start - 1] in " \t\u3000":
        start -= 1
    if end < len(text) and text[end] in _SENTENCE_TERMINATORS:
        end += 1
    return start, end


def _g17_target_is_owned_sentence(inspection: Any, target: Any,
                                  operations: Sequence[Mapping[str, Any]]) -> bool:
    """Whether the target span is exactly one complete operation-owned sentence."""
    if getattr(target, "start", None) is None or getattr(target, "end", None) is None:
        return False
    try:
        span = inspection.by_location(target.location)
    except (KeyError, ValueError, AttributeError):
        return False
    body, _offsets = compact_offsets(span.text)
    left = len(_compact(span.text[:int(target.start)]))
    right = len(_compact(span.text[:int(target.end)]))
    if left >= right or right > len(body):
        return False
    for parts in _g17_source_sentence_parts(inspection, operations):
        if (len(parts) == 1 and parts[0][0] == target.location
                and parts[0][1] == left and parts[0][2] == right):
            return True
    return False


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


# The survey fuzzy pass must not turn a *topic flip* into a hit: contracts write
# "本基金的赎回费率由基金管理人决定…" while the G08 reference reads "申购费率";
# one swapped word is a different clause, not a wording variant (FL-D119).
_CONFUSABLE_SWAPS: tuple[tuple[str, str], ...] = (
    ("申购", "赎回"), ("认购", "申购"), ("认购", "赎回"),
    ("基金托管人", "基金管理人"), ("托管费", "管理费"), ("A类", "C类"),
)


def _semantic_flip_only(target: str, window: str) -> bool:
    """True when ``window`` equals ``target`` with only a confusable word swapped."""
    # A differing trailing punctuation mark does not make it a different clause; the
    # flip is still a topic change (G08 认购 vs 申购 p156).
    trim = "。；;！？!?，, "
    target_clean = _compact(target).rstrip(trim)
    window_clean = _compact(window).rstrip(trim)
    if not target_clean or not window_clean or target_clean == window_clean:
        return False
    for left, right in _CONFUSABLE_SWAPS:
        for old, new in ((left, right), (right, left)):
            if target_clean.count(old) and window_clean == target_clean.replace(old, new):
                return True
    return False


def _numeric_flip_only(target: str, window: str) -> bool:
    """True when ``window`` equals ``target`` with only numeric tokens swapped."""
    trim = "。；;！？!?，, "
    target_clean = _compact(target).rstrip(trim)
    window_clean = _compact(window).rstrip(trim)
    number = re.compile(r"\d+(?:\.\d+)?%?")
    target_numbers = number.findall(target_clean)
    window_numbers = number.findall(window_clean)
    if not target_numbers or len(target_numbers) != len(window_numbers):
        return False
    if target_numbers == window_numbers:
        return False
    return number.split(target_clean) == number.split(window_clean)


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
        # Keep scanning.  A contract may contain several copies of the same clause,
        # including copies split at different paragraph boundaries.  Returning after
        # the first split occurrence used to suppress later sites (recall-first rule).
    # Short reference texts only ever match exactly: a fuzzy ratio over a short
    # string is too easy to satisfy for a different sentence (FL-D047).
    if len(target) < 24 or threshold < 0.9:
        return found
    needle_grams = _character_ngrams(target, 2)
    best: dict[str, tuple[tuple[str, int, int], ...]] = {}
    for span in paragraphs:
        # ``find_old_text_all`` is a public deterministic resolver and is also called
        # outside ``survey_targets`` (for example during artifact replay).  Do not rely
        # on the survey's process-local n-gram cache being warmed; an empty cache used
        # to suppress every fuzzy candidate on direct calls.
        # Location ids restart at ``p0`` for every DOCX, so a process-global cache can
        # carry grams from a previous contract.  Compute this tiny per-paragraph filter
        # from the current text; survey_targets may still warm its cache for diagnostics,
        # but correctness must never depend on it.
        span_grams = _character_ngrams(texts[span.location], 2)
        if not (span_grams & needle_grams):
            continue
        # References ending in sentence punctuation must bind the complete source
        # sentence.  A raw fuzzy window can stop a few characters early (leaving
        # "配。" or swallowing the next clause); clause snapping preserves the true
        # operation range while still allowing wording variants.
        variant = fuzzy_span_clause(span.text, old_text, threshold=threshold,
                                    variable_length=True)
        if variant is None:
            continue
        matched_window = span.text[variant[0]:variant[1]]
        # A one-word topic flip (申购/赎回, 认购/申购, …) or a bare number swap is
        # a different clause, never a wording variant (FL-D119).
        if _semantic_flip_only(old_text, matched_window) \
                or _numeric_flip_only(old_text, matched_window):
            continue
        start_raw, end_raw, _ratio = variant
        # ``fuzzy_span`` returns offsets in the raw paragraph (including spaces and
        # barrier markers), while occurrence parts are offsets in the whitespace-free
        # text.  Mapping through ``compact_offsets`` keeps rebind/replay ranges stable
        # when the variant has a different length from the guide reference.
        _compact_text, compact_map = compact_offsets(span.text)
        compact_start = _raw_to_compact(compact_map, start_raw)
        compact_end = _raw_to_compact(compact_map, end_raw)
        if compact_end <= compact_start:
            continue
        best[span.location] = ((span.location, compact_start, compact_end),)
    # Exact/split occurrences and bounded wording variants are both valid recall
    # candidates.  Keep every fuzzy site, de-duplicating against the exact start
    # offsets already recorded.  Previously fuzzy search ran only when *no* exact
    # occurrence existed, so a second paraphrased copy of a clause was silently
    # dropped whenever one exact copy was present.
    for occurrence in best.values():
        location, start, end = occurrence[0]
        # Exact text is stronger evidence than fuzzy text.  If the candidate overlaps
        # an already recorded exact/split occurrence in the same paragraph, retain the
        # exact binding and avoid producing two edits for one clause.  Disjoint
        # occurrences (including an exact body copy and a paraphrased summary copy)
        # remain independent recall hits.
        if any(existing_location == location and max(existing_start, start) < min(existing_end, end)
               for existing_location, existing_start, existing_end in
               ((part[0], part[1], part[2]) for item in found for part in item)):
            continue
        key = (location, start)
        if key not in seen:
            found.append(occurrence)
            seen.add(key)
    return found


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


def operation_key(rule_id: str, index: int) -> str:
    """Stable internal identity for one guide operation (``G05:1``)."""
    return f"{rule_id}:{index}"


def _declared_operation_key(rule_id: str, index: int,
                            operation: Mapping[str, Any] | None = None) -> str:
    """Return the operation identity declared by the guide.

    Released guides carry ``operation_id``.  The derived ``RULE:index`` form is
    retained for old low-level fixtures, but it is not evidence that a guide
    operation has been registered for routed execution.
    """
    declared = str((operation or {}).get("operation_id") or "").strip().upper()
    return declared or operation_key(str(rule_id).strip().upper(), index)


def _rule_operation_key(rule: Mapping[str, Any], index: int) -> str:
    """Resolve one operation identity from the rule declaration."""
    operations = rule.get("operations") or ()
    operation = operations[index] if 0 <= index < len(operations) else None
    return _declared_operation_key(
        str(rule.get("rule_id") or ""), index,
        operation if isinstance(operation, Mapping) else None,
    )


def _registry_execution_authoritative(rule: Mapping[str, Any]) -> bool:
    """Whether a rule carries a complete explicit operation contract.

    A partially annotated rule is unsafe: deriving the missing sibling identity
    would recreate the sibling-borrowing defect.  Such a rule fails closed in
    the routed caller; wholly legacy fixtures remain low-level compatible.
    """
    operations = [operation for operation in (rule.get("operations") or [])
                  if isinstance(operation, Mapping)]
    if not operations:
        return False
    declared = [str(operation.get("operation_id") or "").strip()
                for operation in operations]
    if any(declared) and not all(declared):
        raise RecallError("RECALL_OPERATION_ID_MISSING", {
            "rule": str(rule.get("rule_id") or ""),
        })
    return bool(any(declared)) and all(declared)


def satisfied_operation_keys(rule: dict, facts: Facts, compact_body: str) -> set[str]:
    """Operation keys whose own replacement/append text is already present.

    ``satisfied_by_new_text`` is a rule-level signal; the per-operation keys let the
    caller mark only the operations that are actually carried out, so G05's satisfied
    replace no longer covers its still-pending delete (FL-D117).
    """
    keys: set[str] = set()
    rule_id = str(rule.get("rule_id") or "")
    for index, operation in enumerate(rule.get("operations") or []):
        if operation.get("op") not in {"replace", "append"}:
            continue
        if not condition_matches(operation.get("condition"), facts):
            continue
        instantiated, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        if issues or not instantiated:
            continue
        compact = _compact(instantiated)
        if compact and compact in compact_body:
            keys.add(_rule_operation_key(rule, index))
            continue
        # The paragraph may express the same operation with reordered subjects or a
        # connector ("…A/C类基金份额费用收取不同" vs "由于基金费用的不同，本基金A/C类
        # 基金份额将分别计算…").  Reuse the rule-level equivalence for this one
        # operation so a satisfied target can still carry its operation identity.
        single = {
            "rule_id": rule_id,
            "title": rule.get("title") or "",
            "requirement": rule.get("requirement") or "",
            "operations": [operation],
        }
        if satisfied_by_new_text(single, facts, compact_body):
            keys.add(_rule_operation_key(rule, index))
    return keys


def _target_paragraphs(target: Target) -> list[str]:
    composite = getattr(target, "composite", ()) or ()
    if composite:
        return [part.rsplit(":", 2)[0] for part in composite]
    return [target.location]


def source_parts_contiguous(inspection: DocumentInspection, locations: Sequence[str]) -> bool:
    """Whether source parts stay in one physical section and readable zone.

    Empty paragraphs may separate Word wraps; nonempty intervening paragraphs,
    headings, reversed/repeated addresses and chapter/zone changes may not.
    This proves geometry only; operation-specific policy checks remain required.
    """
    paragraphs = list(inspection.paragraphs)
    positions = {span.location: index for index, span in enumerate(paragraphs)}
    if not locations or len(set(locations)) != len(locations):
        return False
    if any(location not in positions for location in locations):
        return False
    spans = [paragraphs[positions[location]] for location in locations]
    first = spans[0]
    zone = getattr(first, "logical_zone", None) or getattr(first, "zone", "body")
    section = str(getattr(first, "section_path", ""))
    if zone not in SURVEY_ZONES:
        return False
    for index, span in enumerate(spans):
        if ((getattr(span, "logical_zone", None) or getattr(span, "zone", "body")) != zone
                or str(getattr(span, "section_path", "")) != section):
            return False
        if index:
            left, right = positions[locations[index - 1]], positions[span.location]
            if right <= left:
                return False
            if any(item.text.strip() for item in paragraphs[left + 1:right]):
                return False
            if _looks_like_heading(span.text):
                return False
    return True


def _target_source_body(target: Target, inspection: DocumentInspection) -> str:
    """Read only the source slices owned by a target, never their whole paragraphs."""
    if target.composite:
        locations = _target_paragraphs(target)
        if not source_parts_contiguous(inspection, locations):
            raise RecallError("RECALL_TARGET_COMPOSITE_BOUNDARY", {"target": target.target_id})
        bodies: list[str] = []
        for part in target.composite:
            try:
                location, left, right = part.rsplit(":", 2)
                body, _ = compact_offsets(inspection.by_location(location).text)
                start, end = int(left), int(right)
                if not 0 <= start < end <= len(body):
                    raise ValueError
            except (ValueError, KeyError, DocxError):
                raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
            bodies.append(body[start:end])
        return "".join(bodies)
    span = inspection.by_location(target.location)
    if target.start is not None and target.end is not None:
        return _compact(span.text[int(target.start):int(target.end)])
    return _compact(display_text(span.text)[0])


def target_operation_keys(target: Target, rule: dict | None,
                          inspection: DocumentInspection | None) -> set[str]:
    """Operations this target actually contains (explicit keys first, then span text)."""
    keys = set(getattr(target, "operations", ()) or ())
    if keys or rule is None or inspection is None:
        return keys
    try:
        body = _target_source_body(target, inspection)
    except (RecallError, KeyError, DocxError):
        return keys
    rule_id = str(rule.get("rule_id") or "")
    if rule_id == "G14":
        body = _normalise_fee_rate_reference(body)
    for index, operation in enumerate(rule.get("operations") or []):
        old = str(operation.get("old_text") or "")
        old = (_normalise_fee_rate_reference(old) if rule_id == "G14"
               else _compact(old))
        if old and old in body:
            keys.add(_rule_operation_key(rule, index))
    return keys


def _normalise_operation_ids(rule: dict, keys: Sequence[str], obligations: Any = None) -> list[int]:
    """Map operation aliases/obligation ids to valid, condition-TRUE operation indices."""
    rule_id = str(rule.get("rule_id") or "")
    operations = list(rule.get("operations") or [])
    indices: set[int] = set()
    for raw in keys:
        key = str(raw or "").strip()
        if not key:
            continue
        record = obligations.record(key) if obligations is not None else None
        if record is not None and str(getattr(record.spec, "rule_id", "") or
                                      rule_id) == rule_id:
            indices.add(int(record.spec.operation_index))
            continue
        for index, operation in enumerate(operations):
            if key in {
                _declared_operation_key(rule_id, index, operation),
                operation_key(rule_id, index),
            }:
                indices.add(index)
                break
    return sorted(index for index in indices if 0 <= index < len(operations))


def _selected_operation_indices(rule: dict, target: Target,
                                inspection: DocumentInspection, facts: Facts,
                                obligations: Any = None) -> list[int]:
    """Operation indices this target is authorized to execute.

    Explicit target operation identity wins.  Otherwise the real bound span is the
    evidence: operations whose own old_text is inside it are selected.  A target with
    no text attribution is only auto-assigned when the rule has exactly one applicable
    operation; anything else fails closed instead of re-running the whole rule.
    """
    rule_id = str(rule.get("rule_id") or "")
    operations = list(rule.get("operations") or [])
    if not operations:
        return []
    true_indices = [index for index, operation in enumerate(operations)
                    if condition_status(operation.get("condition"), facts) == "TRUE"]
    if not true_indices:
        return []
    explicit = [str(key) for key in (getattr(target, "operations", ()) or ()) if str(key)]
    if explicit:
        selected = _normalise_operation_ids(rule, explicit, obligations)
        invalid = [key for key in explicit
                   if not _normalise_operation_ids(rule, [key], obligations)]
        if invalid:
            raise RecallError("RECALL_TARGET_OPERATION_UNATTRIBUTED",
                              {"target": target.target_id, "rule": rule_id,
                               "operations": invalid})
        selected = [index for index in selected if index in true_indices]
        if not selected:
            raise RecallError("RECALL_TARGET_OPERATION_UNATTRIBUTED",
                              {"target": target.target_id, "rule": rule_id,
                               "reason": "explicit_operation_not_applicable"})
        # An explicit operation id is not enough: the bound span must actually carry the
        # operation's reference wording (or a declared variant).  Otherwise a model
        # "absent" target with the wrong quote could make the planner delete an
        # unrelated sentence (D01 G05 p135).
        span_body = _target_source_body(target, inspection)
        if rule_id == "G14":
            span_body = _normalise_fee_rate_reference(span_body)
        if (rule_id == "G12" and len(selected) == 1
                and "赎回费总额的" in span_body and "7日" in span_body):
            # G12 has two certified historical wordings for the same obligation.
            # This source carries the explicit 25% allocation plus the 7-day
            # sentence, which is G12:1's shape, not G12:0's generic wording.
            # Selecting the variant by source shape is operation identity, not a
            # file-specific patch: both alternatives share the same ONE_OF group
            # and new policy text.
            current_op = operations[selected[0]]
            group = str(current_op.get("one_of_group") or "")
            preferred = [index for index in true_indices
                         if index != selected[0] and group
                         and str(operations[index].get("one_of_group") or "") == group
                         and "未归入基金财产的部分" in _compact(
                             str(operations[index].get("old_text") or ""))]
            if len(preferred) == 1:
                selected = preferred
        if rule_id in {"G02", "G04"} and bool(rule.get("class_substitution")):
            # A full fee-group clause can prove both class substitutions even when
            # Inventory attached only one explicit operation id.  A heading that
            # merely lists A/C/D has no fee wording and must not gain sibling keys.
            from .generation.effects import _class_group_equivalent
            quote_body = _compact(target.quote) or span_body
            if any(token in quote_body for token in ("申购费", "认购费", "销售服务费")):
                for index in true_indices:
                    if index in selected:
                        continue
                    operation = operations[index]
                    expected, issues = instantiate_slots(
                        str(operation.get("new_text") or ""), facts)
                    if not issues and expected and _class_group_equivalent(
                            expected, quote_body):
                        selected.append(index)
                selected = sorted(set(selected))
        variants = [_compact(str(value)) for value in (rule.get("old_text_variants") or [])]
        if rule_id == "G14":
            variants = [_normalise_fee_rate_reference(value) for value in variants]
        for index in selected:
            operation = operations[index]
            raw_old = str(operation.get("old_text") or "")
            old_text = (_normalise_fee_rate_reference(raw_old) if rule_id == "G14"
                        else _compact(raw_old))
            if operation.get("op") not in {"replace", "delete"} or not old_text:
                continue
            if rule_id in {"G02", "G04"} and bool(rule.get("class_substitution")):
                # G02/G04 rewrite the class-definition sentence with the product's
                # actual class groups; the guide's example letters need not appear.
                continue
            if old_text in span_body:
                continue
            if any(value and value in span_body for value in variants):
                continue
            if (rule_id == "G17" and operation.get("op") == "delete"
                    and _g17_usage_exclusion_matches(span_body, [raw_old])):
                continue
            if (rule_id == "G15" and _g15_delay_continuation(
                    inspection, target.location, operation) == (target.start, target.end)
                    and _same_compact(target.quote, span_body)):
                continue
            # A payment clause may be split exactly at the paragraph boundary:
            # this target owns the payment head and the next paragraph owns only
            # the immediate delay sentence.  The joined source is validated by
            # _g15_split_payment_head_owned; the head alone cannot match the
            # guide's full reference text or its similarity threshold.
            if rule_id == "G15" and _g15_split_payment_head_owned(
                    inspection, target, operation):
                continue
            if any(_compact(fragment) in span_body
                   for value in variants for fragment in reference_fragments(value)):
                continue
            # A one-word topic flip is a different clause, not a paraphrase.  A model
            # target quoting the 认购费率 sentence must not be accepted for G08's
            # 申购费率 operation (live p156 false target).
            if _semantic_flip_only(raw_old, span_body) or _numeric_flip_only(raw_old, span_body):
                raise RecallError("RECALL_TARGET_OPERATION_UNATTRIBUTED",
                                  {"target": target.target_id, "rule": rule_id,
                                    "operation": _rule_operation_key(rule, index),
                                   "reason": "operation_topic_flip"})
            # Real contracts paraphrase or prefix-strip the reference ("C类基金份额的
            # 销售服务费每日计提…" vs "基金销售服务费每日计提…").  Accept a bounded
            # similarity, never a completely different sentence.
            if _sequence_ratio(old_text, span_body) >= 0.35:
                continue
            raise RecallError("RECALL_TARGET_OPERATION_UNATTRIBUTED",
                              {"target": target.target_id, "rule": rule_id,
                                "operation": _rule_operation_key(rule, index),
                               "reason": "operation_span_mismatch"})
        return selected
    inferred = _normalise_operation_ids(
        rule, sorted(target_operation_keys(target, rule, inspection)), obligations)
    inferred = [index for index in inferred if index in true_indices]
    if inferred:
        # The bound span itself contains these operations' reference wording; every
        # one of them is carried by this target (G05's whole-paragraph inventory quote
        # legitimately contains both the replace and the delete).  A span that proves
        # no operation is the ambiguous case and fails closed below.
        return sorted(set(inferred))
    if len(true_indices) == 1:
        return [true_indices[0]]
    raise RecallError("RECALL_TARGET_OPERATION_UNATTRIBUTED",
                      {"target": target.target_id, "rule": rule_id,
                       "operations": [_rule_operation_key(rule, index) for index in true_indices]})


def assign_target_operations(targets: Sequence[Target], rules_by_id: dict[str, dict],
                             inspection: DocumentInspection, facts: Facts,
                             obligations: Any = None) -> list[dict[str, Any]]:
    """Assign one operation identity to every actionable target before planning.

    This is the single attribution point used by the planner, open-obligation recovery,
    Claim Replay and the delivery projection.  A target that cannot be attributed is
    left empty (and therefore cannot cover any obligation); the planner will fail closed
    with ``RECALL_TARGET_OPERATION_UNATTRIBUTED``.
    """
    errors: list[dict[str, Any]] = []
    from .generation.effects import _class_group_equivalent
    for target in targets:
        if target.rule_id in {"G02", "G04", "G05", "G06"} and not target.out_of_scope:
            try:
                source_span = inspection.by_location(target.location)
            except (DocxError, KeyError, ValueError):
                source_span = None
            if source_span is not None and not target_site_ok(
                    target.rule_id, source_span, inspection):
                target.out_of_scope = True
                target.reason = f"{target.reason}|TARGET_SOURCE_MISMATCH"
                continue
        if target.operations and not target.out_of_scope:
            rule = rules_by_id.get(target.rule_id)
            if rule is not None:
                indices = _normalise_operation_ids(rule, target.operations, obligations)
                statuses = [condition_status(
                    (rule.get("operations") or [])[index].get("condition"), facts)
                    for index in indices if 0 <= index < len(rule.get("operations") or [])]
                if statuses and all(status == "FALSE" for status in statuses):
                    # The target's own branch does not apply (for example G20 on a
                    # fixed-management-fee product).  It must not be audited as a
                    # satisfied obligation whose original text should stay unchanged;
                    # a sibling rule (G22) may legitimately edit the same paragraph.
                    target.out_of_scope = True
                    target.reason = f"{target.reason}|TARGET_OPERATION_NOT_APPLICABLE"
                    continue
        if target.state == "satisfied" and not target.out_of_scope:
            # A satisfied inventory target for an applicable no-op branch is a
            # qualification result, not an auditable unchanged obligation.  A
            # sibling operation may legitimately edit the same source paragraph
            # (G21/G22 at D20 p977).
            rule = rules_by_id.get(target.rule_id)
            if rule is not None:
                operations = list(rule.get("operations") or ())
                statuses = [condition_status(operation.get("condition"), facts)
                            for operation in operations]
                applicable = [operation for operation, status in zip(operations, statuses)
                              if status == "TRUE"]
                if (statuses and all(status == "FALSE" for status in statuses)) or (
                        applicable and all(operation.get("op") == "noop"
                                           for operation in applicable)):
                    target.out_of_scope = True
                    target.reason = f"{target.reason}|TARGET_OPERATION_NOT_APPLICABLE"
                    continue
        if target.rule_id == "G16" and target.state == "satisfied":
            quote_body = _compact(target.quote)
            expected_policy = _compact(str(
                (rule.get("operations") or [{}])[0].get("new_text") or ""))
            if (quote_body and quote_body in expected_policy
                    and not all(token in quote_body for token in
                                ("每日计提", "直销机构", "其他销售机构"))):
                # The inventory may find only the final "持有超过一年返还" tail
                # and mark the whole G16 clause satisfied. It is a partial source
                # clause, not a complete policy: require the remaining components.
                target.state = "needs_edit"
                target.reason = f"{target.reason}|G16_PARTIAL_CLAUSE"
        if target.state != "needs_edit":
            # An inventory/survey target can already be marked satisfied while still
            # carrying only one half of a split A/C class-substitution clause.  The
            # sentence itself proves both groups, so expand its operation coverage
            # just as for a needs_edit target; otherwise the sibling obligation remains
            # falsely unproven even though the text is already correct.
            if target.state == "satisfied" and target.rule_id in {"G02", "G04"}:
                rule = rules_by_id.get(target.rule_id)
                if rule is not None and rule.get("class_substitution"):
                    try:
                        indices = _selected_operation_indices(
                            rule, target, inspection, facts, obligations)
                    except RecallError:
                        indices = []
                    if indices:
                        target.operations = tuple(_rule_operation_key(rule, index)
                                                  for index in indices)
            continue
        # A previous planning pass may have marked a valid, already-satisfied
        # G02/G04 target as TARGET_SOURCE_MISMATCH when the canonical guide letters
        # did not occur verbatim.  Reclassify only when the actual fee-group clause
        # already contains every selected class group; headings without fee wording
        # remain excluded.
        if target.out_of_scope and target.rule_id in {"G02", "G04"}:
            rule = rules_by_id.get(target.rule_id) or {}
            quote_body = _compact(target.quote)
            if rule.get("class_substitution") and any(
                    token in quote_body for token in ("申购费", "认购费", "销售服务费")):
                true_indices = [index for index, operation in enumerate(
                    rule.get("operations") or ())
                    if condition_status(operation.get("condition"), facts) == "TRUE"]
                matched = 0
                for index in true_indices:
                    expected, issues = instantiate_slots(
                        str((rule.get("operations") or ())[index].get("new_text") or ""),
                        facts)
                    if not issues and expected and _class_group_equivalent(
                            expected, quote_body):
                        matched += 1
                if true_indices and matched == len(true_indices):
                    target.out_of_scope = False
                    target.reason = (f"{target.reason}|"
                                     "RECLASSIFIED_CLASS_GROUP_PRESENT")
        if target.out_of_scope:
            continue
        rule = rules_by_id.get(target.rule_id)
        if rule is None:
            continue
        try:
            indices = _selected_operation_indices(rule, target, inspection, facts,
                                                  obligations)
        except RecallError as exc:
            if target.operations:
                target.claimed_operations = tuple(target.operations)
                target.operations = ()
            # The target has no provable operation/site attribution.  It must not be
            # planned or audited, but it also must not become a permanent blocking
            # "target" entry: the operation-level open/claim recovery is the layer that
            # must close or keep the obligation.  Mark the target as an invalid site.
            target.out_of_scope = True
            target.reason = (f"{target.reason}|TARGET_OPERATION_NOT_APPLICABLE"
                             if str((exc.detail or {}).get("reason") or "") ==
                             "explicit_operation_not_applicable"
                             else f"{target.reason}|TARGET_SOURCE_MISMATCH")
            errors.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "code": exc.code, "detail": dict(exc.detail or {})})
            continue
        if indices:
            target.operations = tuple(_rule_operation_key(rule, index)
                                     for index in indices)
    return errors


def resolve_absent_site_targets(targets: Sequence[Target], rules_by_id: dict[str, dict],
                                inspection: DocumentInspection,
                                facts: Facts | None = None) -> list[dict[str, Any]]:
    """Turn an out-of-scope G05 delete locator into an already-absent site proof.

    The inventory sometimes finds the class-setup paragraph but reports the
    independent ``并报中国证监会备案`` literal as TARGET_SOURCE_MISMATCH because
    that literal is not in this paragraph.  The paragraph is nevertheless the
    rule's real business site; keep it as a satisfied, site-bound negative proof
    instead of leaving a false OPEN obligation.
    """
    records: list[dict[str, Any]] = []
    for target in list(targets):
        if target.rule_id != "G05" or target.state not in {"needs_edit", "absent"}:
            continue
        rule = rules_by_id.get("G05") or {}
        try:
            span = inspection.by_location(target.location)
        except (KeyError, DocxError):
            continue
        if not target_site_ok("G05", span, inspection):
            continue
        body = _compact(span.text)
        for index, operation in enumerate(rule.get("operations") or []):
            if operation.get("op") != "delete":
                continue
            if facts is not None and condition_status(operation.get("condition"), facts) != "TRUE":
                continue
            old = _compact(str(operation.get("old_text") or ""))
            if len(old) < 8 or old in body:
                continue
            operation_id = _rule_operation_key(rule, index)
            # A target can already own a different G05 branch.  Keep that branch's
            # unresolved state intact and add a separate, operation-specific
            # already-absent proof for the filing deletion (D19 p130).
            # Only a target whose complete operation identity is this delete can be
            # converted in place.  A broad target carrying G05:0 plus G05:2 must be
            # split; otherwise marking the target satisfied would close the still
            # unproven replacement branch along with the absent delete proof.
            if operation_id in target.operations and set(target.operations) == {operation_id}:
                target.state = "satisfied"
                target.out_of_scope = False
                target.quote = span.text
                target.start, target.end = 0, len(span.text)
                target.resolution = "resolved"
                target.segment_ok = True
                target.reason = f"{target.reason}|ALREADY_ABSENT_AT_CLASS_SETUP"
                records.append({"target_id": target.target_id, "rule_id": "G05",
                                "operation_id": operation_id, "location": target.location})
                continue
            if target.operations:
                clone = Target(
                    target_id=f"{target.target_id}-ABSENT-{operation_id.replace(':', '-')}",
                    rule_id="G05", location=target.location, quote=span.text,
                    state="satisfied", reason=f"{target.reason}|ALREADY_ABSENT_AT_CLASS_SETUP",
                    start=0, end=len(span.text), resolution="resolved",
                    segment_ok=True, operations=(operation_id,))
                targets.append(clone)
                records.append({"target_id": clone.target_id, "rule_id": "G05",
                                "operation_id": operation_id, "location": target.location})
                continue
            target.operations = (operation_id,)
            target.state = "satisfied"
            target.out_of_scope = False
            target.quote = span.text
            target.start, target.end = 0, len(span.text)
            target.resolution = "resolved"
            target.segment_ok = True
            target.reason = f"{target.reason}|ALREADY_ABSENT_AT_CLASS_SETUP"
            records.append({"target_id": target.target_id, "rule_id": "G05",
                            "operation_id": operation_id, "location": target.location})
    return records


def rebind_split_class_definition_targets(targets: Sequence[Target],
                                        inspection: DocumentInspection) -> list[dict[str, Any]]:
    """Move a G02/G04 heading-fragment target onto its continuation paragraph.

    Word commonly splits ``…三种不同的`` | ``类别。在投资者申购…``.  The model
    locator then points at the heading, where no fee-group sentence exists.  When
    the next paragraph is the direct continuation and carries the class/fee
    wording, bind the target to that complete paragraph instead of asking the
    class-substitution planner to narrow an impossible heading.
    """
    spans = list(inspection.paragraphs)
    locations = [span.location for span in spans]
    records: list[dict[str, Any]] = []
    for target in targets:
        if target.rule_id not in {"G02", "G04"} or target.state != "needs_edit":
            continue
        if target.location not in locations:
            continue
        index = locations.index(target.location)
        if index >= len(spans) - 1:
            continue
        current, _ = display_text(spans[index].text)
        follower, _ = display_text(spans[index + 1].text)
        if current.rstrip().endswith(("。", "；", ";", "！", "？", "!", "?")):
            continue
        if not follower.lstrip().startswith(("类别", "份额类别", "基金份额类别")):
            continue
        if not any(token in follower for token in ("申购费", "认购费", "销售服务费")):
            continue
        if not any(token in follower for token in ("A类", "A 类", "C类", "C 类", "D类", "D 类")):
            continue
        target.location = spans[index + 1].location
        target.quote = spans[index + 1].text
        target.start, target.end = 0, len(spans[index + 1].text)
        target.resolution = "resolved"
        target.segment_ok = True
        target.reason = f"{target.reason}|SPLIT_CLASS_DEFINITION_CONTINUATION"
        records.append({"target_id": target.target_id, "rule_id": target.rule_id,
                        "from": current[:40], "to": target.location})
    return records


def ensure_unique_target_ids(targets: Sequence[Target], origins: dict[str, str] | None = None) -> dict[str, str]:
    """Make every discovery id unique before it becomes a plan/audit key.

    Inventory windows, survey counters, recovery rounds and duplicate-copy helpers
    each mint ids locally.  Two rounds can otherwise reuse ``Y012`` for unrelated
    targets.  Preserve the first id and deterministically suffix later collisions;
    return the rename map for report/evidence bookkeeping.
    """
    used: set[str] = set()
    renamed: dict[str, str] = {}
    for target in targets:
        base = str(target.target_id or "T")
        candidate = base
        ordinal = 2
        while candidate in used:
            candidate = f"{base}-U{ordinal}"
            ordinal += 1
        used.add(candidate)
        if candidate != target.target_id:
            old = target.target_id
            target.target_id = candidate
            renamed[old] = candidate
            if origins is not None and old in origins:
                origins[candidate] = origins.pop(old)
    return renamed


def dedupe_operation_targets(targets: Sequence[Target], rules_by_id: dict[str, dict],
                             inspection: DocumentInspection) -> tuple[list[Target], list[str]]:
    """Drop duplicate bindings to the same occurrence, retaining disjoint sites.

    The inventory sometimes reports the broad clause and the exact operation phrase as
    two targets (D01 G05 p135).  Planning both creates an artificial overlap and can
    drop the operation.  Prefer the target whose quote is the operation's own old_text,
    then the narrower span.  Different locations (body vs contract summary) are real
    duplicate copies and are both kept.
    """
    # A non-composite target can be a single paragraph of a composite target for the
    # same rule/operation (D16 G13 p222 inside Y007 p221/p222).  Keeping both creates
    # an artificial overlap and can starve the composite merge.
    composites = [target for target in targets
                  if target.state == "needs_edit" and not target.out_of_scope
                  and target.composite and target.operations]
    for target in targets:
        if target.state != "needs_edit" or target.out_of_scope or target.composite \
                or not target.operations:
            continue
        for composite in composites:
            if composite.rule_id != target.rule_id:
                continue
            if not set(composite.operations) & set(target.operations):
                continue
            if any(str(part).rsplit(":", 2)[0] == target.location
                   for part in composite.composite):
                target.out_of_scope = True
                target.reason = f"{target.reason}|SUBSET_OF_COMPOSITE_TARGET:{composite.target_id}"
                break
    groups: dict[tuple[str, str, tuple[str, ...]], list[Target]] = {}
    for target in targets:
        if target.state not in {"needs_edit", "satisfied"} or target.out_of_scope:
            continue
        if not target.operations:
            continue
        key = (target.rule_id, target.location, tuple(sorted(target.operations)))
        groups.setdefault(key, []).append(target)
    removed: set[str] = set()
    for key, items in groups.items():
        if len(items) < 2:
            continue
        rule = rules_by_id.get(key[0]) or {}

        def score(target: Target) -> tuple[int, int]:
            quote = _compact(target.quote)
            exact = 0
            for operation in rule.get("operations") or []:
                old = _compact(str(operation.get("old_text") or ""))
                if not old:
                    continue
                if quote and quote == old:
                    exact = max(exact, 3)
                elif target.start is not None and target.end is not None:
                    try:
                        span = inspection.by_location(target.location)
                    except DocxError:
                        continue
                    if old in _compact(span.text[int(target.start):int(target.end)]):
                        exact = max(exact, 2)
                elif old in quote:
                    exact = max(exact, 1)
            width = ((int(target.end) - int(target.start))
                     if target.start is not None and target.end is not None else 10**9)
            # When the same physical site is reported once as actionable and once
            # as already satisfied, keep the actionable target. A false positive
            # still has to pass source/plan/audit checks; letting the satisfied
            # duplicate win would silently suppress a required edit.
            return (exact, 1 if target.state == "needs_edit" else 0, -width)
        kept: list[Target] = []
        for item in sorted(items, key=score, reverse=True):
            def same_occurrence(other: Target) -> bool:
                if (item.state != other.state
                        and {item.state, other.state} == {"needs_edit", "satisfied"}
                        and item.composite and item.composite == other.composite
                        and set(item.operations) == set(other.operations)):
                    # The survey can re-discover the same composite delete site as
                    # an already-satisfied target while the open-rule target still
                    # needs the edit (D04 G17 p1326). One physical composite site
                    # cannot be both; keep the actionable target so the duplicate
                    # does not create a false occurrence ambiguity.
                    return True
                if item.state != other.state:
                    return False
                if (item.occurrence_index >= 0 and other.occurrence_index >= 0
                        and item.occurrence_index != other.occurrence_index):
                    return False
                if item.state == "satisfied":
                    # Repeated discoveries of an already-correct clause are aliases
                    # only when their source geometry and quote agree exactly.
                    return (item.start is not None and item.end is not None
                            and (item.start, item.end, item.quote, item.composite) ==
                            (other.start, other.end, other.quote, other.composite))
                # Two targets for the same append operation at the same location both
                # insert the same policy; there is no old_text/occurrence to compare
                # (live G03 T004+Y011 duplicated the paragraph text).
                kinds: set[str] = set()
                for key in set(item.operations) | set(other.operations):
                    try:
                        index = int(str(key).split(":", 1)[1])
                    except (IndexError, ValueError):
                        continue
                    operations = rule.get("operations") or []
                    if 0 <= index < len(operations):
                        kinds.add(str(operations[index].get("op") or ""))
                if kinds == {"append"}:
                    return True
                if item.composite or other.composite:
                    return item.composite == other.composite and item.quote == other.quote
                if any(value is None for value in (item.start, item.end, other.start, other.end)):
                    return False
                a, b = max(item.start, other.start), min(item.end, other.end)
                if a >= b:
                    return False
                if (item.start, item.end) == (other.start, other.end):
                    return True
                if item.occurrence_index is not None and other.occurrence_index is not None \
                        and item.occurrence_index != other.occurrence_index:
                    return False
                union = inspection.by_location(item.location).text[
                    min(item.start, other.start):max(item.end, other.end)]
                olds = [str(operation.get("old_text") or "")
                        for operation in rule.get("operations") or []]
                counts = [_compact(union).count(_compact(old)) for old in olds if old]
                return bool(counts) and max(counts) == 1
            best = next((other for other in kept if same_occurrence(other)), None)
            if best is not None:
                item.out_of_scope = True
                item.reason = f"{item.reason}|DUPLICATE_OPERATION_TARGET:{best.target_id}"
                removed.add(item.target_id)
            else:
                kept.append(item)
    return list(targets), sorted(removed)


def duplicate_copy_targets(targets: Sequence[Target], rules_by_id: dict[str, dict],
                           inspection: DocumentInspection,
                           scopes: Mapping[str, Any] | None = None) -> list[Target]:
    """Clone an operation target onto byte-identical body/summary clause copies.

    The contract repeats the same clause in the body and in the contract summary.  Editing
    only one copy makes the two dispositions diverge (D01 p758/p1221, D16 p822/p1306).
    Only identical compact paragraph text is cloned; a paragraph merely sharing a phrase
    is not the same obligation site.

    When ``scopes`` is supplied, a copy is cloned only inside the target rule's resolved
    physical scope.  A duplicate paragraph outside that scope belongs to another site
    (e.g. the 基本情况 copy of a 释义 definition) and must not be edited by this rule.
    """
    # Only an *active* target blocks a duplicate copy.  A stale target that was
    # already judged out of scope (for example G16 on the body copy before missing-
    # operation recovery located the summary copy) must not suppress the repair copy;
    # otherwise the recovered operation is applied to one copy only and the identical
    # body/summary clauses diverge at final replay.
    existing = {(target.rule_id, location, tuple(sorted(target.operations)))
                for target in targets
                if target.state == "needs_edit" and not target.out_of_scope
                and not target.attribution_error
                for location in _target_paragraphs(target)}
    paragraph_text = {span.location: _compact(display_text(span.text)[0])
                      for span in inspection.paragraphs}
    by_text: dict[str, list[str]] = {}
    for location, text in paragraph_text.items():
        if len(text) >= 20:
            by_text.setdefault(text, []).append(location)
    clones: list[Target] = []

    def occurrence_needle(target: Target, rule: dict) -> str:
        """Return the operation text whose occurrence index is authoritative."""
        if target.occurrence_index < 0:
            return ""
        for key in target.operations:
            try:
                index = int(str(key).split(":", 1)[1])
            except (IndexError, ValueError):
                continue
            operations = rule.get("operations") or []
            if 0 <= index < len(operations):
                value = str(operations[index].get("old_text") or "")
                if value:
                    return value
        return ""

    for target in list(targets):
        if target.state != "needs_edit" or target.out_of_scope or target.composite:
            continue
        if not target.operations:
            continue
        rule = rules_by_id.get(target.rule_id) or {}
        source_text = paragraph_text.get(target.location, "")
        if len(source_text) < 20:
            continue
        for location in by_text.get(source_text, ()):
            if location == target.location:
                continue
            if scopes is not None:
                scope = scopes.get(str(target.rule_id))
                if scope is None or not scope.contains(location):
                    continue
            key = (target.rule_id, location, tuple(sorted(target.operations)))
            if key in existing:
                continue
            try:
                span = inspection.by_location(location)
            except DocxError:
                continue
            source_span = inspection.by_location(target.location)
            if target.rule_id == "G16":
                # G16's source identity is the end of its payment clause.  A payment
                # paragraph that happens to be byte-identical to another clause head
                # is not an exact duplicate when one clause continues through usage
                # paragraphs (D20 p804-p806 vs p1259).
                try:
                    clauses = _g16_clause_locations(inspection)
                except (AttributeError, KeyError, TypeError, ValueError):
                    # Small unit-test inspections and legacy callers may expose only
                    # paragraph text.  Preserve the previous exact-copy behaviour when
                    # the structural index cannot be built; real DOCX inspections have
                    # the fields required for the clause-specific guard.
                    clauses = []
                source_clause = next((clause for clause in clauses
                                      if target.location in clause), ())
                candidate_clause = next((clause for clause in clauses
                                        if location in clause), ())
                if (clauses and (not source_clause or not candidate_clause
                                 or source_clause[-1] != target.location
                                 or candidate_clause[-1] != location)):
                    continue
            if target.start is None or target.end is None:
                source_located = resolve_quote(source_span, target.quote)
                if source_located is None:
                    continue
                source_start, source_end = source_located
            else:
                source_start, source_end = target.start, target.end
            start, end = source_start, source_end
            if _compact(target.quote):
                # G02/G04 plan occurrence_index against the operation old_text, while
                # the inventory quote may contain the whole surrounding sentence.  On
                # an identical copy, transfer the indexed operation span directly so a
                # second occurrence cannot silently become the first one.
                needle = occurrence_needle(target, rule)
                located = None
                if needle:
                    positions = _compact_positions(span.text, needle)
                    if target.occurrence_index < len(positions):
                        located = positions[target.occurrence_index]
                if located is None:
                    located = (resolve_occurrence(
                        span, target.quote, anchor=target.occurrence_anchor)
                               if target.occurrence_index >= 0
                               else resolve_quote(span, target.quote))
                if located is None:
                    continue
                start, end = located
            elif span.text[start:end] != inspection.by_location(
                    target.location).text[start:end]:
                continue
            clone = Target(
                target_id=f"{target.target_id}-D{len(clones) + 1}",
                rule_id=target.rule_id, location=location, quote=target.quote,
                state="needs_edit", reason=f"duplicate_copy:{target.reason}",
                start=start, end=end, resolution="resolved",
                segment_ok=containing_segment(span, start, end) is not None,
                operations=target.operations,
                occurrence_index=target.occurrence_index,
                occurrence_anchor=target.occurrence_anchor)
            clones.append(clone)
            existing.add(key)
    return clones


def known_operations_from_targets(targets: Sequence[Target], rules_by_id: dict[str, dict],
                                  inspection: DocumentInspection
                                  ) -> dict[tuple[str, str], set[str] | None]:
    known: dict[tuple[str, str], set[str] | None] = {}
    for target in targets:
        # A target that failed site/operation attribution, or was ruled out of scope,
        # must not claim coverage.  Otherwise one bad model target at a real clause
        # location suppresses the deterministic survey hit for that same clause and
        # the operation is left unplanned (live G15 p806 regression).
        if getattr(target, "out_of_scope", False) or getattr(target, "attribution_error", ""):
            continue
        # An ``absent`` judgment asserts that the operation's source material is not
        # at this site, so it cannot also claim that the operation is covered there.
        # Letting it claim coverage suppressed the deterministic delete target the
        # residual pass had just found (恒裕 G17 p888: the model quoted the whole
        # two-sentence reference, reported "absent", and swallowed the first
        # sentence's delete target; FL-D118 is the same failure for appends).
        if str(getattr(target, "state", "")) == "absent":
            continue
        keys = target_operation_keys(target, rules_by_id.get(target.rule_id), inspection)
        for location in _target_paragraphs(target):
            pair = (target.rule_id, location)
            if keys:
                current = known.get(pair, set())
                if current is None:
                    continue
                current.update(keys)
                known[pair] = current
            else:
                known[pair] = None
    return known


def normalise_known_operations(known: Any) -> dict[tuple[str, str], Any]:
    if isinstance(known, dict):
        return {key: (None if value is None else set(value)) for key, value in known.items()}
    return {(rule_id, location): _LOCATION_WILDCARD for rule_id, location in known}


_MISSING = object()
# Legacy callers pass ``known`` as (rule_id, location) pairs: the location is covered
# but the operation is unknown, and a hit there is suppressed (old behaviour). Target
# derived coverage uses ``None`` for "operation unknown" and lets specific operation
# hits through (FL-D118).
_LOCATION_WILDCARD = object()


def _add_operation_coverage(known: dict[tuple[str, str], set[str] | None], rule_id: str,
                            location: str, keys: Sequence[str]) -> None:
    """Record covered operations at a location without crashing on a wildcard state."""
    current = known.get((rule_id, location))
    if current is _LOCATION_WILDCARD:
        return
    if current is None:
        known[(rule_id, location)] = set(keys)
    else:
        current.update(keys)


def operations_cover_hit(known: dict[tuple[str, str], set[str] | None], rule_id: str,
                         locations: Sequence[str], operation_keys: Sequence[str]) -> bool:
    """True when every location already covers this hit's operation.

    A ``None`` state means "location covered, operation unknown" (legacy/inventory
    target); a specific operation hit at a location covered by other operations is not
    suppressed. A wildcard hit (no operation identity) keeps the old location-level
    behaviour.
    """
    for location in locations:
        state = known.get((rule_id, location), _MISSING)
        if state is _MISSING:
            return False
        if state is _LOCATION_WILDCARD:
            continue
        if state is None:
            # Unknown operation identity must fail open for a specific operation hit:
            # an inventory target whose span contains none of the operation references
            # may be an append/satisfied target, and must not hide a real delete hit at
            # the same location. A wildcard hit keeps the old location-level behaviour.
            if operation_keys:
                return False
            continue
        if not state:
            return False
        if operation_keys and not (set(operation_keys) & state):
            return False
    return True


def _class_definition_polarity_ok(clause: str, fact: Any) -> bool:
    """Whether one definition clause already states this class's fee treatment."""
    if not clause:
        return False
    subscription = bool(getattr(fact, "subscription_fee", False))
    service = bool(getattr(fact, "service_fee", False))
    subscription_mentioned = any(token in clause for token in ("申购费", "认购费"))
    subscription_negated = bool(re.search(
        r"(?:不收取|不收|免收|无需)[^。；;]{0,8}(?:申购费|认购费)", clause))
    if subscription:
        if not subscription_mentioned or subscription_negated:
            return False
        if not any(token in clause for token in ("收取", "交纳", "支付")):
            return False
    elif subscription_mentioned and not subscription_negated:
        return False
    service_mentioned = "销售服务费" in clause
    service_negated = bool(re.search(
        r"(?:不计提|不收取|不收|无需)[^。；;]{0,10}销售服务费", clause))
    if service:
        if not service_mentioned or service_negated or "计提" not in clause:
            return False
    elif service_mentioned and not service_negated:
        return False
    return True


def class_definition_satisfied_hits(rule: dict, facts: Facts,
                                    compact_text: Mapping[str, str],
                                    scoped_locations: Iterable[str],
                                    existing: Mapping[tuple[str, str], Any]
                                    ) -> list[tuple[str, str, tuple[str, ...]]]:
    """Already-correct class-definition sites for G02/G04 (location, quote, keys).

    The definition style ``…的，称为A类基金份额`` writes the fee treatment *before*
    the label, so the generic ``satisfied_by_new_text`` check (which needs the
    concatenated replacement text) never fires and the obligation stayed open even
    though the contract already lists every actual class with the right polarity
    (景宁 p151).  Only paragraphs that really define classes are considered, and
    every actual class must match its own fee treatment.
    """
    rule_id = str(rule.get("rule_id") or "")
    if rule_id not in {"G02", "G04"} or not rule.get("class_substitution"):
        return []
    classes = [fact for fact in getattr(facts, "classes", ())
               if bool(getattr(fact, "current", True))]
    if len(classes) < 2:
        return []
    operations = list(rule.get("operations") or ())
    results: list[tuple[str, str, tuple[str, ...]]] = []
    for location in scoped_locations:
        if (rule_id, location) in existing:
            continue
        body = compact_text.get(location, "")
        if not body or ("称为" not in body and "将基金份额分为" not in body):
            continue
        clauses = [clause for clause in re.split(r"[；;。]", body) if clause]
        keys: list[str] = []
        for fact in classes:
            name = str(getattr(fact, "name", "") or "").strip()
            if not name:
                keys = []
                break
            label = f"{name}基金份额"
            matched = [clause for clause in clauses if label in clause or f"称为{name}" in clause]
            if not matched or not any(_class_definition_polarity_ok(clause, fact)
                                      for clause in matched):
                keys = []
                break
            operation_keys = [ _rule_operation_key(rule, index)
                               for index, operation in enumerate(operations)
                               if str(operation.get("op") or "") == "replace"
                               and name in str(operation.get("old_text") or "")]
            keys.extend(operation_keys)
        if not keys:
            continue
        results.append((location, body, tuple(sorted(set(keys)))))
    return results


def survey_targets(inspection: DocumentInspection, rules: Sequence[dict], facts: Facts, *,
                   known: Any = (),
                   threshold: float = FUZZY_MATCH_THRESHOLD,
                   override_rules: frozenset[str] = frozenset(),
                   allowed_locations: Mapping[str, Iterable[str]] | None = None
                   ) -> list[SurveyHit]:
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
    existing = normalise_known_operations(known)
    for rule_id, location in list(existing):
        if rule_id in override_rules:
            del existing[(rule_id, location)]
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
        scoped_locations = (set(allowed_locations.get(rule_id, ()))
                            if allowed_locations is not None else set(compact_text))
        if not scoped_locations:
            continue
        for location, body in compact_text.items():
            if location not in scoped_locations:
                continue
            if (rule_id, location) in existing:
                continue
            matched = satisfied_by_new_text(rule, facts, body)
            if not matched:
                continue
            counter += 1
            satisfied_keys = satisfied_operation_keys(rule, facts, body)
            hits.append(SurveyHit(rule_id=rule_id, operation="satisfied",
                                  locations=(location,), quote=matched,
                                  start=0, end=0, ratio=1.0, index=counter,
                                  operation_keys=tuple(sorted(satisfied_keys))))
            if satisfied_keys:
                _add_operation_coverage(existing, rule_id, location, satisfied_keys)
            else:
                existing[(rule_id, location)] = None
        # Class definitions write the fee treatment before the label
        # ("…的，称为A类基金份额"), which the replacement-text check above cannot
        # recognise.  Emit a satisfied hit only when every actual class already
        # matches its own subscription/service-fee polarity.
        for location, _body, keys in class_definition_satisfied_hits(
                rule, facts, compact_text, scoped_locations, existing):
            span = by_location.get(location)
            if span is None:
                continue
            counter += 1
            hits.append(SurveyHit(rule_id=rule_id, operation="satisfied",
                                  locations=(location,), quote=span.text,
                                  start=0, end=0, ratio=1.0, index=counter,
                                  operation_keys=keys))
            _add_operation_coverage(existing, rule_id, location, keys)
        tail_keys = set(bare_tail_keys(rule, facts))
        anchors = rule_context_anchors(rule, facts)
        # Clause-boundary extension is safe only for a genuinely delete-only rule.
        # The keyword-bag fallback below may still use delete references from a mixed
        # rule (for example G05 replace + delete), but must not widen the exact replace
        # span into the surrounding sentence.
        delete_only_rule = is_delete_only_rule(rule, facts)
        for operation_key_value, key in operation_search_key_pairs(rule, facts):
            hit_keys = () if operation_key_value == "*" else (operation_key_value,)
            occurrences = find_old_text_all(paragraphs, key, threshold=SURVEY_FUZZY_THRESHOLD)
            for parts in occurrences:
                locations = tuple(item[0] for item in parts)
                if any(location not in scoped_locations for location in locations):
                    continue
                if operations_cover_hit(existing, rule_id, locations, hit_keys):
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
                         # follower already carries only its independently matched
                         # sentence in compact coordinates (FL-D225).
                        first_compact_body, first_map = compact_offsets(span.text)
                        # Map the extended raw span back into compact offsets for part 0.
                        compact_start = _raw_to_compact(first_map, raw_start)
                        compact_end = _raw_to_compact(first_map, raw_end)
                        parts = [(first[0], compact_start, compact_end),
                                 follower_part]
                        locations = (first[0], follower_part[0])
                counter += 1
                hits.append(SurveyHit(rule_id=rule_id, operation="survey", locations=locations,
                                      quote=quote or key, start=first[1], end=first[2],
                                      ratio=1.0, index=counter,
                                      operation_keys=hit_keys).with_parts(parts))
                if hit_keys:
                    for location in locations:
                        _add_operation_coverage(existing, rule_id, location, hit_keys)
                else:
                    for location in locations:
                        existing[(rule_id, location)] = None
        # A pure deletion may still be present under a paraphrase (FL-D062).  Run the
        # keyword signature even when another operation/reference already matched: one
        # exact operation site must not suppress a second operation or a wording variant
        # at a different site.  The per-location ``existing`` gate below keeps exact
        # hits from being duplicated, while operation coverage remains explicit.
        delete_keys = tuple(
            _rule_operation_key(rule, index)
            for index, operation in enumerate(rule.get("operations") or [])
            if operation.get("op") == "delete"
            and condition_matches(operation.get("condition"), facts))
        bag = _delete_keyword_bag(rule, facts)
        if bag:
            bag_operation_keys = tuple(
                _rule_operation_key(rule, index)
                for index, operation in enumerate(rule.get("operations") or [])
                if operation.get("op") == "delete"
                and condition_matches(operation.get("condition"), facts)
            )
            ordered = list(compact_text.items())
            for index, (location, body) in enumerate(ordered):
                if location not in scoped_locations:
                    continue
                state = existing.get((rule_id, location), _MISSING)
                # A keyword-bag hit is a fallback for the delete operations only.  A
                # model target for another operation at this location must not suppress
                # it; skip only when every applicable delete operation is already
                # covered, or when a legacy wildcard target explicitly owns the site.
                if state is _LOCATION_WILDCARD or (
                        state is not _MISSING and state is not None
                        and bag_operation_keys
                        and set(bag_operation_keys).issubset(state)):
                    continue
                in_self = _keyword_bag_in_clause(body, bag)
                follower_location = (ordered[index + 1][0]
                                     if index + 1 < len(ordered) else None)
                follower = (ordered[index + 1][1]
                            if index + 1 < len(ordered) else "")
                if follower_location not in scoped_locations:
                    follower_location, follower = None, ""
                # A split clause can only continue into the next paragraph while the
                # current one is still open.  Pairing after a full stop used to merge
                # G15's payment clause with G17's usage clause (FL-D157), deleting the
                # wrong paragraph and overlapping a sibling operation's target.
                body_closed = body.rstrip().endswith(("。", "；", ";", "！", "？", "!", "?"))
                follower_new_topic = follower.lstrip().startswith(
                    ("销售服务费主要用于", "销售服务费使用范围"))
                # A pair is only the owner when the signature is genuinely split: the
                # follower alone must not already satisfy it, otherwise the follower is
                # the single paragraph to bind and pairing would drag in the preceding
                # line (a fee-formula row) as well.  A head that already satisfies the
                # bag but ends mid-clause (for example "…按月支付，") is extended to its
                # continuation instead of becoming a half-clause target.
                in_pair = (
                    follower_location is not None
                    and not body_closed
                    and not follower_new_topic
                    and not _keyword_bag_in_clause(follower, bag)
                    and (rule_id, follower_location) not in existing
                    and (not in_self or body.rstrip().endswith(("，", ",", "、", "：", ":")))
                    and _keyword_bag_in_clause(body + follower, bag))
                tail_pair = (
                    in_self and follower_location is not None
                    and not follower_new_topic
                    and not _keyword_bag_in_clause(follower, bag)
                    and (rule_id, follower_location) not in existing
                    and _reference_tail_match(rule, follower))
                if tail_pair:
                    # The first sentence is self-contained, but the next paragraph
                    # repeats the rule's own tail sentence; both are one delete scope.
                    in_pair = True
                if not (in_self or in_pair):
                    continue
                # G06's generic ``份额类别`` + ``转换`` signature is too broad for
                # adjacent amendment/meeting paragraphs.  Require the bounded
                # semantic prohibition before pairing them; otherwise an unrelated
                # ``调整…转换`` sequence becomes a false deletion target.
                if rule_id == "G06":
                    candidate_body = body + follower if in_pair else body
                    if not _semantic_delete_sentences(rule_id, candidate_body):
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
                    # Composite offsets are measured in each paragraph's
                    # whitespace-free text (plan_composite_target maps them back
                    # through compact_offsets).  Raw lengths include spaces and
                    # made the plan fail with RECALL_TARGET_COMPOSITE_UNRESOLVED
                    # whenever the paragraph contained any spacing.
                    parts = [(location, 0, len(compact_text[location])),
                             (follower_location, 0, len(compact_text[follower_location]))]
                else:
                    locations = (location,)
                    parts = [(location, 0, len(compact_text[location]))]
                hits.append(SurveyHit(rule_id=rule_id, operation="survey",
                                      locations=locations, quote=span.text.strip(),
                                      start=0, end=0, ratio=1.0,
                                      index=counter,
                                      operation_keys=bag_operation_keys).with_parts(parts))
                for item in locations:
                    if bag_operation_keys:
                        _add_operation_coverage(existing, rule_id, item, bag_operation_keys)
                    else:
                        existing[(rule_id, item)] = None
        # A model target may bind only the first sentence of a two-sentence delete
        # clause and mark that location covered.  The tail sentence can live in the
        # next paragraph and then survives untouched (ESG G17 p814).  Add a
        # deterministic target for any uncovered paragraph that repeats the rule's
        # own tail sentence.
        if delete_keys:
            needed = set(delete_keys)
            for location, body in compact_text.items():
                if location not in scoped_locations:
                    continue
                state = existing.get((rule_id, location), _MISSING)
                if state is _LOCATION_WILDCARD:
                    continue
                if state is not _MISSING and state is not None and needed.issubset(state):
                    continue
                if state is None:
                    continue
                span = by_location.get(location)
                if span is None or _looks_like_heading(span.text):
                    continue
                if not _reference_tail_match(rule, span.text):
                    continue
                counter += 1
                hits.append(SurveyHit(
                    rule_id=rule_id, operation="survey", locations=(location,),
                    quote=span.text.strip(), start=0, end=0, ratio=1.0,
                    index=counter, operation_keys=delete_keys).with_parts(
                        [(location, 0, len(body))]))
                _add_operation_coverage(existing, rule_id, location, delete_keys)
    if allowed_locations is not None:
        hits = [hit for hit in hits if all(
            location in allowed_locations.get(hit.rule_id, ()) for location in hit.locations)]
    return hits


_G16_MECHANISM_TOKENS: tuple[tuple[str, ...], ...] = (
    ("直销",),
    ("返还",),
    ("超过一年", "一年（即365天）", "365"),
)


def _append_obligation_present(rule_id: str, required: str, document_compact: str) -> bool:
    """Is the append obligation already present in the contract?

    G16 is special: the OLD payment clause also opens with "销售服务费每日计提", so
    accepting the lead sentence alone would let "old clause deleted, new mechanism not
    added" pass (external review 2026-10-19, P0-C). Its new mechanism counts as present
    only when the direct-sales refund and the over-one-year refund wording are present
    as well — otherwise the deterministic append target is created.
    """
    lead = _compact(required.split("。")[0])
    if not lead or lead not in document_compact:
        return False
    if str(rule_id) == "G16" and _tier1_enabled():
        return all(any(_compact(token) in document_compact for token in group)
                   for group in _G16_MECHANISM_TOKENS)
    return True


# G01/G03 append the new policy after the share-class *definition*, not after every
# paragraph that happens to contain "基金份额类别".  Contract summaries repeat the
# amendment trigger "调整基金份额类别设置" in the contract-change list; matching that
# sentence put the new clause inside the change-events list (FL-D158).
_APPEND_DEFINITION_MARKERS = (
    "份额类别：", "份额类别:", "基金份额类别定义", "份额类别定义",
    "将基金份额分为", "称为",
)
_APPEND_DEFINITION_EXCLUDES = (
    "调整基金份额类别设置", "调整基金份额的分类", "份额类别设置",
    "增设新的份额类别", "减少基金份额类别", "基金推出新业务",
    "变更基金合同", "修改《基金合同》", "终止基金合同",
    "调整有关认购", "业务规则",
)


def _definition_next_entry_start(text: str) -> int | None:
    """Return a raw append boundary before a merged, numbered next definition."""
    for match in re.finditer(
            r"(?<=[\s。；;])(?:[0-9０-９一二三四五六七八九十百]{1,6}[、．.]|"
            r"[（(][0-9０-９一二三四五六七八九十百]{1,6}[）)])\s*"
            r"[^\s：:。；;，,、]{2,24}\s*[：:]", text):
        prefix = text[:match.start()].rstrip()
        compact = _compact(prefix)
        if (any(marker in compact for marker in _APPEND_DEFINITION_MARKERS)
                and re.search(r"(?:基金)?份额[。；;]?$", compact)
                and "称为" in compact):
            return len(prefix)
    return None


def _split_definition_end(anchor: Any, inspection: DocumentInspection) -> Any | None:
    """Resolve a definition broken within a class name or unfinished clause.

    Only a lexical continuation of a definition anchor starts the chain. Later
    wrapped class restrictions remain part of it until the first closed paragraph.
    """
    spans = list(inspection.paragraphs)
    try:
        index = next(i for i, span in enumerate(spans) if span.location == anchor.location)
    except StopIteration:
        return None
    head = _compact(display_text(anchor.text)[0])
    if not any(marker in head for marker in _APPEND_DEFINITION_MARKERS):
        return None
    if not head or head[-1] in "。；;！？!?":
        return None
    if head.endswith(("计算公式为：", "计算公式为:")) and index + 1 < len(spans):
        # The definition already closes before its NAV formula lead. Preserve the
        # lead/formula adjacency and append after a fully source-bound equation.
        follower = spans[index + 1]
        formula = _compact(display_text(follower.text)[0])
        if re.fullmatch(
                r"计算日[某该]类基金份额净值[＝=]计算日[某该]类基金份额的?基金资产净值"
                r"[/／÷]计算日[某该]类基金份额余额总数[。]?", formula):
            return follower
        return None
    current = head
    for position in range(index + 1, min(len(spans), index + 7)):
        follower = spans[position]
        body = _compact(display_text(follower.text)[0])
        if not body or _looks_like_heading(follower.text):
            return None
        if position == index + 1:
            fragment = re.split(r"[。；;！？!?]", current)[-1]
            joined = fragment + body
            fee_definition = (bool(fragment) and any(
                opening.startswith(fragment) and len(fragment) < len(opening)
                for opening in ("在投资者申购基金份额时", "在投资者认购基金份额时"))
                and joined.startswith(("在投资者申购基金份额时", "在投资者认购基金份额时"))
                and "称为" in joined and bool(re.search(r"[A-ZＡ-Ｚ]类基金份额", joined)))
            lexical = ((bool(re.search(r"[A-ZＡ-Ｚ]$", current)) and body.startswith("类"))
                       or (current[-1] in "的和与及、，,（(：:" and
                            body.startswith(("类别", "份额类别", "基金份额类别", "在投资者")))
                       or fee_definition)
            if not lexical or not any(token in body for token in
                                      ("基金份额", "申购费", "认购费", "销售服务费")):
                return None
        elif not re.match(r"[A-ZＡ-Ｚ]类(?:基金)?份额", body):
            return None
        if body[-1] in "。；;！？!?":
            return follower
        if body[-1] not in "的和与及、，,（(：:" and not re.search(r"[A-ZＡ-Ｚ]$", body):
            return follower  # complete continuation with an omitted final stop
        current = body
    return None


def rebind_split_append_targets(targets: Sequence[Target],
                                inspection: DocumentInspection) -> None:
    for target in targets:
        if (target.rule_id not in {"G01", "G03"} or target.state != "needs_edit"
                or target.out_of_scope):
            continue
        try:
            anchor = inspection.by_location(target.location)
        except (KeyError, ValueError):
            continue
        end = _split_definition_end(anchor, inspection)
        if end is not None:
            target.location, target.quote = end.location, end.text
            target.start, target.end = 0, len(end.text)
            target.composite = ()
            target.resolution, target.segment_ok = "resolved", True
            target.reason = f"{target.reason}|SPLIT_DEFINITION_APPEND_END"


def _append_definition_anchor(rule_id: str, span: Any,
                              inspection: DocumentInspection) -> bool:
    """Whether an append anchor is a real share-class definition clause.

    A definition can be split by Word into ``…三种不同的`` | ``类别。…``; the
    continuation is accepted only when the previous paragraph carries the marker and
    is still an open sentence, the same rule ``append_site_ok`` uses.
    """
    if rule_id not in {"G01", "G03"}:
        return True
    paragraph, _ = display_text(span.text)
    compact = _compact(paragraph)
    if any(token in compact for token in _APPEND_DEFINITION_EXCLUDES):
        return False
    if any(token in compact for token in _APPEND_DEFINITION_MARKERS):
        return True
    # The final paragraph of a source-proven split definition inherits its own
    # definition anchor, even when the class letter was in an earlier paragraph.
    spans = list(inspection.paragraphs)
    position = next((i for i, item in enumerate(spans) if item.location == span.location), -1)
    for anchor in spans[max(0, position - 6):max(0, position)]:
        end = _split_definition_end(anchor, inspection)
        if end is not None and end.location == span.location:
            return True
    locations = [item.location for item in inspection.paragraphs]
    try:
        index = locations.index(span.location)
    except ValueError:
        return False
    if index <= 0:
        return False
    previous = inspection.paragraphs[index - 1]
    previous_text, _ = display_text(previous.text)
    if previous_text.rstrip().endswith(("。", "；", ";", "！", "？", "!", "?")):
        return False
    if not any(token in _compact(previous_text) for token in _APPEND_DEFINITION_MARKERS):
        return False
    return paragraph.lstrip().startswith(("类别", "份额类别", "基金份额类别"))


def _g16_payment_anchor(text: str) -> bool:
    """The sales-service-fee accrual + payment sentence (G16 append head)."""
    compact = _compact(display_text(text)[0])
    accrual = any(token in compact for token in (
        "每日计提", "日计提", "每日计算", "逐日累计", "计提"))
    monthly = ("按月支付" in compact or
               ("按月" in compact and "支付" in compact) or
               "逐月支付" in compact)
    return "销售服务费" in compact and accrual and monthly


def _g16_clause_end(anchor: Any, section: Section,
                    inspection: DocumentInspection) -> Any:
    """Last paragraph of the sales-service-fee clause that starts at ``anchor``.

    G16 must be appended after the whole fee clause (payment + usage scope), not
    between ``…按月支付，`` and its continuation (FL-D159).  Walk only through the
    clause's own continuation and sales-service-fee usage sentences, bounded to six
    paragraphs and the anchor's section.
    """
    by_location = {item.location: item for item in inspection.paragraphs}
    locations = list(section.locations)
    try:
        index = locations.index(anchor.location)
    except ValueError:
        return anchor
    end = anchor
    for location in locations[index + 1:index + 7]:
        span = by_location.get(location)
        if span is None:
            break
        text, _ = display_text(span.text)
        compact = _compact(text)
        if not compact or _looks_like_heading(text):
            break
        # A second accrual/payment mechanism is a distinct business occurrence,
        # even when the previous paragraph was truncated without punctuation.
        if _g16_payment_anchor(text):
            break
        current, _ = display_text(end.text)
        current_closed = current.rstrip().endswith(("。", "；", ";", "！", "？", "!", "?"))
        if not current_closed:
            end = span
            continue
        # Some contracts put the payment-delay sentence before the usage text
        # (FL-D192). Accept only that bounded payment continuation, not arbitrary
        # prose preceding a later sales-service-fee mention.
        usage = re.sub(
            r"^(?:若|如)遇(?:法定)?(?:节假日|休息日|公休日)[^。；;]{0,100}"
            r"(?:支付日期|支付时间)(?:相应)?顺延[。；;]", "", compact, count=1)
        if (usage != compact and not usage) or (
                usage.startswith("销售服务费") and any(
                    token in usage for token in ("主要用于", "使用范围"))):
            end = span
            continue
        break
    return end


def _g16_clause_locations(inspection: DocumentInspection) -> list[tuple[str, ...]]:
    """Source-proven fee clauses, preserving body/summary and payment mechanisms."""
    clauses = []
    for section in structure_index(inspection):
        locations = list(section.locations)
        for index, location in enumerate(locations):
            head = inspection.by_location(location)
            if not _g16_payment_anchor(head.text):
                continue
            tail = _g16_clause_end(head, section, inspection)
            clauses.append(tuple(locations[index:locations.index(tail.location) + 1]))
    return clauses


def _g16_append_end(inspection: DocumentInspection, clause: Sequence[str]) -> int:
    """End the append at its own usage sentence, before independent tail prose."""
    tail = inspection.by_location(clause[-1])
    joined = ""
    coordinates = []
    for location in clause:
        span = inspection.by_location(location)
        compact, offsets = compact_offsets(span.text)
        joined += compact
        coordinates.extend((location, offset + 1) for offset in offsets)
    ends = [coordinates[match.end() - 1][1] for match in re.finditer(
        r"销售服务费(?:主要用于|的?使用范围)[^。；;！？!?]*[。；;！？!?]", joined)
        if coordinates[match.end() - 1][0] == tail.location]
    return max(ends) if ends else len(tail.text)


def rebind_g16_clause_targets(targets: Sequence[Target],
                              inspection: DocumentInspection) -> list[dict[str, Any]]:
    """Bind payment-head and clause-tail discoveries to one physical append site.

    Inventory may choose the payment paragraph while survey chooses its usage-scope
    tail. Both belong to the same clause; normalize them before exact target dedupe.
    Separate payment mechanisms and body/summary copies retain separate addresses.
    """
    spans = list(inspection.paragraphs)
    indices = {span.location: index for index, span in enumerate(spans)}
    sections = structure_index(inspection)
    changes = []
    for target in targets:
        if target.rule_id != "G16" or target.state != "needs_edit" or target.out_of_scope:
            continue
        index = indices.get(target.location)
        if index is None:
            continue
        for head_index in range(index, max(-1, index - 7), -1):
            head = spans[head_index]
            if not _g16_payment_anchor(head.text):
                continue
            section = next((item for item in sections if head.location in item.locations), None)
            if section is None:
                continue
            end = _g16_clause_end(head, section, inspection)
            if not head_index <= index <= indices[end.location]:
                continue
            clause = list(section.locations)[list(section.locations).index(head.location):
                                             list(section.locations).index(end.location) + 1]
            append_end = _g16_append_end(inspection, clause)
            if target.location != end.location or target.end != append_end:
                changes.append({"target_id": target.target_id, "from": target.location,
                                "to": end.location})
                target.location = end.location
                target.quote = end.text[:append_end]
                target.start, target.end = 0, append_end
                target.composite = ()
                target.resolution = "resolved"
                target.segment_ok = True
                target.reason = f"{target.reason}|G16_CLAUSE_END"
            break
    return changes


def guard_g17_deletes_against_g16(planned: dict[str, Any],
                                  targets: Sequence[Target],
                                  inspection: DocumentInspection) -> list[dict[str, Any]]:
    """Keep G17 from deleting a clause whose required G16 append is unplanned.

    G16 and G17 share one physical fee clause.  If fact gating or planning leaves
    G16 unresolved, applying G17 alone destroys the source span where the new
    mechanism must be written.  A planned G16 edit authorizes the merge; without
    one, retain the old text and leave both business obligations open.
    """
    edits = list(planned.get("edits") or [])
    if not edits:
        return []
    clauses = _g16_clause_locations(inspection)
    by_location = {location: clause for clause in clauses for location in clause}
    pending_g16: dict[tuple[str, ...], list[Target]] = {}
    for target in targets:
        if (target.rule_id == "G16" and target.state == "needs_edit"
                and target.location in by_location):
            clause = by_location[target.location]
            pending_g16.setdefault(clause, []).append(target)
    if not pending_g16:
        return []
    planned_g16 = {str(edit.get("location") or "") for edit in edits
                   if str(edit.get("rule_id") or "").split("+")[-1] == "G16"
                   or "G16" in str(edit.get("rule_id") or "").split("+")}
    blocked: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for edit in edits:
        rule_id = str(edit.get("rule_id") or "")
        location = str(edit.get("location") or "")
        clause = by_location.get(location)
        if ("G17" in rule_id.split("+") and clause in pending_g16
                and not any(item in planned_g16 for item in clause)):
            blocked.append({"target_id": edit.get("target_id"), "location": location,
                            "reason": "G17_BLOCKED_G16_UNPLANNED"})
            continue
        kept.append(edit)
    if not blocked:
        return []
    planned["edits"] = kept
    blocked_ids = {str(item.get("target_id") or "") for item in blocked}
    for entry in planned.get("ledger") or []:
        if str(entry.get("target_id") or "") in blocked_ids and entry.get("status") == "planned":
            entry["status"] = "unresolved"
            entry["reason"] = "G17_BLOCKED_G16_UNPLANNED"
    return blocked


def _append_member(rule_id: str, span: Any,
                   inspection: DocumentInspection) -> bool:
    """Rule-specific membership for an append anchor.

    G16 membership stays on the payment sentence; its clause end is resolved after
    membership so a single clause does not become several append targets.  G01/G03
    additionally require a real class-definition clause (FL-D158).
    """
    if rule_id == "G16":
        return _g16_payment_anchor(span.text)
    if not append_site_ok(rule_id, span, inspection):
        return False
    return _append_definition_anchor(rule_id, span, inspection)


def _reference_tail_match(rule: dict, follower: str) -> bool:
    """Whether the next paragraph repeats a tail sentence of a delete reference.

    Contracts split ``销售服务费主要用于…。销售服务费使用范围不包括…`` into two
    paragraphs and may add a ``的``.  A keyword hit on the first sentence must extend
    to that tail, otherwise the second sentence survives (ESG G17 p814).
    """
    body = _compact(follower)
    if len(body) < 12:
        return False
    for operation in rule.get("operations") or []:
        if operation.get("op") != "delete":
            continue
        raw = str(operation.get("old_text") or "")
        texts = [raw, _strip_class_lead(raw)]
        for text in texts:
            for sentence in re.split(r"(?<=[。；;！？!?])", text or ""):
                stripped = _strip_class_lead(sentence)
                candidate = _compact(stripped or sentence)
                if len(candidate) < 12 or candidate[:4] != body[:4]:
                    continue
                if candidate in body or _sequence_ratio(candidate, body) >= 0.75:
                    return True
    return False


def append_applicability_targets(inspection: DocumentInspection, rules: Sequence[dict],
                                 facts: Facts, sections: Sequence[Section], *,
                                 known: Sequence[tuple[str, str]] = (),
                                 hinted: dict[str, str] | None = None,
                                 allowed_locations: Mapping[str, Iterable[str]] | None = None
                                 ) -> list[SurveyHit]:
    """Find missing append effects at rule-specific anchors in every routed section.

    Existing targets and policy text cover only their own business site. A policy in
    the definition cannot satisfy the basic-information clause or its summary copy.
    An ambiguous or missing anchor stays open for the bounded operation locator.
    """
    existing = set(known)
    paragraphs = [span for span in inspection.paragraphs if span.text.strip()]
    hits: list[SurveyHit] = []
    for rule in rules:
        rule_id = str(rule.get("rule_id") or "")
        append_ops = [(index, operation) for index, operation in enumerate(rule.get("operations") or [])
                      if operation.get("op") == "append"
                      and condition_matches(operation.get("condition"), facts)]
        if not rule_id or not append_ops:
            continue
        scoped = (set(allowed_locations.get(rule_id, ()))
                  if allowed_locations is not None else None)
        if allowed_locations is not None and not scoped:
            continue
        hint = _compact(str(rule.get("section_hint") or ""))
        routed = [section for section in sections if hint and hint in _compact(section.title)]
        # Contract summaries are often indexed under a generic heading instead of
        # the body section's ``section_hint``.  Append obligations apply to each
        # independently repeated business clause, so include summary sections as
        # candidates and let ``append_site_ok`` prove the local anchor.
        for section in sections:
            if section.zone == "summary" and section not in routed:
                routed.append(section)
        for section in routed:
            if scoped is not None and not (scoped & set(section.locations)):
                continue
            members = [span for span in paragraphs if span.location in set(section.locations)
                       and (scoped is None or span.location in scoped)
                       and not _looks_like_heading(span.text)
                       and _append_member(rule_id, span, inspection)]
            if rule_id in {"G01", "G03"}:
                # Word may split inside a word ("在投资|者申购").  Resolve
                # the definition end before counting candidates so both fragments
                # represent one append site rather than an ambiguous pair.
                ends = {}
                for member in members:
                    end = _split_definition_end(member, inspection) or member
                    if end.location in section.locations:
                        ends[end.location] = end
                members = list(ends.values())
            prefer = (hinted or {}).get(rule_id)
            preferred = next((span for span in members if span.location == prefer), None)
            # G16 has one payment mechanism per body/summary copy, so every member
            # is a real append site.  G01/G03 must keep their single class-definition
            # anchor; when Word splits that sentence, bind the continuation paragraph
            # (D01 p91|p92) instead of refusing or appending twice.
            if preferred is not None:
                anchors = [preferred]
            elif rule_id == "G16":
                anchors = members
            elif len(members) == 1:
                anchors = members
            else:
                locations = [item.location for item in inspection.paragraphs]
                continuations = []
                for member in members:
                    try:
                        index = locations.index(member.location)
                    except ValueError:
                        continue
                    if index <= 0:
                        continue
                    previous = inspection.paragraphs[index - 1]
                    previous_text, _ = display_text(previous.text)
                    current_text, _ = display_text(member.text)
                    if (not previous_text.rstrip().endswith(("。", "；", ";", "！", "？", "!", "?"))
                            and any(anchor in previous_text for anchor in
                                    _TARGET_ANCHORS[rule_id][0])
                            and current_text.lstrip().startswith(
                                ("类别", "份额类别", "基金份额类别"))):
                        continuations.append(member)
                anchors = continuations[:1]
            for anchor in anchors:
                if (rule_id, anchor.location) in existing:
                    continue
                if rule_id == "G16":
                    # Append after the complete fee clause, never between its
                    # payment head and the continuation paragraph (FL-D159).
                    anchor = _g16_clause_end(anchor, section, inspection)
                    if (rule_id, anchor.location) in existing:
                        continue
                for index, operation in append_ops:
                    template = str(operation.get("new_text") or "")
                    instantiated, issues = instantiate_slots(template, facts)
                    required = template if issues else instantiated
                    # G16's policy is often split into several adjacent paragraphs:
                    # daily accrual, direct-sales refund, and the over-one-year
                    # treatment may each have their own paragraph.  Checking only the
                    # payment anchor would then propose a duplicate append even when
                    # the complete mechanism is already present in this body/summary
                    # copy (产业优选 p852–p858 / p1324–p1330).  Use a bounded local
                    # section window for this multi-component rule; other append rules
                    # remain anchored to their own paragraph.
                    presence_text = _compact(anchor.text)
                    if rule_id == "G16":
                        try:
                            anchor_index = section.locations.index(anchor.location)
                        except ValueError:
                            anchor_index = -1
                        if anchor_index >= 0:
                            nearby = section.locations[max(0, anchor_index - 6):
                                                       anchor_index + 7]
                            presence_text = "".join(
                                _compact(inspection.by_location(location).text)
                                for location in nearby)
                    if not required or _append_obligation_present(
                            rule_id, required, presence_text):
                        continue
                    hits.append(SurveyHit(rule_id=rule_id, operation="append",
                        locations=(anchor.location,), quote=anchor.text.strip(),
                        start=0, end=0, ratio=1.0, index=len(hits) + 1,
                        operation_keys=(_rule_operation_key(rule, index),))
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

    The matched span may stop inside a sentence; the reference may continue in the next
    paragraph. Return only the independently matched compact slice from that follower, so
    an unrelated clause later in the same paragraph remains intact (FL-D225).
    """
    matched = _compact(matched_quote)
    if not matched or len(matched) < 8:
        return None
    def sentence_parts(value: str) -> list[str]:
        return [part for part in re.split(r"(?<=[。；;！？!?])", _compact(value)) if part]

    def equivalent_forms(value: str) -> tuple[str, ...]:
        compact = _compact(value)
        forms = [compact]
        stripped = _strip_class_lead(compact)
        if stripped:
            forms.append(stripped)
        if compact.startswith("基金销售服务费"):
            forms.append(compact[2:])
        # These are the same bounded G17 source variants accepted by the
        # independent source-scope proof.  They must not authorize a different
        # subject, polarity, period, or an additional sentence.
        for item in tuple(forms):
            forms.extend((item.replace("、以及", "，及"),
                          item.replace("基金份额持有人服务费", "持有人服务费"),
                          item.replace("销售服务费的使用范围", "销售服务费使用范围"),
                          item.replace("销售服务费使用范围", "销售服务费的使用范围")))
        return tuple(dict.fromkeys(forms))

    def authorized_prefix_end(value: str, expected: Sequence[str]) -> int | None:
        """Return the compact end of one authorized sentence at follower start."""
        for candidate in expected:
            candidate = _compact(candidate)
            if not candidate:
                continue
            body = candidate.rstrip("。；;！？!?")
            if not value.startswith(body):
                continue
            if len(value) == len(body):
                return len(body)
            if value[len(body)] in "。；;！？!?":
                return len(body) + 1
        return None

    matched_forms = equivalent_forms(matched_quote)
    for operation in rule.get("operations") or []:
        if operation.get("op") != "delete":
            continue
        if facts is not None and not condition_matches(operation.get("condition"), facts):
            continue
        reference = _compact(str(operation.get("old_text") or ""))
        reference_sentences = sentence_parts(reference)
        if len(reference_sentences) < 2:
            continue
        # Find the first guide sentence that the matched source slice starts or
        # ends.  The old implementation searched for only the last 16 chars and
        # then returned the whole follower paragraph; that swallowed independent
        # fee/permission text after the authorized G17 sentence.
        continuation = ""
        for index, source_sentence in enumerate(reference_sentences[:-1]):
            source_forms = equivalent_forms(source_sentence)
            for source_form in source_forms:
                for matched_form in matched_forms:
                    if source_form.startswith(matched_form) and len(source_form) > len(matched_form):
                        # The anchor stopped inside this sentence.  Only its
                        # remaining source text belongs in the follower; the
                        # next sentence may be an independent clause in the
                        # same paragraph and must not be swallowed.
                        continuation = source_form[len(matched_form):]
                        break
                if continuation:
                    break
            if continuation:
                break
            if any(form.rstrip("。；;") == matched_form.rstrip("。；;")
                   for form in source_forms for matched_form in matched_forms):
                # The current source sentence is already fully bound.  In this
                # case the next operation sentence is the only authorized
                # follower sentence.
                continuation = reference_sentences[index + 1]
                break
        if not continuation:
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
        follower_span = by_location.get(follower_location)
        if follower_span is None:
            continue
        follower_end = authorized_prefix_end(follower, equivalent_forms(continuation))
        if follower_end is None:
            continue
        follower_sentence = follower[:follower_end]
        # Compare the beginning of the actual follower with the authorized
        # sentence.  The source may use a class-free lead and the bounded G17
        # punctuation/holder variants above, but the returned slice ends at the
        # first source terminator and never consumes the next sentence.
        if len(_compact(follower_sentence)) >= 8:
            return (follower_location, 0, len(_compact(follower_sentence)))
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


def _extend_g15_payment_delay_target(text: str, start: int, end: int) -> int:
    """Extend a source-bound G15 payment target through its adjacent delay sentence.

    Some inventory targets bind the payment mechanism but stop before the final
    ``支付日期顺延`` sentence.  That sentence is part of G15's payment clause.  The
    extension is deliberately one immediate raw sentence only: reconciliation,
    usage, and another payment mechanism remain separate source sites (FL-D206).
    """
    if start < 0 or end <= start or end >= len(text):
        return end
    bound = _compact(text[start:end])
    if (not re.search(r"销售服务费每日(?:计提|计算)", bound)
            or "按月支付" not in bound or not bound.endswith("。")):
        return end
    cursor = end
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    stop = next((index for index in range(cursor, len(text))
                 if text[index] in "。！？；!?;"), None)
    if stop is None:
        return end
    sentence = _compact(text[cursor:stop + 1])
    if re.fullmatch(r"若遇[^。；;！？!?]{1,80}[，,](?:销售服务费)?支付(?:日期|时间)(?:相应)?顺延[。！？；!?;]",
                    sentence):
        return stop + 1
    return end


def _g12_short_holding_end(compact: str, end: int, old: str) -> int:
    """Extend to the short-holding sentence only when this operation owns it.

    G12:1's reference includes ``其中，对持续持有期少于7日的投资者……``; G12:0's
    reference ends before it.  The same paragraph therefore needs two different
    bounds, decided by the operation's own old text, never by the sibling G13 rule.
    """
    if "对持续持有期少于7日的投资者收取" not in old:
        return end
    match = re.match(
        r"其中[，,]?对持续持有期少于7日的投资者收取[^。；;！？!?]{0,60}[。；;]",
        compact[end:])
    return end + match.end() if match is not None else end


def _g12_allocation_end(text: str, operation: Mapping[str, Any]) -> int | None:
    """Recognize only an operation-owned redemption-fee allocation prefix.

    Explicit percentages describe the same old allocation policy as the guide's
    unspecified statutory proportion. A following independent sentence is never
    part of this prefix. The short-holding sentence belongs here only when this
    operation's own reference includes it (not a sibling G13 authorization).
    """
    bearer = ("赎回费用由赎回基金份额的基金份额持有人承担，"
              "在基金份额持有人赎回基金份额时收取。")
    old = _compact(str(operation.get("old_text") or ""))
    new = _compact(str(operation.get("new_text") or ""))
    if (operation.get("op") != "replace" or not old.startswith(bearer)
            or new != bearer + "赎回费用全额计入基金财产。"
            or not ("赎回费用归入基金财产的比例" in old
                    or "赎回费总额的" in old)):
        return None
    compact, offsets = compact_offsets(text)
    if not compact.startswith(bearer):
        return None
    ratio = re.match(
        r"不低于赎回费总额的(?P<ratio>\d{1,3}(?:\.\d+)?)%应归基金财产[，,]"
        r"其余用于支付登记费和其他必要的手续费[。；;]", compact[len(bearer):])
    if ratio is not None:
        if not 0 < float(ratio.group("ratio")) <= 100:
            return None
        end = len(bearer) + ratio.end()
        end = _g12_short_holding_end(compact, end, old)
        return offsets[end - 1] + 1
    # Historical contracts also express the same allocation policy without a
    # percentage, for example ``比例应根据相关规定执行，具体见招募说明书的
    # 规定，未计入基金财产的部分用于支付登记费和其他必要的手续费。``.
    # Keep this bounded to the current sentence and require both the allocation
    # subject and the unallocated-balance use.  The following short-holding
    # sentence belongs to G13 and must remain outside this operation.
    generic = re.match(
        r"赎回费用归入基金财产的比例[^。；;！？!?]{0,180}"
        r"(?:未(?:计入|归入)|其余)[^。；;！？!?]{0,80}"
        r"用于支付登记费和其他必要的手续费[。；;]",
        compact[len(bearer):])
    # G12:0's canonical old text ends after the standard ``比例……招募说明书``
    # wording, while the guide's declared historical variant may spell the same
    # allocation boundary with ``具体见……未计入……``.  The operation still owns
    # that complete G12 source variant; no sibling G13 text is borrowed.
    if generic is None or "比例" not in old:
        return None
    end = len(bearer) + generic.end()
    end = _g12_short_holding_end(compact, end, old)
    return offsets[end - 1] + 1


def _g12_source_effect_owned(before: str, after: str, operation: Mapping[str, Any]) -> bool:
    end = _g12_allocation_end(before, operation)
    return end is not None and _same_compact(
        after, str(operation.get("new_text") or "") + before[end:])


_G06_PROHIBITION = re.compile(
    r"(?:(?:不同基金份额类别之间)|(?:[A-ZＡ-Ｚ]\s*类\s*基金\s*份额)"
    r"(?:和|、|及|或)[A-ZＡ-Ｚ]\s*类\s*基金\s*份额之间)"
    r".{0,32}(?:不得|不能|不允许|暂不允许|不可)"
    r".{0,18}(?:互相|相互|进行)?转换|"
    r"[A-ZＡ-Ｚ]\s*类\s*基金\s*份额.{0,32}"
    r"(?:不得|不能|不允许|暂不允许|不可).{0,18}"
    r"(?:互相|相互|进行)?转换")


def _g06_prohibition_bounds(text: str, start: int | None, end: int | None
                            ) -> tuple[int, int, str] | None:
    """A source-bound class-conversion prohibition may be deleted as one sentence.

    G06's guide reference includes the optional ``除非…另行公告…`` prefix, while a
    contract often stores only the prohibition sentence, or splits the prefix and
    sentence differently. The already source-bound target proves this operation
    owns the sentence; expand only to its immediate sentence boundary and require
    the conversion prohibition inside it.
    """
    if start is None or end is None or start < 0 or end <= start or end > len(text):
        return None
    left, right = start, end
    while left > 0 and text[left - 1] not in "。；;！？":
        left -= 1
    if not text[:end].rstrip().endswith(tuple("。；;！？")):
        while right < len(text) and text[right] not in "。；;！？":
            right += 1
        if right < len(text):
            right += 1
    sentence = text[left:right]
    compact = _compact(sentence)
    if len(compact) > 160 or not _G06_PROHIBITION.search(compact):
        return None
    return left, right, sentence


def _g13_short_holding_end(text: str, operation: Mapping[str, Any]) -> int | None:
    """One complete short-holding sentence, authorized by this deletion alone."""
    old = _compact(str(operation.get("old_text") or ""))
    if (operation.get("op") != "delete" or not all(
            token in old.replace("1.50%", "1.5%")
            for token in ("少于7日", "1.5%", "赎回费", "全额计入基金财产"))):
        return None
    compact, offsets = compact_offsets(text)
    match = re.match(
        r"(?:其中[，,]?)?(?:本基金)?(?:对于|对)?持续持有期少于7日的投资[者人]"
        r"收取(?:不低于)?1\.5(?:0)?%的赎回费[，,]"
        r"(?:并(?:将上述赎回费)?|并将赎回费|并)?全额计入基金财产[。；;]", compact)
    return offsets[match.end() - 1] + 1 if match else None


def _g13_short_holding_owned(inspection: Any, location: str, text: str,
                             operation: Mapping[str, Any]) -> int | None:
    """Return a locally editable end for a source-bound G13 sentence.

    Inventory may bind only the continuation of a sentence split over two DOCX
    paragraphs.  The operation still has to prove the complete source clause: the
    preceding paragraph is context only and is never included in the edit.  This
    helper accepts that shape only when the operation's own reference authorizes
    the complete short-holding sentence and the match ends at this target's end.
    """
    local_end = _g13_short_holding_end(text, operation)
    if local_end is not None:
        return local_end
    old = _compact(str(operation.get("old_text") or ""))
    if operation.get("op") != "delete" or not old:
        return None
    spans = list(getattr(inspection, "paragraphs", ()) or ())
    index = next((i for i, span in enumerate(spans)
                  if str(getattr(span, "location", "")) == str(location)), -1)
    if index <= 0 or str(text).lstrip() != str(text):
        return None
    context = str(spans[index - 1].text)
    compact_context, _ = compact_offsets(context)
    compact_text, _ = compact_offsets(text)
    joined = compact_context + compact_text
    # The full operation must authorize the same business clause.  Requiring the
    # operation's distinctive markers prevents a naked "7 日..." tail from
    # borrowing authorization from a neighbouring fee sentence.
    old_markers = old.replace("1.50%", "1.5%")
    if not all(token in old_markers for token in ("少于7日", "1.5%", "赎回费", "全额计入基金财产")):
        return None
    match = re.search(
        r"(?:其中[，,]?)?(?:本基金)?(?:对于|对)?持续持有期少于7日的投资[者人]"
        r"收取(?:不低于)?1\.5(?:0)?%的赎回费[，,]"
        r"(?:并(?:将上述赎回费)?|并将赎回费|并)?全额计入基金财产[。；;]", joined)
    if (match is None or match.end() != len(joined)
            or match.start() >= len(compact_context)):
        return None
    return len(str(text).rstrip())


def _g15_payment_clause_end(text: str, start: int, end: int, *, allow_head: bool = False) -> int | None:
    """Find the explicit delay terminator without crossing another business clause."""
    current = text[start:end]
    compact_current = _compact(current)
    if ("销售服务费" not in compact_current
            or not any(token in compact_current for token in
                       ("每日计提", "每日计算", "逐日累计", "日计提"))
            or not any(token in compact_current for token in ("按月支付", "逐月支付"))):
        return None
    service_pos = compact_current.find("销售服务费")
    lead = compact_current[:service_pos]
    # The payment operation owns a normal class/product lead, but not an arbitrary
    # policy sentence that happens to end in ``基金份额的``.  Keep the stricter
    # boundary while accepting real contracts' multi-class and one-year variants.
    lead_ok = bool(re.fullmatch(
        r"(?:基金)?(?:(?:[A-ZＡ-Ｚ]类(?:基金份额)?[、，,和及与]?)+)?的?(?:基金)?", lead))
    lead_ok = lead_ok or bool(re.fullmatch(
        r"对于投资者持续持有期限未超过一年(?:（即365天[，,]?下同）)?的基金份额收取的", lead))
    if not lead_ok:
        return None
    parsed_end = 0
    for index, match in enumerate(re.finditer(r"[^。；;！？!?]+[。；;！？!?]", current)):
        parsed_end = match.end()
        sentence = _compact(match.group())
        if any(token in sentence for token in (
                "费用自动扣划后", "销售服务费主要用于", "销售服务费使用范围", "管理费", "赎回款")):
            return None
        if sentence.startswith("若遇"):
            if re.fullmatch(
                    r"若遇[^。；;！？!?]{1,80}[，,](?:销售服务费)?支付(?:日期|时间)(?:相应)?顺延[。！？；!?;]",
                    sentence):
                return start + match.end()
            return None
        if index > 0 and not any(token in sentence for token in (
                "划付指令", "划拨指令", "财务数据", "基金财产", "代付", "支付给")):
            return None
    if allow_head and parsed_end and not current[parsed_end:].strip():
        return end
    return None


def _bound_g15_payment_target(text: str, start: int, end: int) -> int:
    """Return the end of G15's payment clause within an already bound target."""
    clause_end = _g15_payment_clause_end(text, start, end)
    if clause_end is not None:
        return clause_end
    return _extend_g15_payment_delay_target(text, start, end)


def _g15_payment_delete_authorized(operation: Mapping[str, Any]) -> bool:
    """Only a complete payment-and-delay deletion grants the bounded executor."""
    if operation.get("op") != "delete":
        return False
    reference = str(operation.get("old_text") or "").rstrip()
    return bool(reference) and _g15_payment_clause_end(reference, 0, len(reference)) == len(reference)


def _g15_payment_source_owned(text: str, operation: Mapping[str, Any]) -> bool:
    """Prove a complete payment variant without trusting planner evidence.

    A split payment head may end before its delay sentence. Validate every head
    sentence with the same parser by using the operation's own delay terminator;
    closure separately requires the real adjacent delay site when present.
    """
    if operation.get("op") != "delete":
        return False
    if _same_compact(text, str(operation.get("old_text") or "")):
        return True
    body = text.rstrip()
    reference = str(operation.get("old_text") or "").rstrip()
    if not _g15_payment_delete_authorized(operation):
        # A custom guide can authorize only the one accrual/payment sentence.
        # Its same-sentence payment variant is valid, but it grants no right to
        # remove another sentence or a delay tail missing from the operation.
        sentences = r"[^。；;！？!?]+[。；;！？!?]"
        return bool(re.fullmatch(sentences, body) and re.fullmatch(sentences, reference)
                    and not _compact(body).startswith("若遇")
                    and _g15_payment_clause_end(reference, 0, len(reference), allow_head=True) == len(reference)
                    and _g15_payment_clause_end(body, 0, len(body), allow_head=True) == len(body))
    if _g15_payment_clause_end(body, 0, len(body)) == len(body):
        return True
    return _g15_payment_clause_end(body, 0, len(body), allow_head=True) == len(body)


def _g15_delay_continuation(inspection: Any, location: str,
                            operation: Mapping[str, Any] | None = None) -> tuple[int, int] | None:
    """Bind only the next paragraph's first delay sentence to its payment head."""
    if operation is not None and not _g15_payment_delete_authorized(operation):
        return None
    spans = list(inspection.paragraphs)
    index = next((i for i, span in enumerate(spans) if span.location == location), -1)
    if index <= 0:
        return None
    head = str(spans[index - 1].text).rstrip()
    body = str(spans[index].text)
    # The next paragraph can start with the payment continuation and put the
    # delay sentence second (the production contract's p806/p807 shape), or it
    # can start directly with ``若遇``.  In both cases the whole prefix through
    # the first delay sentence is one source-bound G15 tail.
    match = re.search(r"若遇[^。；;！？!?]+[。；;！？!?]", body)
    if match is None:
        return None
    sentence = body[:match.end()]
    joined = head + sentence
    # The existing payment parser checks every intervening sentence and excludes
    # reconciliation, other fees and unrelated policy. Proximity alone is no proof.
    if _g15_payment_clause_end(joined, 0, len(joined)) != len(joined):
        return None
    # Composite part slices cover the whole paragraph when the only source text
    # after the delay sentence is formatting whitespace.  Keep that whitespace
    # inside the source-bound edit so Claim Replay compares the same raw span as
    # the writer (FL-D275); unrelated visible text still ends at the sentence.
    return 0, len(body) if not body[match.end():].strip() else match.end()


def _g15_split_payment_head_owned(inspection: Any, target: Target,
                                  operation: Mapping[str, Any]) -> bool:
    """Prove a G15 payment head whose delay sentence is in the next paragraph.

    Real DOCX files commonly split the payment clause after ``按月支付，``.
    The target on the first paragraph therefore cannot contain the guide's full
    ``old_text``.  Attribution still has to bind the complete source clause: the
    next paragraph must contribute only its first, operation-owned delay sentence
    and the shared payment parser must accept the joined text.  This keeps the
    operation-specific guard while avoiding a false ``operation_span_mismatch``.
    """
    if not _g15_payment_delete_authorized(operation) or target.composite:
        return False
    if target.start != 0 or target.end is None:
        return False
    try:
        spans = list(inspection.paragraphs)
        index = next(i for i, span in enumerate(spans)
                     if str(span.location) == str(target.location))
    except (StopIteration, AttributeError):
        return False
    head = spans[index]
    if target.end != len(str(head.text)) or not _same_compact(target.quote, head.text):
        return False
    if index + 1 >= len(spans):
        return False
    follower = spans[index + 1]
    return _g15_delay_continuation(inspection, str(follower.location), operation) is not None


def g15_delay_continuation_targets(targets: Sequence[Target], rules: Mapping[str, dict],
                                   inspection: DocumentInspection) -> list[Target]:
    """Close an established G15 payment site's immediately adjacent delay tail."""
    rule = rules.get("G15")
    if rule is None:
        return []
    spans = list(inspection.paragraphs)
    positions = {span.location: i for i, span in enumerate(spans)}
    added: list[Target] = []
    for target in targets:
        if (target.rule_id != "G15" or target.out_of_scope or target.attribution_error
                or target.state not in {"needs_edit", "satisfied"}
                or target.resolution != "resolved"):
            continue
        index = positions.get(target.location, -1)
        if index < 0 or index + 1 >= len(spans):
            continue
        head = spans[index]
        if (target.start != 0 or target.end is None
                or str(head.text)[target.end:].strip()
                or not _same_compact(target.quote, str(head.text)[:target.end])):
            continue
        for op_index, operation in enumerate(rule.get("operations") or []):
            key = _rule_operation_key(rule, op_index)
            if key not in target.operations:
                continue
            follower = spans[index + 1]
            bound = _g15_delay_continuation(inspection, follower.location, operation)
            if bound is None:
                continue
            start, end = bound
            if any(t.location == follower.location and key in t.operations
                   and not t.out_of_scope and t.start == start and t.end == end
                   for t in [*targets, *added]):
                continue
            added.append(Target(
                f"{target.target_id}:delay", "G15", follower.location,
                str(follower.text)[start:end], "needs_edit", "source_payment_delay_continuation",
                start=start, end=end, resolution="resolved",
                segment_ok=containing_segment(follower, start, end) is not None,
                operations=(key,)))
    return added


def _g08_fee_clause_start(text: str, start: int, end: int,
                          operation: Mapping[str, Any], facts: Facts) -> int:
    """Include a same-sentence exemption already restated by this full policy."""
    if operation.get("op") != "replace" or not (0 < start < end <= len(text)):
        return start
    policy, issues = instantiate_policy_text("G08", operation, facts)
    if issues:
        return start
    from .generation.template import plan_policy_replacement
    if plan_policy_replacement(text[start:end], policy, "G08") is None:
        return start
    # Exactly one literal current-class exemption joined by a comma to the bound
    # rate clause. A full stop, fee formula, extra mechanism or different policy
    # cannot be swallowed merely because it is nearby (FL-D217).
    match = re.search(
        r"(?:本基金\s*)?[A-ZＡ-Ｚ]\s*类\s*基金\s*份额\s*不收取\s*申购费(?:用)?\s*[，,]\s*$",
        text[:start])
    if match is None:
        return start
    if match.start() and text[:match.start()].rstrip()[-1:] not in "。；;！？!?：:":
        return start
    from .fact_evidence import class_labels
    prefix = _compact(match.group()).rstrip("，,")
    equivalent = prefix.removeprefix("本基金").replace("申购费用", "申购费")
    if (class_labels(prefix) and equivalent in _compact(policy).replace("申购费用", "申购费")
            and plan_policy_replacement(text[match.start():end], policy, "G08") is not None):
        return match.start()
    return start


def _keyword_bag_in_clause(body: str, bag: tuple[str, ...], window: int = 60) -> bool:
    """True when every keyword appears inside one short window of the paragraph body.

    A paragraph can hold several clauses (a托管费 sentence followed by a销售服务费
    heading); requiring the keywords anywhere in the paragraph lets a neighbouring clause
    satisfy the signature. A bounded window keeps the hit on the clause the rule is about
    while still allowing the fixed wording to span a comma (FL-D062).
    """
    if not bag:
        return False
    positions: list[int] = []
    for token in bag:
        variants = _KEYWORD_VARIANTS.get(token, (token,))
        position = min((body.find(variant) for variant in variants
                        if body.find(variant) >= 0), default=-1)
        positions.append(position)
    if any(position < 0 for position in positions):
        return False
    for start in positions:
        if all(abs(position - start) <= window for position in positions):
            return True
    return False


def _delete_keyword_bag(rule: dict, facts: Facts | None) -> tuple[str, ...]:
    """Closed-class keyword requirements derived from applicable delete references.

    A pure deletion frequently survives in contracts in several paraphrases ("每日计提"
    against "每日计算", "按月支付" against "次月支付"), so no single string anchor covers
    every wording. The rule's own reference text still names the domain terms, the action
    it is about, and (for the payment clause) a period or purpose marker; requiring the
    matched markers to co-occur in one window finds the clause across paraphrases while
    staying specific enough not to hit neighbouring fee lines (FL-D062).

    Groups are collected independently and at least two must match — G06 carries a domain
    term plus the conversion action, G13 a domain term plus collection action and holding
    period, G17 a domain term plus the purpose markers (external review 2026-10-19, P1:
    deterministic recall for G06/G13/G17).
    """
    domain = ("销售服务费", "申购费", "赎回费", "认购费", "管理费", "托管费",
              "销售服务费率", "份额类别")
    action = ("支付", "划付", "划出", "划款", "计提", "计算", "收取", "计入", "转换")
    period = ("按月", "次月", "每月", "逐日", "每季", "持有期", "少于7日", "7日", "七日")
    purpose = ("佣金", "广告", "促销", "持有人服务", "使用范围")
    references = []
    for operation in rule.get("operations") or []:
        if facts is not None and not condition_matches(operation.get("condition"), facts):
            continue
        if operation.get("op") == "delete":
            references.append(_compact(str(operation.get("old_text") or "")))
    if not references:
        return ()
    body = "".join(references)
    bag: list[str] = []
    for group in (domain, action, period, purpose):
        matched = next((token for token in group if token in body), None)
        if matched:
            bag.append(matched)
    # At least a domain term plus one more marker; a lone fee mention must not qualify.
    return tuple(bag) if len(bag) >= 2 else ()


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


_CLASS_LETTER_FORM = re.compile(
    r"^([A-Za-zＡ-Ｚａ-ｚ0-9]+)(?:类(?:基金份额|份额)?|基金份额|份额|类)?$")


def class_label(names: Sequence[str]) -> str:
    """Build the guide's class-group label from fact names such as "A", "A类基金份额".

    Letter-type names are canonicalised ("A", "A类份额" → "A类"); names the contract
    writes descriptively ("人民币份额", "A类人民币份额") are kept **verbatim** — the
    guide requires the product's own class wording, and rebuilding those names produced
    doubled labels such as "人民币类基金份额" / "A类人民币类基金份额" (external review
    2026-10-19, P0-B). The trailing "基金份额" is appended only when every component is
    a bare "X类" form. Placeholder names ("default") are dropped.
    """
    cleaned: list[str] = []
    for name in names:
        label = re.sub(r"\s+", "", name or "")
        if not label or label.lower() in _PLACEHOLDER_CLASS_NAMES:
            continue
        match = _CLASS_LETTER_FORM.match(label)
        if match:
            label = match.group(1) + "类"
        if label not in cleaned:
            cleaned.append(label)
    if not cleaned:
        return "基金份额"
    joined = "、".join(cleaned)
    if all(label.endswith("类") and "份额" not in label for label in cleaned):
        joined += "基金份额"
    return joined


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


def instantiate_policy_text(rule_id: str, operation: Mapping[str, Any],
                            facts: Facts) -> tuple[str, list[str]]:
    """The operation's applicable new policy, shared by replay/effects/review.

    Only certified absence may remove the service-group component. In particular,
    an empty extraction with UNKNOWN/CONFLICT is not an empty business group.
    This mirrors the planner's existing partial-component reduction for G08/G11
    and append reduction for G01/G03; it grants no new operation/site authority.
    """
    text = str(operation.get("new_text") or "")
    if (rule_id in {"G01", "G03", "G08", "G11"}
            and "C类基金份额" in text and not facts.service_group):
        if any(facts.status_of(name) != "VERIFIED" for name in (
                "share_class_structure", "service_fee_group")):
            return text, ["SERVICE_GROUP_UNVERIFIED"]
        if operation.get("op") == "append":
            reduced = _append_without_missing_group(text, facts)
            return (reduced, []) if reduced else (text, ["SUBSCRIPTION_GROUP_EMPTY"])
        if operation.get("op") == "replace":
            reduced = _reduce_missing_group_operation(dict(operation), facts)
            text = str((reduced or {}).get("new_text") or "")
            if not text:
                return text, ["POLICY_COMPONENTS_EMPTY"]
    return instantiate_slots(text, facts)


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


def _trim_missing_group_text(text: str, missing: str = "C类基金份额") -> str:
    """Drop only the sentences/clauses naming the missing class group (plan P0-D).

    G08/G11 carry one combined replacement: the subscription-group policy, the
    service-group sentence and the channel policy. When the product lacks the
    service-fee class, only the clauses naming it disappear — the rest of the
    obligation (subscription group + channel policy) still applies, so the whole
    operation must not be dropped (external review 2026-10-19).
    """
    kept_sentences: list[str] = []
    for sentence in re.split(r"(?<=[。；])", text):
        if not sentence:
            continue
        if missing not in sentence:
            kept_sentences.append(sentence)
            continue
        clauses = re.split(r"(?<=，)", sentence)
        kept_clauses = [clause for clause in clauses if missing not in clause]
        kept_sentences.append("".join(kept_clauses))
    trimmed = "".join(kept_sentences).strip()
    trimmed = re.sub(r"[，、；]+(?=。)", "。", trimmed)
    trimmed = re.sub(r"[；，、]+$", "。", trimmed)
    return trimmed


def _reduce_missing_group_operation(operation: dict, facts: Facts) -> dict | None:
    """Rewrite one replace operation without its missing-service-group clauses."""
    text = str(operation.get("new_text") or "")
    if "C类基金份额" not in text:
        return operation
    trimmed = _trim_missing_group_text(text)
    if not trimmed.strip():
        return None
    if not trimmed.endswith(("。", "；")):
        trimmed += "。"
    reduced = dict(operation)
    reduced["new_text"] = trimmed
    reduced["dropped_component"] = "service_fee_group"
    return reduced


def _drop_empty_group_operations(rule: dict, operations: Sequence[dict],
                                 facts: Facts) -> list[dict]:
    """Resolve operations whose replacement names a class group the product lacks.

    Registry mode (plan P0-D) trims only the clauses naming the missing group and keeps
    the remaining obligation; legacy mode keeps the historical whole-operation drop.
    """
    if not rule.get("class_substitution") or facts.service_group:
        return list(operations)
    if not _tier1_enabled():
        # An append is never dropped here: ``plan_target``'s append path handles a
        # missing service-fee class by dropping only the sentence that names it
        # (FL-D090), so removing the whole operation would silently lose the obligation.
        kept = [operation for operation in operations
                if operation.get("op") == "append"
                or "C类基金份额" not in str(operation.get("new_text") or "")]
        return kept
    reduced_ops: list[dict] = []
    for operation in operations:
        if operation.get("op") == "append":
            reduced_ops.append(operation)
            continue
        reduced = _reduce_missing_group_operation(operation, facts)
        if reduced is not None:
            reduced_ops.append(reduced)
    return reduced_ops


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


# Hard-fact topic tokens per rule family (F1: a plain presence test, no interpretation).
# The engine may only veto a model judgment when the contract provably lacks the topic
# the rule is about; anything weaker (a paraphrase of the reference text) is a semantic
# judgment and must stay with the model (FL-D106).
_RULE_TOPIC_TOKENS: dict[str, tuple[str, ...]] = {
    "G01": ("销售服务费", "直销", "份额类别"),
    "G02": ("基金份额",),
    "G03": ("销售服务费", "份额类别"),
    "G04": ("基金份额",),
    "G05": ("调低", "费率"),
    "G06": ("份额类别", "转换"),
    "G07": ("申购费",),
    "G08": ("申购费",),
    "G09": ("赎回金额",),
    "G10": ("申购费",),
    "G11": ("申购费",),
    "G12": ("赎回费",),
    "G13": ("赎回费",),
    "G14": ("调低", "费率"),
    "G15": ("销售服务费", "支付"),
    "G16": ("销售服务费",),
    "G17": ("销售服务费",),
    "G18": ("销售服务费", "费用"),
    "G19": ("清算", "分配"),
    "G20": ("清算", "分配"),
    "G21": ("清算", "分配"),
    "G22": ("清算", "分配"),
}


def hard_fact_topic_absent(rule: dict, document_compact: str) -> bool:
    """True only when the contract provably lacks the rule's topic (F1, hard fact).

    This is the one deterministic veto that may override a model judgment, because
    "the contract never mentions the subject of this rule" is a verifiable fact, not
    an interpretation: a document with no ``销售服务费`` occurrence genuinely has no
    sales-service-fee clause to edit.

    Every weaker signal the engine currently uses — a reference text that does not
    appear verbatim, a class group the product lacks, a paraphrase — is a **semantic**
    judgment. Per FL-D106 those must not silently drop a target the model reported;
    they are returned as "needs review" instead (see ``weak_rule_signals``).
    """
    if not document_compact:
        return False
    tokens = _RULE_TOPIC_TOKENS.get(str(rule.get("rule_id") or ""))
    if not tokens:
        return False
    # Every topic token must be absent for this to be a hard fact.
    return all(_compact(token) not in document_compact for token in tokens)


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

    Two reasons return True; they are **not** equivalent under FL-D106:

    * ``class_substitution_letter_stable`` — the instantiated replacement equals the
      reference (a *hard fact*: the substitution provably yields identical text, so there
      is nothing to change);
    * ``fee_homogeneous_classes`` — the product's classes share one fee profile, so the
      guide's grouping selects nothing (a *semantic* judgment: whether the clause applies
      is exactly what needs adjudication, so it must not silently drop a model target).
    """
    if not rule.get("class_substitution"):
        return False
    if class_substitution_letter_stable(rule, facts):
        return True
    return fee_homogeneous_classes(facts)


def class_substitution_letter_stable(rule: dict, facts: Facts) -> bool:
    """Hard fact: every instantiated replacement equals its reference (nothing to change)."""
    if any(facts.status_of(name) != "VERIFIED" for name in (
            "share_class_structure", "subscription_fee_group", "service_fee_group")):
        return False
    if not rule.get("class_substitution") or fee_homogeneous_classes(facts):
        return False
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


def _condition_fact_names(condition: dict | None) -> set[str]:
    if not condition:
        return set()
    kind = condition.get("kind")
    if kind == "compound":
        names: set[str] = set()
        for part in condition.get("value") or []:
            names |= _condition_fact_names(part)
        return names
    if kind == "class_count":
        return {"share_class_structure"}
    if kind == "has_service_fee":
        return {"share_class_structure", "subscription_fee_group", "service_fee_group"}
    if kind == "is_floating_fee":
        return {"floating_management_fee"}
    return set()


def _condition_override(condition: dict | None, facts: Facts) -> str | None:
    if not condition:
        return None
    import json
    key = json.dumps(condition, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    value = getattr(facts, "condition_overrides", {}).get(key)
    if value not in {"TRUE", "FALSE"}:
        return None
    # A branch opinion cannot substitute for a missing prerequisite fact.
    names = _condition_fact_names(condition)
    if names:
        return None
    return value


def condition_matches(condition: dict | None, facts: Facts) -> bool:
    names = _condition_fact_names(condition)
    if any((not facts.quotes_verified.get("floating", False)
            if name == "floating_management_fee" else facts.status_of(name) != "VERIFIED")
           for name in names):
        return False
    override = _condition_override(condition, facts)
    if override is not None:
        return override == "TRUE"
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


def condition_status(condition: dict | None, facts: Facts) -> str:
    """Tri-state applicability: ``TRUE | FALSE | UNKNOWN`` (external review 2026-10-19).

    UNKNOWN means the contract's facts do not prove either branch. Callers must keep
    the target unresolved instead of guessing one (plan §3.3: an unknown fact never
    falls through to generation). Only consulted in registry mode; the legacy
    ``condition_matches`` behaviour is unchanged.
    """
    override = _condition_override(condition, facts)
    if override is not None:
        return override
    if not condition:
        return "TRUE"
    kind = condition.get("kind")
    value = condition.get("value")
    if kind == "none":
        return "TRUE"
    if kind == "compound":
        statuses = [condition_status(part, facts) for part in value or []]
        if any(status == "FALSE" for status in statuses):
            return "FALSE"
        if any(status == "UNKNOWN" for status in statuses):
            return "UNKNOWN"
        return "TRUE"
    if kind == "class_count":
        if facts.status_of("share_class_structure") != "VERIFIED":
            return "UNKNOWN"
        count = facts.class_count
        if value == 1:
            return "TRUE" if count == 1 else "FALSE"
        if value == "multiple":
            return "TRUE" if count > 1 else "FALSE"
        return "FALSE"
    if kind == "has_service_fee":
        if any(facts.status_of(name) != "VERIFIED" for name in
               ("share_class_structure", "subscription_fee_group", "service_fee_group")):
            return "UNKNOWN"
        return "TRUE" if bool(value) == facts.has_service_fee else "FALSE"
    if kind == "is_floating_fee":
        if not facts.quotes_verified.get("floating", False):
            return "UNKNOWN"
        return "TRUE" if bool(value) == facts.floating_management_fee else "FALSE"
    return "UNKNOWN"


_FACT_STATUS_KEYS = ("fund_type", "share_class_structure", "subscription_fee_group",
                     "service_fee_group", "direct_sales_exempt_group",
                     "other_sales_charged_group")


def _fact_status_map(facts: Facts) -> dict[str, str]:
    return {key: facts.status_of(key) for key in _FACT_STATUS_KEYS}


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
    # The guide operation(s) and obligation(s) this edit actually executes.  This is
    # the edit's own identity; Claim Replay must not have to re-derive it from a
    # target id, which can be synthesized/merged.
    operation_keys: tuple[str, ...] = ()
    obligation_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id, "rule_id": self.rule_id, "location": self.location,
            "start": self.start, "end": self.end, "replacement": self.replacement,
            "operation": self.operation, "content_source": self.content_source,
            "evidence": self.evidence, "anchor_sha256": self.anchor_sha256,
            "operation_keys": list(self.operation_keys),
            "obligation_ids": list(self.obligation_ids),
        }


def _same_compact(left: str, right: str) -> bool:
    return _compact(left) == _compact(right)


def _replay_fragments(actual: str, fragments: Sequence[dict[str, Any]]) -> str | None:
    """Re-apply recorded fragment operations to the source span for verification.

    The planner records each splice it actually applied; replaying them on the
    original span proves the replacement came from the source text and the authorized
    fragments, instead of trusting the planner's output (FL-D112).
    """
    current = actual
    for item in fragments:
        old_text = str(item.get("old_text") or "")
        new_text = str(item.get("new_text") or "")
        if item.get("mode") == "g05_splice":
            # G05 is a terminal-word substitution inside one sentence; inserting
            # sentence separators around it would change the approved replacement
            # and make its own content check fail (D01 p135).
            if current.count(old_text) != 1:
                return None
            current = current.replace(old_text, new_text, 1)
            continue
        if _same_compact(old_text, current):
            current = new_text
            continue
        updated = _splice_fragment(current, old_text, new_text)
        if updated is None:
            return None
        current = updated
    return current


_G05_SPLICE = re.compile(r"调低[^。；;]*?赎回费率")


def plan_g05_splice(actual: str) -> tuple[str, dict[str, Any]] | None:
    """Bounded G05:0 splice: replace the terminal term, keep every modifier.

    The guide's reference is the short "调低赎回费率", but contracts legitimately write
    "调低全部或者部分份额类别的赎回费率".  The old composer then failed with
    RECALL_COMPOSE_FIXED_TEXT_MISSING because the reference was not a literal suffix.
    The operation's real semantics are: inside one sentence, after the unique "调低"
    anchor, replace the terminal "赎回费率" with "销售服务费率".  If the anchor or the
    terminal is not unique in the bound span, this function refuses to guess.
    """
    if not actual:
        return None
    matches = list(_G05_SPLICE.finditer(actual))
    if len(matches) != 1:
        return None
    match = matches[0]
    terminal = "赎回费率"
    cut = actual.rfind(terminal, match.start(), match.end())
    if cut < 0:
        return None
    updated = actual[:cut] + "销售服务费率" + actual[cut + len(terminal):]
    if _compact(updated) == _compact(actual):
        return None
    return updated, {
        "strategy": "g05_bounded_splice",
        "anchor": "调低",
        "old_terminal": terminal,
        "new_terminal": "销售服务费率",
        "matched": actual[match.start():match.end()],
    }


def _normalise_local_punctuation(text: str) -> str:
    """Remove punctuation left empty by a bounded deletion; never rewrite prose."""
    previous = None
    current = text
    pairs = (("，。", "。"), ("；。", "。"), ("、。", "。"), ("，；", "；"),
             ("；，", "；"), ("、，", "，"), ("，、", "，"), ("，，", "，"),
             ("、、", "、"), ("；；", "；"), ("。。", "。"))
    while current != previous:
        previous = current
        for left, right in pairs:
            current = current.replace(left, right)
    return current


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


def _g11_bearer_end(text: str, operation: Mapping[str, Any]) -> int | None:
    """Bound the subscription-fee bearer sentence without consuming class policies."""
    old = _compact(str(operation.get("old_text") or ""))
    if operation.get("op") != "replace" or not all(
            token in old for token in ("申购费用由", "承担", "不列入基金财产")):
        return None
    compact, offsets = compact_offsets(text)
    match = re.match(
        r"[^。；;！？!?]{0,60}申购费用由[^。；;！？!?]{1,40}承担[，,]不列入基金财产[。；;]",
        compact)
    if match is None or any(token in match.group() for token in ("赎回", "认购", "转换")):
        return None
    return offsets[match.end() - 1] + 1


def g11_composite_source_parts(inspection: Any, operation: Mapping[str, Any],
                               location: str) -> tuple[str, ...] | None:
    """Return bounded cross-paragraph slices for a split G11 bearer clause.

    D06 stores ``申购费用由...承担，`` in p228 and ``不列入基金财产。`` in
    p229, immediately followed by the independent C/E/F no-fee sentence.  The
    target must own the two bearer fragments while leaving that following policy
    untouched.
    """
    if operation.get("op") != "replace":
        return None
    spans = list(getattr(inspection, "paragraphs", ()) or ())
    index = next((i for i, span in enumerate(spans)
                  if str(getattr(span, "location", "")) == str(location)), None)
    if index is None or index + 1 >= len(spans):
        return None
    current, following = spans[index], spans[index + 1]
    current_compact, _ = compact_offsets(str(current.text))
    following_compact, _ = compact_offsets(str(following.text))
    if not current_compact or not following_compact:
        return None
    # The source may end in a comma because Word split the sentence at the
    # paragraph boundary.  Avoid joining two independently terminated clauses.
    if current_compact[-1:] not in {"，", ","}:
        return None
    joined = current_compact + following_compact
    boundary = _g11_bearer_end(joined, operation)
    if boundary is None or boundary <= len(current_compact):
        return None
    second_end = boundary - len(current_compact)
    if second_end <= 0 or second_end > len(following_compact):
        return None
    return (f"{current.location}:0:{len(current_compact)}",
            f"{following.location}:0:{second_end}")


def plan_composite_target(rule: dict, target: Target, inspection: DocumentInspection, facts: Facts,
                          *, new_text: str) -> list[PlannedEdit]:
    """Turn a composite (multi-paragraph) reference into one edit per paragraph.

    ``target.composite`` holds ``location:start:end`` items measured in each
    paragraph's whitespace-free text (the survey found them deterministically), so
    each part deletes or replaces only its own slice and keeps the rest verbatim.
    """
    if not target.composite:
        raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
    _target_source_body(target, inspection)
    parts: list[tuple[str, int, int]] = []
    for item in target.composite:
        try:
            location, start_text, end_text = item.rsplit(":", 2)
            parts.append((location, int(start_text), int(end_text)))
        except ValueError:
            raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
    if str(rule.get("rule_id") or "") == "G11":
        indices = _selected_operation_indices(rule, target, inspection, facts, None)
        selected = [rule["operations"][index] for index in indices]
        source = "".join(compact_offsets(inspection.by_location(location).text)[0][start:end]
                         for location, start, end in parts)
        boundary = _g11_bearer_end(source, selected[0]) if len(selected) == 1 else None
        if boundary is None:
            raise RecallError("RECALL_REPLACE_SCOPE_UNPROVEN", {"target": target.target_id})
        # A survey composite may include the following class-fee sentence. That
        # sentence is independent source text, not permission to delete the tail.
        bounded: list[tuple[str, int, int]] = []
        remaining = boundary
        for location, start, end in parts:
            if remaining <= 0:
                break
            length = min(end - start, remaining)
            bounded.append((location, start, start + length))
            remaining -= length
        parts = bounded
        target.composite = tuple(f"{location}:{start}:{end}" for location, start, end in parts)
    edits: list[PlannedEdit] = []
    for index, (location, start_clean, end_clean) in enumerate(parts):
        span = inspection.by_location(location)
        # ``composite`` offsets are measured in the paragraph's whitespace-free text
        # (find_old_text_all), so they must be mapped back through the compact index,
        # not through display_text's raw map (FL-D052).
        compact_body, compact_map = compact_offsets(span.text)
        if start_clean < 0 or end_clean > len(compact_body) or start_clean >= end_clean:
            raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
        if start_clean == 0 and end_clean == len(compact_body):
            # The operation covers the whole paragraph: remove its trailing spaces
            # too.  Mapping only the compact characters left one or two spaces behind,
            # which the artifact validator then reported as an unexplained change.
            start_raw, end_raw = 0, len(span.text)
        else:
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
            replacement = (append_separator(prefix, new_text) + new_text
                           + append_separator(new_text, suffix))
            content_source = "composite_replace"
        else:
            replacement = ""
            content_source = "composite_delete"
        evidence: dict[str, Any] = {
            "composite": True, "unit": target.rule_id, "parts": list(target.composite),
            "part_index": index,
        }
        if content_source == "composite_replace" and new_text:
            # Record the authorized replacement text so the content check can prove it
            # is present instead of trusting the produced paragraph (FL-D112).
            evidence["fixed_text"] = new_text
        edits.append(PlannedEdit(
            target_id=target.target_id, rule_id=target.rule_id, location=location,
            start=start_raw, end=end_raw, replacement=replacement, operation="replace",
            content_source=content_source, evidence=evidence))
    if not edits:
        raise RecallError("RECALL_TARGET_COMPOSITE_UNRESOLVED", {"target": target.target_id})
    if str(rule.get("rule_id") or "") == "G17" and not new_text:
        indices = _selected_operation_indices(rule, target, inspection, facts, None)
        selected = [rule["operations"][index] for index in indices]
        if not selected or any(not _g17_source_effect_owned(inspection, edit.location,
                edit.start, edit.end, edit.replacement, selected) for edit in edits):
            raise RecallError("RECALL_DELETE_SCOPE_UNPROVEN", {
                "rule": "G17", "target": target.target_id})
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


def _tier1_enabled() -> bool:
    """Phase-4 tier-1 generators are opt-in (plan §25): ``registry`` mode only."""
    try:
        return strategy_mode() == "registry"
    except Exception:  # pragma: no cover - flag reading must never break planning
        return False


def _plan_tier1(rule: dict, operations: Sequence[dict], facts: Facts,
                actual: str, *, routing: dict[str, Any] | None = None) -> Any | None:
    """Deterministic generators: G14 structured removal, G09 bounded splice (§7.1/§7.2).

    Returns a ``TemplateResult`` or ``None``; when ``None`` the caller keeps the
    existing cascade (splice → variant → compose).
    """
    from .generation.template import (fee_items, plan_fee_item_removal, plan_splice,
                                      splice_pairs)
    rule_id = str(rule.get("rule_id") or "")
    replace_ops = [operation for operation in operations
                   if operation.get("op") == "replace"]
    if not replace_ops or rule_id not in {"G14", "G09", "G08", "G10", "G11"}:
        return None
    executor = str((routing or {}).get("executor") or "template")
    if executor not in {"template", "splice"}:
        return None
    if rule_id in {"G08", "G10", "G11"}:
        from .generation.template import plan_policy_replacement
        candidates: list[str] = []
        for operation in replace_ops:
            instantiated, issues = instantiate_policy_text(rule_id, operation, facts)
            if issues or not instantiated:
                continue
            if instantiated not in candidates:
                candidates.append(instantiated)
        if len(candidates) != 1:
            return None
        result = plan_policy_replacement(actual, candidates[0], rule_id)
        if result is not None and executor == "splice":
            # A mixed operation is deliberately routed to the bounded splice
            # executor.  The clean-clause helper is only a template executor.
            return None
        return result
    if rule_id == "G14":
        allowed: set[str] = set()
        allowed_order: list[str] = []
        canonical_tail = ""
        for operation in replace_ops:
            instantiated, issues = instantiate_slots(
                str(operation.get("new_text") or ""), facts)
            if issues or not instantiated:
                continue
            for item in fee_items(instantiated):
                if item not in allowed_order:
                    allowed_order.append(item)
            allowed |= fee_items(instantiated)
            if not canonical_tail and "调低" in instantiated:
                canonical_tail = instantiated.split("调低", 1)[1].strip()
        if not allowed:
            return None
        return plan_fee_item_removal(actual, allowed, canonical_tail, allowed_order)
    pairs: list[tuple[str, str]] = []
    for operation in replace_ops:
        instantiated, issues = instantiate_policy_text(rule_id, operation, facts)
        if issues or not instantiated:
            continue
        pairs.extend(splice_pairs(str(operation.get("old_text") or ""), instantiated))
    from .generation.template import plan_g09_splice
    if executor != "splice":
        return None
    return plan_g09_splice(actual, pairs)


def _route_structure(rule_id: str, actual: str, facts: Facts) -> str | None:
    """Classify only the text shape used by the Strategy Router.

    Business applicability is decided before this function.  The classifier is
    deliberately conservative: a clean classification is granted only when a
    deterministic generator can recognize the complete clause.  A failed
    deterministic attempt therefore remains a structural fallback, rather than
    silently authorizing a different operation or allowing facts to be guessed.
    """
    if rule_id in {"G14", "G09"}:
        return "clean"
    if rule_id in {"G08", "G10", "G11"}:
        compact = _compact(actual)
        if rule_id == "G08":
            clean = ("申购费率由基金管理人决定" in compact
                     and "招募说明书" in compact
                     and not any(word in compact for word in
                                 ("赎回", "认购", "转换", "计算方法", "公告", "收费方式")))
        else:
            clean = ("申购费用由" in compact
                     and ("承担" in compact or "不列入基金财产" in compact)
                     and not any(word in compact for word in
                                 ("赎回", "认购", "转换", "公告", "计算方法")))
        return "clean" if clean else "mixed"
    return None


def _route_target_operations(rule: dict, operations: Sequence[dict], facts: Facts,
                             actual: str) -> dict[str, Any]:
    """Route every selected operation and expose the execution contract.

    The planner may combine several operations into one physical edit, but the
    router still evaluates each operation independently.  The aggregate gate is
    conservative: a blocked operation blocks the target, and the narrowest
    allowed executor is selected for the combined edit.
    """
    from .generation.registry import OPERATION_REGISTRY, STRATEGY_REGISTRY, operation_for
    from .generation.router import route_operation

    rule_id = str(rule.get("rule_id") or "")
    fact_status = _fact_status_map(facts)
    decisions: list[dict[str, Any]] = []
    # Only a fully annotated guide operation is a formal Registry contract.
    # Legacy low-level rule fixtures intentionally have no operation_id and must
    # not be mistaken for the built-in Gxx:index inventory.
    if not _registry_execution_authoritative(rule):
        return {"decisions": [], "executor": "legacy",
                "allow_compose_fallback": True}
    for operation in operations:
        index = int(operation.get("_operation_index", 0))
        key = _declared_operation_key(rule_id, index, operation)
        if key not in OPERATION_REGISTRY:
            # A released operation with an explicit identity must have a concrete
            # Registry entry.  This applies equally to extension guides: silently
            # falling back to a rule-level or legacy executor would make the
            # operation identity telemetry-only and could borrow a sibling's policy.
            raise RecallError("RECALL_OPERATION_REGISTRY_MISSING", {
                "operation": key, "rule": rule_id,
            })
        decision = route_operation(
            key,
            fact_status=fact_status,
            structure=_route_structure(rule_id, actual, facts),
        )
        decisions.append({
            "operation": key,
            "requested": decision.requested_tier.value,
            "actual": decision.actual_tier.value if decision.actual_tier else None,
            "selected_executor": decision.selected_executor,
            "fallback_reason": decision.fallback_reason,
            "blocked": decision.blocked,
            "fact_blocking": list(decision.fact_blocking),
            "fact_status": dict(decision.fact_status),
            "allowed_tiers": [tier.value for tier in operation_for(key).allowed_tiers],
        })
    blocked = [item for item in decisions if item["blocked"]]
    if blocked:
        raise RecallError("RECALL_FACT_UNVERIFIED", {
            "rule": rule_id,
            "operations": [item["operation"] for item in blocked],
            "fact_blocking": sorted({field for item in blocked
                                      for field in item["fact_blocking"]}),
        })
    actual_tiers = [item["actual"] for item in decisions if item["actual"]]
    # Compose is an explicit operation choice (G16), while delete is the only
    # executor permitted to remove an entire operation span.  For mixed plans,
    # splice is the safe shared executor and may escalate only when every
    # selected operation declares compose as an allowed structural fallback.
    if any(item["actual"] == "tier3_model_compose" for item in decisions):
        aggregate = "compose"
    elif actual_tiers and all(item["actual"] == "deterministic_delete" for item in decisions):
        aggregate = "delete"
    elif actual_tiers:
        aggregate = "template" if all(item["actual"] == "tier1_template" for item in decisions) else "splice"
    else:
        aggregate = "compose"
    return {"decisions": decisions, "executor": aggregate,
            "allow_compose_fallback": bool(decisions) and (
                all("tier3_model_compose" in item["allowed_tiers"] for item in decisions))}


def _routing_for_target(rule: dict, target: Target, inspection: DocumentInspection,
                        facts: Facts, obligations: Any = None) -> dict[str, Any]:
    """Build the operation execution contract for one resolved target."""
    selected_indices = _selected_operation_indices(rule, target, inspection, facts,
                                                    obligations)
    operations = [{**rule["operations"][index], "_operation_index": index}
                  for index in selected_indices
                  if 0 <= index < len(rule.get("operations") or [])]
    if not operations:
        return {"decisions": [], "executor": None, "allow_compose_fallback": False}
    if inspection is None:
        # The early fact gate can run without a document. A non-blocked route will
        # still fail later as an unresolved target, while a blocked route has already
        # produced the precise fact error the caller needs.
        return _route_target_operations(rule, operations, facts, "")
    span = inspection.by_location(target.location)
    routing = _route_target_operations(rule, operations, facts, span.text)
    from .generation.registry import operation_for
    policies = {
        operation_for(item["operation"]).policy_components.operation_key:
        operation_for(item["operation"]).policy_components.as_dict()
        for item in routing.get("decisions", ())
        if operation_for(item["operation"]).policy_components is not None
    }
    routing["policy_components"] = policies
    return routing


def _routing_for_compose(routing: dict[str, Any]) -> dict[str, Any]:
    """Record an explicit structural escalation before entering model compose."""
    result = {**routing, "decisions": [dict(item) for item in routing.get("decisions", ())]}
    for item in result["decisions"]:
        if item.get("blocked"):
            continue
        if "tier3_model_compose" not in item.get("allowed_tiers", ()):
            continue
        item["actual"] = "tier3_model_compose"
        item["selected_executor"] = "compose"
        item["fallback_reason"] = "deterministic_executor_failed"
    result["executor"] = "compose"
    return result


def _validate_routed_policy(rule: dict, operations: Sequence[dict], facts: Facts,
                            before: str, after: str, *, mode: str = "replace",
                            check_output: bool = True) -> None:
    """Apply the operation-scoped policy gate before/after a routed executor.

    The legacy rule object is only the source of policy text.  Fact dependencies
    and required components come from the concrete registry operation, so a
    sibling operation cannot authorize this edit by sharing its rule id.
    """
    from .generation.registry import operation_for
    from .generation.validators import Authorization, validate_policy_components

    fact_status = _fact_status_map(facts)
    for operation in operations:
        index = int(operation.get("_operation_index", 0))
        key = _declared_operation_key(str(rule.get("rule_id") or ""), index, operation)
        spec = operation_for(key)
        components = spec.policy_components
        if components is None:
            continue
        # Registry metadata describes the complete policy family, while an
        # individual guide operation may intentionally carry only one part of
        # that family.  Validate the components named by this operation's own
        # fixed text at this site.  This is especially important for G08/G11:
        # their fact gate needs both fee groups, but the replacement text only
        # adds the subscription-fee group.  The built-in G16 text names all
        # four components, so its complete Compose contract remains hard-gated.
        fixed_text = str(operation.get("new_text") or "")
        if components.must_add and fixed_text:
            operation_components = tuple(
                item for item in components.must_add
                if any(_compact(term) in _compact(fixed_text)
                       for term in item.terms)
            )
            components = replace(components, must_add=operation_components)
        # The operation's old/new guide text is the authorization boundary for
        # deliberate qualifier removal (for example G14's赎回/转换 fee items).
        # An empty auth object would treat every removed protected literal as an
        # unauthorized loss even when the guide explicitly replaces that text.
        old_texts = [str(operation.get("old_text") or "")]
        old_texts.extend(str(item) for item in (operation.get("old_text_variants") or ())
                         if str(item))
        new_text, slot_issues = instantiate_slots(fixed_text, facts)
        if slot_issues:
            new_text = fixed_text
        report = validate_policy_components(
            components=components,
            fact_status=fact_status,
            before=before,
            after=after,
            auth=Authorization(
                must_add=(new_text,) if new_text else (),
                remove_patterns=tuple(text for text in old_texts if text),
                rewrite_pairs=((old_texts[0], new_text),)
                if old_texts and old_texts[0] and new_text else (),
                removals_authorized=(mode == "delete"),
            ),
            check_output=check_output,
        )
        if report.verdict != "PASS":
            codes = sorted({finding.code for finding in report.findings})
            raise RecallError("RECALL_POLICY_COMPONENTS_UNVERIFIED", {
                "operation": key, "mode": mode,
                "findings": codes or [report.verdict],
            })


def plan_target(rule: dict, target: Target, inspection: DocumentInspection, facts: Facts,
                gateway: Any, *, compose_budget: list[int],
                obligations: Any = None, approvals: Any = None) -> PlannedEdit | None:
    """Plan one target; registry mode adds tri-state applicability and routing records.

    Tri-state (external review 2026-10-19): an operation whose condition cannot be
    decided from VERIFIED facts never executes — if nothing else is applicable the
    target resolves as ``RECALL_FACT_UNVERIFIED`` instead of guessing a branch. The
    per-operation routing decision (requested/actual tier, fallback reason) is recorded
    on the edit evidence for telemetry.

    ``approvals`` is an optional :class:`semantic_evidence.ApprovalBook`.  When the
    target carries a valid, code-verified approval for this rule/operation/source,
    the rule-specific site word list is a fast path only: it can no longer veto the
    same semantic decision a second time (R01-R03).
    """
    approval_check: dict[str, Any] | None = None

    def _attach(edit: PlannedEdit | None) -> PlannedEdit | None:
        if edit is None:
            return None
        if str(rule.get("rule_id") or "") == "G15" and not edit.replacement.strip():
            indices = _selected_operation_indices(rule, target, inspection, facts, obligations)
            selected = [rule["operations"][index] for index in indices]
            source = inspection.by_location(edit.location).text[edit.start:edit.end]
            approved = (edit.content_source == "approved_span_delete"
                        and approvals is not None
                        and approvals.allows(target, inspection).ok)
            if (not approved and (len(selected) != 1 or not (
                    _g15_payment_source_owned(source, selected[0]) or
                    _g15_delay_continuation(inspection, edit.location, selected[0]) ==
                    (edit.start, edit.end)))):
                raise RecallError("RECALL_DELETE_SCOPE_UNPROVEN", {
                    "rule": "G15", "target": target.target_id, "location": edit.location})
        if str(rule.get("rule_id") or "") == "G17":
            indices = _selected_operation_indices(rule, target, inspection, facts, obligations)
            selected = [rule["operations"][index] for index in indices]
            if selected and all(operation.get("op") == "delete" for operation in selected):
                approved = (edit.content_source == "approved_span_delete"
                            and approvals is not None
                            and approvals.allows(target, inspection).ok)
                if not approved and not _g17_source_effect_owned(
                        inspection, edit.location, edit.start, edit.end,
                        edit.replacement, selected):
                    raise RecallError("RECALL_DELETE_SCOPE_UNPROVEN", {
                        "rule": "G17", "target": target.target_id, "location": edit.location})
        if not edit.operation_keys:
            indices = _selected_operation_indices(rule, target, inspection, facts,
                                                  obligations)
            edit.operation_keys = tuple(_rule_operation_key(rule, index)
                                        for index in indices)
            if obligations is not None:
                edit.obligation_ids = tuple(
                    record.obligation_id for index in indices
                    if (record := obligations.record(_rule_operation_key(
                        rule, index))) is not None)
        evidence = dict(edit.evidence or {})
        evidence.setdefault("operation_keys", list(edit.operation_keys))
        evidence.setdefault("obligation_ids", list(edit.obligation_ids))
        route_plan = getattr(target, "_route_plan", None)
        if route_plan is not None:
            evidence.setdefault("strategy", route_plan.get("decisions", []))
            evidence.setdefault("selected_executor", route_plan.get("executor"))
        if obligations is not None:
            evidence["operation_refs"] = [record.spec.as_dict() for key in edit.operation_keys
                                          if (record := obligations.record(key)) is not None]
        approval_check = getattr(target, "_approval_check", None)
        if approval_check is not None:
            evidence.setdefault("semantic_approval", approval_check)
        edit.evidence = evidence
        return edit

    if not _tier1_enabled():
        return _attach(_plan_target_inner(rule, target, inspection, facts, gateway,
                                          compose_budget=compose_budget,
                                          obligations=obligations, approvals=approvals))
    # Apply the Router's fact gate before source binding. This keeps an UNKNOWN or
    # CONFLICT prerequisite from being reported as a secondary quote/location error.
    operation_list = list(rule.get("operations") or [])
    explicit_keys = {str(key) for key in (getattr(target, "operations", ()) or ())}
    candidate_indices = [index for index, operation in enumerate(operation_list)
                         if (not explicit_keys or _rule_operation_key(rule, index)
                              in explicit_keys)
                         and condition_status(operation.get("condition"), facts) == "TRUE"]
    if candidate_indices:
        # Low-level fixtures without explicit operation identities retain their
        # legacy executor path, but built-in operations still receive the registry
        # fact gate in registry mode.  This preserves fixture compatibility without
        # allowing an UNKNOWN/CONFLICT fact to reach a legacy compose fallback.
        if not _registry_execution_authoritative(rule):
            from .generation.registry import OPERATION_REGISTRY
            from .generation.router import route_operation
            fact_status = _fact_status_map(facts)
            for index in candidate_indices:
                key = _rule_operation_key(rule, index)
                if key not in OPERATION_REGISTRY:
                    continue
                decision = route_operation(
                    key,
                    fact_status=fact_status,
                    structure=_route_structure(str(rule.get("rule_id") or ""), "", facts),
                )
                if decision.blocked:
                    raise RecallError("RECALL_FACT_UNVERIFIED", {
                        "rule": rule["rule_id"],
                        "operations": [key],
                        "fact_blocking": list(decision.fact_blocking),
                    })
        _route_target_operations(
            rule,
            [{**operation_list[index], "_operation_index": index}
             for index in candidate_indices],
            facts,
            "",
        )
    selected_indices = _selected_operation_indices(rule, target, inspection, facts,
                                                   obligations)
    applicable: list[dict] = []
    unknown: list[dict] = []
    for index, operation in enumerate(rule.get("operations") or []):
        status = condition_status(operation.get("condition"), facts)
        if status == "TRUE" and index in selected_indices:
            applicable.append(operation)
        elif status == "UNKNOWN":
            unknown.append(operation)
    if not applicable and unknown:
        raise RecallError("RECALL_FACT_UNVERIFIED", {
            "rule": rule["rule_id"],
            "kinds": sorted({str((operation.get("condition") or {}).get("kind"))
                             for operation in unknown}),
        })
    route_plan = _routing_for_target(rule, target, inspection, facts, obligations)
    setattr(target, "_route_plan", route_plan)
    edit = _plan_target_inner(rule, target, inspection, facts, gateway,
                              compose_budget=compose_budget, obligations=obligations,
                              routing=route_plan, approvals=approvals)
    if edit is not None:
        evidence = dict(edit.evidence or {})
        if rule.get("class_substitution") and not facts.service_group:
            evidence.setdefault("component_not_applicable", ["service_fee_group"])
        edit.evidence = evidence
    return _attach(edit)


def _plan_target_inner(rule: dict, target: Target, inspection: DocumentInspection, facts: Facts,
                       gateway: Any, *, compose_budget: list[int],
                       obligations: Any = None,
                       routing: dict[str, Any] | None = None,
                       approvals: Any = None) -> PlannedEdit | None:
    """Turn one needs_edit target into a concrete edit, or raise RecallError.

    Only the operations attributed to THIS target are eligible.  Re-scanning every
    operation of the rule was the source of sibling operations being silently carried
    by an unrelated target or dropped from the final edit set (plan §11).
    """
    rule_id = str(rule.get("rule_id") or "")
    selected_indices = _selected_operation_indices(rule, target, inspection, facts,
                                                   obligations)
    operations = [{**rule["operations"][index], "_operation_index": index} for index in selected_indices
                  if 0 <= index < len(rule.get("operations") or [])]

    def finish(edit: PlannedEdit) -> PlannedEdit:
        edit.operation_keys = tuple(_rule_operation_key(rule, index)
                                    for index in selected_indices)
        if obligations is not None:
            obligation_ids: list[str] = []
            for index in selected_indices:
                record = obligations.record(_rule_operation_key(rule, index))
                if record is not None and record.obligation_id not in obligation_ids:
                    obligation_ids.append(record.obligation_id)
            edit.obligation_ids = tuple(obligation_ids)
        evidence = dict(edit.evidence or {})
        evidence["operation_keys"] = list(edit.operation_keys)
        evidence["obligation_ids"] = list(edit.obligation_ids)
        active_routing = getattr(target, "_route_plan", None) or routing
        if active_routing is not None:
            evidence["strategy"] = [dict(item) for item in active_routing.get("decisions", ())]
            evidence["selected_executor"] = active_routing.get("executor")
            evidence["allow_compose_fallback"] = bool(
                active_routing.get("allow_compose_fallback"))
        edit.evidence = evidence
        if active_routing is not None and str(active_routing.get("executor")) != "legacy":
            before_span = inspection.by_location(edit.location).text
            after_span = (before_span[:edit.start] + edit.replacement +
                          before_span[edit.end:])
            _validate_routed_policy(
                rule, operations, facts, before_span, after_span,
                mode=("delete" if all(operation.get("op") == "delete"
                                      for operation in operations) else "replace"),
                check_output=True,
            )
        return edit

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
        #
        # Hard-fact gate (FL-D106): "the product lacks the class group the guide names"
        # is a semantic judgment, so it may not silently discard a target the model
        # reported. When the contract still mentions the rule's topic, keep the target and
        # plan what the operations can actually carry; only a provable topic absence is a
        # genuine not-applicable.
        if not hard_fact_topic_absent(
                rule, _compact("".join(display_text(span.text)[0]
                                       for span in inspection.paragraphs))):
            operations = _drop_empty_group_operations(rule, operations, facts) or operations
        else:
            raise RecallError("RECALL_RULE_NOT_APPLICABLE",
                              {"rule": rule["rule_id"],
                               "groups": sorted(_missing_slot_groups(rule, operations, facts))})
    if slot_group_missing(rule, operations, facts):
        operations = _drop_empty_group_operations(rule, operations, facts)
    selected_indices = [int(operation["_operation_index"]) for operation in operations]
    if not operations:
        # Every operation needed a class group this product does not have.
        raise RecallError("RECALL_RULE_NOT_APPLICABLE",
                          {"rule": rule["rule_id"], "groups": sorted(_missing_slot_groups(
                              rule, rule.get("operations") or [], facts))})
    if target.resolution != "resolved" or target.start is None or target.end is None:
        # Out-of-scope rules are decided above; a resolved-scope target that cannot bind
        # to the contract text is a genuine unresolved failure.
        raise RecallError("RECALL_TARGET_UNRESOLVED", {"target": target.target_id})
    rebind_split_append_targets([target], inspection)
    span = inspection.by_location(target.location)
    if (rule_id == "G08" and len(operations) == 1
            and _same_compact(target.quote, span.text[target.start:target.end])):
        expanded_start = _g08_fee_clause_start(span.text, target.start, target.end,
                                               operations[0], facts)
        if expanded_start != target.start:
            target.start = expanded_start
            target.quote = span.text[target.start:target.end]
            target.segment_ok = containing_segment(span, target.start, target.end) is not None
    if (rule_id == "G15" and len(operations) == 1
            and _g15_payment_delete_authorized(operations[0])
            and _same_compact(target.quote, span.text[target.start:target.end])):
        expanded_end = _bound_g15_payment_target(
            span.text, int(target.start), int(target.end))
        if expanded_end != target.end:
            target.end = expanded_end
            target.quote = span.text[target.start:target.end]
            target.segment_ok = containing_segment(span, target.start, target.end) is not None
    if rule_id in {"G02", "G04"} and not target_site_ok(rule_id, span, inspection):
        raise RecallError("RECALL_TARGET_SITE_MISMATCH", {
            "target": target.target_id, "rule": rule_id, "location": target.location})
    # A target quote/offset may include the paragraph's trailing space while the
    # DOCX text segment ends just before it.  That whitespace is not editable business
    # content; clamp it to the containing run instead of producing an edit that crosses
    # a read-only barrier (D11 p129).
    if target.start is not None and target.end is not None:
        segment = next((s for s in span.segments
                        if s.start <= target.start and target.end <= s.end), None)
        if segment is None:
            containing = next((s for s in span.segments
                               if s.start <= target.start < s.end), None)
            if containing is not None and not span.text[containing.end:target.end].strip():
                target.end = containing.end
    # A word-only inventory quote can omit the leading list delimiter that the
    # delete operation explicitly owns (G05's "、调低赎回费率"). Expand only to
    # the exact authorized literal containing the already bound source slice;
    # never send a partial literal through compose or delete adjacent content.
    if rule_id == "G05" and target_site_ok(rule_id, span, inspection):
        for operation in operations:
            old = str(operation.get("old_text") or "")
            if operation.get("op") != "delete" or not old.startswith("、"):
                continue
            if _compact(span.text[target.start:target.end]) != _compact(old[1:]):
                continue
            containing = [(start, end) for start, end in _compact_positions(span.text, old)
                          if start <= target.start and target.end <= end]
            if len(containing) == 1:
                target.start, target.end = containing[0]
                target.quote = span.text[target.start:target.end]
                target.reason = f"{target.reason}|BOUND_AUTHORIZED_DELETE_DELIMITER"
    if not containing_segment(span, target.start, target.end) and not (target.start == target.end):
        raise RecallError("RECALL_TARGET_STRUCTURE", {"target": target.target_id})
    rule_id = str(rule.get("rule_id") or "")
    if rule_id in {"G02", "G04"} and operations:
        # If the bound fee-group clause already contains every selected class group
        # (common `A类及D类` / `C类` wording), there is nothing to replace.  This is
        # also the only sound way to close a split class-definition paragraph whose
        # heading and fee-group wording live in adjacent DOCX paragraphs.
        from .generation.effects import _class_group_equivalent
        quote_body = _compact(target.quote) or _compact(span.text[target.start:target.end])
        if any(token in quote_body for token in ("申购费", "认购费", "销售服务费")):
            matched = 0
            for operation in operations:
                expected, issues = instantiate_slots(
                    str(operation.get("new_text") or ""), facts)
                if not issues and expected and _class_group_equivalent(expected, quote_body):
                    matched += 1
            if matched == len(operations):
                target.state = "satisfied"
                target.out_of_scope = False
                target.reason = f"{target.reason}|CLASS_GROUP_ALREADY_PRESENT"
                return None
    if rule_id in {"G02", "G04"}:
        # The inventory often quotes the whole A/C class-definition sentence.  Narrow the
        # edit to the one operation the target actually owns, and prove which identical
        # occurrence the inventory quote meant (G02/G04 same-paragraph class tokens).
        all_operations = rule.get("operations") or []
        candidate_indices: list[int] = list(selected_indices)
        if not candidate_indices:
            quote_compact = _compact(target.quote)
            candidate_indices = [
                index for index, operation in enumerate(all_operations)
                if _compact(str(operation.get("old_text") or ""))
                and _compact(str(operation.get("old_text") or "")) in quote_compact]
        candidate_indices = sorted(set(candidate_indices))
        if len(candidate_indices) == 1:
            operation_index = candidate_indices[0]
            selected_indices = [operation_index]
            operations = [{**all_operations[operation_index],
                           "_operation_index": operation_index}]
            old_text = str(all_operations[operation_index].get("old_text") or "")
            if old_text:
                narrowed = resolve_occurrence(span, old_text, anchor=target.quote)
                if narrowed is None:
                    raise RecallError(
                        "RECALL_TARGET_OCCURRENCE_AMBIGUOUS",
                        {"target": target.target_id, "occurrence": old_text[:80]})
                current = _compact(span.text[target.start:target.end])
                if current == _compact(old_text) and narrowed != (target.start, target.end):
                    # The target's bound offset and its own quote point to different
                    # identical tokens: do not guess which one the inventory meant.
                    raise RecallError(
                        "RECALL_TARGET_OCCURRENCE_AMBIGUOUS",
                        {"target": target.target_id, "occurrence": old_text[:80]})
                original_start, original_end = target.start, target.end
                if original_end > original_start and not (
                        original_start <= narrowed[0] and narrowed[1] <= original_end):
                    raise RecallError(
                        "RECALL_TARGET_OCCURRENCE_AMBIGUOUS",
                        {"target": target.target_id, "occurrence": old_text[:80]})
                target.start, target.end = narrowed
                if not containing_segment(span, target.start, target.end) and \
                        target.start != target.end:
                    raise RecallError("RECALL_TARGET_STRUCTURE",
                                      {"target": target.target_id})
                target.occurrence_index = _occurrence_index(
                    span.text, old_text, narrowed[0])
                target.occurrence_anchor = target.quote
    actual = span.text[target.start:target.end]
    # Routing is performed after source binding and operation narrowing.  This is
    # the execution contract for this target; the branches below may only use the
    # executor selected here.  In particular, a deterministic failure cannot
    # silently turn a DELETE or SPLICE operation into an unauthorized compose.
    # Direct callers of this low-level compatibility helper may not have gone
    # through the registry planner. Only an explicit route plan is authoritative
    # there; plan_target supplies it in registry mode after attribution.
    route_plan = routing or {"decisions": [], "executor": "legacy",
                              "allow_compose_fallback": True}
    target._route_plan = route_plan
    routed_executor = str(route_plan["executor"])
    if routed_executor != "legacy":
        # Fact dependencies are gated by the Router.  Component presence is checked
        # again on the actual output below, but the preflight must run before any
        # model compose request so an operation cannot ask the model to invent a
        # missing policy component.
        _validate_routed_policy(rule, operations, facts, actual, actual,
                                mode="delete" if all(operation.get("op") == "delete"
                                                     for operation in operations)
                                else "replace", check_output=False)
    if (rule_id == "G16" and target.state == "needs_edit"
            and len(operations) == 1 and operations[0].get("op") == "append"
            and target.start is not None and target.end is not None):
        expected, issues = instantiate_slots(str(operations[0].get("new_text") or ""), facts)
        target_body = _compact(str(target.quote) or "")
        if (not issues and expected and target_body
                and target_body in _compact(expected)):
            # The target owns only the final sentence of the G16 policy. Replace
            # that tail with the complete instantiated clause instead of appending
            # after it (which would duplicate the tail) or deleting the paragraph.
            return finish(PlannedEdit(
                target_id=target.target_id, rule_id=rule_id, location=target.location,
                start=target.start, end=target.end, replacement=expected,
                operation="replace", content_source="g16_partial_clause_replace",
                evidence={"fixed_text": expected,
                          "replaced_tail": target.quote,
                          "guide_paragraphs": rule.get("source_paragraphs") or []}))
    has_append = any(operation.get("op") == "append" for operation in operations)
    if has_append:
        if routed_executor == "delete" or routed_executor == "splice":
            raise RecallError("RECALL_ROUTED_EXECUTOR_UNAVAILABLE", {
                "target": target.target_id, "executor": routed_executor,
                "required": "template_or_compose", "rule": rule_id})
        # For an append, the append-site guard is authoritative: it accepts the
        # clause-end anchor G16 resolves to (FL-D159).  Other append rules still
        # keep the ordinary target-site guard as an additional check.
        site_ok = append_site_ok(rule_id, span, inspection)
        if site_ok and rule_id != "G16":
            site_ok = target_site_ok(rule_id, span, inspection)
    else:
        site_ok = target_site_ok(rule_id, span, inspection)
    if not site_ok and approvals is not None:
        # The source, operation identity, scope and guide identity were already
        # verified when the approval was created.  A different word list must not
        # reject the same target again (弘利 G17 "可用于", FL-D394/R01).
        check = approvals.allows(target, inspection)
        if check.ok:
            site_ok = True
            setattr(target, "_approval_check", {
                "approval_id": str(getattr(target, "approval_id", "") or ""),
                "ok": True, "code": ""})
    if not site_ok:
        raise RecallError("TARGET_SOURCE_MISMATCH",
                          {"rule": rule_id, "target": target.target_id,
                           "location": target.location})
    # These two source shapes are fully deterministic. Keep them before every
    # routed/compose branch so a zero compose budget cannot block a bounded edit.
    append_ops = [operation for operation in operations if operation.get("op") == "append"]
    delete_ops = [operation for operation in operations if operation.get("op") == "delete"]
    replace_ops = [operation for operation in operations if operation.get("op") == "replace"]
    noop_ops = [operation for operation in operations if operation.get("op") == "noop"]
    if rule_id == "G12" and len(operations) == 1 and len(replace_ops) == 1:
        # Survey inventory may bind only G12's bearer sentence.  The complete
        # authorized allocation sentence is still in this physical paragraph;
        # inspect the source suffix so a bounded replacement can consume it
        # without borrowing the following G13 short-holding sentence.
        allocation_source = span.text[target.start:]
        allocation_end = _g12_allocation_end(allocation_source, replace_ops[0])
        if allocation_end is not None:
            new_text = str(replace_ops[0].get("new_text") or "")
            return finish(PlannedEdit(
                target_id=target.target_id, rule_id=rule_id, location=target.location,
                start=target.start, end=target.start + allocation_end,
                replacement=new_text, operation="replace",
                content_source="bounded_replace",
                evidence={"strategy": "source_redemption_allocation",
                          "fixed_text": new_text}))
    if rule_id == "G06" and len(operations) == 1 and len(delete_ops) == 1:
        bounds = _g06_prohibition_bounds(span.text, target.start, target.end)
        if bounds is not None:
            left, right, sentence = bounds
            return finish(PlannedEdit(
                target_id=target.target_id, rule_id=rule_id, location=target.location,
                start=left, end=right, replacement="", operation="replace",
                content_source="g06_prohibition_delete",
                evidence={"deleted_quote": sentence}))
    if rule_id == "G13" and len(operations) == 1 and len(delete_ops) == 1:
        short_end = _g13_short_holding_end(actual, delete_ops[0])
        if short_end is None:
            short_end = _g13_short_holding_owned(
                inspection, target.location, actual, delete_ops[0])
        if short_end is not None:
            return finish(PlannedEdit(
                target_id=target.target_id, rule_id=rule_id, location=target.location,
                start=target.start, end=target.start + short_end,
                replacement="", operation="replace", content_source="short_holding_delete",
                evidence={"deleted_quote": actual[:short_end]}))
    if (len(operations) == 1 and len(delete_ops) == 1 and approvals is not None
            and str(getattr(target, "approval_id", "") or "")):
        # A delete whose wording differs from the guide example cannot be spliced
        # literally.  When the model already selected this exact source sentence and
        # code verified the quote, operation identity and scope, the program deletes
        # that approved span instead of asking a model to rewrite the clause (R07).
        check = approvals.allows(target, inspection)
        if check.ok and _approved_span_is_complete_clause(actual, target):
            start, end = _approved_delete_span(actual, int(target.start),
                                               int(target.end))
            if end > start:
                return finish(PlannedEdit(
                    target_id=target.target_id, rule_id=rule_id,
                    location=target.location, start=start, end=end, replacement="",
                    operation="replace", content_source="approved_span_delete",
                    evidence={"deleted_quote": actual[start:end],
                              "approval_id": target.approval_id,
                              "deletion_authority": "semantic_approval"}))
    if routed_executor in {"template", "splice"}:
        tier1 = _plan_tier1(rule, operations, facts, actual, routing=route_plan)
        if tier1 is not None:
            return finish(PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"],
                               location=target.location, start=target.start, end=target.end,
                               replacement=tier1.replacement, operation="replace",
                               content_source=tier1.content_source,
                               evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                         **tier1.evidence}))
    if noop_ops and not (append_ops or delete_ops or replace_ops):
        return None  # branch explicitly requires no change
    if append_ops:
        # Append sites are already source-bound by the locator and the guide text is
        # a fixed policy component.  G16 is routed to the compose executor because
        # preserving its existing payment mechanism is semantic; the actual append
        # still occurs through this compose-authorized branch.
        operation = append_ops[0]
        definition_end = (_definition_next_entry_start(span.text)
                          if rule_id in {"G01", "G03"} else None)
        if definition_end is not None and target.start < definition_end <= target.end:
            target.end = definition_end
            target.quote = span.text[target.start:target.end]
            target.segment_ok = containing_segment(span, target.start, target.end) is not None
        # A DOCX paragraph can end in the middle of a business sentence. Never
        # inject policy between its fragments (for example a definition continued
        # in the next paragraph). The locator must supply a complete clause site.
        if definition_end is None and rule_id in {"G01", "G03", "G16"} and target.end \
                and span.text[:target.end].rstrip(" \t\n\r\"”’）)")[-1:] not in "。！？；;":
            suffix = re.search(r"[。！？；;]", span.text[target.end:])
            if suffix is None:
                tail = span.text[:target.end].rstrip(" \t\n\r\"”’）)")
                if (tail and tail[-1] not in "的和与及、，,（(：:"
                        and not re.search(r"[A-ZＡ-Ｚ]$", tail)):
                    # The paragraph holds a complete clause but simply omits the final
                    # full stop (D02 p93 "...称为 C 类基金份额 ").  Append at its end;
                    # append_separator supplies the missing stop.
                    target.end = len(tail)
                else:
                    # A split definition ends the heading in this paragraph and puts
                    # the rest of the sentence in the next one.  Move the append site
                    # to that continuation only when the previous paragraph has the
                    # rule anchor and no sentence terminator.
                    locations = [item.location for item in inspection.paragraphs]
                    try:
                        index = locations.index(span.location)
                    except ValueError:
                        index = -1
                    next_span = (inspection.paragraphs[index + 1]
                                 if 0 <= index < len(inspection.paragraphs) - 1 else None)
                    if next_span is None or not append_site_ok(rule_id, next_span, inspection):
                        raise RecallError("RECALL_APPEND_CLAUSE_INCOMPLETE",
                                          {"rule": rule_id, "target": target.target_id})
                    span = next_span
                    target.location = str(span.location)
                    target.quote = str(span.text)
                    target.start, target.end = 0, len(str(span.text))
                    suffix = re.search(r"[。！？；;]", span.text[target.end:])
                    if suffix is not None:
                        target.end += suffix.end()
                    actual = span.text[target.start:target.end]
            else:
                target.end += suffix.end()
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
        if routed_executor == "compose" and rule_id != "G16":
            if gateway is None:
                raise RecallError("RECALL_COMPOSE_GATEWAY_MISSING", {"rule": rule_id})
            if compose_budget[0] <= 0:
                raise RecallError("RECALL_COMPOSE_BUDGET_EXHAUSTED", {
                    "target": target.target_id})
            compose_budget[0] -= 1
            composed = compose_variant(span, target, rule, actual, new_text, facts, gateway,
                                       mode="replace", variants=())
            return finish(PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"],
                               location=target.location, start=target.start, end=target.end,
                               replacement=composed["replacement"], operation="replace",
                               content_source="composed",
                               evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                         "slots": list(rule.get("slot_tokens") or []),
                                         "fixed_text": new_text,
                                         "preserved": composed["preserved"],
                                         "basis": composed["basis"], "issues": issues}))
        # G16's Router route is COMPOSE because the operation's policy contract
        # includes preservation requirements. Its fixed append is nevertheless a
        # complete compose executor: the source clause is preserved byte-for-byte
        # and only the guide-authorized component is inserted. No model wording is
        # needed for this append path, which also keeps fixed policy text intact.
        prefix = append_separator(span.text[:target.end], new_text)
        return finish(PlannedEdit(target_id=target.target_id, rule_id=rule["rule_id"],
                           location=target.location, start=target.end, end=target.end,
                           replacement=prefix + new_text, operation="insert",
                           content_source="tier1_template",
                           evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                                     "slots": list(rule.get("slot_tokens") or []),
                                     "fixed_text": new_text,
                                     "join_separator": prefix,
                                     "issues": issues}))
    # Several operations of one rule can apply to the SAME span: G05 both replaces
    # "调低赎回费率" with "调低销售服务费率" and deletes "并报中国证监会备案" inside one
    # sentence. Applying only the first match silently dropped the replacement (FL-D052),
    # so every deterministic fragment operation is accumulated onto one replacement.
    spliced = actual
    applied: list[str] = []
    fragments: list[dict[str, str]] = []
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
            fragments.append({"op": str(op_kind), "old_text": old_text,
                              "new_text": new_fragment, "mode": "full"})
            continue
        updated = None
        if op_kind == "replace" and rule_id == "G05" \
                and _compact(old_text) == "调低赎回费率":
            g05 = plan_g05_splice(spliced)
            if g05 is not None:
                updated, g05_evidence = g05
                fragments.append({"op": str(op_kind), "old_text": old_text,
                                  "new_text": new_fragment, "mode": "g05_splice",
                                  "evidence": g05_evidence})
                applied.append(f"{op_kind}:g05_splice")
        if updated is None:
            updated = _splice_fragment(spliced, old_text, new_fragment)
        if updated is not None:
            spliced = updated
            if op_kind == "delete":
                spliced = _normalise_local_punctuation(spliced)
            if not any(item.endswith(f"{op_kind}:g05_splice") for item in applied):
                applied.append(f"{op_kind}:fragment")
                fragments.append({"op": str(op_kind), "old_text": old_text,
                                  "new_text": new_fragment, "mode": "fragment"})
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
                                     "applied": applied, "fragments": fragments})
    # A delete-only rule whose reference text runs across several sentences or
    # paragraphs (G17 concatenates "…基金份额持有人服务费等。" with "…不包括基金募集期间
    # 的上述费用。"): one target carries one sentence of it verbatim and nothing else.
    # The reference can never match that single-sentence span, so the composer is asked to
    # trim a span it can only leave unchanged and fails with DELETE_NOT_SHRINKING. When the
    # target span is exactly the target quote and that quote is a genuine part of the
    # rule's delete reference, the whole span is the material to remove (FL-D052).
    if delete_ops and not replace_ops and not append_ops:
        quote_compact = _compact(target.quote)
        if (rule_id == "G17" and len(delete_ops) == 1
                and quote_compact == _compact(actual)
                and _g17_usage_exclusion_matches(actual,
                    [str(delete_ops[0].get("old_text") or "")])):
            return finish(PlannedEdit(
                target_id=target.target_id, rule_id=rule_id, location=target.location,
                start=target.start, end=target.end, replacement="", operation="replace",
                content_source="variant_delete",
                evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                          "deleted_quote": target.quote}))
        # The purpose sentence ("销售服务费主要用于支付销售机构佣金…服务费等。")
        # is one complete operation-owned sentence of G17's two-sentence reference.
        # The class lead ("C类基金份额的") is absent from the contract, so the
        # substring test below rejects the span and the composer fails with
        # DELETE_NOT_SHRINKING; the residual then survives (生物科技 p940, 美国房地产
        # p721, 道琼斯 p902).  Delete only when the target span is exactly one
        # complete source sentence owned by this operation.
        if (rule_id == "G17" and len(delete_ops) == 1
                and quote_compact == _compact(actual)
                and _g17_target_is_owned_sentence(inspection, target, delete_ops)):
            return finish(PlannedEdit(
                target_id=target.target_id, rule_id=rule_id, location=target.location,
                start=target.start, end=target.end, replacement="", operation="replace",
                content_source="variant_delete",
                evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                          "deleted_quote": target.quote}))
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
        # Survey fuzzy windows can stop just before the source sentence ends.
        # Matching that already-truncated window again cannot see the remaining
        # characters, so a whole-sentence policy would leave a dangling tail.
        # Rebind only a proved near-identical clause in the SAME paragraph, with
        # the same start and a bounded sentence terminator; otherwise fail closed.
        if (_compact(old_text).endswith(tuple("。！？；"))
                and actual[:end_raw].rstrip()[-1:] not in "。！？；"):
            bound = fuzzy_span_clause(span.text, old_text, threshold=VARIANT_MATCH_RATIO)
            if (bound is None or bound[0] != target.start + start_raw
                    or bound[1] < target.end or bound[1] - target.end > 12
                    or span.text[bound[1] - 1:bound[1]] not in "。！？；"
                    or not containing_segment(span, target.start, bound[1])):
                raise RecallError("RECALL_VARIANT_CLAUSE_INCOMPLETE", {"target": target.target_id})
            target.end = bound[1]
            actual = span.text[target.start:target.end]
            end_raw = len(actual)
            ratio = bound[2]
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
    # This existing whole-paragraph deterministic path consumes no compose call.
    # Run it before checking/decrementing the compose budget, so a zero budget
    # does not prevent a proven delete or charge it as a model request.
    if delete_ops and not replace_ops and _tier1_enabled() and target.quote:
        bag = _delete_keyword_bag(rule, facts)
        if (bag and _same_compact(target.quote, actual) and _same_compact(actual, span.text)
                and _keyword_bag_in_clause(_compact(actual), bag)):
            return finish(PlannedEdit(
                target_id=target.target_id, rule_id=rule["rule_id"],
                location=target.location, start=target.start, end=target.end,
                replacement="", operation="replace", content_source="tier1_delete",
                evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                          "strategy": "tier1_delete_pre_route",
                          "deleted_paragraph": _clip(target.quote, 120)}))
    if (rule_id == "G15" and len(operations) == 1 and len(delete_ops) == 1
            and _g15_payment_delete_authorized(delete_ops[0])
            and target.quote and _same_compact(target.quote, actual)
            and "按月支付" in _compact(actual)
            and re.search(r"支付(?:日期|时间)(?:相应)?顺延[。！？；!?;]$", _compact(actual))
            and _g15_payment_clause_end(actual, 0, len(actual)) == len(actual)):
        return finish(PlannedEdit(
            target_id=target.target_id, rule_id=rule["rule_id"],
            location=target.location, start=target.start, end=target.end,
            replacement="", operation="replace", content_source="bounded_delete",
            evidence={"guide_paragraphs": rule.get("source_paragraphs") or [],
                      "strategy": "g15_payment_clause_delete",
                      "deleted_clause": _clip(target.quote, 160)}))
    if (rule_id == "G15" and len(operations) == 1
            and _g15_delay_continuation(inspection, target.location, operations[0]) ==
                (target.start, target.end)
            and _same_compact(target.quote, actual)):
        return finish(PlannedEdit(
            target_id=target.target_id, rule_id=rule_id, location=target.location,
            start=target.start, end=target.end, replacement="", operation="replace",
            content_source="g15_delay_delete",
            evidence={"strategy": "source_payment_delay_continuation"}))
    if routing is not None and routed_executor not in {"compose", "legacy"}:
        # Preserve the stable bounded-budget failure for a deterministic route that
        # cannot safely execute when no compose request is available.  This is still
        # fail-closed: the budget error must not be treated as authorization for
        # compose, and a positive budget reaches the executor-availability check below.
        if compose_budget[0] <= 0:
            raise RecallError("RECALL_COMPOSE_BUDGET_EXHAUSTED", {"target": target.target_id})
        if not route_plan.get("allow_compose_fallback"):
            # A code-verified approval already binds this operation to this source
            # span and scope.  When the deterministic executor cannot express the
            # variant, a bounded compose under independent verification is the
            # authorized fallback; without an approval the run still fails closed
            # (R07).  Deletes prefer approved_span_delete above and only reach here
            # when the approved span is not a complete clause.
            if approvals is None or not approvals.allows(target, inspection).ok:
                raise RecallError("RECALL_ROUTED_EXECUTOR_UNAVAILABLE", {
                    "target": target.target_id, "executor": routed_executor,
                    "required": "compose", "rule": rule_id})
            setattr(target, "_approval_check", {
                "approval_id": str(getattr(target, "approval_id", "") or ""),
                "ok": True, "code": "", "escalation": "approved_compose_fallback"})
        # A deterministic executor was selected but could not produce a safe
        # bounded edit.  Record the structural escalation before composing so the
        # selected executor evidence describes the code path that actually ran.
        route_plan = _routing_for_compose(route_plan)
        target._route_plan = route_plan
        routed_executor = "compose"
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


def _verify_composed(rule: dict, target: Target, actual: str, replacement: str,
                     fixed_text: str, facts: Facts, gateway: Any, *,
                     mode: str) -> tuple[bool, str]:
    """Three-layer validation for composed edits (plan v4 §11–§13, §27).

    Program checks (V1/V2-B) always run when the strategy flag is on. The V3
    model critic runs **whenever the composed path is reached**: entering
    ``compose_variant`` already means the deterministic tiers could not carry
    the edit (actual tier = COMPOSE), regardless of the rule's default tier
    (external review 2026-10-19, P0-2). Returns ``(ok, reason)``.
    """
    from .generation.validators import Authorization, run_validation

    op_removals = [str(operation.get("old_text") or "")
                   for operation in (rule.get("operations") or [])]
    op_removals += [str(variant) for variant in (rule.get("old_text_variants") or [])]
    auth = Authorization(
        must_add=tuple(part for part in re.split(r"(?<=[。；])", fixed_text or "")
                       if len(_compact(part)) >= 6),
        remove_patterns=tuple(text for text in op_removals if text),
        removals_authorized=(mode == "delete"))
    if rule.get("rule_id") == "G12" and mode == "replace":
        indices = _normalise_operation_ids(rule, target.operations)
        if len(indices) == 1:
            operation = rule["operations"][indices[0]]
            if _g12_source_effect_owned(actual, replacement, operation):
                end = _g12_allocation_end(actual, operation)
                auth = replace(auth, remove_patterns=(*auth.remove_patterns, actual[:end]))
    validation = run_validation(actual, replacement, auth=auth)
    if validation.verdict == "FAIL":
        codes = sorted({finding.code for finding in validation.findings})
        hard = [record.reason for record in validation.changes
                if record.explanation == "UNEXPLAINED_HARD"]
        return False, "program_check:" + ",".join(codes or hard or ["UNEXPLAINED_CHANGE"])

    context = "\n\n".join([
        f"BEFORE\n{_clip(actual, 1200)}",
        f"AFTER\n{_clip(replacement, 1600)}",
        "GUIDE_OPERATION\n" + json.dumps(
            {"rule_id": rule.get("rule_id"), "requirement": _clip(str(rule.get("requirement") or ""), 600),
             "fixed_policy_text": _clip(fixed_text or "", 600)}, ensure_ascii=False),
        "FACTS\n" + json.dumps(facts.as_ledger(), ensure_ascii=False)[:900],
    ])
    if len(context) > gateway.max_context_chars:
        return False, "verify_context_limit"
    result = gateway.call(task_type="recall_verify", bounded_context=context,
                          response_schema=VERIFY_SCHEMA, instruction=VERIFY_INSTRUCTION,
                          prompt_version=VERIFY_PROMPT_VERSION)
    value = result.value if isinstance(result.value, dict) else {}
    if str(value.get("verdict") or "") == "pass":
        return True, "v3_pass"
    return False, "v3_fail:" + _clip(str(value.get("reason") or ""), 120)


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
    attempts = 2 if mode == "delete" or _tier1_enabled() else 1
    last_error: RecallError | None = None
    for attempt in range(attempts):
        context = base_context
        if attempt:
            if mode == "delete":
                note = ("上一次回答没有删减目标文本。请删除指引要求删除的内容，只保留"
                        "指引不要求删除的部分；整句删除时 replacement 必须为空字符串。")
            else:
                note = ("上一次回答没有通过独立复核（{code}）。请重新给出替换文本：完整落实指引政策、"
                        "保留未授权内容、不得新增未授权内容或数字。").format(
                            code=last_error.code if last_error else "-")
            context = base_context + "\n\n[RETRY_NOTE]\n" + note
        if len(context) > gateway.max_context_chars:
            raise RecallError("RECALL_COMPOSE_CONTEXT_LIMIT", {"target": target.target_id})
        result = gateway.call(task_type="recall_compose", bounded_context=context,
                              response_schema=COMPOSE_SCHEMA, instruction=instruction,
                              prompt_version=COMPOSE_PROMPT_VERSION)
        # Each attempt validates only the candidate it just produced.  The retry
        # note above may quote the previous error, but carrying that error into
        # this attempt's checks rejected a correct second answer (FL-D442).
        last_error = None
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
            if new_digits and not _tier1_enabled():
                last_error = RecallError("RECALL_COMPOSE_NEW_NUMBERS",
                                         {"target": target.target_id,
                                          "numbers": sorted(new_digits)[:6]})
            if last_error is None:
                verified, reason = _verify_composed(rule, target, actual, replacement,
                                                    fixed_text, facts, gateway, mode=mode)
                if not verified:
                    last_error = RecallError("RECALL_COMPOSE_UNVERIFIED",
                                             {"target": target.target_id, "reason": reason})
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
            if not _tier1_enabled():
                raise RecallError("RECALL_COMPOSE_NEW_NUMBERS",
                                  {"target": target.target_id, "numbers": sorted(new_digits)[:6]})
            # Flag on: number provenance moves to the V1 validator inside
            # ``_verify_composed`` (plan §27: upgrade, not simply remove).
        verified, reason = _verify_composed(rule, target, actual, replacement,
                                            fixed_text, facts, gateway, mode="replace")
        if not verified:
            last_error = RecallError("RECALL_COMPOSE_UNVERIFIED",
                                     {"target": target.target_id, "reason": reason})
            if attempt + 1 >= attempts:
                raise last_error
            continue
        return {"replacement": replacement, "preserved": verified_preserved,
                "preserved_unverified": unverified_preserved, "basis": basis}
    raise last_error or RecallError("RECALL_COMPOSE_EMPTY", {"target": target.target_id})


def span_slice(inspection: DocumentInspection, location: str, start: int, end: int) -> str:
    try:
        span = inspection.by_location(location)
    except Exception:  # noqa: BLE001
        return ""
    return str(span.text)[int(start):int(end)]


def _component(edit: PlannedEdit, inspection: DocumentInspection) -> dict[str, Any]:
    span = inspection.by_location(edit.location)
    return {
        "target_id": edit.target_id, "rule_id": edit.rule_id, "location": edit.location,
        "start": edit.start, "end": edit.end, "replacement": edit.replacement,
        "operation": edit.operation, "content_source": edit.content_source,
        "evidence": edit.evidence,
        "operation_keys": list(edit.operation_keys),
        "obligation_ids": list(edit.obligation_ids),
        "expected_old_text": span.text[edit.start:edit.end],
    }


def _atomic_paragraph_edits(planned: Sequence[PlannedEdit], inspection: DocumentInspection,
                            obligations: Any = None
                            ) -> list[PlannedEdit]:
    from .generation.atomic import compose_paragraph
    by_location: dict[str, list[PlannedEdit]] = {}
    for edit in planned:
        by_location.setdefault(edit.location, []).append(edit)
    result: list[PlannedEdit] = []
    for location, entries in by_location.items():
        # Composed changes require their own joint semantic review. Deterministic
        # candidates can combine without another model request.
        if len(entries) < 2 or any("compose" in edit.content_source for edit in entries):
            result.extend(entries)
            continue
        if any(max(left.start, right.start) < min(left.end, right.end)
               and _operations_are_alternatives(left, right, obligations)
               for index, left in enumerate(entries) for right in entries[index + 1:]):
            # Historical wording alternatives represent one effect. Let the
            # existing explicit ONE_OF merge choose the containing variant before
            # any paragraph composition can apply the same policy twice.
            result.extend(entries)
            continue
        paragraph = inspection.by_location(location).text
        components = [_component(edit, inspection) for edit in entries]
        replacement = compose_paragraph(paragraph, components)
        if replacement is None:
            result.extend(entries)
            continue
        result.append(PlannedEdit(
            target_id="+".join(edit.target_id for edit in entries),
            rule_id="+".join(dict.fromkeys(edit.rule_id for edit in entries)),
            location=location, start=0, end=len(paragraph), replacement=replacement,
            operation="replace", content_source="atomic_paragraph",
            evidence={"atomic_components": components},
            operation_keys=tuple(dict.fromkeys(key for edit in entries for key in edit.operation_keys)),
            obligation_ids=tuple(dict.fromkeys(key for edit in entries for key in edit.obligation_ids))))
    return result


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


def _operations_are_alternatives(left: PlannedEdit, right: PlannedEdit,
                                 obligations: Any = None) -> bool:
    """Only a declared ONE_OF group may treat two operations as alternatives.

    Sharing a rule id is NOT alternative semantics: G05:0 (replace the redemption-fee
    wording) and G05:2 (delete the filing sentence) are independent obligations that can
    both be applicable at the same location.  The old same-rule shortcut silently dropped
    one of them (plan §15–§19).
    """
    if obligations is None:
        return False
    left_groups: set[str] = set()
    right_groups: set[str] = set()
    for edit, groups in ((left, left_groups), (right, right_groups)):
        keys = edit.operation_keys or ()
        if not keys:
            return False
        for key in keys:
            record = obligations.record(str(key))
            if record is None or not record.spec.one_of_group:
                return False
            groups.add(record.spec.one_of_group)
    return bool(left_groups & right_groups)


def _edit_operation_keys(left: PlannedEdit, right: PlannedEdit) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*left.operation_keys, *right.operation_keys)))


def _edit_obligation_ids(left: PlannedEdit, right: PlannedEdit) -> tuple[str, ...]:
    return tuple(dict.fromkeys((*left.obligation_ids, *right.obligation_ids)))


def _component_target_ids(edit: PlannedEdit, components: Sequence[dict[str, Any]] | None = None
                          ) -> set[str]:
    """Expand a synthetic merged target id (``T005+T002``) into its real components."""
    values: set[str] = set()
    for raw in (edit.target_id,):
        for part in str(raw or "").split("+"):
            if part:
                values.add(part)
    for component in components or ():
        for part in str(component.get("target_id") or "").split("+"):
            if part:
                values.add(part)
    return values


def merge_edits(edits: Sequence[PlannedEdit], inspection: DocumentInspection,
                obligations: Any = None
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
            item_component = _component(item, inspection)
            if item.start == current.end:
                # Adjacent declared alternatives are still ONE effect.  Concatenating
                # both replacements would write the same policy sentence twice (D06
                # G12 p230: G12:0 and G12:1 are historical wording alternatives).
                # Keep the variant that carries the other's effect and mark the other
                # covered; different non-empty policies fail closed instead of being
                # silently applied twice.
                if (_operations_are_alternatives(current, item, obligations)
                        and current.replacement.strip() and item.replacement.strip()):
                    if _compact(item.replacement) in _compact(current.replacement):
                        covered.append(item.target_id)
                        continue
                    if _compact(current.replacement) in _compact(item.replacement):
                        covered.append(current.target_id)
                        current = item
                        current_components = [item_component]
                        continue
                    conflicts.append({"code": "RECALL_EDIT_OVERLAP", "location": location,
                                      "targets": [current.target_id, item.target_id],
                                      "spans": [[current.start, current.end],
                                                [item.start, item.end]],
                                      "reason": "ONE_OF_ALTERNATIVES_DIFFER"})
                    merged.append((current, current_components))
                    current = item
                    current_components = [item_component]
                    continue
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
                    operation_keys=_edit_operation_keys(current, item),
                    obligation_ids=_edit_obligation_ids(current, item),
                )
                continue
            # An append point inside a sibling deletion is the common G15 (delete old
            # payment clause) + G16 (append new mechanism) case.  The append is not an
            # overlap: after the deletion it is exactly the content that remains.
            if (item.start == item.end and item.operation == "insert"
                    and current.start <= item.start <= current.end):
                inserted = str((item.evidence or {}).get("fixed_text") or "")
                if not inserted:
                    inserted = item.replacement
                if not current.replacement.strip():
                    combined_replacement = inserted
                elif item.start == current.end:
                    combined_replacement = current.replacement + inserted
                else:
                    combined_replacement = None
                if combined_replacement is not None:
                    current_components = current_components + [item_component]
                    current = PlannedEdit(
                        target_id=current.target_id + "+" + item.target_id,
                        rule_id=current.rule_id + "+" + item.rule_id,
                        location=location, start=current.start, end=current.end,
                        replacement=combined_replacement, operation="replace",
                        content_source="merged_delete_append",
                        evidence={"merged": [current.evidence, item.evidence],
                                  "append_inside_delete": True},
                        operation_keys=_edit_operation_keys(current, item),
                        obligation_ids=_edit_obligation_ids(current, item),
                    )
                    continue
            # A validated replacement can deterministically carry a contained
            # deletion when the replacement text no longer contains the deleted
            # source slice (D16 G12/G13: the G12 replacement already omits the
            # 7-day/1.5% sentence).  This is not a conflict needing another model
            # composition; combine the operation identities on the replacement.
            if (current.replacement.strip() and not item.replacement.strip()
                    and current.operation_keys and item.operation_keys
                    and set(current.operation_keys) != set(item.operation_keys)
                    and item.start >= current.start and item.end <= current.end):
                deleted_slice = span_slice(inspection, location, item.start, item.end)
                if deleted_slice and _compact(deleted_slice) not in _compact(current.replacement):
                    current_components = current_components + [item_component]
                    current = PlannedEdit(
                        target_id=current.target_id + "+" + item.target_id,
                        rule_id=current.rule_id + "+" + item.rule_id,
                        location=location, start=current.start, end=current.end,
                        replacement=current.replacement, operation="replace",
                        content_source="replace_covers_delete",
                        evidence={"merged": [current.evidence, item.evidence],
                                  "covered_delete": True},
                        operation_keys=_edit_operation_keys(current, item),
                        obligation_ids=_edit_obligation_ids(current, item),
                    )
                    covered.append(item.target_id)
                    continue
            # Same operation, same effect: a composite target and a residual
            # target can describe the same deletion twice (D01/D16 G17).  This is
            # not a business conflict.  Keep the maximal span and mark the subset
            # covered; it carries no independent authorization.
            if current.operation_keys and set(current.operation_keys) == set(item.operation_keys) \
                    and _compact(current.replacement) == _compact(item.replacement):
                if item.start >= current.start and item.end <= current.end:
                    covered.append(item.target_id)
                    continue
                if current.start >= item.start and current.end <= item.end:
                    covered.append(current.target_id)
                    current = item
                    current_components = [item_component]
                    continue
            alternative = _operations_are_alternatives(current, item, obligations)
            if item.start >= current.start and item.end <= current.end:
                # A contained edit may only be absorbed by a declared ONE_OF sibling
                # whose replacement really carries it.  Same-rule independent operations
                # must flow to Joint Compose instead of being dropped as "covered".
                if alternative and (_component_covered(item_component, current.replacement)
                                    or _compact(item.replacement) == _compact(current.replacement)):
                    covered.append(item.target_id)
                    continue
            current_component = _component(current, inspection)
            if current.start >= item.start and current.end <= item.end:
                if alternative and (_component_covered(current_component, item.replacement)
                                    or _compact(current.replacement) == _compact(item.replacement)):
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


_G15_TERM = re.compile(r"(?:\d+|[一二三四五六七八九十]+)\s*个?工作日")

_G15_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
                   "七": 7, "八": 8, "九": 9}


def _g15_normalise_term(term: str) -> str:
    raw = re.sub(r"\s+", "", term).removesuffix("工作日").removesuffix("个")
    if raw.isdigit():
        return f"{int(raw)}个工作日"
    if raw == "十":
        return "10个工作日"
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = _G15_CN_DIGITS.get(left, 1) if left else 1
        units = _G15_CN_DIGITS.get(right, 0) if right else 0
        return f"{tens * 10 + units}个工作日"
    if raw in _G15_CN_DIGITS:
        return f"{_G15_CN_DIGITS[raw]}个工作日"
    return term
#: Subject mentions mapped to families, so "注册登记机构" and "登记机构" compare equal.
_G15_SUBJECT_FAMILIES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("基金管理人", re.compile(r"基金管理人|管理人")),
    ("基金托管人", re.compile(r"基金托管人|托管人")),
    ("登记机构", re.compile(r"注册登记机构|登记机构|登记结算机构")),
    ("销售机构", re.compile(r"销售机构")),
)
#: Payment-path mentions that are only flagged when the guide reference lacks them.
_G15_PATHS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("划付指令", re.compile(r"划付指令|划拨指令|划款指令")),
    ("自动支付/扣划", re.compile(r"自动.{0,6}(支付|扣划|划)")),
    ("一次性支付", re.compile(r"一次性(支付|划出|划付|划款)")),
    ("代收/代付", re.compile(r"代收|代付")),
    ("指定账户路径", re.compile(r"指定的?账户路径|指定账户")),
    ("无需出具指令", re.compile(r"无需.{0,8}出具.{0,8}指令|无需再出具")),
)


def g15_contract_deviation(reference_texts: Sequence[str], deleted_text: str) -> list[str]:
    """Substantive elements where a deleted G15 clause differs from the guide reference.

    The clause is deleted either way; the difference is reported to the reviewer as
    "the original contract may be in error" (user ruling 2026-10-19). Comparisons are
    deliberately narrow — payment deadline, payment subject, payment path — so ordinary
    wording variants produce no notice.
    """
    reference = _compact("".join(reference_texts))
    deleted = _compact(deleted_text or "")
    if not reference or not deleted:
        return []
    reasons: list[str] = []
    reference_terms = sorted({_g15_normalise_term(term)
                              for term in _G15_TERM.findall(reference)})
    deleted_terms = sorted({_g15_normalise_term(term)
                            for term in _G15_TERM.findall(deleted)})
    if deleted_terms and reference_terms and deleted_terms != reference_terms:
        reasons.append("支付时限与指引参照不同（合同 " + "、".join(deleted_terms) +
                       "；指引 " + "、".join(reference_terms) + "）")
    for label, pattern in _G15_SUBJECT_FAMILIES:
        if pattern.search(deleted) and not pattern.search(reference):
            reasons.append(f"支付主体出现“{label}”（指引参照未涉及）")
    for label, pattern in _G15_PATHS:
        if pattern.search(deleted) and not pattern.search(reference):
            reasons.append(f"支付路径/方式出现“{label}”（指引参照未涉及）")
    return reasons


def _g15_notice_for_edit(edit: "PlannedEdit", rule: dict,
                         inspection: DocumentInspection) -> list[dict[str, Any]]:
    """Business notice for a G15 deletion whose clause deviates from the guide."""
    if "G15" not in str(edit.rule_id).split("+"):
        return []
    try:
        span = inspection.by_location(edit.location)
    except Exception:
        return []
    deleted = span.text[edit.start:edit.end]
    if not deleted.strip():
        return []
    references = [str(operation.get("old_text") or "")
                  for operation in (rule.get("operations") or [])]
    references += [str(variant) for variant in (rule.get("old_text_variants") or [])]
    reasons = g15_contract_deviation(references, deleted)
    if not reasons:
        return []
    return [{
        "code": "CONTRACT_POSSIBLY_ERRONEOUS",
        "severity": "warning",
        "affects_completion": False,
        "message": "原合同可能有误：" + "；".join(reasons),
        "reasons": reasons,
    }]


def _coalesce_overlap_conflicts(conflicts: Sequence[dict[str, Any]],
                                planned: Sequence[PlannedEdit]) -> list[dict[str, Any]]:
    """Coalesce pairwise overlap findings into connected edit components.

    Pairwise conflict reporting can produce A-B and B-C for three edits whose
    affected source is one connected interval.  Joint Compose must see A/B/C in
    one call; resolving the pairs independently consumes B on the first pair and
    leaves the second pair unresolved.
    """
    by_target: dict[str, list[PlannedEdit]] = {}
    for edit in planned:
        by_target.setdefault(edit.target_id, []).append(edit)
    groups: list[dict[str, Any]] = []
    for conflict in conflicts:
        location = str(conflict.get("location") or "")
        edits: list[PlannedEdit] = []
        for raw_target in conflict.get("targets") or ():
            for target_id in str(raw_target).split("+"):
                candidates = by_target.get(target_id, [])
                edit = next((candidate for candidate in candidates
                             if candidate.location == location), None)
                if edit is not None and edit not in edits:
                    edits.append(edit)
        if len(edits) < 2:
            groups.append(dict(conflict))
            continue
        edit_ids = {id(edit) for edit in edits}
        # Existing groups are disjoint. A new edge can bridge several of them;
        # combine all matches now so the invariant holds for the next edge.
        matching = [index for index, group in enumerate(groups)
                    if group.get("location") == location
                    and edit_ids & set(group.get("_edit_ids") or ())]
        group = {**conflict, "_edit_ids": edit_ids,
                 "targets": list(conflict.get("targets") or ()),
                 "spans": list(conflict.get("spans") or ())}
        for index in matching:
            previous = groups[index]
            group["_edit_ids"].update(previous["_edit_ids"])
            group["targets"].extend(previous.get("targets") or ())
            group["spans"].extend(previous.get("spans") or ())
        group["targets"] = list(dict.fromkeys(group["targets"]))
        for index in reversed(matching):
            del groups[index]
        groups.insert(matching[0] if matching else len(groups), group)
    for group in groups:
        group.pop("_edit_ids", None)
    return groups


def _resolve_overlaps_with_joint_compose(
        conflicts: Sequence[dict[str, Any]], planned: Sequence[PlannedEdit],
        inspection: DocumentInspection, rules_by_id: dict[str, dict], facts: Facts,
        gateway: Any, *, obligations: Any = None
        ) -> tuple[list[PlannedEdit], list[dict[str, Any]]]:
    """Try Joint Compose for real overlaps; unprovable overlaps stay conflicts."""
    from .generation.joint import plan_joint_compose

    by_target: dict[str, list[PlannedEdit]] = {}
    for edit in planned:
        by_target.setdefault(edit.target_id, []).append(edit)
    resolved: list[PlannedEdit] = []
    remaining: list[dict[str, Any]] = []
    # A composite target produces one edit per paragraph with the same target id.
    # Consume the specific conflicting edit, not every sibling part (D16 G13 p221/p222).
    consumed: set[int] = set()
    for conflict in _coalesce_overlap_conflicts(conflicts, planned):
        target_ids = [str(value) for value in conflict.get("targets") or []]
        location = str(conflict.get("location") or "")
        edits: list[PlannedEdit] = []
        for target_id in target_ids:
            for part in target_id.split("+"):
                candidates = by_target.get(part, [])
                edit = next((candidate for candidate in candidates
                             if candidate.location == location), None)
                if edit is None and candidates:
                    edit = candidates[0]
                if edit is not None and edit not in edits:
                    edits.append(edit)
        if len(edits) < 2 or any(id(edit) in consumed for edit in edits):
            remaining.append(conflict)
            continue
        if any(edit.location != location for edit in edits):
            remaining.append(conflict)
            continue
        span = inspection.by_location(location)
        start = min(int(edit.start) for edit in edits)
        end = max(int(edit.end) for edit in edits)
        # Two composite operations can both reduce the same tail paragraph to an
        # empty slice (D16 G12/G13 p222).  A joint *delete* is the correct merge;
        # asking Joint Compose to regenerate the clause would insert the G12 policy
        # a second time because the replace was already applied to p221.
        if all(not str(edit.replacement or "").strip() for edit in edits):
            consumed.update(id(edit) for edit in edits)
            resolved.append(PlannedEdit(
                target_id="+".join(dict.fromkeys(edit.target_id for edit in edits)),
                rule_id="+".join(dict.fromkeys(
                    rule_id.strip() for edit in edits
                    for rule_id in str(edit.rule_id).split("+") if rule_id.strip())),
                location=location, start=start, end=end, replacement="",
                operation="replace", content_source="joint_delete",
                evidence={"joint_delete": True, "composite_tail": True,
                          "operation_keys": [key for edit in edits
                                             for key in (edit.operation_keys or ())]},
                operation_keys=tuple(dict.fromkeys(
                    key for edit in edits for key in (edit.operation_keys or ()))),
                obligation_ids=tuple(dict.fromkeys(
                    value for edit in edits for value in (edit.obligation_ids or ())))))
            continue
        rule_ids: list[str] = []
        joint_obligations: list[dict[str, Any]] = []
        fixed_texts: list[str] = []
        all_selected_keys = tuple(dict.fromkeys(key for edit in edits for key in edit.operation_keys))
        unattributed = False
        for edit in edits:
            for rule_id in str(edit.rule_id).split("+"):
                rule_id = rule_id.strip()
                if not rule_id or rule_id in rule_ids:
                    continue
                rule_ids.append(rule_id)
                rule = rules_by_id.get(rule_id) or {}
                operations = list(rule.get("operations") or [])
                selected_indices = _normalise_operation_ids(rule, all_selected_keys, obligations)
                if selected_indices:
                    operations = [operations[index] for index in selected_indices]
                else:
                    unattributed = True
                    break
                joint_obligations.append({"rule_id": rule_id,
                                          "requirement": str(rule.get("requirement") or ""),
                                          "operations": operations})
                fixed = str((edit.evidence or {}).get("fixed_text") or "")
                if fixed:
                    fixed_texts.append(fixed)
        if unattributed:
            remaining.append(conflict)
            continue
        try:
            result = plan_joint_compose(span_text=span.text, start=start, end=end,
                                        obligations=joint_obligations,
                                        fixed_texts=fixed_texts,
                                        facts=facts, gateway=gateway, rule_ids=rule_ids)
        except (RecallError, ModelError):
            raise
        except Exception:  # noqa: BLE001 - a failed joint attempt is not a crash
            result = None
        if result is None:
            remaining.append(conflict)
            continue
        consumed.update(id(edit) for edit in edits)
        resolved.append(PlannedEdit(
            target_id="+".join(edit.target_id for edit in edits),
            rule_id="+".join(rule_ids), location=location, start=start, end=end,
            replacement=result["replacement"], operation="replace",
            content_source="joint_compose",
            evidence={"joint_rules": rule_ids, "fixed_text": "".join(fixed_texts),
                      "basis": result.get("basis") or "",
                      "validation": result.get("validation") or {},
                      "operation_keys": [key for edit in edits
                                         for key in (edit.operation_keys or ())]},
            operation_keys=tuple(dict.fromkeys(
                key for edit in edits for key in (edit.operation_keys or ()))),
            obligation_ids=tuple(dict.fromkeys(
                value for edit in edits for value in (edit.obligation_ids or ())))))
    kept = [edit for edit in planned if id(edit) not in consumed]
    return kept + resolved, remaining


def _blocked_recovery_trace(code: str, *, rule_id: str, target_id: str,
                            stage: str = "plan") -> dict[str, Any]:
    """Record the failing planner layer without fabricating an executed retry.

    The planner failed before any recovery action could run, so the first orchestrator
    candidate is recorded as ``skipped`` with an explicit reason.  Callers that can
    actually execute it (audit replan, locator, claim regeneration) record the real
    outcome in their own unified history.
    """
    from .recovery import (RecoveryContext, RecoveryHistory, RecoveryOrchestrator)

    if code == "RECALL_RULE_NOT_APPLICABLE":
        # Out of scope is a decision, not a failure to recover.
        return {}
    context = RecoveryContext(rule_id=rule_id, target_id=target_id, stage=stage,
                              error_code=code, reason=code)
    history = RecoveryHistory()
    orchestrator = RecoveryOrchestrator()
    decision = orchestrator.decide(context, history)
    if decision.terminal:
        orchestrator.record(history, context, decision, outcome="unresolved",
                            detail="planner_layer_failed")
    else:
        orchestrator.record(history, context, decision, outcome="skipped",
                            detail="planner_layer_failed_before_action")
        following = orchestrator.decide(context, history)
        if following.terminal:
            orchestrator.record(history, context, following, outcome="unresolved",
                                detail="no further safe recovery layer")
    return history.summary(context)


def _reconcile_final_plan_ledger(
        ledger: list[dict[str, Any]], records: Sequence[dict[str, Any]],
        conflicts: Sequence[dict[str, Any]], covered: Sequence[str],
        baseline: Sequence[PlannedEdit]) -> None:
    """Re-derive every ledger status from the FINAL edit set (plan §17–§20).

    A pre-merge ``planned`` status is not evidence that the operation reached the
    artifact.  Reconciling after merge/conflict/Joint Compose makes the invariant true:
    ``ledger=planned`` only when the operation exists in a final edit.
    """
    components: dict[tuple[str, str], set[str]] = {}
    final_target_ids: set[str] = set()
    for record in records:
        edit_id = f"{record.get('rule_id')}:{record.get('target_id')}"
        for unit in record.get("components") or [record]:
            target_ids = {part for part in str(unit.get("target_id") or "").split("+") if part}
            evidence = unit.get("evidence") or {}
            operation_ids = set(unit.get("operation_keys") or evidence.get("operation_keys") or [])
            final_target_ids.update(target_ids)
            for target_id in target_ids:
                for operation_id in operation_ids:
                    components.setdefault((target_id, str(operation_id)), set()).add(edit_id)
    conflict_ids = {part for conflict in conflicts for raw in conflict.get("targets") or []
                    for part in str(raw).split("+") if part}
    covered_ids = set(covered)
    baseline_ids = {edit.target_id for edit in baseline}
    for entry in ledger:
        target_id = str(entry.get("target_id") or "")
        keys = list(dict.fromkeys(str(key) for key in entry.get("operation_keys") or []))
        effects = {key: {"status": "planned" if components.get((target_id, key)) else "unresolved",
                         "edit_ids": sorted(components.get((target_id, key)) or [])}
                   for key in keys}
        entry["operation_effects"] = effects
        entry["edit_ids"] = sorted({value for effect in effects.values() for value in effect["edit_ids"]})
        if effects and all(effect["status"] == "planned" for effect in effects.values()):
            entry["status"] = "planned"
            entry.pop("reason", None)
        elif target_id in covered_ids:
            entry["status"] = "satisfied"
            entry["reason"] = "RECALL_COVERED_BY_ALTERNATIVE"
        elif target_id in conflict_ids:
            entry["status"] = "unresolved"
            entry["reason"] = "RECALL_EDIT_OVERLAP"
        elif target_id in baseline_ids or target_id in final_target_ids or entry.get("status") == "planned":
            entry["status"] = "unresolved"
            entry["reason"] = "RECALL_PLAN_COMPONENT_DROPPED"


def approval_book_for(rules_by_id: Mapping[str, dict], targets: Sequence[Target],
                      inspection: DocumentInspection) -> Any:
    """Deterministic approvals for every attributable target.

    Building them here (rather than only in the pipeline) keeps production planning
    and frozen stage replay identical: both derive the same approval ids, evidence
    and guide fingerprint from the recorded targets.
    """
    from .semantic_evidence import (ApprovalBook, AssessmentRef, EvidenceError,
                                    approval_from_target, guide_fingerprint)
    guide_sha256 = guide_fingerprint([rules_by_id[key] for key in sorted(rules_by_id)])
    book = ApprovalBook()
    for target in targets:
        if (target.state != "needs_edit" or target.out_of_scope
                or not target.operations or target.attribution_error):
            continue
        approval_id = str(getattr(target, "approval_id", "") or "") \
            or f"AP:{target.target_id}"
        try:
            approval = approval_from_target(
                approval_id, target, inspection, guide_id="active_guide",
                guide_sha256=guide_sha256,
                semantic_role=str(target.reason or "")[:200],
                assessment=AssessmentRef(
                    assessment_id=f"AS:{target.target_id}", task_type="inventory",
                    decision=str(target.state), model_role="primary"))
        except EvidenceError:
            continue
        book.add(approval)
        target.approval_id = approval.approval_id
    return book


def plan_edits(rules_by_id: dict[str, dict], targets: Sequence[Target], inspection: DocumentInspection,
               facts: Facts, gateway: Any, *, max_compose_calls: int = 6,
               obligations: Any = None,
               reuse_edits: Sequence[Mapping[str, Any]] = (),
               approvals: Any = None) -> dict[str, Any]:
    """Build the edit list, isolating per-target failures into the ledger."""
    if approvals is None:
        approvals = approval_book_for(rules_by_id, targets, inspection)
    planned: list[PlannedEdit] = []
    ledger: list[dict[str, Any]] = []
    compose_budget = [max_compose_calls]
    # A Claim-discovered body/summary copy has the same business site wording and
    # operation as its source target.  Reuse the already verified replacement instead
    # of asking the model to compose it again; this is the duplicate-site closure the
    # operation-first pipeline needs, not a fuzzy global duplicate rule.
    reusable: dict[tuple[str, tuple[str, ...], str], PlannedEdit] = {}
    for source in reuse_edits:
        if not isinstance(source, Mapping):
            continue
        keys = tuple(sorted(str(key) for key in
                            (source.get("operation_keys")
                             or (source.get("evidence") or {}).get("operation_keys") or ())))
        location = str(source.get("location") or "")
        if not keys or not location:
            continue
        quote = str(source.get("expected_old_text") or "")
        if not quote:
            try:
                span = inspection.by_location(location)
                quote = span.text[int(source.get("start", 0)):int(source.get("end", 0))]
            except Exception:  # noqa: BLE001
                quote = ""
        evidence = source.get("evidence") if isinstance(source.get("evidence"), Mapping) else {}
        fields = {key: source.get(key) for key in (
            "target_id", "rule_id", "location", "start", "end", "replacement",
            "operation", "content_source", "anchor_sha256")}
        try:
            prior = PlannedEdit(
                target_id=str(fields["target_id"] or ""), rule_id=str(fields["rule_id"] or ""),
                location=location, start=int(fields["start"] or 0), end=int(fields["end"] or 0),
                replacement=str(fields["replacement"] or ""),
                operation=str(fields["operation"] or ""),
                content_source=str(fields["content_source"] or ""),
                evidence=dict(evidence),
                anchor_sha256=str(fields["anchor_sha256"] or ""),
                operation_keys=keys,
                obligation_ids=tuple(str(key) for key in (source.get("obligation_ids") or ())))
        except (KeyError, TypeError, ValueError):
            continue
        if quote:
            reusable[(prior.rule_id, keys, _compact(quote))] = prior
    for target in targets:
        if target.attribution_error:
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": "unresolved",
                           "reason": target.attribution_error,
                           "operation_keys": list(target.claimed_operations)})
            continue
        if target.out_of_scope:
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": "not_applicable", "reason": "TARGET_SOURCE_MISMATCH"})
            continue
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
                indices = _selected_operation_indices(rule, target, inspection, facts, obligations)
                applicable_ops = [rule["operations"][index] for index in indices
                                  if rule["operations"][index].get("op") == "replace"]
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
                for composite_edit in composite_edits:
                    composite_edit.operation_keys = tuple(target.operations)
                    if obligations is not None:
                        composite_edit.obligation_ids = tuple(
                            record.obligation_id for key in target.operations
                            if (record := obligations.record(key)) is not None)
                    composite_edit.evidence = {
                        **(composite_edit.evidence or {}),
                        "operation_keys": list(composite_edit.operation_keys),
                        "obligation_ids": list(composite_edit.obligation_ids),
                    }
                planned.extend(composite_edits)
                ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                               "status": "planned",
                               "operation": composite_edits[0].operation,
                               "operation_keys": list(target.operations),
                               "parts": [edit.location for edit in composite_edits]})
                continue
            edit = None
            reason_text = str(target.reason or "")
            target_operations = [operation for index, operation
                                 in enumerate(rule.get("operations") or [])
                                 if f"{target.rule_id}:{index}" in target.operations]
            append_site = any(operation.get("op") == "append"
                              for operation in target_operations)
            if not append_site and ("claim_required_site:" in reason_text
                    or "duplicate_copy:" in reason_text):
                reuse_key = (target.rule_id, tuple(sorted(target.operations)),
                             _compact(str(target.quote or "")))
                source_edit = reusable.get(reuse_key)
                if source_edit is not None and target.start is not None \
                        and target.end is not None:
                    from copy import deepcopy
                    edit = deepcopy(source_edit)
                    edit.target_id = target.target_id
                    edit.location = target.location
                    edit.start = target.start
                    edit.end = target.end
                    edit.content_source = "claim_site_reuse"
                    edit.evidence = {
                        **(edit.evidence or {}),
                        "reused_from": source_edit.target_id,
                        "claim_site_reuse": True,
                    }
                    for component in edit.evidence.get("components") or ():
                        component["target_id"] = target.target_id
                        component["location"] = target.location
                        component["start"] = target.start
                        component["end"] = target.end
            if edit is None:
                edit = plan_target(rule, target, inspection, facts, gateway,
                                   compose_budget=compose_budget, obligations=obligations,
                                   approvals=approvals)
        except RecallError as exc:
            status = "not_applicable" if exc.code == "RECALL_RULE_NOT_APPLICABLE" else "unresolved"
            if status == "not_applicable":
                target.out_of_scope = True
            ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                           "status": status, "reason": exc.code, "detail": exc.detail,
                           "recovery": _blocked_recovery_trace(
                               exc.code, rule_id=target.rule_id,
                               target_id=target.target_id)})
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
        notices = _g15_notice_for_edit(edit, rule, inspection)
        if notices:
            edit.evidence = {**(edit.evidence or {}), "business_notices": notices}
        planned.append(edit)
        ledger.append({"target_id": target.target_id, "rule_id": target.rule_id,
                       "status": "planned", "operation": edit.operation,
                       "operation_keys": list(edit.operation_keys),
                       "obligation_ids": list(edit.obligation_ids)})
        if target.quote and edit.replacement is not None:
            reusable[(target.rule_id, tuple(sorted(target.operations)),
                      _compact(str(target.quote or "")))] = edit
    target_by_id = {target.target_id: target for target in targets}
    for entry in ledger:
        target = target_by_id.get(str(entry.get("target_id") or ""))
        if target is not None:
            entry.update(location=target.location, start=target.start, end=target.end,
                         occurrence_index=target.occurrence_index,
                         quote=target.quote, composite=list(target.composite))
            entry.setdefault("operation_keys", list(target.operations))
    baseline = list(planned)
    planned = _atomic_paragraph_edits(planned, inspection, obligations)
    merged, conflicts, covered = merge_edits(planned, inspection, obligations)
    if conflicts and _tier1_enabled():
        planned, conflicts = _resolve_overlaps_with_joint_compose(
            conflicts, planned, inspection, rules_by_id, facts, gateway,
            obligations=obligations)
        merged, conflicts, covered = merge_edits(planned, inspection, obligations)
    conflict_ids: set[str] = set()
    for conflict in conflicts:
        for raw in conflict.get("targets") or ():
            conflict_ids.update(part for part in str(raw or "").split("+") if part)
    # A conflict is only allowed to remove an edit from the final set after Joint
    # Compose had a chance.  Anything still conflicting is unresolved, including every
    # component of a synthetic merged id.
    records: list[dict[str, Any]] = []
    for edit, components in merged:
        ids = _component_target_ids(edit, components)
        if ids & conflict_ids:
            continue
        owned_components = (edit.evidence or {}).get("atomic_components")
        records.append({**edit.as_dict(), "components": owned_components or components})
    _reconcile_final_plan_ledger(ledger, records, conflicts, covered, baseline)
    for record in records:
        _clamp_edit_boundary(record, inspection)
    return {"edits": records, "ledger": ledger, "conflicts": conflicts,
            "covered": sorted(covered)}


def replan_sites(existing: dict[str, Any], dirty_locations: set[str], rules_by_id: dict[str, dict],
                 targets: Sequence[Target], inspection: DocumentInspection, facts: Facts,
                 gateway: Any, *, max_compose_calls: int, obligations: Any = None) -> dict[str, Any]:
    """Recompute dirty paragraph plans and reuse all unchanged final components."""
    from copy import deepcopy
    def target_sites(target: Target) -> set[tuple[str, str]]:
        """Return stable operation/site keys for one target.

        Target ids are discovery artifacts and can be reassigned when a dirty
        inventory window is refreshed. Recovery must therefore match the plan by
        operation and source location, while retaining composite operation parts.
        """
        locations = {str(target.location)}
        for part in target.composite:
            try:
                locations.add(str(part).rsplit(":", 2)[0])
            except (AttributeError, ValueError):
                continue
        return {(str(operation), location)
                for operation in target.operations for location in locations}

    def edit_sites(edit: dict[str, Any]) -> set[tuple[str, str]]:
        return {(str(operation), str(unit.get("location") or edit.get("location") or ""))
                for unit in edit.get("components") or [edit]
                for operation in unit.get("operation_keys") or edit.get("operation_keys") or ()}

    def operation_keys(item: dict[str, Any]) -> set[str]:
        return set(item.get("operation_keys") or
                   (item.get("evidence") or {}).get("operation_keys") or ())

    def bind_reference(unit: dict[str, Any]) -> Target | None:
        """Find a current target from source geometry, never its discovery id."""
        keys = operation_keys(unit)
        location = str(unit.get("location") or "")
        try:
            span = inspection.by_location(location)
            start, end = int(unit["start"]), int(unit["end"])
        except (KeyError, TypeError, ValueError):
            return None
        if not keys or not 0 <= start <= end <= len(span.text):
            return None
        expected = unit.get("expected_old_text")
        if isinstance(expected, str) and expected != span.text[start:end]:
            return None
        parts = tuple((unit.get("evidence") or {}).get("parts") or unit.get("composite") or ())
        if (unit.get("evidence") or {}).get("parts"):
            own_slice = _composite_part_slice(unit, span)
            if own_slice is None:
                return None
            start, end = own_slice
        candidates: list[tuple[tuple[int, int, int], tuple[Any, ...], Target]] = []
        for target in targets:
            if (target.rule_id != unit.get("rule_id") or not keys <= set(target.operations)
                    or target.state not in {"needs_edit", "satisfied", "absent"}
                    or target.out_of_scope or target.attribution_error):
                continue
            # A previously composite component must keep its complete source-part
            # identity. A direct component may bind a newly discovered composite.
            if parts and tuple(target.composite) != parts:
                continue
            ranges = []
            if target.composite:
                for index, raw in enumerate(target.composite):
                    if str(raw).rsplit(":", 2)[0] != location:
                        continue
                    bound = _composite_part_slice({"evidence": {
                        "parts": list(target.composite), "part_index": index}}, span)
                    if bound is not None:
                        ranges.append(bound)
            elif target.location == location:
                left, right = target.start, target.end
                if left is None or right is None:
                    bound = resolve_quote(span, target.quote)
                    if bound is not None:
                        left, right = bound
                if left is not None and right is not None and 0 <= left <= right <= len(span.text) \
                        and target.quote and _compact(target.quote) in _compact(span.text[left:right]):
                    ranges.append((left, right))
            occurrence = int(unit.get("occurrence_index", -1))
            if occurrence >= 0 and target.occurrence_index != occurrence:
                continue
            for left, right in ranges:
                if not left <= start <= end <= right:
                    # Inventory quotes often omit a trailing space that the old
                    # planned delete included.  The target still identifies the
                    # same source clause; only whitespace may extend past it.
                    if not (left <= start and right <= end
                            and not span.text[right:end].strip()):
                        continue
                # G02/G04 may never borrow a sibling occurrence in a broad span.
                if target.occurrence_index >= 0 and (start, end) != (left, right):
                    continue
                rank = (int((left, right) != (start, end)),
                        int(bool(target.composite) and not parts), right - left)
                identity = (target.rule_id, tuple(sorted(target.operations)), location,
                            left, right, target.occurrence_index, tuple(target.composite))
                candidates.append((rank, identity, target))
        if not candidates:
            return None
        best = min(rank for rank, _identity, _target in candidates)
        matches = [(identity, target) for rank, identity, target in candidates if rank == best]
        if len({identity for identity, _target in matches}) != 1:
            return None
        # Duplicate inventory aliases of the exact same operation/source identity
        # are equivalent; their order must not change the selected reference.
        return min((target for _identity, target in matches), key=lambda target: target.target_id)

    def target_metadata(target: Target) -> dict[str, Any]:
        return {"target_id": target.target_id, "location": target.location,
                "start": target.start, "end": target.end, "quote": target.quote,
                "composite": list(target.composite), "occurrence_index": target.occurrence_index}

    def unbound_entry(item: dict[str, Any]) -> dict[str, Any]:
        old_id = str(item.get("target_id") or "")
        identity = "|".join(str(item.get(key) or "") for key in (
            "rule_id", "location", "start", "end")) + "|" + ",".join(sorted(operation_keys(item)))
        return {**deepcopy(item), "target_id": "UNBOUND:" + _sha256(identity + "|" + old_id)[:20],
                "original_target_id": old_id, "status": "unresolved",
                "reason": "RECALL_PLAN_REFERENCE_UNBOUND", "edit_ids": [],
                "operation_effects": {}}

    dirty_locations = set(dirty_locations)
    dirty_keys: set[tuple[str, str]] = set()
    # Resolve the complete composite dependency closure before retaining anything.
    # A single pass can retain an earlier component before a later one makes its
    # site dirty. The result must be independent of the final edit order.
    while True:
        previous = (set(dirty_locations), set(dirty_keys))
        for target in targets:
            keys = target_sites(target)
            if any(location in dirty_locations for _operation, location in keys):
                dirty_keys.update(keys)
                dirty_locations.update(location for _operation, location in keys)
        for edit in existing.get("edits") or []:
            keys = edit_sites(edit)
            if str(edit.get("location") or "") in dirty_locations or keys & dirty_keys:
                dirty_keys.update(keys)
                dirty_locations.update(location for _operation, location in keys)
        if previous == (dirty_locations, dirty_keys):
            break

    retained_edits = []
    # These records belong to the OLD plan. Recover old ledger geometry only
    # from them; the same serial id in current Inventory may be another rule.
    old_units = [((edit_index, component_index), unit)
                 for edit_index, edit in enumerate(existing.get("edits") or [])
                 for component_index, unit in enumerate(edit.get("components") or [edit])]
    bound_units: dict[tuple[int, int], Target] = {}
    dropped_units: dict[tuple[int, int], dict[str, Any]] = {}
    def bind_joint(edit: dict[str, Any]) -> list[Target] | None:
        """Bind a validated joint edit component-by-component.

        Joint Compose deliberately produces one edit whose components carry both
        operation keys (for example G12:1 + G13:0).  No single target owns both
        keys, so requiring one target made replan drop the validated p229 edit.
        Every key only needs its own current target at the same source location,
        while the joint expected_old_text still matches the unchanged source.
        """
        keys = sorted(operation_keys(edit))
        if len(keys) < 2 or edit.get("content_source") != "joint_compose":
            return None
        location = str(edit.get("location") or "")
        try:
            span = inspection.by_location(location)
            start, end = int(edit["start"]), int(edit["end"])
        except (KeyError, TypeError, ValueError, DocxError):
            return None
        expected = edit.get("expected_old_text")
        if isinstance(expected, str) and expected != span.text[start:end]:
            return None
        bound: list[Target] = []
        for key in keys:
            target = next((candidate for candidate in targets
                           if key in candidate.operations
                           and candidate.location == location
                           and not candidate.out_of_scope
                           and not candidate.attribution_error), None)
            if target is None:
                return None
            if target not in bound:
                bound.append(target)
        return bound

    for edit_index, edit in enumerate(existing.get("edits") or []):
        components = edit.get("components") or [edit]
        if (str(edit.get("location") or "") in dirty_locations
                or edit_sites(edit) & dirty_keys):
            continue
        joint_targets = bind_joint(edit)
        if joint_targets is not None:
            retained = deepcopy(edit)
            joined_id = "+".join(dict.fromkeys(target.target_id for target in joint_targets))
            retained["target_id"] = joined_id
            if retained.get("components"):
                for component in retained["components"]:
                    component["target_id"] = joined_id
            bound_units[(edit_index, 0)] = joint_targets[0]
            retained_edits.append(retained)
            continue
        bindings = [bind_reference(unit) for unit in components]
        if any(target is None for target in bindings):
            # The parent edit is atomic. Keeping only some of its components
            # would change its authorized paragraph transformation.
            dropped_units.update({(edit_index, index): unit
                                  for index, unit in enumerate(components)})
            continue
        retained = deepcopy(edit)
        rebound = retained.get("components") or [retained]
        for component_index, (copied, target) in enumerate(zip(rebound, bindings)):
            assert target is not None
            bound_units[(edit_index, component_index)] = target
            copied["target_id"] = target.target_id
        retained["target_id"] = "+".join(dict.fromkeys(unit["target_id"] for unit in rebound))
        if (retained.get("evidence") or {}).get("atomic_components") is not None:
            retained["evidence"]["atomic_components"] = deepcopy(rebound)
        retained_edits.append(retained)
    # Composite operations are indivisible: replan all their source parts together.
    dirty_targets = [target for target in targets
                     if target.location in dirty_locations or target_sites(target) & dirty_keys]
    fresh = plan_edits(rules_by_id, dirty_targets, inspection, facts, gateway,
                       max_compose_calls=max_compose_calls, obligations=obligations,
                       reuse_edits=existing.get("edits") or ())
    records = retained_edits + fresh["edits"]
    ledger = []
    covered = set(fresh["covered"])
    represented_units: set[tuple[int, int]] = set()
    old_references: dict[str, list[dict[str, Any]]] = {}
    for entry in existing.get("ledger") or []:
        keys = operation_keys(entry)
        units = [(index, unit) for index, unit in old_units
                 if unit.get("target_id") == entry.get("target_id")
                 and unit.get("rule_id") == entry.get("rule_id")
                 and (not keys or keys <= operation_keys(unit))]
        sources = [unit for _index, unit in units] or [entry]
        old_references.setdefault(str(entry.get("target_id") or ""), []).extend(sources)
        represented_units.update(index for index, _unit in units)
        if any(str(source.get("location") or "") in dirty_locations
               or edit_sites(source) & dirty_keys for source in sources):
            continue
        bindings = [bound_units.get(index) for index, _unit in units] if units else [bind_reference(entry)]
        if not bindings or any(target is None for target in bindings):
            ledger.append(unbound_entry(entry))
            continue
        unique = {target.target_id: target for target in bindings if target is not None}
        for target in unique.values():
            rebound_entry = {**deepcopy(entry), **target_metadata(target)}
            rebound_entry.setdefault("operation_keys", list(target.operations))
            ledger.append(rebound_entry)
            if entry.get("target_id") in set(existing.get("covered") or ()):
                covered.add(target.target_id)
    ledger.extend(unbound_entry(unit) for index, unit in dropped_units.items()
                  if index not in represented_units)
    ledger.extend(fresh["ledger"])
    conflicts = []
    for conflict in existing.get("conflicts") or []:
        location = str(conflict.get("location") or "")
        if location in dirty_locations or any((str(key), location) in dirty_keys
                                              for key in conflict.get("operation_keys") or []):
            continue
        rebound = deepcopy(conflict)
        rebound_ids = []
        for raw in conflict.get("targets") or []:
            parts = []
            for old_id in str(raw).split("+"):
                references = old_references.get(old_id) or []
                matches = [bind_reference(reference) for reference in references]
                if not matches or any(target is None for target in matches):
                    parts.append("UNBOUND:" + _sha256(location + "|" + old_id)[:20])
                    rebound["reference_status"] = "RECALL_PLAN_REFERENCE_UNBOUND"
                else:
                    parts.extend(target.target_id for target in matches if target is not None)
            rebound_ids.append("+".join(dict.fromkeys(parts)))
        rebound["targets"] = list(dict.fromkeys(rebound_ids))
        conflicts.append(rebound)
    conflicts += fresh["conflicts"]
    covered = sorted(covered)
    _reconcile_final_plan_ledger(ledger, records, conflicts, covered, [])
    for record in records:
        _clamp_edit_boundary(record, inspection)
    return {"edits": records, "ledger": ledger, "conflicts": conflicts, "covered": covered}


def _clamp_edit_boundary(edit: dict[str, Any], inspection: DocumentInspection) -> None:
    """Clamp a trailing-whitespace span to its containing DOCX text segment."""
    try:
        span = inspection.by_location(str(edit.get("location") or ""))
        start, end = int(edit["start"]), int(edit["end"])
    except (KeyError, TypeError, ValueError, DocxError):
        return
    if start < 0 or end < start or end > len(span.text):
        return
    if any(segment.start <= start and end <= segment.end for segment in span.segments):
        return
    containing = next((segment for segment in span.segments
                       if segment.start <= start < segment.end), None)
    if containing is not None and not span.text[containing.end:end].strip():
        edit["end"] = containing.end
        # The planner may have preserved the same trailing paragraph whitespace in
        # the replacement.  It is not editable text; remove it with the clamped span
        # so atomic content verification sees the same final string.
        tail = span.text[containing.end:end]
        replacement = str(edit.get("replacement") or "")
        if tail and replacement.endswith(tail):
            edit["replacement"] = replacement[:-len(tail)].rstrip(" \t\r\n")


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
        item = dict(item)
        _clamp_edit_boundary(item, inspection)
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
            "operation_keys": list(item.get("operation_keys") or []),
            "obligation_ids": list(item.get("obligation_ids") or []),
            "evidence": dict(item.get("evidence") or {}),
            "planning_content_source": item.get("content_source") or "",
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
    # Composite offsets are measured in the paragraph's whitespace-free text
    # (find_old_text_all), exactly like ``plan_composite_target``. Mapping them
    # through ``display_text``'s index table would shift every offset after the
    # first whitespace (FL-D052/FL-D112).
    _cleaned, index_map = compact_offsets(span.text)
    if start_clean < 0 or end_clean > len(index_map) or start_clean >= end_clean:
        return None
    if start_clean == 0 and end_clean == len(index_map):
        # Whole-paragraph parts delete the trailing spaces too, matching
        # plan_composite_target; otherwise the content check expects them back and
        # rejects the edit, silently dropping the second composite component.
        return 0, len(span.text)
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
    fragments = evidence.get("fragments") or []
    if content_source in {"fragment_delete", "fragment_replace", "fragment_mixed"} and fragments:
        replayed = _replay_fragments(expected or "", fragments)
        if replayed is None or replayed != replacement:
            return False
        if content_source == "fragment_delete":
            return len(_compact(replacement)) < len(_compact(expected or ""))
        if content_source == "fragment_replace":
            return any(str(item.get("new_text") or "") for item in fragments)
        return True
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
    if content_source == "target_span_delete":
        # The planner deletes exactly the bound target span; there is no separate
        # fragment trace to replay (FL-D112).
        return replacement == "" and bool(expected)
    if content_source in {"variant_delete", "variant_replace"}:
        # The whole variant span is the target span: verify the recorded ratio by
        # re-running the same bounded fuzzy match (FL-D047).
        matched = str(evidence.get("matched_old_text") or "")
        if not matched:
            # The target-span delete producer records the deleted quote instead of a
            # fuzzy match: the span itself is the material to remove.
            deleted_quote = str(evidence.get("deleted_quote") or "")
            if content_source == "variant_delete" and deleted_quote:
                return replacement == "" and _same_compact(deleted_quote, expected or "")
            return False
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
        # A composite edit replaces only the bound slice. The executor preserves
        # the paragraph outside that slice; including it here would duplicate it.
        if not expected or replacement == expected:
            return False
        deleted = _composite_part_slice(component, span)
        if deleted is None or not deleted:
            return False
        start_offset, end_offset = deleted
        if (start, end) != deleted:
            return False
        prefix, suffix = span.text[:start_offset], span.text[end_offset:]
        if content_source == "composite_delete":
            return replacement == ""
        fixed = str(evidence.get("fixed_text") or "")
        if not fixed or (not compact_in(fixed, replacement) and fixed not in replacement):
            return False
        return replacement == (append_separator(prefix, fixed) + fixed
                               + append_separator(fixed, suffix))
    if content_source in {"guide_text", "composed"}:
        fixed = str(evidence.get("fixed_text") or "")
        if fixed:
            if not compact_in(fixed, replacement):
                return False
        elif content_source == "composed":
            return False
    return True


def content_check_factory(planned: Sequence[dict], inspection: DocumentInspection):
    """docx.validate_edit_plan content_check: re-verify generated/composed text.

    Composite targets emit one edit per paragraph with the same ``edit_id``; the
    lookup key therefore includes target/location/span. Keying only by ``edit_id``
    would validate every part against the last part (FL-D112).
    """
    by_key: dict[tuple[str, str, str, int, int], dict[str, Any]] = {}
    for item in planned:
        try:
            key = (str(item.get("target_id")), str(item.get("rule_id")),
                   str(item.get("location")), int(item["start"]), int(item["end"]))
        except (KeyError, TypeError, ValueError):
            continue
        by_key[key] = item

    def check(edit: dict[str, Any]) -> bool:
        try:
            key = (str(edit.get("target_id")), str(edit.get("rule_id")),
                   str(edit.get("location")), int(edit.get("start", -1)),
                   int(edit.get("end", -2)))
        except (TypeError, ValueError):
            return False
        item = by_key.get(key)
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
        if item.get("content_source") == "atomic_paragraph":
            from .generation.atomic import compose_paragraph
            trailing_ok = (start == 0 and
                           (end == len(span.text) or not span.text[end:].strip()))
            return (trailing_ok
                    and components == (item.get("evidence") or {}).get("atomic_components")
                    and all(_component_ok(component, inspection) for component in components)
                    and compose_paragraph(span.text, components).rstrip(" \t\r\n")
                    == str(item["replacement"]).rstrip(" \t\r\n"))
        if components:
            if "".join(str(component.get("replacement") or "") for component in components) != str(item["replacement"]):
                return False
            return all(_component_ok(component, inspection) for component in components)
        return _component_ok({**item, "expected_old_text": span.text[start:end]}, inspection)

    return check


_TARGET_ANCHORS: dict[str, tuple[tuple[str, ...], str]] = {
    # G05 only authorises edits inside the share-class setup / fee-adjustment clause.
    "G05": (("份额类别", "基金份额类别", "调整前", "调低"), "any"),
    # G06 deletes only the class-conversion prohibition.
    "G06": (("份额类别", "不得"), "all"),
    # Append rules must land in the share-class definition, not another definition.
    "G01": (("基金份额类别", "将基金份额分为", "份额类别："), "any"),
    "G03": (("基金份额类别", "将基金份额分为", "份额类别："), "any"),
    # G18 acts only on the distribution section's fee-difference sentence, never on
    # the bare section heading "基金收益分配原则".
    "G18": (("由于本基金", "费用收取不同"), "any"),
}


def append_site_ok(rule_id: str, span: Any, inspection: DocumentInspection) -> bool:
    """An append anchor must carry its own clause, never a neighbour's anchor."""
    if rule_id in {"G01", "G03"}:
        # A model inventory target can point at the amendment trigger
        # "基金份额类别设置" or a split fragment.  Require a real definition clause
        # before accepting the site; otherwise the policy is appended twice (once to
        # the fragment by the model and once to the definition by the survey).
        if not _append_definition_anchor(rule_id, span, inspection):
            return False
        spans = list(inspection.paragraphs)
        position = next((i for i, item in enumerate(spans) if item.location == span.location), -1)
        if any((end := _split_definition_end(anchor, inspection)) is not None
               and end.location == span.location
               for anchor in spans[max(0, position - 6):max(0, position)]):
            return True
        paragraph, _ = display_text(span.text)
        if any(anchor in paragraph for anchor in _TARGET_ANCHORS[rule_id][0]):
            return True
        # A DOCX paragraph can split the class-definition sentence immediately
        # before the fee-group wording ("…三种不同的" | "类别。在投资者…").  The
        # append belongs after the continuation paragraph, but the anchor remains
        # in the previous paragraph.  Only accept a direct, unfinished-heading
        # continuation, never an unrelated preceding paragraph.
        location = getattr(span, "location", None)
        if location is None:
            return False
        locations = [item.location for item in inspection.paragraphs]
        try:
            index = locations.index(location)
        except ValueError:
            return False
        if index <= 0:
            return False
        previous = inspection.paragraphs[index - 1]
        previous_text, _ = display_text(previous.text)
        current_text, _ = display_text(span.text)
        if previous_text.rstrip().endswith(("。", "；", ";", "！", "？", "!", "?")):
            return False
        if not any(anchor in previous_text for anchor in _TARGET_ANCHORS[rule_id][0]):
            return False
        return (bool(current_text.strip())
                and current_text.lstrip().startswith(
                    ("类别", "份额类别", "基金份额类别"))
                and any(token in current_text for token in
                        ("基金份额", "申购费", "认购费", "销售服务费")))
    if rule_id == "G16":
        paragraph, _ = display_text(span.text)
        compact = _compact(paragraph)
        if _g16_payment_anchor(paragraph):
            return True
        if any(clause[-1] == getattr(span, "location", "")
               for clause in _g16_clause_locations(inspection)):
            return True
        # The resolved append site is the end of the complete fee clause: the
        # usage-scope sentence or the direct continuation of the payment head
        # (FL-D159).  Membership still selects only the payment head; this branch
        # exists so the planner can execute the resolved clause-end target.
        if compact.startswith("销售服务费") and any(
                token in compact for token in ("主要用于", "使用范围")):
            return True
        locations = [item.location for item in inspection.paragraphs]
        try:
            index = locations.index(getattr(span, "location", ""))
        except ValueError:
            return False
        if index <= 0:
            return False
        previous_text, _ = display_text(inspection.paragraphs[index - 1].text)
        return (not previous_text.rstrip().endswith(("。", "；", ";", "！", "？", "!", "?"))
                and _g16_payment_anchor(previous_text))
    return target_site_ok(rule_id, span, inspection)


def target_site_ok(rule_id: str, span: Any, inspection: DocumentInspection) -> bool:
    """Whether this target paragraph carries the rule's own clause (site guard)."""
    if rule_id in {"G01", "G03"}:
        return append_site_ok(rule_id, span, inspection)
    if rule_id == "G05":
        # Apply the same business boundary used by operation effect proof before
        # planning/audit. Meeting exemptions can contain identical fee words.
        compact = _compact(display_text(span.text)[0])
        return bool("份额类别的具体设置" in compact or re.search(
            r"(?:增加|增设|新增|变更|停止)[^。；;]{0,12}(?:基金)?份额类别|"
            r"调整(?:现有|本基金)?(?:基金)?份额类别(?:的[^。；;]{0,12})?", compact))
    if rule_id in {"G02", "G04"}:
        paragraph, _ = display_text(span.text)
        # Account eligibility and class enumeration are not fee-group clauses.
        # Replacing their A/Y labels would change pension sales restrictions.
        if not any(token in _compact(paragraph) for token in
                   ("申购费", "认购费", "销售服务费")):
            return False
        compact = _compact(paragraph)
        # The amendment trigger ("增加新的基金份额类别…变更现有基金份额类别的
        # 申购费率") is G05's business site, not a class definition.  Accepting it
        # let a "satisfied" G04 target with no class label bind there and left the
        # real definition unproven (景宁 p148 vs p151).
        if (re.search(r"(?:增加|增设|新增|变更|停止)[^。；;]{0,16}(?:基金)?份额类别", compact)
                and "将基金份额分为" not in compact and "称为" not in compact):
            return False
        if any(token in paragraph for token in
               ("基金份额类别", "份额类别", "将基金份额分为", "分类")):
            return True
        # Split definitions: the heading is one paragraph and the actual fee-group
        # wording is the next one.  That second paragraph carries the real site; a
        # generic fee sentence must still supply both fee concepts and at least two
        # share-class labels.
        labels = set(re.findall(r"([A-Z])类", compact))
        return (len(labels) >= 2 and "销售服务费" in compact
                and any(token in compact for token in ("申购费用", "申购费", "认购费用", "认购费")))
    if rule_id == "G15":
        paragraph, _ = display_text(span.text)
        return ("销售服务费" in paragraph and "支付" in paragraph) or bool(
            _g15_delay_continuation(inspection, span.location))
    if rule_id == "G16":
        paragraph, _ = display_text(span.text)
        compact = _compact(paragraph)
        # A G16 append belongs after the payment mechanism, not after every
        # paragraph that mentions the sales-service fee. Fee rates, formulas and
        # usage lists also contain the domain term; requiring both an accrual
        # phrase and a monthly-payment phrase isolates the one real anchor.
        accrual = any(token in compact for token in (
            "每日计提", "日计提", "每日计算", "逐日累计", "计提"))
        monthly = ("按月支付" in compact or
                   ("按月" in compact and "支付" in compact) or
                   "逐月支付" in compact)
        return "销售服务费" in compact and accrual and monthly
    if rule_id == "G17":
        paragraph, _ = display_text(span.text)
        return "销售服务费" in paragraph and (
            "主要用于" in paragraph or "使用范围" in paragraph)
    if rule_id == "G06":
        if not g06_scope_present(inspection, span.location):
            return False
        paragraph, _ = display_text(span.text)
        compact = _compact(paragraph)
        # Historical contracts use both the guide's "不得互相转换" wording and
        # variants such as "暂不允许进行相互转换".  Preserve the domain guard while
        # accepting those semantic equivalents for deterministic delete recall.
        return ("份额" in compact and "转换" in compact and
                any(token in compact for token in
                    ("不得", "不允许", "暂不允许", "不能", "不可")))
    if rule_id == "G18":
        paragraph, _ = display_text(span.text)
        compact = _compact(paragraph)
        # The guide also authorizes the neutral summary used by D06. It preserves
        # the fee-difference meaning without inventing a particular class split;
        # the p132 undifferentiated class list remains outside this site predicate.
        if ("各基金份额类别在费用收取上不同" in compact
                and any(token in compact for token in ("可分配收益", "分别计算"))):
            return True
        if "费用收取不同" in compact and "由于本基金" in compact:
            return True
        # Historical contracts state the same two fee groups through explicit
        # ``不收取销售服务费 / 收取销售服务费`` wording rather than the newer
        # ``费用收取不同`` phrase.  This is a valid G18 business site when both
        # polarities occur in one paragraph; it cannot match the D06 p132
        # undifferentiated class list because that paragraph has no such fee facts.
        if ("不收取销售服务费" in compact and "收取销售服务费" in compact
                and len(set(re.findall(r"([A-ZＡ-Ｚ])类", compact))) >= 2):
            return True
        # The guide writes ``A/Y ... and C/E/F ... fees differ``.  A paragraph
        # listing all classes as one undifferentiated set is not a G18 site: it
        # does not prove the two fee groups that the replacement authorizes.
        # Require two ordered groups separated by a fee-difference phrase.
        labels = re.findall(r"([A-ZＡ-Ｚ])类", compact)
        if len(labels) < 2 or "费用" not in compact or "不同" not in compact:
            return False
        if not any(token in compact for token in ("份额净值", "可分配收益", "分别计算")):
            return False
        # The two groups must be explicit in the same sentence.  Requiring the
        # class labels to be listed before each ``基金份额`` phrase distinguishes
        # ``A、C、E、F、Y类基金份额`` from the authorized ``A、Y类基金份额和
        # C、E、F类基金份额`` form.  The former was the false D06 p132 site.
        grouped = re.compile(
            r"(?:[A-ZＡ-Ｚ]类(?:、[A-ZＡ-Ｚ]类)*基金份额)"
            r"(?:和|及|与)(?:[A-ZＡ-Ｚ]类(?:、[A-ZＡ-Ｚ]类)*基金份额)")
        for sentence in re.split(r"[。；;！？!?]", compact):
            class_share_mentions = re.findall(
                r"[A-ZＡ-Ｚ]类基金份额", sentence)
            if any(marker in sentence for marker in _FEE_DIFFERENCE_MARKERS) \
                    and len(class_share_mentions) == 2 \
                    and grouped.search(sentence):
                return True
        return False
    if rule_id not in _TARGET_ANCHORS:
        return True
    paragraph, _ = display_text(span.text)
    if rule_id in {"G01", "G03"}:
        locations = [item.location for item in inspection.paragraphs]
        try:
            index = locations.index(span.location)
        except ValueError:
            index = -1
        if index > 0:
            previous, _ = display_text(inspection.paragraphs[index - 1].text)
            paragraph = previous + paragraph
    anchors, mode = _TARGET_ANCHORS[rule_id]
    return (any(anchor in paragraph for anchor in anchors) if mode == "any"
            else all(anchor in paragraph for anchor in anchors))


_DELETE_SENTENCE_ANCHORS = {
    "G06": ("份额类别", "转换"),
    "G13": ("7日", "赎回费", "短期"),
    "G15": ("销售服务费",),
    "G17": ("销售服务费",),
}

# Canonical guide wording is only one historical form.  These bounded semantic
# probes are used by the deterministic delete sweep after exact/variant matching;
# they are deliberately domain-specific so a generic "转换" sentence cannot become
# a G06 target.  The model may still refine the target, but it must not be allowed
# to suppress this code-discoverable occurrence.
_DELETE_SEMANTIC_PROBES = {
    "G06": re.compile(
        r"(?=(?:.*份额(?:类别|之间)|.*[A-ZＡ-Ｚ]\s*类\s*基金\s*份额))"
        r"(?=.*(?:不得|不允许|暂不允许|不能|不可)[^。；;！？!?]{0,32}转换)"
    ),
}

# One-way养老/Y-class restrictions may reflect a distinct regulatory boundary,
# while G06's reference authorizes deletion of the mutual class-conversion ban.
# Surface these to the final omission review, but do not turn them into automatic
# delete targets without an applicability decision.  Absence cannot be proven by
# the canonical literal alone when such a candidate is still present.
_DELETE_REVIEW_PROBES = {
    "G06": re.compile(
        r"(?=(?:.*份额(?:类别|之间)|.*[A-ZＡ-Ｚ]\s*类\s*基金\s*份额))"
        r"(?=.*(?:不得|不允许|暂不允许|不能|不可)[^。；;！？!?]{0,32}转换)"
    ),
}


def semantic_delete_review_candidates(rule_id: str, text: str) -> list[str]:
    """Potential delete equivalents needing review, including uncertain branches."""
    pattern = _DELETE_REVIEW_PROBES.get(rule_id)
    if pattern is None:
        return []
    candidates: list[str] = []
    for sentence in re.split(r"(?<=[。；;！？!?])", text or ""):
        candidate = sentence.strip()
        if len(_compact(candidate)) >= 12 and pattern.search(candidate):
            candidates.append(candidate)
    return candidates


def _is_one_way_y_class_conversion(text: str) -> bool:
    """Identify the separately governed one-way Y-class conversion path."""
    compact = _compact(text)
    if "Y类基金份额" not in compact or "转换" not in compact:
        return False
    return bool(re.search(
        r"(?:Y类基金份额)[^。；;！？!?]{0,32}"
        r"(?:不得|不允许|暂不允许|不能|不可)[^。；;！？!?]{0,32}转换",
        compact))


def _semantic_delete_sentences(rule_id: str, text: str) -> list[str]:
    pattern = _DELETE_SEMANTIC_PROBES.get(rule_id)
    if pattern is None:
        return []
    sentences: list[str] = []
    for sentence in re.split(r"(?<=[。；;！？!?])", text or ""):
        candidate = sentence.strip()
        if len(_compact(candidate)) < 12 or not pattern.search(candidate):
            continue
        if rule_id == "G06" and _is_one_way_y_class_conversion(candidate):
            continue
        if candidate not in sentences:
            sentences.append(candidate)
    # Contracts occasionally omit terminal punctuation at paragraph boundaries.
    # The split already includes an unterminated final sentence; do not re-probe the
    # whole paragraph (it could pair a class label with a distant conversion ban).
    return sentences


def _rule_scope_locations(scopes: Mapping[str, Any] | None,
                          rule_id: str) -> set[str] | None:
    """Physical locations a rule may inspect for ``ensure_delete_targets``.

    ``None`` means the caller supplied no scope information (legacy behaviour).
    An empty set means fail closed: the rule has no resolved physical scope, so a
    document-wide semantic scan is not allowed.
    """
    if scopes is None:
        return None
    scope = scopes.get(rule_id) if isinstance(scopes, Mapping) else None
    if scope is None:
        return set()
    return set(getattr(scope, "locations", ()) or ())


def ensure_delete_targets(targets: Sequence[Target], rules_by_id: dict[str, dict],
                           inspection: DocumentInspection, *, limit: int = 20,
                           scopes: Mapping[str, Any] | None = None,
                           cursor: int = 0,
                           page_info: dict[str, Any] | None = None) -> list[Target]:
    """Page through residual delete candidates instead of silently stopping.

    ``cursor``/``page_info`` let a caller continue past the per-call safety limit.
    When the page is full, ``has_more``/``next_cursor`` are reported so a long
    contract cannot lose its tail to a silent cap (FL-D441).
    """
    if cursor:
        everything = _ensure_delete_targets_page(
            targets, rules_by_id, inspection, limit=cursor + limit, scopes=scopes)
        page = everything[cursor:]
        has_more = len(everything) >= cursor + limit
    else:
        page = _ensure_delete_targets_page(
            targets, rules_by_id, inspection, limit=limit, scopes=scopes)
        has_more = len(page) >= limit
    if page_info is not None:
        page_info.update({"cursor": cursor, "returned": len(page),
                          "has_more": has_more,
                          "next_cursor": cursor + len(page) if has_more else None})
    return page


def _ensure_delete_targets_page(targets: Sequence[Target], rules_by_id: dict[str, dict],
                                inspection: DocumentInspection, *, limit: int = 20,
                                scopes: Mapping[str, Any] | None = None) -> list[Target]:
    """Create targets for delete-only sentences that no inventory/survey target covers.

    Inventory often binds only the head of a two-sentence clause; the tail then survives
    while the audit marks the deletion complete (D01 G17 p760, D03 G15 p751). This
    document-wide pass creates a deterministic target for every remaining copy of a
    delete sentence that carries the rule's domain anchor, so the planner deletes it.

    When ``scopes`` (``rule_id -> RuleScope``) is supplied, every candidate paragraph,
    G17 sentence proof and semantic probe is restricted to that rule's physical scope;
    a rule without a resolved scope gets no document-wide fallback.
    """
    if not targets and not rules_by_id:
        return []
    paragraphs = [span for span in inspection.paragraphs if span.text.strip()]
    g06_locations = g06_scope_locations(inspection)
    covered: dict[str, list[tuple[str, str]]] = {}
    for target in targets:
        if str(target.rule_id) not in _DELETE_SENTENCE_ANCHORS:
            continue
        if target.out_of_scope or target.attribution_error:
            continue
        locations = ([part.rsplit(":", 2)[0] for part in target.composite]
                     if target.composite else [target.location])
        for location in locations:
            covered.setdefault(target.rule_id, []).append(
                (location, _compact(target.quote)))
        # A composite target's quote often names only its first sentence.  The
        # later parts are still covered by that same operation; otherwise the
        # residual pass recreates a second target for the tail and merge_edits
        # reports a false same-operation overlap (D01/D16 G17).
        for part in target.composite:
            try:
                part_location, start_text, end_text = part.rsplit(":", 2)
                start_clean, end_clean = int(start_text), int(end_text)
                span = inspection.by_location(part_location)
                compact_body, _compact_map = compact_offsets(span.text)
                if 0 <= start_clean < end_clean <= len(compact_body):
                    covered.setdefault(target.rule_id, []).append(
                        (part_location, compact_body[start_clean:end_clean]))
            except (ValueError, KeyError, DocxError):
                continue
    created: list[Target] = []
    for rule_id, anchors in _DELETE_SENTENCE_ANCHORS.items():
        rule = rules_by_id.get(rule_id)
        if rule is None:
            continue
        allowed = _rule_scope_locations(scopes, rule_id)
        if allowed is not None and not allowed:
            # No resolved physical scope: fail closed instead of scanning the document.
            continue
        rule_paragraphs = ([span for span in paragraphs if str(span.location) in allowed]
                           if allowed is not None else paragraphs)
        operations = [operation for operation in (rule.get("operations") or [])
                      if isinstance(operation, dict) and operation.get("op") == "delete"]
        if not operations:
            continue
        if rule_id == "G17":
            # Coverage must describe an independently authorized source range.
            # A broad/failed inventory composite is not proof that its narrow
            # sentence (or a second body/summary occurrence) will be deleted.
            for operation_index, operation in enumerate(rule.get("operations") or []):
                if operation.get("op") != "delete":
                    continue
                key = _rule_operation_key(rule, operation_index)
                for parts in _g17_source_sentence_parts(inspection, [operation],
                                                        locations=allowed):
                    valid_ranges: list[tuple[str, int, int]] = []
                    for target in targets:
                        if (target.rule_id != rule_id or target.out_of_scope
                                or target.attribution_error or target.state != "needs_edit"
                                or (target.operations and key not in target.operations)):
                            continue
                        try:
                            if target.composite:
                                ranges = [(loc, int(left), int(right)) for loc, left, right in
                                          (part.rsplit(":", 2) for part in target.composite)]
                            elif target.start is not None and target.end is not None:
                                span = inspection.by_location(target.location)
                                ranges = [(target.location, len(_compact(span.text[:target.start])),
                                           len(_compact(span.text[:target.end])))]
                            else:
                                continue
                            owned = True
                            for loc, left, right in ranges:
                                span = inspection.by_location(loc)
                                body, offsets = compact_offsets(span.text)
                                if not 0 <= left < right <= len(body) or not _g17_source_effect_owned(
                                        inspection, loc, offsets[left], offsets[right - 1] + 1,
                                        "", [operation], locations=allowed):
                                    owned = False
                                    break
                        except (ValueError, KeyError, DocxError):
                            continue
                        if owned:
                            valid_ranges.extend(ranges)
                        elif any(loc == part_loc and max(left, part_left) < min(right, part_right)
                                 for loc, left, right in ranges
                                 for part_loc, part_left, part_right in parts):
                            target.out_of_scope = True
                            target.reason = f"{target.reason}|SUPERSEDED_BY_SOURCE_DELETE_SCOPE"
                    if all(any(loc == part_loc and left <= part_left < part_right <= right
                               for loc, left, right in valid_ranges)
                           for part_loc, part_left, part_right in parts):
                        continue
                    location, left, right = parts[0]
                    quote = "".join(compact_offsets(inspection.by_location(loc).text)[0][start:end]
                                    for loc, start, end in parts)
                    target = Target(f"DEL{len(created) + 1:03d}", rule_id, location,
                                    quote, "needs_edit", "delete_source_sentence",
                                    operations=(key,))
                    if len(parts) > 1:
                        target.composite = tuple(f"{loc}:{start}:{end}" for loc, start, end in parts)
                        target.resolution = "composite"
                    else:
                        span = inspection.by_location(location)
                        _, offsets = compact_offsets(span.text)
                        target.start, target.end = offsets[left], offsets[right - 1] + 1
                        target.resolution = "resolved"
                        target.segment_ok = containing_segment(span, target.start, target.end) is not None
                    created.append(target)
                    if len(created) >= limit:
                        return created
            continue
        sentences: list[str] = []
        for operation in operations:
            for sentence in re.split(r"(?<=[。；;])", str(operation.get("old_text") or "")):
                sentence = sentence.strip()
                if len(_compact(sentence)) < 8:
                    continue
                if not any(anchor in sentence for anchor in anchors):
                    continue
                if sentence not in sentences:
                    sentences.append(sentence)
        for sentence in sentences:
            probes = [sentence]
            stripped = re.sub(r"^[A-ZＡ-Ｚ]\s*类(?:基金份额)?的?", "",
                              sentence).strip()
            if stripped and stripped != sentence:
                probes.append(stripped)
            for probe in probes:
                for parts in find_old_text_all(rule_paragraphs, probe):
                    location = parts[0][0]
                    if rule_id == "G06":
                        permitted = allowed if allowed is not None else g06_locations
                        if not permitted or location not in permitted:
                            continue
                    already = any(item[0] == location and
                                  (_compact(probe) in item[1] or not item[1])
                                  for item in covered.get(rule_id, []))
                    if already:
                        continue
                    if len(parts) == 1:
                        span = inspection.by_location(location)
                        located = resolve_quote(span, probe)
                        if located is None:
                            continue
                        start, end = located
                        target = Target(target_id=f"DEL{len(created) + 1:03d}",
                                        rule_id=rule_id, location=location, quote=probe,
                                        state="needs_edit", reason="delete_residual_copy",
                                        start=start, end=end, resolution="resolved",
                                        segment_ok=containing_segment(span, start, end) is not None,
                                        operations=(operation_key(rule_id, 0),))
                    else:
                        target = Target(target_id=f"DEL{len(created) + 1:03d}",
                                        rule_id=rule_id, location=location, quote=probe,
                                        state="needs_edit", reason="delete_residual_copy",
                                        composite=tuple(f"{loc}:{start}:{end}"
                                                        for loc, start, end in parts),
                                        resolution="composite",
                                        operations=(operation_key(rule_id, 0),))
                    created.append(target)
                    covered.setdefault(rule_id, []).append((location, _compact(probe)))
                    if len(created) >= limit:
                        return created
        # Semantic fallback: scan every paragraph for an authorised business
        # signature even when all canonical/variant literals are absent.  This is
        # recall-first and produces a real source span; it never marks absence.
        for span in rule_paragraphs:
            if rule_id == "G06":
                permitted = allowed if allowed is not None else g06_locations
                if not permitted or span.location not in permitted:
                    continue
            for candidate in _semantic_delete_sentences(rule_id, str(span.text)):
                location = str(span.location)
                if any(item[0] == location and
                       (_compact(candidate) in item[1] or item[1] in _compact(candidate))
                       for item in covered.get(rule_id, [])):
                    continue
                located = resolve_quote(span, candidate)
                if located is None:
                    continue
                start, end = located
                created.append(Target(
                    target_id=f"DEL{len(created) + 1:03d}", rule_id=rule_id,
                    location=location, quote=candidate, state="needs_edit",
                    reason="delete_semantic_variant", start=start, end=end,
                    resolution="resolved",
                    segment_ok=containing_segment(span, start, end) is not None,
                    operations=(operation_key(rule_id, 0),)))
                covered.setdefault(rule_id, []).append((location, _compact(candidate)))
                if len(created) >= limit:
                    return created
    return created
