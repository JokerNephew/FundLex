"""Loop-6 mechanism repairs: FL-D697 / FL-D698 / FL-D695 residual.

- FL-D697a: a term-level replace rebound onto a composite (multi-paragraph)
  reference must fail closed instead of swapping the whole reference for the
  bare term (B05 G02 p118+p119 collapsed two definitions into "A类基金份额").
- FL-D697b: at a merged multi-rule site the auditor reviews one rule in
  isolation and can demand the survival of text a completed sibling operation
  was authorized to remove (B05 G16 re-audited against the clause G15
  deleted).  A quoted loss covered by the sibling's authorized old text is an
  authorized removal, not this rule's defect.
- FL-D698: same-site occurrence ambiguity counts only ``needs_edit`` targets;
  two satisfied targets assert the same negative fact twice (B12 G05:2 p162,
  resolved target plus its absent-site clone).
- FL-D695 residual: a business-round re-inventory replaces ``entry.targets``
  wholesale and can mint a fresh ``absent`` verdict at a site whose executed
  target the rebuild dropped; re-applying the refutation gate must still
  overturn it.
"""
import json
from pathlib import Path

import pytest
from docx import Document

from fundlex.docx import inspect_docx
from fundlex.recall import (RecallError, Target, plan_composite_target,
                            refute_absent_by_variant_evidence)
from fundlex.recall_pipeline import _audit_issues, _target_identity
from fundlex.generation.claim_replay import replay_claims
from fundlex.obligations import apply_facts, compile_obligations

from test_recall_core import _facts


def _inspect(tmp_path, name, texts):
    path = tmp_path / (name + ".docx")
    document = Document()
    for text in texts:
        document.add_paragraph(text)
    document.save(path)
    return inspect_docx(path, full=True)


# ---------------------------------------------------------------------------
# FL-D697a: composite whole-reference replacement scope guard
# ---------------------------------------------------------------------------

P118 = "A类基金份额或A类份额：指投资人申购时收取申购费用，但不从本类别资产中计提销售服务费的基金份额类别"
P119 = "C类基金份额或C类份额：指从本类别基金资产中计提年费率为0.25%的销售服务费而不收取申购费用的基金份额类别"


def _composite_target():
    parts = (f"p0:0:{len(P118)}", f"p1:0:{len(P119)}")
    return Target("W1:T002", "G02", "p0", P118, "needs_edit", "rebind",
                  operations=("G02:0",), composite=parts)


def _g02_rule(old_text: str, new_text: str = ""):
    return {"rule_id": "G02", "operations": [
        {"op": "replace", "old_text": old_text, "new_text": new_text,
         "condition": {"kind": "none"}}]}


def test_composite_term_replace_fails_closed(tmp_path):
    """The B05 G02 shape: whole-reference swap for a bare term is unauthorized."""
    inspection = _inspect(tmp_path, "src", [P118, P119])
    target = _composite_target()
    with pytest.raises(RecallError) as excinfo:
        plan_composite_target(_g02_rule("A类基金份额"), target, inspection, _facts(),
                              new_text="A类基金份额")
    assert excinfo.value.code == "RECALL_COMPOSITE_REPLACE_SCOPE_UNPROVEN"


def test_composite_whole_reference_replace_still_authorized(tmp_path):
    """A replace whose old_text covers the entire reference stays plannable."""
    inspection = _inspect(tmp_path, "src", [P118, P119])
    target = _composite_target()
    old = P118 + P119
    edits = plan_composite_target(_g02_rule(old), target, inspection, _facts(),
                                  new_text="X类与Y类基金份额的释义整体重述。")
    assert [edit.content_source for edit in edits] == ["composite_replace",
                                                       "composite_delete"]
    assert edits[0].replacement.startswith("X类与Y类基金份额的释义整体重述。")
    assert edits[1].replacement == ""


# ---------------------------------------------------------------------------
# FL-D697b: sibling-authorized loss is not this rule's audit defect
# ---------------------------------------------------------------------------

G15_OLD = ("基金销售服务费每日计提，逐日累计至每月月末，按月支付。经基金管理人与"
           "基金托管人双方核对无误后，基金托管人按照与基金管理人协商一致的方式，"
           "于次月前5个工作日内从基金财产中一次性支付。若遇法定节假日、休息日或"
           "不可抗力致使无法按时支付的，支付日期顺延至最近可支付日支付。")
