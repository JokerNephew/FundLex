"""FL-D585 / B10: a no-site delete closes when an executed replace excised it.

v2 regression shape: the inventory emitted no G13 target row, while G12's
paragraph-wide replacement physically carried the 7-day redemption-fee
sentence away.  The old closure probed only the ORIGINAL document for the
semantic variant and therefore stayed UNPROVEN forever.  The deterministic
excision proof requires: original hit + artifact-wide absence + an executed
replace whose span covered the old policy sentence.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fundlex.generation.effects import evaluate_operation_effect
from fundlex.obligations import compile_obligations


ROOT = Path(__file__).resolve().parents[1]

# B10 p247 (广发招利): G12's wide replacement removes the G13 sentence.
BEFORE = ("5、赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额"
          "时收取。赎回费用归入基金财产的比例依照相关法律法规设定，具体见招募说明书的规定，"
          "未归入基金财产的部分用于支付登记费和其他必要的手续费。其中，"
          "对持续持有期少于7日的投资者收取不低于1.5%的赎回费，并全额计入基金财产。")
AFTER = ("赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额"
         "时收取。赎回费用全额计入基金财产。")
SEVEN_DAY = "其中，对持续持有期少于7日的投资者收取不低于1.5%的赎回费，并全额计入基金财产。"


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{index}", text=text)
                           for index, text in enumerate(texts)]
        self.source_sha256 = "source"

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _record(rule_id: str = "G13"):
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text())
    rule = next(group for group in guide["groups"] if group["rule_id"] == rule_id)
    ledger = compile_obligations({"groups": [rule]})
    record = ledger.records[0]
    record.applicability = SimpleNamespace(status="TRUE")
    return record


def _g12_edit(start: int, end: int) -> dict:
    return {"operation": "replace", "location": "p0", "rule_id": "G12",
            "start": start, "end": end, "replacement": AFTER,
            "operation_keys": ["G12:1"]}


def _span_covering_sentence() -> tuple[int, int]:
    start = BEFORE.index("其中，对持续持有期少于7日")
    return start, start + len(SEVEN_DAY)


def test_replace_excision_proves_no_site_delete():
    record = _record("G13")
    start, end = _span_covering_sentence()
    proof = evaluate_operation_effect(
        record, Inspection([BEFORE]), Inspection([AFTER]),
        [], [_g12_edit(2, len(BEFORE))], None)
    assert proof.state == "PASS"
    assert proof.artifact_status == "VERIFIED_ABSENT"
    assert proof.evidence[0]["proof_kind"] == "semantic_delete_excised_by_replace"
    assert proof.evidence[0]["covering_rule_id"] == "G12"
    assert start >= 0 and end <= len(BEFORE)  # fixture sanity


def test_excision_proof_passes_consumer_gate():
    """Loop-3 integration gap: the final omission review routes through
    ``effect_proof_passed``, whose site-bearing tail rejected the site-free
    excision proof (B10/B14 loop-2 FINAL_OPERATION_UNPROVEN despite replay
    PASS)."""
    from fundlex.generation.effects import effect_proof_passed
    record = _record("G13")
    proof = evaluate_operation_effect(
        record, Inspection([BEFORE]), Inspection([AFTER]),
        [], [_g12_edit(2, len(BEFORE))], None)
    assert effect_proof_passed(proof.as_dict(), operation_id="G13:0",
                               obligation_id=record.obligation_id)


def test_variant_surviving_elsewhere_stays_unproven():
    record = _record("G13")
    artifact = Inspection([AFTER, "其他条款。" + SEVEN_DAY])
    proof = evaluate_operation_effect(
        record, Inspection([BEFORE]), artifact,
        [], [_g12_edit(2, len(BEFORE))], None)
    assert proof.state == "OPEN"
    assert proof.artifact_status == "UNPROVEN"
    assert proof.reason == "semantic_delete_variant_present"


def test_replace_not_covering_sentence_cannot_certify():
    record = _record("G13")
    # The span stops before the 7-day sentence begins.
    proof = evaluate_operation_effect(
        record, Inspection([BEFORE]), Inspection([AFTER]),
        [], [_g12_edit(2, 60)], None)
    assert proof.state == "OPEN"
    assert proof.artifact_status == "UNPROVEN"
    assert proof.reason == "semantic_delete_variant_present"


def test_delete_edit_alone_cannot_certify_replace_excision():
    record = _record("G13")
    delete_edit = {"operation": "delete", "location": "p0", "rule_id": "G15",
                   "start": 2, "end": len(BEFORE), "replacement": "",
                   "operation_keys": ["G15:0"]}
    proof = evaluate_operation_effect(
        record, Inspection([BEFORE]), Inspection([AFTER]),
        [], [delete_edit], None)
    assert proof.state == "OPEN"
    assert proof.reason == "semantic_delete_variant_present"
