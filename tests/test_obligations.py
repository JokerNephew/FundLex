"""Operation / Obligation IR and obligation-first coverage (plan §6, §10, §21)."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.obligations import (GroupKind, apply_facts, compile_obligations,
                                 open_obligations, project)


class FakeFacts:
    def __init__(self, *, status="VERIFIED", class_count=2, service=True, floating=False):
        self.fact_status = {}
        for name in ("fund_type", "share_class_structure", "subscription_fee_group",
                     "service_fee_group"):
            self.fact_status[name] = status
        self.class_count = class_count
        self.has_service_fee = service
        self.floating_management_fee = floating
        self.quotes_verified = {"floating": status == "VERIFIED"}

    def status_of(self, name):
        return self.fact_status.get(name, "UNKNOWN")

    def as_ledger(self):
        return {"fact_status": dict(self.fact_status),
                "class_count": self.class_count}


def rule(rule_id="G05", *, operations=None, variants=None, section="基金的基本情况"):
    return {
        "rule_id": rule_id,
        "title": rule_id,
        "section_hint": section,
        "requirement": f"requirement {rule_id}",
        "operations": operations or [
            {"op": "replace", "old_text": "调低赎回费率", "new_text": "调低销售服务费率",
             "condition": {"kind": "has_service_fee", "value": True}},
            {"op": "delete", "old_text": "并报中国证监会备案",
             "condition": {"kind": "has_service_fee", "value": True}},
            {"op": "delete", "old_text": "报中国证监会备案",
             "condition": {"kind": "none", "value": None}},
        ],
        "old_text_variants": variants or [],
    }


def guide(*rules):
    return {"groups": list(rules)}


def target(rule_id, *, target_id="T1", state="needs_edit", operations=(), location="p1"):
    return {"target_id": target_id, "rule_id": rule_id, "state": state,
            "operations": list(operations), "location": location, "quote": "q"}


def report_with(*, targets=(), plan_ledger=(), audit=(), replay=None, unresolved=()):
    return {
        "targets": list(targets),
        "plan": {"ledger": list(plan_ledger)},
        "audit": {"rounds": [{"results": list(audit)}]},
        "artifact_claim_replay": replay or {},
        "unresolved": list(unresolved),
    }


def test_compile_creates_all_of_branches_and_stable_ids():
    ledger = compile_obligations(guide(rule()))
    assert [item.obligation_id for item in ledger.records] == [
        "G05:B1:O1", "G05:B1:O2", "G05:B2:O1"]
    assert ledger.groups["G05"].group_kind is GroupKind.BRANCH
    assert ledger.records[0].spec.group_kind is GroupKind.ALL_OF
    assert ledger.records[2].spec.group_kind is GroupKind.INDEPENDENT
    # Both the new obligation id and the legacy operation key resolve.
    assert ledger.record("G05:B1:O2").spec.operation_id == "G05:1"
    assert ledger.record("G05:1").obligation_id == "G05:B1:O2"


def test_unknown_branch_runs_no_obligation_and_stays_open():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(status="UNKNOWN"))
    assert {item.completion for item in ledger.records if item.spec.branch_id == "B1"} \
        == {"UNRESOLVED"}
    assert ledger.records[-1].completion == "UNRESOLVED"  # unconditional branch is also blocked
    assert open_obligations(ledger)


def test_false_branch_is_not_applicable():
    ledger = compile_obligations(guide(rule()))
    facts = FakeFacts(service=False)
    apply_facts(ledger, facts)
    b1 = [item for item in ledger.records if item.spec.branch_id == "B1"]
    assert {item.completion for item in b1} == {"NOT_APPLICABLE"}
    # The unconditional delete branch still applies and has no target yet.
    assert ledger.records[-1].completion == "UNRESOLVED"


def test_applicable_obligation_without_any_target_is_open():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(service=False))
    project(ledger, report_with())
    open_items = open_obligations(ledger)
    assert [item["obligation_id"] for item in open_items] == ["G05:B2:O1"]
    assert open_items[0]["reason"].startswith("OPEN_OBLIGATION")


def test_audit_completed_and_claim_replay_close_the_obligation():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(service=True))
    project(ledger, report_with(
        targets=[target("G05", operations=["G05:0", "G05:1"])],
        plan_ledger=[{"target_id": "T1", "status": "planned"}],
        audit=[{"target_id": "T1", "verdict": "completed"}],
        replay={"verified": True, "checked": 1, "failures": [],
                "obligations": {
                    "G05:B1:O1": {"state": "PASS",
                                  "artifact_status": "EXPECTED_EFFECT_PRESENT"},
                    "G05:B1:O2": {"state": "PASS",
                                  "artifact_status": "VERIFIED_ABSENT"}}},
    ))
    b1 = [item for item in ledger.records if item.spec.branch_id == "B1"]
    assert {item.completion for item in b1} == {"ARTIFACT_VERIFIED"}
    # B2 has no target of its own but is covered by the unkeyed/operation target rule?
    # The target explicitly covers operations 0/1, so B2 remains open.
    assert ledger.record("G05:B2:O1").completion == "UNRESOLVED"


def test_plan_unresolved_keeps_only_that_branch_open():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(service=True))
    project(ledger, report_with(
        targets=[target("G05", operations=["G05:0"])],
        plan_ledger=[{"target_id": "T1", "status": "unresolved", "reason": "RECALL_TARGET_UNRESOLVED"}],
    ))
    assert ledger.record("G05:B1:O1").completion == "UNRESOLVED"
    assert ledger.record("G05:B1:O1").completion_evidence == "plan:RECALL_TARGET_UNRESOLVED"
    # O2 was not covered by the keyed target, so it is an open obligation rather than
    # being silently inherited from O1's failure or success.
    assert ledger.record("G05:B1:O2").completion == "UNRESOLVED"


def test_absent_target_is_verified_not_applicable():
    ledger = compile_obligations(guide(rule(rule_id="G15", operations=[
        {"op": "delete", "old_text": "销售服务费按月支付", "condition": {"kind": "none"}}])))
    apply_facts(ledger, FakeFacts())
    project(ledger, report_with(targets=[target("G15", state="absent")]),
            artifact_text="本基金合同。")
    assert ledger.records[0].completion == "NOT_APPLICABLE"
    assert not open_obligations(ledger)


def test_variants_are_one_of_not_all_of():
    ledger = compile_obligations(guide(rule(rule_id="G14", operations=[
        {"op": "replace", "old_text": "调低申购费率", "new_text": "调低销售服务费率",
         "condition": {"kind": "class_count", "value": "multiple"}}],
        variants=["调低申购费率", "调低申购、赎回费率"])))
    group = ledger.groups["G14"]
    assert group.group_kind is GroupKind.ONE_OF
    assert group.variant_alternatives == ("调低申购费率", "调低申购、赎回费率")
    assert ledger.records[0].spec.one_of_group == "G14:B1:VARIANTS"


def test_artifact_replay_failure_reopens_the_obligation():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(service=True))
    project(ledger, report_with(
        targets=[target("G05", operations=["G05:0", "G05:1"])],
        plan_ledger=[{"target_id": "T1", "status": "planned"}],
        audit=[{"target_id": "T1", "verdict": "completed"}],
        replay={"verified": False, "checked": 1,
                "failures": [{"rule_id": "G05", "location": "p1",
                              "code": "CLAIM_REPLACEMENT_MISSING"}]},
    ))
    assert ledger.record("G05:B1:O1").completion == "UNRESOLVED"
    assert ledger.record("G05:B1:O1").completion_evidence == "CLAIM_REPLAY_FAILED"


def test_delivery_closed_states_are_exhaustive_and_fail_closed():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(service=False))
    project(ledger, report_with(targets=[target("G05", state="absent")]),
            artifact_text="本基金合同。")
    # Both branches now have a target: B1 false, B2's reference is proven absent.
    assert all(item.closed for item in ledger.records)
    assert not open_obligations(ledger)


def test_same_replacement_old_text_variants_are_one_of_and_close_together():
    ledger = compile_obligations(guide(rule(rule_id="G11", operations=[
        {"op": "replace", "old_text": "旧写法一", "new_text": "统一的新政策",
         "condition": {"kind": "class_count", "value": "multiple"}},
        {"op": "replace", "old_text": "旧写法二", "new_text": "统一的新政策",
         "condition": {"kind": "class_count", "value": "multiple"}},
    ])))
    assert ledger.records[0].spec.one_of_group == "G11:B1:ONE1"
    assert ledger.records[1].spec.one_of_group == "G11:B1:ONE1"
    assert ledger.records[0].spec.group_kind is GroupKind.ONE_OF
    apply_facts(ledger, FakeFacts(class_count=2))
    project(ledger, report_with(
        targets=[target("G11", operations=["G11:0"])],
        plan_ledger=[{"target_id": "T1", "status": "planned"}],
        audit=[{"target_id": "T1", "verdict": "completed"}],
        replay={"verified": True, "obligations": {
            "G11:B1:O1": {"state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT"},
            "G11:B1:O2": {"state": "PASS", "artifact_status": "ALTERNATIVE_NOT_SELECTED"}}},
    ))
    assert {item.completion for item in ledger.records} <= {"ARTIFACT_VERIFIED", "ALREADY_SATISFIED"}
    assert not open_obligations(ledger)


def test_rule_level_plan_satisfied_cannot_close_an_unattributed_sibling():
    ledger = compile_obligations(guide(rule(rule_id="G02", operations=[
        {"op": "replace", "old_text": "A类基金份额", "new_text": "A类、D类基金份额",
         "condition": {"kind": "none", "value": None}},
        {"op": "replace", "old_text": "C类基金份额", "new_text": "C类、F类基金份额",
         "condition": {"kind": "none", "value": None}},
    ])))
    apply_facts(ledger, FakeFacts())
    project(ledger, report_with(
        targets=[target("G02", operations=["G02:0"], state="needs_edit")],
        plan_ledger=[{"target_id": "T1", "status": "satisfied"}],
    ))
    # A location/plan verdict for G02:0 does not cover G02:1.  The sibling stays OPEN
    # until it has its own target/artifact proof.
    assert ledger.record("G02:B1:O1").completion == "UNRESOLVED"
    assert ledger.record("G02:B1:O2").completion == "UNRESOLVED"
    assert {item["operation_id"] for item in open_obligations(ledger)} == {
        "G02:0", "G02:1"}


def test_one_completed_target_cannot_hide_another_wrong_occurrence():
    ledger = compile_obligations(guide(rule(rule_id="G18", operations=[
        {"op": "replace", "old_text": "旧句", "new_text": "新句",
         "condition": {"kind": "none", "value": None}}])))
    apply_facts(ledger, FakeFacts())
    project(ledger, report_with(
        targets=[target("G18", target_id="T1", operations=["G18:0"]),
                 target("G18", target_id="T2", operations=["G18:0"])],
        plan_ledger=[{"target_id": "T1", "status": "planned"},
                     {"target_id": "T2", "status": "planned"}],
        audit=[{"target_id": "T1", "verdict": "completed"},
               {"target_id": "T2", "verdict": "wrong"}],
    ))
    assert ledger.records[0].completion == "UNRESOLVED"
    assert ledger.records[0].completion_evidence == "audit_wrong"


def test_one_of_variant_closure_requires_the_other_variant_to_be_gone():
    ledger = compile_obligations(guide(rule(rule_id="G11", operations=[
        {"op": "replace", "old_text": "旧写法一", "new_text": "统一的新政策",
         "condition": {"kind": "class_count", "value": "multiple"}},
        {"op": "replace", "old_text": "旧写法二", "new_text": "统一的新政策",
         "condition": {"kind": "class_count", "value": "multiple"}},
    ])))
    apply_facts(ledger, FakeFacts(class_count=2))
    project(ledger, report_with(
        targets=[target("G11", operations=["G11:0"])],
        plan_ledger=[{"target_id": "T1", "status": "planned"}],
        audit=[{"target_id": "T1", "verdict": "completed"}],
        replay={"verified": True, "obligations": {
            "G11:B1:O1": {"state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT"},
            "G11:B1:O2": {"state": "PASS", "artifact_status": "ALTERNATIVE_NOT_SELECTED"}}},
    ), artifact_text="条款仍写旧写法二。")
    assert ledger.records[0].completion == "ARTIFACT_VERIFIED"
    assert ledger.records[1].completion == "UNRESOLVED"
    assert ledger.records[1].completion_evidence == "ONE_OF_VARIANT_RESIDUAL"


def test_absent_delete_reference_is_not_an_open_obligation():
    ledger = compile_obligations(guide(rule(rule_id="G06", operations=[
        {"op": "delete", "old_text": "本基金不同基金份额类别之间不得互相转换。",
         "condition": {"kind": "none", "value": None}}])))
    apply_facts(ledger, FakeFacts())
    project(ledger, report_with(), artifact_text="本基金合同经中国证监会核准。")
    assert ledger.records[0].completion == "NOT_APPLICABLE"
    assert ledger.records[0].completion_evidence == "delete_reference_absent"
    assert not open_obligations(ledger)


def test_satisfied_unkeyed_target_cannot_hide_a_residual_delete():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(service=False))
    project(ledger, report_with(targets=[target("G05", state="satisfied")]),
            artifact_text="基金份额类别调整并报中国证监会备案。")
    b2 = ledger.record("G05:B2:O1")
    assert b2.completion == "UNRESOLVED"
    assert b2.completion_evidence == "SATISFIED_TARGET_RESIDUAL_DELETE"


def test_one_of_variant_present_inside_the_authorized_new_text_closes():
    new_policy = ("通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的"
                  "申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。")
    ledger = compile_obligations(guide(rule(rule_id="G11", operations=[
        {"op": "replace", "old_text": "申购费用由投资人承担，不列入基金财产。",
         "new_text": new_policy, "condition": {"kind": "class_count", "value": "multiple"}},
        {"op": "replace", "old_text": "本基金A类基金份额的申购费用由投资人承担，不列入基金财产。",
         "new_text": new_policy, "condition": {"kind": "class_count", "value": "multiple"}},
    ])))
    apply_facts(ledger, FakeFacts(class_count=2))
    project(ledger, report_with(
        targets=[target("G11", operations=["G11:0"])],
        plan_ledger=[{"target_id": "T1", "status": "planned"}],
        audit=[{"target_id": "T1", "verdict": "completed"}],
        replay={"verified": True, "obligations": {
            "G11:B1:O1": {"state": "PASS", "artifact_status": "EXPECTED_EFFECT_PRESENT"},
            "G11:B1:O2": {"state": "PASS", "artifact_status": "ALTERNATIVE_NOT_SELECTED"}}},
    ), artifact_text=new_policy)
    assert {item.completion for item in ledger.records} <= {"ARTIFACT_VERIFIED", "ALREADY_SATISFIED"}
    assert not open_obligations(ledger)


def test_explicit_empty_scope_cannot_close_an_append_obligation():
    ledger = compile_obligations(guide(rule(rule_id="G01", operations=[
        {"op": "append", "new_text": "通过直销机构申购A类基金份额不收取申购费。",
         "condition": {"kind": "none", "value": None}}])))
    apply_facts(ledger, FakeFacts())
    report = report_with()
    report["scope_mapping"] = {"mappings": {"G01": []}}
    project(ledger, report, artifact_text="本基金合同。")
    assert ledger.records[0].completion == "UNRESOLVED"
    assert ledger.records[0].completion_evidence == "SCOPE_EMPTY_APPEND_UNPROVEN"


def test_survey_satisfied_delete_cannot_hide_a_residual_sentence():
    ledger = compile_obligations(guide(rule()))
    apply_facts(ledger, FakeFacts(service=False))
    report = report_with()
    report["survey"] = [{"records": [{"operation": "satisfied",
                                      "operation_keys": ["G05:2"]}]}]
    project(ledger, report, artifact_text="并报中国证监会备案。")
    record = ledger.record("G05:B2:O1")
    assert record.completion == "UNRESOLVED"
    assert record.completion_evidence == "SURVEY_SATISFIED_RESIDUAL_DELETE"
