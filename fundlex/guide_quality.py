"""Presentation-quality checks for parsed guides (FL-D898, standard S1-S5).

The structural gates (deterministic validation, independent verification,
executability canary) answer "can this parse run at all".  This module answers
"does the parse read as good rules to the owner": human titles, readable
requirements, executable-looking operation texts, usable section hints and the
hard rule that internal identifiers never leak into owner-visible fields
(FL-D883/S5).

Everything here is deterministic and advisory — it never changes the
certified/enable gate semantics.  The results are surfaced on the version's
``issues_detail.quality_checklist`` so the owner can see presentation problems
even on a parsing run that technically passed.
"""
from __future__ import annotations

import re
from typing import Any

from .guide import (CONDITION_KIND_LABELS, FINDING_KIND_LABELS, GuideSource,
                    OPERATIONS)

CHECKLIST_VERSION = "guide-quality-1"

# Internal vocabulary that must never reach an owner-visible string (S5).
# ``detail_tech`` is exempt by design — it is model/log-facing only.
INTERNAL_TOKENS: tuple[str, ...] = (
    "class_count", "has_service_fee", "is_floating_fee",
    "wrong_text", "wrong_condition", "wrong_operation", "missing_group",
    "missing_reference", "ambiguous_branch",
    "operations[", "rule_id", "new_text", "old_text", "slot_token",
    "section_hint", "class_substitution", "source_paragraphs",
    "group_kind", "one_of_group", "coverage_gap", "detail_tech",
    "parser_version", "schema_version",
)

# Placeholder shapes that mean the operation text is not really executable.
_PLACEHOLDER_PATTERNS = tuple(
    re.compile(pattern) for pattern in (
        r"待补", r"TODO", r"TBD", r"____+", r"×{2,}", r"[xX]{3,}",
        r"此处省略", r"\.\.\.\.\.",
    )
)

_MIN_REQUIREMENT_CHARS = 8

# Business domains the runtime scope locator knows (mirrors the parse
# instruction list).  Values outside the set are advisories, not failures —
# a guide may legitimately target a new domain (scope falls back at runtime).
KNOWN_SECTION_DOMAINS: tuple[str, ...] = (
    "释义", "基金的基本情况", "基金份额的申购与赎回",
    "基金费用与税收", "基金的收益与分配", "基金财产的清算",
)


def _contains_internal_token(value: str) -> str | None:
    lowered = value.lower()
    for token in INTERNAL_TOKENS:
        if token.lower() in lowered:
            return token
    return None


def _placeholder_hit(value: str) -> str | None:
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.search(value):
            return pattern.pattern
    return None


def presentation_report(document: dict[str, Any]) -> dict[str, Any]:
    """Check owner-facing rule strings of one parsed document.

    Returns ``{"pass": bool, "problems": [...]}`` where each problem names the
    rule, the field and a Chinese explanation.  ``pass`` is False as soon as
    any *error-level* problem exists (internal-token leak, placeholder text,
    missing/short requirement or title); section-domain mismatches and weak
    noop explanations are warnings and never flip ``pass``.
    """
    problems: list[dict[str, Any]] = []
    groups = document.get("groups") if isinstance(document, dict) else None
    if not isinstance(groups, list):
        return {"pass": False,
                "problems": [{"rule_id": "", "field": "groups", "level": "error",
                              "detail": "解析结果里没有规则列表，无法检查表达质量"}]}
    for group in groups:
        if not isinstance(group, dict):
            continue
        rule_id = str(group.get("rule_id") or "")

        def flag(field: str, detail: str, level: str = "error") -> None:
            problems.append({"rule_id": rule_id, "field": field,
                             "level": level, "detail": detail})

        # S1: human title
        title = group.get("title")
        if not isinstance(title, str) or not title.strip():
            flag("title", "规则缺少人话标题")
        else:
            token = _contains_internal_token(title)
            if token:
                flag("title", f"标题里出现内部标识符「{token}」，不应展示给用户")
            elif re.fullmatch(r"[GＧ]?\d{1,3}", title.strip()):
                flag("title", "标题只是编号，没有概括这则要求在改什么")

        # S2: readable requirement
        requirement = group.get("requirement")
        if not isinstance(requirement, str) or not requirement.strip():
            flag("requirement", "规则缺少可读的修改要求表述")
        else:
            token = _contains_internal_token(requirement)
            if token:
                flag("requirement", f"修改要求里出现内部标识符「{token}」，不应展示给用户")
            if len(requirement.strip()) < _MIN_REQUIREMENT_CHARS:
                flag("requirement",
                     f"修改要求只有 {len(requirement.strip())} 个字，不足以说明要改什么")

        # S5 on free-text notes
        notes = group.get("notes")
        if isinstance(notes, str) and notes.strip():
            token = _contains_internal_token(notes)
            if token:
                flag("notes", f"备注里出现内部标识符「{token}」，不应展示给用户")

        # S4: usable section hint (advisory level)
        hint = group.get("section_hint")
        if isinstance(hint, str) and hint.strip():
            if not any(domain in hint for domain in KNOWN_SECTION_DOMAINS):
                flag("section_hint",
                     f"章节定位「{hint}」不在已知业务域内，运行时可能定位不到对应章节",
                     level="warning")

        # S3: operation texts — placeholders and noop explainability
        operations = group.get("operations")
        if isinstance(operations, list):
            for op_index, operation in enumerate(operations):
                if not isinstance(operation, dict):
                    continue
                at = f"operations[{op_index}]"
                kind = operation.get("op")
                if kind not in OPERATIONS:
                    continue
                fields = {"append": ("new_text",), "replace": ("old_text", "new_text"),
                          "delete": ("old_text",), "noop": ("text",)}[kind]
                for field in fields:
                    value = operation.get(field)
                    if isinstance(value, str) and value.strip():
                        hit = _placeholder_hit(value)
                        if hit:
                            flag(field,
                                 f"该规则第 {op_index + 1} 个操作的文本像占位符"
                                 f"（命中「{hit}」），不是可执行的条款内容")
                if kind == "noop":
                    explains = bool((isinstance(notes, str) and notes.strip())
                                    or (group.get("references")))
                    if not explains:
                        flag(at, "「不改」操作没有在备注或依据引用里说明为什么不改",
                             level="warning")

    errors = [problem for problem in problems if problem["level"] == "error"]
    return {"pass": not errors, "problems": problems,
            "stats": {"rules": len(groups), "errors": len(errors),
                      "warnings": len(problems) - len(errors)}}


