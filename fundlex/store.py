"""SQLite task state and isolated local objects for the development profile.

The database contains metadata, never document bodies.  Each worker update is
guarded by a monotonically increasing fencing token.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .db import Connection, Database

SCHEMA_VERSION = "fundlex-result-v1"


# Two different identities are published by this module:
#
# * ``engine_build()`` is pinned by queued jobs, batches and checkpoints.  It
#   must change only when an input that can change a processed contract's
#   result changes.  Operational code (HTTP API, auth, persistence, UI, upload
#   guards, queues, notifications, compare/integrations) is deliberately
#   excluded so that deploying an API/auth/UI-only fix does not fail in-flight
#   jobs with ``ENGINE_SCHEMA_MISMATCH``.
# * ``service_build()`` covers the complete shipped service source set and is
#   for audit and deployment display only.  It changes on any backend/rules/
#   guides edit, including operational ones.
#
# The engine rule is an explicit allowlist, not a blocklist: a new module is
# inert until someone deliberately adds it here, and the fingerprint test
# guards both directions (core changes must move the digest, operational ones
# must not).  A new result-affecting module must be added to this manifest.
_ENGINE_BUILD_ROOT = Path(__file__).resolve().parent.parent

# Result-affecting backend modules, relative to ``_ENGINE_BUILD_ROOT``.
_ENGINE_BUILD_MODULES = (
    # Contract parsing, recall, evidence verification and decisions.
    "fundlex/applicability.py",
    "fundlex/artifact_review.py",
    "fundlex/checkpoints.py",
    "fundlex/delivery.py",
    "fundlex/docx.py",
    "fundlex/edit_summary.py",
    "fundlex/fact_evidence.py",
    "fundlex/facts_recovery.py",
    "fundlex/fee_evidence.py",
    "fundlex/frozen.py",
    "fundlex/guide.py",
    "fundlex/model.py",
    "fundlex/model_budget.py",
    "fundlex/obligations.py",
    "fundlex/pipeline.py",
    "fundlex/qualification.py",
    "fundlex/qualification_evidence.py",
    "fundlex/recall.py",
    "fundlex/recall_pipeline.py",
    "fundlex/recall_prompts.py",
    "fundlex/rule_scope.py",
    "fundlex/rules.py",
    "fundlex/rules_v2.py",
    "fundlex/selective.py",
    "fundlex/semantic_evidence.py",
    "fundlex/stage_replay.py",
    "fundlex/targeting.py",
    "fundlex/v2.py",
    "fundlex/v2_pipeline.py",
)
# Result-affecting packages (all Python files, including subpackages).
_ENGINE_BUILD_PACKAGES = (
    "fundlex/generation",
    "fundlex/models",
    "fundlex/recovery",
    "fundlex/regulatory",
)
# Rules and guides are behaviour: a changed rule/guide must invalidate a job.
_ENGINE_BUILD_DATA_PATHS = (
    ("rules", "*.py"),
    ("rules", "*.json"),
    ("guides", "*.json"),
)
# Every backend source file the service ships, for audit/deploy display.
_SERVICE_BUILD_PATHS = (
    ("fundlex", "**/*.py"),
    ("rules", "*.py"),
    ("rules", "*.json"),
    ("guides", "*.json"),
)


def _matching_files(manifest: tuple[tuple[str, str], ...]) -> set[Path]:
    files: set[Path] = set()
    for relative_root, pattern in manifest:
        root = _ENGINE_BUILD_ROOT / relative_root
        files.update(path for path in root.glob(pattern) if path.is_file())
    return files


def _sorted_build_files(files: set[Path]) -> tuple[Path, ...]:
    return tuple(sorted(files, key=lambda path: path.relative_to(_ENGINE_BUILD_ROOT).as_posix()))


def _engine_build_files() -> tuple[Path, ...]:
    files = {_ENGINE_BUILD_ROOT / relative for relative in _ENGINE_BUILD_MODULES}
    files = {path for path in files if path.is_file()}
    for relative in _ENGINE_BUILD_PACKAGES:
        package = _ENGINE_BUILD_ROOT / relative
        files.update(path for path in package.glob("**/*.py") if path.is_file())
    files.update(_matching_files(_ENGINE_BUILD_DATA_PATHS))
    return _sorted_build_files(files)


def _service_build_files() -> tuple[Path, ...]:
    return _sorted_build_files(_matching_files(_SERVICE_BUILD_PATHS))


def _build_digest(files: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(_ENGINE_BUILD_ROOT).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def engine_build() -> str:
    """Compatibility identity for queued jobs, batches and checkpoints."""
    return _build_digest(_engine_build_files())


def service_build() -> str:
    """Full shipped service source identity, for audit/deploy display only."""
    return _build_digest(_service_build_files())


class StoreError(Exception):
    pass


class NotFound(StoreError):
    pass


class Conflict(StoreError):
    pass


REPORT_JSON_INVALID = "REPORT_JSON_INVALID"


class ReportJsonError(Conflict):
    """A persisted report cannot be decoded into the public report shape.

    The exception deliberately carries only a stable business code.  In
    particular, JSON decoder messages can contain snippets of persisted
    report content and must never reach an API response.
    """

    code = REPORT_JSON_INVALID

    def __init__(self):
        super().__init__(self.code)


def parse_report_json(raw: Any) -> dict[str, Any] | None:
    """Decode one persisted ``report_json`` value through one safe boundary.

    Missing reports are represented by ``None``.  Any malformed JSON or valid
    JSON value with the wrong top-level shape is the same controlled business
    error to callers.
    """
    if raw is None or raw == "":
        return None
    try:
        report = json.loads(raw)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ReportJsonError() from exc
    if not isinstance(report, dict):
        raise ReportJsonError()
    return report


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


EVALUATION_ARTIFACT_HASHES = {"evaluation_redline": "redline_sha256", "evaluation_final": "final_sha256"}


def _requires_actual_review(report: dict[str, Any]) -> bool:
    try:
        return tuple(int(part) for part in report.get("engine_version", "0.0.0").split(".")) >= (0, 3, 0)
    except (ValueError, AttributeError):
        raise ValueError("ENGINE_VERSION_INVALID") from None


def is_recall_report(report: dict[str, Any]) -> bool:
    """True for the recall-first engine report (engine id or schema 3)."""
    return report.get("engine_id") == "recall_first" or str(report.get("schema_version") or "") == "3"


_RECALL_EDIT_CHECKS = {"package", "revisions", "final_equivalence", "non_target",
                       "content_verification", "actual_content_verification"}
_RECALL_UNCHANGED_CHECKS = {"package", "zero_edit", "byte_identity"}
_RECALL_ARTIFACT_HASHES = {"final": "final_sha256", "redline": "redline_sha256",
                           "working_final": "final_sha256", "working_redline": "redline_sha256"}
# User-driven artifacts derived from an engine revision artifact. They live
# alongside delivery artifacts but are not part of delivery validation.
SELECTED_KINDS = {"selected_final", "selected_redline"}


def _manifests_available(report: dict[str, Any]) -> bool:
    """Whether a persisted report can still drive selective decisions."""
    manifest = report.get("revision_manifest")
    if isinstance(manifest, list) and manifest:
        return True
    plan = report.get("plan")
    edits = plan.get("edits") if isinstance(plan, dict) else None
    return isinstance(edits, list) and bool(edits)


def _require_recall_pair(artifacts: dict[str, Path], validation: dict[str, Any],
                         kinds: tuple[str, str]) -> None:
    if not set(kinds).issubset(artifacts):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    for kind in kinds:
        path = artifacts[kind]
        if not path.is_file() or validation.get(_RECALL_ARTIFACT_HASHES[kind]) != sha256_file(path):
            raise ValueError("ARTIFACT_VERIFICATION_MISMATCH")


def _validate_recall_delivery(report: dict[str, Any], artifacts: dict[str, Path]) -> None:
    """Delivery gate for the recall-first engine (schema 3).

    ``recall_validated_edits``/``recall_validated_unchanged`` publish the final
    pair under the contract names; ``recall_working_edits`` keeps an incomplete
    produced pair strictly under the working names; ``excluded`` and
    ``not_generated`` carry no artifact requirements.  Any other combination
    fails closed.
    """
    validation = report.get("output_validation")
    validation = validation if isinstance(validation, dict) else {}
    kind = validation.get("kind")
    status = report.get("delivery_status")
    checks = validation.get("checks")
    checks = set(checks) if isinstance(checks, (list, tuple)) else set()
    if status in {"excluded", "not_generated"}:
        return
    if kind == "recall_validated_edits":
        if status != "complete" or not _RECALL_EDIT_CHECKS.issubset(checks):
            raise ValueError("MISSING_VERIFIED_ARTIFACTS")
        _require_recall_pair(artifacts, validation, ("final", "redline"))
        return
    if kind == "recall_validated_unchanged":
        if status != "complete" or not _RECALL_UNCHANGED_CHECKS.issubset(checks):
            raise ValueError("MISSING_VERIFIED_ARTIFACTS")
        _require_recall_pair(artifacts, validation, ("final", "redline"))
        return
    if kind == "recall_working_edits":
        unresolved = report.get("unresolved")
        if status != "incomplete" or not isinstance(unresolved, list) or not unresolved:
            raise ValueError("MISSING_VERIFIED_ARTIFACTS")
        if {"final", "redline"} & set(artifacts):
            raise ValueError("MISSING_VERIFIED_ARTIFACTS")
        _require_recall_pair(artifacts, validation, ("working_final", "working_redline"))
        return
    raise ValueError("MISSING_VERIFIED_ARTIFACTS")


def _review_rejected_report_only(report: dict[str, Any], artifacts: dict[str, Path]) -> bool:
    plan = report.get("edit_plan") or {}
    return (_requires_actual_review(report) and report.get("delivery_status") == "incomplete"
            and plan.get("count") == 0 and plan.get("executable") is False
            and plan.get("reason") == "V3_ARTIFACT_REVIEW_REJECTED"
            and not {"final", "redline", "evaluation_final", "evaluation_redline"} & set(artifacts))


def _validate_actual_review(report: dict[str, Any], validation: dict[str, Any]) -> None:
    if not _requires_actual_review(report) or validation["kind"] not in {"evaluated_edits", "validated_edits"}:
        return
    from .v2 import canonical_sha
    records = report.get("actual_content_verifications")
    if not isinstance(records, list) or not records or not isinstance(records[-1], dict):
        raise ValueError("ACTUAL_CONTENT_REVIEW_MISSING")
    review = records[-1]
    if review.get("passed") is not True or review.get("record_sha256") != canonical_sha(
            {key: value for key, value in review.items() if key != "record_sha256"}):
        raise ValueError("ACTUAL_CONTENT_REVIEW_INVALID")
    plan = report.get("edit_plan") or {}
    bindings = {"source_sha256": report.get("source_sha256"), "plan_sha256": plan.get("sha256"),
                "redline_sha256": validation.get("redline_sha256"),
                "final_sha256": validation.get("final_sha256")}
    if any(not digest or review.get(key) != digest for key, digest in bindings.items()):
        raise ValueError("ACTUAL_CONTENT_REVIEW_BINDING_MISMATCH")
    edits = plan.get("edits")
    actions = review.get("actions")
    if (not isinstance(edits, list) or not edits or plan.get("count") != len(edits)
            or not isinstance(actions, list) or not actions
            or "actual_content_verification" not in validation.get("checks", [])):
        raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
    if any(not isinstance(edit, dict) or not edit.get("action_id") for edit in edits):
        raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
    if canonical_sha(edits) != plan.get("sha256"):
        raise ValueError("ACTUAL_CONTENT_REVIEW_PLAN_MISMATCH")
    expected = {edit.get("action_id") for edit in edits}
    seen = set()
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
        identifier = action.get("action_id")
        windows = action.get("windows")
        if (identifier not in expected or identifier in seen or action.get("passed") is not True
                or not isinstance(windows, list) or not windows
                or any(not isinstance(window, dict) or window.get("passed") is not True for window in windows)):
            raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
        locations = {edit.get("location") for edit in edits if edit["action_id"] == identifier}
        covered = {location for window in windows for location in window.get("coverage_locations", [])}
        edited = {location for window in windows for location in window.get("edit_locations", [])}
        if not locations or not locations.issubset(covered & edited):
            raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
        requirements = {requirement.get("id") for edit in edits if edit["action_id"] == identifier
                        for requirement in (edit.get("verification") or {}).get("requirements", [])}
        if not requirements or None in requirements:
            raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
        for window in windows:
            required = {"PRESERVATION"}
            if window.get("edit_locations"):
                required |= requirements | {"COVERAGE"}
            items = window.get("items")
            if not isinstance(items, list) or not items:
                raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
            identifiers = []
            for item in items:
                if (not isinstance(item, dict) or item.get("action_id") != identifier
                        or item.get("result") != "satisfied" or not item.get("evidence_quote")
                        or item.get("evidence_source") not in {"before", "after"}):
                    raise ValueError("ACTUAL_CONTENT_REVIEW_INVALID")
                identifiers.append(item.get("requirement_id"))
            if len(identifiers) != len(set(identifiers)) or set(identifiers) != required:
                raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")
        seen.add(identifier)
    if seen != expected:
        raise ValueError("ACTUAL_CONTENT_REVIEW_COVERAGE_MISSING")


def validate_delivery(report: dict[str, Any], artifacts: dict[str, Path]) -> None:
    if (report.get("verification_status") == "verification_blocked"
            and (report.get("delivery_status") in {"complete", "complete_with_exceptions"}
                 or {"final", "redline"} & set(artifacts))):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    if report.get("execution_mode") == "diagnosis":
        if {"final", "redline", "working_final", "working_redline",
            "evaluation_final", "evaluation_redline"} & set(artifacts):
            raise ValueError("DIAGNOSIS_MUST_NOT_PUBLISH_CONTRACTS")
        return
    if is_recall_report(report):
        if report.get("execution_mode") == "evaluation":
            mapped = {"final": artifacts.get("evaluation_final"),
                      "redline": artifacts.get("evaluation_redline")}
            if report.get("delivery_status") in {"evaluation_modified", "evaluation_modified_with_exceptions",
                                                 "evaluation_unmodified"} and all(mapped.values()):
                probe = dict(report)
                probe["delivery_status"] = "complete"
                probe["execution_mode"] = "delivery"
                _validate_recall_delivery(probe, mapped)  # type: ignore[arg-type]
                return
            raise ValueError("MISSING_VERIFIED_ARTIFACTS")
        _validate_recall_delivery(report, artifacts)
        return
    if report.get("execution_mode") == "evaluation":
        if _review_rejected_report_only(report, artifacts):
            return
        # Evaluation outputs are technically validated but never releasable contracts.
        if report.get("delivery_status") not in {"evaluation_modified", "evaluation_modified_with_exceptions",
                                                 "evaluation_unmodified", "incomplete"}:
            return
        validation = report.get("output_validation")
        if not isinstance(validation, dict):
            raise ValueError("MISSING_VERIFIED_ARTIFACTS")
        required = {
            "evaluated_edits": {"package", "revisions", "final_equivalence", "non_target", "content_verification"},
            "evaluated_zero_edit": {"package", "zero_edit", "byte_identity"},
        }
        checks = validation.get("checks")
        if validation.get("kind") not in required or not isinstance(checks, (list, tuple)) \
                or not required[validation["kind"]].issubset(checks) or validation.get("not_a_final_contract") is not True:
            raise ValueError("MISSING_VERIFIED_ARTIFACTS")
        for kind, hash_key in EVALUATION_ARTIFACT_HASHES.items():
            if kind not in artifacts or not artifacts[kind].is_file() \
                    or validation.get(hash_key) != sha256_file(artifacts[kind]):
                raise ValueError("ARTIFACT_VERIFICATION_MISMATCH")
        _validate_actual_review(report, validation)
        return
    if report.get("delivery_status") not in {"complete", "complete_with_exceptions"}:
        return
    validation = report.get("output_validation")
    if not {"final", "redline"}.issubset(artifacts) or not isinstance(validation, dict):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    required = {"validated_edits": {"package", "revisions", "final_equivalence", "non_target"},
                "validated_unchanged": {"package", "zero_edit", "byte_identity"}}
    checks = validation.get("checks")
    if validation.get("kind") not in required or not isinstance(checks, (list, tuple)):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    present = set(checks)
    if not required[validation["kind"]].issubset(present):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    if validation["kind"] == "validated_edits" and not ({"template_text", "content_verification"} & present):
        raise ValueError("MISSING_VERIFIED_ARTIFACTS")
    for kind in ("final", "redline"):
        if not artifacts[kind].is_file() or validation.get(f"{kind}_sha256") != sha256_file(artifacts[kind]):
            raise ValueError("ARTIFACT_VERIFICATION_MISMATCH")
    _validate_actual_review(report, validation)


class RunStore:
    def __init__(self, root: str | Path, database_url: str | Path | None = None,
                 *, read_only: bool = False):
        self.root = Path(root).resolve()
        self.read_only = read_only
        if not read_only:
            self.root.mkdir(parents=True, exist_ok=True)
        elif not self.root.is_dir():
            raise StoreError("read-only store root does not exist")
        self.objects = self.root / "objects"
        if not read_only:
            self.objects.mkdir(exist_ok=True)
        elif not self.objects.is_dir():
            raise StoreError("read-only store objects directory does not exist")
        self.db_path = self.root / "runs.sqlite3"
        if read_only and not self.db_path.is_file() and not database_url:
            raise StoreError("read-only store database does not exist")
        self.database = Database(database_url) if database_url else Database.from_env(self.db_path)
        if read_only:
            return
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS batches (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, ruleset_version TEXT NOT NULL,
                    ruleset_sha256 TEXT NOT NULL DEFAULT '',
                    mode VARCHAR(32) NOT NULL DEFAULT 'delivery',
                    status TEXT NOT NULL, idempotency_key TEXT, request_hash TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    UNIQUE(owner, idempotency_key)
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batches(id),
                    ordinal INTEGER NOT NULL, filename TEXT NOT NULL,
                    source_sha256 TEXT NOT NULL, source_size INTEGER NOT NULL,
                    input_key TEXT NOT NULL, status TEXT NOT NULL,
                    qualification_status TEXT, delivery_status TEXT NOT NULL DEFAULT 'not_generated',
                    error_code TEXT, report_json TEXT,
                    attempt INTEGER NOT NULL DEFAULT 0, fencing_token INTEGER NOT NULL DEFAULT 0,
                    lease_until REAL, next_attempt_at REAL,
                     created_at REAL NOT NULL, updated_at REAL NOT NULL,
                     selection_epoch INTEGER NOT NULL DEFAULT 0,
                     selection_manifest_hash TEXT NOT NULL DEFAULT '',
                     selection_decision_hash TEXT NOT NULL DEFAULT '',
                     UNIQUE(batch_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    document_id TEXT NOT NULL REFERENCES documents(id), kind TEXT NOT NULL,
                    object_key TEXT NOT NULL, sha256 TEXT NOT NULL, size INTEGER NOT NULL,
                    PRIMARY KEY(document_id, kind)
                );
                CREATE INDEX IF NOT EXISTS documents_work ON documents(status, next_attempt_at, lease_until);
            """)
            for name, definition in {"engine_build": "TEXT NOT NULL DEFAULT ''", "schema_version": "TEXT NOT NULL DEFAULT ''",
                                     "engine_id": "TEXT NOT NULL DEFAULT ''",
                                     "guide_version_id": "TEXT NOT NULL DEFAULT ''",
                                     "guide_rules_sha256": "TEXT NOT NULL DEFAULT ''",
                                     "mode": "VARCHAR(32) NOT NULL DEFAULT 'delivery'"}.items():
                if name not in {row["name"] for row in db.execute("PRAGMA table_info(batches)")}:
                    db.execute(f"ALTER TABLE batches ADD COLUMN {name} {definition}")
            document_columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            if "execution_mode" not in document_columns:
                db.execute("ALTER TABLE documents ADD COLUMN execution_mode TEXT NOT NULL DEFAULT ''")
            for name in ("started_at", "finished_at"):
                if name not in document_columns:
                    db.execute(f"ALTER TABLE documents ADD COLUMN {name} REAL")
            for name, definition in {
                "selection_epoch": "INTEGER NOT NULL DEFAULT 0",
                "selection_manifest_hash": "TEXT NOT NULL DEFAULT ''",
                "selection_decision_hash": "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in document_columns:
                    db.execute(f"ALTER TABLE documents ADD COLUMN {name} {definition}")
            document_columns = {row["name"] for row in db.execute("PRAGMA table_info(documents)")}
            # Historical rows predate the timing columns. Terminal rows get the
            # best available approximation; new rows are stamped by claim/finish.
            db.execute("""UPDATE documents SET started_at=COALESCE(started_at, created_at)
                WHERE status IN ('succeeded','failed') AND started_at IS NULL""")
            db.execute("""UPDATE documents SET finished_at=COALESCE(finished_at, updated_at)
                WHERE status IN ('succeeded','failed') AND finished_at IS NULL""")
            db.execute("""UPDATE documents SET started_at=COALESCE(started_at, updated_at)
                WHERE status IN ('leased','running') AND started_at IS NULL""")
            if "ruleset_sha256" not in {row["name"] for row in db.execute("PRAGMA table_info(batches)")}:
                db.execute("ALTER TABLE batches ADD COLUMN ruleset_sha256 TEXT NOT NULL DEFAULT ''")

    @contextmanager
    def _connect(self):
        with self.database.connect() as db:
            db.execute("PRAGMA foreign_keys=ON")
            if not self.read_only:
                db.execute("PRAGMA journal_mode=WAL")
            yield db

    def object_path(self, key: str) -> Path:
        # Keys are generated here, but validate again before every read.
        path = (self.objects / key).resolve()
        if not path.is_relative_to(self.objects.resolve()):
            raise StoreError("invalid object key")
        return path

    def stage(self, data: bytes) -> tuple[str, str, int]:
        digest = hashlib.sha256(data).hexdigest()
        key = f"inputs/{uuid.uuid4().hex}.docx"
        path = self.object_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return key, digest, len(data)

    def create_batch(self, *, owner: str, ruleset_version: str,
                     uploads: list[tuple[str, bytes]], idempotency_key: str | None = None,
                     ruleset_sha256: str = "") -> dict[str, Any]:
        if not uploads:
            raise ValueError("at least one DOCX is required")
        if not owner or not ruleset_version:
            raise ValueError("owner and ruleset version are required")
        fingerprints = [(name, hashlib.sha256(data).hexdigest()) for name, data in uploads]
        build = engine_build()
        request_hash = hashlib.sha256(json.dumps([ruleset_version, ruleset_sha256, build, SCHEMA_VERSION, fingerprints], ensure_ascii=False).encode()).hexdigest()
        with self._connect() as db:
            if idempotency_key:
                existing = db.execute("SELECT id, request_hash FROM batches WHERE owner=? AND idempotency_key=?",
                                      (owner, idempotency_key)).fetchone()
                if existing:
                    if existing["request_hash"] != request_hash:
                        raise Conflict("idempotency key was used for different input")
                    return self.get_batch(owner, existing["id"])
        staged: list[tuple[str, str, str, int]] = []
        try:
            for name, data in uploads:
                key, digest, size = self.stage(data)
                staged.append((name, key, digest, size))
            batch_id = uuid.uuid4().hex
            now = time.time()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("""INSERT INTO batches
                    (id,owner,ruleset_version,ruleset_sha256,status,idempotency_key,request_hash,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (batch_id, owner, ruleset_version, ruleset_sha256, "queued", idempotency_key, request_hash, now, now))
                db.execute("UPDATE batches SET engine_build=?,schema_version=? WHERE id=?", (build, SCHEMA_VERSION, batch_id))
                for ordinal, (name, key, digest, size) in enumerate(staged):
                    db.execute("""INSERT INTO documents
                        (id,batch_id,ordinal,filename,source_sha256,source_size,input_key,status,created_at,updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (uuid.uuid4().hex, batch_id, ordinal, name, digest, size, key, "queued", now, now))
            return self.get_batch(owner, batch_id)
        except Exception:
            for _, key, _, _ in staged:
                self.object_path(key).unlink(missing_ok=True)
            # A simultaneous request may have won the idempotency race.
            if idempotency_key:
                with self._connect() as db:
                    existing = db.execute("SELECT id, request_hash FROM batches WHERE owner=? AND idempotency_key=?",
                                          (owner, idempotency_key)).fetchone()
                    if existing and existing["request_hash"] == request_hash:
                        return self.get_batch(owner, existing["id"])
            raise

    def list_batches(self, owner: str) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM batches WHERE owner=? ORDER BY created_at DESC", (owner,)).fetchall()
            return [self._batch_dict(db, row) for row in rows]

    def get_batch(self, owner: str, batch_id: str) -> dict[str, Any]:
        with self._connect() as db:
            row = db.execute("SELECT * FROM batches WHERE id=? AND owner=?", (batch_id, owner)).fetchone()
            if row is None:
                raise NotFound("batch not found")
            return self._batch_dict(db, row)

    def _batch_dict(self, db: Connection, row) -> dict[str, Any]:
        docs = db.execute("SELECT * FROM documents WHERE batch_id=? ORDER BY ordinal", (row["id"],)).fetchall()
        result = {key: row[key] for key in ("id", "ruleset_version", "ruleset_sha256", "status", "created_at", "updated_at")}
        result["documents"] = [self._document_dict(db, doc) for doc in docs]
        result["counts"] = {
            "total": len(docs), "succeeded": sum(doc["status"] == "succeeded" for doc in docs),
            "failed": sum(doc["status"] == "failed" for doc in docs),
            "pending": sum(doc["status"] not in ("succeeded", "failed") for doc in docs),
        }
        return result

    def _document_dict(self, db: Connection, row) -> dict[str, Any]:
        artifacts = db.execute("SELECT kind FROM artifacts WHERE document_id=?", (row["id"],)).fetchall()
        try:
            parse_report_json(row["report_json"])
        except ReportJsonError as exc:
            report_error = exc.code
        else:
            report_error = None
        return {key: row[key] for key in ("id", "batch_id", "filename", "source_sha256", "status",
                                          "qualification_status", "delivery_status", "error_code", "attempt",
                                          "execution_mode")} | {
            "selection_epoch": row["selection_epoch"] if "selection_epoch" in row.keys() else 0,
            "selection_manifest_hash": row["selection_manifest_hash"] if "selection_manifest_hash" in row.keys() else "",
            "selection_decision_hash": row["selection_decision_hash"] if "selection_decision_hash" in row.keys() else "",
            "artifacts": [item["kind"] for item in artifacts],
            "report_url": f"/api/batches/{row['batch_id']}/documents/{row['id']}/report",
            "download_urls": {item["kind"]: f"/api/batches/{row['batch_id']}/documents/{row['id']}/download/{item['kind']}" for item in artifacts},
            "report_error": report_error,
        }

    def get_document(self, owner: str, batch_id: str, document_id: str) -> dict[str, Any]:
        self.get_batch(owner, batch_id)
        with self._connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=? AND batch_id=?", (document_id, batch_id)).fetchone()
            if row is None:
                raise NotFound("document not found")
            return self._document_dict(db, row)

    def get_report(self, owner: str, batch_id: str, document_id: str) -> dict[str, Any]:
        self.get_document(owner, batch_id, document_id)
        with self._connect() as db:
            row = db.execute("SELECT report_json FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row or not row["report_json"]:
            raise NotFound("report not available")
        return parse_report_json(row["report_json"]) or {}

    def save_selected_artifact(self, owner: str, batch_id: str, document_id: str,
                               kind: str, source: Path) -> tuple[str, int]:
        """Publish a user-selected DOCX produced from the document's redline.

        ``selected_final`` is a *user* artifact: it is derived from an existing
        revision artifact and is therefore not part of the engine delivery
        validation. It is still integrity-checked and served through the normal
        download path.
        """
        document = self.get_document(owner, batch_id, document_id)
        if kind not in SELECTED_KINDS:
            raise StoreError("invalid artifact")
        if document["execution_mode"] == "evaluation":
            raise Conflict("SELECTED_ARTIFACT_EVALUATION_UNSUPPORTED")
        source = Path(source)
        if not source.is_file():
            raise StoreError("invalid artifact")
        digest = sha256_file(source)
        size = source.stat().st_size
        key = f"selected/{document_id}/{uuid.uuid4().hex}/{kind}{source.suffix}"
        target = self.object_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with source.open("rb") as incoming, target.open("xb") as output:
            for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if sha256_file(target) != digest:
            raise Conflict("artifact copy verification failed")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?)",
                       (document_id, kind, key, digest, size))
        return key, size

    def remove_selected_artifact(self, owner: str, batch_id: str, document_id: str,
                                 kind: str) -> None:
        """Drop a derived user artifact that is no longer trustworthy.

        Used when a freshly derived redline cannot be produced or verified: the
        previous one no longer matches the newest selection, so serving it would
        misrepresent which edits the user accepted.
        """
        self.get_document(owner, batch_id, document_id)
        if kind not in SELECTED_KINDS or kind == "selected_final":
            raise StoreError("invalid artifact")
        with self._connect() as db:
            row = db.execute("SELECT object_key FROM artifacts WHERE document_id=? AND kind=?",
                             (document_id, kind)).fetchone()
            if row is None:
                return
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM artifacts WHERE document_id=? AND kind=?", (document_id, kind))
        self.object_path(row["object_key"]).unlink(missing_ok=True)

    def publish_selected_artifacts(self, owner: str, batch_id: str, document_id: str,
                                   *, final: Path, redline: Path | None,
                                   manifest_hash: str, decision_hash: str,
                                   expected_epoch: int | None = None) -> dict[str, Any]:
        """Publish one final/redline pair and advance the selection epoch atomically.

        Files are copied before the database pointer changes.  The locked update
        then replaces both pointers together, so a request can never expose a
        new final with an old selected redline (or the reverse).
        """
        self.get_document(owner, batch_id, document_id)
        paths = {"selected_final": Path(final)}
        if redline is not None:
            paths["selected_redline"] = Path(redline)
        if any(not path.is_file() for path in paths.values()):
            raise StoreError("invalid artifact")
        copied: dict[str, tuple[str, str, int]] = {}
        committed = False
        try:
            for kind, source in paths.items():
                digest = sha256_file(source)
                key = f"selected/{document_id}/{uuid.uuid4().hex}/{kind}{source.suffix}"
                target = self.object_path(key)
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open("rb") as incoming, target.open("xb") as output:
                    for chunk in iter(lambda: incoming.read(1024 * 1024), b""):
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if sha256_file(target) != digest:
                    raise Conflict("artifact copy verification failed")
                copied[kind] = (key, digest, source.stat().st_size)
            now = time.time()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT * FROM documents WHERE id=? AND batch_id=?",
                                 (document_id, batch_id)).fetchone()
                if row is None:
                    raise NotFound("document not found")
                current_epoch = int(row["selection_epoch"] or 0)
                if expected_epoch is not None and current_epoch != expected_epoch:
                    raise Conflict("SELECTION_EPOCH_CONFLICT")
                new_epoch = current_epoch + 1
                old_rows = db.execute("SELECT kind,object_key FROM artifacts WHERE document_id=? AND kind IN ('selected_final','selected_redline')",
                                      (document_id,)).fetchall()
                for kind, (key, digest, size) in copied.items():
                    db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?)",
                               (document_id, kind, key, digest, size))
                if "selected_redline" not in copied:
                    db.execute("DELETE FROM artifacts WHERE document_id=? AND kind='selected_redline'",
                               (document_id,))
                changed = db.execute("""UPDATE documents SET selection_epoch=?,selection_manifest_hash=?,
                    selection_decision_hash=?,updated_at=? WHERE id=? AND selection_epoch=?""",
                           (new_epoch, manifest_hash, decision_hash, now, document_id, current_epoch)).rowcount
                if changed != 1:
                    raise Conflict("SELECTION_EPOCH_CONFLICT")
            committed = True
            for old in old_rows:
                if old["kind"] not in copied or old["object_key"] != copied[old["kind"]][0]:
                    try:
                        self.object_path(old["object_key"]).unlink(missing_ok=True)
                    except OSError:
                        # The DB pointer is already the authoritative state. An
                        # orphaned old object is safe to reap later and must not
                        # turn a successful selection into a 500 response.
                        pass
            return {"epoch": new_epoch,
                    "selected_final_sha256": copied["selected_final"][1],
                    "selected_redline_sha256": copied.get("selected_redline", (None, None, None))[1]}
        except Exception:
            if not committed:
                for key, _, _ in copied.values():
                    self.object_path(key).unlink(missing_ok=True)
            raise

    def _verify_selected_source(self, document_id: str, kind: str) -> None:
        """A selected artifact is valid only while its source redline is intact.

        The redline is the engine revision artifact the user made decisions on.
        If that artifact is gone or changed, the selection can no longer be
        trusted and must not be served.
        """
        with self._connect() as db:
            document = db.execute("SELECT report_json,execution_mode FROM documents WHERE id=?",
                                  (document_id,)).fetchone()
            rows = db.execute("SELECT kind,object_key,sha256,size FROM artifacts WHERE document_id=?",
                              (document_id,)).fetchall()
        if document is None or not document["report_json"]:
            raise Conflict("SELECTED_SOURCE_UNAVAILABLE")
        try:
            report = parse_report_json(document["report_json"])
        except ReportJsonError as exc:
            raise Conflict(exc.code) from exc
        if report is None:
            raise Conflict("SELECTED_SOURCE_UNAVAILABLE")
        candidates = ("redline", "working_redline", "evaluation_redline")
        source = next((item for name in candidates for item in rows if item["kind"] == name), None)
        if source is None:
            raise Conflict("SELECTED_SOURCE_UNAVAILABLE")
        path = self.object_path(source["object_key"])
        if not path.is_file() or path.stat().st_size != source["size"] \
                or sha256_file(path) != source["sha256"]:
            raise Conflict("SELECTED_SOURCE_INTEGRITY_FAILED")
        if not _manifests_available(report):
            raise Conflict("SELECTED_SOURCE_UNAVAILABLE")

    def get_artifact(self, owner: str, batch_id: str, document_id: str, kind: str) -> tuple[Path, str]:
        self.get_document(owner, batch_id, document_id)
        with self._connect() as db:
            row = db.execute("SELECT * FROM artifacts WHERE document_id=? AND kind=?", (document_id, kind)).fetchone()
            if kind in {"evaluation_final", "evaluation_redline"}:
                document = db.execute("SELECT execution_mode FROM documents WHERE id=?", (document_id,)).fetchone()
                # Evaluation downloads are bound to the persisted execution mode,
                # not to a filename or UI label.
                if row is None or document is None or document["execution_mode"] != "evaluation":
                    raise NotFound("artifact not available")
        if row is None:
            raise NotFound("artifact not available")
        path = self.object_path(row["object_key"])
        if not path.is_file() or path.stat().st_size != row["size"] or sha256_file(path) != row["sha256"]:
            raise Conflict("artifact integrity check failed")
        if kind == "report_json":
            try:
                parse_report_json(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ReportJsonError) as exc:
                raise ReportJsonError() from exc
        if kind in SELECTED_KINDS:
            # User-selected artifacts are bound to the redline they were derived
            # from; re-check that the source revision artifact is still intact.
            self._verify_selected_source(document_id, kind)
            return path, row["sha256"]
        if kind in {"final", "redline", "evaluation_final", "evaluation_redline",
                    "working_final", "working_redline"}:
            with self._connect() as db:
                document = db.execute("SELECT execution_mode,report_json,source_sha256 FROM documents WHERE id=?",
                                      (document_id,)).fetchone()
                pair_rows = db.execute("SELECT * FROM artifacts WHERE document_id=?", (document_id,)).fetchall()
            try:
                report = parse_report_json(document["report_json"]) if document and document["report_json"] else {}
                if is_recall_report(report):
                    # A recall download is bound to the persisted delivery state and
                    # re-validated against the actual stored pair.
                    status = report.get("delivery_status")
                    if kind.startswith("evaluation_"):
                        # Evaluation bytes are the validated final/redline pair under
                        # non-contract names. Validate the same hashes and pair
                        # contract without ever treating them as formal delivery.
                        probe = dict(report)
                        probe["delivery_status"] = "complete"
                        probe["execution_mode"] = "delivery"
                        expected = {"final", "redline"}
                        pairs = {item["kind"]: self.object_path(item["object_key"]) for item in pair_rows
                                 if item["kind"] in {"evaluation_final", "evaluation_redline"}}
                        pairs = {("final" if key.endswith("final") else "redline"): path
                                 for key, path in pairs.items()}
                        validate_delivery(probe, pairs)
                    else:
                        if kind in {"final", "redline"} and status != "complete":
                            raise ValueError("RECALL_DELIVERY_NOT_COMPLETE")
                        if kind in {"working_final", "working_redline"} and status != "incomplete":
                            raise ValueError("RECALL_DELIVERY_NOT_INCOMPLETE")
                        expected = ({"working_final", "working_redline"} if kind.startswith("working_")
                                    else {"final", "redline"})
                        pairs = {item["kind"]: self.object_path(item["object_key"]) for item in pair_rows
                                 if item["kind"] in expected}
                        validate_delivery(report, pairs)
                elif _requires_actual_review(report):
                    if report.get("source_sha256") != document["source_sha256"]:
                        raise ValueError("ACTUAL_CONTENT_REVIEW_SOURCE_MISMATCH")
                    if report.get("execution_mode") != document["execution_mode"]:
                        raise ValueError("ACTUAL_CONTENT_REVIEW_BINDING_MISMATCH")
                    if not kind.startswith("evaluation_") and report.get("delivery_status") not in {"complete", "complete_with_exceptions"}:
                        raise ValueError("ACTUAL_CONTENT_REVIEW_BINDING_MISMATCH")
                    expected = {"evaluation_final", "evaluation_redline"} if kind.startswith("evaluation_") else {"final", "redline"}
                    pairs = {item["kind"]: self.object_path(item["object_key"]) for item in pair_rows
                             if item["kind"] in expected}
                    validate_delivery(report, pairs)
            except (ValueError, TypeError) as exc:
                raise Conflict(str(exc)) from exc
        return path, row["sha256"]

    def claim(self, *, lease_seconds: int = 300, max_attempts: int = 3) -> dict[str, Any] | None:
        now = time.time()
        # The cleanup candidates are only a hint.  Read them before the write
        # transaction so another worker can finish or reclaim one; every
        # cleanup UPDATE below repeats the full fencing predicate.
        exhausted_sql = """SELECT id,batch_id,source_sha256,fencing_token,attempt FROM documents
            WHERE status IN ('leased','running') AND lease_until<=? AND attempt>=?"""
        with self._connect() as db:
            exhausted = db.execute(exhausted_sql, (now, max_attempts)).fetchall()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for expired in exhausted:
                report = {"document_id": expired["id"], "source_sha256": expired["source_sha256"],
                          "qualification_status": "failed", "delivery_status": "not_generated",
                          "error_code": "WORKER_ATTEMPTS_EXHAUSTED",
                          "errors": [{"code": "WORKER_ATTEMPTS_EXHAUSTED", "stage": "worker"}]}
                changed = db.execute("""UPDATE documents SET status='failed',qualification_status='failed',
                    delivery_status='not_generated',error_code='WORKER_ATTEMPTS_EXHAUSTED',
                    report_json=?,lease_until=NULL,started_at=COALESCE(started_at,created_at),
                    finished_at=?,updated_at=? WHERE id=? AND fencing_token=?
                    AND status IN ('leased','running') AND lease_until<=? AND attempt>=?""",
                    (json.dumps(report), now, now, expired["id"], expired["fencing_token"],
                     now, max_attempts)).rowcount
                if changed == 1:
                    self._refresh_batch(db, expired["batch_id"], now)
            active_scope = "active.batch_id=d.batch_id"
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_batches'").fetchone():
                active_scope = """COALESCE((SELECT task_id FROM task_batches WHERE batch_id=active.batch_id),active.batch_id)
                    = COALESCE((SELECT task_id FROM task_batches WHERE batch_id=d.batch_id),d.batch_id)"""
            candidate = f"""SELECT d.*, b.ruleset_version, b.ruleset_sha256, b.engine_build, b.schema_version,
                b.engine_id, b.guide_version_id, b.guide_rules_sha256, b.mode, b.owner
                FROM documents d JOIN batches b ON b.id=d.batch_id
                WHERE b.status IN ('queued','running') AND d.attempt < ? AND
                (d.status='queued' OR (d.status='retry_wait' AND d.next_attempt_at<=?) OR
                 (d.status IN ('leased','running') AND d.lease_until<=?))
                ORDER BY (SELECT COUNT(*) FROM documents active
                    WHERE {active_scope} AND active.status IN ('leased','running')
                    AND active.lease_until>?) ASC, b.updated_at,d.created_at,d.ordinal LIMIT 1"""
            if self.database.dialect == "mysql":
                # A plain START TRANSACTION does not lock candidates; without the
                # row lock two workers could claim the same document.
                candidate += " FOR UPDATE"
            row = db.execute(candidate, (max_attempts, now, now, now)).fetchone()
            if not row:
                return None
            token = row["fencing_token"] + 1
            attempt = row["attempt"] + 1
            changed = db.execute("""UPDATE documents SET status='leased', attempt=?, fencing_token=?, lease_until=?,
                next_attempt_at=NULL, started_at=COALESCE(started_at,?), updated_at=?
                WHERE id=? AND fencing_token=? AND attempt=?
                AND (status='queued' OR (status='retry_wait' AND next_attempt_at<=?)
                     OR (status IN ('leased','running') AND lease_until<=?))""",
                (attempt, token, now + lease_seconds, now, now, row["id"],
                 row["fencing_token"], row["attempt"], now, now)).rowcount
            if changed != 1:
                raise Conflict("claim lost")
            db.execute("UPDATE batches SET status='running',updated_at=? WHERE id=?", (now, row["batch_id"]))
            return dict(row) | {"attempt": attempt, "fencing_token": token}

    def heartbeat(self, document_id: str, token: int, *, lease_seconds: int = 300) -> None:
        with self._connect() as db:
            changed = db.execute("""UPDATE documents SET status='running',lease_until=?,updated_at=?
                WHERE id=? AND fencing_token=? AND status IN ('leased','running') AND lease_until>?""",
                (time.time() + lease_seconds, time.time(), document_id, token, time.time())).rowcount
            if not changed:
                raise Conflict("stale worker lease")

    def finish(self, document_id: str, token: int, *, report: dict[str, Any],
               artifacts: dict[str, Path], failed: bool = False, error_code: str | None = None) -> None:
        # Verify all outputs before publication. Only report files are allowed for incomplete results.
        try:
            validate_delivery(report, artifacts)
        except ValueError as exc:
            raise Conflict(str(exc)) from exc
        delivery = report.get("delivery_status", "not_generated")
        mode = report.get("execution_mode", "delivery")
        allowed_kinds = {"final", "redline", "working_final", "working_redline", "report_json", "report_md"}
        if mode == "evaluation":
            allowed_kinds = {"evaluation_final", "evaluation_redline", "report_json", "report_md"}
            if delivery in {"complete", "complete_with_exceptions"} or {"final", "redline"} & set(artifacts):
                raise Conflict("evaluation cannot publish final delivery")
            if delivery in {"evaluation_modified", "evaluation_modified_with_exceptions",
                            "evaluation_unmodified", "incomplete"} \
                    and not {"evaluation_redline", "evaluation_final"}.issubset(artifacts) \
                    and not _review_rejected_report_only(report, artifacts):
                raise Conflict("evaluation result requires both evaluated contracts")
        else:
            if {"working_final", "working_redline"} & set(artifacts) and not is_recall_report(report):
                # Working files are a recall-first delivery state, never a legacy result.
                raise Conflict("working artifacts require a recall report")
            if delivery in {"complete", "complete_with_exceptions"} and not {"final", "redline"}.issubset(artifacts):
                raise Conflict("complete result requires both verified contracts")
            if delivery not in {"complete", "complete_with_exceptions"} and ("final" in artifacts or "redline" in artifacts):
                raise Conflict("incomplete result cannot publish contract downloads")
        verified = {}
        for kind, path in artifacts.items():
            if kind not in allowed_kinds or not path.is_file():
                raise StoreError("invalid artifact")
            verified[kind] = (sha256_file(path), path.stat().st_size)
        now = time.time()
        published: list[Path] = []
        artifact_keys: dict[str, str] = {}
        try:
            # This read is advisory.  A newer worker may take over after it;
            # the final UPDATE is the fencing authority.
            with self._connect() as db:
                row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
            if not row or row["fencing_token"] != token or row["status"] not in ("leased", "running"):
                raise Conflict("stale worker lease")
            if row["lease_until"] is None or row["lease_until"] <= now:
                raise Conflict("expired worker lease")
            if _requires_actual_review(report) and report.get("source_sha256") != row["source_sha256"]:
                raise Conflict("ACTUAL_CONTENT_REVIEW_SOURCE_MISMATCH")
            for kind, path in artifacts.items():
                # Attempt objects are immutable. Database pointer is published only while token is current.
                key = f"results/{document_id}/{token}/{uuid.uuid4().hex}/{kind}{path.suffix}"
                target = self.object_path(key)
                target.parent.mkdir(parents=True, exist_ok=True)
                with path.open("rb") as source, target.open("xb") as output:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                digest, size = verified[kind]
                if sha256_file(target) != digest:
                    raise Conflict("artifact copy verification failed")
                published.append(target)
                artifact_keys[kind] = key
            transition_now = time.time()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                changed = db.execute("""UPDATE documents SET status=?,qualification_status=?,delivery_status=?,error_code=?,
                    report_json=?,execution_mode=?,lease_until=NULL,finished_at=?,updated_at=?
                    WHERE id=? AND fencing_token=? AND status IN ('leased','running')
                    AND lease_until>? AND attempt=?""",
                    ("failed" if failed else "succeeded", report.get("qualification_status"), delivery,
                     error_code, json.dumps(report, ensure_ascii=False), str(mode), transition_now, transition_now,
                     document_id, token, transition_now, row["attempt"])).rowcount
                if changed != 1:
                    raise Conflict("stale worker lease")
                for kind, key in artifact_keys.items():
                    digest, size = verified[kind]
                    db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?)",
                               (document_id, kind, key, digest, size))
                self._refresh_batch(db, row["batch_id"], transition_now)
        except Exception:
            for target in published:
                target.unlink(missing_ok=True)
            raise

    def retry(self, document_id: str, token: int, *, error_code: str, max_attempts: int = 3,
              base_delay_seconds: int = 2, report: dict[str, Any] | None = None) -> None:
        now = time.time()
        # Validate outside the write transaction so a newer worker can commit
        # a takeover between this read and the fenced UPDATE.
        with self._connect() as db:
            row = db.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if not row or row["fencing_token"] != token or row["status"] not in ("leased", "running"):
            raise Conflict("stale worker lease")
        if row["lease_until"] is None or row["lease_until"] <= now:
            raise Conflict("expired worker lease")
        terminal = row["attempt"] >= max_attempts
        pause_required = error_code in {"MODEL_CIRCUIT_OPEN", "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED", "MODEL_COST_BUDGET_EXCEEDED", "MODEL_CALL_BUDGET_EXCEEDED", "MODEL_LEDGER_UNAVAILABLE", "MODEL_CHECKPOINT_UNAVAILABLE", "MODEL_REPLAY_MISS", "MODEL_CASSETTE_UNAVAILABLE"}
        delay = min(base_delay_seconds * (2 ** max(row["attempt"] - 1, 0)) * random.uniform(0.8, 1.2), 300)
        report_json = json.dumps(report, ensure_ascii=False) if isinstance(report, dict) else None
        if terminal:
            terminal_report = dict(report) if isinstance(report, dict) else {}
            terminal_report.update({"document_id": document_id, "source_sha256": row["source_sha256"],
                      "qualification_status": "failed", "delivery_status": "not_generated",
                      "error_code": error_code})
            terminal_report.setdefault("errors", []).append({"code": error_code, "stage": "worker"})
            report_json = json.dumps(terminal_report, ensure_ascii=False)
        transition_now = time.time()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute("""UPDATE documents SET status=?,error_code=?,next_attempt_at=?,lease_until=NULL,
                finished_at=CASE WHEN ? THEN ? ELSE finished_at END,
                report_json=CASE WHEN ? OR ? THEN ? ELSE report_json END,
                qualification_status=CASE WHEN ? THEN 'failed' ELSE qualification_status END,
                delivery_status=CASE WHEN ? THEN 'not_generated' ELSE delivery_status END,
                updated_at=? WHERE id=? AND fencing_token=? AND status IN ('leased','running')
                AND lease_until>? AND attempt=?""",
                            ("failed" if terminal else "retry_wait", error_code,
                            None if terminal else transition_now + delay, 1 if terminal else 0, transition_now,
                            1 if terminal else 0, 1 if report_json is not None else 0, report_json,
                            1 if terminal else 0,
                            1 if terminal else 0, transition_now, document_id, token, transition_now,
                            row["attempt"])).rowcount
            if changed != 1:
                raise Conflict("stale worker lease")
            self._refresh_batch(db, row["batch_id"], transition_now)
            if not terminal and (pause_required or (row["attempt"] >= 2 and error_code in {"MODEL_NETWORK_ERROR", "MODEL_RETRY_EXHAUSTED"})):
                db.execute("UPDATE batches SET status='paused',updated_at=? WHERE id=?", (transition_now, row["batch_id"]))
            if pause_required or (not terminal and row["attempt"] >= 2 and error_code in {"MODEL_NETWORK_ERROR", "MODEL_RETRY_EXHAUSTED"}):
                # The task layer is optional for legacy RunStore callers. A
                # global budget stop pauses all associated execution segments.
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_batches'").fetchone():
                    task = db.execute("SELECT task_id FROM task_batches WHERE batch_id=?", (row["batch_id"],)).fetchone()
                    if task:
                        db.execute("UPDATE tasks SET paused=1,pause_reason=?,updated_at=? WHERE id=?", (error_code, transition_now, task["task_id"]))
                        db.execute("UPDATE batches SET status='paused',updated_at=? WHERE id IN (SELECT batch_id FROM task_batches WHERE task_id=?) AND status!='completed'", (transition_now, task["task_id"]))

    def pause(self, owner: str, batch_id: str) -> dict[str, Any]:
        self.get_batch(owner, batch_id)
        if task_id := self._parent_task(batch_id):
            from .tasks import TaskStore
            TaskStore(self).control(owner, task_id, "pause")
            return self.get_batch(owner, batch_id)
        with self._connect() as db:
            db.execute("UPDATE batches SET status='paused',updated_at=? WHERE id=? AND status!='completed'",
                       (time.time(), batch_id))
        return self.get_batch(owner, batch_id)

    def resume(self, owner: str, batch_id: str) -> dict[str, Any]:
        self.get_batch(owner, batch_id)
        if task_id := self._parent_task(batch_id):
            from .tasks import TaskStore
            TaskStore(self).control(owner, task_id, "resume")
            return self.get_batch(owner, batch_id)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT COUNT(*) AS pending FROM documents WHERE batch_id=? AND status NOT IN ('succeeded','failed')", (batch_id,)).fetchone()
            db.execute("UPDATE batches SET status=?,updated_at=? WHERE id=?",
                       ("queued" if row["pending"] else "completed", time.time(), batch_id))
        return self.get_batch(owner, batch_id)

    def _parent_task(self, batch_id: str) -> str | None:
        with self._connect() as db:
            if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='task_batches'").fetchone():
                return None
            row = db.execute("SELECT task_id FROM task_batches WHERE batch_id=?", (batch_id,)).fetchone()
            return row["task_id"] if row else None

    @staticmethod
    def _refresh_batch(db: Connection, batch_id: str, now: float) -> None:
        row = db.execute("SELECT COUNT(*) AS pending FROM documents WHERE batch_id=? AND status NOT IN ('succeeded','failed')", (batch_id,)).fetchone()
        current = db.execute("SELECT status FROM batches WHERE id=?", (batch_id,)).fetchone()["status"]
        state = "completed" if row["pending"] == 0 else ("paused" if current == "paused" else "running")
        db.execute("UPDATE batches SET status=?,updated_at=? WHERE id=?", (state, now, batch_id))
