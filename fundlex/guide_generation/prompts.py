"""Versioned prompts and strict JSON schemas for guide generation tasks."""
from __future__ import annotations

REQUIREMENT_EXTRACT_VERSION = "guide_req_extract_v1"
REQUIREMENT_REVIEW_VERSION = "guide_req_review_v1"
INTENT_VERSION = "guide_intent_v1"
IMPACT_SWEEP_VERSION = "guide_impact_sweep_v1"
IMPACT_ADJUDICATE_VERSION = "guide_impact_adjudicate_v1"
LOCAL_CANDIDATE_VERSION = "guide_local_candidate_v1"
MERGE_VERSION = "guide_merge_v1"
QUALITY_VERSION = "guide_quality_review_v1"
COVERAGE_VERSION = "guide_coverage_audit_v1"
RESIDUAL_VERSION = "guide_residual_sweep_v1"
APPLICABILITY_VERSION = "guide_applicability_v1"
ENGINE_VERSION = "guide_engine_map_v1"
REPAIR_VERSION = "guide_repair_v1"

PROMPT_VERSIONS = {
    "requirement_extract": REQUIREMENT_EXTRACT_VERSION,
    "requirement_review": REQUIREMENT_REVIEW_VERSION,
    "intent": INTENT_VERSION,
    "impact_sweep": IMPACT_SWEEP_VERSION,
    "impact_adjudicate": IMPACT_ADJUDICATE_VERSION,
    "local_candidate": LOCAL_CANDIDATE_VERSION,
    "merge": MERGE_VERSION,
    "quality": QUALITY_VERSION,
    "coverage": COVERAGE_VERSION,
    "residual": RESIDUAL_VERSION,
    "applicability": APPLICABILITY_VERSION,
    "engine": ENGINE_VERSION,
    "repair": REPAIR_VERSION,
}

DISPOSITION_ENUM = ["modify_contract", "no_contract_change", "out_of_contract_scope",
                    "uncertain", "needs_external_baseline"]
NORM_ENUM = ["prohibition", "obligation", "permission", "definition", "transition", "other"]

REQUIREMENT_ITEM = {
    "type": "object",
    "required": ["source_block_ids", "source_quote", "article", "norm_type", "subject",
                 "object", "requirement", "conditions", "exceptions", "applicable_scope",
                 "effective_time", "candidate_contract_domains", "external_dependencies",
                 "disposition", "disposition_reason"],
    "additionalProperties": False,
    "properties": {
        "local_id": {"type": "string"},
        "source_block_ids": {"type": "array", "minItems": 1, "maxItems": 16,
                             "items": {"type": "string"}},
        "source_quote": {"type": "string", "minLength": 1, "maxLength": 800},
        "article": {"type": "string", "maxLength": 64},
        "norm_type": {"enum": NORM_ENUM},
        "subject": {"type": "string", "maxLength": 160},
        "object": {"type": "string", "maxLength": 160},
        "requirement": {"type": "string", "minLength": 1, "maxLength": 800},
        "conditions": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 240}},
        "exceptions": {"type": "array", "maxItems": 10, "items": {"type": "string", "maxLength": 240}},
        "applicable_scope": {
            "type": "object", "additionalProperties": False,
            "properties": {
                "fund_types": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
                "channels": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                "share_classes": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
                "investor_types": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
            "required": ["fund_types", "channels", "share_classes", "investor_types", "notes"],
        },
        "effective_time": {"type": "string"},
        "candidate_contract_domains": {"type": "array", "maxItems": 30,
                                       "items": {"type": "string"}},
        "external_dependencies": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
        "disposition": {"enum": DISPOSITION_ENUM},
        "disposition_reason": {"type": "string", "maxLength": 300},
    },
}

