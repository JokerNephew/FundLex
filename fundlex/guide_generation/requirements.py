"""Requirement atomisation, independent challenge and adjudication."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .models import (
    PolicyRequirement,
    RegulationBlock,
    RegulationDocument,
    compact_for_match,
    merge_strings,
    normalize_space,
    quote_in_text,
    sha256_json,
    stable_id,
    unique,
)
from .prompts import (
    REQUIREMENT_EXTRACT_INSTRUCTION,
    REQUIREMENT_EXTRACT_SCHEMA,
    REQUIREMENT_EXTRACT_VERSION,
    REQUIREMENT_REVIEW_INSTRUCTION,
    REQUIREMENT_REVIEW_SCHEMA,
    REQUIREMENT_REVIEW_VERSION,
)
from ..regulatory.anchors import article_number, split_article_groups

_EFFECTIVE_OR_REPEAL = re.compile(
    r"(?:自[^。；]{0,40}起(?:施行|生效)|(?:予以|同时)?废止)")
_CONTRACT_FEE_TERMS = re.compile(
    r"(?:基金合同|基金销售协议|费用|销售服务费|申购费|赎回费|认购费|客户维护费)")

EXTERNAL_REFERENCE = re.compile(
    r"(?:原规定|原办法|原指引|同时废止|按照《[^》]+》执行|依据第[一二三四五六七八九十百零〇\d]+条|"
    r"将第[一二三四五六七八九十百零〇\d]+条(?:修改|修订)为|自本规定施行之日起)"
)
CONTRACT_REFERENCE = re.compile(r"(?:基金合同|销售协议|招募说明书|产品资料概要|法律文件)")
FUND_CONTRACT_REFERENCE = re.compile(r"(?:基金合同|招募说明书|产品资料概要|法律文件)")
SALES_AGREEMENT_REFERENCE = re.compile(r"(?:销售协议)")
IN_SCOPE_ACTIONS = re.compile(r"(?:应当|不得|可以|收取|计提|支付|约定|披露|列示|调整|修改|删除|增加)")
OUT_OF_SCOPE = re.compile(
    r"(?:中国证监会|派出机构|自律管理|监督管理|行政处罚|监管谈话|警示函|责令|追责问责|"
    r"内部考核|内部控?制|合规风控|从业人员|廉洁从业|礼金|礼品|旅游|宴请|回扣|抽奖|送实物|"
    r"内幕信息|商业秘密|信息技术系统|直销服务平台|中国结算)")
NO_CONTRACT_CHANGE = re.compile(
    r"(?:基金销售机构应当在销售场所|宣传推介材料|基金销售协议|销售业务活动|"
    r"定期报告|中期报告|年度报告|基金销售结算资金|客户维护费|销售费用信息披露)")


@dataclass
class RequirementResult:
    requirements: list[PolicyRequirement]
    article_dispositions: dict[str, dict[str, Any]]
    findings: list[dict[str, Any]]
    prompt_versions: dict[str, str]
    model_calls: int = 0
    notes: str = ""


class RequirementError(ValueError):
    def __init__(self, code: str, details: dict | None = None):
        self.code = code
        self.details = details or {}
        super().__init__(code)


def _block_context(blocks: Iterable[RegulationBlock]) -> str:
    lines = []
    for block in blocks:
        marker = f"[{block.block_id}]"
        if block.article_no:
            marker += f"[{block.article_no}]"
        if block.type == "heading":
            marker += "[HEADING]"
        lines.append(f"{marker}\n{block.text}")
    return "\n".join(lines)


def _batch_blocks(blocks: list[RegulationBlock], max_chars: int = 4500) -> list[list[RegulationBlock]]:
    batches: list[list[RegulationBlock]] = []
    current: list[RegulationBlock] = []
    size = 0
    for block in blocks:
        if current and size + len(block.text) + 30 > max_chars:
            batches.append(current)
            current = []
            size = 0
        current.append(block)
        size += len(block.text) + 30
    if current:
        batches.append(current)
    return batches


def _validate_requirement(item: dict[str, Any], blocks: dict[str, RegulationBlock],
                          batch_text: str, ordinal: int) -> PolicyRequirement | None:
    block_ids = [str(value) for value in item.get("source_block_ids") or [] if str(value) in blocks]
    if not block_ids:
        return None
    quote = str(item.get("source_quote") or "").strip()
    if not quote:
        return None
    joined = "\n".join(blocks[block_id].text for block_id in block_ids)
    if not quote_in_text(quote, joined) and not quote_in_text(quote, batch_text):
        return None
    article = str(item.get("article") or "").strip()
    if not article:
        article = next((blocks[block_id].article_no for block_id in block_ids if blocks[block_id].article_no), "")
    norm_type = str(item.get("norm_type") or "other")
    requirement_text = str(item.get("requirement") or "").strip()
    if not requirement_text:
        return None
    disposition = str(item.get("disposition") or "uncertain")
    if disposition not in {"modify_contract", "no_contract_change", "out_of_contract_scope",
                           "uncertain", "needs_external_baseline"}:
        disposition = "uncertain"
    external = [str(value).strip() for value in item.get("external_dependencies") or [] if str(value).strip()]
    combined = requirement_text + " " + quote
    if EXTERNAL_REFERENCE.search(combined) and not external:
        external = ["文本引用了当前输入之外的法规基线或修订关系"]
        if disposition == "modify_contract":
            disposition = "needs_external_baseline"
    if EXTERNAL_REFERENCE.search(combined) and disposition not in {"needs_external_baseline", "out_of_contract_scope"}:
        disposition = "needs_external_baseline"
    if CONTRACT_REFERENCE.search(combined) and disposition == "uncertain":
        disposition = "modify_contract"
    if not CONTRACT_REFERENCE.search(combined) and OUT_OF_SCOPE.search(combined) \
            and disposition == "uncertain":
        disposition = "out_of_contract_scope"
    if (disposition == "modify_contract" and SALES_AGREEMENT_REFERENCE.search(combined)
            and not FUND_CONTRACT_REFERENCE.search(combined)):
        disposition = "no_contract_change"
        disposition_reason = "仅指向基金销售协议事项，不直接要求修改基金合同文本。"
    if disposition == "modify_contract" and not CONTRACT_REFERENCE.search(combined):
        if OUT_OF_SCOPE.search(combined):
            disposition = "out_of_contract_scope"
            disposition_reason = "属于监管、机构治理、人员行为或平台运营要求，未指向基金合同文本。"
        elif norm_type == "definition":
            disposition = "no_contract_change"
            disposition_reason = "定义性条款，不直接要求修改基金合同。"
        elif NO_CONTRACT_CHANGE.search(combined):
            disposition = "no_contract_change"
            disposition_reason = "属于销售机构业务、报告披露或销售协议要求，未直接要求基金合同文本修改。"
    if disposition_reason := str(item.get("disposition_reason") or "").strip():
        pass
    else:
        disposition_reason = "模型对处置给出 uncertain，交由覆盖门和人工复核。"
    stable = stable_id("R", article, normalize_space(requirement_text), length=10)
    return PolicyRequirement(
        requirement_id=stable,
        source_block_ids=unique(block_ids),
        source_quote=quote,
        article=article,
        norm_type=norm_type,
        subject=str(item.get("subject") or "").strip(),
        object=str(item.get("object") or "").strip(),
        requirement=requirement_text,
        conditions=[str(value).strip() for value in item.get("conditions") or [] if str(value).strip()],
        exceptions=[str(value).strip() for value in item.get("exceptions") or [] if str(value).strip()],
        applicable_scope=dict(item.get("applicable_scope") or {}),
        effective_time=str(item.get("effective_time") or "").strip(),
        candidate_contract_domains=[str(value).strip() for value in item.get("candidate_contract_domains") or [] if str(value).strip()],
        external_dependencies=external,
        disposition=disposition,
        disposition_reason=disposition_reason,
        payload={"raw": item},
)

# These patterns are deliberately used as a recall-preserving supplement after
# model extraction.  They do not decide the legal meaning of a paragraph; they
# only identify explicit condition/exception phrases that the source itself
# states and therefore must remain attached to a requirement.
_EXPLICIT_CONDITION = re.compile(r"(?:对于|对)([^，。；]+)(?=[，。；])")
_EXPLICIT_EXCEPTION = re.compile(r"除([^，。；]+)外")
_FEE_CONTRACT_TOPIC = re.compile(
    r"(?:认[（(]申[）)]购费|认购费|申购费|赎回费|销售服务费|客户维护费|费率|收费|"
    r"基金合同|招募说明书|销售协议|销售机构|基金份额|持有期限|前端收费|后端收费)"
)


def _source_conditions(text: str) -> tuple[list[str], list[str]]:
    """Extract only explicit Chinese condition/exception lead-ins.

    The model remains responsible for legal atomisation.  This small source
    pass exists because a model can correctly cite a multi-sentence paragraph
    while putting only its first sentence in ``conditions`` or ``exceptions``.
    Keeping the lead-in phrase is useful to later authoring and coverage stages
    without paraphrasing or inventing a rule.
    """
    conditions: list[str] = []
    exceptions: list[str] = []
    for match in _EXPLICIT_CONDITION.finditer(text or ""):
        value = match.group(1).strip(" ，,；;。\t\n")
        if value and value not in conditions:
            conditions.append(value)
    for match in _EXPLICIT_EXCEPTION.finditer(text or ""):
        value = match.group(1).strip(" ，,；;。\t\n")
        if value and value not in exceptions:
            exceptions.append(value)
    return conditions, exceptions


def _inferred_disposition(text: str) -> tuple[str, str]:
    """Give a conservative disposition to a source-only supplemental atom."""
    if OUT_OF_SCOPE.search(text) and not _FEE_CONTRACT_TOPIC.search(text):
        return "out_of_contract_scope", "法规原文属于监管、机构治理或人员行为事项。"
    if NO_CONTRACT_CHANGE.search(text) and not CONTRACT_REFERENCE.search(text):
        return "no_contract_change", "法规原文指向销售业务、报告披露或销售协议事项。"
    if _FEE_CONTRACT_TOPIC.search(text) or CONTRACT_REFERENCE.search(text):
        return "modify_contract", "法规原文直接涉及基金合同或费用条款，保留为合同影响候选。"
    return "uncertain", "法规原文含有规范性动作，但合同适用范围需要人工确认。"


def _supplement_unquoted_source_blocks(blocks: list[RegulationBlock],
                                       requirements: list[PolicyRequirement]) -> list[PolicyRequirement]:
    """Retain normative source blocks omitted from a model's quoted atom.

    A frequent extraction failure is a valid requirement whose source ids span
    B0030/B0031/B0032 while ``source_quote`` contains only B0030.  Article-level
    coverage then looks complete even though the amount/holding-period and
    front-end/back-end permissions have no independent provenance.  The
    supplement adds one source-backed atom for each uncovered normative block;
    it never removes or rewrites a model atom.
    """
    # Only repair the tail of a source span that the model itself cited.  A
    # completely uncited block belongs to the normal article coverage/challenger
    # path; turning every normative block into a supplement here would silently
    # change a recall repair into a second extractor with different semantics.
    cited_blocks: set[str] = set()
    covered_blocks: set[str] = set()
    for requirement in requirements:
        quote = compact_for_match(requirement.source_quote)
        for block_id in requirement.source_block_ids:
            cited_blocks.add(block_id)
            block = next((item for item in blocks if item.block_id == block_id), None)
            if block and quote and compact_for_match(block.text) in quote:
                covered_blocks.add(block_id)
    existing_ids = {item.requirement_id for item in requirements}
    supplements: list[PolicyRequirement] = []
    for block in blocks:
        text = (block.text or "").strip()
        if (block.type == "heading" or len(text) < 12
                or block.block_id not in cited_blocks
                or block.block_id in covered_blocks):
            continue
        if not IN_SCOPE_ACTIONS.search(text):
            continue
        disposition, reason = _inferred_disposition(text)
        conditions, exceptions = _source_conditions(text)
        if "前端收费方式" in text or "后端收费方式" in text:
            # The source paragraph often states the method in one sentence and
            # amount/holding-period tiers in its next two paragraphs.  The
            # source quote stays exact; the structured condition is added only
            # when it is explicit in this block.
            conditions = merge_strings(conditions, [
                value for value in ("按认（申）购金额（份额）数量", "按持有期限")
                if value in text
            ])
        if "可以" in text or "可" in text:
            norm_type = "permission"
        elif "不得" in text or "禁止" in text:
            norm_type = "prohibition"
        elif "应当" in text or "必须" in text:
            norm_type = "obligation"
        elif "是指" in text:
            norm_type = "definition"
        else:
            norm_type = "other"
        requirement_id = stable_id("R", block.article_no, normalize_space(text), length=10)
        if requirement_id in existing_ids:
            continue
        supplements.append(PolicyRequirement(
            requirement_id=requirement_id,
            source_block_ids=[block.block_id], source_quote=text,
            article=block.article_no, norm_type=norm_type, subject="",
            object="", requirement=text, conditions=conditions,
            exceptions=exceptions, applicable_scope={},
            candidate_contract_domains=["费用条款"] if _FEE_CONTRACT_TOPIC.search(text) else [],
            disposition=disposition, disposition_reason=reason,
            discovery_pass="A-source-supplement", adjudication_status="source_block_supplement",
            payload={"source_supplement": True},
        ))
        existing_ids.add(requirement_id)
    return supplements


def _enrich_explicit_conditions(requirements: list[PolicyRequirement]) -> None:
    for requirement in requirements:
        conditions, exceptions = _source_conditions(requirement.source_quote)
        requirement.conditions = merge_strings(requirement.conditions, conditions)
        requirement.exceptions = merge_strings(requirement.exceptions, exceptions)


def _merge_requirements(items: Iterable[PolicyRequirement]) -> list[PolicyRequirement]:
    merged: dict[str, PolicyRequirement] = {}
    for item in items:
        key = item.requirement_id
        if key not in merged:
            merged[key] = item
            continue
        current = merged[key]
        current.conditions = merge_strings(current.conditions, item.conditions)
        current.exceptions = merge_strings(current.exceptions, item.exceptions)
        current.source_block_ids = unique(current.source_block_ids + item.source_block_ids)
        current.external_dependencies = merge_strings(current.external_dependencies,
                                                      item.external_dependencies)
        current.candidate_contract_domains = merge_strings(current.candidate_contract_domains,
                                                           item.candidate_contract_domains)
        if current.disposition == "uncertain" and item.disposition != "uncertain":
            current.disposition = item.disposition
        current.adjudication_status = "merged_duplicate"
    return sorted(merged.values(), key=lambda item: (item.article, item.requirement_id))


def _article_coverage(blocks: list[RegulationBlock], requirements: list[PolicyRequirement],
                      dispositions: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups = split_article_groups(blocks)
    findings: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for group in groups:
        article = group.get("article") or ""
        block_ids = set(group.get("block_ids") or [])
        # A short unnumbered preamble/title is not a silent requirement gap.
        if not article and len(normalize_space(group.get("text") or "")) < 200:
            continue
        covered = any(set(item.source_block_ids) & block_ids for item in requirements)
        disposition = dispositions.get(article) or next(
            (value for key, value in dispositions.items() if key and key in article), None)
        if not covered:
            # A model-level ``modify_contract`` disposition cannot close an
            # article when every atomic quote was rejected: it has no usable
            # evidence to explain what must change.  Only explicit scope-out
            # dispositions are safe to retain without an atomic requirement.
            if disposition and disposition.get("disposition") in {
                    "no_contract_change", "out_of_contract_scope"}:
                continue
            missing.append(group)
            findings.append({
                "finding_id": stable_id("F", "REQ_ARTICLE_GAP", article, group.get("text", "")[:80]),
                "category": "requirement_coverage", "severity": "critical",
                "article": article, "description": f"{article or '未编号段落'}没有原子要求或明确处置。",
                "evidence_quote": (group.get("text") or "")[:300],
            })
    return findings, missing


def _repair_missing_articles(router, blocks, missing, existing_ids, run_id,
                             prompt_versions) -> tuple[list[PolicyRequirement], list[dict[str, Any]], int, dict[str, dict]]:
    repaired: list[PolicyRequirement] = []
    findings: list[dict[str, Any]] = []
    dispositions: dict[str, dict] = {}
    calls = 0
    block_map = {block.block_id: block for block in blocks}
    # Batch missing articles into bounded calls.  The repair response uses the
    # same strict 18-item requirement array as the primary extractor, so the
    # old 8k window could still overflow maxItems even after primary batching
    # was reduced.
    batches: list[list[RegulationBlock]] = []
    current: list[RegulationBlock] = []
    size = 0
    for group in missing:
        group_blocks = [block_map[block_id] for block_id in group.get("block_ids") or []
                        if block_id in block_map]
        group_size = sum(len(block.text) + 30 for block in group_blocks)
        if current and size + group_size > 1500:
            batches.append(current)
            current = []
            size = 0
        current.extend(group_blocks)
        size += group_size
    if current:
        batches.append(current)
    for batch_index, batch in enumerate(batches):
        batch_text = "\n".join(block.text for block in batch)
        if not batch_text.strip():
            continue
        context = (f"[REGULATION]\nTask: these article groups were not covered by the first extractor. "
                   f"Read every block and return atomic requirements or explicit dispositions.\n"
                   f"Batch: {batch_index + 1}/{len(batches)}\n\n" + _block_context(batch))
        try:
            result = router.call(task_type="guide_req_extract", bounded_context=context,
                                 response_schema=REQUIREMENT_EXTRACT_SCHEMA,
                                 instruction=REQUIREMENT_EXTRACT_INSTRUCTION,
                                 prompt_version=REQUIREMENT_EXTRACT_VERSION + "_repair",
                                 role="regulation_analyst")
            calls += 1
        except Exception as exc:
            findings.append({
                "finding_id": stable_id("F", "REQ_REPAIR_FAILED", batch_index),
                "category": "requirement_coverage", "severity": "critical",
                "description": f"补漏模型调用失败：{getattr(exc, 'code', type(exc).__name__)}",
                "evidence_quote": batch_text[:300],
            })
            continue
        for item in result.value.get("requirements") or []:
            requirement = _validate_requirement(item, block_map, batch_text, 0)
            if requirement:
                repaired.append(requirement)
        for item in result.value.get("article_dispositions") or []:
            article = str(item.get("article") or "").strip()
            if article:
                dispositions[article] = item
    repaired_ids = {item.requirement_id for item in repaired}
    if not repaired_ids and not dispositions:
        for group in missing:
            article = group.get("article") or ""
            findings.append({
                "finding_id": stable_id("F", "REQ_STILL_MISSING", article),
                "category": "requirement_coverage", "severity": "critical",
                "article": article, "description": f"{article}补漏后仍无要求或明确处置。",
                "evidence_quote": (group.get("text") or "")[:300],
            })
    return repaired, findings, calls, dispositions


def extract_requirements(router, document: RegulationDocument, *, run_id: str = "") -> RequirementResult:
    blocks = document.blocks
    block_map = {block.block_id: block for block in blocks}
    # Keep the response below the strict 18-item schema cap.  A 4.5k source
    # window can contain more than 18 atomic definitions/obligations even when
    # the input itself fits comfortably; smaller batches preserve recall while
    # making the output cardinality deliverable.
    batches = _batch_blocks(blocks, max_chars=1500)
    requirements: list[PolicyRequirement] = []
    dispositions: dict[str, dict[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    calls = 0
    notes: list[str] = []
    for batch_index, batch in enumerate(batches):
        context = (f"[REGULATION]\nTitle: {document.title}\n"
                   f"Source: {document.source_type}\nBatch: {batch_index + 1}/{len(batches)}\n\n"
                   + _block_context(batch))
        try:
            result = router.call(task_type="guide_req_extract", bounded_context=context,
                                 response_schema=REQUIREMENT_EXTRACT_SCHEMA,
                                 instruction=REQUIREMENT_EXTRACT_INSTRUCTION,
                                 prompt_version=REQUIREMENT_EXTRACT_VERSION,
                                 role="regulation_analyst")
            calls += 1
        except Exception as exc:
            findings.append({
                "finding_id": stable_id("F", "REQ_EXTRACT_FAILED", batch_index),
                "category": "requirement_extraction", "severity": "critical",
                "description": f"要求抽取批次 {batch_index + 1} 失败：{getattr(exc, 'code', type(exc).__name__)}",
                "evidence_quote": "",
            })
            continue
        batch_text = "\n".join(block.text for block in batch)
        for item in result.value.get("requirements") or []:
            requirement = _validate_requirement(item, block_map, batch_text, len(requirements))
            if requirement:
                requirements.append(requirement)
            else:
                findings.append({
                    "finding_id": stable_id("F", "REQ_INVALID", batch_index, str(item)[:80]),
                    "category": "requirement_extraction", "severity": "major",
                    "description": "模型返回的要求无法绑定到法规原文，已拒绝。",
                    "evidence_quote": str(item.get("source_quote") or "")[:300],
                })
        for item in result.value.get("article_dispositions") or []:
            article = str(item.get("article") or "").strip()
            if article:
                dispositions[article] = item
        notes.append(str(result.value.get("notes") or ""))

    requirements = _merge_requirements(requirements)
    # Preserve source blocks that a valid model atom cited but did not quote in
    # full.  This is especially important for multi-paragraph permissions such
    # as front-end/back-end charging and amount/holding-period tiers.
    source_supplements = _supplement_unquoted_source_blocks(blocks, requirements)
    requirements = _merge_requirements(requirements + source_supplements)
    _enrich_explicit_conditions(requirements)
    coverage_findings, missing = _article_coverage(blocks, requirements, dispositions)
    findings.extend(coverage_findings)
    if missing:
        repaired, repair_findings, repair_calls, repaired_dispositions = _repair_missing_articles(
            router, blocks, missing, {item.requirement_id for item in requirements}, run_id,
            {})
        calls += repair_calls
        dispositions.update(repaired_dispositions)
        initial_gap_articles = {group.get("article") for group in missing}
        findings = [item for item in findings
                    if not (item.get("category") == "requirement_coverage"
                            and item.get("severity") == "critical"
                            and item.get("article") in initial_gap_articles)]
        findings.extend(repair_findings)
        requirements = _merge_requirements(requirements + repaired)
        source_supplements = _supplement_unquoted_source_blocks(blocks, requirements)
        requirements = _merge_requirements(requirements + source_supplements)
        _enrich_explicit_conditions(requirements)
        # Re-check the articles that were actually repaired.
        coverage_findings, still_missing = _article_coverage(blocks, requirements, dispositions)
        for group in still_missing:
            article = group.get("article") or ""
            finding = {
                "finding_id": stable_id("F", "REQ_ARTICLE_UNRESOLVED", article),
                "category": "requirement_coverage", "severity": "critical",
                "article": article,
                "description": f"{article or '未编号段落'}补漏后仍未绑定原子要求；已保留为 uncertain 要求。",
                "evidence_quote": (group.get("text") or "")[:300],
            }
            findings.append(finding)
            requirements.append(PolicyRequirement(
                requirement_id=stable_id("R", "UNRESOLVED_ARTICLE", article, group.get("text", "")[:80]),
                source_block_ids=group.get("block_ids") or [],
                source_quote=(group.get("text") or "")[:1000],
                article=article, norm_type="other", subject="", object="",
                requirement=(group.get("text") or "")[:1000],
                disposition="uncertain",
                disposition_reason="模型和补漏均未能给出可验证的原子要求；不得静默遗漏。",
                adjudication_status="unresolved_article",
            ))

    # Independent challenger pass. Review bounded regulation batches instead
    # of sending the complete regulation and baseline in one response. This
    # keeps the strict response schema below the provider output cap.
    by_id = {item.requirement_id: item for item in requirements}
    review_batches = _batch_blocks(blocks, max_chars=1500)
    for review_index, review_batch in enumerate(review_batches):
        batch_ids = {block.block_id for block in review_batch}
        batch_text = "\n".join(block.text for block in review_batch)
        baseline_text = "\n".join(
            f"- {item.requirement_id} [{item.article}] {item.requirement} QUOTE={item.source_quote[:300]}"
            for item in requirements if batch_ids.intersection(item.source_block_ids))
        review_context = (
            f"[REGULATION]\nTitle: {document.title}\n"
            f"Review batch: {review_index + 1}/{len(review_batches)}\n\n"
            f"{_block_context(review_batch)}\n\n[BASELINE]\n{baseline_text[:3000]}")
        try:
            review = router.call(task_type="guide_req_review", bounded_context=review_context,
                                 response_schema=REQUIREMENT_REVIEW_SCHEMA,
                                 instruction=REQUIREMENT_REVIEW_INSTRUCTION,
                                 prompt_version=REQUIREMENT_REVIEW_VERSION,
                                 role="requirement_reviewer")
            calls += 1
        except Exception as exc:
            findings.append({
                "finding_id": stable_id("F", "REQ_REVIEW_FAILED", review_index),
                "category": "requirement_review", "severity": "critical",
                "description": f"独立要求复核批次 {review_index + 1} 失败：{getattr(exc, 'code', type(exc).__name__)}",
                "evidence_quote": batch_text[:300],
            })
            continue
        rev = review.value
        for item in rev.get("missing_requirements") or []:
            requirement = _validate_requirement(item, block_map, batch_text, len(requirements))
            if requirement:
                requirement.discovery_pass = "B"
                requirement.adjudication_status = "added_by_challenger"
                if requirement.requirement_id not in by_id:
                    requirements.append(requirement)
                    by_id[requirement.requirement_id] = requirement
                else:
                    existing = by_id[requirement.requirement_id]
                    existing.conditions = merge_strings(existing.conditions, requirement.conditions)
                    existing.exceptions = merge_strings(existing.exceptions, requirement.exceptions)
        for correction in rev.get("corrections") or []:
            requirement = by_id.get(str(correction.get("requirement_id") or ""))
            if not requirement:
                continue
            field_name = str(correction.get("field") or "")
            quote = str(correction.get("source_quote") or "")
            if quote and not quote_in_text(quote, batch_text):
                continue  # a correction without source evidence is not evidence
            value = correction.get("corrected_value")
            if field_name in {"conditions", "exceptions", "candidate_contract_domains",
                              "external_dependencies"} and isinstance(value, list):
                setattr(requirement, field_name, merge_strings(getattr(requirement, field_name),
                                                               [str(v) for v in value if str(v).strip()]))
            elif field_name in {"requirement", "subject", "object", "article", "norm_type",
                                "effective_time", "disposition", "disposition_reason"}:
                if field_name == "disposition" and value not in {
                        "modify_contract", "no_contract_change", "out_of_contract_scope",
                        "uncertain", "needs_external_baseline"}:
                    continue
                setattr(requirement, field_name, value)
            requirement.adjudication_status = "corrected_by_challenger"
        for assessment in rev.get("article_assessment") or []:
            article = str(assessment.get("article") or "").strip()
            if article:
                dispositions[article] = {
                    "article": article,
                    "disposition": ("uncertain" if assessment.get("status") == "uncertain"
                                    else "no_contract_change"),
                    "reason": assessment.get("reason", ""),
                    "source_block_ids": [],
                }
        for assessment in rev.get("article_assessment") or []:
            if assessment.get("status") == "uncertain":
                findings.append({
                    "finding_id": stable_id("F", "REVIEW_UNCERTAIN", review_index,
                                             assessment.get("article", "")),
                    "category": "requirement_review", "severity": "major",
                    "article": assessment.get("article", ""),
                    "description": "独立复核认为该条覆盖不确定：" + str(assessment.get("reason") or ""),
                    "evidence_quote": "",
                })

    # The challenger may add a requirement that cites a multi-block span with
    # only a partial quote.  Run the same source-backed repair once more after
    # that pass so the final persisted requirement set has the same provenance
    # guarantee as the baseline and article-repair paths.
    requirements = _merge_requirements(requirements)
    requirements = _merge_requirements(
        requirements + _supplement_unquoted_source_blocks(blocks, requirements)
    )
    _enrich_explicit_conditions(requirements)
    # Ensure every requirement has a non-null disposition.  ``uncertain`` is a
    # handled disposition; it is reported as an unresolved business question.
    for requirement in requirements:
        text = (requirement.requirement + " " + requirement.source_quote).strip()
        if (_EFFECTIVE_OR_REPEAL.search(text)
                and not _CONTRACT_FEE_TERMS.search(text)
                and requirement.disposition in {"modify_contract", "no_contract_change",
                                                "needs_external_baseline", "uncertain"}):
            # An effective-date or repeal sentence does not itself impose a
            # contract modification.  Authoring it produced guide items whose
            # scope was the regulation's commencement clause, which then
            # failed quality review.
            requirement.disposition = "out_of_contract_scope"
            requirement.disposition_reason = "施行/废止条款不直接产生合同修改义务。"
        if requirement.disposition not in {
                "modify_contract", "no_contract_change", "out_of_contract_scope",
                "uncertain", "needs_external_baseline"}:
            requirement.disposition = "uncertain"
            requirement.disposition_reason = "抽取结果缺少合法处置，已保守标记 uncertain。"
        if not requirement.disposition_reason:
            requirement.disposition_reason = "未提供处置理由，保留供人工复核。"
    return RequirementResult(
        requirements=requirements, article_dispositions=dispositions,
        findings=findings,
        prompt_versions={"extract": REQUIREMENT_EXTRACT_VERSION,
                         "review": REQUIREMENT_REVIEW_VERSION},
        model_calls=calls, notes="\n".join(item for item in notes if item)[:4000],
    )
