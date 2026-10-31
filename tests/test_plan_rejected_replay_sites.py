"""FL-D696: a plan-stage rejected site claim must not gate Claim Replay closure.

A T3/locator candidate the planner deterministically rejected
(``TARGET_SOURCE_MISMATCH``) is a refused claim, not an engine commitment.
Claim Replay previously derived it as a required site anyway; worst-of-sites
aggregation then flipped a completed append obligation to OPEN
(``CLAIM_OPERATION_NOT_PLANNED``) and the delivery gate withheld the contract
(loop-5 B12 G16 p796, with p795/p1270 already planned and completed).

The mechanism fix tags such targets with ``plan_rejected`` in the replay
payload and excludes them from the required site set.  Exclusion to an empty
set keeps the original OPEN semantics — it never fabricates a closure.
"""
from docx import Document

from fundlex.docx import inspect_docx
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations

from test_recall_core import _facts

POLICY = ("销售服务费每日计提。对于持续持有期限超过一年的基金份额，持有超过一年后"
          "继续计提的销售服务费，在投资者赎回基金份额时返还。")
APPEND_SITE = "销售服务费主要用于支付销售机构佣金、基金的营销费用以及基金份额持有人服务费等。"
WRONG_CLAIM = "销售服务费每日计提，按月支付。"

GUIDE = {"groups": [{
    "rule_id": "G16", "title": "service fee tail", "section_hint": "基金费用与税收",
    "requirement": "append policy",
    "operations": [{"op": "append", "new_text": POLICY, "condition": {"kind": "none"}}],
    "old_text_variants": [],
}]}


def _ledger():
    ledger = compile_obligations(GUIDE)
    apply_facts(ledger, _facts())
    return ledger


def _inspect(tmp_path, name, texts):
    path = tmp_path / (name + ".docx")
    document = Document()
    for text in texts:
        document.add_paragraph(text)
    document.save(path)
    return inspect_docx(path, full=True)


def _edit(location: str, before_text: str) -> dict:
    end = len(before_text)
    return {"target_id": "T-ok", "rule_id": "G16", "location": location,
            "start": end, "end": end, "replacement": POLICY,
            "operation": "append", "operation_keys": ["G16:0"],
            "components": [{"target_id": "T-ok", "rule_id": "G16", "location": location,
                            "start": end, "end": end, "replacement": POLICY,
                            "operation": "append", "operation_keys": ["G16:0"]}]}


def _target(target_id: str, location: str, quote: str, *, rejected: bool = False) -> dict:
    record = {"target_id": target_id, "rule_id": "G16", "location": location,
              "quote": quote, "state": "needs_edit", "reason": "locator",
              "start": 0, "end": len(quote), "resolution": "resolved",
              "segment_ok": True, "composite": [], "operations": ["G16:0"],
              "claimed_operations": [], "attribution_error": "",
              "site_candidates": [], "occurrence_index": -1, "occurrence_anchor": "",
              "out_of_scope": False, "scope_id": "", "approval_id": ""}
    if rejected:
        record["plan_rejected"] = "TARGET_SOURCE_MISMATCH"
    return record


def _replay(tmp_path, targets_by_id, edits, before_texts, after_texts):
    before = _inspect(tmp_path, "before", before_texts)
    after = _inspect(tmp_path, "after", after_texts)
    return replay_claims(edits, before, after,
                         rules_by_id={"G16": GUIDE["groups"][0]},
                         targets_by_id=targets_by_id, obligations=_ledger(),
                         facts=_facts())


def test_replay_payload_tags_only_code_set_site_rejections():
    from fundlex.recall import Target
    from fundlex.recall_pipeline import _replay_targets_by_id
    targets = [
        Target("T1", "G16", "p1", WRONG_CLAIM, "needs_edit", "locator",
               operations=("G16:0",)),
        Target("T2", "G16", "p0", APPEND_SITE, "needs_edit", "survey",
               operations=("G16:0",)),
        Target("T3", "G16", "p2", APPEND_SITE, "needs_edit", "survey",
               operations=("G16:0",)),
    ]
    planned = {"ledger": [
        {"target_id": "T1", "status": "unresolved", "reason": "TARGET_SOURCE_MISMATCH"},
        {"target_id": "T2", "status": "unresolved", "reason": "RECALL_MODEL_ERROR"},
        {"target_id": "T3", "status": "planned"},
    ]}
    payload = _replay_targets_by_id(targets, planned)
    assert payload["T1"].get("plan_rejected") == "TARGET_SOURCE_MISMATCH"
    assert "plan_rejected" not in payload["T2"]  # model failures are not site rejections
    assert "plan_rejected" not in payload["T3"]


def test_plan_rejected_site_claim_does_not_block_completed_append(tmp_path):
    edits = [_edit("p0", APPEND_SITE)]
    targets = {
        "T-ok": _target("T-ok", "p0", APPEND_SITE),
        "T-rej": _target("T-rej", "p1", WRONG_CLAIM, rejected=True),
    }
    result = _replay(tmp_path, targets, edits,
                     [APPEND_SITE, WRONG_CLAIM], [APPEND_SITE + POLICY, WRONG_CLAIM])
    assert result["verified"], result["failures"]
    assert all(effect.get("state") == "PASS"
               for effect in result["obligations"].values()), result["obligations"]


def test_mutation_untagged_rejected_claim_still_fails_replay(tmp_path):
    """Without the tag the same refused claim must keep the old OPEN behaviour."""
    edits = [_edit("p0", APPEND_SITE)]
    targets = {
        "T-ok": _target("T-ok", "p0", APPEND_SITE),
        "T-rej": _target("T-rej", "p1", WRONG_CLAIM),
    }
    result = _replay(tmp_path, targets, edits,
                     [APPEND_SITE, WRONG_CLAIM], [APPEND_SITE + POLICY, WRONG_CLAIM])
    assert result["verified"] is False
    assert any(failure.get("code") == "CLAIM_OPERATION_NOT_PLANNED"
               and failure.get("location") == "p1"
               for failure in result["failures"]), result["failures"]


def test_exclusion_to_empty_site_set_stays_fail_closed(tmp_path):
    """Excluding the only claim must not invent a closure: OPEN, not PASS."""
    targets = {"T-rej": _target("T-rej", "p0", WRONG_CLAIM, rejected=True)}
    result = _replay(tmp_path, targets, [], [WRONG_CLAIM], [WRONG_CLAIM])
    assert result["verified"] is False
    assert any(effect.get("state") in {"OPEN", "UNRESOLVED", "FAIL"}
               for effect in result["obligations"].values()), result["obligations"]
