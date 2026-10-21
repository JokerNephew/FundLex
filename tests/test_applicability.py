"""Tri-state applicability and its recovery chain (plan §9)."""
from __future__ import annotations

from pathlib import Path

import pytest

from fundlex.applicability import (ApplicabilityDecision, evaluate, judge, resolve,
                                   resolve_ledger)
from fundlex.docx import inspect_docx
from fundlex.model import ModelResult
from fundlex.obligations import compile_obligations

from test_recall_core import CLASS_DEFINITION, build_contract


class Facts:
    def __init__(self, *, status="VERIFIED", class_count=2, service=True):
        self.fact_status = {"share_class_structure": status}
        self.class_count = class_count
        self.has_service_fee = service
        self.floating_management_fee = False
        self.quotes_verified = {"floating": status == "VERIFIED"}

    def status_of(self, name):
        return self.fact_status.get(name, "UNKNOWN")

    def as_ledger(self):
        return {"fact_status": self.fact_status, "class_count": self.class_count}


class Gateway:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.max_context_chars = 60000

    def call(self, *, task_type, bounded_context, response_schema, instruction,
             prompt_version="v1"):
        self.calls.append(task_type)
        value = self.responses[task_type]
        if callable(value):
            value = value(bounded_context)
        return ModelResult(value, "stub", 1, 1, 1, 2, None, 1, task_type=task_type)


def test_deterministic_tri_state():
    condition = {"kind": "class_count", "value": "multiple"}
    assert evaluate(condition, Facts()).status == "TRUE"
    assert evaluate(condition, Facts(class_count=1)).status == "FALSE"
    assert evaluate(condition, Facts(status="UNKNOWN")).status == "UNKNOWN"
    # An unknown condition never becomes FALSE by accident.
    assert evaluate(condition, Facts(status="UNKNOWN")).decidable is False


def test_primary_judge_requires_a_verified_quote(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    condition = {"kind": "class_count", "value": "multiple"}
    decision = evaluate(condition, Facts(status="UNKNOWN"))
    gateway = Gateway({"recall_applicability": {
        "status": "TRUE", "quote": CLASS_DEFINITION, "reason": "three classes"}})
    judged = judge(decision, gateway=gateway, evidence=CLASS_DEFINITION,
                   facts=Facts(status="UNKNOWN"), inspection=inspection)
    assert judged.status == "TRUE"
    assert judged.source == "primary"
    assert judged.evidence_quote == CLASS_DEFINITION

    bad = Gateway({"recall_applicability": {
        "status": "TRUE", "quote": "not in the contract", "reason": "guess"}})
    rejected = judge(decision, gateway=bad, evidence=CLASS_DEFINITION,
                     facts=Facts(status="UNKNOWN"), inspection=inspection)
    assert rejected.status == "UNKNOWN"
    assert rejected.reason == "APPLICABILITY_QUOTE_UNVERIFIED"


def test_review_cannot_replace_unverified_class_set(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    decision = evaluate({"kind": "class_count", "value": "multiple"},
                        Facts(status="UNKNOWN"))
    gateway = Gateway({
        "recall_applicability": {"status": "UNKNOWN", "quote": "", "reason": "unclear"},
        "recall_arbitrate": {"status": "TRUE", "quote": CLASS_DEFINITION,
                             "reason": "three class labels"},
    })
    resolved = resolve(decision.condition, Facts(status="UNKNOWN"), gateway=gateway,
                       evidence=CLASS_DEFINITION, inspection=inspection)
    assert resolved.status == "UNKNOWN"
    assert gateway.calls == []


def test_unknown_remains_unknown_when_no_quote_proves_it(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    gateway = Gateway({
        "recall_applicability": {"status": "UNKNOWN", "quote": "", "reason": "unclear"},
        "recall_arbitrate": {"status": "UNKNOWN", "quote": "", "reason": "still unclear"},
    })
    resolved = resolve({"kind": "class_count", "value": "multiple"},
                       Facts(status="UNKNOWN"), gateway=gateway,
                       evidence=CLASS_DEFINITION, inspection=inspection)
    assert resolved.status == "UNKNOWN"
    assert resolved.decidable is False


def test_resolve_ledger_requires_fact_recovery_before_branch_judgment(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    guide = {"groups": [{
        "rule_id": "G05", "title": "x", "section_hint": "基金的基本情况",
        "requirement": "x",
        "operations": [
            {"op": "replace", "old_text": "调低赎回费率", "new_text": "调低销售服务费率",
             "condition": {"kind": "has_service_fee", "value": True}},
            {"op": "delete", "old_text": "并报中国证监会备案",
             "condition": {"kind": "has_service_fee", "value": True}},
        ]}]}
    ledger = compile_obligations(guide)
    # apply_facts with UNKNOWN status gives both operations UNKNOWN applicability.
    from fundlex.obligations import apply_facts
    apply_facts(ledger, Facts(status="UNKNOWN"))
    gateway = Gateway({"recall_applicability": {
        "status": "TRUE", "quote": CLASS_DEFINITION, "reason": "service class"}})
    history = resolve_ledger(ledger.records, gateway=gateway, inspection=inspection,
                             facts=Facts(status="UNKNOWN"),
                             evidence_by_rule={"G05": CLASS_DEFINITION})
    assert gateway.calls == []
    assert history == []
    assert {record.applicability.status for record in ledger.records} == {"UNKNOWN"}


def test_branch_override_cannot_bypass_fact_completeness():
    from fundlex.recall import condition_matches, condition_status
    condition = {"kind": "has_service_fee", "value": True}
    facts = Facts(status="UNKNOWN")
    assert condition_status(condition, facts) == "UNKNOWN"
    facts.condition_overrides = {
        __import__("json").dumps(condition, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":")): "TRUE"}
    assert condition_status(condition, facts) == "UNKNOWN"
    assert condition_matches(condition, facts) is False


def test_verified_fact_is_not_overturned_by_an_override():
    from fundlex.recall import condition_status
    condition = {"kind": "class_count", "value": 1}
    facts = Facts(class_count=2)
    facts.condition_overrides = {
        __import__("json").dumps(condition, sort_keys=True, ensure_ascii=False,
                                 separators=(",", ":")): "TRUE"}
    assert condition_status(condition, facts) == "FALSE"
