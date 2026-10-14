from types import SimpleNamespace
import copy

import pytest

from fundlex.artifact_review import _contexts, review_artifacts


ACTION = {"action_id": "R99-A1", "requirements": [{"id": "R99-REQ-1", "kind": "must_state",
           "text": "费用全额归入基金财产"}], "generation": {}, "semantics": {
    "subject": "费用", "action": "修改费用归属", "condition": "适用", "fee_terms": "无",
    "ownership": "基金财产", "allowed_changes": ["修改归属"], "must_preserve": ["其他内容"],
    "forbidden_additions": ["新费率"]}}


def inspection(texts, digest):
    spans = [SimpleNamespace(location=f"p{i}", section_path="费用", logical_zone="body", zone="body", text=text)
             for i, text in enumerate(texts)]
    return SimpleNamespace(source_sha256=digest, paragraphs=spans,
                           by_location=lambda location: next(span for span in spans if span.location == location))


class Reviewer:
    max_context_chars = 12000

    def __init__(self, mutation=None):
        self.mutation = mutation
        self.contexts = []

    def verify_artifact(self, context, **kwargs):
        self.contexts.append(context)
        items = [{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                  "evidence_quote": "费用全额归入基金财产。", "evidence_source": "after"}
                 for identifier in ("R99-REQ-1", "PRESERVATION", "COVERAGE")]
        if self.mutation:
            self.mutation(items)
        return SimpleNamespace(value={"items": items})


def review(gateway):
    return review_artifacts(inspection(["费用部分归入基金财产。", "其他内容。"], "source"),
                            inspection(["费用全额归入基金财产。", "其他内容。"], "final"),
                            [ACTION], [{"action_id": "R99-A1", "location": "p0"}], {}, gateway,
                            plan_sha256="plan", redline_sha256="redline", final_sha256="final", round_number=1)


def test_review_reads_actual_sections_and_binds_exact_artifact_pair():
    gateway = Reviewer()
    result = review(gateway)
    assert result["passed"]
    assert result["plan_sha256"] == "plan" and result["final_sha256"] == "final"
    assert result["redline_sha256"] == "redline" and result["source_sha256"] == "source"
    assert "费用部分归入基金财产。" in gateway.contexts[0]
    assert "费用全额归入基金财产。" in gateway.contexts[0]
    assert "其他内容。" in gateway.contexts[0]
    assert "plan_sha256=plan" in gateway.contexts[0] and "final_sha256=final" in gateway.contexts[0]
    assert result["actions"][0]["windows"][0]["coverage_locations"] == ["p0", "p1"]


@pytest.mark.parametrize("mutation", [
    lambda items: items.pop(),
    lambda items: items.append(dict(items[0])),
    lambda items: items[0].update(evidence_quote="并未存在的文字"),
    lambda items: items[0].update(action_id="R98-A1"),
    lambda items: items[0].update(result="unknown"),
    lambda items: items[0].update(evidence_source="before"),
    lambda items: items[0].update(evidence_source="rule", evidence_quote="费用全额归入基金财产"),
])
def test_review_rejects_missing_duplicate_forged_or_unknown_evidence(mutation):
    result = review(Reviewer(mutation))
    assert not result["passed"]
    assert result["actions"][0]["reason"] == "V3_ARTIFACT_SEMANTIC_REJECTED"


class RepairReviewer(Reviewer):
    """First response omits PRESERVATION/COVERAGE; the bounded repair answers them."""

    def __init__(self):
        super().__init__()
        self.calls = 0

    def verify_artifact(self, context, **kwargs):
        self.calls += 1
        if self.calls == 1:
            items = [{"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
                      "evidence_quote": "费用全额归入基金财产。", "evidence_source": "after"}]
        else:
            items = [{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                      "evidence_quote": "费用全额归入基金财产。", "evidence_source": "after"}
                     for identifier in kwargs.get("requirement_ids") or []]
        return SimpleNamespace(value={"items": items})


def test_review_repairs_missing_checklist_items_once():
    gateway = RepairReviewer()
    result = review(gateway)
    assert result["passed"] and gateway.calls == 2
    window = result["actions"][0]["windows"][0]
    assert window["repair_event"] is not None
    assert {item["requirement_id"] for item in window["items"]} == {"R99-REQ-1", "PRESERVATION", "COVERAGE"}


