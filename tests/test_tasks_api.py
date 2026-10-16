"""Task API integration against isolated SQLite and synthetic DOCX packages.

These checks exercise persistence, queue controls and owner authorization.
Report classification values are explicit fixtures, not model evaluation.
"""
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import zipfile

import pytest
from fastapi.testclient import TestClient


ALICE = {"X-FundLex-User": "alice"}
BOB = {"X-FundLex-User": "bob"}


def package(label="fixture"):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", f"<document>{label}</document>")
    return output.getvalue()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # create_app's module default must never touch the user's runtime.
    monkeypatch.setenv("FUNDLEX_DATA_DIR", str(tmp_path / "module-default"))
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "dev")
    from fundlex.api import create_app
    return TestClient(create_app(tmp_path / "task-store"))


def create(client, entries, name="季度合同处理", key="task-key"):
    return client.post("/api/tasks", headers=ALICE | {"Idempotency-Key": key},
                       json={"name": name, "engine_id": "recall_first", "files": entries})


def manifest(count, data):
    return [{"client_id": f"file-{i}", "name": f"合同{i:03}.docx", "size": len(data)} for i in range(count)]


def upload(client, task, entries, data, owner=ALICE):
    return client.post(f"/api/tasks/{task}/uploads", headers=owner,
                       data={"client_ids": json.dumps([d["client_id"] for d in entries])},
                       files=[("files", (d["name"], data)) for d in entries])


def test_manifest_segmented_upload_idempotency_and_refresh(client):
    data = package()
    files = manifest(25, data)
    result = create(client, files)
    assert result.status_code == 201
    task = result.json()["id"]
    assert result.json()["total"] == 25 and result.json()["uploaded"] == 0
    assert create(client, files).json()["id"] == task
    assert create(client, files, name="changed").status_code == 409
    assert upload(client, task, files, data).status_code == 413
    first = upload(client, task, files[:20], data).json()
    assert first["task"]["uploaded"] == 20
    assert len({r["batch_id"] for r in first["receipts"]}) == 1
    again = upload(client, task, files[:20], data).json()
    assert {r["status"] for r in again["receipts"]} == {"already_accepted"}
    assert [r["document_id"] for r in first["receipts"]] == [r["document_id"] for r in again["receipts"]]
    final = upload(client, task, files[20:], data).json()
    assert final["task"]["uploaded"] == 25
    assert final["receipts"][0]["batch_id"] != first["receipts"][0]["batch_id"]
    assert client.post(f"/api/tasks/{task}/seal", headers=ALICE).json()["upload_status"] == "complete"
    docs = client.get(f"/api/tasks/{task}/documents", headers=ALICE).json()
    assert docs["total"] == 25 and len({d["client_id"] for d in docs["items"]}) == 25
    assert all(d["upload_status"] == "accepted" and d["report_url"] is None for d in docs["items"])
    assert client.get("/api/tasks", headers=ALICE).json()["total"] == 1
    assert client.app.state.store.claim() is not None


def test_per_file_rejection_retry_and_manifest_total_preserved(client):
    good, bad = package(), b"x" * len(package())
    files = manifest(3, good)
    task = create(client, files).json()["id"]
    rejected = upload(client, task, files[:1], bad).json()
    assert rejected["receipts"][0]["error_code"] == "INVALID_DOCX_PACKAGE"
    assert rejected["task"]["rejected"] == 1
    assert upload(client, task, files[1:2], good).json()["task"]["uploaded"] == 1
    sealed = client.post(f"/api/tasks/{task}/seal", headers=ALICE).json()
    assert sealed["total"] == 3 and sealed["upload_status"] == "sealed_incomplete"
    summary = client.get(f"/api/tasks/{task}/report", headers=ALICE).text
    assert "尚未上传：1" in summary and "接收失败：1" in summary and "INVALID_DOCX_PACKAGE" in summary
    assert upload(client, task, files[:1], good).json()["receipts"][0]["status"] == "accepted"
    changed = package("different")
    receipt = upload(client, task, files[:1], changed).json()["receipts"][0]
    assert receipt["error_code"] == "UPLOAD_IDENTITY_CONFLICT"
    docs = client.get(f"/api/tasks/{task}/documents", headers=ALICE).json()["items"]
    assert docs[0]["upload_status"] == "accepted" and docs[0]["error_code"] is None
    unknown = dict(files[2], client_id="unknown")
    assert upload(client, task, [unknown], good).json()["receipts"][0]["error_code"] == "MANIFEST_ENTRY_NOT_FOUND"


