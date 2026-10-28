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
from .vector import DenseRetriever, VectorHit, VectorIndexError
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
    BATCH_RESOLVE_INSTRUCTION,
    BATCH_RESOLVE_SCHEMA,
    BATCH_RESOLVE_VERSION,
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
    # A sweep batch must carry only requirements that can be evidenced by the
    # clauses in that batch.  This bounds both prompt size and the number of
    # requirement ids a model can attach to one finding.
    path_b_max_requirements: int = 12
    path_b_latest_only: bool = True
    path_b_max_calls: int = 4000
    path_c_enabled: bool = True
    path_c_max_calls: int = 240
    adjudicate_lexical: bool = True
    adjudicate_batch: int = 20
    vector_top_k: int = 30
    vector_per_contract: int = 1
    vector_max_candidates: int = 60


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
        current.metadata.update(item.metadata or {})
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
                                 *, run_id: str = "", dense: DenseRetriever | None = None,
                                 source_hashes: dict[str, str] | None = None) -> tuple[list[ImpactCandidate], dict[str, list[dict]], int, list[str]]:
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
        vector_hits: list[VectorHit] = []
        if dense is not None:
            query_text = " ".join([
                requirement.requirement, requirement.subject, requirement.object,
                *requirement.conditions, *requirement.exceptions,
                *query.terms, *query.phrases, *query.business_actions,
            ])
            try:
                vector_hits = dense.search(query_text, top_k=config.vector_top_k,
                                           per_contract=config.vector_per_contract,
                                           max_candidates=config.vector_max_candidates)
            except VectorIndexError as exc:
                notes.append(f"{requirement.requirement_id}: vector retrieval unavailable:{exc}")
            except Exception:
                notes.append(f"{requirement.requirement_id}: vector retrieval unavailable")
        by_clause_id = {clause.clause_id: (index, clause) for index, clause in enumerate(clauses)}
        merged: dict[str, tuple[Any, set[str], float]] = {}
        for hit in hits:
            merged[hit.clause_id] = (hit, set(hit.reasons), hit.score)
        expected_sources = source_hashes or {}
        for vector_hit in vector_hits:
            entry = by_clause_id.get(vector_hit.clause_id)
            if not entry or entry[1].contract_version_id != vector_hit.contract_version_id:
                notes.append(f"{requirement.requirement_id}: vector provenance address rejected")
                continue
            expected = expected_sources.get(vector_hit.contract_version_id)
            if expected and vector_hit.source_sha256 != expected:
                notes.append(f"{requirement.requirement_id}: vector source hash rejected")
                continue
            previous = merged.get(vector_hit.clause_id)
            reasons = previous[1] if previous else set()
            reasons.add(f"vector:{vector_hit.embedding_version}")
            merged[vector_hit.clause_id] = (previous[0] if previous else vector_hit,
                                             reasons, max(previous[2], vector_hit.score) if previous else vector_hit.score)
        # Retrieval is a discovery aid, not proof of impact.  Keep hits that
        # contain at least one requirement-specific term or phrase; the full
        # contract-centric sweep independently covers the whole corpus.
        strong_terms = [value for value in (
            [requirement.subject, requirement.object]
            + requirement.conditions + requirement.exceptions
            + requirement.candidate_contract_domains)
            if value and len(value) >= 2 and value not in {"基金", "基金合同"}]
        kept = 0
        ranked = sorted(merged.values(), key=lambda item: -item[2])
        max_kept = config.path_a_max_candidates
        if dense is not None:
            # Each route gets its own bounded budget before the union.  A
            # dense hit must not evict a lexical hit merely because both
            # routes share one output cap.
            max_kept += config.vector_max_candidates
        for hit, hit_reasons, _score in ranked:
            clause = clauses[hit.clause_index] if hasattr(hit, "clause_index") else by_clause_id[hit.clause_id][1]
            compact_text = compact_for_match(clause.text)
            matched = [term for term in strong_terms if compact_for_match(term) in compact_text]
            has_vector = any(reason.startswith("vector:") for reason in hit_reasons)
            is_vector_only = not hasattr(hit, "clause_index")
            if not matched and not any(compact_for_match(phrase) in compact_text
                                       for phrase in query.phrases if phrase) and not has_vector:
                continue
            retrieval_reasons = sorted(hit_reasons)[:6]
            source = "vector" if is_vector_only else "lexical"
            if not is_vector_only and any(reason.startswith("vector:") for reason in hit_reasons):
                source = "lexical+vector"
            impacts.append(_make_impact(
                requirement.requirement_id, clause.contract_version_id, [clause.clause_id],
                clause.text, " > ".join(clause.section_path[-3:]),
                "possible", [], "词法/向量检索命中：" + ",".join((retrieval_reasons + matched)[:8]),
                source))
            impacts[-1].metadata["retrieval"] = {
                "lexical": not is_vector_only,
                "vector": any(reason.startswith("vector:") for reason in hit_reasons),
                "vector_embedding_version": next((reason.split(":", 1)[1] for reason in hit_reasons
                                                   if reason.startswith("vector:")), ""),
            }
            kept += 1
            if kept >= max_kept:
                break
    return _merge_impacts(impacts), intents_by_requirement, calls, notes


