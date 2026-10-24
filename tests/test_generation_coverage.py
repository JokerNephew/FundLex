"""Phase 1 acceptance tests: Coverage Ledger read-only view (plan v4 §16, §22).

The projection maps the existing report state onto the five terminal states;
it must not invent new semantics (report consumers keep seeing the same
report), and the last audit verdict per target wins (repair rounds overwrite).
"""
import json
from pathlib import Path

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


def test_state_of_operation_is_operation_aware():
    report = {
        "targets": [
            {"target_id": "T5", "rule_id": "G05", "location": "p50",
             "state": "needs_edit", "operations": ["G05:0"]},
        ],
        "audit": {"rounds": [{"results": [
            {"target_id": "T5", "rule_id": "G05", "verdict": "completed"}]}]},
        "unresolved": [],
    }
    view = build_coverage_view(report)
    assert view.state_of_operation("G05", "p50", "G05:0") == "SATISFIED"
    assert view.state_of_operation("G05", "p50", "G05:1") is None


def test_plan_level_not_applicable_or_satisfied_closes_the_target():
    report = {
        "targets": [
            {"target_id": "T1", "rule_id": "G20", "location": "p1",
             "state": "needs_edit", "operations": ["G20:0"]},
            {"target_id": "T2", "rule_id": "G02", "location": "p2",
             "state": "needs_edit", "operations": ["G02:0"]},
        ],
        "plan": {"ledger": [
            {"target_id": "T1", "status": "not_applicable"},
            {"target_id": "T2", "status": "satisfied"},
        ]},
        "audit": {"rounds": []}, "unresolved": [],
    }
    view = build_coverage_view(report)
    assert view.state_of("G20", "p1") == "NOT_APPLICABLE"
    assert view.state_of("G02", "p2") == "NOT_APPLICABLE"
    assert not view.unresolved


def test_obligation_projection_preserves_artifact_sites_and_operation_identity():
    report = {
        "obligations": {"records": [{
            "rule_id": "G15", "operation_id": "G15:0",
            "completion": "ARTIFACT_VERIFIED",
            "completion_evidence": "claim_replay:EXPECTED_EFFECT_PRESENT",
            "targets": ["T1", "T2"],
            "artifact_evidence": [
                {"location": "p821"}, {"location": "p1287"},
            ],
        }]},
        "targets": [
            {"target_id": "T1", "rule_id": "G15", "location": "p821"},
            {"target_id": "T2", "rule_id": "G15", "location": "p1287"},
        ],
        "unresolved": [],
    }
    view = build_coverage_view(report)
    assert view.state_of_operation("G15", "p821", "G15:0") == "ARTIFACT_VERIFIED"
    assert view.state_of_operation("G15", "p1287", "G15:0") == "ARTIFACT_VERIFIED"
    assert view.state_of_operation("G15", "", "G15:0") is None


def test_obligation_projection_does_not_double_count_same_open_finding():
    report = {
        "obligations": {"records": [{
            "rule_id": "G05", "operation_id": "G05:1",
            "completion": "UNRESOLVED", "completion_evidence": "CLAIM_REPLAY_FAILED",
            "targets": ["T1"], "artifact_evidence": [],
        }]},
        "targets": [{"target_id": "T1", "rule_id": "G05", "location": "p9"}],
        "unresolved": [{"kind": "claim_replay", "code": "CLAIM_REPLAY_FAILED",
                        "rule_id": "G05", "target_id": "T1", "location": "p9",
                        "operation_id": "G05:1"}],
    }
    view = build_coverage_view(report)
    assert view.counts["UNRESOLVED"] == 1


def test_coverage_view_serializes_entries_for_report_consumers():
    view = build_coverage_view({"obligations": {"records": [{
        "rule_id": "G01", "operation_id": "G01:0", "completion": "ALREADY_SATISFIED",
        "targets": [], "artifact_evidence": [],
    }]}})
    payload = view.as_dict()
    assert payload["entries"][0]["operation_keys"] == ["G01:0"]
    assert payload["counts"]["ALREADY_SATISFIED"] == 1


