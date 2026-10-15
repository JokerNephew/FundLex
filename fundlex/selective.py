"""Selective accept/reject of FundLex revision marks.

The engine publishes a *redline* artifact whose ``w:ins`` / ``w:del`` wrappers
carry the ids recorded in the generation manifest (``del_id = 2n-1``,
``ins_id = 2n``). This module lets a user accept or reject each of those
revisions independently — mirroring exactly what "accept/reject a single
revision" does in Word — and writes a new, separately validated artifact.

Contract of the operations
--------------------------
For one edit pair ``(del, ins)`` covering a replaced span of text:

* ``accept`` — keep the engine's result: unwrap ``w:ins`` (its runs become
  ordinary runs) and drop the ``w:del`` block entirely.
* ``reject`` — restore the original text: drop the ``w:ins`` block (the new
  text disappears) and unwrap ``w:del``, converting its runs back from
  ``w:delText`` to ``w:t`` so Word renders them as normal text again.

Other ids never change. Rejecting an edit whose ``w:del`` is empty keeps the
text as-is; rejecting an edit whose ``w:ins`` is empty simply removes nothing.

This module is deliberately independent from :mod:`fundlex.docx`'s generator:
it only opens an already-generated revision artifact, so a bug here can never
corrupt the primary delivery artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from lxml import etree

from .docx import (
    DOCUMENT,
    Q,
    DocxError,
    ZipLimits,
    _read_parts,
    _sha,
    _validate_package,
    _validate_revision_manifest,
    _write_package,
    _xml,
)


ACCEPT = "accept"
REJECT = "reject"


@dataclass(frozen=True)
class SelectionResult:
    """Outcome of applying a decision set to one revision artifact."""

    accepted: tuple[int, ...]
    rejected: tuple[int, ...]
    absent: tuple[int, ...]
    path: str
    sha256: str


def _manifests_from_report(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Recover the generation manifest for a persisted report.

    Newer reports may carry ``revision_manifest`` verbatim. Older ones only
    persist the plan, so the same deterministic numbering used by
    :func:`fundlex.docx.generate_artifacts` is rebuilt here.
    """
    manifest = report.get("revision_manifest")
    if isinstance(manifest, list) and manifest:
        entries: list[dict[str, Any]] = []
        for item in manifest:
            if not isinstance(item, Mapping):
                continue
            try:
                del_id = int(item["del_id"])
                ins_id = int(item["ins_id"])
            except (KeyError, TypeError, ValueError):
                continue
            entries.append({"del_id": del_id, "ins_id": ins_id,
                            "location": str(item.get("location", "")),
                            "expected_old_text": str(item.get("expected_old_text", "")),
                            "replacement": str(item.get("replacement", ""))})
        if entries:
            return entries
    ordered = _ordered_edits(report)
    return [{"del_id": 2 * n - 1, "ins_id": 2 * n,
             "location": str(e.get("location", "")),
             "expected_old_text": _expected_old(e),
             "replacement": str(e.get("replacement", ""))}
            for n, e in enumerate(ordered, start=1)]


