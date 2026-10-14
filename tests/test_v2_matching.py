"""Source-bound semantic scope/variant matching; no real model requests."""
from __future__ import annotations

import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from fundlex.docx import generate_artifacts, inspect_docx, validate_edit_plan
from fundlex.model import ModelError
from fundlex.rules_v2 import RuleSetV2, load_ruleset_v2
from fundlex.v2 import plan_v2, resolve_action_scope
from test_v2_engine import ScriptedGateway, build_docx, make_profile


class Gateway(ScriptedGateway):
    def resolve_scope(self, context, **kwargs):
        return self._take("resolve_scope", context)


@pytest.fixture
def package():
    return load_ruleset_v2(path=Path(__file__).resolve().parents[1] / "rules/rules_v2.draft.json")


@pytest.fixture
def profile():
    return make_profile(["A", "C"], ["A"], ["C"])


def execute(tmp_path, package, profile, paragraphs, responses, ids=("R06-A1",)):
    source = build_docx(tmp_path / "source.docx", paragraphs)
    inspection = inspect_docx(source, full=True)
    gateway = Gateway(responses)
    outcome = plan_v2(inspection, profile, package, gateway, engine_build_value="test", actions=ids)
    return outcome, gateway, source, inspection


def found(first, last=None):
    return {"status": "found", "ranges": [{"start_quote": first, "end_quote": last or first,
                                           "basis": "本段说明该业务费用"}]}


def quotes(*values):
    return {"quotes": [{"quote": value, "basis": "对应目标指引"} for value in values]}


def test_deterministic_scope_uses_no_model(tmp_path, package, profile):
    old = package.by_id("R06-A1")["locate"]["old_texts"][0]
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", old)], [])
    assert result["actions"][0]["status"] == "applied"
    assert result["actions"][0]["scope_resolution"]["method"] == "code"
    assert gateway.calls == 0


def test_unknown_subsection_model_resolves_by_original_quote(tmp_path, package, profile):
    old = package.by_id("R06-A1")["locate"]["old_texts"][0]
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"), ("text", "交易费用安排"), ("text", old)],
        [("resolve_scope", found(old))])
    assert result["actions"][0]["status"] == "applied"
    assert result["actions"][0]["scope_resolution"]["ranges"][0]["locations"] == ["p2"]
    assert gateway.calls == 1


@pytest.mark.parametrize("response,reason", [
    (found("其他章节原文"), "V3_SCOPE_QUOTE_UNRESOLVED"),
    ({"status": "absent", "ranges": []}, "TARGET_SCOPE_UNRESOLVED"),
    ({"status": "uncertain", "ranges": []}, "TARGET_SCOPE_UNRESOLVED"),
])
def test_scope_never_guesses_absence_or_outside_sources(tmp_path, package, profile, response, reason):
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"), ("text", "业务费用待确认"),
        ("heading", "投资范围"), ("text", "其他章节原文")], [("resolve_scope", response)])
    assert not result["edits"]
    assert result["actions"][0]["failure_reason"] == reason


def test_missing_upper_chapter_does_not_call_model(tmp_path, package, profile):
    result, gateway, _, _ = execute(tmp_path, package, profile,
        [("heading", "投资范围"), ("text", "申购费率由管理人决定。")], [])
    assert result["actions"][0]["status"] == "not_matched"
    assert gateway.calls == 0


def test_duplicate_scope_quote_rejected(tmp_path, package, profile):
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"), ("text", "费用规定"), ("text", "费用规定")],
        [("resolve_scope", found("费用规定"))])
    assert result["actions"][0]["failure_reason"] == "V3_SCOPE_QUOTE_UNRESOLVED"
    assert not result["edits"]


def test_variant_precise_core_preserves_actual_docx_remainder(tmp_path, package, profile):
    core = "本基金A类份额申购费用由投资者负担，不计入基金财产；C类份额免收申购费用。"
    remainder = "申购费用主要用于市场推广等费用。"
    result, _, source, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", core + remainder)],
        [("locate_target", quotes(core))], ids=("R09-A1",))
    assert result["actions"][0]["status"] == "applied"
    edit = result["edits"][0]
    assert edit["expected_old_text"] == core
    assert edit["replacement"] == package.by_id("R09-A1")["generation"]["template_text"]
    plan = validate_edit_plan(source, result["edits"], {}, content_check=result["content_check"])
    generate_artifacts(source, plan, tmp_path / "redline.docx", tmp_path / "final.docx")
    final = inspect_docx(tmp_path / "final.docx", full=True)
    assert final.by_location("p2").text == edit["replacement"] + remainder


