"""FL-D695: deterministic variant evidence refutes a volatile inventory absent.

A single inventory round can judge a real business site "target wording absent"
while the deterministic variant machinery anchors the rule's clause at the same
paragraph (loop-5 B15 G09 p159: the model called the redemption-amount clause
absent one loop after correctly planning it).  Left standing, the verdict blocks
every downstream channel and the delivery gate withholds the whole contract.

``refute_absent_by_variant_evidence`` overturns such a verdict when code evidence
contradicts it: CERTIFIABLE/ANOMALOUS candidates restore ``needs_edit`` bound to
the variant span; EXEMPT candidates (new policy form already present) restore
``satisfied``.  No candidate keeps ``absent`` (fail-closed).
"""
import json
from pathlib import Path

from docx import Document

from fundlex.docx import inspect_docx
from fundlex.recall import Target, refute_absent_by_variant_evidence

from test_recall_core import _facts

P159 = ("2、赎回金额的处理方式：赎回金额为按实际确认的有效赎回份额乘以申请当日"
        "基金份额净值的金额，净赎回金额为赎回金额扣除相应的费用的金额，"
        "各计算结果均保留至小数点后两位，小数点后两位以后的部分四舍五入，"
        "由此产生的误差计入基金财产。")


def _g09():
    guide = json.loads((Path(__file__).resolve().parents[1] /
                        "guides/builtin_guide_v1.json").read_text())
    return next(rule for rule in guide["groups"] if rule["rule_id"] == "G09")


def _inspect(tmp_path, text):
    path = tmp_path / "source.docx"
    document = Document()
    document.add_paragraph(text)
    document.save(path)
    return inspect_docx(path, full=True)


def _absent(location: str = "p0", operations=("G09:0",)) -> Target:
    return Target("W1:T008", "G09", location, "", "absent",
                  "窗口中不存在规则目标原文", operations=operations)


def test_anomalous_variant_at_same_site_refutes_absent(tmp_path):
    inspection = _inspect(tmp_path, P159)
    target = _absent()
    rows = refute_absent_by_variant_evidence([target], {"G09": _g09()}, inspection,
                                              facts=_facts())
    assert target.state == "needs_edit"
    assert target.start == 0 and target.end == 112
    assert "赎回金额为按实际确认" in target.quote
    assert target.resolution == "resolved"
    assert target.operations == ("G09:0",)
    assert "ABSENT_REFUTED_BY_VARIANT_EVIDENCE" in target.reason
    assert len(rows) == 1
    row = rows[0]
    assert row["code"] == "ABSENT_REFUTED_BY_VARIANT_EVIDENCE"
    assert row["target_id"] == "W1:T008" and row["rule_id"] == "G09"
    assert row["operation_id"] == "G09:0" and row["location"] == "p0"
    assert row["bucket"] in {"ANOMALOUS", "CERTIFIABLE"}
    assert row["state"] == "needs_edit" and row["quote"] == target.quote


def test_no_variant_evidence_keeps_absent_fail_closed(tmp_path):
    inspection = _inspect(tmp_path, "本基金的投资范围为具有良好流动性的金融工具。")
    target = _absent()
    rows = refute_absent_by_variant_evidence([target], {"G09": _g09()}, inspection,
                                              facts=_facts())
    assert target.state == "absent" and rows == []
    assert "ABSENT_REFUTED" not in target.reason


def test_exempt_new_form_refutes_absent_as_satisfied(tmp_path):
    new_text = str(_g09()["operations"][0]["new_text"])
    inspection = _inspect(tmp_path, new_text)
    target = _absent()
    rows = refute_absent_by_variant_evidence([target], {"G09": _g09()}, inspection,
                                              facts=_facts())
    assert target.state == "satisfied"
    assert rows and rows[0]["bucket"] == "EXEMPT" and rows[0]["state"] == "satisfied"


def test_live_sibling_target_owns_the_site_no_flip(tmp_path):
    inspection = _inspect(tmp_path, P159)
    sibling = Target("Y001", "G09", "p0", P159, "needs_edit", "survey",
                     operations=("G09:0",))
    target = _absent()
    rows = refute_absent_by_variant_evidence([target, sibling], {"G09": _g09()},
                                              inspection, facts=_facts())
    assert target.state == "absent" and rows == []


def test_absent_attributed_to_another_operation_is_not_stolen(tmp_path):
    inspection = _inspect(tmp_path, P159)
    target = _absent(operations=("G09:9",))
    rows = refute_absent_by_variant_evidence([target], {"G09": _g09()}, inspection,
                                              facts=_facts())
    assert target.state == "absent" and rows == []


def test_out_of_scope_absent_verdict_is_untouched(tmp_path):
    inspection = _inspect(tmp_path, P159)
    target = _absent()
    target.out_of_scope = True
    rows = refute_absent_by_variant_evidence([target], {"G09": _g09()}, inspection,
                                              facts=_facts())
    assert target.state == "absent" and rows == []
