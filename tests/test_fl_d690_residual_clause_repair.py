"""FL-D690: a claim_residual repair target must delete the complete old effect.

The residual detector anchors on the head sentence of G15's surviving payment
clause (B02 loop-3, p1258: quote 「销售服务费每日计提，按月支付。」 inside the
three-sentence clause).  The fragment span failed operation attribution
(``operation_span_mismatch`` against the full reference text), so the recovery
loop starved and the contract delivered no artifact at all.  Even if planned,
deleting just the fragment would shred the remainder of the clause.

Fix: ``g15_residual_clause_span`` expands the repair span to the complete
clause proven by the shared payment parser; the pipeline's residual-repair
block uses it for G15, and the policy text appended into the same paragraph
(a G16 tail) stays outside the span.
"""
import json
from pathlib import Path

import pytest
from docx import Document

from fundlex.docx import inspect_docx
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations
from fundlex.recall import (RecallError, Target, _selected_operation_indices,
                            g15_residual_clause_span)
from fundlex.recall_pipeline import _plan_and_generate
from test_recall_core import _facts

# Real B02 loop-3 p1258 old region (contract paraphrase of the G15:0 reference).
CLAUSE = ("基金销售服务费每日计提，按月支付。由基金托管人根据与基金管理人核对一致的财务数据，"
          "自动在次月初5个工作日内按照指定的账户路径进行支付，注册登记机构收到后按相关合同规定"
          "支付给基金销售机构等。若遇法定节假日、公休假等，支付日期顺延。")
# G16 policy appended into the same paragraph by the main round (must survive).
APPENDED = ("销售服务费每日计提。（1）直销机构：对于投资者通过直销机构持有的C类基金份额计提的"
            "销售服务费，在投资者赎回C类基金份额或基金合同终止时，随赎回款（或清算款）一并返还"
            "给投资者。")
FRAGMENT = "销售服务费每日计提，按月支付。"


def _rule():
    guide = json.loads((Path(__file__).resolve().parents[1] /
                        "guides/builtin_guide_v1.json").read_text())
    return next(g for g in guide["groups"] if g["rule_id"] == "G15")


class NoModel:
    max_context_chars = 60000

    def call(self, **kwargs):
        raise AssertionError("source-bound deterministic deletion must not call a model")


def _write(path, paragraphs):
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)
    return inspect_docx(path, full=True)


def test_residual_fragment_expands_to_complete_clause():
    start = CLAUSE.index(FRAGMENT)
    expanded = g15_residual_clause_span(CLAUSE, start, start + len(FRAGMENT))
    assert expanded == (CLAUSE, 0, len(CLAUSE))


def test_expansion_stops_before_appended_policy_tail():
    text = CLAUSE + APPENDED
    start = text.index(FRAGMENT)
    expanded = g15_residual_clause_span(text, start, start + len(FRAGMENT))
    assert expanded == (CLAUSE, 0, len(CLAUSE))


def test_expansion_falls_back_when_no_clause_proven():
    # A genuinely unrelated residual keeps the honest narrow span (fallback).
    text = "管理费率由基金管理人确定。详情见招募说明书。"
    assert g15_residual_clause_span(text, 0, 6) is None
    # The delay terminator must match the payment-delay shape exactly.
    text = CLAUSE.replace("支付日期顺延。", "办理时间另行公告。")
    start = text.index(FRAGMENT)
    assert g15_residual_clause_span(text, start, start + len(FRAGMENT)) is None


def test_expanded_span_is_attributed_fragment_is_rejected():
    """Mutation evidence for the original defect: the fragment span dies at
    attribution (loop-3 root cause), the expanded clause span passes."""
    rule = _rule()
    inspection = _write_text(CLAUSE)
    fragment_start = CLAUSE.index(FRAGMENT)
    quote, start, end = g15_residual_clause_span(
        CLAUSE, fragment_start, fragment_start + len(FRAGMENT))
    repair = Target("R031", "G15", "p0", quote, "needs_edit",
                    "claim_residual:RESIDUAL_OLD_TEXT", start=start, end=end,
                    resolution="resolved", operations=("G15:0",))
    assert _selected_operation_indices(rule, repair, inspection, _facts()) == [0]
    fragment = Target("R031", "G15", "p0", FRAGMENT, "needs_edit",
                      "claim_residual:RESIDUAL_OLD_TEXT", start=fragment_start,
                      end=fragment_start + len(FRAGMENT),
                      resolution="resolved", operations=("G15:0",))
    with pytest.raises(RecallError) as excinfo:
        _selected_operation_indices(rule, fragment, inspection, _facts())
    assert excinfo.value.code == "RECALL_TARGET_OPERATION_UNATTRIBUTED"
    assert (excinfo.value.detail or {}).get("reason") == "operation_span_mismatch"


def _write_text(text):
    doc = Document()
    doc.add_paragraph(text)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "source.docx"
        doc.save(path)
        return inspect_docx(path, full=True)


def test_residual_repair_deletes_clause_and_preserves_appended_policy(tmp_path, monkeypatch):
    """End-to-end: the expanded repair span deletes exactly the old clause and
    leaves the policy appended into the same paragraph intact."""
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry")
    source = tmp_path / "source.docx"
    original = _write(source, [CLAUSE + APPENDED, "必须保留的独立条款。"])
    rule, facts = _rule(), _facts()
    ledger = compile_obligations({"groups": [rule]})
    apply_facts(ledger, facts)
    start = (CLAUSE + APPENDED).index(FRAGMENT)
    quote, span_start, span_end = g15_residual_clause_span(
        CLAUSE + APPENDED, start, start + len(FRAGMENT))
    target = Target("R031", "G15", "p0", quote, "needs_edit",
                    "claim_residual:RESIDUAL_OLD_TEXT", start=span_start, end=span_end,
                    resolution="resolved", operations=("G15:0",))
    planned, _, _, _, actual = _plan_and_generate(
        NoModel(), {"G15": rule}, [target], original, facts, source, tmp_path,
        max_compose_calls=0, obligations=ledger)
    assert actual.by_location("p0").text.strip() == APPENDED, \
        actual.by_location("p0").text
    assert actual.by_location("p1").text == original.by_location("p1").text
    proof = replay_claims(
        planned["edits"], original, actual, rules_by_id={"G15": rule},
        facts=facts, obligations=ledger,
        targets_by_id={target.target_id: target.as_dict()})
    assert proof["verified"], proof["failures"]
