"""Guide API contract: version listing, configuration, recall binding and downloads.

The guide store, the task store and the recall delivery gate are the real
implementations under test; only DOCX fixtures and the scripted processor are
synthetic, and no model call is made.
"""
from __future__ import annotations

import io
import json

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex import guide_store
from fundlex.guide import GUIDE_SCHEMA_VERSION
from fundlex.jobs import Worker

ALICE = {"X-FundLex-User": "alice"}
BOB = {"X-FundLex-User": "bob"}


def docx_bytes(label: str) -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def parsed_document() -> dict:
    return {"schema_version": GUIDE_SCHEMA_VERSION, "parser_version": "guide-parse-1",
            "prompt_versions": {"guide_parse": "guide_parse_v1", "guide_verify": "guide_verify_v1"},
            "groups": [{"rule_id": "G01", "title": "释义-份额类别定义", "section_hint": "释义",
                        "operations": [{"op": "append", "new_text": "新增内容"},
                                       {"op": "replace", "old_text": "旧文", "new_text": "新文"},
                                       {"op": "delete", "old_text": "删除内容"}]}],
            "validation": {"errors": [], "warnings": [], "coverage_gaps": []}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    # create_app's module default must never touch the user's runtime.
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    from fundlex.api import create_app
    return TestClient(create_app(tmp_path / "state"))


def parsed_custom(client, *, label: str = "自定义指引", owner: str = "alice") -> dict:
    """Insert a parsed custom guide directly through the guide store."""
    store = client.app.state.store
    version = guide_store.create_custom_version(store, owner, "custom-guide.docx", docx_bytes(label))
    finished = guide_store.finish_guide_job(store, version["job_id"], document=parsed_document())
    assert finished["version"]["status"] == "parsed"
    return finished["version"]


def manifest(data: bytes) -> list[dict]:
    return [{"client_id": "c1", "name": "合同.docx", "size": len(data)}]


def test_builtin_guide_is_listed_and_current_by_default(client):
    response = client.get("/api/guides", headers=ALICE)
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [guide_store.BUILTIN_GUIDE_ID]
    builtin = items[0]
    document = guide_store.guide_document(client.app.state.store, guide_store.BUILTIN_GUIDE_ID)
    assert builtin["built_in"] is True and builtin["current"] is True
    assert builtin["status"] == "released" and builtin["qualification_status"] == "frozen_builtin"
    assert builtin["groups"] == len(document["groups"]) and isinstance(builtin["issues"], int)
    assert len(builtin["document_sha256"]) == 64 and builtin["rules_sha256"] == builtin["document_sha256"]
    assert "objects" not in json.dumps(builtin) and "path" not in builtin
    settings = client.get("/api/settings/guide", headers=ALICE).json()
    assert settings["engine_id"] == "recall_first"
    assert settings["current"]["id"] == guide_store.BUILTIN_GUIDE_ID
    assert settings["current"]["current"] is True
    assert [item["id"] for item in settings["available"]] == [guide_store.BUILTIN_GUIDE_ID]
    capabilities = client.get("/api/capabilities", headers=ALICE).json()
    assert capabilities["engine_id"] == "recall_first"
    assert capabilities["guide"] == {"version_id": guide_store.BUILTIN_GUIDE_ID, "built_in": True,
                                     "status": "released", "rules_sha256": builtin["rules_sha256"],
                                     "groups": builtin["groups"], "filename": builtin["filename"]}
    # Every existing capabilities key stays in place.
    assert capabilities["ruleset_version"] == "v1" and capabilities["actions_total"] > 0
    assert [item["id"] for item in client.get("/api/guides", headers=BOB).json()["items"]] == \
        [guide_store.BUILTIN_GUIDE_ID]


def test_guide_upload_parse_switch_and_reset(client):
    data = docx_bytes("指引正文示例")
    uploaded = client.post("/api/guides", headers=ALICE, files={"file": ("custom-guide.docx", data)})
    assert uploaded.status_code == 201
    version = uploaded.json()["version"]
    custom_id = version["id"]
    assert version["built_in"] is False and version["status"] == "uploaded"
    assert version["filename"] == "custom-guide.docx" and version["current"] is False
    assert version["groups"] == 0 and version["issues"] == 0
    assert "objects" not in json.dumps(version)
    listed = client.get("/api/guides", headers=ALICE).json()["items"]
    assert [item["id"] for item in listed] == [guide_store.BUILTIN_GUIDE_ID, custom_id]
    assert [item["current"] for item in listed] == [True, False]
    # An uploaded-but-unparsed version can never become a task guide.
    refused = client.put("/api/settings/guide", headers=ALICE, json={"version_id": custom_id})
    assert refused.status_code == 409 and refused.json()["detail"] == "GUIDE_NOT_ENABLEABLE"
    # The parse worker closes the queued job (real store transition, scripted document).
    store = client.app.state.store
    job = guide_store.claim_guide_job(store)
    assert job["guide_version_id"] == custom_id
    finished = guide_store.finish_guide_job(store, job["id"], document=parsed_document())
    assert finished["version"]["status"] == "parsed"
    detail = client.get(f"/api/guides/{custom_id}", headers=ALICE).json()
    assert detail["status"] == "parsed" and detail["current"] is False
    assert detail["issues_detail"] == {"errors": [], "warnings": [], "coverage_gaps": []}
    assert detail["issues"] == 0
    assert detail["rules_overview"] == [{"rule_id": "G01", "title": "释义-份额类别定义", "section_hint": "释义",
                                         "operations": {"append": 1, "replace": 1, "delete": 1, "noop": 0}}]
    assert detail["prompt_versions"] == {"guide_parse": "guide_parse_v1", "guide_verify": "guide_verify_v1"}
    switched = client.put("/api/settings/guide", headers=ALICE, json={"version_id": custom_id})
    assert switched.status_code == 200
    assert switched.json()["current"]["id"] == custom_id
    assert switched.json()["current"] == client.get("/api/settings/guide", headers=ALICE).json()["current"]
    assert [item["current"] for item in switched.json()["available"]] == [False, True]
    # Resetting accepts null, empty and the built-in aliases.
    for body in ({"version_id": None}, {"version_id": ""}, {"version_id": "builtin"},
                 {"version_id": guide_store.BUILTIN_GUIDE_ID}, {}):
        result = client.put("/api/settings/guide", headers=ALICE, json=body)
        assert result.status_code == 200, result.text
        assert result.json()["current"]["id"] == guide_store.BUILTIN_GUIDE_ID
    # Owner isolation: another identity cannot see, enable, parse or download it.
    assert client.get(f"/api/guides/{custom_id}", headers=BOB).status_code == 404
    assert client.put("/api/settings/guide", headers=BOB, json={"version_id": custom_id}).status_code == 404
    assert client.post(f"/api/guides/{custom_id}/parse", headers=BOB).status_code == 404
    assert client.get(f"/api/guides/{custom_id}/source", headers=BOB).status_code == 404
    assert [item["id"] for item in client.get("/api/guides", headers=BOB).json()["items"]] == \
        [guide_store.BUILTIN_GUIDE_ID]
    assert client.put("/api/settings/guide", headers=ALICE, json={"version_id": "missing-version"}).status_code == 404


def test_guide_source_and_rules_access(client):
    data = docx_bytes("来源核验指引")
    version = client.post("/api/guides", headers=ALICE,
                          files={"file": ("source.docx", data)}).json()["version"]
    # The frozen built-in guide has no user-supplied DOCX to hand back.
    builtin_source = client.get(f"/api/guides/{guide_store.BUILTIN_GUIDE_ID}/source", headers=ALICE)
    assert builtin_source.status_code == 404
    assert builtin_source.json()["detail"] == "BUILTIN_SOURCE_UNAVAILABLE"
    # Rules stay unavailable until parsing produced a document.
    assert client.get(f"/api/guides/{version['id']}/rules", headers=ALICE).status_code == 404
    source = client.get(f"/api/guides/{version['id']}/source", headers=ALICE)
    assert source.status_code == 200 and source.content == data
    assert source.headers["Cache-Control"] == "private, no-store"
    assert "source.docx" in source.headers["content-disposition"]
    builtin_rules = client.get(f"/api/guides/{guide_store.BUILTIN_GUIDE_ID}/rules", headers=ALICE)
    assert builtin_rules.status_code == 200
    assert builtin_rules.json()["schema_version"] == GUIDE_SCHEMA_VERSION
    store = client.app.state.store
    job = guide_store.claim_guide_job(store)
    guide_store.finish_guide_job(store, job["id"], document=parsed_document())
    parsed_rules = client.get(f"/api/guides/{version['id']}/rules", headers=ALICE)
    assert parsed_rules.status_code == 200 and parsed_rules.json()["groups"][0]["rule_id"] == "G01"


def test_guide_upload_rejects_unsupported_and_broken_files(client):
    valid = docx_bytes("指引")
    assert client.post("/api/guides", headers=ALICE,
                       files={"file": ("guide.pdf", valid)}).status_code == 415
    assert client.post("/api/guides", headers=ALICE,
                       files={"file": ("guide.docx", b"%PDF-1.7 not a package")}).status_code == 415
    assert client.post("/api/guides", headers=ALICE,
                       files={"file": ("guide.docx", b"")}).status_code == 413
    assert [item["id"] for item in client.get("/api/guides", headers=ALICE).json()["items"]] == \
        [guide_store.BUILTIN_GUIDE_ID]


def test_guide_parse_endpoint_requeues_owner_versions_only(client):
    data = docx_bytes("重试指引")
    version = client.post("/api/guides", headers=ALICE,
                          files={"file": ("retry.docx", data)}).json()["version"]
    store = client.app.state.store
    # One failed attempt is retryable: the version is parse_failed, not failed.
    job = guide_store.claim_guide_job(store)
    failed = guide_store.finish_guide_job(store, job["id"], error_code="GUIDE_SOURCE_EMPTY")
    assert failed["version"]["status"] == "parse_failed"
    requeued = client.post(f"/api/guides/{version['id']}/parse", headers=ALICE)
    assert requeued.status_code == 202
    assert requeued.json()["version"]["status"] == "parse_failed"
    with store._connect() as db:
        queued = db.execute("SELECT COUNT(*) FROM guide_jobs WHERE guide_version_id=? AND status='queued'",
                            (version["id"],)).fetchone()[0]
    assert queued == 1
    # Claiming consumes the requeued job; a leased version cannot queue twice.
    assert guide_store.claim_guide_job(store)["guide_version_id"] == version["id"]
    assert client.post(f"/api/guides/{version['id']}/parse", headers=ALICE).status_code == 409
    # A parsed version can be re-parsed on demand.
    parsed = parsed_custom(client)
    assert client.post(f"/api/guides/{parsed['id']}/parse", headers=ALICE).status_code == 202
    # The built-in guide is released and never re-queued through this route.
    assert client.post(f"/api/guides/{guide_store.BUILTIN_GUIDE_ID}/parse", headers=ALICE).status_code == 403
    assert client.post("/api/guides/unknown-version/parse", headers=ALICE).status_code == 404


def test_recall_task_creation_binds_guide_snapshot(client):
    data = docx_bytes("合同正文示例")
    files = manifest(data)
    created = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "recall-1"},
                          json={"name": "召回任务", "engine_id": "recall_first", "files": files})
    assert created.status_code == 201, created.text
    task = created.json()
    builtin = guide_store.get_version(client.app.state.store, "alice", guide_store.BUILTIN_GUIDE_ID)
    assert task["engine_id"] == "recall_first"
    assert task["guide_snapshot"] == {"version_id": guide_store.BUILTIN_GUIDE_ID,
                                      "rules_sha256": builtin["rules_sha256"]}
    detail = client.get(f"/api/tasks/{task['id']}", headers=ALICE).json()
    assert detail["engine_id"] == "recall_first" and detail["guide_snapshot"] == task["guide_snapshot"]
    # Idempotent replay returns the same task; a different binding conflicts.
    again = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "recall-1"},
                        json={"name": "召回任务", "engine_id": "recall_first", "files": files})
    assert again.status_code == 201 and again.json()["id"] == task["id"]
    conflict = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "recall-1"},
                           json={"name": "召回任务", "ruleset_version": "v1", "files": files})
    assert conflict.status_code == 409
    # The configured custom guide is what a new task binds without an explicit id.
    custom = parsed_custom(client)
    assert client.put("/api/settings/guide", headers=ALICE, json={"version_id": custom["id"]}).status_code == 200
    bound = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "recall-2"},
                        json={"name": "召回任务二", "engine_id": "recall_first", "files": files})
    assert bound.status_code == 201
    assert bound.json()["guide_snapshot"] == {"version_id": custom["id"],
                                              "rules_sha256": custom["rules_sha256"]}
    # An explicit visible version overrides the current configuration.
    explicit = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "recall-3"},
                           json={"name": "召回任务三", "engine_id": "recall_first",
                                 "guide_version_id": custom["id"], "files": files})
    assert explicit.status_code == 201
    assert explicit.json()["guide_snapshot"]["version_id"] == custom["id"]
    pinned = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "recall-4"},
                         json={"name": "召回任务四", "engine_id": "recall_first",
                               "guide_version_id": guide_store.BUILTIN_GUIDE_ID, "files": files})
    assert pinned.status_code == 201
    assert pinned.json()["guide_snapshot"]["version_id"] == guide_store.BUILTIN_GUIDE_ID


