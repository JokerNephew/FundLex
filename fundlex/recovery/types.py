"""Shared recovery types (plan §17–§19)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class FailureClass(str, Enum):
    FACT = "FACT"
    APPLICABILITY = "APPLICABILITY"
    TARGET = "TARGET"
    GENERATION = "GENERATION"
    EXECUTION = "EXECUTION"
    VERIFICATION = "VERIFICATION"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    RESOURCE = "RESOURCE"


class RecoveryAction(str, Enum):
    RETRY_DETERMINISTIC = "RETRY_DETERMINISTIC"
    FOCUSED_FACT_RESOLVE = "FOCUSED_FACT_RESOLVE"
    FACT_ARBITRATION = "FACT_ARBITRATION"
    APPLICABILITY_ARBITRATION = "APPLICABILITY_ARBITRATION"
    LLM_LOCATE = "LLM_LOCATE"
    LLM_COMPOSE = "LLM_COMPOSE"
    JOINT_COMPOSE = "JOINT_COMPOSE"
    REBUILD_PLAN = "REBUILD_PLAN"
    REGENERATE_ARTIFACT = "REGENERATE_ARTIFACT"
    SPLIT_CONTEXT = "SPLIT_CONTEXT"
    PAUSE_RESUME = "PAUSE_RESUME"
    MARK_UNRESOLVED = "MARK_UNRESOLVED"


#: Internal error code → business failure class.  Unlisted codes are classified by
#: prefix; the fallback is ``VERIFICATION`` (never a silent business retry).
FAILURE_CODE_MAP: dict[str, FailureClass] = {
    "RECALL_FACT_UNVERIFIED": FailureClass.FACT,
    "FUND_TYPE_QUOTE_UNVERIFIED": FailureClass.FACT,
    "FUND_TYPE_UNVERIFIED": FailureClass.FACT,
    "FUND_TYPE_EVIDENCE_MISSING": FailureClass.FACT,
    "FUND_TYPE_EVIDENCE_INVALID": FailureClass.FACT,
    "FUND_TYPE_EVIDENCE_AMBIGUOUS": FailureClass.FACT,
    "FUND_TYPE_EVIDENCE_CONFLICT": FailureClass.FACT,
    "FUND_TYPE_INVESTMENT_EVIDENCE_MISSING": FailureClass.FACT,
    "FUND_TYPE_INVESTMENT_EVIDENCE_CONFLICT": FailureClass.FACT,
    "FUND_TYPE_CD_MANDATE_EVIDENCE_MISSING": FailureClass.FACT,
    "FUND_TYPE_OPERATION_EVIDENCE_INVALID": FailureClass.FACT,
    "MODEL_EVIDENCE_INVALID": FailureClass.FACT,
    "MODEL_EVIDENCE_UNKNOWN": FailureClass.FACT,
    "MODEL_TYPE_CONFLICT": FailureClass.FACT,
    "RECALL_TARGET_UNRESOLVED": FailureClass.TARGET,
    "RECALL_TARGET_REBIND_FAILED": FailureClass.TARGET,
    "RECALL_TARGET_STRUCTURE": FailureClass.TARGET,
    "RECALL_TARGET_COMPOSITE_UNRESOLVED": FailureClass.TARGET,
    "RECALL_TARGET_VARIANT_UNMATCHED": FailureClass.GENERATION,
    "RECALL_SLOT_UNRESOLVED": FailureClass.GENERATION,
    "RECALL_COMPOSE_EMPTY": FailureClass.GENERATION,
    "RECALL_COMPOSE_DELETE_ADDED_TEXT": FailureClass.GENERATION,
    "RECALL_COMPOSE_DELETE_NOT_SHRINKING": FailureClass.GENERATION,
    "RECALL_COMPOSE_FIXED_TEXT_MISSING": FailureClass.GENERATION,
    "RECALL_COMPOSE_NEW_NUMBERS": FailureClass.GENERATION,
    "RECALL_COMPOSE_UNVERIFIED": FailureClass.GENERATION,
    "RECALL_COMPOSE_CONTEXT_LIMIT": FailureClass.RESOURCE,
    "RECALL_COMPOSE_BUDGET_EXHAUSTED": FailureClass.RESOURCE,
    "RECALL_EDIT_CONTENT_UNVERIFIED": FailureClass.GENERATION,
    "RECALL_EDIT_OVERLAP": FailureClass.GENERATION,
    "RECALL_EDIT_NOT_EXECUTABLE": FailureClass.EXECUTION,
    "OUTPUT_IO_ERROR": FailureClass.EXECUTION,
    "OUTPUT_PATH_INVALID": FailureClass.EXECUTION,
    "LEDGER_MISSING": FailureClass.EXECUTION,
    "CLAIM_LOCATION_MISSING": FailureClass.TARGET,
    "CLAIM_NO_CHANGE_APPLIED": FailureClass.EXECUTION,
    "CLAIM_REPLACEMENT_MISSING": FailureClass.EXECUTION,
    "CLAIM_VALIDATION_FAILED": FailureClass.VERIFICATION,
    "CLAIM_REPLAY_FAILED": FailureClass.VERIFICATION,
    "CLAIM_OPERATION_NOT_PLANNED": FailureClass.TARGET,
    "CLAIM_PLANNED_EFFECT_MISSING": FailureClass.EXECUTION,
    "CLAIM_EXECUTION_EFFECT_MISSING": FailureClass.EXECUTION,
    "CLAIM_OPERATION_UNPROVEN": FailureClass.TARGET,
    "CLAIM_OPERATION_UNATTRIBUTED": FailureClass.TARGET,
    "CLAIM_OPERATION_KEYS_INVALID": FailureClass.TARGET,
    "RECALL_PLAN_COMPONENT_DROPPED": FailureClass.GENERATION,
    "RECOVERY_NO_PROGRESS": FailureClass.EXECUTION,
    "CLAIM_UNEXPECTED_PARAGRAPH": FailureClass.EXECUTION,
    "RESIDUAL_OLD_TEXT": FailureClass.GENERATION,
    "DUPLICATE_SITE_UNEDITED": FailureClass.TARGET,
    "RECALL_AUDIT_CONTEXT_LIMIT": FailureClass.RESOURCE,
    "RECALL_INVENTORY_CONTEXT_LIMIT": FailureClass.RESOURCE,
    "RECALL_SCOPE_CONTEXT_LIMIT": FailureClass.RESOURCE,
    "RECALL_SWEEP_CONTEXT_LIMIT": FailureClass.RESOURCE,
    "SWEEP_CHUNK_LIMIT": FailureClass.RESOURCE,
    "RECALL_DELIVERY_NOT_COMPLETE": FailureClass.VERIFICATION,
    "RECALL_DELIVERY_NOT_INCOMPLETE": FailureClass.VERIFICATION,
    "MODEL_HTTP_ERROR": FailureClass.INFRASTRUCTURE,
    "MODEL_NETWORK_ERROR": FailureClass.INFRASTRUCTURE,
    "MODEL_RETRY_EXHAUSTED": FailureClass.INFRASTRUCTURE,
    "MODEL_LEDGER_UNAVAILABLE": FailureClass.INFRASTRUCTURE,
    "MODEL_CHECKPOINT_UNAVAILABLE": FailureClass.INFRASTRUCTURE,
    "MODEL_CONFIG_MISSING": FailureClass.INFRASTRUCTURE,
    "MODEL_CIRCUIT_OPEN": FailureClass.INFRASTRUCTURE,
    "MODEL_CONCURRENCY_LIMIT": FailureClass.INFRASTRUCTURE,
    "MODEL_RESERVATION_EXPIRED": FailureClass.INFRASTRUCTURE,
    "MODEL_CALL_BUDGET_EXCEEDED": FailureClass.RESOURCE,
    "MODEL_COST_BUDGET_EXCEEDED": FailureClass.RESOURCE,
    "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED": FailureClass.RESOURCE,
    "MODEL_OUTPUT_TRUNCATED": FailureClass.RESOURCE,
    "MODEL_RESPONSE_LIMIT": FailureClass.RESOURCE,
    # Validator finding codes (plan §15.2, §17).
    "MISSING_REQUIRED_TERM": FailureClass.GENERATION,
    "OUTSIDE_SPAN_CHANGED": FailureClass.GENERATION,
    "UNAUTHORIZED_NUMBER": FailureClass.GENERATION,
    "LOST_PROTECTED_LITERAL": FailureClass.GENERATION,
    "UNEXPLAINED_HARD": FailureClass.GENERATION,
    "TARGET_SOURCE_MISMATCH": FailureClass.TARGET,
    "STRUCTURE_UNSAFE": FailureClass.GENERATION,
    "COMPONENT_MISSING": FailureClass.GENERATION,
    "COMPONENT_OUTSIDE_SITE": FailureClass.GENERATION,
    "TOPIC_LOST": FailureClass.GENERATION,
    "REVIEW_FAILED": FailureClass.VERIFICATION,
    "APPLICABILITY_UNKNOWN": FailureClass.APPLICABILITY,
    "APPLICABILITY_CONFLICT": FailureClass.APPLICABILITY,
}

_PREFIX_CLASSES = (
    ("FUND_TYPE_", FailureClass.FACT),
    ("MODEL_", FailureClass.INFRASTRUCTURE),
    ("APPLICABILITY_", FailureClass.APPLICABILITY),
    ("CLAIM_", FailureClass.VERIFICATION),
    ("SWEEP_", FailureClass.VERIFICATION),
    ("RECALL_TARGET_", FailureClass.TARGET),
    ("RECALL_FACT_", FailureClass.FACT),
    ("RECALL_COMPOSE_", FailureClass.GENERATION),
    ("RECALL_EDIT_", FailureClass.GENERATION),
    ("RECALL_SCOPE_", FailureClass.RESOURCE),
    ("RECALL_INVENTORY_", FailureClass.RESOURCE),
    ("RECALL_AUDIT_", FailureClass.RESOURCE),
    ("RECALL_SWEEP_", FailureClass.RESOURCE),
)


def classify(code: str, *, default: FailureClass = FailureClass.VERIFICATION) -> FailureClass:
    """Map one internal code to its business failure class."""
    code = str(code or "").strip()
    if code in FAILURE_CODE_MAP:
        return FAILURE_CODE_MAP[code]
    for prefix, failure_class in _PREFIX_CLASSES:
        if code.startswith(prefix):
            return failure_class
    return default


@dataclass
class RecoveryAttempt:
    action: RecoveryAction
    stage: str
    failure_class: FailureClass
    error_code: str
    reason: str = ""
    outcome: str = "pending"     # pending | succeeded | failed | skipped | unresolved
    detail: str = ""
    # Obligation identity: the report must answer "why did THIS obligation end
    # unresolved", not just which action ran globally.
    rule_id: str = ""
    operation_id: str = ""
    obligation_id: str = ""
    target_id: str = ""
    site_id: str = ""
    attempt: int = 0
    budget_key: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "stage": self.stage,
            "failure_class": self.failure_class.value,
            "error_code": self.error_code,
            "reason": self.reason,
            "outcome": self.outcome,
            "detail": self.detail,
            "rule_id": self.rule_id,
            "operation_id": self.operation_id,
            "obligation_id": self.obligation_id,
            "target_id": self.target_id,
            "site_id": self.site_id,
            "attempt": self.attempt,
            "budget_key": self.budget_key,
        }


@dataclass
class RecoveryContext:
    rule_id: str = ""
    operation_id: str = ""
    obligation_id: str = ""
    site_id: str = ""
    target_id: str = ""
    stage: str = ""
    failure_class: FailureClass | None = None
    error_code: str = ""
    reason: str = ""
    facts_snapshot: Mapping[str, Any] = field(default_factory=dict)
    original_text: str = ""
    candidate_text: str = ""
    validator_findings: tuple[Mapping[str, Any], ...] = ()
    review_findings: tuple[Mapping[str, Any], ...] = ()
    attempts: tuple[RecoveryAttempt, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def resolved_class(self) -> FailureClass:
        return self.failure_class or classify(self.error_code)

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "operation_id": self.operation_id,
            "obligation_id": self.obligation_id,
            "site_id": self.site_id,
            "target_id": self.target_id,
            "stage": self.stage,
            "failure_class": self.resolved_class.value,
            "error_code": self.error_code,
            "reason": self.reason,
            "original_text": self.original_text,
            "candidate_text": self.candidate_text,
            "validator_findings": [dict(item) for item in self.validator_findings],
            "review_findings": [dict(item) for item in self.review_findings],
        }


@dataclass(frozen=True)
class RecoveryDecision:
    action: RecoveryAction
    reason: str
    budget_key: str = ""
    attempt: int = 1

    @property
    def terminal(self) -> bool:
        return self.action is RecoveryAction.MARK_UNRESOLVED

    def as_dict(self) -> dict[str, Any]:
        return {"action": self.action.value, "reason": self.reason,
                "budget_key": self.budget_key, "attempt": self.attempt}
