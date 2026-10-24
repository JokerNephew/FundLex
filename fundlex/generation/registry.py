"""Operation-level Strategy Registry (plan v4 §17, §22).

The public rule-level mapping is retained for compatibility, but concrete
operations are indexed separately.  ``strategy_for("G14:3")`` therefore uses
the operation entry first and only falls back to the rule entry for operation
keys that have not yet been compiled into the built-in guide.

Tier choices encode the plan's classification (deterministic-first):

* G14 (structured set removal), G09 (phrase splice), class substitution
  (G02/G04) and fixed appends (G01/G03) — deterministic first;
* G08/G11 — parameterised templates with a splice fallback for mixed clauses;
* delete-only rules (G06/G13/G15/G17) — model locates, program deletes;
* G16 — model compose under the full three-layer validation.
"""
from typing import Any, Mapping

from .components import policy_components_for_operation
from .types import GenerationTier as T, OperationSpec, StrategySpec

_ALL_CLASS = (T.TEMPLATE, T.SPLICE, T.COMPOSE)

_SPECS: tuple[StrategySpec, ...] = (
    StrategySpec("G01", T.TEMPLATE, (T.TEMPLATE,), mode="append",
                 required_fact_status=("share_class_structure",),
                 required_components=("direct_sales_fee_exemption",),
                 note="释义-份额类别定义：追加直销豁免政策句（固定文本）"),
    StrategySpec("G02", T.TEMPLATE, (T.TEMPLATE,), mode="class_substitution",
                 required_fact_status=("share_class_structure", "subscription_fee_group",
                                       "service_fee_group"),
                 note="释义：按收费性质分组替换份额类别"),
    StrategySpec("G03", T.TEMPLATE, (T.TEMPLATE,), mode="append",
                 required_fact_status=("share_class_structure",),
                 note="基本情况-份额类别设置：追加政策句（固定文本）"),
    StrategySpec("G04", T.TEMPLATE, (T.TEMPLATE,), mode="class_substitution",
                 required_fact_status=("share_class_structure", "subscription_fee_group",
                                       "service_fee_group"),
                 note="基本情况：按收费性质分组替换份额类别"),
    StrategySpec("G05", T.SPLICE, (T.SPLICE,), mode="replace",
                 note="词级替换/删除（调低赎回费率→调低销售服务费率 或删除备案句）"),
    StrategySpec("G06", T.DELETE, (T.DELETE,), mode="delete",
                 note="删除类别转换旧句：定位用模型、删除用程序"),
    StrategySpec("G07", T.TEMPLATE, (T.TEMPLATE,), mode="replace",
                 required_fact_status=("share_class_structure",),
                 note="单类别：申购费率及直销豁免（模板实例化）"),
    StrategySpec("G08", T.SPLICE, (T.TEMPLATE, T.SPLICE, T.COMPOSE), mode="replace",
                 required_fact_status=("share_class_structure", "subscription_fee_group",
                                       "service_fee_group"),
                 required_components=("subscription_fee_group", "service_fee_group"),
                 note="多类别申购费率：干净整句→T1，混合句→T2，语义交织→T3（§19）"),
    StrategySpec("G09", T.SPLICE, (T.SPLICE,), mode="replace",
                 note="赎回金额表述：短语级最小替换"),
    StrategySpec("G10", T.TEMPLATE, (T.TEMPLATE,), mode="replace",
                 required_fact_status=("share_class_structure",),
                 note="单类别：申购费用承担（模板实例化）"),
    StrategySpec("G11", T.SPLICE, (T.TEMPLATE, T.SPLICE, T.COMPOSE), mode="replace",
                 required_fact_status=("share_class_structure", "subscription_fee_group",
                                       "service_fee_group"),
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
                 preserve_policy=("fee_rate_formula", "fee_formula",
                                  "other_unauthorized_economic_terms"),
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


def _operation_spec(rule: StrategySpec, index: int, *,
                    default_tier: T | None = None,
                    allowed_tiers: tuple[T, ...] | None = None,
                    mode: str | None = None,
                    required_fact_status: tuple[str, ...] | None = None,
                    required_components: tuple[str, ...] | None = None,
                    executor: str | None = None,
                    condition_kind: str = "",
                    condition_value: Any = None,
                    note: str | None = None) -> OperationSpec:
    """Compile an operation entry without changing the legacy rule object."""
    key = f"{rule.rule_id}:{index}"
    tier = default_tier or rule.default_tier
    tiers = allowed_tiers or rule.allowed_tiers
    components = required_components if required_components is not None \
        else rule.required_components
    facts = required_fact_status if required_fact_status is not None \
        else rule.required_fact_status
    policy = None
    if components or facts:
        policy = policy_components_for_operation(
            key, must_add=components, must_preserve=rule.preserve_policy,
            fact_dependencies=facts,
            preserve_original_qualifiers=(rule.rule_id not in {"G14"}),
        )
    elif rule.preserve_policy:
        policy = policy_components_for_operation(
            key, must_preserve=rule.preserve_policy,
            preserve_original_qualifiers=(rule.rule_id not in {"G14"}),
        )
    selected_executor = executor or {
        T.DELETE: "delete", T.TEMPLATE: "template", T.SPLICE: "splice",
        T.COMPOSE: "compose",
    }[tier]
    return OperationSpec(
        rule_id=rule.rule_id, default_tier=tier, allowed_tiers=tiers,
        mode=mode or rule.mode, required_fact_status=facts,
        required_components=components, preserve_policy=rule.preserve_policy,
        note=note if note is not None else rule.note,
        policy_components=policy, operation_key=key, operation_index=index,
        executor=selected_executor, condition_kind=condition_kind,
        condition_value=condition_value,
    )


# Built-in guide operation inventory.  Keeping this table explicit is
# intentional: it makes operation additions reviewable and prevents a new
# sibling from silently inheriting a rule-level strategy.  The guide remains
# the source of policy text; these entries only describe execution constraints.
_OPERATION_OVERRIDES: dict[str, dict[str, object]] = {
    # G05 has mutually exclusive replace/delete operations with different
    # executors under the same rule.
    "G05:0": {"default_tier": T.SPLICE, "allowed_tiers": (T.SPLICE,)},
    "G05:1": {"default_tier": T.DELETE, "allowed_tiers": (T.DELETE,),
              "mode": "delete", "executor": "delete"},
    "G05:2": {"default_tier": T.DELETE, "allowed_tiers": (T.DELETE,),
              "mode": "delete", "executor": "delete"},
    # G11's first operation is a full clean-clause policy and the second is a
    # smaller source clause; they are routable independently.
    "G11:0": {"default_tier": T.TEMPLATE,
              "allowed_tiers": (T.TEMPLATE, T.SPLICE, T.COMPOSE)},
    "G11:1": {"default_tier": T.SPLICE,
              "allowed_tiers": (T.SPLICE, T.COMPOSE)},
    # The two G12/G20 operations point to different physical sites despite
    # sharing guide text; retain distinct operation identities and evidence.
    "G12:0": {"default_tier": T.SPLICE, "allowed_tiers": (T.SPLICE, T.COMPOSE)},
    "G12:1": {"default_tier": T.SPLICE, "allowed_tiers": (T.SPLICE, T.COMPOSE)},
    "G20:0": {"default_tier": T.SPLICE, "allowed_tiers": (T.SPLICE, T.COMPOSE)},
    "G20:1": {"default_tier": T.SPLICE, "allowed_tiers": (T.SPLICE, T.COMPOSE)},
}


def _build_operation_registry() -> dict[str, OperationSpec]:
    entries: dict[str, OperationSpec] = {}
    # Built-in guide v1 operation counts.  Unknown future operations continue
    # to use the rule fallback until explicitly registered.
    counts = {
        "G01": 1, "G02": 2, "G03": 1, "G04": 2, "G05": 3,
        "G06": 1, "G07": 1, "G08": 1, "G09": 1, "G10": 1,
        "G11": 2, "G12": 2, "G13": 1, "G14": 6, "G15": 1,
        "G16": 1, "G17": 1, "G18": 1, "G19": 1, "G20": 2,
        "G21": 1, "G22": 1,
    }
    for rule_id, count in counts.items():
        rule = STRATEGY_REGISTRY[rule_id]
        for index in range(count):
            override = _OPERATION_OVERRIDES.get(f"{rule_id}:{index}", {})
            entries[f"{rule_id}:{index}"] = _operation_spec(
                rule, index, **override)  # type: ignore[arg-type]
    return entries


OPERATION_REGISTRY: dict[str, OperationSpec] = _build_operation_registry()

_UNKNOWN_SPEC = StrategySpec(
    "UNKNOWN", T.COMPOSE, (T.COMPOSE,), mode="replace",
    note="未登记规则的安全侧默认：Tier3 + 全链验证",
)


def _normalize(operation_key: str) -> str:
    """``"G14:3"`` → ``"G14"``; bare rule ids are returned unchanged."""
    return operation_key.split(":", 1)[0].strip().upper()


def strategy_for(operation_key: str) -> StrategySpec:
    """Spec for one operation, then rule-level compatibility fallback."""
    normalized = str(operation_key or "").strip().upper()
    if ":" in normalized:
        operation = OPERATION_REGISTRY.get(normalized)
        if operation is not None:
            return operation
    rule_id = _normalize(normalized)
    return STRATEGY_REGISTRY.get(rule_id, _UNKNOWN_SPEC)


def operation_for(operation_key: str) -> OperationSpec:
    """Return a concrete operation spec.

    Missing operation entries are intentionally represented by a synthetic spec for
    compatibility with low-level callers.  Routed production callers must check the
    registry explicitly (``operation_registry_coverage_gaps``) before executing.
    """
    normalized = str(operation_key or "").strip().upper()
    operation = OPERATION_REGISTRY.get(normalized)
    if operation is not None:
        return operation
    rule = STRATEGY_REGISTRY.get(_normalize(normalized), _UNKNOWN_SPEC)
    index = 0
    if ":" in normalized:
        try:
            index = int(normalized.rsplit(":", 1)[1])
        except ValueError:
            index = 0
    return _operation_spec(rule, index)


def register_operation(spec: OperationSpec) -> None:
    """Register a custom operation for an extension guide at runtime.

    Registration is explicit and process-local.  It is useful to guide
    adapters and tests; callers should bind the guide version separately.
    """
    key = str(spec.operation_key or "").strip().upper()
    if not key or ":" not in key:
        raise ValueError("operation_key must be RULE_ID:index")
    rule_id, raw_index = key.rsplit(":", 1)
    if not rule_id or not raw_index:
        raise ValueError("operation_key must be RULE_ID:index")
    if spec.operation_key.upper() != key:
        raise ValueError("operation_key must be normalized uppercase")
    if raw_index.isdigit() and int(raw_index) != int(spec.operation_index):
        raise ValueError("operation_index does not match operation_key")
    if spec.rule_id.upper() != rule_id:
        raise ValueError("operation_key rule does not match spec.rule_id")
    OPERATION_REGISTRY[key] = spec


def register_guide_operations(guide_document: Mapping[str, Any], *,
                              specs: Mapping[str, OperationSpec] | None = None) -> list[str]:
    """Register explicitly supplied operation specs for an extension guide.

    Guide text never creates execution policy by itself.  Every operation must have a
    matching ``OperationSpec`` supplied by the controlled publisher; otherwise the
    returned gaps are a release-blocking signal.  Built-in entries are left intact.
    """
    supplied = {str(key).strip().upper(): value for key, value in (specs or {}).items()}
    gaps: list[str] = []
    for group in guide_document.get("groups") or ():
        if not isinstance(group, Mapping):
            continue
        rule_id = str(group.get("rule_id") or "").strip().upper()
        for index, operation in enumerate(group.get("operations") or ()):
            if not isinstance(operation, Mapping):
                continue
            declared = str(operation.get("operation_id") or "").strip().upper()
            key = declared or f"{rule_id}:{index}"
            if key in OPERATION_REGISTRY:
                continue
            spec = supplied.get(key)
            if spec is None:
                gaps.append(key)
                continue
            register_operation(spec)
    return sorted(set(gaps))


def registry_coverage_gaps(guide_document: dict[str, Any]) -> list[str]:
    """Rule ids present in the guide but missing from the registry."""
    gaps: list[str] = []
    for group in guide_document.get("groups") or []:
        rule_id = str(group.get("rule_id") or "").strip().upper()
        if rule_id and rule_id not in STRATEGY_REGISTRY:
            gaps.append(rule_id)
    return sorted(gaps)


def operation_registry_coverage_gaps(guide_document: Mapping[str, Any]) -> list[str]:
    """Return guide operation keys absent from the operation registry."""
    gaps: list[str] = []
    for group in guide_document.get("groups") or []:
        if not isinstance(group, Mapping):
            continue
        rule_id = str(group.get("rule_id") or "").strip().upper()
        for index, operation in enumerate(group.get("operations") or []):
            if isinstance(operation, Mapping):
                key = str(operation.get("operation_id") or f"{rule_id}:{index}").strip().upper()
                if key not in OPERATION_REGISTRY:
                    gaps.append(key)
    return sorted(gaps)
