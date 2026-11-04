"""Engine compatibility: separate from guide quality and coverage.

The candidate DOCX is parsed by the existing FundLex guide parser and, when a
sample contract is supplied, executed by the existing recall-first pipeline.
A failure here is classified as an engine gap unless the guide itself cannot be
parsed or is semantically ambiguous.  Engine results never rewrite a guide.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import GuideItem, PolicyRequirement, utc_now


def _dsl_condition_supported(conditions: list[str], applicability: str) -> bool:
    text = " ".join(conditions + [applicability])
    supported = ("份额类别", "A类", "C类", "多个份额", "单一份额", "销售服务费",
                 "浮动管理费", "持有期限", "持续持有", "直销", "销售机构", "费率")
    # Free-form channel/holding-period conditions cannot be represented by the
    # current CONDITION_KINDS (none/class_count/has_service_fee/is_floating_fee/
    # compound).  Mark them as capability gaps instead of changing the guide.
    unsupported_markers = ("直销", "销售机构", "一年", "持有期限", "持续持有", "公告", "备案",
                           "投资者类型", "条件组合")
    if any(marker in text for marker in unsupported_markers):
        return False
    return any(marker in text for marker in supported) or not text.strip()


def _card_view(unit: dict[str, Any]) -> tuple[str, str, str, str]:
    """(title, section, requirement, unit_id) for legacy groups and card docs."""
    if "card_id" in unit or "action" in unit:
        target = unit.get("target") or {}
        sections = " / ".join(str(name) for name in target.get("contract_sections") or [])
        action = unit.get("action") or {}
        applicability = unit.get("applicability") or {}
        requirement = " ".join([str(action.get("content_requirement") or ""),
                                str(applicability.get("text") or "")]).strip()
        return (str(unit.get("title") or ""), sections, requirement,
                str(unit.get("card_id") or ""))
    return (str(unit.get("title") or ""), str(unit.get("section_hint") or ""),
            str(unit.get("requirement") or ""), str(unit.get("rule_id") or ""))


def classify_item(item: GuideItem, parsed_units: list[dict[str, Any]]) -> dict[str, Any]:
    matched = []
    for unit in parsed_units:
        title, section, requirement, _unit_id = _card_view(unit)
        if item.title and (item.title[:30] in title or title[:30] in item.title):
            matched.append(unit)
        elif item.section and section and item.section[:20] in section:
            matched.append(unit)
        elif item.business_requirement and requirement and item.business_requirement[:40] in requirement:
            matched.append(unit)
    parsed_ids = [_card_view(unit)[3] for unit in matched]
    if not item.new_text.strip():
        return {"classification": "GUIDE_COVERAGE_GAP", "parsed_rule_ids": parsed_ids,
                "reason": "候选指引没有新合同文案，现有引擎无可执行目标。"}
    if not item.requirement_ids or not item.impact_ids:
        return {"classification": "GUIDE_COVERAGE_GAP", "parsed_rule_ids": parsed_ids,
                "reason": "候选指引缺少法规或真实合同来源，不能进入引擎。"}
    if not matched:
        return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": [],
                "reason": "当前 Guide Parser 未能生成可对应规则；不据此修改候选指引。"}
    legacy = [unit for unit in matched if "operations" in unit]
    if legacy:  # frozen guide-rules-v1 documents keep the old capability check
        if not _dsl_condition_supported(item.conditions, item.applicability):
            return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": parsed_ids,
                    "reason": "候选指引含渠道/持有期限/多条件业务条件，旧 DSL 的 condition 类型无法表达。"}
        for group in legacy:
            operations = group.get("operations") or []
            if not operations:
                return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": parsed_ids,
                        "reason": "解析规则没有可执行 operation。"}
            if any(str(op.get("op")) not in {"append", "replace", "delete", "noop"} for op in operations):
                return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": parsed_ids,
                        "reason": "解析规则含当前引擎不支持的 operation。"}
        return {"classification": "expressible", "parsed_rule_ids": parsed_ids,
                "reason": "解析规则在业务含义和当前 operation/condition 能力范围内可对应。"}
    # guide_card_v1 units: natural-language conditions, no DSL ceiling.  Any
    # matched card is expressible in the direct-through contract; the
    # free-form channel/holding-period conditions are records, not blockers.
    return {"classification": "expressible", "parsed_rule_ids": parsed_ids,
            "reason": "原子规则卡以自然语言条件表达，直通契约下可对应；条件复杂度仅为记录。"}


def run_engine_compatibility(*, guide_docx: str | Path, items: list[GuideItem],
                             requirements: list[PolicyRequirement], router,
                             sample_contract: str | Path | None = None,
                             output_dir: str | Path | None = None) -> dict[str, Any]:
    from ..guide import build_guide_document, extract_guide_source, GuideError
    source = extract_guide_source(guide_docx)
    parse_document: dict[str, Any] | None = None
    parse_error = ""
    try:
        parse_document = build_guide_document(source, router, max_repair_rounds=0)
    except GuideError as exc:
        parse_error = f"{exc.code}:{exc.details}"
    except Exception as exc:
        parse_error = f"{type(exc).__name__}:{exc}"
    doc_schema = str((parse_document or {}).get("schema_version") or "")
    # guide_card_v1 exposes "cards"; frozen guide-rules-v1 documents expose "groups".
    parsed_groups = list((parse_document or {}).get("cards") or
                         (parse_document or {}).get("groups") or [])
    results: list[dict[str, Any]] = []
    for item in items:
        result = classify_item(item, parsed_groups)
        result["guide_item_id"] = item.guide_item_id
        result["source"] = "guide_parser_and_dsl"
        results.append(result)
    sample_run: dict[str, Any] = {"status": "not_run"}
    if doc_schema == "guide_card_v1":
        # The legacy recall-first engine cannot consume card documents; the
        # direct-through engine is owned by the contract-editing line.  Skip
        # the sample run instead of silently feeding cards to the old engine.
        sample_run = {"status": "skipped",
                      "note": "guide_card_v1 卡包不接旧 recall-first 引擎；样例合同运行待直通引擎接线。"}
    elif sample_contract and parse_document and not parse_error:
        try:
            from ..recall_pipeline import process_recall_first
            target = Path(output_dir or "/tmp")
            target.mkdir(parents=True, exist_ok=True)
            report = process_recall_first(Path(sample_contract), target,
                                          guide_document=parse_document,
                                          gateway=router.gateways["primary"])
            unresolved = report.get("unresolved") or []
            sample_run = {
                "status": "completed",
                "delivery_status": report.get("delivery_status"),
                "qualification_status": report.get("qualification_status"),
                "unresolved_count": len(unresolved),
                "unresolved_reasons": sorted({str(item.get("reason") or item.get("code") or "")
                                              for item in unresolved}),
                "edit_count": (report.get("edit_plan") or {}).get("count"),
                "engine_build": report.get("engine_build"),
            }
        except Exception as exc:
            sample_run = {"status": "engine_error", "error_code": type(exc).__name__,
                          "error": str(exc)[:500]}
    classification_counts: dict[str, int] = {}
    for result in results:
        classification_counts[result["classification"]] = classification_counts.get(result["classification"], 0) + 1
    return {
        "schema_version": "engine-compatibility-1",
        "generated_at": utc_now(),
        "status": "not_run" if parse_error and not parse_document else "completed",
        "guide_source_sha256": source.source_sha256,
        "parse_error": parse_error,
        "parsed_groups": len(parsed_groups),
        "parser_validation": (parse_document or {}).get("validation", {}),
        "classification_counts": classification_counts,
        "results": results,
        "sample_contract_run": sample_run,
        "note": "Engine Compatibility 是独立报告，不参与 Guide Quality / Coverage 判定。",
    }
