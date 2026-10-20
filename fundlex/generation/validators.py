"""V1 / V2 shadow validators (plan v4 §11–§12, §23).

Phase 2 runs these in **shadow mode**: they observe and record, they never
block. The API is text-level and side-effect free, so the offline replay tool
(``tools/evaluation/validator_shadow.py``) can run them over existing batch
artifacts without a single model call.

Layers:

* **V1**  — policy/literal checks: protected literals kept, number provenance,
  required class/component coverage;
* **V2-A** — boundary guard: everything outside the edit span must stay
  byte-identical (``check_boundary``);
* **V2-B** — change explanation: every diff segment must have an authorization
  reason; unexplained changes that touch *protected* elements fail hard,
  other unexplained changes are routed to V3 (``SOFT``).
"""
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

#: Tokens whose unauthorized change is always a hard failure (V2-B HARD).
_FEE_ITEM = re.compile(r"(申购|赎回|认购|转换|销售服务|管理|托管)费率")
#: Fee topics. A topic may never disappear because a neighbouring fee clause was
#: matched (FL-D119: 申购 authorization applied to a 赎回 clause). Cover every
#: topic the plan requires, not only 赎回/认购.
_TOPIC_FEE = re.compile(r"(?:认购|申购|赎回|转换|销售服务)(?:费|费率|费用)?|"
                        r"(?:管理|托管)(?:费|费率|费用)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?%?")
_TERM = re.compile(r"\d+\s*个?工作日|\d+\s*个月|\d+\s*年")
_SUBJECT = re.compile(r"基金管理人|基金托管人|注册登记机构|登记机构|销售机构|"
                      r"基金份额持有人|投资人")
_CLASS = re.compile(r"[A-ZＡ-Ｚ]\s*类(?:基金份额)?")

_PROTECTED_PATTERNS = (_FEE_ITEM, _TOPIC_FEE, _NUMBER, _TERM, _SUBJECT, _CLASS)

#: Finding codes that always reject an edit (plan §15.2). Kept here so every caller
#: (compose verification, claim replay, plan gate) agrees on the hard set.
HARD_CODES = frozenset({
    "MISSING_REQUIRED_TERM",
    "OUTSIDE_SPAN_CHANGED",
    "UNAUTHORIZED_NUMBER",
    "LOST_PROTECTED_LITERAL",
    "UNEXPLAINED_HARD",
    "TARGET_SOURCE_MISMATCH",
    "STRUCTURE_UNSAFE",
    "COMPONENT_MISSING",
    "COMPONENT_OUTSIDE_SITE",
    "TOPIC_LOST",
})

_FAILURE_CLASSES = {
    "MISSING_REQUIRED_TERM": "GENERATION",
    "OUTSIDE_SPAN_CHANGED": "GENERATION",
    "UNAUTHORIZED_NUMBER": "GENERATION",
    "LOST_PROTECTED_LITERAL": "GENERATION",
    "UNEXPLAINED_HARD": "GENERATION",
    "TARGET_SOURCE_MISMATCH": "TARGET",
    "STRUCTURE_UNSAFE": "GENERATION",
    "COMPONENT_MISSING": "GENERATION",
    "COMPONENT_OUTSIDE_SITE": "GENERATION",
    "TOPIC_LOST": "GENERATION",
}


@dataclass(frozen=True)
class Authorization:
    """What one operation is allowed to do, expressed as text-level reasons."""

    must_add: tuple[str, ...] = ()
    remove_patterns: tuple[str, ...] = ()
    rewrite_pairs: tuple[tuple[str, str], ...] = ()
    equivalences: tuple[tuple[str, str], ...] = ()
    #: A delete-type edit authorizes removing the whole span (plan §7.3).
    allow_whole_span_delete: bool = False
    #: The edit carries a delete-only rule: removed content is authorized by it.
    removals_authorized: bool = False


@dataclass(frozen=True)
class Finding:
    code: str
    detail: str
    severity: str = "hard"
    failure_class: str = ""

    def __post_init__(self) -> None:
        if not self.failure_class:
            object.__setattr__(self, "failure_class",
                               _FAILURE_CLASSES.get(self.code, "VERIFICATION"))

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "detail": self.detail,
                "severity": self.severity, "failure_class": self.failure_class}


@dataclass(frozen=True)
class ChangeRecord:
    kind: str  # insert | delete | replace
    before: str
    after: str
    explanation: str  # EXPLAINED | UNEXPLAINED_SOFT | UNEXPLAINED_HARD
    reason: str