class StubbornReviewer(Reviewer):
    def verify_artifact(self, context, **kwargs):
        self.contexts.append(context)
        return SimpleNamespace(value={"items": [
            {"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
             "evidence_quote": "费用全额归入基金财产。", "evidence_source": "after"}]})


def test_review_still_fails_closed_when_repair_stays_incomplete():
    result = review(StubbornReviewer())
    assert not result["passed"]
    assert result["actions"][0]["reason"] == "V3_ARTIFACT_SEMANTIC_REJECTED"


def test_review_contains_model_errors_per_window():
    from fundlex.model import ModelError

    class ErrorReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            raise ModelError("MODEL_SCHEMA_INVALID")

    result = review(ErrorReviewer())
    assert not result["passed"]
    assert result["actions"][0]["reason"] == "V3_ARTIFACT_SEMANTIC_REJECTED"
    window = result["actions"][0]["windows"][0]
    assert window["model_error"] == "MODEL_SCHEMA_INVALID"
    assert window["items"] == []


def test_review_model_budget_stop_propagates():
    from fundlex.model import ModelError

    class StopReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            raise ModelError("MODEL_COST_BUDGET_EXCEEDED")

    with pytest.raises(ModelError):
        review(StopReviewer())


def test_contexts_disclose_other_authorized_edits():
    before = inspection(["原文甲。", "原文乙。"], "source")
    after = inspection(["修改后甲。", "原文乙。"], "final")
    windows = _contexts(before, after, ACTION, [{"action_id": "R99-A1", "location": "p0"}], {}, 4000,
                        other_edits=[{"action_id": "R03-A3", "location": "p0", "operation": "delete",
                                      "expected_old_text": "并报中国证监会备案"}])
    assert "OTHER_AUTHORIZED_EDITS" in windows[0]["context"]
    assert "R03-A3" in windows[0]["context"]
    assert "并报中国证监会备案" in windows[0]["context"]


def test_template_exact_accepts_artifact_quote_with_surrounding_text():
    before = inspection(["根据法规，费用部分归入基金财产。特此说明。"], "source")
    after = inspection(["根据法规，费用全额归入基金财产。特此说明。"], "final")
    action = {"action_id": "R99-A1",
              "generation": {"mode": "template", "template_text": "费用全额归入基金财产。"},
              "requirements": [{"id": "R99-REQ-1", "kind": "must_preserve", "text": "固定新文",
                                "check": {"kind": "template_exact"}, "verification": "code"}],
              "semantics": ACTION["semantics"]}

    class TemplateReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            items = [{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                      "evidence_quote": "根据法规，费用全额归入基金财产。特此说明。",
                      "evidence_source": "after"}
                     for identifier in ("R99-REQ-1", "PRESERVATION", "COVERAGE")]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [action], [{"action_id": "R99-A1", "location": "p0"}], {},
                              TemplateReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"]


def test_delete_windows_disclose_exact_deleted_target():
    before = inspection(["费用主要用于支付销售机构佣金。", "其他内容。"], "source")
    after = inspection(["", "其他内容。"], "final")
    action = {"action_id": "R99-A1", "operation": "delete",
              "generation": {"mode": "delete"},
              "requirements": [{"id": "R99-REQ-1", "kind": "must_preserve", "text": "删除目标",
                                "check": {"kind": "delete_only"}, "verification": "code"}],
              "semantics": ACTION["semantics"]}
    captured: list[str] = []

    class DeleteReviewer(Reviewer):
        def verify_artifact(self, context, *, instruction="", **kwargs):
            captured.append(instruction)
            items = [{"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
                      "evidence_quote": "费用主要用于支付销售机构佣金。", "evidence_source": "before"},
                     {"action_id": "R99-A1", "requirement_id": "PRESERVATION", "result": "satisfied",
                      "evidence_quote": "其他内容。", "evidence_source": "after"},
                     {"action_id": "R99-A1", "requirement_id": "COVERAGE", "result": "satisfied",
                      "evidence_quote": "其他内容。", "evidence_source": "after"}]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [action],
                              [{"action_id": "R99-A1", "location": "p0", "operation": "delete",
                                "expected_old_text": "费用主要用于支付销售机构佣金。"}], {},
                              DeleteReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"]
    assert any("被删除目标" in instruction and "支付销售机构佣金" in instruction for instruction in captured)