def check_parse_quality(source: GuideSource | None,
                        document: dict[str, Any] | None,
                        validation: dict[str, Any] | None = None,
                        canary: dict[str, Any] | None = None,
                        error_code: str | None = None) -> dict[str, Any]:
    """Version-level quality checklist (advisory; FL-D898 清单五项).

    Combines the existing gate signals (structure/verification/executability —
    reported here, decided elsewhere) with the new presentation and code-map
    checks.  Missing inputs are reported as ``unknown`` so a failed parse can
    still produce a partial checklist.
    """
    validation = validation if isinstance(validation, dict) else {}
    verification = validation.get("verification")
    verification = verification if isinstance(verification, dict) else {}

    structure_ok = not validation.get("errors") and not validation.get("coverage_gaps")
    structure_detail = ("确定性校验：无错误、全覆盖" if structure_ok
                        else "确定性校验存在错误或未覆盖段落")
    if error_code and document is None:
        # The attempt died before producing a parse: structure must not
        # present as clean just because there is no validation payload.
        from .guide_report import explain_code
        structure_ok = False
        structure_detail = f"解析未完成：{explain_code(error_code)['zh']}"
    verification_ok = (not verification.get("findings")
                       and not verification.get("invalid_findings"))
    if canary is None:
        canary_state: str | bool = "unknown"
    else:
        canary_state = bool(canary.get("passed"))

    presentation = presentation_report(document or {})

    # S5/S9: every issue code that surfaced must have a Chinese explanation.
    from .guide_report import CODE_EXPLANATIONS
    codes = set()
    for issue in (validation.get("errors") or []) + (validation.get("warnings") or []):
        if isinstance(issue, dict) and issue.get("code"):
            codes.add(str(issue["code"]))
    if canary:
        for finding in (canary.get("fatal") or []) + (canary.get("advisory") or []):
            if isinstance(finding, dict) and finding.get("code"):
                codes.add(str(finding["code"]))
    missing_explanations = sorted(code for code in codes
                                  if code not in CODE_EXPLANATIONS)

    items = {
        "structure": {"pass": structure_ok,
                      "detail": structure_detail,
                      "gate": "blocking"},
        "verification": {"pass": verification_ok,
                         "detail": "独立核验：无未处置发现" if verification_ok
                                   else "独立核验仍有未处置发现",
                         "gate": "blocking"},
        "executability": {"pass": canary_state,
                          "detail": ("可执行性金丝雀通过" if canary_state is True
                                     else "可执行性金丝雀存在致命问题" if canary_state is False
                                     else "可执行性金丝雀未运行（解析未走完）"),
                          "gate": "blocking"},
        "presentation": ({"pass": "unknown",
                          "detail": "解析未产出规则，未进行表达质量检查",
                          "gate": "advisory", "problems": []}
                         if document is None else
                         {"pass": presentation["pass"],
                          "detail": ("表达质量检查通过（标题/要求可读、无占位符、无内部标识符）"
                                     if presentation["pass"]
                                     else f"表达质量存在 {presentation['stats']['errors']} 项问题"),
                          "gate": "advisory",
                          "problems": presentation["problems"]}),
        "code_map": {"pass": not missing_explanations,
                     "detail": ("全部问题码均有中文解释" if not missing_explanations
                                else f"缺少中文解释的问题码：{'、'.join(missing_explanations)}"),
                     "gate": "advisory",
                     "missing": missing_explanations},
    }
    blocking = [name for name, item in items.items()
                if item["gate"] == "blocking" and item["pass"] is not True]
    advisory = [name for name, item in items.items()
                if item["gate"] == "advisory" and item["pass"] is not True]
    if blocking:
        verdict = "gated"
    elif advisory:
        verdict = "pass_with_advisories"
    else:
        verdict = "pass"
    return {"version": CHECKLIST_VERSION, "verdict": verdict,
            "blocking_failures": blocking, "advisory_failures": advisory,
            "items": items}


__all__ = ["CHECKLIST_VERSION", "INTERNAL_TOKENS", "KNOWN_SECTION_DOMAINS",
           "CONDITION_KIND_LABELS", "FINDING_KIND_LABELS",
           "check_parse_quality", "presentation_report"]
