"""A bounded splice must be reproducible from source and guide, including legacy reports."""
import json
from copy import deepcopy
from pathlib import Path

import pytest

from fundlex.generation.claim_replay import replay_claims
from fundlex.generation.template import plan_g09_splice, splice_pairs
from test_claim_replay_operation_authorization import Inspection


def _case():
    guide = json.loads((Path(__file__).resolve().parents[1] /
                       "guides/builtin_guide_v1.json").read_text())
    rule = next(item for item in guide["groups"] if item["rule_id"] == "G09")
    before = ("赎回金额为按实际确认的有效赎回份额乘以赎回当日基金份额净值"
              "并扣除相应的费用，赎回金额单位为元。")
    op = rule["operations"][0]
    result = plan_g09_splice(before, splice_pairs(op["old_text"], op["new_text"]))
    assert result is not None
    edit = dict(target_id="T", rule_id="G09", location="p0", start=0, end=len(before),
                operation="replace", operation_keys=["G09:0"],
                replacement=result.replacement, content_source=result.content_source,
                expected_old_text=before, evidence=result.evidence)
    return rule, before, edit


@pytest.mark.parametrize("legacy", [False, True])
def test_real_contract_wording_replays_with_recomputed_splice(legacy):
    rule, before, edit = _case()
    if legacy:
        edit["evidence"].pop("fixed_text")
    result = replay_claims([edit], Inspection([before]), Inspection([edit["replacement"]]),
                           rules_by_id={"G09": rule})
    assert result["verified"], result["failures"]


@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("tamper", ["missing_fee_change", "added_policy", "deleted_suffix"])
def test_forged_mode_and_output_cannot_authorize_an_unreproducible_change(legacy, tamper):
    rule, before, edit = _case()
    before += "保留原有计算精度说明。"
    edit["end"] = len(before)
    edit["expected_old_text"] = before
    replacement = edit["replacement"] + "保留原有计算精度说明。"
    if tamper == "missing_fee_change":
        replacement = replacement.replace("扣除或加上", "扣除")
    elif tamper == "added_policy":
        replacement += "投资者可以随时免责。"
    else:
        replacement = replacement.replace("保留原有计算精度说明。", "")
    edit["replacement"] = replacement
    edit["evidence"] = {"mode": "g09_bounded_splice",
                        "applied": [[before, replacement]]}
    if not legacy:
        edit["evidence"]["fixed_text"] = replacement
    result = replay_claims([edit], Inspection([before]), Inspection([replacement]),
                           rules_by_id={"G09": rule})
    assert not result["verified"]
    assert any(item["code"] == "CLAIM_OPERATION_SPAN_UNAUTHORIZED"
               for item in result["failures"])


def test_mode_cannot_borrow_the_other_g09_operations_policy():
    rule, before, edit = _case()
    rule = deepcopy(rule)
    rule["operations"].append(dict(operation_id="G09:1", op="replace", old_text=before,
                                   new_text="另一操作的政策。"))
    edit["replacement"] = "另一操作的政策。"
    edit["evidence"] = {"mode": "g09_bounded_splice", "fixed_text": edit["replacement"]}
    result = replay_claims([edit], Inspection([before]), Inspection([edit["replacement"]]),
                           rules_by_id={"G09": rule})
    assert not result["verified"]
    assert any(item["code"] == "CLAIM_OPERATION_SPAN_UNAUTHORIZED"
               for item in result["failures"])


def test_unlisted_fee_variant_cannot_pass_with_only_nav_wording_change():
    rule, _, edit = _case()
    before = ("赎回金额为按实际确认的有效赎回份额乘以当日该类基金份额净值"
              "并扣除其他相应的费用，赎回金额单位为元。")
    result = plan_g09_splice(before, splice_pairs(
        edit["expected_old_text"], edit["replacement"]))
    assert result is not None
    assert "扣除或加上相应的费用" in result.replacement
    assert "当日该类基金份额的基金份额净值" in result.replacement

    partial = before.replace("当日该类基金份额净值",
                             "当日该类基金份额的基金份额净值")
    edit.update(start=0, end=len(before), replacement=partial,
                expected_old_text=before,
                evidence={"mode": "g09_bounded_splice", "fixed_text": partial})
    replay = replay_claims([edit], Inspection([before]), Inspection([partial]),
                           rules_by_id={"G09": rule})
    assert not replay["verified"]
    assert any(item["code"] in {"CLAIM_OPERATION_EFFECT_MISSING",
                                  "CLAIM_OPERATION_SPAN_UNAUTHORIZED"}
               for item in replay["failures"])
