"""Direct-through atomic guide rule cards (schema ``guide_card_v1``).

The guide DOCX is parsed chapter by chapter into self-contained, slot-free
rule cards.  There is no slot machinery, no fixed section/condition enum, no
verbatim-copy requirement, no independent verification round and no quality
gate: clarity labels are records only, never blockers.  A segment that the
model cannot read is recorded in ``unparsed_segments`` without failing the
rest of the guide; parsing fails honestly only when the source is unreadable,
the model is down for every segment, or zero executable cards remain.

Cross-line contract: ``docs/DIRECT_THROUGH_CONTRACT_20261102.md``.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .guide import GuideError, GuideParagraph, GuideSource, guide_document_sha256
from .model import ModelError

CARD_SCHEMA_VERSION = "guide_card_v1"
CARD_PARSER_VERSION = "guide-cards-1"
CARD_PARSE_PROMPT_VERSION = "guide_card_parse_v1"
CARD_GAP_PROMPT_VERSION = "guide_card_gap_v1"

CARD_ACTIONS = ("replace", "insert_before", "insert_after", "delete")
CLARITY_VALUES = ("clear", "ambiguous")

# ---------------------------------------------------------------------------
# Chapter / segment shaping
# ---------------------------------------------------------------------------

_HEADING_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^\s*第[一二三四五六七八九十百0-9]+[章节部分篇]",
        r"^\s*[一二三四五六七八九十]+[、.．]",
        r"^\s*[（(][一二三四五六七八九十]+[）)]",
        r"^\s*[0-9]+[、.．]",
        r"^\s*[（(][0-9]+[）)]",
        r"^\s*第[一二三四五六七八九十百0-9]+条",
    )
)
_REFERENCE_MARKERS = ("前述", "上述", "同前", "上述各", "前项", "上款", "前款")
_SENTENCE_END = "。；;！？"


def _heading_level(text: str) -> int | None:
    """Heading depth (0 = strongest) for a heading paragraph, else None."""
    stripped = text.strip()
    if not stripped or len(stripped) > 80:
        return None
    for level, pattern in enumerate(_HEADING_PATTERNS):
        if pattern.match(stripped):
            return level
    return None


def _is_heading(text: str) -> bool:
    return _heading_level(text) is not None


def _clip(text: str, limit: int = 120) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


@dataclass
class _Segment:
    """One model-call unit: ordered paragraph indices plus heading context."""

    paragraphs: list[int]
    heading_path: list[str] = field(default_factory=list)


def _blocks(source: GuideSource) -> list[tuple[list[str], list[int]]]:
    """Contiguous (heading_path, paragraph_indices) blocks in document order."""
    blocks: list[tuple[list[str], list[int]]] = []
    heading_stack: list[tuple[int, str]] = []
    current: list[int] = []
    for paragraph in source.paragraphs:
        stripped = paragraph.text.strip()
        if not stripped:
            continue
        level = _heading_level(stripped)
        if level is not None:
            if current:
                blocks.append(([text for _level, text in heading_stack], current))
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            heading_stack.append((level, stripped))
            current = [paragraph.index]
        else:
            current.append(paragraph.index)
    if current:
        blocks.append(([text for _level, text in heading_stack], current))
    return blocks


def _quoted_block(source: GuideSource, indices: list[int]) -> str:
    return "\n".join(
        f"[{source.paragraphs[index].index}] {source.paragraphs[index].text.strip()}"
        for index in indices
        if source.paragraphs[index].text.strip()
    )


def build_segments(source: GuideSource, *, char_budget: int) -> list[_Segment]:
    """Pack guide blocks into segments that fit the model context.

    Boundary preference: split at block (heading) boundaries first; an
    oversized block is split by paragraphs; an oversized single paragraph is
    split at sentence boundaries so progress is always possible.  Every
    segment carries the heading path and lookback of the paragraphs that
    precede it, so "同前述" style references keep their condition carriers.
    """
    segments: list[_Segment] = []
    pending_heading: list[str] = []
    pending: list[int] = []
    pending_chars = 0

    def flush() -> None:
        nonlocal pending, pending_chars
        if pending:
            segments.append(_Segment(pending, list(pending_heading)))
            pending = []
            pending_chars = 0

    for headings, indices in _blocks(source):
        text = _quoted_block(source, indices)
        units: list[list[int]] = [indices]
        if len(text) > char_budget:
            # Greedy paragraph packing inside the oversized block.
            units = []
            run: list[int] = []
            run_chars = 0
            for index in indices:
                line = _quoted_block(source, [index])
                if run and run_chars + len(line) > char_budget:
                    units.append(run)
                    run, run_chars = [], 0
                if len(line) > char_budget:
                    # Sentence-level fallback: same index repeated is fine for
                    # the model; split text would lose the index, so keep the
                    # whole paragraph but isolate it as its own unit.
                    if run:
                        units.append(run)
                        run, run_chars = [], 0
                    units.append([index])
                    continue
                run.append(index)
                run_chars += len(line)
            if run:
                units.append(run)
        for unit in units:
            unit_chars = len(_quoted_block(source, unit))
            starts_new_block = unit == indices and indices[0] in unit and headings
            if pending and (
                pending_chars + unit_chars > char_budget
                or (starts_new_block and not _same_heading_family(pending_heading, headings))
            ):
                flush()
            if not pending:
                pending_heading = list(headings)
            elif headings and headings != pending_heading and starts_new_block:
                pending_heading = list(headings)
            pending.extend(unit)
            pending_chars += unit_chars
    flush()
    return segments


def _same_heading_family(previous: list[str], current: list[str]) -> bool:
    """Same chapter family when one heading path prefixes the other."""
    if not previous or not current:
        return True
    return current == previous or current[:len(previous)] == previous or previous[:len(current)] == current


# ---------------------------------------------------------------------------
# Model contract
# ---------------------------------------------------------------------------

_CLARITY_SCHEMA = {"enum": list(CLARITY_VALUES)}
_CARD_SCHEMA = {
    "type": "object",
    "required": ["title", "applicability", "target", "action", "source"],
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "applicability": {
            "type": "object",
            "required": ["text", "clarity"],
            "properties": {"text": {"type": "string"}, "clarity": _CLARITY_SCHEMA},
        },
        "target": {
            "type": "object",
            "required": ["contract_sections", "locator_quotes", "clarity"],
            "properties": {
                "contract_sections": {"type": "array", "items": {"type": "string"}},
                "locator_quotes": {"type": "array", "items": {"type": "string"}},
                "clarity": _CLARITY_SCHEMA,
            },
        },
        "action": {
            "type": "object",
            "required": ["type", "anchor_quote", "content_requirement"],
            "properties": {
                "type": {"enum": list(CARD_ACTIONS)},
                "anchor_quote": {"type": "string"},
                "content_requirement": {"type": "string"},
            },
        },
        "source": {
            "type": "object",
            "required": ["paragraphs"],
            "properties": {
                "sections": {"type": "array", "items": {"type": "string"}},
                "paragraphs": {"type": "array", "minItems": 1, "items": {"type": "integer", "minimum": 0}},
            },
        },
        "notes": {"type": "string"},
    },
}
_SEGMENT_RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["cards"],
    "properties": {
        "cards": {"type": "array", "maxItems": 60, "items": _CARD_SCHEMA},
        "unparsed": {
            "type": "array",
            "maxItems": 20,
            "items": {
                "type": "object",
                "required": ["paragraphs", "reason"],
                "properties": {
                    "paragraphs": {"type": "array", "items": {"type": "integer", "minimum": 0}},
                    "reason": {"type": "string", "minLength": 1},
                },
            },
        },
    },
}

_PARSE_INSTRUCTION = (
    "你解析一份基金合同修改指引。GUIDE_TEXT 中方括号 [n] 是指引段落编号，是地址标记而非正文。"
    "HEADING_PATH 给出本片段所在的章节路径，PRIOR_CONTEXT 给出片段之前的相邻段落（只读，用于"
    "理解“同前述/上述”类回指；产出卡片时不得引用其中段落的编号，除非该段落也属于 SEGMENT_TEXT）。"
    "把 SEGMENT_TEXT 中的每一条可执行修改要求拆成**原子卡片**："
    "一、不同适用分支必须各自成卡——例如“原合同为条款1写法…；为条款2写法…”必须产出两张自含卡，"
    "不同份额类别（A类/C类/单一份额等）各自成卡；绝不把不同适用条件合并成一张卡，也**不得编造**"
    "指引中没有的类别、费率或政策要求。"
    "二、每张卡自含完整：applicability.text 写清楚的自然语言适用条件（无条件时空串）；"
    "target.contract_sections 写指引指定的合同章节名（自由文本）；target.locator_quotes 抄指引中"
    "足以在合同里定位的原文引句或旧条款写法；action.type 只能是 replace / insert_before / "
    "insert_after / delete——“替换/调整为/修订为”用 replace，“在…之前/之后增加”用 "
    "insert_before/insert_after 并把锚点引句写进 anchor_quote，“删除”用 delete；"
    "content_requirement 用自然语言写清要生成什么新内容（可含指引给定的新写法原文）。"
    "三、applicability.clarity 与 target.clarity 是记录标签：条件或定位含糊时如实标 ambiguous，"
    "不要硬猜，也不要因为含糊就丢卡；歧义点写进 notes。"
    "四、source.paragraphs 必须列出该卡实际用到的全部段落编号（含其引导句）。"
    "五、本片段中确实读不懂、不构成修改要求或无法覆盖的段落，列入 unparsed 并给出简短 reason。"
    "六、输出只能是符合 schema 的 JSON，不要复述指引，不要输出解释文字。"
)

_GAP_INSTRUCTION = (
    "你在做指引解析的遗漏补扫。GUIDE_GAP_TEXT 中是此前各章解析**没有覆盖**的指引段落"
    "（[n] 为段落编号）。按与首次解析完全相同的原子卡规则，为其中确实含可执行修改要求的段落补齐"
    "卡片（分支/类别仍须各自成卡）；确实只是过渡句、说明性文字或无可执行要求的段落列入 unparsed。"
    "只输出符合 schema 的 JSON。"
)


# ---------------------------------------------------------------------------
# Normalisation and structural validation (no quality gates)
# ---------------------------------------------------------------------------

def _clarity(value: Any) -> str:
    return value if value in CLARITY_VALUES else "ambiguous"


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def normalize_card(raw: Any, *, paragraph_count: int) -> tuple[dict[str, Any] | None, str | None]:
    """Return (card, None) or (None, structural-failure detail).

    Structural only: card shape and required fields.  Never a quality,
    verbatim, slot or certification check.
    """
    if not isinstance(raw, dict):
        return None, "card is not an object"
    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        return None, "title missing"
    applicability = raw.get("applicability") if isinstance(raw.get("applicability"), dict) else {}
    applicability_text = str(applicability.get("text") or "").strip()
    target = raw.get("target") if isinstance(raw.get("target"), dict) else {}
    contract_sections = _string_list(target.get("contract_sections"))
    locator_quotes = _string_list(target.get("locator_quotes"))
    action = raw.get("action") if isinstance(raw.get("action"), dict) else {}
    action_type = action.get("type")
    if action_type not in CARD_ACTIONS:
        return None, f"action.type {action_type!r} unsupported"
    anchor = str(action.get("anchor_quote") or "").strip()
    # 总负责人裁决（2026-11-02，待第1线回归上游）：section_append 记法允许
    # insert_after 空锚点——定位器锚到绑定章节最后一个可写段落后。
    section_append = (action_type == "insert_after" and not anchor
                      and "section_append" in str(raw.get("notes") or ""))
    content = str(action.get("content_requirement") or "").strip()
    if action_type in {"insert_before", "insert_after"} and not anchor and not section_append:
        return None, f"{action_type} requires anchor_quote"
    if action_type in {"replace", "insert_before", "insert_after"} and not content:
        return None, f"{action_type} requires content_requirement"
    # Semantic target is enough: a named contract section plus the natural
    # language requirement already suffices to locate work; never drop a card
    # for lacking a verbatim quote (FL-D1022 coordinator review 2026-11-02).
    if action_type in {"replace", "delete"} and not (anchor or locator_quotes or contract_sections):
        return None, f"{action_type} requires an anchor quote, locator quotes or contract sections"
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    paragraphs_raw = source.get("paragraphs")
    if not isinstance(paragraphs_raw, list) or not paragraphs_raw:
        return None, "source.paragraphs missing"
    paragraphs: list[int] = []
    for value in paragraphs_raw:
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value < paragraph_count:
            return None, f"source.paragraphs out of range: {value!r}"
        if value not in paragraphs:
            paragraphs.append(value)
    card = {
        "title": title.strip(),
        "applicability": {"text": applicability_text, "clarity": _clarity(applicability.get("clarity"))},
        "target": {"contract_sections": contract_sections, "locator_quotes": locator_quotes,
                   "clarity": _clarity(target.get("clarity"))},
        "action": {"type": action_type, "anchor_quote": anchor, "content_requirement": content},
        "source": {"sections": _string_list(source.get("sections")), "paragraphs": paragraphs},
        "notes": str(raw.get("notes") or "").strip(),
    }
    return card, None


def _dedup_key(card: dict[str, Any]) -> tuple:
    compact = lambda text: re.sub(r"\s+", "", text)
    return (
        card["action"]["type"],
        compact(card["action"]["anchor_quote"]),
        compact(card["action"]["content_requirement"]),
        compact(card["applicability"]["text"]),
        tuple(card["target"]["contract_sections"]),
    )


def _merge_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop exact duplicates only; never merge different applicability branches."""
    merged: list[dict[str, Any]] = []
    seen: dict[tuple, dict[str, Any]] = {}
    for card in cards:
        key = _dedup_key(card)
        if key in seen:
            kept = seen[key]
            for index in card["source"]["paragraphs"]:
                if index not in kept["source"]["paragraphs"]:
                    kept["source"]["paragraphs"].append(index)
            kept["source"]["paragraphs"].sort()
            continue
        seen[key] = card
        merged.append(card)
    return merged


