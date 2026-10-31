"""FL-D587 / B03 p228: the class-qualified G08 legacy sentence is an edit site.

「本基金A类基金份额的申购费率由基金管理人决定，并在招募说明书中列示。」
keeps the canonical kernel with a class qualifier inserted.  The inventory can
miss the canonical sentence; without a residual target the FL-D601/602
NO_GUIDE_SITE closure falsely certifies the obligation FALSE (v2 B03
false_complete).  The deterministic sweep must create the replace target, and
``plan_policy_replacement`` rewrites the clause to the full multi-class text.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fundlex.recall import Target, ensure_g08_variant_targets
from fundlex.generation.template import plan_policy_replacement


ROOT = Path(__file__).resolve().parents[1]

B03_SENTENCE = "本基金A类基金份额的申购费率由基金管理人决定，并在招募说明书中列示。"
B03_PARAGRAPH = ("2、申购份额的计算及余额的处理方式：本基金申购份额的计算详见《招募说明书》。"
                 + B03_SENTENCE
                 + "申购的有效份额为净申购金额除以当日该类基金份额的基金份额净值。")
CANONICAL = "本基金的申购费率由基金管理人决定，并在招募说明书中列示。"
ACTUAL_RATE = "实际执行的申购费率在招募说明书载明。"


def _guide_rule(rule_id: str) -> dict:
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text())
    return next(group for group in guide["groups"] if group["rule_id"] == rule_id)


def _inspection(texts: list[str]):
    paragraphs = []
    for index, text in enumerate(texts):
        paragraphs.append(SimpleNamespace(
            location=f"p{index}", text=text,
            segments=[SimpleNamespace(start=0, end=len(text))]))
    return SimpleNamespace(paragraphs=paragraphs)


def test_class_qualified_variant_gets_residual_target():
    created = ensure_g08_variant_targets([], {"G08": _guide_rule("G08")},
                                         _inspection([B03_PARAGRAPH]))
    assert len(created) == 1
    target = created[0]
    assert target.rule_id == "G08"
    assert target.state == "needs_edit"
    assert target.reason == "g08_legacy_class_variant"
    assert target.quote == B03_SENTENCE
    assert target.location == "p0"
    assert target.operations == ("G08:0",)
    assert B03_PARAGRAPH[target.start:target.end] == B03_SENTENCE


def test_variant_target_plans_full_replacement():
    created = ensure_g08_variant_targets([], {"G08": _guide_rule("G08")},
                                         _inspection([B03_PARAGRAPH]))
    rule = _guide_rule("G08")
    instantiated = str(rule["operations"][0]["new_text"])
    result = plan_policy_replacement(created[0].quote, instantiated, "G08")
    assert result is not None
    assert result.content_source == "tier1_template"
    assert "A类基金份额在申购时收取申购费用" in result.replacement
    assert "C类基金份额不收取申购费用" in result.replacement
    assert "直销机构申购本基金A类基金份额不收取申购费" in result.replacement
    assert B03_SENTENCE not in result.replacement


def test_canonical_sentence_covered_by_inventory_stays_untouched():
    created = ensure_g08_variant_targets([], {"G08": _guide_rule("G08")},
                                         _inspection(["费用条款。" + CANONICAL]))
    assert created == []


def test_live_g08_target_suppresses_sweep():
    live = Target(target_id="T1", rule_id="G08", location="p0",
                  quote=B03_SENTENCE, state="needs_edit", reason="inventory",
                  start=0, end=len(B03_SENTENCE))
    created = ensure_g08_variant_targets([live], {"G08": _guide_rule("G08")},
                                         _inspection([B03_PARAGRAPH]))
    assert created == []


def test_actual_rate_variant_never_becomes_target():
    # FL-D602: the «实际执行的申购费率在招募说明书载明» wording is evidence
    # only; the sweep must not resurrect it as an edit site.
    created = ensure_g08_variant_targets([], {"G08": _guide_rule("G08")},
                                         _inspection(["费用说明。" + ACTUAL_RATE]))
    assert created == []


def test_mixed_clause_content_never_becomes_target():
    mixed = "本基金A类基金份额的申购费率由基金管理人决定，并在招募说明书中列示，赎回时另行公告。"
    created = ensure_g08_variant_targets([], {"G08": _guide_rule("G08")},
                                         _inspection([mixed]))
    assert created == []