def test_task_creation_engine_and_ruleset_contract(client):
    files = manifest(docx_bytes("合同正文示例"))
    both = client.post("/api/tasks", headers=ALICE,
                       json={"name": "冲突", "engine_id": "recall_first", "ruleset_version": "v1", "files": files})
    assert both.status_code == 422 and both.json()["detail"] == "ENGINE_CONFLICT"
    neither = client.post("/api/tasks", headers=ALICE, json={"name": "缺失", "files": files})
    assert neither.status_code == 422 and neither.json()["detail"] == "ENGINE_OR_RULESET_REQUIRED"
    unknown = client.post("/api/tasks", headers=ALICE,
                          json={"name": "未知引擎", "engine_id": "v9", "files": files})
    assert unknown.status_code == 422
    missing = client.post("/api/tasks", headers=ALICE,
                          json={"name": "未知指引", "engine_id": "recall_first",
                                "guide_version_id": "missing-version", "files": files})
    assert missing.status_code == 404
    # A visible but unparsed custom guide is refused until parsing finishes.
    store = client.app.state.store
    version = guide_store.create_custom_version(store, "alice", "pending.docx", docx_bytes("未解析指引"))
    not_ready = client.post("/api/tasks", headers=ALICE,
                            json={"name": "未就绪", "engine_id": "recall_first",
                                  "guide_version_id": version["id"], "files": files})
    assert not_ready.status_code == 409 and not_ready.json()["detail"] == "GUIDE_NOT_READY"
    # Another owner's custom version is not visible.
    other = guide_store.create_custom_version(store, "bob", "bob.docx", docx_bytes("他人指引"))
    hidden = client.post("/api/tasks", headers=ALICE,
                         json={"name": "越权", "engine_id": "recall_first",
                               "guide_version_id": other["id"], "files": files})
    assert hidden.status_code == 404
    # The legacy ruleset path stays unchanged.
    legacy = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "legacy-1"},
                         json={"name": "旧任务", "ruleset_version": "v1", "files": files})
    assert legacy.status_code == 201
    assert legacy.json()["engine_id"] == ""
    assert legacy.json()["guide_snapshot"] == {"version_id": "", "rules_sha256": ""}


