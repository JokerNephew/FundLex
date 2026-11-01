"""FL-D790: append scoring window symmetrise backwards (mainline ruling).

DEFINITION_GROUP_APPEND_END legally rebinds an append to an earlier paragraph
of the same subsection (the full policy clauses are written there verbatim and
replay-verified).  The forward-only scoring window (index-1..index+6) scored
that legal landing as ``not_executed`` — the B15 T001 false gap.  The append
window now reaches 6 paragraphs backwards; the forward window and every other
path are unchanged.
"""
from tools.evaluation.p6_score import score_target

POLICY = ("投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金A类基金份额时，"
          "不收取认购/申购费用；通过直销机构申购的C类基金份额，不收取销售服务费。"
          "对于投资者通过直销机构之外的其他销售机构申购的C类基金份额且持续持有期限超过一年的，"
          "不再继续收取销售服务费。")
DECLARED = 20  # declared site paragraph index


def _facts():
    return {"classes": [{"name": "A类基金份额", "subscription_fee": True, "service_fee": False},
                        {"name": "C类基金份额", "subscription_fee": False, "service_fee": True}],
            "has_sales_service_fee": True, "fund_type": "混合型"}


def _paragraphs(land_at=None):
    original = [f"第{i}条 基金合同既有条款文本，与本次修订无关。" for i in range(30)]
    final = list(original)
    if land_at is not None:
        final[land_at] = final[land_at] + POLICY
    return original, final


def _score(final):
    original, _ = _paragraphs()
    target = {"target_id": "T001", "rule_id": "G03", "op": "append",
              "required_text": POLICY, "paragraph_index": DECLARED}
    return score_target(target, _facts(), final, original)


def test_backward_legal_append_landing_is_executed():
    """Legal APPEND_END rebind four paragraphs before the declared site."""
    original, final = _paragraphs(land_at=DECLARED - 4)
    assert _score(final)["verdict"] == "completed"


def test_backward_boundary_index_minus_6_is_executed():
    original, final = _paragraphs(land_at=DECLARED - 6)
    assert _score(final)["verdict"] == "completed"


def test_beyond_backward_window_stays_not_executed():
    """Adversarial: identical policy seven paragraphs earlier must not count."""
    original, final = _paragraphs(land_at=DECLARED - 7)
    assert _score(final)["verdict"] == "not_executed"


def test_declared_site_append_positive_control_unchanged():
    original, final = _paragraphs(land_at=DECLARED)
    assert _score(final)["verdict"] == "completed"


def test_absent_policy_stays_not_executed():
    original, final = _paragraphs()
    assert _score(final)["verdict"] == "not_executed"