REQUIREMENT_EXTRACT_SCHEMA = {
    "type": "object",
    "required": ["requirements", "article_dispositions"],
    "additionalProperties": False,
    "properties": {
        "requirements": {"type": "array", "maxItems": 18, "items": REQUIREMENT_ITEM},
        "article_dispositions": {
            "type": "array", "maxItems": 60,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["article", "source_block_ids", "disposition", "reason"],
                "properties": {
                    "article": {"type": "string"},
                    "source_block_ids": {"type": "array", "maxItems": 16, "items": {"type": "string"}},
                    "disposition": {"enum": DISPOSITION_ENUM},
                    "reason": {"type": "string"},
                },
            },
        },
        "notes": {"type": "string", "maxLength": 800},
    },
}

REQUIREMENT_EXTRACT_INSTRUCTION = (
    "Read the supplied [REGULATION] blocks. The [Bxxxx] labels are addresses, not legal text. "
    "Atomicize every normative statement into a PolicyRequirement. Do not summarise a whole article "
    "into one vague item when it contains several independent obligations, prohibitions, permissions, "
    "definitions, transitional rules or conditions. Preserve the exact subject, object, conditions, "
    "exceptions, scope, effective time and any external dependency (for example a rule that only "
    "operates by amending another instrument or referring to a baseline not present in this input). "
    "For every requirement return source_block_ids and a source_quote that is an exact contiguous "
    "copy from those blocks. disposition must be one of: modify_contract (a fund contract may need "
    "changing), no_contract_change (the rule is real but does not require a contract change), "
    "out_of_contract_scope (internal governance, regulator conduct, sanctions, etc.), uncertain, or "
    "needs_external_baseline (the input is missing another instrument needed to understand the rule). "
    "Article numbers, rates, dates and thresholds must be copied, never inferred. Also return one "
    "article_disposition for every article group supplied, including articles you found irrelevant. "
    "Do not create a requirement from historical contract wording; none is supplied here. "
    "Be concise: source_quote is the shortest contiguous sentence(s) that prove the requirement "
    "(do not copy a whole article when one sentence suffices); requirement is at most two sentences; "
    "conditions and exceptions contain only explicitly stated items; applicable_scope arrays may be "
    "empty; disposition_reason is one short sentence. Do not repeat the quote inside requirement and "
    "do not add commentary. Return JSON only."
)

REQUIREMENT_REVIEW_SCHEMA = {
    "type": "object",
    "required": ["missing_requirements", "corrections", "article_assessment"],
    "additionalProperties": False,
    "properties": {
        "missing_requirements": {"type": "array", "maxItems": 18, "items": REQUIREMENT_ITEM},
        "corrections": {
            "type": "array", "maxItems": 30,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["requirement_id", "field", "corrected_value", "reason", "source_quote"],
                "properties": {
                    "requirement_id": {"type": "string"},
                    "field": {"type": "string"},
                    "corrected_value": {},
                    "reason": {"type": "string"},
                    "source_quote": {"type": "string"},
                },
            },
        },
        "article_assessment": {
            "type": "array", "maxItems": 40,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["article", "status", "reason"],
                "properties": {
                    "article": {"type": "string"},
                    "status": {"enum": ["covered", "no_contract_relevance", "uncertain"]},
                    "reason": {"type": "string"},
                    "requirement_ids": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
                },
            },
        },
        "notes": {"type": "string", "maxLength": 800},
    },
}

REQUIREMENT_REVIEW_INSTRUCTION = (
    "You are an independent adversarial requirement reviewer. Re-read the complete [REGULATION] blocks "
    "yourself; do not trust the baseline JSON. The [BASELINE] is supplied only so you can identify what "
    "may have been missed; it is not evidence. Attack for: omitted requirements, omitted conditions, "
    "omitted exceptions, definition effects, cross-references, effective dates, transition arrangements, "
    "scope limits, wrong splitting of one rule into several, wrong merging of several rules into one, and "
    "any external instrument the text depends on but does not contain. Return missing requirements in the "
    "same shape as the extractor, with exact source quotes and block ids. Return corrections only when the "
    "regulation genuinely supports the corrected value. Assess every article group: covered, "
    "no_contract_relevance, or uncertain. Be concise; do not restate the whole regulation. Return JSON only."
)