def test_artifact_and_target_same_site_are_one_operation_entry():
    report = {
        "obligations": {"records": [{
            "rule_id": "G02", "operation_id": "G02:0",
            "completion": "ARTIFACT_VERIFIED", "targets": ["T1"],
            "artifact_evidence": [{"location": "p93", "proof_kind": "site"}],
        }]},
        "targets": [{"target_id": "T1", "rule_id": "G02", "location": "p93"}],
        "unresolved": [],
    }
    view = build_coverage_view(report)
    assert view.counts["ARTIFACT_VERIFIED"] == 1
    assert len(view.entries) == 1
    assert view.entries[0].target_id == "T1"


def test_targetless_open_finding_does_not_duplicate_open_operation_site():
    report = {
        "obligations": {"records": [{
            "rule_id": "G06", "operation_id": "G06:0",
            "completion": "UNRESOLVED", "completion_evidence": "CLAIM_REPLAY_FAILED",
            "targets": ["T1"], "artifact_evidence": [],
        }]},
        "targets": [{"target_id": "T1", "rule_id": "G06", "location": "p129"}],
        "unresolved": [{"kind": "claim_replay", "rule_id": "G06",
                        "operation_id": "G06:0", "location": "",
                        "code": "CLAIM_OPERATION_UNPROVEN"}],
    }
    view = build_coverage_view(report)
    assert view.counts["UNRESOLVED"] == 1
    assert view.entries[0].location == "p129"


def test_partial_replay_projects_each_site_and_keeps_global_obligation_open():
    """D11 G18 regression: p800 passes while p1207 still fails."""
    report = {
        "obligations": {"records": [{
            "obligation_id": "G18:B1:O1", "rule_id": "G18", "operation_id": "G18:0",
            "completion": "UNRESOLVED", "completion_evidence": "CLAIM_REPLAY_FAILED",
            "targets": ["T800", "T1207"], "artifact_evidence": [],
        }]},
        "targets": [
            {"target_id": "T800", "rule_id": "G18", "location": "p800",
             "state": "needs_edit", "operations": ["G18:0"]},
            {"target_id": "T1207", "rule_id": "G18", "location": "p1207",
             "state": "needs_edit", "operations": ["G18:0"]},
        ],
        "artifact_claim_replay": {"obligations": {
            "G18:B1:O1": {
                "state": "FAIL", "failure_code": "CLAIM_OPERATION_NOT_PLANNED",
                "site_effects": [
                    {"site_id": "p800", "location": "p800", "operation_id": "G18:0",
                     "state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT",
                     "proof_kind": "site_final_plan_reconstruction"},
                    {"site_id": "p1207", "location": "p1207", "operation_id": "G18:0",
                     "state": "FAIL", "artifact_status": "MISSING_EFFECT",
                     "failure_code": "CLAIM_OPERATION_NOT_PLANNED",
                     "proof_kind": "site_literal_effect"},
                ],
            },
        }},
        "unresolved": [],
    }
    view = build_coverage_view(report)
    assert view.state_of_operation("G18", "p800", "G18:0") == "ARTIFACT_VERIFIED"
    assert view.state_of_operation("G18", "p1207", "G18:0") == "UNRESOLVED"
    assert view.counts["UNRESOLVED"] == 1
    assert view.site_counts["ARTIFACT_VERIFIED"] == 1
    assert view.site_counts["UNRESOLVED"] == 1


def test_absent_heading_is_not_projected_as_an_artifact_site():
    """D02 G01 p1036 is a summary heading, not a G01 business site."""
    report = {
        "obligations": {"records": [{
            "obligation_id": "G01:B1:O1", "rule_id": "G01", "operation_id": "G01:0",
            "completion": "ARTIFACT_VERIFIED", "completion_evidence": "claim_replay:EXPECTED_EFFECT_PRESENT",
            "targets": ["T93", "T1036"],
            "artifact_evidence": [{"site_id": "p93", "location": "p93",
                                    "proof_kind": "site_final_plan_reconstruction"}],
        }]},
        "targets": [
            {"target_id": "T93", "rule_id": "G01", "location": "p93",
             "state": "needs_edit", "operations": ["G01:0"]},
            {"target_id": "T1036", "rule_id": "G01", "location": "p1036",
             "state": "absent", "operations": ["G01:0"]},
        ],
        "unresolved": [],
    }
    view = build_coverage_view(report)
    assert view.state_of_operation("G01", "p93", "G01:0") == "ARTIFACT_VERIFIED"
    assert view.state_of_operation("G01", "p1036", "G01:0") is None
    assert all(entry.location != "p1036" for entry in view.entries)


