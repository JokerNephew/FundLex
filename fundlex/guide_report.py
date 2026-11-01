"""Owner-facing, human-readable parse diagnostics (任务 C).

The quality channel answers "is this guide safe to enable" with codes; the
parse report answers "which guide blocks parsed, merged, were lost or failed,
and why" in plain Chinese, rendered from the deterministic validation
components — never from model self-assessment.
"""
from __future__ import annotations

from typing import Any, Mapping

from .guide import GuideSource, segment_guide_blocks

REPORT_SCHEMA_VERSION = "guide-parse-report-v1"

# Deterministic code → owner-facing Chinese explanation.  ``remedy`` tells the
# owner what to change in the guide document (or in the environment) next.
CODE_EXPLANATIONS: dict[str, dict[str, str]] = {
    "GUIDE_SOURCE_UNREADABLE": {"zh": "指引文件无法读取或不是有效的 DOCX",
                              "remedy": "请用 Word 另存为标准 .docx 后重新上传"},
    "GUIDE_SOURCE_EMPTY": {"zh": "未从指引中读到任何段落文本",
                           "remedy": "确认文档正文非纯图片，必要时粘贴为文字后重新上传"},
    "GUIDE_CONTEXT_LIMIT": {"zh": "指引文本超出单次解析的上下文容量",
                            "remedy": "拆分指引为多个文件分别上传，或联系支持扩容"},
    "GUIDE_PARSE_INVALID": {"zh": "解析结果不是合法的规则结构", "remedy": "可重试解析；持续出现请联系支持"},
    "GUIDE_PARSE_FAILED": {"zh": "解析未完成", "remedy": "稍后重试；持续出现请联系支持"},
    "GUIDE_GROUP_INVALID": {"zh": "规则结构字段不合法（缺字段或类型错误）",
                            "remedy": "多为解析波动，重试解析；持续出现请人工复核该指引"},
    "GUIDE_RULE_ID_INVALID": {"zh": "规则编号不连续或重复", "remedy": "重试解析；持续出现请人工复核"},
    "GUIDE_TEXT_NOT_VERBATIM": {"zh": "新/旧条款文本未逐字取自指引原文",
                                "remedy": "指引正文中引号、标点不统一时易发；请检查对应块的原文表述"},
    "GUIDE_SLOT_NOT_IN_TEXT": {"zh": "份额类别槽位词未出现在新条款文本中",
                               "remedy": "多为指引原文笔误或新旧条款引用错位，请核对指引原文后重新上传"},
    "GUIDE_PARAGRAPH_RANGE_INVALID": {"zh": "规则引用了不存在的指引段落", "remedy": "重试解析"},
    "GUIDE_VALIDATION_UNCLEAN": {"zh": "解析未通过确定性校验或独立核验，版本不能启用",
                                 "remedy": "按下方块报告逐块修正指引原文后重新上传解析"},
    "GUIDE_CANARY_PARTIAL_IDENTITY": {"zh": "规则操作标识不完整", "remedy": "重试解析；持续出现请联系支持"},
    "GUIDE_CANARY_OP_UNREGISTERED": {"zh": "解析把多个指引义务合并或移序，生成的操作无法映射到已注册执行契约",
                                     "remedy": "按块报告提示的块改写指引：一条义务一个指令块、保持原文顺序；"
                                               "若为新规政策，需要注册扩展后方能使用"},
    "GUIDE_CANARY_ROUTE_BLOCKED": {"zh": "操作在全部事实已验证下仍无可用执行路径",
                                   "remedy": "请人工复核对应块的条件设定"},
    "GUIDE_CANARY_DEAD_CONDITION": {"zh": "分支条件恒不成立（互斥条件被写反或被错误合并）",
                                    "remedy": "请核对指引中『如果…则…』分支的适用条件后重新上传"},
    "GUIDE_CANARY_COMPILE_FAILED": {"zh": "解析产物无法重建为执行计划", "remedy": "请人工复核该指引"},
    "GUIDE_CANARY_COMPILE_MISMATCH": {"zh": "执行计划条目数与操作数不一致", "remedy": "请人工复核该指引"},
    "GUIDE_OPERATION_REGISTRY_MISSING": {"zh": "存在无法执行的操作，版本不能启用",
                                         "remedy": "按块报告改写指引保持一条义务一个指令块；新规政策需注册扩展"},
    "GUIDE_PARSE_ATTEMPTS_EXHAUSTED": {"zh": "解析多次失败已耗尽重试", "remedy": "请检查指引文件后重新上传"},
    "GUIDE_VERSION_SUPERSEDED": {"zh": "该版本已被更新的解析取代", "remedy": "请查看最新版本"},
    "GUIDE_SECTION_HINT_EMPTY": {"zh": "该规则没有标注属于合同哪个章节",
                                 "remedy": "多为解析波动，重试解析；持续出现请人工复核"},
    "GUIDE_PARAGRAPH_ORDER": {"zh": "规则引用的来源段落顺序或唯一性不规范",
                              "remedy": "多为解析波动，重试解析；持续出现请人工复核"},
    "GUIDE_COVERAGE_GAP": {"zh": "指引有段落没有被任何规则覆盖",
                           "remedy": "若为有效指引内容，请调整该段表述后重新上传解析；若为标题性文字属正常"},
    "GUIDE_CANARY_LEGACY_RULE_UNREGISTERED": {"zh": "旧格式规则缺少可注册的操作标识（按兼容路径执行）",
                                              "remedy": "建议重新解析为带操作标识的新格式；仅提示，不影响启用"},
    "GUIDE_DOCUMENT_INVALID": {"zh": "已保存的解析文档不合法", "remedy": "请重新解析该版本"},
}
_MODEL_FAILED_PREFIX = "GUIDE_MODEL_FAILED:"

