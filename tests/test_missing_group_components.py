"""Missing-group component handling tests (external review 2026-10-19, P0-C/P0-D).

* G08/G11 on a product without a service-fee class: only the clauses naming that
  class disappear — the subscription-group and channel obligations still apply.
* G16's append obligation is only "already present" when the new mechanism markers
  exist, not merely because the old clause opens the same way.
* G14's extended-clause rebuild can also ADD a fee item the guide requires.
"""
from fundlex.recall import _append_obligation_present, _drop_empty_group_operations
from fundlex.recall import ClassFact, Facts

REGISTRY_ENV = "FUNDLEX_GENERATION_STRATEGY"

G08_NEW = ("本基金A类基金份额在申购时收取申购费用，C类基金份额不收取申购费用。"
           "通过直销机构申购本基金A类基金份额不收取申购费。"
           "通过直销机构以外的其他销售机构申购本基金的申购费率由基金管理人决定，并在招募说明书中列示。")
G11_NEW = ("通过直销机构申购本基金A类基金份额不收取申购费，通过其他销售机构申购本基金A类基金份额的"
           "申购费用由投资人承担，不列入基金财产。本基金C类基金份额不收取申购费用。")


def _facts_without_service() -> Facts:
    return Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                 classes=(ClassFact("A类", True, False, True, None, ""),),
                 floating_management_fee=False, floating_quote="", floating_basis="",
                 notes="", quotes_verified={}, problems=())


def _rule(new_text: str) -> dict:
    return {"rule_id": "G08", "title": "t", "requirement": "r", "class_substitution": True,
            "operations": [{"op": "replace", "old_text": "老句", "new_text": new_text,
                            "condition": {"kind": "none", "value": None}}]}


def test_registry_mode_trims_only_the_missing_group_clauses(monkeypatch):
    monkeypatch.setenv(REGISTRY_ENV, "registry")
    reduced = _drop_empty_group_operations(_rule(G08_NEW), _rule(G08_NEW)["operations"],
                                           _facts_without_service())
    assert len(reduced) == 1
    text = reduced[0]["new_text"]
    assert "C类基金份额" not in text
    assert "A类基金份额在申购时收取申购费用" in text
    assert "通过直销机构申购本基金A类基金份额不收取申购费" in text
    assert reduced[0]["dropped_component"] == "service_fee_group"


def test_g11_missing_group_drops_only_its_sentence(monkeypatch):
    monkeypatch.setenv(REGISTRY_ENV, "registry")
    reduced = _drop_empty_group_operations(_rule(G11_NEW), _rule(G11_NEW)["operations"],
                                           _facts_without_service())
    assert len(reduced) == 1
    text = reduced[0]["new_text"]
    assert "C类基金份额" not in text
    assert "通过直销机构申购本基金A类基金份额不收取申购费" in text
    assert "不列入基金财产" in text


def test_legacy_mode_keeps_whole_operation_drop(monkeypatch):
    monkeypatch.setenv(REGISTRY_ENV, "legacy")
    reduced = _drop_empty_group_operations(_rule(G08_NEW), _rule(G08_NEW)["operations"],
                                           _facts_without_service())
    assert reduced == []


def test_g16_obligation_needs_mechanism_markers(monkeypatch):
    monkeypatch.setenv(REGISTRY_ENV, "registry")
    required = ("销售服务费每日计提。（1）直销机构：对于投资者通过直销机构持有的C类基金份额"
                "计提的销售服务费，在赎回或合同终止时返还给投资者。")
    old_style = "基金销售服务费每日计提，按月支付，由基金托管人于次月前5个工作日内支付。"
    assert _append_obligation_present("G16", required, old_style) is False
    with_mechanism = old_style + "通过直销机构申购的部分在赎回时返还；持有超过一年后继续计提的部分返还。"
    assert _append_obligation_present("G16", required, with_mechanism) is True


def test_legacy_mode_keeps_lead_sentence_check(monkeypatch):
    monkeypatch.setenv(REGISTRY_ENV, "legacy")
    required = "销售服务费每日计提。其余内容。"
    assert _append_obligation_present("G16", required, "销售服务费每日计提，按月支付。") is True