INTENT_SCHEMA = {
    "type": "object",
    "required": ["intents"],
    "additionalProperties": False,
    "properties": {
        "intents": {
            "type": "array", "minItems": 1, "maxItems": 12,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["terms", "phrases", "section_hints", "business_actions", "rationale"],
                "properties": {
                    "terms": {"type": "array", "maxItems": 40, "items": {"type": "string"}},
                    "phrases": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "section_hints": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "business_actions": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                },
            },
        },
    },
}

INTENT_INSTRUCTION = (
    "Read the [REQUIREMENT]. Produce multiple independent contract-search intents. Cover the "
    "regulation's own terminology, real fund-contract terminology, likely synonyms, related business "
    "actions, related fees/rights/obligations, relevant contract sections, and relevant calculation or "
    "payment wording. Include terms that a contract might use even when it never uses the regulation's "
    "phrase. Optimise for recall, not precision: an intent may be broad. Do not invent legal rules. "
    "Return JSON only."
)

IMPACT_SWEEP_SCHEMA = {
    "type": "object",
    "required": ["findings"],
    "additionalProperties": False,
    "properties": {
        "findings": {
            "type": "array", "maxItems": 120,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["clause_ids", "requirement_ids", "impact_status", "reason"],
                "properties": {
                    "clause_ids": {"type": "array", "minItems": 1, "maxItems": 20,
                                   "items": {"type": "string"}},
                    "requirement_ids": {"type": "array", "minItems": 1, "maxItems": 20,
                                        "items": {"type": "string"}},
                    "impact_status": {"enum": ["definite", "possible", "unlikely"]},
                    "impact_dimensions": {"type": "array", "maxItems": 20,
                                          "items": {"type": "string"}},
                    "reason": {"type": "string", "minLength": 1},
                    "evidence_quote": {"type": "string", "minLength": 1},
                },
            },
        },
        "uncovered_suspicions": {
            "type": "array", "maxItems": 30,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["clause_ids", "reason"],
                "properties": {
                    "clause_ids": {"type": "array", "minItems": 1, "maxItems": 20,
                                   "items": {"type": "string"}},
                    "reason": {"type": "string", "minLength": 1},
                    "evidence_quote": {"type": "string"},
                },
            },
        },
        "section_assessment": {"enum": ["affected", "not_affected", "uncertain"]},
        "notes": {"type": "string"},
    },
}

IMPACT_SWEEP_INSTRUCTION = (
    "You are a high-recall contract impact discoverer. Read the [REQUIREMENTS] and the real contract "
    "clauses in [CONTRACT]. Clause ids are addresses, not text. For every clause that may need to change "
    "because of any requirement, return a finding with the clause ids, requirement ids, impact_status, "
    "impact dimensions, a reason grounded in the clause, and an exact evidence quote from the clause. "
    "Include possible impacts even when the link is indirect; do not silently drop an uncertain clause. "
    "If contract content looks like it may be affected by the regulation but no supplied requirement "
    "explains it, put it in uncovered_suspicions instead of inventing a requirement. If no clause in this "
    "batch is affected, return empty findings and section_assessment=not_affected. Do not rewrite the "
    "contract. Do not use wording from a different contract as a requirement. Return JSON only."
)

IMPACT_ADJUDICATE_SCHEMA = {
    "type": "object",
    "required": ["items"],
    "additionalProperties": False,
    "properties": {
        "items": {
            "type": "array", "maxItems": 80,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["impact_id", "impact_status"],
                "properties": {
                    "impact_id": {"type": "string"},
                    "impact_status": {"enum": ["definite", "possible", "unlikely"]},
                    "reason": {"type": "string"},
                    "guide_relevant": {"type": "boolean"},
                },
            },
        },
    },
}