_STATUS_TEXT = {
    "parsed": "解析成功",
    "split": "被拆分为多条规则（结构正常）",
    "merged": "与其他块合并进一条规则（粒度过粗）",
    "uncovered": "未被任何规则覆盖（内容丢失）",
    "error": "解析结果存在错误",
    "unparsed": "未完成解析",
}


def _explain(code: str) -> dict[str, str]:
    # User wording stays human; the raw technical code/inner message only ever
    # travels in the ``code`` annotation field (FL-D925, backend zh+code 口径).
    if code.startswith(_MODEL_FAILED_PREFIX):
        return {"zh": "模型服务调用失败",
                "remedy": "多为服务暂不可用或限流，稍后重试解析；持续出现请联系支持",
                "code": code}
    if code in CODE_EXPLANATIONS:
        return CODE_EXPLANATIONS[code]
    return {"zh": "未归类问题",
            "remedy": "重试解析；持续出现请联系支持", "code": code}


def explain_code(code: str) -> dict[str, str]:
    return dict(_explain(code))


def _paragraphs_of(source: GuideSource, start: int, end: int) -> list[int]:
    return [p.index for p in source.paragraphs
            if start <= p.index < end and p.text.strip()]


def _group_by_error_rule(errors: list[Mapping[str, Any]]) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for error in errors:
        rule = str(error.get("rule_id") or "")
        grouped.setdefault(rule, []).append(error)
    return grouped


