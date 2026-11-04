"""FastAPI routes for the independent contract comparison feature."""
from __future__ import annotations
import gzip
import hashlib
import json
import logging
from collections import OrderedDict
from threading import Lock
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, File, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .store import CompareStore, Conflict, NotFound
from ..api_errors import raise_api_error

_VIEW_CACHE: OrderedDict[str, tuple[str, str, str, list[dict[str, Any]]]] = OrderedDict()
_VIEW_CACHE_LOCK = Lock()
_VIEW_CACHE_MAX = 4


def _upload_rejection_code(name: str, data: bytes) -> str:
    """Recover the precise rejection cause the shared HTTP guard flattens (FL-D853).

    The injected ``validate_upload`` raises ``HTTPException`` with only a prose
    message, so the encrypted/.doc/wrong-format distinctions were collapsed into
    a single misleading ``COMPARE_INVALID_DOCX``.  Re-running the shared
    validator on this already-rejected payload is cheap and restores the
    machine-readable cause without depending on English message text.
    """
    from ..upload_validation import UploadValidationError, validate_docx_upload
    try:
        validate_docx_upload(name, data)
    except UploadValidationError as exc:
        return {"LEGACY_DOC_UNSUPPORTED": "LEGACY_DOC_UNSUPPORTED",
                "ENCRYPTED_DOCX": "COMPARE_ENCRYPTED_DOCX",
                "UNSUPPORTED_FILE_FORMAT": "COMPARE_UNSUPPORTED_FORMAT",
                }.get(exc.code, "COMPARE_INVALID_DOCX")
    except Exception:
        pass
    return "COMPARE_INVALID_DOCX"


def _capture_ingest_reject(name: str, data: bytes, exc: BaseException) -> None:
    """Persist parser-rejected DOCX bytes + traceback for diagnosis (FL-D1024).

    The ingest guard swallows the cause for clients; without a server-side
    capture a real user file that passes package checks but fails the compare
    parser leaves zero evidence. Captures go to FUNDLEX_REJECT_DIAG_DIR
    (default <FUNDLEX_DATA_DIR>/diagnostics); capture failures must never
    affect the upload response.
    """
    import logging, os, traceback
    try:
        diag_dir = os.environ.get("FUNDLEX_REJECT_DIAG_DIR") or os.path.join(
            os.environ.get("FUNDLEX_DATA_DIR", "/var/lib/fundlex"), "diagnostics")
        os.makedirs(diag_dir, exist_ok=True)
        sha = hashlib.sha256(data).hexdigest()[:16]
        path = os.path.join(diag_dir, f"reject-{sha}.docx")
        with open(path, "wb") as fh:
            fh.write(data)
        logging.getLogger("fundlex.compare").warning(
            "COMPARE_INVALID_DOCX captured: name=%r sha=%s file=%s\n%s",
            name, sha, path, "".join(traceback.format_exception(exc)))
    except Exception:
        logging.getLogger("fundlex.compare").exception("reject capture failed")


class CompareFileManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    size: int = Field(gt=0, strict=True)

    @field_validator("name")
    @classmethod
    def filename(cls, value: str) -> str:
        path = Path(value.replace("\\", "/"))
        suffix = path.suffix.lower()
        # 产品化：CDF 二进制 .doc 与 DOCX 都可以进清单——上传端自动转换。
        if (path.name != value or not value.strip() or any(ord(c) < 32 for c in value)
                or suffix not in {".docx", ".doc"}):
            raise ValueError("manifest requires a DOCX or convertible .doc base filename")
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


class CompareSelectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_epoch: int = Field(ge=0)
    result_sha256: str = Field(min_length=1, max_length=128)
    left_source_sha256: str = Field(min_length=1, max_length=128)
    right_source_sha256: str = Field(min_length=1, max_length=128)
    decisions: dict[str, str] = Field(default_factory=dict)


class CompareSelectionPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: dict[str, str] | None = None


class CompareSelectionGenerate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_epoch: int = Field(ge=1)
    decision_hash: str = Field(min_length=1, max_length=128)
    result_sha256: str = Field(min_length=1, max_length=128)


def _view_cache_get(cache_key: str):
    """Return the cached rendered view for ``cache_key`` or ``None`` (FL-D854)."""
    if not cache_key:
        return None
    with _VIEW_CACHE_LOCK:
        cached = _VIEW_CACHE.get(cache_key)
        if cached is not None:
            _VIEW_CACHE.move_to_end(cache_key)
        return cached


