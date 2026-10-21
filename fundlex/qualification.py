"""Independent certification for irreversible whole-contract exclusions."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Sequence

from .recall_prompts import FUND_TYPES

SCHEMA = {"type": "object", "required": ["fund_type", "quote", "reason"], "properties": {
    "fund_type": {"enum": list(FUND_TYPES)}, "quote": {"type": "string"},
    "reason": {"type": "string"}}}

_SIGNATURES = {
    "etf": r"交易型开放式|ETF",
    "money_market": r"货币市场(?:证券投资)?基金|货币型基金",
    "interbank_cd": r"同业存单",
    "qdii": r"QDII|合格境内机构投资者|境外证券投资",
    "reits": r"REITs?|基础设施|不动产",
}


def certify_exclusion(inspection: Any, facts: Any, gateway: Any,
                      excluded_types: Sequence[str]) -> Any:
    from .recall import _quote_present, _is_etf_feeder, facts_context
    if facts.fund_type not in excluded_types:
        return facts
    quote = facts.fund_type_quote
    primary_ok = bool(quote and _quote_present(inspection, quote)
                      and not re.search(r"…|\.{3}|⋯", quote))
    semantic_ok = bool(primary_ok and re.search(_SIGNATURES.get(facts.fund_type, r"(?!)"),
                                               quote, re.IGNORECASE))
    if facts.fund_type == "etf" and _is_etf_feeder(inspection):
        semantic_ok = False
    certification = {"status": "UNKNOWN", "primary_quote_verified": primary_ok,
                     "semantic_verified": semantic_ok, "independent_review": False,
                     "source_sha256": inspection.source_sha256}
    if semantic_ok:
        context = facts_context(inspection, limit=max(1, gateway.max_context_chars - 1500))
        try:
            response = gateway.call(task_type="recall_qualification_review", bounded_context=context,
                response_schema=SCHEMA, prompt_version="recall_qualification_review_v1",
                instruction="Independently classify THIS fund contract's current product type. "
                "A mention of another fund or future conversion is not its current type. "
                "An ETF feeder (联接基金) is open_regular. Return an exact contiguous source "
                "quote proving the current type; return other with empty quote if uncertain.")
        except Exception as exc:
            from .model import ModelError
            if isinstance(exc, ModelError):
                raise
            certification["review_error"] = type(exc).__name__
            statuses = dict(facts.fact_status)
            statuses["fund_type"] = "UNKNOWN"
            return replace(facts, fund_type_certification=certification, fact_status=statuses)
        value = response.value if isinstance(response.value, dict) else {}
        review_type, review_quote = str(value.get("fund_type") or "other"), str(value.get("quote") or "")
        review_ok = bool(review_quote and _quote_present(inspection, review_quote)
                         and not re.search(r"…|\.{3}|⋯", review_quote))
        review_semantic_ok = bool(review_ok and re.search(
            _SIGNATURES.get(review_type, r"(?!)"), review_quote, re.IGNORECASE))
        certification.update(review_fund_type=review_type, review_quote=review_quote,
                             review_quote_verified=review_ok, independent_review=True,
                             status=("CERTIFIED" if review_type == facts.fund_type and
                                     review_semantic_ok else "CONFLICT" if review_ok else "UNKNOWN"))
    statuses = dict(facts.fact_status)
    if certification["status"] != "CERTIFIED":
        statuses["fund_type"] = certification["status"]
    return replace(facts, fund_type_certification=certification, fact_status=statuses)
