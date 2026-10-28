"""End-to-end tests for the revision review API against a real artifact."""

from __future__ import annotations

import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from lxml import etree
from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.docx import DOCUMENT, Q, ZipLimits, _read_parts

REAL = Path("var/recall-first-evaluation/p6-dev-round1-01/D01")

requires_real = pytest.mark.skipif(not (REAL / "report.json").is_file(),
                                   reason="real D01 evaluation artifact unavailable")


@pytest.fixture()
def seeded(tmp_path):
    """An app seeded with the real D01 report and its revision artifact."""
    data = tmp_path / "data"
    data.mkdir()
    app = create_app(data_dir=data)
    store = app.state.store
    redline = (REAL / "working_redline").read_bytes()
    final = (REAL / "working_final").read_bytes()
    batch = store.create_batch(owner="dev", ruleset_version="v1",
                               uploads=[("D01.docx", redline)])
    lease = store.claim(lease_seconds=300)
    assert lease is not None
    source = data / "report.json"
    report = json.loads(source.read_text()) if source.is_file() else json.loads((REAL / "report.json").read_text())
    artifacts = {"working_redline": data / "working_redline", "working_final": data / "working_final"}
    artifacts["working_redline"].write_bytes(redline)
    artifacts["working_final"].write_bytes(final)
    store.finish(lease["id"], lease["fencing_token"], report=report, artifacts=artifacts)
    client = TestClient(app)
    return client, batch, lease["id"]


def _headers() -> dict:
    return {"X-FundLex-User": "dev"}


def _accepted_paragraph_text(path: Path) -> list[str]:
    root = etree.fromstring(_read_parts(str(path), ZipLimits())[DOCUMENT])
    texts = []
    for paragraph in root.iter(Q("p")):
        parts = []
        for node in paragraph.iter():
            if node.tag != Q("t") or any(parent.tag == Q("del") for parent in node.iterancestors()):
                continue
            parts.append(node.text or "")
        texts.append("".join(parts))
    return texts


@requires_real
def test_revisions_endpoint_returns_html_and_mapping(seeded):
    client, batch, doc = seeded
    response = client.get(f"/api/batches/{batch['id']}/documents/{doc}/revisions",
                          headers=_headers())
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["revision_count"] == 17
    assert body["meta"]["has_toc"] is True
    assert '<ins class="rev' in body["html"]
    assert body["revisions"][0]["rule_id"]
    assert body["revisions"][0]["mapped"] is True


@requires_real
def test_accept_all_publishes_downloadable_selected_final(seeded):
    client, batch, doc = seeded
    response = client.post(f"/api/batches/{batch['id']}/documents/{doc}/accept-all",
                           headers=_headers())
    assert response.status_code == 200, response.text
    assert len(response.json()["accepted"]) == 17
    download = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_final",
                          headers=_headers())
    assert download.status_code == 200
    assert download.content[:2] == b"PK"
    assert "selected_final" in download.headers["content-disposition"]
    # A human selection is still a working file; it never upgrades the
    # persisted delivery status or turns an incomplete contract into a final.
    document = client.app.state.store.get_document("dev", batch["id"], doc)
    assert document["delivery_status"] == "incomplete"
    from fundlex.edit_summary import archive_entry
    root, path = archive_entry("selected_final", "合同", ".docx",
                               delivery_status=document["delivery_status"])
    assert root == "工作文件（未完成）" and "人工选择" in path


@requires_real
def test_decisions_endpoint_accepts_partial_rejection(seeded):
    client, batch, doc = seeded
    response = client.post(f"/api/batches/{batch['id']}/documents/{doc}/decisions",
                           headers=_headers(),
                           json={"decisions": [{"del_id": 1, "decision": "reject"},
                                               {"del_id": 3, "decision": "accept"}]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert 1 in body["rejected"]
    assert body["accepted"]


@requires_real
def test_decisions_publish_a_matching_redline(seeded):
    """A review that rejects something ships both revision files."""
    client, batch, doc = seeded
    response = client.post(f"/api/batches/{batch['id']}/documents/{doc}/decisions",
                           headers=_headers(),
                           json={"decisions": [{"del_id": 1, "decision": "reject"},
                                               {"del_id": 3, "decision": "accept"}]})
    assert response.status_code == 200, response.text

    redline = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_redline",
                         headers=_headers())
    assert redline.status_code == 200, redline.text
    names = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_final",
                       headers=_headers())
    assert names.status_code == 200, names.text
    # The engine's own revision file is still served alongside the selection.
    engine = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/working_redline",
                        headers=_headers())
    assert engine.status_code == 200, engine.text
    # The two revision files are distinct artifacts, and neither is the contract.
    assert redline.content not in (names.content, engine.content)
    assert names.headers["etag"] == response.json()["sha256"]
    assert redline.headers["etag"] == response.json()["selected_redline_sha256"]

    # Downloaded bytes are the source of truth for the response/DOCX contract.
    with tempfile.TemporaryDirectory() as directory:
        final_path = Path(directory) / "selected-final.docx"
        redline_path = Path(directory) / "selected-redline.docx"
        final_path.write_bytes(names.content)
        redline_path.write_bytes(redline.content)
        assert _accepted_paragraph_text(redline_path) == _accepted_paragraph_text(final_path)


@requires_real
def test_decisions_that_reject_nothing_ship_no_second_revision_file(seeded):
    """Accepting every edit matches the engine result, so only one file is needed."""
    client, batch, doc = seeded
    total = len(client.get(f"/api/batches/{batch['id']}/documents/{doc}/revisions",
                           headers=_headers()).json()["revisions"])
    assert total, "the fixture must offer at least one revision"
    response = client.post(f"/api/batches/{batch['id']}/documents/{doc}/decisions",
                           headers=_headers(),
                           json={"decisions": [{"del_id": 2 * n - 1, "decision": "accept"}
                                               for n in range(1, total + 1)]})
    assert response.status_code == 200, response.text
    assert response.json()["rejected"] == []
    selected = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_redline",
                          headers=_headers())
    assert selected.status_code == 404, selected.text


