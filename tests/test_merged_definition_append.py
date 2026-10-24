"""Append to the class definition before a merged next numbered entry (FL-D218)."""
import json
from pathlib import Path

import pytest

from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import Target, _definition_next_entry_start
from fundlex.recall_pipeline import _plan_and_generate
from test_g15_payment_delay_boundary import NoModel, _write
from test_recall_core import _facts
from tools.evaluation.verify_downloaded_artifacts import _xml_texts

DEFINITION = ("基金份额类别：本基金将基金份额分为A类和C类不同的类别。"
              "收取申购费用、不计提销售服务费的，称为A类基金份额；"
              "不收取申购费用、计提销售服务费的，称为C类基金份额")
NEXT = "发起式基金：指投资者承诺认购并持有一定期限的证券投资基金"


@pytest.mark.parametrize("number", ["55、", "５５、", "（五十五）", "55. "])
@pytest.mark.parametrize("punctuation", ["", "。"])
def test_policy_precedes_next_definition_and_wrong_append_fails_replay(
        tmp_path, monkeypatch, number, punctuation):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    head = DEFINITION + punctuation
    tail = " " + number + NEXT
    source = tmp_path/"source.docx"
    original = _write(source, [head+tail, "下一段原文保持。"])
    guide = json.loads((Path(__file__).resolve().parents[1]/"guides/builtin_guide_v1.json").read_text())
    rule = next(g for g in guide["groups"] if g["rule_id"] == "G01")
    facts = _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    target = Target("T", "G01", "p0", head+tail, "needs_edit", "inventory",
        start=0, end=len(head+tail), resolution="resolved", operations=("G01:0",))
    planned, _, _, _, actual = _plan_and_generate(NoModel(), {"G01": rule}, [target],
        original, facts, source, tmp_path, max_compose_calls=0, obligations=ledger)
    edit = planned["edits"][0]
    assert edit["start"] == edit["end"] == len(head)
    assert actual.by_location("p0").text == head+edit["replacement"]+tail
    assert actual.by_location("p1").text == original.by_location("p1").text
    assert _xml_texts(tmp_path/"redline.docx") == _xml_texts(tmp_path/"final.docx")
    assert _xml_texts(tmp_path/"redline.docx", accept=False) == _xml_texts(source)
    proof = replay_claims(planned["edits"], original, actual, rules_by_id={"G01": rule},
        facts=facts, obligations=ledger, targets_by_id={"T": target.as_dict()})
    assert proof["verified"], proof["failures"]
    wrong = {**edit, "components": [], "start": len(head+tail), "end": len(head+tail)}
    wrong_actual = _write(tmp_path/"wrong.docx", [head+tail+edit["replacement"], "下一段原文保持。"])
    rejected = replay_claims([wrong], original, wrong_actual, rules_by_id={"G01": rule},
        facts=facts, obligations=ledger, targets_by_id={"T": target.as_dict()})
    assert not rejected["verified"]
    assert any(f["code"] == "CLAIM_OPERATION_SPAN_UNAUTHORIZED" for f in rejected["failures"])


@pytest.mark.parametrize("text", [
    DEFINITION,
    "55、发起式基金：指发起式证券投资基金",
    "份额类别：本基金将份额分为A类和C类。55、下段：原文",
    DEFINITION + " 55、没有冒号的普通余文",
    DEFINITION + " 55、在投资者申购时收取费用，称为其他类别。",
])
def test_no_complete_merged_definition_boundary_is_invented(text):
    assert _definition_next_entry_start(text) is None