def test_pause_whole_task_and_new_segment_inherits_pause(client):
    data, files = package(), manifest(3, package())
    task = create(client, files).json()["id"]
    first = upload(client, task, files[:1], data).json()["receipts"][0]
    assert client.post(f"/api/tasks/{task}/pause", headers=ALICE).json()["status"] == "paused"
    second = upload(client, task, files[1:2], data).json()["receipts"][0]
    assert client.app.state.store.claim() is None
    for bid in (first["batch_id"], second["batch_id"]):
        assert client.app.state.store.get_batch("alice", bid)["status"] == "paused"
    assert client.post(f"/api/tasks/{task}/resume", headers=ALICE).json()["status"] == "queued"
    job = client.app.state.store.claim()
    client.app.state.store.retry(job["id"], job["fencing_token"], error_code="MODEL_GLOBAL_CALL_BUDGET_EXCEEDED")
    state = client.get(f"/api/tasks/{task}", headers=ALICE).json()
    assert state["status"] == "paused" and state["pause_reason"] == "MODEL_GLOBAL_CALL_BUDGET_EXCEEDED"
    assert client.app.state.store.claim() is None
    upload(client, task, files[2:], data)
    assert client.app.state.store.claim() is None
    # Legacy control endpoints also preserve the parent's atomic controls.
    client.post(f"/api/batches/{second['batch_id']}/resume", headers=ALICE)
    assert client.get(f"/api/tasks/{task}", headers=ALICE).json()["status"] == "queued"


def test_results_four_dimensions_filtering_paging_and_summary(client):
    data, files = package(), manifest(5, package())
    task = create(client, files).json()["id"]
    upload(client, task, files[:4], data)
    store = client.app.state.store
    statuses = [("eligible", "incomplete", False, None), ("excluded_by_fund_type", "not_generated", False, None),
                ("failed", "not_generated", True, "QUALIFICATION_EVIDENCE_MISSING"), ("eligible", "incomplete", False, None)]
    for eligibility, delivery, failed, code in statuses:
        job = store.claim()
        report = {"qualification_status": eligibility, "delivery_status": delivery, "actions": [
            {"status": "failed", "failure_reason": "TARGET_SCOPE_UNRESOLVED", "candidates": [{"status": "failed", "reason": "RELEASE_GATE_CLOSED"}]}]}
        store.finish(job["id"], job["fencing_token"], report=report, artifacts={}, failed=failed, error_code=code)
    root = f"/api/tasks/{task}/documents"
    result = client.get(root, params={"eligibility": "eligible", "delivery_status": "incomplete", "job_status": "succeeded", "error_code": "RELEASE_GATE_CLOSED", "page_size": 1, "page": 2}, headers=ALICE).json()
    assert result["total"] == 2 and len(result["items"]) == 1
    assert result["items"][0]["reason_codes"] == ["RELEASE_GATE_CLOSED", "TARGET_SCOPE_UNRESOLVED"]
    assert {r["code"]: r["count"] for r in result["reason_options"]}["RELEASE_GATE_CLOSED"] == 4
    assert client.get(root, params={"q": "003", "sort": "name_desc"}, headers=ALICE).json()["total"] == 1
    assert client.get(root, params={"upload_status": "pending"}, headers=ALICE).json()["total"] == 1
    assert client.get(root, params={"sort": "exceptions"}, headers=ALICE).json()["items"][0]["job_status"] == "failed"
    assert client.get(root, params={"sort": "status"}, headers=ALICE).json()["items"][0]["job_status"] == "not_started"
    assert client.get("/api/tasks", params={"sort": "exceptions"}, headers=ALICE).status_code == 422
    state = client.get(f"/api/tasks/{task}", headers=ALICE).json()
    assert state["total"] == 5 and state["completed"] == 4 and state["failed"] == 1 and state["status"] == "uploading"
    assert state["delivery_counts"]["incomplete"] == 2
    report = client.get(f"/api/tasks/{task}/report", headers=ALICE).text
    assert "RELEASE_GATE_CLOSED" in report and "'failed': 4" in report


