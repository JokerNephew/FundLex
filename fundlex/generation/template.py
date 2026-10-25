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
from typing import Any, Mapping

from .types import PolicyComponents

#: Fee items a G14 list can enumerate ("申购费率", "销售服务费率", …).
_FEE_ITEM = re.compile(r"(申购|赎回|认购|转换|销售服务|管理|托管)费率")
_SEPARATORS = "、，,和以及与"


@dataclass(frozen=True)
class TemplateResult:
    replacement: str
    content_source: str
    evidence: dict
    #: The typed policy boundary used for this result, when the caller supplied
    #: one.  The first three fields remain unchanged for old callers.
    policy_components: PolicyComponents | None = None

    def as_dict(self) -> dict[str, Any]:
        value = {"replacement": self.replacement,
                 "content_source": self.content_source,
                 "evidence": dict(self.evidence)}
        if self.policy_components is not None:
            value["policy_components"] = self.policy_components.as_dict()
        return value


def apply_policy_template(*, before: str, instantiated: str,
                          operation_key: str, components: PolicyComponents,
                          rule_id: str | None = None) -> TemplateResult | None:
    """Apply a deterministic replacement under an explicit policy boundary.

    This is the generic entry point for operation-aware callers.  It only
    emits text supplied by the guide/slot instantiator and requires the policy
    object's operation identity to match the requested operation.
    """
    if components.operation_key != operation_key:
        raise ValueError("POLICY_OPERATION_MISMATCH")
    replacement = (instantiated or "").strip()
    if not before or not replacement or _compact(before) == _compact(replacement):
        return None
    return TemplateResult(
        replacement=replacement,
        content_source="tier1_template",
        evidence={"mode": "policy_template", "operation_key": operation_key,
                  "rule": rule_id or operation_key.split(":", 1)[0]},
        policy_components=components,
    )


def apply_policy_splice(*, before: str, pairs: list[tuple[str, str]],
                        operation_key: str,
                        components: PolicyComponents) -> TemplateResult | None:
    """Operation-aware bounded splice with policy evidence attached."""
    if components.operation_key != operation_key:
        raise ValueError("POLICY_OPERATION_MISMATCH")
    result = plan_splice(before, pairs)
    if result is None:
        return None
    return TemplateResult(
        result.replacement, result.content_source,
        {**result.evidence, "operation_key": operation_key}, components)


def clause_number_prefix(text: str) -> str:
    """Return only a literal leading clause number, never neighbouring prose."""
    match = re.match(
        r"\s*(?:[0-9０-９一二三四五六七八九十百]{1,6}[、．]|"
        r"[0-9０-９]{1,6}\.(?![0-9０-９])|"
        r"[（(][0-9０-９一二三四五六七八九十百]{1,6}[）)])\s*", text)
    return match.group(0) if match else ""


