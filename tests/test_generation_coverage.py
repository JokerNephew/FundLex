"""Phase 1 acceptance tests: Coverage Ledger read-only view (plan v4 §16, §22).

The projection maps the existing report state onto the five terminal states;
it must not invent new semantics (report consumers keep seeing the same
report), and the last audit verdict per target wins (repair rounds overwrite).
"""
from fundlex.generation import build_coverage_view
from fundlex.generation.coverage import TERMINAL_STATES


def _report(**overrides) -> dict:
    report = {
        "targets": [
            {"target_id": "T1", "rule_id": "G01", "location": "p10",
             "state": "satisfied", "reason": "survey_new_text_present"},
            {"target_id": "T2", "rule_id": "G08", "location": "p20",
             "state": "needs_edit", "reason": ""},
            {"target_id": "T3", "rule_id": "G14", "location": "p30",
             "state": "needs_edit", "reason": ""},
            {"target_id": "T4", "rule_id": "G15", "location": "p40",
             "state": "absent", "reason": ""},
        ],
        "audit": {"rounds": [{"results": [
            {"target_id": "T2", "rule_id": "G08", "verdict": "completed"},
            {"target_id": "T3", "rule_id": "G14", "verdict": "wrong"},
        ]}]},
        "unresolved": [
            {"kind": "audit", "code": "AUDIT_NOT_COMPLETED",
             "rule_id": "G14", "target_id": "T3", "location": "p30"},
        ],
    }
    report.update(overrides)
    return report


def test_projection_maps_every_terminal_state():
    view = build_coverage_view(_report())
    assert view.state_of("G01", "p10") == "ALREADY_SATISFIED"
    assert view.state_of("G08", "p20") == "SATISFIED"
    assert view.state_of("G14", "p30") == "UNRESOLVED"
    assert view.state_of("G15", "p40") == "NOT_APPLICABLE"


def test_unresolved_entries_block_completion_and_are_visible():
    view = build_coverage_view(_report())
    bases = {entry.basis for entry in view.unresolved}
    assert "audit_wrong" in bases
    assert "unresolved:AUDIT_NOT_COMPLETED" in bases
    assert set(view.counts) == set(TERMINAL_STATES)


def test_last_audit_verdict_wins_across_repair_rounds():
    report = _report(audit={"rounds": [
        {"results": [{"target_id": "T2", "rule_id": "G08", "verdict": "wrong"}]},
        {"results": [{"target_id": "T2", "rule_id": "G08", "verdict": "completed"}]},
    ]})
    assert build_coverage_view(report).state_of("G08", "p20") == "SATISFIED"


def test_artifact_claim_replay_upgrades_satisfied():
    report = _report(artifact_claim_replay={"verified": True})
    assert build_coverage_view(report).state_of("G08", "p20") == "ARTIFACT_VERIFIED"


def test_missing_audit_record_is_unresolved_not_silent():
    report = _report(audit={}, unresolved=[])
    assert build_coverage_view(report).state_of("G08", "p20") == "UNRESOLVED"