def test_region_checks_do_not_require_one_quote_to_contain_everything():
    before = inspection(["老文。"], "source")
    after = inspection(["销售服务费每日计提。直销机构返还投资者。其余随赎回款一并返还。"], "final")
    action = {"action_id": "R99-A1", "generation": {},
              "requirements": [{"id": "R99-REQ-1", "kind": "must_state", "text": "关键表述",
                                "check": {"kind": "contains_all",
                                          "values": ["销售服务费每日计提", "随赎回款"]},
                                "verification": "code"}],
              "semantics": ACTION["semantics"]}

    class RegionReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            items = [{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                      "evidence_quote": "销售服务费每日计提。直销机构返还投资者。",
                      "evidence_source": "after"}
                     for identifier in ("R99-REQ-1", "PRESERVATION", "COVERAGE")]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [action], [{"action_id": "R99-A1", "location": "p0"}], {},
                              RegionReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"], "the edited region satisfies the requirement even if the quote omits part"


def test_digit_checks_use_written_text_not_preserved_rates():
    before = inspection(["D类基金份额不收取申购费用，年费率0.4%。"], "source")
    after = inspection(["D类基金份额不收取申购费用，年费率0.4%。"], "final")
    action = {"action_id": "R99-A1", "generation": {},
              "requirements": [{"id": "R99-REQ-1", "kind": "must_state", "text": "改写文字不得含数字",
                                "check": {"kind": "no_digits_and_no_conditions"},
                                "verification": "code"}],
              "semantics": ACTION["semantics"]}

    class WrittenTextReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            items = [{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                      "evidence_quote": "D类基金份额不收取申购费用，年费率0.4%。",
                      "evidence_source": "after"}
                     for identifier in ("R99-REQ-1", "PRESERVATION", "COVERAGE")]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [action],
                              [{"action_id": "R99-A1", "location": "p0", "replacement": "本类份额不收取申购费用。"}], {},
                              WrittenTextReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"], "preserved fee rates in the paragraph must not fail the written-text check"


def test_model_dissent_on_code_provable_item_is_recorded_not_fatal():
    before = inspection(["费用部分归入基金财产。", "其他内容。"], "source")
    after = inspection(["费用全额归入基金财产。", "其他内容。"], "final")
    action = copy.deepcopy(ACTION)
    action["requirements"][0]["check"] = {"kind": "contains_all", "values": ["全额", "基金财产"]}

    class DissentingReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            items = [{"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "unsatisfied",
                      "evidence_quote": "费用全额归入基金财产。", "evidence_source": "after"},
                     *[{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                        "evidence_quote": "其他内容。", "evidence_source": "after"}
                       for identifier in ("PRESERVATION", "COVERAGE")]]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [action], [{"action_id": "R99-A1", "location": "p0"}], {},
                              DissentingReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"], "the artifact provably satisfies the requirement"
    window = result["actions"][0]["windows"][0]
    assert window["model_dissents"] == ["R99-REQ-1"]
    item = next(entry for entry in window["items"] if entry["requirement_id"] == "R99-REQ-1")
    assert item["result"] == "satisfied" and item["model_result"] == "unsatisfied"


def test_preservation_may_cite_before_when_the_text_survives():
    before = inspection(["保留内容。", "其他内容。"], "source")
    after = inspection(["保留内容。", "其他内容。"], "final")

    class BeforePreservationReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            items = [{"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
                      "evidence_quote": "保留内容。", "evidence_source": "after"},
                     {"action_id": "R99-A1", "requirement_id": "PRESERVATION", "result": "satisfied",
                      "evidence_quote": "保留内容。", "evidence_source": "before"},
                     {"action_id": "R99-A1", "requirement_id": "COVERAGE", "result": "satisfied",
                      "evidence_quote": "其他内容。", "evidence_source": "after"}]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [ACTION], [{"action_id": "R99-A1", "location": "p0"}], {},
                              BeforePreservationReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"], "a before-cited quote that still exists in the artifact proves preservation"


def test_coverage_may_cite_the_deleted_target_from_before():
    before = inspection(["销售服务费主要用于支付佣金。", "其他内容。"], "source")
    after = inspection(["", "其他内容。"], "final")
    action = copy.deepcopy(ACTION)
    action["operation"] = "delete"

    class DeletedCoverageReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            items = [{"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
                      "evidence_quote": "销售服务费主要用于支付佣金。", "evidence_source": "before"},
                     {"action_id": "R99-A1", "requirement_id": "PRESERVATION", "result": "satisfied",
                      "evidence_quote": "其他内容。", "evidence_source": "after"},
                     {"action_id": "R99-A1", "requirement_id": "COVERAGE", "result": "satisfied",
                      "evidence_quote": "销售服务费主要用于支付佣金。", "evidence_source": "before"}]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [action],
                              [{"action_id": "R99-A1", "location": "p0", "operation": "delete",
                                "expected_old_text": "销售服务费主要用于支付佣金。"}], {},
                              DeletedCoverageReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"], "coverage evidence may identify the deleted target for a delete action"


