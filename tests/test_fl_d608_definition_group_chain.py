"""FL-D608: append anchors rebinding to the end of a class-definition group.

B05 (广发弘利3个月滚动持有) shows the failure: the engine appended the G01/G03
policy text inline after the class-division *headline* definition (释义 p117 /
基本情况 p155), while the frozen labels declare the site at the end of the
per-class definition group (p119 / p159).  The scorer then misses the appended
clauses at the declared site, producing not_executed.  The group-continuation
chain resolves the group end so the policy lands after the last member.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import (ClassFact, Facts, Target,
                            _definition_group_continuation_end, plan_target,
                            rebind_split_append_targets)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g17_usage_site_closure import NoModel  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "funds_word" / "基金合同第一批" /
          "广发弘利3个月滚动持有债券型证券投资基金基金合同.docx")
GUIDE = json.loads((ROOT / "guides" / "builtin_guide_v1.json").read_text(encoding="utf-8"))


def _inspection():
    return inspect_docx(SOURCE, full=True)


def _text(inspection, location: str) -> str:
    return inspection.by_location(location).text.strip()


def _facts() -> Facts:
    classes = (ClassFact(name="A类", subscription_fee=True, service_fee=False,
                         current=True, rate=None, quote="A类"),
               ClassFact(name="C类", subscription_fee=False, service_fee=True,
                         current=True, rate=0.25, quote="C类"))
    return Facts(fund_type="open_regular", fund_type_quote="契约型开放式",
                 fund_type_basis="test", classes=classes,
                 floating_management_fee=False, floating_quote="", floating_basis="",
                 notes="", quotes_verified={}, problems=(),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def _plan_append(rule_id: str, location: str):
    inspection = _inspection()
    text = inspection.by_location(location).text
    target = Target("T", rule_id, location, text, "needs_edit", "survey",
                    start=0, end=len(text), resolution="resolved",
                    operations=(f"{rule_id}:0",))
    rule = next(item for item in GUIDE["groups"] if item["rule_id"] == rule_id)
    ledger = compile_obligations({"groups": [rule]})
    facts = _facts()
    apply_facts(ledger, facts)
    return plan_target(rule, target, inspection, facts, NoModel(),
                       compose_budget=[0], obligations=ledger)


def test_group_chain_ends_at_last_class_definition_in_glossary():
    inspection = _inspection()
    anchor = inspection.by_location("p117")
    assert anchor.text.strip().startswith("基金份额类别：指根据申购费用")
    end = _definition_group_continuation_end(anchor, inspection)
    assert end is not None
    assert end.location == "p119"
    assert end.text.strip().startswith("C类基金份额或C类份额")
    # The next paragraph is an unrelated definition topic; the chain must stop.
    assert _text(inspection, "p120").startswith("运作期起始日")


def test_group_chain_ends_at_setting_tail_in_basic_info_block():
    inspection = _inspection()
    anchor = inspection.by_location("p155")
    assert anchor.text.strip().startswith("本基金根据申购费用、销售服务费收取方式的不同")
    end = _definition_group_continuation_end(anchor, inspection)
    assert end is not None
    assert end.location == "p159"
    assert "具体设置" in end.text


def test_rebind_moves_append_target_to_group_end():
    inspection = _inspection()
    target = Target("Y001", "G01", "p117", _text(inspection, "p117"),
                    "needs_edit", "survey", operations=("G01:0",))
    rebind_split_append_targets([target], inspection, include_group_continuation=True)
    assert target.location == "p119"
    assert "DEFINITION_GROUP_APPEND_END" in target.reason


def test_anchor_already_at_group_end_is_not_rebound():
    inspection = _inspection()
    anchor = inspection.by_location("p119")
    end = _definition_group_continuation_end(anchor, inspection)
    assert end is None


def test_new_topic_defines_no_group_continuation():
    inspection = _inspection()
    # p156 is a per-class definition; it carries no group-headline marker and
    # must not start a fresh chain.
    anchor = inspection.by_location("p156")
    assert _definition_group_continuation_end(anchor, inspection) is None


def test_plan_stage_acceptance_survives_the_target_site_second_guard():
    """The plan-stage double guard must not veto its own rebound group end.

    First-layer FL-D608 rebound p117->p119 / p155->p159, but the follow-up
    ``target_site_ok`` recheck re-ran ``append_site_ok`` at the AUDIT stance
    (no group-end acceptance), so planning still raised
    TARGET_SOURCE_MISMATCH and no edit materialised.
    """
    edit = _plan_append("G01", "p117")
    assert edit is not None
    assert edit.location == "p119"
    assert "投资者通过直销机构" in edit.replacement
    edit = _plan_append("G03", "p155")
    assert edit is not None
    assert edit.location == "p159"
    assert "投资者通过直销机构" in edit.replacement