IMPACT_ADJUDICATE_INSTRUCTION = (
    "Read each [IMPACT] against its [REQUIREMENT] and the quoted contract clause. Decide whether the "
    "clause is genuinely affected (definite), may be affected (possible), or is not affected (unlikely). "
    "Do not convert a genuine uncertainty into unlikely merely to reduce work. guide_relevant is true "
    "when the impact should be represented in a candidate modification guide, even if the eventual "
    "disposition is not_applicable. Return one item per impact id. Return JSON only."
)

LOCAL_CANDIDATE_SCHEMA = {
    "type": "object",
    "required": ["candidates"],
    "additionalProperties": False,
    "properties": {
        "candidates": {
            "type": "array", "minItems": 1, "maxItems": 20,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["impact_ids", "requirement_ids", "needs_modification"],
                "properties": {
                    "impact_ids": {"type": "array", "minItems": 1, "maxItems": 60,
                                   "items": {"type": "string"}},
                    "requirement_ids": {"type": "array", "minItems": 1, "maxItems": 30,
                                        "items": {"type": "string"}},
                    "clause_relation": {"enum": ["same_rule", "related_but_different", "not_related"]},
                    "needs_modification": {"enum": ["yes", "no", "uncertain"]},
                    "business_goal": {"type": "string"},
                    "semantic_changes": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "applicability": {"type": "string"},
                    "conditions": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "exceptions": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "old_text_patterns": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "new_text": {"type": "string"},
                    "new_text_origin": {"enum": ["regulation_verbatim", "model_drafted",
                                                 "contract_pattern_adapted"]},
                    "notes": {"type": "string"},
                },
            },
        },
    },
}

LOCAL_CANDIDATE_INSTRUCTION = (
    "Read the [REQUIREMENT] and the real [IMPACTS]. For each group of impacts that share one business "
    "meaning, answer: after this requirement takes effect, does this real contract text need a change? "
    "First set clause_relation. same_rule means the clause itself governs the same obligation, "
    "prohibition, permission or calculation as the requirement. related_but_different means it mentions "
    "a related fee or topic but governs a different obligation. not_related means no meaningful relation. "
    "A clause that merely mentions a related fee, a disclosure duty, a fund promoter activity, a "
    "governing-law mechanics clause, or a different fee is related_but_different or not_related; for "
    "either, set needs_modification=no and do not draft new text. If the clause already satisfies the "
    "requirement, set needs_modification=no. If the evidence is insufficient to decide, set "
    "needs_modification=uncertain and do not draft replacement text. Only when the clause genuinely needs "
    "a change should you state the business goal, the exact semantic elements to delete/add/replace, the "
    "applicability conditions, exceptions, representative old-text patterns, and a recommended Chinese "
    "contract expression. When the regulation has type-dependent caps or conditions (for example 0.4% for "
    "stock/mixed, 0.2% for index/bond, 0.15% for money market), and the clause does not prove the fund "
    "type, do not hard-code one cap: state the fund-type condition explicitly or set "
    "needs_modification=uncertain. Never append regulation sentences to an unrelated contract clause and "
    "never invent a new obligation: every new_text must be supported by the regulation; historical contracts are "
    "evidence of wording only. Mark new_text_origin as regulation_verbatim only when the text is copied "
    "verbatim from the regulation; contract_pattern_adapted when adapted from the real clause; otherwise "
    "model_drafted. Keep every impact id in a candidate so it remains traceable. Do not merge genuinely "
    "different business conditions into one candidate. Return JSON only."
)

