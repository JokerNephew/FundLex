"""One-contract processing pipeline. Every uncertain step fails closed."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

from .docx import DocxError, generate_noop_evaluation_artifacts, inspect_docx, validate_edit_plan
from .model import ModelError, ModelGateway
from .rules import RuleError, classify_fund_type, evaluate_candidates, load_ruleset


ENGINE_VERSION = "0.1.0"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_report_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = ["# FundLex 合同处理报告", "",
             f"- 源文件 SHA-256：{report['source_sha256']}",
             f"- 规则版本：{report['ruleset_version']}",
             f"- 资格：{report['qualification_status']}",
             f"- 交付完整性：{report['delivery_status']}",
             f"- 发布门槛：{report['release_gate']['status']}",
             f"- 修改数：{report['edit_plan']['count']}"]
    if report.get("error_code"):
        lines.append(f"- 错误代码：{report['error_code']}")
    if report.get("qualification", {}).get("evidence"):
        evidence = report["qualification"]["evidence"]
        lines.append(f"- 资格依据：{evidence['quote']}（{evidence['part_uri']} {evidence['paragraph_id']}）")
    lines.extend(["", "## Action 结果", ""])
    for action in report.get("actions", []):
        lines.append(f"- {action['action_id']}：{action['status']}；候选 {len(action['candidates'])}；自动写入关闭")
    if report["delivery_status"] != "complete":
        lines.extend(["", "**不完整，不能作为最终合同。**"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def process(input_path: Path, output_dir: Path, ruleset_version: str,
            gateway: ModelGateway | None = None) -> dict[str, Any]:
    """Process one DOCX; return a JSON-serializable report and local artifacts.

    The unreleased v1 rule set performs read-only candidate evaluation. No
    business edit can be generated until the offline action release gates pass.
    """
    input_path, output_dir = Path(input_path), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    source_hash = _sha(input_path) if input_path.is_file() else ""
    report: dict[str, Any] = {
        "schema_version": "1", "engine_version": ENGINE_VERSION,
        "source_sha256": source_hash, "ruleset_version": ruleset_version,
        "ruleset_sha256": None, "qualification_status": "failed",
        "qualification": {"status": "failed", "evidence": None},
        "profile": {}, "actions": [], "edit_plan": {"count": 0, "sha256": None, "edits": []},
        "release_gate": {"status": "closed", "reason": "RULESET_UNRELEASED"},
        "delivery_status": "not_generated", "has_toc_field": None,
        "toc_update_status": "not_applicable", "output_validation": None,
        "model": {"configured_model": None, "actual_model": None, "calls": 0,
                  "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                  "latency_ms": 0, "cost": None, "rate_limit_count": 0,
                  "error_count": 0, "prompt_version": "fund_type_v1"},
        "errors": [], "error_code": None, "artifacts": {},
    }
    try:
        ruleset = load_ruleset(ruleset_version)
        report["ruleset_sha256"] = ruleset.sha256
        report["release_gate"] = {"status": "closed" if not ruleset.auto_write_enabled else "open",
                                  "reason": ruleset.release_policy.get("basis"),
                                  "auto_write_actions": [a["action_id"] for a in ruleset.actions if a["auto_write"]]}
        minimal = inspect_docx(input_path, full=False)
        report["has_toc_field"] = minimal.has_toc_field
        evidence = classify_fund_type(minimal)
        type_quote = evidence["evidence"]["quote"]
        operation_quote = evidence.get("operation_evidence", {}).get("quote", "")
        context = (type_quote + ("\n" + operation_quote if operation_quote else ""))[:2200]
        model = gateway or ModelGateway.from_env()
        report["model"]["configured_model"] = model.model
        model_start = time.monotonic()
        try:
            result = model.extract_fund_type(context)
            report["model"].update({"actual_model": result.model, "calls": 1,
                                    "prompt_tokens": result.prompt_tokens,
                                    "completion_tokens": result.completion_tokens,
                                    "total_tokens": result.total_tokens,
                                    "latency_ms": result.latency_ms,
                                    "attempts": result.attempts,
                                    "request_id": result.request_id})
        except ModelError as exc:
            report["model"].update({"calls": model.calls, "error_count": 1,
                                    "latency_ms": round((time.monotonic() - model_start) * 1000)})
            if exc.code == "MODEL_RETRY_EXHAUSTED":
                report["model"]["rate_limit_count"] = 1
            raise
        if result.value["fund_type"] != evidence["fund_type"]:
            raise RuleError("MODEL_TYPE_CONFLICT")
        model_quote = result.value["quote"]
        if model_quote not in context or len(model_quote) < 4:
            raise RuleError("MODEL_EVIDENCE_INVALID")
        report["model"]["quote_verification"] = "verified_against_bounded_context"
        report["qualification"] = {"status": "eligible", "fund_type": evidence["fund_type"],
                                   "evidence": evidence["evidence"],
                                   "operation_evidence": evidence.get("operation_evidence"),
                                   "model_quote": model_quote, "model_verification": "verified"}
        if evidence["fund_type"] in {"etf", "interbank_cd", "money_market"}:
            report["qualification_status"] = "excluded_by_fund_type"
            report["qualification"]["status"] = "excluded_by_fund_type"
            return report
        report["qualification_status"] = "eligible"
        full = inspect_docx(input_path, full=True)
        report["has_toc_field"] = full.has_toc_field
        report["toc_update_status"] = "not_updated" if full.has_toc_field else "not_applicable"
        report["actions"] = evaluate_candidates(full, ruleset)
        plan = validate_edit_plan(input_path, [], ruleset.templates)
        report["edit_plan"] = {"count": 0, "sha256": plan.plan_sha256, "edits": [],
                               "validated": True, "executable": False,
                               "reason": "RELEASE_GATE_CLOSED"}
        (output_dir / "edits.json").write_text(json.dumps(report["edit_plan"], ensure_ascii=False, indent=2), encoding="utf-8")
        # Diagnostic copies prove transport and byte identity only, never final delivery.
        evaluation = generate_noop_evaluation_artifacts(
            input_path, output_dir / "evaluation_redline.docx", output_dir / "evaluation_final.docx")
        report["output_validation"] = {
            "kind": "zero_edit_evaluation_only",
            "source_sha256": source_hash,
            "redline_sha256": evaluation.redline_sha256,
            "final_sha256": evaluation.final_sha256,
            "byte_identical_to_source": evaluation.redline_sha256 == source_hash and evaluation.final_sha256 == source_hash,
            "not_a_final_contract": True,
        }
        if any(action["candidates"] for action in report["actions"]):
            report["delivery_status"] = "not_generated"
        else:
            report["delivery_status"] = "incomplete"
        return report
    except (DocxError, RuleError, ModelError) as exc:
        code = exc.code
        report["error_code"] = code
        report["errors"].append({"code": code, "stage": "processing", "message": code})
        if report["qualification_status"] != "eligible":
            report["qualification_status"] = "failed"
            report["qualification"]["status"] = "failed"
        report["delivery_status"] = "not_generated"
        return report
    finally:
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
        _write_report_markdown(output_dir / "report.md", report)
