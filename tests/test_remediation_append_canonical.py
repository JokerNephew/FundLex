"""Append fragments discovered twice in one clause must be planned once."""
from __future__ import annotations

from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.recall import Target, canonicalize_append_targets


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发价值优选混合型证券投资基金基金合同.docx"


def _target(target_id: str, location: str) -> Target:
    return Target(
        target_id=target_id,
        rule_id="G16",
        location=location,
        quote="销售服务费",
        state="needs_edit",
        reason="append",
        operations=("G16:0",),
        resolution="resolved",
    )


def test_body_append_site_is_canonical_while_summary_copy_stays():
    inspection = inspect_docx(SOURCE, full=True)
    body_open = _target("S03#1:T019", "p799")
    body_survey = _target("Y009", "p802")
    summary = _target("S25#1:T002", "p1258")
    targets = [body_open, body_survey, summary]
    changes = canonicalize_append_targets(
        targets,
        {"G16": {"operations": [{"op": "append"}]}},
        inspection,
    )
    assert body_open.out_of_scope is False
    assert body_survey.out_of_scope is True
    assert "DUPLICATE_APPEND_SITE_CANONICAL" in body_survey.reason
    assert summary.out_of_scope is False
    assert changes == [{
        "target_id": "Y009",
        "canonical_target_id": "S03#1:T019",
        "location": "p802",
    }]