def plan_policy_replacement(before: str, instantiated: str, rule_id: str) -> TemplateResult | None:
    """Clean-clause deterministic policy replacement (plan §19.1).

    A *clean* clause (no redemption / conversion / calculation / announcement
    content mixed in) converges to the guide sentence as a **Template-tier**
    edit; mixed clauses are rejected here and keep the splice/compose cascade,
    so nothing extra is ever swallowed.
    """
    compact = _compact(before)
    if not compact or not instantiated or not instantiated.strip():
        return None
    if rule_id == "G08":
        anchor_ok = "申购费率由基金管理人决定" in compact and "招募说明书" in compact
        forbidden = ("赎回", "转换", "计算方法", "公告", "收费方式", "认购")
    elif rule_id == "G11":
        anchor_ok = "申购费用由" in compact and ("承担" in compact or "不列入基金财产" in compact)
        forbidden = ("赎回", "认购", "转换", "公告", "计算方法")
    else:
        return None
    if not anchor_ok or any(word in compact for word in forbidden):
        return None
    replacement = clause_number_prefix(before) + instantiated.strip()
    if _compact(replacement) == compact:
        return None
    return TemplateResult(replacement=replacement, content_source="tier1_template",
                          evidence={"mode": "clean_clause_policy_replacement",
                                    "rule": rule_id})


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
                          canonical_tail: str = "",
                          allowed_order: list[str] | None = None) -> TemplateResult | None:
    """G14: remove the fee items the guide no longer allows (plan §7.1).

    Two modes, chosen by the ruling of 2026-10-19:

    * the guide wording **adds** an item the contract does not enumerate, or the
      list carries extra qualifiers ("全部或者部分份额类别") at sentence end
      -> **converge**: rewrite the clause tail to the guide's canonical wording;
    * otherwise -> **rebuild**: keep every surviving item's own surface form
      verbatim, ordered by the guide's own item order (the scorer compares
      against the guide sentence).
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
    sentence_end = tail.strip() == "。"

    if sentence_end and canonical_tail:
        # The clause ends with the fee list: converge to the guide's exact
        # wording (the 2026-10-19 ruling: direct replacement with the new
        # sentence; qualifiers and item order are authorized to converge).
        replacement = _converge(before, first_start, canonical_tail)
    else:
        replacement = _rebuild(before, spans, allowed, first_start, last_end, tail,
                               allowed_order, canonical_tail=canonical_tail)
    if replacement is None:
        return None

    if fee_items(replacement) - allowed:
        return None
    if _compact(replacement) == _compact(before):
        return None
    if "、、" in replacement or replacement.endswith(("、", "和")):
        return None
    return TemplateResult(replacement=replacement, content_source="tier1_template",
                          evidence={"mode": "g14_fee_item_removal",
                                    "removed": sorted(remove),
                                    "allowed": sorted(allowed)})


def _rebuild(before: str, spans: list[tuple[int, int, str]], allowed: set[str],
             first_start: int, last_end: int, tail: str,
             allowed_order: list[str] | None = None,
             *, canonical_tail: str = "") -> str | None:
    kept: list[tuple[str, str]] = []
    present: set[str] = set()
    for start, end, item in spans:
        if item not in allowed:
            continue
        surface_start = _surface_start(before, start)
        kept.append((item, before[surface_start:end]))
        present.add(item)
    missing = [item for item in (allowed_order or []) if item not in present]
    if missing:
        # Never manufacture wording from an item label (for example ``基金`` +
        # ``销售服务费率``).  A missing item is safe only when the operation supplied
        # the complete canonical wording from which its surface form can be copied.
        canonical_surfaces = {
            item: canonical_tail[start:end]
            for start, end, item in _item_spans(canonical_tail)
        }
        if any(item not in canonical_surfaces for item in missing):
            return None
        for item in missing:
            kept.append((item, canonical_surfaces[item]))
    if not kept:
        return None
    if allowed_order:
        order = {item: index for index, item in enumerate(allowed_order)}
        kept.sort(key=lambda pair: order.get(pair[0], 99))
    surfaces = [surface for _, surface in kept]
    if len(surfaces) == 1:
        joined = surfaces[0]
    else:
        joined = "、".join(surfaces[:-1]) + "和" + surfaces[-1]
    return before[:first_start] + joined + tail


def _converge(before: str, first_start: int, canonical_tail: str) -> str:
    """Rewrite the clause from the verb to the guide's canonical tail."""
    head = before[:first_start]
    verb_at = head.rfind("调低")
    if verb_at >= 0:
        head = before[:verb_at + len("调低")]
    return head + canonical_tail


#: Known contract variants for G09 that the guide's own old→new diff does not
#: spell out literally (multi-class wording adds the class reference).
_G09_VARIANTS: tuple[tuple[str, str], ...] = (
    ("并扣除相应的费用", "并扣除或加上相应的费用"),
    ("并扣除其他相应的费用", "并扣除或加上相应的费用"),
    ("当日基金份额净值", "当日该类基金份额的基金份额净值"),
    ("当日该类基金份额净值", "当日该类基金份额的基金份额净值"),
    ("当日对应份额类别的基金份额净值", "当日该类基金份额的基金份额净值"),
)


def plan_g09_splice(before: str, pairs: list[tuple[str, str]]) -> TemplateResult | None:
    """G09: apply the guide-derived pairs plus the known multi-class wording fixes."""
    replacement = before
    applied: list[list[str]] = []
    for old_ctx, new_ctx in [*pairs, *_G09_VARIANTS]:
        if old_ctx and old_ctx in replacement and new_ctx not in replacement:
            candidate = replacement.replace(old_ctx, new_ctx, 1)
            if _compact(candidate) == _compact(replacement):
                continue
            replacement = candidate
            applied.append([old_ctx, new_ctx])
    if not applied:
        return None
    # A partial splice is not a G09 result.  In particular, a contract may use
    # an unlisted fee phrase such as ``扣除其他相应的费用``; changing only the
    # NAV noun would otherwise produce a plausible-looking but incomplete edit
    # and the replay proof would certify the same partial effect.
    compact = _compact(replacement)
    if ("扣除或加上相应的费用" not in compact
            or "当日该类基金份额的基金份额净值" not in compact):
        return None
    return TemplateResult(replacement=replacement, content_source="tier1_splice",
                          evidence={"mode": "g09_bounded_splice", "applied": applied,
                                    # The guide reference has known contract variants;
                                    # this is the deterministic, bounded output that
                                    # the operation actually authorized.
                                    "fixed_text": replacement})


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