def test_recall_document_surface_and_working_downloads(client):
    data = docx_bytes("合同正文示例")
    task_id = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "recall-surface"},
                          json={"name": "召回交付", "engine_id": "recall_first",
                                "files": manifest(data)}).json()["id"]
    upload = client.post(f"/api/tasks/{task_id}/uploads", headers=ALICE,
                         data={"client_ids": json.dumps(["c1"])},
                         files=[("files", ("合同.docx", data))])
    assert upload.status_code == 200 and upload.json()["receipts"][0]["status"] == "accepted"

    def processor(source, output, ruleset):
        from fundlex.docx import generate_unchanged_artifacts, validate_edit_plan
        plan = validate_edit_plan(source, [], {})
        validation = generate_unchanged_artifacts(source, plan, output / "working_redline.docx",
                                                  output / "working_final.docx")
        return {"engine_id": "recall_first", "schema_version": "3", "execution_mode": "delivery",
                "qualification_status": "eligible", "delivery_status": "incomplete",
                "windows": [{"window": "W1", "rounds": [{"round": 0}, {"round": 1, "stage": "inventory"}]}],
                "targets": [{"target_id": "W1:T001", "status": "planned"},
                            {"target_id": "W1:T002", "status": "satisfied"},
                            {"target_id": "W1:T003", "status": "unresolved"}],
                "unresolved": [{"kind": "target", "rule_id": "G01", "reason": "RECALL_TARGET_UNRESOLVED"}],
                "output_validation": {"kind": "recall_working_edits",
                                      "checks": [*validation.checks, "actual_content_verification"],
                                      "final_sha256": validation.final_sha256,
                                      "redline_sha256": validation.redline_sha256},
                "artifacts": {"working_final": "working_final.docx", "working_redline": "working_redline.docx"}}

    store = client.app.state.store
    assert Worker(store, processor).run_once()
    builtin = guide_store.get_version(store, "alice", guide_store.BUILTIN_GUIDE_ID)
    documents = client.get(f"/api/tasks/{task_id}/documents", headers=ALICE).json()
    item = documents["items"][0]
    assert item["delivery_status"] == "incomplete"
    assert item["phase"] == "inventory"
    assert item["target_counts"] == {"total": 3, "completed": 2, "unresolved": 1}
    assert item["guide_snapshot"] == {"version_id": guide_store.BUILTIN_GUIDE_ID,
                                      "rules_sha256": builtin["rules_sha256"]}
    assert {"working_final", "working_redline"}.issubset(item["downloads"])
    assert "final" not in item["downloads"] and "redline" not in item["downloads"]
    # The whitelist serves the incomplete working pair and keeps refusing final names.
    working = client.get(item["downloads"]["working_final"], headers=ALICE)
    assert working.status_code == 200 and working.content == data
    assert client.get(item["downloads"]["working_redline"], headers=ALICE).status_code == 200
    refused = client.get(f"/api/batches/{item['batch_id']}/documents/{item['document_id']}/download/final",
                         headers=ALICE)
    assert refused.status_code == 404
    # The batch surface exposes the same cheap counters, never the full report.
    batch = client.get(f"/api/batches/{item['batch_id']}", headers=ALICE).json()
    assert batch["documents"][0]["target_counts"] == {"total": 3, "completed": 2, "unresolved": 1}
    assert batch["documents"][0]["phase"] == "inventory"
    assert "windows" not in batch["documents"][0] and "targets" not in batch["documents"][0]
    # A non-recall document keeps the legacy listing shape untouched.
    legacy_task = client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": "legacy-surface"},
                              json={"name": "旧任务", "ruleset_version": "v1",
                                    "files": manifest(data)}).json()["id"]
    assert client.post(f"/api/tasks/{legacy_task}/uploads", headers=ALICE,
                       data={"client_ids": json.dumps(["c1"])},
                       files=[("files", ("合同.docx", data))]).status_code == 200
    legacy_item = client.get(f"/api/tasks/{legacy_task}/documents", headers=ALICE).json()["items"][0]
    assert "target_counts" not in legacy_item and "phase" not in legacy_item
    legacy_batch = client.get(f"/api/batches/{legacy_item['batch_id']}", headers=ALICE).json()
    assert "target_counts" not in legacy_batch["documents"][0]
