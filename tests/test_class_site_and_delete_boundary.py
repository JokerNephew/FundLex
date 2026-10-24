"""D07 source boundaries: pension eligibility is not a fee group (FL-D209)."""
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from fundlex.docx import inspect_docx
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import (ClassFact, RecallError, Target, assign_target_operations,
                            plan_target, target_site_ok)
from fundlex.recall_pipeline import _plan_and_generate
from test_recall_core import _facts


def _rule(rule_id):
    guide = json.loads((Path(__file__).resolve().parents[1] /
                       "guides/builtin_guide_v1.json").read_text())
    return next(item for item in guide["groups"] if item["rule_id"] == rule_id)


def _source(tmp_path, paragraphs):
    source = tmp_path / "source.docx"
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(source)
    return source, inspect_docx(source, full=True)


class NoModel:
    max_context_chars = 60000

    def call(self, **kwargs):
        raise AssertionError("exact source binding must not call a model")


@pytest.mark.parametrize("rule_id", ["G02", "G04"])
def test_account_eligibility_is_never_rewritten_as_a_fee_group(tmp_path, rule_id):
    text = ("本基金根据销售所适用账户的不同，将基金份额分为 A 类基金份额和 Y 类基金份额。"
            "A 类基金份额不得对个人养老金账户进行销售，Y 类基金份额仅面向个人养老金账户销售。")
    _, original = _source(tmp_path, [text])
    rule = _rule(rule_id)
    quote = "A 类基金份额不得对个人养老金账户进行销售，"
    start = text.index(quote)
    target = Target("T", rule_id, "p0", quote, "needs_edit", "inventory",
                    start=start, end=start + len(quote), resolution="resolved",
                    operations=(f"{rule_id}:0",))
    assert not target_site_ok(rule_id, original.by_location("p0"), original)
    with pytest.raises(RecallError) as exc:
        plan_target(rule, target, original, _facts(), NoModel(), compose_budget=[0])
    assert exc.value.code == "RECALL_TARGET_SITE_MISMATCH"
    assign_target_operations([target], {rule_id: rule}, original, _facts())
    assert target.out_of_scope
    replay = replay_claims([], original, original, rules_by_id={rule_id: rule},
                           facts=_facts(), targets_by_id={"T": target.as_dict()})
    assert not replay.get("operations")


@pytest.mark.parametrize("delimiter", ["、", "、 "])
def test_g05_word_quote_binds_its_owned_list_delimiter_and_delivers_docx(tmp_path, delimiter):
    text = ("有关基金份额类别的具体设置等由基金管理人确定，并在招募说明书中公告。"
            "基金管理人在履行适当程序后可以增加新的基金份额类别、变更现有基金份额类别的申购费率"
            + delimiter + "调低赎回费率或变更收费方式、或者停止现有基金份额类别的销售等，"
            "调整前基金管理人需及时公告并报中国证监会备案。")
    decoy = "在法律法规规定的范围内调整本基金的申购费率、调低赎回费率或变更收费方式；"
    source, original = _source(tmp_path, [text, decoy])
    rule = _rule("G05")
    facts = replace(_facts(), classes=(ClassFact("A类基金份额", True, False, True, None, ""),
                                     ClassFact("Y类基金份额", True, False, True, None, "")))
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    targets = []
    for index, word in ((1, "调低赎回费率"), (2, "并报中国证监会备案")):
        start = text.index(word)
        targets.append(Target(str(index), "G05", "p0", word, "needs_edit", "inventory",
                              start=start, end=start + len(word), resolution="resolved",
                              operations=(f"G05:{index}",)))
    planned, _, _, _, actual = _plan_and_generate(NoModel(), {"G05": rule}, targets,
        original, facts, source, tmp_path, max_compose_calls=0, obligations=ledger)
    expected = text.replace(delimiter + "调低赎回费率", "").replace("并报中国证监会备案", "")
    assert actual.by_location("p0").text == expected
    assert actual.by_location("p1").text == decoy
    assert targets[0].quote == delimiter + "调低赎回费率"
    assert all(row["status"] == "planned" for row in planned["ledger"])
    replay = replay_claims(planned["edits"], original, actual, rules_by_id={"G05": rule},
                          facts=facts, obligations=ledger,
                          targets_by_id={t.target_id: t.as_dict() for t in targets})
    assert replay["verified"], replay["failures"]
    assert all(item["state"] in {"PASS", "NOT_APPLICABLE"}
               for item in replay["obligations"].values())
