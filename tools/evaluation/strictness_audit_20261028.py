"""Offline characterisation probes, not acceptance tests or a semantic scorer.

Run with .venv/bin/python. No model, network, deployment or source-file mutation.
The output records current limitations; an observed limitation is NOT desired behaviour.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fundlex.applicability import resolve  # noqa: E402
from fundlex.docx import inspect_docx  # noqa: E402
from fundlex.fact_evidence import verify_class_set  # noqa: E402
from fundlex.fee_evidence import fee_value  # noqa: E402
from fundlex.recall import (ClassFact, derive_fact_statuses, facts_context,  # noqa: E402
                            structure_index)
from fundlex.rule_scope import resolve_rule_scopes  # noqa: E402


def span(location: str, text: str) -> NS:
    return NS(location=location, text=text, zone="body", logical_zone="body",
              section_path="", safe_text=text)


def inspection(spans: list[NS]) -> NS:
    by_location = {item.location: item for item in spans}
    return NS(paragraphs=spans, by_location=by_location.__getitem__)


def section(title: str, locations: list[str]) -> NS:
    return NS(id="S01", title=title, locations=tuple(locations), zone="body")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capacity_probes() -> dict:
    """Small generated OOXML fixtures; caps are observed, not declared correct."""
    import fundlex.docx as docx_tools
    from fundlex.generation.claim_replay import check_delete_residuals, replay_claims
    from fundlex.recall import (ensure_delete_targets, plan_windows,
                               source_parts_contiguous)
    from fundlex.recall_pipeline import _section_aware_chunks, _sweep_scope_plan
    from fundlex.targeting import _candidate_context, _open_rule_candidates

    helpers = runpy.run_path(str(ROOT / "tests/test_docx_structures.py"))
    base = Path(tempfile.mkdtemp(prefix="strictness-audit-", dir="/tmp/opencode"))
    make_run = helpers["run"]

    def package(name: str, body: str, extra=None):
        directory = base / name
        directory.mkdir()
        return helpers["package"](directory, body, extra)

    body = ("<w:p>" + make_run("普通正文") + "</w:p><w:tbl><w:tr><w:tc><w:p>"
            + make_run("表格旧文") + "</w:p></w:tc></w:tr></w:tbl>"
            + "<w:p><w:hyperlink>" + make_run("链接可见") + "</w:hyperlink></w:p>"
            + '<w:p><w:fldSimple w:instr="DATE">' + make_run("日期结果")
            + "</w:fldSimple></w:p><w:sdt><w:sdtContent><w:p>" + make_run("控件可见")
            + "</w:p></w:sdtContent></w:sdt>")
    extra = {"word/header1.xml": (
        f'<w:hdr xmlns:w="{docx_tools.W}"><w:p>{make_run("页眉内容")}</w:p></w:hdr>'
    ).encode()}
    source = package("structures", body, extra)
    original = inspect_docx(source, full=True)
    edit = helpers["plan_edit"](source, "tbl0/r0/c0/p0", "旧文", "新文")
    plan = docx_tools.validate_edit_plan(source, [edit], {"fixed": "新文"})
    docx_tools.generate_artifacts(source, plan, base / "redline.docx", base / "final.docx")
    result = {"fixture_directory": str(base), "structures": [
        {"location": item.location, "text": item.text, "safe_text": item.safe_text,
         "editable": item.editable, "zone": item.zone} for item in original.paragraphs],
        "table_written": inspect_docx(base / "final.docx").by_location("tbl0/r0/c0/p0").text,
        "header_enumerated": any("页眉内容" in item.text for item in original.paragraphs),
        "full_modes_equal": inspect_docx(source).paragraphs == original.paragraphs}

    body = "".join('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                   + make_run("章节" + str(i)) + "</w:p><w:p>"
                   + make_run("业务条款" + str(i)) + "</w:p>" for i in range(85))
    source = package("sections", body)
    original = inspect_docx(source, full=True)
    sections = structure_index(original)
    mapping = {"X99": [s.id for s in sections]}
    windows = plan_windows(sections, original, mapping, max_chars=500)
    chunks = _section_aware_chunks(original, sections, max_chars=500)
    scopes = {"X99": NS(locations=tuple(loc for s in sections for loc in s.locations))}
    blind: list[dict] = []
    live, _, _ = _sweep_scope_plan(chunks, scopes=scopes, mapping=mapping,
                                  sections=sections, rules=[{"rule_id": "X99"}],
                                  mandatory={"X99"}, blind_windows=blind)
    last = original.paragraphs[-1].location
    result["sections"] = {"default": len(sections),
        "raised_limit": len(structure_index(original, max_sections=1000)),
        "last_in_inventory": any(last in w.locations for w, _ in windows),
        "last_in_prescope_sweep": any(last in w.locations for w in chunks),
        "last_in_scoped_sweep": any(last in w.locations for w in live), "blind": blind}

    sentence = "销售服务费每日计提，按月支付。"
    source = package("deletions", "".join("<w:p>" + make_run(sentence) + "</w:p>" for _ in range(25)))
    original = inspect_docx(source, full=True)
    rule = {"rule_id": "G15", "operations": [{"op": "delete", "old_text": sentence}]}
    result["delete_cap"] = {"candidates": 25,
        "default": len(ensure_delete_targets([], {"G15": rule}, original)),
        "raised_limit": len(ensure_delete_targets([], {"G15": rule}, original, limit=100))}
    rule = {"rule_id": "X99", "title": "修改", "operations": [{"op": "replace", "old_text": sentence,
                                               "new_text": "新文"}]}
    sections = structure_index(original)
    facts = NS(as_ledger=lambda: {})
    candidates = _open_rule_candidates(original, rule, [s.id for s in sections],
                                       {s.id: s for s in sections}, facts)
    target = NS(location="p0", quote="原目标", site_candidates=tuple(p.location for p in original.paragraphs))
    _, allowed = _candidate_context(original, target, rule, facts, limit=10000)
    result["candidate_cap"] = {"source_candidates": 25, "discovered": len(candidates),
                                "context_allowed": len(allowed)}

    class FixtureInspection:
        def __init__(self, prefix, count):
            self.paragraphs = tuple(span(f"p{i}", prefix + str(i)) for i in range(count))

        def by_location(self, loc):
            return next(item for item in self.paragraphs if item.location == loc)

    before, after = FixtureInspection("原文", 45), FixtureInspection("新文", 45)
    edits = [{"location": f"p{i}", "rule_id": "MISSING", "start": 0,
              "end": len(before.paragraphs[i].text), "replacement": "计划" + str(i),
              "expected_old_text": before.paragraphs[i].text} for i in range(45)]
    proof = replay_claims(edits, before, after, rules_by_id={})
    proof100 = replay_claims(edits, before, after, rules_by_id={}, max_failures=100)
    result["claim_cap"] = {"default_checked": proof["checked"],
                            "raised_checked": proof100["checked"], "verified": proof["verified"]}
    source = package("residuals", "".join("<w:p>" + make_run(sentence) + "</w:p>" for _ in range(45)))
    original = inspect_docx(source, full=True)
    rules = {"G15": {"rule_id": "G15", "operations": [{"op": "delete", "old_text": sentence}]}}
    result["residual_cap"] = {"default": len(check_delete_residuals(rules, original)),
        "raised_limit": len(check_delete_residuals(rules, original, max_failures=100))}
    result["composite"] = {"contiguous": source_parts_contiguous(before, ["p0", "p1"]),
        "skips_independent": source_parts_contiguous(before, ["p0", "p2"])}
    before.paragraphs[1].section_path = "other"
    result["composite"]["cross_section"] = source_parts_contiguous(before, ["p0", "p1"])
    return result


def semantic_gate_probes() -> dict:
    """Scripted model responses only: identify inconsistent semantic contracts."""
    import os
    from unittest.mock import patch
    from fundlex.docx import TextSegment
    from fundlex.generation.claim_replay import replay_claims
    from fundlex.generation.effects import evaluate_operation_effect, operation_site_bound
    from fundlex.obligations import apply_facts, compile_obligations
    from fundlex.recall import (Facts, RecallError, Target, _verify_composed,
                               assign_target_operations, compose_variant,
                               plan_target, target_site_ok)
    from fundlex.targeting import _open_operation_candidates, locate_unresolved_targets

    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text())
    rules = {rule["rule_id"]: rule for rule in guide["groups"]}
    facts = Facts("", "", "", (ClassFact("A", True, False, True, None, ""),
                                 ClassFact("C", False, True, True, None, "")),
                  False, "", "", "", {}, (), fact_status={key: "VERIFIED" for key in
                  ("share_class_structure", "subscription_fee_group", "service_fee_group")})

    class FixtureInspection:
        source_sha256 = "offline-synthetic-probe"

        def __init__(self, texts):
            self.paragraphs = [NS(location=f"p{i}", text=text,
                segments=(TextSegment(0, len(text)),), zone="body", fingerprint=f"p{i}")
                for i, text in enumerate(texts)]

        def by_location(self, loc):
            return next(item for item in self.paragraphs if item.location == loc)

    class Gateway:
        max_context_chars = 20000

        def __init__(self, values=()):
            self.values, self.calls = iter(values), []

        def call(self, **kwargs):
            self.calls.append(kwargs["task_type"])
            return NS(value=next(self.values))

    def target(rule_id, text):
        return Target("T", rule_id, "p0", text, "needs_edit", "offline-audit",
                      start=0, end=len(text), resolution="resolved", segment_ok=True,
                      operations=(rule_id + ":0",))

    result = {}
    texts = {
        "G13": rules["G13"]["operations"][0]["old_text"].replace("持续持有期少于7日", "持有不足7日"),
        "G17": rules["G17"]["operations"][0]["old_text"].replace("主要用于", "用于").replace("使用范围", "用途"),
        "G11": "申购费用由投资人支付，不列入基金财产。",
        "G09": "投资者赎回所得金额按确认的有效赎回份额乘以当日对应份额类别的基金份额净值，再减去应扣的相关费用计算，赎回金额单位为元。",
    }
    with patch.dict(os.environ, {"FUNDLEX_GENERATION_STRATEGY": "registry"}):
        for rule_id, text in texts.items():
            rule = rules[rule_id]
            original = FixtureInspection([text])
            proposed = target(rule_id, text)
            gateway = Gateway()
            ledger = compile_obligations({"groups": [rule]})
            apply_facts(ledger, facts)
            record = ledger.record(rule_id + ":0")
            entry = {"source": text, "site_ok": target_site_ok(rule_id, original.by_location("p0"), original),
                "attribution_errors": assign_target_operations([proposed], {rule_id: rule}, original, facts),
                "operations": proposed.operations,
                "effect_site_bound": operation_site_bound(record.spec, text, original, "p0", facts),
                "candidates": _open_operation_candidates(original, rule, record, ["S"],
                                                          {"S": NS(locations=("p0",))}, facts)}
            recovery = target(rule_id, text)
            recovery.resolution, recovery.site_candidates = "unresolved", ("p0",)
            locator = Gateway([{"location": "p0", "quote": text,
                                "semantic_role": "fee_clause", "reason": "exact source"}])
            entry["locator"] = locate_unresolved_targets([recovery], original, {rule_id: rule}, facts, locator)
            if record.spec.op == "delete":
                proof = evaluate_operation_effect(record, original, original, [], [], facts)
                entry["unchanged_without_sites_proof"] = proof.as_dict()
            try:
                edit = plan_target(rule, proposed, original, facts, gateway,
                                   compose_budget=[5], obligations=ledger)
                entry["plan_source"] = edit.content_source if edit else None
                if edit:
                    after = FixtureInspection([text[:edit.start] + edit.replacement + text[edit.end:]])
                    proof = replay_claims([edit.as_dict()], original, after,
                        rules_by_id={rule_id: rule}, facts=facts, targets_by_id={"T": proposed.as_dict()},
                        obligations=ledger)
                    entry["replay_failures"] = proof["failures"]
            except RecallError as exc:
                entry["plan_error"] = {"code": exc.code, "detail": exc.detail}
            entry["scripted_generation_calls"] = gateway.calls
            result[rule_id] = entry

        path = next((ROOT / "funds_word/基金合同第一批").glob("*弘利*.docx"))
        original = inspect_docx(path, full=True)
        sp = original.by_location("p784")
        quote = sp.text.split("。")[0] + "。"
        proposed = Target("REAL", "G17", "p784", quote, "needs_edit", "exact source",
                          start=0, end=len(quote), resolution="resolved", segment_ok=True,
                          operations=("G17:0",))
        sections = structure_index(original)
        ids = [s.id for s in sections if "费用" in s.title and s.zone == "body"]
        scope = resolve_rule_scopes([rules["G17"]], sections, original, {"G17": ids})["G17"]
        gateway = Gateway()
        entry = {"source": str(path.relative_to(ROOT)), "source_sha256": digest(path), "quote": quote,
                 "in_scope": scope.contains("p784"), "scope_resolution": scope.resolution,
                 "attribution": assign_target_operations([proposed], {"G17": rules["G17"]}, original, facts)}
        try:
            plan_target(rules["G17"], proposed, original, facts, gateway, compose_budget=[5])
        except RecallError as exc:
            entry["plan_error"] = {"code": exc.code, "detail": exc.detail}
        entry["scripted_calls"] = gateway.calls
        result["real_G17"] = entry

        original = FixtureInspection(["原条款。"])
        proposed = target("GTEST", "原条款。")
        rule = {"rule_id": "GTEST", "title": "test", "operations": [{"op": "replace",
                "old_text": "原条款。", "new_text": "赎回费用全额计入基金财产。"}]}
        gateway = Gateway([{"replacement": "本基金的赎回费用全部归入基金资产。",
                            "preserved": [], "basis": "同义改写"}])
        try:
            compose_variant(original.paragraphs[0], proposed, rule, "原条款。",
                            "赎回费用全额计入基金财产。", facts, gateway)
        except RecallError as exc:
            result["fixed_text_before_review"] = {"code": exc.code, "scripted_calls": gateway.calls}

        original = FixtureInspection(["删除旧句。保留原句。"])
        proposed = target("GTEST", original.paragraphs[0].text)
        rule = {"rule_id": "GTEST", "title": "test", "operations": [{"op": "delete", "old_text": "删除旧句。"}]}
        gateway = Gateway([
            {"replacement": "删除旧句。保留原句。", "preserved": [], "basis": ""},
            {"replacement": "保留原句。", "preserved": ["保留原句。"], "basis": ""},
            {"verdict": "pass"}])
        try:
            compose_variant(original.paragraphs[0], proposed, rule, proposed.quote, "", facts, gateway, mode="delete")
        except RecallError as exc:
            result["delete_retry_stale_error"] = {"code": exc.code, "scripted_calls": gateway.calls}

        text = "申购费用由投资人承担，不列入基金财产。"
        gateway = Gateway([{"verdict": "pass"}])
        outcome = _verify_composed({"rule_id": "GTEST", "operations": []},
            target("GTEST", text), text, text.replace("投资人", "投资者"), "", facts, gateway, mode="replace")
        result["protected_word_change"] = {"outcome": outcome, "scripted_calls": gateway.calls}
    return result


def run() -> dict:
    rows: list[dict] = []
    source_root = ROOT / "funds_word/基金合同第一批"
    contract = source_root / "广发景宁纯债债券型证券投资基金基金合同.docx"
    doc = inspect_docx(contract, full=True)
    sections = structure_index(doc)
    basics = [item.id for item in sections if "基本情况" in item.title]
    scope = resolve_rule_scopes([{"rule_id": "G05"}], sections, doc,
                               {"G05": basics})["G05"]
    rows.append({
        "id": "scope_duplicate_body_clause", "source": str(contract.relative_to(ROOT)),
        "source_sha256": digest(contract),
        "p148_zone": doc.by_location("p148").zone,
        "p155_zone": doc.by_location("p155").zone,
        "p148_section": doc.by_location("p148").section_path,
        "p155_section": doc.by_location("p155").section_path,
        "p148_in_G05_scope": scope.contains("p148"),
        "p155_in_G05_scope": scope.contains("p155"),
        "p155_has_old_fee": "调低赎回费率" in doc.by_location("p155").text,
        "p155_has_filing": "并报中国证监会备案" in doc.by_location("p155").text,
        "scope": scope.as_dict(),
    })
    artifact = Path("/tmp/opencode/smoke5-fix-20261028/run") / (
        "002-广发景宁纯债债券型证券投资基金基金合同")
    if (artifact / "final.docx").exists() and (artifact / "report.json").exists():
        actual = inspect_docx(artifact / "final.docx", full=True)
        report = json.loads((artifact / "report.json").read_text())
        rows[-1]["historical_artifact"] = {
            "path": str(artifact), "final_sha256": digest(artifact / "final.docx"),
            "report_sha256": digest(artifact / "report.json"),
            "delivery_status": report.get("delivery_status"),
            "claim_verified": (report.get("artifact_claim_replay") or {}).get("verified"),
            "final_omission_status": (report.get("final_omission_review") or {}).get("status"),
            "p148_old_fee_survives": "调低赎回费率" in actual.by_location("p148").text,
            "p155_old_fee_survives": "调低赎回费率" in actual.by_location("p155").text,
            "p155_filing_survives": "并报中国证监会备案" in actual.by_location("p155").text,
        }

    spans = [span("p0", "一、销售服务费"),
             span("p1", "C类基金份额的销售服务费每日计提，按月支付。")]
    doc = inspection(spans)
    sec = section("第十五部分基金费用", [item.location for item in spans])
    scope = resolve_rule_scopes([{"rule_id": "G15", "section_hint": "基金费用"}],
                               [sec], doc, {"G15": [sec.id]})["G15"]
    rows.append({"id": "fee_chapter_without_tax", "scope": scope.as_dict(),
                 "observation": "An explicit fee leaf in the mapped chapter is unresolved."})

    definition = ("本基金将基金份额分为A类和C类。A类基金份额收取申购费，"
                  "C类基金份额收取销售服务费。")
    spans = [span("p0", "一、基金份额类别设置"), span("p1", definition),
             span("p2", "二、基金份额的类别"), span("p3", definition)]
    doc = inspection(spans)
    sec = section("第三部分基金的基本情况", [item.location for item in spans])
    scope = resolve_rule_scopes([{"rule_id": "G04"}], [sec], doc,
                               {"G04": [sec.id]})["G04"]
    rows.append({"id": "multiple_definition_leaves_choose_first",
                 "scope": scope.as_dict(), "p3_in_scope": scope.contains("p3")})

    spans = [span("p0", "一、基金销售服务费"),
             span("p1", "C类基金份额的销售服务费每日计提，按月支付。")]
    doc = inspection(spans)
    sec = section("第十五部分基金费用与税收", [item.location for item in spans])
    scopes = resolve_rule_scopes([
        {"rule_id": "G01", "title": "基金销售服务费", "section_hint": "基金费用与税收"},
        {"rule_id": "CUSTOM01", "title": "基金销售服务费", "section_hint": "基金费用与税收"},
    ], [sec], doc, {"G01": [sec.id], "CUSTOM01": [sec.id]})
    rows.append({"id": "rule_id_changes_scope_policy",
                 "G01": scopes["G01"].as_dict(),
                 "CUSTOM01": scopes["CUSTOM01"].as_dict(),
                 "scope": "synthetic custom-guide policy dispatch, not a built-in G01 clause"})

    classes = [NS(name="A类", current=True), NS(name="C类", current=True)]
    quote = "本基金现有A类与C类基金份额。"
    evidence = verify_class_set(inspection([span("p0", quote)]), classes, quote)
    rows.append({"id": "class_enumeration_verb_gate", "quote": quote,
                 "result": evidence})
    quote = "C类基金份额销售服务费实行0.5%的年费率。"
    rows.append({"id": "fee_grammar_gate", "quote": quote,
                 "fee_value": fee_value(quote, "sales_service_fee", "C")})

    classes = [ClassFact(name="A类", subscription_fee=True, service_fee=False,
                         current=True, rate=None, quote="A类"),
               ClassFact(name="C类", subscription_fee=False, service_fee=True,
                         current=True, rate=None, quote="C类")]
    statuses = derive_fact_statuses(
        fund_type_ok=True, classes=classes, class_quotes={"A类": True, "C类": True},
        direct_classes=(), direct_ok=False, other_classes=(), other_ok=False,
        set_complete_verified=True,
        fee_polarities={"A类": {"subscription_fee": True, "service_fee": False},
                        "C类": {"subscription_fee": False, "service_fee": None}})
    rows.append({"id": "unrelated_fee_fact_coupling", "statuses": statuses,
                 "observation": "All subscription polarities are proven; service C is unknown."})

    class Gateway:
        max_context_chars = 32000
        calls = 0

        def call(self, **kwargs):
            self.calls += 1
            raise AssertionError("This offline probe must not request a real model.")

    gateway = Gateway()
    facts = NS(status_of=lambda name: "UNKNOWN", class_count=2,
               condition_overrides={})
    decision = resolve({"kind": "class_count", "value": "multiple"}, facts,
                       gateway=gateway, evidence="本基金有两类基金份额。",
                       inspection=inspection([span("p0", "本基金有两类基金份额。")]))
    rows.append({"id": "unknown_fact_blocks_applicability_judge",
                 "decision": decision.as_dict(), "gateway_calls": gateway.calls,
                 "observation": "Fact recovery is separate; this judge cannot override an unknown fact."})

    spans = [span("p0", "本基金设A类、C类基金份额。"),
             span("p1", "其他申赎说明" * 500),
             span("p2", "C类基金份额的销售服务费每日计提，按月支付。")]
    for item in spans:
        item.section_path = "基金份额的申购与赎回"
    context = facts_context(inspection(spans), limit=200)
    rows.append({"id": "facts_context_oversized_paragraph_stops_later_evidence",
                 "context": context, "late_fee_shown": "[p2]" in context,
                 "scope": "synthetic long paragraph; corpus results below are separate"})

    corpus = []
    for path in sorted(source_root.glob("*.docx")):
        try:
            doc = inspect_docx(path, full=True)
        except Exception as exc:
            corpus.append({"file": path.name, "parse_error": getattr(exc, "code", type(exc).__name__)})
            continue
        context = facts_context(doc, limit=28500)
        fee_locations = [item.location for item in doc.paragraphs
                         if "费用" in (item.section_path or "")
                         and "销售服务费" in item.text
                         and (item.logical_zone or item.zone) == "body"]
        absent = [loc for loc in fee_locations if f"[{loc}] " not in context]
        corpus.append({"file": path.name, "source_sha256": digest(path),
                       "context_chars": len(context),
                       "body_fee_paragraphs": len(fee_locations),
                       "body_fee_locations_not_shown": absent})

    paths = ["fundlex/rule_scope.py", "fundlex/recall.py", "fundlex/applicability.py",
             "fundlex/facts_recovery.py", "fundlex/fact_evidence.py", "fundlex/fee_evidence.py",
             "fundlex/docx.py", "fundlex/recall_pipeline.py", "fundlex/targeting.py",
             "fundlex/generation/effects.py", "fundlex/generation/claim_replay.py",
             "guides/builtin_guide_v1.json"]
    return {"date": "2026-10-28", "mode": "offline_current_behaviour",
            "not_acceptance_evidence": True, "model_calls": 0,
            "source_fingerprints": {p: digest(ROOT / p) for p in paths},
            "probes": rows, "facts_context_corpus_probe": corpus,
            "capacity_and_structure_probes": capacity_probes(),
            "semantic_gate_probes": semantic_gate_probes()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    result = run()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "probes": len(result["probes"]),
                      "corpus_files": len(result["facts_context_corpus_probe"]),
                      "model_calls": 0}, ensure_ascii=False))
