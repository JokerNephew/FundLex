"""Phase 1 acceptance tests: Strategy Registry + Router (plan v4 §17, §18, §22).

The registry must cover every rule group of the compiled guide; routing must
honour the plan's two hard rules: fact failures block (never fall through to
Tier3), and only text-structure reasons may degrade a tier.
"""
import json
from pathlib import Path

from fundlex.generation import (
    STRATEGY_REGISTRY,
    GenerationTier,
    registry_coverage_gaps,
    route_operation,
    strategy_for,
    strategy_mode,
)

GUIDE_PATH = Path(__file__).resolve().parents[1] / "guides" / "builtin_guide_v1.json"


def _guide() -> dict:
    return json.loads(GUIDE_PATH.read_text(encoding="utf-8"))


def test_registry_covers_every_guide_rule():
    guide = _guide()
    assert registry_coverage_gaps(guide) == []
    rule_ids = {group["rule_id"] for group in guide["groups"]}
    assert set(STRATEGY_REGISTRY) == rule_ids


def test_registry_specs_are_internally_consistent():
    for spec in STRATEGY_REGISTRY.values():
        assert spec.default_tier in spec.allowed_tiers
        assert spec.mode in {"replace", "append", "delete", "class_substitution", "noop"}
        assert all(isinstance(name, str) and name for name in spec.required_fact_status)


def test_unregistered_rule_falls_back_to_compose():
    spec = strategy_for("G99:0")
    assert spec.default_tier is GenerationTier.COMPOSE
    assert "未登记" in spec.note


def test_unknown_fact_blocks_instead_of_falling_through_to_tier3():
    decision = route_operation("G08:0", fact_status={"share_class_structure": "UNKNOWN"})
    assert decision.blocked is True
    assert decision.actual_tier is None
    assert decision.fallback_reason.startswith("FACT_NOT_VERIFIED")
    # CONFLICT behaves like UNKNOWN; only VERIFIED passes the gate.
    assert route_operation(
        "G08:0", fact_status={"share_class_structure": "CONFLICT",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"}).blocked is True
    assert route_operation(
        "G08:0", fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"}).resolved is True


def test_route_degrades_only_on_structure():
    verified = {"share_class_structure": "VERIFIED"}
    mixed = route_operation("G14:0", fact_status=verified, structure="mixed")
    assert mixed.actual_tier is GenerationTier.SPLICE
    assert mixed.fallback_reason == "complex_mixed_clause"
    unsafe = route_operation("G14:0", fact_status=verified, structure="unsafe")
    assert unsafe.actual_tier is GenerationTier.COMPOSE
    assert unsafe.fallback_reason == "structure_unsafe_for_splice"
    clean = route_operation("G08:0",
                            fact_status={**verified,
                                         "subscription_fee_group": "VERIFIED",
                                         "service_fee_group": "VERIFIED"},
                            structure="clean")
    assert clean.actual_tier is GenerationTier.TEMPLATE
    assert clean.fallback_reason == "clean_single_sentence"


def test_delete_rules_keep_their_deterministic_path():
    decision = route_operation("G15:0", structure="unsafe")
    assert decision.actual_tier is GenerationTier.DELETE


def test_flag_default_is_registry_and_unknown_values_fall_back(monkeypatch):
    monkeypatch.delenv("FUNDLEX_GENERATION_STRATEGY", raising=False)
    assert strategy_mode() == "registry"
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "bogus")
    assert strategy_mode() == "registry"
    monkeypatch.setenv("FUNDLEX_GENERATION_STRATEGY", "registry_shadow")
    assert strategy_mode() == "registry_shadow"


def test_generation_mix_classification_matches_plan_buckets():
    from tools.evaluation.generation_mix import classify
    assert classify("fragment_replace") == "deterministic"
    assert classify("whole_paragraph_delete") == "deterministic"
    assert classify("composed") == "model"
    assert classify("composed_delete") == "model"
    assert classify("merged") == "merge"
    assert classify("unknown-source") == "other"
