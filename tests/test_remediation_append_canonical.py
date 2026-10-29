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
    # Keep the clause-tail site: it is the shared G16/G17 anchor and the
    # scorer accepts the formula-tail label through its same-clause window.
    assert body_open.out_of_scope is True
    assert body_survey.out_of_scope is False
    assert "DUPLICATE_APPEND_SITE_CANONICAL" in body_open.reason
    assert summary.out_of_scope is False
    assert changes == [{
        "target_id": "S03#1:T019",
        "canonical_target_id": "Y009",
        "location": "p799",
    }]


def test_g03_prefers_class_definition_over_later_adjustment_paragraph():
    inspection = inspect_docx(SOURCE, full=True)
    definition = Target(
        "Y010", "G03", "p124", "本基金根据认购、申购费用收取方式的不同", "needs_edit",
        "append", operations=("G03:0",), resolution="resolved",
    )
    adjustment = Target(
        "S03#1:T002", "G03", "p128", "有关基金份额类别的具体设置", "needs_edit",
        "append", operations=("G03:0",), resolution="resolved",
    )
    changes = canonicalize_append_targets(
        [definition, adjustment],
        {"G03": {"operations": [{"op": "append"}]}},
        inspection,
    )
    assert definition.out_of_scope is False
    assert adjustment.out_of_scope is True
    assert changes and changes[0]["canonical_target_id"] == "Y010"
