"""FL-D608: append anchors rebinding to the end of a class-definition group.

B05 (广发弘利3个月滚动持有) shows the failure: the engine appended the G01/G03
policy text inline after the class-division *headline* definition (释义 p117 /
基本情况 p155), while the frozen labels declare the site at the end of the
per-class definition group (p119 / p159).  The scorer then misses the appended
clauses at the declared site, producing not_executed.  The group-continuation
chain resolves the group end so the policy lands after the last member.
"""
from __future__ import annotations

from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.recall import (Target, _definition_group_continuation_end,
                            rebind_split_append_targets)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "funds_word" / "基金合同第一批" /
          "广发弘利3个月滚动持有债券型证券投资基金基金合同.docx")


def _inspection():
    return inspect_docx(SOURCE, full=True)


def _text(inspection, location: str) -> str:
    return inspection.by_location(location).text.strip()


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
