"""T3 primary-model target locator (plan §11).

T1 exact and T2 deterministic semantic binding stay the default.  Only when both
fail does the primary model see a bounded candidate window and propose a location and
literal quote.  The model never supplies offsets: code re-resolves the quote against
the real document and re-checks the containing segment.
"""
from __future__ import annotations

import json
import os
import re
from typing import TYPE_CHECKING, Any, Iterable, Mapping, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids an import cycle at runtime
    from .semantic_evidence import ApprovalBook

#: Historical hard cap on one locator candidate page.  Callers may raise it, but the
#: default stays small so a bounded model prompt cannot silently grow.
DEFAULT_CANDIDATE_LIMIT = 12


class CandidatePage(list):
    """A list of candidate locations that also reports paging state.

    ``list`` is subclassed on purpose: ``_open_rule_candidates`` and
    ``_open_operation_candidates`` historically returned ``list[str]`` and several
    callers/tests still slice, index and compare them.  The extra attributes describe
    the *whole* candidate set before the requested page was cut, so a caller can raise
    ``limit`` or continue with ``next_cursor`` without guessing whether work remains.
    """

    def __init__(self, locations: Sequence[str] = (), *, cursor: int = 0,
                 total: int = 0, has_more: bool = False) -> None:
        super().__init__(locations)
        self.cursor = int(cursor)
        self.total = int(total)
        self.has_more = bool(has_more)

    @property
    def remaining(self) -> int:
        """Candidates after this page, measured against the full candidate set."""
        return max(0, self.total - self.cursor - len(self))

    @property
    def next_cursor(self) -> int | None:
        return self.cursor + len(self) if self.has_more else None


def _candidate_page(locations: Sequence[str], *, limit: int = DEFAULT_CANDIDATE_LIMIT,
                    cursor: int = 0) -> CandidatePage:
    """Cut one stable page from a fully ordered candidate list."""
    start = max(0, int(cursor or 0))
    size = max(1, int(limit or DEFAULT_CANDIDATE_LIMIT))
    total = len(locations)
    page = list(locations[start:start + size])
    return CandidatePage(page, cursor=start, total=total,
                         has_more=start + len(page) < total)

LOCATE_SCHEMA = {
    "type": "object",
    "required": ["location", "quote", "semantic_role", "reason"],
    "properties": {
        "location": {"type": "string"},
        "quote": {"type": "string"},
        "semantic_role": {"type": "string"},
        "reason": {"type": "string"},
    },
}

LOCATE_INSTRUCTION = (
    "The deterministic resolver could not bind this obligation to the contract. Read the "
    "candidate paragraphs and return the ONE paragraph location plus an exact contiguous "
    "quote from that paragraph that carries the obligation. Do not paraphrase, do not "
    "merge two paragraphs, and do not return offsets. If no paragraph carries it, return "
    "an empty quote and explain why. semantic_role states what the clause does (for "
    "example class_definition, subscription_fee, payment_mechanism)."
)

LOCATE_PROMPT_VERSION = "recall_locate_v1"


def normalise_locator_location(value: str, allowed: Iterable[str]) -> str:
    """Normalise the display-form location a locator may copy from context.

    Candidate context labels paragraphs as ``[p164] …``.  Models routinely copy
    that display form ("[p164]") into the location field even though the schema
    asks for ``p164``.  The label is normalised before the window check; a
    correct locator answer must not be rejected as
    location_outside_candidate_window (FL-D488).
    """
    location = str(value or "").strip()
    stripped = re.sub(r"^[\[\(【]\s*", "", location)
    stripped = re.sub(r"\s*[\]\)】]$", "", stripped)
    if stripped and stripped != location:
        location = stripped
    allowed = tuple(str(item) for item in allowed)
    if location not in allowed and location:
        matches = [candidate for candidate in allowed
                   if re.search(rf"(?<![A-Za-z0-9_]){re.escape(candidate)}"
                                rf"(?![A-Za-z0-9_])", location)]
        if len(matches) == 1:
            location = matches[0]
    return location


def _enabled() -> bool:
    return os.environ.get("FUNDLEX_TARGET_LOCATOR", "1").strip().lower() not in {
        "0", "false", "off", "no"}


def _candidate_context(inspection: Any, target: Any, rule: dict, facts: Any,
                       *, limit: int, radius: int = 6,
                       allowed_scope: set[str] | None = None,
                       candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
                       candidate_cursor: int = 0
                       ) -> tuple[str, set[str], dict[str, Any]]:
    from .recall import display_text, rule_context

    scope_filter = (lambda location: str(location) in allowed_scope) \
        if allowed_scope is not None else (lambda location: True)
    candidates = [str(location) for location in (getattr(target, "site_candidates", ()) or ())
                  if scope_filter(location)]
    locations: list[str] = []
    lines: list[str] = []
    coverage: dict[str, Any] = {
        "total": len(candidates), "shown": 0, "remaining": 0,
        "cursor": int(candidate_cursor or 0), "next_cursor": None,
        "has_more": False, "truncated": False,
    }
    if candidates:
        # Open-obligation recovery: code already narrowed the region to anchored
        # paragraphs; the model may not look anywhere else.  FL-D441: a page is
        # explicit and resumable.  The historical code silently dropped candidates
        # after the limit, so a legal 13th site could never be located.
        page = _candidate_page(candidates, limit=candidate_limit,
                               cursor=candidate_cursor)
        coverage.update({
            "cursor": int(page.cursor),
            "next_cursor": page.next_cursor,
            "has_more": bool(page.has_more),
            "remaining": page.remaining,
        })
        budget = max(1000, limit - 4000)
        used = 0
        for location in page:
            try:
                span = inspection.by_location(location)
            except Exception:  # noqa: BLE001 - a vanished candidate is not fatal
                continue
            text, _ = display_text(span.text)
            if not text.strip():
                continue
            line = f"[{location}] {text}"
            if locations and used + len(line) + 2 > budget:
                # Honest truncation: the omitted tail stays reachable through the
                # recorded cursor instead of disappearing from the prompt.
                coverage["truncated"] = True
                coverage["next_cursor"] = page.cursor + len(locations)
                coverage["remaining"] = max(
                    0, len(candidates) - (page.cursor + len(locations)))
                coverage["has_more"] = True
                break
            locations.append(location)
            lines.append(line)
            used += len(line) + 2
        coverage["shown"] = len(locations)
        if not locations:
            # Open targets must never fall back to a radius window: that would let the
            # model choose a paragraph code did not authorize.
            return "", set(), coverage
    if not candidates:
        all_locations = [span.location for span in inspection.paragraphs
                         if scope_filter(span.location)]
        try:
            index = all_locations.index(target.location)
        except ValueError:
            index = 0
        start = max(0, index - radius)
        end = min(len(all_locations), index + radius + 1)
        for location in all_locations[start:end]:
            span = inspection.by_location(location)
            text, _ = display_text(span.text)
            if text.strip():
                lines.append(f"[{location}] {text}")
                locations.append(location)
        coverage.update({"total": len(locations), "shown": len(locations),
                         "remaining": 0, "has_more": False, "truncated": False,
                         "cursor": 0, "next_cursor": None})
    coverage_line = (
        "CANDIDATE_COVERAGE total={total} shown={shown} remaining={remaining} "
        "cursor={cursor} next_cursor={next_cursor} has_more={has_more}"
    ).format(**coverage)
    context = "\n\n".join([
        "CANDIDATE_PARAGRAPHS\n" + "\n".join(lines)[:max(1000, limit - 4000)],
        coverage_line,
        "GUIDE_OPERATION\n" + rule_context([rule], full=True),
        "FACTS\n" + json.dumps(facts.as_ledger() if hasattr(facts, "as_ledger") else {},
                              ensure_ascii=False),
        "FAILED_QUOTE\n" + str(getattr(target, "quote", "") or ""),
    ])
    return context[:limit], set(locations), coverage


