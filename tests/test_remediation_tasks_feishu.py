"""FL-D466/467/470: Feishu owner binding, event recovery and send-all paging."""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from docx import Document

from fundlex import guide_store
from fundlex.application import TaskApplicationService
from fundlex.integrations.feishu.events import MessageEvent
from fundlex.integrations.feishu.service import FeishuService
from fundlex.integrations.store import IntegrationConflict, IntegrationStore
from fundlex.store import NotFound, RunStore
from fundlex.tasks import TaskStore


def docx_bytes(text: str = "公开合同") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


def message(event_id: str, *, text: str = "", message_type: str = "text", content=None,
            tenant: str = "tenant-a", open_id: str = "ou-a", chat_id: str = "oc-a") -> dict:
    return {"header": {"event_id": event_id, "event_type": "im.message.receive_v1", "tenant_key": tenant},
            "event": {"sender": {"sender_id": {"open_id": open_id}},
                      "message": {"message_id": f"msg-{event_id}", "chat_id": chat_id,
                                  "chat_type": "p2p", "message_type": message_type,
                                  "content": content or {"text": text}}}}


class FakeClient:
    def __init__(self, data: bytes | None = None):
        self.data = data or docx_bytes()
        self.remote_name = "合同.docx"
        self.downloads = 0
        self.sent: list[tuple[str, dict]] = []
        self.files: list[tuple[str, str, int]] = []
        self.updated: list[tuple[str, dict]] = []

    def send_card(self, receive_id, card):
        self.sent.append((receive_id, card))
        return f"msg-{len(self.sent)}"

    def update_card(self, message_id, card):
        self.updated.append((message_id, card))

    def download_message_resource(self, message_id, file_key, resource_type="file"):
        self.downloads += 1
        return self.data, self.remote_name

    def send_file(self, receive_id, filename, data):
        self.files.append((receive_id, filename, len(data)))
        return f"file-{len(self.files)}"

    def pin_message(self, message_id):
        return None

    def unpin_message(self, message_id):
        return None


def real_service(tmp_path: Path):
    store = RunStore(tmp_path / "state")
    guide_store.ensure_builtin_guide(store)
    integration = IntegrationStore(store)
    client = FakeClient()
    tasks = TaskStore(store)
    app_service = TaskApplicationService(store, tasks)
    service = FeishuService(store, tasks, app_service, client, base_url="https://fundlex.test")
    return store, integration, tasks, service, client


def bind(integration: IntegrationStore, owner: str, open_id: str = "ou-a") -> None:
    code = integration.create_binding_code("feishu", owner)["code"]
    integration.consume_binding_code("feishu", "tenant-a", open_id, code)


def start_and_send(service, client, *, event_prefix: str, open_id="ou-a", chat_id="oc-a", text="合同修订"):
    service.handle_message_event(message(f"{event_prefix}-start", text=text, open_id=open_id, chat_id=chat_id))
    service.handle_message_event(message(f"{event_prefix}-file", message_type="file",
                                         content={"file_key": f"{event_prefix}-key"},
                                         open_id=open_id, chat_id=chat_id))


def confirm_action(draft_id: str, *, event_id: str, open_id="ou-a", chat_id="oc-a") -> dict:
    return {"header": {"event_id": event_id},
            "event": {"operator": {"tenant_key": "tenant-a", "open_id": open_id},
                      "context": {"open_chat_id": chat_id, "open_message_id": "card-msg"},
                      "action": {"value": {"command": "confirm", "draft_id": draft_id}}}}


