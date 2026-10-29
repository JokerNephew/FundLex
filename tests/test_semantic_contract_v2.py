"""Model-first semantic targets: code validates artifacts, not wording."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from docx import Document

from fundlex.docx import inspect_docx
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import plan_target
from fundlex.semantic_contract import (SemanticTarget, discover_semantic_targets,
                                       load_semantic_policies,
                                       semantic_target_to_target,
                                       validate_semantic_target)
from test_g17_usage_site_closure import NoModel
from test_recall_core import _facts

ROOT = Path(__file__).resolve().parents[1]
GUIDE = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))
OLD = ("赎回金额为按实际确认的有效赎回份额乘以申请当日基金份额净值的金额，"
       "净赎回金额为赎回金额扣除相应的费用的金额，各计算结果均保留至小数点后两位。")
NEW = ("赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额的基金份额净值，"
       "并扣除或加上相应的费用，赎回金额单位为元，各计算结果均保留至小数点后两位。")


class _Gateway:
    max_context_chars = 12000

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def call(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(value=self.payload)


def _doc(tmp_path, text: str, location="p0"):
    path = tmp_path / "contract.docx"
    document = Document()
    document.add_paragraph(text)
    document.save(path)
    return inspect_docx(path, full=True)


def _rule(rule_id="G09"):
    return next(item for item in GUIDE["groups"] if item["rule_id"] == rule_id)


def test_model_target_is_validated_and_planned(tmp_path):
    inspection = _doc(tmp_path, OLD)
    gateway = _Gateway({"targets": [{
        "location": "p0", "quote": OLD, "operation_id": "G09",
        "replacement": NEW, "preserved_text": ["各计算结果均保留至小数点后两位"],
        "reason": "redemption amount clause",
    }]})
    policy = load_semantic_policies()["G09"]
    accepted, rejected, _ = discover_semantic_targets(
        gateway, _rule(), inspection, ["p0"], policy)
    assert not rejected and len(accepted) == 1
    target = semantic_target_to_target(accepted[0])
    ledger = compile_obligations({"groups": [_rule()]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(_rule(), target, inspection, facts, NoModel(),
                       compose_budget=[0], obligations=ledger)
    assert edit.content_source == "semantic_v2"
    assert edit.replacement == NEW
    assert edit.evidence["preserved_text"] == ["各计算结果均保留至小数点后两位"]


def test_wrong_site_is_rejected(tmp_path):
    inspection = _doc(tmp_path, "本基金的管理费按前一日基金资产净值的1%年费率计提。")
    policy = load_semantic_policies()["G09"]
    target = SemanticTarget("G09", "G09:0", "p0", OLD, 0, len(OLD), NEW)
    ok, reason = validate_semantic_target(
        target, _rule(), inspection, ["p0"], policy=policy)
    assert not ok
    assert reason == "quote_not_in_source"


def test_lost_protected_tail_is_rejected(tmp_path):
    inspection = _doc(tmp_path, OLD)
    policy = load_semantic_policies()["G09"]
    target = SemanticTarget(
        "G09", "G09:0", "p0", OLD, 0, len(OLD),
        "赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额的基金份额净值并扣除或加上相应的费用。")
    ok, reason = validate_semantic_target(
        target, _rule(), inspection, ["p0"], policy=policy)
    assert not ok
    assert reason.startswith("lost_protected_term")


def test_quote_outside_scope_is_rejected(tmp_path):
    inspection = _doc(tmp_path, OLD)
    target = SemanticTarget("G09", "G09:0", "p0", OLD, 0, len(OLD), NEW)
    ok, reason = validate_semantic_target(
        target, _rule(), inspection, ["p1"],
        policy=load_semantic_policies()["G09"])
    assert not ok
    assert reason == "location_outside_scope"


def test_multi_operation_rule_infers_operation_from_quote(tmp_path):
    from fundlex.semantic_contract import parse_semantic_targets
    rule = next(item for item in GUIDE["groups"] if item["rule_id"] == "G02")
    inspection = _doc(tmp_path, "A类基金份额：申购时收取申购费，不计提销售服务费。")
    policy = load_semantic_policies()["G02"]
    accepted, rejected = parse_semantic_targets({"targets": [{
        "location": "p0", "quote": "A类基金份额：申购时收取申购费，不计提销售服务费。", "operation_id": "replace",
        "replacement": "A类人民币、A类美元现汇：申购时收取申购费，不计提销售服务费。",
        "preserved_text": [], "reason": "class group",
    }]}, rule, inspection, ["p0"], policy)
    assert not rejected, rejected
    assert accepted[0].operation_id == "G02:0"


def test_template_policy_ignores_model_replacement_text(tmp_path):
    """G16 uses the guide's fixed policy text; the model only locates the site."""
    from fundlex.semantic_contract import parse_semantic_targets
    rule = next(item for item in GUIDE["groups"] if item["rule_id"] == "G16")
    old = "C类基金份额的销售服务费每日计提，按月支付。"
    inspection = _doc(tmp_path, old)
    policy = load_semantic_policies()["G16"]
    accepted, rejected = parse_semantic_targets({"targets": [{
        "location": "p0", "quote": old, "operation_id": "G16:0",
        "replacement": "每年支付一次的错误文本",
        "preserved_text": [], "reason": "payment clause",
    }]}, rule, inspection, ["p0"], policy)
    assert not rejected, rejected
    assert accepted[0].replacement == str(rule["operations"][0]["new_text"])
