"""Artifact claim replay boundary proof (plan §15.3, §24, §49)."""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.generation.claim_replay import replay_claims


class Inspection:
    def __init__(self, texts):
        self.paragraphs = [SimpleNamespace(location=f"p{i}", text=text)
                           for i, text in enumerate(texts)]

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


RULES = {"G01": {"rule_id": "G01", "operations": [
    {"operation_id": "G01:0", "op": "append", "new_text": "新授权句", "condition": {"kind": "none"}}]}}


def _edit():
    return {"rule_id": "G01", "location": "p0", "start": 0, "end": 3,
            "replacement": "新授权句", "components": [], "operation_keys": ["G01:0"]}


def test_replay_proves_the_edit_reached_the_artifact():
    before = Inspection(["授权句。", "后文。"])
    after = Inspection(["新授权句。", "后文。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is True, replay["failures"]
    assert replay["checked"] == 1


def test_replay_rejects_a_change_outside_the_authorized_span():
    before = Inspection(["授权句。", "后文。"])
    after = Inspection(["新授权句。", "后文被改。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is False
    assert any(item["code"] == "CLAIM_OUTSIDE_SPAN_CHANGED"
               for item in replay["failures"])


def test_replay_rejects_a_change_inside_the_paragraph_but_outside_the_span():
    before = Inspection(["授权句。前文。", "后文。"])
    # The writer changed 前文 as well; the span itself is correct.
    after = Inspection(["新授权句。前文被改。", "后文。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is False
    assert any(item["location"] == "p0" and item["code"] == "CLAIM_OUTSIDE_SPAN_CHANGED"
               for item in replay["failures"])


def test_missing_replacement_is_still_reported_after_boundary_passes():
    before = Inspection(["授权句。"])
    after = Inspection(["授权句。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is False
    assert replay["failures"][0]["code"] == "CLAIM_NO_CHANGE_APPLIED"


def test_delete_only_rule_leaves_no_old_sentence_behind():
    from fundlex.generation.claim_replay import check_delete_residuals
    rules = {"G15": {"rule_id": "G15", "operations": [
        {"op": "delete", "old_text": "C类基金份额的销售服务费每日计提，按月支付。"
                                     "C类基金份额的销售服务费使用范围不包括基金募集期间的上述费用。"}]}}
    after = Inspection(["销售服务费每日计提。销售服务费使用范围不包括基金募集期间的上述费用。"])
    failures = check_delete_residuals(rules, after)
    assert failures
    assert failures[0]["code"] == "RESIDUAL_OLD_TEXT"
    assert "使用范围不包括" in failures[0]["quote"]
    clean = Inspection(["销售服务费每日计提。"])
    assert check_delete_residuals(rules, clean) == []


def test_identical_body_and_summary_copy_must_not_diverge():
    text = "C类基金份额的销售服务费每日计提，按月支付。由基金管理人向基金托管人发送划付指令。"
    before = Inspection([text, text])
    after = Inspection(["销售服务费每日计提。", text])
    edit = {"rule_id": "G15", "location": "p0", "start": 0, "end": len(text),
            "replacement": "销售服务费每日计提。", "components": []}
    rules = {"G15": {"rule_id": "G15", "operations": [
        {"op": "delete", "old_text": text, "condition": {"kind": "none"}}]}}
    replay = replay_claims([edit], before, after, rules_by_id=rules,
                           target_rules={"p1": ["G15"]})
    assert replay["verified"] is False
    assert any(item["code"] == "DUPLICATE_SITE_UNEDITED"
               for item in replay["failures"])


def test_residual_check_accepts_a_near_equivalent_new_policy_sentence():
    from fundlex.generation.claim_replay import check_delete_residuals
    rules = {
        "G15": {"rule_id": "G15", "operations": [
            {"op": "delete", "old_text": "若遇法定节假日、公休日等，支付日期顺延。"}]},
        "G16": {"rule_id": "G16", "operations": [
            {"op": "append", "new_text": "若遇法定节假日、公休日或不可抗力等，支付日期顺延。"}]},
    }
    after = Inspection(["若遇法定节假日、公休日等，支付日期顺延。"])
    assert check_delete_residuals(rules, after, edits=[{"location": "p0"}]) == []


def test_added_paragraph_outside_targets_is_rejected():
    before = Inspection(["授权句。", "后文。"])
    after = Inspection(["新授权句。", "后文。", "授权句。"])
    replay = replay_claims([_edit()], before, after, rules_by_id=RULES)
    assert replay["verified"] is False
    assert any(item["code"] == "CLAIM_UNEXPECTED_PARAGRAPH"
               for item in replay["failures"])


def test_duplicate_copy_clone_is_not_blocked_by_a_stale_out_of_scope_target():
    from fundlex.recall import Target, duplicate_copy_targets
    text = "基金销售服务费每日计算，逐月支付。由基金托管人自动划付。"
    span = SimpleNamespace(location="p0", text=text,
                           segments=[SimpleNamespace(start=0, end=len(text))])
    span2 = SimpleNamespace(location="p1", text=text,
                            segments=[SimpleNamespace(start=0, end=len(text))])
    inspection = SimpleNamespace(paragraphs=[span, span2],
                                 by_location=lambda location: {"p0": span, "p1": span2}[location])
    stale = Target("T1", "G16", "p0", "基金销售服务费每日计算，逐月支付。",
                   "needs_edit", "stale", start=0, end=18,
                   operations=("G16:0",), out_of_scope=True)
    source = Target("T2", "G16", "p1", "基金销售服务费每日计算，逐月支付。",
                    "needs_edit", "recovered", start=0, end=18,
                    operations=("G16:0",))
    clones = duplicate_copy_targets([stale, source], {"G16": {}}, inspection)
    assert [(clone.location, clone.rule_id, clone.operations)
            for clone in clones] == [("p0", "G16", ("G16:0",))]


def test_identical_copies_edited_to_different_content_fail():
    before = "基金管理人应当每日计提销售服务费，并按月支付。"
    first = before.replace("每日计提", "按季计提")
    second = before.replace("每日计提", "按年计提")
    before_inspection = Inspection([before, before])
    after_inspection = Inspection([first, second])
    result = replay_claims(
        [{"rule_id": "G15", "location": "p0", "start": 0, "end": len(before),
          "replacement": first},
         {"rule_id": "G15", "location": "p1", "start": 0, "end": len(before),
          "replacement": second}],
        before_inspection, after_inspection,
        rules_by_id={"G15": {"rule_id": "G15", "operations": [
            {"op": "delete", "old_text": "每日计提", "new_text": ""}]}})
    assert result["verified"] is False
    codes = {failure["code"] for failure in result["failures"]}
    assert "DUPLICATE_SITE_DIVERGED" in codes