@dataclass(frozen=True)
class ValidationReport:
    findings: tuple[Finding, ...]
    changes: tuple[ChangeRecord, ...]

    @property
    def verdict(self) -> str:
        if any(record.explanation == "UNEXPLAINED_HARD" for record in self.changes):
            return "FAIL"
        if any(finding.code in HARD_CODES for finding in self.findings):
            return "FAIL"
        return "PASS"

    def as_dict(self) -> dict[str, object]:
        return {
            "verdict": self.verdict,
            "findings": [finding.as_dict() for finding in self.findings],
            "changes": [{"kind": record.kind, "before": record.before,
                         "after": record.after, "explanation": record.explanation,
                         "reason": record.reason} for record in self.changes],
        }

    @property
    def soft_changes(self) -> tuple[ChangeRecord, ...]:
        return tuple(record for record in self.changes
                     if record.explanation == "UNEXPLAINED_SOFT")


def _ordinal_number(text: str, match: "re.Match[str]") -> bool:
    """A bare integer used as a list/clause ordinal is not a financial number."""
    token = match.group(0)
    if "%" in token:
        return False
    rest = text[match.end():]
    index = 0
    while index < len(rest) and rest[index] in " \u3000":
        index += 1
    if index >= len(rest):
        return False
    following = rest[index]
    return following in {"、", "．", "）", ")"} or (
        following == "." and not rest[index + 1:index + 2].isdigit())


def protected_tokens(text: str) -> list[str]:
    """Literals that must survive an edit unless explicitly authorized."""
    found: list[str] = []
    for pattern in _PROTECTED_PATTERNS:
        for match in pattern.finditer(text or ""):
            if pattern is _NUMBER and _ordinal_number(text or "", match):
                continue
            token = re.sub(r"\s+", "", match.group(0))
            if token not in found:
                found.append(token)
    return found


def _compact(value: str) -> str:
    return re.sub(r"[\s\u3000\u00a0\u200b]+", "", value or "")


def _explained_by_add(segment: str, auth: Authorization) -> bool:
    seg = _compact(segment)
    return any(addition and (addition in seg or seg in addition)
               for addition in map(_compact, auth.must_add))


def _explained_by_removal(segment: str, auth: Authorization) -> bool:
    seg = _compact(segment)
    for pattern in map(_compact, auth.remove_patterns):
        if not pattern:
            continue
        if seg in pattern or pattern in seg:
            return True
        if SequenceMatcher(None, seg, pattern).ratio() >= 0.8:
            return True
    return False


def _explained_by_rewrite(before_segment: str, after_segment: str,
                          auth: Authorization) -> bool:
    before_seg, after_seg = _compact(before_segment), _compact(after_segment)
    for left, right in (*auth.rewrite_pairs, *auth.equivalences):
        left, right = _compact(left), _compact(right)
        if not left:
            continue
        if (left in before_seg and right in after_seg) or \
           (right in before_seg and left in after_seg):
            return True
    return False


def check_boundary(before_full: str, after_full: str,
                   before_span: str, after_span: str) -> Finding | None:
    """V2-A: outside the edited span, the source text must be unchanged."""
    if before_span and before_span in before_full:
        expected = before_full.replace(before_span, after_span, 1)
        if after_full != expected:
            return Finding("OUTSIDE_SPAN_CHANGED",
                           "text outside the authorized span differs from the source")
        return None
    if before_full == after_full:
        return None
    return Finding("OUTSIDE_SPAN_CHANGED", "span not locatable in the source")


_CLASS_TOKEN = re.compile(r"([A-ZＡ-Ｚ])\s*类")


def _ordinal_token_in(token: str, text: str) -> bool:
    """A bare list number ("4、", "（4）") is not a lost financial literal."""
    if not token.isdigit() or len(token) > 3:
        return False
    return re.search(rf"(?:^|[\s\n]){re.escape(token)}\s*[、.．)）]", text or "") is not None


def _survives(token: str, after_compact: str) -> bool:
    """Does the protected token still exist in the edited text?

    Class tokens survive when the same letter is still grouped as a class
    ("A类基金份额" survives as "A类、D类基金份额"); everything else is literal.
    """
    if token in after_compact:
        return True
    match = _CLASS_TOKEN.match(token)
    if match:
        return f"{match.group(1)}类" in after_compact
    return False


def _pattern_hit(cleaned: str, auth: Authorization) -> bool:
    for pattern in map(_compact, auth.remove_patterns):
        if not pattern:
            continue
        if cleaned in pattern:
            return True
        if SequenceMatcher(None, cleaned, pattern).ratio() >= 0.8:
            return True
    return False


