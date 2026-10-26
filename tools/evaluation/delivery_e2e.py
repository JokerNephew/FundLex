"""Delivery E2E workflow and assertion layer.

The command follows the ordinary workbench delivery path in an isolated local
application: password login, guide binding, DOCX submission, Worker processing,
report/Claim Replay, final/redline downloads, Review accept/reject, selected
artifacts, authorization checks, and cleanup.

The default processor is a deterministic fixture.  It writes real DOCX files
through the production writer and publishes them through the production store,
but it makes zero model calls.  A real model is available only with both
``--model-mode real`` and ``--allow-real-model``; the latter is intentionally a
separate acknowledgement so a model-backed run cannot happen by accident.

Failure evidence is kept under ``/tmp/opencode`` (or ``--evidence-dir``).  The
temporary application database and test accounts are removed in either outcome.
This runner is a delivery contract check, not a business-quality evaluation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import string
import tempfile
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


REPO = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO / "funds_word" / "广发品质回报混合型证券投资基金基金合同_20230708.docx"
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _random_name(prefix: str) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return prefix + "-" + "".join(secrets.choice(alphabet) for _ in range(10))


@contextmanager
def _environment(values: dict[str, str]) -> Iterator[None]:
    old = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _docx_check(path: Path) -> dict[str, Any]:
    """Reopen a downloaded package and expose revision facts for evidence."""
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
        names = set(archive.namelist())
    return {
        "valid_zip": True,
        "has_document_xml": "word/document.xml" in names,
        "sha256": _sha256(path),
        "insertions": xml.count(b"<w:ins"),
        "deletions": xml.count(b"<w:del"),
        "has_revision_markup": b"<w:ins" in xml or b"<w:del" in xml,
    }


def _fixture_processor(source: Path, output: Path, _ruleset: str) -> dict[str, Any]:
    """Produce a valid, source-bound delivery result without a model call."""
    from fundlex.docx import inspect_docx, validate_edit_plan, generate_artifacts

    inspected = inspect_docx(source, full=True)
    candidates = [paragraph for paragraph in inspected.paragraphs
                  if paragraph.editable and len(paragraph.text) >= 4]
    if len(candidates) < 2:
        raise RuntimeError("DELIVERY_E2E_FIXTURE_NEEDS_TWO_EDITABLE_PARAGRAPHS")

    edits: list[dict[str, Any]] = []
    for index, paragraph in enumerate(candidates[:2], start=1):
        old = paragraph.text[:2]
        edits.append({
            "edit_id": f"delivery-e2e-{index}",
            "action_id": f"DELIVERY-E2E-{index}",
            "rule_id": f"DELIVERY-E2E-{index}",
            "location": paragraph.location,
            "zone": paragraph.zone,
            "start": 0,
            "end": 2,
            "expected_old_text": old,
            "expected_old_hash": hashlib.sha256(old.encode("utf-8")).hexdigest(),
            "replacement": "交付验",
            "template_id": f"delivery-e2e-{index}",
            "verified": True,
            "fingerprint": paragraph.fingerprint,
            "mapping_version": paragraph.mapping_version,
            "source_sha256": inspected.source_sha256,
            "content_source": "template",
            "verification": {"requirements": [{"id": "CONTENT"}]},
        })
    templates = {edit["template_id"]: edit["replacement"] for edit in edits}
    plan = validate_edit_plan(source, edits, templates)
    redline = output / "redline.docx"
    final = output / "final.docx"
    validation = generate_artifacts(source, plan, redline, final)
    manifest = [dict(item) for item in validation.manifest]
    # The fixture's Claim Replay record is deliberately explicit.  The actual
    # production pipeline has a richer record, but the delivery gate only needs
    # to prove that the report and the published pair carry the same claim.
    claim_replay = {
        "status": "passed",
        "passed": True,
        "mode": "delivery-e2e-fixture",
        "source_sha256": inspected.source_sha256,
        "final_sha256": validation.final_sha256,
        "redline_sha256": validation.redline_sha256,
        "checked_operations": [edit["edit_id"] for edit in edits],
    }
    report = {
        "schema_version": "3",
        "engine_id": "recall_first",
        "engine_version": "0.2.0",
        "execution_mode": "delivery",
        "fixture_notice": "delivery-e2e deterministic processor; no model call",
        "model": {"calls": 0, "configured_model": "delivery-e2e-fixture-no-model"},
        "source_sha256": inspected.source_sha256,
        "qualification_status": "eligible",
        "delivery_status": "complete",
        "plan": {"count": len(edits), "edits": edits, "sha256": plan.plan_sha256},
        "revision_manifest": manifest,
        "artifact_claim_replay": claim_replay,
        "claim_replay": claim_replay,
        "output_validation": {
            "kind": "recall_validated_edits",
            "checks": ["package", "revisions", "final_equivalence", "non_target",
                       "content_verification", "actual_content_verification"],
            "final_sha256": validation.final_sha256,
            "redline_sha256": validation.redline_sha256,
        },
        "artifacts": {"final": "final.docx", "redline": "redline.docx"},
        "actions": [{"action_id": edit["action_id"], "status": "verified",
                      "targets": [{"status": "modified", "location": edit["location"]}]}
                     for edit in edits],
        "unresolved": [],
        "errors": [],
        "error_code": None,
    }
    return report


class DeliveryE2EAssertions:
    """Assertions shared by the CLI and focused tests.

    Methods intentionally assert the user-visible contract at each boundary so
    a failure leaves a precise evidence record instead of only a terminal task
    status.
    """

    def __init__(self, client, evidence_dir: Path, source: Path):
        self.client = client
        self.evidence_dir = evidence_dir
        self.source = source
        self.result: dict[str, Any] = {"source": source.name, "source_sha256": _sha256(source)}

    def _save_json(self, name: str, value: Any) -> None:
        (self.evidence_dir / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def assert_workbench_login(self, username: str, password: str) -> tuple[dict[str, str], dict[str, str]]:
        home = self.client.get("/")
        assert home.status_code == 200 and "合同修订工作台" in home.text, home.text[:300]
        registration = self.client.post("/api/auth/register", json={
            "username": username, "password": password, "display_name": "delivery-e2e"
        })
        assert registration.status_code == 201, registration.text
        registered = registration.json()
        assert registered.get("token") and registered.get("user", {}).get("id")
        self.client.post("/api/auth/logout", headers={"Authorization": f"Bearer {registered['token']}"})
        login = self.client.post("/api/auth/login", json={"username": username, "password": password})
        assert login.status_code == 200, login.text
        payload = login.json()
        headers = {"Authorization": f"Bearer {payload['token']}"}
        me = self.client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200 and me.json()["id"] == payload["user"]["id"]
        self.result["login"] = {"status": login.status_code, "user_id": payload["user"]["id"]}
        return headers, payload["user"]

    def assert_guide_and_entry(self, headers: dict[str, str]) -> dict[str, Any]:
        capabilities = self.client.get("/api/capabilities", headers=headers)
        assert capabilities.status_code == 200, capabilities.text
        caps = capabilities.json()
        guide = caps.get("engine", {}).get("guide") or {}
        assert caps["engine"]["id"] == "recall_first"
        assert guide.get("status") in {"parsed", "released"}
        settings = self.client.get("/api/settings/guide", headers=headers)
        assert settings.status_code == 200 and settings.json().get("current")
        self.result["guide"] = {"id": guide.get("version_id"), "status": guide.get("status")}
        return settings.json()["current"]

    def submit_real_contract(self, headers: dict[str, str], guide: dict[str, Any], task_name: str) -> tuple[str, str]:
        data = self.source.read_bytes()
        manifest = [{"client_id": "delivery-e2e-contract", "name": self.source.name, "size": len(data)}]
        created = self.client.post("/api/tasks", headers=headers, json={
            "name": task_name, "engine_id": "recall_first", "guide_version_id": guide["id"],
            "files": manifest,
        })
        assert created.status_code == 201, created.text
        task_id = created.json()["id"]
        upload = self.client.post(
            f"/api/tasks/{task_id}/uploads", headers=headers,
            data={"client_ids": json.dumps([manifest[0]["client_id"]])},
            files=[("files", (self.source.name, data, DOCX_MIME))],
        )
        assert upload.status_code == 200, upload.text
        assert upload.json()["receipts"][0]["status"] == "accepted"
        sealed = self.client.post(f"/api/tasks/{task_id}/seal", headers=headers)
        assert sealed.status_code == 200, sealed.text
        self.result["task_id"] = task_id
        return task_id, upload.json()["receipts"][0]["document_id"]

    def assert_worker_report_and_artifacts(self, headers: dict[str, str], task_id: str, document_id: str,
                                           *, expected_model_calls: int | None = None) -> dict[str, Any]:
        document = self.client.get(f"/api/tasks/{task_id}/documents/{document_id}", headers=headers)
        assert document.status_code == 200, document.text
        row = document.json()
        assert row["job_status"] == "succeeded" and row["delivery_status"] == "complete"
        report_response = self.client.get(f"/api/tasks/{task_id}/documents/{document_id}/report", headers=headers)
        assert report_response.status_code == 200, report_response.text
        report = report_response.json()
        assert report.get("engine_id") == "recall_first"
        replay = report.get("artifact_claim_replay") or report.get("claim_replay")
        assert isinstance(replay, dict) and replay.get("passed") is True
        model = report.get("model") or {}
        if expected_model_calls is not None:
            assert model.get("calls") == expected_model_calls, model
        self._save_json("report.json", report)

        downloads = row.get("downloads") or {}
        for kind in ("final", "redline", "report_json", "report_md"):
            assert kind in downloads, f"missing {kind}: {downloads}"
            response = self.client.get(downloads[kind], headers=headers)
            assert response.status_code == 200, response.text
            suffix = ".json" if kind == "report_json" else ".md" if kind == "report_md" else ".docx"
            (self.evidence_dir / f"{kind}{suffix}").write_bytes(response.content)
        validation = report["output_validation"]
        for kind in ("final", "redline"):
            check = _docx_check(self.evidence_dir / f"{kind}.docx")
            assert check["valid_zip"] and check["has_document_xml"]
            assert check["sha256"] == validation[f"{kind}_sha256"]
            self.result.setdefault("docx", {})[kind] = check
        self.result["report"] = {"delivery_status": report["delivery_status"],
                                  "claim_replay": replay, "model": model}
        return row

    def assert_formal_download_replay(self) -> dict[str, Any]:
        """Reuse the established downloaded-artifact mechanical assertions."""
        from tools.evaluation.verify_downloaded_artifacts import verify_case

        checked = verify_case(self.evidence_dir, self.source)
        assert checked["mechanical_pass"], json.dumps(checked, ensure_ascii=False)
        self._save_json("artifact-review.json", checked)
        self.result["artifact_review"] = {
            "mechanical_pass": checked["mechanical_pass"],
            "changed_paragraphs": len(checked["changed_paragraphs"]),
        }
        return checked

    def assert_review_selection(self, headers: dict[str, str], other_headers: dict[str, str],
                                task_id: str, document_id: str) -> None:
        revisions = self.client.get(f"/api/tasks/{task_id}/documents/{document_id}/revisions", headers=headers)
        assert revisions.status_code == 200, revisions.text
        revision_items = revisions.json().get("revisions") or []
        assert len(revision_items) >= 2
        decisions = [{"del_id": revision_items[0]["del_id"], "decision": "reject"},
                     {"del_id": revision_items[1]["del_id"], "decision": "accept"}]
        selected = self.client.post(
            f"/api/tasks/{task_id}/documents/{document_id}/decisions",
            headers=headers, json={"decisions": decisions})
        assert selected.status_code == 200, selected.text
        selected_body = selected.json()
        assert selected_body["rejected"] and selected_body["accepted"]
        refreshed = self.client.get(f"/api/tasks/{task_id}/documents/{document_id}", headers=headers)
        assert refreshed.status_code == 200
        downloads = refreshed.json().get("downloads") or {}
        assert "selected_final" in downloads and "selected_redline" in downloads
        for kind in ("selected_final", "selected_redline"):
            response = self.client.get(downloads[kind], headers=headers)
            assert response.status_code == 200, response.text
            path = self.evidence_dir / f"{kind}.docx"
            path.write_bytes(response.content)
            check = _docx_check(path)
            assert check["valid_zip"] and check["has_document_xml"]
            self.result.setdefault("selected_artifacts", {})[kind] = check
        unauthenticated = self.client.get(downloads["selected_final"])
        assert unauthenticated.status_code in {401, 403}
        forbidden = self.client.get(downloads["selected_final"], headers=other_headers)
        assert forbidden.status_code in {403, 404}
        self.result["review"] = {"revision_count": len(revision_items),
                                  "accepted": selected_body["accepted"],
                                  "rejected": selected_body["rejected"],
                                  "unauthorized_status": unauthenticated.status_code,
                                  "cross_owner_status": forbidden.status_code}


def _cleanup_runtime(app, owners: list[str], task_ids: list[str]) -> None:
    """Remove task, artifact, session and account rows from the isolated store."""
    store = app.state.store
    with store._connect() as db:
        ids = set(task_ids)
        if owners:
            rows = db.execute("SELECT id FROM tasks WHERE owner IN (%s)" % ",".join("?" * len(owners)), owners).fetchall()
            ids.update(row["id"] for row in rows)
        batch_ids: set[str] = set()
        document_ids: set[str] = set()
        for task_id in ids:
            batch_ids.update(row["batch_id"] for row in db.execute("SELECT batch_id FROM task_batches WHERE task_id=?", (task_id,)).fetchall())
        for batch_id in batch_ids:
            document_ids.update(row["id"] for row in db.execute("SELECT id FROM documents WHERE batch_id=?", (batch_id,)).fetchall())
        object_keys = [row["object_key"] for document_id in document_ids
                       for row in db.execute("SELECT object_key FROM artifacts WHERE document_id=?", (document_id,)).fetchall()]
        # task_files owns the document foreign key, so it must be removed before
        # documents.  Keep this order explicit: a cleanup failure must never
        # hide the delivery assertion that caused the run to stop.
        if ids:
            db.execute("DELETE FROM task_files WHERE task_id IN (%s)" % ",".join("?" * len(ids)), tuple(ids))
        if document_ids:
            db.execute("DELETE FROM artifacts WHERE document_id IN (%s)" % ",".join("?" * len(document_ids)), tuple(document_ids))
            db.execute("DELETE FROM documents WHERE id IN (%s)" % ",".join("?" * len(document_ids)), tuple(document_ids))
        if batch_ids:
            db.execute("DELETE FROM task_batches WHERE batch_id IN (%s)" % ",".join("?" * len(batch_ids)), tuple(batch_ids))
            db.execute("DELETE FROM batches WHERE id IN (%s)" % ",".join("?" * len(batch_ids)), tuple(batch_ids))
        if ids:
            db.execute("DELETE FROM tasks WHERE id IN (%s)" % ",".join("?" * len(ids)), tuple(ids))
        if owners:
            db.execute("DELETE FROM guide_config WHERE owner IN (%s)" % ",".join("?" * len(owners)), tuple(owners))
    # Password accounts deliberately use the separate auth database.  Keeping
    # this cleanup separate also makes it safe for the runner to use the same
    # store layout as a deployed app during a dry-run.
    if owners and getattr(app.state, "auth_db", None) is not None:
        with app.state.auth_db.connect() as auth_db:
            auth_db.execute("DELETE FROM sessions WHERE user_id IN (%s)" % ",".join("?" * len(owners)), tuple(owners))
            auth_db.execute("DELETE FROM users WHERE id IN (%s)" % ",".join("?" * len(owners)), tuple(owners))
    for key in object_keys:
        store.object_path(key).unlink(missing_ok=True)


def run_delivery_e2e(*, source: Path = DEFAULT_SOURCE, evidence_dir: Path | None = None,
                     model_mode: str = "fixture", allow_real_model: bool = False) -> dict[str, Any]:
    """Run the named delivery E2E workflow and return redacted evidence."""
    if model_mode not in {"fixture", "real"}:
        raise ValueError("model_mode must be fixture or real")
    if model_mode == "real" and not allow_real_model:
        raise ValueError("real model mode requires allow_real_model=True")
    source = Path(source).resolve()
    if not source.is_file() or source.suffix.lower() != ".docx":
        raise ValueError(f"delivery-e2e source DOCX not found: {source}")
    evidence = Path(evidence_dir or tempfile.mkdtemp(prefix="fundlex-delivery-e2e-", dir="/tmp/opencode"))
    evidence.mkdir(parents=True, exist_ok=True)
    data_dir = Path(tempfile.mkdtemp(prefix="fundlex-delivery-runtime-", dir="/tmp/opencode"))
    owners: list[str] = []
    task_ids: list[str] = []
    app = None
    assertions: DeliveryE2EAssertions | None = None
    result: dict[str, Any] = {"workflow": "delivery-e2e", "model_mode": model_mode,
                              "evidence_dir": str(evidence), "source": source.name,
                              "source_sha256": _sha256(source)}
    try:
        with _environment({"FUNDLEX_AUTH_MODE": "password", "FUNDLEX_ALLOW_REGISTRATION": "1",
                           "FUNDLEX_DATA_DIR": str(data_dir)}):
            from fastapi.testclient import TestClient
            from fundlex.api import create_app
            from fundlex.jobs import Worker

            app = create_app(data_dir=data_dir)
            processor = None if model_mode == "real" else _fixture_processor
            worker = Worker(app.state.store, processor)
            with TestClient(app) as client:
                assertions = DeliveryE2EAssertions(client, evidence, source)
                username, password = _random_name("delivery-e2e"), uuid.uuid4().hex
                headers, owner = assertions.assert_workbench_login(username, password)
                owners.append(owner["id"])
                guide = assertions.assert_guide_and_entry(headers)
                task_id, document_id = assertions.submit_real_contract(
                    headers, guide, "delivery-e2e-真实合同入口")
                task_ids.append(task_id)
                assert worker.run_once(), "Worker did not claim the submitted document"
                assertions.assert_worker_report_and_artifacts(
                    headers, task_id, document_id,
                    expected_model_calls=0 if model_mode == "fixture" else None)
                assertions.assert_formal_download_replay()

                other_name, other_password = _random_name("delivery-e2e-other"), uuid.uuid4().hex
                other_login = client.post("/api/auth/register", json={
                    "username": other_name, "password": other_password, "display_name": "delivery-e2e-other"
                })
                assert other_login.status_code == 201, other_login.text
                other_payload = other_login.json()
                owners.append(other_payload["user"]["id"])
                other_headers = {"Authorization": f"Bearer {other_payload['token']}"}
                assertions.assert_review_selection(headers, other_headers, task_id, document_id)
                result.update(assertions.result)
                result["cleanup"] = "pending"
    except Exception as exc:
        if assertions is not None:
            result.update(assertions.result)
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["retained_evidence"] = sorted(path.name for path in evidence.iterdir() if path.is_file())
        (evidence / "failure.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        raise
    finally:
        try:
            if app is not None:
                _cleanup_runtime(app, owners, task_ids)
        except Exception as cleanup_error:
            if assertions is not None:
                result.update(assertions.result)
            result["cleanup_error"] = f"{type(cleanup_error).__name__}: {cleanup_error}"
            result["retained_evidence"] = sorted(path.name for path in evidence.iterdir() if path.is_file())
            (evidence / "failure.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            raise
        finally:
            shutil.rmtree(data_dir, ignore_errors=True)
    result["cleanup"] = "isolated runtime, task, artifacts, sessions and accounts removed"
    (evidence / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the FundLex delivery-e2e workflow")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--model-mode", choices=("fixture", "real"), default="fixture",
                        help="fixture is the default and makes zero model calls")
    parser.add_argument("--dry-run", action="store_true",
                        help="explicit alias for the default fixture mode")
    parser.add_argument("--allow-real-model", action="store_true",
                        help="required acknowledgement before the real model mode can run")
    args = parser.parse_args(argv)
    if args.dry_run and args.model_mode == "real":
        parser.error("--dry-run cannot be combined with --model-mode real")
    if args.model_mode == "real" and not args.allow_real_model:
        parser.error("--model-mode real requires --allow-real-model")
    try:
        result = run_delivery_e2e(source=args.source, evidence_dir=args.evidence_dir,
                                  model_mode=args.model_mode, allow_real_model=args.allow_real_model)
    except Exception as exc:
        print(json.dumps({"workflow": "delivery-e2e", "status": "failed", "error": str(exc)},
                         ensure_ascii=False))
        return 1
    print(json.dumps({**result, "status": "passed"}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