def test_multiple_independent_variant_targets_are_all_retained(tmp_path, package, profile):
    first = "本基金的申购费率由管理人确定，并在招募说明书列示。"
    second = "本基金申购费率由管理人决定，在招募说明书予以列示。"
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", first), ("text", second)],
        [("locate_target", quotes(first)), ("locate_target", quotes(second))])
    assert result["actions"][0]["status"] == "applied"
    assert len(result["edits"]) == 2


def test_one_paragraph_deterministic_and_variant_targets_both_inventoried(tmp_path, package, profile):
    old = package.by_id("R06-A1")["locate"]["old_texts"][0]
    variant = "本基金另一渠道的申购费率由管理人确定，在招募说明书列示。"
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", old + " " + variant)],
        [("locate_target", quotes(variant))])
    assert len(result["edits"]) == 2


@pytest.mark.parametrize("value", [quotes("不存在的原文"), quotes("申购费率由管理人决定。"), {"quotes": []}])
def test_unresolved_variant_rejects_whole_action(tmp_path, package, profile, value):
    repeated = "申购费率由管理人决定。"
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", repeated * 2)],
        [("locate_target", value)])
    assert not result["edits"]
    assert result["actions"][0]["status"] == "failed"


def test_variant_budget_stop_propagates(tmp_path, package, profile):
    class Stopped(Gateway):
        def locate_target(self, context, **kwargs):
            raise ModelError("MODEL_REQUEST_BUDGET_EXCEEDED")
    source = build_docx(tmp_path / "budget.docx", [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", "申购费率由管理人决定。")])
    with pytest.raises(ModelError, match="MODEL_REQUEST_BUDGET_EXCEEDED"):
        plan_v2(inspect_docx(source, full=True), profile, package, Stopped([]),
                engine_build_value="test", actions=["R06-A1"])


def test_overlapping_actions_reject_all_sibling_edits(tmp_path, package, profile):
    first = copy.deepcopy(package.by_id("R06-A1"))
    second = copy.deepcopy(first)
    second["action_id"] = "SECOND"
    scoped = RuleSetV2(package.version, package.sha256, (first, second), package.release_policy)
    old = first["locate"]["old_texts"][0]
    result, _, _, _ = execute(tmp_path, scoped, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", old), ("text", old)],
        [], ids=("R06-A1", "SECOND"))
    assert not result["edits"] and not result["records"]
    assert {a["failure_reason"] for a in result["actions"]} == {"V3_ACTION_RANGE_CONFLICT"}


def test_scope_windows_cover_all_paragraphs_without_truncation(tmp_path, package, profile):
    source = build_docx(tmp_path / "windows.docx", [
        ("heading", "基金份额的申购与赎回"),
        *[("text", f"业务段落{i}：" + "费用说明" * 100) for i in range(5)]])
    action = package.by_id("R06-A1")
    inspection = inspect_docx(source, full=True)
    gateway = Gateway([])
    from fundlex.v2 import _matching_context, _scope_windows
    overhead = len(_matching_context(action, profile, [], gateway))
    gateway.max_context_chars = overhead + 1300
    chapter = list(inspection.paragraphs)
    windows = _scope_windows(action, profile, chapter, gateway)
    assert len(windows) >= 2
    assert {s.location for w in windows for s in w} == {s.location for s in chapter}
    assert all(windows[i][-1].location == windows[i + 1][0].location for i in range(len(windows) - 1))
    assert all(len(_matching_context(action, profile, w, gateway)) <= gateway.max_context_chars for w in windows)


def test_known_and_unlabelled_subsections_in_same_chapter_both_found(tmp_path, package, profile):
    old = package.by_id("R06-A1")["locate"]["old_texts"][0]
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", old),
        ("text", "二、其他渠道交易规则"), ("text", old + "本段说明其他渠道。")],
        [("resolve_scope", found("二、其他渠道交易规则", "本段说明其他渠道。"))])
    assert result["actions"][0]["status"] == "applied"
    assert {edit["location"] for edit in result["edits"]} == {"p2", "p4"}


def test_new_policy_embedded_with_remainder_is_verified_no_change(tmp_path, package, profile):
    policy = package.by_id("R06-A1")["generation"]["template_text"]
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", policy + "另有其他业务说明。")], [])
    assert result["actions"][0]["status"] == "satisfied_no_change"
    assert not result["edits"] and gateway.calls == 0


