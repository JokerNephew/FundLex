"""Focused fact recovery and review arbitration (plan §8)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from fundlex.docx import inspect_docx
from fundlex.facts_recovery import recover_fee_facts
from fundlex.model import ModelResult
from fundlex.recall import Facts, facts_from_value

from test_recall_core import CLASS_DEFINITION, build_contract


class FakeGateway:
    def __init__(self, responses):
        self.responses = responses
        self.max_context_chars = 60000
        self.calls = []

    def call(self, *, task_type, bounded_context, response_schema, instruction,
             prompt_version="v1"):
        self.calls.append(task_type)
        value = self.responses[task_type]
        if callable(value):
            value = value(bounded_context)
        return ModelResult(value, "stub", 1, 1, 1, 2, None, 1, task_type=task_type)


def unknown_facts() -> Facts:
    return Facts(fund_type="open_regular", fund_type_quote=CLASS_DEFINITION,
                 fund_type_basis="title", classes=(), floating_management_fee=False,
                 floating_quote="", floating_basis="", notes="",
                 quotes_verified={"fund_type": True}, problems=(),
                 fact_status={"fund_type": "VERIFIED", "share_class_structure": "UNKNOWN",
                              "subscription_fee_group": "UNKNOWN",
                              "service_fee_group": "UNKNOWN",
                              "direct_sales_exempt_group": "UNKNOWN",
                              "other_sales_charged_group": "UNKNOWN"})


def candidate_value() -> dict:
    return {
        "classes": [
            {"name": "A", "subscription_fee": True, "service_fee": False,
             "current": True, "quote": CLASS_DEFINITION},
            {"name": "C", "subscription_fee": False, "service_fee": True,
             "current": True, "quote": CLASS_DEFINITION},
            {"name": "D", "subscription_fee": True, "service_fee": False,
             "current": True, "quote": CLASS_DEFINITION},
        ],
        "class_set_quote": CLASS_DEFINITION,
        "notes": "focused",
    }


def test_all_verified_facts_need_no_recovery_call(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    facts = facts_from_value(inspection, {
        "fund_type": {"value": "open_regular", "quote": CLASS_DEFINITION},
        "classes": candidate_value()["classes"],
        "floating_management_fee": {"value": False, "quote": CLASS_DEFINITION},
    })
    assert all(facts.status_of(name) == "VERIFIED" for name in
               ("share_class_structure", "subscription_fee_group", "service_fee_group"))
    gateway = FakeGateway({})
    recovered, summary = recover_fee_facts(inspection, facts, gateway)
    assert recovered is facts
    assert gateway.calls == []
    assert summary["final"] == "not_required"


def test_focused_recovery_accepts_only_verified_and_complete_class_set(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    gateway = FakeGateway({"recall_fact_recover": candidate_value()})
    recovered, summary = recover_fee_facts(inspection, unknown_facts(), gateway)
    assert gateway.calls == ["recall_fact_recover"]
    assert summary["final"] == "succeeded"
    assert recovered.status_of("share_class_structure") == "VERIFIED"
    assert recovered.subscription_group == ("A", "D")
    assert recovered.service_group == ("C",)
    # Qualification facts always come from the original extraction.
    assert recovered.fund_type == "open_regular"
    assert recovered.fund_type_quote == CLASS_DEFINITION


def test_partial_class_set_without_enumeration_quote_is_rejected(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    value = candidate_value()
    value.pop("class_set_quote")
    value["classes"] = value["classes"][:1]  # A only, silently drops C/D
    gateway = FakeGateway({"recall_fact_recover": value,
                           "recall_arbitrate": {"choice": "unknown", "quote": "",
                                                "reason": "cannot prove"}})
    recovered, summary = recover_fee_facts(inspection, unknown_facts(), gateway)
    assert recovered.status_of("share_class_structure") == "UNKNOWN"
    assert gateway.calls == ["recall_fact_recover", "recall_arbitrate"]
    assert summary["actions"] == ["FOCUSED_FACT_RESOLVE", "FACT_ARBITRATION"]
    assert summary["final"] == "failed"


def test_review_can_choose_the_original_evidence(tmp_path: Path):
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    value = candidate_value()
    value["class_set_quote"] = "not in the contract"
    gateway = FakeGateway({"recall_fact_recover": value,
                           "recall_arbitrate": {"choice": "original",
                                                "quote": CLASS_DEFINITION,
                                                "reason": "original enumeration is authoritative"}})
    recovered, summary = recover_fee_facts(inspection, unknown_facts(), gateway)
    assert recovered is not None
    assert recovered.status_of("share_class_structure") == "UNKNOWN"
    assert summary["final"] == "failed"
    assert summary["history"][-1]["detail"].startswith("choice=original")


def test_enumeration_quote_must_name_every_candidate_class(tmp_path: Path):
    """A prefix enumeration cannot hide C/D behind an A-only candidate (plan §7.3)."""
    source = tmp_path / "contract.docx"
    build_contract(source)
    inspection = inspect_docx(source, full=True)
    value = candidate_value()
    value["classes"] = value["classes"][:1]  # A only
    value["class_set_quote"] = "基金份额类别：本基金将基金份额分为A类、C类和D类不同的类别"
    gateway = FakeGateway({"recall_fact_recover": value,
                           "recall_arbitrate": {"choice": "unknown", "quote": "",
                                                "reason": "cannot prove"}})
    recovered, summary = recover_fee_facts(inspection, unknown_facts(), gateway)
    assert recovered.status_of("share_class_structure") == "UNKNOWN"
    assert summary["final"] == "failed"
