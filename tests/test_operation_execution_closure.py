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

from fundlex.docx import TextSegment
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations, project
from fundlex.recall import (PlannedEdit, Target, _reconcile_final_plan_ledger,
                            _selected_operation_indices, merge_edits,
                            plan_target)
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
