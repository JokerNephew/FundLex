"""Contracts for choosing the left or right side of a compare result.

This module deliberately contains no persistence or DOCX writing.  It turns a
trusted Compare result into a deterministic selection snapshot and reports
whether that snapshot is complete and structurally eligible for a later writer.
The browser may submit only diff ids and the two supported decisions; it never
gets to submit replacement text.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence


DECISIONS = frozenset({"pending", "left", "right"})
EXPLICIT_DECISIONS = frozenset({"left", "right"})
DIFF_TYPES = frozenset({"modify", "insert", "delete"})


class SelectionError(ValueError):
    """A client or result selection contract violation.

    ``code`` is stable enough for the API layer and ``details`` is safe to
    expose as structured information in a validation response.
    """

    def __init__(self, code: str, detail: str = "", *, details: Sequence[Mapping[str, Any]] = ()):
        self.code = code
        self.details = tuple(dict(item) for item in details)
        message = detail or code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class SelectionIssue:
    code: str
    detail: str
    diff_ids: tuple[str, ...] = ()
    blocking: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "detail": self.detail,
            "diff_ids": list(self.diff_ids),
            "blocking": self.blocking,
        }


@dataclass(frozen=True)
class SelectionAssessment:
    """Deterministic state and generation blockers for one Compare result."""

    decisions: tuple[tuple[str, str], ...]
    pending_ids: tuple[str, ...]
    counts: Mapping[str, int]
    issues: tuple[SelectionIssue, ...]
    result_sha256: str = ""
    left_source_sha256: str = ""
    right_source_sha256: str = ""

    @property
    def can_generate(self) -> bool:
        return not self.pending_ids and not any(issue.blocking for issue in self.issues)

    @property
    def decision_map(self) -> dict[str, str]:
        return dict(self.decisions)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": dict(self.decisions),
            "pending_ids": list(self.pending_ids),
            "counts": dict(self.counts),
            "issues": [issue.to_dict() for issue in self.issues],
            "can_generate": self.can_generate,
            "result_sha256": self.result_sha256,
            "left_source_sha256": self.left_source_sha256,
            "right_source_sha256": self.right_source_sha256,
        }


@dataclass(frozen=True)
class SelectionSnapshot:
    """The version-bound selection input consumed by a future writer."""

    selection_epoch: int
    result_sha256: str
    left_source_sha256: str
    right_source_sha256: str
    decisions: tuple[tuple[str, str], ...]
    decision_hash: str
    binding_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selection_epoch": self.selection_epoch,
            "result_sha256": self.result_sha256,
            "left_source_sha256": self.left_source_sha256,
            "right_source_sha256": self.right_source_sha256,
            "decisions": dict(self.decisions),
            "decision_hash": self.decision_hash,
            "binding_hash": self.binding_hash,
        }


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _diff_id(diff: Any) -> str:
    if isinstance(diff, Mapping):
        return diff.get("id", "")
    return getattr(diff, "diff_id", "")


def _diff_type(diff: Any) -> str:
    if isinstance(diff, Mapping):
        return str(diff.get("type", ""))
    return str(getattr(diff, "type", ""))


def _diffs(result_or_diffs: Any) -> tuple[Any, ...]:
    if isinstance(result_or_diffs, Mapping):
        values = result_or_diffs.get("diffs")
        if not isinstance(values, list):
            raise SelectionError("COMPARE_RESULT_INVALID", "result diffs must be a list")
        return tuple(values)
    values = getattr(result_or_diffs, "diffs", result_or_diffs)
    if isinstance(values, (str, bytes, bytearray)):
        raise SelectionError("COMPARE_RESULT_INVALID", "result diffs must be iterable")
    try:
        return tuple(values)
    except TypeError as exc:
        raise SelectionError("COMPARE_RESULT_INVALID", "result diffs must be iterable") from exc


def _source_hashes(result_or_diffs: Any) -> tuple[str, str]:
    if isinstance(result_or_diffs, Mapping):
        left = result_or_diffs.get("left") or {}
        right = result_or_diffs.get("right") or {}
    else:
        left = getattr(result_or_diffs, "left", None)
        right = getattr(result_or_diffs, "right", None)
    def get(value: Any) -> str:
        if isinstance(value, Mapping):
            return str(value.get("sha256", ""))
        return str(getattr(value, "source_sha256", ""))
    return get(left), get(right)


def _side_spans(diff: Any, side: str) -> tuple[Any, ...]:
    name = f"{side}_spans"
    if isinstance(diff, Mapping):
        values = diff.get(name)
        if values is not None:
            if not isinstance(values, list):
                raise SelectionError("COMPARE_RESULT_INVALID", f"{name} must be a list")
            primary = diff.get(side)
            if primary is not None and (not values or primary != values[0]):
                raise SelectionError("COMPARE_RESULT_INVALID", "primary span differs from span list")
            return tuple(values)
        value = diff.get(side)
    else:
        values = getattr(diff, name, ())
        if values:
            return tuple(values)
        value = getattr(diff, side, None)
    return (value,) if value is not None else ()


def _span_value(span: Any, name: str, default: Any = None) -> Any:
    if isinstance(span, Mapping):
        return span.get(name, default)
    return getattr(span, name, default)


def _anchor(diff: Any, side: str) -> Any:
    if isinstance(diff, Mapping):
        return diff.get(f"{side}_anchor")
    return getattr(diff, f"{side}_anchor", None)


def _validate_span_shape(span: Any, *, anchor: bool) -> tuple[str, int, int]:
    block_id = _span_value(span, "block_id")
    start = _span_value(span, "start")
    end = _span_value(span, "end")
    text = _span_value(span, "text")
    if not isinstance(block_id, str) or not block_id:
        raise SelectionError("COMPARE_RESULT_INVALID", "span block_id is required")
    if type(start) is not int or type(end) is not int or start < 0 or end < start:
        raise SelectionError("COMPARE_RESULT_INVALID", "span offsets are invalid")
    if not isinstance(text, str):
        raise SelectionError("COMPARE_RESULT_INVALID", "span text is invalid")
    if anchor and (start != end or text):
        raise SelectionError("COMPARE_RESULT_INVALID", "anchor must be empty")
    if not anchor and end <= start:
        raise SelectionError("COMPARE_RESULT_INVALID", "visible span must not be empty")
    if not anchor and len(text) != end - start:
        raise SelectionError("COMPARE_RESULT_INVALID", "span length differs from text length")
    return block_id, start, end


def _validate_result(diffs: tuple[Any, ...]) -> tuple[tuple[str, ...], tuple[SelectionIssue, ...]]:
    ids: list[str] = []
    issues: list[SelectionIssue] = []
    seen: set[str] = set()
    by_side: dict[str, list[tuple[str, str, int, int]]] = {"left": [], "right": []}
    for diff in diffs:
        diff_id = _diff_id(diff)
        kind = _diff_type(diff)
        if not isinstance(diff_id, str) or not diff_id.strip() or diff_id in seen:
            raise SelectionError("COMPARE_RESULT_INVALID", "diff ids must be unique and non-empty")
        seen.add(diff_id)
        ids.append(diff_id)
        if kind not in DIFF_TYPES:
            raise SelectionError("COMPARE_RESULT_INVALID", f"unsupported diff type for {diff_id}")
        spans_by_side = {side: _side_spans(diff, side) for side in ("left", "right")}
        for side, spans in spans_by_side.items():
            for span in spans:
                block_id, start, end = _validate_span_shape(span, anchor=False)
                by_side[side].append((block_id, diff_id, start, end))
            anchor = _anchor(diff, side)
            if anchor is not None:
                _validate_span_shape(anchor, anchor=True)
            if (spans and anchor is not None) or (not spans and anchor is None):
                raise SelectionError("COMPARE_RESULT_INVALID", "empty side requires an exclusive anchor")
        left_present = bool(spans_by_side["left"])
        right_present = bool(spans_by_side["right"])
        expected = {
            "modify": (True, True),
            "insert": (False, True),
            "delete": (True, False),
        }[kind]
        if (left_present, right_present) != expected:
            raise SelectionError("COMPARE_RESULT_INVALID", f"{kind} sides are malformed for {diff_id}")
        # A multi-block span is still one decision.  The writer performs the
        # real structural eligibility check; preview must not reject every
        # paragraph split/merge before the writer has a chance to inspect it.
        for side, spans in spans_by_side.items():
            block_ids = {str(_span_value(span, "block_id")) for span in spans}
            if len(block_ids) > 1:
                issues.append(SelectionIssue(
                    "MULTI_BLOCK_DIFF", f"{side} 侧差异跨越多个文档块，生成时将校验块级结构。",
                    (diff_id,), blocking=False))
    # Detect overlap independently of the browser's display projection.  The
    # stored compare result should already reject this, but selection must stay
    # safe when called directly with an untrusted result payload.
    for side, spans in by_side.items():
        previous: dict[str, tuple[str, int, int]] = {}
        for block_id, diff_id, start, end in sorted(spans, key=lambda item: (item[0], item[2], item[3], item[1])):
            prior = previous.get(block_id)
            if prior and start < prior[2]:
                issues.append(SelectionIssue(
                    "OVERLAPPING_DIFFS", f"{side} 侧差异范围重叠，不能安全独立选择。",
                    tuple(sorted({prior[0], diff_id}))))
            if not prior or end > prior[2]:
                previous[block_id] = (diff_id, start, end)
    # Keep issues deterministic and do not repeat the same overlap pair.
    unique: dict[tuple[str, tuple[str, ...]], SelectionIssue] = {}
    for issue in issues:
        unique[(issue.code, issue.diff_ids)] = issue
    return tuple(ids), tuple(unique.values())


def _decision_items(decisions: Mapping[str, str] | Iterable[tuple[str, str]]) -> tuple[tuple[str, str], ...]:
    if isinstance(decisions, Mapping):
        values = list(decisions.items())
    else:
        try:
            values = list(decisions)
        except TypeError as exc:
            raise SelectionError("INVALID_DECISIONS", "decisions must be a mapping or pairs") from exc
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for item in values:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise SelectionError("INVALID_DECISIONS", "each decision must be a diff id and choice")
        diff_id, choice = item
        if not isinstance(diff_id, str) or not diff_id.strip():
            raise SelectionError("INVALID_DECISIONS", "diff id is required")
        if not isinstance(choice, str) or choice not in DECISIONS:
            raise SelectionError("INVALID_DECISIONS", f"invalid choice for {diff_id}")
        if diff_id in seen:
            code = "CONFLICTING_DECISION" if any(x == diff_id and y != choice for x, y in out) else "DUPLICATE_DECISION"
            raise SelectionError(code, f"duplicate decision for {diff_id}")
        seen.add(diff_id)
        out.append((diff_id, choice))
    return tuple(sorted(out))


def normalize_decisions(result_or_diffs: Any,
                        decisions: Mapping[str, str] | Iterable[tuple[str, str]] = ()) -> dict[str, str]:
    """Return a complete, sorted decision map with omitted ids as pending."""
    diffs = _diffs(result_or_diffs)
    ids, _ = _validate_result(diffs)
    supplied = dict(_decision_items(decisions))
    unknown = sorted(set(supplied) - set(ids))
    if unknown:
        raise SelectionError("UNKNOWN_DIFF_ID", "decision references an unknown diff", details=(
            {"diff_ids": unknown},))
    return {diff_id: supplied.get(diff_id, "pending") for diff_id in ids}


def decision_hash(decisions: Mapping[str, str] | Iterable[tuple[str, str]]) -> str:
    """Hash only the canonical decision map, independent of input order."""
    canonical = dict(_decision_items(decisions))
    return _digest(canonical)


def binding_hash(*, result_sha256: str, left_source_sha256: str,
                 right_source_sha256: str, selection_epoch: int,
                 decisions: Mapping[str, str] | Iterable[tuple[str, str]]) -> str:
    """Hash the immutable result/source identity and the selection version."""
    if type(selection_epoch) is not int or selection_epoch < 0:
        raise SelectionError("INVALID_SELECTION_EPOCH", "selection epoch must be a non-negative integer")
    values = dict(_decision_items(decisions))
    return _digest({
        "result_sha256": str(result_sha256),
        "left_source_sha256": str(left_source_sha256),
        "right_source_sha256": str(right_source_sha256),
        "selection_epoch": selection_epoch,
        "decisions": values,
    })


def assess_selection(result_or_diffs: Any,
                     decisions: Mapping[str, str] | Iterable[tuple[str, str]] = (),
                     *, result_sha256: str = "") -> SelectionAssessment:
    """Validate a result and return counts, pending ids and safe blockers."""
    diffs = _diffs(result_or_diffs)
    ids, issues = _validate_result(diffs)
    supplied = _decision_items(decisions)
    supplied_map = dict(supplied)
    unknown = sorted(set(supplied_map) - set(ids))
    if unknown:
        raise SelectionError("UNKNOWN_DIFF_ID", "decision references an unknown diff", details=(
            {"diff_ids": unknown},))
    full = tuple((diff_id, supplied_map.get(diff_id, "pending")) for diff_id in ids)
    pending = tuple(diff_id for diff_id, choice in full if choice == "pending")
    counts = {choice: sum(value == choice for _, value in full) for choice in ("pending", "left", "right")}
    left_hash, right_hash = _source_hashes(result_or_diffs)
    return SelectionAssessment(full, pending, counts, issues, str(result_sha256), left_hash, right_hash)


def require_generation_ready(result_or_diffs: Any,
                             decisions: Mapping[str, str] | Iterable[tuple[str, str]] = (),
                             *, result_sha256: str = "") -> SelectionAssessment:
    assessment = assess_selection(result_or_diffs, decisions, result_sha256=result_sha256)
    if assessment.pending_ids:
        raise SelectionError("PENDING_SELECTIONS", "all differences require an explicit left or right choice",
                              details=({"diff_ids": list(assessment.pending_ids)},))
    blocking = [issue.to_dict() for issue in assessment.issues if issue.blocking]
    if blocking:
        raise SelectionError("SELECTION_UNSUPPORTED", "selection contains unsupported document structure",
                              details=blocking)
    return assessment


def make_snapshot(result_or_diffs: Any, decisions: Mapping[str, str] | Iterable[tuple[str, str]], *,
                  selection_epoch: int, result_sha256: str = "") -> SelectionSnapshot:
    assessment = require_generation_ready(result_or_diffs, decisions, result_sha256=result_sha256)
    if type(selection_epoch) is not int or selection_epoch < 0:
        raise SelectionError("INVALID_SELECTION_EPOCH", "selection epoch must be a non-negative integer")
    values = assessment.decisions
    return SelectionSnapshot(
        selection_epoch=selection_epoch,
        result_sha256=assessment.result_sha256,
        left_source_sha256=assessment.left_source_sha256,
        right_source_sha256=assessment.right_source_sha256,
        decisions=values,
        decision_hash=decision_hash(values),
        binding_hash=binding_hash(result_sha256=assessment.result_sha256,
                                  left_source_sha256=assessment.left_source_sha256,
                                  right_source_sha256=assessment.right_source_sha256,
                                  selection_epoch=selection_epoch,
                                  decisions=values),
    )


__all__ = [
    "DECISIONS", "EXPLICIT_DECISIONS", "SelectionError", "SelectionIssue",
    "SelectionAssessment", "SelectionSnapshot", "assess_selection",
    "binding_hash", "decision_hash", "make_snapshot", "normalize_decisions",
    "require_generation_ready",
]
