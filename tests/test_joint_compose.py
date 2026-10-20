"""Joint Compose for overlapping obligations (plan §21)."""
from __future__ import annotations

from fundlex.generation.joint import plan_joint_compose
from fundlex.model import ModelResult


class Facts:
    def as_ledger(self):
        return {"classes": ["A", "C"], "service_group": ["C"]}


class Gateway:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []
        self.max_context_chars = 60000

    def call(self, *, task_type, bounded_context, response_schema, instruction,
             prompt_version="v1"):
        self.calls.append(task_type)
        value = self.responses[task_type]
        return ModelResult(value, "stub", 1, 1, 1, 2, None, 1, task_type=task_type)


SPAN = "基金管理人可以调低赎回费率。并报中国证监会备案。"
OBLIGATIONS = [{
    "rule_id": "G05", "requirement": "调低销售服务费率并删除备案句",
    "operations": [
        {"op": "replace", "old_text": "调低赎回费率", "new_text": "调低销售服务费率"},
        {"op": "delete", "old_text": "并报中国证监会备案"},
    ],
}]


def test_joint_compose_accepts_a_validated_and_reviewed_replacement():
    gateway = Gateway({
        "recall_joint_compose": {"replacement": "基金管理人可以调低销售服务费率。",
                                 "preserved": ["基金管理人"], "basis": "joint"},
        "recall_verify": {"verdict": "pass", "reason": "both obligations met"},
    })
    result = plan_joint_compose(span_text=SPAN, start=0, end=len(SPAN),
                                obligations=OBLIGATIONS,
                                fixed_texts=["调低销售服务费率"], facts=Facts(),
                                gateway=gateway, rule_ids=["G05"])
    assert result is not None
    assert result["replacement"] == "基金管理人可以调低销售服务费率。"
    assert gateway.calls == ["recall_joint_compose", "recall_verify"]


def test_joint_compose_rejects_an_invented_number_before_review():
    gateway = Gateway({
        "recall_joint_compose": {"replacement": "基金管理人可以调低销售服务费率0.5%。",
                                 "preserved": [], "basis": "joint"},
        "recall_verify": {"verdict": "pass", "reason": "should not be reached"},
    })
    result = plan_joint_compose(span_text=SPAN, start=0, end=len(SPAN),
                                obligations=OBLIGATIONS,
                                fixed_texts=["调低销售服务费率"], facts=Facts(),
                                gateway=gateway, rule_ids=["G05"])
    assert result is None
    assert gateway.calls == ["recall_joint_compose"]


def test_joint_compose_rejects_a_review_failure():
    gateway = Gateway({
        "recall_joint_compose": {"replacement": "基金管理人可以调低销售服务费率。",
                                 "preserved": [], "basis": "joint"},
        "recall_verify": {"verdict": "fail", "reason": "delete obligation missing"},
    })
    result = plan_joint_compose(span_text=SPAN, start=0, end=len(SPAN),
                                obligations=OBLIGATIONS,
                                fixed_texts=["调低销售服务费率"], facts=Facts(),
                                gateway=gateway, rule_ids=["G05"])
    assert result is None


def test_joint_compose_rejects_a_missing_fixed_text():
    gateway = Gateway({
        "recall_joint_compose": {"replacement": "基金管理人可以调低赎回费率。",
                                 "preserved": [], "basis": "no change"},
        "recall_verify": {"verdict": "pass", "reason": "should not be reached"},
    })
    result = plan_joint_compose(span_text=SPAN, start=0, end=len(SPAN),
                                obligations=OBLIGATIONS,
                                fixed_texts=["调低销售服务费率"], facts=Facts(),
                                gateway=gateway, rule_ids=["G05"])
    assert result is None
    assert gateway.calls == ["recall_joint_compose"]


def test_joint_compose_rejects_a_replacement_that_keeps_the_delete_text():
    gateway = Gateway({
        "recall_joint_compose": {"replacement": "基金管理人可以调低销售服务费率。并报中国证监会备案。",
                                 "preserved": [], "basis": "kept delete"},
        "recall_verify": {"verdict": "pass", "reason": "should not be reached"},
    })
    result = plan_joint_compose(span_text=SPAN, start=0, end=len(SPAN),
                                obligations=OBLIGATIONS,
                                fixed_texts=["调低销售服务费率"], facts=Facts(),
                                gateway=gateway, rule_ids=["G05"])
    assert result is None
    assert gateway.calls == ["recall_joint_compose"]