_TOPIC_EXPANSIONS = ("费率", "费", "费用")
_FEE_TOPIC_ROOTS = ("认购", "申购", "赎回", "转换", "销售服务", "管理", "托管")
_BARE_TOPICS = ("赎回", "认购", "申购", "转换", "销售服务")


def _fee_roots(text: str) -> set[str]:
    compact = _compact(text)
    return {root for root in _FEE_TOPIC_ROOTS
            if (root + "费") in compact or (root + "费率") in compact
            or compact == root}


def _fee_topic_flip(before: str, after: str) -> bool:
    """A single fee topic replaced by a different single fee topic is a flip.

    Removing one of several fee items (G14) is not a flip; changing the only fee topic
    (管理费 → 托管费, 申购 → 赎回) is never a paraphrase.
    """
    before_roots, after_roots = _fee_roots(before), _fee_roots(after)
    if not before_roots or not after_roots:
        return False
    lost, gained = before_roots - after_roots, after_roots - before_roots
    return len(before_roots) == 1 and len(lost) == 1 and len(gained) == 1


def _token_authorized(token: str, auth: Authorization, context: str = "") -> bool:
    """Is this protected token inside a removal the operation authorizes?

    Fee-item tokens ("赎回费率") match against the rule's reference texts. A bare
    topic token ("赎回") inherits the authorization of the fee item it belongs to
    ("赎回费率" against G14's variants) — but only through that expanded fee item,
    never by bare containment ("赎回" also occurs inside G09's 赎回金额 reference
    and must not ride on it). This keeps a topic flip on a *different* fee item
    unexplained (申购 clause matched to the 赎回 sentence, FL-D119).
    """
    cleaned = _compact(token)
    if cleaned in _BARE_TOPICS:
        if not context:
            return False
        compact_context = _compact(context)
        for suffix in _TOPIC_EXPANSIONS:
            candidate = cleaned + suffix
            if candidate in compact_context and _pattern_hit(candidate, auth):
                return True
        return False
    return _pattern_hit(cleaned, auth)


def explain_changes(before: str, after: str,
                    auth: Authorization) -> list[ChangeRecord]:
    """V2-B: classify every diff segment into the three-level disposition."""
    if auth.allow_whole_span_delete and not (after or "").strip():
        if not (before or "").strip():
            return []
        return [ChangeRecord("delete", before, "", "EXPLAINED", "delete_span_authorized")]
    records: list[ChangeRecord] = []
    matcher = SequenceMatcher(None, before or "", after or "")
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before_segment, after_segment = before[a1:a2], after[b1:b2]
        authorized_old = (not before_segment) or auth.removals_authorized \
            or _explained_by_removal(before_segment, auth) \
            or _explained_by_rewrite(before_segment, after_segment, auth)
        authorized_new = (not after_segment) or _explained_by_add(after_segment, auth)

        if tag == "insert":
            if authorized_new:
                records.append(ChangeRecord(tag, before_segment, after_segment,
                                            "EXPLAINED", "must_add"))
            else:
                records.append(ChangeRecord(tag, before_segment, after_segment,
                                            "UNEXPLAINED_SOFT", "new_text_unexplained"))
            continue

        lost = [token for token in protected_tokens(before_segment)
                if not _survives(token, _compact(after_segment))
                and not _token_authorized(token, auth, before)
                and not _ordinal_token_in(token, before)]

        if tag == "delete" or tag == "replace":
            if authorized_old and authorized_new:
                records.append(ChangeRecord(tag, before_segment, after_segment,
                                            "EXPLAINED", "authorized_replace"))
            elif lost:
                records.append(ChangeRecord(tag, before_segment, after_segment,
                                            "UNEXPLAINED_HARD",
                                            "protected:" + ",".join(sorted(lost)[:4])))
            else:
                records.append(ChangeRecord(tag, before_segment, after_segment,
                                            "UNEXPLAINED_SOFT", "unexplained_paraphrase"))
    return records


