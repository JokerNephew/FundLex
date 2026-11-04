"""Direct-through DOCX write-back adapter (direct-writer-1).

Consumes direct-edit proposals (``direct_edit_proposal_v1``, produced by the
locate/rewrite line from ``guide_card_v1`` cards), independently confirms file
identity, scope authorization, geometry and substantive change, then writes
them through the existing safe writer (:func:`fundlex.docx.generate_artifacts`).

Scope / provenance trust model (FL-D1022 cross-line review):

* **No verbatim business gate.**  The replacement text is never compared to
  any guide sentence, no audit model "approves" the new text, and a plan can
  never fake success by labelling itself ``verified``.  The checks here are
  file / scope / write-truth checks only.
* **Summary authorization is per-location.**  A scope entry authorizes body
  *sections* wholesale, but summary rows only through an explicit
  ``summary_locations`` whitelist, each carrying a semantic ``anchor`` quote
  that this writer independently re-finds inside the current paragraph text.
  An empty or missing whitelist authorizes *no* summary writes.  Directory
  (TOC) paragraphs are zone ``toc`` and can never be writable, so a directory
  search hit is never a write-back authorization.
* **Generation binding needs a server-side ledger, not a self-referential
  hash.**  ``write_direct_edits`` requires ``generation_ledger``: records
  created *inside the engine worker, at the moment model output is frozen
  into proposals* (see :func:`freeze_proposals`) and persisted by the backend
  with the job snapshot.  The writer re-derives each proposal's payload hash
  and requires an exact ledger record; the ``content_check`` closure handed to
  the writer is rooted in that ledger, so text altered after freeze fails
  publication.  The trust boundary is explicit: anything upstream of ledger
  freeze (the model gateway response) is trusted in-process; anything after
  freeze is cryptographically bound.  A proposal without a matching ledger
  record is skipped, silently relabelled proposals cannot pass.
"""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping, Sequence

from lxml import etree

from .docx import (
    BARRIER,
    DOCUMENT,
    DocxError,
    DocumentInspection,
    Q,
    ZipLimits,
    _read_parts,
    _sha,
    _xml,
    generate_artifacts,
    inspect_docx,
    normalize_tracked_base,
    sanitize_docx_external_links,
    validate_edit_plan,
)

PROPOSAL_SCHEMA_VERSION = "direct_edit_proposal_v1"
SCOPE_SCHEMA_VERSION = "direct_write_scope_v2"
SCOPE_SCHEMA_VERSIONS = {"direct_write_scope_v1", "direct_write_scope_v2"}
RESULT_SCHEMA_VERSION = "direct_edit_write_v1"
WRITER_VERSION = "direct-writer-1"
DEFAULT_AUTHOR = "FundLex"
ACTIONS = {"replace", "delete", "insert_before", "insert_after"}
WHITESPACE = frozenset(" \t\r\n　")


def _canonical(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")


def binding_fields(proposal: Mapping[str, Any]) -> dict[str, Any]:
    """Canonical provenance payload, frozen across line 2 and line 3.

    The key set and the ``anchor_text`` key name are the cross-line ruling
    (总负责人 2026-11-02): identical to the locate line's
    ``EditProposal.binding_fields``.
    """
    anchor = proposal.get("anchor") or {}
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "proposal_id": str(proposal.get("proposal_id") or ""),
        "rule_card_id": str(proposal.get("rule_card_id") or ""),
        "scope_ref": str(proposal.get("scope_ref") or ""),
        "action": str(proposal.get("action") or ""),
        "location": str(proposal.get("location") or ""),
        "zone": str(proposal.get("zone") or ""),
        "start": proposal.get("start"),
        "end": proposal.get("end"),
        "expected_old_text": str(proposal.get("expected_old_text") or ""),
        "replacement": str(proposal.get("replacement") or ""),
        "anchor_text": str(anchor.get("text") or ""),
        "source_sha256": str(proposal.get("source_sha256") or ""),
        "fingerprint": str(proposal.get("fingerprint") or ""),
    }


def generation_payload_hash(proposal: Mapping[str, Any]) -> str:
    """Hash over the canonical binding payload.

    The same pure function is used by :func:`freeze_proposals` (production
    side) and by this writer (consumption side).  Only the ledger records the
    expected value, so a caller cannot pass the check by recomputing a hash
    over fields it fabricated — it would still need a ledger record created
    server-side at freeze time.
    """
    return _sha(_canonical(binding_fields(proposal)))


