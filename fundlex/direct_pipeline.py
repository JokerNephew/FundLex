"""Direct-through document pipeline (``direct-edit-1``).

One contract document flows through exactly one path:

    guide_card_v1 cards -> section-scoped locating / model rewrite (line 2)
                        -> safe DOCX write-back (line 3, direct_edit_writer)
                        -> direct_edit_v1 report frozen at persistence time.

There is **no** fallback to the retired recall engine.  Line 2's locating
module is not delivered yet, so the locator is a replaceable adapter: a real
``fundlex.direct_locate`` module wins when present; otherwise the pipeline
fails honestly with ``DIRECT_LOCATE_UNAVAILABLE`` instead of fabricating
work.  The worker injects test doubles through ``locate``/``write``.

Cross-line contracts: ``docs/DIRECT_THROUGH_CONTRACT_20261102.md`` (cards),
``docs/DIRECT_WRITE_LINE3_CONTRACT_20261102.md`` (writer),
``docs/DIRECT_BACKEND_LINE4_WIRING_20261102.md`` (this report).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .store import sha256_file

ENGINE_ID = "direct_edit_v1"
ENGINE_VERSION = "direct-edit-1"
REPORT_CONTRACT = "direct_edit_v1"

Locate = Callable[..., Mapping[str, Any]]
Write = Callable[..., Mapping[str, Any]]


class DirectPipelineError(ValueError):
    """Terminal (non-retryable) pipeline failure with a stable code."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code = code


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

def _import_callable(module_name: str, candidates: tuple[str, ...]) -> Callable | None:
    try:
        module = __import__(module_name, fromlist=list(candidates))
    except ImportError:
        return None
    for name in candidates:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None


def _default_locator() -> Callable:
    """Line 2's locating/rewrite engine as a pipeline locator.

    ``fundlex.direct_edit.propose_edits(contract_path, cards, *, gateway)``
    returns an ``EngineResult``; wrap it into the locator-outcome dict the
    pipeline consumes (proposals, unlocated cards, write scope, diagnostics).
    """
    propose = _import_callable("fundlex.direct_edit", ("propose_edits",))
    if propose is None:
        raise DirectPipelineError("DIRECT_LOCATE_UNAVAILABLE")

    def locate(source_path, card_document, gateway, *, scope=None):
        import dataclasses
        cards = card_document.get("cards") or []
        result = propose(source_path, cards, gateway=gateway)
        proposals = result.proposal_dicts() if hasattr(result, "proposal_dicts") \
            else [dict(p) for p in (getattr(result, "proposals", None) or [])]

        def plain(value):
            if isinstance(value, Mapping):
                return dict(value)
            if dataclasses.is_dataclass(value):
                return dataclasses.asdict(value)
            return value

        card_reports = [plain(report) for report in (getattr(result, "card_reports", ()) or ())]
        unlocated = [
            {"rule_card_id": report.get("card_id"),
             "reason": "LOCATOR_NO_WRITABLE_TARGET",
             "detail": json.dumps(report, ensure_ascii=False, default=str)[:400]}
            for report in card_reports if not report.get("proposal_ids")
        ]
        return {"proposals": proposals, "unlocated": unlocated,
                "scope": getattr(result, "scope", None),
                "card_reports": card_reports,
                "diagnostics": list(getattr(result, "diagnostics", []) or []),
                "stats": dict(getattr(result, "stats", {}) or {})}

    return locate


def _default_writer() -> Callable:
    # Line 3's writer entry (contract: fundlex/direct_edit_writer.py).
    fn = _import_callable("fundlex.direct_edit_writer", ("write_direct_edits",))
    if fn is None:
        raise DirectPipelineError("DIRECT_WRITER_UNAVAILABLE")
    return fn