def _ordered_edits(report: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Plan edits in the generation order used for revision numbering."""
    plan = report.get("plan")
    edits = plan.get("edits") if isinstance(plan, Mapping) else None
    if not isinstance(edits, list):
        return []
    ordered = [e for e in edits if isinstance(e, Mapping)]
    try:
        ordered.sort(key=lambda e: (str(e.get("location", "")), -int(e.get("start") or 0)))
    except (TypeError, ValueError):
        pass
    return ordered


def _normalise_decisions(decisions: Mapping[Any, Any] | Iterable[Any]) -> dict[int, str]:
    """Accept ``{id: accept|reject}`` or ``{"accept": [...], "reject": [...]}``."""
    result: dict[int, str] = {}
    if isinstance(decisions, Mapping) and ("accept" in decisions or "reject" in decisions):
        for verdict, ids in (("accept", decisions.get("accept", ())), ("reject", decisions.get("reject", ()))):
            if isinstance(ids, (str, bytes)) or not isinstance(ids, Iterable):
                continue
            for raw in ids:
                number = _as_int(raw)
                if number is not None:
                    result[number] = verdict
        return result
    if isinstance(decisions, Mapping):
        for raw, verdict in decisions.items():
            number = _as_int(raw)
            if number is None:
                continue
            value = str(verdict).strip().lower()
            if value in {ACCEPT, REJECT}:
                result[number] = value
    return result


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _unwrap_revision(node: etree._Element, *, restoring_delete: bool) -> None:
    """Inline a revision wrapper's runs into its parent.

    ``restoring_delete`` converts ``w:delText`` back to ``w:t`` so rejected
    deletions read as ordinary text in Word.
    """
    parent = node.getparent()
    if parent is None:
        raise DocxError("REVISION_STRUCTURE_INVALID")
    index = parent.index(node)
    insertion = 0
    for run in list(node):
        if restoring_delete:
            for child in run:
                if child.tag == Q("delText"):
                    child.tag = Q("t")
        node.remove(run)
        parent.insert(index + insertion, run)
        insertion += 1
    parent.remove(node)


def apply_decisions(root: etree._Element, manifests: Sequence[Mapping[str, Any]],
                    decisions: Mapping[Any, Any] | Iterable[Any]) -> tuple[int, ...]:
    """Apply decisions in place and return the ids that were not found."""
    verdicts = _normalise_decisions(decisions)
    # Every id defaults to accept, matching "accept all" semantics.
    per_id: dict[str, str] = {}
    for item in manifests:
        for key, default_tag in (("del_id", "del"), ("ins_id", "ins")):
            try:
                rid = str(int(item[key]))
            except (KeyError, TypeError, ValueError):
                continue
            per_id[rid] = verdicts.get(int(rid), ACCEPT)
    seen: set[str] = set()
    for node in list(root.iter()):
        if node.tag not in {Q("ins"), Q("del")}:
            continue
        if node.getparent() is None:
            continue
        rid = node.get(Q("id"), "")
        if rid not in per_id or rid in seen:
            # A revision we did not generate: leave it untouched rather than
            # silently rewriting someone else's markup.
            continue
        seen.add(rid)
        verdict = per_id[rid]
        if node.tag == Q("del"):
            if verdict == ACCEPT:
                parent = node.getparent()
                if parent is None:
                    raise DocxError("REVISION_STRUCTURE_INVALID")
                parent.remove(node)
            else:
                _unwrap_revision(node, restoring_delete=True)
        else:  # w:ins
            if verdict == ACCEPT:
                _unwrap_revision(node, restoring_delete=False)
            else:
                parent = node.getparent()
                if parent is None:
                    raise DocxError("REVISION_STRUCTURE_INVALID")
                parent.remove(node)
    return tuple(int(rid) for rid in per_id if rid not in seen)


def _expected_old(edit: Mapping[str, Any]) -> str:
    value = edit.get("expected_old_text")
    if isinstance(value, str) and value:
        return value
    components = edit.get("components")
    if isinstance(components, list):
        return "".join(str(c.get("expected_old_text", ""))
                       for c in components if isinstance(c, Mapping))
    return ""


def generate_selected_artifact(redline: str | Path, target: str | Path,
                               report: Mapping[str, Any],
                               decisions: Mapping[Any, Any] | Iterable[Any],
                               *, limits: ZipLimits | None = None,
                               verify: bool = True) -> SelectionResult:
    """Write a new DOCX with only the selected revisions accepted.

    ``redline`` must be a revision artifact produced by the engine (it still
    contains the ``w:ins`` / ``w:del`` markup). The selected result is written
    to ``target`` and independently re-opened before it is published.
    """
    limits = limits or ZipLimits()
    redline, target = Path(redline), Path(target)
    if redline.resolve() == target.resolve():
        raise DocxError("OUTPUT_PATH_INVALID")
    manifests = _manifests_from_report(report)
    if not manifests:
        raise DocxError("REVISION_MANIFEST_UNAVAILABLE")
    parts = _read_parts(redline, limits)
    _validate_package(parts, limits, full=False)
    root = _xml(parts[DOCUMENT], limits)
    # Fail closed if the artifact does not match the expected manifest exactly.
    _validate_revision_manifest(root, manifests)
    absent = apply_decisions(root, manifests, decisions)
    document_xml = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
    verdicts = _normalise_decisions(decisions)
    accepted = tuple(sorted(2 * (i + 1) - 1 for i, _ in enumerate(manifests)
                            if verdicts.get(2 * (i + 1) - 1, ACCEPT) == ACCEPT))
    rejected = tuple(sorted(2 * (i + 1) - 1 for i, _ in enumerate(manifests)
                            if verdicts.get(2 * (i + 1) - 1, ACCEPT) == REJECT))
    try:
        _write_package(target, parts, document_xml)
        if verify:
            _verify_selection(target, manifests, decisions, limits)
        return SelectionResult(accepted=accepted, rejected=rejected, absent=absent,
                               path=str(target), sha256=_sha(target.read_bytes()))
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _verify_selection(path: Path, manifests: Sequence[Mapping[str, Any]],
                      decisions: Mapping[Any, Any] | Iterable[Any],
                      limits: ZipLimits) -> None:
    """Independent re-open: no managed revision markup may survive, and the
    package must still be a valid DOCX with an unchanged member set."""
    parts = _read_parts(path, limits)
    _validate_package(parts, limits, full=False)
    root = _xml(parts[DOCUMENT], limits)
    managed = {str(item[key]) for item in manifests for key in ("del_id", "ins_id")}
    leftover = {node.get(Q("id"), "") for node in root.iter()
                if node.tag in {Q("ins"), Q("del")} and node.get(Q("id"), "") in managed}
    if leftover:
        raise DocxError("SELECTED_REVISION_LEFTOVER")


def accept_all(redline: str | Path, report: Mapping[str, Any]) -> dict[Any, Any]:
    """Decision map that accepts every revision the engine produced."""
    return {int(item["del_id"]): ACCEPT for item in _manifests_from_report(report)} | {
        int(item["ins_id"]): ACCEPT for item in _manifests_from_report(report)}
