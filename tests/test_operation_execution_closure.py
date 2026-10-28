"""Operation -> target -> plan -> final edit -> artifact closure (plan §2–§38).

These tests pin the failure modes found in the real D01/D02/D11/D16 reports:
location targets covering a whole rule, sibling operations disappearing from the final
edit set, Claim Replay checking only edited rules, and sweep findings overriding a
deterministic deletion proof.
"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

import pytest

from fundlex.docx import TextSegment
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations, project
from fundlex.recall import (PlannedEdit, RecallError, Target, _reconcile_final_plan_ledger,
                            _selected_operation_indices, merge_edits,
                            plan_composite_target, plan_target)
from fundlex.recall_pipeline import (_apply_artifact_proof_to_findings,
                                     _recovery_snapshot, _run_audit)


class Facts:
    statuses = {}
    class_count = 2
    has_service_fee = True
    floating_management_fee = False
    quotes_verified = {}
    current_classes = ()
    service_group = ()
    subscription_group = ()
    ambiguous_classes = ()

    def status_of(self, name):
        return self.statuses.get(name, "VERIFIED")

    def as_ledger(self):
        return {"class_count": self.class_count}


class Span:
    def __init__(self, location, text):
        self.location, self.text = location, text
        self.zone = "body"
        self.segments = (TextSegment(0, len(text)),)
        self.fingerprint = "fp-" + location


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [Span(f"p{index}", text) for index, text in enumerate(texts)]
        self.source_sha256 = "source"

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


def test_composite_target_rejects_nonempty_intervening_source():
    """A composite target cannot jump over an independent physical paragraph."""
    inspection = Inspection([
        "本规则需要删除的句子，",
        "中间的独立条款。",
        "独立续句。",
    ])
    test_rule = rule("GTEST", [
        {"op": "delete", "old_text": "本规则需要删除的句子，独立续句。",
         "condition": {"kind": "none"}},
        {"op": "delete", "old_text": "中间的独立条款。",
         "condition": {"kind": "none"}},
    ])
    target = Target("T-composite", "GTEST", "p0", "本规则需要删除的句子，",
                    "needs_edit", "composite", start=0, end=len(inspection.by_location("p0").text),
                    resolution="composite", operations=("GTEST:0",))
    target.composite = ("p0:0:10", "p2:0:5")
    with pytest.raises(RecallError) as excinfo:
        plan_composite_target(test_rule, target, inspection, Facts(), new_text="")
    assert excinfo.value.code == "RECALL_TARGET_COMPOSITE_BOUNDARY"


class Ledger:
    def __init__(self, records):
        self.records = records

    def record(self, key):
        for item in self.records:
            if item.spec.operation_id == str(key) or \
                    getattr(item, "obligation_id", "") == str(key):
                return item
        return None


def rule(rule_id="G05", operations=None):
    return {
        "rule_id": rule_id, "title": rule_id, "section_hint": "基金的基本情况",
        "requirement": "requirement",
        "operations": operations or [
            {"op": "replace", "old_text": "调低赎回费率",
             "new_text": "调低销售服务费率", "condition": {"kind": "none"}},
            {"op": "delete", "old_text": "并报中国证监会备案",
             "condition": {"kind": "none"}},
        ],
        "old_text_variants": [],
    }


def target(operations=(), quote="调低赎回费率", start=0, end=6):
    return Target(target_id="T1", rule_id="G05", location="p0", quote=quote,
                  state="needs_edit", reason="test", start=start, end=end,
                  resolution="resolved", operations=tuple(operations))


def test_location_target_without_operation_does_not_cover_the_rule():
    ledger = compile_obligations({"groups": [rule()]})
    apply_facts(ledger, Facts())
    project(ledger, {
        "targets": [{"target_id": "T0", "rule_id": "G05", "state": "needs_edit",
                     "operations": [], "location": "p0"}],
        "plan": {"ledger": [{"target_id": "T0", "status": "planned"}]},
        "audit": {"rounds": []}, "artifact_claim_replay": {},
    })
    assert ledger.record("G05:0").completion == "UNRESOLVED"
    assert ledger.record("G05:1").completion == "UNRESOLVED"


def test_planner_only_executes_the_target_operation():
    inspection = Inspection(["调低赎回费率并报中国证监会备案。基金管理人可调整基金份额类别。"])
    target_obj = target(operations=("G05:0",), quote="调低赎回费率", start=0, end=6)
    edit = plan_target(rule(), target_obj, inspection, Facts(), gateway=None,
                       compose_budget=[0])
    assert edit is not None
    assert edit.operation_keys == ("G05:0",)
    assert (edit.start, edit.end) == (0, 6)
    assert "调低销售服务费率" in edit.replacement
    # The sibling delete is outside the target's authorized span; it is not executed by
    # this edit and remains in the untouched part of the paragraph.
    assert "并报中国证监会备案" not in edit.replacement


def test_same_rule_independent_operations_are_not_alternatives():
    inspection = Inspection(["调低赎回费率或并报中国证监会备案。"])
    replace = PlannedEdit("T0", "G05", "p0", 0, 6, "调低销售服务费率", "replace",
                          "fragment_replace", {"fixed_text": "调低销售服务费率"},
                          operation_keys=("G05:0",))
    delete = PlannedEdit("T1", "G05", "p0", 0, 15, "调低赎回费率", "replace",
                         "fragment_delete", {}, operation_keys=("G05:1",))
    merged, conflicts, covered = merge_edits([replace, delete], inspection)
    assert covered == []
    assert conflicts and conflicts[0]["code"] == "RECALL_EDIT_OVERLAP"


def test_one_of_group_is_still_a_legal_alternative():
    inspection = Inspection(["旧写法"])
    ledger = Ledger([
        SimpleNamespace(obligation_id="G99:B1:O1",
                        spec=SimpleNamespace(operation_id="G99:0", one_of_group="G99:ONE")),
        SimpleNamespace(obligation_id="G99:B1:O2",
                        spec=SimpleNamespace(operation_id="G99:1", one_of_group="G99:ONE")),
    ])
    left = PlannedEdit("T0", "G99", "p0", 0, 3, "新政策", "replace", "fragment_replace",
                       {"fixed_text": "新政策"}, operation_keys=("G99:0",))
    right = PlannedEdit("T1", "G99", "p0", 0, 3, "新政策", "replace", "fragment_replace",
                        {"fixed_text": "新政策"}, operation_keys=("G99:1",))
    _, conflicts, covered = merge_edits([left, right], inspection, ledger)
    assert conflicts == []
    assert covered == ["T1"]


def test_adjacent_one_of_alternatives_are_written_once():
    """D06 G12 p230: two historical wordings must not both be concatenated.

    G12:0 and G12:1 are declared ONE_OF alternatives with the same policy text.
    The planner used to merge the adjacent spans and write the sentence twice; the
    second alternative must be absorbed, and the G13 delete at the same tail span
    must still remove the old 7-day sentence.
    """
    first = "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示。"
    second = "对于持续持有期少于 7 日的投资者收取不低于 1.5%的赎回费，并将上述赎回费全额计入基金财产。"
    policy = "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。赎回费用全额计入基金财产。"
    inspection = Inspection([first + second])
    ledger = Ledger([
        SimpleNamespace(obligation_id="G99:B1:O1",
                        spec=SimpleNamespace(operation_id="G99:0",
                                             one_of_group="G99:history:wording")),
        SimpleNamespace(obligation_id="G99:B1:O2",
                        spec=SimpleNamespace(operation_id="G99:1",
                                             one_of_group="G99:history:wording")),
        SimpleNamespace(obligation_id="G99:B1:O3",
                        spec=SimpleNamespace(operation_id="G99:2",
                                             one_of_group="")),
    ])
    left = PlannedEdit("T0", "G99", "p0", 0, len(first), policy, "replace",
                       "tier1_template", {"fixed_text": policy},
                       operation_keys=("G99:0",))
    right = PlannedEdit("T1", "G99", "p0", len(first), len(first) + len(second),
                        policy, "replace", "tier1_template", {"fixed_text": policy},
                        operation_keys=("G99:1",))
    delete = PlannedEdit("T2", "G99", "p0", len(first), len(first) + len(second),
                         "", "replace", "tier1_delete", {},
                         operation_keys=("G99:2",))
    merged, conflicts, covered = merge_edits([left, right, delete], inspection, ledger)
    assert conflicts == []
    assert covered == ["T1"]
    assert len(merged) == 1
    assert merged[0][0].replacement == policy
    assert merged[0][0].replacement.count("赎回费用全额计入基金财产") == 1
    assert "7 日" not in merged[0][0].replacement


def test_adjacent_one_of_different_policies_fail_closed():
    inspection = Inspection(["旧写法甲。旧写法乙。"])
    ledger = Ledger([
        SimpleNamespace(obligation_id="G99:B1:O1",
                        spec=SimpleNamespace(operation_id="G99:0",
                                             one_of_group="G99:history:wording")),
        SimpleNamespace(obligation_id="G99:B1:O2",
                        spec=SimpleNamespace(operation_id="G99:1",
                                             one_of_group="G99:history:wording")),
    ])
    left = PlannedEdit("T0", "G99", "p0", 0, 5, "新政策甲。", "replace",
                       "tier1_template", {"fixed_text": "新政策甲。"},
                       operation_keys=("G99:0",))
    right = PlannedEdit("T1", "G99", "p0", 5, 10, "新政策乙。", "replace",
                        "tier1_template", {"fixed_text": "新政策乙。"},
                        operation_keys=("G99:1",))
    merged, conflicts, covered = merge_edits([left, right], inspection, ledger)
    assert covered == []
    assert conflicts and conflicts[0]["reason"] == "ONE_OF_ALTERNATIVES_DIFFER"
    assert len(merged) == 2


def test_final_ledger_is_reconciled_from_the_final_edit_set():
    inspection = Inspection(["调低赎回费率"])
    baseline = [PlannedEdit("T1", "G05", "p0", 0, 6, "", "replace", "fragment_delete",
                            {}, operation_keys=("G05:0",))]
    ledger = [{"target_id": "T1", "rule_id": "G05", "status": "planned",
               "operation_keys": ["G05:0"]}]
    _reconcile_final_plan_ledger(ledger, [], [], [], baseline)
    assert ledger[0]["status"] == "unresolved"
    assert ledger[0]["reason"] == "RECALL_PLAN_COMPONENT_DROPPED"


def test_claim_replay_checks_an_applicable_operation_with_no_edit():
    guide = {"groups": [{
        "rule_id": "G03", "title": "class append", "section_hint": "基金的基本情况",
        "requirement": "append policy",
        "operations": [{"op": "append", "new_text": "通过直销机构申购A类不收取申购费。",
                        "condition": {"kind": "none"}}],
        "old_text_variants": [],
    }]}
    ledger = compile_obligations(guide)
    apply_facts(ledger, Facts())
    before = Inspection(["基金份额类别：本基金分为A类、C类。"])
    after = Inspection(["基金份额类别：本基金分为A类、C类。"])
    result = replay_claims([], before, after, rules_by_id={
        "G03": guide["groups"][0]}, obligations=ledger)
    assert result["verified"] is False
    assert result["obligations"]["G03:B1:O1"]["state"] == "OPEN"
    assert result["failures"][0]["code"] == "CLAIM_OPERATION_UNPROVEN"


def test_sweep_removal_unconfirmed_yields_to_artifact_proof():
    inspection = Inspection(["本段已删除。"])
    obligations = Ledger([SimpleNamespace(
        spec=SimpleNamespace(operation_id="G17:0", rule_id="G17", operation_index=0),
        applicability=SimpleNamespace(status="TRUE"),
        obligation_id="G17:B1:O1")])
    replay = {"obligations": {"G17:B1:O1": {
        "state": "PASS", "artifact_status": "VERIFIED_ABSENT",
        "operation_id": "G17:0", "obligation_id": "G17:B1:O1",
        "sites": ["p0"], "evidence": [{"location": "p0", "site_id": "p0",
                                           "operation_id": "G17:0",
                                           "obligation_id": "G17:B1:O1",
                                           "proof_kind": "site_delete"}],
        "site_effects": [{"state": "PASS"}]}}}
    findings = [{"status": "pending", "finding_id": "SW1", "rule_id": "G17",
                 "location": "p0", "issue": "unaddressed_requirement",
                 "quote": "旧句"}]
    _apply_artifact_proof_to_findings(findings, replay, inspection, obligations, {
        "G17": {"operations": [{"op": "delete", "old_text": "旧句仍然存在于本段。"}]}})
    assert findings[0]["status"] == "resolved"
    assert findings[0]["resolution"] == "artifact_proof"


def test_residual_confirmed_is_not_resolved_by_claim_replay():
    inspection = Inspection(["旧句仍然存在于本段。"])
    obligations = Ledger([SimpleNamespace(
        spec=SimpleNamespace(operation_id="G17:0", rule_id="G17", operation_index=0),
        obligation_id="G17:B1:O1")])
    replay = {"obligations": {"G17:B1:O1": {
        "state": "PASS", "artifact_status": "VERIFIED_ABSENT"}}}
    findings = [{"status": "pending", "finding_id": "SW1", "rule_id": "G17",
                 "location": "p0", "issue": "residual_old_text",
                 "quote": "旧句仍然存在于本段。"}]
    _apply_artifact_proof_to_findings(findings, replay, inspection, obligations, {
        "G17": {"operations": [{"op": "delete", "old_text": "旧句仍然存在于本段。"}]}})
    assert findings[0]["status"] == "pending"
    assert findings[0]["proof_kind"] == "RESIDUAL_CONFIRMED"


def test_equivalent_source_site_is_satisfied_while_same_operation_edits_other_site():
    from fundlex.generation.effects import evaluate_operation_effect, effect_proof_passed

    old = "本基金各类基金份额由于费用收取不同，其可供分配利润将有所不同。"
    new = "本基金各类基金份额由于基金费用的不同，其可供分配利润将有所不同。"
    equivalent = "由于基金费用的不同，本基金各类基金份额的可供分配利润将有所不同。"
    guide_rule = rule("G18", [{"op": "replace", "old_text": old,
                               "new_text": new, "condition": {"kind": "none"}}])
    ledger = compile_obligations({"groups": [guide_rule]})
    apply_facts(ledger, Facts())
    before, after = Inspection([equivalent, old]), Inspection([equivalent, new])
    edit = dict(rule_id="G18", target_id="T1", location="p1", start=0, end=len(old),
                replacement=new, operation_keys=["G18:0"])
    sites = [{"location": "p0", "quote": equivalent}, {"location": "p1", "quote": old}]
    proof = evaluate_operation_effect(ledger.records[0], before, after, sites, [edit], Facts(),
        validated_units=[dict(location="p1", operation_id="G18:0", verdict="PASS")])
    assert effect_proof_passed(proof.as_dict()), proof.as_dict()
    local, edited = proof.site_effects
    assert local["artifact_status"] == "ALREADY_SATISFIED"
    assert local["proof_kind"] == "source_operation_policy_equivalent"
    assert edited["artifact_status"] == "EXPECTED_EFFECT_PRESENT"
    local_only = evaluate_operation_effect(ledger.records[0], before, after, sites[:1],
                                          [edit], Facts())
    assert local_only.artifact_status == "ALREADY_SATISFIED"
    assert local_only.edit_ids == ()
    assert effect_proof_passed(local_only.as_dict())


def test_g16_append_sites_exclude_sibling_payment_head():
    from fundlex.generation.claim_replay import _own_rule_append_sites
    sites = [{"location": "p847"}, {"location": "p849"}, {"location": "p1296"}]
    targets = [
        {"rule_id": "G15", "location": "p847", "operations": ["G15:0"]},
        {"rule_id": "G16", "location": "p849", "operations": ["G16:0"]},
        {"rule_id": "G16", "location": "p1296", "operations": ["G16:0"]},
    ]
    kept = _own_rule_append_sites("G16", "G16:0", sites, targets)
    assert [site["location"] for site in kept] == ["p849", "p1296"]


def test_g16_append_ignores_sibling_delete_payment_site():
    """G16 is proven at its append tail, not at G15's deleted payment head."""
    from fundlex.generation.effects import evaluate_operation_effect

    policy = ("销售服务费每日计提。对于持续持有期限超过一年的基金份额，持有超过一年后"
              "继续计提的销售服务费，在投资者赎回基金份额时返还。")
    g16 = rule("G16", [{"op": "append", "new_text": policy,
                        "condition": {"kind": "none"}}])
    ledger = compile_obligations({"groups": [g16]})
    apply_facts(ledger, Facts())
    before = Inspection([
        "基金销售服务费每日计提，按月支付。",
        "销售服务费的使用范围不包括基金募集期间的上述费用。",
    ])
    after = Inspection(["", before.by_location("p1").text + policy])
    sites = [
        {"location": "p0", "quote": before.by_location("p0").text,
         "source_rule_id": "G15", "state": "needs_edit", "operation_id": "G15:0"},
        {"location": "p1", "quote": before.by_location("p1").text,
         "source_rule_id": "G16", "state": "needs_edit", "operation_id": "G16:0"},
    ]
    edit = {"target_id": "T16", "rule_id": "G16", "location": "p1",
            "start": len(before.by_location("p1").text),
            "end": len(before.by_location("p1").text), "replacement": policy,
            "operation": "append", "operation_keys": ["G16:0"],
            "components": [{"target_id": "T16", "rule_id": "G16", "location": "p1",
                            "start": len(before.by_location("p1").text),
                            "end": len(before.by_location("p1").text),
                            "replacement": policy, "operation_keys": ["G16:0"]}]}
    proof = evaluate_operation_effect(
        ledger.records[0], before, after, sites, [edit], Facts(),
        validated_units=[{"location": "p1", "operation_id": "G16:0",
                          "verdict": "PASS"}])
    assert proof.state == "PASS", proof.as_dict()
    assert proof.sites == ("p1",)