def _open_operation_candidates(
        inspection: Any, rule: dict, record: Any, section_ids: Sequence[str],
        section_by_id: dict[str, Any], facts: Any,
        existing_targets: Sequence[Any] = (), *,
        limit: int = DEFAULT_CANDIDATE_LIMIT,
        cursor: int = 0) -> CandidatePage:
    """Operation-specific candidate discovery, strongest evidence first.

    P1 same-rule sibling site, P2 exact operation old_text, P3 variant/reference
    fragment, P4 rule keyword bag + topic/site guard.  The returned paragraphs are the
    only places the bounded locator may choose from; no candidate means the obligation
    stays OPEN instead of searching the whole contract.
    """
    from .recall import (_RULE_TOPIC_TOKENS, _compact, _delete_keyword_bag,
                         _keyword_bag_in_clause, _looks_like_heading,
                         condition_status, reference_fragments, target_operation_keys,
                         _declared_operation_key)

    rule_id = str(rule.get("rule_id") or "")
    operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
    operation = (rule.get("operations") or [])[operation_index]
    old_text = _compact(str(operation.get("old_text") or ""))
    variants = [_compact(str(value)) for value in (rule.get("old_text_variants") or [])
                if _compact(str(value))]
    fragments: list[str] = []
    if len(old_text) >= 4:
        fragments.append(old_text)
    for variant in variants:
        if len(variant) >= 4:
            fragments.append(variant)
        fragments.extend(_compact(fragment) for fragment in reference_fragments(variant))
    topic = tuple(_RULE_TOPIC_TOKENS.get(rule_id, ()))
    bag = _delete_keyword_bag(rule, facts)
    class_rule = bool(rule.get("class_substitution"))
    append_site = (str(operation.get("op") or "") == "append"
                   and rule_id not in {"G01", "G03"})
    class_tokens = ["基金份额类别", "份额类别", "将基金份额分为", "分为A类", "分为C类",
                    "收费方式", "不同类别", "基金份额设置"]
    facts_classes = tuple(f"{item.name}类" if "类" not in item.name else item.name
                         for item in getattr(facts, "current_classes", ()) or ())

    def classify(text: str) -> int:
        """0 = no candidate, 1 = class/topic only, 2 = strong anchor."""
        if len(text) < 12:
            return 0
        if topic and not all(token in text for token in topic):
            # Class rules also accept the definition wording ``将基金份额分为``;
            # the literal ``份额类别`` need not appear in the clause that names the
            # classes (景宁 G03 p151).  The class/fact checks below still gate it.
            if not (class_rule and any(
                    token in text for token in
                    ("将基金份额分为", "基金份额类别", "份额类别"))):
                return 0
        if rule_id == "G12" and not (
                "赎回费用由" in text and "基金财产" in text):
            return 0
        if rule_id == "G11" and not ("申购费用由" in text and "承担" in text):
            return 0
        if rule_id == "G08" and not ("申购费率" in text and "招募说明书" in text):
            return 0
        if rule_id == "G13" and not (
                "少于7日" in text and "赎回费" in text and
                ("1.5%" in text or "1.50%" in text)):
            return 0
        if rule_id == "G09" and not (
                "赎回金额为按实际确认的有效赎回份额" in text
                and "基金份额净值" in text and "扣除" in text):
            # G09's guide literal names "对应份额类别"; contracts already using
            # "该类基金份额净值" do not contain that fragment but still carry the
            # clause the rule must complete ("扣除或加上").  Anchor on the policy
            # shape rather than the historical noun.
            return 0
        if append_site:
            # G16 appends into the sales-service-fee accrual/payment clause, not the
            # class-definition paragraph or a fee formula row (its class_substitution
            # is only a slot).  Payment-mechanism wording ranks above a bare accrual
            # mention.
            if "销售服务费" not in text:
                return 0
            if any(token in text for token in ("按月支付", "支付日期", "划出",
                                                "次月", "一次性")):
                return 3
            if any(token in text for token in ("计提", "支付", "按月")):
                return 2
            return 0
        if class_rule:
            has_class = any(token in text for token in class_tokens)
            has_fact_class = (not facts_classes or
                              any(_compact(name) in text for name in facts_classes))
            return 2 if has_class and has_fact_class else 0
        if fragments and any(fragment in text for fragment in fragments):
            return 2
        if bag and _keyword_bag_in_clause(text, bag, window=80):
            return 2
        return 0

    ordered: list[str] = []
    scores: dict[str, int] = {}

    def add(location: str, score: int) -> None:
        if not location or location in scores and scores[location] >= score:
            return
        scores[location] = score
        if location not in ordered:
            ordered.append(location)

    def body_at(location: str) -> str:
        try:
            return _compact(str(getattr(inspection.by_location(location), "text", "")))
        except Exception:  # noqa: BLE001 - a vanished candidate is not fatal
            return ""

    # P1: a sibling operation of the same rule already proved this clause site.
    sibling_locations: list[str] = []
    for target in existing_targets:
        if str(getattr(target, "rule_id", "")) != rule_id:
            continue
        if getattr(target, "out_of_scope", False) or getattr(target, "state", "") not in {
                "needs_edit", "satisfied"}:
            continue
        sibling_keys = set(getattr(target, "operations", ()) or ())
        if not sibling_keys:
            sibling_keys = target_operation_keys(target, rule, inspection)
        current_id = str(getattr(record.spec, "operation_id", "") or
                         _declared_operation_key(rule_id, operation_index, operation))
        if current_id in sibling_keys:
            continue
        for location in ([target.location] if not getattr(target, "composite", ())
                         else [part.rsplit(":", 2)[0] for part in target.composite]):
            if location not in sibling_locations:
                sibling_locations.append(location)
    for location in sibling_locations:
        if classify(body_at(location)) == 2:
            add(location, 3)

    # G11's bearer sentence is occasionally split exactly at the paragraph
    # boundary: the first paragraph ends with ``申购费用由……承担，`` and the next
    # begins with ``不列入基金财产。``.  The two fragments are one authorized
    # source site; requiring both anchors in one paragraph would leave both G11
    # operations OPEN (D06 p228/p229).
    if rule_id == "G11" and str(operation.get("op") or "") == "replace":
        for index, location in enumerate(getattr(inspection, "paragraphs", ())):
            text = body_at(str(getattr(location, "location", "")))
            if ("申购费用由" in text and "承担" in text
                    and text.endswith(("，", ","))):
                following = getattr(inspection, "paragraphs", ())[index + 1] \
                    if index + 1 < len(getattr(inspection, "paragraphs", ())) else None
                if following is not None and "不列入基金财产" in body_at(
                        str(getattr(following, "location", ""))):
                    add(str(getattr(location, "location", "")), 3)

    # P2/P3/P4: scan only the scope-mapped sections, strongest anchor first.
    for section_id in section_ids:
        section = section_by_id.get(section_id)
        for location in (getattr(section, "locations", ()) if section is not None else ()):
            text = body_at(location)
            if not text:
                continue
            score = classify(text)
            if score == 0:
                continue
            if class_rule and _looks_like_heading(
                    str(getattr(inspection.by_location(location), "text", ""))):
                continue
            if old_text and old_text in text:
                score = 3
            elif any(fragment and fragment in text for fragment in fragments):
                score = 2
            add(location, score)
    def sort_key(location: str) -> tuple[int, int]:
        return (-scores.get(location, 0), ordered.index(location))
    if append_site:
        strong = [location for location in ordered if scores.get(location, 0) >= 3]
        if strong:
            return _candidate_page(sorted(strong, key=sort_key), limit=limit, cursor=cursor)
    return _candidate_page(sorted(ordered, key=sort_key), limit=limit, cursor=cursor)


