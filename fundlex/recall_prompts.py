"""Versioned instructions and JSON schemas for the recall-first engine tasks.

Every schema is strict enough to catch malformed answers but never so strict that a
faithful answer fails. Quotes are validated by the engine module, not here.
"""
from __future__ import annotations

FACTS_PROMPT_VERSION = "recall_facts_v5"
SCOPE_PROMPT_VERSION = "recall_scope_v1"
INVENTORY_PROMPT_VERSION = "recall_inventory_v2"
COMPOSE_PROMPT_VERSION = "recall_compose_v1"
VERIFY_PROMPT_VERSION = "recall_verify_v1"
AUDIT_PROMPT_VERSION = "recall_audit_v3"
SWEEP_PROMPT_VERSION = "recall_sweep_v2"

PROMPT_VERSIONS = {
    "facts": FACTS_PROMPT_VERSION,
    "scope": SCOPE_PROMPT_VERSION,
    "inventory": INVENTORY_PROMPT_VERSION,
    "compose": COMPOSE_PROMPT_VERSION,
    "verify": VERIFY_PROMPT_VERSION,
    "audit": AUDIT_PROMPT_VERSION,
    "sweep": SWEEP_PROMPT_VERSION,
}

FUND_TYPES = ("open_regular", "etf", "money_market", "interbank_cd", "qdii", "reits", "other")

FACTS_SCHEMA = {
    "type": "object",
    "required": ["fund_type", "classes", "class_set_quote", "floating_management_fee"],
    "properties": {
        "class_set_quote": {"type": "string"},
        "fund_type": {
            "type": "object", "required": ["value", "quote"],
            "properties": {
                "value": {"enum": list(FUND_TYPES)},
                "quote": {"type": "string"},
                "basis": {"type": "string"},
            },
        },
        "classes": {
            "type": "array", "maxItems": 24,
            "items": {
                "type": "object",
                "required": ["name", "subscription_fee", "service_fee", "current", "quote"],
                "properties": {
                    "name": {"type": "string"},
                    "subscription_fee": {"type": "boolean"},
                    "service_fee": {"type": "boolean"},
                    "rate": {"type": "string"},
                    "current": {"type": "boolean"},
                    "quote": {"type": "string"},
                    "subscription_quote": {"type": "string"},
                    "service_quote": {"type": "string"},
                },
            },
        },
        "floating_management_fee": {
            "type": "object", "required": ["value", "quote"],
            "properties": {
                "value": {"type": "boolean"},
                "quote": {"type": "string"},
                "basis": {"type": "string"},
            },
        },
        "direct_sales_exempt": {
            "type": "object",
            "properties": {
                "classes": {"type": "array", "maxItems": 24, "items": {"type": "string"}},
                "quote": {"type": "string"},
                "basis": {"type": "string"},
            },
        },
        "other_sales_charged": {
            "type": "object",
            "properties": {
                "classes": {"type": "array", "maxItems": 24, "items": {"type": "string"}},
                "quote": {"type": "string"},
                "basis": {"type": "string"},
            },
        },
        "notes": {"type": "string"},
    },
}

FACTS_INSTRUCTION = (
    "Read [CONTRACT_SOURCE]; the [loc] markers are stable paragraph addresses, not part of the text. "
    "Extract the product's fee and qualification facts. fund_type value: open_regular for an ordinary "
    "open-ended fund contract; etf for an exchange-traded fund itself; a fund whose contract describes "
    "it as a feeder (联接基金) of an ETF is an ordinary open-ended fund (open_regular), not etf; "
    "money_market; interbank_cd; qdii for a "
    "qualified-domestic-institutional-investor fund; reits for a closed-end infrastructure or "
    "commercial real-estate (不动产) fund, including REITs; other only when none fits. A future "
    "possibility (for example text saying the fund may later "
    "convert to an ETF feeder) never changes the current fund_type. classes lists the share classes the "
    "contract currently sets up, one entry per class letter or currency variant: subscription_fee is true "
    "when investors pay a subscription/purchase fee for that class, service_fee is true when a sales "
    "service fee is accrued from that class's assets; current is false for a class the contract only "
    "permits to be added in the future. class_set_quote must copy the COMPLETE current-class "
    "enumeration sentence (for example 本基金将基金份额分为A类、C类和E类不同的类别). "
    "It must prove the entire set, not just some members. Do not truncate or use ellipses; "
    "return an empty quote when the complete set cannot be proven. Every quote must be an exact contiguous copy from "
    "[CONTRACT_SOURCE] and must directly support the value it is attached to. When subscription and "
    "service fee evidence is in different paragraphs, provide subscription_quote and service_quote "
    "separately for that class; each must directly prove its own boolean. An absent fee mention is not "
    "proof of false. A management-fee quote proves neither subscription nor service fee. Never infer a class letter "
    "from habit: read the actual fee clauses. floating_management_fee is true only when the contract ties "
    "management fee to investor holding period or performance (contingent management fee returned to "
    "investors or excess management fee deducted); an ordinary fixed management fee is false. "
    "direct_sales_exempt lists the share classes the contract says are NOT charged a subscription fee when "
    "purchased through the direct channel (直销机构), with a quote; other_sales_charged lists the classes "
    "the contract says ARE charged a subscription fee through other sales agencies, with a quote. When the "
    "contract states no such channel rule for any class, return empty lists with an empty quote — never "
    "guess a class letter or infer a rule the contract does not state."
)

