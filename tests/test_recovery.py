"""Failure classes, recovery budgets and the recovery orchestrator (plan §17–§20)."""
from __future__ import annotations

import pytest

from fundlex.recovery import (DEFAULT_RECOVERY_POLICY, FailureClass, RecoveryAction,
                              RecoveryContext, RecoveryHistory, RecoveryOrchestrator,
                              RecoveryPolicy, RecoveryPolicyError, classify, load_policy)


def test_failure_class_mapping_covers_the_plan_examples():
    assert classify("RECALL_FACT_UNVERIFIED") is FailureClass.FACT
    assert classify("RECALL_TARGET_UNRESOLVED") is FailureClass.TARGET
    assert classify("RECALL_TARGET_STRUCTURE") is FailureClass.TARGET
    assert classify("RECALL_TARGET_VARIANT_UNMATCHED") is FailureClass.GENERATION
    assert classify("MISSING_REQUIRED_TERM") is FailureClass.GENERATION
    assert classify("RECALL_EDIT_NOT_EXECUTABLE") is FailureClass.EXECUTION
    assert classify("CLAIM_VALIDATION_FAILED") is FailureClass.VERIFICATION
    assert classify("MODEL_HTTP_ERROR") is FailureClass.INFRASTRUCTURE
    assert classify("RECALL_SCOPE_CONTEXT_LIMIT") is FailureClass.RESOURCE
    # Unknown verification codes fail closed rather than being retried as generation.
    assert classify("SWEEP_QUOTE_NOT_RESOLVED") is FailureClass.VERIFICATION
    assert classify("SOMETHING_NEW") is FailureClass.VERIFICATION


def test_default_policy_matches_the_plan():
    assert DEFAULT_RECOVERY_POLICY["generation_primary_compose"] == 2
    assert DEFAULT_RECOVERY_POLICY["generation_review_rounds"] == 2
    assert DEFAULT_RECOVERY_POLICY["joint_compose"] == 1
    assert DEFAULT_RECOVERY_POLICY["artifact_recovery"] == 2
    assert DEFAULT_RECOVERY_POLICY["global_business_rounds"] == 3