def _open_rule_candidates(inspection: Any, rule: dict, section_ids: Sequence[str],
                          section_by_id: dict[str, Any], facts: Any, *,
                          limit: int = DEFAULT_CANDIDATE_LIMIT,
                          cursor: int = 0) -> CandidatePage:
    """Deterministic source search for an applicable rule that has no target.

    The candidate region is code-produced from the scope-mapped sections plus the rule's
    own anchors (topic tokens, class tokens, delete keyword bag, reference fragments).
    No anchor evidence means no candidate and therefore no model call: the obligation
    stays OPEN rather than letting the model pick an arbitrary paragraph.
    """
    from .recall import (_RULE_TOPIC_TOKENS, _compact, _delete_keyword_bag,
                         _keyword_bag_in_clause, condition_status,
                         reference_fragments)

    rule_id = str(rule.get("rule_id") or "")
    topic = tuple(_RULE_TOPIC_TOKENS.get(rule_id, ()))
    fragments: list[str] = []
    class_tokens: list[str] = []
    for operation in rule.get("operations") or []:
        if condition_status(operation.get("condition"), facts) != "TRUE":
            continue
        old_text = _compact(str(operation.get("old_text") or ""))
        if len(old_text) >= 4:
            fragments.append(old_text)
        if rule.get("class_substitution"):
            class_tokens.extend(re.findall(r"[A-ZＡ-Ｚ]\s*类", str(operation.get("old_text") or "")))
    for variant in rule.get("old_text_variants") or []:
        old_text = _compact(str(variant or ""))
        if len(old_text) >= 4:
            fragments.append(old_text)
        fragments.extend(_compact(fragment) for fragment in reference_fragments(str(variant or "")))
    bag = _delete_keyword_bag(rule, facts)
    if not (topic or fragments or bag or class_tokens):
        return []
    found: list[str] = []
    for section_id in section_ids:
        section = section_by_id.get(section_id)
        for location in (getattr(section, "locations", ()) if section is not None else ()):
            try:
                span = inspection.by_location(location)
            except Exception:  # noqa: BLE001
                continue
            text = _compact(str(getattr(span, "text", "")))
            if len(text) < 12:
                continue
            if topic and not all(token in text for token in topic):
                continue
            if class_tokens and not any(token in text for token in class_tokens):
                continue
            if bag and not _keyword_bag_in_clause(text, bag, window=80):
                continue
            if fragments and not bag and not any(fragment in text
                                                 for fragment in fragments):
                # The rule's own wording is the strong anchor.  Delete rules whose
                # keyword bag matched are exempt (G15/G17 real paraphrases do not carry
                # the guide reference verbatim).  A broad topic token alone is never
                # enough to select every fee paragraph in the section.
                continue
            if location not in found:
                found.append(location)
    return _candidate_page(found, limit=limit, cursor=cursor)


def _open_rule_quote_ok(rule: dict, facts: Any, paragraph_text: str, quote: str,
                        span: Any = None, inspection: Any = None) -> tuple[bool, str]:
    """Fast-path verification of the locator's quote for an open obligation.

    The quote itself must carry the rule's own wording (class token / delete keyword bag
    / reference fragment), not just appear somewhere in an anchored paragraph.  A bare
    topic token such as ``销售服务费`` is not a locatable edit site.

    This is deliberately *not* the only final semantic judge (R03): when the target
    carries a code-verified approval, :func:`locate_unresolved_targets` may accept an
    exact quote inside the authorized candidate window even though this word-bag check
    misses.  Without an approval the historical gate still applies unchanged.
    """
    from .recall import (_RULE_TOPIC_TOKENS, _compact, _delete_keyword_bag,
                         _keyword_bag_in_clause, condition_status, target_site_ok)

    text = _compact(paragraph_text)
    compact_quote = _compact(quote)
    if len(compact_quote) < 6:
        return False, "quote_too_short"
    if span is not None and inspection is not None:
        if not target_site_ok(str(rule.get("rule_id") or ""), span, inspection):
            return False, "target_site_mismatch"
    topic = tuple(_RULE_TOPIC_TOKENS.get(str(rule.get("rule_id") or ""), ()))
    if topic and not all(token in text for token in topic):
        return False, "topic_missing"
    operations = [operation for operation in rule.get("operations") or []
                  if condition_status(operation.get("condition"), facts) == "TRUE"]
    fragments = [_compact(str(operation.get("old_text") or ""))
                 for operation in operations
                 if len(_compact(str(operation.get("old_text") or ""))) >= 4]
    class_tokens = [token
                    for operation in operations
                    for token in re.findall(r"[A-ZＡ-Ｚ]\s*类",
                                            str(operation.get("old_text") or ""))]
    if rule.get("class_substitution"):
        if class_tokens and not any(token in compact_quote for token in class_tokens):
            return False, "quote_class_missing"
        if not class_tokens:
            # Append-style class guidance (G01/G03): the edit site is the class-
            # definition clause, NOT the new policy wording.  "直销/不收取/销售服务费"
            # are expected artifact effects and must not be required in the source
            # quote (plan §8).  Require a real class-definition/setup site instead.
            if str(rule.get("rule_id")) == "G16":
                if not ("销售服务费" in compact_quote and
                        any(token in compact_quote for token in ("计提", "支付", "按月"))):
                    return False, "quote_sales_service_site_missing"
            else:
                class_site_tokens = ("基金份额类别", "份额类别", "将基金份额分为",
                                     "分为A类", "分为C类", "收费方式", "不同类别",
                                     "基金份额设置")
                if not any(token in compact_quote or token in text
                           for token in class_site_tokens):
                    return False, "quote_class_site_missing"
                fact_classes = tuple(
                    f"{item.name}类" if "类" not in item.name else item.name
                    for item in getattr(facts, "current_classes", ()) or ())
                if fact_classes and not any(_compact(name) in text for name in fact_classes):
                    return False, "class_structure_missing"
            if not compact_quote:
                return False, "quote_too_short"
        if rule.get("rule_id") in {"G02", "G04"}:
            if not any(token in compact_quote for token in
                       ("基金份额类别", "份额类别", "将基金份额分为", "分类")):
                return False, "quote_site_missing"
    bag = _delete_keyword_bag(rule, facts)
    if bag and not _keyword_bag_in_clause(compact_quote, bag, window=80):
        return False, "quote_keyword_bag_missing"
    if not rule.get("class_substitution") and not bag and fragments:
        if not any(fragment in compact_quote for fragment in fragments):
            # No generic topic fallback: "调低...费率" also matches the management-fee
            # clause next to G05's redemption-fee clause.
            return False, "quote_anchor_missing"
    return True, ""


