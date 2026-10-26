"""Local development HTTP API. Run with ``uvicorn fundlex.api:app``.

The development identity adapter requires X-FundLex-User on every API request.
Production identity integration is deliberately unconfigured and fails closed.
"""

from __future__ import annotations

import html
import io
import csv
import hashlib
import shutil
import tempfile
import json
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from starlette.background import BackgroundTask
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles

from . import __version__, guide_store
from .docx import DocxError
from .edit_summary import archive_entry, archive_kinds
from .html_view import project_docx
from .selective import (accept_all as selective_accept_all, generate_selected_artifact,
                        generate_selected_redline, manifest_fingerprint,
                        _manifests_from_report, resolve_selection)
from .store import (Conflict, NotFound, ReportJsonError, RunStore, StoreError,
                    parse_report_json)
from .config import auth_db_target, local_data_dir
from .tasks import TaskStore
from .application import TaskApplicationService
from .upload_validation import (
    MAX_BATCH_BYTES, MAX_BATCH_DOCUMENTS, MAX_COMPRESSION_RATIO,
    MAX_PART_BYTES, MAX_UNCOMPRESSED_BYTES, MAX_UPLOAD_BYTES,
    UploadValidationError, validate_batch_limits, validate_docx_upload,
)
from .upload_guard import add_upload_guard
from .integrations import IntegrationStore
from .integrations.store import IntegrationConflict
from .integrations.feishu.oauth import FeishuOAuthClient, FeishuOAuthError, oauth_available
from .compare.store import CompareStore
from .compare.api import register_compare_routes
from .api_errors import (
    CORRELATION_ID_HEADER, code_from_detail, correlation_id, error_code,
    log_handled_error, message_for, new_correlation_id, raise_api_error,
    reset_correlation_id, set_correlation_id,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FrontendBasePathMiddleware:
    """Accept requests forwarded with an optional deployment path prefix."""

    def __init__(self, app, base_path: str = ""):
        self.app = app
        self.base_path = base_path.rstrip("/") if base_path not in ("", "/") else ""

    async def __call__(self, scope, receive, send):
        if self.base_path and scope["type"] in {"http", "websocket"}:
            path = scope.get("path", "")
            if path == self.base_path or path.startswith(f"{self.base_path}/"):
                scope = dict(scope)
                scope["path"] = path[len(self.base_path):] or "/"
                raw_path = scope.get("raw_path")
                if raw_path is not None:
                    prefix = self.base_path.encode("utf-8")
                    scope["raw_path"] = raw_path[len(prefix):] or b"/"
        await self.app(scope, receive, send)


class ManifestFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    client_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    size: int = Field(gt=0, strict=True)

    @field_validator("name")
    @classmethod
    def safe_name(cls, value):
        if not value.strip() or Path(value.replace("\\", "/")).name != value or any(ord(c) < 32 for c in value):
            raise ValueError("manifest requires a base filename")
        return value


class TaskSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    # New submissions name the recall engine and let the server bind the owner's
    # current guide snapshot. The legacy ``ruleset_version`` path was retired from
    # the runtime and is rejected with RULESET_RETIRED.
    ruleset_version: str | None = Field(default=None, min_length=1, max_length=128)
    engine_id: str | None = Field(default=None, min_length=1, max_length=64)
    guide_version_id: str | None = Field(default=None, min_length=1, max_length=128)
    files: list[ManifestFile] = Field(min_length=1, max_length=10000)

    @field_validator("name")
    @classmethod
    def task_name(cls, value):
        if not value.strip() or any(ord(c) < 32 for c in value):
            raise ValueError("invalid task name")
        return value.strip()

    @field_validator("files")
    @classmethod
    def unique_files(cls, files):
        if len({f.client_id for f in files}) != len(files):
            raise ValueError("duplicate client_id")
        return files


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=1024)


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=1024)
    display_name: str = Field(default="", max_length=128)


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    old_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=8, max_length=1024)


class CreateUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=1024)
    display_name: str = Field(default="", max_length=128)
    role: str = Field(default="member", pattern="^(admin|member)$")


class DisableUserRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool = True


class GuideSettingRequest(BaseModel):
    """Explicit guide switch; ``None``/``""``/``builtin`` resets to the built-in."""

    model_config = ConfigDict(extra="forbid")
    version_id: str | None = Field(default=None, max_length=128)


class FeishuBindingCodeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ttl_seconds: int = Field(default=600, ge=60, le=3600)


class RevisionDecision(BaseModel):
    """One user decision on a single engine revision pair."""

    model_config = ConfigDict(extra="forbid")
    del_id: int = Field(ge=1)
    decision: str = Field(pattern="^(accept|reject)$")


class DecisionRequest(BaseModel):
    """Per-revision accept/reject for one document's redline."""

    model_config = ConfigDict(extra="forbid")
    decisions: list[RevisionDecision] = Field(default_factory=list, max_length=1000)
    selection_epoch: int | None = Field(default=None, ge=0)
    manifest_hash: str | None = Field(default=None, min_length=64, max_length=64,
                                      pattern="^[0-9a-f]{64}$")


def _auth_mode() -> str:
    return os.environ.get("FUNDLEX_AUTH_MODE", "dev")


def _registration_open() -> bool:
    """Self-service registration is available in password mode by default.

    Set ``FUNDLEX_ALLOW_REGISTRATION=0`` to close it again without changing the
    auth mode; the login screen hides the entry when it is closed.
    """
    return _auth_mode() == "password" and os.environ.get("FUNDLEX_ALLOW_REGISTRATION", "1") != "0"


def _bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    if scheme.lower() != "bearer":
        return None
    token = value.strip()
    if not token or len(token) > 512:
        return None
    return token


def _password_identity(request: Request, authorization: str | None) -> dict | None:
    """Resolve a bearer token to a live account; disabled accounts fail closed."""
    users = getattr(request.app.state, "users", None)
    sessions = getattr(request.app.state, "sessions", None)
    token = _bearer_token(authorization)
    if users is None or sessions is None or token is None:
        return None
    user_id = sessions.resolve(token)
    if not user_id:
        return None
    record = users.get(user_id)
    if record is None or record["disabled"]:
        return None
    return record


def _user(request: Request, x_fundlex_user: str | None = Header(default=None),
          authorization: str | None = Header(default=None)) -> str:
    mode = _auth_mode()
    if mode == "password":
        identity = _password_identity(request, authorization)
        if identity is None:
            raise HTTPException(401, "authentication required")
        return identity["id"]
    if mode != "dev":
        raise HTTPException(503, "production identity provider is not configured")
    if not x_fundlex_user or not x_fundlex_user.strip() or len(x_fundlex_user) > 128:
        raise HTTPException(401, "development identity header required")
    return x_fundlex_user.strip()


def _account(request: Request, x_fundlex_user: str | None = Header(default=None),
             authorization: str | None = Header(default=None)) -> dict:
    if _auth_mode() != "password":
        raise HTTPException(404, "not found")
    identity = _password_identity(request, authorization)
    if identity is None:
        raise HTTPException(401, "authentication required")
    return identity


def _admin(request: Request, x_fundlex_user: str | None = Header(default=None),
           authorization: str | None = Header(default=None)) -> dict:
    # Non-admins get 404 so the admin surface never confirms account existence.
    if _auth_mode() != "password":
        raise HTTPException(404, "not found")
    identity = _password_identity(request, authorization)
    if identity is None or identity["role"] != "admin":
        raise HTTPException(404, "not found")
    return identity


