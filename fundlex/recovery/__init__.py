"""Unified recovery layer (plan §17–§20)."""
from .history import RecoveryHistory
from .orchestrator import RecoveryOrchestrator
from .policies import DEFAULT_RECOVERY_POLICY, RecoveryPolicy, RecoveryPolicyError, load_policy
from .types import (FAILURE_CODE_MAP, FailureClass, RecoveryAction, RecoveryAttempt,
                    RecoveryContext, RecoveryDecision, classify)

__all__ = [
    "RecoveryHistory", "RecoveryOrchestrator", "RecoveryPolicy", "RecoveryPolicyError",
    "DEFAULT_RECOVERY_POLICY", "load_policy", "FailureClass", "RecoveryAction",
    "RecoveryAttempt", "RecoveryContext", "RecoveryDecision", "classify",
    "FAILURE_CODE_MAP",
]