G16_NEW = "销售服务费每日计提。（1）直销机构：按月支付。"


def _audit_target(target_id, rule_id, location, quote):
    return Target(target_id, rule_id, location, quote, "needs_edit", "survey",
                  operations=(f"{rule_id}:0",))


def _audit_state(results_pairs):
    return {"results": {key: value for key, value in results_pairs}, "missed": {}}


def _g16_wrong_result(evidence_quote):
    return {"verdict": "wrong", "reason": "AFTER仅含新增文本，原条款被删除",
            "evidence_quote": evidence_quote, "evidence_verified": True,
            "evidence_in_before": True, "evidence_in_after": False,
            "failure_class": "EXECUTION", "affected_fact": "",
            "affected_obligation": ""}


def _g15_completed_result():
    return {"verdict": "completed", "reason": "原支付条款已按G15删除",
            "evidence_quote": G15_OLD[:20], "evidence_verified": True,
            "evidence_in_before": True, "evidence_in_after": False,
            "failure_class": "", "affected_fact": "", "affected_obligation": ""}


def _merged_edit():
    return {"edits": [{
        "location": "p0", "operation_keys": ["G15:0", "G16:0"],
        "expected_old_text": G15_OLD, "replacement": " " + G16_NEW,
        "components": [
            {"rule_id": "G16", "expected_old_text": "", "replacement": G16_NEW},
            {"rule_id": "G15", "expected_old_text": G15_OLD[:-1], "replacement": ""},
        ],
    }]}


def test_sibling_authorized_loss_does_not_reopen_completed_removal():
    g15 = _audit_target("Y003", "G15", "p0", G15_OLD)
    g16 = _audit_target("W1:T001", "G16", "p0", "销售服务费支付条款")
    quoted_loss = ("基金销售服务费每日计提，逐日累计至每月月末，按月支付。"
                   "经基金管理人与基金托管人双方核对无误后……顺延至最近可支付日支付")
    state = _audit_state([
        (_target_identity(g15), _g15_completed_result()),
        (_target_identity(g16), _g16_wrong_result(quoted_loss)),
    ])
    issues = _audit_issues(state, [g15, g16], planned=_merged_edit())
    assert issues == [], issues


def test_mutation_loss_without_completed_sibling_still_issues():
    """Fail-closed: no completed sibling at the site keeps the audit issue."""
    g16 = _audit_target("W1:T001", "G16", "p0", "销售服务费支付条款")
    state = _audit_state([
        (_target_identity(g16), _g16_wrong_result(G15_OLD[:30])),
    ])
    issues = _audit_issues(state, [g16], planned=_merged_edit())
    assert any(issue.get("code") == "AUDIT_NOT_COMPLETED" for issue in issues), issues


def test_mutation_sibling_not_completed_still_issues():
    """A sibling verdict that is not ``completed`` cannot whitewash the loss."""
    g15 = _audit_target("Y003", "G15", "p0", G15_OLD)
    g16 = _audit_target("W1:T001", "G16", "p0", "销售服务费支付条款")
    sibling = _g15_completed_result()
    sibling["verdict"] = "wrong"
    state = _audit_state([
        (_target_identity(g15), sibling),
        (_target_identity(g16), _g16_wrong_result(G15_OLD[:30])),
    ])
    issues = _audit_issues(state, [g15, g16], planned=_merged_edit())
    assert any(issue.get("code") == "AUDIT_NOT_COMPLETED"
               and issue.get("rule_id") == "G16" for issue in issues), issues


# ---------------------------------------------------------------------------
# FL-D698: satisfied targets never count toward same-site ambiguity
# ---------------------------------------------------------------------------

G05_GUIDE = {"groups": [{
    "rule_id": "G05", "title": "class setup wording", "section_hint": "释义",
    "requirement": "delete filing sentence",
    "operations": [{"op": "delete", "old_text": "并报中国证监会备案",
                    "condition": {"kind": "none"}}],
    "old_text_variants": [],
}]}

P162 = ("基金份额类别的设置：本基金根据申购费用、销售服务费收取方式的不同，"
        "将基金份额分为不同的类别。各类基金份额分别设置代码，分别计算和公告"
        "各类基金份额净值和各类基金份额累计净值。")


