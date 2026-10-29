"""Absent delete obligations must close by a deterministic scoped scan."""
from __future__ import annotations

import json
from pathlib import Path

from fundlex.docx import inspect_docx
from fundlex.generation.effects import evaluate_operation_effect
from fundlex.obligations import compile_obligations
from fundlex.recall import absent_delete_coverage, g06_scope_locations

ROOT = Path(__file__).resolve().parents[1]
BATCH = ROOT / "funds_word" / "基金合同第一批"
GUIDE = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text(encoding="utf-8"))


def _ledger(*rule_ids: str):
    groups = [rule for rule in GUIDE["groups"] if rule["rule_id"] in rule_ids]
    return compile_obligations({"groups": groups})


def _by_operation(records):
    return {record.spec.operation_id: record for record in records if record is not None}


def test_a50_absent_g06_closes_as_verified_absent():
    source = BATCH / "广发中证A50交易型开放式指数证券投资基金联接基金合同20261020.docx"
    inspection = inspect_docx(source, full=True)
    ledger = _ledger("G06")
    coverage = absent_delete_coverage({}, [], inspection, None, ledger)
    assert "G06:0" in coverage
    record = ledger.records[0]
    assert record.applicability.status == "TRUE"
    effect = evaluate_operation_effect(
        record, inspection, inspection, [], [], None,
        absent_coverage=coverage["G06:0"])
    assert effect.state == "PASS", effect.as_dict()
    assert effect.artifact_status == "VERIFIED_ABSENT"


def test_hengchang_absent_g13_closes_but_a50_real_g13_does_not():
    hengchang = BATCH / "广发恒昌一年持有期混合型证券投资基金基金合同20261022.docx"
    a50 = BATCH / "广发中证A50交易型开放式指数证券投资基金联接基金合同20261020.docx"
    h_ins = inspect_docx(hengchang, full=True)
    a_ins = inspect_docx(a50, full=True)
    assert "G13:0" in absent_delete_coverage({}, [], h_ins, None, _ledger("G13"))
    # A50 still carries the 7-day fee sentence, so no absence certificate.
    assert "G13:0" not in absent_delete_coverage({}, [], a_ins, None, _ledger("G13"))


def test_value_short_g06_sentence_blocks_absence_coverage():
    source = BATCH / "广发价值优选混合型证券投资基金基金合同.docx"
    inspection = inspect_docx(source, full=True)
    assert g06_scope_locations(inspection)
    assert "G06:0" not in absent_delete_coverage({}, [], inspection, None, _ledger("G06"))


def test_existing_target_blocks_absence_coverage():
    from fundlex.recall import Target

    source = BATCH / "广发中证A50交易型开放式指数证券投资基金联接基金合同20261020.docx"
    inspection = inspect_docx(source, full=True)
    target = Target("T1", "G06", "p128", "stale", "needs_edit", "",
                    operations=("G06:0",))
    assert absent_delete_coverage({}, [target], inspection, None, _ledger("G06")) == {}


def test_hengli_g05_absent_replace_closes_in_its_rule_scope():
    from types import SimpleNamespace

    from fundlex.obligations import apply_facts
    from test_recall_core import _facts

    source = BATCH / "广发弘利3个月滚动持有债券型证券投资基金基金合同.docx"
    inspection = inspect_docx(source, full=True)
    ledger = _ledger("G05")
    apply_facts(ledger, _facts())
    record = next(item for item in ledger.records if item.spec.operation_id == "G05:0")
    assert record.applicability.status == "TRUE"
    # Minimal scope: the class-setup leaf only.  The fee-adjustment wording at
    # p420/p1116 is another section and must not block the no-op certificate.
    scope = {"G05": SimpleNamespace(locations=frozenset(
        {"p154", "p155", "p156", "p157", "p158", "p159"}))}
    coverage = absent_delete_coverage({}, [], inspection, scope, ledger)
    assert "G05:0" in coverage
    assert all(location.startswith("p15") for location
               in coverage["G05:0"]["scanned_locations"])


def test_one_way_y_restriction_does_not_block_mutual_ban_absence():
    from fundlex.generation.effects import evaluate_operation_effect
    from test_recall_core import _facts

    source = BATCH / "广发沪深300指数增强型发起式证券投资基金基金合同.docx"
    inspection = inspect_docx(source, full=True)
    ledger = _ledger("G06")
    coverage = absent_delete_coverage({}, [], inspection, None, ledger)
    assert "G06:0" in coverage
    assert any("Y类" in item for item in
               coverage["G06:0"].get("review_candidates") or ())
    effect = evaluate_operation_effect(
        ledger.records[0], inspection, inspection, [], [], _facts(),
        absent_coverage=coverage["G06:0"])
    assert effect.state == "PASS"
    assert effect.artifact_status == "VERIFIED_ABSENT"
