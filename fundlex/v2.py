"""Rule-constrained AI locate / generate / verify engine (evaluation only).

The engine never trusts model-supplied character offsets or verification flags.
Models propose evidence and text inside one contract paragraph plus labelled rule
and profile sources; this module resolves quotes against the source projection,
computes coordinates, runs deterministic requirement checks and assembles a
server-side verification record. Only a passed record can become an executable
edit, and the record is re-verified again at every DOCX validation boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable, Iterator, Sequence

from .docx import DocxError, DocumentInspection
from .model import ModelError
from .rules import (_fragmented_phrase, _normalized_matches, _normalized_text, _old_text_equal,
                    _recognition_guard, _recognized_literals, _subsection_title, applicability)
from .rules_v2 import PROMPT_VERSIONS_V2, RuleSetV2

RECORD_VERSION = "v2-content-verification-1"
BOUNDARY_POLICY = "trim-inline-whitespace-sentence-span-v1"

_VERIFY_INSTRUCTION = (
    "独立核对：[GENERATED_TEXT] 中的新文是否逐项满足 [RULE_REQUIREMENTS] 的要求。"
    "判断对象只是新文；[CONTRACT_SOURCE] 仅用于核对主体、时点与事实是否一致，"
    "不得因为旧合同原文仍包含旧表述而判定 unsatisfied。"
    "先逐字对照新文与要求；只有新文直接违反该条要求时才判定 unsatisfied；"
    "若判定 unsatisfied，evidence_quote 必须来自 generated；无法从给定来源确认时返回 unknown。"
    "对每条要求给出 satisfied/unsatisfied/unknown，并给出所引用来源中的逐字连续原文："
    "generated=新文原文，contract=合同原文，rule=规则要求文本。"
    "不得使用生成者的解释或事实声明。"
    "逐项输出 requirement_id、result、evidence_quote、evidence_source。"
)

# Boundary punctuation used to decide whether an inserted/replaced text would
# run into its neighbours. A missing separator is repaired with a sentence
# period by code (never by inventing business content).
_LEFT_BOUNDARY = set("。；！？：，、,;:.!?）)】」』”\"'…\u3000 \t\r\n")
_LEFT_LEAD_OK = set("。；！？：，、,;:.!?）】」』”\"'（(“「『《【\u3000 \t")
_RIGHT_BOUNDARY = set("。；！？：，、,;:）】」』”\"'…\u3000 \t\r\n")
_RIGHT_TAIL_OK = set("。；！？…：，、,;:.!?\u3000 \t")


def _numbering_before(text: str, start: int) -> bool:
    if start <= 0:
        return False
    prefix = text[:start]
    return bool(re.search(r"(?:^|[\n。；])\s*(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十\d]+)[、．.]\s*$", prefix))


def _join_repairs(text: str, left_at: int, right_at: int, replacement: str) -> tuple[str, list[str]]:
    """Ensure the written text does not run into its neighbours.

    The repair only adds a sentence period on the joining side; it never invents
    or removes business content. The repaired replacement is what gets verified
    and bound in the server-side record.
    """
    notes: list[str] = []
    if not replacement:
        return replacement, notes
    left = text[left_at - 1] if 0 < left_at <= len(text) else ""
    right = text[right_at] if 0 <= right_at < len(text) else ""
    left_ok = (not left or left in _LEFT_BOUNDARY or _numbering_before(text, left_at)
               or replacement[0] in _LEFT_LEAD_OK)
    right_ok = not right or right in _RIGHT_BOUNDARY or replacement[-1] in _RIGHT_TAIL_OK
    if not left_ok:
        replacement = "。" + replacement
        notes.append("prepend_sentence_period")
    if not right_ok:
        replacement = replacement + "。"
        notes.append("append_sentence_period")
    return replacement, notes


class V2Error(ValueError):
    def __init__(self, code: str, details: dict[str, Any] | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":")).encode("utf-8")).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _quote_in(quote: str, container: str) -> bool:
    """Bind a quote to its role source, tolerating CJK typesetting spaces only."""
    return bool(quote) and (quote in container or _compact(quote) in _compact(container))


def _trim(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _event_summary(gateway: Any) -> dict[str, Any]:
    events = getattr(gateway, "events", [])
    if not events:
        return {}
    event = events[-1]
    return {key: event.get(key) for key in ("task_type", "prompt_version", "actual_model", "request_id",
                                            "latency_ms", "http_status", "error_code")}


def _numbered_heading_like(text: str) -> bool:
    """A numbered paragraph only ends the current subsection when it reads like a heading."""
    if len(text) >= 100 or not re.match(r"^[一二三四五六七八九十\d]+[、．.]", text):
        return False
    stripped = re.sub(r"^[（(]?[一二三四五六七八九十\d]+[）)、．.]\s*", "", text.strip())
    return len(stripped) <= 40 and not re.search(r"[。；，,]", stripped)


def _embedded_subsection_label(text: str, action: dict[str, Any]) -> bool:
    """Recognize subsection labels glued to the end of a preceding paragraph.

    Real contracts often merge a heading into the previous clause, e.g.
    ``基金存续期限不定期八、基金份额类别``. The label must still be preceded
    by a clause number so ordinary sentences cannot establish a scope.
    """
    compact, _ = _normalized_text(text.strip())
    names = [action["subsection_anchor"]] + list(action.get("subsection_aliases", []))
    for name in names:
        if len(compact) > len(name) and compact.endswith(name):
            before = compact[: -len(name)]
            if re.search(r"(?:[一二三四五六七八九十\d]+[、．.]|[（(][一二三四五六七八九十\d]+[）)]|[:：])$", before):
                return True
    return False


def _boundary_ok(text: str, start: int) -> bool:
    if start <= 0:
        return True
    if text[start - 1] in "。；\n":
        return True
    prefix = text[:start]
    return bool(re.search(r"(?:^|[\n。；])\s*(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十\d]+)[、．.]\s*$", prefix))


def iter_scope_spans(inspection: DocumentInspection, action: dict[str, Any]) -> Iterator[tuple[Any, Any]]:
    """Yield in-scope spans and their in-scope predecessor.

    The v2 scope keeps the current subsection across numbered content paragraphs
    (e.g. "1、由于基金费用的不同…"); only heading-like numbered paragraphs end it.
    """
    regions = action["regions"]
    sections = [action["section_anchor"]] + list(action.get("section_aliases", []))
    previous_section = None
    subsection = ""
    previous_span = None
    for span in inspection.paragraphs:
        logical_zone = getattr(span, "logical_zone", None) or span.zone
        current_section = (logical_zone, span.section_path)
        if current_section != previous_section:
            subsection, previous_section, previous_span = "", current_section, None
        if _subsection_title(span.text, action):
            subsection, previous_span = span.text, None
        elif _embedded_subsection_label(span.text, action):
            subsection, previous_span = span.text, None
        elif _numbered_heading_like(span.text):
            subsection, previous_span = "", None
        if logical_zone not in regions or not any(title in span.section_path for title in sections):
            continue
        if not subsection:
            continue
        yield span, previous_span
        previous_span = span


# --------------------------------------------------------------------------- targets

def _failure(reason: str, **details: Any) -> dict[str, Any]:
    return {"status": "failed", "reason": reason, "location": "", "region": "",
            "char_start": 0, "char_end": 0, "quote": "", "mapping_safe": False, **details}


def _matching_context(action: dict[str, Any], profile: dict[str, Any], spans: Sequence[Any],
                      gateway: Any) -> str:
    context = (f"[ACTION {action['action_id']}]\n{_rule_text(action)}\n"
               f"[PROFILE_FACTS]\n{profile_facts_text(profile)}\n[CONTRACT_SOURCE]\n" +
               "\n".join(f"[PARAGRAPH {s.location}]\n{s.text}" for s in spans))
    if len(context) > int(getattr(gateway, "max_context_chars", 12000)):
        raise V2Error("V3_MATCH_CONTEXT_LIMIT")
    return context


def _scope_windows(action: dict[str, Any], profile: dict[str, Any], chapter: Sequence[Any],
                   gateway: Any) -> list[list[Any]]:
    windows: list[list[Any]] = []
    current: list[Any] = []
    for span in chapter:
        try:
            _matching_context(action, profile, [*current, span], gateway)
        except V2Error:
            if not current:
                raise
            windows.append(current)
            overlap = current[-1:]
            try:
                _matching_context(action, profile, [*overlap, span], gateway)
            except V2Error:
                # Never silently remove an overlap or split a single paragraph.
                raise V2Error("V3_MATCH_CONTEXT_LIMIT")
            current = [*overlap, span]
        else:
            current.append(span)
    if current:
        windows.append(current)
    return windows


def _business_candidate(span: Any, action: dict[str, Any], policy: dict,
                        text: str | None = None) -> bool:
    original = _compact(span.text)
    # Titles provide scope, never a clause to rewrite/delete.
    if (len(original) <= 80 and not re.search(r"[。；，,]", original)
            and (_subsection_title(span.text, action) or _numbered_heading_like(span.text)
                 or original == _compact(span.section_path))):
        return False
    candidate = _compact(span.text if text is None else text)
    return (any(token in candidate for token in policy.get("any", []))
            and all(token in candidate for token in policy.get("all", [])))


def resolve_action_scope(inspection: DocumentInspection, action: dict[str, Any],
                         profile: dict[str, Any], gateway: Any) -> tuple[list[tuple[Any, Any]], dict[str, Any]]:
    """Resolve each allowed chapter independently; never infer an absent chapter."""
    deterministic = list(iter_scope_spans(inspection, action))
    diagnostic: dict[str, Any] = {"method": "code", "ranges": [], "failures": []}
    for span, _ in deterministic:
        diagnostic["ranges"].append({"location": span.location, "method": "code"})
    policy = action.get("scope_resolution")
    if not policy:
        return deterministic, diagnostic
    sections = [action["section_anchor"]] + list(action.get("section_aliases", []))
    groups: dict[tuple[str, str], list[Any]] = {}
    chapters: dict[tuple[str, str], list[Any]] = {}
    existing_locations = {s.location for s, _ in deterministic}
    resolved_groups = {((getattr(s, "logical_zone", None) or s.zone), s.section_path) for s, _ in deterministic}
    for span in inspection.paragraphs:
        zone = getattr(span, "logical_zone", None) or span.zone
        if zone in action["regions"] and any(title in span.section_path for title in sections):
            key = (zone, span.section_path)
            chapters.setdefault(key, []).append(span)
    for key, chapter in chapters.items():
        candidates = policy.get("business_candidates") or action["locate"].get("variant_fallback")
        if key not in resolved_groups or (candidates and any(
                s.location not in existing_locations and _business_candidate(s, action, candidates)
                for s in chapter)):
            groups[key] = chapter
    if len(groups) > policy["max_sections"]:
        diagnostic["failures"].append("V3_SCOPE_SECTION_LIMIT")
        return [], diagnostic
    selected = {span.location for span, _ in deterministic}
    try:
        windows = [(key, chapter, window) for key, chapter in groups.items()
                   for window in _scope_windows(action, profile, chapter, gateway)]
        if len(windows) > policy["max_sections"]:
            raise V2Error("V3_SCOPE_WINDOW_LIMIT")
    except V2Error as exc:
        diagnostic["failures"].append(exc.code)
        return [], diagnostic
    found_groups = set()
    for key, chapter, window in windows:
        try:
            context = _matching_context(action, profile, window, gateway)
            response = gateway.resolve_scope(context, prompt_version=PROMPT_VERSIONS_V2["scope"],
                instruction=("识别承担目标业务功能的所有连续段落范围，可以无明确子节标题。"
                             "仅限给定上级章节。每个范围给出首尾段落中的逐字连续引文与依据。"
                             "不得返回修改文字或坐标；找不到返回 absent，不确定返回 uncertain。"))
            value = response.value
            diagnostic.setdefault("windows", []).append({"locations": [s.location for s in window],
                "status": value.get("status"), "model_event": _event_summary(gateway)})
            if value.get("status") == "absent" and not value.get("ranges"):
                continue
            if value.get("status") != "found" or not value.get("ranges"):
                raise V2Error("TARGET_SCOPE_UNRESOLVED")
            group_selected: set[str] = set()
            for item in value["ranges"]:
                endpoints = []
                for field in ("start_quote", "end_quote"):
                    quote = item.get(field)
                    occurrences = [i for i, s in enumerate(chapter)
                                   for _ in range(s.text.count(quote) if isinstance(quote, str) and quote else 0)]
                    if len(occurrences) != 1:
                        raise V2Error("V3_SCOPE_QUOTE_UNRESOLVED")
                    endpoints.append(occurrences[0])
                lo, hi = endpoints
                if not item.get("basis") or lo > hi or hi - lo + 1 > policy["max_range_paragraphs"]:
                    raise V2Error("V3_SCOPE_RANGE_INVALID")
                if any(s.location not in {w.location for w in window} for s in chapter[lo:hi + 1]):
                    raise V2Error("V3_SCOPE_OUTSIDE_WINDOW")
                group_selected.update(s.location for s in chapter[lo:hi + 1])
                diagnostic["ranges"].append({"method": "model", "region": key[0],
                    "section_path": key[1], "start_quote": item["start_quote"],
                    "end_quote": item["end_quote"], "basis": item["basis"],
                    "locations": [s.location for s in chapter[lo:hi + 1]],
                    "model_event": _event_summary(gateway)})
            selected.update(group_selected)
            found_groups.add(key)
        except V2Error as exc:
            diagnostic["failures"].append(exc.code)
    if set(groups) - found_groups:
        diagnostic["failures"].append("TARGET_SCOPE_UNRESOLVED")
    diagnostic["method"] = "code+model" if groups else "code"
    spans = []
    previous = None
    for span in inspection.paragraphs:
        if span.location in selected:
            if previous is not None and (span.section_path != previous.section_path or span.zone != previous.zone):
                previous = None
            spans.append((span, previous))
            previous = span
        else:
            previous = None
    return spans, diagnostic

def _base_target(span: Any, inspection: DocumentInspection) -> dict[str, Any]:
    return {"location": span.location, "region": getattr(span, "logical_zone", None) or span.zone,
            "zone": span.zone, "section_path": span.section_path, "source_sha256": inspection.source_sha256,
            "status": "failed", "reason": None, "char_start": 0, "char_end": 0, "quote": "",
            "mapping_safe": False, "host_evidence": [], "anchor": None}


def _structure_failure(span: Any, inspection: DocumentInspection) -> dict[str, Any]:
    return {**_base_target(span, inspection), "quote": span.text, "char_end": len(span.text),
            "reason": "UNSUPPORTED_TARGET_STRUCTURE", "structure_reasons": list(getattr(span, "reasons", ()))}


def _safe_range(span: Any, start: int, end: int) -> bool:
    return bool(span.editable) and any(segment.start <= start and end <= segment.end for segment in span.segments)


def _slot_groups(action: dict[str, Any]) -> dict[str, str]:
    groups: dict[str, str] = {}
    for key in ("locate", "generation"):
        groups.update((action.get(key) or {}).get("slots") or {})
    return groups


def _instantiate_slots(text: str, action: dict[str, Any],
                       profile: dict[str, Any]) -> tuple[str, str | None, dict[str, list[str]]]:
    """Replace class-slot tokens with the current contract's actual class groups."""
    slots = _slot_groups(action)
    if not slots:
        return text, None, {}
    if not profile.get("fee_groups_verified"):
        return text, "V2_SLOT_UNRESOLVED", {}
    used: dict[str, list[str]] = {}
    for token, group in slots.items():
        names = list(profile.get("fee_groups", {}).get(group, []))
        if not names:
            return text, "V2_SLOT_UNRESOLVED", {}
        text = text.replace(token, "、".join(name + "类" for name in names) + "基金份额")
        used[token] = names
    return text, None, used


