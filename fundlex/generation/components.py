"""Required policy components and their literal evidence (plan §16).

A component is complete only when **all** of its terms occur inside the same
obligation/site output.  Terms are deliberately short and literal: they describe the
mechanism the guide requires, not a paraphrase.  The registry's
``required_components`` ids resolve here; an unknown id is a configuration error
(fail closed) rather than being silently ignored.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from .types import (ComponentRequirement, PolicyComponents,
                    PreserveRequirement)

COMPONENT_TERMS: dict[str, tuple[str, ...]] = {
    # G15/G16/G17 sales-service-fee mechanism.
    "daily_accrual": ("每日计提", "计提"),
    "direct_refund": ("直销",),
    "non_direct_sales_policy": ("其他销售机构", "直销机构之外"),
    "over_one_year_refund": ("超过一年", "超过1年", "满一年"),
    # G01/G03 direct-sales exemption.
    "direct_sales_fee_exemption": ("直销", "不收取"),
    # G08/G11 fee groups.
    "subscription_fee_group": ("申购费",),
    "service_fee_group": ("销售服务费",),
}

# These are intentionally policy-level names.  The contract's concrete class
# letters are parameters supplied by verified facts and must not be invented
# by this module.
COMPONENT_KINDS: dict[str, str] = {
    "daily_accrual": "fee_policy",
    "direct_refund": "fee_policy",
    "non_direct_sales_policy": "fee_policy",
    "over_one_year_refund": "fee_policy",
    "direct_sales_fee_exemption": "fee_policy",
    "subscription_fee_group": "fee_group",
    "service_fee_group": "fee_group",
}


class ComponentConfigError(ValueError):
    pass


def component_specs(component_ids: Iterable[str]) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for component_id in component_ids:
        terms = COMPONENT_TERMS.get(str(component_id))
        if not terms:
            raise ComponentConfigError(f"unknown required component: {component_id!r}")
        specs.append({"id": str(component_id), "kind": COMPONENT_KINDS.get(
            str(component_id), "policy"), "terms": tuple(terms)})
    return specs


def component_requirements(component_ids: Iterable[str]) -> tuple[ComponentRequirement, ...]:
    """Return typed requirements while retaining ``component_specs`` as a dict API."""
    return tuple(
        ComponentRequirement(
            id=str(item["id"]), kind=str(item.get("kind") or "policy"),
            terms=tuple(str(term) for term in item.get("terms", ())),
        )
        for item in component_specs(component_ids)
    )


def policy_components_for_operation(operation_key: str, *,
                                    must_add: Iterable[str] = (),
                                    must_remove: Iterable[str] = (),
                                    must_preserve: Iterable[str] = (),
                                    parameters: Mapping[str, Any] | None = None,
                                    fact_dependencies: Iterable[str] = (),
                                    rewrite_scope: str = "minimal",
                                    preserve_original_qualifiers: bool = True
                                    ) -> PolicyComponents:
    """Build the operation's policy boundary from registry declarations.

    Callers may use this for custom guides as well; unknown component ids fail
    closed through :func:`component_requirements`.
    """
    preserves = tuple(
        item if isinstance(item, PreserveRequirement)
        else PreserveRequirement(id=str(item))
        for item in must_preserve
    )
    return PolicyComponents(
        operation_key=str(operation_key),
        must_add=component_requirements(must_add),
        must_remove=component_requirements(must_remove),
        must_preserve=preserves,
        parameters=dict(parameters or {}),
        rewrite_scope=rewrite_scope,
        preserve_original_qualifiers=preserve_original_qualifiers,
        fact_dependencies=tuple(str(item) for item in fact_dependencies),
    )


def components_for_rules(rule_ids: Iterable[str]) -> list[dict[str, object]]:
    """Resolve the registry's required components for a set of rule ids."""
    from .registry import strategy_for

    wanted: list[str] = []
    for rule_id in rule_ids:
        spec = strategy_for(rule_id)
        for component in spec.required_components:
            if component not in wanted:
                wanted.append(component)
    return component_specs(wanted)


#: Components that must be proven in the **output paragraph**. This is narrower than
#: the registry's fact/strategy metadata: G08/G11 only need the subscription-fee
#: group in their own clause, while G16 must carry the complete payment mechanism.
CLAIM_COMPONENTS: dict[str, tuple[str, ...]] = {
    "G01": ("direct_sales_fee_exemption",),
    "G03": ("direct_sales_fee_exemption",),
    "G16": ("daily_accrual", "direct_refund", "non_direct_sales_policy",
            "over_one_year_refund"),
}


def claim_components_for_rules(rule_ids: Iterable[str],
                               rules_by_id: Mapping[str, Mapping[str, object]] | None = None
                               ) -> list[dict[str, object]]:
    """Components the artifact paragraph must contain for the given rules.

    When the guide rules are supplied, a component is required only if the rule's own
    fixed text actually names its mechanism. This keeps the check tied to the guide
    (a shorter guide version cannot demand text it never asked for) while the builtin
    guide's full G16 wording still requires all four components.
    """
    wanted: list[str] = []
    for rule_id in rule_ids:
        key = str(rule_id).strip().upper()
        for component in CLAIM_COMPONENTS.get(key, ()):
            if component in wanted:
                continue
            if rules_by_id is not None:
                rule = rules_by_id.get(key) or {}
                fixed = "".join(str(operation.get("new_text") or "")
                                for operation in (rule.get("operations") or [])
                                if isinstance(operation, Mapping))
                terms = COMPONENT_TERMS.get(component, ())
                if fixed and not any(term in fixed for term in terms):
                    continue
            wanted.append(component)
    return component_specs(wanted)


def has_component(component_id: str, text: str, *, compact: bool = True) -> bool:
    from .validators import _compact

    body = _compact(text) if compact else (text or "")
    terms = COMPONENT_TERMS.get(component_id)
    if not terms:
        raise ComponentConfigError(f"unknown required component: {component_id!r}")
    return any((_compact(term) if compact else term) in body for term in terms)