def _approval_allows_locator(target: Any, inspection: Any, approvals: Any,
                             location: str) -> tuple[bool, str]:
    """Whether a valid approval authorizes this exact candidate location.

    This is the second, semantic acceptance path for R03.  The quote itself has
    already been re-resolved against the real paragraph and the location has already
    passed the code-generated candidate window; an approval may therefore replace the
    locator's own word-bag/category fast path.  It never widens the window: an
    approval is accepted only for a location the target itself lists as a candidate.
    """
    if approvals is None:
        return False, "APPROVAL_MISSING"
    if not str(getattr(target, "approval_id", "") or ""):
        return False, "APPROVAL_MISSING"
    candidates = tuple(str(item) for item in
                       (getattr(target, "site_candidates", ()) or ()))
    if candidates and str(location) not in candidates:
        return False, "APPROVAL_LOCATION_OUTSIDE_CANDIDATES"
    try:
        check = approvals.allows(target, inspection)
    except Exception as exc:  # noqa: BLE001 - a broken approval never authorizes an edit
        return False, f"APPROVAL_CHECK_ERROR:{type(exc).__name__}"
    return (True, "") if check.ok else (False, str(check.code or "APPROVAL_REJECTED"))


def locate_unresolved_targets(targets: Sequence[Any], inspection: Any,
                              rules_by_id: dict[str, dict], facts: Any, gateway: Any,
                              *, scopes: Mapping[str, Any] | None = None,
                              approvals: "ApprovalBook | None" = None,
                              candidate_limit: int = DEFAULT_CANDIDATE_LIMIT
                              ) -> list[dict[str, Any]]:
    """Try the model locator for every still-unresolved target; record every attempt."""
    if not _enabled():
        return []
    from .docx import DocxError
    from .recall import containing_segment, resolve_quote

    records: list[dict[str, Any]] = []
    for target in targets:
        if target.state != "needs_edit" or target.resolution in {"resolved", "composite"}:
            continue
        if getattr(target, "out_of_scope", False):
            continue
        rule = rules_by_id.get(target.rule_id)
        if rule is None:
            continue
        scope = scopes.get(target.rule_id) if scopes is not None else None
        allowed_scope = ({str(location) for location in getattr(scope, "locations", ())}
                         if scope is not None else (set() if scopes is not None else None))
        if scopes is not None and not allowed_scope:
            continue
        cursor = int(getattr(target, "_candidate_cursor", 0) or 0)
        context, allowed_locations, candidate_coverage = _candidate_context(
            inspection, target, rule, facts, limit=gateway.max_context_chars,
            allowed_scope=allowed_scope, candidate_limit=candidate_limit,
            candidate_cursor=cursor)
        record = {"target_id": target.target_id, "rule_id": target.rule_id,
                  "candidate_coverage": candidate_coverage}

        def reject(reason: str) -> None:
            record["status"] = "rejected"
            record["reject_reason"] = reason
            if (candidate_coverage.get("has_more")
                    and candidate_coverage.get("next_cursor") is not None):
                # The locator only saw this explicit page.  Persist the next page so a
                # later recovery round continues instead of re-reading page 1 forever.
                target._candidate_cursor = int(candidate_coverage["next_cursor"])
                record["resume_cursor"] = int(candidate_coverage["next_cursor"])
            records.append(record)
        try:
            result = gateway.call(task_type="recall_locate", bounded_context=context,
                                  response_schema=LOCATE_SCHEMA,
                                  instruction=LOCATE_INSTRUCTION,
                                  prompt_version=LOCATE_PROMPT_VERSION)
        except Exception as exc:  # noqa: BLE001 - recorded; deterministic failure remains
            from .model import ModelError
            if isinstance(exc, ModelError):
                from .recovery import FailureClass, classify
                if classify(exc.code) in {FailureClass.INFRASTRUCTURE,
                                          FailureClass.RESOURCE}:
                    raise
            record.update(status="error", reason=f"{type(exc).__name__}:"
                          f"{getattr(exc, 'code', '')}")
            records.append(record)
            continue
        value = result.value if isinstance(result.value, dict) else {}
        location = str(value.get("location") or "").strip()
        quote = str(value.get("quote") or "").strip()
        location = normalise_locator_location(location, allowed_locations)
        record.update(location=location, quote=quote,
                      semantic_role=str(value.get("semantic_role") or ""),
                      reason=str(value.get("reason") or ""))
        if not location or not quote:
            reject("empty_location_or_quote")
            continue
        if location not in allowed_locations:
            reject("location_outside_candidate_window")
            continue
        try:
            span = inspection.by_location(location)
        except DocxError:
            reject("location_not_found")
            continue
        located = resolve_quote(span, quote)
        if located is None:
            reject("quote_not_found")
            continue
        start, end = located
        if not containing_segment(span, start, end) and start != end:
            reject("segment_invalid")
            continue
        open_rule = bool(getattr(target, "site_candidates", ()))
        if open_rule:
            from .recall import _compact
            if _compact(span.text).count(_compact(quote)) != 1:
                reject("ambiguous_occurrence")
                continue
            anchor_ok, anchor_reason = _open_rule_quote_ok(
                rule, facts, span.text, quote, span=span, inspection=inspection)
            if not anchor_ok:
                # R03: the word-bag/category check is a candidate fast path, not the
                # only semantic judge.  A valid, code-verified approval for this
                # target/operation may accept an exact quote that really exists in an
                # authorized candidate paragraph.  The window, quote existence,
                # uniqueness and approval state/hash checks above still fail closed.
                approved, approval_reason = (False, "APPROVAL_MISSING")
                if anchor_reason != "quote_too_short":
                    approved, approval_reason = _approval_allows_locator(
                        target, inspection, approvals, location)
                if not approved:
                    if approvals is not None and getattr(target, "approval_id", ""):
                        record["approval_check"] = approval_reason
                    reject(f"anchor_mismatch:{anchor_reason}")
                    continue
                record["anchor_bypassed"] = f"anchor_mismatch:{anchor_reason}"
                record["approval_id"] = str(getattr(target, "approval_id", "") or "")
        target.location = location
        target.start, target.end = start, end
        target.quote = quote
        target.resolution = "resolved"
        target.segment_ok = containing_segment(span, start, end) is not None
        target.reason = f"{target.reason}|locator:{str(value.get('semantic_role') or '')}".strip("|")
        record["status"] = "bound"
        duplicates = 0
        if open_rule and isinstance(targets, list):
            # Identical clause copies (body and contract summary) must be edited too;
            # otherwise the same obligation is only half carried out.
            from .recall import Target
            for other_location in getattr(target, "site_candidates", ()):
                if other_location == location or duplicates >= 4:
                    continue
                try:
                    other_span = inspection.by_location(other_location)
                except DocxError:
                    continue
                if _compact(other_span.text) != _compact(span.text):
                    # Only a byte-identical clause copy (body vs contract summary) may be
                    # cloned; a paragraph that merely contains the same short phrase is
                    # not the same obligation site.
                    continue
                other_offsets = resolve_quote(other_span, quote)
                if other_offsets is None:
                    continue
                if _compact(other_span.text).count(_compact(quote)) != 1:
                    continue
                other_start, other_end = other_offsets
                clone = Target(
                    target_id=f"{target.target_id}-D{duplicates + 1}", rule_id=target.rule_id,
                    location=other_location, quote=quote, state="needs_edit",
                    reason=f"T3_open_rule_duplicate_copy|locator:{target.reason}",
                    start=other_start, end=other_end, resolution="resolved",
                    segment_ok=containing_segment(other_span, other_start, other_end) is not None,
                    operations=tuple(target.operations), site_candidates=(other_location,))
                targets.append(clone)
                duplicates += 1
        if duplicates:
            record["duplicates"] = duplicates
        records.append(record)
    return records


