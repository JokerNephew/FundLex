"""Tier-1 deterministic generators (plan v4 §7, §25).

Pure text transforms: given the target span and the operation's authorized
values, they produce the replacement **without any model call**. The caller
(``recall.plan_target``) wraps a result into a ``PlannedEdit``; nothing here
imports the recall module, so the functions are trivially testable and cannot
create import cycles.

Enabled only when ``FUNDLEX_GENERATION_STRATEGY=registry`` (the flag check
lives at the call site, not here).
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher

#: Fee items a G14 list can enumerate ("申购费率", "销售服务费率", …).
_FEE_ITEM = re.compile(r"(申购|赎回|认购|转换|销售服务|管理|托管)费率")
_SEPARATORS = "、，,和以及与"


@dataclass(frozen=True)
class TemplateResult:
    replacement: str
    content_source: str
    evidence: dict


def _compact(value: str) -> str:
    return re.sub(r"[\s\u3000\u00a0\u200b]+", "", value or "")


def fee_items(text: str) -> set[str]:
    return {match.group(0) for match in _FEE_ITEM.finditer(text or "")}


def _item_spans(text: str) -> list[tuple[int, int, str]]:
    return [(match.start(), match.end(), match.group(0))
            for match in _FEE_ITEM.finditer(text or "")]


def _surface_start(text: str, start: int) -> int:
    """Extend an item's span over its own descriptor prefix ("基金申购费率")."""
    for prefix in ("基金", "的基金"):
        if text[max(0, start - len(prefix)):start] == prefix:
            return start - len(prefix)
    return start


def plan_fee_item_removal(before: str, allowed: set[str],
                          canonical_tail: str = "") -> TemplateResult | None:
    """G14: remove the fee items the guide no longer allows (plan §7.1).

    Two modes, chosen by the ruling of 2026-10-19:

    * the list is followed only by sentence punctuation and the clause between
      the verb and the list carries extra qualifiers ("全部或者部分份额类别")
      -> **converge**: rewrite the clause tail to the guide's canonical tail
      (qualifiers are authorized to disappear, ``full_authorized_clause``);
    * otherwise -> **rebuild**: keep every surviving item's own surface form
      verbatim and re-join with "、" / "和".
    """
    spans = _item_spans(before)
    if not spans:
        return None
    current = {item for _, _, item in spans}
    remove = current - allowed
    if not remove:
        return None
    first_start = _surface_start(before, spans[0][0])
    last_end = spans[-1][1]
    tail = before[last_end:]

    if tail.strip() in ("。", "；", "。 ") and canonical_tail:
        head = before[:first_start]
        verb_at = head.rfind("调低")
        if verb_at >= 0:
            head = before[:verb_at + len("调低")]
        qualifier = before[(verb_at + len("调低")) if verb_at >= 0 else first_start:first_start]
        if any(ch not in "基金的确所有 " for ch in qualifier):
            # Qualifier present ("全部或者部分份额类别的…"): converge to the guide.
            replacement = head + canonical_tail
        else:
            replacement = _rebuild(before, spans, allowed, first_start, last_end, tail)
    else:
        replacement = _rebuild(before, spans, allowed, first_start, last_end, tail)
    if replacement is None:
        return None

    if fee_items(replacement) - allowed:
        return None
    if len(_compact(replacement)) >= len(_compact(before)):
        return None
    if "、、" in replacement or replacement.endswith(("、", "和")):
        return None
    return TemplateResult(replacement=replacement, content_source="tier1_template",
                          evidence={"mode": "g14_fee_item_removal",
                                    "removed": sorted(remove),
                                    "allowed": sorted(allowed)})


def _rebuild(before: str, spans: list[tuple[int, int, str]], allowed: set[str],
             first_start: int, last_end: int, tail: str) -> str | None:
    surfaces: list[str] = []
    for start, end, item in spans:
        if item not in allowed:
            continue
        surface_start = _surface_start(before, start)
        surfaces.append(before[surface_start:end])
    if not surfaces:
        return None
    if len(surfaces) == 1:
        joined = surfaces[0]
    else:
        joined = "、".join(surfaces[:-1]) + "和" + surfaces[-1]
    return before[:first_start] + joined + tail


def splice_pairs(old_text: str, new_text: str, *, window: int = 6
                 ) -> list[tuple[str, str]]:
    """Bounded (old, new) context pairs derived from one operation's texts.

    For G09 the guide rewrites "并扣除相应的费用" into "并扣除或加上相应的费用"
    while the contract keeps a neighbouring wording; the pair carries enough
    context (equal text around the change) that it can be applied as a
    substring replacement without a model call.
    """
    old_text, new_text = old_text or "", new_text or ""
    pairs: list[tuple[str, str]] = []
    matcher = SequenceMatcher(None, old_text, new_text)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        left = old_text[max(0, i1 - window):i1]
        right = old_text[i2:i2 + window]
        old_ctx = left + old_text[i1:i2] + right
        new_ctx = left + new_text[j1:j2] + right
        if _compact(old_ctx) and old_ctx != new_ctx:
            pairs.append((old_ctx, new_ctx))
    return pairs


def plan_splice(before: str, pairs: list[tuple[str, str]]) -> TemplateResult | None:
    """Apply the bounded context pairs that occur verbatim in the span."""
    replacement = before
    applied: list[list[str]] = []
    for old_ctx, new_ctx in pairs:
        if old_ctx and old_ctx in replacement and new_ctx not in replacement:
            candidate = replacement.replace(old_ctx, new_ctx, 1)
            if _compact(candidate) == _compact(replacement):
                continue
            replacement = candidate
            applied.append([old_ctx, new_ctx])
    if not applied:
        return None
    if len(_compact(replacement)) < len(_compact(before)) - 120:
        return None
    return TemplateResult(replacement=replacement, content_source="tier1_splice",
                          evidence={"mode": "bounded_splice", "applied": applied})
