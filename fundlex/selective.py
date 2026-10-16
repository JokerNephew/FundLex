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
from tempfile import NamedTemporaryFile
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


def _explicit_verdicts(manifests: Sequence[Mapping[str, Any]],
                       decisions: Mapping[Any, Any] | Iterable[Any]) -> dict[int, str]:
    """Verdicts for the edits the caller actually named, spread over each pair.

    A caller (the workbench) addresses an edit by its ``del_id``, but the pair
    also owns an ``ins_id``. Rejecting only half of a replacement would leave the
    document holding both the original and the new wording, so every id of a pair
    takes the verdict given for either of its ids.

    Only edits the caller mentioned are returned. An edit left unmentioned has no
    entry, so callers can tell "accepted" apart from "no decision given" — the
    distinction the derived redline depends on.
    """
    named = _normalise_decisions(decisions)
    resolved: dict[int, str] = {}
    for item in manifests:
        ids = [_as_int(item.get(key)) for key in ("del_id", "ins_id")]
        ids = [rid for rid in ids if rid is not None]
        verdict = next((named[rid] for rid in ids if rid in named), None)
        if verdict is None:
            continue
        for rid in ids:
            resolved[rid] = verdict
    return resolved


def apply_decisions(root: etree._Element, manifests: Sequence[Mapping[str, Any]],
                    decisions: Mapping[Any, Any] | Iterable[Any]) -> tuple[int, ...]:
    """Apply decisions in place and return the ids that were not found.

    "Accept all" is the default: ids the caller never mentions are accepted, and
    every verdict is spread across the whole edit pair (see
    :func:`_explicit_verdicts`) so a rejection addresses both halves.
    """
    per_id: dict[str, str] = {}
    for item in manifests:
        for key in ("del_id", "ins_id"):
            rid = _as_int(item.get(key))
            if rid is not None:
                per_id[str(rid)] = ACCEPT
    per_id.update({str(rid): verdict
                   for rid, verdict in _explicit_verdicts(manifests, decisions).items()})
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


def _read_redline_parts(path: Path, limits: ZipLimits) -> dict[str, bytes]:
    """Read an artifact even when it lacks a ``.docx`` suffix.

    Stored artifacts keep their original upload name; ``_read_parts`` rejects
    non-``.docx`` paths as an upload guard, so stage a temporary copy.
    """
    if path.suffix.lower() == ".docx":
        return _read_parts(path, limits)
    with NamedTemporaryFile(prefix=".fundlex-redline-", suffix=".docx", delete=False) as temp:
        temporary = Path(temp.name)
        temp.write(path.read_bytes())
    try:
        return _read_parts(temporary, limits)
    finally:
        temporary.unlink(missing_ok=True)


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
    parts = _read_redline_parts(redline, limits)
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


def generate_selected_redline(redline: str | Path, target: str | Path,
                              report: Mapping[str, Any],
                              decisions: Mapping[Any, Any] | Iterable[Any],
                              *, limits: ZipLimits | None = None) -> SelectionResult:
    """Write a revision artifact showing only the edits kept in the selection.

    The engine's redline tracks *every* edit it planned. After a review only the
    edits the user **accepted** still belong in the tracked changes, so the
    artifact stays consistent with ``selected_final``.

    * an **accepted** edit keeps its ``w:ins``/``w:del`` markup — it remains a
      reviewable change, and accepting it in Word gives the selected wording;
    * a **rejected** edit is settled back to the original text and loses its
      markup — it reads as ordinary text, so Word no longer offers it for review.

    An edit the caller never mentioned keeps the **engine's** intent, i.e. it stays
    tracked as a change. That matches ``apply_decisions``' "accept all by default"
    semantics and keeps this artifact consistent with ``selected_final``, which
    also only changes what a verdict actually named.
    """
    limits = limits or ZipLimits()
    redline, target = Path(redline), Path(target)
    if redline.resolve() == target.resolve():
        raise DocxError("OUTPUT_PATH_INVALID")
    manifests = _manifests_from_report(report)
    if not manifests:
        raise DocxError("REVISION_MANIFEST_UNAVAILABLE")
    parts = _read_redline_parts(redline, limits)
    _validate_package(parts, limits, full=False)
    root = _xml(parts[DOCUMENT], limits)
    _validate_revision_manifest(root, manifests)
    kept = _keep_accepted_only(root, manifests, decisions)
    document_xml = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
    try:
        _write_package(target, parts, document_xml)
        # Independent re-open: only the accepted revisions may remain.
        if _managed_ids(_xml(_read_redline_parts(target, limits)[DOCUMENT], limits)) != kept:
            raise DocxError("SELECTED_REDLINE_MISMATCH")
        return SelectionResult(accepted=tuple(sorted(int(rid) for rid in kept)),
                               rejected=(), absent=(),
                               path=str(target), sha256=_sha(target.read_bytes()))
    except Exception:
        target.unlink(missing_ok=True)
        raise


def _keep_accepted_only(root: etree._Element, manifests: Sequence[Mapping[str, Any]],
                        decisions: Mapping[Any, Any] | Iterable[Any]) -> set[str]:
    """Leave accepted (or undecided) edits tracked; settle rejected ones.

    Undecided edits keep the engine's intent — they stay reviewable, matching the
    default-accept semantics used everywhere else. Returns the revision ids still
    present once the pass is done.
    """
    rejected = {rid for rid, verdict in _explicit_verdicts(manifests, decisions).items()
                if verdict == REJECT}
    for node in list(root.iter()):
        if node.tag not in {Q("ins"), Q("del")}:
            continue
        rid = _int_or_none(node.get(Q("id"), ""))
        # A revision we did not generate, or one the caller did not reject, stays
        # exactly as the engine left it.
        if node.getparent() is None or rid is None or rid not in rejected:
            continue
        if node.tag == Q("del"):
            # Undoing a deletion: the original text returns as ordinary text.
            _unwrap_revision(node, restoring_delete=True)
        else:
            # Undoing an insertion: the new text disappears.
            node.getparent().remove(node)
    return _managed_ids(root)


def _managed_ids(root: etree._Element) -> set[str]:
    """Every revision id the markup actually carries, including foreign ones."""
    return {node.get(Q("id")) for node in root.iter()
            if node.tag in {Q("ins"), Q("del")} and node.get(Q("id"))}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def accept_all(redline: str | Path, report: Mapping[str, Any]) -> dict[Any, Any]:
    """Decision map that accepts every revision the engine produced."""
    return {int(item["del_id"]): ACCEPT for item in _manifests_from_report(report)} | {
        int(item["ins_id"]): ACCEPT for item in _manifests_from_report(report)}
