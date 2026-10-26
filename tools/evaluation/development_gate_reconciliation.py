"""Validate and render the fixed D01-D20 development-gate reconciliation.

This module is deliberately offline.  It does not run the worker, call a model,
rewrite evidence, or assign a business score.  A blocked gate is a valid result;
only contradictory or unverifiable evidence makes the reconciliation invalid.

The input format is the preserved ``D01-D20-gate-reconciliation.json`` format.
The validator recomputes the denominator, snapshot binding, case eligibility,
summary counters, and (when requested) file and SQLite ledger hashes.  It is
fail-closed: missing evidence is reported as an error rather than silently
converted to ``pending`` or ``pass``.

Example::

    .venv/bin/python -m tools.evaluation.development_gate_reconciliation \
        --input docs/evidence/development-gate-reconciliation-20261025/\
            D01-D20-gate-reconciliation.json \
        --output-json /tmp/opencode/reconciliation.json \
        --output-md /tmp/opencode/reconciliation.md

Add ``--ledger`` or ``--verify-files`` only when those external evidence
sources are intentionally being checked.  The default invocation remains
purely a validation of the preserved JSON snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEV_CASE_IDS = tuple(f"D{index:02d}" for index in range(1, 21))
HOLDOUT_COUNT = 8
REQUIRED_CASE_FIELDS = {
    "case_id",
    "source_file",
    "source_sha256",
    "latest_preserved_evidence",
    "engine_reported_delivery_status",
    "mechanical_artifact_pass",
    "claim_replay_verified",
    "delivery_gate",
    "independent_whole_contract_business_review",
    "same_snapshot_19",
    "eligible_for_current_20_case_gate",
}
REQUIRED_EVIDENCE_FIELDS = {
    "evidence_set",
    "snapshot",
    "engine_build",
    "batch_path",
    "result_path",
    "report_path",
    "artifact_review_path",
    "business_review",
    "business_review_evidence",
}
EVIDENCE_JSON_PATH_FIELDS = {
    "batch_path",
    "result_path",
    "report_path",
    "artifact_review_path",
    "business_review_evidence",
}
TERMINAL_LEDGER_STATUSES = {"completed", "failed", "abandoned"}
KNOWN_LEDGER_STATUSES = TERMINAL_LEDGER_STATUSES | {
    "reserved",
    "running",
    "leased",
    "in_progress",
}
EPSILON = 1e-9


@dataclass(frozen=True)
class Issue:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def _issue(issues: list[Issue], code: str, path: str, message: str) -> None:
    issues.append(Issue(code, path, message))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _number(value: Any, *, default: float = 0.0) -> float:
    if isinstance(value, bool) or value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _same_number(left: Any, right: Any) -> bool:
    return abs(_number(left) - _number(right)) <= EPSILON


def _is_pass_status(status: Any) -> bool:
    return isinstance(status, str) and status.startswith("PASS")


def _is_incomplete_business_status(status: Any) -> bool:
    return isinstance(status, str) and status.startswith("INCOMPLETE")


def _eligibility(case: dict[str, Any], candidate_snapshot: str,
                 candidate_build: str) -> tuple[bool, list[str]]:
    evidence = case.get("latest_preserved_evidence") or {}
    delivery_gate = case.get("delivery_gate") or {}
    reasons: list[str] = []
    same_snapshot = (
        evidence.get("snapshot") == candidate_snapshot
        and evidence.get("engine_build") == candidate_build
    )
    if not same_snapshot:
        reasons.append("evidence is not bound to the current snapshot and engine build")
    if case.get("engine_reported_delivery_status") != "complete":
        reasons.append("delivery status is not complete")
    if case.get("mechanical_artifact_pass") is not True:
        reasons.append("mechanical artifact verification did not pass")
    if case.get("claim_replay_verified") is not True:
        reasons.append("Claim Replay is not verified")
    if _number(delivery_gate.get("open_obligations"), default=-1) != 0:
        reasons.append("delivery gate has open obligations")
    if _number(delivery_gate.get("blocking_unresolved"), default=-1) != 0:
        reasons.append("delivery gate has blocking unresolved items")
    if not _is_pass_status(case.get("independent_whole_contract_business_review")):
        reasons.append("independent whole-contract business review is not a pass")
    return not reasons, reasons


def _expected_summary(cases: list[dict[str, Any]], candidate_snapshot: str,
                      candidate_build: str) -> dict[str, int]:
    eligible = []
    same_snapshot = []
    same_snapshot_complete = []
    mechanical = []
    claim = []
    business_pass = []
    business_incomplete = []
    for case in cases:
        evidence = case.get("latest_preserved_evidence") or {}
        current = (evidence.get("snapshot") == candidate_snapshot
                   and evidence.get("engine_build") == candidate_build)
        same_snapshot.append(current)
        same_snapshot_complete.append(
            current and case.get("engine_reported_delivery_status") == "complete")
        mechanical.append(case.get("mechanical_artifact_pass") is True)
        claim.append(case.get("claim_replay_verified") is True)
        business = case.get("independent_whole_contract_business_review")
        business_pass.append(_is_pass_status(business))
        business_incomplete.append(_is_incomplete_business_status(business))
        eligible.append(_eligibility(case, candidate_snapshot, candidate_build)[0])
    return {
        "cases_in_reconciliation": len(cases),
        "same_snapshot_19_evidence_cases": sum(same_snapshot),
        "same_snapshot_19_complete_delivery_cases": sum(same_snapshot_complete),
        "mechanical_artifact_pass_cases": sum(mechanical),
        "claim_replay_verified_cases": sum(claim),
        "independent_whole_contract_business_pass_cases": sum(business_pass),
        "independent_whole_contract_business_pending_cases": sum(
            not passed and not incomplete
            for passed, incomplete in zip(business_pass, business_incomplete)),
        "independent_whole_contract_business_incomplete_cases": sum(business_incomplete),
        "current_gate_eligible_cases": sum(eligible),
        "historical_delivery_complete_cases": sum(
            case.get("engine_reported_delivery_status") == "complete"
            for case in cases),
        "historical_delivery_incomplete_cases": sum(
            case.get("engine_reported_delivery_status") == "incomplete"
            for case in cases),
        "independent_whole_contract_business_incomplete_cases": sum(business_incomplete),
    }


def _validate_manifest(manifest: dict[str, Any], issues: list[Issue]) -> None:
    files = manifest.get("files")
    if not isinstance(files, dict):
        _issue(issues, "MANIFEST_SCHEMA", "manifest.files", "expected a path-to-SHA-256 object")
        return
    for raw_path, expected in files.items():
        path = Path(str(raw_path))
        if not path.is_file():
            _issue(issues, "MANIFEST_MISSING_FILE", f"manifest.files.{raw_path}",
                   f"manifested file does not exist: {path}")
            continue
        actual = sha256_file(path)
        if actual != expected:
            _issue(issues, "MANIFEST_HASH_MISMATCH", f"manifest.files.{raw_path}",
                   f"expected {expected}, got {actual}")


def _validate_selection(selection: dict[str, Any], data: dict[str, Any],
                        issues: list[Issue]) -> None:
    selection_meta = data.get("selection") or {}
    expected_cases = list(selection_meta.get("dev_case_ids") or [])
    selection_cases = [item for item in selection.get("cases") or []
                       if item.get("group", "dev") == "dev"]
    actual_cases = [item.get("case_id") for item in selection_cases]
    if actual_cases != expected_cases:
        _issue(issues, "SELECTION_CASES_MISMATCH", "selection.dev_case_ids",
               f"reconciliation lists {expected_cases!r}, selection lists {actual_cases!r}")
    digest = sha256_file(Path(selection["_path"]))
    if selection_meta.get("selection_sha256") != digest:
        _issue(issues, "SELECTION_HASH_MISMATCH", "selection.selection_sha256",
               f"expected {selection_meta.get('selection_sha256')}, got {digest}")
    for index, item in enumerate(selection_cases):
        case_id = item.get("case_id")
        reconciliation_case = next((case for case in data.get("cases", [])
                                    if case.get("case_id") == case_id), None)
        if reconciliation_case is None:
            continue
        if item.get("file") and reconciliation_case.get("source_file") != item.get("file"):
            _issue(issues, "SELECTION_SOURCE_MISMATCH", f"selection.cases[{index}].file",
                   "source filename differs from the fixed reconciliation denominator")
        if item.get("sha256") and reconciliation_case.get("source_sha256") != item.get("sha256"):
            _issue(issues, "SELECTION_SOURCE_HASH_MISMATCH", f"selection.cases[{index}].sha256",
                   "source hash differs from the fixed reconciliation denominator")


def validate_ledger(path: Path, expected: dict[str, Any]) -> list[Issue]:
    """Compare a live/read-only request ledger with its captured summary."""
    issues: list[Issue] = []
    try:
        connection = sqlite3.connect(path)
    except sqlite3.Error as exc:
        _issue(issues, "LEDGER_OPEN_FAILED", "budget.ledger_path", str(exc))
        return issues
    try:
        rows = connection.execute(
            "SELECT status, reserved_cost, charged_cost FROM requests").fetchall()
    except sqlite3.Error as exc:
        _issue(issues, "LEDGER_SCHEMA", "budget.ledger_path", str(exc))
        connection.close()
        return issues
    finally:
        connection.close()
    by_status: dict[str, dict[str, float]] = {}
    for status, reserved, charged in rows:
        if status not in KNOWN_LEDGER_STATUSES:
            _issue(issues, "LEDGER_UNKNOWN_STATUS", "budget.by_status", str(status))
        item = by_status.setdefault(status, {"requests": 0, "charged_cost_usd": 0.0})
        item["requests"] += 1
        item["charged_cost_usd"] += _number(charged)
    request_count = len(rows)
    charged_total = sum(_number(row[2]) for row in rows)
    reserved_count = sum(status not in TERMINAL_LEDGER_STATUSES for status, _, _ in rows)
    if expected.get("ledger_requests") != request_count:
        _issue(issues, "LEDGER_REQUEST_COUNT_MISMATCH", "budget.ledger_requests",
               f"expected {expected.get('ledger_requests')}, got {request_count}")
    if not _same_number(expected.get("ledger_cost_usd"), charged_total):
        _issue(issues, "LEDGER_COST_MISMATCH", "budget.ledger_cost_usd",
               f"expected {expected.get('ledger_cost_usd')}, got {charged_total}")
    if expected.get("ledger_reserved_requests") != reserved_count:
        _issue(issues, "LEDGER_RESERVED_MISMATCH", "budget.ledger_reserved_requests",
               f"expected {expected.get('ledger_reserved_requests')}, got {reserved_count}")
    for status, captured in (expected.get("by_status") or {}).items():
        actual = by_status.get(status, {"requests": 0, "charged_cost_usd": 0.0})
        if captured.get("requests") != actual["requests"]:
            _issue(issues, "LEDGER_STATUS_COUNT_MISMATCH", f"budget.by_status.{status}.requests",
                   f"expected {captured.get('requests')}, got {actual['requests']}")
        if not _same_number(captured.get("charged_cost_usd"), actual["charged_cost_usd"]):
            _issue(issues, "LEDGER_STATUS_COST_MISMATCH",
                   f"budget.by_status.{status}.charged_cost_usd",
                   f"expected {captured.get('charged_cost_usd')}, got {actual['charged_cost_usd']}")
    remaining_requests = _number(expected.get("cap_requests")) - request_count
    remaining_cost = _number(expected.get("cap_cost_usd")) - charged_total
    if not _same_number(expected.get("remaining_requests"), remaining_requests):
        _issue(issues, "BUDGET_REMAINING_REQUESTS_MISMATCH", "budget.remaining_requests",
               f"expected {expected.get('remaining_requests')}, got {remaining_requests}")
    if not _same_number(expected.get("remaining_cost_usd"), remaining_cost):
        _issue(issues, "BUDGET_REMAINING_COST_MISMATCH", "budget.remaining_cost_usd",
               f"expected {expected.get('remaining_cost_usd')}, got {remaining_cost}")
    top_up = expected.get("minimum_current_snapshot_top_up_excluding_current_D06") or {}
    if top_up:
        expected_shortfall_requests = max(0, _number(top_up.get("requests_baseline"))
                                          - remaining_requests)
        expected_shortfall_cost = max(0, _number(top_up.get("cost_usd_baseline"))
                                      - remaining_cost)
        if not _same_number(top_up.get("request_shortfall_against_remaining"),
                            expected_shortfall_requests):
            _issue(issues, "BUDGET_SHORTFALL_REQUESTS_MISMATCH",
                   "budget.minimum_current_snapshot_top_up_excluding_current_D06.request_shortfall_against_remaining",
                   "captured request shortfall does not match the ledger remainder")
        if not _same_number(top_up.get("cost_shortfall_usd_against_remaining"),
                            expected_shortfall_cost):
            _issue(issues, "BUDGET_SHORTFALL_COST_MISMATCH",
                   "budget.minimum_current_snapshot_top_up_excluding_current_D06.cost_shortfall_usd_against_remaining",
                   "captured cost shortfall does not match the ledger remainder")
    return issues


def _read_json(path: Path, issues: list[Issue], code: str) -> dict[str, Any] | None:
    if not path.is_file():
        _issue(issues, code, str(path), "evidence file does not exist")
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _issue(issues, code, str(path), f"cannot read JSON: {exc}")
        return None
    if not isinstance(value, dict):
        _issue(issues, code, str(path), "expected a JSON object")
        return None
    return value


def _artifact_path(case_dir: Path, kind: str) -> Path | None:
    names = (kind, f"{kind}.docx", f"working_{kind}", f"working_{kind}.docx")
    return next((case_dir / name for name in names if (case_dir / name).is_file()), None)


def validate_case_files(case: dict[str, Any], *, selection_sha256: str | None = None,
                        verify_hashes: bool = True) -> list[Issue]:
    """Validate preserved paths for one case without changing any file."""
    issues: list[Issue] = []
    evidence = case.get("latest_preserved_evidence") or {}
    case_id = case.get("case_id", "?")
    paths = {name: Path(str(evidence.get(name, ""))) for name in EVIDENCE_JSON_PATH_FIELDS}
    loaded: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        value = _read_json(path, issues, "EVIDENCE_MISSING_OR_INVALID")
        if value is not None:
            loaded[name] = value
    report = loaded.get("report_path")
    result = loaded.get("result_path")
    if result is not None:
        if result.get("case_id") and result.get("case_id") != case_id:
            _issue(issues, "RESULT_CASE_MISMATCH", f"{case_id}.result.case_id",
                   "result case ID differs from the reconciliation case")
        if result.get("sha256") and result.get("sha256") != case.get("source_sha256"):
            _issue(issues, "RESULT_SOURCE_HASH_MISMATCH", f"{case_id}.result.sha256",
                   "result source hash differs from the fixed denominator")
        if (result.get("delivery_status") and
                result.get("delivery_status") != case.get("engine_reported_delivery_status")):
            _issue(issues, "RESULT_DELIVERY_MISMATCH", f"{case_id}.result.delivery_status",
                   "result delivery status differs from reconciliation")
        result_model = result.get("model") or {}
        if (result_model.get("http_attempts") is not None
                and result_model.get("http_attempts") != case.get("model_http_attempts")):
            _issue(issues, "RESULT_MODEL_ATTEMPTS_MISMATCH", f"{case_id}.result.model.http_attempts",
                   "result model attempt count differs from reconciliation")
        if (result_model.get("estimated_cost_usd") is not None
                and not _same_number(result_model.get("estimated_cost_usd"),
                                     case.get("model_estimated_cost_usd"))):
            _issue(issues, "RESULT_MODEL_COST_MISMATCH", f"{case_id}.result.model.estimated_cost_usd",
                   "result model cost differs from reconciliation")
    if report is not None:
        if report.get("engine_build") != evidence.get("engine_build"):
            _issue(issues, "REPORT_BUILD_MISMATCH", f"{case_id}.report.engine_build",
                   "report engine build differs from preserved evidence")
        if report.get("source_sha256") != case.get("source_sha256"):
            _issue(issues, "REPORT_SOURCE_HASH_MISMATCH", f"{case_id}.report.source_sha256",
                   "report source hash differs from fixed denominator")
        if report.get("delivery_status") != case.get("engine_reported_delivery_status"):
            _issue(issues, "REPORT_DELIVERY_MISMATCH", f"{case_id}.report.delivery_status",
                   "report delivery status differs from reconciliation")
        report_gate = report.get("delivery_gate") or {}
        captured_gate = case.get("delivery_gate") or {}
        for field in ("open_obligations", "blocking_unresolved"):
            if field in report_gate and report_gate.get(field) != captured_gate.get(field):
                _issue(issues, "REPORT_DELIVERY_GATE_MISMATCH",
                       f"{case_id}.report.delivery_gate.{field}",
                       f"report {field} differs from reconciliation")
        if report_gate.get("counts") is not None and report_gate.get("counts") != captured_gate.get("counts"):
            _issue(issues, "REPORT_DELIVERY_COUNTS_MISMATCH",
                   f"{case_id}.report.delivery_gate.counts",
                   "report delivery-gate counts differ from reconciliation")
        report_targets = report.get("targets")
        if isinstance(report_targets, list) and len(report_targets) != case.get("engine_reported_target_count"):
            _issue(issues, "REPORT_TARGET_COUNT_MISMATCH", f"{case_id}.report.targets",
                   "report target count differs from reconciliation")
        report_unresolved = report.get("unresolved")
        if isinstance(report_unresolved, list) and len(report_unresolved) != case.get("engine_reported_unresolved_count"):
            _issue(issues, "REPORT_UNRESOLVED_COUNT_MISMATCH", f"{case_id}.report.unresolved",
                   "report unresolved count differs from reconciliation")
        replay = (report.get("artifact_claim_replay") or {}).get("verified")
        if replay is not None and replay != case.get("claim_replay_verified"):
            _issue(issues, "REPORT_REPLAY_MISMATCH", f"{case_id}.report.artifact_claim_replay.verified",
                   "report Claim Replay status differs from reconciliation")
        validation = report.get("output_validation") or {}
        report_model = report.get("model") or {}
        if (report_model.get("http_attempts") is not None
                and report_model.get("http_attempts") != case.get("model_http_attempts")):
            _issue(issues, "REPORT_MODEL_ATTEMPTS_MISMATCH", f"{case_id}.report.model.http_attempts",
                   "report model attempt count differs from reconciliation")
        if (report_model.get("estimated_cost_usd") is not None
                and not _same_number(report_model.get("estimated_cost_usd"),
                                     case.get("model_estimated_cost_usd"))):
            _issue(issues, "REPORT_MODEL_COST_MISMATCH", f"{case_id}.report.model.estimated_cost_usd",
                   "report model cost differs from reconciliation")
        for kind in ("final", "redline"):
            artifact = _artifact_path(Path(str(evidence["report_path"])).parent, kind)
            expected_hash = validation.get(f"{kind}_sha256")
            if artifact is None or not expected_hash:
                _issue(issues, "ARTIFACT_HASH_EVIDENCE_MISSING", f"{case_id}.{kind}",
                       "report or preserved case directory lacks the declared artifact")
            elif verify_hashes and sha256_file(artifact) != expected_hash:
                _issue(issues, "ARTIFACT_HASH_MISMATCH", f"{case_id}.{kind}",
                       f"declared {expected_hash}, got {sha256_file(artifact)}")
    artifact_review = loaded.get("artifact_review_path")
    if artifact_review is not None:
        if artifact_review.get("mechanical_pass") != case.get("mechanical_artifact_pass"):
            _issue(issues, "ARTIFACT_REVIEW_MISMATCH", f"{case_id}.artifact_review.mechanical_pass",
                   "artifact review status differs from reconciliation")
        if report is not None:
            report_validation = report.get("output_validation") or {}
            for kind in ("final", "redline"):
                report_hash = report_validation.get(f"{kind}_sha256")
                review_hash = artifact_review.get(f"{kind}_sha256")
                if report_hash and review_hash and report_hash != review_hash:
                    _issue(issues, "REPORT_ARTIFACT_REVIEW_HASH_MISMATCH",
                           f"{case_id}.artifact_review.{kind}_sha256",
                           "artifact review hash differs from report output_validation")
    business_review = loaded.get("business_review_evidence")
    if business_review is not None:
        conclusion = business_review.get("conclusion")
        if conclusion is not None and conclusion != case.get("independent_whole_contract_business_review"):
            _issue(issues, "BUSINESS_REVIEW_CONCLUSION_MISMATCH",
                   f"{case_id}.business_review_evidence.conclusion",
                   "independent business-review conclusion differs from reconciliation")
    batch = loaded.get("batch_path")
    if batch is not None:
        if (selection_sha256 is not None and batch.get("selection_sha256")
                and batch.get("selection_sha256") != selection_sha256):
            _issue(issues, "BATCH_SELECTION_HASH_MISMATCH", f"{case_id}.batch.selection_sha256",
                   "batch was created from a different selection")
        if case_id not in (batch.get("cases") or []):
            _issue(issues, "BATCH_CASE_MISSING", f"{case_id}.batch.cases",
                   "batch does not contain the reconciled case")
    return issues


def reconcile(data: dict[str, Any], *, selection_path: Path | None = None,
              ledger_path: Path | None = None, verify_files: bool = False,
              manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a normalized validation report for a reconciliation snapshot."""
    issues: list[Issue] = []
    if not isinstance(data, dict):
        return {"valid": False, "issues": [{"code": "INPUT_SCHEMA", "path": "$",
                                               "message": "expected a JSON object"}]}
    candidate = data.get("current_candidate") or {}
    candidate_snapshot = candidate.get("snapshot")
    candidate_build = candidate.get("engine_build")
    if not isinstance(candidate_snapshot, str) or not candidate_snapshot:
        _issue(issues, "CANDIDATE_SCHEMA", "current_candidate.snapshot", "missing snapshot")
    if not isinstance(candidate_build, str) or not candidate_build:
        _issue(issues, "CANDIDATE_SCHEMA", "current_candidate.engine_build", "missing engine build")
    selection_meta = data.get("selection") or {}
    if selection_meta.get("denominator_frozen") is not True:
        _issue(issues, "DENOMINATOR_NOT_FROZEN", "selection.denominator_frozen",
               "fixed denominator must be explicitly frozen")
    if selection_meta.get("dev_case_ids") != list(DEV_CASE_IDS):
        _issue(issues, "DENOMINATOR_MISMATCH", "selection.dev_case_ids",
               "expected exactly D01-D20 in fixed order")
    if selection_meta.get("holdout_case_count") != HOLDOUT_COUNT:
        _issue(issues, "HOLDOUT_DENOMINATOR_MISMATCH", "selection.holdout_case_count",
               f"expected fixed holdout count {HOLDOUT_COUNT}")
    cases = data.get("cases")
    if not isinstance(cases, list):
        _issue(issues, "CASES_SCHEMA", "cases", "expected a list")
        cases = []
    case_ids = [case.get("case_id") if isinstance(case, dict) else None for case in cases]
    if case_ids != list(DEV_CASE_IDS):
        _issue(issues, "CASE_DENOMINATOR_MISMATCH", "cases", "cases must be exactly D01-D20 in order")
    if len(set(case_ids)) != len(case_ids):
        _issue(issues, "DUPLICATE_CASE_ID", "cases", "case IDs must be unique")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            _issue(issues, "CASE_SCHEMA", f"cases[{index}]", "expected an object")
            continue
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            _issue(issues, "CASE_SCHEMA", f"cases[{index}]", f"missing fields: {', '.join(missing)}")
            continue
        evidence = case.get("latest_preserved_evidence") or {}
        missing_evidence = sorted(REQUIRED_EVIDENCE_FIELDS - set(evidence))
        if missing_evidence:
            _issue(issues, "EVIDENCE_SCHEMA", f"cases[{index}].latest_preserved_evidence",
                   f"missing fields: {', '.join(missing_evidence)}")
        if isinstance(candidate_snapshot, str) and isinstance(candidate_build, str):
            stored_same = case.get("same_snapshot_19")
            actual_same = (evidence.get("snapshot") == candidate_snapshot
                           and evidence.get("engine_build") == candidate_build)
            if stored_same != actual_same:
                _issue(issues, "SNAPSHOT_BINDING_MISMATCH", f"cases[{index}].same_snapshot_19",
                       f"stored {stored_same!r}, recomputed {actual_same!r}")
            eligible, reasons = _eligibility(case, candidate_snapshot, candidate_build)
            if case.get("eligible_for_current_20_case_gate") != eligible:
                _issue(issues, "ELIGIBILITY_MISMATCH",
                       f"cases[{index}].eligible_for_current_20_case_gate",
                       f"stored {case.get('eligible_for_current_20_case_gate')!r}, recomputed {eligible!r}")
            if eligible and case.get("eligibility_reason"):
                _issue(issues, "ELIGIBILITY_REASON_MISMATCH", f"cases[{index}].eligibility_reason",
                       "eligible cases must not carry a blocking reason")
            if not eligible and not case.get("eligibility_reason"):
                _issue(issues, "ELIGIBILITY_REASON_MISSING", f"cases[{index}].eligibility_reason",
                       f"ineligible case has no reason; expected one of {reasons!r}")
        counts = (case.get("delivery_gate") or {}).get("counts") or {}
        if "UNRESOLVED" in counts and "open_obligations" in (case.get("delivery_gate") or {}):
            if counts["UNRESOLVED"] != case["delivery_gate"]["open_obligations"]:
                _issue(issues, "DELIVERY_COUNT_MISMATCH", f"cases[{index}].delivery_gate",
                       "UNRESOLVED count differs from open_obligations")
    expected_summary = _expected_summary(cases, candidate_snapshot or "", candidate_build or "")
    captured_summary = data.get("summary") or {}
    for key, expected in expected_summary.items():
        if captured_summary.get(key) != expected:
            _issue(issues, "SUMMARY_MISMATCH", f"summary.{key}",
                   f"expected {expected}, got {captured_summary.get(key)!r}")
    if captured_summary.get("fixed_denominator") != {"dev": 20, "holdout": HOLDOUT_COUNT}:
        _issue(issues, "SUMMARY_DENOMINATOR_MISMATCH", "summary.fixed_denominator",
               "summary denominator does not match the fixed selection")
    if data.get("conclusion", {}).get("status") != (
            "PASS" if expected_summary["current_gate_eligible_cases"] == 20
            else "BLOCKED_INCOMPLETE"):
        _issue(issues, "CONCLUSION_STATUS_MISMATCH", "conclusion.status",
               "conclusion status does not follow the recomputed current gate")
    if selection_path is not None:
        selection = _read_json(selection_path, issues, "SELECTION_MISSING_OR_INVALID")
        if selection is not None:
            selection["_path"] = str(selection_path)
            _validate_selection(selection, data, issues)
    if manifest is not None:
        _validate_manifest(manifest, issues)
    if verify_files:
        for case in cases:
            for issue in validate_case_files(
                    case, selection_sha256=data.get("selection", {}).get("selection_sha256")):
                issues.append(issue)
    if ledger_path is not None:
        for issue in validate_ledger(ledger_path, data.get("budget") or {}):
            issues.append(issue)
    normalized = json.loads(json.dumps(data, ensure_ascii=False))
    normalized["validation"] = {
        "valid": not issues,
        "issue_count": len(issues),
        "issues": [item.as_dict() for item in issues],
        "recomputed_summary": expected_summary,
        "model_calls_added_by_reconciliation": 0,
    }
    normalized.pop("_selection_sha256", None)
    return normalized


