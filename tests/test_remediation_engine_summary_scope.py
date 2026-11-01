"""FL-D384/434/443: real body-to-summary fee targets are in scope.

The production failure left 价值优选 p1258 untouched while p802 changed, and the
first-batch 景宁 p1240 summary usage sentence was rejected as out of scope.  These
tests read the real contracts read-only, assert the summary leaf is mapped, and
derive operation targets only where a real candidate exists (no mechanical
summary polish, no G17 target where the summary has no usage clause).
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fundlex.docx import inspect_docx
from fundlex.recall import (ClassFact, Facts, Target, approval_book_for,
                            merge_edits, plan_target, structure_index)
from fundlex.rule_scope import resolve_rule_scopes
from fundlex.targeting import summary_copy_targets

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = Path("/home/opencode/fundlex/funds_word/基金合同第一批")
VALUE = CONTRACT_ROOT / "广发价值优选混合型证券投资基金基金合同.docx"
JINGNING = CONTRACT_ROOT / "广发景宁纯债债券型证券投资基金基金合同.docx"
RULES = {rule["rule_id"]: rule
         for rule in json.loads((ROOT / "guides/builtin_guide_v1.json").read_text())["groups"]}
RULE_IDS = ("G15", "G16", "G17")


class NoModel:
    def call(self, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("model must not be called")


def _facts() -> Facts:
    return Facts("混合型", "", "", (ClassFact("A", True, False, True, None, ""),
                                     ClassFact("C", False, True, True, None, "")),
                 False, "", "", "", {}, (),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"real contract not present: {path}")
    inspection = inspect_docx(path)
    sections = structure_index(inspection)
    mapping = {rule_id: [section.id for section in sections
                         if "费用" in section.title or section.zone == "summary"]
               for rule_id in RULE_IDS}
    scopes = resolve_rule_scopes([RULES[rule_id] for rule_id in RULE_IDS],
                                 sections, inspection, mapping)
    return inspection, sections, scopes


def _body_targets(inspection, rules: dict[str, str]) -> list[Target]:
    return [Target(f"B{rule_id}", rule_id, location, inspection.by_location(location).text,
                   "needs_edit", "", start=0,
                   end=len(inspection.by_location(location).text),
                   resolution="resolved", segment_ok=True,
                   operations=(f"{rule_id}:0",), scope_id=f"{rule_id}:S:L")
            for rule_id, location in rules.items()]


def test_value_summary_fee_copy_is_mapped_and_gets_only_real_operations():
    inspection, sections, scopes = _load(VALUE)
    assert "p1258" in scopes["G15"].locations
    assert "p1258" in scopes["G16"].locations
    assert scopes["G15"].include_summary_copies is True

    body = _body_targets(inspection, {"G15": "p800", "G16": "p802", "G17": "p801"})
    created = summary_copy_targets(body, RULES, inspection, sections, scopes, facts=_facts())
    by_rule = {target.rule_id: target for target in created}
    assert set(by_rule) == {"G15", "G16"}
    assert by_rule["G15"].location == "p1258"
    assert by_rule["G16"].location == "p1258"
    # The summary has no sales-service-fee usage clause; G17 must not be fabricated.
    assert "G17" not in by_rule
    assert all(target.location != "p1259" for target in created)


def test_value_summary_g15_g16_plan_without_compose_and_merge_to_new_policy():
    inspection, sections, scopes = _load(VALUE)
    body = _body_targets(inspection, {"G15": "p800", "G16": "p802", "G17": "p801"})
    summary = summary_copy_targets(body, RULES, inspection, sections, scopes, facts=_facts())
    for target in summary:
        target.scope_id = f"{target.rule_id}:S25:L10"
    facts = _facts()
    approvals = approval_book_for(RULES, [*body, *summary], inspection)
    edits = []
    for target in summary:
        edit = plan_target(RULES[target.rule_id], target, inspection, facts, NoModel(),
                           compose_budget=[0], approvals=approvals)
        assert edit is not None
        edits.append(edit)
    assert {edit.rule_id for edit in edits} == {"G15", "G16"}
    merged, conflicts, _covered = merge_edits(edits, inspection)
    assert conflicts == []
    combined = merged[0][0]
    assert combined.location == "p1258"
    assert combined.replacement.startswith("销售服务费每日计提")
    assert "自动在次月初" not in combined.replacement
    assert set(combined.operation_keys) == {"G15:0", "G16:0"}


def test_jingning_summary_payment_and_usage_targets_are_recovered():
    inspection, sections, scopes = _load(JINGNING)
    assert "p1239" in scopes["G15"].locations
    assert "p1240" in scopes["G17"].locations
    assert scopes["G17"].include_summary_copies is True

    body = _body_targets(inspection, {"G15": "p769", "G16": "p769", "G17": "p770"})
    created = summary_copy_targets(body, RULES, inspection, sections, scopes, facts=_facts())
    mapping = {(target.rule_id, target.location): target for target in created}
    assert ("G15", "p1239") in mapping
    assert ("G16", "p1239") in mapping
    assert ("G17", "p1240") in mapping
    assert mapping[("G17", "p1240")].operations == ("G17:0",)
    assert "主要用于支付销售机构佣金" in mapping[("G17", "p1240")].quote


def test_missing_body_target_creates_no_summary_target():
    inspection, sections, scopes = _load(VALUE)
    created = summary_copy_targets([], RULES, inspection, sections, scopes)
    assert created == []