def test_two_actions_same_paragraph_nonoverlapping_are_both_applied(tmp_path, package, profile):
    first = package.by_id("R06-A1")["locate"]["old_texts"][0]
    second = package.by_id("R07-A1")["locate"]["old_texts"][0]
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"),
        ("text", "申购和赎回的价格、费用及其用途"), ("text", first + " " + second)], [],
        ids=("R06-A1", "R07-A1"))
    assert len(result["edits"]) == 2
    assert {a["status"] for a in result["actions"]} == {"applied"}
    assert gateway.calls == 0


def test_r16_body_and_summary_title_variant_is_atomic(tmp_path, package, profile):
    core = package.by_id("R16-A1")["locate"]["old_texts"][0]
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金的收益与分配"), ("text", "收益分配"),
        ("text", core + "，各类别可供分配利润有所不同。"),
        ("heading", "基金合同内容摘要"), ("heading", "基金收益与分配"),
        ("text", "收益分配"), ("text", core + "，各类别可供分配利润有所不同。")], [], ids=("R16-A1",))
    assert result["actions"][0]["status"] == "applied"
    assert {edit["zone"] for edit in result["edits"]} == {"body", "summary"}
    assert gateway.calls == 0


def test_promotional_action_does_not_rewrite_general_rate_host(tmp_path, package, profile):
    old = package.by_id("R13-A1")["locate"]["old_texts"][0]
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"), ("text", "申购和赎回的价格、费用及其用途"),
        ("text", "基金管理人可以在基金合同约定的范围内调整费率或收费方式。"),
        ("text", old)], [], ids=("R13-A1",))
    assert result["actions"][0]["status"] == "applied"
    assert len(result["edits"]) == 1 and gateway.calls == 0


def test_delete_model_cannot_select_adjacent_holiday_sentence(tmp_path, package, profile):
    host = "销售服务费主要用于支付销售机构佣金和促销费用。"
    wrong = "若遇法定节假日、公休日等，支付日期顺延。"
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金费用与税收"), ("text", "基金销售服务费"), ("text", host + wrong)],
        [("locate_target", quotes(wrong))], ids=("R15-A1",))
    assert not result["edits"]
    assert result["actions"][0]["failure_reason"] == "V3_VARIANT_BUSINESS_CORE_MISMATCH"


def test_delete_variant_rejects_half_sentence_quote(tmp_path, package, profile):
    host = "销售服务费主要用于支付销售机构佣金和促销费用。"
    half = "销售服务费主要用于"
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金费用与税收"), ("text", "基金销售服务费"), ("text", host)],
        [("locate_target", quotes(half))], ids=("R15-A1",))
    assert not result["edits"], "a half-sentence delete would orphan the remainder"
    assert result["actions"][0]["failure_reason"] == "V3_DELETE_SENTENCE_BOUNDARY"


def test_delete_variant_rejects_merged_sentences_quote(tmp_path, package, profile):
    host = "销售服务费主要用于支付销售机构佣金和促销费用。"
    formula = "基金管理人向基金托管人发送划付指令，经复核后支付。"
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金费用与税收"), ("text", "基金销售服务费"), ("text", host + formula)],
        [("locate_target", quotes(host + formula))], ids=("R15-A1",))
    assert not result["edits"], "a merged quote would swallow the non-target payment clause"
    assert result["actions"][0]["failure_reason"] == "V3_DELETE_SENTENCE_MERGED"


def test_delete_variant_accepts_complete_business_sentence(tmp_path, package, profile):
    host = "销售服务费主要用于支付销售机构佣金和促销费用。"
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金费用与税收"), ("text", "基金销售服务费"), ("text", host)],
        [("locate_target", quotes(host))], ids=("R15-A1",))
    assert result["actions"][0]["status"] == "applied"
    assert [edit["replacement"] for edit in result["edits"]] == [""]


def test_r10_positive_substrings_with_contradiction_require_semantic_review(tmp_path, package, profile):
    from test_v2_engine import R10_GOOD
    wrong = "但部分赎回费用归基金管理人所有。"
    text = R10_GOOD + wrong
    action = package.by_id("R10-A1")
    responses = [("locate_target", quotes(R10_GOOD)), ("verify_content", {"items": [
        {"requirement_id": identifier, "result": "unsatisfied", "evidence_quote": wrong,
         "evidence_source": "generated"} for identifier in action["model_verification"]]})]
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"), ("text", "申购和赎回的价格、费用及其用途"),
        ("text", text)], responses, ids=("R10-A1",))
    assert not result["edits"] and result["actions"][0]["status"] == "failed"
    assert gateway.calls == 2


