"""Loader for the executable v2 semantic rule package.

The v2 package is evaluation-only until a separate offline release act happens.
The loader rejects any package that claims auto-write or approved state, and it
refuses unknown check kinds so that every requirement stays code-verifiable.
"""

from __future__ import annotations

import hashlib
import json
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
GENERATION_MODES = {"delete", "generate"}
CHECK_KINDS = {
    "delete_only",
    "contains_all",
    "not_contains",
    "no_digits_and_no_conditions",
    "direct_sales_clause",
    "classes_within_profile_and_no_digits",
    "boundary_scope",
    "semantic_review",
}
VERIFICATIONS = {"code", "code+model", "model"}


@dataclass(frozen=True)
class RuleSetV2:
    version: str
    sha256: str
    actions: tuple[dict[str, Any], ...]
    release_policy: dict[str, Any]

    @property
    def auto_write_enabled(self) -> bool:
        return False

    def by_id(self, action_id: str) -> dict[str, Any]:
        for action in self.actions:
            if action["action_id"] == action_id:
                return action
        raise RuleV2Error("V2_ACTION_NOT_FOUND")


def _validate_action(action: dict[str, Any], known_ids: set[str]) -> None:
    required = {"rule_id", "action_id", "description", "section_anchor", "subsection_anchor",
                "regions", "scope", "operation", "condition", "approval", "semantics",
                "locate", "generation", "requirements", "model_verification", "source_provenance"}
    if not required.issubset(action):
        raise RuleV2Error("V2_SCHEMA_INVALID", {"action": action.get("action_id")})
    if action["action_id"] in known_ids:
        raise RuleV2Error("V2_ACTION_DUPLICATE")
    approval = action["approval"]
    if not isinstance(approval, dict) or approval.get("auto_write") is not False or approval.get("approved") is not False:
        # v2 is evaluation-only; enabling writes requires a separate release act
        # with preregistered evidence. Editing this flag cannot enable writes.
        raise RuleV2Error("V2_RELEASE_NOT_SEPARATE")
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


def load_ruleset_v2(version: str = "v2") -> RuleSetV2:
    if version != "v2":
        raise RuleV2Error("V2_RULESET_NOT_FOUND")
    path = Path(__file__).resolve().parent.parent / "rules" / f"rules_{version}.json"
    if not path.is_file():
        raise RuleV2Error("V2_RULESET_NOT_FOUND")
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
        if data.get("version") != "v2" or data.get("schema_version") != "2":
            raise RuleV2Error("V2_RULESET_INVALID")
        policy = data.get("release_policy") or {}
        if policy.get("auto_write_enabled") is not False or policy.get("status") != "unreleased":
            raise RuleV2Error("V2_RELEASE_NOT_SEPARATE")
        actions = data.get("actions")
        if not isinstance(actions, list) or not actions:
            raise RuleV2Error("V2_RULESET_INVALID")
        known: set[str] = set()
        for action in actions:
            _validate_action(action, known)
            known.add(action["action_id"])
        return RuleSetV2("v2", hashlib.sha256(raw).hexdigest(), tuple(actions), policy)
    except RuleV2Error:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuleV2Error("V2_RULESET_INVALID") from exc
