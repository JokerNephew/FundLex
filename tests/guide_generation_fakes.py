"""Deterministic model doubles for guide generation tests (no network)."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class _Result:
    value: dict
    model: str = "fake"
    latency_ms: int = 0
    prompt_tokens: int | None = 1
    completion_tokens: int | None = 1
    total_tokens: int | None = 2
    request_id: str | None = None
    attempts: int = 1
    estimated_cost_usd: float | None = 0.0
    task_type: str = ""
    context_sha256: str = ""


class FakeGuideRouter:
    def __init__(self):
        self.records: list[dict] = []
        self.callback = None
        self.run_max_calls = 10000
        self.run_max_cost = 100.0
        self.gateways = {"primary": self}
        self.fail_task_types: set[str] = set()

    def set_call_callback(self, callback):
        self.callback = callback

    def identity(self):
        return {
            "regulation_analyst": {"role": "regulation_analyst", "model": "fake-analyst", "provider": "fake", "configured": True},
            "requirement_reviewer": {"role": "requirement_reviewer", "model": "fake-reviewer", "provider": "fake", "configured": True},
            "discovery": {"role": "discovery", "model": "fake-discovery", "provider": "fake", "configured": True},
            "guide_author": {"role": "guide_author", "model": "fake-author", "provider": "fake", "configured": True},
            "guide_reviewer": {"role": "guide_reviewer", "model": "fake-guide-reviewer", "provider": "fake", "configured": True},
            "coverage_auditor": {"role": "coverage_auditor", "model": "fake-coverage", "provider": "fake", "configured": True},
            "independent_model_review": True,
            "independent_model_review_status": "qualified",
        }

    @property
    def max_context_chars(self):
        return 32000

    @property
    def max_calls(self):
        return 10000

    @property
    def model(self):
        return "fake-primary"

    @property
    def calls(self):
        return len(self.records)

    @property
    def events(self):
        return []

    @property
    def budget(self):
        return None

    def metrics(self):
        return {"by_role": {}, "calls": len(self.records), "estimated_cost_usd": 0.0, "error_count": 0}

    def close(self):
        pass

    def call(self, *, task_type: str, bounded_context: str, response_schema: dict,
             instruction: str, prompt_version: str = "v1", role: str | None = None):
        if task_type in self.fail_task_types:
            raise RuntimeError(f"fake failure: {task_type}")
        value = self._value(task_type, bounded_context)
        record = {
            "role": role or "fake", "task_type": task_type, "prompt_version": prompt_version,
            "model": "fake", "provider": "fake", "context_sha256": "x",
            "instruction_sha256": "x", "schema_sha256": "x", "prompt_bundle_sha256": "x",
            "request_options_sha256": "x", "context_chars": len(bounded_context),
            "latency_ms": 0, "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
            "estimated_cost_usd": 0.0, "attempts": 1, "reused_checkpoint": False,
            "error_code": "",
        }
        self.records.append(record)
        if self.callback:
            class Record:
                def to_dict(inner):
                    return record
            self.callback(Record())
        return _Result(value)

    def _value(self, task_type: str, context: str) -> dict:
        if task_type == "guide_req_extract":
            blocks = re.findall(r"\[(B\d{4})\](?:\[([^\]]+)\])?(?:\[HEADING\])?\n([^\n]+)", context)
            requirements = []
            dispositions = {}
            current_article = ""
            for block_id, article, text in blocks:
                if article:
                    current_article = article
                requirements.append({
                    "source_block_ids": [block_id], "source_quote": text.strip(),
                    "article": article or current_article, "norm_type": "obligation",
                    "subject": "基金管理人", "object": "基金销售费用",
                    "requirement": "基金管理人应当按本规定管理基金销售费用：" + text.strip()[:80],
                    "conditions": [], "exceptions": [],
                    "applicable_scope": {"fund_types": [], "channels": [], "share_classes": [],
                                         "investor_types": [], "notes": ""},
                    "effective_time": "", "candidate_contract_domains": ["基金费用与税收", "基金份额的申购与赎回"],
                    "external_dependencies": [], "disposition": "modify_contract",
                    "disposition_reason": "fake",
                })
                if article:
                    dispositions[article] = {
                        "article": article, "source_block_ids": [block_id],
                        "disposition": "modify_contract", "reason": "fake",
                    }
            return {"requirements": requirements, "article_dispositions": list(dispositions.values()),
                    "notes": ""}
        if task_type == "guide_req_review":
            return {"missing_requirements": [], "corrections": [], "article_assessment": [], "notes": ""}
        if task_type == "guide_intent":
            return {"intents": [{"terms": ["销售服务费", "申购费", "赎回费", "直销机构", "销售机构"],
                                 "phrases": ["销售服务费", "申购费"],
                                 "section_hints": ["基金费用与税收", "基金份额的申购与赎回"],
                                 "business_actions": ["收取", "计提", "支付"], "rationale": "fake"}]}
        if task_type == "guide_impact_sweep":
            findings = []
            reqs = re.findall(r"- (R-[0-9a-f]+) \[", context)
            for cid in re.findall(r"\[(CL-[0-9a-f]+)\]", context):
                match = re.search(re.escape(cid) + r"\] section=([^\n]*)\n([^\n]*)", context)
                text = match.group(2) if match else ""
                if any(term in text for term in ("销售服务费", "申购费", "赎回费", "认购费")):
                    if reqs:
                        findings.append({"clause_ids": [cid], "requirement_ids": [reqs[0]],
                                         "impact_status": "possible", "impact_dimensions": ["fee"],
                                         "reason": "费用条款", "evidence_quote": text[:80]})
                if len(findings) >= 8:
                    break
            return {"findings": findings, "uncovered_suspicions": [],
                    "section_assessment": "affected" if findings else "not_affected", "notes": ""}
        if task_type == "guide_impact_adjudicate":
            ids = re.findall(r"\[IMPACT id=([^\]]+)\]", context)
            return {"items": [{"impact_id": value, "impact_status": "possible",
                               "reason": "fake", "guide_relevant": True} for value in ids]}
        if task_type == "guide_local_candidate":
            ids = re.findall(r"\[IMPACT (IC-[^\]]+)\]", context)
            reqs = re.findall(r"\[(R-[0-9a-f]+)\] article=", context)
            return {"candidates": [{
                "impact_ids": ids, "requirement_ids": reqs[:1] or ["R-missing"],
                "needs_modification": "yes", "business_goal": "按销售费用新规调整费用条款",
                "semantic_changes": ["明确直销机构不收申购费"],
                "applicability": "存在申购费条款的基金合同",
                "conditions": ["通过直销机构申购"], "exceptions": [],
                "old_text_patterns": ["申购费由基金管理人决定"],
                "new_text": "通过直销机构申购本基金不收取申购费。",
                "new_text_origin": "model_drafted", "notes": "fake",
            }]}
        if task_type == "guide_merge":
            ids = re.findall(r"\[(LG-[0-9a-f]+)\]", context)
            return {"families": [{
                "local_ids": ids, "title": "销售费用条款调整", "section": "基金费用与税收",
                "business_requirement": "按新规调整销售费用条款",
                "instruction": "调整申购费及销售服务费表述",
                "applicability": "存在相关费用条款", "conditions": ["通过直销机构申购"],
                "exceptions": [], "old_text_patterns": ["申购费由基金管理人决定"],
                "new_text": "通过直销机构申购本基金不收取申购费。",
                "new_text_origin": "model_drafted", "merge_rationale": "fake",
            }]}
        if task_type == "guide_quality_review":
            return {"verdict": "pass", "findings": [], "notes": ""}
        if task_type == "guide_coverage_audit":
            return {"requirement_results": [], "impact_results": [], "missing_topics": [], "notes": ""}
        if task_type == "guide_residual_sweep":
            return {"uncovered": [], "guide_conflicts": [], "notes": ""}
        if task_type == "guide_applicability":
            return {"verdict": "covered", "reason": "fake", "evidence_quote": ""}
        if task_type == "guide_engine_map":
            return {"results": []}
        if task_type == "guide_parse":
            return {"groups": []}
        if task_type == "guide_verify":
            return {"findings": [], "invalid_findings": 0, "coverage_explanation": ""}
        return {}