def run_validation(before: str, after: str, *, auth: Authorization,
                   required_terms: tuple[str, ...] = (),
                   before_full: str | None = None,
                   after_full: str | None = None,
                   components: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] = (),
                   authorized_numbers: tuple[str, ...] = ()) -> ValidationReport:
    """V1 + V2-B (and V2-A when full paragraphs are supplied).

    ``components`` are required policy components that must all appear **inside the
    same output span** (one semantic site); a term found elsewhere in the document
    does not prove completeness (plan §16.1).  ``authorized_numbers`` lists numbers
    whose provenance is a guide/fact source, in addition to numbers already present
    in ``before`` or in the authorized new text.
    """
    findings: list[Finding] = []

    # V1: protected literals must survive unless authorized to be removed.
    before_compact, after_compact = _compact(before), _compact(after)
    whole_span_delete = auth.allow_whole_span_delete and not after.strip()
    if not whole_span_delete and not auth.removals_authorized:
        for token in protected_tokens(before):
            if _survives(token, after_compact):
                continue
            if _token_authorized(token, auth, before):
                continue
            findings.append(Finding("LOST_PROTECTED_LITERAL", token))

    # V1: the only fee topic in the span may not be replaced by a different one,
    # unless the authorized new text itself names the replacement topic (G05's
    # 赎回费率 → 销售服务费率 is an explicit guide policy).
    if _fee_topic_flip(before, after):
        after_roots = _fee_roots(after)
        additions = {_compact(addition) for addition in auth.must_add}
        authorized = all(any((root + "费") in addition for addition in additions)
                         for root in after_roots)
        if not authorized:
            findings.append(Finding("TOPIC_LOST", "fee_topic_flip"))

    # V1: every new number must be traceable (guide text / facts / source).
    known = {t for t in protected_tokens(before) if _NUMBER.fullmatch(t)}
    known.update(_compact(token) for token in authorized_numbers if token)
    additions = {addition for addition in map(_compact, auth.must_add)}
    for match in _NUMBER.finditer(after):
        if _ordinal_number(after, match):
            continue
        token = match.group(0)
        if token in before_compact or token in known:
            continue
        if any(token in addition for addition in additions):
            continue
        findings.append(Finding("UNAUTHORIZED_NUMBER", token))

    # V1: required class/component coverage.
    for term in required_terms:
        if term and _compact(term) not in after_compact:
            findings.append(Finding("MISSING_REQUIRED_TERM", term))

    # V1: component × site coverage (plan §16.1).
    if components:
        findings.extend(check_components(after, components))

    # V2-A (only when the caller supplied whole paragraphs).
    if before_full is not None and after_full is not None:
        boundary = check_boundary(before_full, after_full, before, after)
        if boundary is not None:
            findings.append(boundary)

    # V2-B.
    changes = tuple(explain_changes(before, after, auth))
    return ValidationReport(findings=tuple(findings), changes=changes)


def check_components(site_text: str,
                     components: "Mapping[str, Any] | Sequence[Mapping[str, Any]]"
                     ) -> list[Finding]:
    """All required components must be present in the same semantic site.

    A component is ``{"id": "...", "terms": ["...", ...]}`` (``text`` or
    ``required_terms`` are accepted aliases).  Presence anywhere outside this span
    does not count: the caller passes the output of the one site being verified.
    """
    findings: list[Finding] = []
    if isinstance(components, Mapping):
        components = [components]
    compact_site = _compact(site_text)
    for component in components:
        if not isinstance(component, Mapping):
            continue
        component_id = str(component.get("id") or component.get("component_id") or "")
        raw_terms = component.get("terms") or component.get("required_terms") \
            or ([component.get("text")] if component.get("text") else [])
        terms = [str(term) for term in raw_terms if str(term).strip()]
        # Terms inside one component are alternative wordings (其他销售机构 /
        # 直销机构之外; 超过一年 / 超过1年 / 满一年), not a conjunction.
        if terms and not any(_compact(term) in compact_site for term in terms):
            findings.append(Finding(
                "COMPONENT_MISSING",
                (component_id + ":" if component_id else "") + ",".join(terms[:4]),
                failure_class="GENERATION"))
    return findings


def validate_edit(before: str, after: str, *, auth: Authorization,
                  required_terms: tuple[str, ...] = (),
                  components: "tuple[Mapping[str, Any], ...]" = (),
                  authorized_numbers: tuple[str, ...] = (),
                  before_full: str | None = None,
                  after_full: str | None = None) -> ValidationReport:
    """Single entry point used by every generation tier (deterministic or model)."""
    return run_validation(before, after, auth=auth, required_terms=required_terms,
                          before_full=before_full, after_full=after_full,
                          components=components, authorized_numbers=authorized_numbers)


def _token_context(text: str, token: str) -> str:
    """The smallest sentence-ish window around ``token`` (for removal checks)."""
    index = _compact(text).find(token)
    if index < 0:
        return token
    compact = _compact(text)
    start = max(0, index - 24)
    end = min(len(compact), index + len(token) + 24)
    return compact[start:end]