def _sweep_requirements(requirements: list[PolicyRequirement], clauses: list[ClauseUnit],
                        max_requirements: int) -> list[PolicyRequirement]:
    """Select a bounded, evidence-related requirement window for one sweep.

    Contract sweeps still cover every clause batch.  They do not need every
    regulation requirement in every request: unrelated requirements create
    noisy many-to-one findings and frequently exceed the response schema's
    requirement id bound.  Keep a deterministic fallback so a sparse batch is
    still reviewed against at least a small high-recall window.
    """
    max_requirements = max(1, int(max_requirements))
    text = compact_for_match("\n".join(clause.text for clause in clauses))
    scored: list[tuple[int, str, PolicyRequirement]] = []
    for requirement in requirements:
        terms = [requirement.subject, requirement.object, requirement.requirement,
                 *requirement.conditions, *requirement.exceptions,
                 *requirement.candidate_contract_domains]
        score = sum(1 for term in terms if term and compact_for_match(term) in text)
        scored.append((score, requirement.requirement_id, requirement))
    scored.sort(key=lambda item: (-item[0], item[1]))
    positive = [item[2] for item in scored if item[0] > 0]
    if positive:
        return positive[:max_requirements]
    return [item[2] for item in scored[:max_requirements]]


def _sweep_prompt_context(requirements: list[PolicyRequirement], contract: ContractVersion,
                          clauses: list[ClauseUnit], *, max_requirements: int = 12,
                          requirements_are_window: bool = False) -> str:
    selected = (requirements if requirements_are_window else
                _sweep_requirements(requirements, clauses, max_requirements))
    return (
        "[REQUIREMENTS]\n" + _requirements_context(selected, compact=True) +
        "\n\n[CONTRACT]\n"
        f"contract_version_id={contract.contract_version_id}\n"
        f"fund={contract.fund_identity}\nversion_date={contract.version_date}\n"
        f"latest_known={contract.latest_known_version}\n"
        "Clause ids in square brackets are addresses, not legal text.\n\n"
        + "\n\n".join(_compact_clause(clause) for clause in clauses)
    )


def _validate_sweep(value: dict[str, Any], clauses: list[ClauseUnit],
                    allowed_requirement_ids: set[str] | None = None,
                    max_requirement_ids: int = 12) -> tuple[list[dict], list[dict], str, str]:
    by_id = {clause.clause_id: clause for clause in clauses}
    findings: list[dict] = []
    invalid_bindings = 0
    for item in value.get("findings") or []:
        ids = [str(cid) for cid in item.get("clause_ids") or [] if str(cid) in by_id]
        if not ids:
            continue
        requirement_ids = unique(str(value) for value in item.get("requirement_ids") or [] if value)
        if (not requirement_ids or len(requirement_ids) > max_requirement_ids
                or (allowed_requirement_ids is not None
                    and not set(requirement_ids).issubset(allowed_requirement_ids))):
            invalid_bindings += 1
            continue
        quote = str(item.get("evidence_quote") or "")
        text = "\n".join(by_id[cid].text for cid in ids)
        if quote and not quote_in_text(quote, text):
            continue
        findings.append({**item, "clause_ids": ids, "requirement_ids": requirement_ids})
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
    validation_error = (f"INVALID_REQUIREMENT_BINDINGS:{invalid_bindings}"
                        if invalid_bindings else "")
    return findings, suspicions, str(value.get("section_assessment") or "uncertain"), validation_error


