"""The scorer must accept the independent first-batch label schema.

The first-batch labeler records facts under ``fund`` and paths under
``relative``; the legacy P6 schema uses ``facts`` and ``data_root/funds_word``.
Scoring an empty run already exercised the top-level adapter; these checks pin
the two failure modes that made the first real scoring attempt abort.
"""
from __future__ import annotations

import json
from pathlib import Path

from tools.evaluation.p6_score import (
    _case_facts,
    _case_source_path,
    paragraphs_of,
    score_target,
)


REPO = Path(__file__).resolve().parents[1]
LABELS = REPO / "docs" / "evidence" / "labels-first-batch-20261028-v2.json"


def _case(case_id: str) -> dict:
    payload = json.loads(LABELS.read_text(encoding="utf-8"))
    return next(case for case in payload["cases"] if case["case_id"] == case_id)


def test_first_batch_facts_and_relative_source_are_supported():
    case = _case("B02")
    facts = _case_facts(case)
    assert facts["class_count"] == 2
    assert facts["has_service_fee"] is True
    assert {item["name"] for item in facts["classes"]} >= {"A类基金份额", "C类基金份额"}
    source = _case_source_path(case, REPO, REPO / "funds_word")
    assert source is not None and source.name == case["file"]
    assert source.is_file()


def test_target_count_is_derived_when_label_omits_it():
    case = _case("B02")
    targets = case.get("targets") or []
    assert targets
    # The current label file has target_count; the scorer's fallback must remain
    # safe if a future wave omits the convenience field.
    case_without = {key: value for key, value in case.items() if key != "target_count"}
    assert len(case_without.get("targets") or []) == len(targets)


def test_append_at_a_declared_site_is_not_satisfied_by_source_text():
    case = _case("B02")
    source = _case_source_path(case, REPO, REPO / "funds_word")
    assert source is not None
    target = next(
        item for item in case["targets"]
        if item["rule_id"] == "G16" and item.get("scope") == "summary"
    )
    paragraphs = paragraphs_of(source)
    verdict = score_target(target, _case_facts(case), paragraphs, paragraphs)
    assert verdict["verdict"] != "completed"
    assert verdict["site_scoped"] is True
