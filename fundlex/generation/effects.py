"""One operation's effect, proven at every verified business site.

No document-wide text is accepted as a substitute for a missing site. Source offsets
are used only on the source; the final paragraph is reconstructed from the final edit
set, including all sibling components, before its own effect is considered.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence


def _compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _class_labels(value: str) -> set[str]:
    """Share-class labels in a G02/G04 phrase (``A类及D类`` -> {A, D})."""
    return set(re.findall(r"([A-Z])类", _compact(value)))


def _class_group_equivalent(expected: str, source_quote: str) -> bool:
    """Treat ``A类及D类`` and ``A类、D类`` as the same already-correct group.

    G02/G04 authorize the *class set* in a fee-group definition, not a particular
    Chinese list delimiter.  The guide/canonical template uses ``、`` while real
    contracts commonly use ``及``/``和``; an exact string comparison falsely reported
    a multi-class group as an unperformed replacement.  Require the same non-empty
    label set so a missing or extra class still fails closed.
    """
    labels = _class_labels(expected)
    if not labels:
        return False
    # A fee-group quote often contains both clauses in one paragraph
    # ("A/D类…；C类…"). Compare within each clause so the expected A/D group is
    # not rejected merely because the C-class sibling is also present.
    return any(_class_labels(clause) == labels
               for clause in re.split(r"[；;。！？!?]", source_quote or ""))


@dataclass(frozen=True)
class OperationEffect:
    state: str
    artifact_status: str
    rule_id: str
    operation_id: str
    obligation_id: str
    sites: tuple[str, ...] = ()
    edit_ids: tuple[str, ...] = ()
    evidence: tuple[dict[str, Any], ...] = ()
    failure_code: str = ""
    reason: str = ""
    site_effects: tuple[dict[str, Any], ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "sites": list(self.sites), "edit_ids": list(self.edit_ids),
                "evidence": list(self.evidence), "site_effects": list(self.site_effects),
                "operations": [self.operation_id]}


def _keys(edit: Mapping[str, Any]) -> set[str]:
    evidence = edit.get("evidence") or {}
    result = {str(value) for value in edit.get("operation_keys") or ()}
    result.update(str(value) for value in evidence.get("operation_keys") or ())
    result.update(value.strip() for value in str(edit.get("operation_id") or "").split(",")
                  if value.strip())
    return result


def operation_units(edits: Sequence[Mapping[str, Any]], operation_id: str
                    ) -> list[tuple[Mapping[str, Any], Mapping[str, Any]]]:
    """A merged parent cannot lend its sibling's span to a component operation."""
    units = []
    for edit in edits:
        components = edit.get("components") or []
        for unit in components or [edit]:
            if isinstance(unit, Mapping) and operation_id in _keys(unit):
                units.append((edit, unit))
    return units


def effect_proof_passed(proof: Mapping[str, Any] | None, *, operation_id: str = "",
                        obligation_id: str = "") -> bool:
    """Shared consumer gate for replay, projection, sweep and delivery."""
    if not isinstance(proof, Mapping) or proof.get("state") != "PASS":
        return False
    if operation_id and proof.get("operation_id") != operation_id:
        return False
    if obligation_id and proof.get("obligation_id") != obligation_id:
        return False
    if proof.get("artifact_status") == "NOT_REQUIRED":
        return bool(proof.get("evidence"))
    sites = set(proof.get("sites") or ())
    evidence = proof.get("evidence") or ()
    proven_sites = {item.get("site_id") for item in evidence if isinstance(item, Mapping)
                    and item.get("proof_kind") and item.get("operation_id") == proof.get("operation_id")
                    and item.get("obligation_id") == proof.get("obligation_id")}
    effects = proof.get("site_effects") or ()
    return bool(sites) and sites <= proven_sites and not proof.get("failure_code") and all(
        item.get("state") == "PASS" for item in effects)


def _delete_quote_belongs(quote: str, references: Sequence[str]) -> bool:
    """Bind actual contract wording to this deletion, including verified variants.

    A target quote is not itself an old-effect signature: it can be an already
    satisfied business site. Require the operation's literal or bounded semantic
    signature before treating its unchanged source wording as a residual.
    """
    from ..recall import _delete_keyword_bag, _keyword_bag_in_clause
    body = _compact(quote)
    if len(body) < 8:
        return False
    for reference in references:
        old = _compact(reference)
        if not old:
            continue
        if old in body or body in old:
            return True
        bag = _delete_keyword_bag({"operations": [{"op": "delete", "old_text": old}]}, None)
        if bag and _keyword_bag_in_clause(body, bag):
            return True
    return False


