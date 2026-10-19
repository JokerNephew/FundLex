"""Tri-state applicability tests (external review 2026-10-19, P0-A).

``condition_status`` never guesses: an operation whose branch cannot be decided from
VERIFIED facts stays UNKNOWN, and the registry-mode planner resolves the target as
``RECALL_FACT_UNVERIFIED`` instead of executing a branch.
"""
import pytest

from fundlex.recall import (ClassFact, Facts, RecallError, Target, condition_status,
                            plan_target)

REGISTRY_ENV = "FUNDLEX_GENERATION_STRATEGY"


def _facts(*, verified: bool = True, classes=None, service: bool = True,
           floating: bool = False, floating_ok: bool = True) -> Facts:
    classes = classes if classes is not None else (
        ClassFact("A类", True, False, True, None, ""),
        ClassFact("C类", False, True, True, None, ""),
    )
    status = {"fund_type": "VERIFIED", "share_class_structure": "VERIFIED",
              "subscription_fee_group": "VERIFIED", "service_fee_group": "VERIFIED"}
    if not verified:
        status = {}
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=classes, floating_management_fee=floating, floating_quote="",
                 floating_basis="", notes="", quotes_verified={"floating": floating_ok},
                 problems=(), fact_status=status)


def test_class_count_unknown_without_verified_structure():
    facts = _facts(verified=False)
    assert condition_status({"kind": "class_count", "value": 1}, facts) == "UNKNOWN"
    assert condition_status({"kind": "class_count", "value": "multiple"}, facts) == "UNKNOWN"


def test_class_count_true_false_when_verified():
    single = _facts(classes=(ClassFact("A类", True, False, True, None, ""),))
    assert condition_status({"kind": "class_count", "value": 1}, single) == "TRUE"
    assert condition_status({"kind": "class_count", "value": "multiple"}, single) == "FALSE"
    multi = _facts()
    assert condition_status({"kind": "class_count", "value": "multiple"}, multi) == "TRUE"


def test_has_service_fee_tri_state():
    facts = _facts()
    assert condition_status({"kind": "has_service_fee", "value": True}, facts) == "TRUE"
    assert condition_status({"kind": "has_service_fee", "value": False}, facts) == "FALSE"
    unverified = _facts(verified=False)
    assert condition_status({"kind": "has_service_fee", "value": True}, unverified) == "UNKNOWN"


def test_floating_fee_needs_a_verified_quote():
    facts = _facts(floating=False, floating_ok=False)
    assert condition_status({"kind": "is_floating_fee", "value": False}, facts) == "UNKNOWN"
    verified = _facts(floating=False, floating_ok=True)
    assert condition_status({"kind": "is_floating_fee", "value": False}, verified) == "TRUE"


def test_compound_propagates_false_and_unknown():
    facts = _facts(verified=False)
    unknown = {"kind": "compound", "value": [{"kind": "has_service_fee", "value": True}]}
    assert condition_status(unknown, facts) == "UNKNOWN"
    mixed = {"kind": "compound", "value": [
        {"kind": "has_service_fee", "value": True},
        {"kind": "is_floating_fee", "value": True}]}
    verified = _facts(floating=False, floating_ok=True)
    # has_service_fee TRUE, is_floating_fee FALSE → FALSE dominates.
    assert condition_status(mixed, verified) == "FALSE"


def _target(rule_id: str) -> Target:
    return Target(target_id="T1", rule_id=rule_id, location="p1", quote="",
                  state="needs_edit", reason="")


def test_unknown_only_operations_resolve_as_fact_unverified(monkeypatch):
    monkeypatch.setenv(REGISTRY_ENV, "registry")
    rule = {"rule_id": "G05", "title": "t", "requirement": "r",
            "operations": [{"op": "replace", "old_text": "调低赎回费率",
                            "new_text": "调低销售服务费率",
                            "condition": {"kind": "has_service_fee", "value": True}}]}
    with pytest.raises(RecallError) as excinfo:
        plan_target(rule, _target("G05"), None, _facts(verified=False), None,
                    compose_budget=[1])
    assert excinfo.value.code == "RECALL_FACT_UNVERIFIED"


def test_route_blocked_facts_resolve_as_fact_unverified(monkeypatch):
    monkeypatch.setenv(REGISTRY_ENV, "registry")
    rule = {"rule_id": "G16", "title": "t", "requirement": "r",
            "operations": [{"op": "append", "new_text": "销售服务费每日计提。",
                            "condition": {"kind": "none", "value": None}}]}
    with pytest.raises(RecallError) as excinfo:
        plan_target(rule, _target("G16"), None, _facts(verified=False), None,
                    compose_budget=[1])
    assert excinfo.value.code == "RECALL_FACT_UNVERIFIED"