def to_markdown(result: dict[str, Any]) -> str:
    validation = result.get("validation") or {}
    summary = result.get("summary") or {}
    candidate = result.get("current_candidate") or {}
    lines = ["# Development gate reconciliation", "",
             f"- Candidate: `{candidate.get('snapshot')}`",
             f"- Engine build: `{candidate.get('engine_build')}`",
             f"- Current gate: **{summary.get('current_gate_eligible_cases', '—')}/20**",
             f"- Validation: **{'PASS' if validation.get('valid') else 'FAIL'}**", ""]
    if validation.get("issues"):
        lines += ["## Validation issues", "", "| Code | Path | Message |",
                  "| --- | --- | --- |"]
        for issue in validation["issues"]:
            lines.append(f"| {issue['code']} | `{issue['path']}` | {issue['message']} |")
        lines.append("")
    lines += ["## Fixed denominator", "",
              "| Set | Count |", "| --- | ---: |",
              f"| Development | {summary.get('fixed_denominator', {}).get('dev', '—')} |",
              f"| Holdout | {summary.get('fixed_denominator', {}).get('holdout', '—')} |", "",
              "## Case status", "",
              "| Measure | Count |", "| --- | ---: |"]
    for key in ("same_snapshot_19_evidence_cases", "same_snapshot_19_complete_delivery_cases",
                "mechanical_artifact_pass_cases", "claim_replay_verified_cases",
                "independent_whole_contract_business_pass_cases",
                "independent_whole_contract_business_pending_cases",
                "independent_whole_contract_business_incomplete_cases",
                "current_gate_eligible_cases"):
        lines.append(f"| {key} | {summary.get(key, '—')} |")
    return "\n".join(lines) + "\n"


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-md", type=Path)
    parser.add_argument("--selection", type=Path)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--manifest", type=Path,
                        help="optional JSON object with a files path-to-SHA-256 map")
    parser.add_argument("--verify-files", action="store_true",
                        help="read every preserved evidence JSON and verify artifact hashes")
    args = parser.parse_args(list(argv) if argv is not None else None)
    data = json.loads(args.input.read_text(encoding="utf-8"))
    manifest = json.loads(args.manifest.read_text(encoding="utf-8")) if args.manifest else None
    result = reconcile(data, selection_path=args.selection, ledger_path=args.ledger,
                       verify_files=args.verify_files, manifest=manifest)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    if args.output_md:
        args.output_md.parent.mkdir(parents=True, exist_ok=True)
        args.output_md.write_text(to_markdown(result), encoding="utf-8")
    print(json.dumps(result["validation"], ensure_ascii=False, indent=2))
    return 0 if result["validation"]["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