def test_orphan_sweep_contradicted_by_its_own_quoted_old_clause_is_resolved():
    inspection = Inspection(["销售服务费每日计提，按月支付。新支付路径为5个工作日。"])
    finding = {"status": "pending", "finding_id": "SW1", "rule_id": "G15",
               "location": "p0", "issue": "unaddressed_requirement",
               "quote": inspection.paragraphs[0].text,
               "reason": "G15要求删除“由基金管理人发送划付指令，次月首日起10个工作日内支付”。"}
    _apply_artifact_proof_to_findings([finding], {"obligations": {}}, inspection, None, {
        "G15": {"operations": [{"op": "delete",
                                 "old_text": "C类基金份额的销售服务费每日计提，按月支付。由基金管理人发送划付指令，次月首日起10个工作日内支付。"}]}})
    assert finding["status"] == "resolved"
    assert finding["resolution_evidence"] == "claimed_residual_absent"


def test_class_definition_satisfied_hit_requires_each_class_polarity():
    """A definition that already lists every class with the right fee polarity."""
    from types import SimpleNamespace

    from fundlex.recall import class_definition_satisfied_hits

    rule = {"rule_id": "G04", "class_substitution": True, "operations": [
        {"operation_id": "G04:0", "op": "replace", "old_text": "A类基金份额",
         "new_text": "A类、B类基金份额"},
        {"operation_id": "G04:1", "op": "replace", "old_text": "C类基金份额",
         "new_text": "C类、D类基金份额"}]}
    facts = SimpleNamespace(classes=[
        SimpleNamespace(name="A类", current=True, subscription_fee=True, service_fee=False),
        SimpleNamespace(name="C类", current=True, subscription_fee=False, service_fee=True)])
    good = ("本基金根据申购费用收取方式的不同，将基金份额分为不同的类别。"
            "在投资者申购基金份额时收取申购费用，而不计提销售服务费的，称为A类基金份额；"
            "在投资者申购基金份额时不收取申购费用，而是从本类别基金资产中计提销售服务费的，称为C类基金份额。")
    wrong = good.replace("而不计提销售服务费的，称为A类", "而是计提销售服务费的，称为A类")
    hits = class_definition_satisfied_hits(rule, facts, {"p1": good, "p2": wrong},
                                           ["p1", "p2"], {})
    assert [(location, keys) for location, _quote, keys in hits] == [
        ("p1", ("G04:0", "G04:1"))]


