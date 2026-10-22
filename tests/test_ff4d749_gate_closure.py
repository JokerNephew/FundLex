"""Deterministic closure tests for the ff4d749 Gate blockers (no models)."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import (PlannedEdit, Target, ensure_delete_targets, merge_edits,
                            target_site_ok)
from test_operation_execution_closure import Facts, Inspection


def test_g16_payment_site_rejects_rate_formula_and_usage():
    rate = SimpleNamespace(text="本基金C类基金份额销售服务费年费率为0.40%。")
    formula = SimpleNamespace(text="H为C类基金份额每日应计提的销售服务费")
    usage = SimpleNamespace(text="销售服务费主要用于支付销售机构佣金和促销活动费。")
    payment = SimpleNamespace(text="基金销售服务费每日计算，逐日累计至每月月末，按月支付。")
    assert target_site_ok("G16", payment, Inspection([payment.text])) is True
    assert target_site_ok("G16", rate, Inspection([rate.text])) is False
    assert target_site_ok("G16", formula, Inspection([formula.text])) is False
    assert target_site_ok("G16", usage, Inspection([usage.text])) is False


def test_g16_append_uses_every_payment_member_not_a_unique_member_rule():
    from fundlex.recall import Section, append_applicability_targets
    body = "基金销售服务费每日计提，逐日累计至每月月末，按月支付，经基金管理人与基金托管人核对一致后支付。"
    summary = "基金销售服务费每日计提，逐日累计至每月月末，按月支付，经基金管理人与基金托管人核对一致后支付。"
    rate = "本基金C类基金份额销售服务费年费率为0.40%。"
    inspection = Inspection([body, summary, rate])
    section = Section("S1", "基金费用与税收", "body", ("p0", "p1", "p2"), 200, body[:40])
    rule = {"rule_id": "G16", "section_hint": "基金费用与税收",
            "operations": [{"op": "append", "new_text": "新增销售服务费返还机制。",
                            "condition": {"kind": "none"}}]}
    facts = Facts()
    hits = append_applicability_targets(inspection, [rule], facts, [section])
    assert sorted(hit.locations[0] for hit in hits) == ["p0", "p1"]


def test_composite_g17_target_suppresses_residual_tail_target():
    from fundlex.recall import compact_offsets
    first = "销售服务费主要用于支付销售机构佣金、以及基金管理人的基金行销广告费、促销活动费、基金份额持有人服务费等。"
    second = "销售服务费使用范围不包括基金募集期间的上述费用。"
    inspection = Inspection([first, second])
    first_compact, _ = compact_offsets(first)
    second_compact, _ = compact_offsets(second)
    target = Target("C1", "G17", "p0", first, "needs_edit", "", 0, len(first),
                    operations=("G17:0",),
                    composite=(f"p0:0:{len(first_compact)}", f"p1:0:{len(second_compact)}"))
    rule = {"rule_id": "G17", "operations": [{"op": "delete", "old_text": first + second,
                                               "condition": {"kind": "none"}}]}
    assert ensure_delete_targets([target], {"G17": rule}, inspection) == []


def test_same_operation_identical_subset_is_absorbed_not_conflicted():
    text = "同一句删除内容。"
    inspection = Inspection([text])
    outer = PlannedEdit("C1", "G17", "p0", 0, len(text), "", "replace", "tier1_delete", {},
                        operation_keys=("G17:0",))
    subset = PlannedEdit("C2", "G17", "p0", 0, len(text), "", "replace", "tier1_delete", {},
                         operation_keys=("G17:0",))
    merged, conflicts, covered = merge_edits([outer, subset], inspection)
    assert conflicts == []
    assert len(merged) == 1
    assert covered == ["C2"]


def test_delete_document_literal_absent_passes_and_present_does_not():
    from fundlex.generation.effects import evaluate_operation_effect
    guide = {"groups": [{"rule_id": "G06", "operations": [{
        "op": "delete", "old_text": "本基金不同基金份额类别之间不得互相转换。",
        "condition": {"kind": "none"}}]}]}
    ledger = compile_obligations(guide)
    record = ledger.records[0]
    record.applicability = SimpleNamespace(status="TRUE")
    facts = Facts()
    source = Inspection(["本基金A类、C类份额的费用不同。"])
    effect = evaluate_operation_effect(record, source, source, [], [], facts)
    assert effect.state == "PASS"
    assert effect.artifact_status == "VERIFIED_ABSENT"
    assert effect.evidence[0]["proof_kind"] == "document_literal_absent"
    present = Inspection(["本基金不同基金份额类别之间不得互相转换。"])
    effect2 = evaluate_operation_effect(record, present, present, [], [], facts)
    assert effect2.state == "OPEN"


def test_joint_edit_survives_replan_sites():
    from fundlex.recall import replan_sites
    text = "赎回费用由赎回基金份额的基金份额持有人承担，赎回费用全额计入基金财产。"
    inspection = Inspection([text])
    targets = [Target("T12", "G12", "p0", text, "needs_edit", "", 0, len(text),
                      operations=("G12:1",)),
               Target("T13", "G13", "p0", text, "needs_edit", "", 0, len(text),
                      operations=("G13:0",))]
    joint = {"target_id": "T12+T13", "rule_id": "G12+G13", "location": "p0",
             "start": 0, "end": len(text), "replacement": "新句。", "operation": "replace",
             "content_source": "joint_compose",
             "operation_keys": ["G12:1", "G13:0"],
             "evidence": {"operation_keys": ["G12:1", "G13:0"]},
             "expected_old_text": text,
             "components": [{"target_id": "T12+T13", "rule_id": "G12+G13",
                             "location": "p0", "start": 0, "end": len(text),
                             "replacement": "新句。", "operation": "replace",
                             "content_source": "joint_compose",
                             "operation_keys": ["G12:1", "G13:0"],
                             "evidence": {"operation_keys": ["G12:1", "G13:0"]},
                             "expected_old_text": text}]}
    result = replan_sites({"edits": [joint], "ledger": []}, set(),
                          {"G12": {"rule_id": "G12"}, "G13": {"rule_id": "G13"}},
                          targets, inspection, Facts(), None, max_compose_calls=0)
    assert [edit["content_source"] for edit in result["edits"]] == ["joint_compose"]
    assert result["edits"][0]["operation_keys"] == ["G12:1", "G13:0"]


def test_target_ids_are_made_globally_unique():
    from fundlex.recall import ensure_unique_target_ids
    targets = [Target("X", "G01", "p0", "a", "needs_edit", ""),
               Target("X", "G02", "p1", "b", "needs_edit", "")]
    origins = {"X": "first"}
    renamed = ensure_unique_target_ids(targets, origins)
    assert [target.target_id for target in targets] == ["X", "X-U2"]
    assert renamed == {"X": "X-U2"}
    assert origins["X-U2"] == "first"


def test_split_class_definition_target_moves_to_fee_group_paragraph():
    from fundlex.recall import rebind_split_class_definition_targets
    first = "基金份额类别：本基金将基金份额分为 A 类、C 类和 D 类三种不同的"
    second = ("类别。在投资者申购 A 类及 D 类基金份额时收取申购费用，不计提销售服务费；"
              "在投资者申购 C 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费")
    inspection = Inspection([first, second])
    target = Target("T", "G02", "p0", first, "needs_edit", "", 0, len(first),
                    operations=("G02:0", "G02:1"))
    records = rebind_split_class_definition_targets([target], inspection)
    assert records and target.location == "p1"
    assert target.quote == second
    assert (target.start, target.end) == (0, len(second))


def test_g16_payment_target_produces_append_edit():
    from fundlex.recall import plan_target
    text = "基金销售服务费每日计提，逐日累计至每月月末，按月支付。"
    target = Target("G16", "G16", "p0", text, "needs_edit", "", 0, len(text),
                    operations=("G16:0",), resolution="resolved")
    rule = {"rule_id": "G16", "operations": [{
        "op": "append", "new_text": "新增销售服务费返还机制。",
        "condition": {"kind": "none"}}]}
    edit = plan_target(rule, target, Inspection([text]), Facts(), None,
                       compose_budget=[0])
    assert edit is not None and edit.operation == "insert"
    assert edit.start == edit.end == len(text)
    assert "新增销售服务费返还机制" in edit.replacement


def test_g15_delete_and_g16_append_merge_at_payment_site():
    text = "基金销售服务费每日计提，按月支付。"
    old = PlannedEdit("G15", "G15", "p0", 0, len(text), "", "replace",
                      "tier1_delete", {}, operation_keys=("G15:0",))
    new = PlannedEdit("G16", "G16", "p0", len(text), len(text),
                      "新销售服务费返还机制。", "insert", "append",
                      {"fixed_text": "新销售服务费返还机制。"},
                      operation_keys=("G16:0",))
    merged, conflicts, _covered = merge_edits([old, new], Inspection([text]))
    assert conflicts == []
    assert len(merged) == 1
    assert merged[0][0].content_source in {"merged", "merged_delete_append"}
    assert "新销售服务费返还机制" in merged[0][0].replacement


def test_g05_class_setup_without_filing_literal_becomes_absent_site():
    from fundlex.recall import resolve_absent_site_targets
    text = ("有关基金份额类别的具体设置等由基金管理人确定。基金管理人可以增加新的基金份额"
            "类别、变更现有基金份额类别的申购费率、调低赎回费率或者停止现有基金份额类别"
            "的销售等，调整前需及时公告。")
    target = Target("G05", "G05", "p0", "调整前需及时公告", "needs_edit", "",
                    operations=(), out_of_scope=True)
    rule = {"rule_id": "G05", "operations": [{
        "op": "delete", "old_text": "并报中国证监会备案", "condition": {"kind": "none"}}]}
    records = resolve_absent_site_targets([target], {"G05": rule}, Inspection([text]))
    assert records and target.state == "satisfied"
    assert target.operations == ("G05:0",)
    assert target.out_of_scope is False
    assert target.quote == text
