"""Cross-layer reconciliation: every applicable obligation must close at one layer.

FL-D652 / FL-D653 (mechanism A of the "该改未改" overhaul): the engine's proof
layers (target resolution → plan → final/edit list → claim replay → Ledger) were
each internally consistent but could disagree silently.  The measured cases:

* a replay PASS proof the Ledger did not adopt (FL-D589/651 family),
* a TRUE obligation that never received a plan edit (FL-D588 B17 family),
* a plan edit that never reached the executed edit list,
* an edit that wrote text whose effect replay could not prove,
* a model ``not_applicable`` swing that left the obligation open (FL-D643/650
  family — the deterministic layers must never fabricate a closure here),
* a recovery-created target without a backing Ledger claim (B19 family).

This module reconciles the layers *after* the final Ledger projection and emits
a machine- and user-readable ``miss_classification`` section.  A replay-proof
that the Ledger ignored is upgraded to an explicit blocking row; nothing is
ever auto-closed.  All logic is deterministic — model output only enters via
the recorded plan/replay data.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .generation.effects import effect_proof_passed

SCHEMA = "fundlex-reconciliation-v1"

#: Layer that owns each classification.  ``stage_owner`` is the first party that
#: must fix a miss; ``closure_layer`` says where a closed obligation closed.
CLASS_TEXT: dict[str, dict[str, str]] = {
    "CLOSED_REPLAY": {
        "zh": "义务已由交付前独立复核（claim replay）证明完成。",
        "en": "Obligation closed with an independent claim-replay proof.",
        "owner": "replay",
    },
    "CLOSED_DETERMINISTIC": {
        "zh": "义务由确定性层判定无需修改或已满足（缺席/已满足/资格排除）。",
        "en": "Obligation closed deterministically (absent, already satisfied or "
              "disqualified); no artifact change was required.",
        "owner": "plan",
    },
    "MISS_TARGET_RESOLUTION": {
        "zh": "规则适用，但未能在合同中定位到需要修改的原文（目标解析失败）。",
        "en": "The rule applies but no source span to change could be located "
              "(target resolution failure).",
        "owner": "targeting",
    },
    "MISS_MODEL_DEFERRAL": {
        "zh": "审核模型判断该处不适用，但确定性层未获证据；为避免误改暂不修改，"
              "作为待人工复核的诚实扣件保留。",
        "en": "The review model deemed this site not applicable and the "
              "deterministic layer could not confirm; left unmodified on "
              "purpose and held for human review.",
        "owner": "model",
    },
    "MISS_RECOVERY_GENERATED": {
        "zh": "恢复通道补造的目标缺乏既有台账依据；该目标保留阻断但不计入"
              "既有义务的正当欠缺。",
        "en": "A recovery-created target without backing Ledger evidence; kept "
              "blocking but not charged against an existing obligation's "
              "legitimate gap.",
        "owner": "recovery",
    },
    "MISS_PLAN_GAP": {
        "zh": "规则适用且目标存在，但计划轮没有为该义务生成修改动作（计划缺口）。",
        "en": "The rule applies and a target exists, but the planning stage "
              "emitted no edit for this obligation (plan gap).",
        "owner": "plan",
    },
    "MISS_EDIT_LOST": {
        # Not emitted by the current classifier: the Ledger drops ``edit_ids``
        # for open records, so a lost plan edit is indistinguishable from an
        # unproven effect at this layer and conservatively reported as
        # ``MISS_EFFECT_UNPROVEN``.  Kept as a stable public class for wire
        # compatibility once plan-side binding evidence exists.
        "zh": "计划轮已生成修改动作，但该动作在最终台账中失去绑定（跨层丢失）。",
        "en": "The planning stage recorded an edit that lost its binding in the "
              "final ledger (lost between layers).",
        "owner": "edit",
    },
    "MISS_EFFECT_UNPROVEN": {
        "zh": "修改动作已写入产物，但独立复核未能证明其效果（效果未证）。",
        "en": "The edit was written to the artifact, but independent replay "
              "could not prove its effect.",
        "owner": "replay",
    },
    "MISS_COVERAGE_RESIDUAL": {
        "zh": "覆盖审计在最终产物中仍发现该义务缺少闭环证明（覆盖残余）。",
        "en": "The final coverage sweep still finds no closing proof for this "
              "obligation in the artifact.",
        "owner": "coverage",
    },
    "MISS_REPLAY_GATE": {
        "zh": "独立复核已证明完成，但台账层未采纳该证明（跨层隔膜）；引擎按未闭合"
              "阻断并显式升级记录。",
        "en": "Independent replay proved completion but the Ledger did not "
              "adopt the proof (cross-layer diaphragm); the engine keeps the "
              "obligation blocked and records the mismatch explicitly.",
        "owner": "ledger",
    },
    "MISS_REVIEW_PENDING": {
        "zh": "义务处于待复核开放状态，未归入更具体的缺口类别。",
        "en": "The obligation remains open in a review-pending state without a "
              "more specific gap classification.",
        "owner": "coverage",
    },
}

BLOCKING_ESCALATION_CODE = "RECONCILIATION_LAYER_MISMATCH"


def _norm(value: Any) -> str:
    return str(value or "").upper()


def _ledger_cause(completion_evidence: str) -> bool:
    """Whether the open Ledger record already names a competing cause."""
    value = str(completion_evidence or "").strip().upper()
    if not value:
        return False
    # These prefixes are bookkeeping defaults, not causes: an open record whose
    # only evidence is the generic bracket is still an unexplained diaphragm.
    return not value.startswith(("OPEN_OBLIGATION", "APPLICABLE_WITHOUT_SITE_PROOF"))


def _binding_keys(edit: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    """(operation ids, obligation ids) an executed/planned edit claims to serve."""
    evidence = edit.get("evidence") if isinstance(edit.get("evidence"), Mapping) else {}
    ops = {str(v) for v in (evidence.get("operation_keys") or [])}
    obligations = {str(v) for v in (evidence.get("obligation_ids") or [])}
    for key in ("operation",):
        if edit.get(key):
            ops.add(str(edit[key]))
    edit_id = str(edit.get("edit_id") or "")
    # ``G14:0``-shaped ids both identify the rule and the operation.
    if ":" in edit_id:
        ops.add(edit_id)
    return ops, obligations


def _edit_binds(edit: Mapping[str, Any], *, rule_id: str, operation_id: str,
                obligation_id: str, target_ids: set[str]) -> bool:
    if str(edit.get("rule_id") or "") != rule_id:
        return False
    ops, obligations = _binding_keys(edit)
    if obligation_id and obligation_id in obligations:
        return True
    if operation_id in ops:
        return True
    if target_ids and str(edit.get("target_id") or "") in target_ids:
        return True
    return False


def _replay_proof(replay: Mapping[str, Any], obligation_id: str) -> Mapping[str, Any] | None:
    obligations = replay.get("obligations")
    if not isinstance(obligations, Mapping):
        return None
    proof = obligations.get(obligation_id)
    return proof if isinstance(proof, Mapping) else None


def classify_record(record: Any, *, plan_edits: list[Mapping[str, Any]],
                    target_rows: Mapping[str, Mapping[str, Any]],
                    recovery_target_rules: set[str],
                    replay: Mapping[str, Any]) -> dict[str, Any] | None:
    """Classify one Ledger record.  Returns ``None`` for non-applicable records."""
    status = _norm(getattr(getattr(record, "applicability", None), "status", ""))
    if status != "TRUE":
        return None
    spec = record.spec
    rule_id = str(spec.rule_id)
    operation_id = str(spec.operation_id)
    obligation_id = str(record.obligation_id)
    sites = [str(v) for v in (getattr(record, "sites", ()) or ())]
    target_ids = {str(v) for v in (getattr(record, "targets", ()) or ())}
    targets = [target_rows[tid] for tid in sorted(target_ids) if tid in target_rows]

    proof = _replay_proof(replay, obligation_id)
    proof_passed = bool(proof is not None and effect_proof_passed(
        proof, operation_id=operation_id, obligation_id=obligation_id))
    entry = {
        "obligation_id": obligation_id,
        "rule_id": rule_id,
        "operation_id": operation_id,
        "sites": sites,
        "target_ids": sorted(target_ids),
        "completion": _norm(getattr(record, "completion", "")),
        "replay_state": _norm(proof.get("state")) if proof else "",
        "closure_layer": "",
        "miss_class": "",
        "message_zh": "",
        "en": "",
    }

    declared = [edit for edit in plan_edits
                if _edit_binds(edit, rule_id=rule_id, operation_id=operation_id,
                               obligation_id=obligation_id, target_ids=target_ids)]
    ledger_edit_ids = {str(v) for v in (getattr(record, "edit_ids", ()) or ())}

    def _finish(miss_class: str, closure_layer: str) -> dict[str, Any]:
        text = CLASS_TEXT[miss_class]
        entry.update(miss_class=miss_class, closure_layer=closure_layer,
                     stage_owner=text["owner"],
                     message_zh=text["zh"], en=text["en"])
        return entry

    if bool(getattr(record, "closed", False)):
        if proof_passed:
            return _finish("CLOSED_REPLAY", "replay")
        return _finish("CLOSED_DETERMINISTIC", "plan")

    # Fail-closed upgrade: replay has a proof the Ledger never adopted.  This is
    # the silent diaphragm family (FL-D589/651).  Only an *unexplained* open
    # record escalates to a blocking row: when the Ledger already carries a
    # named competing cause (e.g. an audit evidence row that policy treats as a
    # review item), that cause's own rows drive blocking and a second
    # reconciliation blocker would conflict with review-assisted delivery.
    if proof_passed:
        entry = _finish("MISS_REPLAY_GATE", "none")
        cause = str(getattr(record, "completion_evidence", "") or "").strip().upper()
        # A Ledger cause that names a replay failure is directly refuted by the
        # PASS proof and must escalate just like an unexplained open record.
        contradicted = cause.startswith("CLAIM_REPLAY")
        entry["escalate"] = contradicted or not _ledger_cause(cause)
        return entry

    if rule_id in recovery_target_rules:
        return _finish("MISS_RECOVERY_GENERATED", "none")
    if not target_ids or not targets:
        if not declared:
            return _finish("MISS_TARGET_RESOLUTION", "none")
    elif all(_norm(row.get("state")) == "NOT_APPLICABLE" for row in targets) \
            and not declared:
        return _finish("MISS_MODEL_DEFERRAL", "none")
    if not declared:
        return _finish("MISS_PLAN_GAP", "none")
    if proof is not None and _norm(proof.get("state")) == "FAIL":
        return _finish("MISS_EFFECT_UNPROVEN", "none")
    if not proof_passed:
        return _finish("MISS_EFFECT_UNPROVEN", "none")
    return _finish("MISS_REVIEW_PENDING", "none")


def reconcile(report: Mapping[str, Any], ledger: Any) -> dict[str, Any]:
    """Build the cross-layer classification for every applicable obligation."""
    records = getattr(ledger, "records", ()) or ()
    replay = report.get("artifact_claim_replay") if isinstance(
        report.get("artifact_claim_replay"), Mapping) else {}
    plan_edits = [dict(edit) for edit in
                  ((report.get("plan") or {}).get("edits") or [])]
    target_rows = {
        str(row.get("target_id") or ""): row
        for row in (report.get("targets") or [])
        if isinstance(row, Mapping) and row.get("target_id")
    }
    recovery_target_rules = {
        str(reason.split(":", 2)[1])
        for row in (report.get("targets") or [])
        for reason in [str((row or {}).get("reason") or "")]
        if reason.startswith("recovery_missing_operation:")
    }

    entries: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for record in records:
        entry = classify_record(record, plan_edits=plan_edits,
                                target_rows=target_rows,
                                recovery_target_rules=recovery_target_rules,
                                replay=replay)
        if entry is None:
            continue
        entries.append(entry)
        key = entry["miss_class"] or "UNKNOWN"
        counts[key] = counts.get(key, 0) + 1
    misses = [entry for entry in entries
              if not entry["miss_class"].startswith("CLOSED_")]
    return {
        "schema": SCHEMA,
        "summary": {
            "applicable_obligations": len(entries),
            "closed": len(entries) - len(misses),
            "misses": len(misses),
            "counts": counts,
        },
        "entries": entries,
    }


def apply_reconciliation(report: dict[str, Any], ledger: Any,
                         unresolved: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Attach the classification to the report and escalate silent diaphragms.

    * ``report["miss_classification"]`` receives :func:`reconcile` output.
    * Every open obligation row in ``unresolved`` gets its classification under
      ``miss`` so downstream renderers can print the bilingual reason.
    * ``MISS_REPLAY_GATE`` entries become explicit blocking rows
      (``RECONCILIATION_LAYER_MISMATCH``); an unknown taxonomy code blocks under
      every delivery policy, which is the intended fail-closed behaviour.
    """
    result = reconcile(report, ledger)
    report["miss_classification"] = result
    by_obligation = {entry["obligation_id"]: entry for entry in result["entries"]}
    if unresolved is None:
        return result
    for item in unresolved:
        entry = by_obligation.get(str(item.get("obligation_id") or ""))
        if entry is not None and entry["miss_class"].startswith("MISS_"):
            item["miss"] = {key: entry[key] for key in
                            ("miss_class", "stage_owner", "message_zh", "en")}
    escalated = {str(item.get("obligation_id") or "") for item in unresolved
                 if item.get("kind") == "reconciliation"}
    for entry in result["entries"]:
        if entry["miss_class"] != "MISS_REPLAY_GATE" or not entry.get("escalate"):
            continue
        if entry["obligation_id"] in escalated:
            continue
        unresolved.append({
            "kind": "reconciliation",
            "code": BLOCKING_ESCALATION_CODE,
            "rule_id": entry["rule_id"],
            "obligation_id": entry["obligation_id"],
            "operation_id": entry["operation_id"],
            "reason": BLOCKING_ESCALATION_CODE + ":" + entry["replay_state"],
            "failure_class": "VERIFICATION",
            "location": (entry["sites"] or [""])[0],
            "message_zh": entry["message_zh"],
            "en": entry["en"],
        })
    return result