def _capabilities_identity(request: Request, x_fundlex_user: str | None = Header(default=None),
                           authorization: str | None = Header(default=None)) -> dict | None:
    """Capabilities stay reachable without a token in password mode.

    The unauthenticated response is intentionally minimal so the login screen
    can learn ``auth_mode``/``login_required`` before credentials exist.
    """
    if _auth_mode() == "password":
        return _password_identity(request, authorization)
    return {"id": _user(request, x_fundlex_user, authorization)}


def _public_user(record: dict) -> dict:
    return {"id": record["id"], "username": record["username"],
            "display_name": record["display_name"], "role": record["role"]}


def _oauth_result_page(title: str, message: str, *, success: bool) -> HTMLResponse:
    """Minimal callback page; never reflects authorization codes or tokens."""
    base = os.environ.get("FUNDLEX_PUBLIC_BASE_URL", "").rstrip("/")
    settings = f"{base}/settings" if base else "/settings"
    app_id = os.environ.get("FUNDLEX_FEISHU_APP_ID", "")
    bot_link = f"https://applink.feishu.cn/client/bot/open?appId={html.escape(app_id)}" if app_id else ""
    bot = f'<p><a href="{bot_link}">打开 FundLex 机器人私聊</a></p>' if bot_link else ""
    color = "#1f7a4d" if success else "#b42318"
    body = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)} · FundLex</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:0;background:#f6f3ee;color:#23302b">
