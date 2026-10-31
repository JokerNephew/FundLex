"""Runtime variant pipeline: discover → classify → certify → authorize (FL-D655).

Mechanism B of the 该改未改 overhaul.  Guide rules declare one canonical
``old_text`` (plus historical variants), yet real contracts phrase the same
clause differently — class qualifiers inserted, factual references reordered,
equivalent conjunctions.  Previously an unmatched wording left the applicable
obligation without any plan edit (family ①/⑥, e.g. B17 G08@p292) and the
policy gate fail-closed without an authorized removal.  This module
generalises the FL-D587/588 G08 predicate into a rule-agnostic pipeline:

* **discover**: sentences in scope that share a material anchor with an
  operation's ``old_text``;
* **classify**: ``CERTIFIABLE`` (待认证 — passes the deterministic predicate),
  ``EXEMPT`` (可豁免 — already carries the operation's ``new_text`` form),
  ``ANOMALOUS`` (异常 — anchored but contradicted; honest-hold review) or
  ``IGNORE``;
* **certify**: a deterministic predicate over the operation's own
  old/new/variants shape — shared anchor ≥ 6 chars, ordered chunk coverage ≥
  50 %, bounded stretch and identical negation profile.  Nothing model-derived
  may widen certification;
* **authorize**: certified sentences join the removal authorisation of
  ``_validate_routed_policy`` and may create residual replace targets, exactly
  the FL-D587 G08 channel — now for every rule.

Fail-closed direction is preserved: an *anomalous* (anchored but uncertified)
candidate never authorises a removal; it only reappears as review evidence.
All functions are deterministic.
"""
from __future__ import annotations

import difflib
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

SCHEMA = "fundlex-variant-certification-v1"

MIN_ANCHOR_CHARS = 6
MIN_COVERAGE_RATIO = 0.5
MIN_CANDIDATE_CHARS = 12
MIN_REFERENCE_CHARS = 8
MAX_STRETCH_RATIO = 2.5
MIN_STRETCH_RATIO = 0.5
#: A certified variant may replace at most this many sites per operation —
#: bounded blast radius for a certification mistake.
MAX_VARIANTS_PER_OPERATION = 4

_SENTENCE_TAIL = re.compile(r"(?<=[。；;！？!?])")
#: Polarity must match between the guide wording and a certified variant; a
#: candidate that negates differently is *anomalous*, not a variant.  The
#: alternation is longest-first so a bare ``不`` (as in 不按/不适用) is
#: counted once and never hidden inside a longer token.
_NEGATION_RE = re.compile("不允许|暂不允许|不收取|不得|不能|不可|禁止|无需|免收|不")

#: Rules with an existing stricter rule-specific variant predicate.  The
#: generic pipeline must never weaken such a gate; it only adds rules that
#: have none.
RESIDUAL_TARGET_EXEMPT_RULES: frozenset[str] = frozenset({"G08"})


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", str(value or ""))


def _negation_profile(value: str) -> Counter:
    return Counter(_NEGATION_RE.findall(_compact(value)))


def _keygrams(value: str, n: int = 4) -> set[str]:
    if len(value) < n:
        return {value} if value else set()
    return {value[i:i + n] for i in range(len(value) - n + 1)}


def _exclusive_regions(reference: str, other: str, min_len: int = 6
                       ) -> list[str]:
    """Chunks of ``reference`` that ``other`` does not contain anywhere.

    Two sentences sharing 90 % of characters can still be semantically
    opposite (class-qualified vs canonical fee base).  Only the distinguishing
    region decides the form, so certification and exemption bind to these
    regions instead of raw coverage.
    """
    if not reference or not other:
        return []
    matcher = difflib.SequenceMatcher(None, reference, other, autojunk=False)
    regions: list[str] = []
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        segment = reference[i1:i2]
        if len(segment) >= min_len and segment not in other:
            regions.append(segment)
    return regions


def _matching(reference: str, candidate: str) -> tuple[int, float]:
    """(longest shared ordered chunk, ordered coverage ratio) of reference."""
    if not reference or not candidate:
        return 0, 0.0
    blocks = difflib.SequenceMatcher(None, reference, candidate,
                                     autojunk=False).get_matching_blocks()
    total = sum(block.size for block in blocks)
    longest = max((block.size for block in blocks), default=0)
    return longest, total / max(len(reference), 1)


def split_sentences(text: str) -> list[tuple[str, int, int]]:
    """(sentence, start, end) pieces of ``text`` split on sentence terminals."""
    pieces: list[tuple[str, int, int]] = []
    offset = 0
    body = str(text or "")
    for sentence in _SENTENCE_TAIL.split(body):
        start = body.find(sentence, offset)
        if start < 0:
            continue
        offset = start + max(len(sentence), 1)
        if sentence.strip():
            pieces.append((sentence, start, start + len(sentence)))
    return pieces


