"""Unit tests for v2 review-finding adjudication helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/evaluation/build_labels_v2_20261028.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


builder = _load(BUILDER, "build_labels_v2_tool")


def test_scorer_facts_uses_fee_groups_not_currency_variants():
    fund = {
        "share_classes": [
            {"label": "A", "pays_purchase_fee": True, "charges_sales_service_fee": False},
            {"label": "C", "pays_purchase_fee": False, "charges_sales_service_fee": True},
        ],
        "class_count": 2,
        "has_sales_service_fee": True,
        "floating_management_fee": False,
        "fund_type": "混合型",
        "currency_variants": ["人民币", "美元"],
    }
    facts = builder.scorer_facts(fund)
    assert facts["class_count_basis"] == "fee_group"
    assert [c["name"] for c in facts["classes"]] == ["A类基金份额", "C类基金份额"]
    assert facts["classes"][0]["subscription_fee"] is True
    assert facts["classes"][1]["service_fee"] is True
    assert facts["currency_variants"] == ["人民币", "美元"]


def test_build_findings_assigns_stable_ids():
    case = {
        "review": {
            "findings": {
                "missing_targets": [{"rule_id": "G01"}],
                "incorrect_targets": [{"target_id": "T001"}, {"target_id": "T002"}],
                "fact_issues": [],
                "status_issues": [],
                "uncertain": [{"rule_id": "G02"}],
            }
        }
    }
    findings = builder.build_findings(case)
    assert [f["finding_id"] for f in findings] == ["R001", "R002", "R003", "R004"]
    assert [f["type"] for f in findings] == [
        "missing_targets", "incorrect_targets", "incorrect_targets", "uncertain",
    ]


def test_fact_correction_dotted_path_and_class_count_coercion():
    fund = {"fund_type_evidence": {"paragraph_index": 5}}
    assert builder._apply_fact_correction(fund, {"field": "fund_type_evidence.paragraph_index", "value": "105"}, None)
    assert fund["fund_type_evidence"]["paragraph_index"] == 105
    assert not builder._apply_fact_correction(fund, {"field": "unknown.path", "value": 1}, None)