SCOPE_SCHEMA = {
    "type": "object",
    "required": ["mappings"],
    "properties": {
        "mappings": {
            "type": "array", "maxItems": 60,
            "items": {
                "type": "object",
                "required": ["rule_id", "section_ids", "reason"],
                "properties": {
                    "rule_id": {"type": "string"},
                    "section_ids": {"type": "array", "maxItems": 12, "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
            },
        },
        "notes": {"type": "string"},
    },
}

SCOPE_INSTRUCTION = (
    "Read [GUIDE_RULES] and [CONTRACT_STRUCTURE]. For every rule decide which contract sections may "
    "contain its targets. Section ids come from [CONTRACT_STRUCTURE]; a section may be chosen for "
    "several rules and a rule may need several sections (for example both the definition chapter and the "
    "fund-basics chapter, or both a main clause and the contract summary). Chapters are navigation only: "
    "never drop a plausible section because the rule's hint names a different chapter. Choose every "
    "section that could contain the business clause, including the summary section when the rule has a "
    "summary counterpart. Return one mapping per rule with a short reason. An empty section_ids list is "
    "allowed only when no section could contain the rule."
)

INVENTORY_SCHEMA = {
    "type": "object",
    "required": ["targets"],
    "properties": {
        "targets": {
            "type": "array", "maxItems": 60,
            "items": {
                "type": "object",
                "required": ["rule_id", "location", "quote", "state", "reason"],
                "properties": {
                    "rule_id": {"type": "string"},
                    "location": {"type": "string"},
                    "quote": {"type": "string"},
                    "state": {"enum": ["needs_edit", "satisfied", "absent"]},
                    "reason": {"type": "string"},
                    "operation_id": {"type": "string"},
                    "obligation_id": {"type": "string"},
                    "site_id": {"type": "string"},
                },
            },
        },
        "notes": {"type": "string"},
    },
}

INVENTORY_INSTRUCTION = (
    "Read [CONTRACT_WINDOW] (the [loc] markers are stable paragraph addresses) together with "
    "[GUIDE_RULES] and [FACTS]. For every rule, report every location in this window where the rule's "
    "business clause exists or is required. A rule may list several operations (a replacement, a "
    "deletion, an append, or a branch selected by the facts): report a separate target for each "
    "operation that applies in this window and quote the exact text that operation targets; never merge "
    "two operations into one target and never skip an operation because another one already has a "
    "target. For every target also copy the operation identity from [GUIDE_RULES] "
    "(`operation_id`, for example G05:1, and `obligation_id` when shown) so coverage can "
    "be tracked per obligation instead of being guessed later from the quote. The same "
    "clause often appears twice — once in a main chapter and once in the contract "
    "summary — so report each occurrence as its own target instead of assuming one edit covers both. "
    "state=needs_edit when the clause exists but does not yet "
    "meet the rule; state=satisfied when the clause already meets the rule (including wording different "
    "from the guide's reference text); state=absent only when you are certain this window contains no "
    "such clause and no place to add it. quote must be an exact contiguous copy from the window at the "
    "given location: for a replace or delete requirement quote the exact text the operation targets; for "
    "an append requirement quote the sentence after which the new content belongs. Read the whole window "
    "before answering; never answer from a keyword alone. Do not invent locations and do not report the "
    "same clause twice for the same rule and operation."
)

COMPOSE_SCHEMA = {
    "type": "object",
    "required": ["replacement", "preserved", "basis"],
    "properties": {
        "replacement": {"type": "string"},
        "preserved": {"type": "array", "maxItems": 12, "items": {"type": "string"}},
        "basis": {"type": "string"},
    },
}

COMPOSE_INSTRUCTION = (
    "Read [CONTRACT_TARGET] (the actual contract text to be rewritten), [GUIDE_OPERATION] (the guide's "
    "requirement, the reference old text and the fixed policy text) and [FACTS]. Produce the replacement "
    "text for exactly this target span. The fixed policy text given in [GUIDE_OPERATION] must appear in "
    "the replacement verbatim (with share-class slots already instantiated as instructed in the context). "
    "Keep every other element of the target span that the guide does not require changing, especially "
    "fee formulas, calculation rules, rates and conditions; list those kept elements in preserved. Never "
    "add policy, numbers or promises the guide does not state. Write plain Chinese contract text only, no "
    "markdown, no quotes around the whole answer."
)

COMPOSE_DELETE_INSTRUCTION = (
    "Read [CONTRACT_TARGET] (the actual contract text that must be deleted or trimmed) and "
    "[GUIDE_OPERATION] (the guide's deletion requirement with its reference text). Produce the "
    "replacement for exactly this target span: remove the content the guide requires to be deleted and "
    "keep, unchanged, any other content inside the span that the guide does not ask to remove. Return an "
    "empty replacement when the whole span is deleted. Never add policy, numbers or promises, and never "
    "reword the kept content; list what you kept in preserved. Write plain Chinese contract text only, no "
    "markdown, no quotes around the whole answer."
)

VERIFY_SCHEMA = {
    "type": "object",
    "required": ["verdict", "reason"],
    "properties": {
        "verdict": {"enum": ["pass", "fail"]},
        "reason": {"type": "string"},
    },
}

#: V3 independent semantic critic (plan v4 §13): only the questions code cannot
#: prove. Numbers, class coverage and boundary checks are verified by V1/V2 and
#: must not be repeated here.
VERIFY_INSTRUCTION = (
    "Read [BEFORE] (the contract text that was rewritten), [AFTER] (the proposed replacement), "
    "[GUIDE_OPERATION] and [FACTS]. Answer only what cannot be proven mechanically: (1) does AFTER carry "
    "out the guide requirement in business meaning — paraphrasing is allowed, exact wording is not "
    "required; (2) does it keep the parts of BEFORE the guide does not authorize changing; (3) does it "
    "avoid obligations, promises or content the guide does not state. Do NOT re-check numbers, share-class "
    "letters or the text outside the span — those are verified separately. Reply verdict=pass only when "
    "all three hold; otherwise verdict=fail with one short reason."
)

AUDIT_SCHEMA = {
    "type": "object",
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array", "maxItems": 60,
            "items": {
                "type": "object",
                "required": ["target_id", "verdict", "reason"],
                "properties": {
                    "target_id": {"type": "string"},
                    "verdict": {"enum": ["completed", "incomplete", "wrong"]},
                    "reason": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                    "failure_class": {"enum": ["FACT", "APPLICABILITY", "TARGET",
                                               "GENERATION", "EXECUTION",
                                               "VERIFICATION"]},
                    "affected_fact": {"type": "string"},
                    "affected_obligation": {"type": "string"},
                },
            },
        },
        "missed_targets": {
            "type": "array", "maxItems": 20,
            "items": {
                "type": "object",
                "required": ["rule_id", "location", "quote", "reason"],
                "properties": {
                    "rule_id": {"type": "string"},
                    "location": {"type": "string"},
                    "quote": {"type": "string"},
                    "reason": {"type": "string"},
                },
            },
        },
        "notes": {"type": "string"},
    },
}

