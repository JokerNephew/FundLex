"""Tri-state applicability (plan §9).

``TRUE`` / ``FALSE`` / ``UNKNOWN`` is a first-class business value: an ``UNKNOWN``
condition never falls through to *either* branch.  The deterministic evaluator reads
VERIFIED facts only.  When it cannot decide, the primary model may judge against
literal contract evidence and the review model may arbitrate; every quote is checked
by code against the original inspection before a decision is accepted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

STATUSES = ("TRUE", "FALSE", "UNKNOWN")

APPLICABILITY_SCHEMA = {
    "type": "object",
    "required": ["status", "quote", "reason"],
    "properties": {
        "status": {"enum": list(STATUSES)},
        "quote": {"type": "string"},
        "reason": {"type": "string"},
    },
}

APPLICABILITY_INSTRUCTION = (
    "Decide whether the GUIDE_CONDITION holds for this contract. Answer TRUE only when "
    "the cited contract text directly proves it, FALSE only when the text directly "
    "proves the opposite, and UNKNOWN when the text does not decide it. quote must be an "
    "exact contiguous copy from [CONTRACT_EVIDENCE] that supports the answer; use an empty "
    "quote only for UNKNOWN. Never infer a share class, fee or branch from habit."
)

ARBITRATION_SCHEMA = {
    "type": "object",
    "required": ["status", "quote", "reason"],
    "properties": {
        "status": {"enum": list(STATUSES)},
        "quote": {"type": "string"},
        "reason": {"type": "string"},
        "rejected_evidence": {"type": "string"},
    },
}

ARBITRATION_INSTRUCTION = (
    "Independently arbitrate the applicability decision for this contract. Read the "
    "contract evidence yourself; do not defer to the earlier decision. Answer TRUE or "
    "FALSE only when an exact contract quote proves it, otherwise UNKNOWN. quote must be "
    "an exact contiguous copy from [CONTRACT_EVIDENCE]. A class that carries both a "
    "subscription fee and a sales-service fee does not prove either fee branch."
)


@dataclass(frozen=True)
class ApplicabilityDecision:
    status: str
    condition: Mapping[str, Any] | None = None
    rule_id: str = ""
    operation_id: str = ""
    source: str = "deterministic"  # deterministic | primary | review | default
    evidence_quote: str = ""
    reason: str = ""
    history: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"invalid applicability status: {self.status!r}")

    @property
    def decidable(self) -> bool:
        return self.status != "UNKNOWN"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "condition": dict(self.condition or {}),
            "rule_id": self.rule_id,
            "operation_id": self.operation_id,
            "source": self.source,
            "evidence_quote": self.evidence_quote,
            "reason": self.reason,
            "history": list(self.history),
        }


def evaluate(condition: Mapping[str, Any] | None, facts: Any, *,
             rule_id: str = "", operation_id: str = "") -> ApplicabilityDecision:
    """Deterministic tri-state evaluation from VERIFIED facts."""
    from .recall import condition_status

    status = condition_status(dict(condition) if condition is not None else None, facts)
    return ApplicabilityDecision(
        status=status,
        condition=condition,
        rule_id=rule_id,
        operation_id=operation_id,
        source="deterministic",
        reason=f"condition_status:{status}",
    )


def _verify_quote(inspection: Any, quote: str) -> bool:
    if not quote:
        return False
    from .recall import _verify_quote as verify

    return bool(verify(inspection, quote))


def _evidence_context(evidence: str, condition: Mapping[str, Any] | None,
                      facts: Any) -> str:
    import json

    return "\n\n".join([
        "CONTRACT_EVIDENCE\n" + (evidence or ""),
        "GUIDE_CONDITION\n" + json.dumps(condition or {"kind": "none"}, ensure_ascii=False),
        "FACTS\n" + json.dumps(facts.as_ledger() if hasattr(facts, "as_ledger") else {},
                              ensure_ascii=False),
    ])


def judge(decision: ApplicabilityDecision, *, gateway: Any, evidence: str,
          facts: Any, inspection: Any) -> ApplicabilityDecision:
    """Primary-model focused judgement; only a code-verified quote is accepted."""
    context = _evidence_context(evidence, decision.condition, facts)
    if len(context) > gateway.max_context_chars:
        return decision
    result = gateway.call(task_type="recall_applicability", bounded_context=context,
                          response_schema=APPLICABILITY_SCHEMA,
                          instruction=APPLICABILITY_INSTRUCTION,
                          prompt_version="recall_applicability_v1")
    value = result.value if isinstance(result.value, dict) else {}
    status = str(value.get("status") or "UNKNOWN")
    quote = str(value.get("quote") or "")
    history = (*decision.history, {"stage": "primary", "status": status,
                                   "reason": str(value.get("reason") or "")})
    if status not in STATUSES:
        status = "UNKNOWN"
    if status in ("TRUE", "FALSE") and not _verify_quote(inspection, quote):
        status = "UNKNOWN"
        reason = "APPLICABILITY_QUOTE_UNVERIFIED"
    else:
        reason = str(value.get("reason") or f"primary:{status}")
    return ApplicabilityDecision(status=status, condition=decision.condition,
                                 rule_id=decision.rule_id,
                                 operation_id=decision.operation_id,
                                 source="primary", evidence_quote=quote,
                                 reason=reason, history=history)


def arbitrate(decision: ApplicabilityDecision, *, gateway: Any, evidence: str,
              facts: Any, inspection: Any) -> ApplicabilityDecision:
    """Review-model arbitration; the review answer still needs a verified quote."""
    context = _evidence_context(evidence, decision.condition, facts)
    context += "\n\nPRIOR_DECISION\n" + __import__("json").dumps(
        {key: value for key, value in decision.as_dict().items()
         if key in {"status", "source", "evidence_quote", "reason"}},
        ensure_ascii=False)
    if len(context) > gateway.max_context_chars:
        return decision
    result = gateway.call(task_type="recall_arbitrate", bounded_context=context,
                          response_schema=ARBITRATION_SCHEMA,
                          instruction=ARBITRATION_INSTRUCTION,
                          prompt_version="recall_arbitrate_v1")
    value = result.value if isinstance(result.value, dict) else {}
    status = str(value.get("status") or "UNKNOWN")
    quote = str(value.get("quote") or "")
    history = (*decision.history, {"stage": "review", "status": status,
                                   "reason": str(value.get("reason") or "")})
    if status not in STATUSES:
        status = "UNKNOWN"
    if status in ("TRUE", "FALSE") and not _verify_quote(inspection, quote):
        status = "UNKNOWN"
        reason = "APPLICABILITY_QUOTE_UNVERIFIED"
    else:
        reason = str(value.get("reason") or f"review:{status}")
    return ApplicabilityDecision(status=status, condition=decision.condition,
                                 rule_id=decision.rule_id,
                                 operation_id=decision.operation_id,
                                 source="review", evidence_quote=quote,
                                 reason=reason, history=history)


def resolve(condition: Mapping[str, Any] | None, facts: Any, *,
            gateway: Any = None, evidence: str = "", inspection: Any = None,
            rule_id: str = "", operation_id: str = "") -> ApplicabilityDecision:
    """Full recovery chain: deterministic → primary judge → review arbitration.

    Without a gateway (offline/unit tests) this is exactly :func:`evaluate`.
    """
    decision = evaluate(condition, facts, rule_id=rule_id, operation_id=operation_id)
    if decision.decidable or gateway is None or inspection is None:
        return decision
    decision = judge(decision, gateway=gateway, evidence=evidence, facts=facts,
                     inspection=inspection)
    if decision.decidable:
        return decision
    return arbitrate(decision, gateway=gateway, evidence=evidence, facts=facts,
                     inspection=inspection)


def branch_key(condition: Mapping[str, Any] | None) -> str:
    """Stable branch identity for one condition mapping."""
    import hashlib
    import json

    raw = json.dumps(condition or {"kind": "none"}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:8]


def describe_condition(condition: Mapping[str, Any] | None) -> str:
    if not condition:
        return "none"
    kind = str(condition.get("kind") or "")
    value = condition.get("value")
    if kind == "none":
        return "none"
    if kind == "compound":
        return "compound(" + ",".join(describe_condition(part)
                                      for part in (value or [])) + ")"
    return f"{kind}={value}"


def resolve_ledger(records: Iterable[Any], *, gateway: Any, inspection: Any, facts: Any,
                   evidence_by_rule: Mapping[str, str],
                   enabled: bool = True) -> list[dict[str, Any]]:
    """Resolve UNKNOWN applicability for scoped rules (plan §9).

    One decision per (rule, condition) is reused by every operation in that branch.
    The result is recorded on the obligation itself; callers must not execute an
    operation whose status is still UNKNOWN.
    """
    history: list[dict[str, Any]] = []
    if not enabled or gateway is None or inspection is None:
        return history
    cache: dict[tuple[str, str], ApplicabilityDecision] = {}
    for record in records:
        spec = getattr(record, "spec", None)
        if spec is None:
            continue
        current = getattr(record, "applicability", None)
        if current is None or current.status != "UNKNOWN":
            continue
        evidence = evidence_by_rule.get(spec.rule_id)
        if evidence is None:
            continue
        key = (spec.rule_id, describe_condition(spec.condition))
        decision = cache.get(key)
        if decision is None:
            decision = resolve(spec.condition, facts, gateway=gateway,
                               evidence=evidence, inspection=inspection,
                               rule_id=spec.rule_id,
                               operation_id=spec.operation_id)
            cache[key] = decision
            history.append({
                "rule_id": spec.rule_id,
                "condition": describe_condition(spec.condition),
                "status": decision.status,
                "source": decision.source,
                "reason": decision.reason,
                "evidence_quote": decision.evidence_quote,
                "history": list(decision.history),
            })
        loose = getattr(record, "applicability", None)
        if loose is not None:
            record.applicability = decision
        statuses = getattr(record, "statuses", None)
        if isinstance(statuses, dict):
            statuses["applicability"] = decision.status
        if decision.status == "FALSE":
            record.completion = "NOT_APPLICABLE"
            record.completion_evidence = f"applicability_false:{decision.reason}"
        elif decision.status == "UNKNOWN":
            record.completion = "UNRESOLVED"
            record.completion_evidence = f"applicability_unknown:{decision.reason}"
        if decision.status in {"TRUE", "FALSE"}:
            overrides = getattr(facts, "condition_overrides", None)
            if isinstance(overrides, dict):
                import json
                overrides[json.dumps(spec.condition or {"kind": "none"}, sort_keys=True,
                                     ensure_ascii=False, separators=(",", ":"))] = decision.status
    return history
