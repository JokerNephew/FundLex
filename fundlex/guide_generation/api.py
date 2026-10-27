"""HTTP API for regulation-driven candidate guide generation.

Routes are owner-scoped and reuse the FundLex authentication dependency.  The
API only enqueues long-running work; the worker performs all model calls.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..store import Conflict, NotFound, RunStore
from .human import rebuild_evidence, update_guide_item
from .models import sha256_bytes
from .store import GuideGenerationStore

MAX_REGULATION_BYTES = 80 * 1024 * 1024
ALLOWED_SUFFIXES = {".docx", ".pdf"}
DOWNLOAD_KINDS = {
    "guide": ("generated_guide.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "guide_ai": ("generated_guide_ai.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "evidence_json": ("guide_generation_evidence.json", "application/json"),
    "evidence_html": ("guide_generation_report.html", "text/html"),
    "engine_json": ("engine_compatibility_report.json", "application/json"),
    "engine_html": ("engine_compatibility_report.html", "text/html"),
}


class GuideItemUpdate(BaseModel):
    title: str | None = None
    business_requirement: str | None = None
    instruction: str | None = None
    applicability: str | None = None
    conditions: list[str] | str | None = None
    exceptions: list[str] | str | None = None
    old_text_patterns: list[str] | str | None = None
    new_text: str | None = None
    new_text_origin: str | None = None
    expected_current_version_id: str | None = None


class CandidateVersionRequest(BaseModel):
    version_id: str | None = None


class PublicPipelineConfig(BaseModel):
    """Public tuning only; filesystem access and spending limits are server-owned."""

    model_config = ConfigDict(extra="forbid", strict=True)
    corpus_limit: int | None = Field(default=None, ge=1, le=10000)
    path_a_top_k: int = Field(default=30, ge=1, le=100)
    path_a_per_contract: int = Field(default=1, ge=1, le=10)
    path_a_max_candidates: int = Field(default=60, ge=1, le=200)
    path_a_max_intent_calls: int = Field(default=12, ge=0, le=100)
    path_b_batch_chars: int = Field(default=12000, ge=1000, le=32000)
    path_b_latest_only: bool = True
    path_b_max_calls: int = Field(default=4000, ge=1, le=4000)
    path_c_enabled: bool = True
    path_c_max_calls: int = Field(default=240, ge=0, le=240)
    adjudicate_lexical: bool = True
    local_batch_size: int = Field(default=12, ge=1, le=50)
    max_residual_rounds: int = Field(default=4, ge=1, le=4)
    required_clean_rounds: int = Field(default=2, ge=1, le=4)
    residual_max_calls_per_round: int = Field(default=600, ge=1, le=600)
    semantic_applicability: bool = True


def public_pipeline_config(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
        options = PublicPipelineConfig.model_validate(value)
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(422, "CONFIG_INVALID") from None
    result = options.model_dump(exclude_unset=True)
    # Bounded initial scope is explicit in the returned/persisted config and
    # corpus snapshot. A wider reference corpus requires an explicit limit.
    if result.get("corpus_limit") is None:
        result["corpus_limit"] = max(1, min(10000, int(os.environ.get(
            "FUNDLEX_GUIDE_DEFAULT_CORPUS_LIMIT", "1"))))
    # Never take these values from a multipart client, even for compatibility.
    result.update({
        "corpus_dir": os.environ.get("FUNDLEX_GUIDE_CORPUS_DIR") or str(
            Path(__file__).resolve().parent.parent.parent / "funds_word"),
        "soft_max_calls": int(os.environ.get("FUNDLEX_GUIDE_RUN_MAX_CALLS", "6000")),
        "soft_max_cost": float(os.environ.get("FUNDLEX_GUIDE_RUN_MAX_COST_USD", "12")),
    })
    return result


def _public_run(gg: GuideGenerationStore, run: dict[str, Any], *, detail: bool = False) -> dict[str, Any]:
    payload = run.get("payload") or {}
    base = {key: run.get(key) for key in (
        "id", "owner", "filename", "title", "status", "stage", "error_code",
        "created_at", "updated_at", "corpus_snapshot_id", "regulation_document_id",
        "regulation_document_sha256", "guide_sha256", "evidence_sha256", "report_sha256",
        "engine_status", "qualification_status", "commit_sha", "code_build")}
    base["stats"] = gg.stats(run["id"])
    base["stages"] = gg.list_steps(run["id"])
    base["retry"] = gg.retry_state(run["id"])
    base["artifacts"] = {
        item["kind"]: f"/api/guide-generation/runs/{run['id']}/download/{item['kind']}"
        for item in gg.list_artifacts(run["id"])
    }
    base["summary"] = {
        "finalize": payload.get("finalize"),
        "coverage": payload.get("coverage"),
        "quality": payload.get("quality"),
        "residual": payload.get("residual"),
        "discovery": payload.get("discovery"),
        "corpus_counts": payload.get("corpus_counts"),
        "requirement_verification": payload.get("requirement_verification"),
        "path_c_status": (payload.get("discovery") or {}).get("path_c_status"),
    }
    try:
        candidate = gg.get_candidate(run["id"], owner=run.get("owner"))
        current = gg.get_candidate_version(run["id"], candidate["current_version_id"],
                                           owner=run.get("owner"))
        base["candidate"] = {
            "candidate_guide_id": candidate["candidate_guide_id"],
            "status": candidate["status"],
            "current_version_id": candidate["current_version_id"],
            "current_version_no": current.get("version_no"),
            "human_review_override": bool((current.get("payload") or {}).get("human_review_override")),
        }
    except NotFound:
        base["candidate"] = None
    if detail:
        base["model_identity"] = payload.get("model_identity") or {}
        base["config"] = {key: value for key, value in (payload.get("config") or {}).items()
                          if key in PublicPipelineConfig.model_fields}
        base["requirement_notes"] = payload.get("requirement_notes") or ""
        base["article_dispositions"] = payload.get("article_dispositions") or {}
        base["human_edited"] = bool(payload.get("human_edited"))
        base["human_version"] = payload.get("human_version")
    return base


def register_guide_generation_routes(application, store: RunStore,
                                     gg: GuideGenerationStore, user_dependency) -> None:
    gg.ensure_schema()
    application.state.guide_generation = gg

    def run_for(user: str, run_id: str) -> dict[str, Any]:
        try:
            return gg.get_run_for_owner(user, run_id)
        except Exception:
            raise HTTPException(404, "guide generation run not found") from None

    @application.post("/api/guide-generation/runs", status_code=201)
    async def create_guide_run(
            file: UploadFile = File(...),
            config: str = Form("{}"),
            user: str = Depends(user_dependency)):
        try:
            filename = Path((file.filename or "").replace("\\", "/")).name.strip()
            suffix = Path(filename).suffix.lower()
            if suffix not in ALLOWED_SUFFIXES:
                raise HTTPException(422, "REGULATION_TYPE_UNSUPPORTED")
            config_payload = public_pipeline_config(config)
            data = await file.read(MAX_REGULATION_BYTES + 1)
            if len(data) > MAX_REGULATION_BYTES:
                raise HTTPException(413, "REGULATION_FILE_LIMIT")
            if not data:
                raise HTTPException(422, "REGULATION_EMPTY")
        finally:
            await file.close()
        digest = sha256_bytes(data)
        run = gg.create_run(owner=user, filename=filename, source_type=suffix[1:],
                            source_sha256=digest, title=Path(filename).stem,
                            payload={"config": config_payload, "source_sha256": digest,
                                     "uploaded_filename": filename})
        relpath = f"guide_generation/{run['id']}/source{suffix}"
        target = store.object_path(relpath)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        gg.update_run(run["id"], payload={
            **(run.get("payload") or {}),
            "source_relpath": relpath,
            "source_object_key": relpath,
            "source_size": len(data),
        })
        gg.enqueue(run["id"])
        return _public_run(gg, gg.get_run(run["id"]), detail=True)

    @application.get("/api/guide-generation/runs")
    def list_guide_runs(limit: int = Query(default=50, ge=1, le=200),
                        q: str = "", status: str = "",
                        page: int | None = Query(default=None, ge=1),
                        page_size: int | None = Query(default=None, ge=1, le=200),
                        user: str = Depends(user_dependency)):
        result = gg.page_runs(user, q=q, status=status, page=page or 1,
                              page_size=(page_size or 50) if page is not None or page_size is not None else limit)
        result["items"] = [_public_run(gg, run) for run in result["items"]]
        return result

    @application.get("/api/guide-generation/runs/{run_id}")
    def get_guide_run(run_id: str, user: str = Depends(user_dependency)):
        return _public_run(gg, run_for(user, run_id), detail=True)

    @application.post("/api/guide-generation/runs/{run_id}/resume", status_code=202)
    def resume_guide_run(run_id: str, user: str = Depends(user_dependency)):
        run_for(user, run_id)
        try:
            run = gg.resume(user, run_id)
        except NotFound:
            raise HTTPException(404, "guide generation run not found") from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        return _public_run(gg, run, detail=True)

    @application.get("/api/guide-generation/runs/{run_id}/requirements")
    def guide_requirements(run_id: str, user: str = Depends(user_dependency)):
        run_for(user, run_id)
        return {"items": [item.to_dict() for item in gg.get_requirements(run_id)]}

    @application.get("/api/guide-generation/runs/{run_id}/impacts")
    def guide_impacts(run_id: str, requirement_id: str = "", status: str = "",
                      page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200),
                      user: str = Depends(user_dependency)):
        run_for(user, run_id)
        impacts = gg.get_impacts(run_id, requirement_id=requirement_id, impact_status=status)
        start = (page - 1) * page_size
        return {"total": len(impacts), "page": page, "page_size": page_size,
                "items": [item.to_dict() for item in impacts[start:start + page_size]]}

    @application.get("/api/guide-generation/runs/{run_id}/guide")
    def guide_items(run_id: str, user: str = Depends(user_dependency)):
        run_for(user, run_id)
        return {"items": [item.to_dict() for item in gg.get_guide_items(run_id)],
                "families": gg.get_families(run_id),
                "human_versions": gg.list_human_versions(run_id),
                 "human_changes": gg.list_human_changes(run_id),
                 "guide_sha256": gg.get_run(run_id).get("guide_sha256")}

    @application.get("/api/guide-generation/runs/{run_id}/candidate")
    def candidate_guide(run_id: str, user: str = Depends(user_dependency)):
        run_for(user, run_id)
        candidate = gg.get_candidate(run_id, owner=user)
        return {
            "candidate_guide_id": candidate["candidate_guide_id"],
            "run_id": run_id,
            "owner": candidate["owner"],
            "status": candidate["status"],
            "current_version_id": candidate["current_version_id"],
            "versions": candidate["versions"],
        }

    @application.post("/api/guide-generation/runs/{run_id}/candidate/approve")
    def approve_candidate(run_id: str, request: CandidateVersionRequest | None = None,
                          user: str = Depends(user_dependency)):
        run = run_for(user, run_id)
        if run.get("status") not in {"complete", "complete_with_unresolved", "completed"}:
            raise HTTPException(409, "RUN_NOT_COMPLETE")
        candidate = gg.get_candidate(run_id, owner=user)
        version_id = (request.version_id if request else None) or candidate["current_version_id"]
        try:
            version = gg.approve_candidate(run_id, actor=user, version_id=version_id, owner=user)
        except (Conflict, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None
        return {"status": "approved", "version": version,
                "review_mode": "human_override" if (version.get("payload") or {}).get(
                    "human_review_override") else "qualified_candidate",
                "qualification_status": run.get("qualification_status")}

    @application.post("/api/guide-generation/runs/{run_id}/candidate/publish")
    def publish_candidate(run_id: str, request: CandidateVersionRequest | None = None,
                          user: str = Depends(user_dependency)):
        run = run_for(user, run_id)
        if run.get("status") not in {"complete", "complete_with_unresolved", "completed"}:
            raise HTTPException(409, "RUN_NOT_COMPLETE")
        candidate = gg.get_candidate(run_id, owner=user)
        version_id = (request.version_id if request else None) or candidate["current_version_id"]
        try:
            version = gg.publish_candidate(run_id, actor=user, version_id=version_id, owner=user)
        except (Conflict, ValueError) as exc:
            raise HTTPException(409, str(exc)) from None
        return {"status": "published", "version": version,
                "review_mode": "human_override" if (version.get("payload") or {}).get(
                    "human_review_override") else "qualified_candidate",
                "qualification_status": run.get("qualification_status"),
                "runtime_guide_import": "not_requested"}

    @application.patch("/api/guide-generation/runs/{run_id}/guide/items/{item_id}")
    def edit_guide_item(run_id: str, item_id: str, payload: GuideItemUpdate,
                        user: str = Depends(user_dependency)):
        run_for(user, run_id)
        try:
            changes = payload.model_dump(exclude_unset=True)
            expected_version = changes.pop("expected_current_version_id", None)
            result = update_guide_item(gg, run_id, item_id, changes, user,
                                       expected_current_version_id=expected_version)
        except KeyError:
            raise HTTPException(404, "guide item not found") from None
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from None
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from None
        return result

    @application.get("/api/guide-generation/runs/{run_id}/quality")
    def guide_quality(run_id: str, user: str = Depends(user_dependency)):
        run = run_for(user, run_id)
        findings = gg.get_findings(run_id)
        return {"summary": (run.get("payload") or {}).get("quality") or {},
                "findings": findings}

    @application.get("/api/guide-generation/runs/{run_id}/coverage")
    def guide_coverage(run_id: str, level: str = "", status: str = "",
                       limit: int = Query(default=500, ge=1, le=5000),
                       user: str = Depends(user_dependency)):
        run = run_for(user, run_id)
        rows = gg.get_coverage(run_id, level)
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return {"summary": (run.get("payload") or {}).get("coverage") or {},
                "total": len(rows), "items": rows[:limit],
                "applicability": gg.get_applicability(run_id)[:limit]}

    @application.get("/api/guide-generation/runs/{run_id}/residual")
    def guide_residual(run_id: str, user: str = Depends(user_dependency)):
        run = run_for(user, run_id)
        return {"summary": (run.get("payload") or {}).get("residual") or {},
                "rounds": gg.get_residual_rounds(run_id)}

    @application.get("/api/guide-generation/runs/{run_id}/evidence")
    def guide_evidence(run_id: str, user: str = Depends(user_dependency)):
        run = run_for(user, run_id)
        artifact = gg.get_artifact(run_id, "evidence_json")
        if not artifact:
            raise HTTPException(404, "evidence not ready")
        return JSONResponse(content={"artifact": {
            "sha256": artifact["sha256"], "size": artifact["size"],
            "download_url": f"/api/guide-generation/runs/{run_id}/download/evidence_json",
            "report_url": f"/api/guide-generation/runs/{run_id}/download/evidence_html",
        }, "summary": _public_run(gg, run, detail=True)["summary"]})

    @application.get("/api/guide-generation/runs/{run_id}/report", response_class=HTMLResponse)
    def guide_report(run_id: str, user: str = Depends(user_dependency)):
        run_for(user, run_id)
        artifact = gg.get_artifact(run_id, "evidence_html")
        if not artifact:
            raise HTTPException(404, "report not ready")
        path = store.object_path(artifact["object_key"])
        if not path.is_file():
            raise HTTPException(404, "report not ready")
        return HTMLResponse(path.read_text(encoding="utf-8"))

    @application.get("/api/guide-generation/runs/{run_id}/download/{kind}")
    def guide_download(run_id: str, kind: str, user: str = Depends(user_dependency)):
        run_for(user, run_id)
        artifact = gg.get_artifact(run_id, kind)
        if not artifact:
            raise HTTPException(404, "artifact not found")
        path = store.object_path(artifact["object_key"])
        if not path.is_file():
            raise HTTPException(404, "artifact not found")
        filename, media_type = DOWNLOAD_KINDS.get(
            kind, (Path(artifact["object_key"]).name, "application/octet-stream"))
        return FileResponse(path, media_type=media_type, filename=filename)

    @application.post("/api/guide-generation/runs/{run_id}/engine-compatibility", status_code=202)
    def guide_engine_compatibility(run_id: str, user: str = Depends(user_dependency)):
        run = run_for(user, run_id)
        if run.get("status") not in {"complete", "complete_with_unresolved", "completed"}:
            raise HTTPException(409, "RUN_NOT_COMPLETE")
        payload = run.get("payload") or {}
        payload["engine_requested"] = True
        gg.update_run(run_id, engine_status="queued", payload=payload)
        gg.enqueue(run_id)
        return {"status": "queued"}

    @application.get("/api/guide-generation/corpus")
    def guide_corpus(user: str = Depends(user_dependency)):
        snapshots = gg.list_snapshots(limit=5)
        latest = snapshots[0] if snapshots else None
        versions = gg.list_contract_versions()
        return {
            "default_corpus_limit": public_pipeline_config("{}")["corpus_limit"],
            "scope_note": "默认仅使用服务端配置数量的参考合同；候选核验范围以任务语料快照为准，不代表全库核验。",
            "latest_snapshot": latest.to_dict() if latest else None,
            "contracts": len(versions),
            "latest_contracts": sum(1 for item in versions if item.latest_known_version),
            "historical_contracts": sum(1 for item in versions if not item.latest_known_version),
            "parsed": sum(1 for item in versions if item.status == "parsed"),
            "parse_failed": sum(1 for item in versions if item.status == "parse_failed"),
        }

    @application.post("/api/guide-generation/runs/{run_id}/rebuild-evidence", status_code=202)
    def guide_rebuild_evidence(run_id: str, user: str = Depends(user_dependency)):
        run_for(user, run_id)
        return rebuild_evidence(gg, run_id)