def _render_view(pair_result: dict[str, Any], left_path: Path, right_path: Path,
                 *, cache_key: str = "") -> tuple[str, str, str, list[dict[str, Any]]]:
    cached = _view_cache_get(cache_key)
    if cached is not None:
        return cached
    from . import parser
    from .align import align_documents
    from .render import render_compare_document, render_merged_document
    left_doc = parser.parse_compare_document(left_path, filename=pair_result.get("left", {}).get("filename", ""), side="L")
    right_doc = parser.parse_compare_document(right_path, filename=pair_result.get("right", {}).get("filename", ""), side="R")
    diffs = pair_result.get("diffs") or []
    rendered = (render_compare_document(left_doc, diffs, side="left"),
                render_compare_document(right_doc, diffs, side="right"),
                 render_merged_document(right_doc, diffs, left_document=left_doc),
                 pair_result.get("alignment") or [group.to_dict() for group in align_documents(left_doc, right_doc)[0]])
    if cache_key:
        with _VIEW_CACHE_LOCK:
            _VIEW_CACHE[cache_key] = rendered
            _VIEW_CACHE.move_to_end(cache_key)
            while len(_VIEW_CACHE) > _VIEW_CACHE_MAX:
                _VIEW_CACHE.popitem(last=False)
    return rendered