# ---------------------------------------------------------------------------
# Model call plumbing
# ---------------------------------------------------------------------------

def _model_call(gateway: Any, *, task_type: str, bounded_context: str,
                response_schema: dict, instruction: str, prompt_version: str) -> Any:
    try:
        return gateway.call(task_type=task_type, bounded_context=bounded_context,
                            response_schema=response_schema, instruction=instruction,
                            prompt_version=prompt_version)
    except ModelError as exc:
        # Keep the GUIDE_MODEL_FAILED:<inner> convention so the job worker can
        # recognise releasable model stops (config/budget/transport).
        raise GuideError(f"GUIDE_MODEL_FAILED:{exc.code}",
                         {"model_error": exc.code, "metrics": getattr(exc, "metrics", {})}) from exc


def _is_model_stop(exc: GuideError) -> bool:
    if not str(exc.code or "").startswith("GUIDE_MODEL_FAILED:"):
        return False
    inner = str(exc.code).split(":", 1)[1]
    from .recall_pipeline import STOP_CODES
    return inner in STOP_CODES


def _context_limit(gateway: Any) -> int:
    return max(2000, int(getattr(gateway, "max_context_chars", 12000)))


def _doc_header(source: GuideSource) -> str:
    return "\n".join([
        "GUIDE_SOURCE",
        f"source_path_hint: {Path(source.path).name}",
        f"paragraph_count: {len(source.paragraphs)}",
    ])