def test_adjacent_actions_rejected_without_discarding_unrelated_action(tmp_path, package, profile):
    first = package.by_id("R06-A1")["locate"]["old_texts"][0]
    second = package.by_id("R07-A1")["locate"]["old_texts"][0]
    unrelated = package.by_id("R13-A1")["locate"]["old_texts"][0]
    result, _, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"), ("text", "申购和赎回的价格、费用及其用途"),
        ("text", first + second), ("text", unrelated)], [], ids=("R06-A1", "R07-A1", "R13-A1"))
    assert {edit["action_id"] for edit in result["edits"]} == {"R13-A1"}
    assert {action["failure_reason"] for action in result["actions"] if action["status"] == "failed"} == {
        "V3_ACTION_RANGE_CONFLICT"}


def test_model_variant_context_limit_does_not_truncate(tmp_path, package, profile):
    action = package.by_id("R06-A1")
    source = build_docx(tmp_path / "long.docx", [
        ("heading", "基金份额的申购与赎回"), ("text", "申购和赎回的价格、费用及其用途"),
        ("text", "申购费率由管理人决定。" + "甲" * 13000)])
    gateway = Gateway([])
    result = plan_v2(inspect_docx(source, full=True), profile, package, gateway,
                     engine_build_value="test", actions=[action["action_id"]])
    assert result["actions"][0]["failure_reason"] == "V3_MATCH_CONTEXT_LIMIT"
    assert gateway.calls == 0 and not result["edits"]


def test_scope_quote_from_different_window_rejected(tmp_path, package, profile):
    from fundlex.v2 import _matching_context
    source = build_docx(tmp_path / "outside-window.docx", [
        ("heading", "基金份额的申购与赎回"),
        *[("text", f"业务条款{i}：" + "甲" * 400) for i in range(4)]])
    action = package.by_id("R06-A1")
    gateway = Gateway([("resolve_scope", found("业务条款3："))] +
                      [("resolve_scope", {"status": "absent", "ranges": []})] * 3)
    gateway.max_context_chars = len(_matching_context(action, profile, [], gateway)) + 1300
    spans, diagnostic = resolve_action_scope(inspect_docx(source, full=True), action, profile, gateway)
    assert "V3_SCOPE_OUTSIDE_WINDOW" in diagnostic["failures"]
    assert not spans


def test_network_scope_and_variant_schemas_accept_source_evidence_fields():
    import httpx
    from fundlex.model import ModelGateway
    responses = [found("原文费用条款"), {"quotes": [{"quote": "原文费用条款", "basis": "对应业务",
                                                  "source": "contract", "evidence_quote": "原文费用条款"}]}]
    requests = []

    def response(request):
        import json
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "test", "choices": [{"message": {
            "content": json.dumps(responses.pop(0), ensure_ascii=False)}}]})

    with ModelGateway(base_url="https://model.invalid/v1", model="test", api_key="test",
                      retries=0, client=httpx.Client(transport=httpx.MockTransport(response))) as gateway:
        scope = gateway.resolve_scope("[CONTRACT_SOURCE]\n原文费用条款", instruction="只定位")
        target = gateway.locate_target("[CONTRACT_SOURCE]\n原文费用条款", instruction="只定位",
                                       prompt_version="v3_locate_v1")
        assert scope.value["status"] == "found"
        assert target.value["quotes"][0]["source"] == "contract"
        assert gateway.calls == 2
        assert requests[0]["messages"][1]["content"].startswith("prompt_version=v3_scope_v1")
        assert requests[1]["messages"][1]["content"].startswith("prompt_version=v3_locate_v1")


def test_network_artifact_schema_supports_actual_source_roles():
    import httpx
    import json
    from fundlex.model import ModelGateway
    values = {"items": [{"action_id": "R06-A1", "requirement_id": "COVERAGE", "result": "unknown",
                         "evidence_quote": "实际原文", "evidence_source": "after"}]}
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": [{"message": {
        "content": json.dumps(values, ensure_ascii=False)}}]}))
    with ModelGateway(base_url="https://model.invalid/v1", model="test", api_key="test", retries=0,
                      client=httpx.Client(transport=transport)) as gateway:
        result = gateway.verify_artifact("[AFTER]\n实际原文", instruction="独立复核")
        assert result.value == values
        assert gateway.events[-1]["task_type"] == "verify_artifact"


def test_variant_candidates_over_bound_refuse_before_model_call(tmp_path, package, profile):
    text = "申购费率由管理人决定，并在招募说明书列示。"
    result, gateway, _, _ = execute(tmp_path, package, profile, [
        ("heading", "基金份额的申购与赎回"), ("text", "申购和赎回的价格、费用及其用途"),
        *[("text", text) for _ in range(9)]], [])
    assert result["actions"][0]["failure_reason"] == "V3_VARIANT_CANDIDATE_LIMIT"
    assert not result["edits"] and gateway.calls == 0