def register_compare_routes(application, compare_store: CompareStore, user_dependency: Callable,
                            validate_upload: Callable[[str, bytes], str], *, max_upload_bytes: int,
                            max_batch_bytes: int, max_pairs: int = 1000) -> None:
    def call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        except Conflict as exc:
            raise_api_error(409, exc, fallback="CONFLICT")
        except ValueError as exc:
            raise_api_error(422, exc, fallback="INVALID_REQUEST")

    @application.post("/api/compare/tasks", status_code=201)
    def create_compare_task(payload: CompareTaskSubmission,
                            idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                            user: str = Depends(user_dependency)):
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise HTTPException(422, "invalid idempotency key")
        # The registration-time max_pairs bound is enforced here (FL-D855);
        # the store keeps its own hard bound as a second defence.
        if len(payload.pairs) > max_pairs:
            raise HTTPException(422, "COMPARE_TOO_MANY_PAIRS")
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
        if (not isinstance(ids, list) or len(ids) != len(files)
                or any(not isinstance(i, str) or not 1 <= len(i) <= 128 for i in ids) or len(set(ids)) != len(ids)):
            raise HTTPException(422, "invalid client_ids")
        uploads, total = [], 0
        try:
            for cid, upload in zip(ids, files):
                data = await upload.read(max_upload_bytes + 1)
                if total + len(data) > max_batch_bytes:
                    # Reject as soon as the request budget is crossed; do not keep
                    # reading the remaining multipart parts into memory.
                    raise HTTPException(413, "COMPARE_UPLOAD_REJECTED")
                total += len(data)
                name = Path((upload.filename or "").replace("\\", "/")).name
                error = None
                prepared = None
                from ..doc_convert import is_legacy_doc
                # 二进制 .doc：跳过旧 *格式* 闸门，真接走归一转换+包安全链，
                # 失败如实返回转换/包安全码（不再混成 UNSUPPORTED）。
                if is_legacy_doc(data) or name.lower().endswith(".doc"):
                    from .ingest import prepare_compare_upload
                    from ..upload_validation import UploadValidationError
                    try:
                        prepared = prepare_compare_upload(name, data)
                    except Exception as exc:  # noqa: BLE001 - 失败如实上抛
                        error = (exc.code if isinstance(exc, UploadValidationError)
                                 else "COMPARE_INVALID_DOCX")
                        prepared = None
                        _capture_ingest_reject(name, data, exc)
                else:
                    try:
                        validate_upload(name, data)
                    except HTTPException as exc:
                        if exc.status_code == 415:
                            error = _upload_rejection_code(name, data)
                        else:
                            error = "COMPARE_UPLOAD_REJECTED"
                    if error is None:
                        from .ingest import prepare_compare_upload
                        try:
                            prepared = prepare_compare_upload(name, data)
                        except Exception as _ingest_exc:
                            error = "COMPARE_INVALID_DOCX"
                            prepared = None
                            _capture_ingest_reject(name, data, _ingest_exc)
                uploads.append({
                    "client_id": cid,
                    "name": name,
                    "data": prepared["data"] if error is None else data,
                    "original_sha256": prepared["original_sha256"] if prepared else hashlib.sha256(data).hexdigest(),
                    "original_size": prepared["original_size"] if prepared else len(data),
                    "revisions_accepted": prepared["revisions_accepted"] if prepared and error is None else 0,
                    "error_code": error,
                })
            # FL-D1093：上传完成落结构化 INFO——名称+status/error_code 摘要，不含内容。
            result = call(compare_store.upload, user, task_id, uploads)
            try:
                receipts = result.get("receipts", []) if isinstance(result, dict) else []
                logging.getLogger("fundlex.compare").info(
                    "compare uploads task=%s files=%d receipts=%s",
                    task_id, len(uploads),
                    json.dumps([
                        {"client_id": u["client_id"], "name": u["name"],
                         "status": (next((r.get("status") for r in receipts
                                          if r.get("client_id") == u["client_id"]), None)
                                    or ("rejected" if u["error_code"] else "accepted")),
                         "error_code": (u["error_code"]
                                        or next((r.get("error_code") for r in receipts
                                                 if r.get("client_id") == u["client_id"]), None))}
                        for u in uploads], ensure_ascii=False))
            except Exception:
                logging.getLogger("fundlex.compare").warning("compare receipts log capture failed")
            return result
        finally:
            for upload in files:
                await upload.close()

    @application.post("/api/compare/tasks/{task_id}/seal")
    def seal_compare_task(task_id: str, user: str = Depends(user_dependency)):
        return call(compare_store.seal, user, task_id)

    @application.get("/api/compare/pairs/{pair_id}")
    def get_compare_pair(pair_id: str, user: str = Depends(user_dependency)):
        return call(compare_store.get_pair, user, pair_id)

    @application.get("/api/compare/pairs/{pair_id}/view")
    def view_compare_pair(pair_id: str, request: Request, user: str = Depends(user_dependency)):
        pair = call(compare_store.get_pair, user, pair_id)
        if pair.get("status") not in {"succeeded", "incomplete"} or not pair.get("result"):
            raise HTTPException(409, "COMPARE_RESULT_NOT_READY")
        try:
            files = {f["side"]: f for f in compare_store.pair_inputs(pair_id)}
            lp = compare_store.store.object_path(files["left"]["object_key"])
            rp = compare_store.store.object_path(files["right"]["object_key"])
            # FL-D854 评估结论：缓存命中也必须保留全量完整性校验——fails-closed
            # 测试（test_compare_system_review）要求源对象被改动时即返回 409，
            # size 活性门无法发现同长度篡改，故不采用分级校验。
            for side in ("left", "right"):
                f, path = files[side], (lp if side == "left" else rp)
                if (not path.is_file() or path.stat().st_size != f["size"]
                        or hashlib.sha256(path.read_bytes()).hexdigest() != f["source_sha256"]):
                    raise Conflict("COMPARE_INPUT_INTEGRITY_FAILED")
            left_html, right_html, merged_html, alignment = _render_view(
                pair["result"], lp, rp,
                cache_key=f"{pair['id']}:{pair.get('result_sha256') or ''}")
        except (NotFound, Conflict) as exc:
            raise_api_error(409, exc, fallback="CONFLICT")
        except (OSError, ValueError, KeyError) as exc:
            raise HTTPException(409, "COMPARE_RESULT_INVALID") from exc
        payload = {"pair": {k: pair[k] for k in ("id", "label", "ordinal", "status")},
                   "left": {"name": pair["left"]["name"], "html": left_html},
                   "right": {"name": pair["right"]["name"], "html": right_html},
                   "merged": {"name": pair["right"]["name"], "html": merged_html},
                   "alignment": alignment,
                   "summary": pair["result"].get("summary"), "coverage": pair["result"].get("coverage"),
                   "diffs": pair["result"].get("diffs", []), "result_sha256": pair.get("result_sha256")}
        # Long contracts produce multi-megabyte HTML. Compress this one JSON
        # response when the client supports gzip; browsers transparently decode
        # it and the payload drops by roughly an order of magnitude.
        if "gzip" in request.headers.get("accept-encoding", "").lower():
            body = gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), compresslevel=5)
            return Response(content=body, media_type="application/json",
                            headers={"Content-Encoding": "gzip", "Vary": "Accept-Encoding"})
        return payload

    @application.get("/api/compare/pairs/{pair_id}/selection")
    def get_compare_selection(pair_id: str, user: str = Depends(user_dependency)):
        return call(compare_store.selection_state, user, pair_id)

    @application.put("/api/compare/pairs/{pair_id}/selection")
    def save_compare_selection(pair_id: str, payload: CompareSelectionUpdate,
                               user: str = Depends(user_dependency)):
        return call(compare_store.save_selection, user, pair_id,
                    expected_epoch=payload.expected_epoch,
                    result_sha256=payload.result_sha256,
                    left_source_sha256=payload.left_source_sha256,
                    right_source_sha256=payload.right_source_sha256,
                    decisions=payload.decisions)

    @application.post("/api/compare/pairs/{pair_id}/selection/preview")
    def preview_compare_selection(pair_id: str, payload: CompareSelectionPreview | None = None,
                                  user: str = Depends(user_dependency)):
        return call(compare_store.preview_selection, user, pair_id,
                    decisions=payload.decisions if payload else None)

    @application.post("/api/compare/pairs/{pair_id}/selection/generate")
    def generate_compare_selection(pair_id: str, payload: CompareSelectionGenerate,
                                   user: str = Depends(user_dependency)):
        return call(compare_store.generate_selection, user, pair_id,
                    expected_epoch=payload.expected_epoch,
                    expected_decision_hash=payload.decision_hash,
                    result_sha256=payload.result_sha256)

    @application.get("/api/compare/pairs/{pair_id}/selection-artifacts/{version}/{kind}")
    def download_compare_selection(pair_id: str, version: int, kind: str,
                                   user: str = Depends(user_dependency)):
        try:
            path, row = compare_store.selection_artifact(user, pair_id, version, kind)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        except Conflict as exc:
            raise_api_error(409, exc, fallback="CONFLICT")
        return FileResponse(
            path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"fundlex-compare-{pair_id[:8]}-v{version}-{kind}.docx",
            headers={"Cache-Control": "no-store", "X-Content-SHA256": row["sha256"]})