def test_g05_coordinated_rate_list_proves_already_satisfied():
    """``调低赎回费率和销售服务费率`` already carries ``调低销售服务费率``."""
    from fundlex.generation.effects import evaluate_operation_effect

    ledger = compile_obligations({"groups": [rule("G05")]})
    apply_facts(ledger, Facts())
    text = "调整本基金的申购费率、调低赎回费率和销售服务费率或变更收费方式。"
    inspection = Inspection([text])
    sites = [{"location": "p0", "quote": text, "state": "satisfied"}]
    proof = evaluate_operation_effect(ledger.records[0], inspection, inspection,
                                      sites, [], Facts())
    assert proof.state == "PASS", proof.as_dict()
    assert proof.artifact_status == "ALREADY_SATISFIED"


def test_class_amendment_trigger_is_not_a_class_definition_site():
    """G05's amendment clause must not become a satisfied G04 definition site."""
    from fundlex.recall import target_site_ok

    inspection = Inspection([
        "在符合法律法规、基金合同的约定且不损害已有基金份额持有人权益的情况下，经与基金托管人协商一致，基金管理人在履行适当程序后可以增加新的基金份额类别、或者在法律法规和基金合同规定的范围内变更现有基金份额类别的申购费率、调低赎回费率或变更收费方式、或者停止现有基金份额类别的销售等，调整前基金管理人需及时公告并报中国证监会备案。",
        "本基金根据申购费用收取方式的不同，将基金份额分为不同的类别。在投资者申购基金份额时收取申购费用，而不计提销售服务费的，称为A类基金份额；在投资者申购基金份额时不收取申购费用，而是从本类别基金资产中计提销售服务费的，称为C类基金份额。",
    ])
    assert not target_site_ok("G04", inspection.by_location("p0"), inspection)
    assert target_site_ok("G04", inspection.by_location("p1"), inspection)


