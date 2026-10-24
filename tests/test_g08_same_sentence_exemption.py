"""G08 full policy consumes its own same-sentence exemption once (FL-D217)."""
import json
from pathlib import Path

import pytest

from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import RecallError, Target, _g08_fee_clause_start, plan_target
from fundlex.recall_pipeline import _plan_and_generate
from test_g15_payment_delay_boundary import NoModel, _write
from test_recall_core import _facts

RATE = "A 类基金份额的申购费率由基金管理人决定，并在招募说明书中列示。"
EXEMPT = "本基金 C 类基金份额不收取申购费，"
CALC = "申购份额按净值计算，保留到小数点后2位。"


def rule():
    guide = json.loads((Path(__file__).resolve().parents[1]/"guides/builtin_guide_v1.json").read_text())
    return next(g for g in guide["groups"] if g["rule_id"] == "G08")


def test_actual_docx_full_sentence_policy_once_and_old_artifact_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    source = tmp_path/"source.docx"
    lead = "申购份额的计算详见招募说明书。"
    original = _write(source, [lead + EXEMPT + RATE + CALC])
    g, facts = rule(), _facts()
    target = Target("T", "G08", "p0", RATE, "needs_edit", "inventory",
        start=len(lead+EXEMPT), end=len(lead+EXEMPT+RATE), resolution="resolved", operations=("G08:0",))
    ledger = compile_obligations({"groups": [g]})
    apply_facts(ledger, facts)
    planned, _, _, _, actual = _plan_and_generate(NoModel(), {"G08": g}, [target], original,
        facts, source, tmp_path, max_compose_calls=0, obligations=ledger)
    expected = g["operations"][0]["new_text"]
    assert actual.by_location("p0").text == lead + expected + CALC
    proof = replay_claims(planned["edits"], original, actual, rules_by_id={"G08": g}, facts=facts,
        obligations=ledger, targets_by_id={target.target_id: target.as_dict()})
    assert proof["verified"], proof["failures"]
    old_target = {**target.as_dict(), "start": len(lead+EXEMPT), "quote": RATE}
    old_edit = {**planned["edits"][0], "start": len(lead+EXEMPT), "components": [],
                "expected_old_text": RATE}
    old_actual = _write(tmp_path/"old.docx", [lead + EXEMPT + expected + CALC])
    rejected = replay_claims([old_edit], original, old_actual, rules_by_id={"G08": g}, facts=facts,
        obligations=ledger, targets_by_id={"T": old_target})
    assert not rejected["verified"]
    assert any(f["code"] == "CLAIM_DUPLICATE_EFFECT" for f in rejected["failures"])


@pytest.mark.parametrize("prefix", [
    EXEMPT.replace("，", "。"),
    "本基金C类基金份额不收取赎回费，",
    "本基金E类基金份额不收取申购费，",
    "本基金C类基金份额不收取认购费，",
    EXEMPT + "费用按原比例计提，",
    "通过其他机构申购的" + EXEMPT,
])
def test_unrelated_or_independent_prefix_is_preserved(tmp_path, monkeypatch, prefix):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    original = _write(tmp_path/"source.docx", [prefix + RATE + CALC])
    target = Target("T", "G08", "p0", RATE, "needs_edit", "inventory", start=len(prefix),
                    end=len(prefix+RATE), resolution="resolved", operations=("G08:0",))
    try:
        edit = plan_target(rule(), target, original, _facts(), NoModel(), compose_budget=[0])
    except RecallError as error:
        # Mixed business clauses may legitimately require compose. Even when
        # blocked by its zero budget they must not gain a larger source span.
        assert str(error) == "RECALL_COMPOSE_BUDGET_EXHAUSTED"
    else:
        assert edit.start == len(prefix)
    assert target.start == len(prefix)


def test_custom_policy_without_exemption_has_no_prefix_authority():
    operation = {"op": "replace", "new_text": "新申购费率由基金管理人决定。"}
    assert _g08_fee_clause_start(EXEMPT+RATE, len(EXEMPT), len(EXEMPT+RATE), operation, _facts()) == len(EXEMPT)