AUDIT_INSTRUCTION = (
    "Read [BEFORE] (the original contract region), [AFTER] (the actual rewritten region taken from the "
    "produced file), [REQUIREMENTS] (the guide rules with their fixed policy text and the target "
    "ledger) and [OTHER_AUTHORIZED_EDITS] (changes other guide rules legitimately made in the same "
    "locations). Independently judge each target in the ledger: completed when the AFTER text satisfies "
    "the requirement with no lost content, incomplete when part of the requirement is missing, wrong "
    "when the AFTER text contradicts the requirement, drops required content, or adds policy the guide "
    "does not state. A rule whose slot classes are placeholders means the AFTER text must name the "
    "product's actual share classes that fall in that group: adding a real class the contract defines "
    "(for example including a D类 class in the group the guide wrote as A类) is correct instantiation, "
    "not an unauthorized addition, as long as [FACTS] lists that class in the group. "
    "[APPLICABLE_POLICIES] supplies each operation's condition status and instantiated new text. "
    "When policy_status is READY, review that applicable text against AFTER while retaining all "
    "other source-preservation requirements. If verified facts prove there is no service-fee class, "
    "the guide's C-class service-fee component is inapplicable; never require a nonexistent class "
    "or the omitted component. UNRESOLVED policies or UNKNOWN/CONFLICT fee facts are not certified "
    "absence and cannot justify omitting a component; report a FACT or APPLICABILITY failure when "
    "they prevent a verdict. These entries authorize policy only: read AFTER independently and "
    "do not treat READY as proof that the policy was applied. Never report an "
    "OTHER_AUTHORIZED_EDITS change as an unauthorized addition. For every non-completed "
    "target also classify the root cause (failure_class) and, when known, the affected_fact "
    "or affected_obligation, so recovery can return to the correct business layer. A region "
    "shown as （该位置内容已删除） means the content was removed: for a deletion requirement that is "
    "completed, and for a replacement requirement judge it against the requirement and the ledger, not "
    "against the absence itself. Cite an exact contiguous evidence_quote from AFTER (or BEFORE when "
    "judging a loss) for every verdict. Also report missed_targets when you find a clause in AFTER that "
    "still needs editing but is absent from the ledger. Never trust the ledger over the actual text; "
    "never mark completed without reading AFTER."
)

