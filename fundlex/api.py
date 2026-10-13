"""Local development HTTP API. Run with ``uvicorn fundlex.api:app``.

The development identity adapter requires X-FundLex-User on every API request.
Production identity integration is deliberately unconfigured and fails closed.
"""

from __future__ import annotations

import io
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .store import Conflict, NotFound, RunStore
from .config import local_data_dir


MAX_UPLOAD_BYTES = int(os.environ.get("FUNDLEX_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UNCOMPRESSED_BYTES = int(os.environ.get("FUNDLEX_MAX_UNCOMPRESSED_BYTES", str(200 * 1024 * 1024)))
MAX_BATCH_DOCUMENTS = int(os.environ.get("FUNDLEX_MAX_BATCH_DOCUMENTS", "20"))
MAX_BATCH_BYTES = int(os.environ.get("FUNDLEX_MAX_BATCH_BYTES", str(50 * 1024 * 1024)))
MAX_PART_BYTES = int(os.environ.get("FUNDLEX_MAX_PART_BYTES", str(32 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = int(os.environ.get("FUNDLEX_MAX_COMPRESSION_RATIO", "100"))


def _user(x_fundlex_user: str | None = Header(default=None)) -> str:
    if os.environ.get("FUNDLEX_AUTH_MODE", "dev") != "dev":
        raise HTTPException(503, "production identity provider is not configured")
    if not x_fundlex_user or not x_fundlex_user.strip() or len(x_fundlex_user) > 128:
        raise HTTPException(401, "development identity header required")
    return x_fundlex_user.strip()


def _validate_upload(name: str, data: bytes) -> str:
    safe_name = Path(name.replace("\\", "/")).name
    if not safe_name or not safe_name.lower().endswith(".docx"):
        raise HTTPException(415, "only DOCX files are supported")
    if not data or len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "DOCX upload size limit exceeded")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise HTTPException(415, "not an editable DOCX package")
            if any(info.flag_bits & 0x1 for info in archive.infolist()):
                raise HTTPException(415, "encrypted DOCX is unsupported")
            members = archive.infolist()
            if len({info.filename for info in members}) != len(members):
                raise HTTPException(415, "duplicate DOCX member")
            if any(info.file_size > MAX_PART_BYTES for info in members):
                raise HTTPException(413, "DOCX part size limit exceeded")
            if any(info.file_size > MAX_COMPRESSION_RATIO * max(info.compress_size, 1) for info in members):
                raise HTTPException(413, "DOCX compression ratio limit exceeded")
            if sum(info.file_size for info in members) > MAX_UNCOMPRESSED_BYTES:
                raise HTTPException(413, "DOCX expanded size limit exceeded")
    except (zipfile.BadZipFile, zipfile.LargeZipFile):
        raise HTTPException(415, "invalid DOCX package") from None
    return safe_name


def _public_batch(batch: dict, *, detail: bool) -> dict:
    docs = batch["documents"]
    base = {
        "id": batch["id"], "status": batch["status"], "ruleset_version": batch["ruleset_version"],
        "ruleset_sha256": batch["ruleset_sha256"],
        "total": len(docs), "completed": sum(d["status"] in {"succeeded", "failed"} for d in docs),
        "failed": sum(d["status"] == "failed" for d in docs),
        "qualification_counts": dict(Counter(d["qualification_status"] or "pending" for d in docs)),
        "delivery_counts": dict(Counter(d["delivery_status"] for d in docs)),
        "created_at": datetime.fromtimestamp(batch["created_at"], timezone.utc).isoformat(),
    }
    if detail:
        base["documents"] = [{
            "document_id": d["id"], "name": d["filename"], "job_status": d["status"],
            "eligibility": d["qualification_status"], "delivery_status": d["delivery_status"],
            "error_code": d["error_code"], "report_url": d["report_url"],
            "downloads": d["download_urls"], "source_sha256": d["source_sha256"],
        } for d in docs]
    return base


def create_app(data_dir: str | Path | None = None) -> FastAPI:
    application = FastAPI(title="FundLex", version="0.1.0")
    store = RunStore(data_dir or local_data_dir())
    application.state.store = store

    @application.get("/api/health")
    def health(user: str = Depends(_user)):
        return {"status": "ok", "profile": "local", "user": user}

    @application.get("/api/batches")
    def list_batches(user: str = Depends(_user)):
        return {"batches": [_public_batch(item, detail=False) for item in store.list_batches(user)]}

    @application.post("/api/batches", status_code=201)
    async def submit_batch(files: list[UploadFile] = File(...), ruleset_version: str = Form(...),
                           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                           user: str = Depends(_user)):
        if not ruleset_version.strip() or len(ruleset_version) > 128:
            raise HTTPException(422, "invalid ruleset version")
        from .rules import RuleError, load_ruleset
        try:
            ruleset = load_ruleset(ruleset_version.strip())
        except RuleError as exc:
            raise HTTPException(422, str(exc)) from exc
        if len(files) > MAX_BATCH_DOCUMENTS:
            raise HTTPException(413, "batch document count limit exceeded")
        if idempotency_key and len(idempotency_key) > 128:
            raise HTTPException(422, "idempotency key too long")
        uploads = []
        total_bytes = 0
        for upload in files:
            data = await upload.read(MAX_UPLOAD_BYTES + 1)
            total_bytes += len(data)
            if total_bytes > MAX_BATCH_BYTES:
                raise HTTPException(413, "batch upload size limit exceeded")
            name = _validate_upload(upload.filename or "", data)
            uploads.append((name, data))
        try:
            result = store.create_batch(owner=user, ruleset_version=ruleset_version.strip(),
                                        ruleset_sha256=ruleset.sha256,
                                        uploads=uploads, idempotency_key=idempotency_key)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        return _public_batch(result, detail=True)

    @application.get("/api/batches/{batch_id}")
    def get_batch(batch_id: str, user: str = Depends(_user)):
        try:
            return _public_batch(store.get_batch(user, batch_id), detail=True)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @application.post("/api/batches/{batch_id}/pause")
    def pause_batch(batch_id: str, user: str = Depends(_user)):
        try:
            return _public_batch(store.pause(user, batch_id), detail=True)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @application.post("/api/batches/{batch_id}/resume")
    def resume_batch(batch_id: str, user: str = Depends(_user)):
        try:
            return _public_batch(store.resume(user, batch_id), detail=True)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @application.get("/api/batches/{batch_id}/documents/{document_id}/report")
    def document_report(batch_id: str, document_id: str, user: str = Depends(_user)):
        try:
            return store.get_report(user, batch_id, document_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @application.get("/api/batches/{batch_id}/documents/{document_id}/download/{kind}")
    def download(batch_id: str, document_id: str, kind: str, user: str = Depends(_user)):
        if kind not in {"final", "redline", "report_json", "report_md"}:
            raise HTTPException(404, "artifact not found")
        try:
            path, digest = store.get_artifact(user, batch_id, document_id, kind)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if kind in {"final", "redline"} else ("application/json" if kind == "report_json" else "text/markdown")
        return FileResponse(path, media_type=media, filename=f"{document_id}_{kind}{path.suffix}",
                            headers={"ETag": digest, "Cache-Control": "private, no-store"})

    @application.get("/api/batches/{batch_id}/report")
    def batch_report(batch_id: str, user: str = Depends(_user)):
        try:
            batch = store.get_batch(user, batch_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        qualifications: Counter[str] = Counter()
        deliveries: Counter[str] = Counter()
        action_states: Counter[str] = Counter()
        candidate_states: Counter[str] = Counter()
        for doc in batch["documents"]:
            qualifications[doc["qualification_status"] or "pending"] += 1
            deliveries[doc["delivery_status"]] += 1
            try:
                report = store.get_report(user, batch_id, doc["id"])
            except NotFound:
                continue
            for action in report.get("actions", []):
                if not isinstance(action, dict):
                    continue
                action_states[action.get("status") or action.get("processing_status") or "unknown"] += 1
                for candidate in action.get("candidates", []):
                    if isinstance(candidate, dict):
                        candidate_states[candidate.get("status") or candidate.get("result") or "unknown"] += 1
        lines = ["# FundLex 批次报告", "", f"- 批次 ID：{batch['id']}",
                 f"- 规则版本：{batch['ruleset_version']}", f"- 状态：{batch['status']}",
                 f"- 合同总数：{batch['counts']['total']}", f"- 任务失败：{batch['counts']['failed']}", "",
                 "## 分类汇总", "",
                 f"- 资格：{dict(qualifications)}", f"- 交付：{dict(deliveries)}",
                 f"- action：{dict(action_states)}", f"- 候选位置：{dict(candidate_states)}", "",
                 "| 合同 ID | 文件 | 资格 | 交付 | 任务 | 错误 |", "|---|---|---|---|---|---|"]
        for doc in batch["documents"]:
            safe_name = doc["filename"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {doc['id']} | {safe_name} | {doc['qualification_status'] or '-'} | {doc['delivery_status']} | {doc['status']} | {doc['error_code'] or '-'} |")
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/markdown; charset=utf-8")

    frontend = Path(__file__).resolve().parent.parent / "frontend"
    if frontend.is_dir():
        application.mount("/static", StaticFiles(directory=frontend), name="static")

        @application.get("/", include_in_schema=False)
        def home():
            return FileResponse(frontend / "index.html", media_type="text/html")

    return application


app = create_app()
