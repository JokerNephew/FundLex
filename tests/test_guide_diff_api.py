"""Guide diff endpoint and enable-gate API contract (store is real, no model)."""
from __future__ import annotations

import io
import json

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex import guide_store
from fundlex.guide import GUIDE_SCHEMA_VERSION

ALICE = {"X-FundLex-User": "alice"}
BOB = {"X-FundLex-User": "bob"}


def docx_bytes(label: str) -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(label)
    document.save(stream)
    return stream.getvalue()


def document(rules, *, clean=True, errors=None, findings=None) -> dict:
    return {"schema_version": GUIDE_SCHEMA_VERSION, "parser_version": "guide-parse-1",
            "prompt_versions": {"guide_parse": "guide_parse_v1", "guide_verify": "guide_verify_v1"},
            "groups": rules,
            "validation": {"errors": errors or [], "warnings": [], "coverage_gaps": [],
                           "clean": clean, "rounds": 1,
                           "verification": {"findings": findings or [], "invalid_findings": 0}}}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    from fundlex.api import create_app
    return TestClient(create_app(tmp_path / "state"))


def parsed_version(client, label: str, rules, *, owner: str = "alice", **kwargs) -> dict:
    store = client.app.state.store
    version = guide_store.create_custom_version(store, owner, f"{label}.docx", docx_bytes(label))
    job = guide_store.claim_guide_job(store)
    return guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                        document=document(rules, **kwargs))["version"]


def test_diff_endpoint_contract_and_determinism(client):
    first = parsed_version(client, "v1", [{"rule_id": "G01", "title": "旧", "requirement": "要求",
                                           "operations": [{"op": "append", "new_text": "甲"}]}])
    second = parsed_version(client, "v2", [{"rule_id": "G01", "title": "新", "requirement": "要求",
                                            "operations": [{"op": "append", "new_text": "甲"}]},
                                           {"rule_id": "G02", "title": "加",
                                            "old_text_variants": ["旧文A", "旧文B"]}])
    url = f"/api/guides/{second['id']}/diff"
    response = client.get(url, params={"against": first["id"]}, headers=ALICE)
    assert response.status_code == 200
    payload = response.json()
    assert payload["version_id"] == second["id"] and payload["against"] == first["id"]
    diff = payload["diff"]
    assert diff["algorithm"] == "guide-diff-v1"
    assert diff["summary"] == {"rules_before": 1, "rules_after": 2, "added": 1, "removed": 0,
                               "changed": 1, "groups_added": 1, "groups_removed": 0,
                               "groups_order_changed": False, "meta_fields_changed": 0,
                               "identical": False}
    assert [item["rule_id"] for item in diff["rules"]["added"]] == ["G02"]
    assert diff["rules"]["changed"][0]["fields"]["title"] == {"old": "旧", "new": "新"}
    assert diff["validation"]["before"]["clean"] is True
    # Deterministic: repeated calls return byte-identical bodies.
    again = client.get(url, params={"against": first["id"]}, headers=ALICE)
    assert again.content == response.content


def test_diff_endpoint_guards(client):
    first = parsed_version(client, "v1", [{"rule_id": "G01", "title": "旧"}])
    unparsed = guide_store.create_custom_version(client.app.state.store, "alice",
                                                 "pending.docx", docx_bytes("pending"))
    # Missing/empty against -> 422.
    missing = client.get(f"/api/guides/{first['id']}/diff", headers=ALICE)
    assert missing.status_code == 422
    # Unparsed side -> 404.
    unready = client.get(f"/api/guides/{first['id']}/diff",
                         params={"against": unparsed["id"]}, headers=ALICE)
    assert unready.status_code == 404
    # Unknown version -> 404; cross-owner -> 404 (never leaks existence).
    assert client.get("/api/guides/nope/diff", params={"against": first["id"]},
                      headers=ALICE).status_code == 404
    assert client.get(f"/api/guides/{first['id']}/diff",
                      params={"against": guide_store.BUILTIN_GUIDE_ID},
                      headers=BOB).status_code == 404
    # Built-in participates as either side.
    ok = client.get(f"/api/guides/{first['id']}/diff",
                    params={"against": guide_store.BUILTIN_GUIDE_ID}, headers=ALICE)
    assert ok.status_code == 200
    assert ok.json()["diff"]["summary"]["rules_before"] > 0


def test_enable_gate_api_surfaces_certification_reason(client):
    # Upload -> quality channel passes -> certified -> enableable (201/202 flow).
    upload = client.post("/api/guides", headers=ALICE,
                         files={"file": ("guide.docx", docx_bytes("指引"))})
    assert upload.status_code == 201
    item = upload.json()["version"]
    assert item["certified"] is False and item["enable_block_reason"] == "GUIDE_NOT_PARSED"
    store = client.app.state.store
    job = guide_store.claim_guide_job(store)
    guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                 document=document([{"rule_id": "G01", "title": "规则"}]))
    detail = client.get(f"/api/guides/{item['id']}", headers=ALICE).json()
    assert detail["certified"] is True and detail["enable_block_reason"] is None
    assert detail["qualification_status"] == "certified"
    enabled = client.put("/api/settings/guide", headers=ALICE, json={"version_id": item["id"]})
    assert enabled.status_code == 200
    assert enabled.json()["current"]["id"] == item["id"]


def test_quality_failure_visible_in_api_and_enable_blocked(client):
    upload = client.post("/api/guides", headers=ALICE,
                         files={"file": ("dirty.docx", docx_bytes("脏指引"))})
    version_id = upload.json()["version"]["id"]
    store = client.app.state.store
    job = guide_store.claim_guide_job(store)
    guide_store.finish_guide_job(store, job["id"], job["fencing_token"],
                                 document=document([{"rule_id": "G01", "title": "规则"}],
                                                   clean=False,
                                                   errors=[{"code": "RULE_OP_UNKNOWN",
                                                            "detail": "无法识别的操作"}]))
    detail = client.get(f"/api/guides/{version_id}", headers=ALICE).json()
    assert detail["status"] == "failed"
    assert detail["certified"] is False
    assert detail["enable_block_reason"] == "GUIDE_NOT_PARSED"
    assert detail["issues_detail"]["error_code"] == "GUIDE_VALIDATION_UNCLEAN"
    assert detail["issues_detail"]["errors"][0]["code"] == "RULE_OP_UNKNOWN"
    assert detail["issues_detail"]["detail"]
    blocked = client.put("/api/settings/guide", headers=ALICE, json={"version_id": version_id})
    assert blocked.status_code == 409
    # Listing surfaces the same gate so the UI can grey the button out.
    items = client.get("/api/guides", headers=ALICE).json()["items"]
    row = next(item for item in items if item["id"] == version_id)
    assert row["enable_block_reason"] == "GUIDE_NOT_PARSED"
    assert row["review"] is None


def test_uncertified_enable_conflict_code(client):
    parsed = parsed_version(client, "legacy", [{"rule_id": "G01", "title": "规则"}])
    with client.app.state.store._connect() as db:
        db.execute("UPDATE guide_versions SET qualification_status='not_run' WHERE id=?",
                   (parsed["id"],))
    detail = client.get(f"/api/guides/{parsed['id']}", headers=ALICE).json()
    assert detail["certified"] is False
    assert detail["enable_block_reason"] == "GUIDE_NOT_CERTIFIED"
    blocked = client.put("/api/settings/guide", headers=ALICE, json={"version_id": parsed["id"]})
    assert blocked.status_code == 409
    assert json.loads(blocked.content)["detail"] == "GUIDE_NOT_CERTIFIED"
