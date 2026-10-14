"""V2 pipeline: source-bound planning and independent actual-artifact review.

The v1 ``process`` path stays untouched and read-only. This path runs under an
explicit evaluation execution mode: generated edits are allowed only with a
server-side content-verification record, artifacts are labelled evaluation
files, and delivery never claims a releasable final contract.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from pathlib import Path
from typing import Any

from .docx import (DocxError, generate_artifacts, generate_noop_evaluation_artifacts,
                   generate_unchanged_artifacts, inspect_docx, validate_edit_plan)
from .model import ModelError, ModelGateway
from .rules import RuleError, classify_document_identity, classify_fund_type, resolve_profile
from .rules_v2 import PROMPT_VERSIONS_V2, RuleV2Error, load_ruleset_v2
from .store import engine_build, SCHEMA_VERSION
from .v2 import V2Error, plan_v2
from .artifact_review import review_artifacts

ENGINE_VERSION = "0.3.0"
EXECUTION_MODE = "evaluation"
STOP_CODES = {"MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED",
              "MODEL_CIRCUIT_OPEN", "MODEL_CONFIG_MISSING", "MODEL_HTTP_ERROR",
              "MODEL_LEDGER_UNAVAILABLE", "MODEL_CHECKPOINT_UNAVAILABLE"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_v2_markdown(path: Path, report: dict[str, Any]) -> None:
    lines = ["# FundLex v2 评测处理报告", "",
             f"- 执行模式：{report.get('execution_mode')}",
             f"- 源文件 SHA-256：{report.get('source_sha256')}",
             f"- 规则版本：{report.get('ruleset_version')} / {report.get('ruleset_sha256')}",
             f"- 资格：{report.get('qualification_status')}",
             f"- 交付完整性：{report.get('delivery_status')}",
             f"- 修改数：{report.get('edit_plan', {}).get('count')}"]
    if report.get("error_code"):
        lines.append(f"- 错误代码：{report['error_code']}")
    lines.extend(["", "## v2 Action 结果", ""])
    for action in report.get("actions", []):
        lines.append(f"- {action['action_id']}：{action['status']}；适用性 {action['applicability']}；"
                     f"目标 {len(action['targets'])}；{action.get('failure_reason') or '无失败'}")
        for target in action.get("targets", []):
            lines.append(f"  - {target['location']} [{target['char_start']},{target['char_end']})："
                         f"{target['status']}；{target.get('reason') or '核验通过'}；原文：{target['quote'][:80]}")
            if target.get("generated_text"):
                lines.append(f"    新文：{target['generated_text'][:160]}")
    records = report.get("content_verifications", [])
    if records:
        lines.extend(["", "## 服务端内容验证记录", ""])
        for record in records:
            lines.append(f"- {record['action_id']} {record['location']} "
                         f"content={record['content_source']} passed={record['passed']} "
                         f"record_sha256={record['record_sha256'][:16]}…")
            for item in record.get("requirements", []):
                lines.append(f"  - {item['id']} [{item['checker']}]：{item['result']}")
    if report.get("actual_content_verifications"):
        lines.extend(["", "## 实际 DOCX 独立复核", ""])
        for review in report["actual_content_verifications"]:
            lines.append(f"- 第 {review['round']} 轮：passed={review['passed']}；"
                         f"plan={review['plan_sha256']}；final={review['final_sha256']}")
            for action in review["actions"]:
                lines.append(f"  - {action['action_id']}：passed={action['passed']}；"
                             f"{action.get('reason') or '通过'}")
    if report.get("execution_mode") == "delivery":
        if report.get("delivery_status") == "complete":
            lines.extend(["", "**正式交付：修订版与接受修订后版本均通过校验。**"])
        elif report.get("delivery_status") == "complete_with_exceptions":
            lines.extend(["", "**附例外交付：已验证的修改已生成正式合同文件；拒绝动作保留原文，请查看例外清单。**"])
        else:
            lines.extend(["", "**不完整交付：存在未处理动作，未生成正式合同文件。**"])
    elif report.get("delivery_status") != "evaluation_modified":
        lines.extend(["", "**本次为评测产物，不构成可直接使用的正式最终合同。**"])
    else:
        lines.extend(["", "**已通过技术校验的评测修改版；仍非正式最终合同。**"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _revert_actions(outcome: dict, reasons: dict[str, str]) -> None:
    for action in outcome["actions"]:
        if action["action_id"] not in reasons:
            continue
        reason = reasons[action["action_id"]]
        action.update(status="failed", failure_reason=reason)
        for target in action.get("targets", []):
            if target["status"] == "verified":
                target.update(status="failed", reason=reason, generated_text=None,
                              verification=None, previously_verified=True)
    outcome["edits"] = [e for e in outcome["edits"] if e["action_id"] not in reasons]
    outcome["records"] = [r for r in outcome["records"] if r["action_id"] not in reasons]


def _review_modified_artifacts(input_path: Path, output_dir: Path, full: Any, profile: dict,
                               ruleset: Any, model: Any, outcome: dict, evaluation: bool,
                               review_records: list[dict]) -> tuple[Any, Any, bool]:
    """Generate privately; only the exact successfully reviewed pair is exposed."""
    plan = validate_edit_plan(input_path, outcome["edits"], {}, content_check=outcome["content_check"])
    if not outcome["edits"]:
        return plan, None, False
    with tempfile.TemporaryDirectory(prefix=".v3-review-", dir=output_dir) as temporary:
        temporary_dir = Path(temporary)
        for round_number in (1, 2):
            redline = temporary_dir / "redline.docx"
            final = temporary_dir / "final.docx"
            artifacts = generate_artifacts(input_path, plan, redline, final)
            actual = inspect_docx(final, full=True)
            try:
                review = review_artifacts(full, actual, list(ruleset.actions), outcome["edits"],
                    profile, model, plan_sha256=plan.plan_sha256,
                    redline_sha256=artifacts.redline_sha256, final_sha256=artifacts.final_sha256,
                    round_number=round_number)
            except ValueError as exc:
                raise V2Error(str(exc)) from exc
            review_records.append(review)
            if review["passed"]:
                prefix = "evaluation_" if evaluation else ""
                redline.replace(output_dir / f"{prefix}redline.docx")
                final.replace(output_dir / f"{prefix}final.docx")
                return plan, artifacts, False
            rejected = {entry["action_id"]: entry["reason"] or "V3_ARTIFACT_SEMANTIC_REJECTED"
                        for entry in review["actions"] if not entry["passed"]}
            _revert_actions(outcome, rejected)
            if round_number == 2:
                _revert_actions(outcome, {edit["action_id"]: "V3_ARTIFACT_REVIEW_LIMIT"
                                         for edit in outcome["edits"]})
            plan = validate_edit_plan(input_path, outcome["edits"], {}, content_check=outcome["content_check"])
            if not outcome["edits"]:
                return plan, None, True
    return plan, None, True


def process_v2(input_path: Path, output_dir: Path, ruleset_version: str = "v2",
               gateway: ModelGateway | None = None, *, evaluation: bool | None = None) -> dict[str, Any]:
    """Run the v2 pipeline. ``evaluation=None`` follows the rule package state.

    Unreleased packages always run as evaluation (evaluation artifacts only).
    A released package runs as formal delivery. Verified modifications can be
    delivered with explicit exceptions; actual artifact review failures revoke
    actions before any modified contract becomes downloadable.
    """
    input_path, output_dir = Path(input_path), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    source_hash = _sha(input_path) if input_path.is_file() else ""
    report: dict[str, Any] = {
        "schema_version": "2", "engine_version": ENGINE_VERSION, "execution_mode": EXECUTION_MODE,
        "source_sha256": source_hash, "ruleset_version": ruleset_version, "ruleset_sha256": None,
        "qualification_status": "failed", "qualification": {"status": "failed", "evidence": None},
        "document_identity": {"status": "failed", "document_type": "unknown", "evidence": []},
        "profile": {}, "actions": [], "content_verifications": [], "actual_content_verifications": [],
        "edit_plan": {"count": 0, "sha256": None, "edits": [], "validated": False,
                      "executable": False, "reason": "EVALUATION_MODE"},
        "release_gate": {"status": "closed", "reason": "RULESET_UNRELEASED", "auto_write_actions": []},
        "delivery_status": "not_generated", "has_toc_field": None, "toc_update_status": "not_applicable",
        "output_validation": None,
        "model": {"configured_model": None, "actual_model": None, "calls": 0,
                  "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
                  "latency_ms": 0, "cost": None, "rate_limit_count": 0, "error_count": 0,
                  "prompt_versions": dict(PROMPT_VERSIONS_V2)},
        "errors": [], "error_code": None, "artifacts": {},
    }
    model = gateway
    try:
        ruleset = load_ruleset_v2(ruleset_version)
        if evaluation is None:
            evaluation = not ruleset.auto_write_enabled
        if not evaluation and not ruleset.auto_write_enabled:
            raise V2Error("V2_DELIVERY_REQUIRES_RELEASED_PACKAGE")
        mode = "evaluation" if evaluation else "delivery"
        report["execution_mode"] = mode
        report["ruleset_sha256"] = ruleset.sha256
        report["release_gate"] = {"status": "open" if not evaluation else "closed",
                                  "reason": ruleset.release_policy.get("basis"),
                                  "auto_write_actions": [action["action_id"] for action in ruleset.actions
                                                         if action["approval"]["auto_write"]]}
        minimal = inspect_docx(input_path, full=False)
        report["has_toc_field"] = minimal.has_toc_field
        report["document_identity"] = classify_document_identity(minimal)
        evidence = classify_fund_type(minimal)
        type_quote = evidence["evidence"]["quote"]
        operation_quote = evidence.get("operation_evidence", {}).get("quote", "")
        supporting = evidence.get("supporting_evidence", [])
        context = "\n".join([type_quote] + ([operation_quote] if operation_quote else []) + [e["quote"] for e in supporting])
        if len(context) > 2200:
            raise RuleError("QUALIFICATION_CONTEXT_LIMIT")
        model = gateway or ModelGateway.from_env()
        if ruleset.auto_write_enabled and not evaluation:
            # A released package only writes on the engine and model transport
            # that produced its evaluation evidence; any drift fails closed.
            # Evaluation reruns are not writes and stay available.
            from .rules import release_runtime_context
            try:
                runtime = release_runtime_context(model, None)
            except Exception as exc:  # noqa: BLE001 - converted to a fail-closed code
                raise V2Error("V2_RELEASE_CONTEXT_UNVERIFIED") from exc
            expected = ruleset.release_policy.get("evaluation_context") or {}
            if (expected.get("engine_build") != runtime["engine_build"]
                    or expected.get("model_transport_sha256") != runtime["model_transport_sha256"]
                    or expected.get("prompt_versions") != PROMPT_VERSIONS_V2):
                raise V2Error("V2_RELEASE_CONTEXT_UNVERIFIED")
        report["model"]["configured_model"] = model.model
        model_start = time.monotonic()
        try:
            result = model.extract_fund_type(context)
            report["model"].update({"actual_model": result.model, "calls": 1,
                                    "prompt_tokens": result.prompt_tokens,
                                    "completion_tokens": result.completion_tokens,
                                    "total_tokens": result.total_tokens,
                                    "latency_ms": result.latency_ms, "attempts": result.attempts,
                                    "request_id": result.request_id})
        except ModelError as exc:
            report["model"].update({"calls": model.calls, "error_count": 1,
                                    "latency_ms": round((time.monotonic() - model_start) * 1000)})
            raise
        if result.value["fund_type"] != evidence["fund_type"]:
            raise RuleError("MODEL_TYPE_CONFLICT")
        model_quote = result.value["quote"]
        if model_quote not in context or len(model_quote) < 4:
            # One bounded repair attempt: a formatting slip must not fail the
            # whole contract. The re-answer is validated against the original
            # bounded context, so it cannot invent text.
            repair_context = context + "\nquote必须逐字复制上述上下文中的连续原句，不得改写、合并或补全。"
            retry = model.extract_fund_type(repair_context)
            report["model"].update({"calls": report["model"].get("calls", 1) + 1,
                                    "prompt_tokens": report["model"].get("prompt_tokens", 0) + retry.prompt_tokens,
                                    "completion_tokens": report["model"].get("completion_tokens", 0) + retry.completion_tokens,
                                    "total_tokens": report["model"].get("total_tokens", 0) + retry.total_tokens,
                                    "latency_ms": report["model"].get("latency_ms", 0) + retry.latency_ms,
                                    "request_id": retry.request_id})
            if retry.value["fund_type"] != evidence["fund_type"]:
                raise RuleError("MODEL_TYPE_CONFLICT")
            model_quote = retry.value["quote"]
            if model_quote not in context or len(model_quote) < 4:
                raise RuleError("MODEL_EVIDENCE_INVALID")
        report["model"]["quote_verification"] = "verified_against_bounded_context"
        report["qualification"] = {"status": "eligible", "fund_type": evidence["fund_type"],
                                   "evidence": evidence["evidence"],
                                   "operation_evidence": evidence.get("operation_evidence"),
                                   "supporting_evidence": supporting,
                                   "model_quote": model_quote, "model_verification": "verified"}
        if evidence["fund_type"] in {"etf", "interbank_cd", "money_market", "other_excluded"}:
            report["qualification_status"] = "excluded_by_fund_type"
            report["qualification"]["status"] = "excluded_by_fund_type"
            return report
        report["qualification_status"] = "eligible"
        full = inspect_docx(input_path, full=True)
        report["has_toc_field"] = full.has_toc_field
        report["toc_update_status"] = "not_updated" if full.has_toc_field else "not_applicable"
        report["profile"] = resolve_profile(full, model)
        outcome = plan_v2(full, report["profile"], ruleset, model,
                          engine_build_value=engine_build())
        report["actions"] = outcome["actions"]
        plan, reviewed_artifacts, review_blocked = _review_modified_artifacts(
            input_path, output_dir, full, report["profile"], ruleset, model, outcome, evaluation,
            report["actual_content_verifications"])
        report["content_verifications"] = outcome["records"]
        edits = outcome["edits"]
        report["edit_plan"] = {"count": len(edits), "sha256": plan.plan_sha256, "edits": edits,
                               "validated": True, "executable": not evaluation and not review_blocked,
                               "reason": "DELIVERY_MODE" if not evaluation else "EVALUATION_MODE",
                               "boundary_policy": "trim-inline-whitespace-sentence-span-v1"}
        if review_blocked:
            report["edit_plan"].update(executable=False, reason="V3_ARTIFACT_REVIEW_REJECTED")
        (output_dir / "edits.json").write_text(json.dumps(report["edit_plan"], ensure_ascii=False, indent=2),
                                               encoding="utf-8")
        failed_actions = [action for action in report["actions"]
                          if action["status"] in {"failed", "partial", "not_matched"}]
        # Every failure in this engine is a fail-closed refusal: nothing is ever
        # written for a failed action. Delivery therefore publishes the verified
        # edits together with an explicit exception list instead of withholding
        # the whole contract (see docs/DELIVERY_STATUS_POLICY.md).
        report["exceptions"] = [{"action_id": action["action_id"], "reason": action.get("failure_reason"),
                                 "description": action.get("description")} for action in failed_actions]
        if review_blocked:
            report["edit_plan"].update(executable=False, reason="V3_ARTIFACT_REVIEW_REJECTED")
            report["delivery_status"] = "incomplete"
            return report
        if evaluation:
            if edits:
                redline, final = output_dir / "evaluation_redline.docx", output_dir / "evaluation_final.docx"
                artifacts = reviewed_artifacts
                report["output_validation"] = {
                    "kind": "evaluated_edits",
                    "checks": [*artifacts.checks, "actual_content_verification"],
                    "redline_sha256": artifacts.redline_sha256, "final_sha256": artifacts.final_sha256,
                    "not_a_final_contract": True,
                }
                report["artifacts"] = {"evaluation_redline": str(redline), "evaluation_final": str(final)}
                report["delivery_status"] = "evaluation_modified_with_exceptions" if failed_actions else "evaluation_modified"
            else:
                redline, final = output_dir / "evaluation_redline.docx", output_dir / "evaluation_final.docx"
                artifacts = generate_noop_evaluation_artifacts(input_path, redline, final)
                report["output_validation"] = {
                    "kind": "evaluated_zero_edit",
                    "checks": list(artifacts.checks),
                    "redline_sha256": artifacts.redline_sha256, "final_sha256": artifacts.final_sha256,
                    "not_a_final_contract": True,
                }
                report["artifacts"] = {"evaluation_redline": str(redline), "evaluation_final": str(final)}
                report["delivery_status"] = "incomplete" if failed_actions else "evaluation_unmodified"
        else:
            # Formal delivery: verified edits are published together with the
            # exception list; only a set with no edits and failed actions is
            # withheld (nothing to deliver and known gaps).
            if edits:
                redline, final = output_dir / "redline.docx", output_dir / "final.docx"
                artifacts = reviewed_artifacts
                report["output_validation"] = {
                    "kind": "validated_edits",
                    "checks": [*artifacts.checks, "actual_content_verification"],
                    "redline_sha256": artifacts.redline_sha256, "final_sha256": artifacts.final_sha256,
                }
                report["artifacts"] = {"redline": str(redline), "final": str(final)}
                report["delivery_status"] = "complete_with_exceptions" if failed_actions else "complete"
            elif not failed_actions:
                redline, final = output_dir / "redline.docx", output_dir / "final.docx"
                artifacts = generate_unchanged_artifacts(input_path, plan, redline, final)
                report["output_validation"] = {
                    "kind": "validated_unchanged",
                    "checks": list(artifacts.checks),
                    "redline_sha256": artifacts.redline_sha256, "final_sha256": artifacts.final_sha256,
                    "byte_identical_to_source": artifacts.final_sha256 == source_hash,
                }
                report["artifacts"] = {"redline": str(redline), "final": str(final)}
                report["delivery_status"] = "complete"
            else:
                report["delivery_status"] = "incomplete"
        return report
    except (DocxError, RuleError, RuleV2Error, V2Error, ModelError, OSError) as exc:
        code = getattr(exc, "code", "OUTPUT_IO_ERROR")
        if getattr(exc, "details", {}).get("document_identity"):
            report["document_identity"] = exc.details["document_identity"]
        report["error_code"] = code
        report["errors"].append({"code": code, "stage": "v2_processing", "message": code})
        for action in report["actions"]:
            reverted = False
            for target in action.get("targets", []):
                if target["status"] == "verified":
                    target.update(status="failed", reason=code, generated_text=None, verification=None)
                    reverted = True
            if reverted or action.get("status") in {"applied", "partial"}:
                action.update(status="failed", failure_reason=code)
        report["edit_plan"].update(executable=False, reason=code)
        if report["qualification_status"] != "eligible":
            report["qualification_status"] = "failed"
            report["qualification"]["status"] = "failed"
        report["delivery_status"] = "not_generated"
        return report
    finally:
        if 'model' in locals() and hasattr(model, 'metrics'):
            report["model"].update(model.metrics())
        if gateway is None and 'model' in locals() and hasattr(model, 'close'):
            model.close()
        report["duration_ms"] = round((time.monotonic() - started) * 1000)
        _write_v2_markdown(output_dir / "report.md", report)