@requires_real
def test_accept_all_publishes_no_extra_redline(seeded):
    """Accepting everything matches the engine result, so nothing extra is shipped."""
    client, batch, doc = seeded
    assert client.post(f"/api/batches/{batch['id']}/documents/{doc}/accept-all",
                       headers=_headers()).status_code == 200
    response = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_redline",
                          headers=_headers())
    # The engine redline already records that choice; a duplicate would confuse.
    assert response.status_code == 404, response.text
    engine = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/working_redline",
                        headers=_headers())
    assert engine.status_code == 200, engine.text


@requires_real
def test_decisions_rejects_invalid_verdict(seeded):
    client, batch, doc = seeded
    response = client.post(f"/api/batches/{batch['id']}/documents/{doc}/decisions",
                           headers=_headers(),
                           json={"decisions": [{"del_id": 1, "decision": "maybe"}]})
    assert response.status_code == 422


@requires_real
def test_decisions_rejects_unknown_even_duplicate_and_conflicting_ids(seeded):
    client, batch, doc = seeded
    url = f"/api/batches/{batch['id']}/documents/{doc}/decisions"
    cases = [
        ([{"del_id": 9999, "decision": "reject"}], "SELECTION_UNKNOWN_REVISION"),
        ([{"del_id": 2, "decision": "reject"}], "SELECTION_INS_ID_NOT_ALLOWED"),
        ([{"del_id": 9999, "decision": "reject"}, {"del_id": 2, "decision": "accept"}],
         "SELECTION_UNKNOWN_REVISION"),
        ([{"del_id": 1, "decision": "reject"}, {"del_id": 1, "decision": "reject"}],
         "SELECTION_DUPLICATE_DECISION"),
        ([{"del_id": 1, "decision": "reject"}, {"del_id": 1, "decision": "accept"}],
         "SELECTION_CONFLICTING_DECISIONS"),
    ]
    for decisions, code in cases:
        response = client.post(url, headers=_headers(), json={"decisions": decisions})
        assert response.status_code == 422, response.text
        assert response.json()["detail"] == code


@requires_real
def test_selection_epoch_rejects_stale_request_and_deletes_old_selected_redline(seeded):
    client, batch, doc = seeded
    view_url = f"/api/batches/{batch['id']}/documents/{doc}/revisions"
    url = f"/api/batches/{batch['id']}/documents/{doc}/decisions"
    view = client.get(view_url, headers=_headers()).json()
    wrong_manifest = client.post(url, headers=_headers(), json={
        "decisions": [{"del_id": 1, "decision": "reject"}],
        "selection_epoch": view["selection_epoch"],
        "manifest_hash": "0" * 64,
    })
    assert wrong_manifest.status_code == 409
    assert wrong_manifest.json()["detail"] == "SELECTION_MANIFEST_CONFLICT"
    first = client.post(url, headers=_headers(), json={
        "decisions": [{"del_id": 1, "decision": "reject"}],
        "selection_epoch": view["selection_epoch"],
        "manifest_hash": view["manifest_hash"],
    })
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["selection_epoch"] == 1
    assert body["selected_redline_sha256"]
    assert client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_redline",
                      headers=_headers()).status_code == 200
    stale = client.post(url, headers=_headers(), json={
        "decisions": [{"del_id": 3, "decision": "accept"}],
        "selection_epoch": 0,
        "manifest_hash": view["manifest_hash"],
    })
    assert stale.status_code == 409
    assert stale.json()["detail"] == "SELECTION_EPOCH_CONFLICT"
    latest = client.get(view_url, headers=_headers()).json()
    accepts = client.post(url, headers=_headers(), json={
        "decisions": [{"del_id": item["del_id"], "decision": "accept"}
                      for item in latest["revisions"]],
        "selection_epoch": latest["selection_epoch"],
        "manifest_hash": latest["manifest_hash"],
    })
    assert accepts.status_code == 200, accepts.text
    assert accepts.json()["selected_redline_sha256"] is None
    assert client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_redline",
                      headers=_headers()).status_code == 404


@requires_real
def test_concurrent_selection_requests_only_one_epoch_wins(seeded):
    client, batch, doc = seeded
    view = client.get(f"/api/batches/{batch['id']}/documents/{doc}/revisions",
                      headers=_headers()).json()
    url = f"/api/batches/{batch['id']}/documents/{doc}/decisions"
    payload = {"decisions": [{"del_id": 1, "decision": "reject"}],
               "selection_epoch": view["selection_epoch"],
               "manifest_hash": view["manifest_hash"]}
    def submit():
        return client.post(url, headers=_headers(), json=payload)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: submit(), range(2)))
    assert sorted(response.status_code for response in responses) == [200, 409]
    assert [response.json().get("detail") for response in responses if response.status_code == 409] == ["SELECTION_EPOCH_CONFLICT"]


@requires_real
def test_selected_final_requires_authentication(seeded):
    client, batch, doc = seeded
    response = client.get(f"/api/batches/{batch['id']}/documents/{doc}/download/selected_final")
    assert response.status_code in {401, 403, 404}


@requires_real
def test_revisions_are_owner_scoped(seeded):
    client, batch, doc = seeded
    response = client.get(f"/api/batches/{batch['id']}/documents/{doc}/revisions",
                          headers={"X-FundLex-User": "someone-else"})
    assert response.status_code == 404
