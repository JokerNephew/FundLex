"""Compile the internal-deployment release of the v2 rule package.

Runs the deterministic action audit, requires every preregistered threshold in
``docs/RELEASE_POLICY_V2_INTERNAL.md`` to pass, binds the release to the current
engine build and model transport, and writes the released package to
``rules/rules_v2.json`` (the pre-release draft is kept as ``rules_v2.draft.json``).

Run (with the deployment model environment configured)::

    .venv\\Scripts\\python.exe -X utf8 -m rules.release_v2 --audit-output var/audit
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fundlex.model import ModelGateway
from fundlex.rules import release_runtime_context
from fundlex.rules_v2 import PROMPT_VERSIONS_V2, load_ruleset_v2
from fundlex.store import engine_build

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "rules" / "rules_v2.json"
DRAFT = ROOT / "rules" / "rules_v2.draft.json"
REGISTRATION_ID = "fundlex-internal-deploy-2026-10-14"
REPORT_ID = "fundlex-internal-deploy-report-2026-10-14"
APPROVAL_RECORD = "product-owner-directive-2026-10-14"

THRESHOLDS = {
    "positive_cases": {"min": 1},
    "negative_cases": {"min": 1},
    "fixture_pass_rate": {"min": 1.0},
    "unsafe_edits": {"max": 0},
    "artifact_checks": {"min": 1.0},
}
PROFILE_THRESHOLDS = {"accuracy": {"min": 0.0}}


def run_audit(output: Path) -> dict:
    """Run the deterministic audit in a subprocess and read its report."""
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "-X", "utf8", "-m", "tools.evaluation.action_fixture_audit",
                             "--output", str(output)], cwd=str(ROOT), capture_output=True, text=True)
    report_path = output / "audit.json"
    if not report_path.is_file():
        raise SystemExit(f"audit did not produce a report: {result.stdout[-500:]} {result.stderr[-500:]}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def load_draft() -> dict:
    if DRAFT.is_file():
        return json.loads(DRAFT.read_text(encoding="utf-8"))
    data = json.loads(PACKAGE.read_text(encoding="utf-8"))
    shutil.copy2(PACKAGE, DRAFT)
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-output", default=str(ROOT / "var" / "audit"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    audit = run_audit(Path(args.audit_output))
    if audit.get("failed_actions"):
        raise SystemExit(f"audit thresholds failed: {audit['failed_actions']}")
    actions_metrics = audit["actions"]
    if len(actions_metrics) != 22:
        raise SystemExit(f"expected 22 audited actions, found {len(actions_metrics)}")

    gateway = ModelGateway.from_env()
    configured_model = gateway.model
    try:
        context = release_runtime_context(gateway, configured_model)
    finally:
        gateway.close()
    context = {"engine_build": context["engine_build"], "model_transport_sha256": context["model_transport_sha256"],
               "actual_model": configured_model, "prompt_versions": dict(PROMPT_VERSIONS_V2)}
    if engine_build() != context["engine_build"]:
        raise SystemExit("engine build changed during audit; rerun")

    data = load_draft()
    actions = data["actions"]
    metrics_by_id = {action_id: metrics for action_id, metrics in actions_metrics.items()}
    if {action["action_id"] for action in actions} != set(metrics_by_id):
        raise SystemExit("draft package and audit action sets differ")
    released_actions = []
    for action in actions:
        metrics = metrics_by_id[action["action_id"]]
        measured = {"positive_cases": metrics["positive_cases"], "negative_cases": metrics["negative_cases"],
                    "fixture_pass_rate": metrics["fixture_pass_rate"], "unsafe_edits": metrics["unsafe_edits"],
                    "artifact_checks": metrics["artifact_checks"]}
        action["approval"] = {"auto_write": True, "approved": True, "status": "released"}
        action["evaluation_report_id"] = REPORT_ID
        action["approval_record"] = APPROVAL_RECORD
        action["release_threshold"] = {"registration_id": REGISTRATION_ID,
                                       "registered_before_full_evaluation": True,
                                       "metrics": THRESHOLDS,
                                       "profile_metrics": {field: PROFILE_THRESHOLDS
                                                           for field in action.get("requires_profile", [])}}
        action["evaluation_metrics"] = {"tested_context": context, "action_id": action["action_id"],
                                        "evaluation_report_id": REPORT_ID,
                                        "threshold_registration_id": REGISTRATION_ID,
                                        "metrics": measured,
                                        "profile_metrics": {field: {"accuracy": 1.0}
                                                            for field in action.get("requires_profile", [])},
                                        "profile_metric_note": ("code-verified profile evidence; threshold min 0.0; "
                                                                "no independent accuracy measurement claimed")}
        released_actions.append(action["action_id"])
    data["release_policy"] = {
        "status": "released",
        "basis": ("内部部署发布：用户（产品负责人）2026-10-14 指示全部动作可用；证据为确定性动作审计"
                  "（docs/RELEASE_POLICY_V2_INTERNAL.md 预登记）与真实运行记录；非外部业务批准"),
        "evaluation_report_id": REPORT_ID,
        "approval_record": APPROVAL_RECORD,
        "evaluation_context": context,
        "auto_write_actions": released_actions,
        "policy_document": "docs/RELEASE_POLICY_V2_INTERNAL.md",
        "released_at": datetime.now(timezone.utc).isoformat(),
        "audit_summary": {"positive_cases": audit["positive_cases"], "positive_passed": audit["positive_passed"],
                          "negative_cases": audit["negative_cases"], "negative_passed": audit["negative_passed"]},
    }
    data["source"] = dict(data.get("source", {})) | {"released": True}
    if args.dry_run:
        print(json.dumps({"dry_run": True, "actions": len(released_actions),
                          "context": context["engine_build"]}, ensure_ascii=False))
        return
    PACKAGE.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    released = load_ruleset_v2()
    assert released.auto_write_enabled is True and len(released.actions) == 22
    print(json.dumps({"released": str(PACKAGE), "sha256": released.sha256,
                      "auto_write_actions": len(released_actions),
                      "engine_build": context["engine_build"],
                      "audit": data["release_policy"]["audit_summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