def target_for_claim_site(record: Any, location: str, targets: Sequence[Any],
                          rules_by_id: dict[str, dict], facts: Any, inspection: Any,
                          *, target_id: str = "",
                          allowed_locations: set[str] | None = None) -> Any | None:
    """Create the repair target for a Claim-discovered required occurrence.

    Claim Replay can prove that a duplicate body/summary site must carry the
    operation even when an active target already exists elsewhere.  That evidence
    is stronger than the old "one active target covers the operation" shortcut;
    it authorizes a site-specific repair target, not a global fuzzy clone.
    """
    from .recall import Target, resolve_quote
    from .generation.effects import operation_site_bound

    rule_id = str(getattr(record.spec, "rule_id", "") or "")
    operation_id = str(getattr(record.spec, "operation_id", "") or "")
    if not rule_id or not operation_id or not location:
        return None
    # Claim Replay propagates an exact duplicate site across the whole document.
    # A duplicate outside the rule's mapped sections is a sibling rule's business
    # site, not a repair site for this operation (纳斯达克 p169: G02's definition
    # text also appears in 基金的基本情况, which belongs to G04).
    if allowed_locations is not None and location not in allowed_locations:
        return None
    rule = rules_by_id.get(rule_id)
    if rule is None:
        return None
    active = [target for target in targets
              if operation_id in (getattr(target, "operations", ()) or ())
              and getattr(target, "state", "") == "needs_edit"
              and not getattr(target, "out_of_scope", False)]
    if any(getattr(target, "location", "") == location for target in active):
        return None
    if not active:
        return None
    source = active[0]
    try:
        span = inspection.by_location(location)
    except Exception:  # noqa: BLE001 - vanished location is not a repair site
        return None
    quote = str(getattr(source, "quote", "") or "")
    located = resolve_quote(span, quote) if quote else None
    if located is None:
        for reference in [str(getattr(record.spec, "old_text", "") or ""),
                          *tuple(getattr(record.spec, "alternatives", ()) or ())]:
            if not reference:
                continue
            candidate = resolve_quote(span, reference)
            if candidate is not None:
                quote, located = reference, candidate
                break
    if located is None:
        return None
    if not operation_site_bound(record.spec, quote, inspection, location, facts):
        return None
    start, end = located
    return Target(
        target_id=target_id or f"R{len(targets) + 1:03d}", rule_id=rule_id,
        location=location, quote=quote, state="needs_edit",
        reason=f"claim_required_site:{operation_id}", start=start, end=end,
        resolution="resolved", segment_ok=True, operations=(operation_id,))


def _scan_scope_pages(
        inspection: Any, rule: dict, record: Any, section_ids: Sequence[str],
        section_by_id: dict[str, Any], facts: Any, *, existing_targets: Sequence[Any] = (),
        scope: Any = None, limit: int = DEFAULT_CANDIDATE_LIMIT,
        pass_name: str = "") -> tuple[CandidatePage, dict[str, Any]]:
    """Consume candidate pages until a physically scoped page is found.

    FL-D441: the historical consumer took the first 12 anchors and only then
    applied the rule scope, so a legal 13th candidate stayed permanently starved.
    The scan returns the first page containing at least one in-scope location and
    records how many pages/locations were inspected, the persisted next cursor and
    whether unscanned candidates remain.
    """

    cursor = 0
    pages = 0
    scanned: list[str] = []
    scope_rejected: list[str] = []
    first_total = 0
    while True:
        page = _open_operation_candidates(
            inspection, rule, record, section_ids, section_by_id, facts,
            existing_targets=existing_targets, limit=limit, cursor=cursor)
        pages += 1
        first_total = first_total or int(page.total)
        scanned.extend(str(location) for location in page)
        if scope is None:
            accepted = list(page)
        else:
            usable = (getattr(scope, "resolution", "") != "unresolved"
                      and bool(getattr(scope, "locations", ())))
            accepted = [location for location in page
                        if usable and scope.contains(str(location))]
            scope_rejected.extend(str(location) for location in page
                                  if str(location) not in set(accepted))
        if accepted or not page.has_more:
            # CandidatePage derives ``next_cursor`` from cursor + len(page).  The
            # accepted subset can be smaller than the scanned page, so anchor the
            # cursor at the end of the scanned page instead of the accepted tail.
            base_cursor = (int(page.next_cursor) - len(accepted)) \
                if page.has_more and page.next_cursor is not None else int(page.cursor)
            result = CandidatePage(accepted, cursor=base_cursor, total=page.total,
                                   has_more=bool(page.has_more))
            coverage = {
                "pass": pass_name,
                "pages": pages,
                "scanned": len(scanned),
                "total": first_total,
                "scope_rejected": len(scope_rejected),
                "in_scope": len(accepted),
                "cursor": result.cursor,
                "next_cursor": result.next_cursor,
                "has_more": result.has_more,
                # An exhausted scan leaves no unread candidate, even when the first
                # accepted page was a subset of the ordered anchor set.
                "remaining": (max(0, first_total - len(scanned))
                              if result.has_more else 0),
                "complete": not result.has_more,
            }
            return result, coverage
        cursor = int(page.next_cursor or 0)