def operation_site_bound(spec: Any, quote: str, original: Any, location: str,
                         facts: Any, *, parts: Sequence[Mapping[str, Any]] = (),
                         occurrence_index: int = -1) -> bool:
    """Require a rule's business site as well as a resolvable source quote.

    Inventory can attach an explicit operation key to a generic heading or a
    sibling clause. Reuse the existing site guards and operation wording rather
    than treating model attribution as source evidence. An already absent filing
    phrase can still be proven at its share-class setup site; a generic heading
    cannot supply that negative proof.
    """
    from types import SimpleNamespace
    from ..recall import (append_site_ok, instantiate_slots, reference_fragments,
                          target_site_ok, _looks_like_heading, _sequence_ratio)
    try:
        span = original.by_location(location)
    except (KeyError, ValueError, IndexError, AttributeError):
        return False
    if parts:
        body = "".join(str(part.get("quote") or "") for part in parts)
        span = SimpleNamespace(location=location, text=body)
    else:
        body = str(span.text)
    if not quote or _compact(quote) not in _compact(body) or _looks_like_heading(body):
        return False
    site_ok = (append_site_ok(spec.rule_id, span, original) if spec.op == "append"
               else target_site_ok(spec.rule_id, span, original))
    if not site_ok and spec.rule_id in {"G02", "G04"} and occurrence_index >= 0:
        # Narrow class substitutions authorize an exact occurrence within their
        # actual fee-group paragraph. The small quote is just the class label;
        # dropping it for lacking a paragraph-level heading could hide a second
        # unmodified occurrence behind another edit's successful proof.
        site_ok = (_compact(quote) == _compact(str(spec.old_text or "")) and
                   any(token in _compact(body) for token in
                       ("申购费", "认购费", "销售服务费")))
    if not site_ok and spec.rule_id in {"G02", "G04"}:
        # Split DOCX paragraphs put the heading ("基金份额类别：…") and the
        # fee-group wording ("…申购A类及D类…；…C类…") in adjacent paragraphs.
        # The target quote can still prove both fee groups and multiple class
        # labels even when its own paragraph has no heading token.
        q = _compact(quote)
        if (any(token in q for token in ("申购费", "认购费"))
                and "销售服务费" in q and len(_class_labels(q)) >= 2):
            site_ok = True
    if not site_ok:
        return False
    if spec.rule_id in {"G02", "G04"} and not any(
            token in _compact(body) for token in ("申购费", "认购费", "销售服务费")):
        # A split class-definition heading (for example "基金份额类别：本基金将
        # 基金份额分为 A 类、C 类和 D 类三种不同的") is not the fee-group clause
        # that G02/G04 authorize.  The actual group wording continues in the next
        # paragraph; treating the heading as a verified site both hides the real
        # occurrence and creates a false MISSING_EFFECT.
        return False
    if spec.rule_id == "G05":
        # G05 authorizes the manager's add/change/stop share-class setup clause.
        # Meeting-convening exemptions independently mention lowering redemption
        # fees; their matching fee words are neither duplicate G05 sites nor
        # evidence that G05's independent filing deletion is already satisfied.
        class_setup = _compact(body)
        if not ("份额类别的具体设置" in class_setup or re.search(
                r"(?:增加|增设|新增|变更|停止)[^。；;]{0,12}(?:基金)?份额类别",
                class_setup)):
            return False
    if spec.op == "append" and spec.rule_id in {"G01", "G03", "G16"}:
        # These append rules already have explicit rule-specific clause anchors.
        return True
    references = [str(spec.old_text or ""), *getattr(spec, "alternatives", ())]
    compact = _compact(quote)
    if spec.rule_id in {"G02", "G04"}:
        label = re.fullmatch(r"([A-Z])类基金份额", _compact(str(spec.old_text or "")))
        if label is not None and label.group(1) + "类" in compact:
            return True
    for reference in references:
        old = _compact(reference)
        if old and (old in compact or (len(compact) >= 8 and compact in old)):
            return True
        if any(_compact(fragment) in compact for fragment in reference_fragments(reference)):
            return True
    if spec.op == "delete":
        if _delete_quote_belongs(quote, references):
            return True
        # G05 filing is a bounded literal deletion within the class-setup/fee
        # adjustment clause. Its already-absent effect needs this own business
        # site, not the deleted literal, to remain a provable no-op.
        return spec.rule_id == "G05" and bool(references) and all(
            "备案" in _compact(reference) for reference in references if reference)
    expected = str(spec.new_text or "")
    try:
        instantiated, issues = instantiate_slots(expected, facts)
        if not issues:
            expected = instantiated
    except (AttributeError, TypeError):
        pass
    if expected and _compact(expected) in _compact(body):
        return True
    # The existing attribution layer accepts bounded wording variants at this
    # threshold. Keep its operation semantics while adding the site guard above.
    return any(len(_compact(reference)) >= 24 and
               _sequence_ratio(_compact(reference), compact) >= 0.35
               for reference in references)


