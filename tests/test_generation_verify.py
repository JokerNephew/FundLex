"""Phase 6 tests: composed-edit verification (plan v4 §11–§13, §27).

Program checks (V1/V2-B) always run when the strategy flag is on; the V3 model
critic runs only for tier-3 rules. The gateway is scripted, so no model calls.
"""
from fundlex.recall import ClassFact, Facts, Target, _verify_composed


class _Gateway:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.max_context_chars = 60000
        self.calls = []

    def call(self, *, task_type, bounded_context, response_schema, instruction,
             prompt_version="v1"):
        self.calls.append(task_type)
        value = self.responses.get(task_type)
        if value is None:
            raise AssertionError(f"unexpected task_type {task_type}")
        return type("Result", (), {"value": value})()


def _facts() -> Facts:
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=(ClassFact("C类", False, True, True, None, ""),),
                 floating_management_fee=False, floating_quote="", floating_basis="",
                 notes="", quotes_verified={}, problems=())


def _target(rule_id: str = "G16") -> Target:
    return Target(target_id="T1", rule_id=rule_id, location="p1", quote="",
                  state="needs_edit", reason="")


def _rule(rule_id: str, old_text: str, new_text: str) -> dict:
    return {"rule_id": rule_id, "title": "t", "requirement": "按指引改写本条款。",
            "operations": [{"op": "replace", "old_text": old_text, "new_text": new_text}],
            "old_text_variants": []}


def test_program_check_blocks_protected_literal_loss_without_calling_v3():
    gateway = _Gateway()
    rule = _rule("G18", "老条款", "新条款")
    ok, reason = _verify_composed(
        rule, _target("G18"),
        actual="C类基金份额的销售服务费按前一日资产净值的0.40%年费率计提。",
        replacement="C类基金份额的销售服务费按前一日资产净值的0.60%年费率计提。",
        fixed_text="", facts=_facts(), gateway=gateway, mode="replace")
    assert ok is False
    assert reason.startswith("program_check")
    assert gateway.calls == []


def test_tier3_rule_runs_v3_and_can_fail():
    gateway = _Gateway({"recall_verify": {"verdict": "fail", "reason": "遗漏直销返还"}})
    rule = _rule("G16", "基金销售服务费每日计提。", "基金销售服务费每日计提，其余不变。")
    ok, reason = _verify_composed(
        rule, _target("G16"),
        actual="基金销售服务费每日计提，按月支付给销售机构。",
        replacement="基金销售服务费每日计提，按月支付给销售机构。",
        fixed_text="", facts=_facts(), gateway=gateway, mode="replace")
    assert ok is False
    assert reason.startswith("v3_fail")
    assert gateway.calls == ["recall_verify"]


def test_tier3_rule_passes_with_v3():
    gateway = _Gateway({"recall_verify": {"verdict": "pass", "reason": ""}})
    rule = _rule("G16", "基金销售服务费每日计提。", "基金销售服务费每日计提。")
    ok, reason = _verify_composed(
        rule, _target("G16"),
        actual="基金销售服务费每日计提，按月支付给销售机构。",
        replacement="基金销售服务费每日计提，按月支付给销售机构。",
        fixed_text="", facts=_facts(), gateway=gateway, mode="replace")
    assert ok is True
    assert reason == "v3_pass"


def test_non_tier3_rules_get_program_checks_only():
    gateway = _Gateway()
    rule = _rule("G08", "老句", "新句")
    ok, reason = _verify_composed(
        rule, _target("G08"),
        actual="本基金的申购费率由基金管理人决定，并在招募说明书中列示。",
        replacement="本基金的申购费率由基金管理人决定，并在招募说明书中列示。",
        fixed_text="", facts=_facts(), gateway=gateway, mode="replace")
    assert ok is True
    assert reason == "program_only"
    assert gateway.calls == []
