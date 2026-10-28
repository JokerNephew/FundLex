"""A deterministic executor may escalate to compose only with a valid approval."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fundlex.docx import TextSegment
from fundlex.recall import (ClassFact, Facts, RecallError, Target, plan_target)
from fundlex.semantic_evidence import ApprovalBook, approval_from_target, guide_fingerprint

ROOT = Path(__file__).resolve().parents[1]
RULES = {rule["rule_id"]: rule
         for rule in json.loads((ROOT / "guides/builtin_guide_v1.json").read_text())["groups"]}
VARIANT = ("投资者赎回所得金额按确认的有效赎回份额乘以当日对应份额类别的基金份额净值，"
           "再减去应扣的相关费用计算，赎回金额单位为元。")


def inspection(text: str):
    span = SimpleNamespace(location="p0", text=text,
                           segments=(TextSegment(0, len(text)),),
                           zone="body", fingerprint="p0", section_path="赎回")
    return SimpleNamespace(source_sha256="escalation-source",
                           paragraphs=(span,),
                           by_location=lambda location: span)


def facts() -> Facts:
    return Facts("", "", "", (ClassFact("A", True, False, True, None, ""),
                              ClassFact("C", False, True, True, None, "")),
                 False, "", "", "", {}, (),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


class Gateway:
    max_context_chars = 20000

    def __init__(self, replacement: str):
        self.replacement = replacement
        self.calls: list[str] = []

    def call(self, **kwargs):
        self.calls.append(kwargs["task_type"])
        if kwargs["task_type"] == "recall_compose":
            return SimpleNamespace(value={"replacement": self.replacement,
                                          "preserved": [], "basis": "same policy"})
        return SimpleNamespace(value={"verdict": "pass"})


def target():
    return Target("T", "G09", "p0", VARIANT, "needs_edit", "inventory",
                  start=0, end=len(VARIANT), resolution="resolved", segment_ok=True,
                  operations=("G09:0",), scope_id="G09:probe")


def test_variant_without_approval_still_fails_closed():
    doc = inspection(VARIANT)
    gateway = Gateway("新文")
    with pytest.raises(RecallError) as error:
        plan_target(RULES["G09"], target(), doc, facts(), gateway, compose_budget=[5])
    assert error.value.code in {"RECALL_ROUTED_EXECUTOR_UNAVAILABLE",
                                "RECALL_TARGET_VARIANT_UNMATCHED"}
    assert not gateway.calls


def test_variant_with_approval_reaches_compose():
    doc = inspection(VARIANT)
    bound = target()
    approval = approval_from_target("AP:T", bound, doc, guide_id="active_guide",
                                    guide_sha256=guide_fingerprint([RULES["G09"]]))
    bound.approval_id = approval.approval_id
    gateway = Gateway("赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额的基金份额净值"
                      "并扣除或加上相应的费用，赎回金额单位为元。")
    edit = plan_target(RULES["G09"], bound, doc, facts(), gateway,
                       compose_budget=[5], approvals=ApprovalBook([approval]))
    assert gateway.calls, "approved variant must reach the compose fallback"
    assert edit is not None
    assert edit.evidence["semantic_approval"]["approval_id"] == "AP:T"
