"""Recall-first pipeline orchestration tests.

The gateway is scripted; no real model calls are made. The synthetic contract and
the scripted task responses are reused from ``test_recall_core``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from fundlex.model import ModelError
from fundlex.recall import ENGINE_ID, ENGINE_VERSION
from fundlex.recall_pipeline import RecallPipelineStop, process_recall_first
from fundlex.recall_prompts import PROMPT_VERSIONS

from test_recall_core import (CLASS_DEFINITION, CONVERSION_CLAUSE, LIQUIDATION_CLAUSE,
                              ScriptedGateway, _facts as _core_facts, build_contract,
                              facts_response, guide_rules, inventory_response, scope_response)

COMPOSE_RESPONSE = {"replacement": "基金管理人可以适当调低基金申购费率和销售服务费率。",
                    "preserved": [], "basis": "scripted compose"}
GUIDE_SHA = "ab" * 32


def guide_document(rules: list[dict] | None = None) -> dict:
    return {"schema_version": "guide-rules-v1", "groups": rules if rules is not None else guide_rules(),
            "document_sha256": GUIDE_SHA,
            "validation": {"errors": [], "warnings": [], "coverage_gaps": []}}


def rules_subset(*rule_ids: str) -> list[dict]:
    """Guide rules for one test path only.

    The deterministic coverage survey searches the whole document for every rule in
    the guide, so tests that script a narrower behaviour restrict the guide to the
    rules under test.
    """
    wanted = set(rule_ids)
    return [rule for rule in guide_rules() if rule["rule_id"] in wanted]


class PipelineGateway(ScriptedGateway):
    """Scripted gateway with the pipeline-facing surface (metrics, checkpoints)."""

    def __init__(self, responses: dict[str, object], *, max_context_chars: int = 60000):
        super().__init__(responses, max_context_chars=max_context_chars)
        self.max_calls = 400
        self.bindings: list[tuple[Path, dict]] = []
        self.contexts: dict[str, list[str]] = {}

    def call(self, **kwargs):
        context = kwargs["bounded_context"]
        assert len(context) <= self.max_context_chars, f"{kwargs['task_type']} context too large"
        self.contexts.setdefault(kwargs["task_type"], []).append(context)
        return super().call(**kwargs)

    def bind_checkpoints(self, directory: Path, dependencies: dict) -> None:
        self.bindings.append((Path(directory), dependencies))

    def metrics(self) -> dict:
        return {"logical_calls": len(self.calls), "http_attempts": len(self.calls),
                "checkpoint_reuses": 0, "checkpoint_invalidations": 0, "prompt_tokens": 0,
                "completion_tokens": 0, "total_tokens": 0, "latency_ms": 0,
                "rate_limit_count": 0, "error_count": 0, "estimated_cost_usd": 0.0, "events": []}


def _audit_sections(context: str) -> tuple[str, str, list[dict]]:
    before = context.split("[BEFORE]\n", 1)[1].split("\n\n[AFTER]", 1)[0]
    after = context.split("[AFTER]\n", 1)[1].split("\n\n[REQUIREMENTS]", 1)[0]
    ledger_text = context.split("[TARGET_LEDGER]\n", 1)[1].split("\n\n[", 1)[0]
    ledger = json.loads(ledger_text)
    return before, after, ledger


def passing_audit(context: str) -> dict:
    """Answer every target in the supplied ledger with a verified completion."""
    ledger_text = context.split("[TARGET_LEDGER]\n", 1)[1].split("\n\n[", 1)[0]
    ledger = json.loads(ledger_text)
    after = context.split("[AFTER]\n", 1)[1].split("\n\n[REQUIREMENTS]", 1)[0]
    quote = ""
    for line in after.splitlines():
        body = line.split("] ", 1)[-1].strip()
        if len(body) >= 12:
            quote = body[:40]
            break
    return {"results": [{"target_id": item["target_id"], "verdict": "completed",
                         "reason": "scripted ok", "evidence_quote": quote}
                        for item in ledger if item.get("target_id")],
            "missed_targets": []}


def _line_quote(region: str) -> str:
    for line in region.splitlines():
        if line.startswith("[") and "] " in line:
            content = line.split("] ", 1)[1].strip()
            if content and content not in {"（该位置内容已删除）", "（该位置无文本）"}:
                return content[:12]
    return ""


def _audit_quote(before: str, after: str) -> str:
    """Prefer AFTER evidence; deletions may only be evidenced from BEFORE."""
    return _line_quote(after) or _line_quote(before)


def completed_audit(context: str) -> dict:
    before, after, ledger = _audit_sections(context)
    quote = _audit_quote(before, after)
    return {"results": [{"target_id": item["target_id"], "verdict": "completed",
                         "reason": "scripted ok", "evidence_quote": quote} for item in ledger],
            "missed_targets": []}


def failing_audit(rule_id: str, times: int = 1) -> object:
    state = {"remaining": times}

    def response(context: str) -> dict:
        before, after, ledger = _audit_sections(context)
        quote = _audit_quote(before, after)
        results = []
        for item in ledger:
            fail = item["rule_id"] == rule_id and state["remaining"] > 0
            if fail:
                state["remaining"] -= 1
            results.append({"target_id": item["target_id"],
                            "verdict": "incomplete" if fail else "completed",
                            "reason": "scripted first-round failure" if fail else "scripted ok",
                            "evidence_quote": quote})
        return {"results": results, "missed_targets": []}

    return response


def persistent_failing_audit(rule_id: str) -> object:
    def response(context: str) -> dict:
        before, after, ledger = _audit_sections(context)
        quote = _audit_quote(before, after)
        results = []
        for item in ledger:
            fail = item["rule_id"] == rule_id
            results.append({"target_id": item["target_id"],
                            "verdict": "incomplete" if fail else "completed",
                            "reason": "scripted persistent failure" if fail else "scripted ok",
                            "evidence_quote": quote})
        return {"results": results, "missed_targets": []}

    return response


def empty_sweep(context: str) -> dict:
    return {"findings": []}


def sweep_finding(rule_id: str, location: str, quote: str, issue: str = "residual_old_text") -> object:
    def response(context: str) -> dict:
        window = context.split("[ARTIFACT_WINDOW]\n", 1)[1]
        if quote in window:
            return {"findings": [{"rule_id": rule_id, "location": location, "quote": quote,
                                  "issue": issue, "reason": "scripted residual clause"}]}
        return {"findings": []}

    return response


def first_sweep_finding(rule_id: str, location: str, quote: str,
                        issue: str = "residual_old_text") -> object:
    """Report a finding on the first sweep, then only while its paragraph still exists."""
    state = {"reported": False}

    def response(context: str) -> dict:
        window = context.rsplit("[ARTIFACT_WINDOW]\n", 1)[-1]
        if f"[{location}]" in window:
            return {"findings": [{"rule_id": rule_id, "location": location, "quote": quote,
                                  "issue": issue, "reason": "scripted first-sweep finding"}]}
        state["reported"] = True
        return {"findings": []}

    return response


def base_responses(**overrides) -> dict[str, object]:
    responses: dict[str, object] = {
        "recall_facts": facts_response,
        "recall_scope": scope_response,
        "recall_inventory": inventory_response,
        "recall_compose": COMPOSE_RESPONSE,
        "recall_audit": completed_audit,
        "recall_sweep": empty_sweep,
    }
    responses.update(overrides)
    return responses


def run(tmp_path: Path, responses: dict | None = None, *, gateway: PipelineGateway | None = None,
        guide: dict | None = None, checkpoint_dir: Path | None = None, **kwargs):
    source = tmp_path / "contract.docx"
    build_contract(source)
    output_dir = tmp_path / "out"
    model = gateway or PipelineGateway(base_responses(**(responses or {})))
    report = process_recall_first(source, output_dir, guide_document=guide or guide_document(),
                                  gateway=model, checkpoint_dir=checkpoint_dir, **kwargs)
    return source, output_dir, model, report


def docx_names(directory: Path) -> set[str]:
    return {path.name for path in directory.glob("*.docx")}


def assert_no_temp_artifacts(directory: Path) -> None:
    assert not list(directory.glob(".recall-*"))


# ---------------------------------------------------------------------------

def test_happy_path_complete_delivery(tmp_path: Path):
    source, output_dir, model, report = run(tmp_path)
    source_sha = hashlib.sha256(source.read_bytes()).hexdigest()

    assert report["delivery_status"] == "complete"
    assert report["schema_version"] == "3"
    assert report["engine_id"] == ENGINE_ID == "recall_first"
    assert report["engine_version"] == ENGINE_VERSION
    assert report["execution_mode"] == "delivery"
    assert report["source_sha256"] == source_sha
    assert report["guide"]["document_sha256"] == GUIDE_SHA
    assert report["guide"]["prompt_versions"] == dict(PROMPT_VERSIONS)
    assert report["guide"]["groups"] == guide_rules()
    assert report["qualification"]["status"] == "eligible"
    assert report["facts"]["fund_type"] == "open_regular"
    assert report["scope_mapping"]["coverage"]
    assert len(report["windows"]) == 1
    assert report["windows"][0]["rounds"][0]["round"] == 0
    assert all("coverage" in entry for entry in report["scope_mapping"]["coverage"])
    assert report["targets"] and all("status" in target for target in report["targets"])
    assert report["plan"]["count"] > 0 and report["plan"]["sha256"]
    assert report["plan"]["conflicts"] == []
    assert len(report["audit"]["rounds"]) == 1 and report["audit"]["issues"] == []
    assert report["sweep"]["chunks"] >= 1 and report["sweep"]["findings"] == []
    assert report["sweep"]["gaps"] == []
    assert report["unresolved"] == []
    assert report["errors"] == []
    assert report["duration_ms"] >= 0
    assert report["edit_plan"] == report["plan"]
    assert report["model"]["logical_calls"] > 0

    assert report["artifacts"] == {"final": "final.docx", "redline": "redline.docx"}
    assert report["output_validation"]["kind"] == "recall_validated_edits"
    assert "actual_content_verification" in report["output_validation"]["checks"]
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}
    assert (output_dir / "report.md").exists() and (output_dir / "edits.json").exists()
    edits_payload = json.loads((output_dir / "edits.json").read_text(encoding="utf-8"))
    assert edits_payload["plan"]["count"] == report["plan"]["count"]
    assert "交付状态" in (output_dir / "report.md").read_text(encoding="utf-8")
    assert_no_temp_artifacts(output_dir)

    from docx import Document
    final_text = "\n".join(paragraph.text for paragraph in Document(output_dir / "final.docx").paragraphs)
    assert "调低销售服务费率" in final_text and CONVERSION_CLAUSE not in final_text


def test_audit_failure_repaired_then_complete(tmp_path: Path):
    _, output_dir, gateway, report = run(
        tmp_path, {"recall_audit": failing_audit("G05", times=1)})

    assert report["delivery_status"] == "complete"
    assert len(report["audit"]["rounds"]) == 2
    assert report["audit"]["rounds"][0]["issues"], "round 0 must record the scripted failure"
    assert report["audit"]["issues"] == []
    assert any("[REPAIR_CONTEXT]" in context for context in gateway.contexts["recall_inventory"])
    assert report["limits"]["business_rounds_used"] == 1
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}


def test_audit_failure_persists_incomplete_working_pair(tmp_path: Path):
    _, output_dir, _, report = run(
        tmp_path, {"recall_audit": persistent_failing_audit("G05")})

    assert report["delivery_status"] == "incomplete"
    assert report["limits"]["business_rounds_used"] == 3
    assert len(report["audit"]["rounds"]) == 4
    assert report["audit"]["issues"]
    assert report["output_validation"]["kind"] == "recall_working_edits"
    assert report["artifacts"] == {"working_final": "working_final.docx",
                                   "working_redline": "working_redline.docx"}
    assert docx_names(output_dir) == {"working_final.docx", "working_redline.docx"}
    assert any(item["kind"] == "audit" for item in report["unresolved"])
    assert_no_temp_artifacts(output_dir)


def test_sweep_finding_repaired_then_complete(tmp_path: Path):
    def repair_aware_inventory(context: str) -> dict:
        value = inventory_response(context)
        if not isinstance(value, dict) or "targets" not in value:
            return value
        value = dict(value)
        if "[REPAIR_CONTEXT]" not in context:
            # The first inventory misses G06 on purpose: the final sweep must report
            # it and the repair round must recover the target.
            value["targets"] = [target for target in value["targets"]
                                if target.get("rule_id") != "G06"]
        return value

    _, output_dir, gateway, report = run(
        tmp_path,
        {"recall_inventory": repair_aware_inventory,
         "recall_audit": passing_audit,
         "recall_sweep": first_sweep_finding("G06", "p8", CONVERSION_CLAUSE)},
        guide=guide_document(rules_subset("G05", "G06")))

    assert report["delivery_status"] == "complete"
    # The deterministic coverage survey usually recovers this target before the sweep;
    # when the sweep does report it, the repair round must resolve it and the run must
    # still complete with no pending/unresolved finding left behind.
    findings = report["sweep"]["findings"]
    assert all(finding["status"] == "resolved" for finding in findings)
    assert not [item for item in report["unresolved"] if item["kind"] == "sweep"]
    assert report["sweep"]["gaps"] == []
    assert len(report["sweep"]["rounds"]) >= 1
    assert any("[REPAIR_CONTEXT]" in context for context in gateway.contexts["recall_inventory"]) \
        or report["survey"]
    assert report["limits"]["business_rounds_used"] <= 1
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}

    from docx import Document
    final_text = "\n".join(paragraph.text for paragraph in Document(output_dir / "final.docx").paragraphs)
    assert CONVERSION_CLAUSE not in final_text


def test_sweep_filters_finding_when_rule_already_carried_out(tmp_path: Path):
    """A sweep finding is dropped when the artifact already carries the rule out."""
    def satisfied_sweep(context: str) -> dict:
        window = context.rsplit("[ARTIFACT_WINDOW]\n", 1)[-1]
        if "[p7]" in window:
            return {"findings": [{"rule_id": "G05", "location": "p7",
                                  "quote": "并报中国证监会备案",
                                  "issue": "residual_old_text",
                                  "reason": "scripted false positive"}]}
        return {"findings": []}

    _, output_dir, _, report = run(tmp_path, {"recall_sweep": satisfied_sweep})

    assert report["delivery_status"] == "complete"
    assert report["sweep"]["findings"] == []
    residue = [item for item in report["unresolved"] if item["kind"] == "sweep"]
    assert residue == []
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}


def test_sweep_filters_class_substitution_rule_that_needs_no_change(tmp_path: Path):
    """A class-substitution finding is dropped when the product's classes already match.

    G02/G04 ask to regroup the share classes with the guide's example letters (A类、B类).
    For a product that only has A and C, the instantiated replacement equals the reference,
    so the clause is already correct and the sweep finding is noise, not a real gap
    (FL-D052).
    """
    substitution = {
        "rule_id": "G02", "title": "释义-基金份额类别定义", "section_hint": "释义",
        "requirement": "按产品实际类别对份额类别描述分组替换。",
        "operations": [
            {"op": "replace", "old_text": "A类基金份额", "new_text": "A类、B类基金份额",
             "condition": {"kind": "none", "value": None}},
            {"op": "replace", "old_text": "C类基金份额", "new_text": "C类、D类基金份额",
             "condition": {"kind": "none", "value": None}},
        ],
        "old_text_variants": [], "slot_tokens": ["A类、B类基金份额", "C类、D类基金份额"],
        "class_substitution": True, "references": [], "source_paragraphs": [0, 4],
    }

    def two_class_facts(context: str) -> dict:
        value = facts_response(context)
        value["classes"] = [item for item in value["classes"] if item["name"] in {"A", "C"}]
        return value

    definition_quote = "在投资者认购、申购基金时收取认购、申购费用而不计提销售服务费的，称为A类基金份额"
    finding = sweep_finding("G02", "p4", definition_quote, issue="unaddressed_requirement")

    _, output_dir, _, report = run(tmp_path, {"recall_facts": two_class_facts,
                                              "recall_sweep": finding},
                                   guide=guide_document([*rules_subset("G05", "G14"), substitution]))

    assert report["sweep"]["findings"] == []
    dropped = [item for round_ledger in report["sweep"]["rounds"]
               for item in round_ledger["dropped"]]
    assert any(item["code"] == "SWEEP_ALREADY_SATISFIED" and item.get("rule_id") == "G02"
               for item in dropped)
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}


def test_sweep_filters_finding_outside_rule_section(tmp_path: Path):
    """A sweep finding at a paragraph outside the rule's mapped section is noise.

    The sweep searches by section hint and can report a rule in an unrelated clause
    (G22's liquidation requirement against the fee-adjustment paragraph); the mapped
    section decides whether the location can possibly be this rule's target (FL-D052).
    """
    def out_of_scope_sweep(context: str) -> dict:
        window = context.rsplit("[ARTIFACT_WINDOW]\n", 1)[-1]
        if "[p7]" in window:
            # A real sentence of p7's fee-adjustment clause that survives the G05 edit,
            # wrongfully reported as G22's liquidation requirement. G22 maps to the
            # liquidation section, so p7 cannot be its target.
            return {"findings": [{"rule_id": "G22", "location": "p7",
                                  "quote": "变更现有基金份额类别的申购费率",
                                  "issue": "unaddressed_requirement",
                                  "reason": "scripted out-of-scope"}]}
        return {"findings": []}

    _, output_dir, _, report = run(tmp_path, {"recall_sweep": out_of_scope_sweep})

    assert report["delivery_status"] == "complete"
    dropped = [item for round_ledger in report["sweep"]["rounds"]
               for item in round_ledger["dropped"]]
    assert any(item["code"] == "SWEEP_LOCATION_OUT_OF_SCOPE" for item in dropped)
    assert report["sweep"]["findings"] == []
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}


def test_excluded_fund_type_report(tmp_path: Path):
    def etf_facts(context: str) -> dict:
        value = facts_response(context)
        value["fund_type"] = {"value": "etf", "quote": "某某灵活配置混合型证券投资基金基金合同",
                              "basis": "scripted etf"}
        return value

    _, output_dir, gateway, report = run(tmp_path, {"recall_facts": etf_facts})

    assert report["delivery_status"] == "excluded"
    assert report["qualification"]["status"] == "excluded_by_fund_type"
    assert report["qualification"]["fund_type"] == "etf"
    assert report["qualification"]["fund_type_quote_verified"] is True
    assert "etf" in report["qualification"]["excluded_types"]
    assert report["facts"]["fund_type"] == "etf"
    assert report["artifacts"] == {} and report["output_validation"]["kind"] is None
    assert docx_names(output_dir) == set()
    assert [task for task, _ in gateway.calls] == ["recall_facts"]
    assert (output_dir / "report.md").exists()
    assert_no_temp_artifacts(output_dir)


def test_excluded_types_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FUNDLEX_RECALL_EXCLUDED_TYPES", "reits, qdii")

    def etf_facts(context: str) -> dict:
        value = facts_response(context)
        value["fund_type"] = {"value": "etf", "quote": "某某灵活配置混合型证券投资基金基金合同",
                              "basis": "scripted etf"}
        return value

    _, output_dir, _, report = run(tmp_path, {"recall_facts": etf_facts})

    assert report["delivery_status"] == "complete"
    assert report["qualification"]["status"] == "eligible"
    assert report["qualification"]["excluded_types"] == ["reits", "qdii"]
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}


def test_zero_edit_already_satisfied_unchanged(tmp_path: Path):
    def satisfied_inventory(context: str) -> dict:
        if CLASS_DEFINITION not in context:
            return {"targets": []}
        return {"targets": [
            {"rule_id": "G01", "location": "p4", "quote": CLASS_DEFINITION,
             "state": "satisfied", "reason": "scripted already satisfied"},
            {"rule_id": "G22", "location": "p17", "quote": LIQUIDATION_CLAUSE,
             "state": "absent", "reason": "scripted not applicable"},
        ]}

    source, output_dir, gateway, report = run(
        tmp_path, {"recall_inventory": satisfied_inventory},
        guide=guide_document(rules_subset("G01", "G22")))

    assert report["delivery_status"] == "complete"
    assert report["plan"]["count"] == 0
    assert report["output_validation"]["kind"] == "recall_validated_unchanged"
    assert "zero_edit" in report["output_validation"]["checks"]
    assert report["artifacts"] == {"final": "final.docx", "redline": "redline.docx"}
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}
    assert (output_dir / "final.docx").read_bytes() == source.read_bytes()
    assert "recall_audit" not in gateway.contexts
    assert report["scope_mapping"]["no_target_rules"] == []
    assert any(target["state"] == "absent" for target in report["windows"][0]["targets"])
    assert_no_temp_artifacts(output_dir)


def test_stop_code_during_facts_raises(tmp_path: Path):
    def stop_facts(context: str) -> dict:
        raise ModelError("MODEL_CALL_BUDGET_EXCEEDED")

    source = tmp_path / "contract.docx"
    build_contract(source)
    output_dir = tmp_path / "out"
    gateway = PipelineGateway(base_responses(recall_facts=stop_facts))
    with pytest.raises(RecallPipelineStop) as excinfo:
        process_recall_first(source, output_dir, guide_document=guide_document(), gateway=gateway)
    assert excinfo.value.code == "MODEL_CALL_BUDGET_EXCEEDED"
    assert docx_names(output_dir) == set()
    assert_no_temp_artifacts(output_dir)


def test_stop_code_during_audit_raises_and_cleans_temp(tmp_path: Path):
    def stop_audit(context: str) -> dict:
        raise ModelError("MODEL_HTTP_ERROR")

    source = tmp_path / "contract.docx"
    build_contract(source)
    output_dir = tmp_path / "out"
    gateway = PipelineGateway(base_responses(recall_audit=stop_audit))
    with pytest.raises(RecallPipelineStop) as excinfo:
        process_recall_first(source, output_dir, guide_document=guide_document(), gateway=gateway)
    assert excinfo.value.code == "MODEL_HTTP_ERROR"
    assert docx_names(output_dir) == set()
    assert_no_temp_artifacts(output_dir)


def test_tampered_plan_not_generated(tmp_path: Path):
    import fundlex.recall_pipeline as pipeline

    original = pipeline.build_docx_edits

    def tamper(planned, inspection):
        edits = original(planned, inspection)
        if edits:
            edits[0]["expected_old_text"] = "被篡改的旧文"
        return edits

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(pipeline, "build_docx_edits", tamper)
    try:
        _, output_dir, _, report = run(tmp_path)
    finally:
        monkeypatch.undo()

    assert report["delivery_status"] == "incomplete"
    assert report["artifacts"].get("working_final") == "working_final.docx"
    assert "final" not in report["artifacts"]
    assert any(item.get("reason") == "RECALL_EDIT_CONTENT_UNVERIFIED"
               for item in report["unresolved"])
    assert "working_final.docx" in docx_names(output_dir)
    assert_no_temp_artifacts(output_dir)


def test_unsupported_target_operation_not_generated(tmp_path: Path):
    """A target whose clause cannot be resolved by any operation refuses to guess.

    The survey finds the real liquidation clause, but the guide operation belongs to a
    different rule, so the plan cannot carry it out: the run must report an unresolved
    target and deliver nothing rather than editing around it.
    """

    def mismatched_inventory(context: str) -> dict:
        if CONVERSION_CLAUSE not in context:
            return {"targets": []}
        return {"targets": [{"rule_id": "G22", "location": "p8", "quote": CONVERSION_CLAUSE,
                             "state": "needs_edit", "reason": "scripted operation mismatch"}]}

    def unrelated_rule(context: str) -> dict:
        value = inventory_response(context)
        if LIQUIDATION_CLAUSE in context:
            return {"targets": [{"rule_id": "G22", "location": "p17", "quote": LIQUIDATION_CLAUSE,
                                 "state": "needs_edit", "reason": "scripted real target"}]}
        return {"targets": []}

    _, output_dir, _, report = run(tmp_path, {"recall_inventory": unrelated_rule},
                                   guide=guide_document([
                                       {"rule_id": "G22", "title": "清算分配-仅删除",
                                        "requirement": "删除清算分配句",
                                        "operations": [{"op": "delete",
                                                        "old_text": "这一段在合同中并不存在。",
                                                        "condition": {"kind": "none", "value": None}}],
                                        "old_text_variants": [], "slot_tokens": [],
                                        "class_substitution": False, "references": [],
                                        "source_paragraphs": [101]}]))

    assert report["delivery_status"] == "not_generated"
    assert report["plan"]["count"] == 0
    assert any(item["kind"] == "target" for item in report["unresolved"])
    # A mismatched reference now routes through the compose path; the scripted gateway has
    # no compose answer, so the target stays unresolved rather than being edited blindly.
    assert report["unresolved"][0]["reason"] in {"RECALL_TARGET_VARIANT_UNMATCHED",
                                                 "RECALL_COMPOSE_FIXED_TEXT_MISSING",
                                                 "RECALL_COMPOSE_DELETE_ADDED_TEXT",
                                                 "RECALL_COMPOSE_DELETE_NOT_SHRINKING",
                                                 "RECALL_COMPOSE_EMPTY"}
    assert docx_names(output_dir) == set()
    assert report["artifacts"] == {}
    assert_no_temp_artifacts(output_dir)


def test_sweep_chunk_limit_recorded_as_coverage_gap(tmp_path: Path):
    _, output_dir, _, report = run(tmp_path, max_sweep_chunks=0)

    assert report["sweep"]["chunks"] == 0
    gaps = report["sweep"]["gaps"]
    assert len(gaps) == 1 and gaps[0]["code"] == "SWEEP_CHUNK_LIMIT"
    assert report["delivery_status"] == "incomplete"
    assert report["output_validation"]["kind"] == "recall_working_edits"
    assert docx_names(output_dir) == {"working_final.docx", "working_redline.docx"}
    assert any(item["kind"] == "coverage" for item in report["unresolved"])


def test_sweep_chunk_budget_subtracts_facts_block(tmp_path: Path):
    """A long contract must not fail closed when the facts block fills the context.

    The sweep context is requirements + facts + window; the window budget has to leave
    room for all three, otherwise long contracts hit MODEL_CONTEXT_LIMIT and the run
    aborts without producing a file.
    """
    from fundlex.recall_pipeline import _sweep_chunk_chars

    class _Model:
        max_context_chars = 12000

    requirements = "R" * 3000
    facts_text = "F" * 5000
    budget = _sweep_chunk_chars(_Model(), requirements, facts_text)
    assert 1500 <= budget
    assert budget + len(requirements) + len(facts_text) + 200 <= 12000
    # Without the facts block the budget is larger; the subtraction is real.
    assert _sweep_chunk_chars(_Model(), requirements, "") > budget


def test_sweep_context_limit_when_rules_and_facts_fill_context(tmp_path: Path):
    from fundlex.recall import RecallError
    from fundlex.recall_pipeline import _sweep_chunk_chars

    class _Model:
        max_context_chars = 12000

    with pytest.raises(RecallError) as error:
        _sweep_chunk_chars(_Model(), "R" * 6000, "F" * 6000)
    assert error.value.code == "RECALL_SWEEP_CONTEXT_LIMIT"


def test_audit_missed_target_triggers_repair(tmp_path: Path):
    state = {"missed_sent": False}

    def audit_with_missed(context: str) -> dict:
        before, after, ledger = _audit_sections(context)
        quote = _audit_quote(before, after)
        results = [{"target_id": item["target_id"], "verdict": "completed", "reason": "scripted ok",
                    "evidence_quote": quote} for item in ledger]
        missed = []
        if not state["missed_sent"] and any(item["rule_id"] == "G01" for item in ledger):
            state["missed_sent"] = True
            missed = [{"rule_id": "G01", "location": "p4", "quote": CLASS_DEFINITION,
                       "reason": "scripted missed target"}]
        return {"results": results, "missed_targets": missed}

    _, output_dir, gateway, report = run(tmp_path, {"recall_audit": audit_with_missed})

    assert report["delivery_status"] == "complete"
    assert len(report["audit"]["rounds"]) == 2
    assert report["audit"]["rounds"][0]["missed_targets"]
    assert report["audit"]["issues"] == []
    assert report["limits"]["business_rounds_used"] == 1
    assert any("复核另报未登记目标" in context for context in gateway.contexts["recall_inventory"])
    assert docx_names(output_dir) == {"final.docx", "redline.docx"}


def test_audit_evidence_unverified_blocks_complete(tmp_path: Path):
    def hallucinating_audit(context: str) -> dict:
        _, _, ledger = _audit_sections(context)
        return {"results": [{"target_id": item["target_id"], "verdict": "completed",
                             "reason": "scripted without a real quote",
                             "evidence_quote": "不存在的证据引文"}
                            for item in ledger], "missed_targets": []}

    _, output_dir, _, report = run(tmp_path, {"recall_audit": hallucinating_audit})

    assert report["delivery_status"] == "incomplete"
    assert any(item["kind"] == "audit" and item["code"] == "AUDIT_NOT_COMPLETED"
               for item in report["unresolved"])
    dropped = [item for round_ledger in report["audit"]["rounds"]
               for item in round_ledger["dropped"]]
    assert any(item["code"] == "AUDIT_EVIDENCE_UNVERIFIED" for item in dropped)
    assert docx_names(output_dir) == {"working_final.docx", "working_redline.docx"}


def test_unresolved_inventory_target_is_rebound_cross_paragraph(tmp_path: Path):
    """A faithful quote that runs across a paragraph break must still become an edit.

    The windowed inventory resolves a quote against one paragraph, so the
    sales-service-fee payment clause (head closes one paragraph, tail opens the next)
    lands as ``quote_not_found`` and the planner would stop with
    ``RECALL_TARGET_UNRESOLVED``. The pipeline re-binds it deterministically (FL-D052).
    """
    from docx import Document

    from fundlex.docx import inspect_docx
    from fundlex.recall import Target
    from fundlex.recall_pipeline import _rebind_unresolved_targets

    path = tmp_path / "cross.docx"
    document = Document()
    document.add_paragraph("C 类基金份额的基金销售服务费每日计算，逐日累计至每月月末，按月支付，")
    document.add_paragraph("由基金管理人与基金托管人核对一致后按上述方式支付。")
    document.save(path)
    inspection = inspect_docx(path, full=True)
    quote = ("C 类基金份额的基金销售服务费每日计算，逐日累计至每月月末，按月支付，"
             "由基金管理人与基金托管人核对一致后按上述方式支付。")
    target = Target(target_id="W#1:T013", rule_id="G15", location="p0", quote=quote,
                    state="needs_edit", reason="删除支付句")
    target.resolution = "quote_not_found"
    origins: dict[str, str] = {}
    records = _rebind_unresolved_targets([target], origins, inspection,
                                         rules_by_id={rule["rule_id"]: rule for rule in guide_rules()},
                                         facts=_core_facts())
    assert target.resolution == "composite"
    assert [part.rsplit(":", 2)[0] for part in target.composite] == ["p0", "p1"]
    assert records and records[0]["source"] == "target_quote"
    assert origins["W#1:T013"] == "rebind_target_quote"


def test_rebind_extends_resolved_target_to_clause_continuation(tmp_path: Path):
    """A resolved head fragment grows into the clause's continuation paragraph.

    When the guide's own wording differs from the contract, no reference matches and the
    inventory binds only the first paragraph ("…按月支付，"). The deletion must still cover
    the continuation ("由基金管理人与基金托管人核对一致后…支付日期顺延。"): the target's
    whole-paragraph span ending in a comma marks the next paragraph as its continuation
    (FL-D052).
    """
    from docx import Document

    from fundlex.docx import inspect_docx
    from fundlex.recall import Target
    from fundlex.recall_pipeline import _rebind_unresolved_targets

    path = tmp_path / "head.docx"
    document = Document()
    document.add_paragraph("C 类基金份额的基金销售服务费每日计算，逐日累计至每月月末，按月支付，")
    document.add_paragraph("由基金管理人与基金托管人核对一致后按上述方式支付。")
    document.save(path)
    inspection = inspect_docx(path, full=True)
    head = "C 类基金份额的基金销售服务费每日计算，逐日累计至每月月末，按月支付，"
    target = Target(target_id="W#1:T016", rule_id="G15", location="p0", quote=head,
                    state="needs_edit", reason="删除支付句")
    target.start, target.end = 0, len(head)
    target.segment_ok = True
    target.resolution = "resolved"
    origins: dict[str, str] = {}
    records = _rebind_unresolved_targets([target], origins, inspection,
                                         rules_by_id={rule["rule_id"]: rule for rule in guide_rules()},
                                         facts=_core_facts(), extend_resolved=True)
    assert target.resolution == "composite"
    assert [part.rsplit(":", 2)[0] for part in target.composite] == ["p0", "p1"]
    assert records and records[0]["source"] == "clause_continuation"
    assert origins["W#1:T016"] == "rebind_clause_continuation"
    # A target that stops mid-paragraph or ends a sentence must be left alone.
    mid = Target(target_id="W#1:T017", rule_id="G15", location="p0", quote="按月支付，",
                 state="needs_edit", reason="")
    mid.start, mid.end = 20, len(head)
    mid.resolution = "resolved"
    mid_records = _rebind_unresolved_targets([mid], {}, inspection, rules_by_id={
        rule["rule_id"]: rule for rule in guide_rules()}, facts=_core_facts(), extend_resolved=True)
    assert mid.resolution == "resolved" and mid.composite == ()
    assert all(record["source"] != "clause_continuation" for record in mid_records)


def test_rebind_records_failure_when_reference_absent(tmp_path: Path):
    from docx import Document

    from fundlex.docx import inspect_docx
    from fundlex.recall import Target
    from fundlex.recall_pipeline import _rebind_unresolved_targets

    path = tmp_path / "absent.docx"
    document = Document()
    document.add_paragraph("本段与任何参考旧文都无关。")
    document.save(path)
    inspection = inspect_docx(path, full=True)
    target = Target(target_id="W#1:T001", rule_id="G15", location="p0", quote="完全不存在的一句话。",
                    state="needs_edit", reason="删除支付句")
    target.resolution = "quote_not_found"
    records = _rebind_unresolved_targets([target], {}, inspection,
                                         rules_by_id={rule["rule_id"]: rule for rule in guide_rules()},
                                         facts=_core_facts())
    assert target.resolution == "quote_not_found"
    assert records and records[0]["reason"] == "RECALL_TARGET_REBIND_FAILED"


def test_checkpoint_binding_dependencies(tmp_path: Path):
    checkpoint_dir = tmp_path / "checkpoints"
    source, _, gateway, report = run(tmp_path, checkpoint_dir=checkpoint_dir)

    assert gateway.bindings, "checkpoint binding must happen when checkpoint_dir is given"
    bound_dir, dependencies = gateway.bindings[0]
    assert bound_dir == checkpoint_dir
    assert dependencies["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert dependencies["guide_document_sha256"] == GUIDE_SHA
    assert dependencies["prompt_versions"] == dict(PROMPT_VERSIONS)
    assert dependencies["engine_id"] == ENGINE_ID
    assert dependencies["engine_version"] == ENGINE_VERSION
    assert dependencies["boundary_policy"] == report["plan"]["boundary_policy"]


def test_target_identity_hashes_the_full_span():
    from fundlex.recall import Target
    from fundlex.recall_pipeline import _target_identity
    common = {"target_id": "T1", "rule_id": "G15", "location": "p1",
              "state": "needs_edit", "reason": "", "start": 0, "end": 61}
    first = Target(**common, quote="甲" * 60 + "乙")
    second = Target(**common, quote="甲" * 60 + "丙")
    assert _target_identity(first) != _target_identity(second)
    assert _target_identity(first) == _target_identity(Target(**common, quote="甲" * 60 + "乙"))


def test_plan_by_target_missing_ledger_is_unresolved():
    from fundlex.recall_pipeline import _plan_by_target
    planned = {"ledger": [], "edits": [{"components": [
        {"target_id": "T1", "rule_id": "G15", "operation": "replace", "replacement": "x"}]}]}
    record = _plan_by_target(planned)["T1"]
    assert record["status"] == "unresolved"
    assert record["reason"] == "LEDGER_MISSING"


def test_window_scope_blind_window_falls_back_to_mandatory():
    from types import SimpleNamespace
    from fundlex.recall_pipeline import _Chunk, _window_rule_scope
    sections = [SimpleNamespace(id="S1", locations=("p0",)),
                SimpleNamespace(id="S2", locations=("p1",))]
    chunks = [_Chunk(id="C1", locations=("p0",), text=""),
              _Chunk(id="C2", locations=("p2",), text="")]
    blind: list[dict] = []
    scoped = _window_rule_scope(chunks, mapping={"G01": ["S1"], "G02": ["S1"]},
                                sections=sections,
                                rules=[{"rule_id": "G01"}, {"rule_id": "G02"}],
                                mandatory={"G02"}, blind_windows=blind)
    by_id = {chunk.id: ids for chunk, ids in scoped}
    assert by_id["C1"] == {"G01", "G02"}
    assert by_id["C2"] == {"G02"}
    assert blind == [{"chunk": "C2", "locations": ["p2"], "fallback_rules": ["G02"]}]


def test_window_scope_blind_window_without_mandatory_has_no_rules():
    from types import SimpleNamespace
    from fundlex.recall_pipeline import _Chunk, _window_rule_scope
    sections = [SimpleNamespace(id="S1", locations=("p0",))]
    chunks = [_Chunk(id="C0", locations=("p0",), text=""),
              _Chunk(id="C1", locations=("p1",), text="")]
    blind: list[dict] = []
    scoped = _window_rule_scope(chunks, mapping={"G01": ["S1"]}, sections=sections,
                                rules=[{"rule_id": "G01"}], mandatory=set(),
                                blind_windows=blind)
    by_id = {chunk.id: ids for chunk, ids in scoped}
    assert by_id["C1"] == set()
    assert blind[0]["fallback_rules"] == []


def test_composite_parts_gone_checks_every_paragraph(tmp_path: Path):
    from docx import Document
    from fundlex.docx import inspect_docx
    from fundlex.recall import Target, compact_offsets
    from fundlex.recall_pipeline import _composite_parts_gone

    original_path = tmp_path / "original.docx"
    document = Document()
    document.add_paragraph("前段保留，删除销售服务费。")
    document.add_paragraph("后段保留，删除销售服务费。")
    document.save(original_path)
    original = inspect_docx(original_path, full=True)
    parts = []
    for location in ("p0", "p1"):
        span = original.by_location(location)
        compact, _map = compact_offsets(span.text)
        start = compact.index("销售服务费")
        parts.append(f"{location}:{start}:{start + len('销售服务费')}")
    target = Target(target_id="T1", rule_id="G15", location="p0",
                    quote=original.by_location("p0").text, state="needs_edit",
                    reason="", composite=tuple(parts))

    both_path = tmp_path / "both.docx"
    document = Document()
    document.add_paragraph("前段保留，删除。")
    document.add_paragraph("后段保留，删除。")
    document.save(both_path)
    assert _composite_parts_gone(target, original, inspect_docx(both_path, full=True)) is True

    half_path = tmp_path / "half.docx"
    document = Document()
    document.add_paragraph("前段保留，删除。")
    document.add_paragraph("后段保留，删除销售服务费。")
    document.save(half_path)
    assert _composite_parts_gone(target, original, inspect_docx(half_path, full=True)) is False
