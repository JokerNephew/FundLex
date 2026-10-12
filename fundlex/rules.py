"""Versioned, fail-closed rule catalogue and contract-evidence classification."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class RuleError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RuleSet:
    version: str
    sha256: str
    templates: dict[str, str]
    actions: tuple[dict[str, Any], ...]
    release_policy: dict[str, Any]

    @property
    def auto_write_enabled(self) -> bool:
        return any(action["auto_write"] for action in self.actions)


def load_ruleset(version: str) -> RuleSet:
    if not re.fullmatch(r"v[0-9]+", version):
        raise RuleError("RULESET_NOT_FOUND")
    path = Path(__file__).resolve().parent.parent / "rules" / f"rules_{version}.json"
    if not path.is_file():
        raise RuleError("RULESET_NOT_FOUND")
    raw = path.read_bytes()
    try:
        data = json.loads(raw)
        if data["version"] != version or data["schema_version"] != "1":
            raise ValueError("version")
        templates = {key: item["text"] for key, item in data["templates"].items()}
        if not templates or not all(isinstance(value, str) for value in templates.values()):
            raise ValueError("templates")
        actions = data["actions"]
        if not actions or len({item["action_id"] for item in actions}) != len(actions):
            raise ValueError("actions")
        required = {"rule_id", "action_id", "section_anchor", "subsection_anchor", "regions",
                    "scope", "old_triggers", "new_triggers", "operation", "template_id", "order",
                    "risk_class", "requires_profile", "on_unknown", "auto_write", "release_threshold", "approved"}
        for action in actions:
            if not required.issubset(action) or action["template_id"] not in templates:
                raise ValueError("action fields")
            if action["scope"] not in {"phrase", "sentence", "paragraph"}:
                raise ValueError("scope")
            if action["operation"] not in {"replace", "delete", "append"}:
                raise ValueError("operation")
            if not action["section_anchor"] or not action["subsection_anchor"]:
                raise ValueError("anchors")
            if not action["old_triggers"] or not set(action["regions"]).issubset({"body", "summary"}):
                raise ValueError("target")
            if action["auto_write"]:
                # A release is a separate, explicit offline act. Merely editing a
                # Boolean in a draft package cannot enable write operations.
                if not action["approved"] or not action["release_threshold"] or data["release_policy"]["status"] != "released":
                    raise ValueError("release gate")
                if not data["release_policy"].get("evaluation_report_id") or not data["release_policy"].get("approval_record"):
                    raise ValueError("approval evidence")
            if action["operation"] == "delete" and templates[action["template_id"]] != "":
                raise ValueError("deletion template")
        return RuleSet(version, hashlib.sha256(raw).hexdigest(), templates,
                       tuple(actions), data["release_policy"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuleError("RULESET_INVALID") from exc


def _category_value(paragraphs: tuple[Any, ...]) -> tuple[str, Any, int] | None:
    """Find a current-product category clause, never using the filename or title.

    A heading may end with 基金的类别 and its value may occupy the next paragraph.
    We use that adjacent clause only; a definitions-section ETF mention is not
    evidence that this contract itself is an ETF.
    """
    for index, span in enumerate(paragraphs):
        if span.zone != "body" or not span.segments:
            continue
        text = span.text.replace(" ", "")
        marker = "基金的类别" if "基金的类别" in text else ("基金的类型" if "基金的类型" in text else None)
        if not marker:
            continue
        after = text.split(marker, 1)[1].strip("：: \t")
        after = re.split(r"[三四五六七八九十]、(?:基金的|本基金的)", after, maxsplit=1)[0]
        if after and len(after) <= 100 and any(word in after for word in ("基金", "股票型", "债券型", "混合型")):
            return after, span, index
        for following in paragraphs[index + 1:index + 3]:
            if following.zone != "body" or not following.segments:
                break
            candidate = following.text.strip()
            if candidate and len(candidate) <= 100 and any(word in candidate for word in ("基金", "股票型", "债券型", "混合型")):
                return candidate, following, index
    return None


def classify_fund_type(inspection: Any) -> dict[str, Any]:
    """Classify only from a locatable current-product category clause."""
    paragraphs = getattr(inspection, "evidence_paragraphs", inspection.paragraphs)
    found = _category_value(tuple(paragraphs))
    if found is None:
        raise RuleError("FUND_TYPE_EVIDENCE_MISSING")
    quote, span, category_index = found
    compact = re.sub(r"\s+", "", quote)
    operation_quote = ""
    operation_span = None
    for index in range(category_index + 1, min(category_index + 9, len(paragraphs))):
        candidate_span = paragraphs[index]
        value = re.sub(r"\s+", "", candidate_span.text)
        if "基金的运作方式" not in value:
            continue
        after = value.split("基金的运作方式", 1)[1].strip("：:")
        if not after and index + 1 < len(paragraphs):
            candidate_span = paragraphs[index + 1]
            after = re.sub(r"\s+", "", candidate_span.text)
        operation_quote, operation_span = after[:100], candidate_span
        break
    types: set[str] = set()
    if "同业存单" in compact:
        types.add("interbank_cd")
    if "货币市场基金" in compact or re.search(r"货币(?:型|市场).*基金", compact):
        types.add("money_market")
    if ("交易型开放式" in compact or "交易型开放式" in operation_quote) and "联接" not in compact and "联接" not in operation_quote:
        types.add("etf")
    if "联接" in compact or ("交易型开放式" not in operation_quote and "交易型开放式" not in compact and any(x in compact for x in ("混合型", "债券型", "股票型", "指数型", "基金中基金", "FOF"))):
        types.add("ordinary")
    if len(types) != 1:
        raise RuleError("FUND_TYPE_EVIDENCE_AMBIGUOUS")
    kind = next(iter(types))
    start = span.text.find(quote)
    result = {"fund_type": kind, "evidence": {
        "field": "fund_type", "quote": quote, "part_uri": span.part_uri,
        "section_path": span.section_path, "paragraph_id": span.location,
        "char_start": start, "char_end": start + len(quote),
        "text_view": "accepted", "mapping_version": span.mapping_version,
        "source_kind": "deterministic", "verification": "verified"}}
    if operation_quote and operation_span is not None:
        result["operation_evidence"] = {"quote": operation_quote, "part_uri": operation_span.part_uri,
                                        "paragraph_id": operation_span.location,
                                        "section_path": operation_span.section_path,
                                        "verification": "verified"}
    return result


def evaluate_candidates(inspection: Any, ruleset: RuleSet) -> list[dict[str, Any]]:
    """Read-only candidate census; it never authorizes an edit."""
    results: list[dict[str, Any]] = []
    for action in ruleset.actions:
        found: list[dict[str, Any]] = []
        for span in inspection.paragraphs:
            if span.zone not in action["regions"] or not span.editable:
                continue
            if action["section_anchor"] not in span.section_path:
                continue
            for trigger in action["old_triggers"]:
                offset = 0
                while True:
                    at = span.text.find(trigger, offset)
                    if at < 0:
                        break
                    end = at + len(trigger)
                    safe = any(segment.start <= at and end <= segment.end for segment in span.segments)
                    found.append({"location": span.location, "region": span.zone,
                                  "section_path": span.section_path, "trigger": trigger,
                                  "char_start": at, "char_end": end,
                                  "quote": span.text[at:end], "mapping_safe": safe,
                                  "status": "failed", "reason": "RELEASE_GATE_CLOSED" if safe else "UNSAFE_TEXT_MAPPING"})
                    offset = end
        results.append({"rule_id": action["rule_id"], "action_id": action["action_id"],
                        "applicability": "unknown", "status": "failed" if found else "not_matched",
                        "auto_write": action["auto_write"], "candidates": found,
                        "release_gate": "closed"})
    return results