def certify_variant(operation: Mapping[str, Any], sentence: str
                    ) -> dict[str, Any] | None:
    """Deterministic proof that ``sentence`` is a wording variant of old_text."""
    reference = _compact(str(operation.get("old_text") or ""))
    candidate = _compact(sentence)
    if len(reference) < MIN_REFERENCE_CHARS or len(candidate) < MIN_CANDIDATE_CHARS:
        return None
    if reference in candidate or candidate in reference:
        return None  # the literal inventory path already owns this wording
    variants = {reference}
    variants.update(_compact(str(item)) for item in
                    (operation.get("old_text_variants") or ()) if str(item))
    if any(variant and variant in candidate for variant in variants):
        return None  # declared variant: the variant inventory path owns it
    new_text = _compact(str(operation.get("new_text") or ""))
    if new_text and new_text in candidate:
        return None  # already satisfied wording is exempt, never an old-variant
    if not (_keygrams(candidate) & _keygrams(reference)):
        return None
    # Critical-token preservation: every materially replaced or removed
    # reference segment (≥2 chars) must still appear verbatim in the
    # candidate.  Without this gate 「管理费率」certifies as a variant of
    # 「…申购费率…」 (FL-D588 over-authorization mutation): the two sentences
    # share a 22-char anchor while differing in exactly the fee item.
    # Class-qualifier insertions (B17) keep the replaced fragment (e.g.
    # 「本基金」) as a substring and stay certified.
    matcher = difflib.SequenceMatcher(None, reference, candidate,
                                      autojunk=False)
    for tag, i1, i2, _j1, _j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        segment = reference[i1:i2]
        if len(segment) >= 2 and segment not in candidate:
            return None
    # The candidate must carry at least one *distinguishing* old-form region —
    # skeleton overlap alone cannot tell an old variant from a new one.
    old_exclusive = _exclusive_regions(reference, new_text)
    if old_exclusive and not any(region in candidate for region in old_exclusive):
        return None
    anchor, coverage = _matching(reference, candidate)
    if anchor < MIN_ANCHOR_CHARS or coverage < MIN_COVERAGE_RATIO:
        return None
    ratio = len(candidate) / max(len(reference), 1)
    if not (MIN_STRETCH_RATIO <= ratio <= MAX_STRETCH_RATIO):
        return None
    if _negation_profile(candidate) != _negation_profile(reference):
        return None
    return {
        "variant": sentence,
        "proof_kind": "variant_chunk_signature",
        "anchor_chars": anchor,
        "coverage_ratio": round(coverage, 4),
        "reference": str(operation.get("old_text") or ""),
        "operation_id": str(operation.get("operation_id") or ""),
    }


#: Exemption (合同已满足) requires an essentially complete new-form sentence —
#: partial new-form overlap is a certified edit site, not a skip (fail-closed).
EXEMPT_MIN_COVERAGE_RATIO = 0.99


def classify_candidate(operation: Mapping[str, Any], sentence: str) -> dict[str, Any]:
    """Bucket one discovered sentence for an operation."""
    reference = _compact(str(operation.get("old_text") or ""))
    candidate = _compact(sentence)
    new_text = _compact(str(operation.get("new_text") or ""))
    # A ≥6-char shared anchor implies a shared 4-gram; sentences sharing none
    # can be skipped without any SequenceMatcher work (hot loop over a whole
    # contract × every dictionary of guide rules).
    ref_grams = _keygrams(reference) | _keygrams(new_text)
    if ref_grams and not (_keygrams(candidate) & ref_grams):
        return {"bucket": "IGNORE", "variant": sentence,
                "operation_id": str(operation.get("operation_id") or "")}
    # Distinguishing regions decide the form: a candidate carrying a
    # new-exclusive region and no old-exclusive one is already satisfied
    # (exempt evidence), never an old-form variant or an edit site.
    anchor_new, coverage_new = _matching(new_text, candidate)
    if new_text and (new_text in candidate or anchor_new >= MIN_ANCHOR_CHARS):
        old_exclusive = _exclusive_regions(reference, new_text)
        new_exclusive = _exclusive_regions(new_text, reference)
        has_old_exclusive = any(region in candidate for region in old_exclusive)
        has_new_exclusive = any(region in candidate for region in new_exclusive)
        # Pure-insertion old/new pairs make old-vs-new indistinguishable by
        # exclusive regions; fail-closed direction then treats the wording as
        # an edit site, so only a *structurally complete* new form exempts.
        if (new_text in candidate
                or (has_new_exclusive and not has_old_exclusive
                    and coverage_new >= EXEMPT_MIN_COVERAGE_RATIO)):
            return {"bucket": "EXEMPT", "variant": sentence,
                    "operation_id": str(operation.get("operation_id") or ""),
                    "anchor_chars": anchor_new}
    certified = certify_variant(operation, sentence)
    if certified is not None:
        return {"bucket": "CERTIFIABLE", **certified}
    anchor_old, coverage_old = _matching(reference, candidate)
    # ANOMALOUS is a *near-miss* worth human review — the same anchor and
    # ordered-coverage floors as a certification attempt that then failed on
    # stretch/negation/token preservation.  Weak-anchor sentences (a shared 6
    # char fee phrase) are ambient noise: B15 produced 221 such rows, drowning
    # the genuine candidates a reviewer must read (FL-D658 observation).
    if anchor_old >= MIN_ANCHOR_CHARS and coverage_old >= MIN_COVERAGE_RATIO:
        return {"bucket": "ANOMALOUS", "variant": sentence,
                "operation_id": str(operation.get("operation_id") or ""),
                "anchor_chars": anchor_old,
                "coverage_ratio": round(coverage_old, 4)}
    return {"bucket": "IGNORE", "variant": sentence,
            "operation_id": str(operation.get("operation_id") or "")}


