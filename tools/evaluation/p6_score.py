"""P6 scorer: compare the actual delivered DOCX against the frozen independent labels.

The scorer reads ONLY the frozen ``labels.json`` and the downloaded artifacts under the run
directory. It never reads the engine's plan, report replacements or target ledger, so the
score reflects what the customer would actually receive (the plan requires scoring the real
file, not ``report.applied``).

For every labelled target it decides one of:

* ``completed``   -- the required obligation is present in the final DOCX and the superseded
                     clause is gone;
* ``not_executed`` -- the target is absent/unresolved in the run and the file is unchanged;
* ``wrong``        -- the file changed but the required obligation is not correctly in place;
* ``kept``         -- a delete/replace target whose source text is still present verbatim
                     (the change did not happen where it was required).

Usage::

    .venv/bin/python -X utf8 -m tools.evaluation.p6_score \\
        --labels var/recall-first-evaluation/p6/labels.json \\
        --run var/recall-first-evaluation/p6-dev-baseline-01 \\
        --output var/recall-first-evaluation/p6-dev-baseline-01/score.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
Q = lambda name: "{" + W + "}" + name
COMPACT = re.compile(r"[\s\u3000]")
SCORER_VERSION = "p6-score-4-appendwindow-20261101"
_SITE_INDEX_KEYS = ("paragraph_index", "paragraph", "para_index", "source_paragraph",
                    "source_paragraph_index", "source_index")
_SITE_LOCATION_KEYS = ("paragraph_index", "paragraph", "para_index", "index", "paragraph_id")
_SITE_SCOPE_KEYS = ("site_scope", "scope", "zone", "section_scope")


def compact(text: str) -> str:
    return COMPACT.sub("", text or "")


def target_site(target: dict) -> dict:
    """The physical site a frozen label declares, when the label provides one.

    New independent labels distinguish the body and summary sites of the same rule
    (or two identical paragraphs) with ``paragraph_index``/``location`` and
    ``site_scope``.  Legacy labels have neither, so they keep the document-wide
    compatibility path and the score reports that limitation instead of pretending
    the site was proven.  Supported forms::

        {"paragraph_index": 157, "site_scope": "body"}
        {"location": {"paragraph_index": 157, "scope": "summary"}}
        {"location": "p157", "site_scope": "body"}

    ``compact_start`` is used as a fallback only when the label is already
    site-scoped but has no explicit paragraph index.
    """
    index = None
    for key in _SITE_INDEX_KEYS:
        value = target.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            index = value
            break
    location = target.get("location")
    if index is None and isinstance(location, int) and not isinstance(location, bool):
        index = location
    if index is None and isinstance(location, dict):
        for key in _SITE_LOCATION_KEYS:
            value = location.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                index = value
                break
    if index is None and isinstance(location, str):
        match = re.fullmatch(r"\s*(?:p|para|paragraph|§)?\s*(\d+)\s*", location,
                             flags=re.IGNORECASE)
        if match:
            index = int(match.group(1))
    scope = ""
    for key in _SITE_SCOPE_KEYS:
        value = target.get(key)
        if isinstance(value, str) and value.strip():
            scope = value.strip()
            break
    if not scope and isinstance(location, dict):
        for key in _SITE_SCOPE_KEYS:
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                scope = value.strip()
                break
    declared = index is not None or bool(scope) or location not in (None, "", {})
    if index is None and declared and isinstance(target.get("compact_start"), int):
        index = -1  # caller resolves the compact offset to a paragraph
    return {"declared": declared, "paragraph_index": index, "site_scope": scope,
            "location": location if isinstance(location, (str, int)) else None,
            "from_compact_start": index == -1}


def _site_text(paragraphs: list[str], index: int, *, after: int = 2,
               before: int = 1) -> str:
    """Target paragraph plus the neighbouring paragraphs an edit may create."""
    if index < 0 or index >= len(paragraphs):
        return ""
    return "\n".join(paragraphs[max(0, index - before):index + after + 1])


def _required_clauses(required: str) -> list[str]:
    """Sentence clauses without their boundary punctuation.

    Contracts legitimately end a clause with "。" where the guide uses "；" (or
    vice versa); the obligation is the wording, not the separator.  Keeping the
    separator made a correct clause read as missing.
    """
    return [clause.strip().rstrip("。；")
            for clause in re.split(r"(?<=[。；])", required or "") if clause.strip("。； \t\r\n")]


def _has_service_fee(facts: dict) -> bool:
    value = (facts or {}).get("has_service_fee")
    if isinstance(value, bool):
        return value
    return any(isinstance(item, dict) and item.get("service_fee")
               for item in ((facts or {}).get("classes") or []))


def _applicable_append_clauses(required: str, facts: dict) -> list[str]:
    """Clauses that require a subject in this product.

    The policy templates bundle a subscription-class clause with service-fee
    clauses.  A contract with no service-fee class cannot receive an invented C
    class, so the service clauses have no subject; requiring them would turn the
    engine's correct single-class append into a false miss (FL-D100/FL-D450).
    """
    clauses = _required_clauses(required)
    if not clauses or _has_service_fee(facts):
        return clauses
    applicable = [clause for clause in clauses if "销售服务费" not in clause]
    return applicable or clauses


def _clause_present(clause: str, text: str, *, threshold: float = 0.9,
                    min_fuzzy_chars: int = 24) -> bool:
    """Normalised clause presence; short clauses may not pass on fuzzy overlap.

    A short obligation such as "本基金C类基金份额不收取申购费用。" can share most
    characters with a different fee clause.  Only exact (normalised) matching is
    proof below ``min_fuzzy_chars``; long clauses may tolerate the small wording
    variants contracts legitimately introduce (FL-D099), with a high threshold.
    """
    obligation = _normalise_policy(clause)
    haystack = _normalise_policy(text)
    if not obligation or not haystack:
        return False
    if len(obligation) < min_fuzzy_chars:
        return obligation in haystack
    return _obligation_in_region(obligation, haystack, threshold=threshold)


def _replacement_present(required: str, text: str) -> bool:
    """Every labelled obligation clause must be in the replacement site.

    A long replacement can bundle a core rule and a conditional clause; matching
    only its first 24 characters or only the lead sentence would accept a partial
    edit (FL-D450).  Class enumerations are normalised because the product's own
    class letters legitimately differ from the template.
    """
    clauses = _required_clauses(required)
    if not clauses:
        return False
    return all(_clause_present(clause, text) for clause in clauses)


def _old_signature(target: dict, required: str) -> str:
    """Text whose survival proves the superseded obligation is still there.

    ``old_text`` can be a shared lead that the corrected sentence legitimately
    reuses, so a short substring of the required replacement is not evidence of a
    missed edit.  In that case the label's quoted old clause is used when it is
    itself superseded; otherwise the site/required-presence checks decide.
    """
    old = compact(target.get("old_text") or "")
    replacement = compact(required)
    if old and old not in replacement:
        return old
    quote = compact(_requirement_clause(target.get("requirement") or ""))
    if quote and quote not in replacement and quote != old:
        return quote
    return ""


def _changed_from_original(original_paragraphs: list[str], original_index: int,
                           final_index: int, site_text: str) -> bool:
    if final_index < 0:
        return True
    if original_index < 0 or original_index >= len(original_paragraphs):
        return False
    return compact(site_text) != compact(original_paragraphs[original_index])


def paragraphs_of(path: Path) -> list[str]:
    with ZipFile(path) as package:
        root = etree.fromstring(package.read("word/document.xml"),
                                parser=etree.XMLParser(resolve_entities=False, no_network=True))
    body = root.find(Q("body"))
    return ["".join(node.text or "" for node in paragraph.iter(Q("t")))
            for paragraph in body.iter(Q("p"))]


def class_label_from_guide(new_text: str, facts: dict, group: str) -> str | None:
    """What the guide's example group becomes for this product.

    G02/G04 write ``A类基金份额`` -> ``A类、B类基金份额``. For the group that charges a
    subscription fee and no service fee the replacement must name every such class; for the
    service-fee group every class that carries the fee. The labels record the product's own
    classes, so the expected label is derived here without reading engine output.
    """
    classes = facts.get("classes") or []
    if group == "subscription":
        names = [item["name"] for item in classes
                 if item.get("subscription_fee") and not item.get("service_fee")]
    else:
        names = [item["name"] for item in classes if item.get("service_fee")]
    if not names:
        return None
    return "、".join(name.replace("基金份额", "") for name in names) + "基金份额"


def paragraph_of_offset(paragraphs: list[str], compact_offset: int) -> int:
    """The paragraph index holding a given compacted-text offset (or -1)."""
    running = 0
    for index, paragraph in enumerate(paragraphs):
        running += len(compact(paragraph))
        if compact_offset < running:
            return index
    return len(paragraphs) - 1


def locate_paragraph(final_paragraphs: list[str], original_paragraph: str,
                     hint: int) -> int:
    """Find the original paragraph in the final document despite inserted paragraphs.

    Paragraph indices shift when the engine appends or deletes paragraphs, so the region is
    found by its content: the paragraph with the largest shared compact prefix near the hint.
    A paragraph whose own wording was replaced keeps its unchanged lead, which is what anchors
    the match.
    """
    target = compact(original_paragraph)
    if not target:
        return -1
    best, best_score = -1, 0.0
    low = max(0, hint - 12)
    high = min(len(final_paragraphs), hint + 40)
    for index in range(low, high):
        candidate = compact(final_paragraphs[index])
        if not candidate:
            continue
        head = min(len(target), len(candidate), 24)
        common = 0
        while common < head and target[common] == candidate[common]:
            common += 1
        score = common / max(1, head)
        if candidate == target:
            return index
        if score > best_score:
            best, best_score = index, score
    return best if best_score >= 0.6 else -1


def _locate_declared_site(final_paragraphs: list[str], original_paragraph: str,
                          declared_index: int) -> int:
    """Resolve a label-declared paragraph without jumping to a duplicate elsewhere.

    The body and summary of a contract can contain the same sentence.  A wide
    document-wide search would match the unchanged duplicate and prove the wrong
    site, so a declared site only searches its immediate neighbourhood.  If the
    wording was fully replaced and no neighbour shares its lead, the declared
    index is kept: the paragraph still occupies that position unless it was
    deleted (delete handles that case separately).
    """
    if declared_index < 0 or declared_index >= len(final_paragraphs):
        return -1
    target = compact(original_paragraph)
    best, best_score = -1, 0.0
    low, high = max(0, declared_index - 2), min(len(final_paragraphs), declared_index + 3)
    for index in range(low, high):
        candidate = compact(final_paragraphs[index])
        if candidate == target:
            return index
        head = min(len(target), len(candidate), 24)
        common = 0
        while common < head and target[common] == candidate[common]:
            common += 1
        score = common / max(1, head)
        if score > best_score:
            best, best_score = index, score
    if best_score >= 0.6:
        return best
    return declared_index


def _normalise_policy(value: str) -> str:
    """Canonicalise the wording variants contracts legitimately introduce.

    Beyond the punctuation/pronoun variants, contracts refer to fund share
    classes by their real letters. The rule templates assume "A类"/"C类", but a
    contract with three classes writes "A类、D类基金份额" where the template
    says "A类基金份额". The obligation is identical, so collapse every
    share-class enumeration to a single token before comparing.
    """
    value = compact(value)
    for variant, canonical in (("认购/申购", "申购"), ("认购、申购", "申购"),
                               ("的基金份额", "基金份额")):
        value = value.replace(variant, canonical)
    # Contract explanations of the same period ("持续持有期限超过一年（即365天，
    # 下同）") are not a different obligation.  Parentheticals are clarifications;
    # removing them from both sides prevents a correct append from reading as a
    # miss while still requiring the substantive clause (FL-D450).
    value = re.sub(r"（即\s*365\s*天(?:，下同)?）", "", value)
    value = value.replace("不再继续收取", "不再收取")
    value = value.replace("持有超过一年", "持续持有期限超过一年")
    # FL-D692 (a)/(b), mainline-authorised scorer equivalence layers (labels stay
    # frozen; only this instrument changes):
    # (b) Currency-split class names.  A product whose classes subdivide by
    # currency writes "A类人民币、A类美元" where the template/label names
    # "A类基金份额"; the fee obligation is class-letter-scoped, so drop the
    # currency qualifier from class tokens (closed domain lexicon, mirrors the
    # existing 认购/申购 canonicalisation), then dedupe the identical tokens the
    # exhaustive split produces ("A类、A类" -> "A类").
    value = re.sub(r"([A-ZＡ-Ｚ]类)(?:人民币|美元现汇|美元)", r"\1", value)
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"([A-ZＡ-Ｚ]类)(?:(?:和|、|及|与)+\1类)+", r"\1类", value)
    # "A类、D类基金份额" -> "类基金份额"; "A类" -> "类基金份额"-compatible form.
    value = re.sub(r"[A-ZＡ-Ｚ](?:类|份额)?(?:[、和及与][A-ZＡ-Ｚ](?:类|份额)?)*类?基金份额", "类基金份额", value)
    value = re.sub(r"[A-ZＡ-Ｚ]类基金份额", "类基金份额", value)
    # A single-class contract names no class letter at all ("申购本基金基金份额时"),
    # which is the same obligation as the template's "A类基金份额". Collapse the bare
    # form so a correct single-class append is not read as a miss.
    value = value.replace("类基金份额", "基金份额")
    # FL-D692 (a): fold-vs-expanded enumeration equivalence.  After the letter
    # collapse above, the label's expanded "C类基金份额和E类基金份额" reads
    # "基金份额和基金份额" while the engine's folded "C类、E类基金份额" reads
    # "基金份额" — run-collapse the connector-joined repeats so both canonical
    # forms converge (the "和"-repeated subject was the B17/T003 false-miss
    # mechanism the mainline review identified).  Class tokens that survived the
    # letter collapse carry no obligation distinction by design (the scorer is
    # letter-insensitive everywhere above), so any remaining bare "X类"/"X类份额"
    # token resolves to the same canonical "基金份额"; the loop is idempotent
    # because a token collapse can itself create a new connector-joined repeat.
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"基金份额(?:(?:和|、|及|与)+基金份额)+", "基金份额", value)
        value = re.sub(r"[A-ZＡ-Ｚ](?:类基金份额|类份额|类|份额)", "基金份额", value)
    return value


def _obligation_in_region(required: str, region: str, *, threshold: float = 0.9) -> bool:
    """True when the required obligation appears in the region up to small wording noise.

    A replacement can differ from the label only by a couple of characters: the G14
    policy "基金管理人可以适当调低基金申购费率和销售服务费率。" is delivered as
    "…调低基金申购费率和基金销售服务费率。" (one extra "基金"). A fixed-window
    comparison fails on an insertion because it shifts every later character, so measure
    the best alignment ratio over candidate windows with ``difflib`` instead. Only used
    as a fallback after the exact and normalised checks, and the threshold is high so a
    genuinely different obligation does not pass (FL-D099).
    """
    from difflib import SequenceMatcher

    obligation = compact(required)
    haystack = compact(region)
    if not obligation or not haystack:
        return False
    if obligation in haystack:
        return True
    # The obligation is a sentence; rarely longer than the region's paragraph, but compare
    # against windows of its own length stepped one character at a time.
    window = len(obligation)
    matcher = SequenceMatcher(autojunk=False)
    best = 0.0
    for start in range(0, max(1, len(haystack) - window) + 1):
        matcher.set_seq2(haystack[start:start + window])
        matcher.set_seq1(obligation)
        ratio = matcher.ratio()
        if ratio > best:
            best = ratio
            if best >= 0.999:
                break
    return best >= threshold


def appendix_present(required: str, final_compact: str) -> bool:
    """True when the appended clause appears in the final document.

    The appended wording is a full clause that contracts reproduce with small
    variations: an extra parenthetical, "申购" extended to "认购/申购", or a
    different set of fund share classes ("A类、D类" where the template says
    "A类"). Normalise those variants, but do **not** accept the clause by its lead
    sentence alone: a policy whose later required clause is missing must remain
    incomplete (FL-D450). Short clauses require an exact normalised match so a
    different fee obligation with shared characters cannot pass.
    """
    policy = _normalise_policy(required)
    haystack = _normalise_policy(final_compact)
    if not policy or not haystack:
        return False
    if policy in haystack:
        return True
    if len(policy) < 24:
        return False
    return _obligation_in_region(policy, haystack, threshold=0.9)


def appendix_present_applicable_clauses(required: str, final_compact: str,
                                        facts: dict) -> bool:
    """True when every clause that *can* apply to this contract is present.

    The policy bundles clauses for two class groups: the subscription class
    ("A类基金份额不收取认购/申购费用") and the service-fee class ("C类基金份额不收取
    销售服务费…持有超过一年不再收取").  A single-class contract charges no sales
    service fee, so the service clauses have no subject: the engine correctly
    appends only the subscription clause and must not invent a C class.  Score those
    contracts on the clauses that apply, but require *every* applicable clause —
    matching only the policy's first sentence would accept a partial append
    (FL-D450).
    """
    applicable = _applicable_append_clauses(required, facts)
    if not applicable:
        return False
    return all(appendix_present(clause, final_compact) for clause in applicable)


def _requirement_clause(requirement: str) -> str:
    """The clause text the requirement quotes between the Chinese quotation marks."""
    if not requirement:
        return ""
    for left, right in (("“", "”"), ("「", "」"), ('"', '"')):
        start = requirement.find(left)
        end = requirement.find(right, start + 1) if start >= 0 else -1
        if start >= 0 and end > start + 1:
            return requirement[start + 1:end]
    return ""


def _superseded_survives(target: dict, region: str, final_compact: str) -> bool:
    """True when the deleted clause is still present in the final document.

    The label's ``old_text`` is the anchor that located the clause and can be a short
    fragment ("销售服务费每日计提") that also appears verbatim inside a *different* clause
    kept on purpose (the appended policy text). Judging on that fragment alone reports a
    completed deletion as ``kept``. The requirement quotes the whole clause, so the verdict
    is decided on a distinctive long fragment of it (FL-D074).

    A quotation that names more than one sentence ("…服务费等。C类基金份额的销售服务费
    使用范围不包括…") is not a single deletion: only the sentence carrying the anchor is the
    target, and a later sentence can legitimately survive as its own clause. The trailing
    fragment is therefore only evidence when the anchor reaches the end of the quotation
    (FL-D097).
    """
    anchor = compact(target.get("old_text") or "")
    clause = compact(_requirement_clause(target.get("requirement") or ""))
    # Distinctive middle fragments of the quoted clause: skip the lead (often shared with
    # the kept policy text) and take interior runs.
    fragments: list[str] = []
    if len(clause) >= 24:
        fragments.extend([clause[8:40], clause[len(clause) // 2:len(clause) // 2 + 24]])
    # The trailing run is only distinctive when the anchor belongs to the quotation's last
    # sentence: a surviving later sentence is a separate clause, not a missed deletion.
    if len(clause) >= 24:
        last_sentence = [part for part in re.split(r"(?<=[。；])", clause) if part.strip()][-1]
        if anchor and anchor in last_sentence:
            fragments.append(clause[-24:])
    fragments = [frag for frag in fragments if len(frag) >= 12]
    if fragments:
        # The clause survives when any distinctive fragment is still present.
        return any(frag in final_compact for frag in fragments)
    # No quoted clause: fall back to the anchor.  When the paragraph could not be
    # located the whole document must be checked; treating an unlocatable paragraph
    # as proof of deletion let a clause moved further down the file count as gone
    # (FL-D450).
    if not anchor:
        return False
    return anchor in region or (not region and anchor in final_compact)


def score_target(target: dict, facts: dict, final_paragraphs: list[str],
                 original_paragraphs: list[str]) -> dict:
    """Judge one frozen label by comparing the original contract with the final DOCX.

    The region is the original paragraph that carried the target.  A label may name
    that physical site explicitly (``paragraph_index``/``location``/``site_scope``)
    so the body and summary occurrences of the same rule are scored separately: an
    append or replacement elsewhere in the file must not prove that this site was
    changed (FL-D450 site addendum).  Legacy labels without site metadata keep the
    document-wide compatibility path; the score reports a limitation instead of
    claiming the site was proven.

    Completion requires the full required obligation, not merely the disappearance
    of the old string.  For replace, the superseded obligation must also be gone;
    for append every applicable clause must be present; delete either removes the
    paragraph or proves the quoted clause/old anchor is absent from its region and
    the document.
    """
    rule_id = target["rule_id"]
    operation = target["op"]
    required = target.get("required_text") or ""
    old_text = target.get("old_text") or ""
    result = {"target_id": target.get("target_id"), "rule_id": rule_id, "op": operation}
    site = target_site(target)
    site_declared = bool(site.get("declared"))
    result["site_scoped"] = site_declared
    result["site"] = dict(site)
    final_compact = compact("\n".join(final_paragraphs))
    compact_offset = target.get("compact_start")
    original_index = -1
    # Independent labels use inspect_docx paragraph numbering, while the scorer
    # extracts every ``w:p`` (including TOC/table paragraphs).  A paragraph hash
    # is the common coordinate and prevents a valid target from being applied to
    # an unrelated paragraph that happens to share the numerical index.
    hashes = {
        value for value in (target.get("paragraph_text_sha256"),
                            target.get("anchor_paragraph_text_sha256"))
        if isinstance(value, str) and value
    }
    if hashes:
        matches = [index for index, paragraph in enumerate(original_paragraphs)
                   if hashlib.sha256(paragraph.encode("utf-8")).hexdigest() in hashes]
        if matches:
            # The same formula/anchor paragraph can occur in both the body and
            # the summary.  The label declares which copy it means; use the
            # contract's summary heading to disambiguate instead of taking the
            # first hash match (which sent the summary G16 target to the body).
            scope = str(site.get("scope") or target.get("scope") or "").lower()
            summary_headings = [
                index for index, paragraph in enumerate(original_paragraphs)
                if "基金合同内容摘要" in compact(paragraph)
            ]
            summary_start = max(summary_headings) if summary_headings else -1
            if scope == "summary" and summary_start >= 0:
                scoped = [index for index in matches if index >= summary_start]
                if scoped:
                    matches = scoped
            elif scope in {"main", "body"} and summary_start >= 0:
                scoped = [index for index in matches if index < summary_start]
                if scoped:
                    matches = scoped
            original_index = matches[0]
            site["paragraph_index"] = original_index
            site["resolved_by_paragraph_hash"] = True
    if original_index < 0 and isinstance(site.get("paragraph_index"), int) \
            and site["paragraph_index"] >= 0:
        original_index = site["paragraph_index"]
    elif original_index < 0 and isinstance(compact_offset, int):
        original_index = paragraph_of_offset(original_paragraphs, compact_offset)
    if site_declared and original_index < 0:
        result.update(verdict="unknown",
                      detail="declared site has no resolvable paragraph index")
        return result
    explicit_site = (site_declared and not site.get("from_compact_start")
                     and isinstance(site.get("paragraph_index"), int)
                     and site["paragraph_index"] >= 0)
    if explicit_site:
        final_index = _locate_declared_site(final_paragraphs,
                                           original_paragraphs[original_index], original_index)
    elif original_index >= 0:
        final_index = locate_paragraph(final_paragraphs, original_paragraphs[original_index],
                                       original_index)
    else:
        final_index = -1
    result["original_paragraph"] = original_index
    result["final_paragraph"] = final_index
    result["site"]["resolved_final_paragraph"] = final_index
    region = compact(final_paragraphs[final_index]) if final_index >= 0 else ""
    site_text = _site_text(final_paragraphs, final_index, after=2)
    # A fee clause can be split across several short paragraphs (formula, old
    # payment sentence, usage sentence, section tail).  The engine may choose a
    # different valid anchor inside the same clause (p799 vs p802); searching a
    # small clause window prevents a correct append from being reported missing
    # while still requiring the full policy text.  A body/summary target has its
    # own declared site and is scored separately.
    # FL-D790 (mainline ruling 2026-11-01): DEFINITION_GROUP_APPEND_END legally
    # rebinds an append to an earlier paragraph of the same subsection, with the
    # three policy clauses verbatim and replay-verified.  The forward-only
    # window (index-1..index+6) scored that legal landing as not_executed.
    # Symmetrize the backward reach to 6 paragraphs; the forward window and all
    # other paths are unchanged.
    append_text = _site_text(final_paragraphs, final_index, after=6, before=6)

    if operation == "append":
        if not required:
            result.update(verdict="wrong", detail="append without required text")
            return result
        if site_declared and final_index < 0:
            result.update(verdict="unknown",
                          detail="declared append site paragraph not found in final document")
            return result
        # Every applicable clause has to be present.  The old scorer accepted the
        # policy's lead clause alone, so a missing "超过一年不再收取" or
        # "其他销售机构按月支付" clause still counted as completed (FL-D450).
        applicable = _applicable_append_clauses(required, facts)
        haystack = append_text if site_declared else final_compact
        missing = [clause for clause in applicable if not appendix_present(clause, haystack)]
        if not missing:
            detail = ("appended policy text present at its declared site"
                      if site_declared else "appended policy text present")
            if not _has_service_fee(facts):
                detail += " (applicable clauses only)"
            result.update(verdict="completed", detail=detail)
        elif site_declared:
            result.update(verdict="not_executed",
                          detail=f"appended policy absent from its declared site: {len(missing)} clause(s)")
        else:
            result.update(verdict="not_executed",
                          detail=f"appended policy text absent: {len(missing)} clause(s)")
        return result

    if not old_text or not compact(old_text):
        result.update(verdict="wrong", detail=f"{operation} without old text")
        return result
    needle = compact(old_text)

    if rule_id in {"G02", "G04"}:
        classes = (facts or {}).get("classes") if isinstance(facts, dict) else None
        known_classes = [item for item in classes if isinstance(item, dict)] \
            if isinstance(classes, list) else []
        if not known_classes:
            # An empty/unknown class list cannot prove that no substitution was
            # needed; never turn "no group" into completed (FL-D450).
            result.update(verdict="unknown",
                          detail="class facts missing or empty; no group can be proven")
            return result
        subscription = class_label_from_guide(required, facts, "subscription")
        service = class_label_from_guide(required, facts, "service")
        expected = [label for label in (subscription, service) if label]
        if not expected:
            # Facts are known but this product has no class in either guided group.
            # The old "no group to substitute" verdict hid an unchanged clause.
            if site_declared and final_index < 0:
                result.update(verdict="unknown",
                              detail="declared class site paragraph not found")
            elif needle in (region or final_compact):
                result.update(verdict="kept",
                              detail="no class group matched and the old wording remains")
            elif _changed_from_original(original_paragraphs, original_index, final_index, region):
                result.update(verdict="wrong",
                              detail="file changed but no expected class group is derivable from facts")
            else:
                result.update(verdict="not_executed",
                              detail="no class group matched; old clause not executed")
            return result
        haystack = site_text if site_declared else final_compact
        missing = [label for label in expected if compact(label) not in compact(haystack)]
        if missing:
            result.update(verdict="wrong", detail=f"group label(s) absent: {missing}")
        else:
            result.update(verdict="completed",
                          detail="group labels present" + (" at the declared site"
                                                           if site_declared else ""))
        return result

    if operation == "delete":
        if final_index < 0:
            # The paragraph disappeared, which is the expected outcome, but the old
            # clause must still be verified against the whole document: locating
            # failure alone is not proof (FL-D450).
            if _superseded_survives(target, "", final_compact):
                result.update(verdict="kept",
                              detail="deleted clause still present elsewhere in the document")
            else:
                result.update(verdict="completed",
                              detail="deleted clause gone with its paragraph")
        elif not _superseded_survives(target, region, final_compact):
            result.update(verdict="completed", detail="deleted clause gone from its region")
        else:
            result.update(verdict="kept", detail="deleted clause still in its region")
        return result

    # replace: require the complete new obligation AND elimination of the old one.
    # The old-obligation check is site/region based: the same wording can legitimately
    # remain in another independent clause or at the other body/summary site, which is
    # scored by its own target.  Only when the paragraph disappeared do we fall back to
    # the whole document.
    old_signature = _old_signature(target, required)
    old_survives = bool(old_signature) and (
        old_signature in region or (final_index < 0 and old_signature in final_compact))
    if site_declared and final_index < 0:
        result.update(verdict="unknown",
                      detail="declared replacement site paragraph not found in final document")
        return result
    if site_declared:
        if not _replacement_present(required, site_text):
            if old_signature and old_signature in region:
                result.update(verdict="kept", detail="old wording still in its declared site")
            elif _changed_from_original(original_paragraphs, original_index, final_index, region):
                result.update(verdict="wrong",
                              detail="declared site changed but the complete required obligation is absent")
            else:
                result.update(verdict="not_executed",
                              detail="required replacement absent from its declared site")
            return result
        if old_survives:
            result.update(verdict="kept",
                          detail="required replacement present but the old obligation survives")
        else:
            result.update(verdict="completed",
                          detail="complete replacement present at its declared site")
        return result

    # Legacy labels have no declared site: keep the document-wide compatibility
    # path, but still require the full obligation and old-obligation elimination.
    if _replacement_present(required, site_text):
        if old_survives:
            result.update(verdict="kept",
                          detail="required replacement present but the old obligation survives")
        else:
            result.update(verdict="completed",
                          detail="required replacement present in its region")
    elif _replacement_present(required, final_compact):
        if old_survives:
            result.update(verdict="kept",
                          detail="required replacement elsewhere but the old obligation survives")
        else:
            result.update(verdict="completed",
                          detail="required replacement present elsewhere (legacy document-wide label)")
    elif old_signature and old_signature in region:
        result.update(verdict="kept", detail="old wording still in its region")
    elif _changed_from_original(original_paragraphs, original_index, final_index, region):
        result.update(verdict="wrong",
                      detail="file changed but the complete required obligation is absent")
    else:
        result.update(verdict="not_executed", detail="required replacement absent")
    return result


def _select_label_cases(label_cases: list[dict], run_dir: Path, group: str
                        ) -> tuple[list[dict], set[str], str | None]:
    """Pick the label cases this run actually covers (FL-D116).

    The frozen label file contains both the dev and holdout sets. A dev-only batch has
    no holdout artifacts, so scoring every label would count 111 unrun holdout targets
    as ``not_executed`` and make a 95% dev run look like 65%.
    """
    if group == "all":
        return list(label_cases), set(), None
    if group in {"dev", "holdout"}:
        return [case for case in label_cases if case.get("group") == group], set(), None
    batch_path = run_dir / "batch.json"
    run_cases: set[str] = set()
    if batch_path.exists():
        batch = json.loads(batch_path.read_text(encoding="utf-8"))
        run_cases = {str(case) for case in batch.get("cases") or []}
        run_cases |= {str(row.get("case_id")) for row in batch.get("results") or []
                      if row.get("case_id")}
    if not run_cases:
        return list(label_cases), set(), "no batch.json case list; scoring every label case"
    selected = [case for case in label_cases if case["case_id"] in run_cases]
    missing = {case["case_id"] for case in label_cases} - {case["case_id"] for case in selected}
    return selected, missing, None


def _case_facts(label: dict) -> dict:
    """Return the scorer facts for both legacy and first-batch label schemas.

    The independent first-batch labeler records richer, human-readable facts under
    ``fund`` (``share_classes`` with long field names) rather than the old scorer's
    compact ``classes`` list.  Do not flatten the evidence away: adapt only the
    fields the scorer consumes, and fail closed to an empty class list when the
    source does not prove a class set.
    """
    facts = label.get("facts") if isinstance(label.get("facts"), dict) else {}
    fund = label.get("fund") if isinstance(label.get("fund"), dict) else {}
    classes = list(facts.get("classes") or []) if isinstance(facts.get("classes"), list) else []
    if not classes:
        for item in fund.get("share_classes") or []:
            if not isinstance(item, dict):
                continue
            letter = str(item.get("label") or "").strip()
            name = item.get("name") or (f"{letter}类基金份额" if letter else "基金份额")
            classes.append({
                "name": name,
                "letter": letter,
                "subscription_fee": bool(item.get("pays_purchase_fee")),
                "service_fee": bool(item.get("charges_sales_service_fee")),
            })
    has_service_fee = facts.get("has_service_fee")
    if not isinstance(has_service_fee, bool):
        has_service_fee = facts.get("has_sales_service_fee")
    if not isinstance(has_service_fee, bool):
        has_service_fee = any(item.get("service_fee") for item in classes
                              if isinstance(item, dict))
    return {
        **facts,
        "fund_type": facts.get("fund_type") or fund.get("fund_type") or "",
        "excluded": bool(facts.get("excluded") or fund.get("excluded")),
        "class_count": int(facts.get("class_count") or fund.get("class_count")
                           or len(classes)),
        "classes": classes,
        "has_service_fee": bool(has_service_fee),
        "is_floating_fee": bool(facts.get("is_floating_fee")
                                if isinstance(facts.get("is_floating_fee"), bool)
                                else (facts.get("floating_management_fee")
                                      or fund.get("floating_management_fee"))),
    }


def _case_source_path(label: dict, source_root: Path, words_root: Path) -> Path | None:
    """Resolve a label's source without assuming old ``data/funds_word`` layout."""
    relative = label.get("relative")
    if isinstance(relative, str) and relative:
        path = source_root / relative
        if path.is_file():
            return path
    name = label.get("file")
    if isinstance(name, str) and name:
        path = words_root / name
        if path.is_file():
            return path
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default="var/recall-first-evaluation/p6/labels.json")
    parser.add_argument("--run", required=True)
    parser.add_argument("--data-root", default="/home/opencode/data")
    parser.add_argument("--source-root", default="/home/opencode/fundlex",
                        help="project root used to resolve label 'relative' paths")
    parser.add_argument("--output", default=None)
    parser.add_argument("--group", choices=("run", "dev", "holdout", "all"), default="run",
                        help="Label cases to score. 'run' (default) scores exactly the cases "
                             "listed in the run's batch.json, so a dev-only run is not diluted "
                             "by unrun holdout labels (FL-D116).")
    args = parser.parse_args()

    labels = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    run_dir = Path(args.run)
    words_root = Path(args.data_root) / "funds_word"
    output = Path(args.output) if args.output else run_dir / "score.json"

    label_cases = labels["cases"]
    selected, missing, warning = _select_label_cases(label_cases, run_dir, args.group)
    if warning:
        print("WARNING:", warning, flush=True)
    groups = {group: sum(1 for case in selected if case.get("group") == group)
              for group in sorted({case.get("group") or "?" for case in selected})}
    print(f"scored_cases={len(selected)}/{len(label_cases)} groups={json.dumps(groups, ensure_ascii=False)}",
          flush=True)
    if missing and args.group == "run":
        print(f"note: {len(missing)} label cases not in this run (not scored)", flush=True)

    case_rows: list[dict] = []
    verdict_totals: dict[str, int] = {}
    rule_stats: dict[str, dict[str, int]] = {}
    site_scoped_targets = 0
    legacy_targets = 0
    delivery = {"reported_complete": 0, "actually_complete": 0, "false_complete": 0,
                "editable_cases": 0}

    for label in selected:
        case_id = label["case_id"]
        case_dir = run_dir / case_id
        targets = label.get("targets") or []
        target_count = label.get("target_count")
        if not isinstance(target_count, int):
            target_count = len(targets)
        facts = _case_facts(label)
        entry: dict = {"case_id": case_id, "group": label.get("group") or "",
                       "editable": target_count > 0,
                       "facts": facts}
        final = None
        for candidate in ("final", "final.docx", "working_final", "working_final.docx"):
            path = case_dir / candidate
            if path.exists():
                final = path
                break
        if final is None:
            # No artifact at all: every editable target is not executed.
            plain = (case_dir / "result.json")
            report = json.loads((case_dir / "report.json").read_text(encoding="utf-8")) \
                if (case_dir / "report.json").exists() else {}
            entry["artifact"] = None
            entry["delivery_status"] = report.get("delivery_status")
            entry["verdicts"] = [{"target_id": t.get("target_id"), "rule_id": t["rule_id"],
                                  "verdict": "not_executed", "detail": "no artifact"}
                                 for t in targets]
        else:
            entry["artifact"] = str(final)
            entry["artifact_sha256"] = hashlib.sha256(final.read_bytes()).hexdigest()
            report = json.loads((case_dir / "report.json").read_text(encoding="utf-8")) \
                if (case_dir / "report.json").exists() else {}
            entry["delivery_status"] = report.get("delivery_status")
            final_paragraphs = paragraphs_of(final)
            original_path = _case_source_path(label, Path(args.source_root), words_root)
            original_paragraphs = paragraphs_of(original_path) if original_path and original_path.exists() else []
            entry["original"] = str(original_path)
            # The engine's own applicability decisions are cross-checked, never used to
            # score the text. A label the engine judged not applicable / already satisfied
            # is a disagreement about scope to report separately, not a silent miss.
            engine_status: dict[str, set] = {}
            for item in report.get("targets") or []:
                engine_status.setdefault(item.get("rule_id"), set()).add(item.get("status"))
            verdicts: list[dict] = []
            conflicts: list[dict] = []
            for label_target in targets:
                verdict = score_target(label_target, facts, final_paragraphs,
                                       original_paragraphs)
                statuses = engine_status.get(verdict["rule_id"]) or set()
                if statuses and statuses <= {"not_applicable", "satisfied"} \
                        and verdict["verdict"] in {"kept", "not_executed"}:
                    verdict["scope_conflict"] = True
                    conflicts.append({"rule_id": verdict["rule_id"],
                                      "engine_status": sorted(statuses),
                                      "label_verdict": verdict["verdict"]})
                verdicts.append(verdict)
            entry["verdicts"] = verdicts
            entry["applicability_conflicts"] = conflicts
        counts: dict[str, int] = {}
        for verdict in entry["verdicts"]:
            counts[verdict["verdict"]] = counts.get(verdict["verdict"], 0) + 1
            verdict_totals[verdict["verdict"]] = verdict_totals.get(verdict["verdict"], 0) + 1
            if verdict.get("site_scoped"):
                site_scoped_targets += 1
            else:
                legacy_targets += 1
            key = verdict["rule_id"]
            stats = rule_stats.setdefault(key, {"completed": 0, "total": 0})
            stats["total"] += 1
            if verdict["verdict"] == "completed":
                stats["completed"] += 1
        entry["counts"] = counts
        if entry["editable"]:
            delivery["editable_cases"] += 1
            if report.get("delivery_status") == "complete":
                delivery["reported_complete"] += 1
            complete = counts.get("completed", 0) == len(entry["verdicts"]) and not counts.get("wrong")
            entry["integrated_complete"] = complete
            if complete:
                delivery["actually_complete"] += 1
                if report.get("delivery_status") != "complete":
                    delivery["false_complete"] += 0  # reported less than actual: fine
            elif report.get("delivery_status") == "complete":
                delivery["false_complete"] += 1
        case_rows.append(entry)

    total = sum(verdict_totals.values()) or 1
    completed = verdict_totals.get("completed", 0)
    site_scoped_targets = sum(1 for case in selected for target in case["targets"]
                              if target_site(target).get("declared"))
    legacy_targets = max(0, total - site_scoped_targets)
    limitations: list[str] = []
    if legacy_targets:
        limitations.append(
            f"{legacy_targets} of {total} target(s) have no location/paragraph_index/"
            "site_scope; they were scored document-wide for backward compatibility, so a "
            "same-text edit at another body/summary site can not be distinguished for them")
    conflicts_total = sum(len(case.get("applicability_conflicts") or []) for case in case_rows)
    payload = {
        "schema": "fundlex-p6-score-v1",
        "scorer_version": SCORER_VERSION,
        "scored_at": datetime.now(timezone.utc).isoformat(),
        "run": str(run_dir),
        "labels_sha256": hashlib.sha256(Path(args.labels).read_bytes()).hexdigest(),
        "totals": {
            "targets": total,
            "completed": completed,
            "target_completion_rate": round(completed / total, 4),
            "verdicts": verdict_totals,
            "applicability_conflicts": conflicts_total,
        },
        "delivery": delivery,
        "scoring": {
            "site_scoped_targets": site_scoped_targets,
            "legacy_document_wide_targets": legacy_targets,
            "site_aware": True,
        },
        "limitations": limitations,
        "cases_scored": len(selected),
        "groups": groups,
        "rule_completion": {
            rule: {"completed": stats["completed"], "total": stats["total"],
                   "rate": round(stats["completed"] / stats["total"], 4)}
            for rule, stats in sorted(rule_stats.items())},
        "cases": case_rows,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"targets": total, "completed": completed,
                      "rate": payload["totals"]["target_completion_rate"],
                      "verdicts": verdict_totals, "delivery": delivery}, ensure_ascii=False))
    print("score sha256:", hashlib.sha256(output.read_bytes()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