def build_write_scope(card_document: Mapping[str, Any], source_sha256: str) -> dict[str, Any]:
    """Derive the writer authorization scope from the frozen card pack.

    One entry per card; section names are the card's own free-text
    ``target.contract_sections``.  The writer independently re-derives the
    allowed locations from its own inspection, so over-broad text here never
    widens real write access.  Summary-zone authorization stays conservative:
    only sections whose name names the summary area (摘要) authorize summary
    writes (line 3's summary authorization is still under review).
    """
    entries: list[dict[str, Any]] = []
    cards = card_document.get("cards")
    for card in cards if isinstance(cards, list) else []:
        if not isinstance(card, Mapping):
            continue
        card_id = str(card.get("card_id") or "")
        if not card_id:
            continue
        sections = [str(s) for s in ((card.get("target") or {}).get("contract_sections") or [])
                    if str(s).strip()]
        summary_sections = [s for s in sections if "摘要" in s]
        entries.append({
            "scope_id": f"S-{card_id}",
            "rule_card_ids": [card_id],
            "sections": sections,
            "summary": bool(summary_sections),
            "summary_sections": summary_sections,
        })
    return {"schema_version": "direct_write_scope_v1",
            "source_sha256": source_sha256,
            "entries": entries}


def _scope_ref_for(card_document: Mapping[str, Any], proposals: list[Mapping[str, Any]]) -> None:
    """Fill missing scope_ref values with the per-card scope id convention."""
    for proposal in proposals:
        if isinstance(proposal, Mapping) and not proposal.get("scope_ref"):
            card_id = proposal.get("rule_card_id")
            if card_id:
                proposal["scope_ref"] = f"S-{card_id}"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def process_direct_edit(input_path: Path, output_dir: Path, *,
                        card_document: Mapping[str, Any], guide: Mapping[str, Any],
                        model_snapshot: Mapping[str, Any] | None = None,
                        source_sha256: str, gateway: Any = None,
                        locate: Locate | None = None, write: Write | None = None,
                        document_id: str = "", mode: str = "delivery") -> dict[str, Any]:
    """Run the direct path for one contract; build the direct_edit_v1 report."""
    if mode != "delivery":
        raise DirectPipelineError("DIRECT_MODE_UNSUPPORTED")
    report: dict[str, Any] = {
        "report_contract": REPORT_CONTRACT,
        "engine_id": ENGINE_ID,
        "engine_version": ENGINE_VERSION,
        "execution_mode": "delivery",
        "created_at": time.time(),
        "document_id": document_id,
        "source_sha256": source_sha256,
        "guide": {
            "version_id": str(guide.get("version_id") or ""),
            "schema_version": str(guide.get("schema_version") or ""),
            "document_sha256": str(guide.get("document_sha256") or ""),
            "parser_version": str(guide.get("parser_version") or ""),
            # 裁决 D4：报告自包含的冻结卡轻量快照（changes[] 不带标题）。
            "cards": [{"card_id": str(c.get("card_id") or ""), "title": str(c.get("title") or "")}
                      for c in (card_document.get("cards") or []) if isinstance(c, Mapping)],
        },
        "model": dict(model_snapshot or {}),
        "delivery_status": "not_generated",
        "qualification_status": "failed",
        "error_code": None,
        "errors": [],
    }

    # FL-D1076+FL-D1115: 入口归一序——先 prepare_compare_input（既往修订并入定稿）、
    # 再 sanitize_docx_external_links（剥惰性外链），最终字节+哈希为全程唯一指纹。
    # 均为幂等变换：下游引擎/写回器各自重复同一套不会改哈希（SCOPE_SOURCE_HASH_MISMATCH 互撞的根除）。
    from .compare.revisions import prepare_compare_input
    from .docx import sanitize_docx_external_links

    raw_bytes = Path(input_path).read_bytes()
    prepared = prepare_compare_input(raw_bytes)
    report["preparation"] = {
        "revisions_accepted": getattr(prepared, "revisions_accepted", 0),
        "changed": bool(prepared.data != raw_bytes),
        "original_sha256": getattr(prepared, "original_sha256", source_sha256),
    }
    sanitization = sanitize_docx_external_links(prepared.data)
    report["sanitization"] = {
        "original_sha256": source_sha256,
        "sanitized_sha256": source_sha256,
        "journal": [dict(entry) if isinstance(entry, Mapping) else entry
                    for entry in sanitization.journal],
    }
    normalization_changed = bool(sanitization.journal) or bool(prepared.data != raw_bytes)
    if normalization_changed:
        stage_dir = output_dir / ".normalize-stage"
        stage_dir.mkdir(parents=True, exist_ok=True)
        staged_input = stage_dir / Path(input_path).name
        staged_input.write_bytes(sanitization.data)
        input_path = staged_input
        source_sha256 = hashlib.sha256(sanitization.data).hexdigest()
        report["source_sha256"] = source_sha256
        report["sanitization"]["sanitized_sha256"] = source_sha256

    locate_fn = locate or _default_locator()
    write_fn = write or _default_writer()

    cards = card_document.get("cards")
    card_count = len(cards) if isinstance(cards, list) else 0
    if card_count == 0:
        raise DirectPipelineError("GUIDE_CARD_DOCUMENT_INVALID")
    if gateway is None:
        from .model import ModelGateway
        gateway = ModelGateway.from_env()

    scope = build_write_scope(card_document, source_sha256)
    outcome = locate_fn(input_path, card_document, gateway, scope=scope)
    if not isinstance(outcome, Mapping):
        raise DirectPipelineError("DIRECT_LOCATE_INVALID_RESULT")
    # The locating line derives the authoritative write scope from its own
    # inspection (FL-D1029 precise summary whitelist); only fixtures fall back
    # to the card-derived scope.
    if isinstance(outcome.get("scope"), Mapping):
        scope = dict(outcome["scope"])
    proposals = [p for p in (outcome.get("proposals") or []) if isinstance(p, Mapping)]
    unlocated = [u for u in (outcome.get("unlocated") or []) if isinstance(u, Mapping)]
    report["unlocated"] = [dict(u) for u in unlocated]
    proposals = [dict(p) for p in proposals]
    _scope_ref_for(card_document, proposals)

    for proposal in proposals:
        proposal.setdefault("schema_version", "direct_edit_proposal_v1")
        proposal.setdefault("source_sha256", source_sha256)

    redline_path = output_dir / "redline.docx"
    final_path = output_dir / "final.docx"
    # Freeze the located proposals and mint the generation ledger at the worker
    # boundary (FL-D1030): the writer binds every edit to this ledger, so
    # text altered between locating and write-back is rejected, not written.
    from .direct_edit_writer import freeze_proposals
    frozen_proposals, generation_ledger = freeze_proposals(
        proposals, frozen_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    try:
        result = write_fn(input_path, frozen_proposals, scope, redline_path, final_path,
                          generation_ledger=generation_ledger, author="FundLex")
    except DirectPipelineError:
        raise
    except Exception as exc:  # noqa: BLE001 - writer technical failure is terminal but honest
        from .docx import DocxError
        if isinstance(exc, DocxError):
            raise DirectPipelineError(str(exc.code or "DIRECT_WRITER_FAILED")) from exc
        raise

    write_result = result.to_dict() if hasattr(result, "to_dict") else dict(result)
    if not isinstance(write_result, Mapping):
        raise DirectPipelineError("DIRECT_WRITER_INVALID_RESULT")
    count = int(write_result.get("actual_written_count") or 0)
    status = str(write_result.get("status") or "")
    if status == "zero_written" or count == 0:
        delivery_status = "incomplete"
    elif status == "written" and count >= 1:
        delivery_status = "complete"
    else:
        raise DirectPipelineError("DIRECT_WRITER_INVALID_RESULT")

    actual = Path(write_result.get("final_path") or final_path)
    actual_redline = Path(write_result.get("redline_path") or redline_path)
    if delivery_status == "complete":
        for produced, target in ((actual, final_path), (actual_redline, redline_path)):
            if not produced.is_file():
                raise DirectPipelineError("DIRECT_WRITER_ARTIFACT_MISSING")
            if produced != target and not target.exists():
                produced.replace(target)
        file_final_sha, file_redline_sha = sha256_file(final_path), sha256_file(redline_path)
        if (write_result.get("final_sha256") not in (None, file_final_sha)
                or write_result.get("redline_sha256") not in (None, file_redline_sha)):
            raise DirectPipelineError("DIRECT_WRITER_HASH_MISMATCH")
        if str(write_result.get("source_sha256") or source_sha256) != source_sha256:
            raise DirectPipelineError("DIRECT_WRITER_SOURCE_MISMATCH")
        reopen_ok = bool(write_result.get("checks")) and count == len(
            [c for c in (write_result.get("changes") or []) if c.get("status") == "written"])
        if not reopen_ok:
            raise DirectPipelineError("DIRECT_WRITER_REOPEN_FAILED")
        report["direct_edit"] = {
            "schema_version": REPORT_CONTRACT,
            "writer_schema_version": write_result.get("schema_version"),
            "writer_version": write_result.get("engine_writer_version"),
            "actual_written_count": count,
            "reopen_verified": True,
            "pair_token": uuid.uuid4().hex,
            "artifacts": {
                "final_sha256": file_final_sha,
                "redline_sha256": file_redline_sha,
                "plan_sha256": write_result.get("plan_sha256"),
                "final_size": final_path.stat().st_size,
                "redline_size": redline_path.stat().st_size,
            },
            "changes": list(write_result.get("changes") or []),
            "skipped": list(write_result.get("skipped") or []),
            "revision_manifest": list(write_result.get("revision_manifest") or []),
            "source_revision_manifest": list(write_result.get("source_revision_manifest") or []),
            # 用户拍板 C：修订档位透传（normalized_base 档照样凭实写数与产物门
            # 判 complete，但对外报告/文档行必须带档位标记供前端标注）。
            "revision_tier": (write_result.get("revision_tier")
                              if isinstance(write_result, Mapping)
                              else None) or "strict_dual_layer",
            "generation_ledger": generation_ledger,
            "write_result": write_result,
        }
        report["artifacts"] = {"final": final_path.name, "redline": redline_path.name}
        report["revision_manifest"] = list(write_result.get("revision_manifest") or [])
        report["qualification_status"] = "qualified"
    else:
        # Zero actual writes: honest "未完成".  No DOCX may be published; an
        # unmodified source file must never masquerade as the final contract.
        report["direct_edit"] = {
            "schema_version": REPORT_CONTRACT,
            "writer_schema_version": write_result.get("schema_version"),
            "writer_version": write_result.get("engine_writer_version"),
            "actual_written_count": 0,
            "reopen_verified": False,
            "pair_token": "",
            "artifacts": {"final_sha256": None, "redline_sha256": None,
                          "plan_sha256": write_result.get("plan_sha256")},
            "changes": [],
            "skipped": list(write_result.get("skipped") or []),
            "revision_manifest": [],
            "source_revision_manifest": [],
            "revision_tier": (write_result.get("revision_tier")
                              if isinstance(write_result, Mapping)
                              else None) or "strict_dual_layer",
            "write_result": write_result,
        }
        report["unresolved"] = [
            {"code": "DIRECT_NO_WRITABLE_EDIT",
             "reason": "zero proposals survived locating and write-back verification",
             "unlocated": len(unlocated),
             "skipped": len(write_result.get("skipped") or [])},
        ]
        report["qualification_status"] = "qualified"
        report["diagnostics"] = {"card_count": card_count,
                                 "proposal_count": len(proposals)}
    report["delivery_status"] = delivery_status
    diagnostics = {"card_count": card_count, "proposal_count": len(proposals),
                   "locate_stats": outcome.get("stats") or {},
                   "card_reports": outcome.get("card_reports") or []}
    report["diagnostics"] = {**report.get("diagnostics", {}), **diagnostics}
    return report
