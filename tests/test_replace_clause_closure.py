"""Multi-sentence replacement closure found in real dev-05 DOCX review (FL-D205)."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from fundlex.docx import inspect_docx
from fundlex.generation.claim_replay import replay_claims
from fundlex.generation.effects import evaluate_operation_effect
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import Target, plan_target, resolve_quote
from test_recall_core import _facts


BEARER = "赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
RATIO = "赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示"
SHORT = "对于持续持有期少于 7 日的投资者收取不低于 1.5%的赎回费，并将上述赎回费全额计入基金财产。"
NEW = BEARER + "赎回费用全额计入基金财产。"
TAIL = "赎回金额计算结果按四舍五入方法保留到小数点后2位。"


def rules():
    guide = json.loads((Path(__file__).resolve().parents[1] /
                       "guides/builtin_guide_v1.json").read_text())
    return {rule["rule_id"]: rule for rule in guide["groups"]
            if rule["rule_id"] in {"G12", "G13"}}


def inspect_text(tmp_path, name, text):
    path = tmp_path / (name + ".docx")
    document = Document()
    document.add_paragraph(text)
    document.save(path)
    return inspect_docx(path, full=True)


@pytest.mark.parametrize("terminal", ["。", "；", ";"])
def test_full_quote_binding_keeps_policy_clause_and_excludes_sibling(tmp_path, terminal):
    source = inspect_text(tmp_path, "source", BEARER + RATIO + terminal + SHORT + TAIL)
    span = source.by_location("p0")
    bound = resolve_quote(span, BEARER + RATIO + "。")
    assert bound == (0, len(BEARER + RATIO + terminal))
    assert SHORT not in span.text[bound[0]:bound[1]]


@pytest.mark.parametrize("keep_old", [True, False])
@pytest.mark.parametrize("sibling_removed", [True, False])
def test_actual_docx_claim_checks_replaced_policy_and_sibling_separately(
        tmp_path, keep_old, sibling_removed):
    original = inspect_text(tmp_path, "source", BEARER + RATIO + "；" + SHORT + TAIL)
    actual = inspect_text(tmp_path, "actual", NEW + (RATIO + "；" if keep_old else "") +
                          ("" if sibling_removed else SHORT) + TAIL)
    by_id = rules()
    ledger = compile_obligations({"groups": list(by_id.values())})
    apply_facts(ledger, _facts())
    ratio_end = len(BEARER + RATIO + "；")
    targets = {
        "T12": Target("T12", "G12", "p0", BEARER + RATIO + "。", "needs_edit", "source",
            start=0, end=len(BEARER) if keep_old else ratio_end,
            resolution="resolved", segment_ok=True, operations=("G12:0",)).as_dict(),
        "T13": Target("T13", "G13", "p0", SHORT, "needs_edit", "source",
            start=ratio_end, end=ratio_end + len(SHORT),
            resolution="resolved", segment_ok=True, operations=("G13:0",)).as_dict(),
    }
    edits = [dict(rule_id="G12", target_id="T12", location="p0", start=0,
        end=targets["T12"]["end"], replacement=NEW, operation="replace",
        content_source="composed", operation_keys=["G12:0"],
        evidence={"fixed_text": NEW})]
    if sibling_removed:
        edits.append(dict(rule_id="G13", target_id="T13", location="p0",
            start=ratio_end, end=ratio_end + len(SHORT), replacement="",
            operation="replace", content_source="composed_delete", operation_keys=["G13:0"]))
    for edit in edits:
        edit["components"] = [{**edit, "expected_old_text": original.by_location("p0").text[
            edit["start"]:edit["end"]]}]
    replay = replay_claims(edits, original, actual, rules_by_id=by_id,
                          targets_by_id=targets, obligations=ledger, facts=_facts())
    if keep_old:
        assert replay["verified"] is False
        assert any(failure.get("operation_id") == "G12:0" and
                   failure["code"] == "RESIDUAL_OLD_TEXT" for failure in replay["failures"])
    elif not sibling_removed:
        assert replay["verified"] is False
        assert any(failure.get("operation_id") == "G13:0" for failure in replay["failures"])
    else:
        assert replay["verified"], replay["failures"]
    assert actual.by_location("p0").text.endswith(TAIL)


def test_validated_unit_cannot_certify_old_policy_residual(tmp_path):
    by_id = rules()
    record = compile_obligations({"groups": [by_id["G12"]]}).record("G12:0")
    record.applicability = SimpleNamespace(status="TRUE")
    original = inspect_text(tmp_path, "source", BEARER + RATIO + "；" + TAIL)
    actual = inspect_text(tmp_path, "actual", NEW + RATIO + "；" + TAIL)
    edit = dict(rule_id="G12", target_id="T12", location="p0", start=0,
                end=len(BEARER), replacement=NEW, operation_keys=["G12:0"])
    proof = evaluate_operation_effect(record, original, actual,
        [{"location": "p0", "quote": BEARER + RATIO + "。"}], [edit], _facts(),
        validated_units=[dict(location="p0", target_id="T12", operation_id="G12:0", verdict="PASS")])
    assert proof.state == "FAIL"
    assert proof.failure_code == "RESIDUAL_OLD_TEXT"


def test_routed_planner_replaces_both_bound_sentences_without_consuming_sibling(tmp_path):
    source = inspect_text(tmp_path, "source", BEARER + RATIO + "；" + SHORT + TAIL)
    rule = rules()["G12"]
    span = source.by_location("p0")
    start, end = resolve_quote(span, BEARER + RATIO + "。")
    target = Target("T12", "G12", "p0", BEARER + RATIO + "。", "needs_edit", "source",
                    start=start, end=end, resolution="resolved", segment_ok=True,
                    operations=("G12:0",))
    class Gateway:
        def call(self, **kwargs):
            return SimpleNamespace(value={"replacement": NEW, "preserved": [],
                                          "basis": "replace fee attribution clause"})
    edit = plan_target(rule, target, source, _facts(), Gateway(), compose_budget=[1])
    after = span.text[:edit.start] + edit.replacement + span.text[edit.end:]
    assert after == NEW + SHORT + TAIL
    assert edit.operation_keys == ("G12:0",)


def test_g12_bounded_replacement_accepts_explicit_ratio(tmp_path):
    """A source-specific G12 ratio is owned by G12 and replaces its full old span."""
    from fundlex.generation.claim_replay import replay_claims

    rule = rules()["G12"]
    source_text = (BEARER + "不低于赎回费总额的25%应归基金财产，其余用于支付登记费和其他必要的手续费。"
                   + "对于持续持有期少于 7 日的投资者收取不低于 1.5%的赎回费，并将上述赎回费全额计入基金财产。")
    source = inspect_text(tmp_path, "ratio-source", source_text)
    target = Target("T12-ratio", "G12", "p0", source_text, "needs_edit", "source",
                    start=0, end=len(source_text), resolution="resolved", segment_ok=True,
                    operations=("G12:1",))

    class NoModel:
        max_context_chars = 60000
        def call(self, **kwargs):
            raise AssertionError("bounded G12 replacement must not call a model")

    edit = plan_target(rule, target, source, _facts(), NoModel(), compose_budget=[0])
    assert edit.content_source == "bounded_replace"
    assert edit.replacement == NEW
    assert edit.end == len(BEARER + "不低于赎回费总额的25%应归基金财产，其余用于支付登记费和其他必要的手续费。")
    actual = inspect_text(tmp_path, "ratio-actual", edit.replacement + source_text[edit.end:])
    proof = replay_claims([edit.as_dict()], source, actual, rules_by_id={"G12": rule},
                          facts=_facts(), targets_by_id={target.target_id: target.as_dict()})
    assert proof["verified"], proof["failures"]


def test_g12_g13_atomic_plan_uses_separate_bounded_components(tmp_path, monkeypatch):
    from fundlex.recall import plan_edits
    monkeypatch.setenv("FUNDLEX_STRATEGY_MODE", "registry")
    ratio = BEARER + "不低于赎回费总额的25%应归基金财产，其余用于支付登记费和其他必要的手续费。"
    text = ratio + SHORT + TAIL
    source = inspect_text(tmp_path, "atomic-source", text)
    targets = [Target("T12", "G12", "p0", text, "needs_edit", "source",
                      start=0, end=len(text), resolution="resolved", segment_ok=True,
                      operations=("G12:1",)),
               Target("T13", "G13", "p0", SHORT + TAIL, "needs_edit", "source",
                      start=len(ratio), end=len(text), resolution="resolved", segment_ok=True,
                      operations=("G13:0",))]
    by_id = rules()
    ledger = compile_obligations({"groups": list(by_id.values())})
    apply_facts(ledger, _facts())
    plan = plan_edits(by_id, targets, source, _facts(), None,
                      max_compose_calls=0, obligations=ledger)
    edits = plan["edits"]
    assert not plan["conflicts"]
    assert all(item["status"] == "planned" for item in plan["ledger"])
    assert len(edits) == 1
    edit = edits[0]
    components = edit["components"]
    assert edit["replacement"] == NEW + TAIL
    assert [(c["operation_keys"], c["start"], c["end"]) for c in components] == [
        (["G12:1"], 0, len(ratio)), (["G13:0"], len(ratio), len(ratio + SHORT))]
    actual = inspect_text(tmp_path, "atomic-result", edit["replacement"])
    proof = replay_claims(edits, source, actual,
                          rules_by_id=by_id, facts=_facts(), obligations=ledger,
                          targets_by_id={t.target_id: t.as_dict() for t in targets})
    assert proof["verified"], proof["failures"]
