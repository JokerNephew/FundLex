"""Offline tests for the fixed D01-D20 gate reconciliation."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from tools.evaluation.development_gate_reconciliation import (
    DEV_CASE_IDS,
    reconcile,
    sha256_file,
    to_markdown,
    validate_case_files,
)


def _case(case_id: str, *, snapshot: str = "snapshot-19", build: str = "b" * 64,
          delivery: str = "incomplete", mechanical: bool = True,
          replay: bool = False, business: str = "PENDING", eligible: bool = False) -> dict:
    gate = {"open_obligations": 1 if delivery != "complete" else 0,
            "blocking_unresolved": 1 if delivery != "complete" else 0,
            "counts": {"UNRESOLVED": 1 if delivery != "complete" else 0}}
    return {
        "case_id": case_id,
        "source_file": f"{case_id}.docx",
        "source_sha256": "s" * 64,
        "latest_preserved_evidence": {
            "evidence_set": "synthetic",
            "snapshot": snapshot,
            "engine_build": build,
            "batch_path": "/missing/batch.json",
            "result_path": "/missing/result.json",
            "report_path": "/missing/report.json",
            "artifact_review_path": "/missing/artifact-review.json",
            "review_packet_path": "/missing/review.json",
            "business_review": business,
            "business_review_evidence": "/missing/business.json",
        },
        "engine_reported_delivery_status": delivery,
        "engine_reported_target_count": 1,
        "engine_reported_unresolved_count": 0 if delivery == "complete" else 1,
        "mechanical_artifact_pass": mechanical,
        "claim_replay_verified": replay,
        "claim_replay_checked": 1,
        "delivery_gate": gate,
        "independent_whole_contract_business_review": business,
        "model_http_attempts": 0,
        "model_estimated_cost_usd": 0,
        "actual_changes_in_review_packet": None,
        "same_snapshot_19": snapshot == "snapshot-19" and build == "b" * 64,
        "eligible_for_current_20_case_gate": eligible,
        "eligibility_reason": "synthetic blocked evidence" if not eligible else "",
    }


def _reconciliation(*, first_case: dict | None = None) -> dict:
    cases = [_case(case_id) for case_id in DEV_CASE_IDS]
    if first_case:
        cases[0] = first_case
    return {
        "schema": "fundlex-development-gate-reconciliation-v1",
        "created_at": "2026-10-26",
        "purpose": "synthetic",
        "selection": {"path": "selection.json", "selection_sha256": "x" * 64,
                       "dev_case_ids": list(DEV_CASE_IDS), "holdout_case_count": 8,
                       "denominator_frozen": True},
        "current_candidate": {"snapshot": "snapshot-19", "engine_build": "b" * 64,
                               "path": "/snapshot-19"},
        "gate_policy": ["fixed denominator", "current snapshot"],
        "summary": {
            "fixed_denominator": {"dev": 20, "holdout": 8},
            "cases_in_reconciliation": 20,
            "same_snapshot_19_evidence_cases": 20,
            "same_snapshot_19_complete_delivery_cases": 0,
            "mechanical_artifact_pass_cases": 20,
            "claim_replay_verified_cases": 0,
            "independent_whole_contract_business_pass_cases": 0,
            "independent_whole_contract_business_pending_cases": 20,
            "independent_whole_contract_business_incomplete_cases": 0,
            "current_gate_eligible_cases": 0,
            "historical_delivery_complete_cases": 0,
            "historical_delivery_incomplete_cases": 20,
        },
        "budget": {"cap_requests": 100, "cap_cost_usd": 1.0,
                   "ledger_requests": 0, "ledger_cost_usd": 0,
                   "ledger_reserved_requests": 0, "by_status": {},
                   "remaining_requests": 100, "remaining_cost_usd": 1.0},
        "cases": cases,
        "conclusion": {"status": "BLOCKED_INCOMPLETE"},
        "evidence_scope": {"model_calls_added_by_reconciliation": 0},
    }


def test_reconciliation_recomputes_fixed_denominator_and_blocked_gate():
    result = reconcile(_reconciliation())
    assert result["validation"]["valid"] is True
    assert result["validation"]["recomputed_summary"]["current_gate_eligible_cases"] == 0
    assert "Current gate: **0/20**" in to_markdown(result)


def test_old_snapshot_cannot_become_current_gate_pass():
    case = _case("D01", snapshot="snapshot-18", delivery="complete", replay=True,
                 business="PASS_FOR_HISTORICAL_INDEPENDENT_BUSINESS_REVIEW")
    case["same_snapshot_19"] = True
    case["eligible_for_current_20_case_gate"] = True
    result = reconcile(_reconciliation(first_case=case))
    assert result["validation"]["valid"] is False
    codes = {issue["code"] for issue in result["validation"]["issues"]}
    assert "SNAPSHOT_BINDING_MISMATCH" in codes
    assert "ELIGIBILITY_MISMATCH" in codes


def test_manifest_hash_mismatch_fails_closed(tmp_path: Path):
    path = tmp_path / "evidence.json"
    path.write_text("{}\n", encoding="utf-8")
    data = _reconciliation()
    result = reconcile(data, manifest={"files": {str(path): "0" * 64}})
    assert result["validation"]["valid"] is False
    assert any(issue["code"] == "MANIFEST_HASH_MISMATCH"
               for issue in result["validation"]["issues"])


def test_selection_hash_and_source_denominator_are_checked(tmp_path: Path):
    selection = {"cases": [{"case_id": case_id, "file": f"{case_id}.docx",
                             "sha256": "s" * 64} for case_id in DEV_CASE_IDS]}
    path = tmp_path / "selection.json"
    path.write_text(json.dumps(selection), encoding="utf-8")
    data = _reconciliation()
    data["selection"]["selection_sha256"] = sha256_file(path)
    result = reconcile(data, selection_path=path)
    assert result["validation"]["valid"] is True
    selection["cases"][0]["sha256"] = "t" * 64
    path.write_text(json.dumps(selection), encoding="utf-8")
    result = reconcile(data, selection_path=path)
    assert any(issue["code"] == "SELECTION_SOURCE_HASH_MISMATCH"
               for issue in result["validation"]["issues"])


def test_ledger_counters_and_costs_are_checked(tmp_path: Path):
    ledger = tmp_path / "ledger.sqlite"
    with sqlite3.connect(ledger) as db:
        db.execute("CREATE TABLE requests (status TEXT, reserved_cost REAL, charged_cost REAL)")
        db.execute("INSERT INTO requests VALUES ('completed', 0.2, 0.1)")
    data = _reconciliation()
    data["budget"].update({"ledger_requests": 1, "ledger_cost_usd": 0.1,
                            "ledger_reserved_requests": 0,
                            "by_status": {"completed": {"requests": 1,
                                                            "charged_cost_usd": 0.1}},
                            "remaining_requests": 99, "remaining_cost_usd": 0.9})
    result = reconcile(data, ledger_path=ledger)
    assert result["validation"]["valid"] is True
    data["budget"]["ledger_cost_usd"] = 0.2
    result = reconcile(data, ledger_path=ledger)
    assert any(issue["code"] == "LEDGER_COST_MISMATCH"
               for issue in result["validation"]["issues"])


def test_report_result_and_artifact_review_conflicts_fail_closed(tmp_path: Path):
    case = _case("D01")
    evidence = case["latest_preserved_evidence"]
    report_dir = tmp_path / "D01"
    report_dir.mkdir()
    final = report_dir / "final"
    redline = report_dir / "redline"
    final.write_bytes(b"final")
    redline.write_bytes(b"redline")
    report = {
        "case_id": "D01",
        "engine_build": "wrong-build",
        "source_sha256": case["source_sha256"],
        "delivery_status": "complete",
        "artifact_claim_replay": {"verified": False},
        "output_validation": {
            "final_sha256": sha256_file(final),
            "redline_sha256": sha256_file(redline),
        },
    }
    result = {"case_id": "D01", "sha256": case["source_sha256"],
              "delivery_status": "complete"}
    artifact_review = {"case_id": "D01", "mechanical_pass": True,
                       "final_sha256": "0" * 64,
                       "redline_sha256": sha256_file(redline)}
    batch = {"selection_sha256": "selection", "cases": ["D01"]}
    business = {"status": "PENDING"}
    files = {
        "batch_path": batch,
        "result_path": result,
        "report_path": report,
        "artifact_review_path": artifact_review,
        "business_review_evidence": business,
    }
    paths = {}
    for name, value in files.items():
        path = report_dir / f"{name}.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[name] = str(path)
    evidence.update(paths)
    issues = validate_case_files(case, selection_sha256="selection")
    codes = {issue.code for issue in issues}
    assert "REPORT_BUILD_MISMATCH" in codes
    assert "REPORT_DELIVERY_MISMATCH" in codes
    assert "RESULT_DELIVERY_MISMATCH" in codes
    assert "REPORT_ARTIFACT_REVIEW_HASH_MISMATCH" in codes