def test_model_judged_failure_gets_one_consensus_retry():
    class DisagreeingReviewer(Reviewer):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def verify_artifact(self, context, **kwargs):
            self.calls += 1
            preservation = "unsatisfied" if self.calls == 1 else "satisfied"
            items = [{"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
                      "evidence_quote": "费用全额归入基金财产。", "evidence_source": "after"},
                     {"action_id": "R99-A1", "requirement_id": "PRESERVATION", "result": preservation,
                      "evidence_quote": "其他内容。", "evidence_source": "after"},
                     {"action_id": "R99-A1", "requirement_id": "COVERAGE", "result": "satisfied",
                      "evidence_quote": "其他内容。", "evidence_source": "after"}]
            return SimpleNamespace(value={"items": items})

    gateway = DisagreeingReviewer()
    result = review(gateway)
    assert result["passed"] and gateway.calls == 2
    assert result["actions"][0]["windows"][0]["consensus_event"] is not None


def test_full_sections_are_split_without_truncating_paragraphs():
    before = inspection(["原文" + str(i) + "甲" * 280 for i in range(3)], "source")
    after = inspection(["产物" + str(i) + "乙" * 280 for i in range(3)], "final")
    windows = _contexts(before, after, ACTION, [{"location": "p1"}], {}, 2300)
    assert set(location for window in windows for location in window["locations"]) == {"p0", "p1", "p2"}
    assert all(len(window["context"]) <= 2300 for window in windows)
    assert all(windows[index]["locations"][-1] == windows[index + 1]["locations"][0]
               for index in range(len(windows) - 1))


def test_unbounded_sections_fail_closed():
    before = inspection(["原文" + "甲" * 3000], "source")
    after = inspection(["产物" + "乙" * 3000], "final")
    with pytest.raises(ValueError, match="V3_ARTIFACT_CONTEXT_LIMIT"):
        _contexts(before, after, ACTION, [{"location": "p0"}], {}, 1600)


def test_sections_that_cannot_share_a_boundary_paragraph_fail_closed():
    before = inspection(["原文" + str(i) + "甲" * 280 for i in range(3)], "source")
    after = inspection(["产物" + str(i) + "乙" * 280 for i in range(3)], "final")
    with pytest.raises(ValueError, match="V3_ARTIFACT_WINDOW_BOUNDARY"):
        _contexts(before, after, ACTION, [{"location": "p1"}], {}, 1600)


def test_review_rejects_an_artifact_hash_different_from_actual_file():
    with pytest.raises(ValueError, match="V3_ARTIFACT_HASH_MISMATCH"):
        review_artifacts(inspection(["旧文"], "source"), inspection(["新文"], "actual"),
            [ACTION], [{"action_id": "R99-A1", "location": "p0"}], {}, Reviewer(),
            plan_sha256="plan", redline_sha256="redline", final_sha256="claimed", round_number=1)


def test_satisfied_business_evidence_cannot_be_an_unrelated_after_quote(monkeypatch):
    monkeypatch.setitem(ACTION["requirements"][0], "check",
                        {"kind": "contains_all", "values": ["全额", "基金财产"]})
    assert not review(Reviewer(lambda items: items[0].update(evidence_quote="其他内容。")))["passed"]


@pytest.mark.parametrize("delete_quote,passed", [("费用用途原句。", True), ("保留邻句。", False)])
def test_delete_evidence_must_bind_to_the_actual_deleted_target(delete_quote, passed):
    action = copy.deepcopy(ACTION)
    action["operation"] = "delete"
    action["requirements"][0]["check"] = {"kind": "delete_only"}

    class DeletionReviewer:
        max_context_chars = 12000

        def verify_artifact(self, context, **kwargs):
            return SimpleNamespace(value={"items": [
                {"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
                 "evidence_source": "before", "evidence_quote": delete_quote},
                *[{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                   "evidence_source": "after", "evidence_quote": "保留邻句。"}
                  for identifier in ("PRESERVATION", "COVERAGE")]]})

    result = review_artifacts(inspection(["费用用途原句。", "保留邻句。"], "source"),
        inspection(["", "保留邻句。"], "final"), [action],
        [{"action_id": "R99-A1", "location": "p0", "expected_old_text": "费用用途原句。"}], {},
        DeletionReviewer(), plan_sha256="plan", redline_sha256="redline", final_sha256="final", round_number=1)
    assert result["passed"] is passed