def _sweep_one(router, requirements, contract, batch, config, instruction, prompt_version, role):
    selected = list(requirements)
    context = _sweep_prompt_context(
        requirements, contract, batch,
        max_requirements=config.path_b_max_requirements,
        requirements_are_window=True)
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
    findings, suspicions, assessment, validation_error = _validate_sweep(
        result.value, batch,
        allowed_requirement_ids={item.requirement_id for item in selected},
        max_requirement_ids=config.path_b_max_requirements)
    if validation_error:
        return "model_error", validation_error, [], [], "uncertain"
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
    max_requirements = max(1, int(config.path_b_max_requirements))
    # Every requirement must appear in a window for EVERY contract, otherwise
    # per-contract coverage cannot distinguish "not affected" from "never
    # scanned" (smoke24: 42 latest-uncertain rows).  Build the related windows,
    # then add a coverage tail over all clause batches for requirements that
    # never entered a window for that contract.
    rotating_requirements = list(requirements)
    rotating_cursor = 0
    for contract in versions:
        clauses = clauses_by_version.get(contract.contract_version_id) or []
        if not clauses:
            continue
        contract_jobs = []
        contract_batches = _batches(clauses, config.path_b_batch_chars)
        covered_ids: set[str] = set()
        for batch in contract_batches:
            if len(jobs) + len(contract_jobs) >= limit:
                break
            related = _sweep_requirements(requirements, batch, max_requirements)
            related_ids = {item.requirement_id for item in related}
            window = related[:8]
            rotating_attempts = 0
            while (rotating_requirements and len(window) < max_requirements
                   and rotating_attempts < len(rotating_requirements)):
                item = rotating_requirements[rotating_cursor % len(rotating_requirements)]
                rotating_cursor += 1
                rotating_attempts += 1
                if item.requirement_id not in related_ids:
                    window.append(item)
                    related_ids.add(item.requirement_id)
            for item in related[8:]:
                if len(window) >= max_requirements:
                    break
                if item.requirement_id not in related_ids:
                    window.append(item)
                    related_ids.add(item.requirement_id)
            contract_jobs.append((contract, batch, window))
            covered_ids.update(item.requirement_id for item in window)
        missing = [item for item in requirements
                   if item.requirement_id not in covered_ids]
        if missing and contract_batches:
            for start in range(0, len(missing), max_requirements):
                group = missing[start:start + max_requirements]
                for batch in contract_batches:
                    if len(jobs) + len(contract_jobs) >= limit:
                        break
                    contract_jobs.append((contract, batch, group))
        jobs.extend(contract_jobs)
        if len(jobs) >= limit:
            break
    if not jobs:
        return [], [], [], 0

    def run_jobs(work):
        nonlocal calls
        failed = []
        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(work)))) as executor:
            futures = {
                executor.submit(_sweep_one, router, window, contract, batch, config,
                                instruction, prompt_version, role): (contract, batch, window)
                for contract, batch, window in work
            }
            for future in as_completed(futures):
                contract, batch, window = futures[future]
                try:
                    status, error, findings, found_suspicions, assessment = future.result()
                except ModelError:
                    raise
                calls += 1
                if status != "ok":
                    # Do not record a model_error evidence yet: the bounded
                    # retry may succeed, and a stale error row makes coverage
                    # mark every requirement of the contract uncertain.
                    failed.append((contract, batch, window))
                    continue
                _collect_sweep_results(contract, batch, findings, found_suspicions, assessment,
                                        impacts, suspicions, batch_evidence, role, prompt_version,
                                        requirement_ids=[item.requirement_id for item in window],
                                        validation_error=error)
        return failed

    def _collect_sweep_results(contract, batch, findings, found_suspicions, assessment,
                               impacts, suspicions, batch_evidence, role, prompt_version,
                               requirement_ids=None, validation_error=""):
        by_id = {clause.clause_id: clause for clause in batch}
        for item in findings:
            ids = item["clause_ids"]
            text = "\n".join(by_id[cid].text for cid in ids)
            for requirement_id in unique(str(value) for value in item.get("requirement_ids") or [] if value):
                impacts.append(_make_impact(
                    requirement_id=requirement_id,
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
        evidence = {
            "contract_version_id": contract.contract_version_id,
            "clause_ids": [clause.clause_id for clause in batch],
            "requirement_ids": list(requirement_ids or []),
            "status": assessment,
            "finding_count": len(findings),
            "prompt_version": prompt_version,
        }
        if validation_error:
            evidence["validation_error"] = validation_error
        batch_evidence.append(evidence)

    failed = run_jobs(jobs)
    if failed:
        # One bounded retry after a schema/network failure; never unbounded.
        retry_failed = run_jobs(failed[:min(len(failed), config.path_b_max_calls)])
        if retry_failed:
            for contract, batch, window in retry_failed:
                batch_evidence.append({
                    "contract_version_id": contract.contract_version_id,
                    "clause_ids": [clause.clause_id for clause in batch],
                    "requirement_ids": [item.requirement_id for item in window],
                    "status": "uncertain", "error": "MODEL_RETRY_EXHAUSTED",
                })
    return _merge_impacts(impacts), suspicions, batch_evidence, calls

def resolve_uncertain_batches(router, requirements: list[PolicyRequirement],
                              versions: list[ContractVersion],
                              clauses_by_version: dict[str, list[ClauseUnit]],
                              sweep_batches: list[dict[str, Any]],
                              config: DiscoveryConfig, *, max_calls: int | None = None
                              ) -> tuple[list[ImpactCandidate], int]:
    """Resolve sweep batches whose section assessment was uncertain.

    A single uncertain batch used to make every requirement of that contract
    uncertain.  Ask a strict per-requirement judge for every uncertain batch;
    the batch becomes not_affected only when the model explicitly marks every
    supplied requirement not_affected.  Omitted or uncertain requirements keep
    the batch open.
    """
    version_map = {item.contract_version_id: item for item in versions}
    impacts: list[ImpactCandidate] = []
    calls = 0
    limit = config.path_b_max_calls if max_calls is None else max_calls
    for batch_evidence in sweep_batches:
        if str(batch_evidence.get("status") or "") not in {"uncertain", "affected"}:
            continue
        if batch_evidence.get("resolution"):
            continue
        if calls >= limit:
            break
        version = version_map.get(str(batch_evidence.get("contract_version_id") or ""))
        if version is None:
            continue
        clauses = clauses_by_version.get(version.contract_version_id) or []
        by_id = {clause.clause_id: clause for clause in clauses}
        batch = [by_id[cid] for cid in batch_evidence.get("clause_ids") or [] if cid in by_id]
        if not batch:
            continue
        window_ids = set(batch_evidence.get("requirement_ids") or [])
        if window_ids:
            window = [item for item in requirements if item.requirement_id in window_ids]
        else:
            window = _sweep_requirements(requirements, batch, config.path_b_max_requirements)
        if not window:
            continue
        context = _sweep_prompt_context(window, version, batch, requirements_are_window=True)
        try:
            result = router.call(task_type="guide_batch_resolve", bounded_context=context,
                                 response_schema=BATCH_RESOLVE_SCHEMA,
                                 instruction=BATCH_RESOLVE_INSTRUCTION,
                                 prompt_version=BATCH_RESOLVE_VERSION,
                                 role="discovery")
            calls += 1
        except ModelError as exc:
            if str(exc.code).startswith("GUIDE_RUN_") or str(exc.code).startswith("MODEL_COST_BUDGET"):
                raise
            continue
        except Exception:
            continue
        batch_ids = {clause.clause_id for clause in batch}
        resolved: dict[str, str] = {}
        for item in result.value.get("results") or []:
            requirement_id = str(item.get("requirement_id") or "")
            if requirement_id not in {value.requirement_id for value in window}:
                continue
            if requirement_id in resolved:
                continue
            status = str(item.get("status") or "uncertain")
            ids = [str(value) for value in item.get("clause_ids") or []
                   if str(value) in batch_ids]
            quote = str(item.get("evidence_quote") or "")
            if status == "affected":
                text = "\n".join(by_id[cid].text for cid in ids)
                if not ids or (quote and not quote_in_text(quote, text)):
                    resolved[requirement_id] = "uncertain"
                    continue
                impacts.append(_make_impact(
                    requirement_id, version.contract_version_id, ids, text,
                    " > ".join(by_id[ids[0]].section_path[-3:]), "possible", [],
                    str(item.get("reason") or ""), "batch_resolution"))
                resolved[requirement_id] = "affected"
            elif status == "not_affected":
                resolved[requirement_id] = "not_affected"
            else:
                resolved[requirement_id] = "uncertain"
        if all(resolved.get(item.requirement_id) == "not_affected" for item in window):
            new_status = "not_affected"
        elif any(value == "affected" for value in resolved.values()):
            new_status = "affected"
        else:
            new_status = "uncertain"
        batch_evidence["status"] = new_status
        batch_evidence["resolution"] = {"resolved": resolved, "model_calls": 1}
    return impacts, calls


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
             config: DiscoveryConfig | None = None, dense: DenseRetriever | None = None) -> DiscoveryResult:
    config = config or DiscoveryConfig()
    latest_ids = set(snapshot.latest_version_ids)
    selected = [item for item in versions if (not config.path_b_latest_only or item.contract_version_id in latest_ids)]
    clauses_by_version = _clauses_by_contract(store, [item.contract_version_id for item in versions])
    all_clauses = [clause for version_id in [item.contract_version_id for item in versions]
                   for clause in clauses_by_version.get(version_id, [])]
    clauses_by_id = {clause.clause_id: clause for clause in all_clauses}
    source_hashes = {item.contract_version_id: item.source_sha256 for item in versions}
    path_a, intents, calls_a, notes = path_a_requirement_retrieval(
        router, store, requirements, all_clauses, config, run_id=run_id,
        dense=dense, source_hashes=source_hashes)
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
    # Resolve uncertain contract batches with per-requirement verdicts before
    # computing coverage.  Only an explicit all-not_affected result closes a
    # batch; omitted or uncertain requirements keep it open.
    resolved_impacts, resolve_calls = resolve_uncertain_batches(
        router, requirements, selected, clauses_by_version, batches, config)
    calls += resolve_calls
    all_impacts = _merge_impacts(all_impacts + resolved_impacts)
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