def _expand_sentence(text: str, start: int, end: int) -> tuple[int, int]:
    marks = ("。", "；", "\n", "\ufff9")
    at = max(text.rfind(mark, 0, start) for mark in marks)
    start = at + 1
    if end > start and text[end - 1] in "。；\n":
        return start, end
    stops = [(index, mark) for mark in marks if (index := text.find(mark, end)) >= 0]
    if stops:
        position, mark = min(stops)
        end = position + (1 if mark in "。；" else 0)
    else:
        end = len(text)
    return start, end


def _locate_literal(action: dict[str, Any], spans: Sequence[tuple[Any, Any]],
                    inspection: DocumentInspection, profile: dict[str, Any]) -> list[dict[str, Any]]:
    raw_triggers = action["locate"]["triggers"]
    raw_old_texts = action["locate"].get("old_texts", raw_triggers)
    triggers: list[str] = []
    for trigger in raw_triggers:
        instantiated, error, _ = _instantiate_slots(trigger, action, profile)
        if error:
            return [{"status": "failed", "reason": error, "location": "", "region": "",
                     "char_start": 0, "char_end": 0, "quote": "", "mapping_safe": False}]
        triggers.append(instantiated)
    old_texts: list[str] = []
    for old in raw_old_texts:
        instantiated, error, _ = _instantiate_slots(old, action, profile)
        if error:
            return [{"status": "failed", "reason": error, "location": "", "region": "",
                     "char_start": 0, "char_end": 0, "quote": "", "mapping_safe": False}]
        old_texts.append(instantiated)
    scope = action["scope"]
    targets: list[dict[str, Any]] = []
    for span, previous in spans:
        if span.zone == "unsupported_table":
            targets.append(_structure_failure(span, inspection))
            continue
        for fragmented in _fragmented_phrase(previous, span, triggers):
            targets.append({**_base_target(span, inspection), "char_start": fragmented["char_start"],
                            "char_end": fragmented["char_end"], "quote": fragmented["quote"],
                            "evidence_spans": fragmented["evidence_spans"],
                            "reason": "CROSS_PARAGRAPH_TARGET_UNSUPPORTED"})
        seen: set[tuple[int, int]] = set()
        for trigger in triggers:
            for start, end in _normalized_matches(span.text, trigger):
                if scope == "sentence":
                    start, end = _expand_sentence(span.text, start, end)
                elif scope == "paragraph":
                    start, end = 0, len(span.text)
                start, end = _trim(span.text, start, end)
                if (start, end) in seen:
                    continue
                seen.add((start, end))
                literal = span.text[start:end]
                target = {**_base_target(span, inspection), "char_start": start, "char_end": end,
                          "quote": literal, "trigger": trigger,
                          "mapping_safe": _safe_range(span, start, end)}
                if scope in {"sentence", "paragraph"} and not any(_old_text_equal(literal, old) for old in old_texts):
                    # The whole sentence/paragraph must equal the published old
                    # text, otherwise a replacement would drop surrounding text.
                    target["reason"] = "V2_SCOPE_TEXT_MISMATCH"
                elif not target["mapping_safe"]:
                    target["reason"] = "UNSAFE_TEXT_MAPPING"
                else:
                    target["status"] = "located"
                targets.append(target)
    return targets


