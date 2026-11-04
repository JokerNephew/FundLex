"""Deterministic conversion of the frozen legacy built-in guide to ``guide_card_v1``.

The legacy ``guides/builtin_guide_v1.json`` (schema ``guide-rules-v1``) is
history: its identity and hash are never touched.  This module performs a
*mechanical* mapping of its groups/operations into the direct-through card
format so unconfigured owners still get a real executable default card pack
instead of being routed into the retired engine.  Nothing about the guide's
policy content is invented:

- replace/delete operations convert one-to-one, carrying ``old_text`` (plus
  ``old_text_variants`` as locators) and the guide-supplied ``new_text``;
- structured legacy conditions are not paraphrased; they are recorded
  verbatim as JSON in ``applicability.text`` and flagged ``ambiguous``;
- append operations without an anchor quote and noop operations cannot be
  expressed under the frozen ``guide_card_v1`` structural constraints, so
  they are honestly recorded under ``unparsed_segments`` (``card_dropped``).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

BUILTIN_CARD_V1_ID = "builtin-cards-v1"
# 用户口径（2026-11-03）：默认可执行内置 = 生产真实模型解析的 V2 卡包冻结种子。
# （guides/builtin_cards_v2.json，源自 guide_versions aa5edf83 的 rules_json。）
# FL-D1128（用户令 2026-11-04 ~11:3x）：兜底默认=用户 10:39:27 重传解析的存量指引 V2
# （6046eb6c，承接 FL-D1123/1124 的 bf4991 版；原件 sha ff95dfdb）。
BUILTIN_CARD_DEFAULT_ID = "6046eb6cb23b40518aaa0f9c49c5e1fc"
BUILTIN_CARD_PARSER_VERSION = "builtin-converted-1"
BUILTIN_CARD_SOURCE_PATH_HINT = "builtin_guide_v1.json (机械转换)"


def _condition_text(condition: Any) -> tuple[str, str]:
    """Mechanical applicability text; never invents semantics."""
    if not isinstance(condition, dict):
        return "", "ambiguous"
    kind = condition.get("kind")
    if kind in (None, "", "none"):
        return "", "clear"
    raw = json.dumps(condition, ensure_ascii=False, sort_keys=True)
    return f"（内置转换）结构化适用条件：{raw}", "ambiguous"


def _card(group: dict[str, Any], operation: dict[str, Any], index: int) -> dict[str, Any] | None:
    """Map one legacy operation to a card, or ``None`` when not expressible."""
    op = operation.get("op")
    old_text = str(operation.get("old_text") or "").strip()
    new_text = str(operation.get("new_text") or "").strip()
    requirement = str(group.get("requirement") or "").strip()
    paragraphs = [p for p in (group.get("source_paragraphs") or []) if isinstance(p, int)]
    section = str(group.get("section_hint") or "").strip()
    title = str(group.get("title") or operation.get("operation_id") or "").strip()
    applicability, clarity = _condition_text(operation.get("condition"))
    base: dict[str, Any] = {
        "card_id": str(operation.get("operation_id") or f"{group.get('rule_id')}:op{index}"),
        "title": title,
        "applicability": {"text": applicability, "clarity": clarity},
        "target": {
            "contract_sections": [section] if section else [],
            "locator_quotes": ([old_text] if old_text else [])
                              + [str(v) for v in (group.get("old_text_variants") or []) if str(v).strip()],
            "clarity": "clear" if old_text else "ambiguous",
        },
        "source": {"sections": [section] if section else [], "paragraphs": paragraphs},
        "notes": "",
    }
    if op == "replace" and old_text:
        base["action"] = {
            "type": "replace",
            "anchor_quote": old_text,
            "content_requirement": (requirement + "\n指引给定的新写法：" + new_text).strip(),
        }
        return base
    if op == "delete" and old_text:
        base["action"] = {
            "type": "delete",
            "anchor_quote": old_text,
            "content_requirement": requirement,
        }
        return base
    if op == "append" and (section or new_text):
        # 总负责人裁决（2026-11-02）：无锚点 append 一律以章节尾部追加形式表达，
        # 定位器锚到绑定章节最后一个可写段落后；不再 dropped。
        base["action"] = {
            "type": "insert_after",
            "anchor_quote": "",
            "content_requirement": (requirement + "\n指引给定的新写法：" + new_text).strip()
            or "追加指引给定的新条款",
        }
        base["notes"] = "section_append"
        base["target"]["clarity"] = "clear" if section else "ambiguous"
        return base
    return None


def build_builtin_card_document(legacy_document: dict[str, Any]) -> dict[str, Any]:
    """Convert the frozen legacy built-in document to a ``guide_card_v1`` pack.

    Raises ``ValueError("BUILTIN_CARD_CONVERSION_EMPTY")`` when no operation is
    expressible; callers must treat that as a hard failure (no silent fallback
    to the legacy engine).
    """
    if not isinstance(legacy_document, dict) or legacy_document.get("schema_version") != "guide-rules-v1":
        raise ValueError("BUILTIN_CARD_SOURCE_SCHEMA")
    cards: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    groups = legacy_document.get("groups")
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        operations = group.get("operations")
        for index, operation in enumerate(operations if isinstance(operations, list) else []):
            if not isinstance(operation, dict):
                continue
            card = _card(group, operation, index)
            if card is not None:
                cards.append(card)
                continue
            dropped.append({
                "kind": "card_dropped",
                "paragraphs": [p for p in (group.get("source_paragraphs") or []) if isinstance(p, int)],
                "reason": (f"legacy operation {operation.get('operation_id') or group.get('rule_id')} "
                           f"(op={operation.get('op')}) is not expressible in guide_card_v1 "
                           "(insert requires a non-empty anchor_quote; noop has no edit)"),
                "detail": "",
            })
    if not cards:
        raise ValueError("BUILTIN_CARD_CONVERSION_EMPTY")
    source_sha = str(legacy_document.get("source_sha256") or "")
    document: dict[str, Any] = {
        "schema_version": "guide_card_v1",
        "parser_version": BUILTIN_CARD_PARSER_VERSION,
        "source_sha256": source_sha,
        "source_path_hint": BUILTIN_CARD_SOURCE_PATH_HINT,
        "prompt_versions": {},
        "cards": cards,
        "unparsed_segments": dropped,
        "stats": {
            "paragraphs": 0,
            "cards": len(cards),
            "cards_by_action": _counts(cards),
            "unparsed_segments": len(dropped),
            "covered_paragraphs": 0,
            "segments_total": 0, "segments_failed": 0, "segments_succeeded": 0,
            "model_calls": 0,
            "converted_from": "builtin_guide_v1.json",
            "converted_from_document_sha256": str(legacy_document.get("document_sha256") or ""),
        },
        "built_at": "",
        "model": {},
        "legacy_condition_note": "structured legacy conditions are recorded verbatim in applicability.text",
    }
    return document


def _counts(cards: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for card in cards:
        action = (card.get("action") or {}).get("type")
        if isinstance(action, str) and action:
            counts[action] = counts.get(action, 0) + 1
    return counts
