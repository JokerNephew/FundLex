"""Pure failure taxonomy and strategy escalation tests.

The planner may call this helper after a failed attempt.  These tests pin the
root cause mapping and, especially, the requirement that each retry changes the
method instead of sending the same compose request again.
"""

from fundlex.generation import (
    FailureTaxonomy,
    GenerationTier,
    RecoveryStrategy,
    classify_failure,
    strategy_for_failure,
)


def test_failure_codes_map_to_root_cause_taxonomy():
    assert classify_failure("RECALL_TARGET_REBIND_FAILED") is FailureTaxonomy.SOURCE_NOT_FOUND
    assert classify_failure("RECALL_TARGET_STRUCTURE") is FailureTaxonomy.RANGE_INVALID
    assert classify_failure("UNAUTHORIZED_NUMBER") is FailureTaxonomy.PROTECTED_TEXT_CHANGED
    assert classify_failure("COMPONENT_MISSING") is FailureTaxonomy.REQUIREMENT_MISSING
    assert classify_failure("RECALL_EDIT_OVERLAP") is FailureTaxonomy.DUPLICATE_CONTENT
    assert classify_failure("RECALL_TARGET_VARIANT_UNMATCHED") is FailureTaxonomy.SPLICE_FAILED
    assert classify_failure("RECALL_SLOT_UNRESOLVED") is FailureTaxonomy.TEMPLATE_NOT_APPLICABLE
    assert classify_failure("RECALL_COMPOSE_UNVERIFIED") is FailureTaxonomy.COMPOSE_VALIDATION_FAILED
    assert classify_failure("CLAIM_REPLACEMENT_MISSING") is FailureTaxonomy.ARTIFACT_MISMATCH
    assert classify_failure("new-unclassified-code") is FailureTaxonomy.UNKNOWN


def test_delete_path_escalates_to_a_different_method_each_time():
    expected = [
        RecoveryStrategy.DELETE,
        RecoveryStrategy.EXACT,
        RecoveryStrategy.NORMALIZED,
        RecoveryStrategy.FUZZY,
        RecoveryStrategy.TEMPLATE,
        RecoveryStrategy.SPLICE,
        RecoveryStrategy.COMPOSE,
    ]
    current = None
    observed = []
    for attempt in range(len(expected)):
        decision = strategy_for_failure(
            "SOURCE_NOT_FOUND", current_tier=current, attempt=attempt, mode="delete"
        )
        observed.append(decision.strategy)
        current = decision.strategy
    assert observed == expected
    assert strategy_for_failure(
        "SOURCE_NOT_FOUND", current_tier=RecoveryStrategy.COMPOSE,
        attempt=len(expected), mode="delete"
    ).terminal


def test_current_tier_aliases_are_normalized():
    # GenerationTier and the serialized content_source are both accepted.
    assert strategy_for_failure(
        "RECALL_SLOT_UNRESOLVED", current_tier=GenerationTier.TEMPLATE
    ).strategy is RecoveryStrategy.SPLICE
    assert strategy_for_failure(
        "RECALL_COMPOSE_UNVERIFIED", content_source="composed"
    ).strategy is RecoveryStrategy.REPAIR_COMPOSE
    assert strategy_for_failure(
        "RECALL_COMPOSE_UNVERIFIED", content_source="compose_repair"
    ).terminal


def test_artifact_failure_never_repeats_generation():
    decision = strategy_for_failure("CLAIM_NO_CHANGE_APPLIED")
    assert decision.taxonomy is FailureTaxonomy.ARTIFACT_MISMATCH
    assert decision.strategy is RecoveryStrategy.ARTIFACT_REBIND
    assert strategy_for_failure(
        "CLAIM_NO_CHANGE_APPLIED", current_tier=RecoveryStrategy.ARTIFACT_REBIND
    ).terminal


def test_decision_is_serializable_for_recovery_history():
    decision = strategy_for_failure("RECALL_COMPOSE_NEW_NUMBERS")
    assert decision.as_dict() == {
        "taxonomy": "COMPOSE_VALIDATION_FAILED",
        "strategy": "compose_repair",
        "reason": "compose_validation_failed->compose_repair",
        "attempt": 0,
        "terminal": False,
    }