def _locate_recognition(action: dict[str, Any], spans: Sequence[tuple[Any, Any]],
                        inspection: DocumentInspection) -> list[dict[str, Any]]:
    kind = action["locate"]["recognition_kind"]
    targets: list[dict[str, Any]] = []
    for span, previous in spans:
        if span.zone == "unsupported_table":
            targets.append(_structure_failure(span, inspection))
            continue
        hits = list(_recognized_literals(span.text, kind))
        seen: set[tuple[int, int]] = set()
        for quote in hits:
            start, end = _trim(span.text, span.text.find(quote), span.text.find(quote) + len(quote))
            if (start, end) in seen:
                continue
            seen.add((start, end))
            literal = span.text[start:end]
            target = {**_base_target(span, inspection), "char_start": start, "char_end": end,
                      "quote": literal, "mapping_safe": _safe_range(span, start, end),
                      "recognition_kind": kind}
            recognized, recognition_reason = _recognition_guard(literal, kind, span, previous)
            if recognized and kind == "short_holding_redemption":
                evidence = []
                for host_span in [span] + ([previous] if previous is not None else []):
                    for segment in host_span.segments:
                        text = host_span.text[segment.start:segment.end]
                        compact, positions = _normalized_text(text)
                        match = re.search(r"(?:调整(?:费率|收费方式)|申购费率[^。；\n\ufff9]*?赎回费率|赎回费率按照持有时间|实际执行的赎回费率)", compact)
                        if match:
                            lo = segment.start + positions[match.start()]
                            hi = segment.start + positions[match.end() - 1] + 1
                            evidence.append({"location": host_span.location, "quote": host_span.text[lo:hi],
                                             "char_start": lo, "char_end": hi, "part_uri": host_span.part_uri})
                target["host_evidence"] = evidence
            if recognized and target["mapping_safe"]:
                target["status"] = "located"
            elif recognition_reason == "SHORT_HOLDING_NON_TARGET_HOST":
                target.update(status="excluded", reason=recognition_reason)
            else:
                target["reason"] = recognition_reason or "UNSAFE_TEXT_MAPPING"
            targets.append(target)
    return targets


def _sentence_spans(span: Any) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    offset = 0
    for piece in re.split(r"(?<=[。；;])", span.text):
        if piece:
            spans.append((offset, offset + len(piece)))
        offset += len(piece)
    return spans


def _class_definition_sentences(span: Any, action: dict[str, Any],
                                window_text: str = "") -> list[tuple[int, int, set[str]]]:
    """Find the class-definition statement; class letters may follow in the block.

    Many contracts write ``将基金份额分为不同的类别。`` first and name the
    classes in the following sentences or paragraphs. The window text (this
    paragraph plus the next in-scope paragraphs, bounded by the caller) is used
    only to collect class names for the consistency check.
    """
    require_any = action["locate"].get("require_any", [])
    minimum = int(action["locate"].get("require_class_letters_min", 2))
    matches: list[tuple[int, int, set[str]]] = []
    for start, end in _sentence_spans(span):
        text = span.text[start:end]
        if not any(token in text for token in require_any):
            continue
        letters = set(re.findall(r"([A-ZＡ-Ｚ])类", _compact(text)))
        if len(letters) < minimum and window_text and window_text.startswith(span.text):
            letters |= set(re.findall(r"([A-ZＡ-Ｚ])类", _compact(window_text[end:])))
        if len(letters) >= minimum:
            matches.append((start, end, letters))
    return matches