def _g05_ledger():
    ledger = compile_obligations(G05_GUIDE)
    apply_facts(ledger, _facts())
    return ledger


def _g05_target(target_id, state, *, clone=False):
    return {"target_id": target_id, "rule_id": "G05", "location": "p0",
            "quote": P162[:30], "state": state,
            "reason": "absent_clone" if clone else "resolved",
            "start": 0, "end": len(P162), "resolution": "resolved",
            "segment_ok": True, "composite": [], "operations": ["G05:0"],
            "claimed_operations": [], "attribution_error": "",
            "site_candidates": [], "occurrence_index": -1, "occurrence_anchor": "",
            "out_of_scope": False, "scope_id": "", "approval_id": ""}


def test_satisfied_same_site_pair_is_not_ambiguous(tmp_path):
    before = _inspect(tmp_path, "before", [P162])
    after = _inspect(tmp_path, "after", [P162])
    targets = {
        "T006": _g05_target("T006", "satisfied"),
        "ABSENT-G05-0": _g05_target("ABSENT-G05-0", "satisfied", clone=True),
    }
    result = replay_claims([], before, after,
                           rules_by_id={"G05": G05_GUIDE["groups"][0]},
                           targets_by_id=targets, obligations=_g05_ledger(),
                           facts=_facts())
    assert not any(failure.get("code") == "CLAIM_SITE_OCCURRENCE_UNRESOLVED"
                   for failure in result["failures"]), result["failures"]


def test_mutation_needs_edit_same_site_pair_still_ambiguous(tmp_path):
    before = _inspect(tmp_path, "before", [P162])
    after = _inspect(tmp_path, "after", [P162])
    targets = {
        "T006": _g05_target("T006", "needs_edit"),
        "T007": _g05_target("T007", "needs_edit"),
    }
    result = replay_claims([], before, after,
                           rules_by_id={"G05": G05_GUIDE["groups"][0]},
                           targets_by_id=targets, obligations=_g05_ledger(),
                           facts=_facts())
    assert any(failure.get("code") == "CLAIM_SITE_OCCURRENCE_UNRESOLVED"
               for failure in result["failures"]), result["failures"]


# ---------------------------------------------------------------------------
# FL-D695 residual: re-applying the refutation gate after a rebuild
# ---------------------------------------------------------------------------

G09_P159 = ("2、赎回金额的处理方式：赎回金额为按实际确认的有效赎回份额乘以申请当日"
            "基金份额净值的金额，净赎回金额为赎回金额扣除相应的费用的金额，"
            "各计算结果均保留至小数点后两位，小数点后两位以后的部分四舍五入，"
            "由此产生的误差计入基金财产。")


def _g09():
    guide = json.loads((Path(__file__).resolve().parents[1] /
                        "guides/builtin_guide_v1.json").read_text())
    return next(rule for rule in guide["groups"] if rule["rule_id"] == "G09")


def test_refutation_gate_reapplied_after_wholesale_rebuild(tmp_path):
    """The rebuild mints a NEW absent target id; the gate must flip it again."""
    inspection = _inspect(tmp_path, "src", [G09_P159])
    rebuilt = [Target("W1:T011", "G09", "p0", "", "absent",
                      "规则源文在本窗口不存在", operations=("G09:0",))]
    rows = refute_absent_by_variant_evidence(rebuilt, {"G09": _g09()}, inspection,
                                             facts=_facts())
    assert rebuilt[0].state == "needs_edit"
    assert rows and rows[0]["target_id"] == "W1:T011"
    # A correct fail-closed verdict with no variant evidence still stands.
    guarded = [Target("W2:T007", "G09", "p0", "", "absent",
                      "本窗口不存在规则目标原文", operations=("G09:0",))]
    inspection_other = _inspect(tmp_path, "other", ["本基金的投资范围为具有良好流动性的金融工具。"])
    rows = refute_absent_by_variant_evidence(guarded, {"G09": _g09()},
                                             inspection_other, facts=_facts())
    assert guarded[0].state == "absent" and rows == []


# ---------------------------------------------------------------------------
# FL-D699: identity class substitution inside a container is a satisfied no-op
# ---------------------------------------------------------------------------

def _g02_full():
    guide = json.loads((Path(__file__).resolve().parents[1] /
                        "guides/builtin_guide_v1.json").read_text())
    return next(rule for rule in guide["groups"] if rule["rule_id"] == "G02")