MERGE_SCHEMA = {
    "type": "object",
    "required": ["families"],
    "additionalProperties": False,
    "properties": {
        "families": {
            "type": "array", "minItems": 1, "maxItems": 40,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["local_ids", "title", "instruction", "new_text"],
                "properties": {
                    "local_ids": {"type": "array", "minItems": 1, "maxItems": 120,
                                  "items": {"type": "string"}},
                    "title": {"type": "string", "minLength": 1},
                    "section": {"type": "string"},
                    "business_requirement": {"type": "string", "minLength": 1},
                    "instruction": {"type": "string", "minLength": 1},
                    "applicability": {"type": "string"},
                    "conditions": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "exceptions": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "old_text_patterns": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
                    "new_text": {"type": "string"},
                    "new_text_origin": {"enum": ["regulation_verbatim", "model_drafted",
                                                 "contract_pattern_adapted"]},
                    "merge_rationale": {"type": "string"},
                },
            },
        },
    },
}

MERGE_INSTRUCTION = (
    "Read the [LOCAL_CANDIDATES]. Group only candidates that share the same business meaning, "
    "applicability and conditions. Do not force a group: rare, singleton or genuinely different patterns "
    "must remain separate. Preserve every local id in exactly one family; if a local candidate should "
    "produce two guide items, keep two families and reference it twice only when the business content "
    "genuinely requires it. Generalise wording only when the regulation supports the generalisation; do "
    "not overfit or over-generalise. Return JSON only."
)

QUALITY_SCHEMA = {
    "type": "object",
    "required": ["verdict"],
    "additionalProperties": False,
    "properties": {
        "verdict": {"enum": ["pass", "pass_with_findings", "fail", "uncertain"]},
        "findings": {
            "type": "array", "maxItems": 40,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["category", "severity", "description"],
                "properties": {
                    "category": {"enum": ["regulation_fidelity", "draft_text_fidelity",
                                          "generalization", "internal_consistency",
                                          "provenance", "other"]},
                    "severity": {"enum": ["critical", "major", "minor", "info"]},
                    "description": {"type": "string", "minLength": 1},
                    "evidence_quote": {"type": "string"},
                    "recommendation": {"type": "string"},
                },
            },
        },
        "notes": {"type": "string"},
    },
}

QUALITY_INSTRUCTION = (
    "You are an adversarial guide reviewer, not the author. Read [COVERAGE_CONTEXT], the "
    "[REQUIREMENT] and the [GUIDE_ITEM]. Attack four areas. Regulation fidelity: did the guide "
    "expand, narrow, omit a condition/exception, use a wrong scope, or misstate the effective rule? "
    "Draft-text fidelity: does the proposed contract wording add/reduce an obligation, change the "
    "subject, condition, time, or drop an exception? Generalization: was the wording overfitted to "
    "the cited historical contracts or over-generalised beyond the regulation? Internal consistency: "
    "conflicts, duplicates, overlapping conditions, gaps, or broken evidence references. "
    "A critical finding is reserved for a concrete text-level error: a new obligation, prohibition "
    "or permission not supported by the regulation; a changed subject; a changed condition, time or "
    "numeric threshold; an omitted condition/exception that applies to the SAME scoped clause; or an "
    "invented quote/rate. Do NOT make a finding critical merely because: the item covers one aspect "
    "while sibling items cover other aspects; the item uses the contract's actual share classes "
    "(A/C/D); the item omits other fund types or 'other funds' that do not apply to the cited "
    "contract; the item does not restate the entire article; or the wording is stylistic. Put those "
    "in major/minor/info and explain the residual risk. If sibling items exist, review this item's "
    "own scope_statement and do not fail it for omitting an aspect assigned to a sibling. Cite exact "
    "source text in evidence_quote. A critical finding means the item must not be published as a "
    "candidate without human revision. Do not approve merely because the item is plausible. "
    "Return JSON only."
)

