"""Regression tests for Router telemetry and materialized executor evidence."""
from __future__ import annotations

from pathlib import Path

from docx import Document
import pytest

from fundlex.docx import DocxError, inspect_docx, validate_edit_plan
from tools.evaluation.strategy_consistency import inspect_path, inspect_report, source_tier


def _strategy(operation: str, actual: str, *, applicable: bool = True) -> dict:
    return {
        "operation": operation,
        "requested": actual,
        "actual": actual,
        "fallback_reason": None,
        "blocked": False,
        "applicable": applicable,
    }


def _report(*edits: dict) -> dict:
    return {
        "delivery_status": "incomplete",
        "edit_plan": {"edits": list(edits)},
        "operation_coverage": {"counts": {
            "ARTIFACT_VERIFIED": 1,
            "ALREADY_SATISFIED": 2,
            "UNRESOLVED": 1,
        }},
    }


def test_strategy_consistency_flags_router_executor_tier_mismatch():
    result = inspect_report(_report({
        "rule_id": "G08", "target_id": "T08", "location": "p1",
        "content_source": "tier1_template",
        "evidence": {"strategy": [_strategy("G08:0", "tier2_minimal_splice")]},
    }))

    assert result["summary"]["mismatch_count"] == 1
    mismatch = result["mismatches"][0]
    assert mismatch["code"] == "ROUTER_EXECUTOR_TIER_MISMATCH"
    assert mismatch["operation_keys"] == ["G08:0"]
    assert result["operation_coverage"]["UNRESOLVED"] == 1
    assert result["summary"]["missing_fingerprint_count"] == 1


def test_strategy_consistency_preserves_applicable_operation_identity_and_duplicates():
    result = inspect_report(_report(
        {
            "rule_id": "G02", "target_id": "T1", "location": "p1",
            "content_source": "fragment_replace",
            "operation_keys": ["G02:0"],
            "evidence": {"strategy": [_strategy("G02:0", "tier2_minimal_splice")]},
        },
        {
            "rule_id": "G02", "target_id": "T2", "location": "p2",
            "content_source": "fragment_replace",
            # Older reports put operation identity only in Router telemetry.
            "evidence": {"strategy": [_strategy("G02:0", "tier2_minimal_splice")]},
        },
    ))

    assert result["operation_counts"] == {"G02:0": 2}
    assert result["duplicate_operation_occurrences"] == [{
        "operation_key": "G02:0", "count": 2,
        "locations": ["p1", "p2"],
        "code": "DUPLICATE_OPERATION_OCCURRENCE",
    }]


def test_operation_coverage_is_projected_per_operation():
    report = _report({
        "rule_id": "G14", "target_id": "T14", "location": "p3",
        "content_source": "tier1_template",
        "evidence": {"strategy": [_strategy("G14:0", "tier1_template")]},
    })
    report["operation_coverage"]["entries"] = [
        {"rule_id": "G14", "location": "p3", "operation_keys": ["G14:0"],
         "state": "ARTIFACT_VERIFIED"},
        {"rule_id": "G14", "location": "p4", "operation_keys": ["G14:0"],
         "state": "UNRESOLVED"},
    ]
    result = inspect_report(report)
    assert result["coverage_by_operation"] == {
        "G14:0": {"ARTIFACT_VERIFIED": 1, "UNRESOLVED": 1}
    }


def test_source_tier_covers_g14_add_missing_and_model_paths():
    assert source_tier("tier1_template") == "tier1_template"
    assert source_tier("composed") == "tier3_model_compose"
    assert source_tier("tier1_delete") == "deterministic_delete"
    assert source_tier("variant_delete") == "deterministic_delete"
    assert source_tier("unrecognized") == "unknown"


def test_finalized_generated_edit_uses_planning_source_and_fingerprint():
    result = inspect_report(_report({
        "rule_id": "G14", "target_id": "T14", "location": "p3",
        "content_source": "generated",
        "planning_content_source": "tier1_template",
        "fingerprint": "fp-p3",
        "evidence": {"strategy": [_strategy("G14:0", "tier1_template")]},
    }))

    edit = result["edits"][0]
    assert edit["effective_content_source"] == "tier1_template"
    assert edit["observed_tier"] == "tier1_template"
    assert edit["fingerprint_status"] == "present"
    assert result["summary"]["missing_fingerprint_count"] == 0


def test_strategy_consistency_scans_report_directory(tmp_path: Path):
    case = tmp_path / "case-a"
    case.mkdir()
    (case / "report.json").write_text(
        __import__("json").dumps(_report({
            "rule_id": "G14", "target_id": "T14", "location": "p3",
            "content_source": "tier1_template",
            "evidence": {"strategy": [_strategy("G14:0", "tier1_template")]},
        }), ensure_ascii=False), encoding="utf-8")

    result = inspect_path(tmp_path)
    assert result["report_count"] == 1
    assert result["summary"]["mismatch_count"] == 0
    assert result["reports"][0]["operation_counts"] == {"G14:0": 1}


def test_docx_fingerprint_is_required_and_mutation_is_rejected(tmp_path: Path):
    document = Document()
    document.add_paragraph("原有收费条款")
    source = tmp_path / "source.docx"
    document.save(source)
    inspection = inspect_docx(source, full=True)
    span = inspection.by_location("p0")
    old = span.text
    edit = {
        "edit_id": "fingerprint-test",
        "source_sha256": inspection.source_sha256,
        "location": "p0",
        "zone": span.zone,
        "start": 0,
        "end": len(old),
        "expected_old_text": old,
        "expected_old_hash": __import__("hashlib").sha256(old.encode()).hexdigest(),
        "replacement": "新的收费条款",
        "verified": True,
        "fingerprint": span.fingerprint,
        "mapping_version": span.mapping_version,
    }
    # Generated edits require a trusted content closure; this test isolates the
    # paragraph identity gate before that closure is reached.
    edit["content_source"] = "generated"
    with pytest.raises(DocxError) as error:
        validate_edit_plan(source, [{**edit, "fingerprint": "mutated"}], {},
                           content_check=lambda item: True)
    assert error.value.code == "PARAGRAPH_DRIFT"

    validated = validate_edit_plan(source, [edit], {}, content_check=lambda item: True)
    assert validated.edits[0]["fingerprint"] == span.fingerprint
