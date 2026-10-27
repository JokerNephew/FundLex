"""Multi-path high-recall impact discovery.

Path A is requirement-centric retrieval.  Path B is an independent
contract-centric semantic sweep in which the model reads real contract clauses
and is asked which requirements may affect them.  Path C optionally repeats the
sweep with a different discovery model.  Paths are unioned, never intersected;
cheap retrieval never gets the final say on whether a clause is affected.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from .lexical import LexicalIndex, Query, deterministic_query, query_from_intents
from ..model import ModelError
from .models import (
    ClauseUnit,
    ContractVersion,
    ImpactCandidate,
    PolicyRequirement,
    compact_for_match,
    quote_in_text,
    sha256_json,
    stable_id,
    unique,
)
from .prompts import (
    IMPACT_ADJUDICATE_INSTRUCTION,
    IMPACT_ADJUDICATE_SCHEMA,
    IMPACT_ADJUDICATE_VERSION,
    IMPACT_SWEEP_INSTRUCTION,
    IMPACT_SWEEP_SCHEMA,
    IMPACT_SWEEP_VERSION,
    INTENT_INSTRUCTION,
    INTENT_SCHEMA,
    INTENT_VERSION,
)

DIMENSION_TERMS = (
    "费率", "认购", "申购", "赎回", "销售服务费", "计提", "支付", "基金财产",
    "持有期限", "七日", "份额类别", "直销", "销售机构", "公告", "备案", "计算",
)


@dataclass
class DiscoveryConfig:
    path_a_top_k: int = 30
    path_a_per_contract: int = 1
    path_a_max_candidates: int = 60
    path_a_max_intent_calls: int = 12
    path_b_batch_chars: int = 12000
    path_b_latest_only: bool = True
    path_b_max_calls: int = 4000
    path_c_enabled: bool = True
    path_c_max_calls: int = 240
    adjudicate_lexical: bool = True
    adjudicate_batch: int = 20


@dataclass
class DiscoveryResult:
    impacts: list[ImpactCandidate]
    uncovered_suspicions: list[dict[str, Any]]
    search_intents: dict[str, list[dict]] = field(default_factory=dict)
    sweep_batches: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0
    path_c_status: str = "not_configured"
    notes: list[str] = field(default_factory=list)


def _requirement_brief(requirement: PolicyRequirement, *, compact: bool = False) -> str:
    if compact:
        conditions = "; ".join(requirement.conditions[:4])[:160]
        exceptions = "; ".join(requirement.exceptions[:4])[:160]
        return (f"- {requirement.requirement_id} [{requirement.article}] "
                f"{requirement.requirement[:260]}"
                + (f" | cond={conditions}" if conditions else "")
                + (f" | exc={exceptions}" if exceptions else ""))
    return (f"- {requirement.requirement_id} [{requirement.article}] {requirement.requirement}\n"
            f"  subject={requirement.subject}; object={requirement.object}; "
            f"conditions={requirement.conditions}; exceptions={requirement.exceptions}; "
            f"domains={requirement.candidate_contract_domains}")


def _requirements_context(requirements: Iterable[PolicyRequirement], *, compact: bool = False) -> str:
    return "\n".join(_requirement_brief(item, compact=compact) for item in requirements)


def _compact_clause(clause: ClauseUnit, *, max_chars: int = 0) -> str:
    text = clause.text
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "…"
    path = " > ".join(clause.section_path[-3:])
    return f"[{clause.clause_id}] section={path}\n{text}"


def _batches(clauses: list[ClauseUnit], max_chars: int) -> list[list[ClauseUnit]]:
    batches: list[list[ClauseUnit]] = []
    current: list[ClauseUnit] = []
    size = 0
    for clause in clauses:
        piece = len(clause.text) + len(clause.clause_id) + 80
        if current and size + piece > max_chars:
            batches.append(current)
            current = []
            size = 0
        current.append(clause)
        size += piece
    if current:
        batches.append(current)
    return batches


def _clauses_by_contract(store, version_ids: Iterable[str]) -> dict[str, list[ClauseUnit]]:
    return {version_id: store.get_clauses(version_id) for version_id in version_ids}


def _make_impact(requirement_id: str, version_id: str, clause_ids: list[str],
                 source_text: str, context: str, status: str, dimensions: list[str],
                 reason: str, source: str) -> ImpactCandidate:
    impact_id = stable_id("IC", requirement_id, version_id, ",".join(sorted(clause_ids)), length=20)
    return ImpactCandidate(
        impact_id=impact_id, requirement_id=requirement_id, contract_version_id=version_id,
        clause_ids=sorted(set(clause_ids)), source_text=source_text, context=context,
        impact_status=status, impact_dimensions=unique(dimensions), impact_reason=reason,
        discovery_sources=[source],
    )


def _merge_impacts(items: Iterable[ImpactCandidate]) -> list[ImpactCandidate]:
    rank = {"unlikely": 0, "possible": 1, "definite": 2}
    merged: dict[str, ImpactCandidate] = {}
    for item in items:
        key = item.impact_id
        if key not in merged:
            merged[key] = item
            continue
        current = merged[key]
        current.discovery_sources = unique(current.discovery_sources + item.discovery_sources)
        current.impact_dimensions = unique(current.impact_dimensions + item.impact_dimensions)
        if rank.get(item.impact_status, 0) > rank.get(current.impact_status, 0):
            current.impact_status = item.impact_status
        if not current.impact_reason and item.impact_reason:
            current.impact_reason = item.impact_reason
        current.source_text = current.source_text or item.source_text
        current.context = current.context or item.context
    return sorted(merged.values(), key=lambda item: (item.requirement_id, item.contract_version_id,
                                                     item.impact_id))


def _intents_for_requirement(router, requirement: PolicyRequirement) -> tuple[list[dict], int]:
    context = f"[REQUIREMENT]\n{_requirement_brief(requirement)}"
    try:
        result = router.call(task_type="guide_intent", bounded_context=context,
                             response_schema=INTENT_SCHEMA, instruction=INTENT_INSTRUCTION,
                             prompt_version=INTENT_VERSION, role="discovery")
        return list(result.value.get("intents") or []), 1
    except ModelError as exc:
        if str(exc.code).startswith("GUIDE_RUN_") or str(exc.code).startswith("MODEL_COST_BUDGET"):
            raise
        return [], 0
    except Exception:
        return [], 0


def path_a_requirement_retrieval(router, store, requirements: list[PolicyRequirement],
                                 clauses: list[ClauseUnit], config: DiscoveryConfig,
                                 *, run_id: str = "") -> tuple[list[ImpactCandidate], dict[str, list[dict]], int, list[str]]:
    index = LexicalIndex(clauses)
    impacts: list[ImpactCandidate] = []
    intents_by_requirement: dict[str, list[dict]] = {}
    calls = 0
    notes: list[str] = []
    intent_calls = 0
    for requirement in requirements:
        if requirement.disposition not in {"modify_contract", "uncertain", "needs_external_baseline"}:
            continue
        intents: list[dict] = []
        if intent_calls < config.path_a_max_intent_calls:
            intents, used = _intents_for_requirement(router, requirement)
            intent_calls += used
            calls += used
        if not intents:
            intents_by_requirement[requirement.requirement_id] = []
            query = deterministic_query(requirement)
            notes.append(f"{requirement.requirement_id}: deterministic query used")
        else:
            intents_by_requirement[requirement.requirement_id] = intents
            query = query_from_intents(requirement, intents)
        hits = index.search(query, top_k=config.path_a_top_k,
                            per_contract=config.path_a_per_contract,
                            max_candidates=config.path_a_max_candidates)
        # Retrieval is a discovery aid, not proof of impact.  Keep hits that
        # contain at least one requirement-specific term or phrase; the full
        # contract-centric sweep independently covers the whole corpus.
        strong_terms = [value for value in (
            [requirement.subject, requirement.object]
            + requirement.conditions + requirement.exceptions
            + requirement.candidate_contract_domains)
            if value and len(value) >= 2 and value not in {"基金", "基金合同"}]
        kept = 0
        for hit in hits:
            clause = clauses[hit.clause_index]
            compact_text = compact_for_match(clause.text)
            matched = [term for term in strong_terms if compact_for_match(term) in compact_text]
            if not matched and not any(compact_for_match(phrase) in compact_text
                                       for phrase in query.phrases if phrase):
                continue
            impacts.append(_make_impact(
                requirement.requirement_id, clause.contract_version_id, [clause.clause_id],
                clause.text, " > ".join(clause.section_path[-3:]),
                "possible", [], "词法/意图检索命中：" + ",".join((hit.reasons[:4] + matched)[:6]),
                "lexical"))
            kept += 1
            if kept >= config.path_a_max_candidates:
                break
    return _merge_impacts(impacts), intents_by_requirement, calls, notes


def _sweep_prompt_context(requirements: list[PolicyRequirement], contract: ContractVersion,
                          clauses: list[ClauseUnit]) -> str:
    return (
        "[REQUIREMENTS]\n" + _requirements_context(requirements, compact=True) +
        "\n\n[CONTRACT]\n"
        f"contract_version_id={contract.contract_version_id}\n"
        f"fund={contract.fund_identity}\nversion_date={contract.version_date}\n"
        f"latest_known={contract.latest_known_version}\n"
        "Clause ids in square brackets are addresses, not legal text.\n\n"
        + "\n\n".join(_compact_clause(clause) for clause in clauses)
    )


def _validate_sweep(value: dict[str, Any], clauses: list[ClauseUnit]) -> tuple[list[dict], list[dict], str]:
    by_id = {clause.clause_id: clause for clause in clauses}
    findings: list[dict] = []
    for item in value.get("findings") or []:
        ids = [str(cid) for cid in item.get("clause_ids") or [] if str(cid) in by_id]
        if not ids:
            continue
        quote = str(item.get("evidence_quote") or "")
        text = "\n".join(by_id[cid].text for cid in ids)
        if quote and not quote_in_text(quote, text):
            continue
        findings.append({**item, "clause_ids": ids})
    suspicions: list[dict] = []
    for item in value.get("uncovered_suspicions") or []:
        ids = [str(cid) for cid in item.get("clause_ids") or [] if str(cid) in by_id]
        if not ids:
            continue
        quote = str(item.get("evidence_quote") or "")
        text = "\n".join(by_id[cid].text for cid in ids)
        if quote and not quote_in_text(quote, text):
            continue
        suspicions.append({**item, "clause_ids": ids})
    return findings, suspicions, str(value.get("section_assessment") or "uncertain")


def _sweep_one(router, requirements, contract, batch, config, instruction, prompt_version, role):
    context = _sweep_prompt_context(requirements, contract, batch)
    try:
        result = router.call(task_type="guide_impact_sweep", bounded_context=context,
                             response_schema=IMPACT_SWEEP_SCHEMA,
                             instruction=instruction, prompt_version=prompt_version,
                             role=role)
    except ModelError as exc:
        if str(exc.code).startswith("GUIDE_RUN_") or str(exc.code).startswith("MODEL_COST_BUDGET"):
            raise
        return "model_error", type(exc).__name__, [], [], None
    except Exception as exc:
        return "model_error", type(exc).__name__, [], [], None
    findings, suspicions, assessment = _validate_sweep(result.value, batch)
    return "ok", "", findings, suspicions, assessment


def path_b_contract_sweep(router, store, requirements: list[PolicyRequirement],
                          versions: list[ContractVersion], clauses_by_version: dict[str, list[ClauseUnit]],
                          config: DiscoveryConfig, *, run_id: str = "",
                          instruction: str = IMPACT_SWEEP_INSTRUCTION,
                          prompt_version: str = IMPACT_SWEEP_VERSION,
                          role: str = "discovery",
                          max_calls: int | None = None,
                          max_workers: int = 4) -> tuple[list[ImpactCandidate], list[dict], list[dict], int]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    impacts: list[ImpactCandidate] = []
    suspicions: list[dict] = []
    batch_evidence: list[dict] = []
    calls = 0
    limit = config.path_b_max_calls if max_calls is None else max_calls
    jobs = []
    for contract in versions:
        clauses = clauses_by_version.get(contract.contract_version_id) or []
        if not clauses:
            continue
        for batch in _batches(clauses, config.path_b_batch_chars):
            if len(jobs) >= limit:
                break
            jobs.append((contract, batch))
        if len(jobs) >= limit:
            break
    if not jobs:
        return [], [], [], 0

    def run_jobs(work):
        nonlocal calls
        failed = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(work)))) as executor:
            futures = {
                executor.submit(_sweep_one, router, requirements, contract, batch, config,
                                instruction, prompt_version, role): (contract, batch)
                for contract, batch in work
            }
            for future in as_completed(futures):
                contract, batch = futures[future]
                try:
                    status, error, findings, found_suspicions, assessment = future.result()
                except ModelError:
                    raise
                calls += 1
                if status != "ok":
                    failed.append((contract, batch))
                    batch_evidence.append({
                        "contract_version_id": contract.contract_version_id,
                        "clause_ids": [clause.clause_id for clause in batch],
                        "status": "model_error", "error": error,
                    })
                    continue
                _collect_sweep_results(contract, batch, findings, found_suspicions, assessment,
                                       impacts, suspicions, batch_evidence, role, prompt_version)
        return failed

    def _collect_sweep_results(contract, batch, findings, found_suspicions, assessment,
                               impacts, suspicions, batch_evidence, role, prompt_version):
        by_id = {clause.clause_id: clause for clause in batch}
        for item in findings:
            ids = item["clause_ids"]
            text = "\n".join(by_id[cid].text for cid in ids)
            impacts.append(_make_impact(
                requirement_id=str(item.get("requirement_ids", [""])[0]),
                version_id=contract.contract_version_id, clause_ids=ids,
                source_text=text, context=" > ".join(by_id[ids[0]].section_path[-3:]),
                status=str(item.get("impact_status") or "possible"),
                dimensions=[str(value) for value in item.get("impact_dimensions") or []],
                reason=str(item.get("reason") or ""),
                source="contract_semantic_sweep" if role == "discovery" else "alternative_model_sweep",
            ))
        for item in found_suspicions:
            suspicions.append({**item, "contract_version_id": contract.contract_version_id,
                               "discovery_source": role})
        batch_evidence.append({
            "contract_version_id": contract.contract_version_id,
            "clause_ids": [clause.clause_id for clause in batch],
            "status": assessment,
            "finding_count": len(findings),
            "prompt_version": prompt_version,
        })

    failed = run_jobs(jobs)
    if failed:
        # One bounded retry after a schema/network failure; never unbounded.
        retry_failed = run_jobs(failed[:min(len(failed), config.path_b_max_calls)])
        if retry_failed:
            for contract, batch in retry_failed:
                batch_evidence.append({
                    "contract_version_id": contract.contract_version_id,
                    "clause_ids": [clause.clause_id for clause in batch],
                    "status": "uncertain", "error": "MODEL_RETRY_EXHAUSTED",
                })
    return _merge_impacts(impacts), suspicions, batch_evidence, calls

def _adjudicate_one(router, batch, requirements, clauses_by_id):
    lines = []
    for item in batch:
        requirement = requirements.get(item.requirement_id)
        clause = clauses_by_id.get(item.clause_ids[0]) if item.clause_ids else None
        if not requirement or not clause:
            continue
        lines.append(
            f"[IMPACT id={item.impact_id}]\n"
            f"[REQUIREMENT {requirement.requirement_id}] {requirement.requirement}\n"
            f"[CLAUSE {clause.clause_id}] {clause.text[:1800]}\n"
            f"initial_status={item.impact_status}; lexical_reason={item.impact_reason}")
    if not lines:
        return [], 0
    context = "\n\n".join(lines)
    try:
        result = router.call(task_type="guide_impact_adjudicate", bounded_context=context,
                             response_schema=IMPACT_ADJUDICATE_SCHEMA,
                             instruction=IMPACT_ADJUDICATE_INSTRUCTION,
                             prompt_version=IMPACT_ADJUDICATE_VERSION,
                             role="discovery")
    except ModelError as exc:
        if str(exc.code).startswith("GUIDE_RUN_") or str(exc.code).startswith("MODEL_COST_BUDGET"):
            raise
        return [], 0
    except Exception:
        return [], 0
    return list(result.value.get("items") or []), 1


def adjudicate_lexical_impacts(router, store, impacts: list[ImpactCandidate], requirements: dict[str, PolicyRequirement],
                               clauses_by_id: dict[str, ClauseUnit], config: DiscoveryConfig,
                               *, max_workers: int = 4) -> tuple[list[ImpactCandidate], int]:
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if not config.adjudicate_lexical:
        return impacts, 0
    lexical = [item for item in impacts if item.discovery_sources == ["lexical"]]
    if not lexical:
        return impacts, 0
    batches = [lexical[start:start + config.adjudicate_batch]
               for start in range(0, len(lexical), config.adjudicate_batch)]
    calls = 0
    changed: dict[str, ImpactCandidate] = {}
    by_id = {item.impact_id: item for item in impacts}
    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(batches) or 1))) as executor:
        futures = [executor.submit(_adjudicate_one, router, batch, requirements, clauses_by_id)
                   for batch in batches]
        for future in as_completed(futures):
            items, used = future.result()
            calls += used
            for item in items:
                impact = by_id.get(str(item.get("impact_id") or ""))
                if not impact:
                    continue
                if item.get("impact_status") in {"definite", "possible", "unlikely"}:
                    impact.impact_status = item["impact_status"]
                if item.get("reason"):
                    impact.impact_reason = (impact.impact_reason + "；复核：" + str(item["reason"])).strip("；")
                changed[impact.impact_id] = impact
    return list(by_id.values()), calls

def _best_requirement_anchor(requirement: PolicyRequirement,
                              clauses: list[ClauseUnit]) -> ClauseUnit | None:
    terms = [value for value in (
        [requirement.subject, requirement.object] + requirement.candidate_contract_domains
        + requirement.conditions + requirement.exceptions)
        if value and len(value) >= 2]
    best = None
    best_score = -1
    for clause in clauses:
        text = compact_for_match(clause.text)
        score = sum(1 for term in terms if compact_for_match(term) in text)
        section = " ".join(clause.section_path)
        score += sum(1 for domain in requirement.candidate_contract_domains
                     if domain and compact_for_match(domain) in compact_for_match(section))
        if score > best_score:
            best, best_score = clause, score
    if best is None:
        return None
    return best


def discover(router, store, requirements: list[PolicyRequirement], snapshot,
             versions: list[ContractVersion], *, run_id: str = "",
             config: DiscoveryConfig | None = None) -> DiscoveryResult:
    config = config or DiscoveryConfig()
    latest_ids = set(snapshot.latest_version_ids)
    selected = [item for item in versions if (not config.path_b_latest_only or item.contract_version_id in latest_ids)]
    clauses_by_version = _clauses_by_contract(store, [item.contract_version_id for item in versions])
    all_clauses = [clause for version_id in [item.contract_version_id for item in versions]
                   for clause in clauses_by_version.get(version_id, [])]
    clauses_by_id = {clause.clause_id: clause for clause in all_clauses}
    path_a, intents, calls_a, notes = path_a_requirement_retrieval(
        router, store, requirements, all_clauses, config, run_id=run_id)
    path_b, suspicions, batches, calls_b = path_b_contract_sweep(
        router, store, requirements, selected, clauses_by_version, config, run_id=run_id)
    all_impacts = _merge_impacts(path_a + path_b)
    calls = calls_a + calls_b
    path_c_status = "not_configured"
    identity = router.identity()
    author_model = identity.get("guide_author", {}).get("model", "")
    discovery_model = identity.get("discovery", {}).get("model", "")
    if config.path_c_enabled and discovery_model and author_model and discovery_model != author_model:
        # Independent alternative-model sweep over batches that the first sweep
        # marked not_affected.  It is a separate discovery path, not a filter.
        negative = [item for item in batches if item.get("status") == "not_affected"]
        negative_versions = []
        seen = set()
        for item in negative:
            version_id = item.get("contract_version_id")
            if version_id and version_id not in seen:
                seen.add(version_id)
                negative_versions.append(next((v for v in selected if v.contract_version_id == version_id), None))
        negative_versions = [item for item in negative_versions if item]
        alt, alt_suspicions, alt_batches, calls_c = path_b_contract_sweep(
            router, store, requirements, negative_versions, clauses_by_version, config,
            run_id=run_id,
            instruction=IMPACT_SWEEP_INSTRUCTION + " This is an independent second-model pass; "
                        "assume the first pass may have missed a subtle or differently worded impact.",
            prompt_version=IMPACT_SWEEP_VERSION + "_alt",
            role="guide_author", max_calls=config.path_c_max_calls)
        calls += calls_c
        all_impacts = _merge_impacts(all_impacts + alt)
        suspicions.extend(alt_suspicions)
        batches.extend(alt_batches)
        path_c_status = "qualified" if calls_c else "configured_not_run"
    else:
        path_c_status = "independent_model_review_not_qualified"
    # Every modify_contract requirement must have a chance to become a guide,
    # including a genuinely new clause that no historical contract contains.
    # The anchor is only a real contract location for drafting/review; the
    # author model still decides whether the clause actually needs changing.
    covered_requirement_ids = {item.requirement_id for item in all_impacts
                               if item.impact_status in {"definite", "possible"}}
    for requirement in requirements:
        if requirement.disposition != "modify_contract" or requirement.requirement_id in covered_requirement_ids:
            continue
        anchor = _best_requirement_anchor(requirement, all_clauses)
        if anchor is None:
            continue
        all_impacts.append(_make_impact(
            requirement.requirement_id, anchor.contract_version_id, [anchor.clause_id],
            anchor.text, " > ".join(anchor.section_path[-3:]), "possible", [],
            "Full corpus sweep found no existing affected clause; this is a real contract anchor "
            "for deciding whether the requirement needs a new or amended clause.",
            "requirement_only"))
    all_impacts, calls_adj = adjudicate_lexical_impacts(
        router, store, all_impacts, {item.requirement_id: item for item in requirements},
        clauses_by_id, config)
    calls += calls_adj
    return DiscoveryResult(impacts=all_impacts, uncovered_suspicions=suspicions,
                           search_intents=intents, sweep_batches=batches,
                           model_calls=calls, path_c_status=path_c_status, notes=notes)
