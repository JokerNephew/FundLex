"""Operation-aware overlap merge and Joint Compose (plan §21).

A deterministic merge is tried first.  Only when two obligations genuinely overlap and
cannot be proven compatible does the primary model receive the **complete paragraph**
plus every overlapping obligation; the result must satisfy all of them and is then
checked by the same code validator and the independent review role.
"""
from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

JOINT_SCHEMA = {
    "type": "object",
    "required": ["replacement", "preserved", "basis"],
    "properties": {
        "replacement": {"type": "string"},
        "preserved": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
        "basis": {"type": "string"},
    },
}

JOINT_INSTRUCTION = (
    "Rewrite ONLY [AUTHORIZED_SPAN] of the contract paragraph so that EVERY listed "
    "obligation is carried out at the same time. Keep all text outside the authorized "
    "span byte-identical. Preserve fee rates, percentages, amounts, dates, subjects, "
    "formulas, accounts, share classes and every fee topic unless an obligation "
    "explicitly removes it. Do not introduce a number that is not in the source, the "
    "guide text or the verified facts. Return the complete replacement for the span, "
    "not a diff. List the source literals you preserved."
)

JOINT_PROMPT_VERSION = "recall_joint_compose_v1"


def _compact(value: str) -> str:
    import re
    return re.sub(r"[\s\u3000\u00a0\u200b]+", "", value or "")


def plan_joint_compose(*, span_text: str, start: int, end: int,
                       obligations: Sequence[Mapping[str, Any]],
                       fixed_texts: Sequence[str], facts: Any, gateway: Any,
                       rule_ids: Sequence[str]) -> dict[str, Any] | None:
    """Ask the primary model to satisfy all overlapping obligations in one span.

    Returns ``{"replacement", "preserved", "basis"}`` after code validation and
    independent review, or ``None`` when the result is not safe to accept.
    """
    from .components import claim_components_for_rules
    from .validators import Authorization, validate_edit

    actual = span_text[start:end]
    if not actual.strip():
        return None
    context = "\n\n".join([
        "CONTRACT_PARAGRAPH\n" + span_text,
        f"AUTHORIZED_SPAN\nstart={start}\nend={end}\ntext={actual}",
        "OBLIGATIONS\n" + json.dumps(list(obligations), ensure_ascii=False, indent=1),
        "GUIDE_FIXED_TEXTS\n" + json.dumps(list(fixed_texts), ensure_ascii=False),
        "FACTS\n" + json.dumps(facts.as_ledger() if hasattr(facts, "as_ledger") else {},
                              ensure_ascii=False),
    ])
    if len(context) > gateway.max_context_chars:
        return None
    result = gateway.call(task_type="recall_joint_compose", bounded_context=context,
                          response_schema=JOINT_SCHEMA, instruction=JOINT_INSTRUCTION,
                          prompt_version=JOINT_PROMPT_VERSION)
    value = result.value if isinstance(result.value, dict) else {}
    replacement = str(value.get("replacement") or "").strip()
    if not replacement:
        return None
    if not all(_compact(text) in _compact(replacement) for text in fixed_texts if text.strip()):
        return None

    operations: list[Mapping[str, Any]] = []
    for obligation in obligations:
        operations.extend(obligation.get("operations") or [])
    for operation in operations:
        if operation.get("op") != "delete":
            continue
        deleted = _compact(str(operation.get("old_text") or ""))
        if deleted and deleted in _compact(replacement):
            # A joint replacement must actually satisfy every delete obligation; it
            # cannot keep the text the delete was supposed to remove.
            return None
    auth = Authorization(
        must_add=tuple(part.strip() for text in fixed_texts
                       for part in __import__("re").split(r"(?<=[。；])", text)
                       if len(_compact(part)) >= 6),
        remove_patterns=tuple(str(operation.get("old_text") or "")
                              for operation in operations
                              if operation.get("old_text")),
    )
    expected_full = span_text[:start] + replacement + span_text[end:]
    components: list[Mapping[str, Any]] = []
    for rule_id in rule_ids:
        components.extend(claim_components_for_rules([rule_id]))
    validation = validate_edit(actual, replacement, auth=auth,
                               components=tuple(components),
                               before_full=span_text, after_full=expected_full)
    if validation.verdict == "FAIL":
        return None

    review_context = "\n\n".join([
        "BEFORE\n" + actual,
        "AFTER\n" + replacement,
        "OBLIGATIONS\n" + json.dumps(list(obligations), ensure_ascii=False),
        "FACTS\n" + json.dumps(facts.as_ledger() if hasattr(facts, "as_ledger") else {},
                              ensure_ascii=False),
        "PROTECTED_CHECK\n" + json.dumps(validation.as_dict(), ensure_ascii=False),
    ])
    if len(review_context) > gateway.max_context_chars:
        return None
    from ..recall_prompts import VERIFY_INSTRUCTION, VERIFY_PROMPT_VERSION, VERIFY_SCHEMA
    review = gateway.call(task_type="recall_verify", bounded_context=review_context,
                          response_schema=VERIFY_SCHEMA, instruction=VERIFY_INSTRUCTION,
                          prompt_version=VERIFY_PROMPT_VERSION)
    verdict = review.value if isinstance(review.value, dict) else {}
    if str(verdict.get("verdict") or "") != "pass":
        return None
    return {"replacement": replacement,
            "preserved": [str(item) for item in value.get("preserved") or []],
            "basis": str(value.get("basis") or ""),
            "validation": validation.as_dict()}