def _attach_candidate_coverage(target: Any, coverage: Mapping[str, Any]) -> Any:
    """Persist one candidate scan on the created target without changing its schema."""
    try:
        setattr(target, "candidate_coverage", dict(coverage))
    except Exception:  # noqa: BLE001 - a frozen/legacy target still keeps the reason
        pass
    return target


def summary_copy_targets(targets: Sequence[Any], rules_by_id: Mapping[str, dict],
                         inspection: Any, sections: Sequence[Any],
                         scopes: Mapping[str, Any] | None = None) -> list[Any]:
    """Create operation targets for real body->contract-summary clause copies.

    FL-D384/434/443 generalised this beyond byte-identical paragraphs.  A summary
    leaf is mapped to its selected body leaf through ``summary_of``/``copy_key``;
    an operation target is created only when the rule's own candidate anchors find a
    real paragraph inside that summary leaf.  A satisfied body target still maps, so
    a summary copy that lags the body is repaired; no candidate means no target, and
    a summary that merely mentions the topic is never polished or deduplicated.
    """

    from types import SimpleNamespace
    from .recall import (Target, _compact, instantiate_slots, resolve_quote)
    from .rule_scope import build_leaf_sections

    leaves = build_leaf_sections(inspection, sections)
    by_id = {leaf.id: leaf for leaf in leaves}
    summary_by_body: dict[str, list[Any]] = {}
    for leaf in leaves:
        if leaf.zone != "summary" or not leaf.summary_of:
            continue
        body = by_id.get(leaf.summary_of)
        if body is not None and body.zone == "body":
            summary_by_body.setdefault(body.id, []).append(leaf)

    def location_in_leaf(location: str, leaf: Any) -> bool:
        return str(location) in {str(item) for item in leaf.locations}

    operation_targets: list[Any] = [target for target in targets
                                    if getattr(target, "state", "") in
                                    {"needs_edit", "satisfied"}
                                    and not getattr(target, "out_of_scope", False)
                                    and not getattr(target, "attribution_error", "")
                                    and getattr(target, "operations", ())]
    active: list[Any] = [target for target in operation_targets
                         if getattr(target, "state", "") == "needs_edit"]

    facts_stub = _facts_stub()
    created: list[Any] = []
    for rule_id, rule in rules_by_id.items():
        scope = scopes.get(rule_id) if scopes is not None else None
        if scope is None:
            continue
        body_leaves = [leaf for leaf in leaves
                       if leaf.zone == "body" and leaf.id in scope.leaf_ids]
        for body_leaf in body_leaves:
            operations: set[str] = set()
            for target in operation_targets:
                if str(getattr(target, "rule_id", "")) != rule_id:
                    continue
                keys = set(getattr(target, "operations", ()) or ())
                locations = ([target.location] if not getattr(target, "composite", ())
                             else [part.rsplit(":", 2)[0] for part in target.composite])
                if keys and any(location_in_leaf(item, body_leaf)
                                for item in locations):
                    operations.update(keys)
            if not operations:
                continue
            for summary_leaf in summary_by_body.get(body_leaf.id, ()):
                if scope is not None and summary_leaf.id not in scope.leaf_ids:
                    continue
                if not summary_leaf.locations:
                    continue
                section = SimpleNamespace(id=summary_leaf.id, zone="summary",
                                          title=summary_leaf.title,
                                          locations=tuple(summary_leaf.locations))
                section_by_id = {summary_leaf.id: section}
                for operation_key in sorted(operations):
                    try:
                        index = int(str(operation_key).split(":", 1)[1])
                    except (IndexError, ValueError):
                        continue
                    operation_list = rule.get("operations") or []
                    if not 0 <= index < len(operation_list):
                        continue
                    operation = operation_list[index]
                    if any(location_in_leaf(target.location, summary_leaf)
                           and operation_key in (getattr(target, "operations", ()) or ())
                           for target in operation_targets):
                        continue
                    record = SimpleNamespace(spec=SimpleNamespace(
                        rule_id=rule_id, operation_index=index,
                        operation_id=operation_key,
                        old_text=str(operation.get("old_text") or ""),
                        alternatives=()))
                    page = _open_operation_candidates(
                        inspection, rule, record, [summary_leaf.id],
                        section_by_id, facts_stub, existing_targets=targets)
                    candidates = [str(location) for location in page
                                  if location_in_leaf(location, summary_leaf)]
                    if not candidates:
                        continue
                    location = candidates[0]
                    span = inspection.by_location(location)
                    text = str(span.text)
                    compact_text = _compact(text)
                    required_new = ""
                    for sibling in rule.get("operations") or ():
                        if str(sibling.get("op") or "") not in {"append", "replace"}:
                            continue
                        instantiated, issues = instantiate_slots(
                            str(sibling.get("new_text") or ""), facts_stub)
                        raw = _compact(str(sibling.get("new_text") or ""))
                        for required in (_compact(instantiated if not issues else ""), raw):
                            if not required:
                                continue
                            if required in compact_text or (
                                    len(required) >= 20
                                    and required[:20] in compact_text):
                                required_new = required
                                break
                        if required_new:
                            break
                    op_kind = str(operation.get("op") or "")
                    old_text = str(operation.get("old_text") or "")
                    old_present = bool(_compact(old_text)) and _compact(old_text) in compact_text
                    if op_kind in {"append", "replace"} and required_new:
                        continue
                    if op_kind == "delete" and required_new and not old_present:
                        # The same physical paragraph already carries the authorized
                        # replacement mechanism; the old payment clause is gone.
                        continue
                    if op_kind == "replace":
                        located = resolve_quote(span, old_text) if old_text else None
                        if located is None:
                            created.append(Target(
                                target_id=f"SC{len(created) + 1:03d}",
                                rule_id=rule_id, location=location, quote="",
                                state="needs_edit",
                                reason=f"summary_copy:{body_leaf.id}:{operation_key}",
                                resolution="unresolved",
                                operations=(operation_key,),
                                site_candidates=(location,)))
                            continue
                        start, end = located
                        quote = text[start:end]
                    else:
                        start, end = 0, len(text)
                        quote = text
                    created.append(Target(
                        target_id=f"SC{len(created) + 1:03d}", rule_id=rule_id,
                        location=location, quote=quote, state="needs_edit",
                        reason=f"summary_copy:{body_leaf.id}:{operation_key}",
                        start=start, end=end, resolution="resolved",
                        segment_ok=True, operations=(operation_key,)))
    return created


def _facts_stub() -> Any:
    """Facts are irrelevant for the structural candidate anchors used here."""
    from .recall import Facts
    return Facts("", "", "", (), False, "", "", "", {}, ())



