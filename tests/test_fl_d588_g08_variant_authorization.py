"""FL-D588 / B17: G08 class-qualified variant clause must be plannable.

B17 p292 (loop-2 d55702b): the target T009 carried a class-qualified member of
the G08 legacy-clause family
(「本基金C类基金份额和E类基金份额不收取申购费，A类人民币基金份额和A类美元现汇
基金份额的申购费率由基金管理人决定，并在招募说明书中列示。」).  The planner's
routed policy gate authorizes removals only against ``old_text`` /
``old_text_variants``; the guide declares neither, so the variant's qualifier
tokens (人民币 / 美元现汇 / C类 E类 grouping) tripped UNEXPLAINED_HARD and the
target was fail-closed as RECALL_POLICY_COMPONENTS_UNVERIFIED while claim replay
reported CLAIM_OPERATION_NOT_PLANNED.  The fix authorizes removal of exactly the
sentences the recall side already certifies as the G08 family (FL-D587's bounded
predicate); every other sentence remains an unauthorized removal.
"""
import json
from pathlib import Path

import pytest

from fundlex.recall import (ClassFact, Facts, RecallError,
                            _g08_authorized_variant_sentences,
                            _validate_routed_policy, instantiate_slots)

GUIDE = json.loads(Path("guides/builtin_guide_v1.json").read_text())
G08 = next(group for group in GUIDE["groups"] if group["rule_id"] == "G08")

B17_BEFORE = ("本基金C类基金份额和E类基金份额不收取申购费，A类人民币基金份额和"
              "A类美元现汇基金份额的申购费率由基金管理人决定，并在招募说明书中列示。")
CANONICAL = "本基金的申购费率由基金管理人决定，并在招募说明书中列示。"
UNRELATED_FEE_SENTENCE = "本基金的管理费率由基金管理人决定，并在招募说明书中列示。"


def _facts():
    classes = (ClassFact(name="A", subscription_fee=True, service_fee=False,
                         current=True, rate=None, quote=""),
               ClassFact(name="C", subscription_fee=False, service_fee=True,
                         current=True, rate=None, quote=""),
               ClassFact(name="E", subscription_fee=False, service_fee=True,
                         current=True, rate=None, quote=""))
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=classes, floating_management_fee=False, floating_quote="",
                 floating_basis="", notes="", quotes_verified={}, problems=(),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def _operations():
    return [dict(operation, _operation_index=index)
            for index, operation in enumerate(G08["operations"])]


def _after(facts):
    new_text, issues = instantiate_slots(str(G08["operations"][0]["new_text"]), facts)
    assert not issues
    return new_text


def test_variant_sentence_certifier_matches_b17_shape_only():
    assert _g08_authorized_variant_sentences(B17_BEFORE) == [B17_BEFORE]
    assert _g08_authorized_variant_sentences(CANONICAL) == [CANONICAL]
    # A redemption-side rate sentence must never enter the G08 family.
    redemption = "本基金的赎回费率由基金管理人决定，并在招募说明书中列示。"
    assert _g08_authorized_variant_sentences(redemption) == []
    # Management fees share the tail but lack the subscription anchor.
    assert _g08_authorized_variant_sentences(UNRELATED_FEE_SENTENCE) == []


def test_b17_variant_clause_passes_policy_gate():
    facts = _facts()
    _validate_routed_policy(G08, _operations(), facts, B17_BEFORE, _after(facts))


def test_over_authorization_guard_unrelated_fee_sentence_still_blocked():
    facts = _facts()
    with pytest.raises(RecallError) as excinfo:
        _validate_routed_policy(G08, _operations(), facts,
                                UNRELATED_FEE_SENTENCE, _after(facts))
    assert excinfo.value.code == "RECALL_POLICY_COMPONENTS_UNVERIFIED"


def test_mutation_without_variant_authorization_b17_still_blocked():
    """Removing the new authorization must restore the loop-2 UNEXPLAINED_HARD
    fail-closed posture (report.findings empty + verdict FAIL)."""
    facts = _facts()
    rule = dict(G08, rule_id="G08-MUT")  # bypasses the rule_id hook
    with pytest.raises(RecallError) as excinfo:
        _validate_routed_policy(rule, _operations(), facts, B17_BEFORE, _after(facts))
    assert excinfo.value.code == "RECALL_POLICY_COMPONENTS_UNVERIFIED"