def test_policy_env_override(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FUNDLEX_RECOVERY_GENERATION_PRIMARY_COMPOSE", "4")
    policy = load_policy()
    assert policy.limit("generation_primary_compose") == 4
    with pytest.raises(RecoveryPolicyError):
        policy.with_overrides({"generation_primary_compose": "x"})
    with pytest.raises(RecoveryPolicyError):
        policy.with_overrides({"unknown_key": 1})


def test_fact_recovery_walks_primary_then_review_then_unresolved():
    orchestrator = RecoveryOrchestrator()
    history = RecoveryHistory()
    context = RecoveryContext(stage="facts", error_code="RECALL_FACT_UNVERIFIED",
                              reason="share classes unknown")
    first = orchestrator.decide(context, history)
    assert first.action is RecoveryAction.FOCUSED_FACT_RESOLVE
    orchestrator.record(history, context, first, outcome="failed")
    second = orchestrator.decide(context, history)
    assert second.action is RecoveryAction.FACT_ARBITRATION
    orchestrator.record(history, context, second, outcome="failed")
    third = orchestrator.decide(context, history)
    assert third.action is RecoveryAction.MARK_UNRESOLVED
    assert third.terminal


def test_same_method_is_never_retried_unchanged():
    orchestrator = RecoveryOrchestrator()
    history = RecoveryHistory()
    context = RecoveryContext(stage="target", error_code="RECALL_TARGET_UNRESOLVED",
                              reason="quote not found")
    first = orchestrator.decide(context, history)
    assert first.action is RecoveryAction.RETRY_DETERMINISTIC
    orchestrator.record(history, context, first, outcome="failed")
    second = orchestrator.decide(context, history)
    # The identical deterministic retry is skipped; the next layer is the LLM locator.
    assert second.action is RecoveryAction.LLM_LOCATE
    orchestrator.record(history, context, second, outcome="failed")
    assert orchestrator.decide(context, history).action is RecoveryAction.MARK_UNRESOLVED


def test_generation_falls_back_to_compose_and_respects_its_budget():
    orchestrator = RecoveryOrchestrator(RecoveryPolicy().with_overrides(
        {"generation_primary_compose": 2}))
    history = RecoveryHistory()
    context = RecoveryContext(stage="plan", error_code="RECALL_COMPOSE_UNVERIFIED",
                              reason="validator")
    orchestrator.record(history, context,
                        orchestrator.decide(context, history), outcome="failed")
    assert orchestrator.decide(context, history).action is RecoveryAction.LLM_COMPOSE
    # Compose attempts count globally, so two recorded attempts exhaust that path.
    for _ in range(2):
        decision = orchestrator.decide(context, history)
        assert decision.action is RecoveryAction.LLM_COMPOSE
        orchestrator.record(history, context, decision, outcome="failed")
    assert orchestrator.decide(context, history).action is RecoveryAction.MARK_UNRESOLVED


def test_overlap_routes_to_joint_compose():
    orchestrator = RecoveryOrchestrator()
    history = RecoveryHistory()
    context = RecoveryContext(stage="plan", error_code="RECALL_EDIT_OVERLAP",
                              reason="spans overlap", metadata={"overlap": True})
    orchestrator.record(history, context,
                        orchestrator.decide(context, history), outcome="failed")
    assert orchestrator.decide(context, history).action is RecoveryAction.LLM_COMPOSE
    orchestrator.record(history, context,
                        orchestrator.decide(context, history), outcome="failed")
    # The first compose attempt is already recorded; the budget allows a second.
    assert orchestrator.decide(context, history).action is RecoveryAction.LLM_COMPOSE
    orchestrator.record(history, context,
                        orchestrator.decide(context, history), outcome="failed")
    assert orchestrator.decide(context, history).action is RecoveryAction.JOINT_COMPOSE


def test_claim_replay_failure_enters_artifact_recovery_not_final_unresolved():
    orchestrator = RecoveryOrchestrator()
    history = RecoveryHistory()
    context = RecoveryContext(stage="deliver", error_code="CLAIM_REPLACEMENT_MISSING",
                              failure_class=FailureClass.VERIFICATION,
                              reason="artifact lost replacement")
    decision = orchestrator.decide(context, history)
    assert decision.action is RecoveryAction.REGENERATE_ARTIFACT
    assert not decision.terminal


def test_resource_failure_splits_context_instead_of_failing_the_contract():
    orchestrator = RecoveryOrchestrator()
    context = RecoveryContext(stage="scope", error_code="RECALL_SCOPE_CONTEXT_LIMIT",
                              reason="too many rules")
    assert orchestrator.decide(context, RecoveryHistory()).action is \
        RecoveryAction.SPLIT_CONTEXT


def test_run_executes_until_success_and_records_history():
    orchestrator = RecoveryOrchestrator()
    context = RecoveryContext(stage="target", error_code="RECALL_TARGET_UNRESOLVED",
                              reason="quote not found")
    seen: list[RecoveryAction] = []

    def handler(action, _context):
        seen.append(action)
        return (action is RecoveryAction.LLM_LOCATE, "located")

    history = orchestrator.run(context, handler)
    assert seen == [RecoveryAction.RETRY_DETERMINISTIC, RecoveryAction.LLM_LOCATE]
    assert [item.outcome for item in history.attempts] == ["failed", "succeeded"]
    assert history.summary(context)["final"] == "succeeded"
    assert history.to_json()


def test_infrastructure_pauses_instead_of_using_a_business_fallback():
    orchestrator = RecoveryOrchestrator()
    context = RecoveryContext(stage="facts", error_code="MODEL_HTTP_ERROR",
                              reason="timeout")
    assert orchestrator.decide(context, RecoveryHistory()).action is RecoveryAction.PAUSE_RESUME
