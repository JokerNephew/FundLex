"""Focused persistence and orchestration checks for the Feishu channel."""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from docx import Document

from fundlex.integrations.feishu.events import MessageEvent
from fundlex.integrations.feishu.service import FeishuService
from fundlex.integrations.store import IntegrationConflict, IntegrationStore
from fundlex.store import RunStore


def docx_bytes(text: str = "公开合同") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


class FakeClient:
    def __init__(self, data: bytes):
        self.data = data
        self.downloads = 0
        self.sent: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, dict]] = []
        self.fail_send = False

    def send_card(self, receive_id, card):
        if self.fail_send:
            raise RuntimeError("SEND_FAILED")
        self.sent.append((receive_id, card))
        return f"msg-{len(self.sent)}"

    def reply_card(self, message_id, card):
        return self.send_card(message_id, card)

    def update_card(self, message_id, card):
        self.updated.append((message_id, card))

    def download_message_resource(self, message_id, file_key, resource_type="file"):
        self.downloads += 1
        return self.data, "合同.docx"


class FakeTaskService:
    def __init__(self):
        self.created = []
        self.uploaded = []
        self.sealed = []
        self.fail_upload_once = False
        self._tasks = {}

    def create_task(self, owner, name, files, *, idempotency_key=None):
        self.created.append((owner, name, files, idempotency_key))
        if idempotency_key in self._tasks:
            return self._tasks[idempotency_key]
        task = {"id": "task-1", "status": "queued", "total": len(files), "name": name}
        self._tasks[idempotency_key] = task
        return task

    def upload_files(self, owner, task_id, files):
        self.uploaded.append((owner, task_id, files))
        if self.fail_upload_once:
            self.fail_upload_once = False
            raise RuntimeError("UPLOAD_FAILED")
        return {"receipts": []}

    def seal_task(self, owner, task_id):
        self.sealed.append((owner, task_id))
        return {"status": "queued"}

    def get_task(self, owner, task_id):
        return {"id": task_id, "name": "合同", "status": "completed", "total": 1,
                "completed": 1, "failed": 0, "delivery_counts": {"complete": 1}}


def message(event_id: str, *, text: str = "", message_type: str = "text", content=None,
            tenant: str = "tenant-a", open_id: str = "ou-a", chat_id: str = "oc-a") -> dict:
    return {"header": {"event_id": event_id, "event_type": "im.message.receive_v1", "tenant_key": tenant},
            "event": {"sender": {"sender_id": {"open_id": open_id}},
                      "message": {"message_id": f"msg-{event_id}", "chat_id": chat_id,
                                   "chat_type": "p2p", "message_type": message_type,
                                   "content": content or {"text": text}}}}


def service_fixture(tmp_path: Path, *, data: bytes | None = None):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    code = integration.create_binding_code("feishu", "owner-a")["code"]
    integration.consume_binding_code("feishu", "tenant-a", "ou-a", code)
    client = FakeClient(data or docx_bytes())
    tasks = FakeTaskService()
    service = FeishuService(store, tasks, tasks, client, base_url="https://fundlex.test")
    return service, integration, tasks, client


def test_binding_codes_are_one_time_and_unbinding_allows_rebind(tmp_path):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    code = integration.create_binding_code("feishu", "owner-a")["code"]
    assert integration.consume_binding_code("feishu", "tenant-a", "ou-a", code) == "owner-a"
    with pytest.raises(IntegrationConflict, match="FEISHU_BINDING_CODE_CONSUMED"):
        integration.consume_binding_code("feishu", "tenant-a", "ou-a", code)

    other = integration.create_binding_code("feishu", "owner-b")["code"]
    with pytest.raises(IntegrationConflict, match="FEISHU_IDENTITY_ALREADY_BOUND"):
        integration.consume_binding_code("feishu", "tenant-a", "ou-a", other)

    integration.revoke_user_binding("feishu", "owner-a")
    rebound = integration.create_binding_code("feishu", "owner-b")["code"]
    assert integration.consume_binding_code("feishu", "tenant-a", "ou-a", rebound) == "owner-b"
    assert integration.identity("feishu", "tenant-a", "ou-a")["user_id"] == "owner-b"

    integration.revoke_user_binding("feishu", "owner-b")
    owner_a_again = integration.create_binding_code("feishu", "owner-a")["code"]
    integration.consume_binding_code("feishu", "tenant-a", "ou-b", owner_a_again)
    integration.revoke_user_binding("feishu", "owner-a")
    owner_b_again = integration.create_binding_code("feishu", "owner-b")["code"]
    with pytest.raises(IntegrationConflict, match="FEISHU_REBIND_CONFLICT"):
        integration.consume_binding_code("feishu", "tenant-a", "ou-b", owner_b_again)


