"""CLAIM_DUPLICATE_EFFECT is scoped to one operation and one authorized site."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import compile_obligations


POLICY = "本基金销售服务费每日计提，逐日累计至每月月末，按月支付。"
OPS = [{"operation_id": "G99:0", "op": "append", "new_text": POLICY,
        "condition": {"kind": "none"}, "group_kind": "INDEPENDENT"}]


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{index}", text=text)
                           for index, text in enumerate(texts)]
        self.source_sha256 = "source"

    def by_location(self, location):
        return next(span for span in self.paragraphs if span.location == location)


def _ledger(rule, operations=None):
    ledger = compile_obligations({"groups": [{**rule,
                                             "operations": operations or rule["operations"]}]})
    for record in ledger.records:
        record.applicability = SimpleNamespace(status="TRUE")
    return ledger


def _rule(operations=None):
    return {"rule_id": "G99", "title": "scope fixture",
            "operations": operations or OPS, "old_text_variants": []}


def _edit(location, start, replacement, target_id):
    return {"rule_id": "G99", "target_id": target_id, "location": location,
            "start": start, "end": start, "replacement": replacement,
            "operation": "insert", "content_source": "tier1_template",
            "operation_keys": ["G99:0"],
            "evidence": {"operation_keys": ["G99:0"]}}


def _target(location, source, target_id, occurrence=-1, operations=("G99:0",)):
    return {"target_id": target_id, "rule_id": "G99", "location": location,
            "quote": source, "state": "needs_edit",
            "occurrence_index": occurrence, "operations": list(operations)}


def _replay(rule, before_texts, after_texts, edits, targets, ledger):
    return replay_claims(edits, Inspection(before_texts), Inspection(after_texts),
                         rules_by_id={"G99": rule}, facts=None, obligations=ledger,
                         targets_by_id={item["target_id"]: item for item in targets})


def _duplicate_codes(result):
    return [item for item in result["failures"]
            if item["code"] == "CLAIM_DUPLICATE_EFFECT"]


def test_two_category_sites_at_one_location_may_each_write_the_policy_once():
    rule = _rule()
    ledger = _ledger(rule)
    source = "A类基金份额的销售服务费按0.40%计提。C类基金份额的销售服务费按0.20%计提。"
    edits = [_edit("p0", len(source), POLICY, "T1"),
             _edit("p0", len(source), POLICY, "T2")]
    targets = [_target("p0", source, "T1", occurrence=0),
               _target("p0", source, "T2", occurrence=1)]
    result = _replay(rule, [source], [source + POLICY + POLICY], edits, targets, ledger)
    assert not _duplicate_codes(result)


def test_two_insertions_at_one_site_are_duplicate():
    rule = _rule()
    ledger = _ledger(rule)
    source = "A类基金份额的销售服务费按0.40%计提。"
    edits = [_edit("p0", len(source), POLICY + POLICY, "T1")]
    targets = [_target("p0", source, "T1", occurrence=0)]
    result = _replay(rule, [source], [source + POLICY + POLICY], edits, targets, ledger)
    assert _duplicate_codes(result)
    proof = result["obligations"][ledger.records[0].obligation_id]
    assert proof["state"] == "FAIL"
    assert proof["failure_code"] == "CLAIM_DUPLICATE_EFFECT"


def test_body_and_summary_copies_at_different_locations_are_not_duplicate():
    rule = _rule()
    ledger = _ledger(rule)
    body = "A类基金份额的销售服务费按0.40%计提。"
    summary = "C类基金份额的销售服务费按0.20%计提。"
    edits = [_edit("p0", len(body), POLICY, "T1"),
             _edit("p1", len(summary), POLICY, "T2")]
    targets = [_target("p0", body, "T1", occurrence=0),
               _target("p1", summary, "T2", occurrence=0)]
    result = _replay(rule, [body, summary], [body + POLICY, summary + POLICY],
                     edits, targets, ledger)
    assert not _duplicate_codes(result)


def test_one_of_alternatives_writing_the_same_policy_twice_are_duplicate():
    operations = [
        {"operation_id": "G99:0", "op": "replace", "old_text": "旧政策甲。",
         "new_text": POLICY, "condition": {"kind": "none"},
         "group_kind": "ONE_OF", "one_of_group": "ALT"},
        {"operation_id": "G99:1", "op": "replace", "old_text": "旧政策乙。",
         "new_text": POLICY, "condition": {"kind": "none"},
         "group_kind": "ONE_OF", "one_of_group": "ALT"},
    ]
    rule = _rule(operations)
    ledger = _ledger(rule, operations)
    source = "旧政策甲。旧政策乙。"
    edits = [{"rule_id": "G99", "target_id": "T1", "location": "p0",
              "start": 0, "end": len("旧政策甲。"), "replacement": POLICY,
              "operation": "replace", "content_source": "tier1_template",
              "operation_keys": ["G99:0"], "evidence": {"operation_keys": ["G99:0"]}},
             {"rule_id": "G99", "target_id": "T2", "location": "p0",
              "start": len("旧政策甲。"), "end": len(source), "replacement": POLICY,
              "operation": "replace", "content_source": "tier1_template",
              "operation_keys": ["G99:1"], "evidence": {"operation_keys": ["G99:1"]}}]
    targets = [_target("p0", source, "T1", occurrence=0, operations=("G99:0",)),
               _target("p0", source, "T2", occurrence=1, operations=("G99:1",))]
    result = _replay(rule, [source], [POLICY + POLICY], edits, targets, ledger)
    assert _duplicate_codes(result)
    assert {proof["state"] for proof in result["obligations"].values()} == {"FAIL"}
    assert {proof["failure_code"] for proof in result["obligations"].values()} == {
        "CLAIM_DUPLICATE_EFFECT"}
