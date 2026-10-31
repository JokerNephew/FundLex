"""Executability canary for parsed guides (FL-D648 closure).

A parsed guide is only useful when the recall engine can actually execute its
operations.  The canary replays the runtime's own admission decision
deterministically — no model call, no contract document:

* authoritative operation identities must resolve to a registered operation
  contract (the exact predicate the runtime router fails closed on,
  ``RECALL_OPERATION_REGISTRY_MISSING``);
* every condition must be satisfiable by at least one assignment of the fact
  space the engine supports (dead branches are parsing bugs, not policy);
* registered operations must route without fact blocking when every fact is
  verified;
* the obligation compiler must rebuild exactly one record per operation.

Legacy documents (no ``operation_id`` anywhere) are tolerated the same way the
runtime tolerates them: unknown legacy rules become advisories, never fatal,
because the runtime executes them through the low-level compatibility path.

Findings are graded: ``fatal`` findings block certification/enabling (the
version enters the owner-visible review list instead of being silently
enabled); ``advisory`` findings only enrich the review verdict.
"""
from __future__ import annotations

from typing import Any, Mapping

CANARY_SCHEMA_VERSION = "guide-canary-v1"

# The fact fields the recall runtime may query; all are VERIFIED for the
# canary so route decisions exercise the full fact dimension (FL-D445:
# deterministic, zero model spend).
_FACT_STATUS_ALL_VERIFIED = {
    "fund_type": "VERIFIED",
    "share_class_structure": "VERIFIED",
    "subscription_fee_group": "VERIFIED",
    "service_fee_group": "VERIFIED",
    "direct_sales_exempt_group": "VERIFIED",
    "other_sales_charged_group": "VERIFIED",
    "floating_management_fee": "VERIFIED",
    "floating": "VERIFIED",
}


class _CanaryFacts:
    """Synthetic contract facts for condition satisfiability enumeration."""

    fact_status: dict[str, str] = dict(_FACT_STATUS_ALL_VERIFIED)

    def __init__(self, *, class_count: int, has_service_fee: bool,
                 floating_management_fee: bool):
        self.class_count = class_count
        self.has_service_fee = has_service_fee
        self.floating_management_fee = floating_management_fee
        self.quotes_verified = {"floating": True}

    def status_of(self, name: str) -> str:
        return "VERIFIED"


def _fact_assignments() -> list[_CanaryFacts]:
    """Every assignment of the boolean/count fact space the engine evaluates."""
    return [_CanaryFacts(class_count=count, has_service_fee=service,
                         floating_management_fee=floating)
            for count in (1, 2) for service in (False, True)
            for floating in (False, True)]


def _declared_key(rule_id: str, index: int, operation: Mapping[str, Any]) -> str:
    """Mirror ``fundlex.recall._declared_operation_key`` (admission parity)."""
    declared = str(operation.get("operation_id") or "").strip().upper()
    return declared or f"{rule_id}:{index}"


