"""G11 must not keep the source class-group prefix when the policy repeats it."""
import json
import sys
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import Target, plan_target

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g17_usage_site_closure import NoModel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "funds_word" / "基金合同第一批" / "广发沪深300指数增强型发起式证券投资基金基金合同.docx"
GUIDE = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))


def _facts():
    from fundlex.recall import ClassFact, Facts
    classes = (
        ClassFact(name="A类基金份额", subscription_fee=True, service_fee=False,
                  current=True, rate="1.2%", quote="A类"),
        ClassFact(name="Y类基金份额", subscription_fee=True, service_fee=False,
                  current=True, rate=None, quote="Y类"),
        ClassFact(name="C类基金份额", subscription_fee=False, service_fee=True,
                  current=True, rate="0.4%", quote="C类"),
    )
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=classes, floating_management_fee=False,
                 floating_quote="", floating_basis="", notes="",
                 quotes_verified={}, problems=(),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def test_g11_drops_the_source_class_prefix_before_the_policy_text():
    inspection = inspect_docx(SOURCE, full=True)
    rule = next(item for item in GUIDE["groups"] if item["rule_id"] == "G11")
    operation = next(item for item in rule["operations"] if item["operation_id"] == "G11:1")
    text = inspection.by_location("p243").text
    quote = "申购费用由投资人承担，不列入基金财产。"
    start = text.find(quote)
    target = Target("T", "G11", "p243", quote, "needs_edit", "",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=("G11:1",))
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    edit = plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[3], obligations=ledger)
    assert edit is not None
    assert edit.start == text.index("本基金A类")
    assert not text[edit.start:edit.start + 12].endswith("的通过")
    assert edit.replacement.startswith("通过直销机构")