@pytest.mark.parametrize("after_text,passed", [("", True), ("费用用途原句。", False)])
def test_delete_evidence_may_cite_the_artifact_when_the_target_is_gone(after_text, passed):
    action = copy.deepcopy(ACTION)
    action["operation"] = "delete"
    action["requirements"][0]["check"] = {"kind": "delete_only"}

    class DeletionReviewer:
        max_context_chars = 12000

        def verify_artifact(self, context, **kwargs):
            return SimpleNamespace(value={"items": [
                {"action_id": "R99-A1", "requirement_id": "R99-REQ-1", "result": "satisfied",
                 "evidence_source": "after", "evidence_quote": "保留邻句。"},
                *[{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                   "evidence_source": "after", "evidence_quote": "保留邻句。"}
                  for identifier in ("PRESERVATION", "COVERAGE")]]})

    result = review_artifacts(inspection(["费用用途原句。", "保留邻句。"], "source"),
        inspection([after_text, "保留邻句。"], "final"), [action],
        [{"action_id": "R99-A1", "location": "p0", "expected_old_text": "费用用途原句。"}], {},
        DeletionReviewer(), plan_sha256="plan", redline_sha256="redline", final_sha256="final", round_number=1)
    assert result["passed"] is passed


def test_region_digit_checks_ignore_list_numbering():
    before = inspection(["5.赎回费用归基金管理人所有。"], "source")
    after = inspection(["5.赎回费用全额计入基金财产。"], "final")
    action = {"action_id": "R99-A1", "generation": {},
              "requirements": [{"id": "R99-REQ-1", "kind": "must_state", "text": "不含数字与条件",
                                "check": {"kind": "no_digits_and_no_conditions"},
                                "verification": "code"}],
              "semantics": ACTION["semantics"]}

    class RegionReviewer(Reviewer):
        def verify_artifact(self, context, **kwargs):
            items = [{"action_id": "R99-A1", "requirement_id": identifier, "result": "satisfied",
                      "evidence_quote": "5.赎回费用全额计入基金财产。", "evidence_source": "after"}
                     for identifier in ("R99-REQ-1", "PRESERVATION", "COVERAGE")]
            return SimpleNamespace(value={"items": items})

    result = review_artifacts(before, after, [action], [{"action_id": "R99-A1", "location": "p0"}], {},
                              RegionReviewer(), plan_sha256="plan", redline_sha256="redline",
                              final_sha256="final", round_number=1)
    assert result["passed"], "list numbering must not trip the digit check"


def test_windows_without_edits_review_preservation_only():
    before = inspection(["旧文" + "甲" * 300, "其他" + "乙" * 300, "末文" + "丙" * 300], "source")
    after = inspection(["新文" + "甲" * 300, "其他" + "乙" * 300, "末文" + "丙" * 300], "final")

    class WindowReviewer:
        max_context_chars = 2300

        def verify_artifact(self, context, **kwargs):
            locations = context.split("[EDIT_LOCATIONS]\n")[1].split("\n")[0]
            # Edits present: requirements + coverage + preservation.
            # No edits: preservation only (coverage is scoped to edited windows).
            expected = ["R99-REQ-1", "PRESERVATION", "COVERAGE"] if locations else ["PRESERVATION"]
            quote = context.split("[AFTER location=")[1].split("]\n", 1)[1].split("\n")[0]
            return SimpleNamespace(value={"items": [{"action_id": "R99-A1", "requirement_id": identifier,
                "result": "satisfied", "evidence_quote": quote, "evidence_source": "after"}
                for identifier in expected]})

    result = review_artifacts(before, after, [ACTION], [{"action_id": "R99-A1", "location": "p0"}], {},
        WindowReviewer(), plan_sha256="plan", redline_sha256="redline", final_sha256="final", round_number=1)
    assert result["passed"]
    assert any(not window["edit_locations"] for window in result["actions"][0]["windows"])