def _rules(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [group for group in (document or {}).get("groups") or []
            if isinstance(group, Mapping)]


def _operations(rule: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [operation for operation in (rule.get("operations") or [])
            if isinstance(operation, Mapping)]


def _identity_state(rule: Mapping[str, Any]) -> str:
    """``authoritative`` | ``legacy`` | ``partial`` — the runtime's exact split."""
    operations = _operations(rule)
    if not operations:
        return "legacy"
    declared = [str(operation.get("operation_id") or "").strip()
                for operation in operations]
    if any(declared) and not all(declared):
        return "partial"
    return "authoritative" if any(declared) else "legacy"


def blocking_gaps(document: Mapping[str, Any]) -> list[str]:
    """Runtime-exact admission predicate: operation keys that cannot execute.

    A key lands here precisely when the runtime router would raise
    ``RECALL_OPERATION_REGISTRY_MISSING`` (authoritative identity absent from
    the operation registry) or ``RECALL_OPERATION_ID_MISSING`` (partially
    annotated rule, reported as the rule id).  Legacy rules never block.
    """
    from .generation.registry import OPERATION_REGISTRY

    gaps: list[str] = []
    for rule in _rules(document):
        rule_id = str(rule.get("rule_id") or "").strip().upper()
        state = _identity_state(rule)
        if state == "partial":
            gaps.append(rule_id or "?")
            continue
        if state != "authoritative":
            continue
        for index, operation in enumerate(_operations(rule)):
            key = _declared_key(rule_id, index, operation)
            if key not in OPERATION_REGISTRY:
                gaps.append(key)
    return sorted(set(gaps))


def _condition_satisfiable(condition: Mapping[str, Any]) -> bool:
    if not isinstance(condition, Mapping) or condition.get("kind") in (None, "none"):
        return True
    from .applicability import evaluate
    for facts in _fact_assignments():
        if evaluate(condition, facts).status == "TRUE":
            return True
    return False


def executability_report(document: Mapping[str, Any]) -> dict[str, Any]:
    """Full canary verdict for one parsed guide document."""
    from .generation.registry import OPERATION_REGISTRY, STRATEGY_REGISTRY
    from .generation.router import route_operation

    fatal: list[dict[str, Any]] = []
    advisory: list[dict[str, Any]] = []
    operation_count = 0
    authoritative_count = 0
    routed = 0
    for rule in _rules(document):
        rule_id = str(rule.get("rule_id") or "").strip().upper()
        state = _identity_state(rule)
        operations = _operations(rule)
        if state == "partial":
            fatal.append({"code": "GUIDE_CANARY_PARTIAL_IDENTITY", "rule_id": rule_id,
                          "detail": "规则操作标识不完整：运行时按权威契约处理并拒绝执行"})
            operation_count += len(operations)
            continue
        if state == "legacy":
            if operations and rule_id not in STRATEGY_REGISTRY:
                advisory.append({"code": "GUIDE_CANARY_LEGACY_RULE_UNREGISTERED",
                                 "rule_id": rule_id,
                                 "detail": "旧式规则未注册策略，运行时将走低层兼容路径"})
            operation_count += len(operations)
            continue
        for index, operation in enumerate(operations):
            operation_count += 1
            authoritative_count += 1
            key = _declared_key(rule_id, index, operation)
            if key not in OPERATION_REGISTRY:
                fatal.append({"code": "GUIDE_CANARY_OP_UNREGISTERED", "rule_id": rule_id,
                              "operation": key,
                              "detail": "操作未映射到已注册执行契约，运行时必然失败（操作注册缺失）"})
                continue
            decision = route_operation(key, fact_status=_FACT_STATUS_ALL_VERIFIED,
                                       structure=None)
            if decision.blocked:
                fatal.append({"code": "GUIDE_CANARY_ROUTE_BLOCKED", "rule_id": rule_id,
                              "operation": key,
                              "detail": "全事实已验证下路由仍被阻断: "
                                        + str(decision.fallback_reason or "")})
                continue
            routed += 1
            condition = operation.get("condition")
            if isinstance(condition, Mapping) and condition.get("kind") not in (None, "none"):
                if not _condition_satisfiable(condition):
                    fatal.append({"code": "GUIDE_CANARY_DEAD_CONDITION", "rule_id": rule_id,
                                  "operation": key,
                                  "detail": "分支条件在引擎支持的事实空间内恒不成立（解析把互斥分支条件写错或合并）"})
    ledger_count = operation_count
    try:
        from .obligations import compile_obligations
        ledger_count = len(compile_obligations(document).records)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        fatal.append({"code": "GUIDE_CANARY_COMPILE_FAILED", "rule_id": "",
                      "detail": f"义务编译无法重建操作计划: {type(exc).__name__}"})
    else:
        if ledger_count != operation_count:
            fatal.append({"code": "GUIDE_CANARY_COMPILE_MISMATCH", "rule_id": "",
                          "detail": f"义务计划条目 {ledger_count} 与操作数 {operation_count} 不一致"})
    return {"schema_version": CANARY_SCHEMA_VERSION,
            "rules_total": len(_rules(document)),
            "operations_total": operation_count,
            "authoritative_operations": authoritative_count,
            "routed_operations": routed,
            # Legacy operations run through the low-level compatibility path;
            # they are neither routable nor at risk, so the ratio measures only
            # the authoritative (registry-contract) surface.
            "executable_ratio": (routed / authoritative_count) if authoritative_count else 1.0,
            "fatal": fatal,
            "advisory": advisory,
            "blocking_gaps": sorted({item["operation"] for item in fatal
                                     if item.get("operation")}),
            "passed": not fatal}


def review_dimensions(report: Mapping[str, Any]) -> dict[str, Any]:
    """Compact canary dimensions for the owner-visible review verdict."""
    return {"canary_schema": report.get("schema_version"),
            "operations_total": report.get("operations_total"),
            "routed_operations": report.get("routed_operations"),
            "executable_ratio": report.get("executable_ratio"),
            "fatal_codes": sorted({str(item.get("code")) for item in report.get("fatal") or []}),
            "blocking_gaps": list(report.get("blocking_gaps") or []),
            "fatal_detail": [dict(item) for item in (report.get("fatal") or [])][:20],
            "advisory_codes": sorted({str(item.get("code"))
                                      for item in report.get("advisory") or []})}
