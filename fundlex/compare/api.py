"""FastAPI routes for the independent contract comparison feature."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Callable, Literal

from fastapi import Depends, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .store import CompareStore, Conflict, NotFound
from ..docx import DocxError
from .selection_writer import generate_selection_artifacts


class CompareSelectionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_epoch: int = Field(ge=0, strict=True)
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    left_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    right_source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CompareSelectionSave(CompareSelectionBinding):
    decisions: dict[str, Literal["pending", "left", "right"]] = Field(max_length=100000)


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

    @application.get("/api/compare/pairs/{pair_id}/selection")
    def get_compare_selection(pair_id: str, user: str = Depends(user_dependency)):
        return call(compare_store.get_selection, user, pair_id)

    @application.put("/api/compare/pairs/{pair_id}/selection")
    def save_compare_selection(pair_id: str, payload: CompareSelectionSave,
                               user: str = Depends(user_dependency)):
        return call(compare_store.save_selection, user, pair_id, **payload.model_dump())

    @application.post("/api/compare/pairs/{pair_id}/selection/preview")
    def preview_compare_selection(pair_id: str, payload: CompareSelectionBinding,
                                  user: str = Depends(user_dependency)):
        return call(compare_store.preview_selection, user, pair_id, **payload.model_dump())

    @application.post("/api/compare/pairs/{pair_id}/selection/generate")
    def generate_compare_selection(pair_id: str, payload: CompareSelectionBinding,
                                   idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                                   user: str = Depends(user_dependency)):
        inputs = call(compare_store.selection_generation_inputs, user, pair_id, **payload.model_dump())
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise HTTPException(422, "INVALID_IDEMPOTENCY_KEY")
        temp_parent = compare_store.store.object_path("compare/selection-work")
        temp_parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="generate-", dir=temp_parent) as directory:
            final_path, redline_path = Path(directory) / "selected_final.docx", Path(directory) / "selected_redline.docx"
            try:
                validation = generate_selection_artifacts(
                    inputs["left_path"], inputs["right_path"], inputs["result"], inputs["decisions"],
                    final_path, redline_path, selection_epoch=inputs["selection_epoch"],
                    result_sha256=inputs["result_sha256"])
            except DocxError as exc:
                raise HTTPException(409, exc.code) from exc

            def report_builder(version: int, final_hash: str, redline_hash: str) -> tuple[bytes, bytes]:
                if final_hash != validation.final_sha256 or redline_hash != validation.redline_sha256:
                    raise Conflict("SELECTION_ARTIFACT_INTEGRITY_FAILED")
                report = {
                    "schema_version": "compare-selection-report-v1", "kind": "human_compare_selection",
                    "pair_id": pair_id, "generation_version": version,
                    "selection_epoch": inputs["selection_epoch"], "result_sha256": inputs["result_sha256"],
                    "left_source_sha256": inputs["left_source_sha256"],
                    "right_source_sha256": inputs["right_source_sha256"], "decisions": inputs["decisions"],
                    "counts": {choice: sum(value == choice for value in inputs["decisions"].values())
                               for choice in ("pending", "left", "right")},
                    "output_validation": validation.to_dict(),
                    "outputs": {"selected_final": {"sha256": final_hash, "size": final_path.stat().st_size},
                                "selected_redline": {"sha256": redline_hash, "size": redline_path.stat().st_size}},
                }
                lines = ["# FundLex 人工 Compare 选择报告", "", f"- 生成版本：{version}",
                         f"- 草稿版本：{inputs['selection_epoch']}",
                         f"- 比较结果 SHA-256：{inputs['result_sha256']}",
                         f"- 左侧来源 SHA-256：{inputs['left_source_sha256']}",
                         f"- 右侧来源 SHA-256：{inputs['right_source_sha256']}",
                         f"- 选择版 SHA-256：{final_hash}", f"- 修订版 SHA-256：{redline_hash}",
                         f"- 采用左侧：{report['counts']['left']}；采用右侧：{report['counts']['right']}",
                         "", "人工选择版以原版（左侧）结构为基底，依据已保存的左右文本选择生成。", "",
                         "## 逐条选择", ""]
                for diff_id, choice in sorted(inputs["decisions"].items()):
                    lines.append(f"- {diff_id}：{'采用左侧' if choice == 'left' else '采用右侧'}")
                lines.extend(["", "## 实际改动", ""])
                for item in validation.manifest:
                    lines.extend([f"- {item['diff_id']} / {item['location']} / {item['start']}–{item['end']}",
                                  f"  - 原文：{item['left_text']}", f"  - 选定文本：{item['selected_text']}"])
                if not validation.manifest:
                    lines.append("- 全部保留左侧，没有实际文字改动。")
                lines.extend(["", "## 复核与例外", "", f"- 已通过：{', '.join(validation.checks)}"])
                lines.extend(f"- {item}" for item in validation.limitations)
                return (json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
                        ("\n".join(lines) + "\n").encode("utf-8"))

            return call(compare_store.publish_selection_generation, user, pair_id,
                        **payload.model_dump(), idempotency_key=idempotency_key,
                        final_path=final_path, redline_path=redline_path, report_builder=report_builder)

    @application.get("/api/compare/pairs/{pair_id}/selection-artifacts/{version}/{kind}")
    def download_compare_selection(pair_id: str, version: int, kind: str, user: str = Depends(user_dependency)):
        metadata, path = call(compare_store.get_selection_artifact, user, pair_id, version, kind)
        media_type = {"selected_final": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                      "selected_redline": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                      "selection_report_json": "application/json", "selection_report_markdown": "text/markdown"}[metadata["kind"]]
        return FileResponse(path, media_type=media_type, filename=f"compare-v{version}-{path.name}",
                            headers={"X-Content-SHA256": metadata["sha256"], "Cache-Control": "private, no-store"})

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