def test_rebuilding_after_second_project_refreshes_site_projection():
    """A late project/replay update must be reflected by a fresh coverage view."""
    report = {
        "obligations": {"records": [{
            "obligation_id": "G18:B1:O1", "rule_id": "G18", "operation_id": "G18:0",
            "completion": "UNRESOLVED", "completion_evidence": "CLAIM_REPLAY_FAILED",
            "targets": ["T1"], "artifact_evidence": [],
        }]},
        "targets": [{"target_id": "T1", "rule_id": "G18", "location": "p1207",
                     "state": "needs_edit", "operations": ["G18:0"]}],
        "artifact_claim_replay": {"obligations": {
            "G18:B1:O1": {"state": "FAIL", "failure_code": "CLAIM_OPERATION_NOT_PLANNED",
                           "site_effects": [{"site_id": "p1207", "location": "p1207",
                                              "operation_id": "G18:0", "state": "FAIL",
                                              "failure_code": "CLAIM_OPERATION_NOT_PLANNED",
                                              "proof_kind": "site_literal_effect"}]},
        }},
    }
    first = build_coverage_view(report)
    assert first.state_of_operation("G18", "p1207", "G18:0") == "UNRESOLVED"

    # This represents the second obligations.project/replay pass in the final
    # pipeline. The old coverage_view object must never be reused after it.
    report["obligations"]["records"][0].update(
        completion="ARTIFACT_VERIFIED", completion_evidence="claim_replay:EXPECTED_EFFECT_PRESENT")
    report["artifact_claim_replay"]["obligations"]["G18:B1:O1"] = {
        "state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT",
        "site_effects": [{"site_id": "p1207", "location": "p1207", "operation_id": "G18:0",
                           "state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT",
                           "proof_kind": "site_final_plan_reconstruction"}],
        "evidence": [{"site_id": "p1207", "location": "p1207", "operation_id": "G18:0",
                      "proof_kind": "site_final_plan_reconstruction"}],
    }
    refreshed = build_coverage_view(report)
    assert refreshed is not first
    assert refreshed.state_of_operation("G18", "p1207", "G18:0") == "ARTIFACT_VERIFIED"
    assert refreshed.counts["UNRESOLVED"] == 0


def test_same_location_occurrences_keep_the_failed_occurrence_visible():
    report = {
        "obligations": {"records": [{
            "obligation_id": "G05:B1:O1", "rule_id": "G05", "operation_id": "G05:0",
            "completion": "UNRESOLVED", "targets": ["T1", "T2"],
        }]},
        "targets": [
            {"target_id": "T1", "rule_id": "G05", "location": "p7",
             "state": "needs_edit", "operations": ["G05:0"]},
            {"target_id": "T2", "rule_id": "G05", "location": "p7",
             "state": "needs_edit", "operations": ["G05:0"]},
        ],
        "artifact_claim_replay": {"obligations": {
            "G05:B1:O1": {"state": "FAIL", "site_effects": [
                {"site_id": "p7#occurrence:0", "location": "p7", "operation_id": "G05:0",
                 "state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT",
                 "proof_kind": "site_final_plan_reconstruction"},
                {"site_id": "p7#occurrence:1", "location": "p7", "operation_id": "G05:0",
                 "state": "FAIL", "artifact_status": "MISSING_EFFECT",
                 "failure_code": "CLAIM_OPERATION_NOT_PLANNED",
                 "proof_kind": "site_literal_effect"},
            ]},
        }},
    }
    view = build_coverage_view(report)
    assert {entry.site_id for entry in view.entries} == {
        "p7#occurrence:0", "p7#occurrence:1"}
    assert view.state_of_operation("G05", "p7", "G05:0") == "UNRESOLVED"
    assert view.counts["UNRESOLVED"] == 1
    assert view.site_counts["ARTIFACT_VERIFIED"] == 1
    assert view.site_counts["UNRESOLVED"] == 1


