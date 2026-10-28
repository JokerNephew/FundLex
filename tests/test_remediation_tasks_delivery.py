"""FL-D454/456: one verified artifact accessor and persisted task mode.

The task store, worker, HTTP routes and Feishu facade are the real production
objects. Only the model-facing pipeline is replaced by a deterministic writer,
so these checks exercise publication and download gates rather than model
quality.
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex import guide_store
from fundlex.api import create_app
from fundlex.docx import generate_unchanged_artifacts, validate_edit_plan
from fundlex.integrations.feishu.events import MessageEvent
from fundlex.integrations.feishu.service import FeishuService
from fundlex.jobs import Worker
from fundlex.store import Conflict, NotFound, RunStore
from fundlex.tasks import TaskStore

OWNER = "remediation-owner"
HEADERS = {"X-FundLex-User": OWNER}


def contract_bytes(label: str = "公开合同正文示例") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def bound_store(tmp_path: Path) -> tuple[RunStore, dict]:
    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    version = guide_store.get_version(store, OWNER, guide_store.BUILTIN_GUIDE_ID)
    return store, version


def api_bound(tmp_path: Path):
    app = create_app(tmp_path / "state")
    store = app.state.store
    guide_store.ensure_builtin_guide(store)
    version = guide_store.get_version(store, OWNER, guide_store.BUILTIN_GUIDE_ID)
    return app, store, version


def submit_task(store: RunStore, version: dict, *, mode: str = "delivery", data: bytes | None = None):
    payload = data or contract_bytes()
    tasks = TaskStore(store)
    task = tasks.create(OWNER, "整改验证任务", {"version": "v1", "sha256": ""},
                        [{"client_id": "c1", "name": "contract.docx", "size": len(payload)}],
                        engine_id="recall_first", guide_version_id=version["id"],
                        guide_rules_sha256=version["sha256"] if "sha256" in version else version["rules_sha256"],
                        mode=mode)
    receipts = tasks.uploads(OWNER, task["id"],
                             [{"client_id": "c1", "name": "contract.docx", "data": payload}])
    assert receipts["receipts"][0]["status"] == "accepted"
    return tasks, task["id"], receipts["receipts"][0]["batch_id"], receipts["receipts"][0]["document_id"], payload


def complete_processor(source, output, ruleset):
    plan = validate_edit_plan(source, [], {})
    validation = generate_unchanged_artifacts(source, plan, output / "redline.docx", output / "final.docx")
    return {"engine_id": "recall_first", "schema_version": "3", "execution_mode": "delivery",
            "qualification_status": "eligible", "delivery_status": "complete",
            "output_validation": {"kind": "recall_validated_unchanged", "checks": list(validation.checks),
                                  "final_sha256": validation.final_sha256,
                                  "redline_sha256": validation.redline_sha256},
            "artifacts": {"final": "final.docx", "redline": "redline.docx"}}


def incomplete_evaluation_processor(source, output, ruleset):
    """A real pipeline-shaped report that is incomplete before mode binding."""
    plan = validate_edit_plan(source, [], {})
    validation = generate_unchanged_artifacts(source, plan, output / "working_redline.docx",
                                              output / "working_final.docx")
    return {"engine_id": "recall_first", "schema_version": "3", "execution_mode": "delivery",
            "qualification_status": "eligible", "delivery_status": "incomplete",
            "unresolved": [{"kind": "target", "rule_id": "G01", "reason": "RECALL_TARGET_UNRESOLVED"}],
            "output_validation": {"kind": "recall_working_edits",
                                  "checks": [*validation.checks, "actual_content_verification"],
                                  "final_sha256": validation.final_sha256,
                                  "redline_sha256": validation.redline_sha256},
            "artifacts": {"working_final": "working_final.docx",
                          "working_redline": "working_redline.docx"}}


class FakeFeishuClient:
    def __init__(self):
        self.files: list[tuple[str, str, int]] = []

    def send_card(self, receive_id, card):
        return "msg-1"

    def update_card(self, message_id, card):
        return None

    def send_file(self, receive_id, filename, data):
        self.files.append((receive_id, filename, len(data)))
        return f"file-{len(self.files)}"


class TaskFacade:
    """Only the read/send methods Feishu result delivery uses."""

    def __init__(self, tasks: TaskStore):
        self.tasks = tasks

    def get_task(self, owner, task_id):
        return self.tasks.get(owner, task_id)

    def list_documents(self, owner, task_id, **filters):
        return self.tasks.documents(owner, task_id, **filters)

    def artifact(self, owner, task_id, document_id, kind):
        return self.tasks.artifact(owner, task_id, document_id, kind)


def feishu_sender(store: RunStore, tasks: TaskStore):
    client = FakeFeishuClient()
    facade = TaskFacade(tasks)
    service = FeishuService(store, facade, facade, client)
    return service, client


def send_event() -> MessageEvent:
    return MessageEvent("evt-send", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                        "p2p", "msg-send", "text", {"text": "发送全部"})


def artifact_path(store: RunStore, document_id: str, kind: str) -> Path:
    with store._connect() as db:
        row = db.execute("SELECT object_key FROM artifacts WHERE document_id=? AND kind=?",
                         (document_id, kind)).fetchone()
    assert row is not None
    return store.object_path(row["object_key"])


def test_http_and_feishu_reject_a_final_when_its_redline_is_corrupt(tmp_path):
    app, store, version = api_bound(tmp_path)
    client = TestClient(app)
    tasks, task_id, batch_id, document_id, _ = submit_task(store, version)
    assert Worker(store, complete_processor).run_once()
    doc = tasks.documents(OWNER, task_id)["items"][0]
    assert {"final", "redline"}.issubset(doc["downloads"])
    assert client.get(doc["downloads"]["final"], headers=HEADERS).status_code == 200

    artifact_path(store, document_id, "redline").write_bytes(b"corrupted redline")
    refused = client.get(doc["downloads"]["final"], headers=HEADERS)
    assert refused.status_code == 409
    assert client.get(doc["downloads"]["report_md"], headers=HEADERS).status_code == 200
    assert client.get(doc["downloads"]["final"]).status_code == 401
    assert client.get(doc["downloads"]["final"], headers={"X-FundLex-User": "other"}).status_code == 404

    service, sender = feishu_sender(store, tasks)
    result = service._send_result_file(send_event(), OWNER, "revision", task_id, "all")
    names = [name for _, name, _ in sender.files]
    assert not any(name.endswith(("final.docx", "redline.docx")) for name in names)
    assert any("report_md" in name for name in names)
    assert "2 个文件发送失败" in result and "final" in result and "redline" in result

    with pytest.raises(Conflict):
        tasks.artifact(OWNER, task_id, document_id, "final")


def test_invalid_report_and_execution_mode_mismatch_block_http_and_feishu(tmp_path):
    app, store, version = api_bound(tmp_path)
    client = TestClient(app)
    tasks, task_id, _, document_id, _ = submit_task(store, version)
    assert Worker(store, complete_processor).run_once()
    doc = tasks.documents(OWNER, task_id)["items"][0]

    with store._connect() as db:
        db.execute("UPDATE documents SET report_json='{' WHERE id=?", (document_id,))
    assert client.get(doc["downloads"]["final"], headers=HEADERS).status_code == 409
    service, sender = feishu_sender(store, tasks)
    refused = service._send_result_file(send_event(), OWNER, "revision", task_id, "all")
    assert not sender.files and "失败" in refused

    # Restore a valid report but make its declared mode disagree with the
    # persisted job. Neither the pair nor the report may be served.
    app2, store2, version2 = api_bound(tmp_path / "second")
    client2 = TestClient(app2)
    tasks2, task2, _, document2, _ = submit_task(store2, version2)
    assert Worker(store2, complete_processor).run_once()
    doc2 = tasks2.documents(OWNER, task2)["items"][0]
    with store2._connect() as db:
        row = db.execute("SELECT report_json FROM documents WHERE id=?", (document2,)).fetchone()
        report = json.loads(row["report_json"])
        report["execution_mode"] = "evaluation"
        db.execute("UPDATE documents SET report_json=? WHERE id=?",
                   (json.dumps(report), document2))
    assert client2.get(doc2["downloads"]["final"], headers=HEADERS).status_code == 409
    assert client2.get(doc2["downloads"]["report_md"], headers=HEADERS).status_code == 409
    service2, sender2 = feishu_sender(store2, tasks2)
    assert "失败" in service2._send_result_file(send_event(), OWNER, "revision", task2, "all")
    assert not sender2.files


def test_selected_download_is_refused_when_its_source_redline_is_damaged(tmp_path):
    app, store, version = api_bound(tmp_path)
    client = TestClient(app)
    tasks, task_id, batch_id, document_id, payload = submit_task(store, version)
    assert Worker(store, complete_processor).run_once()
    with store._connect() as db:
        row = db.execute("SELECT report_json FROM documents WHERE id=?", (document_id,)).fetchone()
        report = json.loads(row["report_json"])
        report["revision_manifest"] = [{"revision_id": "fixture-r1"}]
        db.execute("UPDATE documents SET report_json=? WHERE id=?", (json.dumps(report), document_id))
    doc = tasks.documents(OWNER, task_id)["items"][0]
    source = artifact_path(store, document_id, "final")
    store.save_selected_artifact(OWNER, batch_id, document_id, "selected_final", source)
    with store._connect() as db:
        row = db.execute("SELECT object_key FROM artifacts WHERE document_id=? AND kind='selected_final'",
                         (document_id,)).fetchone()
    selected_url = f"/api/tasks/{task_id}/documents/{document_id}/download/selected_final"
    assert client.get(selected_url, headers=HEADERS).status_code == 200
    assert row is not None

    artifact_path(store, document_id, "redline").write_bytes(b"damaged")
    assert client.get(selected_url, headers=HEADERS).status_code == 409
    service, sender = feishu_sender(store, tasks)
    assert "失败" in service._send_result_file(send_event(), OWNER, "revision", task_id, "selected_final")
    assert not sender.files


def test_incomplete_evaluation_is_report_only_and_not_selectable(tmp_path):
    app, store, version = api_bound(tmp_path)
    client = TestClient(app)
    tasks, task_id, _, document_id, _ = submit_task(store, version, mode="evaluation")
    assert Worker(store, incomplete_evaluation_processor).run_once()
    doc = tasks.documents(OWNER, task_id)["items"][0]
    assert doc["execution_mode"] == "evaluation"
    assert doc["delivery_status"] == "incomplete"
    assert set(doc["downloads"]) == {"report_md", "report_json"}
    assert not {"final", "redline", "working_final", "working_redline",
                "evaluation_final", "evaluation_redline"} & set(doc["downloads"])
    assert client.get(f"/api/tasks/{task_id}/documents/{document_id}/download/working_final",
                      headers=HEADERS).status_code == 404
    assert client.get(f"/api/tasks/{task_id}/documents/{document_id}/download/final",
                      headers=HEADERS).status_code == 404
    assert client.get(f"/api/tasks/{task_id}/documents/{document_id}/revisions",
                      headers=HEADERS).status_code == 409
    assert client.get(doc["report_url"], headers=HEADERS).json()["execution_mode"] == "evaluation"
    with pytest.raises(NotFound):
        store.get_artifact(OWNER, doc["batch_id"], document_id, "working_final")


@pytest.mark.parametrize("terminal", ["excluded", "not_generated", "failed"])
def test_evaluation_terminal_states_keep_evaluation_identity(tmp_path, terminal):
    store, version = bound_store(tmp_path)
    tasks, task_id, _, document_id, _ = submit_task(store, version, mode="evaluation")

    if terminal == "failed":
        def processor(source, output, ruleset):
            raise ValueError("deterministic failure")
    else:
        def processor(source, output, ruleset):
            plan = validate_edit_plan(source, [], {})
            validation = generate_unchanged_artifacts(source, plan, output / "redline.docx",
                                                      output / "final.docx")
            return {"engine_id": "recall_first", "schema_version": "3",
                    "execution_mode": "delivery",
                    "qualification_status": "excluded_by_fund_type" if terminal == "excluded" else "eligible",
                    "delivery_status": terminal,
                    "output_validation": {"kind": "recall_validated_unchanged",
                                          "checks": list(validation.checks),
                                          "final_sha256": validation.final_sha256,
                                          "redline_sha256": validation.redline_sha256},
                    "artifacts": {"final": "final.docx", "redline": "redline.docx"}}

    assert Worker(store, processor).run_once()
    doc = tasks.documents(OWNER, task_id)["items"][0]
    assert doc["execution_mode"] == "evaluation"
    assert doc["delivery_status"] in {terminal, "not_generated"}
    assert not {"final", "redline", "working_final", "working_redline",
                "evaluation_final", "evaluation_redline"} & set(doc["downloads"])
    assert {"report_json", "report_md"}.issubset(doc["downloads"])


def test_store_rejects_a_delivery_report_for_an_evaluation_job(tmp_path):
    app, store, version = api_bound(tmp_path)
    client = TestClient(app)
    tasks, task_id, _, document_id, _ = submit_task(store, version, mode="evaluation")
    job = store.claim()
    assert job is not None and job["id"] == document_id and job["mode"] == "evaluation"
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({"delivery_status": "not_generated"}), encoding="utf-8")
    with pytest.raises(Conflict, match="EXECUTION_MODE_MISMATCH"):
        store.finish(document_id, job["fencing_token"],
                     report={"delivery_status": "not_generated", "execution_mode": "delivery"},
                     artifacts={"report_json": report_path})
