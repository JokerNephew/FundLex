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


def classify_item(item: GuideItem, parsed_groups: list[dict[str, Any]]) -> dict[str, Any]:
    matched = []
    for group in parsed_groups:
        title = str(group.get("title") or "")
        section = str(group.get("section_hint") or "")
        requirement = str(group.get("requirement") or "")
        if item.title and (item.title[:30] in title or title[:30] in item.title):
            matched.append(group)
        elif item.section and section and item.section[:20] in section:
            matched.append(group)
        elif item.business_requirement and requirement and item.business_requirement[:40] in requirement:
            matched.append(group)
    parsed_ids = [str(group.get("rule_id") or "") for group in matched]
    if not item.new_text.strip():
        return {"classification": "GUIDE_COVERAGE_GAP", "parsed_rule_ids": parsed_ids,
                "reason": "候选指引没有新合同文案，现有引擎无可执行目标。"}
    if not item.requirement_ids or not item.impact_ids:
        return {"classification": "GUIDE_COVERAGE_GAP", "parsed_rule_ids": parsed_ids,
                "reason": "候选指引缺少法规或真实合同来源，不能进入引擎。"}
    if not _dsl_condition_supported(item.conditions, item.applicability):
        return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": parsed_ids,
                "reason": "候选指引含渠道/持有期限/多条件业务条件，当前 DSL 的 condition 类型无法表达。"}
    if not matched:
        return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": [],
                "reason": "当前 Guide Parser 未能生成可对应规则；不据此修改候选指引。"}
    for group in matched:
        operations = group.get("operations") or []
        if not operations:
            return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": parsed_ids,
                    "reason": "解析规则没有可执行 operation。"}
        if any(str(op.get("op")) not in {"append", "replace", "delete", "noop"} for op in operations):
            return {"classification": "ENGINE_CAPABILITY_GAP", "parsed_rule_ids": parsed_ids,
                    "reason": "解析规则含当前引擎不支持的 operation。"}
    return {"classification": "expressible", "parsed_rule_ids": parsed_ids,
            "reason": "解析规则在业务含义和当前 operation/condition 能力范围内可对应。"}


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
    parsed_groups = list((parse_document or {}).get("groups") or [])
    results: list[dict[str, Any]] = []
    for item in items:
        result = classify_item(item, parsed_groups)
        result["guide_item_id"] = item.guide_item_id
        result["source"] = "guide_parser_and_dsl"
        results.append(result)
    sample_run: dict[str, Any] = {"status": "not_run"}
    if sample_contract and parse_document and not parse_error:
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
