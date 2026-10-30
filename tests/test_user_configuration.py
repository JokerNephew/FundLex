"""User-facing guide switches, task snapshots and delivery reporting.

The tests use the real guide/task stores and a scripted guide document; no model
call or real contract is involved.
"""
from __future__ import annotations

import io
import json

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex import guide_store
from fundlex.delivery import build_user_summary
from fundlex.guide import GUIDE_SCHEMA_VERSION
from fundlex.recall import RecallError
from fundlex.recall_pipeline import _active_guide_document

ALICE = {"X-FundLex-User": "alice"}
BOB = {"X-FundLex-User": "bob"}


def docx_bytes(label: str = "合同正文") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def two_rule_document() -> dict:
    return {
        "schema_version": GUIDE_SCHEMA_VERSION,
        "parser_version": "guide-parse-1",
        "prompt_versions": {"guide_parse": "guide_parse_v1", "guide_verify": "guide_verify_v1"},
        "groups": [
            {"rule_id": "G01", "title": "释义规则", "section_hint": "释义",
             "operations": [{"op": "append", "new_text": "新增一"}]},
            {"rule_id": "G02", "title": "费用规则", "section_hint": "基金费用",
             "operations": [{"op": "append", "new_text": "新增二"}]},
        ],
        "validation": {"errors": [], "warnings": [], "coverage_gaps": []},
    }


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    from fundlex.api import create_app
    return TestClient(create_app(tmp_path / "state"))


def parsed_custom(client, *, owner: str = "alice") -> dict:
    store = client.app.state.store
    version = guide_store.create_custom_version(store, owner, "custom.docx", docx_bytes("指引"))
    job = guide_store.claim_guide_job(store)
    finished = guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                             document=two_rule_document())
    return finished["version"]


def test_guide_rule_settings_are_owner_scoped_and_validate_ids(client):
    version = parsed_custom(client)
    response = client.get(f"/api/guides/{version['id']}/rule-settings", headers=ALICE)
    assert response.status_code == 200
    body = response.json()
    assert body["disabled_rule_ids"] == []
    assert [rule["rule_id"] for rule in body["rules"]] == ["G01", "G02"]
    assert all(rule["enabled"] for rule in body["rules"])

    saved = client.put(f"/api/guides/{version['id']}/rule-settings", headers=ALICE,
                       json={"disabled_rule_ids": ["G02"]})
    assert saved.status_code == 200
    assert saved.json()["disabled_rule_ids"] == ["G02"]
    assert [rule["enabled"] for rule in saved.json()["rules"]] == [True, False]

    # Another owner cannot see or change this guide.
    assert client.get(f"/api/guides/{version['id']}/rule-settings", headers=BOB).status_code == 404
    assert client.put(f"/api/guides/{version['id']}/rule-settings", headers=BOB,
                      json={"disabled_rule_ids": []}).status_code == 404

    unknown = client.put(f"/api/guides/{version['id']}/rule-settings", headers=ALICE,
                         json={"disabled_rule_ids": ["G99"]})
    assert unknown.status_code == 422
    assert "GUIDE_RULE_INVALID" in unknown.text

    all_disabled = client.put(f"/api/guides/{version['id']}/rule-settings", headers=ALICE,
                              json={"disabled_rule_ids": ["G01", "G02"]})
    assert all_disabled.status_code == 422
    assert "GUIDE_RULES_ALL_DISABLED" in all_disabled.text


def test_task_snapshot_records_disabled_rules_and_idempotency_rejects_changes(client):
    version = parsed_custom(client)
    assert client.put(f"/api/guides/{version['id']}/rule-settings", headers=ALICE,
                      json={"disabled_rule_ids": ["G02"]}).status_code == 200
    assert client.put("/api/settings/guide", headers=ALICE,
                      json={"version_id": version["id"]}).status_code == 200
    data = docx_bytes()
    files = [{"client_id": "c1", "name": "合同.docx", "size": len(data)}]
    created = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "switch-task"},
                          json={"name": "规则开关任务", "engine_id": "recall_first", "files": files})
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["disabled_rule_ids"] == ["G02"]
    assert task["guide_snapshot"]["version_id"] == version["id"]

    # Changing the switches after creation must not alter the snapshot, and the
    # same idempotency key with a different effective configuration conflicts.
    assert client.put(f"/api/guides/{version['id']}/rule-settings", headers=ALICE,
                      json={"disabled_rule_ids": []}).status_code == 200
    same = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "switch-task"},
                       json={"name": "规则开关任务", "engine_id": "recall_first", "files": files})
    assert same.status_code == 409
    assert client.get(f"/api/tasks/{task['id']}", headers=ALICE).json()["disabled_rule_ids"] == ["G02"]

    # The worker claim carries the same snapshot.
    uploaded = client.post(f"/api/tasks/{task['id']}/uploads", headers=ALICE,
                           data={"client_ids": json.dumps(["c1"])},
                           files=[("files", ("合同.docx", data))])
    assert uploaded.status_code == 200, uploaded.text
    job = client.app.state.store.claim()
    assert job is not None
    assert job["disabled_rule_ids"] == json.dumps(["G02"])


def test_active_guide_document_removes_only_disabled_rules():
    document = two_rule_document()
    active, disabled = _active_guide_document(document, ["G02"])
    assert [rule["rule_id"] for rule in active["groups"]] == ["G01"]
    assert [rule["rule_id"] for rule in document["groups"]] == ["G01", "G02"]
    assert disabled == [{"rule_id": "G02", "title": "费用规则",
                         "section_hint": "基金费用", "reason": "USER_DISABLED"}]
    with pytest.raises(RecallError, match="GUIDE_RULE_UNKNOWN"):
        _active_guide_document(document, ["G99"])


