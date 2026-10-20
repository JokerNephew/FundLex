"""Required policy components and their literal evidence (plan §16).

A component is complete only when **all** of its terms occur inside the same
obligation/site output.  Terms are deliberately short and literal: they describe the
mechanism the guide requires, not a paraphrase.  The registry's
``required_components`` ids resolve here; an unknown id is a configuration error
(fail closed) rather than being silently ignored.
"""
from __future__ import annotations

from typing import Iterable, Mapping

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


class ComponentConfigError(ValueError):
    pass


def component_specs(component_ids: Iterable[str]) -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []
    for component_id in component_ids:
        terms = COMPONENT_TERMS.get(str(component_id))
        if not terms:
            raise ComponentConfigError(f"unknown required component: {component_id!r}")
        specs.append({"id": str(component_id), "terms": tuple(terms)})
    return specs


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
