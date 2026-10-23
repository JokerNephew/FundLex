"""FastAPI routes for the independent contract comparison feature."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .store import CompareStore, Conflict, NotFound


class CompareFileManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    size: int = Field(gt=0, strict=True)

    @field_validator("name")
    @classmethod
    def filename(cls, value: str) -> str:
        path = Path(value.replace("\\", "/"))
        if path.name != value or not value.strip() or any(ord(c) < 32 for c in value) or not value.lower().endswith(".docx"):
            raise ValueError("manifest requires a DOCX base filename")
        return value


class ComparePairManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_pair_id: str = Field(min_length=1, max_length=128)
    label: str = Field(default="", max_length=200)
    left: CompareFileManifest
    right: CompareFileManifest


class CompareTaskSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    pairs: list[ComparePairManifest] = Field(min_length=1, max_length=1000)

    @field_validator("name")
    @classmethod
    def task_name(cls, value: str) -> str:
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("invalid task name")
        return value.strip()


def _render_view(pair_result: dict[str, Any], left_path: Path, right_path: Path) -> tuple[str, str]:
    from . import parser
    from .render import render_compare_document
    left_doc = parser.parse_compare_document(left_path, filename=pair_result.get("left", {}).get("filename", ""), side="L")
    right_doc = parser.parse_compare_document(right_path, filename=pair_result.get("right", {}).get("filename", ""), side="R")
    diffs = pair_result.get("diffs") or []
    return (render_compare_document(left_doc, diffs, side="left"),
            render_compare_document(right_doc, diffs, side="right"))


def register_compare_routes(application, compare_store: CompareStore, user_dependency: Callable,
                            validate_upload: Callable[[str, bytes], str], *, max_upload_bytes: int,
                            max_batch_bytes: int, max_pairs: int = 1000,
                            max_request_files: int = 20) -> None:
    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.post("/api/compare/tasks", status_code=201)
    def create_compare_task(payload: CompareTaskSubmission,
                            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                            user: str = Depends(user_dependency)):
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise HTTPException(422, "invalid idempotency key")
        return call(compare_store.create, user, payload.name,
                    [item.model_dump() for item in payload.pairs], idempotency_key)

    @application.get("/api/compare/tasks")
    def list_compare_tasks(user: str = Depends(user_dependency)):
        items = call(compare_store.list, user)
        return {"items": items, "total": len(items)}

    @application.get("/api/compare/tasks/{task_id}")
    def get_compare_task(task_id: str, user: str = Depends(user_dependency)):
        return call(compare_store.get, user, task_id)

    @application.get("/api/compare/tasks/{task_id}/pairs")
    def list_compare_pairs(task_id: str, user: str = Depends(user_dependency)):
        items = call(compare_store.pairs, user, task_id)
        return {"items": items, "total": len(items)}

    @application.post("/api/compare/tasks/{task_id}/uploads")
    async def upload_compare_task(task_id: str, files: list[UploadFile] = File(...), client_ids: str = Form(...),
                                  user: str = Depends(user_dependency)):
        call(compare_store.get, user, task_id)
        try:
            ids = json.loads(client_ids)
        except (ValueError, TypeError):
            raise HTTPException(422, "invalid client_ids") from None
        if len(files) > max_request_files:
            raise HTTPException(413, "COMPARE_UPLOAD_REJECTED")
        if (not isinstance(ids, list) or len(ids) != len(files)
                or any(not isinstance(i, str) or not 1 <= len(i) <= 128 for i in ids) or len(set(ids)) != len(ids)):
            raise HTTPException(422, "invalid client_ids")
        uploads, total = [], 0
        for cid, upload in zip(ids, files):
            data = await upload.read(max_upload_bytes + 1)
            if total + len(data) > max_batch_bytes:
                # Reject as soon as the request budget is crossed; do not keep
                # reading the remaining multipart parts into memory.
                raise HTTPException(413, "COMPARE_UPLOAD_REJECTED")
            total += len(data)
            name = Path((upload.filename or "").replace("\\", "/")).name
            error = None
            try:
                validate_upload(name, data)
            except HTTPException as exc:
                error = "COMPARE_INVALID_DOCX" if exc.status_code == 415 else "COMPARE_UPLOAD_REJECTED"
            if error is None:
                # Enforce the same safe OOXML reader used by the worker. A ZIP
                # bearing a document.xml member alone is not a valid DOCX.
                from .parser import parse_compare_document
                from ..docx import DocxError
                try:
                    parse_compare_document(data, filename=name)
                except (DocxError, ValueError, OSError, KeyError):
                    error = "COMPARE_INVALID_DOCX"
            uploads.append({"client_id": cid, "name": name, "data": data, "error_code": error})
        return call(compare_store.upload, user, task_id, uploads)

    @application.post("/api/compare/tasks/{task_id}/seal")
    def seal_compare_task(task_id: str, user: str = Depends(user_dependency)):
        return call(compare_store.seal, user, task_id)

    @application.get("/api/compare/pairs/{pair_id}")
    def get_compare_pair(pair_id: str, user: str = Depends(user_dependency)):
        return call(compare_store.get_pair, user, pair_id)

    @application.get("/api/compare/pairs/{pair_id}/view")
    def view_compare_pair(pair_id: str, user: str = Depends(user_dependency)):
        pair = call(compare_store.get_pair, user, pair_id)
        if pair.get("status") not in {"succeeded", "incomplete"} or not pair.get("result"):
            raise HTTPException(409, "COMPARE_RESULT_NOT_READY")
        try:
            files = {f["side"]: f for f in compare_store.pair_inputs(pair_id)}
            lp = compare_store.store.object_path(files["left"]["object_key"])
            rp = compare_store.store.object_path(files["right"]["object_key"])
            for side in ("left", "right"):
                f, path = files[side], (lp if side == "left" else rp)
                if (not path.is_file() or path.stat().st_size != f["size"]
                        or hashlib.sha256(path.read_bytes()).hexdigest() != f["source_sha256"]):
                    raise Conflict("COMPARE_INPUT_INTEGRITY_FAILED")
            left_html, right_html = _render_view(pair["result"], lp, rp)
        except (NotFound, Conflict) as exc:
            raise HTTPException(409, str(exc)) from exc
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(409, "COMPARE_RESULT_INVALID") from exc
        return {"pair": {k: pair[k] for k in ("id", "label", "ordinal", "status")},
                "left": {"name": pair["left"]["name"], "html": left_html},
                "right": {"name": pair["right"]["name"], "html": right_html},
                "summary": pair["result"].get("summary"), "coverage": pair["result"].get("coverage"),
                "diffs": pair["result"].get("diffs", []), "result_sha256": pair.get("result_sha256")}