def test_orphan_sweep_quoted_with_ascii_quotes_is_still_arbitrated():
    """A finding quoting the old clause in ASCII quotes must not become an orphan."""
    inspection = Inspection(["销售服务费每日计提，按月支付。新支付路径为5个工作日。"])
    finding = {"status": "pending", "finding_id": "SW2", "rule_id": "G15",
               "location": "p0", "issue": "residual_old_text",
               "quote": inspection.paragraphs[0].text,
               "reason": ("G15 requires deleting the old payment clause "
                          "'C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金"
                          "托管人发送基金销售服务费划付指令，经基金托管人复核后于次月首日起10个工作日内支付。'")}
    _apply_artifact_proof_to_findings([finding], {"obligations": {}}, inspection, None, {
        "G15": {"operations": [{"op": "delete",
                                 "old_text": "C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金托管人发送基金销售服务费划付指令，经基金托管人复核后于次月首日起10个工作日内支付。"}]}})
    assert finding["status"] == "resolved"
    assert finding["resolution_evidence"] == "claimed_residual_absent"


def test_sweep_cannot_borrow_sibling_effect_when_own_operation_has_no_site_proof():
    from fundlex.generation.effects import evaluate_operation_effect

    rules = [rule("G98", [{"op": "replace", "old_text": "独立旧政策仍需处理。",
                          "new_text": "独立新政策。", "condition": {"kind": "none"}}]),
             rule("G99", [{"op": "replace", "old_text": "原有业务政策。",
                          "new_text": "授权新的业务政策。", "condition": {"kind": "none"}}])]
    ledger = compile_obligations({"groups": rules})
    apply_facts(ledger, Facts())
    original, actual = Inspection(["授权新的业务政策。"]), Inspection(["授权新的业务政策。"])
    sibling = ledger.record("G99:0")
    proof = evaluate_operation_effect(sibling, original, actual,
        [{"location": "p0", "quote": actual.paragraphs[0].text}], [], Facts()).as_dict()
    findings = [dict(status="pending", rule_id="G98", operation_id="G98:0",
                     location="p0", quote=actual.paragraphs[0].text,
                     issue="unaddressed_requirement")]
    _apply_artifact_proof_to_findings(findings, {"obligations": {sibling.obligation_id: proof}},
        actual, ledger, {item["rule_id"]: item for item in rules}, original=original, facts=Facts())
    assert findings[0]["status"] == "pending"
    assert findings[0]["proof_kind"] == "SEMANTIC_UNCERTAIN"