def test_disabled_rule_is_skipped_and_reported_by_the_pipeline(tmp_path):
    from test_recall_pipeline import run

    _source, _output, _model, report = run(tmp_path, disabled_rule_ids=["G06"])
    assert report["delivery_status"] == "complete_with_exceptions"
    assert [item["rule_id"] for item in report["disabled_rules"]] == ["G06"]
    assert "G06" not in {str(target.get("rule_id")) for target in report["targets"]}
    assert report["user_summary"]["status"] == "complete_with_notices"
    assert report["user_summary"]["disabled_rules"][0]["rule_id"] == "G06"


def test_disabled_rules_are_visible_in_user_summary():
    summary = build_user_summary({
        "delivery_status": "complete_with_exceptions",
        "delivery_policy": "review_assisted",
        "disabled_rules": [{"rule_id": "G02", "title": "费用规则",
                            "section_hint": "基金费用", "reason": "USER_DISABLED"}],
        "unresolved": [],
    })
    assert summary["status"] == "complete_with_notices"
    assert "1 条规则由用户关闭" in summary["headline"]
    assert summary["issues"][0]["code"] == "RULE_DISABLED_BY_USER"
    assert summary["issues"][0]["rule_id"] == "G02"


def test_model_choice_is_bound_at_task_creation(client):
    from fundlex import model_settings
    store = client.app.state.store
    model_settings.save_settings(store, "alice", {"primary": {"model": "before"}})
    data = docx_bytes()
    response = client.post("/api/tasks", headers=ALICE, json={
        "name": "模型快照", "engine_id": "recall_first",
        "files": [{"client_id": "c1", "name": "合同.docx", "size": len(data)}]})
    assert response.status_code == 201, response.text
    task = response.json()
    model_settings.save_settings(store, "alice", {"primary": {"model": "after"}})
    current = client.get(f"/api/tasks/{task['id']}", headers=ALICE).json()
    assert current["model_preferences"]["primary"]["model"] == "before"
    client.post(f"/api/tasks/{task['id']}/uploads", headers=ALICE,
                data={"client_ids": '["c1"]'}, files=[("files", ("合同.docx", data))])
    job = store.claim()
    assert json.loads(job["model_preferences"])["primary"]["model"] == "before"


def test_default_worker_applies_disabled_rules_and_authorized_download(client, tmp_path, monkeypatch):
    """Real API/store/Worker/DOCX; only model responses are scripted."""
    from fundlex import model_settings
    from fundlex.jobs import Worker
    from test_recall_pipeline import PipelineGateway, base_responses, build_contract, guide_document

    store = client.app.state.store
    version = guide_store.create_custom_version(store, "alice", "rules.docx", docx_bytes("指引"))
    job = guide_store.claim_guide_job(store)
    from fundlex.guide import certify_guide_document
    document = guide_document()
    document["source_sha256"] = version["source_sha256"]
    document = certify_guide_document(document, source_sha256=version["source_sha256"])
    guide_store.finish_guide_job(store, job["id"], job["fencing_token"], document=document)
    guide_store.set_current_guide(store, "alice", version["id"])
    guide_store.set_rule_settings(store, "alice", version["id"], ["G06"])
    model_settings.save_settings(store, "alice", {"primary": {"model": "snapshot-model"}})
    captured = []

    def scripted_gateway(preferences):
        captured.append(preferences)
        return PipelineGateway(base_responses())

    monkeypatch.setattr(model_settings, "gateway_for", scripted_gateway)
    source = tmp_path / "source.docx"
    build_contract(source)
    data = source.read_bytes()
    task = client.post("/api/tasks", headers=ALICE, json={
        "name": "离线全链路", "engine_id": "recall_first",
        "files": [{"client_id": "c1", "name": "合同.docx", "size": len(data)}]}).json()
    receipt = client.post(f"/api/tasks/{task['id']}/uploads", headers=ALICE,
                          data={"client_ids": '["c1"]'},
                          files=[("files", ("合同.docx", data))]).json()["receipts"][0]
    client.post(f"/api/tasks/{task['id']}/seal", headers=ALICE)
    assert Worker(store).run_once()
    root = f"/api/tasks/{task['id']}/documents/{receipt['document_id']}"
    report_response = client.get(root + "/report", headers=ALICE)
    assert report_response.status_code == 200, report_response.text
    report = report_response.json()
    assert report["delivery_status"] == "complete_with_exceptions", report.get("errors")
    assert report["disabled_rules"][0]["rule_id"] == "G06"
    assert captured[0]["primary"]["model"] == "snapshot-model"
    final = client.get(root + "/download/final", headers=ALICE)
    redline = client.get(root + "/download/redline", headers=ALICE)
    assert final.status_code == redline.status_code == 200
    import hashlib
    import zipfile
    from lxml import etree
    from test_recall_core import CONVERSION_CLAUSE
    def xml_of(blob):
        with zipfile.ZipFile(io.BytesIO(blob)) as archive:
            return etree.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    final_xml = xml_of(final.content)
    text = "".join(final_xml.xpath("//w:t/text()", namespaces=ns))
    assert CONVERSION_CLAUSE in text, "disabled G06 must preserve the conversion clause"
    assert report["plan"]["count"] > 0
    assert final.content != data
    assert hashlib.sha256(final.content).hexdigest() == report["output_validation"]["final_sha256"]
    assert not final_xml.xpath("//w:ins | //w:del", namespaces=ns)
    assert xml_of(redline.content).xpath("//w:ins | //w:del", namespaces=ns)
    assert client.get(root + "/download/final", headers=BOB).status_code == 404
    markdown = client.get(root + "/download/report_md", headers=ALICE)
    assert markdown.status_code == 200
    assert "用户关闭的规则" in markdown.text