def test_retired_engine_task_row_is_flagged_legacy(client):
    # Production history keeps first-class task rows written by the retired
    # ruleset engine (engine_id=''). They must be flagged read-only, otherwise
    # the UI would offer controls the runtime no longer honours.
    store = client.app.state.store
    seeded = store.create_batch(owner="alice", ruleset_version="v2", ruleset_sha256="0" * 64,
                                uploads=[("retired.docx", package())])
    with store._connect() as db:
        db.execute("""INSERT INTO tasks(id,owner,name,ruleset_version,ruleset_sha256,engine_id,
            guide_version_id,guide_rules_sha256,idempotency_key,request_hash,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                   ("retired-task-1", "alice", "历史任务", "v2", "0" * 64, "", "", "",
                    None, "hash", 1.0, 1.0))
        db.execute("""INSERT INTO task_batches VALUES(?,?)""",
                   ("retired-task-1", seeded["id"]))
    detail = client.get("/api/tasks/retired-task-1", headers=ALICE).json()
    assert detail["legacy"] is True
    assert detail["engine_id"] == "" and detail["ruleset_version"] == "v2"


def test_identity_isolation_capabilities_and_historical_mapping(client, monkeypatch):
    data, files = package(), manifest(1, package())
    task = create(client, files).json()["id"]
    result = upload(client, task, files, data).json()["receipts"][0]
    for suffix in ("", "/documents", "/report"):
        assert client.get(f"/api/tasks/{task}{suffix}", headers=BOB).status_code == 404
    for operation in ("pause", "resume", "seal"):
        assert client.post(f"/api/tasks/{task}/{operation}", headers=BOB).status_code == 404
    assert upload(client, task, files, data, owner=BOB).status_code == 404
    assert client.get(f"/api/tasks/{task}/documents?page=0", headers=BOB).status_code == 404
    assert client.get("/api/tasks", headers=BOB).json()["items"] == []
    assert client.get(f"/api/batches/{result['batch_id']}/documents/{result['document_id']}/report", headers=BOB).status_code == 404
    assert client.get("/api/capabilities").status_code == 401
    caps = client.get("/api/capabilities", headers=ALICE).json()
    engine = caps["engine"]
    assert engine["id"] == "recall_first" and engine["rule_source"] == "guide"
    assert engine["actions_total"] == int((engine["guide"] or {}).get("groups") or 0)
    assert caps["upload_limits"]["max_request_files"] == 20
    # Legacy batches can no longer be created over HTTP; the historical read and
    # control mapping they exercise is still supported, so seed one directly.
    seeded = client.app.state.store.create_batch(owner="alice", ruleset_version="v1", ruleset_sha256="0" * 64,
                                                 uploads=[("legacy.docx", data)])
    legacy = "legacy-" + seeded["id"]
    assert client.get(f"/api/tasks/{legacy}", headers=ALICE).json()["legacy"] is True
    assert client.post(f"/api/tasks/{legacy}/pause", headers=ALICE).json()["status"] == "paused"
    assert client.post(f"/api/tasks/{legacy}/resume", headers=ALICE).json()["status"] == "queued"
    assert client.post(f"/api/tasks/{legacy}/seal", headers=ALICE).status_code == 409
    assert upload(client, legacy, files, data).status_code == 409
    assert client.get(f"/api/tasks/{legacy}/documents", headers=BOB).status_code == 404
    # Legacy history is flagged for the read-only UI.
    assert client.get(f"/api/tasks/{legacy}", headers=ALICE).json()["legacy"] is True
    assert client.get("/api/tasks", headers=ALICE).json()["total"] == 2
    monkeypatch.setenv("FUNDLEX_AUTH_MODE", "production")
    assert client.get("/api/capabilities", headers=ALICE).status_code == 503
    assert client.get("/api/tasks", headers=ALICE).status_code == 503


def test_all_api_responses_disable_owner_metadata_caching(client):
    data, files = package(), manifest(1, package())
    task = create(client, files).json()["id"]
    for url, owner, status in [
        ("/api/tasks", {}, 401),
        (f"/api/tasks/{task}", BOB, 404),
        ("/api/capabilities", ALICE, 200),
        (f"/api/tasks/{task}/documents", ALICE, 200),
        ("/api/nonexistent", ALICE, 404),
    ]:
        response = client.get(url, headers=owner)
        assert response.status_code == status
        assert response.headers["Cache-Control"] == "private, no-store"
    assert "no-store" not in client.get("/static/app.js").headers.get("Cache-Control", "")


def test_concurrent_same_file_receipt_and_commit_cleanup_safety(client, monkeypatch):
    data, files = package(), manifest(2, package())
    task = create(client, files).json()["id"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: upload(client, task, files[:1], data).json(), range(2)))
    assert {r["receipts"][0]["status"] for r in results} == {"accepted", "already_accepted"}
    assert len({r["receipts"][0]["document_id"] for r in results}) == 1
    store = client.app.state.store
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 1
        original = store.object_path(db.execute("SELECT input_key FROM documents").fetchone()[0])
    assert len(list((store.objects / "inputs").glob("*.docx"))) == 1
    real_unlink = Path.unlink
    def deny_redundant_cleanup(path, *args, **kwargs):
        if path.parent == original.parent and path != original:
            raise PermissionError("injected unreferenced cleanup failure")
        return real_unlink(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", deny_redundant_cleanup)
    with pytest.raises(PermissionError):
        store_task = client.app.state.tasks
        store_task.uploads("alice", task, [{"client_id": f["client_id"], "name": f["name"], "data": data, "error_code": None} for f in files])
    assert original.read_bytes() == data
    assert client.get(f"/api/tasks/{task}", headers=ALICE).json()["uploaded"] == 2
    with store._connect() as db:
        for row in db.execute("SELECT input_key FROM documents"):
            assert store.object_path(row["input_key"]).read_bytes() == data


def test_paused_inflight_completion_preserves_pause_and_future_uploads(client):
    data, files = package(), manifest(2, package())
    task = create(client, files).json()["id"]
    upload(client, task, files[:1], data)
    store = client.app.state.store
    job = store.claim()
    client.post(f"/api/tasks/{task}/pause", headers=ALICE)
    store.finish(job["id"], job["fencing_token"], report={"qualification_status": "excluded_by_fund_type", "delivery_status": "not_generated"}, artifacts={})
    assert store.get_batch("alice", job["batch_id"])["status"] == "completed"
    assert client.get(f"/api/tasks/{task}", headers=ALICE).json()["status"] == "paused"
    upload(client, task, files[1:], data)
    assert store.claim() is None
    client.post(f"/api/tasks/{task}/resume", headers=ALICE)
    assert store.claim() is not None


def test_last_inflight_contract_completion_finishes_paused_task(client):
    data, files = package(), manifest(1, package())
    task = create(client, files).json()["id"]
    upload(client, task, files, data)
    store = client.app.state.store
    job = store.claim()
    assert client.post(f"/api/tasks/{task}/pause", headers=ALICE).json()["status"] == "paused"
    store.finish(job["id"], job["fencing_token"], report={"qualification_status": "eligible", "delivery_status": "incomplete"}, artifacts={})
    result = client.get(f"/api/tasks/{task}", headers=ALICE).json()
    assert result["status"] == "completed" and result["completed"] == result["total"] == 1
    assert result["delivery_counts"] == {"incomplete": 1}


@pytest.mark.parametrize("changes", [{"size": True}, {"size": 0}, {"name": "../secret.docx"}, {"name": " "}, {"extra": 1}])
def test_invalid_manifest_rejected(client, changes):
    files = manifest(1, package())
    files[0].update(changes)
    assert create(client, files).status_code == 422


def test_task_archive_authorization_names_and_integrity(client, tmp_path):
    from fundlex.jobs import Worker
    data = package()
    files = manifest(3, data)
    files[1]["name"] = files[0]["name"]  # repeated filenames must not overwrite ZIP entries
    task = create(client, files).json()["id"]
    url = f"/api/tasks/{task}/download/all"
    assert client.get(url, headers=BOB).status_code == 404
    assert client.get(url, headers=ALICE).status_code == 409
    upload(client, task, files[:2], data)
    store = client.app.state.store
    worker = Worker(store, lambda *_: {"qualification_status": "excluded_by_fund_type",
                                      "delivery_status": "not_generated"})
    assert worker.run_until_idle() == 2
    response = client.get(url, headers=ALICE)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert len([n for n in archive.namelist() if n.endswith("report_json.json")]) == 2
        assert "not_started" in archive.read("结果清单.csv").decode("utf-8-sig")
        assert "结果总览.md" in archive.namelist()
        overview = archive.read("结果总览.md").decode("utf-8")
        assert "每份合同的修改情况" in overview
        # The version column states where the delivered final comes from, and the
        # note explains what each value means.
        assert "| 合同文件 | 交付完整性 | 版本 | 修改处数 | 涉及条款 |" in overview
        assert "引擎全量" in overview
        assert "（全量痕迹版）" in overview and "（选择修订版）" in overview
    documents = client.get(f"/api/tasks/{task}/documents", headers=ALICE).json()["items"]
    doc = documents[0]
    path, _ = store.get_artifact("alice", doc["batch_id"], doc["document_id"], "report_json")
    path.write_bytes(b"tampered")
    assert client.get(url, headers=ALICE).status_code == 409


def test_task_archive_groups_final_and_notes_by_folder(client, tmp_path):
    """The ZIP mirrors the offline package: 结果总览.md + 结果清单.csv +
    最终版（接受修订后）/<合同>.docx + 逐份修改说明/<合同>/（全量痕迹版）.docx."""
    from fundlex.edit_summary import archive_entry

    final_root = "最终版（接受修订后）"
    final_root_name, final_path = archive_entry("final", "甲合同", ".docx")
    assert final_root_name == final_root and final_path == f"{final_root}/甲合同.docx"
    _, working_path = archive_entry("working_final", "甲合同", ".docx")
    assert working_path == f"{final_root}/甲合同.docx"
    _, redline_path = archive_entry("redline", "甲合同", ".docx")
    assert redline_path == "逐份修改说明/甲合同/甲合同（全量痕迹版）.docx"
    _, working_redline_path = archive_entry("working_redline", "甲合同", ".docx")
    assert working_redline_path == redline_path
    # A reviewed contract ships a second revision file, named for what it holds.
    _, selected_redline_path = archive_entry("selected_redline", "甲合同", ".docx")
    assert selected_redline_path == "逐份修改说明/甲合同/甲合同（选择修订版）.docx"
    # Reports stay with the notes, never in the final folder.
    notes_root, report_path = archive_entry("report_md", "甲合同", ".md")
    assert notes_root == "逐份修改说明" and report_path == "逐份修改说明/甲合同/report_md.md"


def test_archive_entry_places_a_selected_final_in_the_final_folder():
    """The user's selection fills the final slot, but has its own revision file."""
    from fundlex.edit_summary import archive_entry

    assert archive_entry("selected_final", "甲合同", ".docx") == \
        archive_entry("final", "甲合同", ".docx")
    assert archive_entry("selected_redline", "甲合同", ".docx") != \
        archive_entry("redline", "甲合同", ".docx")


def test_archive_kinds_ships_two_revision_files_only_after_a_choice():
    from fundlex.edit_summary import archive_kinds

    # No review: one final version and the engine's own revision file.
    assert sorted(archive_kinds({"final": "u", "redline": "u", "report_md": "u"})) == \
        ["final", "redline", "report_md"]
    # Reviewed and something was turned down: both revision files, plus the
    # selected final version.
    chosen = archive_kinds({"final": "u", "redline": "u", "report_md": "u",
                            "selected_final": "u", "selected_redline": "u"})
    assert sorted(chosen) == ["redline", "report_md", "selected_final", "selected_redline"]
    # An incomplete run keeps its working final when nothing was reviewed.
    assert sorted(archive_kinds({"working_final": "u", "working_redline": "u"})) == \
        ["working_final", "working_redline"]
    # A reviewed incomplete run prefers the selection for the final version while
    # still shipping the engine's revision file.
    assert sorted(archive_kinds({"working_final": "u", "working_redline": "u",
                                 "selected_final": "u"})) == \
        ["selected_final", "working_redline"]


def test_multiple_tasks_really_execute_concurrently(client):
    import threading
    import time
    from fundlex.jobs import Worker
    data = package()
    files = manifest(1, data)
    first = create(client, files, name="first", key="first").json()["id"]
    upload(client, first, files, data)
    # The second task is created after the first already owns a running job.
    store = client.app.state.store
    entered = threading.Barrier(3)
    release, stop = threading.Event(), threading.Event()
    def processor(*_):
        entered.wait(timeout=10)
        assert release.wait(10)
        return {"qualification_status": "excluded_by_fund_type", "delivery_status": "not_generated"}
    worker = Worker(store, processor)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(worker.run_forever, poll_seconds=0.02, concurrency=2, stop_event=stop)
        try:
            deadline = time.monotonic() + 5
            while client.get(f"/api/tasks/{first}", headers=ALICE).json()["status"] != "running":
                assert time.monotonic() < deadline
                time.sleep(0.02)
            second_response = create(client, files, name="second", key="second")
            assert second_response.status_code == 201
            second = second_response.json()["id"]
            upload(client, second, files, data)
            entered.wait(timeout=10)
            for task_id in (first, second):
                assert client.get(f"/api/tasks/{task_id}", headers=ALICE).json()["status"] == "running"
            release.set()
            deadline = time.monotonic() + 10
            while any(client.get(f"/api/tasks/{t}", headers=ALICE).json()["status"] != "completed"
                      for t in (first, second)):
                assert time.monotonic() < deadline
                time.sleep(0.02)
        finally:
            release.set()
            stop.set()
        future.result(timeout=10)


def test_scheduler_prefers_different_task_across_upload_batches(client):
    data, files = package(), manifest(3, package())
    first = create(client, files, key="large").json()["id"]
    for entry in files:
        upload(client, first, [entry], data)
    store = client.app.state.store
    claimed = store.claim()
    assert claimed
    second = create(client, files[:1], key="small").json()["id"]
    receipt = upload(client, second, files[:1], data).json()["receipts"][0]
    next_job = store.claim()
    assert next_job["id"] == receipt["document_id"]
