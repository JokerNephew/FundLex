"""Local development HTTP API. Run with ``uvicorn fundlex.api:app``.

The development identity adapter requires X-FundLex-User on every API request.
Production identity integration is deliberately unconfigured and fails closed.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .store import Conflict, NotFound, RunStore
from .config import auth_db_target, local_data_dir
from .tasks import TaskStore
from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    ruleset_version: str = Field(min_length=1, max_length=128)
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


MAX_UPLOAD_BYTES = int(os.environ.get("FUNDLEX_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UNCOMPRESSED_BYTES = int(os.environ.get("FUNDLEX_MAX_UNCOMPRESSED_BYTES", str(200 * 1024 * 1024)))
MAX_BATCH_DOCUMENTS = int(os.environ.get("FUNDLEX_MAX_BATCH_DOCUMENTS", "20"))
MAX_BATCH_BYTES = int(os.environ.get("FUNDLEX_MAX_BATCH_BYTES", str(50 * 1024 * 1024)))
MAX_PART_BYTES = int(os.environ.get("FUNDLEX_MAX_PART_BYTES", str(32 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = int(os.environ.get("FUNDLEX_MAX_COMPRESSION_RATIO", "100"))


def _auth_mode() -> str:
    return os.environ.get("FUNDLEX_AUTH_MODE", "dev")


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
            "execution_mode": d.get("execution_mode", ""),
            "error_code": d["error_code"], "report_url": d["report_url"],
            "downloads": d["download_urls"], "source_sha256": d["source_sha256"],
        } for d in docs]
    return base


def create_app(data_dir: str | Path | None = None, *, auth_db=None) -> FastAPI:
    application = FastAPI(title="FundLex", version="0.1.0")

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
            raise HTTPException(409, str(exc)) from exc

    @application.get("/api/capabilities")
    def capabilities(identity: dict | None = Depends(_capabilities_identity)):
        mode = _auth_mode()
        if mode == "password" and identity is None:
            # Minimal pre-login payload: no ruleset or identity metadata leaks.
            return {"auth_mode": mode, "login_required": True, "task_api": True}
        from .rules import RuleError, load_ruleset
        from .rules_v2 import RuleV2Error, load_ruleset_v2
        try:
            rule = load_ruleset("v1")
        except RuleError as exc:
            raise HTTPException(503, str(exc)) from exc
        revision: dict = {"revision_ruleset_version": None, "revision_ruleset_sha256": None,
                          "revision_actions_total": 0, "revision_auto_write_enabled": False,
                          "revision_mode": None, "revision_action_labels": {}}
        try:
            revision_rule = load_ruleset_v2("v2")
            revision = {"revision_ruleset_version": revision_rule.version,
                        "revision_ruleset_sha256": revision_rule.sha256,
                        "revision_actions_total": len(revision_rule.actions),
                        "revision_auto_write_enabled": revision_rule.auto_write_enabled,
                        "revision_mode": "delivery" if revision_rule.auto_write_enabled else "evaluation",
                        "revision_action_labels": {a["action_id"]: a.get("description", "")
                                                   for a in revision_rule.actions}}
        except RuleV2Error:
            pass
        return {"auth_mode": mode, "login_required": mode == "password", "task_api": True,
                "ruleset_version": rule.version, "ruleset_sha256": rule.sha256,
                "actions_total": len(rule.actions), "auto_write_enabled": rule.auto_write_enabled,
                "auto_write_count": sum(bool(a["auto_write"]) for a in rule.actions),
                "action_labels": {a["action_id"]: a.get("description", "") for a in rule.actions},
                "upload_limits": {"max_file_bytes": MAX_UPLOAD_BYTES, "max_request_files": MAX_BATCH_DOCUMENTS,
                                  "max_request_bytes": MAX_BATCH_BYTES},
                **revision}

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
            raise HTTPException(422, str(exc)) from exc
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

    @application.post("/api/tasks", status_code=201)
    def create_task(payload: TaskSubmission,
                    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
                    user: str = Depends(_user)):
        from .rules import RuleError, load_ruleset
        from .rules_v2 import RuleV2Error, load_ruleset_v2
        if idempotency_key is not None and (not idempotency_key.strip() or len(idempotency_key) > 128):
            raise HTTPException(422, "invalid idempotency key")
        try:
            rule = load_ruleset(payload.ruleset_version.strip())
        except RuleError:
            try:
                rule = load_ruleset_v2(payload.ruleset_version.strip())
            except RuleV2Error as exc:
                raise HTTPException(422, str(exc)) from exc
        return task_call(tasks.create, user, payload.name, rule, [f.model_dump() for f in payload.files], idempotency_key)

    @application.get("/api/tasks")
    def list_tasks(q: str = "", status: str | None = None, sort: str = "newest",
                   page: int = 1, page_size: int = 50, user: str = Depends(_user)):
        check_pagination(page, page_size, sort)
        return tasks.list(user, q=q, status=status, sort=sort, page=page, page_size=page_size)

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
        return task_call(tasks.documents, user, task_id, q=q, eligibility=eligibility, job_status=job_status,
                         delivery_status=delivery_status, error_code=error_code, upload_status=upload_status,
                         sort=sort, page=page, page_size=page_size)

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
        for cid, upload in zip(ids, files):
            data = await upload.read(MAX_UPLOAD_BYTES + 1)
            total_bytes += len(data)
            name = Path((upload.filename or "").replace("\\", "/")).name
            error = None
            try:
                _validate_upload(name, data)
            except HTTPException as exc:
                error = reasons.get(str(exc.detail), "UPLOAD_REJECTED")
            if total_bytes > MAX_BATCH_BYTES:
                error = "UPLOAD_REQUEST_SIZE_LIMIT"
            uploads.append({"client_id": cid, "name": name, "data": data, "error_code": error})
        return task_call(tasks.uploads, user, task_id, uploads)

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
        from .rules_v2 import RuleV2Error, load_ruleset_v2
        try:
            ruleset = load_ruleset(ruleset_version.strip())
        except RuleError:
            try:
                # v2 exists for evaluation-mode batches only; the loader refuses
                # any package that claims auto-write.
                ruleset = load_ruleset_v2(ruleset_version.strip())
            except RuleV2Error as exc:
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
        docx_kinds = {"final", "redline", "evaluation_final", "evaluation_redline"}
        if kind not in docx_kinds | {"report_json", "report_md"}:
            raise HTTPException(404, "artifact not found")
        try:
            path, digest = store.get_artifact(user, batch_id, document_id, kind)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if kind in docx_kinds else ("application/json" if kind == "report_json" else "text/markdown")
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