def _verified_site_closure(sites: Sequence[Mapping[str, Any]], original: Any,
                           spec: Any) -> list[dict[str, Any]]:
    """Keep source duplicates and split-clause tails in the required site set.

    Only exact source paragraph copies inherit an established operation binding.
    A continuation must follow an unterminated bound quote and independently
    match that operation's reference; proximity alone never creates a site.
    """
    from ..recall import resolve_quote
    spans = list(getattr(original, "paragraphs", ()))
    index = {str(span.location): position for position, span in enumerate(spans)}
    references = [str(getattr(spec, "old_text", "") or ""),
                  *[str(value) for value in getattr(spec, "alternatives", ())]]
    closed: list[dict[str, Any]] = []
    for raw in sites:
        site = dict(raw)
        # Inventory's ``absent`` state means that no operation-specific source site
        # was found in that window.  It is never proof that a delete effect is
        # already absent, and it must not become a verified site merely because its
        # generic quote happens to resolve in the source document.  Claim Replay
        # filters these targets before calling the evaluator; keep this defensive
        # guard here for direct callers and future effect consumers.
        if str(site.get("state") or "") == "absent":
            continue
        location = str(site.get("location") or site.get("site_id") or "")
        if location not in index:
            closed.append(site)
            continue
        span = spans[index[location]]
        quote = str(site.get("quote") or "")
        bound = resolve_quote(span, quote) if quote else None
        if bound is None:
            closed.append(site)
            continue
        belongs = spec.op == "delete" and _delete_quote_belongs(quote, references)
        continuation = None
        if spec.op == "delete" and bound and quote.rstrip()[-1:] not in "。；;！？!?":
            # Survey may bind only the first physical paragraph of a clause. Use
            # the source offset and one immediately following paragraph to prove
            # that this is the operation's split effect before closing the site.
            start = bound[0]
            current = str(span.text)[start:]
            for follower in spans[index[location] + 1:]:
                follower_text = str(follower.text)
                if not follower_text.strip():
                    continue
                candidate = current + follower_text
                follows_reference = any(
                    len(_compact(follower_text)) >= 8 and
                    _compact(follower_text) in _compact(reference) for reference in references)
                if (_delete_quote_belongs(candidate, references)
                        and (not _delete_quote_belongs(current, references) or follows_reference)):
                    continuation = follower
                break
        if belongs or continuation is not None:
            start, end = bound
            # Complete a mid-sentence locator quote in its own source paragraph.
            if quote.rstrip()[-1:] not in "。；;！？!?":
                terminal = re.search(r"[。；;！？!?]", str(span.text)[end:])
                end = end + terminal.end() if terminal else len(str(span.text))
                site["quote"] = str(span.text)[start:end]
                if terminal is None and continuation is not None:
                    closed.append({"location": str(continuation.location),
                                   "quote": str(continuation.text),
                                   "source_binding": "operation_reference_continuation"})
        closed.append(site)
        # Repeated body/summary paragraphs remain separate required sites. Never
        # infer occurrence identity for the narrow G02/G04 substitution path.
        if int(site.get("occurrence_index", -1)) >= 0:
            continue
        body = _compact(str(span.text))
        if len(body) < 20:
            continue
        for duplicate in spans:
            if str(duplicate.location) != location and _compact(str(duplicate.text)) == body:
                match = resolve_quote(duplicate, str(site.get("quote") or ""))
                if match is not None:
                    closed.append({"location": str(duplicate.location),
                                   "quote": str(duplicate.text)[match[0]:match[1]],
                                   "source_binding": "exact_source_duplicate"})
    return closed


