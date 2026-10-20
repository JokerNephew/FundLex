"""Focused fact recovery (plan §8).

A first UNKNOWN/CONFLICT is not a final failure.  The primary model re-reads a
focused fee/class evidence set; every quote is verified by code exactly like the
generic extraction.  If the answer is still undecided, the independent review model
arbitrates between the original and the recovered evidence.  Only then does the
fact stay UNKNOWN/CONFLICT.
"""
from __future__ import annotations

import json
import os
from dataclasses import replace
from typing import Any

from .recovery import (RecoveryAction, RecoveryAttempt, RecoveryHistory, FailureClass)
from .recall import Facts, facts_context, facts_from_value

FACT_RECOVERY_PROMPT_VERSION = "recall_fact_recover_v1"
FACT_ARBITRATION_PROMPT_VERSION = "recall_fact_arbitrate_v1"

_RECOVERED_CLASS = {
    "type": "object",
    "required": ["name", "subscription_fee", "service_fee", "current", "quote"],
    "properties": {
        "name": {"type": "string"},
        "subscription_fee": {"type": "boolean"},
        "service_fee": {"type": "boolean"},
        "rate": {"type": "string"},
        "current": {"type": "boolean"},
        "quote": {"type": "string"},
    },
}

FACT_RECOVERY_SCHEMA = {
    "type": "object",
    "required": ["classes", "class_set_quote"],
    "properties": {
        "classes": {"type": "array", "maxItems": 24, "items": _RECOVERED_CLASS},
        "class_set_quote": {"type": "string"},
        "direct_sales_exempt": {
            "type": "object",
            "properties": {
                "classes": {"type": "array", "maxItems": 24,
                            "items": {"type": "string"}},
                "quote": {"type": "string"},
                "basis": {"type": "string"},
            },
        },
        "other_sales_charged": {
            "type": "object",
            "properties": {
                "classes": {"type": "array", "maxItems": 24,
                            "items": {"type": "string"}},
                "quote": {"type": "string"},
                "basis": {"type": "string"},
            },
        },
        "notes": {"type": "string"},
    },
}

FACT_RECOVERY_INSTRUCTION = (
    "The generic extraction could not verify the share-class fee facts. Re-read the "
    "contract evidence below and answer only the missing facts. List every current share "
    "class, one entry per class letter or currency variant, with subscription_fee true "
    "only when investors pay a subscription/purchase fee for that class and service_fee "
    "true only when a sales-service fee is accrued from that class's assets. A class "
    "carrying both flags is ambiguous: do not force it into either group. Every quote "
    "must be an exact contiguous copy from the contract text and must directly support "
    "the entry. Do not infer a class letter from another contract. For an empty channel "
    "rule return an empty list and empty quote; never guess. class_set_quote must be an "
    "exact contract sentence that enumerates the fund's current share classes (for "
    "example '本基金将基金份额分为A类、C类和D类不同的类别'); it proves that the list is "
    "complete, so every listed class must appear in that quote."
)

FACT_ARBITRATION_SCHEMA = {
    "type": "object",
    "required": ["choice", "quote", "reason"],
    "properties": {
        "choice": {"enum": ["original", "candidate", "unknown"]},
        "quote": {"type": "string"},
        "reason": {"type": "string"},
    },
}

FACT_ARBITRATION_INSTRUCTION = (
    "Two fee-fact extractions disagree or remain uncertain. Independently read the "
    "contract evidence and choose the extraction that is directly supported by the "
    "contract: original, candidate, or unknown when neither is proven. quote must be an "
    "exact contiguous copy from the contract text that proves the choice; use an empty "
    "quote only for unknown. A class with both a subscription fee and a sales-service "
    "fee does not prove either fee branch."
)

_FEE_FACTS = ("share_class_structure", "subscription_fee_group", "service_fee_group")


def _enabled() -> bool:
    return os.environ.get("FUNDLEX_FACT_RECOVERY", "1").strip().lower() not in {
        "0", "false", "off", "no"}


def _verified_count(facts: Facts, names: tuple[str, ...] = _FEE_FACTS) -> int:
    return sum(1 for name in names if facts.status_of(name) == "VERIFIED")


def _class_set_complete(inspection: Any, candidate: Facts, quote: str) -> bool:
    """The enumeration quote must verify and name every listed current class.

    A verified per-class quote proves that class exists, not that no other class
    exists (plan §7.3).  The focused resolver therefore has to supply the contract's
    own enumeration sentence; code checks that every recovered class appears in it.
    """
    if not quote:
        return False
    from .recall import _verify_quote, _compact
    if not _verify_quote(inspection, quote):
        return False
    compact_quote = _compact(quote)
    if "分为" not in compact_quote and "类别" not in compact_quote:
        return False
    for item in candidate.current_classes:
        letter = str(item.name).strip()
        # Display names may be "A", "A类人民币" etc.; require the class label itself.
        if f"{letter}类" not in compact_quote and letter not in compact_quote:
            return False
    return True


def _candidate_usable(candidate: Facts, original: Facts, *, inspection: Any,
                      class_set_quote: str, require_improvement: bool = True) -> bool:
    if require_improvement and _verified_count(candidate) <= _verified_count(original):
        return False
    # Every current class must carry a code-verified quote.
    for item in candidate.current_classes:
        if not candidate.quotes_verified.get(f"class:{item.name}", False):
            return False
    return _class_set_complete(inspection, candidate, class_set_quote)


