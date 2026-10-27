"""Resumable orchestration for regulation-driven candidate guide generation.

Discovery, authoring, quality, coverage, residual mining and engine
compatibility are separate stages.  A failed or interrupted stage can be
retried when its input hash is unchanged; a changed regulation, corpus snapshot
or model identity creates a new stage input and therefore cannot silently reuse
an old result.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..model import ModelError
from ..store import RunStore, engine_build
from .authoring import AuthoringConfig, build_local_candidates, families_to_guide_items, induce_families
from .corpus_catalog import sync_corpus
from .coverage import run_coverage_gate
from .discovery import DiscoveryConfig, discover
from .engine_compat import run_engine_compatibility
from .export import build_evidence_package, export_guide_docx, render_evidence_html
from .models import (
    ClauseUnit,
    GuideItem,
    ImpactCandidate,
    LocalGuideCandidate,
    RegulationDocument,
    sha256_json,
    stable_id,
    utc_now,
)
from .quality import run_quality_gate
from ..regulatory.ingestion import ingest_regulation, validate_regulation_document
from .requirements import extract_requirements
from .residual import ResidualConfig, run_residual_mining
from .store import GuideGenerationStore


STAGES = (
    "INGEST_REGULATION",
    "EXTRACT_REQUIREMENTS",
    "VERIFY_REQUIREMENTS",
    "BUILD_CORPUS_SNAPSHOT",
    "DISCOVERY_REQUIREMENT_RETRIEVAL",
    "DISCOVERY_CONTRACT_SWEEP",
    "ADJUDICATE_IMPACTS",
    "BUILD_LOCAL_GUIDE_CANDIDATES",
    "MERGE_AND_GENERALIZE",
    "GUIDE_QUALITY_REVIEW",
    "GUIDE_REPAIR",
    "SEMANTIC_COVERAGE",
    "RESIDUAL_MINING",
    "FINALIZE_GUIDE",
    "BUILD_EVIDENCE",
)


@dataclass
class PipelineConfig:
    corpus_dir: str = ""
    corpus_limit: int | None = None
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
    local_batch_size: int = 12
    max_residual_rounds: int = 4
    required_clean_rounds: int = 2
    residual_max_calls_per_round: int = 600
    semantic_applicability: bool = True
    run_engine_compatibility: bool = False
    sample_contract: str = ""
    soft_max_calls: int = 8000
    soft_max_cost: float = 20.0

    @classmethod
    def from_payload(cls, payload: dict[str, Any], fallback_corpus: str = "") -> "PipelineConfig":
        config = cls()
        for name in config.__dataclass_fields__:
            if name in payload and payload[name] is not None:
                setattr(config, name, payload[name])
        if not config.corpus_dir:
            config.corpus_dir = fallback_corpus or os.environ.get(
                "FUNDLEX_GUIDE_CORPUS_DIR",
                str(Path(__file__).resolve().parent.parent.parent / "funds_word"))
        return config

    def to_dict(self) -> dict[str, Any]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


def _commit_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent.parent.parent,
            stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return os.environ.get("FUNDLEX_COMMIT_SHA", "")


def _file_sha(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return ""


def _counts(items: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if item:
            counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items()))


class GuidePipeline:
    def __init__(self, store: GuideGenerationStore, run_id: str, router,
                 config: PipelineConfig | None = None):
        self.store = store
        self.run_id = run_id
        self.router = router
        self.config = config or PipelineConfig()
        self.run_dir = store.store.objects / "guide_generation" / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.router.set_call_callback(lambda record: store.record_model_call(run_id, record))
        self.router.run_max_calls = self.config.soft_max_calls
        self.router.run_max_cost = self.config.soft_max_cost
        self._restore_run()

    def _restore_run(self) -> None:
        self.run_record = self.store.get_run(self.run_id)
        self.payload = self.run_record.get("payload") or {}
        self.payload.update({
            "model_identity": self.router.identity(),
            "config": self.config.to_dict(),
            "commit_sha": _commit_sha(),
            "code_build": engine_build(),
            "lockfile_sha256": _file_sha(Path(__file__).resolve().parent.parent.parent / "uv.lock"),
            "runtime_config_sha256": sha256_json({
                "config": self.config.to_dict(),
                "env": {key: value for key, value in os.environ.items()
                        if (key.startswith("FUNDLEX_GUIDE_") and "KEY" not in key and "SECRET" not in key)
                        or key in {"LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL",
                                   "FUNDLEX_MODEL_MODE", "FUNDLEX_MODEL_CONTEXT_CHARS"}},
            }),
        })

    def _update(self, **fields: Any) -> None:
        payload = fields.pop("payload", None)
        if payload is not None:
            self.payload = payload
        self.run_record = self.store.update_run(self.run_id, payload=self.payload, **fields)

    def _stage(self, stage: str, input_hash: str, fn, *args, **kwargs) -> Any:
        completed = self.store.get_completed_step(self.run_id, stage, input_hash)
        if completed:
            return completed.get("payload") or {}
        self._update(status="running", stage=stage)
        attempt = self.store.start_step(
            self.run_id, stage, input_hash,
            model_identity=self.router.identity(),
            prompt_hash=sha256_json({"stage": stage, "input_hash": input_hash}))
        try:
            payload = fn(*args, **kwargs) or {}
            check = getattr(self.router, 'raise_if_blocked', None)
            if check:
                check()
            self.store.finish_step(self.run_id, stage, attempt, status="completed",
                                   output_hash=sha256_json(payload), payload=payload)
            self.payload.setdefault("stages", {})[stage] = {
                "status": "completed", "attempt": attempt,
                "output_hash": sha256_json(payload), "finished_at": utc_now(),
            }
            self._update(payload=self.payload)
            return payload
        except Exception as exc:
            self.store.finish_step(self.run_id, stage, attempt, status="failed",
                                   error_code=getattr(exc, "code", type(exc).__name__),
                                   payload={"error": str(exc)[:1000]})
            raise

    # -- helpers --------------------------------------------------------------
    def _source_path(self) -> Path:
        relpath = self.payload.get("source_relpath") or self.run_record.get("source_object_key")
        if not relpath:
            raise ValueError("RUN_SOURCE_MISSING")
        return self.store.store.object_path(relpath)

    def _load_document(self) -> RegulationDocument:
        blocks = self.store.get_blocks(self.run_id)
        return RegulationDocument(
            document_id=self.run_record.get("regulation_document_id") or "",
            source_type=self.run_record.get("source_type") or self.payload.get("source_type", ""),
            source_sha256=self.run_record.get("source_sha256") or "",
            title=self.run_record.get("title") or "",
            filename=self.run_record.get("filename") or "",
            page_count=int(self.payload.get("page_count") or 0),
            parser_version=str(self.payload.get("parser_version") or ""),
            blocks=blocks,
            document_sha256=self.run_record.get("regulation_document_sha256") or "",
        )

    def _all_impacts(self) -> list[ImpactCandidate]:
        return self.store.get_impacts(self.run_id)

    def _all_items(self) -> list[GuideItem]:
        return self.store.get_guide_items(self.run_id)

    def _clauses_for_impacts(self, impacts: Iterable[ImpactCandidate],
                             extra: Iterable[str] = ()) -> dict[str, ClauseUnit]:
        ids = [clause_id for impact in impacts for clause_id in impact.clause_ids]
        ids.extend(extra)
        clauses = self.store.get_clauses_by_ids(ids)
        return {clause.clause_id: clause for clause in clauses}

    def _sweep_batches(self) -> list[dict[str, Any]]:
        return self.store.get_evidence_by_kind(self.run_id, "sweep_batch")

    def _merge_findings(self, new_findings: list[dict[str, Any]]) -> None:
        existing = {item["finding_id"]: item for item in self.store.get_findings(self.run_id)}
        for item in new_findings:
            existing[item["finding_id"]] = item
        self.store.replace_findings(self.run_id, existing.values())

    # -- stages ---------------------------------------------------------------
    def stage_ingest(self) -> dict[str, Any]:
        source = self._source_path()
        document = ingest_regulation(source, original_filename=self.run_record.get("filename") or source.name)
        validate_regulation_document(document)
        self.store.replace_blocks(self.run_id, document.blocks)
        self.payload.update({
            "source_type": document.source_type,
            "parser_version": document.parser_version,
            "page_count": document.page_count,
            "block_count": len(document.blocks),
            "source_relpath": str(source.relative_to(self.store.store.objects)),
        })
        self._update(title=document.title, source_type=document.source_type,
                     regulation_document_id=document.document_id,
                     regulation_document_sha256=document.document_sha256)
        return {"blocks": len(document.blocks), "title": document.title,
                "source_type": document.source_type}

    def stage_extract(self) -> dict[str, Any]:
        document = self._load_document()
        result = extract_requirements(self.router, document, run_id=self.run_id)
        if not result.requirements:
            raise ValueError("NO_REQUIREMENTS_EXTRACTED")
        self.store.replace_requirements(self.run_id, result.requirements)
        if result.findings:
            self.store.add_evidence_many(self.run_id, [
                (stable_id("EV", "req_finding", item["finding_id"]), "requirement_finding",
                 item.get("article", ""), item) for item in result.findings
            ])
        self.payload.update({
            "article_dispositions": result.article_dispositions,
            "requirement_prompt_versions": result.prompt_versions,
            "requirement_notes": result.notes,
            "requirement_model_calls": result.model_calls,
        })
        self._update(payload=self.payload)
        return {"requirements": len(result.requirements),
                "unhandled": sum(1 for item in result.requirements if not item.disposition),
                "dispositions": _counts(item.disposition for item in result.requirements),
                "findings": len(result.findings)}

    def stage_verify(self) -> dict[str, Any]:
        requirements = self.store.get_requirements(self.run_id)
        unhandled = [item.requirement_id for item in requirements if not item.disposition]
        if unhandled:
            raise ValueError("UNHANDLED_REQUIREMENTS:" + ",".join(unhandled[:10]))
        self.payload["requirement_verification"] = {
            "status": "pass", "unhandled": 0, "requirements": len(requirements),
            "independent_challenger": True,
        }
        self._update(payload=self.payload)
        return {"unhandled": 0, "requirements": len(requirements)}

    def stage_snapshot(self) -> dict[str, Any]:
        result = sync_corpus(self.store, self.config.corpus_dir, limit=self.config.corpus_limit)
        snapshot = result.snapshot
        self._update(corpus_snapshot_id=snapshot.snapshot_id)
        self.payload["corpus_sync"] = {
            "parsed": result.parsed, "reused": result.reused, "skipped": result.skipped,
            "errors": result.errors[:50],
        }
        self.payload["corpus_counts"] = snapshot.counts
        self._update(payload=self.payload)
        if not snapshot.contract_version_ids:
            raise ValueError("CORPUS_EMPTY")
        return {"snapshot_id": snapshot.snapshot_id, **snapshot.counts,
                "errors": len(result.errors)}

    def stage_discovery(self) -> dict[str, Any]:
        requirements = self.store.get_requirements(self.run_id)
        snapshot = self.store.get_snapshot(self.run_record["corpus_snapshot_id"])
        if snapshot is None:
            raise ValueError("CORPUS_SNAPSHOT_MISSING")
        versions = self.store.get_contract_versions(snapshot.contract_version_ids)
        config = DiscoveryConfig(
            path_a_top_k=self.config.path_a_top_k,
            path_a_per_contract=self.config.path_a_per_contract,
            path_a_max_candidates=self.config.path_a_max_candidates,
            path_a_max_intent_calls=self.config.path_a_max_intent_calls,
            path_b_batch_chars=self.config.path_b_batch_chars,
            path_b_latest_only=self.config.path_b_latest_only,
            path_b_max_calls=self.config.path_b_max_calls,
            path_c_enabled=self.config.path_c_enabled,
            path_c_max_calls=self.config.path_c_max_calls,
            adjudicate_lexical=self.config.adjudicate_lexical,
        )
        result = discover(self.router, self.store, requirements, snapshot, versions,
                          run_id=self.run_id, config=config)
        self.store.replace_impacts(self.run_id, result.impacts)
        evidence = []
        for index, batch in enumerate(result.sweep_batches):
            evidence.append((stable_id("EV", "sweep", self.run_id, index, length=24),
                             "sweep_batch", str(batch.get("contract_version_id") or ""), batch))
        for requirement_id, intents in result.search_intents.items():
            evidence.append((stable_id("EV", "intent", requirement_id, length=24),
                             "search_intents", requirement_id, {"intents": intents}))
        for index, suspicion in enumerate(result.uncovered_suspicions):
            evidence.append((stable_id("EV", "suspicion", self.run_id, index, length=24),
                             "uncovered_suspicion", str(suspicion.get("contract_version_id") or ""),
                             suspicion))
        self.store.add_evidence_many(self.run_id, evidence)
        self.payload["discovery"] = {
            "impacts": len(result.impacts),
            "statuses": _counts(item.impact_status for item in result.impacts),
            "sources": _counts(source for item in result.impacts for source in item.discovery_sources),
            "sweep_batches": len(result.sweep_batches),
            "uncovered_suspicions": len(result.uncovered_suspicions),
            "path_c_status": result.path_c_status,
            "model_calls": result.model_calls,
            "notes": result.notes[:50],
        }
        self._update(payload=self.payload)
        return {"impacts": len(result.impacts), "sweep_batches": len(result.sweep_batches),
                "path_c_status": result.path_c_status}

    def stage_marker_sweep(self) -> dict[str, Any]:
        batches = self._sweep_batches()
        return {"sweep_batches": len(batches),
                "affected": sum(1 for item in batches if item.get("status") == "affected"),
                "not_affected": sum(1 for item in batches if item.get("status") == "not_affected"),
                "uncertain": sum(1 for item in batches if item.get("status") == "uncertain")}

    def stage_marker_adjudicate(self) -> dict[str, Any]:
        impacts = self._all_impacts()
        missing = [item.impact_id for item in impacts if not item.discovery_sources]
        if missing:
            raise ValueError("IMPACT_DISCOVERY_SOURCE_MISSING")
        return {"impacts": len(impacts),
                "statuses": _counts(item.impact_status for item in impacts)}

    def stage_marker_merge(self) -> dict[str, Any]:
        local = self.store.get_local(self.run_id)
        families = self.store.get_families(self.run_id)
        local_ids = {item.local_id for item in local if item.needs_modification == "yes"}
        family_members = {value for family in families for value in family.get("local_ids") or []}
        orphan_local = sorted(local_ids - family_members)
        if orphan_local:
            raise ValueError("LOCAL_CANDIDATE_NOT_IN_FAMILY:" + ",".join(orphan_local[:10]))
        return {"local_candidates": len(local), "guide_relevant": len(local_ids),
                "families": len(families), "guide_items": len(self._all_items())}

    def stage_authoring(self, impacts: list[ImpactCandidate] | None = None,
                        append: bool = False) -> dict[str, Any]:
        requirements = self.store.get_requirements(self.run_id)
        all_impacts = self._all_impacts()
        target = impacts if impacts is not None else all_impacts
        target = [item for item in target if item.impact_status in {"definite", "possible"}]
        clauses = self._clauses_for_impacts(target)
        config = AuthoringConfig(local_batch_size=self.config.local_batch_size)
        local, calls = build_local_candidates(self.router, requirements, target, clauses, config)
        # Definite impacts may not disappear.  If the author model omitted one
        # or returned only an uncertain candidate, add a conservative
        # regulation-verbatim candidate for human review rather than dropping it.
        requirement_map = {item.requirement_id: item for item in requirements}
        definite_yes = {impact_id for candidate in local
                        if candidate.needs_modification == "yes" and candidate.new_text.strip()
                        for impact_id in candidate.impact_ids}
        for impact in target:
            if impact.impact_status != "definite" or impact.impact_id in definite_yes:
                continue
            requirement = requirement_map.get(impact.requirement_id)
            if requirement is None:
                continue
            section = ""
            if impact.clause_ids:
                clause = clauses.get(impact.clause_ids[0])
                if clause and clause.section_path:
                    section = clause.section_path[0]
            local.append(LocalGuideCandidate(
                local_id=stable_id("LG", impact.impact_id, "definite-fallback", length=20),
                impact_ids=[impact.impact_id], requirement_ids=[requirement.requirement_id],
                section=section, needs_modification="yes",
                business_goal=requirement.requirement,
                semantic_changes=["按法规要求补充或调整该条款；具体措辞需结合合同上下文人工确认。"],
                applicability="确定影响但模型未能给出具体改写时的保守候选，必须人工复核。",
                conditions=list(requirement.conditions), exceptions=list(requirement.exceptions),
                old_text_patterns=[impact.source_text[:800]] if impact.source_text else [],
                new_text=requirement.source_quote,
                new_text_origin="regulation_verbatim",
                notes="definite_impact_fallback",
                payload={"fallback": "definite_impact"},
            ))
            definite_yes.add(impact.impact_id)
        # ``needs_modification`` is an authoring decision, not a discovery
        # deletion: every impact still receives an explicit disposition below.
        impact_map = {item.impact_id: item for item in all_impacts}
        guide_relevant = []
        for candidate in local:
            if candidate.needs_modification == "yes" and candidate.new_text.strip():
                guide_relevant.append(candidate)
                continue
            disposition = ("not_applicable" if candidate.needs_modification == "no"
                           else "unresolved")
            for impact_id in candidate.impact_ids:
                impact = impact_map.get(impact_id)
                if impact is None:
                    continue
                impact.disposition = disposition
                impact.disposition_reason = (impact.disposition_reason + "；" +
                                             (candidate.business_goal or candidate.notes or
                                              "Local GuideCandidate 判定无需修改" if disposition == "not_applicable"
                                              else "Local GuideCandidate 无法确定是否修改")).strip("；")
        self.store.replace_impacts(self.run_id, all_impacts)
        if append:
            existing_local = {item.local_id: item for item in self.store.get_local(self.run_id)}
            existing_local.update({item.local_id: item for item in local})
            local_all_values = list(existing_local.values())
        else:
            local_all_values = local
        self.store.replace_local(self.run_id, local_all_values)
        family_result = induce_families(self.router, guide_relevant, requirements, clauses, config)
        if append:
            existing_families = {item["family_id"]: item for item in self.store.get_families(self.run_id)}
            existing_families.update({item["family_id"]: item for item in family_result.families})
            family_values = list(existing_families.values())
        else:
            family_values = family_result.families
        self.store.replace_families(self.run_id, family_values)
        items = families_to_guide_items(family_result.families, clauses,
                                        {item.impact_id: item for item in all_impacts})
        if append:
            existing_items = {item.guide_item_id: item for item in self._all_items()}
            existing_items.update({item.guide_item_id: item for item in items})
            item_values = list(existing_items.values())
        else:
            item_values = items
        self.store.replace_guide_items(self.run_id, item_values)
        self.payload.setdefault("authoring", []).append({
            "local_candidates": len(local), "guide_relevant": len(guide_relevant),
            "families": len(family_result.families),
            "guide_items": len(items), "model_calls": calls + family_result.calls,
            "append": append,
        })
        self._update(payload=self.payload)
        return {"local_candidates": len(local), "families": len(family_result.families),
                "guide_items": len(items), "model_calls": calls + family_result.calls}

    def stage_quality(self, items: list[GuideItem] | None = None) -> dict[str, Any]:
        requirements = self.store.get_requirements(self.run_id)
        impacts = self._all_impacts()
        all_items = self._all_items()
        reviewed = {"pass", "pass_with_findings", "fail", "human_reviewed"}
        target = items if items is not None else [
            item for item in all_items if item.quality_status not in reviewed]
        clauses = self._clauses_for_impacts(impacts)
        if not target:
            findings = self.store.get_findings(self.run_id)
            return {"run_status": "no_new_items", "findings": len(findings)}
        item_state = {item.guide_item_id: item for item in all_items}

        def on_item(item: GuideItem, item_findings: list[dict[str, Any]]) -> None:
            self._merge_findings(item_findings)
            current = item_state.get(item.guide_item_id)
            if current is not None:
                current.quality_status = item.quality_status
                self.store.update_guide_item(self.run_id, current)

        result = run_quality_gate(self.router, target, requirements, impacts, clauses,
                                  on_item=on_item, max_workers=4)
        all_items = self._all_items()
        for item in all_items:
            if item.guide_item_id in result.item_status:
                item.quality_status = result.item_status[item.guide_item_id]
        self.store.replace_guide_items(self.run_id, all_items)
        all_findings = self.store.get_findings(self.run_id)
        critical = [value for value in all_findings
                    if value.get("severity") == "critical"
                    and value.get("status") in {"open", "", None}
                    and (value.get("source") != "guide_reviewer" or value.get("evidence_verified", True))]
        major = [value for value in all_findings if value.get("severity") == "major"]
        overall = "fail" if critical else ("pass_with_findings" if major else "pass")
        self.payload["quality"] = {
            "run_status": overall, "findings": len(all_findings),
            "item_status": result.item_status, "calls": result.calls,
            "reviewed_now": len(target),
            "independent_model_review": result.independent_review,
        }
        self._update(payload=self.payload)
        return {"run_status": overall, "findings": len(all_findings), "reviewed": len(target)}

    def stage_repair(self) -> dict[str, Any]:
        from .repair import repair_items
        requirements = self.store.get_requirements(self.run_id)
        impacts = self._all_impacts()
        items = self._all_items()
        findings = self.store.get_findings(self.run_id)
        critical = [item for item in findings
                    if item.get("severity") == "critical"
                    and item.get("status") in {"open", "", None}
                    and item.get("category") in {"regulation_fidelity", "draft_text_fidelity",
                                                 "provenance", "generalization", "internal_consistency"}]
        if not critical:
            return {"repaired": 0, "reason": "no_critical_findings"}
        clauses = self._clauses_for_impacts(impacts)
        repaired, fixes, calls = repair_items(self.router, items, requirements, impacts, clauses,
                                              findings)
        if not repaired:
            return {"repaired": 0, "calls": calls}
        repaired_ids = {item.guide_item_id for item in repaired}
        for finding in findings:
            if finding.get("guide_item_id") in repaired_ids and finding.get("status") == "open":
                finding["status"] = "superseded"
                finding["superseded_by"] = "guide_repair"
        findings.extend(fixes)
        self.store.replace_findings(self.run_id, findings)
        self.store.replace_guide_items(self.run_id, items)
        # Re-run the independent review only on the repaired items.  The final
        # critical status is decided by the new findings, not by the old ones.
        self.stage_quality(items=repaired)
        self.payload.setdefault("repair", []).append({
            "repaired": len(repaired), "calls": calls,
            "finding_ids": [item["finding_id"] for item in fixes],
        })
        self._update(payload=self.payload)
        return {"repaired": len(repaired), "calls": calls}

    def stage_coverage(self) -> dict[str, Any]:
        requirements = self.store.get_requirements(self.run_id)
        impacts = self._all_impacts()
        items = self._all_items()
        snapshot = self.store.get_snapshot(self.run_record["corpus_snapshot_id"])
        versions = self.store.get_contract_versions(snapshot.contract_version_ids) if snapshot else []
        clauses = self._clauses_for_impacts(impacts)
        result = run_coverage_gate(
            self.router, requirements, impacts, items, clauses, versions,
            self._sweep_batches(), snapshot,
            semantic_applicability=self.config.semantic_applicability)
        self.store.replace_coverage(self.run_id, result.rows)
        self.store.add_applicability(self.run_id, result.applicability)
        self._merge_findings(result.findings)
        self.store.replace_impacts(self.run_id, impacts)
        coverage_by_item: dict[str, list[str]] = {}
        for row in result.rows:
            if row["level"] == "impact" and row.get("guide_item_ids"):
                for item_id in row["guide_item_ids"]:
                    coverage_by_item.setdefault(item_id, []).append(row["status"])
        for item in items:
            statuses = coverage_by_item.get(item.guide_item_id, [])
            item.coverage_status = ("covered" if statuses and all(value == "covered" for value in statuses)
                                    else ("partial" if statuses else "not_run"))
        self.store.replace_guide_items(self.run_id, items)
        latest_uncertain = sum(
            1 for row in result.rows
            if row.get("level") == "contract_requirement" and row.get("latest_known")
            and row.get("status") == "uncertain")
        self.payload["coverage"] = {
            "run_status": result.run_status,
            "requirements": result.requirement_summary,
            "impacts": result.impact_summary,
            "contracts": result.contract_summary,
            "latest_uncertain": latest_uncertain,
            "findings": len(result.findings), "applicability": len(result.applicability),
            "calls": result.calls,
        }
        self._update(payload=self.payload)
        return {"run_status": result.run_status, **result.requirement_summary,
                **result.impact_summary, "latest_uncertain": latest_uncertain}

    def stage_residual(self) -> dict[str, Any]:
        requirements = self.store.get_requirements(self.run_id)
        impacts = self._all_impacts()
        items = self._all_items()
        snapshot = self.store.get_snapshot(self.run_record["corpus_snapshot_id"])
        versions = self.store.get_contract_versions(snapshot.contract_version_ids) if snapshot else []
        sweep_batches = self._sweep_batches()
        version_ids = {str(batch.get("contract_version_id") or "") for batch in sweep_batches}
        clauses_by_version = {version_id: self.store.get_clauses(version_id)
                              for version_id in version_ids if version_id}
        clauses = {clause.clause_id: clause for values in clauses_by_version.values() for clause in values}
        seen: set[str] = set()
        rounds: list[dict[str, Any]] = []
        clean_streak = 0
        saturated = False
        total_calls = 0
        status = "max_rounds_reached"
        for round_no in range(1, self.config.max_residual_rounds + 1):
            try:
                result = run_residual_mining(
                    self.router, requirements, items, impacts, versions, clauses_by_version, clauses,
                    sweep_batches, config=ResidualConfig(
                        max_rounds=1, required_clean_rounds=1,
                        batch_chars=self.config.path_b_batch_chars,
                        max_calls_per_round=self.config.residual_max_calls_per_round),
                    round_index=round_no - 1, seen_patterns=seen)
            except ModelError as exc:
                if str(exc.code).startswith("GUIDE_RUN_") or str(exc.code).startswith("MODEL_COST_BUDGET"):
                    status = "budget_exhausted"
                    break
                raise
            total_calls += result.calls
            round_item = result.rounds[0] if result.rounds else None
            new_impacts = round_item.new_impacts if round_item else []
            for pattern in {item.get("pattern_key") for item in (round_item.uncovered if round_item else [])
                            if item.get("pattern_key")}:
                seen.add(pattern)
            self.store.add_residual_round(
                self.run_id, round_no, round_item.status if round_item else "not_run", {
                    "new_impacts": len(new_impacts),
                    "new_impact_ids": [item.impact_id for item in new_impacts],
                    "new_patterns": round_item.new_patterns if round_item else 0,
                    "uncovered": round_item.uncovered if round_item else [],
                    "calls": result.calls, "clean_streak": clean_streak,
                })
            self._merge_findings(result.findings)
            rounds.append({"round_no": round_no, "new_impacts": len(new_impacts),
                           "new_patterns": round_item.new_patterns if round_item else 0,
                           "status": round_item.status if round_item else "not_run"})
            if new_impacts:
                clean_streak = 0
                before_ids = {item.guide_item_id for item in self._all_items()}
                self.store.add_impacts(self.run_id, new_impacts)
                impacts = self._all_impacts()
                self.stage_authoring(impacts=new_impacts, append=True)
                items = self._all_items()
                new_items = [item for item in items if item.guide_item_id not in before_ids]
                if new_items:
                    self.stage_quality(items=new_items)
                self.stage_coverage()
                items = self._all_items()
                impacts = self._all_impacts()
            else:
                clean_streak += 1
                if clean_streak >= self.config.required_clean_rounds:
                    saturated = True
                    status = "saturated"
                    break
        self.payload["residual"] = {"rounds": rounds, "saturated": saturated,
                                    "clean_streak": clean_streak, "calls": total_calls,
                                    "status": status}
        self._update(payload=self.payload)
        return self.payload["residual"]

    def stage_finalize(self) -> dict[str, Any]:
        requirements = self.store.get_requirements(self.run_id)
        items = self._all_items()
        findings = self.store.get_findings(self.run_id)
        unhandled = sum(1 for item in requirements if not item.disposition)
        critical_quality = [item for item in findings if item.get("severity") == "critical"
                            and item.get("status") in {"open", "", None}
                            and item.get("category") in {"regulation_fidelity", "draft_text_fidelity",
                                                         "provenance"}
                            and (item.get("source") != "guide_reviewer" or item.get("evidence_verified", True))]
        coverage_summary = self.payload.get("coverage") or {}
        residual_summary = self.payload.get("residual") or {}
        unresolved_impacts = (coverage_summary.get("impacts") or {}).get("unresolved", 0)
        requirement_gaps = (coverage_summary.get("requirements") or {}).get("gap", 0)
        latest_uncertain = coverage_summary.get("latest_uncertain", 0)
        complete = (unhandled == 0 and not critical_quality and requirement_gaps == 0
                    and unresolved_impacts == 0 and latest_uncertain == 0
                    and residual_summary.get("saturated") is True)
        status = "complete" if complete else "complete_with_unresolved"
        qualification = "candidate_ready" if complete else "candidate_with_findings"
        docx_path = self.run_dir / "generated_guide.docx"
        export = export_guide_docx(items, docx_path, title="新法规候选修改指引",
                                   regulation_title=self.run_record.get("title") or "")
        self.store.put_artifact(self.run_id, "guide",
                                str(docx_path.relative_to(self.store.store.objects)),
                                export["sha256"], export["size"])
        ai_path = self.run_dir / "generated_guide_ai.docx"
        ai_path.write_bytes(docx_path.read_bytes())
        self.store.put_artifact(self.run_id, "guide_ai",
                                str(ai_path.relative_to(self.store.store.objects)),
                                export["sha256"], export["size"])
        candidate = self.store.get_candidate(self.run_id)
        current_version = self.store.get_candidate_version(
            self.run_id, candidate["current_version_id"])
        self.payload["finalize"] = {
            "status": status, "qualification_status": qualification,
            "unhandled_requirements": unhandled,
            "critical_quality_findings": len(critical_quality),
            "requirement_gaps": requirement_gaps,
            "unresolved_impacts": unresolved_impacts,
            "latest_contract_uncertain": latest_uncertain,
            "residual_saturated": bool(residual_summary.get("saturated")),
            "checklist": {
                "all_requirements_have_evidence": all(item.source_quote and item.source_block_ids
                                                      for item in requirements),
                "all_requirements_dispositioned": unhandled == 0,
                "all_guide_items_have_requirement": all(item.requirement_ids for item in items),
                "all_guide_items_have_impact": all(item.impact_ids for item in items),
                "all_guide_items_have_new_text_origin": all(item.new_text_origin for item in items),
                "requirement_coverage_complete": requirement_gaps == 0,
                "impact_coverage_complete": unresolved_impacts == 0,
                "latest_contract_coverage_complete": latest_uncertain == 0,
                "residual_saturated": bool(residual_summary.get("saturated")),
            },
        }
        if current_version.get("status") == "draft":
            version = self.store.create_candidate_version(
                self.run_id, status=qualification,
                payload={
                    "schema_version": "candidate-guide-version-1",
                    "run_id": self.run_id,
                    "source_sha256": self.run_record.get("source_sha256", ""),
                    "regulation_document_sha256": self.run_record.get(
                        "regulation_document_sha256", ""),
                    "guide_items": [item.to_dict() for item in items],
                    "finalize": self.payload["finalize"],
                    "guide_artifact": {"kind": "guide", "sha256": export["sha256"],
                                       "size": export["size"],
                                       "object_key": str(docx_path.relative_to(self.store.store.objects))},
                    "ai_artifact": {"kind": "guide_ai", "sha256": export["sha256"],
                                    "size": export["size"],
                                    "object_key": str(ai_path.relative_to(self.store.store.objects))},
                },
                content_sha256=sha256_json([item.to_dict() for item in items]),
                expected_current_version_id=current_version["candidate_version_id"])
            self.payload["candidate_version_id"] = version["candidate_version_id"]
            self.payload["candidate_version_no"] = version["version_no"]
        self._update(status=status, stage="FINALIZE_GUIDE",
                     qualification_status=qualification,
                     guide_sha256=export["sha256"], payload=self.payload)
        return self.payload["finalize"]

    def stage_evidence(self) -> dict[str, Any]:
        run = self.store.get_run(self.run_id)
        blocks = [block.to_dict() for block in self.store.get_blocks(self.run_id)]
        requirements = [item.to_dict() for item in self.store.get_requirements(self.run_id)]
        impacts = [item.to_dict() for item in self._all_impacts()]
        items = [item.to_dict() for item in self._all_items()]
        findings = self.store.get_findings(self.run_id)
        coverage = self.store.get_coverage(self.run_id)
        applicability = self.store.get_applicability(self.run_id)
        residual_rounds = self.store.get_residual_rounds(self.run_id)
        model_calls = self.store.get_model_calls(self.run_id)
        local = [item.to_dict() for item in self.store.get_local(self.run_id)]
        families = self.store.get_families(self.run_id)
        engine_results = self.store.get_engine_results(self.run_id)
        engine_runs = self.store.get_engine_runs(self.run_id)
        engine_package = {"status": "not_run", "runs": engine_runs, "results": engine_results}
        package = build_evidence_package(
            run={**run, "stats": self.store.stats(self.run_id)},
            regulation={"document_id": run.get("regulation_document_id"),
                        "title": run.get("title"), "source_type": run.get("source_type"),
                        "source_sha256": run.get("source_sha256"),
                        "document_sha256": run.get("regulation_document_sha256"),
                        "blocks": blocks},
            requirements=requirements, impacts=impacts, local_candidates=local,
            families=families, guide_items=items, findings=findings, coverage=coverage,
            applicability=applicability, residual_rounds=residual_rounds,
            model_calls=model_calls, model_identity=self.router.identity(),
            engine_compatibility=engine_package,
            human_versions=self.store.list_human_versions(self.run_id),
            human_changes=self.store.list_human_changes(self.run_id),
        )
        evidence_path = self.run_dir / "guide_generation_evidence.json"
        evidence_path.write_text(json.dumps(package, ensure_ascii=False, indent=2, default=str),
                                 encoding="utf-8")
        html_path = self.run_dir / "guide_generation_report.html"
        html_path.write_text(render_evidence_html(package), encoding="utf-8")
        evidence_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        report_sha = hashlib.sha256(html_path.read_bytes()).hexdigest()
        self.store.put_artifact(self.run_id, "evidence_json",
                                str(evidence_path.relative_to(self.store.store.objects)),
                                evidence_sha, evidence_path.stat().st_size)
        self.store.put_artifact(self.run_id, "evidence_html",
                                str(html_path.relative_to(self.store.store.objects)),
                                report_sha, html_path.stat().st_size)
        self._update(evidence_sha256=evidence_sha, report_sha256=report_sha,
                     stage="BUILD_EVIDENCE", payload=self.payload)
        return {"evidence_sha256": evidence_sha, "report_sha256": report_sha}

    def run(self) -> dict[str, Any]:
        self._update(status="running", stage="INGEST_REGULATION",
                     commit_sha=self.payload["commit_sha"], code_build=self.payload["code_build"],
                     runtime_config_sha256=self.payload["runtime_config_sha256"],
                     lockfile_sha256=self.payload["lockfile_sha256"], payload=self.payload)
        identity_hash = sha256_json(self.router.identity())
        source_hash = self.run_record.get("source_sha256") or ""
        self._stage("INGEST_REGULATION", sha256_json({"source": source_hash, "parser": "regulation-1"}),
                    self.stage_ingest)
        self._stage("EXTRACT_REQUIREMENTS",
                    sha256_json({"document": self.run_record.get("regulation_document_sha256"),
                                 "identity": identity_hash, "prompts": "requirements-v1"}),
                    self.stage_extract)
        self._stage("VERIFY_REQUIREMENTS",
                    sha256_json({"requirements": [item.to_dict() for item in self.store.get_requirements(self.run_id)]}),
                    self.stage_verify)
        self._stage("BUILD_CORPUS_SNAPSHOT",
                    sha256_json({"corpus_dir": self.config.corpus_dir,
                                 "limit": self.config.corpus_limit,
                                 "parser": "contract-segmenter-1"}),
                    self.stage_snapshot)
        self._stage("DISCOVERY_REQUIREMENT_RETRIEVAL",
                    sha256_json({"snapshot": self.run_record.get("corpus_snapshot_id"),
                                 "requirements": [item.to_dict() for item in self.store.get_requirements(self.run_id)],
                                 "identity": identity_hash, "config": self.config.to_dict()}),
                    self.stage_discovery)
        self._stage("DISCOVERY_CONTRACT_SWEEP",
                    sha256_json({"snapshot": self.run_record.get("corpus_snapshot_id"),
                                 "config": self.config.to_dict()}),
                    self.stage_marker_sweep)
        self._stage("ADJUDICATE_IMPACTS",
                    sha256_json({"impacts": [item.impact_id for item in self._all_impacts()]}),
                    self.stage_marker_adjudicate)
        self._stage("BUILD_LOCAL_GUIDE_CANDIDATES",
                    sha256_json({"impacts": [item.impact_id for item in self._all_impacts()],
                                 "identity": identity_hash}),
                    self.stage_authoring)
        self._stage("MERGE_AND_GENERALIZE",
                    sha256_json({"locals": [item.local_id for item in self.store.get_local(self.run_id)]}),
                    self.stage_marker_merge)
        self._stage("GUIDE_QUALITY_REVIEW",
                    sha256_json({"items": [item.to_dict() for item in self._all_items()],
                                 "identity": identity_hash}),
                    self.stage_quality)
        self._stage("GUIDE_REPAIR",
                    sha256_json({"items": [item.to_dict() for item in self._all_items()],
                                 "findings": self.store.get_findings(self.run_id),
                                 "identity": identity_hash}),
                    self.stage_repair)
        self._stage("SEMANTIC_COVERAGE",
                    sha256_json({"items": [item.to_dict() for item in self._all_items()],
                                 "impacts": [item.impact_id for item in self._all_impacts()],
                                 "identity": identity_hash}),
                    self.stage_coverage)
        self._stage("RESIDUAL_MINING",
                    sha256_json({"items": [item.to_dict() for item in self._all_items()],
                                 "impacts": [item.impact_id for item in self._all_impacts()],
                                 "config": self.config.to_dict()}),
                    self.stage_residual)
        self._stage("FINALIZE_GUIDE",
                    sha256_json({"items": [item.to_dict() for item in self._all_items()],
                                 "coverage": self.payload.get("coverage"),
                                 "residual": self.payload.get("residual")}),
                    self.stage_finalize)
        self._stage("BUILD_EVIDENCE",
                    sha256_json({"items": [item.to_dict() for item in self._all_items()],
                                 "findings": self.store.get_findings(self.run_id),
                                 "coverage": self.payload.get("coverage")}),
                    self.stage_evidence)
        if self.config.run_engine_compatibility:
            self.run_record_engine_compatibility()
        final_status = (self.payload.get("finalize") or {}).get("status") or "complete_with_unresolved"
        self._update(status=final_status, stage="COMPLETED", payload=self.payload)
        return self.store.get_run(self.run_id)

    def run_engine_compatibility(self) -> dict[str, Any]:
        artifact = self.store.get_artifact(self.run_id, "guide")
        if not artifact:
            raise ValueError("GUIDE_ARTIFACT_MISSING")
        guide_path = self.store.store.object_path(artifact["object_key"])
        requirements = self.store.get_requirements(self.run_id)
        items = self._all_items()
        output = self.run_dir / "engine_compatibility"
        result = run_engine_compatibility(
            guide_docx=guide_path, items=items, requirements=requirements,
            router=self.router, sample_contract=self.config.sample_contract or None,
            output_dir=output)
        attempt = len(self.store.get_engine_runs(self.run_id)) + 1
        self.store.save_engine_run(self.run_id, attempt, result.get("status", "completed"), result)
        self.store.replace_engine_results(self.run_id, result.get("results") or [])
        json_path = self.run_dir / "engine_compatibility_report.json"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                             encoding="utf-8")
        html_path = self.run_dir / "engine_compatibility_report.html"
        html_path.write_text(_engine_html(result), encoding="utf-8")
        for kind, path in (("engine_json", json_path), ("engine_html", html_path)):
            data = path.read_bytes()
            self.store.put_artifact(self.run_id, kind,
                                    str(path.relative_to(self.store.store.objects)),
                                    hashlib.sha256(data).hexdigest(), len(data))
        self._update(engine_status=result.get("status", "completed"), payload=self.payload)
        return result


def _engine_html(result: dict[str, Any]) -> str:
    import html as _html
    rows = "".join(
        f"<tr><td>{_html.escape(str(item.get('guide_item_id')))}</td>"
        f"<td>{_html.escape(str(item.get('classification')))}</td>"
        f"<td>{_html.escape(str(item.get('reason')))}</td></tr>"
        for item in result.get("results") or [])
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>Engine Compatibility</title><style>body{{font-family:sans-serif;margin:32px}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px;text-align:left}}</style></head><body>
<h1>Engine Compatibility Report</h1>
<p>独立于 Guide Quality / Coverage。当前解析组：{_html.escape(str(result.get('parsed_groups')))}；parse_error：{_html.escape(str(result.get('parse_error')))}。</p>
<p>分类：{_html.escape(json.dumps(result.get('classification_counts') or {}, ensure_ascii=False))}</p>
<p>Sample run：{_html.escape(json.dumps(result.get('sample_contract_run') or {}, ensure_ascii=False))}</p>
<table><thead><tr><th>GuideItem</th><th>Classification</th><th>Reason</th></tr></thead><tbody>{rows}</tbody></table>
</body></html>"""