def test_rebinding_cancels_old_draft_and_blocks_old_confirmation(tmp_path):
    store, integration, tasks, service, client = real_service(tmp_path)
    bind(integration, "owner-a")
    start_and_send(service, client, event_prefix="a")
    old = integration.active_draft("tenant-a", "ou-a", "oc-a", owner_user_id="owner-a")
    assert old is not None and old["owner_user_id"] == "owner-a"
    old_card_message = old["card_message_id"]

    integration.revoke_user_binding("feishu", "owner-a")
    assert integration.draft(old["id"])["status"] == "CANCELLED"
    assert integration.active_draft("tenant-a", "ou-a", "oc-a", owner_user_id="owner-a") is None
    assert integration.draft_files(old["id"]) == []

    bind(integration, "owner-b")
    before_tasks = len(tasks.list("owner-b")["items"])
    result = service.handle_card_action_event(confirm_action(old["id"], event_id="old-confirm"))
    assert "过期" in result
    assert len(tasks.list("owner-b")["items"]) == before_tasks == 0
    assert not any(message_id == old_card_message for message_id, _ in client.updated)

    # B starts and submits their own file under a fresh draft.
    start_and_send(service, client, event_prefix="b", open_id="ou-a", chat_id="oc-a")
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a", owner_user_id="owner-b")
    assert draft is not None and draft["owner_user_id"] == "owner-b"
    service.handle_message_event(message("b-confirm", text="确认"))
    tasks_b = tasks.list("owner-b")["items"]
    assert len(tasks_b) == 1
    channel = integration.channels()[0]
    assert channel["owner_user_id"] == "owner-b"
    with pytest.raises(NotFound):
        tasks.get("owner-a", tasks_b[0]["id"])

    # The cancelled A draft cannot be resurrected by a new event.
    assert integration.draft(old["id"])["status"] == "CANCELLED"
    assert integration.draft_files(old["id"]) == []


def test_normal_a_and_b_submit_their_own_tasks(tmp_path):
    store, integration, tasks, service, client = real_service(tmp_path)
    bind(integration, "owner-a", "ou-a")
    bind(integration, "owner-b", "ou-b")

    start_and_send(service, client, event_prefix="a", open_id="ou-a", chat_id="oc-a")
    service.handle_message_event(message("a-confirm", text="确认", open_id="ou-a", chat_id="oc-a"))
    start_and_send(service, client, event_prefix="b", open_id="ou-b", chat_id="oc-b")
    service.handle_message_event(message("b-confirm", text="确认", open_id="ou-b", chat_id="oc-b"))

    a_tasks = tasks.list("owner-a")["items"]
    b_tasks = tasks.list("owner-b")["items"]
    assert len(a_tasks) == len(b_tasks) == 1 and a_tasks[0]["id"] != b_tasks[0]["id"]
    channels = {channel["owner_user_id"]: channel for channel in integration.channels()}
    assert set(channels) == {"owner-a", "owner-b"}
    assert channels["owner-a"]["task_id"] == a_tasks[0]["id"]
    assert channels["owner-b"]["task_id"] == b_tasks[0]["id"]
    assert tasks.get("owner-a", a_tasks[0]["id"])["name"]
    with pytest.raises(NotFound):
        tasks.get("owner-a", b_tasks[0]["id"])


def test_revoked_channel_and_pending_outbox_are_not_delivered_to_the_new_owner(tmp_path):
    store, integration, tasks, service, client = real_service(tmp_path)
    bind(integration, "owner-a")
    start_and_send(service, client, event_prefix="a")
    service.handle_message_event(message("a-confirm", text="确认"))
    channel = integration.channels()[0]
    assert channel["owner_user_id"] == "owner-a"
    with store._connect() as db:
        pending = db.execute("SELECT COUNT(*) AS n FROM integration_outbox WHERE status IN ('pending','retry_wait')").fetchone()["n"]
    assert pending >= 1

    integration.revoke_user_binding("feishu", "owner-a")
    with store._connect() as db:
        statuses = {row["status"] for row in db.execute(
            "SELECT status FROM integration_outbox WHERE aggregate_id=?", (channel["task_id"],))}
    assert statuses and statuses <= {"dead"}
    assert integration.pending_outbox() == []

    bind(integration, "owner-b")
    sent_before = len(client.sent)
    assert service.send_outbox() == 0
    assert len(client.sent) == sent_before
    service.sync_tasks()
    with store._connect() as db:
        after = db.execute("SELECT COUNT(*) AS n FROM integration_outbox WHERE aggregate_id=? AND status IN ('pending','retry_wait')",
                           (channel["task_id"],)).fetchone()["n"]
    assert after == 0


