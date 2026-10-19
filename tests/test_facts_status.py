"""Phase 3 tests: Facts extension + tri-state evidence (plan v4 §24, §20).

The tri-state rules under test:

* VERIFIED — verified quote and internally consistent;
* UNKNOWN  — no verified evidence (never read as "empty");
* CONFLICT — evidence names a class the contract does not define.
"""
from fundlex.recall import ClassFact, Facts, derive_fact_statuses
from fundlex.recall_prompts import FACTS_SCHEMA


def _class(name: str, subscription: bool, service: bool, current: bool = True) -> ClassFact:
    return ClassFact(name=name, subscription_fee=subscription, service_fee=service,
                     current=current, rate=None, quote=f"{name} quote")


def test_all_verified_facts():
    classes = (_class("A类", True, False), _class("C类", False, True))
    statuses = derive_fact_statuses(
        fund_type_ok=True, classes=classes,
        class_quotes={"A类": True, "C类": True},
        direct_classes=["A类"], direct_ok=True,
        other_classes=["A类"], other_ok=True)
    assert statuses["fund_type"] == "VERIFIED"
    assert statuses["share_class_structure"] == "VERIFIED"
    assert statuses["service_fee_group"] == "VERIFIED"
    assert statuses["direct_sales_exempt_group"] == "VERIFIED"
    assert statuses["other_sales_charged_group"] == "VERIFIED"


def test_unverified_inputs_are_unknown_not_empty():
    classes = (_class("A类", True, False), _class("C类", False, True))
    statuses = derive_fact_statuses(
        fund_type_ok=False, classes=classes,
        class_quotes={"A类": True, "C类": False},
        direct_classes=[], direct_ok=False,
        other_classes=[], other_ok=False)
    assert statuses["fund_type"] == "UNKNOWN"
    assert statuses["share_class_structure"] == "UNKNOWN"
    assert statuses["direct_sales_exempt_group"] == "UNKNOWN"


def test_channel_evidence_naming_unknown_class_is_conflict():
    classes = (_class("A类", True, False),)
    statuses = derive_fact_statuses(
        fund_type_ok=True, classes=classes,
        class_quotes={"A类": True},
        direct_classes=["Z类"], direct_ok=True,
        other_classes=[], other_ok=False)
    assert statuses["direct_sales_exempt_group"] == "CONFLICT"


def test_verified_empty_channel_is_unknown_not_verified():
    classes = (_class("A类", True, False),)
    statuses = derive_fact_statuses(
        fund_type_ok=True, classes=classes,
        class_quotes={"A类": True},
        direct_classes=[], direct_ok=True,
        other_classes=[], other_ok=True)
    # An empty verified list cannot prove "no rule"; the generator may later
    # upgrade it to VERIFIED_EMPTY via the hard-fact topic check (plan §20).
    assert statuses["direct_sales_exempt_group"] == "UNKNOWN"


def test_facts_helper_properties_and_back_compat():
    legacy = Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                   classes=(_class("A类", True, False),), floating_management_fee=False,
                   floating_quote="", floating_basis="", notes="",
                   quotes_verified={}, problems=())
    assert legacy.share_class_structure == "SINGLE"
    assert legacy.status_of("fund_type") == "UNKNOWN"  # unrecorded → never VERIFIED

    multi = Facts(fund_type="open_regular", fund_type_quote="", fund_type_basis="",
                  classes=(_class("A类", True, False), _class("C类", False, True)),
                  floating_management_fee=False, floating_quote="", floating_basis="",
                  notes="", quotes_verified={}, problems=(),
                  direct_sales_exempt_group=("A类",),
                  other_sales_charged_group=("A类",),
                  fact_status={"direct_sales_exempt_group": "VERIFIED"})
    assert multi.share_class_structure == "MULTIPLE"
    assert multi.status_of("direct_sales_exempt_group") == "VERIFIED"
    ledger = multi.as_ledger()
    assert ledger["share_class_structure"] == "MULTIPLE"
    assert ledger["direct_sales_exempt_group"] == ["A类"]
    assert ledger["fact_status"]["direct_sales_exempt_group"] == "VERIFIED"


def test_facts_schema_carries_channel_fields():
    properties = FACTS_SCHEMA["properties"]
    assert "direct_sales_exempt" in properties
    assert "other_sales_charged" in properties
    assert FACTS_SCHEMA["required"] == ["fund_type", "classes", "floating_management_fee"]


def test_ambiguous_double_flag_class_is_conflict():
    classes = (_class("A类", True, False), _class("E类", True, True))
    statuses = derive_fact_statuses(
        fund_type_ok=True, classes=classes,
        class_quotes={"A类": True, "E类": True},
        direct_classes=[], direct_ok=False,
        other_classes=[], other_ok=False)
    assert statuses["share_class_structure"] == "VERIFIED"
    assert statuses["service_fee_group"] == "CONFLICT"
    assert statuses["subscription_fee_group"] == "CONFLICT"
