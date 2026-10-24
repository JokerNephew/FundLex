"""Audits receive applicable policy without inventing missing fee groups."""
import json
from dataclasses import replace
from pathlib import Path

import pytest

from fundlex.recall import ClassFact, Target
from fundlex.recall_pipeline import _audit_context
from test_g15_payment_delay_boundary import _write
from test_recall_core import _facts


@pytest.mark.parametrize("rule_id", ["G01", "G03", "G08", "G11"])
@pytest.mark.parametrize("status", ["VERIFIED", "UNKNOWN", "CONFLICT"])
def test_audit_policy_omits_service_component_only_on_certified_absence(tmp_path, rule_id, status):
    original = _write(tmp_path/"source.docx", ["本基金定义A类和Y类基金份额。"])
    facts = _facts()
    facts = replace(facts, classes=(ClassFact("A类基金份额", True, False, True, None, ""),
                                    ClassFact("Y类基金份额", True, False, True, None, "")),
                    fact_status={**facts.fact_status, "service_fee_group": status})
    guide = json.loads((Path(__file__).resolve().parents[1]/"guides/builtin_guide_v1.json").read_text())
    rule = next(g for g in guide["groups"] if g["rule_id"] == rule_id)
    rule["operations"][0]["operation_id"] = "DECLARED:OP"
    target = Target("T", rule_id, "p0", original.by_location("p0").text, "needs_edit", "test")
    context, _, _ = _audit_context(rule, [target], {}, original, original, limit=60000, facts=facts)
    policies = json.loads(context.split("[APPLICABLE_POLICIES]\n")[1].split("\n\n[OTHER_AUTHORIZED_EDITS]")[0])
    policy = policies[0]
    assert policy["operation_id"] == "DECLARED:OP"
    assert "[REQUIREMENTS]" in context and rule["operations"][0]["new_text"] in context
    if status == "VERIFIED":
        assert policy["policy_status"] == "READY", policy
        assert "Y类" in policy["applicable_new_text"]
        assert "C类" not in policy["applicable_new_text"]
        assert "销售服务费" not in policy["applicable_new_text"]
    else:
        assert policy["policy_status"] == "UNRESOLVED"
        assert policy["applicable_new_text"] == ""
        assert policy["issues"]