def test_link_task_rejects_cross_owner_draft_and_channel(tmp_path):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    draft_a = integration.create_draft("tenant-a", "ou-a", "oc-a", "owner-a", "A")
    with pytest.raises(IntegrationConflict, match="FEISHU_TASK_OWNER_MISMATCH"):
        integration.link_task("task-a", draft_a, None, task_owner="owner-b")

    draft_a = integration.draft(draft_a["id"])
    integration.link_task("task-a", draft_a, None, task_owner="owner-a")
    draft_b = integration.create_draft("tenant-a", "ou-b", "oc-b", "owner-b", "B")
    with pytest.raises(IntegrationConflict, match="FEISHU_TASK_OWNER_MISMATCH"):
        integration.link_task("task-a", draft_b, None, task_owner="owner-b")


def test_transient_handler_error_is_redelivered_and_processed_once(tmp_path, monkeypatch):
    store, integration, tasks, service, client = real_service(tmp_path)
    bind(integration, "owner-a")
    service.handle_message_event(message("start", text="合同修订"))
    original = service._handle_message
    calls = {"n": 0}

    def flaky(event):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("temporary object-store error")
        return original(event)

    monkeypatch.setattr(service, "_handle_message", flaky)
    redelivered = message("file-retry", message_type="file", content={"file_key": "key-retry"})
    service.handle_message_event(redelivered)
    with store._connect() as db:
        row = db.execute("SELECT status,attempts FROM integration_events WHERE event_id='file-retry'").fetchone()
    assert row["status"] == "retry_wait" and row["attempts"] == 1
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a", owner_user_id="owner-a")
    assert len(integration.draft_files(draft["id"])) == 0

    assert service.retry_pending_events() == 1
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a", owner_user_id="owner-a")
    assert len(integration.draft_files(draft["id"])) == 1 and client.downloads == 1
    with store._connect() as db:
        row = db.execute("SELECT status,attempts FROM integration_events WHERE event_id='file-retry'").fetchone()
    assert row["status"] == "processed" and row["attempts"] == 2
    service.handle_message_event(redelivered)
    assert client.downloads == 1


def test_interrupted_received_and_dead_events_are_reclaimed_within_attempts(tmp_path):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    payload = {"message": "same"}

    token = integration.begin_event("feishu", "evt-crash", "message", payload, lease_seconds=60)
    assert token is not None
    assert integration.begin_event("feishu", "evt-crash", "message", payload, lease_seconds=60) is None
    with store._connect() as db:
        db.execute("UPDATE integration_events SET lease_until=0 WHERE event_id='evt-crash'")
    token2 = integration.begin_event("feishu", "evt-crash", "message", payload, lease_seconds=60)
    assert token2 is not None and token2 != token
    assert integration.mark_event("feishu", "evt-crash", "processed", fencing_token=token) is False
    assert integration.mark_event("feishu", "evt-crash", "processed", fencing_token=token2) is True
    assert integration.begin_event("feishu", "evt-crash", "message", payload) is None

    # A row left as "received" by an older release is claimable too.
    integration.begin_event("feishu", "evt-received", "message", payload)
    with store._connect() as db:
        db.execute("UPDATE integration_events SET status='received',lease_until=NULL,attempts=0 WHERE event_id='evt-received'")
    assert integration.record_event("feishu", "evt-received", "message", payload) is True

    # Dead events are reclaimed until the bounded attempt count is exhausted.
    integration.begin_event("feishu", "evt-dead", "message", payload)
    with store._connect() as db:
        db.execute("UPDATE integration_events SET status='dead',lease_until=NULL,attempts=1 WHERE event_id='evt-dead'")
    for _ in range(4):
        token = integration.begin_event("feishu", "evt-dead", "message", payload, max_attempts=5)
        assert token is not None
        integration.mark_event("feishu", "evt-dead", "dead", "TEST_FAILURE", fencing_token=token, max_attempts=5)
    with store._connect() as db:
        row = db.execute("SELECT status,attempts FROM integration_events WHERE event_id='evt-dead'").fetchone()
    assert row["status"] == "dead" and row["attempts"] == 5
    assert integration.record_event("feishu", "evt-dead", "message", payload) is False


