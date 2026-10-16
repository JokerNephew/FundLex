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


def test_capabilities_expose_engine_contract(tmp_path):
    app = create_app(tmp_path / "state")
    client = TestClient(app)
    capabilities = client.get("/api/capabilities", headers=HEADERS).json()
    engine = capabilities["engine"]
    assert engine["id"] == "recall_first"
    assert engine["rule_source"] == "guide"
    assert engine["delivery_mode"] in {"formal", "unavailable"}
    assert engine["auto_write_enabled"] is (engine["delivery_mode"] == "formal")
    assert engine["actions_total"] == int((engine["guide"] or {}).get("groups") or 0)
    # Retired ruleset fields must not leak back into the capability payload.
    assert not {"revision_ruleset_version", "revision_mode", "revision_auto_write_enabled",
                "revision_actions_total", "revision_action_labels",
                "ruleset_version", "auto_write_enabled", "actions_total", "engine_id"} & set(capabilities)


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
    batch = app.state.store.create_batch(owner=OWNER, ruleset_version="v2", ruleset_sha256="0" * 64,
                                         uploads=[(source.name, source.read_bytes())])
    batch_id = batch["id"]
    gateway = ScriptedGateway()
    worker = Worker(app.state.store, lambda src, out, ver: process_v2(src, out, ver, gateway, evaluation=True))
    assert worker.run_once()
    # The v2 task surface is retired; its persisted batch is what the offline
    # runner inspects and what the download surface still serves.
    detail = client.get(f"/api/batches/{batch_id}", headers=HEADERS).json()
    assert detail["status"] == "completed"
    document = detail["documents"][0]
    assert document["execution_mode"] == "evaluation"
    assert document["delivery_status"] == "evaluation_modified_with_exceptions"
    assert {"evaluation_final", "evaluation_redline"}.issubset(document["downloads"])
    assert "final" not in document["downloads"] and "redline" not in document["downloads"]
    assert document["report_url"]
    final = client.get(document["downloads"]["evaluation_final"], headers=HEADERS)
    assert final.status_code == 200
    assert client.get(f"/api/batches/{batch_id}/documents/{document['document_id']}/download/final",
                      headers=HEADERS).status_code == 404
    report = client.get(document["report_url"], headers=HEADERS).json()
    assert report["execution_mode"] == "evaluation"
    assert report["content_verifications"][0]["passed"] is True
    batch_report = client.get(f"/api/batches/{batch_id}/report", headers=HEADERS)
    assert batch_report.status_code == 200
    assert "v2" in batch_report.text