def block_report(source: GuideSource, document: Mapping[str, Any] | None, *,
                 error_code: str | None = None,
                 rule_problems: Mapping[str, list[Mapping[str, Any]]] | None = None) -> dict[str, Any]:
    """Per-block owner-facing verdict for one parse attempt.

    ``document=None`` covers attempts that died before producing a parse
    (source unreadable, model failure): every block is ``unparsed`` with the
    reason derived from ``error_code``.  ``rule_problems`` maps rule ids to
    additional fatal findings (typically the executability canary's), so an
    executability failure is localised to the guide blocks that caused it.
    """
    blocks = segment_guide_blocks(source)
    groups = [group for group in (document or {}).get("groups") or []
              if isinstance(group, Mapping)] if isinstance(document, Mapping) else []
    validation = (document.get("validation") or {}) if isinstance(document, Mapping) else {}
    errors = [e for e in (validation.get("errors") or []) if isinstance(e, Mapping)]
    errors_by_rule = _group_by_error_rule(errors)
    problems_by_rule: dict[str, list[Mapping[str, Any]]] = {}
    if rule_problems:
        for rule_id, items in rule_problems.items():
            normalized = [dict(item, rule_id=str(item.get("rule_id") or rule_id))
                          for item in items if isinstance(item, Mapping)]
            if normalized:
                problems_by_rule.setdefault(str(rule_id), []).extend(normalized)
    # paragraph → owning rule ids (a paragraph may legitimately have several)
    owners: dict[int, list[str]] = {}
    rule_blocks: dict[str, set[int]] = {}
    for group in groups:
        rule_id = str(group.get("rule_id") or "")
        for paragraph in (group.get("source_paragraphs") or []):
            if isinstance(paragraph, int) and not isinstance(paragraph, bool):
                owners.setdefault(paragraph, []).append(rule_id)
    for group in groups:
        rule_id = str(group.get("rule_id") or "")
        block_ids = {block.index for block in blocks
                     for paragraph in (group.get("source_paragraphs") or [])
                     if isinstance(paragraph, int) and block.start <= paragraph < block.end}
        rule_blocks[rule_id] = block_ids
    entries: list[dict[str, Any]] = []
    counts = {"parsed": 0, "split": 0, "merged": 0, "uncovered": 0, "error": 0, "unparsed": 0}
    for block in blocks:
        paragraphs = _paragraphs_of(source, block.start, block.end)
        rules = sorted({rule for paragraph in paragraphs
                        for rule in owners.get(paragraph, [])})
        if document is None:
            status = "unparsed"
            reason = _explain(error_code or "GUIDE_PARSE_FAILED")["zh"]
            remedy = _explain(error_code or "GUIDE_PARSE_FAILED")["remedy"]
        elif not rules:
            status, reason, remedy = "uncovered", "该块未被任何解析规则使用", "若为有效指引内容，请调整表述后重新上传解析"
        elif any(rule in errors_by_rule for rule in rules):
            first = errors_by_rule[[r for r in rules if r in errors_by_rule][0]][0]
            info = _explain(str(first.get("code") or ""))
            status, reason, remedy = "error", f"{info['zh']}：{str(first.get('detail') or '')[:60]}", info["remedy"]
        elif any(rule in problems_by_rule for rule in rules):
            first = problems_by_rule[[r for r in rules if r in problems_by_rule][0]][0]
            info = _explain(str(first.get("code") or ""))
            operation = str(first.get("operation") or "")
            status, reason, remedy = "error", \
                f"{info['zh']}：{operation or str(first.get('detail') or '')[:60]}", info["remedy"]
        elif len(rules) > 1:
            status = "split"
            reason = f"该块被拆分为 {len(rules)} 条规则（{'、'.join(rules)}）"
            remedy = ""
        elif len(rule_blocks.get(rules[0], set())) > 1:
            status = "merged"
            reason = f"该块与其他块合并为规则 {rules[0]}，粒度偏粗"
            remedy = "建议一条指引义务对应一个指令块，保持原文顺序"
        else:
            status, reason, remedy = "parsed", "", ""
        counts[status] += 1
        entry = {"block": block.index, "paragraphs": [block.start, block.end - 1],
                 "label": block.label, "status": status, "status_zh": _STATUS_TEXT[status],
                 "rule_ids": rules}
        if reason:
            entry["reason_zh"] = reason
        if remedy:
            entry["remedy_zh"] = remedy
        entries.append(entry)
    total = len(blocks)
    summary = (f"共 {total} 个指引块：成功 {counts['parsed']}、拆分 {counts['split']}、"
               f"合并 {counts['merged']}、未覆盖 {counts['uncovered']}、"
               f"错误 {counts['error']}、未解析 {counts['unparsed']}")
    if document is None:
        summary += f"；任务未完成：{_explain(error_code or 'GUIDE_PARSE_FAILED')['zh']}"
    return {"schema_version": REPORT_SCHEMA_VERSION, "blocks_total": total,
            "summary_zh": summary, "counts": counts, "entries": entries,
            "explanations": {code: _explain(code)
                             for code in ({error_code} if error_code else set())
                             | {str(e.get("code")) for e in errors}}}


def granularity_metrics(source: GuideSource, document: Mapping[str, Any]) -> dict[str, Any]:
    """Structure-only granularity metrics (diagnostics, never gating)."""
    blocks = segment_guide_blocks(source)
    groups = [group for group in (document or {}).get("groups") or []
              if isinstance(group, Mapping)]
    multi_block_rules = 0
    for group in groups:
        touched = {block.index for block in blocks
                   for paragraph in (group.get("source_paragraphs") or [])
                   if isinstance(paragraph, int) and block.start <= paragraph < block.end}
        if len(touched) > 1:
            multi_block_rules += 1
    return {"blocks": len(blocks), "rules": len(groups),
            "rules_spanning_blocks": multi_block_rules,
            "segmentation": "emphasis-labels" if len(blocks) > 1 else "single-block"}
