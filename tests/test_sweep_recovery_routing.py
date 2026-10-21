"""Sweep repairs preserve target/plan ownership instead of restarting discovery."""
import pytest

from fundlex.recall import Target
from fundlex.recall_pipeline import _sweep_recovery_contexts


def test_bound_sweep_site_uses_generation_without_inventory_discovery():
    target = Target("T1", "G17", "p8", "旧用途句", "needs_edit", "",
                    start=0, end=4, resolution="resolved", operations=("G17:0",))
    contexts = _sweep_recovery_contexts([
        {"finding_id": "SW1", "rule_id": "G17", "location": "p8",
         "issue": "residual_old_text", "reason": "exact residual"}],
        [target], {"edits": [{"operation_keys": ["G17:0"], "location": "p8"}]},
        {"failures": []})
    assert len(contexts) == 1
    assert contexts[0].stage == "sweep"
    assert contexts[0].operation_id == "G17:0"
    assert contexts[0].site_id == "p8"
    assert contexts[0].resolved_class.value == "GENERATION"


def test_unbound_sweep_site_routes_to_target_discovery():
    contexts = _sweep_recovery_contexts([
        {"finding_id": "SW2", "rule_id": "G17", "location": "p9",
         "issue": "missing_new_text", "reason": "no bound target"}],
        [], {"edits": []}, {"failures": []})
    assert len(contexts) == 1
    assert contexts[0].resolved_class.value == "TARGET"
    assert contexts[0].error_code == "SWEEP_TARGET_UNBOUND"


def test_sweep_execution_failure_preserves_existing_final_plan_route():
    target = Target("T1", "G17", "p8", "旧用途句", "needs_edit", "",
                    start=0, end=4, resolution="resolved", operations=("G17:0",))
    contexts = _sweep_recovery_contexts([
        {"finding_id": "SW1", "rule_id": "G17", "location": "p8",
         "issue": "residual_old_text", "reason": "execution missed planned delete"}],
        [target], {"edits": [{"operation_keys": ["G17:0"], "location": "p8"}]},
        {"failures": [{"code": "CLAIM_EXECUTION_EFFECT_MISSING", "rule_id": "G17",
                       "operation_id": "G17:0", "location": "p8"}]})
    assert len(contexts) == 1
    assert contexts[0].resolved_class.value == "EXECUTION"


@pytest.mark.parametrize("code", ["CLAIM_OPERATION_NOT_PLANNED", "CLAIM_OPERATION_UNPROVEN"])
def test_sweep_claim_no_plan_with_existing_target_routes_generation(code):
    target = Target("T1", "G05", "p0", "旧句", "needs_edit", "",
                    start=0, end=2, resolution="resolved", operations=("G05:0",))
    contexts = _sweep_recovery_contexts([
        {"finding_id": "SW3", "rule_id": "G05", "location": "p0",
         "issue": "missing_new_text", "reason": "claim did not plan operation"}],
        [target], {"edits": []},
        {"failures": [{"code": code, "rule_id": "G05",
                        "operation_id": "G05:0", "location": "p0",
                        "target_id": "T1"}]})
    assert len(contexts) == 1
    assert contexts[0].resolved_class.value == "GENERATION"
    assert contexts[0].metadata["root_cause"] == "TARGET_EXISTS_NO_PLAN"