def discover_candidates(operation: Mapping[str, Any], text: str
                        ) -> list[dict[str, Any]]:
    """Classify every material sentence of ``text`` against one operation."""
    candidates: list[dict[str, Any]] = []
    for sentence, start, end in split_sentences(text):
        if len(_compact(sentence)) < MIN_CANDIDATE_CHARS:
            continue
        item = classify_candidate(operation, sentence)
        if item["bucket"] == "IGNORE":
            continue
        item.update(start=start, end=end)
        candidates.append(item)
    return candidates


def authorized_variant_sentences(rule: Mapping[str, Any],
                                 operation: Mapping[str, Any],
                                 before: str) -> list[str]:
    """Certified variant sentences of ``before`` for one routed operation.

    Consumed by ``_validate_routed_policy`` as removal authorisation — the
    generalisation of the FL-D588 G08 sentence gate.
    """
    certified: list[str] = []
    for item in discover_candidates(operation, before):
        if item["bucket"] != "CERTIFIABLE":
            continue
        if item["variant"] not in certified:
            certified.append(item["variant"])
        if len(certified) >= MAX_VARIANTS_PER_OPERATION:
            break
    return certified


def _replace_operations(rule: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [operation for operation in (rule.get("operations") or [])
            if isinstance(operation, Mapping)
            and str(operation.get("op") or "replace") == "replace"
            and str(operation.get("old_text") or "").strip()]


def operation_variants_for_rule(rule: Mapping[str, Any], inspection: Any, *,
                                scopes: Mapping[str, Any] | None = None,
                                scope_id: str | None = None
                                ) -> list[dict[str, Any]]:
    """All discovered/known candidates of one rule across a document.

    ``inspection`` is a ``DocumentInspection``-shaped object whose paragraphs
    carry ``.text``/``.location``; scoping is optional rule-scope containment.
    """
    operations = _replace_operations(rule)
    if not operations:
        return []
    scope = (scopes or {}).get(scope_id or str(rule.get("rule_id") or ""))
    canonical = {_compact(str(operation.get("old_text") or ""))
                 for operation in operations}
    found: list[dict[str, Any]] = []
    for span in getattr(inspection, "paragraphs", ()) or ():
        text = str(getattr(span, "text", "") or "")
        location = str(getattr(span, "location", "") or "")
        if not text.strip():
            continue
        if scope is not None and not scope.contains(location):
            continue
        compact = _compact(text)
        if any(ref and ref in compact for ref in canonical):
            continue  # literal wording present; inventory path owns it
        for operation in operations:
            for item in discover_candidates(operation, text):
                item.update(rule_id=str(rule.get("rule_id") or ""),
                            location=location, paragraph=text)
                found.append(item)
    return found


def review_candidate_rows(rule: Mapping[str, Any], inspection: Any, *,
                          scopes: Mapping[str, Any] | None = None
                          ) -> list[dict[str, Any]]:
    """Anchored-but-uncertified wordings as honest review evidence rows.

    An anomalous candidate must never authorise an edit; it stays visible so a
    human can confirm whether the contract really skips the clause.
    """
    rows: list[dict[str, Any]] = []
    for item in operation_variants_for_rule(rule, inspection, scopes=scopes):
        if item["bucket"] != "ANOMALOUS":
            continue
        rows.append({
            "kind": "variant_candidate",
            "code": "VARIANT_PENDING_CERTIFICATION",
            "rule_id": item["rule_id"],
            "operation_id": item["operation_id"],
            "location": item["location"],
            "reason": "variant_pending_certification",
            "quote": item["variant"],
            "anchor_chars": item["anchor_chars"],
        })
    return rows