<main style="max-width:560px;margin:12vh auto;padding:32px;background:#fff;border-radius:16px;box-shadow:0 12px 40px rgba(35,48,43,.12)">
<h1 style="font-size:22px;margin:0 0 14px;color:{color}">{html.escape(title)}</h1>
<p style="line-height:1.7;margin:0 0 18px">{html.escape(message)}</p>
<p><a href="{html.escape(settings)}">返回 FundLex 设置</a></p>{bot}
</main></body></html>"""
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


def _validate_upload(name: str, data: bytes) -> str:
    try:
        return validate_docx_upload(name, data)
    except UploadValidationError as exc:
        raise HTTPException(exc.status_code, exc.message) from None


RECALL_ENGINE_ID = "recall_first"
_GUIDE_RESET_IDS = frozenset({"", "builtin"})
_RECALL_TARGET_DONE = frozenset({"planned", "satisfied", "not_applicable"})
_RECALL_TARGET_UNRESOLVED = frozenset({"unresolved", "not_planned"})


def _report_has_revisions(report: dict) -> bool:
    """Whether a persisted report describes engine revisions we can select on."""
    manifest = report.get("revision_manifest")
    if isinstance(manifest, list) and manifest:
        return True
    plan = report.get("plan")
    edits = plan.get("edits") if isinstance(plan, dict) else None
    return isinstance(edits, list) and bool(edits)


def _selection_overrides_default(report: dict, decisions: dict, rejected) -> bool:
    """Whether a review actually turned any of the engine's edits down.

    "Accept everything" is the engine's own result, so a review that rejects
    nothing is indistinguishable from not having reviewed at all. In that case
    there is no separate selection to publish: the engine redline already *is* the
    record of that choice.
    """
    if rejected:
        return True
    return any(str(verdict).strip().lower() == "reject" for verdict in (decisions or {}).values())


def _recall_phase(report: dict) -> str:
    """Last non-empty window/round stage, or ``""`` when none was recorded."""
    windows = report.get("windows")
    if not isinstance(windows, list):
        return ""
    for window in reversed(windows):
        if not isinstance(window, dict):
            continue
        rounds = window.get("rounds")
        if not isinstance(rounds, list):
            continue
        for entry in reversed(rounds):
            if not isinstance(entry, dict):
                continue
            for key in ("stage", "phase"):
                value = entry.get(key)
                if isinstance(value, str) and value:
                    return value
    return ""


def _recall_target_counts(report: dict) -> dict[str, int]:
    """Small per-document counters derived from the persisted recall report."""
    targets = report.get("targets")
    targets = [item for item in targets if isinstance(item, dict)] if isinstance(targets, list) else []
    # A candidate target superseded after obligation proof is terminal.  It is not
    # user-visible unfinished work, but it must still be counted as processed so the
    # workbench total reconciles (total == completed + unresolved).
    completed = sum(1 for item in targets
                    if item.get("status") in _RECALL_TARGET_DONE or item.get("out_of_scope"))
    unresolved = sum(1 for item in targets if item.get("status") in _RECALL_TARGET_UNRESOLVED
                     and not item.get("out_of_scope"))
    entries = report.get("unresolved")
    if isinstance(entries, list):
        # The delivery gate records target blockers here even when the per-target
        # ledger is absent; the counter must never under-report them.
        unresolved = max(unresolved, sum(1 for item in entries
                                          if isinstance(item, dict) and item.get("kind") == "target"))
    return {"total": len(targets), "completed": completed, "unresolved": unresolved}


def _recall_metrics(store: RunStore, documents: list[dict], key: str) -> dict[str, dict]:
    """Cheap recall-first counters keyed by document id.

    The full report stays behind the authorized report endpoint; only the small
    workbench counters are read from the persisted ``report_json`` rows. Documents
    without a recall report are skipped silently and no schema is added.
    """
    ids = sorted({document.get(key) for document in documents if document.get(key)})
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with store._connect() as db:
        rows = db.execute(f"SELECT d.id AS document_id, d.report_json, b.guide_version_id, "
                          f"b.guide_rules_sha256 FROM documents d JOIN batches b ON b.id=d.batch_id "
                          f"WHERE d.id IN ({placeholders})", ids).fetchall()
    metrics: dict[str, dict] = {}
    for row in rows:
        try:
            report = parse_report_json(row["report_json"])
        except ReportJsonError:
            report = None
        if not isinstance(report, dict) or report.get("engine_id") != RECALL_ENGINE_ID:
            continue
        metrics[row["document_id"]] = {
            "phase": _recall_phase(report),
            "target_counts": _recall_target_counts(report),
            "guide_snapshot": {"version_id": row["guide_version_id"] or "",
                               "rules_sha256": row["guide_rules_sha256"] or ""},
        }
    return metrics


def _guide_public(version: dict, *, current: bool) -> dict:
    """Owner-facing guide metadata; server paths never appear here."""
    issues = version.get("issues")
    issue_count = 0
    if isinstance(issues, dict):
        issue_count = sum(len(issues[key]) for key in ("errors", "warnings", "coverage_gaps")
                          if isinstance(issues.get(key), list))
    return {"id": version["id"], "built_in": bool(version["built_in"]), "filename": version["filename"],
            "status": version["status"], "qualification_status": version["qualification_status"],
            "document_sha256": version["document_sha256"], "rules_sha256": version["rules_sha256"],
            "groups": int(version.get("rules_count") or 0), "issues": issue_count,
            "current": bool(current), "created_at": version["created_at"], "updated_at": version["updated_at"]}


def _rules_overview(store: RunStore, version_id: str) -> list[dict]:
    """Per-rule operation counts from the parsed document; empty when not parsed."""
    try:
        document = guide_store.guide_document(store, version_id)
    except (KeyError, StoreError):
        return []
    groups = document.get("groups") if isinstance(document, dict) else None
    overview: list[dict] = []
    for group in groups if isinstance(groups, list) else []:
        if not isinstance(group, dict):
            continue
        counts = {"append": 0, "replace": 0, "delete": 0, "noop": 0}
        operations = group.get("operations")
        for operation in operations if isinstance(operations, list) else []:
            kind = operation.get("op") if isinstance(operation, dict) else None
            if kind in counts:
                counts[kind] += 1
        overview.append({"rule_id": group.get("rule_id"), "title": group.get("title"),
                         "section_hint": group.get("section_hint"), "operations": counts})
    return overview


def _public_batch(batch: dict, *, detail: bool, metrics: dict[str, dict] | None = None) -> dict:
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
            "execution_mode": d.get("execution_mode", ""),
            "error_code": d["error_code"], "report_url": d["report_url"],
            "downloads": d["download_urls"], "source_sha256": d["source_sha256"],
            "report_error": d.get("report_error"),
        } | (metrics or {}).get(d["id"], {}) for d in docs]
    return base


def create_app(data_dir: str | Path | None = None, *, auth_db=None) -> FastAPI:
    application = FastAPI(title="FundLex", version="0.1.0")
    add_upload_guard(application, max_upload_bytes=MAX_UPLOAD_BYTES,
                     max_batch_bytes=MAX_BATCH_BYTES,
                     max_request_files=MAX_BATCH_DOCUMENTS)

    def api_error_response(request: Request, status_code: int, code: str) -> JSONResponse:
        cid = getattr(request.state, "correlation_id", None) or correlation_id()
        return JSONResponse(
            status_code=status_code,
            content={"error_code": code, "message": message_for(status_code),
                     "detail": code, "correlation_id": cid},
            headers={CORRELATION_ID_HEADER: cid},
        )

    @application.exception_handler(StarletteHTTPException)
    async def stable_http_error(request: Request, exc: StarletteHTTPException):
        code = code_from_detail(exc.detail, exc.status_code)
        log_handled_error(exc, code, request_id=getattr(request.state, "correlation_id", None))
        return api_error_response(request, exc.status_code, code)

    @application.exception_handler(RequestValidationError)
    async def stable_validation_error(request: Request, exc: RequestValidationError):
        code = "INVALID_REQUEST"
        log_handled_error(exc, code, request_id=getattr(request.state, "correlation_id", None))
        return api_error_response(request, 422, code)

    @application.exception_handler(Exception)
    async def stable_unexpected_error(request: Request, exc: Exception):
        code = error_code(exc, "INTERNAL_ERROR")
        log_handled_error(exc, code, request_id=getattr(request.state, "correlation_id", None))
        return api_error_response(request, 500, code)

    @application.middleware("http")
    async def correlation_context(request: Request, call_next):
        cid = new_correlation_id()
        request.state.correlation_id = cid
        token = set_correlation_id(cid)
        try:
            response = await call_next(request)
        finally:
            reset_correlation_id(token)
        response.headers[CORRELATION_ID_HEADER] = cid
        return response

    @application.middleware("http")
    async def private_api_responses(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            # Owner-scoped metadata and authorization failures must not remain
            # in a browser/proxy cache after a development identity changes.
            response.headers["Cache-Control"] = "private, no-store"
        return response

    store = RunStore(data_dir or local_data_dir())
    application.state.store = store
    tasks = TaskStore(store)
    application.state.tasks = tasks
    task_service = TaskApplicationService(store, tasks)
    application.state.task_service = task_service
    integrations = IntegrationStore(store)
    application.state.integrations = integrations
    compare_store = CompareStore(store)
    application.state.compare_store = compare_store

    # Accounts and sessions share the fundlex.db adapter. Initialization fails
    # closed: password mode refuses to start when the store is unavailable, and
    # the bootstrap secret is never logged or written to disk.
    try:
        from .db import Database
        from .auth import SessionStore, UserStore, bootstrap_admin
    except ImportError as exc:
        # fundlex.db is delivered by a parallel change; dev mode stays usable
        # while it is absent, but a broken import inside an existing module is
        # never masked.
        if _auth_mode() == "password":
            raise RuntimeError("password auth mode requires the fundlex.db module") from exc
        if getattr(exc, "path", None) is not None:
            raise
    else:
        target = auth_db if auth_db is not None else auth_db_target(data_dir)
        database = target if hasattr(target, "connect") else Database(str(target))
        users = UserStore(database)
        sessions = SessionStore(database)
        application.state.auth_db = database
        application.state.users = users
        application.state.sessions = sessions
        bootstrap_admin(database, users=users)

    def task_call(fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except NotFound as exc:
            raise HTTPException(404, "task not found") from exc
        except Conflict as exc:
            from .api_errors import raise_api_error
            raise_api_error(409, exc, fallback="CONFLICT")

    # --- revision review (HTML presentation + per-revision selection) -------

    def _redline_for(owner: str, batch_id: str, document_id: str) -> tuple[Path, dict]:
        """Locate the revision artifact a user makes decisions on."""
        document = store.get_document(owner, batch_id, document_id)
        if document["execution_mode"] == "evaluation":
            raise Conflict("REVISION_REVIEW_EVALUATION_UNSUPPORTED")
        report = store.get_report(owner, batch_id, document_id)
        if not _report_has_revisions(report):
            raise Conflict("REVISION_REVIEW_UNAVAILABLE")
        for kind in ("working_redline", "redline"):
            if kind in document["artifacts"]:
                path, _ = store.get_artifact(owner, batch_id, document_id, kind)
                return path, report
        raise Conflict("REVISION_REVIEW_UNAVAILABLE")

    def _revision_view(owner: str, batch_id: str, document_id: str) -> dict:
        path, report = _redline_for(owner, batch_id, document_id)
        document = store.get_document(owner, batch_id, document_id)
        manifests = _manifests_from_report(report)
        view = project_docx(str(path), report=report)
        return {
            "document_id": document_id,
            "html": view["html"],
            "revisions": view["revisions"],
            "meta": view["meta"],
            "selection_epoch": document.get("selection_epoch", 0),
            "manifest_hash": manifest_fingerprint(manifests),
            "decision_hash": document.get("selection_decision_hash", ""),
            "download_url": f"/api/batches/{batch_id}/documents/{document_id}/download/selected_final",
        }

    def _apply_selection(owner: str, batch_id: str, document_id: str,
                         decisions: list[dict] | None, *, expected_epoch: int | None = None,
                         expected_manifest_hash: str | None = None) -> dict:
        path, report = _redline_for(owner, batch_id, document_id)
        manifests = _manifests_from_report(report)
        chosen = decisions if decisions is not None else selective_accept_all(str(path), report)
        verdict = resolve_selection(manifests, chosen, client_ids=decisions is not None)
        if expected_manifest_hash is not None and expected_manifest_hash != verdict.manifest_hash:
            raise Conflict("SELECTION_MANIFEST_CONFLICT")
        document = store.get_document(owner, batch_id, document_id)
        current_epoch = int(document.get("selection_epoch", 0) or 0)
        if expected_epoch is not None and expected_epoch != current_epoch:
            raise Conflict("SELECTION_EPOCH_CONFLICT")
        if expected_epoch is None and current_epoch:
            raise Conflict("SELECTION_EPOCH_REQUIRED")
        publish_epoch = current_epoch if expected_epoch is None else expected_epoch
        temp_dir = Path(tempfile.mkdtemp(prefix="fundlex-selected-"))
        target = temp_dir / "selected_final.docx"
        derived_redline = temp_dir / "selected_redline.docx"
        try:
            result = generate_selected_artifact(path, target, report, verdict.decisions)
            # The engine redline always stays available as the full record of what
            # the engine planned. A second revision file is only worth publishing
            # when the user actually departed from "accept everything": otherwise it
            # would duplicate the engine redline under a different name.
            has_selected_redline = _selection_overrides_default(report, verdict.decisions,
                                                                 result.rejected)
            if has_selected_redline:
                generate_selected_redline(path, derived_redline, report, verdict.decisions)
            published = store.publish_selected_artifacts(
                owner, batch_id, document_id, final=target,
                redline=derived_redline if has_selected_redline else None,
                manifest_hash=verdict.manifest_hash, decision_hash=verdict.decision_hash,
                expected_epoch=publish_epoch)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return {
            "document_id": document_id,
            "accepted": list(result.accepted),
            "rejected": list(result.rejected),
            "sha256": result.sha256,
            "selection_epoch": published["epoch"],
            "manifest_hash": verdict.manifest_hash,
            "decision_hash": verdict.decision_hash,
            "selected_redline_sha256": published["selected_redline_sha256"],
            "download_url": f"/api/batches/{batch_id}/documents/{document_id}/download/selected_final",
        }

    def bound_guide_version(owner: str, version_id: str | None) -> dict:
        """Resolve the guide snapshot for a new recall task (never a fallback)."""
        requested = (version_id or "").strip()
        try:
            version = (guide_store.get_version(store, owner, requested) if requested
                       else guide_store.current_guide(store, owner))
        except KeyError as exc:
            raise HTTPException(404, "guide version not found") from exc
        if version["status"] not in guide_store.ENABLEABLE_STATUSES:
            raise HTTPException(409, "GUIDE_NOT_READY")
        return version

    def visible_guide(owner: str, version_id: str) -> dict:
        try:
            return guide_store.get_version(store, owner, version_id)
        except KeyError as exc:
            raise HTTPException(404, "guide version not found") from exc

    def guide_items(owner: str) -> list[dict]:
        current = guide_store.current_guide(store, owner)
        return [_guide_public(version, current=version["id"] == current["id"])
                for version in guide_store.list_versions(store, owner)]

    def guide_settings(owner: str) -> dict:
        items = guide_items(owner)
        current = next((item for item in items if item["current"]), items[0] if items else None)
        return {"current": current, "available": items, "engine_id": RECALL_ENGINE_ID}

    @application.get("/api/capabilities")
    def capabilities(identity: dict | None = Depends(_capabilities_identity)):
        mode = _auth_mode()
        if mode == "password" and identity is None:
            # Minimal pre-login payload: no ruleset or identity metadata leaks.
            return {"auth_mode": mode, "login_required": True, "task_api": True,
                    "app_version": __version__, "registration_open": _registration_open()}
        # The runtime has a single rule source: the bound guide snapshot. The
        # legacy rulesets no longer participate, so capabilities must not load
        # or expose them (a broken legacy file must not break the engine).
        try:
            current = guide_store.current_guide(store, identity["id"])
            guide = {"version_id": current["id"], "built_in": bool(current["built_in"]),
                     "status": current["status"], "rules_sha256": current["rules_sha256"],
                     "groups": int(current.get("rules_count") or 0), "filename": current["filename"]}
        except (KeyError, OSError, ValueError, StoreError):
            # A broken guide installation must not hide the rest of capabilities.
            guide = None
        enabled = bool(guide) and guide.get("status") in {"parsed", "released"}
        engine = {
            "id": RECALL_ENGINE_ID,
            "rule_source": "guide",
            "guide": guide,
            "delivery_mode": "formal" if enabled else "unavailable",
            "auto_write_enabled": enabled,
            "actions_total": int(guide.get("groups") or 0) if guide else 0,
        }
        return {"auth_mode": mode, "login_required": mode == "password", "task_api": True,
                "app_version": __version__, "registration_open": _registration_open(),
                "upload_limits": {"max_file_bytes": MAX_UPLOAD_BYTES, "max_request_files": MAX_BATCH_DOCUMENTS,
                                  "max_request_bytes": MAX_BATCH_BYTES},
                "engine": engine}

    @application.post("/api/auth/login")
    def auth_login(payload: LoginRequest, request: Request):
        if _auth_mode() != "password":
            raise HTTPException(404, "not found")
        from .auth import AccountDisabled, InvalidCredentials
        users, sessions = request.app.state.users, request.app.state.sessions
        try:
            record = users.authenticate(payload.username, payload.password)
        except AccountDisabled as exc:
            raise HTTPException(403, "account is disabled") from exc
        except InvalidCredentials as exc:
            raise HTTPException(401, "invalid username or password") from exc
        return {"token": sessions.login(record["id"]), "user": _public_user(record)}

    @application.post("/api/auth/register", status_code=201)
    def auth_register(payload: RegisterRequest, request: Request):
        """Self-service account creation; returns a session like login does."""
        if _auth_mode() != "password":
            raise HTTPException(404, "not found")
        if not _registration_open():
            raise HTTPException(403, "registration is disabled")
        from .auth import UserExists
        from .auth import ValidationError as AuthValidationError
        users, sessions = request.app.state.users, request.app.state.sessions
        try:
            record = users.create_user(payload.username.strip(), payload.password,
                                       payload.display_name.strip(), "member")
        except UserExists as exc:
            raise HTTPException(409, "username already exists") from exc
        except (AuthValidationError, ValueError) as exc:
            from .api_errors import raise_api_error
            raise_api_error(422, exc, fallback="INVALID_REQUEST")
        return {"token": sessions.login(record["id"]), "user": _public_user(record)}

    @application.post("/api/auth/logout")
    def auth_logout(request: Request, authorization: str | None = Header(default=None)):
        if _auth_mode() != "password":
            raise HTTPException(404, "not found")
        token = _bearer_token(authorization)
        if token:
            # Logout is idempotent: revoking an unknown token is not an error.
            request.app.state.sessions.logout(token)
        return {"ok": True}

    @application.get("/api/auth/me")
    def auth_me(identity: dict = Depends(_account)):
        return _public_user(identity)

    @application.post("/api/auth/password")
    def auth_change_password(payload: PasswordChangeRequest, request: Request,
                             identity: dict = Depends(_account),
                             authorization: str | None = Header(default=None)):
        from .auth import InvalidCredentials, UserNotFound
        try:
            request.app.state.users.change_password(identity["id"], payload.old_password, payload.new_password)
        except InvalidCredentials as exc:
            raise HTTPException(401, "current password is incorrect") from exc
        except UserNotFound as exc:
            raise HTTPException(401, "authentication required") from exc
        # A changed password ends every other session but keeps this one alive.
        request.app.state.sessions.revoke_user_sessions(identity["id"], keep_token=_bearer_token(authorization))
        return {"ok": True}

    @application.post("/api/integrations/feishu/binding-code")
    def create_feishu_binding_code(payload: FeishuBindingCodeRequest, user: str = Depends(_user)):
        result = integrations.create_binding_code("feishu", user, payload.ttl_seconds)
        return {"provider": "feishu", "code": result["code"], "expires_at": result["expires_at"]}

    @application.get("/api/integrations/feishu/binding")
    def get_feishu_binding(user: str = Depends(_user)):
        binding = integrations.binding_for_user("feishu", user)
        if binding is None:
            return {"provider": "feishu", "bound": False}
        return {"provider": "feishu", "bound": True, "tenant_key": binding["tenant_key"],
                "subject_id": binding["subject_id"], "created_at": binding["created_at"],
                "updated_at": binding["updated_at"]}

    @application.delete("/api/integrations/feishu/binding")
    def revoke_feishu_binding(user: str = Depends(_user)):
        integrations.revoke_user_binding("feishu", user)
        return {"provider": "feishu", "bound": False}

    @application.post("/api/integrations/feishu/oauth/start")
    def start_feishu_oauth(user: str = Depends(_user)):
        """Create a one-time personal QR/OAuth URL for the current account."""
        if _auth_mode() != "password":
            raise HTTPException(404, "not found")
        if not oauth_available():
            raise HTTPException(503, "FEISHU_OAUTH_NOT_CONFIGURED")
        try:
            client = FeishuOAuthClient.from_env()
        except FeishuOAuthError as exc:
            raise HTTPException(503, exc.code) from None
        state = integrations.create_oauth_state("feishu", user, 600)
        url = client.authorization_url(state["state"])
        return {"provider": "feishu", "authorization_url": url,
                "expires_at": state["expires_at"], "qr_svg": client.qr_svg(url)}

    @application.get("/api/integrations/feishu/oauth/callback", include_in_schema=False)
    def feishu_oauth_callback(code: str = "", state: str = "", error: str = ""):
        """Feishu OAuth callback; binds the authorized Feishu identity to `state`."""
        if error:
            # A denied authorization is still a callback for a one-time state.
            # Consume it when possible so the same URL cannot later be reused
            # with a different authorization code.
            if state and len(state) <= 512:
                try:
                    integrations.consume_oauth_state("feishu", state)
                except IntegrationConflict:
                    pass
            return _oauth_result_page("未完成绑定", "你在飞书授权页取消了授权，请重新生成二维码。", success=False)
        if not code or not state or len(state) > 512:
            return _oauth_result_page("绑定链接无效", "缺少授权码或绑定状态，请回到 FundLex 设置页重新生成二维码。", success=False)
        try:
            user_id = integrations.consume_oauth_state("feishu", state)
        except IntegrationConflict as exc:
            messages = {
                "FEISHU_OAUTH_STATE_EXPIRED": "二维码已过期，请回到 FundLex 设置页重新生成。",
                "FEISHU_OAUTH_STATE_CONSUMED": "该二维码已使用，请重新生成。",
                "FEISHU_OAUTH_STATE_INVALID": "绑定链接无效，请重新生成二维码。",
            }
            return _oauth_result_page("绑定链接无效", messages.get(error_code(exc, "FEISHU_OAUTH_STATE_INVALID"), "绑定链接已失效，请重新生成二维码。"), success=False)
        try:
            identity = FeishuOAuthClient.from_env().exchange_identity(code)
        except FeishuOAuthError:
            return _oauth_result_page("飞书授权未完成", "无法读取飞书身份，请重新生成二维码后重试；如持续失败请联系管理员。", success=False)
        try:
            integrations.bind_oauth_identity("feishu", user_id, identity.tenant_key, identity.open_id)
        except IntegrationConflict as exc:
            messages = {
                "FEISHU_IDENTITY_ALREADY_BOUND": "该飞书账号已绑定其他 FundLex 账号，请先在原账号解除绑定。",
                "FEISHU_USER_ALREADY_BOUND": "当前 FundLex 账号已绑定其他飞书账号，请先在设置页解除绑定。",
                "FEISHU_REBIND_CONFLICT": "存在历史绑定记录，暂时无法自动换绑，请联系管理员处理。",
            }
            return _oauth_result_page("绑定失败", messages.get(error_code(exc, "FEISHU_BINDING_FAILED"), "绑定未完成，请稍后重试。"), success=False)
        return _oauth_result_page("绑定成功", f"飞书账号 {identity.name or identity.open_id} 已绑定到当前 FundLex 账号。现在可以在飞书私聊发送 DOCX 合同。", success=True)

    @application.get("/api/admin/integrations/feishu/health")
    def feishu_health(admin: dict = Depends(_admin)):
        return {"provider": "feishu", "configured": bool(os.environ.get("FUNDLEX_FEISHU_APP_ID") and os.environ.get("FUNDLEX_FEISHU_APP_SECRET")),
                "service_process_active": __import__("fundlex.integrations.feishu.service", fromlist=["active_service"]).active_service() is not None,
                **integrations.health()}

    @application.get("/api/admin/users")
    def admin_list_users(request: Request, admin: dict = Depends(_admin)):
        return {"users": request.app.state.users.list_users()}

    @application.post("/api/admin/users", status_code=201)
    def admin_create_user(payload: CreateUserRequest, request: Request, admin: dict = Depends(_admin)):
        from .auth import UserExists
        try:
            record = request.app.state.users.create_user(payload.username, payload.password,
                                                         payload.display_name, payload.role)
        except UserExists as exc:
            raise HTTPException(409, "username already exists") from exc
        except ValueError as exc:
            from .api_errors import raise_api_error
            raise_api_error(422, exc, fallback="INVALID_REQUEST")
        return _public_user(record)

    @application.post("/api/admin/users/{user_id}/disable")
    def admin_disable_user(user_id: str, request: Request, payload: DisableUserRequest | None = None,
                           admin: dict = Depends(_admin)):
        from .auth import UserNotFound
        disabled = True if payload is None else payload.disabled
        try:
            record = request.app.state.users.set_disabled(user_id, disabled)
        except UserNotFound as exc:
            raise HTTPException(404, "user not found") from exc
        if disabled:
            request.app.state.sessions.revoke_user_sessions(user_id)
        return {**_public_user(record), "disabled": record["disabled"]}

    @application.get("/api/guides")
    def list_guides(user: str = Depends(_user)):
        return {"items": guide_items(user)}

    @application.post("/api/guides", status_code=201)
    async def upload_guide(file: UploadFile = File(...), user: str = Depends(_user)):
        try:
            data = await file.read(MAX_UPLOAD_BYTES + 1)
            name = _validate_upload(file.filename or "", data)
            version = guide_store.create_custom_version(store, user, name, data)
        except ValueError as exc:
            from .api_errors import raise_api_error
            raise_api_error(422, exc, fallback="INVALID_REQUEST")
        finally:
            await file.close()
        return {"version": _guide_public(version, current=False)}

    @application.get("/api/guides/{version_id}")
    def get_guide(version_id: str, user: str = Depends(_user)):
        version = visible_guide(user, version_id)
        current = guide_store.current_guide(store, user)
        item = _guide_public(version, current=version["id"] == current["id"])
        issues = version.get("issues")
        item["issues_detail"] = issues if isinstance(issues, dict) else {}
        item["rules_overview"] = _rules_overview(store, version_id)
        prompts = version.get("prompt_versions")
        item["prompt_versions"] = prompts if isinstance(prompts, dict) else {}
        return item

    @application.post("/api/guides/{version_id}/parse", status_code=202)
    def parse_guide(version_id: str, user: str = Depends(_user)):
        version = visible_guide(user, version_id)
        if version["built_in"]:
            raise HTTPException(403, "built-in guide is already parsed and released")
        if version["status"] not in guide_store.PARSEABLE_STATUSES:
            raise HTTPException(409, "GUIDE_NOT_PARSEABLE")
        try:
            guide_store.enqueue_parse(store, version_id)
        except KeyError as exc:
            raise HTTPException(404, "guide version not found") from exc
        except ValueError as exc:
            from .api_errors import raise_api_error
            raise_api_error(409, exc, fallback="CONFLICT")
        refreshed = visible_guide(user, version_id)
        current = guide_store.current_guide(store, user)
        return {"version": _guide_public(refreshed, current=refreshed["id"] == current["id"])}

    @application.get("/api/guides/{version_id}/source")
    def guide_source(version_id: str, user: str = Depends(_user)):
        version = visible_guide(user, version_id)
        if version["built_in"]:
            # The frozen built-in guide has no user-supplied DOCX to hand back.
            raise HTTPException(404, "BUILTIN_SOURCE_UNAVAILABLE")
        try:
            path = guide_store.guide_source_path(store, version_id)
        except (KeyError, StoreError) as exc:
            raise HTTPException(404, "guide source not available") from exc
        if not path.is_file():
            raise HTTPException(404, "guide source not available")
        return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            filename=Path(version["filename"] or f"{version_id}.docx").name,
                            headers={"Cache-Control": "private, no-store"})

    @application.get("/api/guides/{version_id}/rules")
    def guide_rules(version_id: str, user: str = Depends(_user)):
        version = visible_guide(user, version_id)
        if version["status"] not in {"parsed", "validated", "released"}:
            raise HTTPException(404, "guide rules not available")
        try:
            return guide_store.guide_document(store, version_id)
        except (KeyError, StoreError) as exc:
            raise HTTPException(404, "guide rules not available") from exc

    @application.get("/api/settings/guide")
    def get_guide_settings(user: str = Depends(_user)):
        return guide_settings(user)

    @application.put("/api/settings/guide")
    def update_guide_settings(payload: GuideSettingRequest, user: str = Depends(_user)):
        requested = (payload.version_id or "").strip()
        target = (guide_store.BUILTIN_GUIDE_ID if requested in _GUIDE_RESET_IDS | {guide_store.BUILTIN_GUIDE_ID}
                  else requested)
        try:
            guide_store.set_current_guide(store, user, target)
        except KeyError as exc:
            raise_api_error(404, exc, fallback="GUIDE_NOT_FOUND")
        except ValueError as exc:
            raise_api_error(409, exc, fallback="CONFLICT")
        return guide_settings(user)

    @application.post("/api/tasks", status_code=201)
    def create_task(payload: TaskSubmission,
                    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                    user: str = Depends(_user)):
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise HTTPException(422, "invalid idempotency key")
        engine = (payload.engine_id or "").strip()
        ruleset_version = (payload.ruleset_version or "").strip()
        if ruleset_version:
            # The legacy rulesets were retired from the runtime; the guide-bound
            # engine is the only way to create a task now.
            raise HTTPException(422, "RULESET_RETIRED")
        if not engine:
            raise HTTPException(422, "ENGINE_REQUIRED")
        if engine != RECALL_ENGINE_ID:
            raise HTTPException(422, "ENGINE_UNSUPPORTED")
        try:
            return task_service.create_task(user, payload.name,
                                            [f.model_dump() for f in payload.files],
                                            guide_version_id=payload.guide_version_id,
                                            idempotency_key=idempotency_key)
        except ValueError as exc:
            if error_code(exc, "CONFLICT") == "GUIDE_NOT_FOUND":
                raise_api_error(404, exc, fallback="GUIDE_NOT_FOUND")
            raise_api_error(409, exc, fallback="CONFLICT")
        except Conflict as exc:
            raise_api_error(409, exc, fallback="CONFLICT")

    @application.get("/api/tasks")
    def list_tasks(q: str = "", status: str | None = None, sort: str = "newest",
                   guide_version_id: str | None = None,
                   page: int = 1, page_size: int = 50, user: str = Depends(_user)):
        check_pagination(page, page_size, sort)
        if guide_version_id is not None and len(guide_version_id) > 128:
            raise HTTPException(422, "invalid guide_version_id")
        return tasks.list(user, q=q, status=status, sort=sort,
                          guide_version_id=guide_version_id,
                          page=page, page_size=page_size)

    @application.get("/api/tasks/stats")
    def task_stats(month: str | None = None, user: str = Depends(_user)):
        try:
            return tasks.stats(user, month=month)
        except ValueError as exc:
            raise HTTPException(422, "invalid month") from exc

    def check_pagination(page, page_size, sort, *, documents=False):
        allowed = {"newest", "oldest", "name", "name_desc"} | ({"exceptions", "status"} if documents else set())
        if page < 1 or not 1 <= page_size <= 200 or sort not in allowed:
            raise HTTPException(422, "invalid pagination or sorting")

    @application.get("/api/tasks/{task_id}")
    def get_task(task_id: str, user: str = Depends(_user)):
        return task_call(tasks.get, user, task_id)

    @application.get("/api/tasks/{task_id}/documents")
    def task_documents(task_id: str, q: str = "", eligibility: str | None = None,
                       job_status: str | None = None, delivery_status: str | None = None,
                       error_code: str | None = None, upload_status: str | None = None,
                       sort: str = "oldest", page: int = 1, page_size: int = 50,
                       user: str = Depends(_user)):
        task_call(tasks.get, user, task_id)
        check_pagination(page, page_size, sort, documents=True)
        result = task_call(tasks.documents, user, task_id, q=q, eligibility=eligibility, job_status=job_status,
                           delivery_status=delivery_status, error_code=error_code, upload_status=upload_status,
                           sort=sort, page=page, page_size=page_size)
        metrics = _recall_metrics(store, result["items"], "document_id")
        for item in result["items"]:
            item.update(metrics.get(item["document_id"], {}))
        return result

    def task_document_context(user: str, task_id: str, document_id: str) -> tuple[str, dict]:
        document = task_call(tasks.document, user, task_id, document_id)
        batch_id = document.get("batch_id")
        if not batch_id:
            raise HTTPException(409, "document has no processing batch")
        return batch_id, document

    @application.get("/api/tasks/{task_id}/documents/{document_id}")
    def get_task_document(task_id: str, document_id: str, user: str = Depends(_user)):
        try:
            tasks.get(user, task_id)
        except NotFound as exc:
            raise HTTPException(404, "task not found") from exc
        try:
            return tasks.document(user, task_id, document_id)
        except NotFound as exc:
            raise HTTPException(404, "document not found") from exc

    @application.get("/api/tasks/{task_id}/documents/{document_id}/report")
    def task_document_report(task_id: str, document_id: str, user: str = Depends(_user)):
        batch_id, _ = task_document_context(user, task_id, document_id)
        return document_report(batch_id, document_id, user)

    @application.get("/api/tasks/{task_id}/documents/{document_id}/revisions")
    def task_document_revisions(task_id: str, document_id: str, user: str = Depends(_user)):
        batch_id, _ = task_document_context(user, task_id, document_id)
        return document_revisions(batch_id, document_id, user)

    @application.post("/api/tasks/{task_id}/documents/{document_id}/decisions")
    def task_document_decisions(task_id: str, document_id: str, payload: DecisionRequest,
                                user: str = Depends(_user)):
        batch_id, _ = task_document_context(user, task_id, document_id)
        return document_decisions(batch_id, document_id, payload, user)

    @application.post("/api/tasks/{task_id}/documents/{document_id}/accept-all")
    def task_document_accept_all(task_id: str, document_id: str, payload: DecisionRequest | None = None,
                                 user: str = Depends(_user)):
        batch_id, _ = task_document_context(user, task_id, document_id)
        return document_accept_all(batch_id, document_id, payload=payload, user=user)

    @application.get("/api/tasks/{task_id}/documents/{document_id}/download/{kind}")
    def task_document_download(task_id: str, document_id: str, kind: str, user: str = Depends(_user)):
        batch_id, _ = task_document_context(user, task_id, document_id)
        return download(batch_id, document_id, kind, user)

    @application.post("/api/tasks/{task_id}/uploads")
    async def upload_task(task_id: str, files: list[UploadFile] = File(...), client_ids: str = Form(...),
                          user: str = Depends(_user)):
        task_call(tasks.get, user, task_id)
        try:
            ids = json.loads(client_ids)
        except (ValueError, TypeError):
            raise HTTPException(422, "invalid client_ids") from None
        if not isinstance(ids, list) or len(ids) != len(files) or any(not isinstance(i, str) or not 1 <= len(i) <= 128 for i in ids) or len(set(ids)) != len(ids):
            raise HTTPException(422, "invalid client_ids")
        if len(files) > MAX_BATCH_DOCUMENTS:
            raise HTTPException(413, "upload request document count limit exceeded")
        uploads, total_bytes = [], 0
        reasons = {"only DOCX files are supported": "UNSUPPORTED_FILE_FORMAT", "DOCX upload size limit exceeded": "UPLOAD_SIZE_LIMIT",
                   "not an editable DOCX package": "INVALID_DOCX_PACKAGE", "encrypted DOCX is unsupported": "ENCRYPTED_DOCX",
                   "duplicate DOCX member": "DUPLICATE_DOCX_MEMBER", "DOCX part size limit exceeded": "DOCX_PART_SIZE_LIMIT",
                   "DOCX compression ratio limit exceeded": "DOCX_COMPRESSION_RATIO_LIMIT",
                   "DOCX expanded size limit exceeded": "DOCX_EXPANDED_SIZE_LIMIT", "invalid DOCX package": "INVALID_DOCX_PACKAGE"}
        try:
            for cid, upload in zip(ids, files):
                data = await upload.read(MAX_UPLOAD_BYTES + 1)
                total_bytes += len(data)
                name = Path((upload.filename or "").replace("\\", "/")).name
                error = None
                try:
                    validate_docx_upload(name, data)
                except UploadValidationError as exc:
                    error = exc.code
                if total_bytes > MAX_BATCH_BYTES:
                    error = "UPLOAD_REQUEST_SIZE_LIMIT"
                uploads.append({"client_id": cid, "name": name, "data": data, "error_code": error})
            return task_call(tasks.uploads, user, task_id, uploads)
        finally:
            for upload in files:
                await upload.close()

    @application.post("/api/tasks/{task_id}/seal")
    def seal_task(task_id: str, user: str = Depends(_user)):
        return task_call(tasks.control, user, task_id, "seal")

    @application.post("/api/tasks/{task_id}/pause")
    def pause_task(task_id: str, user: str = Depends(_user)):
        return task_call(tasks.control, user, task_id, "pause")

    @application.post("/api/tasks/{task_id}/resume")
    def resume_task(task_id: str, user: str = Depends(_user)):
        return task_call(tasks.control, user, task_id, "resume")

    @application.get("/api/tasks/{task_id}/report")
    def task_report(task_id: str, user: str = Depends(_user)):
        return PlainTextResponse(task_call(tasks.report, user, task_id), media_type="text/markdown; charset=utf-8",
                                 headers={"Cache-Control": "private, no-store"})

    @application.get("/api/tasks/{task_id}/download/all")
    def task_archive(task_id: str, user: str = Depends(_user)):
        task = task_call(tasks.get, user, task_id)
        docs, page = [], 1
        while True:
            result = task_call(tasks.documents, user, task_id, page=page, page_size=200)
            docs.extend(result["items"])
            if len(docs) >= result["total"] or not result["items"]:
                break
            page += 1
        output = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")
        try:
            count = 0
            rows = [["合同", "处理状态", "交付状态", "已打包文件"]]
            # The accepted-revision contracts go into their own folder so the deliverable
            # is the same shape as the offline package: 结果总览.md + 结果清单.csv +
            # 最终版（接受修订后）/<合同>.docx + 逐份修改说明/<合同>/.
            final_dir = "最终版（接受修订后）"
            notes_dir = "逐份修改说明"
            used_names: set[str] = set()

            def unique(name: str) -> str:
                if name not in used_names:
                    used_names.add(name)
                    return name
                index = 2
                while f"{name} ({index})" in used_names:
                    index += 1
                result = f"{name} ({index})"
                used_names.add(result)
                return result

            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for index, doc in enumerate(docs, 1):
                    name = Path(doc["name"].replace("\\", "/")).stem
                    name = "".join(c for c in name if c.isalnum() or c in " _-（）()")[:100] or "合同"
                    name = unique(name)
                    included = []
                    for kind in archive_kinds(doc.get("downloads")):
                        path, digest = store.get_artifact(user, doc["batch_id"], doc["document_id"], kind)
                        data = path.read_bytes()
                        if hashlib.sha256(data).hexdigest() != digest:
                            raise Conflict("ARTIFACT_VERIFICATION_MISMATCH")
                        _, arcname = archive_entry(kind, name, path.suffix,
                                                  delivery_status=doc["delivery_status"])
                        archive.writestr(arcname, data)
                        included.append(kind)
                        count += 1
                    rows.append([doc["name"], doc["job_status"], doc["delivery_status"], "; ".join(included)])
                if not count:
                    raise Conflict("暂无可下载结果，请等待合同处理完成")
                summary = io.StringIO()
                csv.writer(summary).writerows(rows)
                archive.writestr("结果清单.csv", summary.getvalue().encode("utf-8-sig"))
                archive.writestr("结果总览.md", task_call(tasks.report, user, task_id))
            output.seek(0)
        except (NotFound, Conflict) as exc:
            output.close()
            raise_api_error(409, exc, fallback="CONFLICT")
        except BaseException:
            output.close()
            raise
        def chunks():
            try:
                while data := output.read(256 * 1024):
                    yield data
            finally:
                output.close()
        return StreamingResponse(chunks(), media_type="application/zip",
                                 headers={"Content-Disposition": f'attachment; filename="fundlex-{task["id"]}.zip"',
                                          "Cache-Control": "private, no-store"},
                                 background=BackgroundTask(output.close))

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
        # The legacy rulesets are retired from the runtime; batches created here
        # used to run the ruleset-only path and produced no guide-bound edits.
        # Existing batches stay readable, but no new ones can be created.
        raise HTTPException(410, "RULESET_RETIRED")

    @application.get("/api/batches/{batch_id}")
    def get_batch(batch_id: str, user: str = Depends(_user)):
        try:
            batch = store.get_batch(user, batch_id)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        return _public_batch(batch, detail=True, metrics=_recall_metrics(store, batch["documents"], "id"))

    @application.post("/api/batches/{batch_id}/pause")
    def pause_batch(batch_id: str, user: str = Depends(_user)):
        try:
            batch = store.pause(user, batch_id)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        return _public_batch(batch, detail=True, metrics=_recall_metrics(store, batch["documents"], "id"))

    @application.post("/api/batches/{batch_id}/resume")
    def resume_batch(batch_id: str, user: str = Depends(_user)):
        try:
            batch = store.resume(user, batch_id)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        return _public_batch(batch, detail=True, metrics=_recall_metrics(store, batch["documents"], "id"))

    @application.get("/api/batches/{batch_id}/documents/{document_id}/report")
    def document_report(batch_id: str, document_id: str, user: str = Depends(_user)):
        try:
            return store.get_report(user, batch_id, document_id)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        except ReportJsonError as exc:
            raise_api_error(409, exc, fallback="REPORT_JSON_INVALID")

    @application.get("/api/batches/{batch_id}/documents/{document_id}/revisions")
    def document_revisions(batch_id: str, document_id: str, user: str = Depends(_user)):
        """HTML view of the contract with per-revision accept/reject anchors."""
        try:
            return task_call(_revision_view, user, batch_id, document_id)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        except Conflict as exc:
            raise_api_error(409, exc, fallback="CONFLICT")

    @application.post("/api/batches/{batch_id}/documents/{document_id}/decisions")
    def document_decisions(batch_id: str, document_id: str, payload: DecisionRequest,
                           user: str = Depends(_user)):
        """Apply per-revision decisions and publish ``selected_final``."""
        decisions = [{"del_id": item.del_id, "decision": item.decision}
                     for item in payload.decisions]
        try:
            return task_call(_apply_selection, user, batch_id, document_id, decisions,
                             expected_epoch=payload.selection_epoch,
                             expected_manifest_hash=payload.manifest_hash)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        except Conflict as exc:
            raise_api_error(409, exc, fallback="CONFLICT")
        except DocxError as exc:
            raise_api_error(422, exc, fallback="INVALID_DOCUMENT")

    @application.post("/api/batches/{batch_id}/documents/{document_id}/accept-all")
    def document_accept_all(batch_id: str, document_id: str, payload: DecisionRequest | None = None,
                            user: str = Depends(_user)):
        """Accept every revision and publish ``selected_final``."""
        try:
            return task_call(_apply_selection, user, batch_id, document_id, None,
                             expected_epoch=payload.selection_epoch if payload else None,
                             expected_manifest_hash=payload.manifest_hash if payload else None)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        except Conflict as exc:
            raise_api_error(409, exc, fallback="CONFLICT")
        except DocxError as exc:
            raise_api_error(422, exc, fallback="INVALID_DOCUMENT")

    @application.get("/api/batches/{batch_id}/documents/{document_id}/download/{kind}")
    def download(batch_id: str, document_id: str, kind: str, user: str = Depends(_user)):
        docx_kinds = {"final", "redline", "evaluation_final", "evaluation_redline",
                      "working_final", "working_redline", "selected_final", "selected_redline"}
        if kind not in docx_kinds | {"report_json", "report_md"}:
            raise HTTPException(404, "artifact not found")
        try:
            path, digest = store.get_artifact(user, batch_id, document_id, kind)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        except Conflict as exc:
            raise_api_error(409, exc, fallback="CONFLICT")
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if kind in docx_kinds else ("application/json" if kind == "report_json" else "text/markdown")
        return FileResponse(path, media_type=media, filename=f"{document_id}_{kind}{path.suffix}",
                            headers={"ETag": digest, "Cache-Control": "private, no-store"})

    @application.get("/api/batches/{batch_id}/report")
    def batch_report(batch_id: str, user: str = Depends(_user)):
        try:
            batch = store.get_batch(user, batch_id)
        except NotFound as exc:
            raise_api_error(404, exc, fallback="NOT_FOUND")
        qualifications: Counter[str] = Counter()
        deliveries: Counter[str] = Counter()
        action_states: Counter[str] = Counter()
        candidate_states: Counter[str] = Counter()
        report_errors: Counter[str] = Counter()
        for doc in batch["documents"]:
            qualifications[doc["qualification_status"] or "pending"] += 1
            deliveries[doc["delivery_status"]] += 1
            try:
                report = store.get_report(user, batch_id, doc["id"])
            except NotFound:
                continue
            except ReportJsonError as exc:
                report_errors[exc.code] += 1
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
                 f"- action：{dict(action_states)}", f"- 候选位置：{dict(candidate_states)}",
                 f"- 报告读取异常：{dict(report_errors)}", "",
                 "| 合同 ID | 文件 | 资格 | 交付 | 任务 | 错误 |", "|---|---|---|---|---|---|"]
        for doc in batch["documents"]:
            safe_name = doc["filename"].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {doc['id']} | {safe_name} | {doc['qualification_status'] or '-'} | {doc['delivery_status']} | {doc['status']} | {doc['error_code'] or '-'} |")
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/markdown; charset=utf-8")

    # Contract comparison has its own task/store/worker surface and is mounted
    # independently from the revision task routes above.
    register_compare_routes(application, compare_store, _user, _validate_upload,
                            max_upload_bytes=MAX_UPLOAD_BYTES,
                            max_batch_bytes=MAX_BATCH_BYTES,
                            max_request_files=MAX_BATCH_DOCUMENTS,
                            max_pairs=1000)

    frontend = Path(__file__).resolve().parent.parent / "frontend"
    dist = frontend / "dist"
    # V1 is the default workbench again. Keep the Vite source/build available
    # for explicit V2 regression runs without letting a build switch the UI.
    frontend_v2 = os.environ.get("FUNDLEX_FRONTEND_VERSION", "v1") == "v2"
    frontend_base = os.environ.get("FUNDLEX_FRONTEND_BASE_PATH", "").rstrip("/")
    if frontend_base and not frontend_base.startswith("/"):
        frontend_base = f"/{frontend_base}"
    if frontend_base == "/":
        frontend_base = ""
    if frontend_base:
        application.add_middleware(FrontendBasePathMiddleware, base_path=frontend_base)
    if frontend.is_dir():
        application.mount("/static", StaticFiles(directory=frontend), name="static")
        if (dist / "assets").is_dir():
            application.mount("/assets", StaticFiles(directory=dist / "assets"), name="vite-assets")

        def _asset_version(*names: str) -> str:
            """内容哈希做缓存标识：任一静态资源变化即生成新 URL。"""
            digest = hashlib.sha256()
            for name in names:
                path = frontend / name
                digest.update(name.encode("utf-8"))
                try:
                    digest.update(path.read_bytes())
                except OSError:
                    digest.update(b"missing")
            return digest.hexdigest()[:16]

        @application.get("/", include_in_schema=False)
        def home():
            entry = ((dist / "index.html" if (dist / "index.html").is_file() else frontend / "index.html")
                     if frontend_v2 else frontend / "compare.html")
            html = entry.read_text(encoding="utf-8")
            version = _asset_version("dist/index.html", "app.css", "app.js", "compare.css", "compare.js")
            for name in ("app.css", "app.js", "compare.css", "compare.js"):
                html = html.replace(f'/static/{name}"', f'/static/{name}?v={version}"')
            if frontend_base:
                html = html.replace('="/static/', f'="{frontend_base}/static/')
                html = html.replace('="/assets/', f'="{frontend_base}/assets/')
                html = html.replace("url(/static/", f"url({frontend_base}/static/")
                html = html.replace('</head>', f'<meta name="fundlex-base-path" content="{frontend_base}"></head>')
            html = html.replace('src="/src/main.tsx"', f'src="/src/main.tsx?v={version}"')
            html = html.replace('href="/assets/', f'href="/assets/')
            return HTMLResponse(
                html,
                headers={"Cache-Control": "no-store, must-revalidate"},
            )

        @application.get("/index.html", include_in_schema=False)
        def index_html():
            return home()

        @application.get("/favicon.ico", include_in_schema=False)
        def favicon():
            # Keep the conventional browser request valid even though the
            # React entry also carries an inline fallback favicon.
            return Response(
                content=(
                    "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\">"
                    "<rect width=\"64\" height=\"64\" rx=\"14\" fill=\"#B5471E\"/>"
                    "<path d=\"M17 17h30v8H25v7h18v8H25v7h22v8H17z\" fill=\"white\"/>"
                    "</svg>"
                ),
                media_type="image/svg+xml",
                headers={"Cache-Control": "public, max-age=31536000, immutable"},
            )

        @application.get("/compare", include_in_schema=False)
        def compare_home():
            if not frontend_v2:
                return RedirectResponse(f"{frontend_base}/#compare", status_code=307)
            return home()

        @application.get("/{full_path:path}", include_in_schema=False)
        def frontend_fallback(full_path: str):
            # Browser refreshes on React routes must resolve to the Vite entry.
            # API and static mounts are registered before this catch-all.
            if full_path == "api" or full_path.startswith("api/"):
                raise HTTPException(404, "not found")
            # A source asset is a Vite-dev-server concern; returning HTML for
            # /src/main.tsx makes a missing production build look successful
            # while the browser fails later with a misleading module error.
            if Path(full_path).suffix:
                raise HTTPException(404, "frontend asset is not built")
            if not frontend_v2:
                if full_path.startswith("tasks/") and full_path != "tasks/new":
                    task_id = full_path[len("tasks/"):]
                    if task_id and "/" not in task_id:
                        return RedirectResponse(
                            f"{frontend_base}/?task={quote(task_id)}#task", status_code=307)
                view = {"tasks": "overview", "tasks/new": "import", "guides": "guide",
                        "settings": "settings", "users": "users"}.get(full_path, "overview")
                return RedirectResponse(f"{frontend_base}/#{view}", status_code=307)
            return home()

        @application.middleware("http")
        async def static_cache_control(request, call_next):
            response = await call_next(request)
            path = request.url.path
            if path.startswith("/static/") or path.startswith("/assets/"):
                # 静态资源 URL 带内容哈希，可长期缓存；入口 HTML 必须每次校验。
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path in ("/", "/index.html"):
                response.headers["Cache-Control"] = "no-store, must-revalidate"
            return response

    return application


app = create_app()
