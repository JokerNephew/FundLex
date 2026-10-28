"""Residual impact mining and saturation accounting."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Iterable

from .discovery import (_batches, _compact_clause, _merge_impacts, _requirements_context,
                        _sweep_requirements)
from ..model import ModelError
from .models import (
    ClauseUnit,
    ContractVersion,
    GuideItem,
    ImpactCandidate,
    PolicyRequirement,
    compact_for_match,
    quote_in_text,
    stable_id,
    unique,
)
from .scope import section_in_scope
from .prompts import (
    RESIDUAL_INSTRUCTION,
    RESIDUAL_SCHEMA,
    RESIDUAL_VERSION,
)


@dataclass
class ResidualConfig:
    max_rounds: int = 4
    required_clean_rounds: int = 2
    batch_chars: int = 11000
    max_calls_per_round: int = 900
    sample_not_affected: int = 8
    max_requirements: int = 12
    circuit_wait_s: float = 130.0


@dataclass
class ResidualRound:
    round_no: int
    status: str
    new_impacts: list[ImpactCandidate]
    findings: list[dict[str, Any]]
    uncovered: list[dict[str, Any]]
    calls: int
    new_patterns: int
    notes: str = ""


@dataclass
class ResidualResult:
    rounds: list[ResidualRound]
    new_impacts: list[ImpactCandidate]
    findings: list[dict[str, Any]]
    saturated: bool
    status: str
    calls: int
    unresolved_count: int = 0


def _guide_index(items: list[GuideItem], limit: int = 14000) -> str:
    """Compact index of every existing guide item.

    Residual mining used to see only the first ~6000 characters of a detailed
    summary (about 20 of 100 items), so it repeatedly reported patterns that
    were already covered by invisible items.  The index keeps every item
    visible without exceeding the model context; the batch-specific details
    below explain the relevant ones.
    """
    lines = ["[ALL_GUIDE_ITEM_INDEX]"]
    total = len(lines[0])
    for item in items:
        line = (f"- {item.guide_item_id} req={','.join(item.requirement_ids[:2])} "
                f"title={item.title[:50]}")
        if total + len(line) + 1 > limit:
            break
        lines.append(line)
        total += len(line) + 1
    return "\n".join(lines)


def _guide_details(items: list[GuideItem], requirement_ids: set[str],
                   limit: int = 4000) -> str:
    lines: list[str] = []
    for item in items:
        if not set(item.requirement_ids) & requirement_ids:
            continue
        block = (f"- {item.guide_item_id} title={item.title}\n"
                 f"  requirements={item.requirement_ids}\n"
                 f"  applicability={item.applicability}\n"
                 f"  conditions={item.conditions}\n"
                 f"  exceptions={item.exceptions}\n"
                 f"  old={item.old_text_patterns}\n"
                 f"  new={item.new_text[:500]}")
        if sum(len(line) for line in lines) + len(block) > limit:
            break
        lines.append(block)
    return "\n".join(lines)


def _select_batches(sweep_batches: list[dict[str, Any]], config: ResidualConfig,
                    round_index: int = 0) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    not_affected = []
    for batch in sweep_batches:
        status = str(batch.get("status") or "uncertain")
        if status in {"uncertain", "affected", "model_error"}:
            selected.append(batch)
        elif status == "not_affected":
            not_affected.append(batch)
    # Rotate the negative sample each round so residual mining hunts different
    # parts of the corpus instead of re-reading the same sample forever.
    step = max(1, len(not_affected) // max(1, config.sample_not_affected))
    offset = round_index % step if step else 0
    selected.extend(not_affected[offset::step][:config.sample_not_affected])
    return selected


def _pattern_key(contract_version_id: str, clause_ids: list[str],
                 requirement_ids: list[str]) -> str:
    """Stable identity for one physical residual obligation.

    Model prose is deliberately excluded.  A changed explanation for the same
    clause and requirement is a re-review of one pattern, not a new impact.
    """
    return stable_id("PAT", contract_version_id, ",".join(sorted(set(clause_ids))),
                     ",".join(sorted(set(requirement_ids))), length=20)


def run_residual_mining(router, requirements: list[PolicyRequirement], items: list[GuideItem],
                        impacts: list[ImpactCandidate], versions: list[ContractVersion],
                        clauses_by_version: dict[str, list[ClauseUnit]],
                        clauses: dict[str, ClauseUnit], sweep_batches: list[dict[str, Any]],
                        *, config: ResidualConfig | None = None,
                        round_index: int = 0,
                        seen_patterns: set[str] | None = None,
                        scope_sections: list[str] | None = None) -> ResidualResult:
    config = config or ResidualConfig()
    guide_index = _guide_index(items)
    selected = _select_batches(sweep_batches, config, round_index)
    version_map = {item.contract_version_id: item for item in versions}
    # Expand every selected batch back to its real clauses, then split into model
    # batches.  We deliberately use the original clause text, not a summary.
    residual_batches: list[tuple[ContractVersion, list[ClauseUnit]]] = []
    for selected_batch in selected:
        version_id = str(selected_batch.get("contract_version_id") or "")
        version = version_map.get(version_id)
        if not version:
            continue
        clauses = clauses_by_version.get(version_id) or []
        wanted = set(selected_batch.get("clause_ids") or [])
        if wanted:
            subset = [clause for clause in clauses if clause.clause_id in wanted]
        else:
            subset = clauses
        if scope_sections:
            subset = [clause for clause in subset
                      if section_in_scope(" > ".join(clause.section_path), scope_sections)]
            if not subset:
                continue
        for batch in _batches(subset, config.batch_chars):
            residual_batches.append((version, batch))
    rounds: list[ResidualRound] = []
    all_new: list[ImpactCandidate] = []
    findings: list[dict[str, Any]] = []
    seen = set(seen_patterns or set())
    # Existing discovery impacts already identify physical clause/requirement
    # patterns.  Residual prose may change between rounds, but that is a
    # re-review of the same pattern rather than a new uncovered impact.
    for impact in impacts:
        if impact.clause_ids and impact.requirement_id:
            seen.add(_pattern_key(impact.contract_version_id, impact.clause_ids,
                                  [impact.requirement_id]))
    calls = 0
    clean_streak = 0
    status = "max_rounds_reached"
    for round_no in range(1, config.max_rounds + 1):
        new_impacts: list[ImpactCandidate] = []
        uncovered: list[dict[str, Any]] = []
        round_findings: list[dict[str, Any]] = []
        round_calls = 0
        round_patterns: set[str] = set()
        for version, batch in residual_batches:
            if round_calls >= config.max_calls_per_round:
                break
            contract_text = "\n\n".join(_compact_clause(clause) for clause in batch)
            selected_requirements = _sweep_requirements(
                requirements, batch, config.max_requirements)
            selected_ids = {item.requirement_id for item in selected_requirements}
            requirements_context = _requirements_context(selected_requirements, compact=True)
            guide_details = _guide_details(items, selected_ids)
            context = (f"[REQUIREMENTS]\n{requirements_context[:3000]}\n\n"
                       f"{guide_index}\n\n"
                       f"[GUIDE_ITEMS_RELEVANT]\n{guide_details[:4000]}\n\n"
                       f"[CONTRACT]\ncontract={version.contract_version_id} fund={version.fund_identity}\n"
                       + contract_text[:6000])
            # The index is first, so a hard guard cuts contract text rather
            # than hiding guide items from the residual scanner.
            context = context[:30000]
            def call_residual():
                return router.call(task_type="guide_residual_sweep",
                                   bounded_context=context,
                                   response_schema=RESIDUAL_SCHEMA,
                                   instruction=RESIDUAL_INSTRUCTION,
                                   prompt_version=f"{RESIDUAL_VERSION}_r{round_no}",
                                   role="coverage_auditor")

            try:
                result = call_residual()
                round_calls += 1
            except ModelError as exc:
                if str(exc.code).startswith("GUIDE_RUN_") or str(exc.code).startswith("MODEL_COST_BUDGET"):
                    raise
                if str(exc.code) == "MODEL_CIRCUIT_OPEN" and config.circuit_wait_s > 0:
                    # The shared budget circuit opens after a few provider
                    # failures.  A blocked residual round is not evidence of
                    # saturation; wait out the cooldown and retry once.
                    time.sleep(config.circuit_wait_s)
                    try:
                        result = call_residual()
                        round_calls += 1
                    except Exception as retry_exc:
                        round_findings.append({
                            "finding_id": stable_id("F", "RESIDUAL_CIRCUIT_RETRY", round_no,
                                                    version.contract_version_id, length=20),
                            "guide_item_id": "", "category": "residual_mining",
                            "severity": "major", "status": "open",
                            "description": ("residual round "
                                            f"{round_no} circuit retry failed："
                                            f"{type(retry_exc).__name__}"),
                            "evidence_quote": "", "source": "residual_mining",
                        })
                        continue
                else:
                    round_findings.append({
                        "finding_id": stable_id("F", "RESIDUAL_MODEL_ERROR", round_no,
                                                version.contract_version_id, length=20),
                        "guide_item_id": "", "category": "residual_mining", "severity": "major",
                        "status": "open",
                        "description": f"residual round {round_no} 模型失败：{type(exc).__name__}",
                        "evidence_quote": "", "source": "residual_mining",
                    })
                    continue
            except Exception as exc:
                round_findings.append({
                    "finding_id": stable_id("F", "RESIDUAL_MODEL_ERROR", round_no,
                                            version.contract_version_id, length=20),
                    "guide_item_id": "", "category": "residual_mining", "severity": "major",
                    "status": "open",
                    "description": f"residual round {round_no} 模型失败：{type(exc).__name__}",
                    "evidence_quote": "", "source": "residual_mining",
                })
                continue
            by_id = {clause.clause_id: clause for clause in batch}
            for item in result.value.get("uncovered") or []:
                ids = [str(value) for value in item.get("clause_ids") or [] if str(value) in by_id]
                if not ids:
                    continue
                quote = str(item.get("evidence_quote") or "")
                text = "\n".join(by_id[cid].text for cid in ids)
                if quote and not quote_in_text(quote, text):
                    continue
                requirement_ids = [str(value) for value in item.get("requirement_ids") or [] if value]
                if not requirement_ids:
                    requirement_ids = ["UNMAPPED"]
                allowed_ids = {requirement.requirement_id
                               for requirement in selected_requirements}
                if (len(requirement_ids) > config.max_requirements
                        or (requirement_ids != ["UNMAPPED"]
                            and not set(requirement_ids).issubset(allowed_ids))):
                    round_findings.append({
                        "finding_id": stable_id("F", "RESIDUAL_INVALID_BINDING", round_no,
                                                version.contract_version_id, ids, length=20),
                        "guide_item_id": "", "category": "residual_mining", "severity": "major",
                        "status": "open",
                        "description": "Residual 模型返回了未在当前条款批次提供的法规要求绑定。",
                        "evidence_quote": quote[:500], "source": "residual_mining",
                    })
                    continue
                description = str(item.get("pattern_description") or item.get("reason") or "")
                pattern = _pattern_key(version.contract_version_id, ids, requirement_ids)
                if pattern in seen:
                    continue
                seen.add(pattern)
                round_patterns.add(pattern)
                uncovered.append({**item, "clause_ids": ids,
                                  "contract_version_id": version.contract_version_id,
                                  "pattern_key": pattern})
                for requirement_id in requirement_ids:
                    impact_id = stable_id("IC", requirement_id, version.contract_version_id,
                                          ",".join(sorted(ids)), f"residual-{round_no}", length=20)
                    new_impacts.append(ImpactCandidate(
                        impact_id=impact_id, requirement_id=requirement_id,
                        contract_version_id=version.contract_version_id,
                        clause_ids=sorted(set(ids)), source_text=text,
                        context=" > ".join(by_id[ids[0]].section_path[-3:]),
                        impact_status="possible", impact_dimensions=[],
                        impact_reason=f"Residual round {round_no}: {item.get('reason') or description}",
                        discovery_sources=[f"residual_round_{round_no}"],
                    ))
            for item in result.value.get("guide_conflicts") or []:
                round_findings.append({
                    "finding_id": stable_id("F", "RESIDUAL_CONFLICT", round_no,
                                            str(item.get("guide_item_id") or ""),
                                            str(item.get("reason") or ""), length=20),
                    "guide_item_id": str(item.get("guide_item_id") or ""),
                    "category": "guide_conflict", "severity": "major", "status": "open",
                    "description": "Residual mining 发现指引可能误改：" + str(item.get("reason") or ""),
                    "evidence_quote": str(item.get("evidence_quote") or "")[:500],
                    "source": "residual_mining",
                })
        calls += round_calls
        new_impacts = _merge_impacts(new_impacts)
        all_new = _merge_impacts(all_new + new_impacts)
        findings.extend(round_findings)
        if round_patterns:
            clean_streak = 0
            round_status = "new_uncovered"
        elif round_findings:
            # A failed or invalid audit is not evidence that the batch is
            # clean.  Keep the gate closed until a later round gets a valid,
            # finding-free result.
            clean_streak = 0
            round_status = "blocked"
        else:
            clean_streak += 1
            round_status = "clean"
        rounds.append(ResidualRound(
            round_no=round_no, status=round_status, new_impacts=new_impacts,
            findings=round_findings, uncovered=uncovered, calls=round_calls,
            new_patterns=len(round_patterns),
        ))
        if round_status == "clean" and clean_streak >= config.required_clean_rounds:
            status = "saturated"
            break
    if status != "saturated":
        status = "max_rounds_reached" if rounds else "not_run"
    return ResidualResult(rounds=rounds, new_impacts=all_new, findings=findings,
                          saturated=(status == "saturated"), status=status, calls=calls,
                          unresolved_count=sum(1 for item in all_new
                                               if not item.disposition))
