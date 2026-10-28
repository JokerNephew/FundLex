"""Versioned source evidence, semantic approvals and coverage accounting.

Plan: ``docs/SEMANTIC_ENGINE_REMEDIATION_EXECUTION_PLAN_20261028.md`` (R01-R03,
R12, S1).  The module is deliberately free of model/network access: it only
records *what a model claimed* next to *what code could verify*, so that later
stages consume one approval record instead of re-running their own word lists.

Invariants enforced here:

* a source quote is verified against a concrete document hash and a concrete
  paragraph projection; a stale hash or shifted offset is never accepted;
* an approval is bound to one guide identity, one rule/operation and one scope
  revision, and can only be consumed in the ``approved`` state;
* the raw model claim (``claimed_operations``/inventory answer) is *not* an
  approval: :func:`approval_from_target` re-verifies the quote and the scope
  binding before it produces one;
* coverage is accounted explicitly, so "not looked at" can never be reported as
  "nothing to do".
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

from .docx import BARRIER

SCHEMA_VERSION = "semantic-evidence-v1"
#: Offsets in :class:`EvidencePart` are measured in this projection: barrier
#: markers removed, whitespace and punctuation preserved.  ``display_text``
#: returns the index map needed to convert them back to raw span offsets.
PROJECTION = "safe_text_v1"

APPROVAL_STATES = ("candidate", "source_bound", "approved", "rejected", "unresolved")
COVERAGE_STATES = ("complete", "partial", "not_started")

_ELLIPSIS = re.compile(r"…|\.{3,}|⋯")
_NORMAL = re.compile(r"\s+")


def _display_text(value: str) -> tuple[str, list[int]]:
    """Same projection as ``recall.display_text`` without importing recall.

    Importing ``recall`` here would create a cycle (recall consumes this module),
    so the two-line barrier strip is duplicated with an explicit note.
    """
    chars: list[str] = []
    index: list[int] = []
    for position, char in enumerate(value):
        if char == BARRIER:
            continue
        chars.append(char)
        index.append(position)
    return "".join(chars), index


class EvidenceError(ValueError):
    """Raised when an evidence object cannot be built from the real source."""

    def __init__(self, code: str, detail: Any = None) -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class EvidencePart:
    """One exact source slice inside a single paragraph."""

    location: str
    start: int
    end: int
    exact_quote: str

    def as_dict(self) -> dict[str, Any]:
        return {"location": self.location, "start": self.start, "end": self.end,
                "exact_quote": self.exact_quote}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidencePart":
        return cls(str(value["location"]), int(value["start"]), int(value["end"]),
                   str(value["exact_quote"]))


@dataclass(frozen=True)
class EvidenceRef:
    """A verified source reference: one or more exact parts of one document."""

    evidence_id: str
    source_sha256: str
    parts: tuple[EvidencePart, ...]
    schema_version: str = SCHEMA_VERSION
    projection: str = PROJECTION
    occurrence_index: int = 0
    context_sha256: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"evidence_id": self.evidence_id, "source_sha256": self.source_sha256,
                "parts": [part.as_dict() for part in self.parts],
                "schema_version": self.schema_version, "projection": self.projection,
                "occurrence_index": self.occurrence_index,
                "context_sha256": self.context_sha256}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "EvidenceRef":
        if str(value.get("schema_version") or "") != SCHEMA_VERSION:
            raise EvidenceError("EVIDENCE_SCHEMA_UNSUPPORTED",
                                {"schema_version": value.get("schema_version")})
        return cls(str(value["evidence_id"]), str(value["source_sha256"]),
                   tuple(EvidencePart.from_dict(part) for part in value["parts"]),
                   str(value.get("schema_version") or SCHEMA_VERSION),
                   str(value.get("projection") or PROJECTION),
                   int(value.get("occurrence_index") or 0),
                   str(value.get("context_sha256") or ""))

    @property
    def text(self) -> str:
        return "".join(part.exact_quote for part in self.parts)

    def verify(self, inspection: Any) -> tuple[bool, str]:
        """Return ``(ok, code)``; never raise for a malformed/stale reference."""
        if not self.parts:
            return False, "EVIDENCE_EMPTY"
        if str(getattr(inspection, "source_sha256", "")) != self.source_sha256:
            return False, "EVIDENCE_SOURCE_MISMATCH"
        for part in self.parts:
            if part.start < 0 or part.end <= part.start:
                return False, "EVIDENCE_OFFSET_INVALID"
            if not part.exact_quote or _ELLIPSIS.search(part.exact_quote):
                return False, "EVIDENCE_QUOTE_NOT_LITERAL"
            try:
                span = inspection.by_location(part.location)
            except Exception:
                return False, "EVIDENCE_LOCATION_NOT_FOUND"
            body, _ = _display_text(str(span.text))
            if body[part.start:part.end] != part.exact_quote:
                return False, "EVIDENCE_QUOTE_MISMATCH"
        return True, ""

    def compact(self) -> str:
        return _NORMAL.sub("", self.text)


def _context_digest(inspection: Any, locations: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for location in locations:
        try:
            span = inspection.by_location(location)
        except Exception:
            continue
        digest.update(str(location).encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(span.text).encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def evidence_from_span(evidence_id: str, inspection: Any, location: str, *,
                       quote: str = "", start: int | None = None,
                       end: int | None = None,
                       occurrence_index: int = 0) -> EvidenceRef:
    """Build evidence for an exact slice of one real paragraph.

    ``quote`` is located in the safe-text projection when offsets are omitted;
    ``occurrence_index`` selects among identical occurrences instead of
    deduplicating by quote text.
    """
    span = inspection.by_location(location)
    body, _ = _display_text(str(span.text))
    if start is None or end is None:
        if not quote:
            raise EvidenceError("EVIDENCE_QUOTE_REQUIRED", {"location": location})
        needle = str(quote)
        positions = [match.start() for match in re.finditer(re.escape(needle), body)]
        if not positions:
            raise EvidenceError("EVIDENCE_QUOTE_NOT_FOUND",
                                {"location": location, "quote": needle[:120]})
        if occurrence_index >= len(positions):
            raise EvidenceError("EVIDENCE_OCCURRENCE_OUT_OF_RANGE",
                                {"location": location, "occurrence_index": occurrence_index,
                                 "occurrences": len(positions)})
        start = positions[occurrence_index]
        end = start + len(needle)
        quote = body[start:end]
    quote = body[start:end] if not quote else quote
    if body[start:end] != quote:
        raise EvidenceError("EVIDENCE_QUOTE_MISMATCH",
                            {"location": location, "start": start, "end": end})
    part = EvidencePart(location, int(start), int(end), quote)
    return EvidenceRef(evidence_id, str(inspection.source_sha256), (part,),
                       occurrence_index=occurrence_index,
                       context_sha256=_context_digest(inspection, [location]))


def evidence_from_composite(evidence_id: str, inspection: Any,
                            parts: Sequence[Mapping[str, Any]]) -> EvidenceRef:
    """Build evidence for ``{"location","start","end"}`` parts (safe offsets)."""
    built: list[EvidencePart] = []
    for part in parts:
        location = str(part["location"])
        span = inspection.by_location(location)
        body, _ = _display_text(str(span.text))
        start, end = int(part["start"]), int(part["end"])
        if start < 0 or end <= start:
            raise EvidenceError("EVIDENCE_OFFSET_INVALID", {"location": location})
        built.append(EvidencePart(location, start, end, body[start:end]))
    if not built:
        raise EvidenceError("EVIDENCE_EMPTY", {})
    return EvidenceRef(evidence_id, str(inspection.source_sha256), tuple(built),
                       context_sha256=_context_digest(
                           inspection, [part.location for part in built]))


@dataclass(frozen=True)
class AssessmentRef:
    """Traceable record of one model judgement (claim or independent review)."""

    assessment_id: str
    task_type: str
    decision: str
    model_role: str = ""
    model_id: str = ""
    prompt_version: str = ""
    context_sha256: str = ""
    independent: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {"assessment_id": self.assessment_id, "task_type": self.task_type,
                "decision": self.decision, "model_role": self.model_role,
                "model_id": self.model_id, "prompt_version": self.prompt_version,
                "context_sha256": self.context_sha256,
                "independent": self.independent}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "AssessmentRef":
        return cls(str(value["assessment_id"]), str(value.get("task_type") or ""),
                   str(value.get("decision") or ""),
                   str(value.get("model_role") or ""), str(value.get("model_id") or ""),
                   str(value.get("prompt_version") or ""),
                   str(value.get("context_sha256") or ""),
                   bool(value.get("independent", False)))


@dataclass(frozen=True)
class ApprovalCheck:
    ok: bool
    code: str = ""
    detail: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "code": self.code, "detail": dict(self.detail)}


@dataclass(frozen=True)
class SemanticApproval:
    """What one operation may change, with the evidence that justifies it."""

    approval_id: str
    guide_id: str
    guide_sha256: str
    rule_id: str
    operation_key: str
    evidence: tuple[EvidenceRef, ...]
    scope_id: str = ""
    scope_revision: str = ""
    condition_digest: str = ""
    semantic_role: str = ""
    append_anchor: str = ""
    fact_refs: tuple[str, ...] = ()
    assessments: tuple[AssessmentRef, ...] = ()
    state: str = "candidate"
    reason: str = ""
    schema_version: str = SCHEMA_VERSION

    def as_dict(self) -> dict[str, Any]:
        return {"approval_id": self.approval_id, "guide_id": self.guide_id,
                "guide_sha256": self.guide_sha256, "rule_id": self.rule_id,
                "operation_key": self.operation_key,
                "evidence": [item.as_dict() for item in self.evidence],
                "scope_id": self.scope_id, "scope_revision": self.scope_revision,
                "condition_digest": self.condition_digest,
                "semantic_role": self.semantic_role, "append_anchor": self.append_anchor,
                "fact_refs": list(self.fact_refs),
                "assessments": [item.as_dict() for item in self.assessments],
                "state": self.state, "reason": self.reason,
                "schema_version": self.schema_version}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SemanticApproval":
        if str(value.get("schema_version") or "") != SCHEMA_VERSION:
            raise EvidenceError("APPROVAL_SCHEMA_UNSUPPORTED",
                                {"schema_version": value.get("schema_version")})
        return cls(str(value["approval_id"]), str(value["guide_id"]),
                   str(value["guide_sha256"]), str(value["rule_id"]),
                   str(value["operation_key"]),
                   tuple(EvidenceRef.from_dict(item) for item in value["evidence"]),
                   str(value.get("scope_id") or ""),
                   str(value.get("scope_revision") or ""),
                   str(value.get("condition_digest") or ""),
                   str(value.get("semantic_role") or ""),
                   str(value.get("append_anchor") or ""),
                   tuple(str(item) for item in value.get("fact_refs") or ()),
                   tuple(AssessmentRef.from_dict(item)
                         for item in value.get("assessments") or ()),
                   str(value.get("state") or "candidate"),
                   str(value.get("reason") or ""),
                   str(value.get("schema_version") or SCHEMA_VERSION))

    # -- state transitions -------------------------------------------------
    def bind_sources(self) -> "SemanticApproval":
        return replace(self, state="source_bound")

    def approve(self, *, reason: str = "") -> "SemanticApproval":
        return replace(self, state="approved", reason=reason or self.reason)

    def reject(self, reason: str) -> "SemanticApproval":
        return replace(self, state="rejected", reason=reason)

    def leave_unresolved(self, reason: str) -> "SemanticApproval":
        return replace(self, state="unresolved", reason=reason)

    # -- consumption -------------------------------------------------------
    def check(self, inspection: Any, *, guide_id: str = "", guide_sha256: str = "",
              operation_keys: Iterable[str] | None = None, scope_id: str = "",
              scope_revision: str = "") -> ApprovalCheck:
        if self.state != "approved":
            return ApprovalCheck(False, "APPROVAL_NOT_APPROVED", {"state": self.state})
        if guide_id and self.guide_id != guide_id:
            return ApprovalCheck(False, "APPROVAL_GUIDE_MISMATCH",
                                 {"expected": guide_id, "actual": self.guide_id})
        if guide_sha256 and self.guide_sha256 != guide_sha256:
            return ApprovalCheck(False, "APPROVAL_GUIDE_STALE",
                                 {"expected": guide_sha256, "actual": self.guide_sha256})
        if operation_keys is not None:
            allowed = {str(key) for key in operation_keys}
            if allowed and self.operation_key not in allowed:
                return ApprovalCheck(False, "APPROVAL_OPERATION_MISMATCH",
                                     {"expected": sorted(allowed),
                                      "actual": self.operation_key})
        if scope_id and self.scope_id and self.scope_id != scope_id:
            return ApprovalCheck(False, "APPROVAL_SCOPE_MISMATCH",
                                 {"expected": scope_id, "actual": self.scope_id})
        if scope_revision and self.scope_revision \
                and self.scope_revision != scope_revision:
            return ApprovalCheck(False, "APPROVAL_SCOPE_STALE",
                                 {"expected": scope_revision,
                                  "actual": self.scope_revision})
        if not self.evidence:
            return ApprovalCheck(False, "APPROVAL_EVIDENCE_MISSING", {})
        for item in self.evidence:
            ok, code = item.verify(inspection)
            if not ok:
                return ApprovalCheck(False, code,
                                     {"approval_id": self.approval_id,
                                      "evidence_id": item.evidence_id})
        return ApprovalCheck(True)


class ApprovalBook:
    """Approvals available to the current run, keyed by target/operation."""

    def __init__(self, approvals: Iterable[SemanticApproval] = ()) -> None:
        self._by_id: dict[str, SemanticApproval] = {}
        for approval in approvals:
            self.add(approval)

    def add(self, approval: SemanticApproval) -> SemanticApproval:
        self._by_id[approval.approval_id] = approval
        return approval

    def get(self, approval_id: str) -> SemanticApproval | None:
        return self._by_id.get(str(approval_id or ""))

    def __len__(self) -> int:
        return len(self._by_id)

    def values(self) -> tuple[SemanticApproval, ...]:
        return tuple(self._by_id.values())

    def for_operation(self, rule_id: str, operation_key: str) -> tuple[SemanticApproval, ...]:
        return tuple(item for item in self._by_id.values()
                     if item.rule_id == rule_id and item.operation_key == operation_key)

    def allows(self, target: Any, inspection: Any, *, guide_id: str = "",
               guide_sha256: str = "", scope_revision: str = "") -> ApprovalCheck:
        """Check the approval attached to ``target`` (empty id = no approval)."""
        approval_id = str(getattr(target, "approval_id", "") or "")
        if not approval_id:
            return ApprovalCheck(False, "APPROVAL_MISSING", {})
        approval = self.get(approval_id)
        if approval is None:
            return ApprovalCheck(False, "APPROVAL_UNKNOWN", {"approval_id": approval_id})
        operations = tuple(str(key) for key in
                           (getattr(target, "operations", ()) or ()))
        return approval.check(inspection, guide_id=guide_id,
                              guide_sha256=guide_sha256,
                              operation_keys=operations or None,
                              scope_id=str(getattr(target, "scope_id", "") or ""),
                              scope_revision=scope_revision)

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION,
                "approvals": [item.as_dict() for item in self._by_id.values()]}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ApprovalBook":
        return cls(SemanticApproval.from_dict(item)
                   for item in (value or {}).get("approvals") or ())


def approval_from_target(approval_id: str, target: Any, inspection: Any, *,
                         guide_id: str, guide_sha256: str,
                         semantic_role: str = "",
                         assessment: AssessmentRef | None = None,
                         scope_revision: str = "",
                         append_anchor: str = "") -> SemanticApproval:
    """Turn a code-verified target binding into an approved operation record.

    The inventory/locator claim alone is *not* trusted: the quote must exist at
    the bound offsets of the real source, the operation identity must be present
    and a physical scope must be recorded.  Anything else raises
    :class:`EvidenceError` and the caller keeps the failure visible.
    """
    operations = tuple(str(key) for key in (getattr(target, "operations", ()) or ()))
    if not operations:
        raise EvidenceError("APPROVAL_OPERATION_MISSING",
                            {"target": getattr(target, "target_id", "")})
    if len(operations) > 1:
        raise EvidenceError("APPROVAL_OPERATION_AMBIGUOUS",
                            {"target": getattr(target, "target_id", ""),
                             "operations": list(operations)})
    scope_id = str(getattr(target, "scope_id", "") or "")
    if not scope_id:
        raise EvidenceError("APPROVAL_SCOPE_MISSING",
                            {"target": getattr(target, "target_id", "")})
    parts: list[dict[str, Any]] = []
    composite = tuple(getattr(target, "composite", ()) or ())
    if composite:
        for part in composite:
            location, start, end = str(part).rsplit(":", 2)
            parts.append({"location": location, "start": int(start), "end": int(end)})
        evidence = evidence_from_composite(f"{approval_id}:source", inspection, parts)
    else:
        start = getattr(target, "start", None)
        end = getattr(target, "end", None)
        quote = str(getattr(target, "quote", "") or "")
        if start is None or end is None:
            evidence = evidence_from_span(f"{approval_id}:source", inspection,
                                          str(target.location), quote=quote)
        else:
            # Pass the claimed quote as well: offsets alone would "verify" whatever
            # happens to sit at those offsets, silently blessing a stale quote.
            evidence = evidence_from_span(f"{approval_id}:source", inspection,
                                          str(target.location), quote=quote,
                                          start=int(start), end=int(end))
    assessments = (assessment,) if assessment is not None else ()
    approval = SemanticApproval(
        approval_id=approval_id, guide_id=guide_id, guide_sha256=guide_sha256,
        rule_id=str(target.rule_id), operation_key=operations[0],
        evidence=(evidence,), scope_id=scope_id, scope_revision=scope_revision,
        semantic_role=semantic_role or str(getattr(target, "state", "") or ""),
        append_anchor=append_anchor, assessments=assessments, state="approved")
    return approval


@dataclass(frozen=True)
class CoverageRecord:
    """Explicit accounting of what a pass did and did not examine."""

    pass_name: str
    total_units: int = 0
    visited_units: int = 0
    cursor: str = ""
    has_more: bool = False
    limit_reached: str = ""
    unreadable: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def state(self) -> str:
        if self.total_units and self.visited_units >= self.total_units and not self.has_more:
            return "complete"
        if not self.visited_units:
            return "not_started"
        return "partial"

    @property
    def remaining(self) -> int:
        return max(0, self.total_units - self.visited_units)

    def as_dict(self) -> dict[str, Any]:
        return {"pass_name": self.pass_name, "total_units": self.total_units,
                "visited_units": self.visited_units, "remaining": self.remaining,
                "cursor": self.cursor, "has_more": self.has_more,
                "limit_reached": self.limit_reached,
                "unreadable": list(self.unreadable), "notes": list(self.notes),
                "state": self.state}

    def mark_visited(self, count: int = 1) -> "CoverageRecord":
        return replace(self, visited_units=min(self.total_units or 10 ** 9,
                                               self.visited_units + count))

    def next_page(self, *, cursor: str, has_more: bool,
                  limit_reached: str = "") -> "CoverageRecord":
        return replace(self, cursor=cursor, has_more=has_more,
                       limit_reached=limit_reached)


def guide_fingerprint(rules: Sequence[Mapping[str, Any]]) -> str:
    """Deterministic identity of the compiled guide rules actually in force.

    Two guides that reuse a rule id (for example a custom guide with ``G01``) get
    different fingerprints, so an approval can never cross guide versions.
    """
    payload = json.dumps([dict(rule) for rule in rules], ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def coverage_complete(records: Iterable[CoverageRecord]) -> bool:
    """True only when every pass finished; partial passes block completion."""
    records = tuple(records)
    return bool(records) and all(record.state == "complete" for record in records)


def dumps(value: Any) -> str:
    """Stable JSON used for evidence/report hashing."""
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