def test_redelivered_confirm_after_side_effect_does_not_create_second_task(tmp_path, monkeypatch):
    store, integration, tasks, service, client = real_service(tmp_path)
    bind(integration, "owner-a")
    start_and_send(service, client, event_prefix="a")
    original = service._handle_message
    fail_after = {"value": True}

    def after_side_effect(event):
        result = original(event)
        if fail_after["value"]:
            fail_after["value"] = False
            raise OSError("connection dropped after submit")
        return result

    monkeypatch.setattr(service, "_handle_message", after_side_effect)
    confirm = message("confirm-once", text="确认")
    service.handle_message_event(confirm)
    assert len(tasks.list("owner-a")["items"]) == 1
    with store._connect() as db:
        row = db.execute("SELECT status FROM integration_events WHERE event_id='confirm-once'").fetchone()
    assert row["status"] == "retry_wait"

    service.handle_message_event(confirm)
    assert len(tasks.list("owner-a")["items"]) == 1
    assert len(integration.channels()) == 1
    with store._connect() as db:
        row = db.execute("SELECT status,attempts FROM integration_events WHERE event_id='confirm-once'").fetchone()
    assert row["status"] == "processed" and row["attempts"] == 2


class PagedTaskService:
    def __init__(self, count: int):
        self.count = count
        self.fail_doc = ""

    def list_documents(self, owner, task_id, *, page=1, page_size=100, **filters):
        effective = min(int(page_size), 40)
        start = (page - 1) * effective
        items = [{"document_id": f"doc-{index:03}", "name": f"合同{index:03}.docx",
                  "downloads": {"final": f"/api/task/{index}/final"}}
                 for index in range(start, min(start + effective, self.count))]
        return {"items": items, "total": self.count, "page": page, "page_size": effective}

    def artifact(self, owner, task_id, document_id, kind):
        if document_id == self.fail_doc:
            raise OSError("temporary send failure")
        return f"{document_id}-{kind}".encode(), f"{document_id}-{kind}.docx"


class FailingFileClient(FakeClient):
    def __init__(self, fail_contains: str = ""):
        super().__init__()
        self.fail_contains = fail_contains

    def send_file(self, receive_id, filename, data):
        if self.fail_contains and self.fail_contains in filename:
            raise OSError("simulated Feishu upload failure")
        return super().send_file(receive_id, filename, data)


def send_event() -> MessageEvent:
    return MessageEvent("send-all", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                        "p2p", "msg-send", "text", {"text": "发送全部"})


def test_send_all_pages_101_documents_and_reports_each_success(tmp_path):
    store = RunStore(tmp_path / "state")
    tasks = PagedTaskService(101)
    client = FailingFileClient()
    service = FeishuService(store, tasks, tasks, client)
    result = service._send_result_file(send_event(), "owner-a", "revision", "task-101", "all")
    assert result == "已发送 101 个文件。"
    assert len(client.files) == 101
    assert client.files[0][1] == "doc-000-final.docx"
    assert client.files[-1][1] == "doc-100-final.docx"


def test_send_all_does_not_silently_drop_one_failed_file(tmp_path):
    store = RunStore(tmp_path / "state")
    tasks = PagedTaskService(101)
    tasks.fail_doc = "doc-050"
    client = FailingFileClient(fail_contains="doc-050")
    service = FeishuService(store, tasks, tasks, client)
    result = service._send_result_file(send_event(), "owner-a", "revision", "task-101", "all")
    assert "已发送 100 个文件" in result
    assert "1 个文件发送失败" in result
    assert "合同050.docx" in result
    assert len(client.files) == 100
    assert not any(name.startswith("doc-050") for _, name, _ in client.files)