def freeze_proposals(proposals: Sequence[Mapping[str, Any]], *,
                     model_response_sha256: Mapping[str, str] | None = None,
                     frozen_at: str = "") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Freeze located proposals and mint the generation ledger.

    Must be called by the engine worker **immediately after** model output is
    frozen into proposal dicts, before any persistence or transport.  Assigns
    ``generation_record_id`` to every proposal and returns the ledger entries.
    Pass exactly the returned ``(proposals, ledger)`` pair to
    :func:`write_direct_edits`; proposals taken from anywhere else will not
    bind.

    If a producer already stamped ``generation_sha256`` (the locate line's
    canonical self-hash), freeze verifies it against the recomputed binding
    hash: drift means the payload was altered after stamping and is refused.
    """
    responses = dict(model_response_sha256 or {})
    frozen: list[dict[str, Any]] = []
    ledger: list[dict[str, Any]] = []
    for number, raw in enumerate(proposals, start=1):
        proposal = dict(raw)
        proposal.pop("generation_record_id", None)
        declared = proposal.pop("generation_sha256", None)
        recomputed = generation_payload_hash(proposal)
        if declared is not None and declared != recomputed:
            raise DocxError("GENERATION_BINDING_DRIFT", str(proposal.get("proposal_id") or ""))
        proposal["generation_record_id"] = f"GR-{number:04d}"
        frozen.append(proposal)
        ledger.append({
            "record_id": proposal["generation_record_id"],
            "proposal_id": str(proposal.get("proposal_id") or ""),
            "rule_card_id": str(proposal.get("rule_card_id") or ""),
            "payload_sha256": generation_payload_hash(proposal),
            "model_response_sha256": str(responses.get(str(proposal.get("proposal_id") or ""), "")),
            "frozen_at": frozen_at,
        })
    return frozen, ledger


def _normalized(value: str) -> str:
    """Whitespace-only differences are not substantive changes."""
    return "".join(char for char in value if char not in WHITESPACE)


@dataclass(frozen=True)
class SkipDiagnostic:
    proposal_id: str
    rule_card_id: str
    location: str
    reason_code: str
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"proposal_id": self.proposal_id, "rule_card_id": self.rule_card_id,
                "location": self.location, "status": "skipped",
                "reason_code": self.reason_code, "detail": self.detail}


@dataclass(frozen=True)
class DirectWriteResult:
    status: str  # "written" | "zero_written"
    source_sha256: str
    actual_written_count: int
    redline_sha256: str | None
    final_sha256: str | None
    plan_sha256: str | None
    redline_path: str | None
    final_path: str | None
    revision_manifest: tuple[dict[str, Any], ...]
    source_revision_manifest: tuple[dict[str, str], ...]
    changes: tuple[dict[str, Any], ...]
    skipped: tuple[SkipDiagnostic, ...]
    checks: tuple[str, ...]
    has_toc_field: bool
    toc_update_status: str
    #: "strict_dual_layer" — original revisions preserved next to ours;
    #: "normalized_base" — original revisions were flattened into the accepted
    #: view first (FL-D1035 fallback, user ruling 2026-11-03).  In
    #: "normalized_base" tier there are no foreign revisions to select, so
    #: layered accept/reject of the original marks is not offered.  The value
    #: set is owned by this writer; downstream layers only pass it through.
    revision_tier: str = "strict_dual_layer"
    #: Present only in "normalized_base" tier.
    normalized_from: Mapping[str, Any] | None = None
    #: Inert attachedTemplate links stripped from the working copy (journal).
    input_sanitization: tuple[dict[str, str], ...] = ()

    @property
    def foreign_selection(self) -> str:
        return ("unavailable_normalized_base" if self.revision_tier == "normalized_base"
                else "available")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": RESULT_SCHEMA_VERSION,
            "engine_writer_version": WRITER_VERSION,
            "status": self.status,
            "source_sha256": self.source_sha256,
            "actual_written_count": self.actual_written_count,
            "plan_sha256": self.plan_sha256,
            "redline_sha256": self.redline_sha256,
            "final_sha256": self.final_sha256,
            "revision_manifest": [dict(item) for item in self.revision_manifest],
            "source_revision_manifest": [dict(item) for item in self.source_revision_manifest],
            "changes": [dict(item) for item in self.changes],
            "skipped": [item.to_dict() for item in self.skipped],
            "checks": list(self.checks),
            "has_toc_field": self.has_toc_field,
            "toc_update_status": self.toc_update_status,
            "revision_tier": self.revision_tier,
            "foreign_selection": self.foreign_selection,
            "normalized_from": (dict(self.normalized_from) if self.normalized_from else None),
            "input_sanitization": [dict(item) for item in self.input_sanitization],
        }


class WriteScope:
    """Write-back authorization, re-derived from a fresh inspection.

    Body sections are authorized by exact ``section_path`` match.  Summary
    rows are authorized **only** per actual hit:

    * ``summary_locations`` (additive field; v1 strings or v2
      ``{location, anchor}`` dicts) is an exact per-location whitelist.  v2
      entries carry a semantic anchor which must still be inside the current
      paragraph text;
    * when ``summary_locations`` is absent, the explicitly enumerated
      ``summary_sections`` titles are the fallback whitelist;
    * with neither, the entry authorizes **no** summary writes — a scope can
      never mean "the whole summary zone".
    """

    def __init__(self, raw: Any, inspection: DocumentInspection) -> None:
        if not isinstance(raw, Mapping):
            raise DocxError("SCOPE_SCHEMA_INVALID", "scope must be a mapping")
        if str(raw.get("schema_version")) not in SCOPE_SCHEMA_VERSIONS:
            raise DocxError("SCOPE_SCHEMA_INVALID", "unexpected scope schema_version")
        if raw.get("source_sha256") != inspection.source_sha256:
            raise DocxError("SCOPE_SOURCE_HASH_MISMATCH")
        entries = raw.get("entries")
        if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)):
            raise DocxError("SCOPE_SCHEMA_INVALID", "entries missing")
        self.entries: dict[str, dict[str, Any]] = {}
        # K1(FL-D1080): 同一位置可被多个 scope 条目同时授权（同章多卡）。
        # 允许集合按位置收完整 scope_id 集合，first-wins 不再吞并后卡。
        self.allowed: dict[str, set[str]] = {}
        for entry in entries:
            if not isinstance(entry, Mapping) or not isinstance(entry.get("scope_id"), str):
                raise DocxError("SCOPE_SCHEMA_INVALID", "entry missing scope_id")
            scope_id = entry["scope_id"]
            if scope_id in self.entries:
                raise DocxError("SCOPE_SCHEMA_INVALID", f"duplicate scope_id {scope_id}")
            summary_locations: dict[str, str | None] = {}
            for item in entry.get("summary_locations") or ():
                if isinstance(item, str):
                    summary_locations[item] = None
                    continue
                if not isinstance(item, Mapping) or not item.get("location"):
                    raise DocxError("SCOPE_SCHEMA_INVALID", f"{scope_id}: summary location entries need location")
                anchor = str(item.get("anchor") or "")
                if item.get("anchor") is not None and len(anchor.strip()) < 6:
                    raise DocxError("SCOPE_SCHEMA_INVALID", f"{scope_id}: summary anchor too short")
                summary_locations[str(item["location"])] = anchor or None
            record = {
                "scope_id": scope_id,
                "rule_card_ids": {str(item) for item in (entry.get("rule_card_ids") or ())},
                # K2(FL-D1080): scope v2 附加逐段白名单（节级授权可达；为显式名单
                # 不扩授权，仅补上 T 级标题永远不可 endswith 匹配 section_path 的死路）
                "body_locations": {str(item) for item in (entry.get("body_locations") or ())},
                "sections": {str(item) for item in (entry.get("sections") or ())},
                "summary_locations": summary_locations,
                "summary_sections": {str(item) for item in (entry.get("summary_sections") or ())}
                if not entry.get("summary_locations") else set(),
                "summary_reason": str(entry.get("summary_reason") or ""),
            }
            self.entries[scope_id] = record
        # Independently resolve the authorized location set from the current
        # package; the scope document itself is only a claim.
        for paragraph in inspection.paragraphs:
            if not paragraph.editable:
                continue
            for scope_id, entry in self.entries.items():
                if self._covered(entry, paragraph):
                    self.allowed.setdefault(paragraph.location, set()).add(scope_id)

    @staticmethod
    def _section_match(section_path: str, title: str) -> bool:
        # Normalization of a paragraph-mark deletion merges the paragraph into
        # the heading that follows it; the accepted view then carries the
        # previous text prepended to the real title.  A title that ends the
        # merged path is still exactly that chapter's heading.
        return section_path == title or section_path.endswith(title)

    @classmethod
    def _covered(cls, entry: Mapping[str, Any], paragraph: Any) -> bool:
        if paragraph.zone == "body":
            if paragraph.location in entry.get("body_locations", ()):
                return True
            return any(cls._section_match(paragraph.section_path, title)
                       for title in entry["sections"] if title)
        if paragraph.zone == "summary":
            if paragraph.location in entry["summary_locations"]:
                anchor = entry["summary_locations"][paragraph.location]
                # Semantic authorization: a recorded anchor must still be
                # inside this paragraph's current text in this package.
                return anchor is None or _normalized(anchor) in _normalized(paragraph.text)
            return paragraph.section_path in entry["summary_sections"]
        return False


def _skip(skipped: list[SkipDiagnostic], proposal: Mapping[str, Any],
          code: str, detail: str = "") -> None:
    skipped.append(SkipDiagnostic(
        proposal_id=str(proposal.get("proposal_id") or ""),
        rule_card_id=str(proposal.get("rule_card_id") or ""),
        location=str(proposal.get("location") or ""),
        reason_code=code, detail=detail[:200]))


_REQUIRED_FIELDS = ("proposal_id", "rule_card_id", "scope_ref", "action", "location",
                    "zone", "start", "end", "expected_old_text", "expected_old_hash",
                    "replacement", "fingerprint", "source_sha256",
                    "generation_record_id")


def _screen(proposal: Mapping[str, Any], inspection: DocumentInspection,
            scope: WriteScope, ledger: Mapping[str, Mapping[str, Any]],
            occupied: dict[str, list[tuple[int, int]]],
            skipped: list[SkipDiagnostic]) -> dict[str, Any] | None:
    """Screen one proposal. Pure file/scope/provenance/geometry truth checks."""
    if proposal.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
        _skip(skipped, proposal, "SCHEMA_VERSION_MISMATCH")
        return None
    if any(proposal.get(key) is None for key in _REQUIRED_FIELDS):
        _skip(skipped, proposal, "MISSING_FIELD")
        return None
    action = str(proposal["action"])
    if action not in ACTIONS:
        _skip(skipped, proposal, "MISSING_FIELD", f"unknown action {action!r}")
        return None
    if proposal["source_sha256"] != inspection.source_sha256:
        _skip(skipped, proposal, "SOURCE_HASH_MISMATCH")
        return None
    record_id = str(proposal["generation_record_id"])
    record = ledger.get(record_id)
    payload_hash = generation_payload_hash(proposal)
    if record is None or record.get("payload_sha256") != payload_hash \
            or record.get("proposal_id") != str(proposal["proposal_id"]):
        _skip(skipped, proposal, "BINDING_RECORD_MISMATCH", record_id)
        return None
    location = str(proposal["location"])
    try:
        paragraph = inspection.by_location(location)
    except DocxError:
        _skip(skipped, proposal, "LOCATION_NOT_FOUND", location)
        return None
    if proposal["fingerprint"] != paragraph.fingerprint:
        _skip(skipped, proposal, "PARAGRAPH_DRIFT", location)
        return None
    if str(proposal["zone"]) != paragraph.zone or not paragraph.editable:
        _skip(skipped, proposal, "REGION_NOT_EDITABLE", location)
        return None
    entry = None
    if str(proposal["scope_ref"]) in scope.allowed.get(location, set()):
        entry = scope.entries[str(proposal["scope_ref"])]
    if entry is None or str(proposal["rule_card_id"]) not in entry["rule_card_ids"]:
        _skip(skipped, proposal, ("SCOPE_REF_UNKNOWN" if str(proposal["scope_ref"]) not in scope.entries
                                  else "UNAUTHORIZED_LOCATION"), location)
        return None
    start, end = proposal["start"], proposal["end"]
    insertion = action in {"insert_before", "insert_after"}
    if not isinstance(start, int) or not isinstance(end, int) or isinstance(start, bool) \
            or not (0 <= start <= end <= len(paragraph.text)) or (start == end) != insertion:
        _skip(skipped, proposal, "EDIT_RANGE_INVALID", location)
        return None
    old = paragraph.text[start:end]
    if old != str(proposal["expected_old_text"]) \
            or _sha(old.encode("utf-8")) != proposal["expected_old_hash"]:
        _skip(skipped, proposal, "EXPECTED_TEXT_MISMATCH", location)
        return None
    replacement = str(proposal["replacement"])
    if not insertion and _normalized(old) == _normalized(replacement):
        _skip(skipped, proposal, "NO_EFFECT", location)
        return None
    for kept_start, kept_end in occupied.setdefault(location, []):
        if not (end < kept_start or start > kept_end):
            _skip(skipped, proposal, "CONFLICT_WITH_KEPT_PROPOSAL", location)
            return None
    edit: dict[str, Any] = {
        "edit_id": str(proposal["proposal_id"]),
        "source_sha256": inspection.source_sha256,
        "verified": True,  # this writer performed the checks above; no caller label
        "location": location,
        "zone": paragraph.zone,
        "start": start,
        "end": end,
        "expected_old_text": old,
        "expected_old_hash": proposal["expected_old_hash"],
        "replacement": replacement,
        "operation": ("insert_before" if action == "insert_before"
                      else "insert_after" if action == "insert_after" else "replace"),
        "fingerprint": paragraph.fingerprint,
        "mapping_version": paragraph.mapping_version,
        "content_source": "generated",
        "_proposal": dict(proposal),  # provenance payload, re-bound inside content_check
    }
    if insertion:
        anchor = proposal.get("anchor")
        if not isinstance(anchor, Mapping):
            _skip(skipped, proposal, "INSERT_ANCHOR_INVALID", "anchor missing")
            return None
        anchor_start, anchor_end = anchor.get("start"), anchor.get("end")
        adjacent = (anchor_end == start) if action == "insert_after" else (anchor_start == start)
        if not isinstance(anchor_start, int) or not isinstance(anchor_end, int) \
                or not (0 <= anchor_start < anchor_end) or not adjacent:
            _skip(skipped, proposal, "INSERT_ANCHOR_INVALID", location)
            return None
        edit["anchor"] = {"start": anchor_start, "end": anchor_end,
                          "text": str(anchor.get("text") or ""),
                          "sha256": str(anchor.get("sha256") or "")}
    occupied[location].append((start, end))
    return {"edit": edit, "proposal": proposal, "paragraph": paragraph}


def _make_content_check(ledger: Mapping[str, Mapping[str, Any]]):
    """Provenance closure rooted in the server-side generation ledger.

    Raises :class:`DocxError` unless the edit carries a frozen proposal whose
    payload hash re-derives to a ledger record minted at freeze time, and the
    edit's published fields still equal that payload.  Never returns True
    unconditionally.
    """

    def check(edit: Mapping[str, Any]) -> None:
        proposal = edit.get("_proposal")
        if not isinstance(proposal, Mapping) or proposal.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
            raise DocxError("GENERATION_BINDING_MISMATCH", str(edit.get("edit_id") or ""))
        record_id = str(proposal.get("generation_record_id") or "")
        record = ledger.get(record_id)
        if record is None or record.get("proposal_id") != str(edit.get("edit_id") or "") \
                or record.get("payload_sha256") != generation_payload_hash(proposal):
            raise DocxError("GENERATION_BINDING_MISMATCH", str(edit.get("edit_id") or ""))
        for key in ("location", "start", "end", "expected_old_text", "replacement"):
            if proposal.get(key) != edit.get(key):
                raise DocxError("GENERATION_BINDING_MISMATCH", str(edit.get("edit_id") or ""))

    return check


def _try_batch(candidates: list[dict[str, Any]], source: Path, content_check,
               *, author: str, allow_existing_revisions: bool,
               redline: Path, final: Path, limits: ZipLimits):
    edits = [dict(item["edit"]) for item in candidates]
    plan = validate_edit_plan(source, edits, {}, content_check=content_check,
                              limits=limits,
                              allow_existing_revisions=allow_existing_revisions)
    validation = generate_artifacts(source, plan, redline, final, author=author,
                                    limits=limits,
                                    allow_existing_revisions=allow_existing_revisions)
    return plan, validation


def _resolve_writable(candidates: list[dict[str, Any]], source: Path,
                      workdir: Path, counter: list[int], content_check,
                      *, author: str, allow_existing_revisions: bool,
                      limits: ZipLimits,
                      failures: list[tuple[dict[str, Any], str]]) -> list[dict[str, Any]]:
    """Keep every individually writable edit; bisect mixed failures.

    One unsafe or failing proposal is reported and never rolls back the
    successful writes of the others.
    """
    if not candidates:
        return []
    counter[0] += 1
    redline = workdir / f"try-{counter[0]}-redline.docx"
    final = workdir / f"try-{counter[0]}-final.docx"
    try:
        _try_batch(candidates, source, content_check, author=author,
                   allow_existing_revisions=allow_existing_revisions,
                   redline=redline, final=final, limits=limits)
        return list(candidates)
    except (DocxError, ValueError) as exc:
        code = exc.code if isinstance(exc, DocxError) else type(exc).__name__
        for path in (redline, final):
            path.unlink(missing_ok=True)
        if len(candidates) == 1:
            failures.append((candidates[0], code))
            return []
        middle = len(candidates) // 2
        kept = _resolve_writable(candidates[:middle], source, workdir, counter,
                                 content_check, author=author,
                                 allow_existing_revisions=allow_existing_revisions,
                                 limits=limits, failures=failures)
        kept += _resolve_writable(candidates[middle:], source, workdir, counter,
                                  content_check, author=author,
                                  allow_existing_revisions=allow_existing_revisions,
                                  limits=limits, failures=failures)
        return kept


def _revision_ids(path: Path, limits: ZipLimits) -> dict[str, str]:
    """Re-open a produced redline: revision id -> owning author, for evidence."""
    parts = _read_parts(path, limits)
    root = _xml(parts[DOCUMENT], limits)
    found: dict[str, str] = {}
    for node in root.iter():
        if node.tag in {Q("ins"), Q("del")}:
            rid = node.get(Q("id"))
            if rid is not None:
                found[rid] = node.get(Q("author"), "")
    return found


def _accepted_view_equals_final(redline_root: etree._Element, final_path: Path,
                                limits: ZipLimits) -> None:
    """Index-agnostic global evidence: accept-all of the redline IS the final.

    Foreign paragraph-mark deletions join paragraphs in the accepted view, so
    any location-indexed comparison of the two packages is unsound; comparing
    canonical accepted view with the final is the only truthful equivalence.
    """
    from .compare.revisions import _accept_revisions
    accepted = deepcopy(redline_root)
    _accept_revisions(accepted)
    final_root = _xml(_read_parts(final_path, limits)[DOCUMENT], limits)
    if etree.tostring(accepted, method="c14n") != etree.tostring(final_root, method="c14n"):
        raise DocxError("WRITE_EVIDENCE_MISMATCH", "accepted-view-of-redline != final")


def _evidence_pairs(red_root: etree._Element, manifest: Sequence[Mapping[str, Any]],
                    author: str) -> None:
    """Per-change evidence inside the re-opened redline: our pair, right text."""
    wrapper_by_id: dict[str, etree._Element] = {}
    for node in red_root.iter():
        if node.tag in {Q("ins"), Q("del")}:
            wrapper_by_id[node.get(Q("id"), "")] = node
    for entry in manifest:
        location = str(entry["location"])
        del_node = wrapper_by_id.get(str(entry["del_id"]))
        ins_node = wrapper_by_id.get(str(entry["ins_id"]))
        if del_node is None or ins_node is None \
                or del_node.get(Q("author")) != author or ins_node.get(Q("author")) != author:
            raise DocxError("WRITE_EVIDENCE_MISMATCH", f"{location}:{entry.get('edit_id', '')}")
        del_text = "".join(t.text or "" for t in del_node.iter(Q("delText")))
        ins_text = "".join(("\n" if t.tag == Q("br") else (t.text or ""))
                           for t in ins_node.iter() if t.tag in {Q("t"), Q("br")})
        if del_text != str(entry["expected_old_text"]) or ins_text != str(entry["replacement"]):
            raise DocxError("WRITE_EVIDENCE_MISMATCH", f"{location}:{entry.get('edit_id', '')}")


def _paragraph_host(node: etree._Element) -> etree._Element | None:
    """Nearest ancestor w:p of a revision wrapper."""
    ancestor: etree._Element | None = node.getparent()
    while ancestor is not None and ancestor.tag != Q("p"):
        ancestor = ancestor.getparent()
    return ancestor


def _visible_text(paragraph: etree._Element | None) -> str:
    """Readable text of a paragraph: ins/body text kept, delText excluded."""
    if paragraph is None:
        return ""
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == Q("delText"):
            continue
        if node.tag in {Q("br"), Q("cr")}:
            parts.append("\n")
        elif node.tag == Q("t") and next(node.iterancestors(Q("del")), None) is None:
            parts.append(node.text or "")
    return "".join(parts)


def _rewrite_source_identity(ledger: Mapping[str, Mapping[str, Any]],
                             proposals: Sequence[Mapping[str, Any]],
                             from_sha: str, to_sha: str) -> dict[str, Mapping[str, Any]]:
    """Re-bind ledger + proposals after a deterministic identity rewrite.

    The sanitized working copy changes ``source_sha256``; paragraphs and
    fingerprints do not move.  Rewrite the identity on-chain, recompute the
    binding hash with the same pure function, and keep the previous hash in
    ``id_rewrite_from`` so the ledger stays auditable instead of silent.
    """
    rewritten: dict[str, Mapping[str, Any]] = dict(ledger)
    for proposal in proposals:
        record_id = str(proposal.get("generation_record_id") or "")
        record = ledger.get(record_id)
        if record is None:
            continue
        if proposal.get("source_sha256") == from_sha:
            proposal["source_sha256"] = to_sha
        entry = dict(record)
        if entry.get("payload_sha256") == generation_payload_hash(
                {**proposal, "source_sha256": from_sha}):
            entry["id_rewrite_from"] = from_sha
            entry["payload_sha256"] = generation_payload_hash(proposal)
        rewritten[record_id] = entry
    return rewritten


def _remap_one_to_base(proposal: Mapping[str, Any],
                       inspection: DocumentInspection) -> tuple[dict[str, Any] | None, str]:
    """Remap one verified proposal from the original file's coordinates onto
    the normalized (accepted-view) basis.

    Matching is by the proposal's text (``expected_old_text`` or the anchor
    quote), barriers stripped, inside editable paragraphs of the same zone.
    ``section_title`` disambiguates repeated hits.  Anything non-unique or
    missing is refused, never guessed.
    """
    insertion = proposal["action"] in {"insert_before", "insert_after"}
    if insertion:
        anchor = proposal.get("anchor") or {}
        probe = str(anchor.get("text") or "").replace(BARRIER, "")
    else:
        probe = str(proposal.get("expected_old_text") or "").replace(BARRIER, "")
    if not probe:
        return None, "NORMALIZED_REMAP_NOT_FOUND"
    hits: list[tuple[Any, int]] = []
    for paragraph in inspection.paragraphs:
        if not paragraph.editable or paragraph.zone != str(proposal["zone"]):
            continue
        count = paragraph.text.count(probe)
        if count == 1:
            hits.append((paragraph, paragraph.text.find(probe)))
        elif count > 1:
            return None, "NORMALIZED_REMAP_AMBIGUOUS"
    if not hits:
        return None, "NORMALIZED_REMAP_NOT_FOUND"
    if len(hits) > 1:
        titled = [hit for hit in hits
                  if hit[0].section_path == str(proposal.get("section_title") or "")]
        if len(titled) != 1:
            return None, "NORMALIZED_REMAP_AMBIGUOUS"
        hits = titled
    paragraph, index = hits[0]
    remapped = dict(proposal)
    if insertion:
        insert_at = index if proposal["action"] == "insert_before" else index + len(probe)
        remapped.update(start=insert_at, end=insert_at,
                        anchor={"start": index, "end": index + len(probe),
                                "text": probe,
                                "sha256": sha256(probe.encode("utf-8")).hexdigest()})
    else:
        remapped.update(start=index, end=index + len(probe), expected_old_text=probe,
                        expected_old_hash=sha256(probe.encode("utf-8")).hexdigest())
    remapped.update(location=paragraph.location, zone=paragraph.zone,
                    fingerprint=paragraph.fingerprint,
                    mapping_version=paragraph.mapping_version,
                    source_sha256=inspection.source_sha256)
    return remapped, ""


def _remap_proposals_to_normalized_base(
        proposals: Sequence[Mapping[str, Any]],
        ledger: Mapping[str, Mapping[str, Any]],
        inspection: DocumentInspection,
) -> tuple[dict[str, Mapping[str, Any]], list[dict[str, Any]], list[SkipDiagnostic]]:
    """Verify original payloads against the ledger, then re-map coordinates.

    Returns the re-bound ledger (same record ids, remapped payload hashes, the
    original hash kept as ``remapped_from``), the remapped proposals, and the
    honest per-proposal skip diagnostics.  Binding failures are never softened.
    """
    remapped_ledger: dict[str, Mapping[str, Any]] = {}
    remapped: list[dict[str, Any]] = []
    skipped: list[SkipDiagnostic] = []
    for proposal in proposals:
        if not isinstance(proposal, Mapping):
            skipped.append(SkipDiagnostic("", "", "", "MISSING_FIELD", "not a mapping"))
            continue
        record_id = str(proposal.get("generation_record_id") or "")
        record = ledger.get(record_id)
        original_hash = generation_payload_hash(proposal)
        if record is None or record.get("payload_sha256") != original_hash \
                or record.get("proposal_id") != str(proposal.get("proposal_id") or ""):
            skipped.append(SkipDiagnostic(str(proposal.get("proposal_id") or ""),
                                          str(proposal.get("rule_card_id") or ""),
                                          str(proposal.get("location") or ""),
                                          "BINDING_RECORD_MISMATCH", record_id))
            continue
        if proposal.get("schema_version") != PROPOSAL_SCHEMA_VERSION:
            skipped.append(SkipDiagnostic(str(proposal.get("proposal_id") or ""),
                                          str(proposal.get("rule_card_id") or ""),
                                          str(proposal.get("location") or ""),
                                          "SCHEMA_VERSION_MISMATCH"))
            continue
        base, error = _remap_one_to_base(proposal, inspection)
        if base is None:
            _skip(skipped, proposal, error, str(proposal.get("location") or ""))
            continue
        new_hash = generation_payload_hash(base)
        entry = dict(record)
        entry["payload_sha256"] = new_hash
        entry["remapped_from"] = original_hash
        remapped_ledger[record_id] = entry
        remapped.append(base)
    return remapped_ledger, remapped, skipped


def write_direct_edits(source_path: str | Path, proposals: Sequence[Mapping[str, Any]],
                       scope: Mapping[str, Any], redline_path: str | Path,
                       final_path: str | Path,
                       *, generation_ledger: Sequence[Mapping[str, Any]],
                       author: str = DEFAULT_AUTHOR,
                       limits: ZipLimits | None = None,
                       allow_existing_revisions: bool = True) -> DirectWriteResult:
    """Screen direct-edit proposals and write the survivors into DOCX artifacts.

    ``generation_ledger`` is required: provenance records minted by
    :func:`freeze_proposals` inside the engine worker at freeze time.
    Technical failures (unreadable/corrupt package, verification failure of a
    fully produced artifact) raise :class:`DocxError` and must be reported as
    failures by the caller; a *successful* return with
    ``status == "zero_written"`` means every proposal was honestly judged
    unwritable and **no artifact was produced**.
    """
    limits = limits or ZipLimits()
    source = Path(source_path)
    redline_path, final_path = Path(redline_path), Path(final_path)
    if redline_path.resolve() == final_path.resolve() or \
            source.resolve() in {redline_path.resolve(), final_path.resolve()}:
        raise DocxError("OUTPUT_PATH_INVALID")
    for ledger_entry in generation_ledger:
        if not isinstance(ledger_entry, Mapping) or not ledger_entry.get("record_id"):
            raise DocxError("GENERATION_LEDGER_INVALID")
    ledger = {str(entry["record_id"]): entry for entry in generation_ledger}
    if len(ledger) != len(generation_ledger):
        raise DocxError("GENERATION_LEDGER_INVALID", "duplicate record_id")
    original_sha256 = _sha(source.read_bytes())
    tier = "strict_dual_layer"
    basis = source
    normalized_from: dict[str, Any] | None = None
    temp_base_dir: TemporaryDirectory | None = None
    effective_proposals: Sequence[Mapping[str, Any]] = proposals
    remap_skips: list[SkipDiagnostic] = []
    # Normalize the working copy: strip ONLY inert attachedTemplate links
    # (FL-D1044 user file).  Journal is empty for every other external shape
    # (hyperlinks etc.), so clean inputs keep byte-identical behavior.
    sanitization = sanitize_docx_external_links(source.read_bytes(), limits=limits)
    if sanitization.journal:
        temp_base_dir = TemporaryDirectory(prefix="fundlex-sanitized-")
        basis = Path(temp_base_dir.name) / "sanitized-source.docx"
        basis.write_bytes(sanitization.data)
        sanitized_sha = _sha(sanitization.data)
        effective_proposals = [dict(p) for p in proposals]
        ledger = _rewrite_source_identity(ledger, effective_proposals,
                                          original_sha256, sanitized_sha)
        if isinstance(scope, Mapping) and scope.get("source_sha256") == original_sha256:
            scope = dict(scope) | {"source_sha256": sanitized_sha}
        original_sha256 = sanitized_sha
    try:
        inspection = inspect_docx(basis, full=True, limits=limits,
                                  allow_existing_revisions=allow_existing_revisions)
    except DocxError as exc:
        if not allow_existing_revisions or exc.code != "EXISTING_REVISION_STRUCTURE_UNSUPPORTED":
            raise
        # FL-D1035 user ruling (2026-11-03): fall back to the normalized
        # accepted-view base, write our revisions on top of it, and report the
        # tier honestly.  DOCUMENT_PROTECTED and every other gate stay strict.
        normalization = normalize_tracked_base(basis.read_bytes(), limits=limits)
        if not normalization.had_tracked_changes:
            raise  # gate failure unrelated to tracked changes: never bypass
        tier = "normalized_base"
        temp_base_dir = TemporaryDirectory(prefix="fundlex-norm-base-")
        basis = Path(temp_base_dir.name) / "normalized-base.docx"
        basis.write_bytes(normalization.data)
        inspection = inspect_docx(basis, full=True, limits=limits)
        normalized_from = {
            "source_sha256": normalization.original_sha256,
            "base_sha256": normalization.base_sha256,
            "revisions_accepted": normalization.revisions_accepted,
            "flattened_revision_count": len(normalization.source_revisions),
            "flattened_inventory": [dict(item) for item in normalization.source_revisions],
        }
        scope = dict(scope) | {"source_sha256": inspection.source_sha256}
        # Proposals carry coordinates of the original file.  Each is verified
        # against the ledger with its original payload first (binding is
        # mandatory here too), then remapped onto the normalized basis.
        ledger, effective_proposals, remap_skips = _remap_proposals_to_normalized_base(
            proposals, ledger, inspection)
        # Paragraph-mark merges shift paragraph indices: rebuild each entry's
        # summary whitelist from the proposals that actually landed on the
        # basis (exact-hit rule, FL-D1029), and disable the title fallback —
        # after merges a title may legitimately not compare equal.
        scope["entries"] = [
            dict(entry,
                 summary_locations=sorted(
                     {str(proposal["location"]) for proposal in effective_proposals
                      if str(proposal.get("scope_ref") or "") == str(entry.get("scope_id") or "")
                      and str(proposal.get("zone") or "") == "summary"}),
                 summary_sections=[])
            for entry in scope.get("entries") or ()
        ]
    skipped: list[SkipDiagnostic] = list(remap_skips)
    occupied: dict[str, list[tuple[int, int]]] = {}
    candidates: list[dict[str, Any]] = []
    scope_obj = WriteScope(scope, inspection)
    for proposal in effective_proposals:
        if not isinstance(proposal, Mapping):
            skipped.append(SkipDiagnostic("", "", "", "MISSING_FIELD", "not a mapping"))
            continue
        screened = _screen(proposal, inspection, scope_obj, ledger, occupied, skipped)
        if screened is not None:
            candidates.append(screened)
    failures: list[tuple[dict[str, Any], str]] = []
    try:
        if candidates:
            with TemporaryDirectory(prefix="fundlex-direct-write-", dir=redline_path.parent if redline_path.parent.is_dir() else None) as workdir:
                kept = _resolve_writable(candidates, basis, Path(workdir), [0],
                                         _make_content_check(ledger), author=author,
                                         allow_existing_revisions=allow_existing_revisions,
                                         limits=limits, failures=failures)
        else:
            kept = []
        for item, code in failures:
            _skip(skipped, item["proposal"], f"WRITE_FAILED_{code}", str(item["edit"]["location"]))
        if not kept:
            return DirectWriteResult(
                status="zero_written", source_sha256=original_sha256,
                actual_written_count=0, redline_sha256=None, final_sha256=None,
                plan_sha256=None, redline_path=None, final_path=None,
                revision_manifest=(), source_revision_manifest=inspection.revisions,
                changes=(), skipped=tuple(skipped), checks=("screen",),
                has_toc_field=inspection.has_toc_field,
                toc_update_status="not_updated" if inspection.has_toc_field else "not_present",
                revision_tier=tier,
                normalized_from=(dict(normalized_from) if normalized_from else None),
                input_sanitization=tuple(dict(item) for item in sanitization.journal))
        plan, validation = _try_batch(kept, basis, _make_content_check(ledger), author=author,
                                      allow_existing_revisions=allow_existing_revisions,
                                      redline=redline_path, final=final_path, limits=limits)
    finally:
        if temp_base_dir is not None:
            temp_base_dir.cleanup()
    # Post-open evidence (index-agnostic).  Two independent facts are proven
    # by re-reading BOTH output packages:
    #   1. every manifest revision pair physically exists in the re-opened
    #      redline, authored by us, carrying exactly the before/after text of
    #      the proposal that the write-back claims;
    #   2. the re-opened redline's accepted view is byte-canonical identical
    #      to the re-opened final package.
    # (b) replaces the earlier index-based paragraph-text comparison: when the
    # accepted view joins paragraphs (foreign paragraph-mark deletions), pN
    # indices shift between redline and final, so comparing by location string
    # produced false WRITE_EVIDENCE_MISMATCH on a perfectly valid write
    # (FL-D1050 reproduction: A50 redline 1404 p vs final 1393 p, contents
    # otherwise equal).  actual_written_count still counts only evidenced
    # writes — never proposals, never model calls.
    red_root = _xml(_read_parts(redline_path, limits)[DOCUMENT], limits)
    from .compare.revisions import _accept_revisions
    accepted_clone = deepcopy(red_root)
    _accept_revisions(accepted_clone)
    final_root = _xml(_read_parts(final_path, limits)[DOCUMENT], limits)
    if etree.tostring(accepted_clone, method="c14n") != \
            etree.tostring(final_root, method="c14n"):
        raise DocxError("WRITE_EVIDENCE_MISMATCH", "accepted-view-of-redline != final")
    by_edit_id = {str(item["edit"]["edit_id"]): item for item in kept}
    wrapper_by_id: dict[str, etree._Element] = {}
    for node in red_root.iter():
        if node.tag in {Q("ins"), Q("del")}:
            wrapper_by_id[node.get(Q("id"), "")] = node
    changes: list[dict[str, Any]] = []
    for entry in validation.manifest:
        candidate = by_edit_id.get(str(entry.get("edit_id", "")))
        del_node = wrapper_by_id.get(str(entry["del_id"]))
        ins_node = wrapper_by_id.get(str(entry["ins_id"]))
        location = str(entry["location"])
        if candidate is None or del_node is None or ins_node is None \
                or del_node.get(Q("author")) != author or ins_node.get(Q("author")) != author:
            raise DocxError("WRITE_EVIDENCE_MISMATCH", f"{location}:{entry.get('edit_id', '')}")
        del_text = "".join(t.text or "" for t in del_node.iter(Q("delText")))
        ins_text = "".join(("\n" if t.tag == Q("br") else (t.text or ""))
                           for t in ins_node.iter() if t.tag in {Q("t"), Q("br")})
        before, after = str(entry["expected_old_text"]), str(entry["replacement"])
        if del_text != before or ins_text != after:
            raise DocxError("WRITE_EVIDENCE_MISMATCH", f"{location}:{entry.get('edit_id', '')}")
        proposal = candidate["proposal"]
        paragraph = candidate["paragraph"]
        host = _paragraph_host(del_node)
        if host is None:
            host = _paragraph_host(ins_node)
        changes.append({
            "proposal_id": str(proposal["proposal_id"]),
            "rule_card_id": str(proposal["rule_card_id"]),
            "action": str(proposal["action"]),
            "location": location,
            "zone": paragraph.zone,
            "section_path": paragraph.section_path,
            "status": "written",
            "before": before,
            "after": after,
            "final_paragraph_excerpt": _visible_text(host)[:400],
            "del_id": entry["del_id"],
            "ins_id": entry["ins_id"],
            "generation_record_id": str(proposal.get("generation_record_id", "")),
        })
    return DirectWriteResult(
        status="written", source_sha256=original_sha256,
        actual_written_count=len(changes),
        redline_sha256=validation.redline_sha256,
        final_sha256=validation.final_sha256,
        plan_sha256=plan.plan_sha256,
        redline_path=str(redline_path), final_path=str(final_path),
        revision_manifest=tuple(dict(item) for item in validation.manifest),
        # A normalized base carries no foreign revisions: the selection
        # whitelist is honestly empty (flattened inventory lives in
        # ``normalized_from``), so original marks can never appear as
        # independent selection entries.
        source_revision_manifest=tuple(dict(item) for item in validation.source_revisions),
        changes=tuple(changes), skipped=tuple(skipped), checks=validation.checks,
        has_toc_field=validation.has_toc_field,
        toc_update_status=validation.toc_update_status,
        revision_tier=tier,
        normalized_from=(dict(normalized_from) if normalized_from else None),
        input_sanitization=tuple(dict(item) for item in sanitization.journal))
