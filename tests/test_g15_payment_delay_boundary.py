"""G15 delay continuation is part of its payment clause (FL-D206)."""
import json
from pathlib import Path

import pytest
from docx import Document

from fundlex.docx import inspect_docx
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import RecallError, Target, plan_target
from fundlex.recall_pipeline import _plan_and_generate
from test_recall_core import _facts


PAYMENT = ("基金销售服务费每日计提，按月支付。由基金托管人根据与基金管理人核对一致的财务数据，"
           "自动在月初 5 个工作日内，按照指定的账户路径从基金财产中一次性支付给注册登记机构，"
           "由登记机构代付给销售机构。基金管理人无需再出具资金划拨指令。")
DELAY = "若遇法定节假日、公休日等，支付日期顺延。"
CHECK = "费用自动扣划后，管理人应进行核对，如发现数据不符，及时联系托管人协商解决。"


class NoModel:
    max_context_chars = 60000

    def call(self, **kwargs):
        raise AssertionError("source-bound deterministic deletion must not call a model")


def _rule():
    guide = json.loads((Path(__file__).resolve().parents[1] /
                       "guides/builtin_guide_v1.json").read_text())
    return next(g for g in guide["groups"] if g["rule_id"] == "G15")


def _write(path, paragraphs):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)
    return inspect_docx(path, full=True)


def _target(location, quote):
    return Target(location, "G15", location, quote, "needs_edit", "inventory",
                  start=0, end=len(quote), resolution="resolved", operations=("G15:0",))