def test_g06_one_way_review_hit_blocks_literal_absence_proof():
    from fundlex.generation.effects import evaluate_operation_effect

    old = "本基金不同基金份额类别之间不得相互转换。"
    ledger = compile_obligations({"groups": [rule("G06", [{
        "op": "delete", "old_text": old, "condition": {"kind": "none"}}])]})
    apply_facts(ledger, Facts())
    text = "但 Y 类基金份额不能转换为 A 类、C 类、E 类或 F 类基金份额。"
    inspection = Inspection([text])
    proof = evaluate_operation_effect(ledger.records[0], inspection, inspection,
                                      [], [], Facts()).as_dict()
    assert proof["state"] == "OPEN"
    assert proof["reason"] == "semantic_delete_review_required"


def test_no_progress_snapshot_changes_only_when_inputs_change():
    inspection = Inspection(["调低赎回费率"])
    planned = {"edits": [{"target_id": "T1", "location": "p0", "start": 0, "end": 6,
                          "replacement": ""}]}
    replay = {"failures": [{"code": "CLAIM_OPERATION_NOT_PLANNED",
                            "operation_id": "G05:1", "location": "p0"}]}
    first = _recovery_snapshot([target(operations=("G05:0",))], planned, inspection, replay)
    second = _recovery_snapshot([target(operations=("G05:0",))], planned, inspection, replay)
    assert first == second
    changed = _recovery_snapshot([target(operations=("G05:0", "G05:1"))], planned,
                                 inspection, replay)
    assert changed != first