def evaluate_operation_effect(obligation: Any, original: Any, artifact: Any,
                              sites: Sequence[Mapping[str, Any]],
                              edits: Sequence[Mapping[str, Any]], facts: Any,
                              *, validated_units: Sequence[Mapping[str, Any]] = (),
                              authorized_new_texts: Mapping[str, Sequence[str]] | None = None
                              ) -> OperationEffect:
    spec = obligation.spec
    rule_id, operation_id = spec.rule_id, spec.operation_id
    obligation_id = obligation.obligation_id
    base = dict(rule_id=rule_id, operation_id=operation_id, obligation_id=obligation_id)
    applicability = obligation.applicability.status
    if applicability == "FALSE":
        return OperationEffect("NOT_APPLICABLE", "NOT_REQUIRED", **base)
    if applicability != "TRUE":
        return OperationEffect("OPEN", "UNPROVEN", **base,
                               failure_code="APPLICABILITY_UNKNOWN")
    if spec.op == "noop":
        return OperationEffect("PASS", "NOT_REQUIRED", **base, evidence=({
            "proof_kind": "certified_noop_branch", "operation_id": operation_id,
            "obligation_id": obligation_id},))
    sites = _verified_site_closure(sites, original, spec)
    if not sites:
        return OperationEffect("OPEN", "UNPROVEN", **base,
                               failure_code="CLAIM_OPERATION_UNPROVEN", reason="verified site missing")
    from ..recall import instantiate_slots
    from .claim_replay import _expected_after
    expected = str(spec.new_text or "")
    try:
        instantiated, issues = instantiate_slots(expected, facts)
        if not issues and instantiated:
            expected = instantiated
    except (AttributeError, TypeError):
        pass
    own_units = operation_units(edits, operation_id)
    evidence: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    edit_ids: list[str] = []
    seen: set[str] = set()
    # Several targets can bind different fragments in one paragraph. Retain all
    # operation-specific source quotes before deduplicating its proof site.
    bound_quotes: dict[str, list[str]] = {}
    for site in sites:
        location = str(site.get("location") or site.get("site_id") or "")
        bound_quotes.setdefault(location, []).append(str(site.get("quote") or ""))
    for site in sites:
        location = str(site.get("location") or site.get("site_id") or "")
        occurrence = int(site.get("occurrence_index", -1))
        site_id = f"{location}#occurrence:{occurrence}" if occurrence >= 0 else location
        if not location or site_id in seen:
            continue
        seen.add(site_id)
        item = {"site_id": site_id, "location": location, **base,
                "state": "OPEN", "artifact_status": "UNPROVEN",
                "failure_code": "CLAIM_OPERATION_UNPROVEN"}
        try:
            before = str(original.by_location(location).text)
            after = str(artifact.by_location(location).text)
        except (KeyError, ValueError, AttributeError, IndexError):
            results.append(item)
            continue
        quotes = [candidate for candidate in bound_quotes.get(location, ())
                  if candidate and _compact(candidate) in _compact(before)]
        quote = max(quotes, key=lambda value: len(_compact(value)), default="")
        if not quote:
            results.append(item)
            continue
        parent_edits = [edit for edit in edits if str(edit.get("location") or "") == location]
        own = [(edit, unit) for edit, unit in own_units
               if str(unit.get("location") or edit.get("location") or "") == location
               and (occurrence < 0 or unit.get("target_id") == site.get("target_id"))]
        actual_expected = _expected_after(before, parent_edits) if parent_edits else before
        planned_matches = actual_expected is not None and actual_expected == after
        unit_proofs = [unit for unit in validated_units
                       if str(unit.get("location") or "") == location
                       and (occurrence < 0 or unit.get("target_id") == site.get("target_id"))
                       and operation_id in {value.strip() for value in
                                            str(unit.get("operation_id") or "").split(",")}]
        validated = bool(unit_proofs) and all(unit.get("verdict") == "PASS" for unit in unit_proofs)
        expected_present = bool(expected) and (
            _compact(expected) in _compact(after)
            or (spec.rule_id in {"G02", "G04"} and spec.op == "replace"
                and _class_group_equivalent(expected, quote)))
        if occurrence >= 0 and spec.op == "replace":
            from .claim_replay import _occurrence_positions
            positions = _occurrence_positions(before, str(spec.old_text or ""))
            expected_present = False
            if occurrence < len(positions):
                left, right = positions[occurrence]
                shift = 0
                bounded = True
                for edit in sorted(parent_edits, key=lambda value: int(value.get("start") or 0)):
                    start, end = int(edit["start"]), int(edit["end"])
                    replacement = str(edit.get("replacement") or "")
                    if end <= left:
                        shift += len(replacement) - (end - start)
                    elif start < right:
                        if start == left and end == right:
                            right = left + len(replacement)
                        else:
                            bounded = False
                        break
                expected_present = bounded and _compact(after[left + shift:right + shift]) == _compact(expected)
        old_wordings = [str(spec.old_text or ""), *getattr(spec, "alternatives", ())]
        allowed_new = [str(value) for value in (authorized_new_texts or {}).get(location, ())
                       if _compact(str(value)) in _compact(after)]
        def retained_as_authorized_new(value: str) -> bool:
            return any(_compact(value) in _compact(new) for new in allowed_new)
        # Residual is evaluated in this verified site. Source offsets never slice AFTER.
        residual = any(_compact(old) and _compact(old) in _compact(after)
                       and _compact(old) not in _compact(expected)
                       and not retained_as_authorized_new(str(old)) for old in old_wordings)
        if spec.op == "delete":
            # The actual source wording is proof too. Canonical absence cannot
            # certify an unchanged variant or a composite paragraph component.
            residual = residual or any(
                _compact(candidate) in _compact(after)
                and _delete_quote_belongs(candidate, old_wordings)
                and not retained_as_authorized_new(candidate) for candidate in quotes)
            if not residual and any(str(item.get("location") or "") == location
                                    and item.get("source_binding") ==
                                    "operation_reference_continuation" for item in sites):
                residual = bool(_compact(quote) and _compact(quote) in _compact(after)
                                and not retained_as_authorized_new(quote))
        if own:
            edit_ids.extend(str(edit.get("edit_id") or
                                f"{edit.get('rule_id')}:{edit.get('target_id')}")
                            for edit, _ in own)
            if spec.op == "delete" and validated and not residual and all(
                    not _compact(str(unit.get("before") or "")) or
                    _compact(str(unit.get("before") or "")) not in _compact(after)
                    for unit in unit_proofs):
                # An independently proven deletion stays proven when another
                # component has an execution failure. Paragraph integrity still
                # blocks the document separately in Claim Replay.
                item.update(state="PASS", artifact_status="VERIFIED_ABSENT", failure_code="")
            elif not planned_matches:
                item.update(state="FAIL", artifact_status="WRONG_EFFECT",
                            failure_code="CLAIM_EXECUTION_EFFECT_MISSING")
            elif not validated:
                item.update(state="FAIL", artifact_status="WRONG_EFFECT",
                            failure_code="CLAIM_PLANNED_EFFECT_MISSING")
            elif spec.op == "delete" and residual:
                item.update(state="FAIL", artifact_status="RESIDUAL_OLD_TEXT",
                            failure_code="RESIDUAL_OLD_TEXT")
            elif spec.op == "replace" and residual and rule_id not in {"G02", "G04"}:
                item.update(state="FAIL", artifact_status="RESIDUAL_OLD_TEXT",
                            failure_code="RESIDUAL_OLD_TEXT")
            else:
                # Validated unit proof covers semantic compose as well as exact
                # templates; it has passed operation authorization and hard validators.
                item.update(state="PASS", artifact_status=("VERIFIED_ABSENT"
                            if spec.op == "delete" else "EXPECTED_EFFECT_PRESENT"), failure_code="")
        elif spec.op == "delete" and not residual:
            item.update(state="PASS", artifact_status="VERIFIED_ABSENT", failure_code="")
        elif spec.op in {"replace", "append"} and expected_present and not residual:
            item.update(state="PASS", artifact_status="ALREADY_SATISFIED", failure_code="")
        else:
            item.update(state="FAIL", artifact_status=("RESIDUAL_OLD_TEXT" if residual
                        else "MISSING_EFFECT"), failure_code="CLAIM_OPERATION_NOT_PLANNED")
        item.update(before_quote=quote, after_quote=after,
                    proof_kind="site_final_plan_reconstruction" if own else "site_literal_effect")
        evidence.append({key: item[key] for key in ("rule_id", "operation_id", "obligation_id",
            "site_id", "location", "before_quote", "after_quote", "proof_kind")})
        results.append(item)
    if not results:
        return OperationEffect("OPEN", "UNPROVEN", **base,
                               failure_code="CLAIM_OPERATION_UNPROVEN")
    failure = next((item for item in results if item["state"] == "FAIL"), None)
    unproven = next((item for item in results if item["state"] == "OPEN"), None)
    worst = failure or unproven
    status = worst["artifact_status"] if worst else (
        "VERIFIED_ABSENT" if spec.op == "delete" else
        "EXPECTED_EFFECT_PRESENT" if own_units else "ALREADY_SATISFIED")
    return OperationEffect(worst["state"] if worst else "PASS", status, **base,
        sites=tuple(sorted(seen)), edit_ids=tuple(dict.fromkeys(edit_ids)), evidence=tuple(evidence),
        failure_code=worst["failure_code"] if worst else "", site_effects=tuple(results))
