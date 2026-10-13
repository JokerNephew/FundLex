"""Task-workbench integration tests for the v2 contract-revision mode."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.jobs import Worker
from fundlex.v2_pipeline import process_v2
from test_v2_release import ScriptedGateway, build_fixture

OWNER = "workbench-user"
HEADERS = {"X-FundLex-User": OWNER}


def create_v2_task(client: TestClient, source: Path, name: str = "合同修订任务"):
    response = client.post("/api/tasks", headers={**HEADERS, "Idempotency-Key": "task-revision-c1"},
                           json={"name": name, "ruleset_version": "v2",
                                 "files": [{"client_id": "c1", "name": source.name,
                                            "size": source.stat().st_size}]})
    assert response.status_code == 201, response.text
    task_id = response.json()["id"]
    upload = client.post(f"/api/tasks/{task_id}/uploads", headers=HEADERS,
                         data={"client_ids": json.dumps(["c1"])},
                         files=[("files", (source.name, source.read_bytes()))])
    assert upload.status_code == 200, upload.text
    assert upload.json()["receipts"][0]["status"] == "accepted"
    return task_id


def test_capabilities_expose_revision_mode(tmp_path):
    app = create_app(tmp_path / "state")
    client = TestClient(app)
    capabilities = client.get("/api/capabilities", headers=HEADERS).json()
    assert capabilities["revision_ruleset_version"] == "v2"
    assert capabilities["revision_mode"] in {"evaluation", "delivery"}
    assert capabilities["revision_auto_write_enabled"] is (capabilities["revision_mode"] == "delivery")
    assert capabilities["revision_actions_total"] == 22
    assert "R10-A1" in capabilities["revision_action_labels"]
    assert capabilities["auto_write_enabled"] is False


def test_unknown_ruleset_rejected_on_task_creation(tmp_path):
    app = create_app(tmp_path / "state")
    client = TestClient(app)
    response = client.post("/api/tasks", headers=HEADERS,
                           json={"name": "bad", "ruleset_version": "v9",
                                 "files": [{"client_id": "c1", "name": "x.docx", "size": 1}]})
    assert response.status_code == 422


def test_task_runs_evaluation_revision_and_downloads(tmp_path):
    source = build_fixture(tmp_path / "fixture.docx")
    app = create_app(tmp_path / "state")
    client = TestClient(app)
    task_id = create_v2_task(client, source)
    gateway = ScriptedGateway()
    worker = Worker(app.state.store, lambda src, out, ver: process_v2(src, out, ver, gateway, evaluation=True))
    assert worker.run_once()
    summary = client.get(f"/api/tasks/{task_id}", headers=HEADERS).json()
    assert summary["ruleset_version"] == "v2"
    assert summary["status"] == "completed"
    assert summary["delivery_counts"].get("evaluation_modified") == 1
    documents = client.get(f"/api/tasks/{task_id}/documents", headers=HEADERS).json()
    document = documents["items"][0]
    assert document["execution_mode"] == "evaluation"
    assert document["delivery_status"] == "evaluation_modified"
    assert {"evaluation_final", "evaluation_redline"}.issubset(document["downloads"])
    assert "final" not in document["downloads"] and "redline" not in document["downloads"]
    assert document["report_url"]
    final = client.get(document["downloads"]["evaluation_final"], headers=HEADERS)
    assert final.status_code == 200
    assert client.get(f"/api/batches/{document['batch_id']}/documents/{document['document_id']}/download/final",
                      headers=HEADERS).status_code == 404
    report = client.get(document["report_url"], headers=HEADERS).json()
    assert report["execution_mode"] == "evaluation"
    assert report["content_verifications"][0]["passed"] is True
    task_report = client.get(summary["summary_url"], headers=HEADERS)
    assert task_report.status_code == 200
    assert "v2" in task_report.text