def _locate_class_definition(action: dict[str, Any], spans: Sequence[tuple[Any, Any]],
                             inspection: DocumentInspection, profile: dict[str, Any]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    profile_classes = set(profile.get("share_classes", []))
    span_texts = [pair[0].text for pair in spans]

    def window(index: int) -> str:
        # This paragraph plus at most two following in-scope paragraphs.
        return "\n".join(span_texts[index:index + 3])[:2500]

    for index, (span, _previous) in enumerate(spans):
        if span.zone == "unsupported_table":
            targets.append(_structure_failure(span, inspection))
            continue
        matches = _class_definition_sentences(span, action, window(index))
        if not matches:
            continue
        if len(matches) > 1:
            targets.append({**_base_target(span, inspection), "char_start": matches[0][0],
                            "char_end": matches[-1][1], "quote": span.text[matches[0][0]:matches[-1][1]],
                            "reason": "V2_TARGET_AMBIGUOUS"})
            continue
        start, end, letters = matches[0]
        start, end = _trim(span.text, start, end)
        # The append anchor is the last fee/class sentence of the definition so
        # that the new clause lands after the whole class definition block.
        anchor_start, anchor_end = start, end
        for sentence_start, sentence_end in _sentence_spans(span):
            if sentence_start < start:
                continue
            text = span.text[sentence_start:sentence_end]
            if re.search(r"[A-ZＡ-Ｚ]\s*类", text) and any(
                    token in text for token in ("申购费", "认购费", "销售服务费", "费用")):
                anchor_start, anchor_end = sentence_start, sentence_end
        anchor_start, anchor_end = _trim(span.text, anchor_start, anchor_end)
        anchor_text = span.text[anchor_start:anchor_end]
        target = {**_base_target(span, inspection), "char_start": anchor_start, "char_end": anchor_end,
                  "quote": anchor_text, "mapping_safe": _safe_range(span, anchor_start, anchor_end),
                  "class_letters": sorted(letters), "definition_start": start, "definition_end": end}
        parts = direct_sales_parts(span.text, profile)
        groups = profile.get("fee_groups", {})
        subscription_group = set(groups.get("subscription_group", []))
        service_group = set(groups.get("service_group", []))
        ungrouped = [name for name in sorted(profile_classes)
                     if (name in subscription_group) == (name in service_group)]
        if all(parts.values()):
            target.update(status="satisfied", reason="V2_ALREADY_SATISFIED")
        elif profile_classes and letters != profile_classes:
            target.update(status="failed", reason="V2_CLASS_DEFINITION_CONFLICT")
        elif ungrouped:
            # A class with both or neither default fee cannot be placed in the
            # direct-sales exemption clause without inventing policy.
            target.update(status="failed", reason="V2_HYBRID_CLASS_FEE_UNSUPPORTED",
                          ungrouped_classes=ungrouped)
        elif "直销机构" in span.text:
            target.update(status="failed", reason="V2_EXISTING_CLAUSE_UNSUPPORTED")
        elif not target["mapping_safe"]:
            target.update(status="failed", reason="UNSAFE_TEXT_MAPPING")
        else:
            if not any(segment.start <= anchor_start and anchor_end <= segment.end for segment in span.segments):
                target.update(status="failed", reason="UNSAFE_APPEND_ANCHOR")
            else:
                target.update(status="located", anchor={"start": anchor_start, "end": anchor_end,
                                                        "text": anchor_text,
                                                        "sha256": _sha_text(anchor_text)})
        targets.append(target)
    return targets


def _locate_model_assisted(action: dict[str, Any], spans: Sequence[tuple[Any, Any]],
                           inspection: DocumentInspection, gateway: Any) -> list[dict[str, Any]]:
    locate = action["locate"]
    prefilter = locate.get("prefilter") or {}
    minimum = int(locate.get("min_chars", 20))
    candidates = []
    for span, _previous in spans:
        if span.zone == "unsupported_table":
            candidates.append(span)
            continue
        if len(span.text) < minimum:
            continue
        if any(token not in span.text for token in prefilter.get("all", [])):
            continue
        if prefilter.get("any") and not any(token in span.text for token in prefilter["any"]):
            continue
        candidates.append(span)
    targets: list[dict[str, Any]] = []
    structured = [span for span in candidates if span.zone == "unsupported_table"]
    for span in structured:
        targets.append(_structure_failure(span, inspection))
    candidates = [span for span in candidates if span.zone != "unsupported_table"]
    limit = int(locate.get("max_locate_paragraphs", 3))
    if len(candidates) > limit:
        return [{"status": "failed", "reason": "V2_LOCATE_SCOPE_TOO_WIDE", "location": "",
                 "region": "", "char_start": 0, "char_end": 0, "quote": "", "mapping_safe": False,
                 "candidates": len(candidates)}] + targets
    found: list[dict[str, Any]] = []
    attempts = []
    for span in candidates:
        context = f"[CONTRACT_PARAGRAPH location={span.location} zone={span.zone}]\n{span.text}"
        if len(context) > int(getattr(gateway, "max_context_chars", 12000)):
            return [_failure("V3_MATCH_CONTEXT_LIMIT")] + targets
        result = gateway.locate_target(context, instruction=locate["instruction"],
                                       max_quotes=8, prompt_version=PROMPT_VERSIONS_V2["locate"])
        attempt = {"location": span.location, "quotes": []}
        attempts.append(attempt)
        for item in result.value.get("quotes", []):
            quote = str(item.get("quote") or "")
            if not quote:
                continue
            matches = _normalized_matches(span.text, quote)
            if len(matches) != 1:
                attempt["quotes"].append({"quote": quote[:160], "result": "V2_LOCATE_UNRESOLVED",
                                          "matches": len(matches)})
                targets.append(_failure("V2_LOCATE_UNRESOLVED", location=span.location))
                continue
            start, end = _trim(span.text, matches[0][0], matches[0][1])
            numbering = re.match(r"^[（(]?[一二三四五六七八九十\d]+[）)、．.]\s*", span.text[start:end])
            if numbering:
                start += numbering.end()
            literal = span.text[start:end]
            reason = None
            if not any(literal.startswith(prefix) for prefix in locate.get("start_prefixes", [])):
                reason = "V2_LOCATE_PREFIX_MISMATCH"
            elif any(token in literal for token in locate.get("forbid_contains", [])):
                reason = "V2_LOCATE_FORBIDDEN_CONTENT"
            elif literal and literal[-1] not in locate.get("require_end", ["。", "；"]):
                reason = "V2_LOCATE_END_MISMATCH"
            elif not (locate.get("min_chars") <= len(literal) <= locate.get("max_chars", 10**9)):
                reason = "V2_LOCATE_LENGTH"
            elif not _boundary_ok(span.text, start):
                reason = "V2_LOCATE_BOUNDARY"
            if reason:
                attempt["quotes"].append({"quote": quote[:160], "result": reason, "range": [start, end]})
                targets.append(_failure(reason, location=span.location))
                continue
            attempt["quotes"].append({"quote": quote[:160], "result": "resolved", "range": [start, end]})
            found.append({"span": span, "start": start, "end": end, "quote": literal,
                          "mapping_safe": _safe_range(span, start, end)})
    distinct = {(item["span"].location, item["start"], item["end"]) for item in found}
    base = {"attempts": attempts, "region": candidates[0].zone if candidates else "",
            "section_path": candidates[0].section_path if candidates else ""}
    if not found:
        return [{**base, "status": "failed", "reason": "V2_TARGET_NOT_LOCATED", "location": "",
                 "char_start": 0, "char_end": 0, "quote": "", "mapping_safe": False}] + targets
    resolved = []
    for item in found:
        identity = (item["span"].location, item["start"], item["end"])
        if identity not in distinct:
            continue
        distinct.remove(identity)
        target = {**_base_target(item["span"], inspection), **base, "char_start": item["start"],
                  "char_end": item["end"], "quote": item["quote"], "mapping_safe": item["mapping_safe"]}
        if target["mapping_safe"]:
            target["status"] = "located"
        else:
            target["reason"] = "UNSAFE_TEXT_MAPPING"
        resolved.append(target)
    return resolved + targets


_SENTENCE_MARKS = "。；！？"


def _delete_sentence_span(text: str, start: int, end: int) -> tuple[int, int]:
    """Delete targets must cover whole business sentences.

    A half-sentence quote would leave an orphaned fragment, and a quote that
    merges several sentences would swallow non-target content (e.g. payment
    instructions or fee formulas). Both fail closed.
    """
    if end < len(text) and text[end] in _SENTENCE_MARKS:
        end += 1
    left_ok = start == 0 or text[start - 1] in _SENTENCE_MARKS
    right_ok = end == len(text) or text[end - 1] in _SENTENCE_MARKS
    if not (left_ok and right_ok):
        raise V2Error("V3_DELETE_SENTENCE_BOUNDARY")
    body = text[start:end]
    if body and body[-1] in _SENTENCE_MARKS:
        body = body[:-1]
    if any(mark in body for mark in _SENTENCE_MARKS):
        raise V2Error("V3_DELETE_SENTENCE_MERGED")
    return start, end


def _locate_variants(action: dict[str, Any], spans: Sequence[tuple[Any, Any]],
                     inspection: DocumentInspection, profile: dict[str, Any], gateway: Any,
                     deterministic: list[dict[str, Any]]) -> list[dict[str, Any]]:
    policy = action["locate"].get("variant_fallback")
    if not policy or policy.get("range_mode") != "policy_core":
        return deterministic
    delete_sentence = (action["generation"]["mode"] == "delete"
                       and action["scope"] in {"sentence", "paragraph"})
    candidates = []
    for span, _ in spans:
        remaining = list(span.text)
        for target in deterministic:
            if target["location"] == span.location and target["status"] in {"located", "satisfied"}:
                remaining[target["char_start"]:target["char_end"]] = " " * (
                    target["char_end"] - target["char_start"])
        if _business_candidate(span, action, policy, "".join(remaining)):
            candidates.append(span)
    if len(candidates) > policy["max_paragraphs"]:
        return deterministic + [_failure("V3_VARIANT_CANDIDATE_LIMIT", candidates=len(candidates))]
    targets = list(deterministic)
    for span in candidates:
        if span.zone == "unsupported_table":
            targets.append(_structure_failure(span, inspection))
            continue
        if action["generation"]["mode"] == "template" and all(
                item["result"] == "satisfied" for item in run_code_checks(action, span.text, profile)):
            targets.append({**_base_target(span, inspection), "status": "satisfied",
                            "reason": "V2_ALREADY_SATISFIED", "quote": span.text,
                            "char_end": len(span.text)})
            continue
        try:
            context = _matching_context(action, profile, [span], gateway)
            existing = [t["quote"] for t in deterministic if t["location"] == span.location
                        and t["status"] in {"located", "satisfied"}]
            instruction = ("盘点本段中该动作全部应修改的旧表述。逐字引用最小完整业务核心，"
                           "保留核心以外文字；不要生成新文。依据必须说明对应指引。"
                           "不能确定删除或替换边界时不返回引文。不要把已符合指引的新文作为目标。"
                           "以下目标已经由代码盘点，不要再次输出，也不得与其重叠：" +
                           json.dumps(existing, ensure_ascii=False))
            response = gateway.locate_target(context, max_quotes=8,
                prompt_version=PROMPT_VERSIONS_V2["locate_variant"],
                instruction=instruction)
            items = response.value.get("quotes", [])
            resolved = []
            if not items:
                raise V2Error("V3_VARIANT_TARGET_UNRESOLVED")
            for item in items:
                quote = item.get("quote", "")
                if not quote or span.text.count(quote) != 1 or not item.get("basis"):
                    raise V2Error("V3_VARIANT_QUOTE_UNRESOLVED")
                normalized_quote = _compact(quote)
                if (any(token not in normalized_quote for token in policy["quote_all"])
                        or not any(token in normalized_quote for token in policy["quote_any"])):
                    raise V2Error("V3_VARIANT_BUSINESS_CORE_MISMATCH")
                if item.get("source", "contract") != "contract" or (
                        item.get("evidence_quote") and item["evidence_quote"] not in span.text):
                    raise V2Error("V3_VARIANT_EVIDENCE_MISMATCH")
                start = span.text.index(quote)
                end = start + len(quote)
                if delete_sentence:
                    start, end = _delete_sentence_span(span.text, start, end)
                    quote = span.text[start:end]
                if not _safe_range(span, start, end):
                    raise V2Error("UNSAFE_TEXT_MAPPING")
                if len(quote) > 4000:
                    raise V2Error("V2_LOCATE_LENGTH")
                resolved.append({**_base_target(span, inspection), "status": "located", "reason": None,
                    "char_start": start, "char_end": end, "quote": quote, "mapping_safe": True,
                    "locate_method": "model_variant", "basis": item["basis"],
                    "model_event": _event_summary(gateway)})
            targets = [t for t in targets if not (t["location"] == span.location
                       and t.get("reason") == "V2_SCOPE_TEXT_MISMATCH")]
            seen = set()
            seen.update((t["char_start"], t["char_end"]) for t in targets
                        if t["location"] == span.location and t["status"] in {"located", "satisfied"})
            for target in resolved:
                key = (target["char_start"], target["char_end"])
                if key not in seen:
                    targets.append(target)
                    seen.add(key)
        except V2Error as exc:
            targets.append(_failure(exc.code, location=span.location))
    return targets


def locate_targets(action: dict[str, Any], spans: Sequence[tuple[Any, Any]],
                   inspection: DocumentInspection, profile: dict[str, Any],
                   gateway: Any) -> list[dict[str, Any]]:
    mode = action["locate"]["mode"]
    if mode == "code_literal":
        deterministic = _locate_literal(action, spans, inspection, profile)
        if action["generation"]["mode"] == "template":
            template, error, _ = _instantiate_slots(action["generation"]["template_text"], action, profile)
            if not error:
                for span, _ in spans:
                    for start, end in _normalized_matches(span.text, template):
                        if not _safe_range(span, start, end):
                            continue
                        # Old substrings embedded in the complete new policy do
                        # not prove an outstanding old target.
                        deterministic = [t for t in deterministic if not (
                            t["location"] == span.location and start <= t["char_start"]
                            and t["char_end"] <= end)]
                        deterministic.append({**_base_target(span, inspection), "status": "satisfied",
                            "reason": "V2_ALREADY_SATISFIED", "char_start": start, "char_end": end,
                            "quote": span.text[start:end], "mapping_safe": True})
        return _locate_variants(action, spans, inspection, profile, gateway,
                                deterministic)
    if mode == "code_recognition":
        return _locate_recognition(action, spans, inspection)
    if mode == "class_definition":
        return _locate_class_definition(action, spans, inspection, profile)
    if mode == "model_assisted":
        return _locate_model_assisted(action, spans, inspection, gateway)
    raise V2Error("V2_LOCATE_MODE_INVALID")


# --------------------------------------------------------------------------- checks

def direct_sales_parts(text: str, profile: dict[str, Any]) -> dict[str, bool]:
    groups = profile.get("fee_groups", {})
    subscription = list(groups.get("subscription_group", []))
    service = list(groups.get("service_group", []))

    def named(sentence: str, classes: list[str]) -> list[str]:
        return [name for name in classes if re.search(re.escape(name) + r"类", sentence)]

    compact = _compact(text)
    sentences = [s for s in re.split(r"[。；;]", compact) if s]
    subscription_sentence = next((s for s in sentences if "直销机构" in s and "不收取" in s
                                  and re.search(r"(?:认购[、/和及]?)?申购费(?:用)?|认购费(?:用)?", s)
                                  and "销售服务费" not in s and "之外" not in s), None)
    service_sentence = next((s for s in sentences if "直销机构" in s and "不收取销售服务费" in s
                             and "之外" not in s), None)
    long_sentence = next((s for s in sentences if re.search(r"直销机构之外|其他销售机构", s)
                          and re.search(r"超过一年|一年以上|满一年", s)
                          and re.search(r"不再(?:继续)?收取销售服务费", s)), None)
    return {
        "subscription_group": bool(subscription and subscription_sentence
                                   and len(named(subscription_sentence, subscription)) == len(subscription)
                                   and not named(subscription_sentence, service)),
        "service_group": bool(service and service_sentence
                              and len(named(service_sentence, service)) == len(service)
                              and not named(service_sentence, subscription)),
        "long_holding": bool(service and long_sentence
                             and len(named(long_sentence, service)) == len(service)),
    }


def _check_requirement(check: dict[str, Any], text: str, profile: dict[str, Any],
                       action: dict[str, Any] | None = None) -> tuple[bool | None, dict[str, Any]]:
    kind = check.get("kind")
    compact = _compact(text)
    if kind == "delete_only":
        return text == "", {}
    if kind == "template_exact":
        template = (action or {}).get("generation", {}).get("template_text")
        if not template:
            return False, {"error": "TEMPLATE_MISSING"}
        instantiated, error, _ = _instantiate_slots(template, action or {}, profile)
        if error:
            return False, {"error": error}
        return compact == _compact(instantiated), {"expected_prefix": instantiated[:80]}
    if kind == "contains_all":
        missing = [value for value in check["values"] if _compact(value) not in compact]
        return (not missing), ({"missing": missing} if missing else {})
    if kind == "not_contains":
        found = [value for value in check["values"] if value in text]
        return (not found), ({"found": found} if found else {})
    if kind == "no_digits_and_no_conditions":
        digits = "".join(re.findall(r"\d", text))
        conditions = [value for value in check.get("conditions", []) if value in text]
        return (not digits and not conditions), {"digits": digits, "conditions": conditions}
    if kind == "boundary_scope":
        return True, {"boundary": check.get("boundary")}
    if kind == "classes_within_profile_and_no_digits":
        letters = {chr(ord(char) - 0xFEE0) if "\uff21" <= char <= "\uff3a" else char.upper()
                   for char in re.findall(r"[A-ZＡ-Ｚa-z]", compact)}
        allowed = set(profile.get("share_classes", []))
        unexpected = sorted(letter for letter in letters if letter not in allowed)
        digits = "".join(re.findall(r"\d", text))
        return (not unexpected and not digits), {"unexpected_letters": unexpected, "digits": digits}
    if kind == "direct_sales_clause":
        parts = direct_sales_parts(text, profile)
        return bool(parts.get(check.get("part"))), {"parts": parts}
    if kind == "semantic_review":
        return None, {"checker": "model"}
    raise V2Error("V2_CHECK_KIND_INVALID", {"kind": kind})


def run_code_checks(action: dict[str, Any], text: str, profile: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for requirement in action["requirements"]:
        if requirement["verification"] == "model":
            continue
        satisfied, detail = _check_requirement(requirement["check"], text, profile, action)
        results.append({"id": requirement["id"], "result": "satisfied" if satisfied else "unsatisfied",
                        "checker": "code", "detail": detail})
    return results


def _requirement_lines(action: dict[str, Any], only: set[str] | None = None) -> str:
    lines = []
    for requirement in action["requirements"]:
        if only is not None and requirement["id"] not in only:
            continue
        lines.append(f"- {requirement['id']} [{requirement['kind']}]: {requirement['text']}")
    return "\n".join(lines)


def _semantics_text(action: dict[str, Any]) -> str:
    semantics = action["semantics"]
    values = [f"subject={semantics['subject']}", f"action={semantics['action']}",
              f"condition={semantics['condition']}", f"fee_terms={semantics.get('fee_terms')}",
              f"ownership={semantics.get('ownership')}",
              "allowed_changes=" + "; ".join(semantics["allowed_changes"]),
              "must_preserve=" + "; ".join(semantics["must_preserve"]),
              "forbidden_additions=" + "; ".join(semantics["forbidden_additions"])]
    return "\n".join(values)


def _rule_text(action: dict[str, Any]) -> str:
    parts = [_requirement_lines(action), _semantics_text(action)]
    reference = action["generation"].get("reference_text")
    if reference:
        parts.append(reference)
    if action["generation"].get("template_text"):
        parts.append("[FIXED_POLICY_TEXT]\n" + action["generation"]["template_text"])
    return "\n".join(parts)


def profile_facts_text(profile: dict[str, Any]) -> str:
    groups = profile.get("fee_groups", {})
    lines = [f"share_classes={list(profile.get('share_classes', []))}",
             f"subscription_group={list(groups.get('subscription_group', []))}",
             f"service_group={list(groups.get('service_group', []))}",
             f"fee_groups_verified={bool(profile.get('fee_groups_verified'))}"]
    for item in profile.get("classes", []):
        quote = ""
        for evidence in item.get("evidence", []):
            if evidence.get("field") in ("subscription_fee", "sales_service_fee") and evidence.get("quote"):
                quote = evidence["quote"]
                break
        lines.append(f"class {item.get('name')}: subscription_fee={item.get('subscription_fee')} "
                     f"sales_service_fee={item.get('sales_service_fee')} evidence={quote}")
    return "\n".join(lines)[:2400]


def _bounded(parts: list[str], paragraphs: list[str], limit: int) -> str:
    head = "\n".join(parts)
    for index, paragraph in enumerate(paragraphs):
        piece = f"[{index}]\n{paragraph}"
        if len(head) + len(piece) <= limit:
            head = head + "\n" + piece
        else:
            break
    return head


# --------------------------------------------------------------------------- generation

def _build_generate_context(action: dict[str, Any], span: Any, target: dict[str, Any],
                            profile: dict[str, Any], limit: int) -> str:
    parts = [f"[CONTRACT_SOURCE location={span.location} zone={span.zone}]", target["quote"],
             f"[RULE_REQUIREMENTS action={action['action_id']}]", _requirement_lines(action),
             "[SEMANTICS]", _semantics_text(action)]
    reference = action["generation"].get("reference_text")
    if reference:
        parts += ["[REFERENCE_TEXT]", reference]
    if action.get("requires_profile"):
        parts += ["[PROFILE_FACTS]", profile_facts_text(profile)]
    paragraphs = [span.text[:2500]] if action["locate"]["mode"] == "class_definition" else []
    if action["operation"] == "append":
        left = span.text[target["char_end"] - 1:target["char_end"]] if target["char_end"] > 0 else ""
        parts += ["[JOIN_CONTEXT]",
                  f"新条款将插入在 CONTRACT_SOURCE 之后；该处前一个字符是“{left or '（段落开头）'}”。"
                  "如果它不是句号、分号等分隔标点，新条款必须以合适的标点开头，确保与上文自然衔接，"
                  "不要与上文文字直接相连。"]
    return _bounded(parts, paragraphs, limit)


def _build_verify_context(action: dict[str, Any], span: Any, target: dict[str, Any],
                          replacement: str, profile: dict[str, Any], limit: int) -> str:
    only = set(action["model_verification"])
    parts = [f"[CONTRACT_SOURCE location={span.location} zone={span.zone}]", target["quote"],
             "[GENERATED_TEXT]", replacement,
             f"[RULE_REQUIREMENTS action={action['action_id']}]", _requirement_lines(action, only=only)]
    if action.get("requires_profile"):
        parts += ["[PROFILE_FACTS]", profile_facts_text(profile)]
    return _bounded(parts, [], limit)


def _validate_facts(facts: list[dict[str, Any]], changes: list[dict[str, Any]], span: Any,
                    action: dict[str, Any], profile_facts: str | None) -> tuple[str | None, dict[str, Any]]:
    rule_text = _rule_text(action)
    ids = set()
    for fact in facts:
        fact_id, quote, role = fact.get("fact_id"), fact.get("quote") or "", fact.get("role")
        if not fact_id or fact_id in ids:
            return "V2_FACT_ID_INVALID", {"fact": fact}
        ids.add(fact_id)
        if not quote or not fact.get("statement"):
            return "V2_FACT_INCOMPLETE", {"fact": fact}
        if role == "contract":
            if not _quote_in(quote, span.text):
                return "V2_FACT_ROLE_MISMATCH", {"fact": fact}
        elif role == "rule":
            if not _quote_in(quote, rule_text):
                return "V2_FACT_ROLE_MISMATCH", {"fact": fact}
        elif role == "profile":
            if not profile_facts or not _quote_in(quote, profile_facts):
                return "V2_FACT_ROLE_MISMATCH", {"fact": fact}
        else:
            return "V2_FACT_ROLE_INVALID", {"fact": fact}
    requirement_ids = {item["id"] for item in action["requirements"]}
    for change in changes:
        if change.get("fact_id") not in ids:
            return "V2_CHANGE_FACT_UNKNOWN", {"change": change}
        if change.get("change") not in {"removed", "retained", "added"}:
            return "V2_CHANGE_KIND_INVALID", {"change": change}
        basis = change.get("basis_requirement")
        if basis and basis not in requirement_ids:
            return "V2_CHANGE_BASIS_UNKNOWN", {"change": change}
    return None, {}


def _validate_model_verify(value: dict[str, Any], action: dict[str, Any], replacement: str,
                           span: Any, target: dict[str, Any]) -> None:
    required = set(action["model_verification"])
    items = {item["requirement_id"]: item for item in value.get("items", [])}
    if set(items) != required:
        raise V2Error("V2_VERIFY_ITEMS_MISMATCH", {"items": value.get("items", [])})
    rule_text = _rule_text(action)
    unsatisfied = []
    for item in items.values():
        if item["result"] != "satisfied":
            unsatisfied.append(item)
            continue
        quote, source = item.get("evidence_quote") or "", item.get("evidence_source")
        container = {"contract": span.text, "generated": replacement, "rule": rule_text}.get(source)
        if not quote or container is None or not _quote_in(quote, container):
            raise V2Error("V2_VERIFY_QUOTE_MISMATCH", {"items": value.get("items", [])})
    if unsatisfied:
        raise V2Error("V2_VERIFY_NOT_SATISFIED", {"items": unsatisfied})


def _assemble_record(action: dict[str, Any], target: dict[str, Any], span: Any, replacement: str,
                     code_results: list[dict[str, Any]], profile: dict[str, Any], ruleset: RuleSetV2,
                     *, engine_build_value: str, content_source: str,
                     model_verify: dict[str, Any] | None, facts: list[dict[str, Any]],
                     changes: list[dict[str, Any]], normalization: list[str] | None = None,
                     slot_instantiation: dict[str, list[str]] | None = None) -> dict[str, Any]:
    requirements = []
    by_code = {item["id"]: item for item in code_results}
    by_model = {item["requirement_id"]: item for item in (model_verify or {}).get("items", [])}
    for requirement in action["requirements"]:
        code = by_code.get(requirement["id"])
        model = by_model.get(requirement["id"])
        if requirement["verification"] == "model":
            result = model["result"] if model else "unknown"
            checker = "model"
        elif requirement["verification"] == "code+model":
            if not code or code["result"] != "satisfied":
                result, checker = "unsatisfied", "code"
            elif not model:
                result, checker = "unknown", "code+model"
            else:
                result, checker = model["result"], "code+model"
        else:
            result, checker = (code or {}).get("result", "unknown"), "code"
        requirements.append({"id": requirement["id"], "kind": requirement["kind"],
                             "verification": requirement["verification"], "text": requirement["text"],
                             "result": result, "checker": checker,
                             "code_detail": (code or {}).get("detail", {})})
    profile_facts = profile_facts_text(profile) if action.get("requires_profile") else None
    record = {
        "record_version": RECORD_VERSION,
        "action_id": action["action_id"], "rule_id": action["rule_id"],
        "source_sha256": target["source_sha256"], "ruleset_version": ruleset.version,
        "ruleset_sha256": ruleset.sha256, "engine_build": engine_build_value,
        "prompt_versions": dict(PROMPT_VERSIONS_V2),
        "content_source": content_source,
        "location": target["location"], "zone": target["zone"], "section_path": target["section_path"],
        "char_start": target["char_start"], "char_end": target["char_end"],
        "source_quote": target["quote"], "source_quote_sha256": _sha_text(target["quote"]),
        "replacement_text": replacement, "replacement_sha256": _sha_text(replacement),
        "profile_facts_sha256": _sha_text(profile_facts) if profile_facts is not None else None,
        "boundary_policy": BOUNDARY_POLICY,
        "text_normalization": list(normalization or []),
        "slot_instantiation": dict(slot_instantiation or {}),
        "requirements": requirements,
        "facts": facts, "changes": changes,
        "model_verify": model_verify,
    }
    passed = all(item["result"] == "satisfied" for item in requirements)
    record["passed"] = passed
    record["record_sha256"] = canonical_sha(record)
    if not passed:
        raise V2Error("V2_CONTENT_VERIFICATION_FAILED",
                      {"requirements": [item["id"] for item in requirements if item["result"] != "satisfied"]})
    return record


def verify_target(action: dict[str, Any], target: dict[str, Any], span: Any, profile: dict[str, Any],
                  ruleset: RuleSetV2, gateway: Any, engine_build_value: str) -> dict[str, Any]:
    """Generate or select replacement text and run the independent content checks."""
    if action["generation"]["mode"] == "template":
        # The published rule literal is assembled by code; class slots come from
        # the current contract evidence and the result is checked by code.
        replacement, slot_error, slot_used = _instantiate_slots(
            action["generation"].get("template_text", ""), action, profile)
        if slot_error:
            raise V2Error(slot_error)
        normalization: list[str] = []
        if action["operation"] == "append" or action["scope"] in {"sentence", "paragraph"}:
            join_left = target["char_end"] if action["operation"] == "append" else target["char_start"]
            replacement, normalization = _join_repairs(span.text, join_left, target["char_end"], replacement)
        if not replacement or len(replacement) > int(action["generation"].get("max_chars", 4000)):
            raise V2Error("V2_REPLACEMENT_INVALID")
        code_results = run_code_checks(action, replacement, profile)
        if any(item["result"] != "satisfied" for item in code_results):
            failed = [item["id"] for item in code_results if item["result"] != "satisfied"]
            raise V2Error("V2_CONTENT_CHECK_FAILED", {"requirements": failed, "replacement": replacement[:600]})
        return {"replacement": replacement, "content_source": "rule_template", "code_results": code_results,
                "model_verify": None, "facts": [], "changes": [], "normalization": normalization,
                "slot_instantiation": slot_used}
    if action["generation"]["mode"] == "delete":
        code_results = run_code_checks(action, "", profile)
        return {"replacement": "", "content_source": "rule_delete", "code_results": code_results,
                "model_verify": None, "facts": [], "changes": []}
    profile_facts = profile_facts_text(profile) if action.get("requires_profile") else None
    context = _build_generate_context(action, span, target, profile, int(getattr(gateway, "max_context_chars", 12000)) - 200)
    result = gateway.generate_clause(context, instruction=action["generation"]["instruction"])
    value = result.value
    if not _old_text_equal(value["source_quote"], target["quote"]):
        raise V2Error("V2_SOURCE_QUOTE_MISMATCH")
    replacement = str(value["replacement_text"])
    if not replacement or "\n" in replacement or "\r" in replacement or "\ufffd" in replacement:
        raise V2Error("V2_REPLACEMENT_INVALID")
    if len(replacement) > int(action["generation"]["max_chars"]):
        raise V2Error("V2_REPLACEMENT_TOO_LONG")
    if any(ord(char) < 32 for char in replacement):
        raise V2Error("V2_REPLACEMENT_INVALID")
    if _old_text_equal(replacement, target["quote"]):
        raise V2Error("V2_REPLACEMENT_UNCHANGED")
    join_left = target["char_end"] if action["operation"] == "append" else target["char_start"]
    if action["operation"] == "append" or action["scope"] in {"sentence", "paragraph"}:
        replacement, normalization = _join_repairs(span.text, join_left, target["char_end"], replacement)
    fact_error, fact_details = _validate_facts(value.get("facts", []), value.get("changes", []), span, action, profile_facts)
    if fact_error:
        raise V2Error(fact_error, fact_details)
    code_results = run_code_checks(action, replacement, profile)
    if any(item["result"] != "satisfied" for item in code_results):
        failed = [item["id"] for item in code_results if item["result"] != "satisfied"]
        raise V2Error("V2_CONTENT_CHECK_FAILED", {"requirements": failed, "replacement": replacement[:600]})
    model_verify = None
    if action["model_verification"]:
        context = _build_verify_context(action, span, target, replacement, profile,
                                        int(getattr(gateway, "max_context_chars", 12000)) - 200)
        verified = gateway.verify_content(context, instruction=_VERIFY_INSTRUCTION)
        try:
            _validate_model_verify(verified.value, action, replacement, span, target)
        except V2Error as exc:
            exc.details.setdefault("replacement", replacement[:600])
            raise
        model_verify = {"task_type": "verify_content", "prompt_version": PROMPT_VERSIONS_V2["verify"],
                        **_event_summary(gateway), "items": verified.value["items"]}
    return {"replacement": replacement, "content_source": "model_generated", "code_results": code_results,
            "model_verify": model_verify, "facts": value.get("facts", []),
            "changes": value.get("changes", []), "normalization": normalization,
            "generation": {"task_type": "generate_clause", "prompt_version": PROMPT_VERSIONS_V2["generate"],
                           **_event_summary(gateway)}}


# --------------------------------------------------------------------------- plan

def build_content_check(inspection: DocumentInspection, profile: dict[str, Any], ruleset: RuleSetV2,
                        *, engine_build_value: str) -> Callable[[dict[str, Any]], None]:
    """Return the trusted closure re-verifying generated edits at publication time."""

    def check(edit: dict[str, Any]) -> None:
        record = edit.get("verification")
        if not isinstance(record, dict):
            raise DocxError("GENERATED_CONTENT_UNVERIFIED")
        digest = record.get("record_sha256")
        if digest != canonical_sha({key: value for key, value in record.items() if key != "record_sha256"}):
            raise DocxError("CONTENT_RECORD_HASH_MISMATCH")
        if record.get("record_version") != RECORD_VERSION or record.get("passed") is not True:
            raise DocxError("CONTENT_RECORD_NOT_PASSED")
        if record.get("source_sha256") != edit.get("source_sha256"):
            raise DocxError("CONTENT_RECORD_SOURCE_MISMATCH")
        if record.get("ruleset_version") != ruleset.version or record.get("ruleset_sha256") != ruleset.sha256:
            raise DocxError("CONTENT_RECORD_RULESET_MISMATCH")
        if record.get("engine_build") != engine_build_value or record.get("prompt_versions") != dict(PROMPT_VERSIONS_V2):
            raise DocxError("CONTENT_RECORD_CONTEXT_MISMATCH")
        location = str(edit.get("location", ""))
        paragraph = inspection.by_location(location)
        if record.get("location") != location or record.get("zone") != edit.get("zone"):
            raise DocxError("CONTENT_RECORD_RANGE_MISMATCH")
        start, end = edit.get("start"), edit.get("end")
        insertion = edit.get("operation") == "insert"
        if insertion:
            anchor = edit.get("anchor") or {}
            if not isinstance(anchor, dict):
                raise DocxError("CONTENT_RECORD_RANGE_MISMATCH")
            if not (record.get("char_start") == anchor.get("start") and record.get("char_end") == end and start == end):
                raise DocxError("CONTENT_RECORD_RANGE_MISMATCH")
            anchor_text = paragraph.text[int(anchor["start"]):int(anchor["end"])]
            if anchor_text != anchor.get("text") or _sha_text(anchor_text) != record.get("source_quote_sha256") \
                    or anchor_text != record.get("source_quote"):
                raise DocxError("CONTENT_RECORD_QUOTE_MISMATCH")
        else:
            if not isinstance(start, int) or not isinstance(end, int):
                raise DocxError("CONTENT_RECORD_RANGE_MISMATCH")
            old = paragraph.text[start:end]
            if old != edit.get("expected_old_text") or old != record.get("source_quote") \
                    or _sha_text(old) != record.get("source_quote_sha256"):
                raise DocxError("CONTENT_RECORD_QUOTE_MISMATCH")
            if not (record.get("char_start") == start and record.get("char_end") == end):
                raise DocxError("CONTENT_RECORD_RANGE_MISMATCH")
        replacement = str(edit.get("replacement", ""))
        if replacement != record.get("replacement_text") or _sha_text(replacement) != record.get("replacement_sha256"):
            raise DocxError("CONTENT_RECORD_REPLACEMENT_MISMATCH")
        action = ruleset.by_id(str(edit.get("action_id", "")))
        if edit.get("operation") == "insert" or action["scope"] in {"sentence", "paragraph"}:
            join_left = end if insertion else start
            join_right = end
            if not isinstance(join_left, int) or not isinstance(join_right, int):
                raise DocxError("CONTENT_RECORD_RANGE_MISMATCH")
            _repaired, join_notes = _join_repairs(paragraph.text, join_left, join_right, replacement)
            if join_notes:
                raise DocxError("CONTENT_JOIN_UNSAFE")
        action = ruleset.by_id(str(edit.get("action_id", "")))
        rule_text = _rule_text(action)
        profile_facts = profile_facts_text(profile) if record.get("profile_facts_sha256") is not None else None
        if profile_facts is not None and _sha_text(profile_facts) != record.get("profile_facts_sha256"):
            raise DocxError("CONTENT_PROFILE_FACTS_DRIFT")
        for fact in record.get("facts", []):
            container = {"contract": paragraph.text, "rule": rule_text, "profile": profile_facts}.get(fact.get("role"))
            if not fact.get("quote") or container is None or not _quote_in(fact["quote"], container):
                raise DocxError("CONTENT_FACT_ROLE_MISMATCH")
        rerun = {item["id"]: item for item in run_code_checks(action, replacement, profile)}
        for item in record.get("requirements", []):
            if item.get("checker") in ("code", "code+model"):
                fresh = rerun.get(item.get("id"))
                if fresh is None or fresh["result"] != "satisfied" or item.get("result") != fresh["result"]:
                    raise DocxError("CONTENT_CHECK_DRIFT")
            elif item.get("result") != "satisfied":
                raise DocxError("CONTENT_RECORD_NOT_PASSED")
        model_verify = record.get("model_verify")
        if action["model_verification"]:
            if not isinstance(model_verify, dict):
                raise DocxError("CONTENT_MODEL_VERIFY_MISSING")
            items = {item["requirement_id"]: item for item in model_verify.get("items", [])}
            if set(items) != set(action["model_verification"]):
                raise DocxError("CONTENT_MODEL_VERIFY_MISSING")
            for item in items.values():
                if item.get("result") != "satisfied" or not item.get("evidence_quote"):
                    raise DocxError("CONTENT_MODEL_VERIFY_FAILED")
                container = {"contract": paragraph.text, "generated": replacement, "rule": rule_text}.get(item.get("evidence_source"))
                if container is None or not _quote_in(item["evidence_quote"], container):
                    raise DocxError("CONTENT_MODEL_QUOTE_MISMATCH")
        elif model_verify:
            raise DocxError("CONTENT_MODEL_VERIFY_UNEXPECTED")
    return check


def plan_v2(inspection: DocumentInspection, profile: dict[str, Any], ruleset: RuleSetV2, gateway: Any,
            *, engine_build_value: str, actions: Sequence[str] | None = None) -> dict[str, Any]:
    """Locate, generate, verify and freeze v2 actions into executable edits.

    ``actions`` optionally restricts processing to a subset of action ids; the
    production pipeline passes every action in the package.
    """
    selected = [action for action in ruleset.actions
                if actions is None or action["action_id"] in actions]
    actions_out: list[dict[str, Any]] = []
    edits: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    for action in selected:
        applies, basis = applicability(action, profile)
        spans = list(iter_scope_spans(inspection, action))
        result: dict[str, Any] = {
            "rule_id": action["rule_id"], "action_id": action["action_id"],
            "description": action["description"], "applicability": applies,
            "applicability_basis": basis, "scope_verified": bool(spans),
            "auto_write": False, "release_gate": "closed", "status": "failed",
            "failure_reason": None, "targets": [], "generated_text": None,
            "scope_resolution": {"method": "code", "ranges": [
                {"location": s.location, "method": "code"} for s, _ in spans], "failures": []},
        }
        if applies == "false":
            result["status"] = "not_applicable"
            actions_out.append(result)
            continue
        if applies == "unknown":
            result["failure_reason"] = basis or "PROFILE_EVIDENCE_INCOMPLETE"
            actions_out.append(result)
            continue
        spans, scope_resolution = resolve_action_scope(inspection, action, profile, gateway)
        result["scope_resolution"] = scope_resolution
        result["scope_verified"] = bool(spans) and not scope_resolution["failures"]
        if scope_resolution["failures"]:
            result["failure_reason"] = scope_resolution["failures"][0]
            actions_out.append(result)
            continue
        if not spans:
            # An absent section is reported as not matched, never as satisfied.
            result["status"] = "not_matched"
            result["failure_reason"] = "TARGET_SCOPE_UNRESOLVED"
            actions_out.append(result)
            continue
        targets = locate_targets(action, spans, inspection, profile, gateway)
        for target in targets:
            result["targets"].append(target)
        verified: list[tuple[dict[str, Any], Any, dict[str, Any]]] = []
        cache: dict[str, dict[str, Any]] = {}
        for target in targets:
            if target["status"] == "satisfied":
                continue
            if target["status"] != "located":
                continue
            span = inspection.by_location(target["location"])
            key = _compact(target["quote"])
            try:
                if action["operation"] == "replace":
                    pre = run_code_checks(action, target["quote"], profile)
                    if all(item["result"] == "satisfied" for item in pre):
                        if action["model_verification"]:
                            context = _build_verify_context(action, span, target, span.text, profile,
                                int(getattr(gateway, "max_context_chars", 12000)) - 200)
                            response = gateway.verify_content(context, instruction=_VERIFY_INSTRUCTION,
                                prompt_version=PROMPT_VERSIONS_V2["verify"])
                            _validate_model_verify(response.value, action, span.text, span, target)
                            target["no_change_verification"] = {
                                "items": response.value["items"], "model_event": _event_summary(gateway)}
                        target.update(status="satisfied", reason="V2_ALREADY_SATISFIED")
                        continue
                outcome = cache.get(key)
                if outcome is not None and outcome.get("model_verify"):
                    # Reusing a generation across body/summary is allowed only when
                    # every contract-role verification quote still exists in this
                    # location; otherwise a fresh verification is required.
                    if not all(_quote_in(item["evidence_quote"], span.text) for item in outcome["model_verify"]["items"]
                               if item["evidence_source"] == "contract"):
                        outcome = None
                if outcome is None:
                    outcome = verify_target(action, target, span, profile, ruleset, gateway, engine_build_value)
                    cache[key] = outcome
                record = _assemble_record(action, target, span, outcome["replacement"], outcome["code_results"],
                                          profile, ruleset, engine_build_value=engine_build_value,
                                          content_source=outcome["content_source"],
                                          model_verify=outcome["model_verify"], facts=outcome["facts"],
                                          changes=outcome["changes"],
                                          normalization=outcome.get("normalization"),
                                          slot_instantiation=outcome.get("slot_instantiation"))
            except ModelError:
                raise
            except V2Error as exc:
                target.update(status="failed", reason=exc.code, details=exc.details)
                continue
            target.update(status="verified", reason=None,
                          verification={"record_sha256": record["record_sha256"]},
                          generated_text=outcome["replacement"])
            verified.append((target, span, {**outcome, "record": record}))
            records.append(record)
        # body/summary consistency for the whole action group
        replacements = {_compact(outcome["replacement"]) for _t, _s, outcome in verified}
        if len(replacements) > 1:
            for target, _span, _outcome in verified:
                target.update(status="failed", reason="V2_BODY_SUMMARY_CONFLICT",
                              verification=None, generated_text=None)
            records = records[:len(records) - len(verified)]
            verified = []
            result["failure_reason"] = "V2_BODY_SUMMARY_CONFLICT"
        # Per-action atomicity: one failed target must not leave a half-applied
        # modification across body/summary or sibling target locations.
        if verified and any(target["status"] == "failed" for target in targets):
            for target, _span, _outcome in verified:
                target.update(status="failed", reason="V2_ACTION_PARTIAL_REVERTED",
                              previously_verified=True, verification=None, generated_text=None)
            records = records[:len(records) - len(verified)]
            verified = []
            result["failure_reason"] = result["failure_reason"] or "V2_ACTION_PARTIAL_REVERTED"
        edit_count = 0
        for target, span, outcome in verified:
            edit = {
                "edit_id": f"{action['action_id']}:{len(edits)}",
                "action_id": action["action_id"], "source_sha256": inspection.source_sha256,
                "location": target["location"], "zone": target["zone"],
                "start": target["char_end"] if target.get("anchor") else target["char_start"],
                "end": target["char_end"], "expected_old_text": target["quote"],
                "expected_old_hash": _sha_text(target["quote"]),
                "replacement": outcome["replacement"], "verified": True,
                "fingerprint": span.fingerprint, "mapping_version": span.mapping_version,
                "content_source": "generated", "verification": outcome["record"],
                "record_sha256": outcome["record"]["record_sha256"],
            }
            if target.get("anchor"):
                edit.update(operation="insert", anchor=dict(target["anchor"]),
                            start=target["char_end"], end=target["char_end"], expected_old_text="",
                            expected_old_hash=_sha_text(""))
            edits.append(edit)
            edit_count += 1
        statuses = [target["status"] for target in targets]
        failed = [status for status in statuses if status == "failed"]
        if edit_count and not failed:
            result["status"] = "applied"
        elif edit_count and failed:
            result["status"] = "partial"
            result["failure_reason"] = result["failure_reason"] or "TARGET_PARTIALLY_VERIFIED"
        elif any(status == "satisfied" for status in statuses) and not failed:
            result["status"] = "satisfied_no_change"
        elif failed:
            result["status"] = "failed"
            result["failure_reason"] = result["failure_reason"] or targets[0].get("reason") or "TARGET_FAILED"
        else:
            result["status"] = "not_matched"
            result["failure_reason"] = "V3_TARGET_INVENTORY_UNRESOLVED"
        actions_out.append(result)
    # Every range was resolved against the same original document. Conflicts
    # invalidate whole actions, including their other body/summary edits.
    conflicts: set[str] = set()
    for i, left in enumerate(edits):
        for right in edits[i + 1:]:
            if left["location"] != right["location"]:
                continue
            lo, hi = left["start"], left["end"]
            rlo, rhi = right["start"], right["end"]
            overlaps = max(lo, rlo) <= min(hi, rhi)
            if lo == hi:
                overlaps = rlo <= lo <= rhi
            if rlo == rhi:
                overlaps = overlaps or lo <= rlo <= hi
            if overlaps:
                conflicts.update((left["action_id"], right["action_id"]))
    if conflicts:
        edits = [e for e in edits if e["action_id"] not in conflicts]
        records = [r for r in records if r["action_id"] not in conflicts]
        for result in actions_out:
            if result["action_id"] in conflicts:
                result.update(status="failed", failure_reason="V3_ACTION_RANGE_CONFLICT")
                for target in result["targets"]:
                    if target["status"] == "verified":
                        target.update(status="failed", reason="V3_ACTION_RANGE_CONFLICT",
                                      verification=None, generated_text=None)
    return {"actions": actions_out, "edits": edits, "records": records,
            "content_check": build_content_check(inspection, profile, ruleset, engine_build_value=engine_build_value)}
