"""Cross-layer reconciliation (FL-D653, mechanism A of the 该改未改 overhaul).

Every applicable obligation must close at exactly one layer; when replay proves
what the Ledger never adopted the mismatch must become an explicit blocking
row, and every remaining miss must carry a machine class plus bilingual text.
"""
from __future__ import annotations

from fundlex.applicability import ApplicabilityDecision
from fundlex.obligations import compile_obligations
from fundlex.reconciliation import (BLOCKING_ESCALATION_CODE, CLASS_TEXT,
                                    apply_reconciliation, reconcile)


def _rule(rule_id="G05", *, operations=None):
    return {
        "rule_id": rule_id,
        "title": rule_id,
        "section_hint": "基金份额的申购与赎回",
        "requirement": f"requirement {rule_id}",
        "operations": operations or [
            {"op": "replace", "old_text": "旧句一", "new_text": "新句一",
             "condition": {"kind": "none", "value": None}},
        ],
        "old_text_variants": [],
    }


def _ledger(*rules):
    return compile_obligations({"groups": list(rules)})


def _true(record, *, targets=("T1",), sites=("p5",)):
    record.applicability = ApplicabilityDecision(
        status="TRUE", condition=record.spec.condition,
        rule_id=record.spec.rule_id, operation_id=record.spec.operation_id,
        source="test", reason="forced", evidence_quote="")
    record.targets = tuple(targets)
    record.sites = tuple(sites)
    return record


def _pass_proof(record, *, status="EXPECTED_EFFECT_PRESENT"):
    sites = list(record.sites)
    evidence = [{"proof_kind": "site_final_plan_reconstruction",
                 "rule_id": record.spec.rule_id,
                 "operation_id": record.spec.operation_id,
                 "obligation_id": record.obligation_id,
                 "site_id": site, "location": site} for site in sites]
    site_effects = [{"site_id": site, "location": site,
                     "rule_id": record.spec.rule_id,
                     "operation_id": record.spec.operation_id,
                     "obligation_id": record.obligation_id,
                     "state": "PASS", "artifact_status": status,
                     "failure_code": ""} for site in sites]
    return {"state": "PASS", "artifact_status": status,
            "rule_id": record.spec.rule_id,
            "operation_id": record.spec.operation_id,
            "obligation_id": record.obligation_id,
            "failure_code": "", "edit_ids": ["E1"],
            "evidence": evidence, "site_effects": site_effects,
            "sites": sites}


def _target_row(target_id="T1", rule_id="G05", *, state="needs_edit", reason="survey"):
    return {"target_id": target_id, "rule_id": rule_id, "state": state,
            "reason": reason, "location": "p5", "status": "planned"}


def _record(ledger, obligation_id):
    index = int(obligation_id.rsplit(":O", 1)[1]) - 1
    return ledger.records[index]


def test_closed_replay_proof_is_replay_closure():
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"))
    record.completion = "ARTIFACT_VERIFIED"
    record.completion_evidence = "claim_replay:EXPECTED_EFFECT_PRESENT"
    report = {"artifact_claim_replay": {"obligations": {
        record.obligation_id: _pass_proof(record)}},
        "plan": {"edits": []}, "targets": [_target_row()]}
    view = reconcile(report, ledger)
    entry = view["entries"][0]
    assert entry["miss_class"] == "CLOSED_REPLAY"
    assert entry["closure_layer"] == "replay"
    assert view["summary"] == {"applicable_obligations": 1, "closed": 1,
                               "misses": 0, "counts": {"CLOSED_REPLAY": 1}}


def test_deterministic_closure_without_edit():
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"), targets=(), sites=())
    record.completion = "ALREADY_SATISFIED"
    record.completion_evidence = "absent_delete_coverage:scoped_scan"
    report = {"artifact_claim_replay": {"obligations": {}},
              "plan": {"edits": []}, "targets": []}
    view = reconcile(report, ledger)
    entry = view["entries"][0]
    assert entry["miss_class"] == "CLOSED_DETERMINISTIC"
    assert entry["closure_layer"] == "plan"


def test_replay_pass_but_ledger_open_is_escalated_and_blocking():
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"))
    report = {"artifact_claim_replay": {"obligations": {
        record.obligation_id: _pass_proof(record)}},
        "plan": {"edits": []}, "targets": [_target_row()]}
    unresolved: list[dict] = []
    result = apply_reconciliation(report, ledger, unresolved)
    entry = result["entries"][0]
    assert entry["miss_class"] == "MISS_REPLAY_GATE"
    assert len(unresolved) == 1
    escalation = unresolved[0]
    assert escalation["code"] == BLOCKING_ESCALATION_CODE
    assert escalation["kind"] == "reconciliation"
    assert escalation["obligation_id"] == record.obligation_id
    assert escalation["failure_class"] == "VERIFICATION"
    # The row must block delivery: the code is outside every known taxonomy
    # and therefore fails closed under both delivery policies.
    from fundlex.delivery import requires_blocker
    assert requires_blocker(escalation) is True


def test_replay_pass_refuting_claim_failure_cause_still_escalates():
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"))
    record.completion_evidence = "CLAIM_REPLAY_FAILED"
    report = {"artifact_claim_replay": {"obligations": {
        record.obligation_id: _pass_proof(record)}},
        "plan": {"edits": []}, "targets": [_target_row()]}
    unresolved: list[dict] = []
    apply_reconciliation(report, ledger, unresolved)
    assert [row["code"] for row in unresolved] == [BLOCKING_ESCALATION_CODE]