def _facts_mixed():
    """subscription ['A','B'] -> G02:0 expands; service ['C'] -> G02:1 identity."""
    from fundlex.recall import ClassFact, Facts
    return Facts(fund_type="open_regular", fund_type_quote="某某混合型基金基金合同",
                 fund_type_basis="标题",
                 classes=(ClassFact(name="A类基金份额", subscription_fee=True,
                                    service_fee=False, current=True, rate="1.2%", quote="A类"),
                          ClassFact(name="B类基金份额", subscription_fee=True,
                                    service_fee=False, current=True, rate="1.5%", quote="B类"),
                          ClassFact(name="C类基金份额", subscription_fee=False,
                                    service_fee=True, current=True, rate="0.4%", quote="C类")),
                 floating_management_fee=False, floating_quote="本基金合同经中国证监会核准。",
                 floating_basis="无浮动安排", notes="",
                 quotes_verified={"floating": True}, problems=(),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def test_identity_composite_class_substitution_closes_satisfied(tmp_path):
    """B05 loop-7 shape: G02:0 instantiated == reference -> satisfied-noop."""
    from fundlex.recall import plan_edits
    inspection = _inspect(tmp_path, "src", [P118, P119])
    target = _composite_target()
    rule = _g02_full()
    plan = plan_edits({"G02": rule}, [target], inspection, _facts(), None,
                      max_compose_calls=0)
    assert target.state == "satisfied"
    assert "CLASS_SUBSTITUTION_IDENTITY_NOOP" in target.reason
    assert plan["edits"] == []
    assert plan["ledger"][0]["status"] == "satisfied"
    assert plan["ledger"][0]["reason"] == "class_substitution_identity_noop"


def test_mutation_non_identity_op_does_not_collapse(tmp_path):
    """Expanded group keeps the target live and the scope guard fails closed."""
    from fundlex.recall import plan_edits
    inspection = _inspect(tmp_path, "src", [P118, P119])
    target = _composite_target()
    plan = plan_edits({"G02": _g02_full()}, [target], inspection, _facts_mixed(), None,
                      max_compose_calls=0)
    assert target.state == "needs_edit"
    assert plan["edits"] == []
    assert plan["ledger"][0]["status"] == "unresolved"
    assert plan["ledger"][0]["reason"] == "RECALL_COMPOSITE_REPLACE_SCOPE_UNPROVEN"


def test_identity_helper_guards():
    from fundlex.recall import target_class_ops_identity
    rule = _g02_full()
    assert target_class_ops_identity(rule, ["G02:0"], _facts()) is True
    assert target_class_ops_identity(rule, ["G02:1"], _facts()) is True
    assert target_class_ops_identity(rule, ["G02:0"], _facts_mixed()) is False
    plain = {"rule_id": "G99", "operations": []}
    assert target_class_ops_identity(plain, ["G99:0"], _facts()) is False
    unverified = _facts_mixed()
    object.__setattr__(unverified, "fact_status",
                       {"share_class_structure": "VERIFIED",
                        "subscription_fee_group": "UNRESOLVED",
                        "service_fee_group": "VERIFIED"})
    assert target_class_ops_identity(rule, ["G02:0"], unverified) is False


# ---------------------------------------------------------------------------
# FL-D862/863/864: holdout first-check families
# ---------------------------------------------------------------------------

def _guide_path():
    return Path(__file__).resolve().parents[1] / "guides/builtin_guide_v1.json"


def _facts_single():
    """Single unlettered class, no sales service fee (BH04 shape)."""
    from fundlex.recall import ClassFact, Facts
    return Facts(fund_type="open_regular", fund_type_quote="某某纯债债券型证券投资基金基金合同",
                 fund_type_basis="标题",
                 classes=(ClassFact(name="__single__", subscription_fee=True,
                                    service_fee=False, current=True, rate="0.8%",
                                    quote="本基金"),),
                 floating_management_fee=False, floating_quote="本基金合同经中国证监会核准。",
                 floating_basis="无浮动安排", notes="",
                 quotes_verified={"floating": True}, problems=(),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def _facts_multi_no_svc():
    """Multi-class, every class subscription-fee only (BH07 FOF shape)."""
    from fundlex.recall import ClassFact, Facts
    return Facts(fund_type="open_regular", fund_type_quote="某养老目标FOF基金合同",
                 fund_type_basis="标题",
                 classes=(ClassFact(name="A", subscription_fee=True, service_fee=False,
                                    current=True, rate="1.2%", quote="A类"),
                          ClassFact(name="Y", subscription_fee=True, service_fee=False,
                                    current=True, rate="1.2%", quote="Y类")),
                 floating_management_fee=False, floating_quote="本基金合同经中国证监会核准。",
                 floating_basis="无浮动安排", notes="",
                 quotes_verified={"floating": True}, problems=(),
                 fact_status={"share_class_structure": "VERIFIED",
                              "subscription_fee_group": "VERIFIED",
                              "service_fee_group": "VERIFIED"})


def _apply_guide_applicability(facts):
    guide = json.loads(_guide_path().read_text())
    ledger = compile_obligations(guide)
    apply_facts(ledger, facts)
    return ledger


def test_guide_conditions_single_class_not_applicable():
    """FL-D863: single unlettered class makes class/service rules N/A (BH04)."""
    ledger = _apply_guide_applicability(_facts_single())
    for obligation_id in ("G01:B1:O1", "G02:B1:O1", "G02:B1:O2", "G03:B1:O1",
                          "G04:B1:O1", "G04:B1:O2", "G15:B1:O1", "G16:B1:O1",
                          "G17:B1:O1", "G18:B1:O1"):
        record = ledger.record(obligation_id)
        assert record.applicability.status == "FALSE", (obligation_id, record.applicability)
        assert record.completion == "NOT_APPLICABLE"


def test_guide_conditions_multi_class_no_service():
    """Multi-class product without a service-fee class (BH07 post-FL-D862)."""
    ledger = _apply_guide_applicability(_facts_multi_no_svc())
    for obligation_id in ("G01:B1:O1", "G02:B1:O1", "G03:B1:O1", "G04:B1:O1"):
        assert ledger.record(obligation_id).applicability.status == "TRUE", obligation_id
    for obligation_id in ("G15:B1:O1", "G16:B1:O1", "G17:B1:O1", "G18:B1:O1"):
        record = ledger.record(obligation_id)
        assert record.applicability.status == "FALSE", (obligation_id, record.applicability)


def test_guide_conditions_multi_class_with_service():
    """A/C product keeps the service-fee rules applicable (BH02/dev shape)."""
    ledger = _apply_guide_applicability(_facts())
    for obligation_id in ("G01:B1:O1", "G02:B1:O1", "G03:B1:O1", "G04:B1:O1",
                          "G15:B1:O1", "G16:B1:O1", "G17:B1:O1", "G18:B1:O1"):
        record = ledger.record(obligation_id)
        assert record.applicability.status == "TRUE", (obligation_id, record.applicability)


def test_fee_value_letterless_default_subscription_sentence():
    """FL-D862(a): a letterless default fee sentence proves the class polarity."""
    from fundlex.fee_evidence import fee_value
    assert fee_value("申购费用由投资人承担，不列入基金财产。",
                     "subscription_fee", "A") is True
    # Mutation: the allowance is subscription-only; the service fee stays unread.
    assert fee_value("申购费用由投资人承担，不列入基金财产。",
                     "sales_service_fee", "A") is None
    # Mutation: a letterless special-channel clause still proves nothing.
    assert fee_value("通过直销机构网上交易申购本基金可享费率优惠，详列公告。",
                     "subscription_fee", "A") is None


def test_fee_value_exemption_proves_default_fee():
    """FL-D862(b): 豁免（含可以豁免）presupposes the fee regime exists."""
    from fundlex.fee_evidence import fee_value
    assert fee_value("本基金可以豁免Y类基金份额的申购费用，具体规定请参见招募说明书或相关公告，"
                     "法律法规另有规定的从其规定。", "subscription_fee", "Y") is True
    # Exemption of the *other* fee must not leak into this class's polarity.
    assert fee_value("本基金可以豁免Y类基金份额的申购费用，具体规定请参见招募说明书。",
                     "subscription_fee", "A") is None


def test_multi_class_no_service_evidence(tmp_path):
    """FL-D862(c): zero class-bound service-fee sentences prove the empty group."""
    from fundlex.recall import ClassFact, multi_class_no_service_evidence
    classes = (ClassFact(name="A", subscription_fee=True, service_fee=False,
                         current=True, rate=None, quote="A类"),
               ClassFact(name="Y", subscription_fee=True, service_fee=False,
                         current=True, rate=None, quote="Y类"))
    fof = _inspect(tmp_path, "fof", [
        "本基金根据销售账户的不同，将基金份额分为A类基金份额和Y类基金份额。",
        "基金管理人运用本基金财产申购自身管理的其他基金（ETF除外），应当通过直销渠道申购"
        "且不收取申购费、赎回费、销售服务费等销售费用。",
        "申购费用由投资人承担，不列入基金财产。",
    ])
    assert multi_class_no_service_evidence(fof, classes) is True
    bound = _inspect(tmp_path, "bound", [
        "本基金根据收费方式的不同，将基金份额分为A类基金份额和C类基金份额。",
        "C类基金份额的销售服务费按前一日C类基金份额资产净值的0.50%的年费率计提。",
    ])
    ac_classes = (classes[0],
                  ClassFact(name="C", subscription_fee=False, service_fee=False,
                            current=True, rate=None, quote="C类"))
    assert multi_class_no_service_evidence(bound, ac_classes) is False
    service_classes = (classes[0], ClassFact(name="Y", subscription_fee=True,
                                             service_fee=True, current=True,
                                             rate=None, quote="Y类"))
    assert multi_class_no_service_evidence(fof, service_classes) is False


# FL-D864: G18 replace absence certificate -----------------------------------

def _g18_contract_paragraphs(extra_income=()):
    return [
        "基金利润指基金利息收入、投资收益、公允价值变动收益和其他收入扣除相关费用后的余额。",
        "基金可供分配利润指截至收益分配基准日基金未分配利润与未分配利润中已实现收益的孰低数。",
        *extra_income,
        "本基金的收益分配原则如下：在符合有关基金分红条件的前提下，本基金可以进行收益分配。",
    ]


def _g18_obligations(facts):
    guide = json.loads(_guide_path().read_text())
    ledger = compile_obligations(guide)
    apply_facts(ledger, facts)
    return guide, ledger


def test_g18_absence_certificate_scoped(tmp_path):
    """BH02 shape: old wording absent from the income scope -> certificate."""
    from types import SimpleNamespace
    from fundlex.recall import absent_delete_coverage
    insp = _inspect(tmp_path, "g18", _g18_contract_paragraphs())
    guide, ledger = _g18_obligations(_facts())
    rules_by_id = {rule["rule_id"]: rule for rule in guide["groups"]}
    scopes = {"G18": SimpleNamespace(locations=frozenset(
        [f"p{index}" for index in range(4)]))}
    records = absent_delete_coverage(rules_by_id, [], insp, scopes, ledger,
                                     facts=_facts())
    assert "G18:0" in records
    assert records["G18:0"]["kind"] == "rule_scope_scan"


def test_mutation_g18_cert_blocked_by_service_fee_mention(tmp_path):
    """A surviving 销售服务费 mention in the income scope blocks the certificate."""
    from types import SimpleNamespace
    from fundlex.recall import absent_delete_coverage
    insp = _inspect(tmp_path, "g18x", _g18_contract_paragraphs(
        extra_income=("由于本基金A类基金份额不收取销售服务费，C类份额费率不同，收益分配存在差异。",
                      )))
    guide, ledger = _g18_obligations(_facts())
    rules_by_id = {rule["rule_id"]: rule for rule in guide["groups"]}
    scopes = {"G18": SimpleNamespace(locations=frozenset(
        [f"p{index}" for index in range(4)]))}
    records = absent_delete_coverage(rules_by_id, [], insp, scopes, ledger,
                                     facts=_facts())
    assert "G18:0" not in records


def test_mutation_g18_cert_blocked_by_unverified_facts(tmp_path):
    """Unverified fee groups fail closed: no absence certificate."""
    from types import SimpleNamespace
    from fundlex.recall import absent_delete_coverage
    insp = _inspect(tmp_path, "g18u", _g18_contract_paragraphs())
    facts = _facts()
    object.__setattr__(facts, "fact_status",
                       {"share_class_structure": "VERIFIED",
                        "subscription_fee_group": "UNKNOWN",
                        "service_fee_group": "VERIFIED"})
    guide = json.loads(_guide_path().read_text())
    ledger = compile_obligations(guide)
    for record in ledger.records:
        if record.obligation_id == "G18:B1:O1":
            continue
    scopes = {"G18": SimpleNamespace(locations=frozenset(["p0", "p1", "p2", "p3"]))}
    rules_by_id = {rule["rule_id"]: rule for rule in guide["groups"]}
    records = absent_delete_coverage(rules_by_id, [], insp, scopes, ledger,
                                     facts=facts)
    assert "G18:0" not in records


# FL-D863: G06 dual-scope replay gate ----------------------------------------

class _ShimSpan:
    """Paragraph span carrying the structure metadata of a real DOCX run."""

    def __init__(self, location, text, section_path):
        self.location = location
        self.text = text
        self.zone = "body"
        self.section_path = section_path


class _ShimInspection:
    """Inspect-alike whose spans expose section_path (LOF no-heading shape)."""

    def __init__(self, texts, section_path="第三部分基金的基本情况"):
        self.paragraphs = tuple(
            _ShimSpan(f"p{index}", text, section_path)
            for index, text in enumerate(texts))
        self.source_sha256 = "0" * 64

    def by_location(self, location):
        for span in self.paragraphs:
            if span.location == location:
                return span
        raise KeyError(location)


def _g06_obligation_stub():
    from types import SimpleNamespace
    spec = SimpleNamespace(rule_id="G06", operation_id="G06:0", op="delete",
                           old_text="本基金各类基金份额之间不得相互转换。",
                           alternatives=(), new_text="")
    return SimpleNamespace(spec=spec, obligation_id="G06:B1:O1",
                           applicability=SimpleNamespace(status="TRUE"))


def _g06_coverage(insp, locations):
    return {"kind": "rule_scope_scan", "operation_id": "G06:0",
            "obligation_id": "G06:B1:O1", "scanned_locations": list(locations),
            "document_sha256": insp.source_sha256}


def test_g06_replay_gate_falls_back_to_rule_scope(tmp_path):
    """LOF shape: no 份额类别设置 heading; boundary scope closes the delete."""
    from fundlex.generation.effects import evaluate_operation_effect
    insp = _ShimInspection([
        "本基金设A类、C类、E类三类基金份额。",
        "在符合法律法规且不损害持有人利益的前提下，基金管理人可以调整基金份额类别设置。",
        "七、基金的财产",
        "基金财产独立于基金管理人、基金托管人的固有财产。",
    ])
    boundary = {f"p{index}" for index in range(2)}
    result = evaluate_operation_effect(_g06_obligation_stub(), insp, insp, [], [],
                                       _facts(), boundary_locations=boundary,
                                       absent_coverage=_g06_coverage(insp, boundary))
    assert result.state == "PASS", result.as_dict()


def test_mutation_g06_gate_still_closed_without_boundary(tmp_path):
    """Old behaviour preserved: no subsection heading and no boundary -> OPEN."""
    from fundlex.generation.effects import evaluate_operation_effect
    insp = _ShimInspection([
        "本基金设A类、C类两类基金份额。",
        "七、基金的财产",
        "基金财产独立于基金管理人、基金托管人的固有财产。",
    ])
    result = evaluate_operation_effect(_g06_obligation_stub(), insp, insp, [], [],
                                       _facts(), boundary_locations=None)
    assert result.state == "OPEN"
    assert "g06_subsection_scope_missing" in str(result.reason)


# ---------------------------------------------------------------------------
# FL-D869: BH07 second order — class-grouping replace completion verdict
# ---------------------------------------------------------------------------

def _g02_contract_paragraphs(extra=()):
    return [
        "本基金根据销售所适用账户的不同，将基金份额分为A类基金份额和Y类基金份额。"
        "A类基金份额不得对个人养老金账户进行销售，Y类基金份额仅面向个人养老金账户销售。",
        "本基金A类、Y类基金份额分别设置代码。由于基金费用可能存在不同,"
        "本基金A类基金份额和Y类基金份额将分别计算基金份额净值。",
        *extra,
    ]


def _g02_coverage(tmp_path, name, paragraphs, facts, targets=()):
    from types import SimpleNamespace
    from fundlex.recall import absent_delete_coverage
    insp = _inspect(tmp_path, name, paragraphs)
    guide = json.loads(_guide_path().read_text())
    ledger = compile_obligations(guide)
    apply_facts(ledger, facts)
    rules_by_id = {rule["rule_id"]: rule for rule in guide["groups"]}
    locations = frozenset(f"p{index}" for index in range(len(paragraphs)))
    scopes = {"G02": SimpleNamespace(locations=locations),
              "G04": SimpleNamespace(locations=locations)}
    return absent_delete_coverage(rules_by_id, list(targets), insp, scopes,
                                  ledger, facts=facts)


def test_g02_g04_enumerated_absence_and_empty_group_certificates(tmp_path):
    """BH07 shape: enumeration/partition sentences only + VERIFIED-empty
    service group -> enumerated absence for the letter ops, empty-group
    no-op for the service-side ops."""
    facts = _facts_multi_no_svc()
    records = _g02_coverage(tmp_path, "g02", _g02_contract_paragraphs(), facts)
    assert records["G02:0"]["kind"] == "enumerated_absence"
    assert records["G02:1"]["kind"] == "empty_group_noop"
    assert records["G04:0"]["kind"] == "enumerated_absence"
    assert records["G04:1"]["kind"] == "empty_group_noop"


def test_mutation_g02_certificate_blocked_by_fee_regime_sentence(tmp_path):
    """A real fee-grouping prototype sentence is the operation's object: the
    certificate must NOT fire (fail closed), even for G04 which shares the
    reference term."""
    facts = _facts_multi_no_svc()
    records = _g02_coverage(tmp_path, "g02b", _g02_contract_paragraphs(extra=(
        "A类基金份额：指在投资者申购时收取申购费用，"
        "不再从本类别基金财产中计提销售服务费的基金份额。",
    )), facts)
    assert "G02:0" not in records
    assert "G04:0" not in records
    # ...but the empty-group service-side ops stay completable.
    assert records["G02:1"]["kind"] == "empty_group_noop"


def test_mutation_g02_certificates_need_verified_facts(tmp_path):
    """UNKNOWN fee groups fail closed for every completable shape."""
    facts = _facts_multi_no_svc()
    object.__setattr__(facts, "fact_status",
                       {"share_class_structure": "VERIFIED",
                        "subscription_fee_group": "VERIFIED",
                        "service_fee_group": "UNKNOWN"})
    records = _g02_coverage(tmp_path, "g02u", _g02_contract_paragraphs(), facts)
    assert "G02:0" not in records
    assert "G02:1" not in records


def test_mutation_g02_false_recovery_binding_is_rebutted(tmp_path):
    """FL-D869: a recovery target claiming the op on an enumeration paragraph
    must not disable the certificate; the same claim with a real fee sentence
    in scope keeps the operation open."""
    from fundlex.recall import Target
    facts = _facts_multi_no_svc()
    claim = Target(target_id="R-valse", rule_id="G02", location="p0",
                   quote="分为A类基金份额和Y类基金份额", state="needs_edit",
                   start=0, end=0, reason="claim_operation_recovery:G02:0",
                   operations=("G02:0",))
    records = _g02_coverage(tmp_path, "g02r", _g02_contract_paragraphs(),
                            facts, targets=(claim,))
    assert records["G02:0"]["kind"] == "enumerated_absence"
    # A real fee-regime sentence still wins over the claimed site.
    claim2 = Target(target_id="R-real", rule_id="G02", location="p2",
                    quote="A类基金份额收取申购费", state="needs_edit",
                    start=0, end=0, reason="claim_operation_recovery:G02:0",
                    operations=("G02:0",))
    records = _g02_coverage(tmp_path, "g02r2", _g02_contract_paragraphs(extra=(
        "A类基金份额收取申购费用，Y类基金份额的申购费用另有约定。",
    )), facts, targets=(claim2,))
    assert "G02:0" not in records


def test_g02_identity_noop_ac_product(tmp_path):
    """Dev AC shape: instantiated replacements equal the references, so the
    identity no-op fires even inside fee sentences (dev 回归防回摆)。"""
    facts = _facts()
    paragraphs = [
        "A类基金份额：指在投资者申购时收取申购费用，不再从本类别基金财产中计提销售服务费的基金份额。",
        "C类基金份额：指从本类别基金财产中计提销售服务费的基金份额。",
    ]
    records = _g02_coverage(tmp_path, "g02i", paragraphs, facts)
    assert records["G02:0"]["kind"] == "identity_noop"
    assert records["G02:1"]["kind"] == "identity_noop"
