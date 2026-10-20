"""Recovery orchestrator (plan §18–§19).

The orchestrator never performs a business edit itself.  It answers one question:
*given this failure, which layer should be retried next?*  Every decision is bounded
by :class:`RecoveryPolicy`, records an attempt in :class:`RecoveryHistory`, and the
exact same method is never retried unchanged (plan §20).

Callers execute the returned action and report the outcome; the orchestrator then
moves to the next action or terminates with ``MARK_UNRESOLVED``.
"""
from __future__ import annotations

from typing import Iterable

from .history import RecoveryHistory
from .policies import RecoveryPolicy, load_policy
from .types import FailureClass, RecoveryAction, RecoveryAttempt, RecoveryContext, RecoveryDecision

_A = RecoveryAction


class RecoveryOrchestrator:
    def __init__(self, policy: RecoveryPolicy | None = None):
        self.policy = policy or load_policy()

    # -- decision ---------------------------------------------------------------
    def decide(self, context: RecoveryContext,
               history: RecoveryHistory | None = None) -> RecoveryDecision:
        history = history or RecoveryHistory()
        failure_class = context.resolved_class
        stage = context.stage or failure_class.value.lower()
        candidates = self._candidates(failure_class, context)
        for action, budget_key in candidates:
            limit = self.policy.limit(budget_key)
            if history.count(action) >= limit:
                continue
            if action in {_A.RETRY_DETERMINISTIC, _A.REGENERATE_ARTIFACT} and \
                    history.identical_attempt(action, stage=stage,
                                              error_code=context.error_code,
                                              reason=context.reason):
                # Same deterministic method, same reason: repeating it cannot change
                # the result. Model-assisted actions carry new structured feedback.
                continue
            return RecoveryDecision(action, f"{failure_class.value}:{budget_key}",
                                    budget_key, history.count(action) + 1)
        return RecoveryDecision(_A.MARK_UNRESOLVED,
                                f"{failure_class.value}:recovery_budget_exhausted")

    def _candidates(self, failure_class: FailureClass,
                    context: RecoveryContext) -> list[tuple[RecoveryAction, str]]:
        if failure_class is FailureClass.FACT:
            return [(_A.FOCUSED_FACT_RESOLVE, "fact_primary_retry"),
                    (_A.FACT_ARBITRATION, "fact_review_arbitration")]
        if failure_class is FailureClass.APPLICABILITY:
            return [(_A.APPLICABILITY_ARBITRATION, "applicability_review_arbitration")]
        if failure_class is FailureClass.TARGET:
            return [(_A.RETRY_DETERMINISTIC, "target_deterministic_retry"),
                    (_A.LLM_LOCATE, "target_primary_locator")]
        if failure_class is FailureClass.GENERATION:
            candidates = [(_A.RETRY_DETERMINISTIC, "generation_deterministic_retry"),
                          (_A.LLM_COMPOSE, "generation_primary_compose")]
            if context.metadata.get("overlap") or context.metadata.get("joint"):
                candidates.append((_A.JOINT_COMPOSE, "joint_compose"))
            return candidates
        if failure_class is FailureClass.EXECUTION:
            return [(_A.REBUILD_PLAN, "execution_rebuild"),
                    (_A.REGENERATE_ARTIFACT, "artifact_recovery")]
        if failure_class is FailureClass.VERIFICATION:
            if str(context.error_code).startswith("CLAIM_"):
                return [(_A.REGENERATE_ARTIFACT, "artifact_recovery"),
                        (_A.REBUILD_PLAN, "execution_rebuild")]
            return []
        if failure_class is FailureClass.RESOURCE:
            return [(_A.SPLIT_CONTEXT, "context_split")]
        if failure_class is FailureClass.INFRASTRUCTURE:
            return [(_A.PAUSE_RESUME, "infrastructure_pause_resume")]
        return []

    # -- execution helpers ------------------------------------------------------
    def record(self, history: RecoveryHistory, context: RecoveryContext,
               decision: RecoveryDecision, *, outcome: str, detail: str = "") -> RecoveryAttempt:
        attempt = RecoveryAttempt(action=decision.action,
                                  stage=context.stage or context.resolved_class.value.lower(),
                                  failure_class=context.resolved_class,
                                  error_code=context.error_code,
                                  reason=context.reason,
                                  outcome=outcome, detail=detail)
        history.append(attempt)
        return attempt

    def run(self, context: RecoveryContext, handler: "RecoveryHandler",
            history: RecoveryHistory | None = None) -> RecoveryHistory:
        """Execute recovery actions until one succeeds or the budget is exhausted.

        ``handler`` is a callable ``(action, context) -> (succeeded, detail)``.
        """
        history = history or RecoveryHistory()
        while True:
            decision = self.decide(context, history)
            if decision.terminal:
                self.record(history, context, decision, outcome="failed",
                            detail="all recovery paths exhausted")
                return history
            try:
                succeeded, detail = handler(decision.action, context)
            except Exception as exc:  # noqa: BLE001 - recorded, never swallowed silently
                succeeded, detail = False, f"{type(exc).__name__}:{exc}"
            self.record(history, context, decision,
                        outcome="succeeded" if succeeded else "failed", detail=detail)
            if succeeded:
                return history
            if history.count(decision.action) >= self.policy.limit(decision.budget_key):
                # Count against the exhausted key, then let decide() route onward.
                continue


#: Structural type for the handler; kept as a protocol-like alias for readability.
class RecoveryHandler:
    def __call__(self, action: RecoveryAction,
                 context: RecoveryContext) -> tuple[bool, str]:  # pragma: no cover - typing
        raise NotImplementedError


def failure_codes(history: RecoveryHistory) -> Iterable[str]:
    return (item.error_code for item in history.attempts if item.error_code)