def _merge_candidate(original: Facts, candidate: Facts) -> Facts:
    """Take the fee facts from the candidate, never its qualification facts."""
    status = dict(original.fact_status)
    for name in _FEE_FACTS:
        status[name] = candidate.status_of(name)
    status["direct_sales_exempt_group"] = candidate.status_of("direct_sales_exempt_group")
    status["other_sales_charged_group"] = candidate.status_of("other_sales_charged_group")
    return replace(
        original,
        classes=candidate.classes,
        direct_sales_exempt_group=candidate.direct_sales_exempt_group,
        other_sales_charged_group=candidate.other_sales_charged_group,
        fact_status=status,
        quotes_verified={**original.quotes_verified, **candidate.quotes_verified},
        problems=tuple(sorted(set(original.problems) | set(candidate.problems))),
        notes=(original.notes + " | " + candidate.notes).strip(" |"),
    )


def recover_fee_facts(inspection: Any, facts: Facts, gateway: Any, *,
                      force_names: tuple[str, ...] = ()) -> tuple[Facts, dict[str, Any]]:
    """Focused recovery + review arbitration; returns the facts and a history summary.

    ``force_names`` is used after an audit reports a FACT failure: the named facts are
    re-read even when their current status is VERIFIED, and a replacement is accepted
    only through review arbitration with a code-verified enumeration quote.
    """
    forced = bool(force_names)
    missing = tuple(force_names) or tuple(
        name for name in _FEE_FACTS if facts.status_of(name) != "VERIFIED")
    if (not missing and not forced) or not _enabled():
        return facts, {"attempts": 0, "actions": [], "final": "not_required",
                       "missing": list(missing), "history": []}
    history = RecoveryHistory()
    context = "\n\n".join([
        facts_context(inspection, limit=max(4000, gateway.max_context_chars - 3500)),
        "CURRENT_FACTS\n" + json.dumps(facts.as_ledger(), ensure_ascii=False),
        "MISSING_FACTS\n" + json.dumps(list(missing)),
    ])
    if len(context) > gateway.max_context_chars:
        return facts, {"attempts": 0, "actions": [], "final": "context_limit",
                       "missing": list(missing), "history": [],
                       "error": "RECALL_FACTS_CONTEXT_LIMIT"}
    attempt = RecoveryAttempt(RecoveryAction.FOCUSED_FACT_RESOLVE, "facts",
                              FailureClass.FACT, "RECALL_FACT_UNVERIFIED",
                              ",".join(missing), outcome="failed")
    candidate: Facts | None = None
    class_set_quote = ""
    try:
        result = gateway.call(task_type="recall_fact_recover", bounded_context=context,
                              response_schema=FACT_RECOVERY_SCHEMA,
                              instruction=FACT_RECOVERY_INSTRUCTION,
                              prompt_version=FACT_RECOVERY_PROMPT_VERSION)
        value = result.value if isinstance(result.value, dict) else {}
        class_set_quote = str(value.get("class_set_quote") or "")
        candidate = facts_from_value(inspection, {**value,
                                                  "fund_type": {
                                                      "value": facts.fund_type,
                                                      "quote": facts.fund_type_quote,
                                                      "basis": facts.fund_type_basis},
                                                  "floating_management_fee": {
                                                      "value": facts.floating_management_fee,
                                                      "quote": facts.floating_quote,
                                                      "basis": facts.floating_basis}})
    except Exception as exc:  # noqa: BLE001 - recorded, caller keeps the original facts
        attempt.detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
    if candidate is not None and not forced and _candidate_usable(
            candidate, facts, inspection=inspection, class_set_quote=class_set_quote):
        attempt.outcome, attempt.detail = "succeeded", "focused_quotes_verified"
        history.append(attempt)
        return _merge_candidate(facts, candidate), history.summary()
    attempt.detail = attempt.detail or "no_verified_improvement"
    history.append(attempt)

    # Review arbitration: only a quoted choice is accepted; quote verification is code.
    arb_context = "\n\n".join([
        context,
        "ORIGINAL_FACTS\n" + json.dumps(facts.as_ledger(), ensure_ascii=False),
        "CANDIDATE_FACTS\n" + json.dumps((candidate or facts).as_ledger(), ensure_ascii=False),
    ])
    arb_attempt = RecoveryAttempt(RecoveryAction.FACT_ARBITRATION, "facts",
                                  FailureClass.FACT, "RECALL_FACT_UNVERIFIED",
                                  ",".join(missing), outcome="failed")
    if candidate is not None and len(arb_context) <= gateway.max_context_chars:
        try:
            review = gateway.call(task_type="recall_arbitrate",
                                  bounded_context=arb_context,
                                  response_schema=FACT_ARBITRATION_SCHEMA,
                                  instruction=FACT_ARBITRATION_INSTRUCTION,
                                  prompt_version=FACT_ARBITRATION_PROMPT_VERSION)
            value = review.value if isinstance(review.value, dict) else {}
            choice = str(value.get("choice") or "unknown")
            quote = str(value.get("quote") or "")
            from .recall import _verify_quote
            quote_ok = bool(quote) and _verify_quote(inspection, quote)
            if choice == "candidate" and quote_ok and _candidate_usable(
                    candidate, facts, inspection=inspection,
                    class_set_quote=class_set_quote, require_improvement=not forced):
                arb_attempt.outcome = "succeeded"
                arb_attempt.detail = "review_chose_candidate"
                history.append(arb_attempt)
                return _merge_candidate(facts, candidate), history.summary()
            arb_attempt.detail = (f"choice={choice};quote_verified={quote_ok}"
                                  if quote else f"choice={choice}")
        except Exception as exc:  # noqa: BLE001
            arb_attempt.detail = f"{type(exc).__name__}:{getattr(exc, 'code', '')}"
    else:
        arb_attempt.detail = "no_candidate_or_context_limit"
    history.append(arb_attempt)
    return facts, history.summary()