def test_event_duplicate_and_payload_conflict_are_fail_closed(tmp_path):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    payload = {"message": "same"}
    assert integration.record_event("feishu", "evt-1", "message", payload) is True
    assert integration.record_event("feishu", "evt-1", "message", payload) is False
    with pytest.raises(IntegrationConflict, match="INTEGRATION_EVENT_PAYLOAD_CONFLICT"):
        integration.record_event("feishu", "evt-1", "message", {"message": "changed"})


def test_multiple_files_are_staged_once_and_duplicate_delivery_is_ignored(tmp_path):
    service, integration, _, client = service_fixture(tmp_path)
    first = message("evt-file-1", message_type="file", content={"file_key": "key-1"})
    second = message("evt-file-2", message_type="file", content={"file_key": "key-2"})
    service.handle_message_event(first)
    service.handle_message_event(second)
    service.handle_message_event(first)
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None
    files = integration.draft_files(draft["id"])
    assert len(files) == 2 and all(item["status"] == "accepted" for item in files)
    assert client.downloads == 2


def test_submit_failure_keeps_draft_retryable_and_task_creation_is_idempotent(tmp_path):
    service, integration, tasks, client = service_fixture(tmp_path)
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None
    tasks.fail_upload_once = True
    event = MessageEvent("evt-confirm", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                         "p2p", "msg-confirm", "text", {"text": "确认"})
    assert service.submit_draft(event, "owner-a") == "failed"
    retryable = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert retryable is not None and retryable["status"] == "COLLECTING"
    assert service.submit_draft(event, "owner-a") == "submitted"
    assert len(tasks.created) == 2
    assert tasks.created[0][3] == tasks.created[1][3]
    assert tasks.sealed == [("owner-a", "task-1")]
    assert integration.draft(retryable["id"])["status"] == "SUBMITTED"
    assert client.sent


def test_card_confirmation_reports_failure_and_duplicate_action_is_not_replayed(tmp_path):
    service, integration, tasks, client = service_fixture(tmp_path)
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None
    tasks.fail_upload_once = True
    action = {"header": {"event_id": "card-evt-1"},
              "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                        "context": {"open_chat_id": "oc-a", "open_message_id": "card-msg"},
                        "action": {"value": {"command": "confirm", "draft_id": draft["id"]}}}}
    assert "失败" in service.handle_card_action_event(action)
    sent_after_first = len(client.sent)
    assert "已处理" in service.handle_card_action_event(action)
    assert len(client.sent) == sent_after_first
    assert integration.health()["dead_events"] == 0


def test_status_card_send_failure_leaves_durable_outbox_recovery(tmp_path):
    service, integration, tasks, client = service_fixture(tmp_path)
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None
    client.fail_send = True
    event = MessageEvent("evt-confirm", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                         "p2p", "msg-confirm", "text", {"text": "确认"})
    assert service.submit_draft(event, "owner-a") == "submitted"
    channel = integration.channels()
    assert len(channel) == 1 and channel[0]["task_id"] == "task-1"
    assert integration.draft(draft["id"])["status"] == "SUBMITTED"
    with integration.store._connect() as db:
        pending = db.execute("SELECT status FROM integration_outbox WHERE dedupe_key=?", ("task_status:task-1:queued",)).fetchone()
    assert pending["status"] == "pending"
    client.fail_send = False
    assert service.send_outbox() == 1
    assert integration.channels()[0]["card_message_id"]


def test_outbox_fencing_rejects_stale_sender(tmp_path):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    assert integration.add_outbox("task_status", "task-1", {"task_id": "task-1"}, "dedupe-1")
    first = integration.pending_outbox()
    assert len(first) == 1
    item = first[0]
    integration.finish_outbox(item["id"], fencing_token=item["fencing_token"] + 1, error_code="STALE")
    assert integration.pending_outbox() == []
    with store._connect() as db:
        row = db.execute("SELECT status,last_error_code FROM integration_outbox WHERE id=?", (item["id"],)).fetchone()
    assert row["status"] == "sending" and row["last_error_code"] is None


def test_owner_and_chat_scope_prevents_cross_chat_draft_access(tmp_path):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    draft = integration.create_draft("tenant-a", "ou-a", "chat-a", "owner-a", "A")
    assert integration.active_draft("tenant-a", "ou-a", "chat-b") is None
    assert integration.active_draft("tenant-a", "ou-b", "chat-a") is None
    assert integration.draft(draft["id"])["owner_user_id"] == "owner-a"