def _segment_context(source: GuideSource, segment: _Segment, all_indices: list[int], limit: int) -> str:
    first = segment.paragraphs[0]
    lookback = [index for index in all_indices if index < first][-6:]
    marker_lines = []
    for index in lookback:
        text = source.paragraphs[index].text.strip()
        if text and any(marker in text for marker in _REFERENCE_MARKERS):
            marker_lines.append(f"[{index}] {text}")
    # Always include the paragraph immediately before the segment.
    if lookback:
        previous = f"[{lookback[-1]}] {source.paragraphs[lookback[-1]].text.strip()}"
        if previous not in marker_lines:
            marker_lines.append(previous)
    parts = [_doc_header(source), "", "HEADING_PATH", " / ".join(segment.heading_path) or "(文档开头)"]
    if len(marker_lines) <= 6:
        parts += ["", "PRIOR_CONTEXT", *marker_lines]
    parts += ["", "SEGMENT_TEXT", _quoted_block(source, segment.paragraphs)]
    context = "\n".join(parts)
    if len(context) > limit:
        raise GuideError("GUIDE_SEGMENT_CONTEXT_LIMIT", {"chars": len(context), "limit": limit})
    return context


def _collect_cards(value: Any, *, paragraph_count: int, failures: list[dict[str, Any]],
                   nonempty: set[int] | None = None) -> list[dict[str, Any]]:
    payload = value if isinstance(value, dict) else {}
    cards: list[dict[str, Any]] = []
    if not isinstance(payload.get("cards"), list):
        raise GuideError("GUIDE_CARD_RESPONSE_INVALID", {"reason": "response has no cards array"})
    for raw in payload["cards"]:
        card, detail = normalize_card(raw, paragraph_count=paragraph_count)
        if card is None:
            paragraphs = raw.get("source", {}).get("paragraphs") if isinstance(raw, dict) else None
            failures.append({"kind": "card_dropped",
                             "paragraphs": paragraphs if isinstance(paragraphs, list) else [],
                             "reason": "card failed structural validation",
                             "detail": str(detail)[:200]})
            continue
        cards.append(card)
    for unparsed in payload.get("unparsed") or []:
        if not isinstance(unparsed, dict):
            continue
        indices = [value for value in unparsed.get("paragraphs") or []
                   if isinstance(value, int) and not isinstance(value, bool)
                   and 0 <= value < paragraph_count
                   and (nonempty is None or value in nonempty)]
        reason = unparsed.get("reason")
        if indices and isinstance(reason, str) and reason.strip():
            failures.append({"kind": "uncovered", "paragraphs": indices,
                             "reason": _clip(reason.strip(), 200), "detail": ""})
    return cards


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def build_guide_card_document(source: GuideSource, gateway: Any, *,
                              segment_retries: int = 2) -> dict[str, Any]:
    """Parse a guide into the guide_card_v1 card package.

    Fails honestly (``GuideError``) only when the model is unusable for every
    segment (``GUIDE_CARD_MODEL_FAILED``, or a stop-code model error which is
    re-raised as ``GUIDE_MODEL_FAILED:*`` for the job worker lease release)
    or zero executable cards survive (``GUIDE_NO_EXECUTABLE_CARDS``).
    Partial segment losses are recorded in ``unparsed_segments``.
    """
    if segment_retries < 1:
        raise GuideError("GUIDE_CARD_ARGUMENT_INVALID", {"segment_retries": segment_retries})
    paragraph_count = len(source.paragraphs)
    all_indices = [paragraph.index for paragraph in source.paragraphs if paragraph.text.strip()]
    nonempty = set(all_indices)
    budget = _context_limit(gateway) - 2500  # instruction + envelope headroom
    segments = build_segments(source, char_budget=budget)
    failures: list[dict[str, Any]] = []
    cards: list[dict[str, Any]] = []
    segments_failed = segments_succeeded = 0
    model_failures = 0

    for segment in segments:
        segment_cards: list[dict[str, Any]] | None = None
        last_error: GuideError | None = None
        for _attempt in range(segment_retries):
            try:
                context = _segment_context(source, segment, all_indices, _context_limit(gateway))
                result = _model_call(gateway, task_type="guide_parse", bounded_context=context,
                                     response_schema=_SEGMENT_RESPONSE_SCHEMA,
                                     instruction=_PARSE_INSTRUCTION,
                                     prompt_version=CARD_PARSE_PROMPT_VERSION)
                segment_cards = _collect_cards(result.value, paragraph_count=paragraph_count,
                                               failures=failures, nonempty=nonempty)
                last_error = None
                break
            except GuideError as exc:
                if str(exc.code).startswith("GUIDE_MODEL_FAILED:") and _is_model_stop(exc):
                    raise  # releasable model stop: lease must be returned, not burned
                last_error = exc
        if segment_cards is None:
            segments_failed += 1
            if last_error is not None and str(last_error.code).startswith("GUIDE_MODEL_FAILED:"):
                model_failures += 1
            failures.append({"kind": "segment_failed", "paragraphs": list(segment.paragraphs),
                             "reason": "model transport failed after retries",
                             "detail": _clip(str(getattr(last_error, "code", "") or ""), 120)})
            continue
        segments_succeeded += 1
        cards.extend(segment_cards)

    if segments and segments_succeeded == 0 and model_failures == len(segments):
        raise GuideError("GUIDE_CARD_MODEL_FAILED", {"segments": len(segments)})

    # Gap sweep: one bounded pass over non-empty paragraphs no card covered.
    covered = {index for card in cards for index in card["source"]["paragraphs"]}
    dropped = {index for failure in failures if failure["kind"] in {"card_dropped", "uncovered", "segment_failed"}
               for index in failure["paragraphs"]}
    gap_indices = [index for index in all_indices
                   if index not in covered and index not in dropped
                   and not _is_heading(source.paragraphs[index].text)]
    if gap_indices:
        gap_text = _quoted_block(source, gap_indices)
        if len(gap_text) <= budget:
            try:
                context = "\n".join([_doc_header(source), "", "GUIDE_GAP_TEXT", gap_text])
                result = _model_call(gateway, task_type="guide_parse", bounded_context=context,
                                     response_schema=_SEGMENT_RESPONSE_SCHEMA,
                                     instruction=_GAP_INSTRUCTION,
                                     prompt_version=CARD_GAP_PROMPT_VERSION)
                before_drop = len(failures)
                gap_cards = _collect_cards(result.value, paragraph_count=paragraph_count,
                                           failures=failures, nonempty=nonempty)
                # Sweep-reported "unparsed" notes are real gap resolutions.
                cards.extend(gap_cards)
                del before_drop  # clarity: sweep failures already recorded above
            except GuideError as exc:
                if _is_model_stop(exc):
                    raise
                failures.append({"kind": "segment_failed", "paragraphs": list(gap_indices),
                                 "reason": "gap sweep failed", "detail": _clip(str(exc.code), 120)})
        else:
            failures.append({"kind": "segment_failed", "paragraphs": list(gap_indices),
                             "reason": "gap sweep context too large", "detail": ""})

    cards = _merge_cards(cards)
    cards.sort(key=lambda card: (min(card["source"]["paragraphs"]), card["action"]["type"]))
    for position, card in enumerate(cards):
        card["card_id"] = f"C{position + 1:04d}"

    if not cards:
        raise GuideError("GUIDE_NO_EXECUTABLE_CARDS",
                         {"segments_total": len(segments), "segments_failed": segments_failed,
                          "paragraphs": paragraph_count})

    covered_final = {index for card in cards for index in card["source"]["paragraphs"]}
    # Record still-uncovered, non-heading paragraphs as uncovered (ops ledger).
    recorded = {index for failure in failures for index in failure["paragraphs"]}
    residual = [index for index in all_indices
                if index not in covered_final and index not in recorded
                and not _is_heading(source.paragraphs[index].text)]
    if residual:
        failures.append({"kind": "uncovered", "paragraphs": residual,
                         "reason": "no card covered these paragraphs", "detail": ""})

    actions = {kind: 0 for kind in CARD_ACTIONS}
    for card in cards:
        actions[card["action"]["type"]] += 1
    stats = {
        "paragraphs": paragraph_count,
        "cards": len(cards),
        "cards_by_action": actions,
        "unparsed_segments": len(failures),
        "covered_paragraphs": len(covered_final),
        "segments_total": len(segments),
        "segments_failed": segments_failed,
        "segments_succeeded": segments_succeeded,
        "model_calls": getattr(gateway, "calls", None),
    }
    document = {
        "schema_version": CARD_SCHEMA_VERSION,
        "parser_version": CARD_PARSER_VERSION,
        "source_sha256": source.source_sha256,
        "source_path_hint": Path(source.path).name,
        "prompt_versions": {"guide_card_parse": CARD_PARSE_PROMPT_VERSION,
                            "guide_card_gap": CARD_GAP_PROMPT_VERSION},
        "cards": cards,
        "unparsed_segments": failures,
        "stats": stats,
        # guide_store.finish_guide_job stores document["validation"] as the
        # parse issues shown with the version.  This is a ledger, not a gate.
        "validation": {"unparsed_segments": failures, "stats": stats},
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "model": _model_summary(gateway),
    }
    return document