def test_replay_pass_with_named_audit_cause_does_not_double_block():
    """A named non-replay cause keeps its own policy treatment (review item)."""
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"))
    record.completion_evidence = "AUDIT_EVIDENCE_UNVERIFIED"
    report = {"artifact_claim_replay": {"obligations": {
        record.obligation_id: _pass_proof(record)}},
        "plan": {"edits": []}, "targets": [_target_row()]}
    unresolved = [{"kind": "obligation", "code": "OPEN_OBLIGATION",
                   "rule_id": "G05", "obligation_id": record.obligation_id}]
    result = apply_reconciliation(report, ledger, unresolved)
    assert result["entries"][0]["miss_class"] == "MISS_REPLAY_GATE"
    assert result["entries"][0]["escalate"] is False
    # No extra blocker row; the open-obligation row still carries the class.
    assert len(unresolved) == 1
    assert unresolved[0]["miss"]["miss_class"] == "MISS_REPLAY_GATE"


def test_no_target_no_plan_is_target_resolution_gap():
    ledger = _ledger(_rule())
    _true(_record(ledger, "G05:B1:O1"), targets=(), sites=())
    report = {"artifact_claim_replay": {"obligations": {}},
              "plan": {"edits": []}, "targets": []}
    entry = reconcile(report, ledger)["entries"][0]
    assert entry["miss_class"] == "MISS_TARGET_RESOLUTION"
    assert entry["stage_owner"] == "targeting"


def test_model_not_applicable_swing_stays_honest_hold():
    ledger = _ledger(_rule())
    _true(_record(ledger, "G05:B1:O1"))
    report = {"artifact_claim_replay": {"obligations": {}},
              "plan": {"edits": []},
              "targets": [_target_row(state="not_applicable",
                                      reason="本窗口不存在旧句一")]}
    entry = reconcile(report, ledger)["entries"][0]
    assert entry["miss_class"] == "MISS_MODEL_DEFERRAL"
    assert "诚实扣件" in entry["message_zh"]


def test_recovery_generated_target_is_classified_not_retried():
    ledger = _ledger(_rule())
    _true(_record(ledger, "G05:B1:O1"), targets=("R1",))
    report = {"artifact_claim_replay": {"obligations": {}},
              "plan": {"edits": []},
              "targets": [_target_row("R1", reason="recovery_missing_operation:G05:0")]}
    entry = reconcile(report, ledger)["entries"][0]
    assert entry["miss_class"] == "MISS_RECOVERY_GENERATED"
    assert entry["stage_owner"] == "recovery"


def test_target_without_plan_edit_is_plan_gap():
    ledger = _ledger(_rule())
    _true(_record(ledger, "G05:B1:O1"))
    report = {"artifact_claim_replay": {"obligations": {}},
              "plan": {"edits": []}, "targets": [_target_row()]}
    entry = reconcile(report, ledger)["entries"][0]
    assert entry["miss_class"] == "MISS_PLAN_GAP"
    assert entry["stage_owner"] == "plan"


def test_planned_edit_with_failed_proof_is_effect_unproven():
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"))
    edit = {"rule_id": "G05", "target_id": "T1", "operation": "G05:0",
            "evidence": {"operation_keys": ["G05:0"],
                         "obligation_ids": [record.obligation_id]}}
    failing = {"state": "FAIL", "artifact_status": "WRONG_EFFECT",
               "rule_id": "G05", "operation_id": "G05:0",
               "obligation_id": record.obligation_id,
               "failure_code": "CLAIM_PLANNED_EFFECT_MISSING"}
    report = {"artifact_claim_replay": {"obligations": {record.obligation_id: failing}},
              "plan": {"edits": [edit]}, "targets": [_target_row()]}
    entry = reconcile(report, ledger)["entries"][0]
    assert entry["miss_class"] == "MISS_EFFECT_UNPROVEN"
    assert entry["stage_owner"] == "replay"


def test_open_obligation_row_is_enriched_not_duplicated():
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"))
    report = {"artifact_claim_replay": {"obligations": {}},
              "plan": {"edits": []}, "targets": [_target_row()]}
    unresolved = [{"kind": "obligation", "code": "OPEN_OBLIGATION",
                   "rule_id": "G05", "obligation_id": record.obligation_id}]
    apply_reconciliation(report, ledger, unresolved)
    assert unresolved[0]["miss"]["miss_class"] == "MISS_PLAN_GAP"
    assert unresolved[0]["miss"]["message_zh"]
    # Only replay-gate mismatches escalate; ordinary misses stay on their rows.
    assert len(unresolved) == 1


def test_applicability_false_records_are_not_classified():
    ledger = _ledger(_rule())
    record = _true(_record(ledger, "G05:B1:O1"))
    record.applicability = ApplicabilityDecision(
        status="FALSE", condition=record.spec.condition,
        rule_id=record.spec.rule_id, operation_id=record.spec.operation_id,
        source="test", reason="does not apply", evidence_quote="")
    record.completion = "NOT_APPLICABLE"
    view = reconcile({"artifact_claim_replay": {"obligations": {}},
                      "plan": {"edits": []}, "targets": []}, ledger)
    assert view["summary"]["applicable_obligations"] == 0
    assert view["entries"] == []


def test_every_class_has_bilingual_text_and_owner():
    for key, text in CLASS_TEXT.items():
        assert text["zh"].strip(), key
        assert text["en"].strip(), key
        assert text["owner"] in {"targeting", "plan", "edit", "replay",
                                 "coverage", "ledger", "model", "recovery"}
