"""Offline characterisation of the remediation slice (no model, no network).

Run: ``.venv/bin/python tools/evaluation/remediation_probe_20261028.py --output <path>``

It records *current working-tree behaviour* for the first remediation stages:
RuleScope multi-leaf coverage (景宁 p148/p155), the approval-based site-guard
waiver (弘利 G17 p784), G14 repeated-noun binding, full structure indexing and
the delete-retry state fix.  An observation is evidence for these tests only,
not a business acceptance result or a real DOCX delivery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fundlex.docx import TextSegment, inspect_docx  # noqa: E402
from fundlex.generation.effects import evaluate_operation_effect  # noqa: E402
from fundlex.obligations import apply_facts, compile_obligations  # noqa: E402
from fundlex.recall import (Facts, RecallError, Target, assign_target_operations,  # noqa: E402
                            plan_target, structure_index)
from fundlex.rule_scope import resolve_rule_scopes  # noqa: E402
from fundlex.semantic_evidence import (ApprovalBook, approval_from_target,  # noqa: E402
                                       guide_fingerprint)

SOURCE_ROOT = ROOT / "funds_word/基金合同第一批"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rules_by_id() -> dict[str, dict]:
    guide = json.loads((ROOT / "guides/builtin_guide_v1.json").read_text())
    return {str(rule["rule_id"]): rule for rule in guide["groups"]}


def facts() -> Facts:
    from fundlex.recall import ClassFact
    return Facts("", "", "", (ClassFact("A", True, False, True, None, ""),
                              ClassFact("C", False, True, True, None, "")),
                 False, "", "", "", {}, (),
                 fact_status={key: "VERIFIED" for key in
                              ("share_class_structure", "subscription_fee_group",
                               "service_fee_group")})


class Gateway:
    max_context_chars = 20000

    def __init__(self) -> None:
        self.calls = 0

    def call(self, **kwargs):
        self.calls += 1
        raise AssertionError("offline probe must not request a model")


def scope_for(path: Path, rule_ids: list[str]) -> tuple[Any, dict]:
    inspection = inspect_docx(path, full=True)
    sections = structure_index(inspection)
    mapped = {}
    for rule_id in rule_ids:
        if rule_id.startswith("G05"):
            mapped[rule_id] = [s.id for s in sections if "基本情况" in s.title]
        elif rule_id.startswith("G17"):
            mapped[rule_id] = [s.id for s in sections
                               if "费用" in s.title and s.zone == "body"]
        else:
            mapped[rule_id] = [s.id for s in sections]
    rules = [rules_by_id()[rule_id] for rule_id in rule_ids]
    scopes = resolve_rule_scopes(rules, sections, inspection, mapped)
    return inspection, scopes


def main() -> dict:
    out: dict = {"date": "2026-10-28", "model_calls": 0,
                 "not_business_acceptance": True}
    rules = rules_by_id()

    # 1. RuleScope multi-leaf: both body class clauses must be reachable.
    path = SOURCE_ROOT / "广发景宁纯债债券型证券投资基金基金合同.docx"
    inspection, scopes = scope_for(path, ["G05"])
    scope = scopes["G05"]
    out["jingning_g05"] = {
        "source": str(path.relative_to(ROOT)), "source_sha256": digest(path),
        "resolution": scope.resolution, "locations": sorted(scope.locations),
        "p148_in_scope": scope.contains("p148"), "p155_in_scope": scope.contains("p155"),
        "p155_zone": inspection.by_location("p155").zone,
        "p155_old_rate": "调低赎回费率" in inspection.by_location("p155").text,
        "p155_filing": "并报中国证监会备案" in inspection.by_location("p155").text,
    }

    # 2. Approval-based site-guard waiver for the real 弘利 G17 sentence.
    path = SOURCE_ROOT / "广发弘利3个月滚动持有债券型证券投资基金基金合同.docx"
    inspection, scopes = scope_for(path, ["G17"])
    span = inspection.by_location("p784")
    quote = span.text.split("。")[0] + "。"
    target = Target("REAL", "G17", "p784", quote, "needs_edit", "exact source",
                    start=0, end=len(quote), resolution="resolved", segment_ok=True,
                    operations=("G17:0",))
    errors = assign_target_operations([target], {"G17": rules["G17"]}, inspection,
                                      facts(), None)
    target.scope_id = next(iter(scopes["G17"].locations)) and "G17:probe"
    target.scope_id = "G17:probe"
    approval = approval_from_target("AP:REAL", target, inspection,
                                    guide_id="active_guide",
                                    guide_sha256=guide_fingerprint(
                                        [rules["G17"]]))
    target.approval_id = approval.approval_id
    book = ApprovalBook([approval])
    gateway = Gateway()
    entry = {"source": str(path.relative_to(ROOT)), "source_sha256": digest(path),
             "quote": quote, "in_scope": scopes["G17"].contains("p784"),
             "scope_resolution": scopes["G17"].resolution,
             "attribution_errors": errors, "operations": list(target.operations),
             "approval_ok": book.allows(target, inspection).ok}
    try:
        edit = plan_target(rules["G17"], target, inspection, facts(), gateway,
                           compose_budget=[5], approvals=book)
        entry["plan_error"] = None
        if edit is not None:
            entry["planned"] = {"content_source": edit.content_source,
                                "start": edit.start, "end": edit.end,
                                "replacement": edit.replacement,
                                "deleted_quote": (edit.evidence or {}).get("deleted_quote")}
    except RecallError as exc:
        entry["plan_error"] = {"code": exc.code}
    except Exception as exc:  # noqa: BLE001 - record, do not mask
        entry["plan_error"] = {"code": type(exc).__name__, "detail": str(exc)[:200]}
    entry["model_calls"] = gateway.calls
    entry["site_guard_waived"] = "TARGET_SOURCE_MISMATCH" not in str(
        (entry.get("plan_error") or {}).get("code"))
    out["hongli_g17"] = entry

    # 3. G14 repeated noun binding on the real QDII paragraph.
    from fundlex.recall import _normalise_fee_rate_reference
    qdii = SOURCE_ROOT / "广发全球稳健配置混合型证券投资基金（QDII）基金合同.docx"
    qdii_inspection = inspect_docx(qdii, full=True)
    text = qdii_inspection.by_location("p263").text
    out["g14_binding"] = {
        "source": str(qdii.relative_to(ROOT)), "source_sha256": digest(qdii),
        "normalised_contains_expression_2": "调低基金申购费率、赎回费率和转换费率" in
        _normalise_fee_rate_reference(text),
    }

    # 4. Full structure indexing past the old 80-section cap.
    helpers = runpy.run_path(str(ROOT / "tests/test_docx_structures.py"))
    base = Path(tempfile.mkdtemp(prefix="remediation-probe-", dir="/tmp/opencode"))
    make_run = helpers["run"]
    body = "".join('<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
                   + make_run("章节" + str(i)) + "</w:p><w:p>"
                   + make_run("业务条款" + str(i)) + "</w:p>" for i in range(85))
    directory = base / "sections"
    directory.mkdir()
    source = helpers["package"](directory, body)
    long_doc = inspect_docx(source, full=True)
    sections = structure_index(long_doc)
    out["structure_index"] = {
        "section_count": len(sections),
        "last_location_indexed": long_doc.paragraphs[-1].location in
        set(loc for section in sections for loc in section.locations),
        "explicit_80_still_limits": len(structure_index(long_doc, max_sections=80)),
    }

    # 5. Delete proof must not pass from literal absence alone.
    record = compile_obligations({"groups": [rules["G13"]]}).record("G13:0")
    apply_facts(compile_obligations({"groups": [rules["G13"]]}), facts())
    proof = evaluate_operation_effect(record, long_doc, long_doc, [], [], facts())
    out["effect_literal_absence"] = {"state": proof.state,
                                     "artifact_status": proof.artifact_status,
                                     "failure_code": proof.failure_code}
    out["source_fingerprints"] = {
        name: digest(ROOT / name) for name in (
            "fundlex/semantic_evidence.py", "fundlex/recall.py",
            "fundlex/recall_pipeline.py", "fundlex/rule_scope.py",
            "fundlex/generation/effects.py", "fundlex/generation/claim_replay.py",
            "guides/builtin_guide_v1.json")}
    return out


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = main()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print(json.dumps({"output": str(output), "model_calls": 0,
                      "checks": [key for key in result if key not in
                                 ("date", "model_calls", "not_business_acceptance",
                                  "source_fingerprints")]}, ensure_ascii=False))
