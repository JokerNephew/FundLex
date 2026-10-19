"""Strategy Registry (plan v4 §17, §22).

Keyed by **rule id**; every operation of a rule shares its spec, so
``strategy_for("G14:3")`` resolves through the ``G14`` entry. The registry is
advisory in Phase 1 and must cover every rule group of the compiled guide; the
coverage helper below reports gaps and a unit test enforces it.

Tier choices encode the plan's classification (deterministic-first):

* G14 (structured set removal), G09 (phrase splice), class substitution
  (G02/G04) and fixed appends (G01/G03) — deterministic first;
* G08/G11 — parameterised templates with a splice fallback for mixed clauses;
* delete-only rules (G06/G13/G15/G17) — model locates, program deletes;
* G16 — model compose under the full three-layer validation.
"""
from typing import Any

from .types import GenerationTier as T, StrategySpec

_ALL_CLASS = (T.TEMPLATE, T.SPLICE, T.COMPOSE)

_SPECS: tuple[StrategySpec, ...] = (
    StrategySpec("G01", T.TEMPLATE, (T.TEMPLATE,), mode="append",
                 required_fact_status=("share_class_structure",),
                 required_components=("direct_sales_fee_exemption",),
                 note="释义-份额类别定义：追加直销豁免政策句（固定文本）"),
    StrategySpec("G02", T.TEMPLATE, (T.TEMPLATE,), mode="class_substitution",
                 required_fact_status=("share_class_structure",),
                 note="释义：按收费性质分组替换份额类别"),
    StrategySpec("G03", T.TEMPLATE, (T.TEMPLATE,), mode="append",
                 required_fact_status=("share_class_structure",),
                 note="基本情况-份额类别设置：追加政策句（固定文本）"),
    StrategySpec("G04", T.TEMPLATE, (T.TEMPLATE,), mode="class_substitution",
                 required_fact_status=("share_class_structure",),
                 note="基本情况：按收费性质分组替换份额类别"),
    StrategySpec("G05", T.SPLICE, (T.SPLICE,), mode="replace",
                 note="词级替换/删除（调低赎回费率→调低销售服务费率 或删除备案句）"),
    StrategySpec("G06", T.DELETE, (T.DELETE,), mode="delete",
                 note="删除类别转换旧句：定位用模型、删除用程序"),
    StrategySpec("G07", T.TEMPLATE, (T.TEMPLATE,), mode="replace",
                 required_fact_status=("share_class_structure",),
                 note="单类别：申购费率及直销豁免（模板实例化）"),
    StrategySpec("G08", T.SPLICE, (T.TEMPLATE, T.SPLICE, T.COMPOSE), mode="replace",
                 required_fact_status=("share_class_structure",),
                 required_components=("subscription_fee_group", "service_fee_group"),
                 note="多类别申购费率：干净整句→T1，混合句→T2，语义交织→T3（§19）"),
    StrategySpec("G09", T.SPLICE, (T.TEMPLATE, T.SPLICE), mode="replace",
                 note="赎回金额表述：短语级最小替换"),
    StrategySpec("G10", T.TEMPLATE, (T.TEMPLATE,), mode="replace",
                 required_fact_status=("share_class_structure",),
                 note="单类别：申购费用承担（模板实例化）"),
    StrategySpec("G11", T.SPLICE, (T.TEMPLATE, T.SPLICE, T.COMPOSE), mode="replace",
                 required_fact_status=("share_class_structure",),
                 required_components=("subscription_fee_group", "service_fee_group"),
                 note="多类别申购费用承担：同 G08（§19）；定位须含“申购”主题（§23）"),
    StrategySpec("G12", T.SPLICE, (T.SPLICE, T.COMPOSE), mode="replace",
                 note="赎回费全额计入基金财产：句子级替换"),
    StrategySpec("G13", T.DELETE, (T.DELETE,), mode="delete",
                 note="删除 7 日短期赎回费旧句：定位用模型、删除用程序"),
    StrategySpec("G14", T.TEMPLATE, (T.TEMPLATE, T.SPLICE, T.COMPOSE), mode="replace",
                 required_fact_status=("share_class_structure",),
                 note="结构化集合删除；前置条件不满足降级 T2/T3（§7.1）"),
    StrategySpec("G15", T.DELETE, (T.DELETE,), mode="delete",
                 note="删除销售服务费支付旧条款；出入时记 business_notices（§7.3）"),
    StrategySpec("G16", T.COMPOSE, (T.COMPOSE,), mode="append",
                 required_fact_status=("share_class_structure", "service_fee_group"),
                 required_components=("daily_accrual", "direct_refund",
                                      "non_direct_sales_policy", "over_one_year_refund"),
                 preserve_policy=("fee_rate_formula", "existing_payment_actor",
                                  "existing_payment_path", "existing_payment_timing"),
                 note="Tier3 试点：组件化新增 + 保留原机制（§10/§27）"),
    StrategySpec("G17", T.DELETE, (T.DELETE,), mode="delete",
                 note="删除销售服务费用途旧条款：定位用模型、删除用程序"),
    StrategySpec("G18", T.SPLICE, (T.SPLICE, T.COMPOSE), mode="replace",
                 note="收益分配费用差异表述：句子级替换"),
    StrategySpec("G19", T.SPLICE, (T.SPLICE, T.COMPOSE), mode="replace",
                 note="单类别浮动费：清算分配表述"),
    StrategySpec("G20", T.SPLICE, (T.SPLICE, T.COMPOSE), mode="replace",
                 note="多类别浮动费：清算分配表述（两个操作）"),
    StrategySpec("G21", T.COMPOSE, (T.COMPOSE,), mode="noop",
                 note="noop 操作占位；按需后续裁定"),
    StrategySpec("G22", T.SPLICE, (T.SPLICE, T.COMPOSE), mode="replace",
                 note="非浮动多类别：清算分配表述"),
)

STRATEGY_REGISTRY: dict[str, StrategySpec] = {spec.rule_id: spec for spec in _SPECS}

_UNKNOWN_SPEC = StrategySpec(
    "UNKNOWN", T.COMPOSE, (T.COMPOSE,), mode="replace",
    note="未登记规则的安全侧默认：Tier3 + 全链验证",
)


def _normalize(operation_key: str) -> str:
    """``"G14:3"`` → ``"G14"``; bare rule ids are returned unchanged."""
    return operation_key.split(":", 1)[0].strip().upper()


def strategy_for(operation_key: str) -> StrategySpec:
    """Spec for one operation; unregistered rules fall back to the safe side."""
    rule_id = _normalize(operation_key)
    return STRATEGY_REGISTRY.get(rule_id, _UNKNOWN_SPEC)


def registry_coverage_gaps(guide_document: dict[str, Any]) -> list[str]:
    """Rule ids present in the guide but missing from the registry."""
    gaps: list[str] = []
    for group in guide_document.get("groups") or []:
        rule_id = str(group.get("rule_id") or "").strip().upper()
        if rule_id and rule_id not in STRATEGY_REGISTRY:
            gaps.append(rule_id)
    return sorted(gaps)