def test_counts_remain_record_completion_when_site_projection_is_stale():
    """Site failures are visible in entries without rewriting ledger counts."""
    report = {
        "obligations": {"records": [{
            "obligation_id": "G18:B1:O1", "rule_id": "G18", "operation_id": "G18:0",
            "completion": "ARTIFACT_VERIFIED", "targets": ["T1"],
        }]},
        "targets": [{"target_id": "T1", "rule_id": "G18", "location": "p1",
                     "state": "needs_edit", "operations": ["G18:0"]}],
        "artifact_claim_replay": {"obligations": {
            "G18:B1:O1": {"state": "FAIL", "site_effects": [{
                "site_id": "p1", "location": "p1", "operation_id": "G18:0",
                "state": "FAIL", "failure_code": "CLAIM_OPERATION_NOT_PLANNED",
                "proof_kind": "site_literal_effect"}]},
        }},
    }
    view = build_coverage_view(report)
    assert view.counts["ARTIFACT_VERIFIED"] == 1
    assert view.counts["UNRESOLVED"] == 0
    assert view.state_of_operation("G18", "p1", "G18:0") == "UNRESOLVED"
    assert view.site_counts["UNRESOLVED"] == 1


def test_real_d11_report_keeps_partial_g18_artifact_replay_visible():
    root = Path(__file__).resolve().parents[1]
    report_path = (root / "docs/evidence/final-validation-20261022"
                   / "gate-closure-4090a22/frozen/D11/report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    view = build_coverage_view(report)
    assert view.counts == report["obligations"]["counts"]
    assert sum(view.counts.values()) == len(report["obligations"]["records"])
    assert view.state_of_operation("G18", "p800", "G18:0") == "ARTIFACT_VERIFIED"
    assert view.state_of_operation("G18", "p1207", "G18:0") == "UNRESOLVED"
    assert view.site_counts["UNRESOLVED"] == 1


def test_real_d02_report_excludes_absent_heading_from_artifact_coverage():
    root = Path(__file__).resolve().parents[1]
    report_path = (root / "docs/evidence/final-validation-20261022"
                   / "gate-closure-4090a22/frozen/D02/report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    view = build_coverage_view(report)
    assert view.counts == report["obligations"]["counts"]
    assert view.state_of_operation("G01", "p93", "G01:0") == "ARTIFACT_VERIFIED"
    assert view.state_of_operation("G01", "p1036", "G01:0") is None
    assert sum(view.counts.values()) == len(report["obligations"]["records"])
    assert sum(view.site_counts.values()) > sum(
        view.counts[state] for state in ("ARTIFACT_VERIFIED", "ALREADY_SATISFIED"))


def test_unknown_and_conflict_site_effects_are_unresolved_even_after_pass():
    report = {
        "obligations": {"records": [{
            "obligation_id": "G08:B1:O1", "rule_id": "G08", "operation_id": "G08:0",
            "completion": "ARTIFACT_VERIFIED", "targets": ["T1"],
        }]},
        "targets": [{"target_id": "T1", "rule_id": "G08", "location": "p20",
                      "state": "needs_edit", "operations": ["G08:0"]}],
        "artifact_claim_replay": {"obligations": {
            "G08:B1:O1": {"state": "PASS", "site_effects": [
                {"site_id": "p20", "location": "p20", "operation_id": "G08:0",
                 "state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT",
                 "proof_kind": "site_final_plan_reconstruction"},
                {"site_id": "p20", "location": "p20", "operation_id": "G08:0",
                 "state": "UNKNOWN", "artifact_status": "UNKNOWN",
                 "failure_code": "VALIDATION_UNKNOWN",
                 "proof_kind": "site_final_plan_reconstruction"},
            ]},
        }},
    }
    view = build_coverage_view(report)
    assert view.state_of_operation("G08", "p20", "G08:0") == "UNRESOLVED"
    assert view.site_counts["UNRESOLVED"] == 1


def test_operation_query_does_not_use_a_sibling_operation_row():
    report = {
        "obligations": {"records": [{
            "obligation_id": "G05:B1:O1", "rule_id": "G05", "operation_id": "G05:0",
            "completion": "ARTIFACT_VERIFIED", "targets": [],
            "artifact_evidence": [{"location": "p9", "proof_kind": "site"}],
        }, {
            "obligation_id": "G05:B1:O2", "rule_id": "G05", "operation_id": "G05:1",
            "completion": "UNRESOLVED", "targets": [],
        }]},
    }
    view = build_coverage_view(report)
    assert view.state_of_operation("G05", "p9", "G05:0") == "ARTIFACT_VERIFIED"
    assert view.state_of_operation("G05", "p9", "G05:1") is None


def test_duplicate_operation_sites_keep_stable_target_identity():
    report = {
        "obligations": {"records": [{
            "obligation_id": "G05:B1:O1", "rule_id": "G05", "operation_id": "G05:0",
            "completion": "UNRESOLVED", "targets": ["T0", "T1"],
        }]},
        "targets": [
            {"target_id": "T0", "rule_id": "G05", "location": "p7",
             "occurrence_index": 0, "operations": ["G05:0"]},
            {"target_id": "T1", "rule_id": "G05", "location": "p7",
             "occurrence_index": 1, "operations": ["G05:0"]},
        ],
        "artifact_claim_replay": {"obligations": {
            "G05:B1:O1": {"site_effects": [
                {"site_id": "p7#occurrence:0", "location": "p7", "operation_id": "G05:0",
                 "state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT",
                 "proof_kind": "site_final_plan_reconstruction"},
                {"site_id": "p7#occurrence:1", "location": "p7", "operation_id": "G05:0",
                 "state": "FAIL", "artifact_status": "MISSING_EFFECT",
                 "failure_code": "CLAIM_OPERATION_NOT_PLANNED",
                 "proof_kind": "site_literal_effect"},
            ]},
        }},
    }
    view = build_coverage_view(report)
    assert [(entry.site_id, entry.target_id, entry.state) for entry in view.entries] == [
        ("p7#occurrence:0", "T0", "ARTIFACT_VERIFIED"),
        ("p7#occurrence:1", "T1", "UNRESOLVED"),
    ]


def test_failed_legacy_evidence_row_is_not_hidden_by_successful_evidence():
    report = {
        "obligations": {"records": [{
            "obligation_id": "G08:B1:O1", "rule_id": "G08", "operation_id": "G08:0",
            "completion": "ARTIFACT_VERIFIED", "targets": ["T1"],
            "artifact_evidence": [
                {"site_id": "p20", "location": "p20", "proof_kind": "site",
                 "state": "PASS"},
                {"site_id": "p20", "location": "p20", "proof_kind": "site",
                 "state": "UNKNOWN", "artifact_status": "UNKNOWN"},
            ],
        }]},
        "targets": [{"target_id": "T1", "rule_id": "G08", "location": "p20",
                      "state": "needs_edit", "operations": ["G08:0"]}],
    }
    view = build_coverage_view(report)
    assert view.state_of_operation("G08", "p20", "G08:0") == "UNRESOLVED"


def test_unrecognized_obligation_state_is_normalized_to_unresolved():
    report = {"obligations": {"records": [{
        "obligation_id": "G08:B1:O1", "rule_id": "G08", "operation_id": "G08:0",
        "completion": "future_terminal_state", "targets": [],
    }]}}
    view = build_coverage_view(report)
    assert view.entries[0].state == "UNRESOLVED"
    assert view.counts["UNRESOLVED"] == 1


def test_missing_occurrence_proof_is_not_hidden_by_same_location_pass():
    report = {
        "obligations": {"records": [{
            "obligation_id": "G05:B1:O1", "rule_id": "G05", "operation_id": "G05:0",
            "completion": "UNRESOLVED", "targets": ["T0", "T1"],
        }]},
        "targets": [dict(target_id=f"T{i}", rule_id="G05", location="p7",
                         state="needs_edit", occurrence_index=i, operations=["G05:0"])
                    for i in (0, 1)],
        "artifact_claim_replay": {"obligations": {"G05:B1:O1": {"site_effects": [{
            "site_id": "p7#occurrence:0", "location": "p7", "operation_id": "G05:0",
            "state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT",
            "proof_kind": "site_final_plan_reconstruction",
        }]}}},
    }
    view = build_coverage_view(report)
    assert [(e.site_id, e.target_id, e.state) for e in view.entries] == [
        ("p7#occurrence:0", "T0", "ARTIFACT_VERIFIED"),
        ("p7#occurrence:1", "T1", "UNRESOLVED")]
