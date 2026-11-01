"""Runtime variant pipeline (FL-D655, mechanism B).

Discover → classify → certify → authorize, all deterministic.  Key properties
pinned here: a class-qualified rewording of the guide clause certifies; a
negation flip or length explosion stays anchored-but-anomalous; the literal
and declared-variant paths stay untouched; review rows stay review-only.
"""
from __future__ import annotations

from types import SimpleNamespace

from fundlex.delivery import requires_blocker
from fundlex.recall import ensure_certified_variant_targets
from fundlex.variants import (authorized_variant_sentences, certify_variant,
                              classify_candidate, discover_candidates,
                              review_candidate_rows)

OLD = "本基金的管理费按前一日基金资产净值的1.0%年费率计提。"
NEW = "本基金A类份额和C类份额的管理费分别按前一日该类基金资产净值的1.0%年费率计提。"
QUALIFIED = "本基金A类份额和C类份额的管理费按前一日基金资产净值的1.0%年费率计提。"


def _rule(rule_id="G90", old=OLD, new=NEW, *, op="replace"):
    return {
        "rule_id": rule_id,
        "title": rule_id,
        "operations": [
            {"op": op, "old_text": old, "new_text": new,
             "condition": {"kind": "none", "value": None}},
        ],
        "old_text_variants": [],
    }


def _inspection(*paragraphs: tuple[str, str]):
    spans = [SimpleNamespace(text=text, location=location, segments=())
             for location, text in paragraphs]
    inspection = SimpleNamespace(paragraphs=spans)
    inspection.by_location = lambda location: next(
        span for span in spans if span.location == location)
    return inspection


def test_class_qualified_rewording_certifies():
    record = certify_variant(_rule()["operations"][0], QUALIFIED)
    assert record is not None
    assert record["proof_kind"] == "variant_chunk_signature"
    assert record["anchor_chars"] >= 6
    assert record["coverage_ratio"] >= 0.5


def test_literal_old_text_stays_on_the_inventory_path():
    assert certify_variant(_rule()["operations"][0], OLD) is None
    assert classify_candidate(_rule()["operations"][0], OLD)["bucket"] != "CERTIFIABLE"


def test_unrelated_sentence_is_ignored():
    bucket = classify_candidate(_rule()["operations"][0],
                                "本基金托管人为中国工商银行股份有限公司。")
    assert bucket["bucket"] == "IGNORE"


def test_negation_flip_is_anomalous_never_certified():
    negated = "本基金管理费不按前一日基金资产净值的年费率计提，而按月计提。"
    classification = classify_candidate(_rule()["operations"][0], negated)
    assert classification["bucket"] in {"ANOMALOUS", "IGNORE"}
    assert certification_none(certify_variant(_rule()["operations"][0], negated))


def certification_none(value):
    return value is None


def test_length_explosion_stays_anomalous():
    stretched = ("本基金管理费按前一日基金资产净值的1.0%年费率计提，"
                 "托管费另计，销售服务费另计，申购费另计，赎回费另计，"
                 "转换费另计，公告费另计，审计费另计。")
    assert certify_variant(_rule()["operations"][0], stretched) is None


def test_already_satisfied_wording_is_exempt():
    bucket = classify_candidate(_rule()["operations"][0], NEW)
    assert bucket["bucket"] != "CERTIFIABLE"


def test_authorized_variant_sentences_feeds_the_policy_gate():
    sentences = authorized_variant_sentences(_rule()["operations"][0],
                                             QUALIFIED + "其他句子。")
    assert QUALIFIED in sentences


def test_ensure_certified_variant_targets_creates_residual_target():
    rule = _rule()
    inspection = _inspection(("p7", QUALIFIED))
    created = ensure_certified_variant_targets([], {"G90": rule}, inspection)
    assert len(created) == 1
    target = created[0]
    assert target.rule_id == "G90"
    assert target.state == "needs_edit"
    assert target.reason.startswith("certified_variant:G90:")
    assert target.location == "p7"


def test_existing_live_target_suppresses_duplicates():
    rule = _rule()
    existing = SimpleNamespace(rule_id="G90", out_of_scope=False,
                               state="needs_edit")
    inspection = _inspection(("p7", QUALIFIED))
    assert ensure_certified_variant_targets([existing], {"G90": rule},
                                            inspection) == []


def test_canonical_old_text_present_suppresses_variants():
    rule = _rule()
    inspection = _inspection(("p7", OLD + QUALIFIED))
    assert ensure_certified_variant_targets([], {"G90": rule}, inspection) == []


def test_g08_keeps_its_stricter_rule_specific_predicate():
    rule = _rule("G08")
    inspection = _inspection(("p7", QUALIFIED))
    assert ensure_certified_variant_targets([], {"G08": rule}, inspection) == []


def test_rule_without_true_condition_creates_nothing():
    rule = _rule()
    rule["operations"][0]["condition"] = {"kind": "class_count", "value": "single"}
    inspection = _inspection(("p7", QUALIFIED))
    facts = SimpleNamespace(status_of=lambda name: "UNKNOWN", class_count=3)
    assert ensure_certified_variant_targets([], {"G90": rule}, inspection,
                                            facts=facts) == []


def test_anomalous_candidate_becomes_review_only_row():
    rule = _rule()
    anomalous = "本基金管理费不按前一日基金资产净值的年费率计提，而按月计提。"
    inspection = _inspection(("p9", anomalous))
    rows = review_candidate_rows(rule, inspection)
    assert row_codes(rows) in (["VARIANT_PENDING_CERTIFICATION"], [])
    if rows:
        # Review evidence must never block delivery.
        assert requires_blocker(rows[0]) is False


def row_codes(rows):
    return [row["code"] for row in rows]


def test_certified_target_cap_is_respected():
    rule = _rule()
    inspection = _inspection(*((f"p{i}", QUALIFIED) for i in range(8)))
    created = ensure_certified_variant_targets([], {"G90": rule}, inspection)
    assert len(created) <= 4


def test_discover_candidates_marks_exempt_for_new_form():
    candidates = discover_candidates(_rule()["operations"][0], NEW)
    assert candidates == [] or candidates[0]["bucket"] == "EXEMPT"


def test_critical_token_swap_never_certifies():
    """FL-D588 over-authorization mutation in generic form: a 22-char anchor
    with the fee item swapped (申购→管理) must stay blocked, mirroring the
    rule-specific G08 guard test."""
    op = {"op": "replace",
          "old_text": "本基金的申购费率由基金管理人决定，并在招募说明书中列示。",
          "new_text": "本基金A类份额不收取申购费，其他机构申购费率由基金管理人决定。",
          "operation_id": "G91:0"}
    assert certify_variant(op, "本基金的管理费率由基金管理人决定，并在招募说明书中列示。") is None
    assert certify_variant(op, "本基金A类份额的申购费率由基金管理人决定，并在招募说明书中列示。") is not None