def test_artifact_text_signature_ignores_container_source_hash():
    from fundlex.recall_pipeline import _artifact_text_signature
    first = Inspection(["保留句", "修改后句"])
    second = Inspection(["保留句", "修改后句"])
    # DOCX ZIP bytes/source hashes can differ after a write even when the semantic
    # paragraph artifact is unchanged; sweep must not treat that as progress.
    first.source_sha256 = "zip-a"
    second.source_sha256 = "zip-b"
    assert _artifact_text_signature(first) == _artifact_text_signature(second)
    second.paragraphs[1].text = "真正变化"
    assert _artifact_text_signature(first) != _artifact_text_signature(second)


def test_review_concurrency_keeps_rule_order_and_runs_in_parallel(monkeypatch):
    monkeypatch.setenv("FUNDLEX_REVIEW_CONCURRENCY", "2")
    routes = {
        "G01": "基金份额类别：本基金分为A类、C类。",
        "G02": "基金份额类别：本基金分为A类、C类。",
    }

    class Gateway:
        max_context_chars = 60000
        budget = None

        def __init__(self):
            self.inflight = 0
            self.max_inflight = 0
            self.lock = threading.Lock()

        def call(self, *, task_type, bounded_context, **kwargs):
            with self.lock:
                self.inflight += 1
                self.max_inflight = max(self.max_inflight, self.inflight)
            time.sleep(0.03)
            with self.lock:
                self.inflight -= 1
            # Return a completed verdict for every target id in the ledger.
            import json
            ledger_text = bounded_context.split("[TARGET_LEDGER]\n", 1)[1].split(
                "\n\n", 1)[0]
            ledger = json.loads(ledger_text)
            return SimpleNamespace(value={"results": [
                {"target_id": item["target_id"], "verdict": "completed",
                 "reason": "ok", "evidence_quote": "基金份额类别"} for item in ledger]})

    inspection = Inspection(["基金份额类别：本基金分为A类、C类。"])
    targets = [Target("T1", "G01", "p0", "基金份额类别", "needs_edit", "test",
                      0, 7, "resolved", True),
               Target("T2", "G02", "p0", "基金份额类别", "needs_edit", "test",
                      0, 7, "resolved", True)]
    planned = {"ledger": [{"target_id": "T1", "status": "planned"},
                          {"target_id": "T2", "status": "planned"}]}
    rules = {key: {"rule_id": key, "title": key, "section_hint": "释义",
                   "requirement": "requirement",
                   "operations": [{"op": "replace",
                                   "old_text": "基金份额类别",
                                   "new_text": "基金份额类别"}]}
             for key in routes}
    gateway = Gateway()
    result = _run_audit(gateway, rules, targets, planned, inspection, inspection,
                        facts=Facts())
    assert gateway.max_inflight >= 2
    assert result["rules"] == ["G01", "G02"]
    assert [item["rule_id"] for item in result["results"]] == ["G01", "G02"]