def target_for_missing_operation(
        record: Any, targets: Sequence[Any], rules_by_id: dict[str, dict], facts: Any,
        inspection: Any, mapping: dict[str, list[str]], sections: Sequence[Any],
        *, target_id: str = "", scopes: Mapping[str, Any] | None = None,
        coverage: dict[str, Any] | None = None) -> Any | None:
    """Recovery target for one applicable operation Claim Replay proved missing.

    Candidate discovery is the same operation-first ladder as open-obligation recovery
    (sibling site -> operation old_text -> variants -> keyword bag).  No code-proven
    candidate means no model location guess; the operation stays unresolved.
    """
    if not _enabled():
        return None
    from .recall import Target, _declared_operation_key, g11_composite_source_parts

    rule_id = str(getattr(record.spec, "rule_id", "") or "")
    operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
    rule = rules_by_id.get(rule_id)
    if rule is None:
        return None
    operations = rule.get("operations") or []
    operation = operations[operation_index] if 0 <= operation_index < len(operations) else {}
    operation_id = str(getattr(record.spec, "operation_id", "") or
                       _declared_operation_key(rule_id, operation_index, operation))
    for target in targets:
        keys = set(getattr(target, "operations", ()) or ())
        if operation_id in keys and getattr(target, "state", "") == "needs_edit" \
                and not getattr(target, "out_of_scope", False):
            return None
    # FL-D656 mechanism D (recovery conservatism): a satisfied target for this
    # operation already proves the business site.  Manufacturing a second
    # needs_edit twin for the same operation creates an unplannable blocker
    # that poisons the Ledger (B19 G04 R036/R037: T005/T006 satisfied at p160,
    # recovery still injected R036/R037 and flipped both obligations open).
    # Fail-closed is preserved: only an explicit satisfied/already_satisfied
    # state suppresses recovery, and the obligation's own open rows stay.
    for target in targets:
        keys = set(getattr(target, "operations", ()) or ())
        if operation_id in keys \
                and getattr(target, "state", "") in {"satisfied", "already_satisfied"} \
                and not getattr(target, "out_of_scope", False):
            return None
    section_ids = mapping.get(rule_id) or []
    section_by_id = {section.id: section for section in sections}
    scope = scopes.get(rule_id) if scopes is not None else None
    if scopes is not None and (scope is None
                               or getattr(scope, "resolution", "") == "unresolved"
                               or not getattr(scope, "locations", ())):
        return None
    candidates, scan = _scan_scope_pages(
        inspection, rule, record, section_ids, section_by_id, facts,
        existing_targets=targets, scope=scope,
        pass_name=f"missing_operation:{operation_id}")
    if coverage is not None:
        coverage[operation_id] = scan
    if not candidates:
        return None
    if rule_id == "G11" and str(operation.get("op") or "") == "replace":
        parts = g11_composite_source_parts(inspection, operation, candidates[0])
        if parts:
            found = Target(
                target_id=target_id or f"R{operation_index + 1:03d}",
                rule_id=rule_id, location=candidates[0], quote="",
                state="needs_edit", reason=f"recovery_missing_operation:{operation_id}",
                resolution="composite", composite=parts, operations=(operation_id,))
            _attach_candidate_coverage(found, scan)
            return found
    if rule.get("class_substitution") and operation.get("op") == "replace":
        from .recall import Target as _Target, instantiate_slots, resolve_quote
        expected, issues = instantiate_slots(str(operation.get("new_text") or ""), facts)
        old_text = str(operation.get("old_text") or "")
        if not issues and expected:
            for location in candidates:
                try:
                    span = inspection.by_location(location)
                except Exception:  # noqa: BLE001
                    continue
                for needle, state in ((expected, "satisfied"), (old_text, "needs_edit")):
                    if not needle:
                        continue
                    located = resolve_quote(span, needle)
                    if located is None:
                        continue
                    found = _Target(
                        target_id=target_id or f"R{operation_index + 1:03d}",
                        rule_id=rule_id, location=location,
                        quote=span.text[located[0]:located[1]], state=state,
                        reason=f"class_operation_binding:{operation_id}:{state}",
                        start=located[0], end=located[1], resolution="resolved",
                        segment_ok=True, operations=(operation_id,))
                    _attach_candidate_coverage(found, scan)
                    return found
    found = Target(target_id=target_id or f"R{operation_index + 1:03d}",
                   rule_id=rule_id, location=candidates[0], quote="",
                   state="needs_edit",
                   reason=f"recovery_missing_operation:{operation_id}:"
                          f"candidates={len(candidates)}:"
                          f"pages={scan['pages']}:has_more={int(scan['has_more'])}",
                   resolution="unresolved", operations=(operation_id,),
                   site_candidates=tuple(candidates))
    _attach_candidate_coverage(found, scan)
    return found