def test_payment_delay_is_bound_in_raw_offsets_and_both_docx_copies_are_deleted(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    source = tmp_path / "source.docx"
    original = _write(source, [PAYMENT + DELAY + " ", "必须保留的独立条款。", PAYMENT + DELAY + " "])
    rule, facts = _rule(), _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    targets = [_target("p0", PAYMENT + DELAY), _target("p2", PAYMENT)]
    planned, _, _, _, actual = _plan_and_generate(NoModel(), {"G15": rule}, targets,
        original, facts, source, tmp_path, max_compose_calls=0, obligations=ledger)
    assert len(planned["edits"]) == 2
    assert all(e["end"] == len(PAYMENT + DELAY) for e in planned["edits"])
    assert actual.by_location("p0").text.strip() == actual.by_location("p2").text.strip() == ""
    assert actual.by_location("p1").text == original.by_location("p1").text
    assert (tmp_path / "redline.docx").is_file()
    proof = replay_claims(planned["edits"], original, actual, rules_by_id={"G15": rule},
        facts=facts, obligations=ledger, targets_by_id={t.target_id: t.as_dict() for t in targets})
    assert proof["verified"], proof["failures"]


@pytest.mark.parametrize("tail", [
    CHECK + DELAY,
    "若遇法定节假日，管理费支付日期顺延。",
    "若遇法定节假日，赎回款支付日期顺延。",
])
def test_delay_binding_does_not_skip_or_borrow_another_payment_mechanism(tmp_path, monkeypatch, tail):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    original = _write(tmp_path / "source.docx", [PAYMENT + tail])
    target = _target("p0", PAYMENT)
    # A partial variant still requires compose; it must not gain another mechanism.
    with pytest.raises(RecallError, match="RECALL_COMPOSE_BUDGET_EXHAUSTED"):
        plan_target(_rule(), target, original, _facts(), NoModel(), compose_budget=[0])
    assert target.end == len(PAYMENT)
    assert target.quote == PAYMENT


def test_delay_binding_keeps_following_reconciliation_outside_the_target(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    original = _write(tmp_path / "source.docx", [PAYMENT + DELAY + CHECK])
    target = _target("p0", PAYMENT)
    edit = plan_target(_rule(), target, original, _facts(), NoModel(), compose_budget=[0])
    assert edit.replacement == ""
    assert edit.content_source == "bounded_delete"
    assert target.end == len(PAYMENT + DELAY)
    assert original.by_location("p0").text[target.end:] == CHECK


@pytest.mark.parametrize("budget", [0, 1])
def test_deterministic_whole_payment_delete_does_not_consume_compose_budget(tmp_path, monkeypatch, budget):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    original = _write(tmp_path / "source.docx", [PAYMENT + DELAY])
    remaining = [budget]
    edit = plan_target(_rule(), _target("p0", PAYMENT), original, _facts(), NoModel(),
                       compose_budget=remaining)
    assert edit.replacement == ""
    assert edit.end == len(PAYMENT + DELAY)
    assert edit.content_source == "tier1_delete"
    assert remaining == [budget]


def test_custom_g15_delete_without_delay_authorization_cannot_extend(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "legacy")
    original = _write(tmp_path / "source.docx", [PAYMENT + DELAY])
    rule = _rule()
    rule["operations"][0]["old_text"] = PAYMENT
    target = _target("p0", PAYMENT)
    edit = plan_target(rule, target, original, _facts(), NoModel(), compose_budget=[0])
    assert edit.end == len(PAYMENT)
    assert target.end == len(PAYMENT)


def test_overwide_payment_target_keeps_reconciliation_in_both_docx_copies(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    source = tmp_path / "source.docx"
    usage = "销售服务费主要用于支付销售机构佣金。"
    original = _write(source, [PAYMENT + DELAY + CHECK + usage,
                               PAYMENT + DELAY + CHECK + usage])
    targets = [_target("p0", PAYMENT + DELAY + CHECK), _target("p1", PAYMENT + DELAY)]
    rule, facts = _rule(), _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    planned, _, _, _, actual = _plan_and_generate(NoModel(), {"G15": rule}, targets,
        original, facts, source, tmp_path, max_compose_calls=0, obligations=ledger)
    assert len(planned["edits"]) == 2
    assert all(e["end"] == len(PAYMENT + DELAY) for e in planned["edits"])
    assert all(actual.by_location(loc).text == CHECK + usage for loc in ("p0", "p1"))
    proof = replay_claims(planned["edits"], original, actual, rules_by_id={"G15": rule},
        facts=facts, obligations=ledger, targets_by_id={t.target_id: t.as_dict() for t in targets})
    assert proof["verified"], proof["failures"]


def test_partial_paragraph_delete_cannot_borrow_delay_from_another_mechanism(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    quote = PAYMENT + "若遇法定节假日，管理费支付日期顺延。"
    original = _write(tmp_path / "source.docx", [quote + CHECK])
    with pytest.raises(RecallError, match="RECALL_COMPOSE_BUDGET_EXHAUSTED"):
        plan_target(_rule(), _target("p0", quote), original, _facts(), NoModel(), compose_budget=[0])


@pytest.mark.parametrize("tamper", ["reconciliation", "other_mechanism", "extra_policy", "custom_authorization"])
def test_bounded_delete_replay_recomputes_own_scope_instead_of_trusting_evidence(tmp_path, tamper):
    from test_claim_replay_operation_authorization import Inspection
    rule = _rule()
    before = PAYMENT + DELAY
    if tamper == "reconciliation":
        before += CHECK
    elif tamper == "other_mechanism":
        before = PAYMENT + "若遇法定节假日，管理费支付日期顺延。"
    elif tamper == "extra_policy":
        before = PAYMENT + "投资者可以随时免责。" + DELAY
    else:
        rule["operations"][0]["old_text"] = DELAY
    edit = dict(target_id="T", rule_id="G15", location="p0", start=0, end=len(before),
                replacement="", operation="replace", content_source="bounded_delete",
                operation_keys=["G15:0"], expected_old_text=before,
                evidence={"strategy": "g15_payment_clause_delete", "deleted_quote": before})
    proof = replay_claims([edit], Inspection([before]), Inspection([""]), rules_by_id={"G15": rule})
    assert not proof["verified"]
    assert any(f["code"] == "CLAIM_OPERATION_SPAN_UNAUTHORIZED" for f in proof["failures"])


def test_bounded_delete_cannot_remove_unrelated_sentence_between_payment_and_delay(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    quote = PAYMENT + "投资者可以随时免责。" + DELAY
    original = _write(tmp_path / "source.docx", [quote + CHECK])
    with pytest.raises(RecallError, match="RECALL_COMPOSE_BUDGET_EXHAUSTED"):
        plan_target(_rule(), _target("p0", quote), original, _facts(), NoModel(), compose_budget=[0])


@pytest.mark.parametrize("content_source", ["tier1_delete", "whole_paragraph_delete", "composite_delete"])
def test_whole_payment_delete_cannot_self_authorize_extra_source_sentence(content_source):
    from test_claim_replay_operation_authorization import Inspection
    before = PAYMENT + "投资者可以随时免责。" + DELAY
    edit = dict(target_id="T", rule_id="G15", location="p0", start=0, end=len(before),
        replacement="", operation="replace", content_source=content_source,
        operation_keys=["G15:0"], expected_old_text=before,
        evidence={"deleted_paragraph": before})
    proof = replay_claims([edit], Inspection([before]), Inspection([""]),
                          rules_by_id={"G15": _rule()})
    assert not proof["verified"]
    assert any(f["code"] == "CLAIM_OPERATION_SPAN_UNAUTHORIZED" for f in proof["failures"])


def test_whole_paragraph_planner_rejects_unrelated_sentence_in_payment_quote(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    quote = PAYMENT + "投资者可以随时免责。" + DELAY
    original = _write(tmp_path / "source.docx", [quote])
    with pytest.raises(RecallError, match="RECALL_DELETE_SCOPE_UNPROVEN"):
        plan_target(_rule(), _target("p0", quote), original, _facts(), NoModel(), compose_budget=[0])


@pytest.mark.parametrize("extra", ["投资者可以随时免责。", DELAY])
def test_short_payment_operation_does_not_authorize_extra_sentence(extra):
    from fundlex.recall import _g15_payment_source_owned
    operation = dict(op="delete", old_text="C类基金份额的销售服务费每日计提，按月支付。")
    payment = ("基金销售服务费每日计提，逐日累计至每月月末，按月支付，经基金管理人与基金托管人"
               "核对一致后，由基金托管人于次月前5个工作日内从基金财产中一次性划出。")
    assert _g15_payment_source_owned(payment, operation)
    assert not _g15_payment_source_owned(payment + extra, operation)


@pytest.mark.parametrize("lead", [
    "C 类基金份额、E 类基金份额和 F 类基金份额的",
    "C类、E类和F类基金份额的",
])
def test_multiclass_payment_deletes_both_copies_and_keeps_independent_suffix(tmp_path, monkeypatch, lead):
    """FL-D226: class enumeration must not block the complete G15 payment site."""
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    payment = (lead + "销售服务费每日计提，按月支付。由基金管理人向基金托管人发送基金销售服务费"
               "划付指令，经基金托管人复核后于次月前 5 个工作日内从基金财产中一次性划出，"
               "由注册登记机构代收，注册登记机构收到后按相关合同规定支付给基金销售机构等。" + DELAY)
    source = tmp_path / "source.docx"
    original = _write(source, [payment + CHECK, "独立条款。", payment + CHECK])
    rule, facts = _rule(), _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    targets = [_target("p0", payment), _target("p2", payment)]
    plan, _, _, _, actual = _plan_and_generate(NoModel(), {"G15": rule}, targets,
        original, facts, source, tmp_path, max_compose_calls=0, obligations=ledger)
    assert len(plan["edits"]) == 2
    assert actual.by_location("p0").text == actual.by_location("p2").text == CHECK
    assert actual.by_location("p1").text == "独立条款。"
    proof = replay_claims(plan["edits"], original, actual, rules_by_id={"G15": rule},
        facts=facts, obligations=ledger, targets_by_id={t.target_id: t.as_dict() for t in targets})
    assert proof["verified"], proof["failures"]


@pytest.mark.parametrize("lead", [
    "C类基金份额以及投资者持有的F类基金份额的",
    "C类基金份额不收取，F类基金份额的",
    "C类基金份额。F类基金份额的",
])
def test_multiclass_payment_prefix_cannot_hide_other_policy(lead):
    from fundlex.recall import _g15_payment_source_owned
    assert not _g15_payment_source_owned(lead + PAYMENT.removeprefix("基金") + DELAY,
                                         _rule()["operations"][0])


@pytest.mark.parametrize("extra", ["投资者可以随时免责。", CHECK])
def test_multiclass_payment_proof_rejects_extra_sentence(extra):
    from fundlex.recall import _g15_payment_source_owned
    text = "C类基金份额、E类基金份额和F类基金份额的" + PAYMENT.removeprefix("基金")
    operation = _rule()["operations"][0]
    assert _g15_payment_source_owned(text + DELAY, operation)
    assert not _g15_payment_source_owned(text + extra + DELAY, operation)
    assert not _g15_payment_source_owned(text + DELAY + extra, operation)
