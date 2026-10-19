"""FL-D119 permanent regression: topic-flip and generic-tail false positives.

Reproduces the D01/p227 mechanism offline (plan v4 §23-B):

* the G08 survey fuzzy pass must not match the 赎回 clause
  ("本基金的**赎回**费率由基金管理人决定，并在招募说明书中列示。") to the
  申购 reference — a one-word topic flip is a different clause;
* ``satisfied_by_new_text`` must not accept a paragraph merely because it ends
  with the same generic closing formula ("并在招募说明书中列示。");
* G11 search keys must stay on the 申购 theme; 认购-only spans are not
  candidates (B-report erratum, 2026-10-19 ruling).
"""
import json
from pathlib import Path

from fundlex import recall as R
from fundlex.recall import ClassFact, Facts

GUIDE_PATH = Path(__file__).resolve().parents[1] / "guides" / "builtin_guide_v1.json"

G08_OLD = "本基金的申购费率由基金管理人决定，并在招募说明书中列示。"

# D01 original p227 (the mis-targeted paragraph).
P227_TEXT = (
    "赎回金额的计算及处理方式：本基金赎回金额的计算详见《招募说明书》。"
    "本基金的赎回费率由基金管理人决定，并在招募说明书中列示。"
    "赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额净值并扣除相应的费用，"
    "赎回金额单位为元。"
)


class _Span:
    def __init__(self, location: str, text: str) -> None:
        self.location = location
        self.text = text


def _prepare(spans: list[_Span]) -> None:
    # survey_targets populates this cache before searching; mirror it here.
    R._PARAGRAPH_GRAMS_CACHE.clear()
    for span in spans:
        cleaned, _ = R.display_text(span.text)
        R._PARAGRAPH_GRAMS_CACHE[span.location] = R._character_ngrams(
            R._compact(cleaned), 2)


def _guide_rule(rule_id: str) -> dict:
    guide = json.loads(GUIDE_PATH.read_text(encoding="utf-8"))
    return next(group for group in guide["groups"] if group["rule_id"] == rule_id)


def _facts() -> Facts:
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=(ClassFact("A类", True, False, True, None, ""),
                          ClassFact("D类", True, False, True, None, ""),
                          ClassFact("C类", False, True, True, "0.10%", "")),
                 floating_management_fee=False, floating_quote="",
                 floating_basis="", notes="", quotes_verified={}, problems=())


def test_g08_fuzzy_pass_rejects_topic_flip():
    span = _Span("p227", P227_TEXT)
    _prepare([span])
    hits = R.find_old_text_all([span], G08_OLD, threshold=R.SURVEY_FUZZY_THRESHOLD)
    assert hits == []


def test_g08_fuzzy_pass_still_accepts_bounded_wording_variant():
    variant = "本基金的申购费率由基金管理人决定并在招募说明书中列示。"
    span = _Span("p900", variant)
    _prepare([span])
    hits = R.find_old_text_all([span], G08_OLD, threshold=R.SURVEY_FUZZY_THRESHOLD)
    assert hits, "a bounded wording variant must remain discoverable"


def test_numeric_flip_is_not_a_variant():
    target = "基金销售服务费由基金托管人于次月首日起10个工作日内支付完毕。"
    window = "基金销售服务费由基金托管人于次月首日起5个工作日内支付完毕。"
    assert R._numeric_flip_only(target, window) is True
    span = _Span("p901", window)
    _prepare([span])
    assert R.find_old_text_all([span], target, threshold=R.SURVEY_FUZZY_THRESHOLD) == []


def test_satisfied_by_new_text_rejects_generic_tail():
    rule = _guide_rule("G08")
    body = R._compact(P227_TEXT)
    assert R.satisfied_by_new_text(rule, _facts(), body) is None


def test_satisfied_by_new_text_still_recognises_the_real_policy():
    rule = _guide_rule("G08")
    instantiated, issues = R.instantiate_slots(
        str((rule.get("operations") or [{}])[0].get("new_text") or ""), _facts())
    assert not issues and instantiated
    body = R._compact(instantiated)
    assert R.satisfied_by_new_text(rule, _facts(), body) is not None


def test_g11_search_keys_stay_on_subscription_theme():
    rule = _guide_rule("G11")
    pairs = R.operation_search_key_pairs(rule, _facts())
    assert pairs, "G11 must have search keys"
    assert all("认购" not in key for _, key in pairs)


def test_g11_does_not_match_subscription_swap_variant():
    rule = _guide_rule("G11")
    reference = R._compact(str((rule.get("operations") or [{}])[0].get("old_text") or ""))
    flipped = reference.replace("申购", "认购")
    assert flipped != reference
    span = _Span("p902", flipped)
    _prepare([span])
    assert R.find_old_text_all([span], reference, threshold=R.SURVEY_FUZZY_THRESHOLD) == []
