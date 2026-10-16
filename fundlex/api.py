"""Local development HTTP API. Run with ``uvicorn fundlex.api:app``.

The development identity adapter requires X-FundLex-User on every API request.
Production identity integration is deliberately unconfigured and fails closed.
"""

from __future__ import annotations

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

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
    StreamingResponse,
)
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles

from . import guide_store
from .docx import DocxError
from .edit_summary import archive_entry, archive_kinds
from .html_view import project_docx
from .selective import (accept_all as selective_accept_all, generate_selected_artifact,
                        generate_selected_redline)
from .store import Conflict, NotFound, RunStore, StoreError
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


class RevisionDecision(BaseModel):
    """One user decision on a single engine revision pair."""

    model_config = ConfigDict(extra="forbid")
    del_id: int = Field(ge=1)
    decision: str = Field(pattern="^(accept|reject)$")


class DecisionRequest(BaseModel):
    """Per-revision accept/reject for one document's redline."""

    model_config = ConfigDict(extra="forbid")
    decisions: list[RevisionDecision] = Field(default_factory=list, max_length=1000)


MAX_UPLOAD_BYTES = int(os.environ.get("FUNDLEX_MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))
MAX_UNCOMPRESSED_BYTES = int(os.environ.get("FUNDLEX_MAX_UNCOMPRESSED_BYTES", str(200 * 1024 * 1024)))
MAX_BATCH_DOCUMENTS = int(os.environ.get("FUNDLEX_MAX_BATCH_DOCUMENTS", "20"))
MAX_BATCH_BYTES = int(os.environ.get("FUNDLEX_MAX_BATCH_BYTES", str(50 * 1024 * 1024)))
MAX_PART_BYTES = int(os.environ.get("FUNDLEX_MAX_PART_BYTES", str(32 * 1024 * 1024)))
MAX_COMPRESSION_RATIO = int(os.environ.get("FUNDLEX_MAX_COMPRESSION_RATIO", "100"))


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
    completed = sum(1 for item in targets if item.get("status") in _RECALL_TARGET_DONE)
    unresolved = sum(1 for item in targets if item.get("status") in _RECALL_TARGET_UNRESOLVED)
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
            report = json.loads(row["report_json"]) if row["report_json"] else None
        except (TypeError, ValueError):
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
        } | (metrics or {}).get(d["id"], {}) for d in docs]
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
        view = project_docx(str(path), report=report)
        return {
            "document_id": document_id,
            "html": view["html"],
            "revisions": view["revisions"],
            "meta": view["meta"],
            "download_url": f"/api/batches/{batch_id}/documents/{document_id}/download/selected_final",
        }

    def _apply_selection(owner: str, batch_id: str, document_id: str,
                         decisions: dict[int, str] | None) -> dict:
        path, report = _redline_for(owner, batch_id, document_id)
        chosen = decisions if decisions is not None else selective_accept_all(str(path), report)
        temp_dir = Path(tempfile.mkdtemp(prefix="fundlex-selected-"))
        target = temp_dir / "selected_final.docx"
        derived_redline = temp_dir / "selected_redline.docx"
        try:
            result = generate_selected_artifact(path, target, report, chosen)
            store.save_selected_artifact(owner, batch_id, document_id, "selected_final", target)
            # The engine redline tracks every planned edit, including the ones the
            # user just turned down. Publish a redline that agrees with this
            # selection so the delivered pair stays consistent.
            try:
                generate_selected_redline(path, derived_redline, report, chosen)
                store.save_selected_artifact(owner, batch_id, document_id,
                                             "selected_redline", derived_redline)
            except (DocxError, Conflict, StoreError):
                # The selected contract is already published; a redline that
                # cannot be derived must not fail the whole decision request.
                store.remove_selected_artifact(owner, batch_id, document_id, "selected_redline")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
        return {
            "document_id": document_id,
            "accepted": list(result.accepted),
            "rejected": list(result.rejected),
            "sha256": result.sha256,
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
                    "registration_open": _registration_open()}
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
                "registration_open": _registration_open(),
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
            raise HTTPException(422, str(exc)) from exc
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

    @application.get("/api/guides")
    def list_guides(user: str = Depends(_user)):
        return {"items": guide_items(user)}

    @application.post("/api/guides", status_code=201)
    async def upload_guide(file: UploadFile = File(...), user: str = Depends(_user)):
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        name = _validate_upload(file.filename or "", data)
        try:
            version = guide_store.create_custom_version(store, user, name, data)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
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
        if version["status"] not in {"uploaded", "parse_failed", "parsed"}:
            raise HTTPException(409, "GUIDE_NOT_PARSEABLE")
        try:
            guide_store.enqueue_parse(store, version_id)
        except KeyError as exc:
            raise HTTPException(404, "guide version not found") from exc
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
            raise HTTPException(404, "guide version not found") from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
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
        version = bound_guide_version(user, payload.guide_version_id)
        return task_call(tasks.create, user, payload.name, version,
                         [f.model_dump() for f in payload.files], idempotency_key,
                         engine_id=RECALL_ENGINE_ID, guide_version_id=version["id"],
                         guide_rules_sha256=version["rules_sha256"])

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
        result = task_call(tasks.documents, user, task_id, q=q, eligibility=eligibility, job_status=job_status,
                           delivery_status=delivery_status, error_code=error_code, upload_status=upload_status,
                           sort=sort, page=page, page_size=page_size)
        metrics = _recall_metrics(store, result["items"], "document_id")
        for item in result["items"]:
            item.update(metrics.get(item["document_id"], {}))
        return result

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
                        _, arcname = archive_entry(kind, name, path.suffix)
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
            raise HTTPException(409, str(exc)) from exc
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
            raise HTTPException(404, str(exc)) from exc
        return _public_batch(batch, detail=True, metrics=_recall_metrics(store, batch["documents"], "id"))

    @application.post("/api/batches/{batch_id}/pause")
    def pause_batch(batch_id: str, user: str = Depends(_user)):
        try:
            batch = store.pause(user, batch_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        return _public_batch(batch, detail=True, metrics=_recall_metrics(store, batch["documents"], "id"))

    @application.post("/api/batches/{batch_id}/resume")
    def resume_batch(batch_id: str, user: str = Depends(_user)):
        try:
            batch = store.resume(user, batch_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        return _public_batch(batch, detail=True, metrics=_recall_metrics(store, batch["documents"], "id"))

    @application.get("/api/batches/{batch_id}/documents/{document_id}/report")
    def document_report(batch_id: str, document_id: str, user: str = Depends(_user)):
        try:
            return store.get_report(user, batch_id, document_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc

    @application.get("/api/batches/{batch_id}/documents/{document_id}/revisions")
    def document_revisions(batch_id: str, document_id: str, user: str = Depends(_user)):
        """HTML view of the contract with per-revision accept/reject anchors."""
        try:
            return task_call(_revision_view, user, batch_id, document_id)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc

    @application.post("/api/batches/{batch_id}/documents/{document_id}/decisions")
    def document_decisions(batch_id: str, document_id: str, payload: DecisionRequest,
                           user: str = Depends(_user)):
        """Apply per-revision decisions and publish ``selected_final``."""
        decisions = {item.del_id: item.decision for item in payload.decisions}
        try:
            return task_call(_apply_selection, user, batch_id, document_id, decisions)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except DocxError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.post("/api/batches/{batch_id}/documents/{document_id}/accept-all")
    def document_accept_all(batch_id: str, document_id: str, user: str = Depends(_user)):
        """Accept every revision and publish ``selected_final``."""
        try:
            return task_call(_apply_selection, user, batch_id, document_id, None)
        except NotFound as exc:
            raise HTTPException(404, str(exc)) from exc
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except DocxError as exc:
            raise HTTPException(422, str(exc)) from exc

    @application.get("/api/batches/{batch_id}/documents/{document_id}/download/{kind}")
    def download(batch_id: str, document_id: str, kind: str, user: str = Depends(_user)):
        docx_kinds = {"final", "redline", "evaluation_final", "evaluation_redline",
                      "working_final", "working_redline", "selected_final", "selected_redline"}
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

        def _asset_version(*names: str) -> str:
            """内容哈希做缓存标识：任一静态资源变化即生成新 URL，避免浏览器沿用旧缓存。"""
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
            html = (frontend / "index.html").read_text(encoding="utf-8")
            version = _asset_version("app.css", "app.js")
            html = html.replace('/static/app.css"', f'/static/app.css?v={version}"')
            html = html.replace('/static/app.js"', f'/static/app.js?v={version}"')
            return HTMLResponse(
                html,
                headers={"Cache-Control": "no-store, must-revalidate"},
            )

        @application.middleware("http")
        async def static_cache_control(request, call_next):
            response = await call_next(request)
            path = request.url.path
            if path.startswith("/static/"):
                # 静态资源 URL 带内容哈希，可长期缓存；入口 HTML 必须每次校验。
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path in ("/", "/index.html"):
                response.headers["Cache-Control"] = "no-store, must-revalidate"
            return response

    return application


app = create_app()
