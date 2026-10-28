"""FL-D458: an audit verdict proves one site, not the outer obligation only.

The old probe returned an outer PASS/SEMANTIC_VERIFIED while ``site_effects`` kept
``CLAIM_OPERATION_NOT_PLANNED``.  This regression requires a real site proof bound
to artifact hash, operation, location/occurrence and exact quote, and keeps every
other failing site blocking.
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.generation.claim_replay import replay_claims
from fundlex.generation.effects import effect_proof_passed
from fundlex.obligations import compile_obligations
from fundlex.recall import Facts
from fundlex.semantic_evidence import ApprovalBook, approval_from_target

OLD = "申购费用由投资人承担，不列入基金财产。"
NEW = "申购费用由申购基金份额的投资者承担，不列入基金财产。"
EQUIVALENT = "申购基金份额的投资者支付申购费用，该项费用不计入基金财产。"
RULE = {"rule_id": "G99", "title": "申购费用承担",
        "operations": [{"op": "replace", "old_text": OLD, "new_text": NEW,
                        "condition": {"kind": "none"}}]}


class Inspection:
    def __init__(self, texts, sha: str = "source"):
        self.paragraphs = tuple(
            SimpleNamespace(location=f"p{i}", text=text, zone="body",
                            logical_zone="body", section_path="")
            for i, text in enumerate(texts))
        self.source_sha256 = sha

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _facts() -> Facts:
    return Facts("普通开放式基金", "", "", (), False, "", "", "", {}, ())


def _ledger():
    ledger = compile_obligations({"groups": [RULE]})
    for record in ledger.records:
        record.applicability = SimpleNamespace(status="TRUE")
    return ledger


def _target(inspection, *, target_id="T", location="p0", quote=EQUIVALENT,
            state="satisfied") -> dict:
    return {"target_id": target_id, "rule_id": "G99", "location": location,
            "quote": quote, "state": state, "operations": ["G99:0"],
            "start": 0, "end": len(quote), "scope_id": "G99:S:L",
            "approval_id": "A", "occurrence_index": -1}


def _replay(*, before_texts, after_texts, targets, proofs):
    before = Inspection(before_texts)
    after = Inspection(after_texts, sha="artifact-hash")
    first = next(iter(targets.values()))
    approval = approval_from_target("A", SimpleNamespace(**first), before,
                                    guide_id="g", guide_sha256="h")
    return replay_claims(
        [], before, after, rules_by_id={"G99": RULE},
        facts=_facts(), targets_by_id=targets, obligations=_ledger(),
        approvals=ApprovalBook([approval]), audit_proofs=proofs)


def test_audit_verdict_creates_a_real_site_proof_and_closes_the_obligation():
    result = _replay(before_texts=[EQUIVALENT], after_texts=[EQUIVALENT],
                     targets={"T": _target(Inspection([EQUIVALENT]))},
                     proofs={"T": {"verdict": "completed",
                                   "evidence_verified": True}})
    item = result["obligations"]["G99:B1:O1"]
    assert result["verified"] is True and result["failures"] == []
    assert item["state"] == "PASS" and item["artifact_status"] == "SEMANTIC_VERIFIED"
    site = item["site_effects"][0]
    assert site["state"] == "PASS"
    assert site["artifact_status"] == "SEMANTIC_VERIFIED"
    assert site["proof_kind"] == "semantic_audit_site"
    proof = next(evidence for evidence in item["evidence"]
                 if evidence.get("proof_kind") == "semantic_audit_site")
    assert proof["operation_id"] == "G99:0"
    assert proof["obligation_id"] == "G99:B1:O1"
    assert proof["document_sha256"] == "artifact-hash"
    assert proof["evidence_quote"]
    assert effect_proof_passed(item, operation_id="G99:0",
                               obligation_id="G99:B1:O1")


def test_stale_artifact_hash_never_closes_the_site():
    result = _replay(before_texts=[EQUIVALENT], after_texts=[EQUIVALENT],
                     targets={"T": _target(Inspection([EQUIVALENT]))},
                     proofs={"T": {"verdict": "completed",
                                   "evidence_verified": True,
                                   "document_sha256": "stale-artifact"}})
    item = result["obligations"]["G99:B1:O1"]
    assert result["verified"] is False
    assert item["state"] == "FAIL"
    assert item["site_effects"][0]["state"] == "FAIL"


def test_another_failing_site_still_blocks_the_obligation():
    before_texts = [EQUIVALENT, OLD]
    after_texts = [EQUIVALENT, OLD]
    targets = {
        "T0": _target(Inspection(before_texts), target_id="T0", location="p0"),
        "T1": _target(Inspection(before_texts), target_id="T1", location="p1",
                      quote=OLD, state="needs_edit"),
    }
    result = _replay(before_texts=before_texts, after_texts=after_texts,
                     targets=targets,
                     proofs={"T0": {"verdict": "completed",
                                    "evidence_verified": True}})
    item = result["obligations"]["G99:B1:O1"]
    assert result["verified"] is False
    assert item["state"] == "FAIL"
    sites = {site["location"]: site for site in item["site_effects"]}
    assert sites["p0"]["state"] == "PASS"
    assert sites["p1"]["state"] == "FAIL"


def test_proof_for_another_location_or_operation_is_ignored():
    for proof in (
            {"verdict": "completed", "evidence_verified": True,
             "location": "p1"},
            {"verdict": "completed", "evidence_verified": True,
             "operation_id": "G99:1"},
    ):
        result = _replay(before_texts=[EQUIVALENT], after_texts=[EQUIVALENT],
                         targets={"T": _target(Inspection([EQUIVALENT]))},
                         proofs={"T": proof})
        item = result["obligations"]["G99:B1:O1"]
        assert result["verified"] is False
        assert item["state"] == "FAIL"
        assert item["site_effects"][0]["state"] == "FAIL"


def test_audit_evidence_quote_must_exist_at_the_site():
    result = _replay(before_texts=[EQUIVALENT], after_texts=[EQUIVALENT],
                     targets={"T": _target(Inspection([EQUIVALENT]))},
                     proofs={"T": {"verdict": "completed",
                                   "evidence_verified": True,
                                   "evidence_quote": "合同中不存在的句子"}})
    item = result["obligations"]["G99:B1:O1"]
    assert result["verified"] is False
    assert item["state"] == "FAIL"