SWEEP_SCHEMA = {
    "type": "object",
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array", "maxItems": 40,
            "items": {
                "type": "object",
                "required": ["rule_id", "location", "quote", "issue"],
                "properties": {
                    "rule_id": {"type": "string"},
                    "location": {"type": "string"},
                    "quote": {"type": "string"},
                    "issue": {"enum": ["residual_old_text", "missing_new_text", "wrong_text",
                                       "unaddressed_requirement"]},
                    "reason": {"type": "string"},
                    "failure_class": {"enum": ["FACT", "APPLICABILITY", "TARGET",
                                               "GENERATION", "EXECUTION",
                                               "VERIFICATION"]},
                },
            },
        },
        "notes": {"type": "string"},
    },
}

SWEEP_INSTRUCTION = (
    "Read [GUIDE_REQUIREMENTS] (the complete authorization), [FACTS] (the product's actual share-class "
    "and fee facts) and [ARTIFACT_WINDOW] (a chunk of the rewritten contract with [loc] paragraph "
    "addresses). Find every place in this chunk where a guide requirement is still unmet: an old clause "
    "that should have been replaced or deleted but survives, a required new clause that is missing, a "
    "rewritten clause that contradicts the guide, or a business clause the guide clearly covers but that "
    "was never addressed. Judge semantically against [FACTS]: when a clause already satisfies the "
    "requirement — including wording that differs from the guide's reference, class names already "
    "instantiated for the actual classes, or a substitution that is a no-op because the actual class "
    "group is unchanged — do NOT report it. When a rule's condition is not met by [FACTS] (for example a "
    "single-class branch on a multi-class product, or a floating-fee branch on a fixed-fee product), do "
    "NOT report it either. Every finding must be a real unmet requirement: the quoted text must be the "
    "clause that still needs work, and your reason must state which part of the requirement is missing "
    "or which old text survives. Never report a clause that already carries out the requirement, and "
    "never report a clause whose own reason says the requirement is met. Output only unmet requirements. "
    "quote must be an exact contiguous copy from the chunk. Report "
    "only real, checkable findings; do not report style preferences. Use the ledger excerpt only to avoid "
    "duplicate reports, never as a reason to skip reading the chunk."
)