def _model_summary(gateway: Any) -> dict[str, Any]:
    """Observation-only ledger snapshot (same shape class as guide._model_summary)."""
    summary: dict[str, Any] = {"configured_model": getattr(gateway, "model", None),
                               "logical_calls": getattr(gateway, "calls", None)}
    events = getattr(gateway, "events", [])
    if isinstance(events, list):
        summary["events"] = [{key: event.get(key) for key in (
            "task_type", "prompt_version", "configured_model", "actual_model", "request_id",
            "latency_ms", "prompt_tokens", "completion_tokens", "total_tokens",
            "estimated_cost_usd", "http_status", "error_code", "reused_checkpoint")}
            for event in events if isinstance(event, dict)][-50:]
    metrics = getattr(gateway, "metrics", None)
    if callable(metrics):
        try:
            snapshot = metrics()
        except Exception:
            snapshot = None
        if isinstance(snapshot, dict):
            summary["metrics"] = {key: snapshot.get(key) for key in (
                "logical_calls", "http_attempts", "prompt_tokens", "completion_tokens",
                "total_tokens", "latency_ms", "rate_limit_count", "error_count",
                "estimated_cost_usd")}
    return summary


def validate_card_document(doc: dict[str, Any]) -> dict[str, Any]:
    """Structural contract check for a guide_card_v1 package (replaces the role
    of ``validate_runtime_guide`` for card documents; not a certification)."""
    failures: list[str] = []
    if not isinstance(doc, dict):
        raise GuideError("GUIDE_CARD_DOCUMENT_INVALID", {"failures": ["document_not_object"]})
    if doc.get("schema_version") != CARD_SCHEMA_VERSION:
        failures.append("schema_unsupported:" + str(doc.get("schema_version")))
    cards = doc.get("cards")
    if not isinstance(cards, list) or not cards:
        failures.append("cards_missing")
        cards = []
    paragraph_count = doc.get("stats", {}).get("paragraphs")
    upper = paragraph_count if isinstance(paragraph_count, int) and paragraph_count > 0 else 10 ** 9
    seen_ids: set[str] = set()
    for card in cards:
        normalized, detail = normalize_card(card, paragraph_count=upper)
        if normalized is None:
            failures.append("card_invalid:" + str(detail))
            continue
        card_id = card.get("card_id")
        if not isinstance(card_id, str) or not card_id.strip() or card_id in seen_ids:
            failures.append("card_id_invalid_or_duplicate:" + str(card_id))
        seen_ids.add(str(card_id))
    if failures:
        raise GuideError("GUIDE_CARD_DOCUMENT_INVALID", {"failures": sorted(set(failures))})
    actions: dict[str, int] = {}
    for card in cards:
        actions[card["action"]["type"]] = actions.get(card["action"]["type"], 0) + 1
    return {"state": "OK", "schema_version": CARD_SCHEMA_VERSION,
            "card_count": len(cards), "cards_by_action": actions,
            "source_sha256": str(doc.get("source_sha256") or ""),
            "document_sha256": guide_document_sha256(doc)}


__all__ = [
    "CARD_SCHEMA_VERSION", "CARD_PARSER_VERSION", "CARD_PARSE_PROMPT_VERSION",
    "CARD_GAP_PROMPT_VERSION", "CARD_ACTIONS", "build_segments",
    "build_guide_card_document", "normalize_card", "validate_card_document",
]
