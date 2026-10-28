"""A literal guide-sentence miss is not proof that a delete's old meaning is gone."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fundlex.generation.effects import evaluate_operation_effect, effect_proof_passed
from fundlex.obligations import compile_obligations


ROOT = Path(__file__).resolve().parents[1]


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{index}", text=text)
                           for index, text in enumerate(texts)]
        self.source_sha256 = "source"

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _record(rule_id: str):
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text())
    rule = next(group for group in guide["groups"] if group["rule_id"] == rule_id)
    ledger = compile_obligations({"groups": [rule]})
    record = ledger.records[0]
    record.applicability = SimpleNamespace(status="TRUE")
    return record


def _coverage(record, document, *, kind="scoped_site_scan"):
    return {"kind": kind, "operation_id": record.spec.operation_id,
            "obligation_id": record.obligation_id,
            "scanned_locations": ["p0"],
            "document_sha256": document.source_sha256,
            "reason": "test fixture: complete rule scope scan"}


@pytest.mark.parametrize("rule_id,replacement", [
    ("G13", ("持续持有期少于7日", "持有不足7日")),
    ("G13", ("持续持有期少于7日", "持有期不足七日")),
    ("G17", ("主要用于", "用于")),
    ("G17", ("使用范围", "用途")),
])
def test_synonymous_old_meaning_survives_literal_absence(rule_id, replacement):
    record = _record(rule_id)
    old_literal = str(record.spec.old_text)
    old, new = replacement
    assert old in old_literal
    text = old_literal.replace(old, new)
    source = Inspection([text])
    proof = evaluate_operation_effect(record, source, source, [], [], None)
    assert proof.state != "PASS"
    assert proof.artifact_status != "VERIFIED_ABSENT"
    assert proof.failure_code == "EFFECT_SITE_UNPROVEN"
    assert proof.reason == "semantic_delete_variant_present"
    assert proof.evidence[0]["probe_hits"]
    # Supplying coverage must not turn a surviving old meaning into success.
    covered = evaluate_operation_effect(record, source, source, [], [], None,
                                        absent_coverage=_coverage(record, source))
    assert covered.state != "PASS"
    assert covered.reason == "semantic_delete_variant_present"


@pytest.mark.parametrize("rule_id,text", [
    ("G13", "本基金赎回费率由基金管理人根据基金合同约定确定。"),
    ("G17", "本基金销售服务费按前一日基金资产净值的0.40%年费率计提。"),
])
def test_literal_absence_without_coverage_fails_closed(rule_id, text):
    record = _record(rule_id)
    source = Inspection([text])
    proof = evaluate_operation_effect(record, source, source, [], [], None)
    assert proof.state == "OPEN"
    assert proof.artifact_status == "UNPROVEN"
    assert proof.failure_code == "EFFECT_SITE_UNPROVEN"
    assert proof.reason == "document_literal_absent_without_coverage"
    assert not effect_proof_passed(proof.as_dict())
    assert proof.evidence[0]["proof_kind"] == "effect_site_unproven"


@pytest.mark.parametrize("rule_id,text", [
    ("G13", "本基金赎回费率由基金管理人根据基金合同约定确定。"),
    ("G17", "本基金销售服务费按前一日基金资产净值的0.40%年费率计提。"),
])
def test_literal_absence_passes_only_with_explicit_coverage(rule_id, text):
    record = _record(rule_id)
    source = Inspection([text])
    proof = evaluate_operation_effect(
        record, source, source, [], [], None,
        absent_coverage=_coverage(record, source))
    assert proof.state == "PASS"
    assert proof.artifact_status == "VERIFIED_ABSENT"
    assert proof.sites == ()
    assert proof.evidence[0]["proof_kind"] == "document_literal_absent"
    assert proof.evidence[0]["coverage"]["scanned_locations"] == ["p0"]
    assert effect_proof_passed(proof.as_dict())


def test_coverage_must_bind_the_operation_obligation_and_source_hash():
    record = _record("G13")
    source = Inspection(["本基金赎回费率由基金管理人根据基金合同约定确定。"])
    wrong_operation = {**_coverage(record, source), "operation_id": "G13:9"}
    wrong_obligation = {**_coverage(record, source), "obligation_id": "G13:B9:O9"}
    wrong_hash = {**_coverage(record, source), "document_sha256": "other"}
    missing_locations = {**_coverage(record, source), "scanned_locations": []}
    unknown_kind = {**_coverage(record, source), "kind": "model_verdict"}
    for coverage in (wrong_operation, wrong_obligation, wrong_hash,
                     missing_locations, unknown_kind):
        proof = evaluate_operation_effect(record, source, source, [], [], None,
                                          absent_coverage=coverage)
        assert proof.state == "OPEN"
        assert proof.failure_code == "EFFECT_SITE_UNPROVEN"


def test_legacy_document_literal_proof_without_coverage_is_not_a_pass():
    record = _record("G13")
    legacy = {
        "state": "PASS", "artifact_status": "VERIFIED_ABSENT",
        "rule_id": "G13", "operation_id": record.spec.operation_id,
        "obligation_id": record.obligation_id, "sites": [], "edit_ids": [],
        "failure_code": "", "reason": "",
        "evidence": [{"proof_kind": "document_literal_absent",
                      "operation_id": record.spec.operation_id,
                      "obligation_id": record.obligation_id,
                      "searched_literals": [str(record.spec.old_text)],
                      "match_count": 0, "document_sha256": "source"}],
        "site_effects": [],
    }
    assert not effect_proof_passed(legacy)