COVERAGE_SCHEMA = {
    "type": "object",
    "required": [],
    "additionalProperties": False,
    "properties": {
        "requirement_results": {
            "type": "array", "maxItems": 30,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["requirement_id", "status", "guide_item_ids", "reason"],
                "properties": {
                    "requirement_id": {"type": "string"},
                    "status": {"enum": ["covered", "disposed", "gap", "uncertain"]},
                    "guide_item_ids": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
        "impact_results": {
            "type": "array", "maxItems": 40,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["impact_id", "status", "guide_item_ids", "reason"],
                "properties": {
                    "impact_id": {"type": "string"},
                    "status": {"enum": ["covered", "false_positive", "not_applicable", "unresolved"]},
                    "guide_item_ids": {"type": "array", "maxItems": 30, "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
        "missing_topics": {"type": "array", "maxItems": 25,
                           "items": {"type": "object", "additionalProperties": False,
                                     "required": ["description", "requirement_ids", "evidence_quote"],
                                     "properties": {"description": {"type": "string"},
                                                    "requirement_ids": {"type": "array", "maxItems": 20,
                                                                        "items": {"type": "string"}},
                                                    "evidence_quote": {"type": "string"}}}},
        "notes": {"type": "string"},
    },
}

COVERAGE_INSTRUCTION = (
    "You are a semantic coverage auditor. The [REQUIREMENTS], [GUIDE_ITEMS] and [IMPACTS] are the "
    "current candidate set. Decide whether every requirement has a guide item or a genuine disposition, "
    "and whether every definite/possible impact is covered, a false positive, not applicable, or "
    "unresolved. A requirement that needs a contract change but has no guide item is a gap. A possible "
    "impact may not disappear: give it a final status. Also list missing topics that the current guide "
    "does not explain. Do not mark something covered because its wording is merely similar; it must "
    "express the same business rule and conditions. Only return entries that are gaps, unresolved, "
    "false positives, not applicable, or missing topics; do not enumerate every covered item. "
    "Be concise and return JSON only."
)

RESIDUAL_SCHEMA = {
    "type": "object",
    "required": ["uncovered"],
    "additionalProperties": False,
    "properties": {
        "uncovered": {
            "type": "array", "maxItems": 30,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["clause_ids", "requirement_ids", "reason", "pattern_description"],
                "properties": {
                    "clause_ids": {"type": "array", "minItems": 1, "maxItems": 20,
                                   "items": {"type": "string"}},
                    "requirement_ids": {"type": "array", "minItems": 1, "maxItems": 20,
                                        "items": {"type": "string"}},
                    "reason": {"type": "string", "minLength": 1, "maxLength": 400},
                    "evidence_quote": {"type": "string", "minLength": 1, "maxLength": 600},
                    "pattern_description": {"type": "string", "minLength": 1, "maxLength": 300},
                },
            },
        },
        "guide_conflicts": {
            "type": "array", "maxItems": 12,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["guide_item_id", "clause_ids", "reason", "evidence_quote"],
                "properties": {
                    "guide_item_id": {"type": "string"},
                    "clause_ids": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "reason": {"type": "string", "minLength": 1},
                    "evidence_quote": {"type": "string"},
                },
            },
        },
        "notes": {"type": "string"},
    },
}

RESIDUAL_INSTRUCTION = (
    "You are an independent residual-impact miner. Read the [REQUIREMENTS], the current [GUIDE_ITEMS] "
    "summary, and real [CONTRACT] clauses. Find contract content that is probably affected by a "
    "requirement but cannot be explained or covered by the current guide items. Also flag a guide item "
    "that would incorrectly modify a clause. Do not repeat an already-covered pattern; describe the "
    "distinct uncovered pattern. Do not invent requirements. If the guide is complete for this batch, "
    "return an empty uncovered list. Report only distinct uncovered patterns, at most one per "
    "business pattern; never enumerate every clause. Be concise and return JSON only."
)

APPLICABILITY_SCHEMA = {
    "type": "object",
    "required": ["verdict"],
    "additionalProperties": False,
    "properties": {
        "verdict": {"enum": ["covered", "not_covered", "not_applicable", "ambiguous"]},
        "reason": {"type": "string", "minLength": 1},
        "evidence_quote": {"type": "string"},
    },
}

APPLICABILITY_INSTRUCTION = (
    "You are a semantic applicability judge. Read the [REQUIREMENT], the candidate [GUIDE_ITEM], and "
    "one real [CONTRACT_CLAUSE]. Decide whether the guide's business rule would correctly cover this "
    "clause. covered means the guide identifies and handles the same business situation; not_covered "
    "means the requirement affects the clause but the guide cannot handle it; not_applicable means the "
    "requirement does not affect this clause; ambiguous means the evidence is insufficient. This is not "
    "a FundLex execution test. Return JSON only."
)

REPAIR_SCHEMA = {
    "type": "object",
    "required": ["title", "business_requirement", "instruction", "applicability",
                 "conditions", "exceptions", "old_text_patterns", "new_text", "new_text_origin"],
    "additionalProperties": False,
    "properties": {
        "title": {"type": "string", "minLength": 1},
        "business_requirement": {"type": "string", "minLength": 1},
        "instruction": {"type": "string", "minLength": 1},
        "applicability": {"type": "string"},
        "conditions": {"type": "array", "maxItems": 15, "items": {"type": "string"}},
        "exceptions": {"type": "array", "maxItems": 15, "items": {"type": "string"}},
        "old_text_patterns": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
        "new_text": {"type": "string", "minLength": 1},
        "new_text_origin": {"enum": ["regulation_verbatim", "model_drafted", "contract_pattern_adapted"]},
        "repair_notes": {"type": "string"},
    },
}

REPAIR_INSTRUCTION = (
    "You are repairing one candidate guide item after an independent review. Read the [REQUIREMENT], "
    "the [GUIDE_ITEM], the [REVIEW_FINDINGS] and the real contract evidence. Correct the identified "
    "text-level errors: restore a regulation floor instead of a fixed rate; remove an obligation or "
    "condition not supported by the regulation; fix a wrong subject; remove an inapplicable exception; "
    "or correct a mislabeled origin. Do not broaden the item's scope, do not invent a new obligation, and "
    "do not delete a valid existing contract protection. Keep the same impact ids and requirement ids. "
    "Return the complete repaired item. new_text must be a usable Chinese contract expression supported "
    "by the regulation and/or the cited contract clause. Return JSON only."
)

ENGINE_SCHEMA = {
    "type": "object",
    "required": ["results"],
    "additionalProperties": False,
    "properties": {
        "results": {
            "type": "array", "maxItems": 40,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["guide_item_id", "classification", "parsed_rule_ids", "reason"],
                "properties": {
                    "guide_item_id": {"type": "string"},
                    "classification": {"enum": ["expressible", "ENGINE_CAPABILITY_GAP",
                                                "ENGINE_LOCATE_GAP", "ENGINE_EDIT_GAP",
                                                "ENGINE_VERIFY_GAP", "GUIDE_AMBIGUOUS",
                                                "GUIDE_COVERAGE_GAP"]},
                    "parsed_rule_ids": {"type": "array", "maxItems": 20, "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
    },
}

ENGINE_INSTRUCTION = (
    "You are mapping candidate guide items to the existing FundLex execution representation. The "
    "[PARSED_RULES] were produced by the current guide parser from the exported DOCX. For each guide "
    "item decide whether a parsed rule expresses the same operation, condition and text. Distinguish a "
    "genuine guide defect (GUIDE_AMBIGUOUS, GUIDE_COVERAGE_GAP) from a limitation of the current engine "
    "or DSL (ENGINE_CAPABILITY_GAP, ENGINE_LOCATE_GAP, ENGINE_EDIT_GAP, ENGINE_VERIFY_GAP). Never mark a "
    "correct guide as wrong because the current engine cannot execute it. Return JSON only."
)