def targets_for_open_rules(obligations: Any, targets: Sequence[Any], rules_by_id: dict[str, dict],
                           facts: Any, inspection: Any, mapping: dict[str, list[str]],
                           sections: Sequence[Any], *, limit: int = 12,
                           scopes: Mapping[str, Any] | None = None,
                           coverage: dict[str, Any] | None = None) -> list[Any]:
    """Create T3 locate candidates for applicable OPERATIONS with no target.

    Coverage is operation-first: ``G05:0`` having a target does not cover ``G05:2``.
    The function keeps its historical name for callers, but no rule-level
    ``seen_rules``/``covered_rules`` shortcut remains.
    """
    from .recall import (Target, _compact, _append_obligation_present,
                         class_substitution_noop, instantiate_slots,
                         satisfied_operation_keys, target_operation_keys,
                         _declared_operation_key, condition_status)

    if not _enabled():
        return []
    mode = os.environ.get("FUNDLEX_TARGET_LOCATOR_OPEN_RULES", "auto").strip().lower()
    if mode in {"0", "false", "off", "no"}:
        return []
    auto = mode in {"", "auto", "default"}
    section_by_id = {section.id: section for section in sections}
    body = _compact("\n".join(str(getattr(span, "text", ""))
                              for span in getattr(inspection, "paragraphs", ())))
    covered_operations: set[str] = set()

    def target_body(target: Any) -> str:
        locations = ([target.location] if not getattr(target, "composite", ())
                     else [part.rsplit(":", 2)[0] for part in target.composite])
        chunks: list[str] = []
        for location in locations:
            try:
                chunks.append(_compact(str(getattr(inspection.by_location(location), "text", ""))))
            except Exception:  # noqa: BLE001
                continue
        return "".join(chunks)

    for target in targets:
        rule_id = str(target.rule_id)
        rule = rules_by_id.get(rule_id) or {}
        keys = set(getattr(target, "operations", ()) or ())
        if not keys:
            keys = target_operation_keys(target, rule, inspection)
        if target.state == "needs_edit" and not target.out_of_scope:
            covered_operations.update(keys)
        elif target.state == "satisfied":
            operations = list(rule.get("operations") or ())
            statuses = [condition_status(operation.get("condition"), facts)
                        for operation in operations]
            applicable = [operation for operation, status in zip(operations, statuses)
                          if status == "TRUE"]
            # A satisfied applicable noop is a valid obligation proof, while its
            # target is excluded from audit so a sibling (G22) may edit the same
            # paragraph.  Preserve operation coverage here without making that target
            # an editable/auditable site (G21/G22).
            if target.out_of_scope and not (
                    applicable and all(operation.get("op") == "noop"
                                       for operation in applicable)):
                continue
            if keys:
                covered_operations.update(keys)
            else:
                covered_operations.update(
                    satisfied_operation_keys(rule, facts, target_body(target)))
        elif target.state == "absent" and not target.out_of_scope:
            # An "absent" verdict belongs only to the operation explicitly attributed
            # to that target.  In particular, an absent G05:0 replace source does not
            # prove the replacement exists, and must not also close G05:2 merely because
            # that sibling's literal is absent from the same paragraph (D19 p130).
            # Site-bound negative proofs for a delete are added later by
            # resolve_absent_site_targets(); until then, an un-attributed absent target
            # cannot close any operation.
            for operation_key in keys:
                try:
                    index = int(str(operation_key).split(":", 1)[1])
                except (IndexError, ValueError):
                    continue
                operations = rule.get("operations") or []
                if not 0 <= index < len(operations):
                    continue
                operation = operations[index]
                old_text = _compact(str(operation.get("old_text") or ""))
                new_text = str(operation.get("new_text") or "")
                if operation.get("op") == "replace":
                    instantiated, issues = instantiate_slots(new_text, facts)
                    required = _compact(instantiated if not issues else new_text)
                    if required and required in body and (not old_text or old_text not in body):
                        covered_operations.add(str(operation_key))
                elif (operation.get("op") == "delete"
                      and str(rule_id) != "G05"
                      and old_text and old_text not in body):
                    # G05's independent filing deletion requires the class-setup site
                    # proof below; other rules retain the legacy absent-delete path.
                    covered_operations.add(str(operation_key))

    def operation_closed(rule: dict, record: Any) -> bool:
        operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
        operation = (rule.get("operations") or [])[operation_index]
        old_text = _compact(str(operation.get("old_text") or ""))
        new_text = str(operation.get("new_text") or "")
        if operation.get("op") == "append":
            instantiated, issues = instantiate_slots(new_text, facts)
            required = new_text if issues else instantiated
            return bool(required) and _append_obligation_present(
                str(rule.get("rule_id") or ""), required, body)
        if operation.get("op") == "delete":
            if str(rule.get("rule_id") or "") == "G05":
                # G05:2 is an independent filing deletion.  Document-wide absence is
                # insufficient because the same phrase may occur in an unrelated
                # amendment clause; require the class-setup operation site to prove
                # the negative (resolve_absent_site_targets).
                return False
            return bool(old_text) and old_text not in body
        if operation.get("op") == "replace":
            instantiated, issues = instantiate_slots(new_text, facts)
            required = _compact(instantiated if not issues else new_text)
            # New policy present and old wording gone: already satisfied.  An absent
            # source old wording with the new effect present is also already satisfied
            # (the inventory/survey may discover it after the applicable branch ran).
            return bool(required) and required in body and (
                not old_text or old_text not in body or
                _compact(new_text).find(old_text) >= 0)
        return False

    created: list[Any] = []
    seen_operations: set[str] = set()
    for record in getattr(obligations, "records", ()):
        rule_id = str(getattr(record.spec, "rule_id", "") or "")
        rule = rules_by_id.get(rule_id) or {}
        operation_index = int(getattr(record.spec, "operation_index", 0) or 0)
        operations = rule.get("operations") or []
        operation = (operations[operation_index]
                      if 0 <= operation_index < len(operations) else None)
        operation_id = str(getattr(record.spec, "operation_id", "") or
                           _declared_operation_key(
                               rule_id, operation_index, operation))
        if operation_id in seen_operations or operation_id in covered_operations:
            continue
        if record.applicability.status != "TRUE":
            continue
        section_ids = mapping.get(rule_id) or []
        if not section_ids:
            continue
        seen_operations.add(operation_id)
        if len(created) >= limit:
            break
        if rule is None or operation_closed(rule, record):
            continue
        if rule.get("class_substitution") and all(
                operation.get("op") == "replace"
                for operation in rule.get("operations") or []) and \
                class_substitution_noop(rule, facts):
            continue

        if auto:
            from .recall import _compact as _compact_rule
            operation = (rule.get("operations") or [])[operation_index]
            strong = bool(rule.get("class_substitution")) or (
                condition_status(operation.get("condition"), facts) == "TRUE"
                and len(_compact_rule(str(operation.get("old_text") or ""))) >= 4)
            if not strong:
                continue
        candidates = _open_operation_candidates(
            inspection, rule, record, section_ids, section_by_id, facts,
            existing_targets=targets)
        if not candidates:
            if auto:
                # The missed operation has no code-proven site; keep it OPEN rather
                # than letting the model search the whole contract.
                continue
            candidates = [section_by_id[section_id].locations[0]
                          for section_id in section_ids
                          if section_id in section_by_id
                          and getattr(section_by_id[section_id], "locations", ())][:1]
        if scopes is not None:
            # A T3 candidate outside the rule's physical scope belongs to another
            # clause; fail closed instead of handing the locator a sibling site.
            # FL-D441: scan later anchor pages before declaring starvation.  The old
            # code filtered only the first page and permanently skipped a legal
            # candidate that sorted onto page 2.
            scope = scopes.get(rule_id)
            candidates, scan = _scan_scope_pages(
                inspection, rule, record, section_ids, section_by_id, facts,
                existing_targets=targets, scope=scope,
                pass_name=f"open_operation:{operation_id}")
            if coverage is not None:
                coverage[operation_id] = scan
            if not candidates:
                continue
        if not candidates:
            continue
        if rule_id == "G11" and str(operation.get("op") or "") == "replace":
            from .recall import g11_composite_source_parts
            parts = g11_composite_source_parts(inspection, operation, candidates[0])
            if parts:
                created_target = Target(
                    target_id=f"T3{len(created) + 1:03d}", rule_id=rule_id,
                    location=candidates[0], quote="", state="needs_edit",
                    reason=f"T3_open_operation:{operation_id}:composite",
                    resolution="composite", composite=parts,
                    operations=(operation_id,))
                _attach_candidate_coverage(
                    created_target,
                    (coverage or {}).get(operation_id) or {})
                created.append(created_target)
                continue
        created_target = Target(
            target_id=f"T3{len(created) + 1:03d}", rule_id=rule_id,
            location=candidates[0], quote="", state="needs_edit",
            reason=f"T3_open_operation:{operation_id}:"
                   f"candidates={len(candidates)}",
            resolution="unresolved",
            operations=(operation_id,),
            site_candidates=tuple(candidates))
        _attach_candidate_coverage(created_target,
                                   (coverage or {}).get(operation_id) or {})
        created.append(created_target)
    return created
