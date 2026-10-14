"""Loader for the executable v2 semantic rule package.

An unreleased package cannot enable writes. A released package must carry, for
every auto-write action, the same evidence the v1 gate requires (evaluation
report, approval record, preregistered thresholds and measured results), so the
write switches cannot be flipped by editing a boolean.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RuleV2Error(ValueError):
    def __init__(self, code: str, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


PROMPT_VERSIONS_V2 = {
    "fund_type": "fund_type_v3",
    "profile": "profile_v3",
    "locate": "v2_locate_v1",
    "generate": "v2_generate_v1",
    "verify": "v2_verify_v1",
}

LOCATE_MODES = {"code_literal", "code_recognition", "model_assisted", "class_definition"}
GENERATION_MODES = {"delete", "generate", "template"}
CHECK_KINDS = {
    "delete_only",
    "contains_all",
    "not_contains",
    "no_digits_and_no_conditions",
    "direct_sales_clause",
    "classes_within_profile_and_no_digits",
    "boundary_scope",
    "semantic_review",
    "template_exact",
}
SLOT_GROUPS = {"subscription_group", "service_group"}


def _valid_slots(slots: Any) -> bool:
    return (isinstance(slots, dict) and bool(slots)
            and all(isinstance(token, str) and token and group in SLOT_GROUPS
                    for token, group in slots.items()))
VERIFICATIONS = {"code", "code+model", "model"}


@dataclass(frozen=True)
class RuleSetV2:
    version: str
    sha256: str
    actions: tuple[dict[str, Any], ...]
    release_policy: dict[str, Any]

    @property
    def auto_write_enabled(self) -> bool:
        return any(action["approval"].get("auto_write") is True for action in self.actions)

    def by_id(self, action_id: str) -> dict[str, Any]:
        for action in self.actions:
            if action["action_id"] == action_id:
                return action
        raise RuleV2Error("V2_ACTION_NOT_FOUND")


def _validate_released_action(action: dict[str, Any], policy: dict[str, Any]) -> None:
    """A released auto-write action must carry the same evidence the v1 gate requires.

    The evidence is produced outside this repository (evaluation report + approval
    record + preregistered thresholds). Editing a boolean cannot bypass it.
    """
    approval = action["approval"]
    if approval.get("approved") is not True:
        raise RuleV2Error("V2_RELEASE_EVIDENCE_MISSING", {"action": action["action_id"]})
    if not policy.get("evaluation_report_id") or not policy.get("approval_record") \
            or not action.get("evaluation_report_id") or not action.get("approval_record"):
        raise RuleV2Error("V2_RELEASE_EVIDENCE_MISSING", {"action": action["action_id"]})
    threshold, actual = action.get("release_threshold"), action.get("evaluation_metrics")
    if not isinstance(threshold, dict) or threshold.get("registration_id") is None \
            or threshold.get("registered_before_full_evaluation") is not True or not isinstance(actual, dict):
        raise RuleV2Error("V2_RELEASE_EVIDENCE_MISSING", {"action": action["action_id"]})
    context = policy.get("evaluation_context")
    if not isinstance(context, dict) or any(
            not isinstance(context.get(key), str) or not re.fullmatch(r"[0-9a-f]{64}", context[key])
            for key in ("engine_build", "model_transport_sha256")):
        raise RuleV2Error("V2_RELEASE_CONTEXT_UNVERIFIED")
    if not isinstance(context.get("actual_model"), str) or not context["actual_model"] \
            or context.get("prompt_versions") != PROMPT_VERSIONS_V2:
        raise RuleV2Error("V2_RELEASE_CONTEXT_UNVERIFIED")
    if actual.get("tested_context") != context or actual.get("action_id") != action["action_id"] \
            or actual.get("evaluation_report_id") != action.get("evaluation_report_id") \
            or actual.get("threshold_registration_id") != threshold.get("registration_id"):
        raise RuleV2Error("V2_RELEASE_EVIDENCE_MISSING", {"action": action["action_id"]})

    def check(gates: Any, measured: Any, where: str) -> None:
        if not isinstance(gates, dict) or not gates or not isinstance(measured, dict):
            raise RuleV2Error("V2_RELEASE_METRICS_MISSING", {"where": where})
        for name, bounds in gates.items():
            value = measured.get(name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise RuleV2Error("V2_RELEASE_METRICS_MISSING", {"where": where, "metric": name})
            if not isinstance(bounds, dict) or not bounds or not set(bounds).issubset({"min", "max"}):
                raise RuleV2Error("V2_RELEASE_THRESHOLD_INVALID", {"where": where, "metric": name})
            for operator, target in bounds.items():
                if not isinstance(target, (int, float)) or isinstance(target, bool) or not math.isfinite(target):
                    raise RuleV2Error("V2_RELEASE_THRESHOLD_INVALID", {"where": where, "metric": name})
                if (operator == "min" and value < target) or (operator == "max" and value > target):
                    raise RuleV2Error("V2_RELEASE_METRIC_BELOW_THRESHOLD", {"where": where, "metric": name})

    check(threshold.get("metrics"), actual.get("metrics"), action["action_id"])
    dependencies = threshold.get("profile_metrics", {})
    if set(dependencies) != set(action.get("requires_profile", [])):
        raise RuleV2Error("V2_RELEASE_PROFILE_GATES_MISSING", {"action": action["action_id"]})
    for field, gates in dependencies.items():
        check(gates, (actual.get("profile_metrics") or {}).get(field), f"{action['action_id']}:{field}")


def _validate_action(action: dict[str, Any], known_ids: set[str]) -> None:
    required = {"rule_id", "action_id", "description", "section_anchor", "subsection_anchor",
                "regions", "scope", "operation", "condition", "approval", "semantics",
                "locate", "generation", "requirements", "model_verification", "source_provenance"}
    if not required.issubset(action):
        raise RuleV2Error("V2_SCHEMA_INVALID", {"action": action.get("action_id")})
    if action["action_id"] in known_ids:
        raise RuleV2Error("V2_ACTION_DUPLICATE")
    approval = action["approval"]
    if not isinstance(approval, dict) or not {"auto_write", "approved"}.issubset(approval) \
            or not isinstance(approval.get("auto_write"), bool) or not isinstance(approval.get("approved"), bool):
        raise RuleV2Error("V2_APPROVAL_INVALID", {"action": action.get("action_id")})
    if action["scope"] not in {"phrase", "sentence", "paragraph", "clause"}:
        raise RuleV2Error("V2_SCOPE_INVALID")
    if action["operation"] not in {"replace", "delete", "append"}:
        raise RuleV2Error("V2_OPERATION_INVALID")
    if not set(action["regions"]).issubset({"body", "summary"}):
        raise RuleV2Error("V2_REGION_INVALID")
    semantics = action["semantics"]
    for key in ("subject", "action", "condition", "allowed_changes", "must_preserve",
                "forbidden_additions", "unsupported"):
        if key not in semantics or semantics[key] in (None, "", []):
            raise RuleV2Error("V2_SEMANTICS_INCOMPLETE", {"action": action["action_id"], "field": key})
    locate, generation = action["locate"], action["generation"]
    if not isinstance(locate, dict) or locate.get("mode") not in LOCATE_MODES:
        raise RuleV2Error("V2_LOCATE_MODE_INVALID")
    if locate["mode"] == "code_literal" and not locate.get("triggers"):
        raise RuleV2Error("V2_LOCATE_TRIGGERS_MISSING")
    if locate.get("slots") is not None and not _valid_slots(locate.get("slots")):
        raise RuleV2Error("V2_SLOT_GROUPS_INVALID", {"action": action["action_id"]})
    if locate["mode"] == "code_recognition" and locate.get("recognition_kind") not in {"conversion_prohibition", "short_holding_redemption"}:
        raise RuleV2Error("V2_RECOGNITION_KIND_INVALID")
    if locate["mode"] == "model_assisted":
        for key in ("instruction", "start_prefixes", "min_chars", "max_chars"):
            if not locate.get(key):
                raise RuleV2Error("V2_LOCATE_CONTRACT_INCOMPLETE", {"field": key})
    if not isinstance(generation, dict) or generation.get("mode") not in GENERATION_MODES:
        raise RuleV2Error("V2_GENERATION_MODE_INVALID")
    if generation["mode"] == "generate":
        if not generation.get("instruction") or not generation.get("max_chars"):
            raise RuleV2Error("V2_GENERATION_CONTRACT_INCOMPLETE")
        if generation.get("kind") not in {"direct_sales_clause", "redemption_fee_ownership"}:
            raise RuleV2Error("V2_GENERATION_KIND_INVALID")
        # Reference text is guidance only; it must not carry A/C slot tokens
        # that would gate writes (TEMPLATE_VARIANT_UNNAPROVED in v1).
        if "template_slots" in generation:
            raise RuleV2Error("V2_TEMPLATE_SLOTS_UNSUPPORTED")
    if generation["mode"] == "template":
        if not generation.get("template_text") or not generation.get("max_chars"):
            raise RuleV2Error("V2_GENERATION_CONTRACT_INCOMPLETE")
        if action["operation"] != "replace":
            raise RuleV2Error("V2_TEMPLATE_OPERATION_INVALID")
        if generation.get("slots") is not None and not _valid_slots(generation.get("slots")):
            raise RuleV2Error("V2_SLOT_GROUPS_INVALID", {"action": action["action_id"]})
    requirements = action["requirements"]
    if not isinstance(requirements, list) or not requirements:
        raise RuleV2Error("V2_REQUIREMENTS_MISSING")
    ids = [item.get("id") for item in requirements]
    if len(set(ids)) != len(ids) or any(not isinstance(item, str) or not item for item in ids):
        raise RuleV2Error("V2_REQUIREMENT_IDS_INVALID")
    for item in requirements:
        check = item.get("check") or {}
        if check.get("kind") not in CHECK_KINDS or item.get("verification") not in VERIFICATIONS:
            raise RuleV2Error("V2_REQUIREMENT_CHECK_INVALID", {"id": item.get("id")})
        if not item.get("text"):
            raise RuleV2Error("V2_REQUIREMENT_TEXT_MISSING", {"id": item.get("id")})
    by_requirement = {item["id"]: item for item in requirements}
    for requirement_id in action["model_verification"]:
        item = by_requirement.get(requirement_id)
        if item is None or item["verification"] not in {"model", "code+model"}:
            raise RuleV2Error("V2_MODEL_VERIFICATION_INVALID", {"id": requirement_id})
    if generation["mode"] == "delete":
        if action["operation"] != "delete" or any(item["check"]["kind"] != "delete_only"
                                                  and item["check"]["kind"] != "boundary_scope" for item in requirements):
            raise RuleV2Error("V2_DELETE_CONTRACT_INVALID")
    if generation["mode"] == "template" and not any(item["check"]["kind"] == "template_exact"
                                                    for item in requirements):
        raise RuleV2Error("V2_TEMPLATE_CHECK_MISSING")


def load_ruleset_v2(version: str = "v2", *, path: Path | None = None) -> RuleSetV2:
    if version != "v2":
        raise RuleV2Error("V2_RULESET_NOT_FOUND")
    path = path or Path(__file__).resolve().parent.parent / "rules" / f"rules_{version}.json"
    if not path.is_file():
        raise RuleV2Error("V2_RULESET_NOT_FOUND")
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
        if data.get("version") != "v2" or data.get("schema_version") != "2":
            raise RuleV2Error("V2_RULESET_INVALID")
        policy = data.get("release_policy") or {}
        status = policy.get("status")
        if status not in {"unreleased", "released"}:
            raise RuleV2Error("V2_RELEASE_NOT_SEPARATE")
        if status == "unreleased" and policy.get("auto_write_enabled") is not False:
            raise RuleV2Error("V2_RELEASE_NOT_SEPARATE")
        actions = data.get("actions")
        if not isinstance(actions, list) or not actions:
            raise RuleV2Error("V2_RULESET_INVALID")
        known: set[str] = set()
        for action in actions:
            _validate_action(action, known)
            known.add(action["action_id"])
        if status == "unreleased":
            for action in actions:
                approval = action["approval"]
                if approval["auto_write"] or approval["approved"]:
                    # A release is a separate, explicit offline act with evidence.
                    raise RuleV2Error("V2_RELEASE_NOT_SEPARATE", {"action": action["action_id"]})
        else:
            if set(policy.get("auto_write_actions", [])) != {a["action_id"] for a in actions if a["approval"]["auto_write"]}:
                raise RuleV2Error("V2_RELEASE_EVIDENCE_MISSING", {"field": "auto_write_actions"})
            for action in actions:
                if action["approval"]["auto_write"]:
                    _validate_released_action(action, policy)
                elif action["approval"]["approved"]:
                    raise RuleV2Error("V2_APPROVAL_INCONSISTENT", {"action": action["action_id"]})
        return RuleSetV2("v2", hashlib.sha256(raw).hexdigest(), tuple(actions), policy)
    except RuleV2Error:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuleV2Error("V2_RULESET_INVALID") from exc
