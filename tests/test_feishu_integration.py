"""Focused persistence and orchestration checks for the Feishu channel."""
from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from docx import Document

from fundlex.integrations.feishu.cards import menu_card, result_card
from fundlex.integrations.feishu.events import MessageEvent
from fundlex.integrations.feishu.service import FeishuService
from fundlex.integrations.store import IntegrationConflict, IntegrationStore
from fundlex.compare.store import CompareStore
from fundlex.guide_generation.store import GuideGenerationStore
from fundlex.store import RunStore
from fundlex.upload_validation import has_tracked_revisions


def docx_bytes(text: str = "公开合同") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


class FakeClient:
    def __init__(self, data: bytes):
        self.data = data
        self.remote_name = "合同.docx"
        self.downloads = 0
        self.sent: list[tuple[str, dict]] = []
        self.updated: list[tuple[str, dict]] = []
        self.files: list[tuple[str, str, int]] = []
        self.pinned: list[str] = []
        self.unpinned: list[str] = []
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
        return self.data, self.remote_name

    def send_file(self, receive_id, filename, data):
        self.files.append((receive_id, filename, len(data)))
        return f"file-{len(self.files)}"

    def pin_message(self, message_id):
        self.pinned.append(message_id)

    def unpin_message(self, message_id):
        self.unpinned.append(message_id)


class FakeTaskService:
    def __init__(self):
        self.created = []
        self.uploaded = []
        self.sealed = []
        self.fail_upload_once = False
        self._tasks = {}

    def create_task(self, owner, name, files, *, idempotency_key=None, mode="delivery"):
        self.created.append((owner, name, files, idempotency_key))
        if idempotency_key in self._tasks:
            return self._tasks[idempotency_key]
        task = {"id": "task-1", "status": "queued", "total": len(files), "name": name, "mode": mode}
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
                "completed": 1, "failed": 0, "delivery_counts": {"complete": 1},
                "mode": "delivery", "downloadable_count": 1}

    def list(self, owner, **filters):
        return {"items": [{"id": "task-1", "name": "合同", "status": "completed", "total": 1,
                           "completed": 1, "failed": 0, "mode": "delivery",
                           "downloadable_count": 1, "created_at": "2026-10-28T00:00:00+00:00"}],
                "total": 1, "page": 1, "page_size": 50}

    def list_documents(self, owner, task_id, **filters):
        return {"items": [{"document_id": "doc-1", "name": "合同.docx",
                           "downloads": {"report_md": "/api/report", "final": "/api/final"}}],
                "total": 1, "page": 1, "page_size": 100}

    def artifact(self, owner, task_id, document_id, kind):
        return b"report-bytes", f"合同-{kind}.md"


def docx_with_tracked_revision() -> bytes:
    with zipfile.ZipFile(io.BytesIO(docx_bytes())) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document = parts["word/document.xml"].decode("utf-8")
    document = document.replace(
        "<w:body>",
        '<w:body><w:p><w:ins w:id="1" w:author="tester" '
        'w:date="2026-01-01T00:00:00Z"><w:r><w:t>修订内容</w:t></w:r></w:ins></w:p>',
        1,
    )
    parts["word/document.xml"] = document.encode("utf-8")
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return output.getvalue()


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


def multi_service_fixture(tmp_path: Path, *, data: bytes | None = None):
    store = RunStore(tmp_path / "state")
    integration = IntegrationStore(store)
    code = integration.create_binding_code("feishu", "owner-a")["code"]
    integration.consume_binding_code("feishu", "tenant-a", "ou-a", code)
    client = FakeClient(data or docx_bytes())
    tasks = FakeTaskService()
    service = FeishuService(store, tasks, tasks, client, base_url="https://fundlex.test",
                            compare_store=CompareStore(store),
                            guide_store=GuideGenerationStore(store))
    return service, integration, tasks, client


def test_card_2_0_uses_column_set_buttons_not_removed_action_module():
    card = menu_card()
    elements = card["body"]["elements"]
    assert not any(item.get("tag") == "action" for item in elements)
    action_sets = [item for item in elements if item.get("tag") == "column_set"]
    assert action_sets and all(
        column.get("tag") == "column" and column.get("elements")[0].get("tag") == "button"
        and column["elements"][0].get("behaviors")[0].get("type") == "callback"
        for item in action_sets for column in item.get("columns", [])
    )


def test_menu_and_compare_flow_creates_compare_task(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-menu", text="菜单"))
    assert "任务中心" in client.sent[-1][1]["header"]["title"]["content"]

    service.handle_message_event(message("evt-compare", text="合同对比"))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None and draft["task_type"] == "compare"
    assert draft["step"] == "left"
    assert "左侧" in json.dumps(client.sent[-1][1], ensure_ascii=False)
    assert "form" not in json.dumps(client.sent[-1][1], ensure_ascii=False)

    service.handle_message_event(message("evt-left", message_type="file", content={"file_key": "left"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["step"] == "right"
    assert re.match(r"^合同对比 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", draft["name"])
    service.handle_message_event(message("evt-right", message_type="file", content={"file_key": "right"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["step"] == "confirm"
    sides = {item["side"] for item in integration.draft_files(draft["id"]) if item["status"] == "accepted"}
    assert sides == {"left", "right"}

    replace = {"header": {"event_id": "compare-replace-left"},
               "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                         "context": {"open_chat_id": "oc-a", "open_message_id": "card-msg"},
                         "action": {"value": {"command": "replace_side", "side": "left"}}}}
    assert "请发送新的左侧" in service.handle_card_action_event(replace)
    assert integration.active_draft("tenant-a", "ou-a", "oc-a")["step"] == "left"
    client.data = docx_bytes("新的左侧合同")
    service.handle_message_event(message("evt-left-new", message_type="file", content={"file_key": "left-new"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["step"] == "confirm"
    sides = {item["side"] for item in integration.draft_files(draft["id"]) if item["status"] == "accepted"}
    assert sides == {"left", "right"}

    service.handle_message_event(message("evt-confirm", text="确认"))
    submitted = integration.draft(draft["id"])
    assert submitted["status"] == "SUBMITTED"
    channel = integration.channels()
    assert len(channel) == 1 and channel[0]["task_type"] == "compare"
    task = service.compare.get("owner-a", channel[0]["task_id"])
    assert task["sealed"] is True and task["total"] == 1


def test_revision_uses_timestamp_name_and_has_no_naming_button(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None and draft["step"] == "collecting"
    assert re.match(r"^合同修订 \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$", draft["name"])
    body = json.dumps(client.sent[-1][1], ensure_ascii=False)
    assert "请直接发送" in body and "\"form\"" not in body
    assert "命名" not in body

    before = draft["name"]
    client.remote_name = "某某基金合同.docx"
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["name"] == before
    assert "确认创建任务" in json.dumps(client.sent[-1][1], ensure_ascii=False)


def test_first_file_retires_the_prompt_card(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    old_card = integration.active_draft("tenant-a", "ou-a", "oc-a")["card_message_id"]
    assert old_card
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    retired = [card for message_id, card in client.updated if message_id == old_card]
    assert retired and retired[-1]["header"]["title"]["content"] == "卡片已更新"
    assert integration.active_draft("tenant-a", "ou-a", "oc-a")["card_message_id"] != old_card


def test_cancel_returns_a_fresh_task_centre_card(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    action = {"header": {"event_id": "cancel-and-menu"},
              "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                        "context": {"open_chat_id": "oc-a", "open_message_id": "card-msg"},
                        "action": {"value": {"command": "cancel", "draft_id": draft["id"]}}}}
    assert "已取消" in service.handle_card_action_event(action)
    assert client.sent[-1][1]["header"]["title"]["content"] == "FundLex 任务中心"
    assert "请重新选择任务" in json.dumps(client.sent[-1][1], ensure_ascii=False)
    assert integration.get_state("feishu", "menu_card:tenant-a:ou-a") == "msg-" + str(len(client.sent))


def test_rename_text_no_longer_changes_the_task_name(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    before = integration.active_draft("tenant-a", "ou-a", "oc-a")["name"]
    service.handle_message_event(message("evt-rename", text="改名 采购合同 2026"))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["name"] == before
    assert integration.draft_files(draft["id"])[0]["status"] == "accepted"
    assert "需要我做什么" in json.dumps(client.sent[-1][1], ensure_ascii=False)


def test_legacy_name_card_unknown_form_action_falls_back_to_default_name(tmp_path):
    service, integration, _, _ = multi_service_fixture(tmp_path)
    draft = integration.create_draft("tenant-a", "ou-a", "oc-a", "owner-a", "飞书合同任务",
                                     step="name")
    action = {"header": {"event_id": "name-fallback"},
              "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                        "context": {"open_chat_id": "oc-a", "open_message_id": "card-msg"},
                        "action": {"name": "Button_generated", "tag": "button"}}}
    assert "已保存" in service.handle_card_action_event(action)
    draft = integration.draft(draft["id"])
    assert draft["step"] == "collecting" and draft["name"] == "飞书合同任务"


def test_guide_flow_accepts_pdf_and_creates_run(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path, data=b"%PDF-1.7\npublic regulation\n")
    client.remote_name = "公开法规.pdf"
    service.handle_message_event(message("evt-guide", text="生成指引"))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None and draft["task_type"] == "guide"
    service.handle_message_event(message("evt-pdf", message_type="file", content={"file_key": "pdf"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["step"] == "confirm"
    old_file = integration.draft_files(draft["id"])[0]
    assert old_file["kind"] == "regulation"

    replace = {"header": {"event_id": "guide-replace-file"},
               "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                         "context": {"open_chat_id": "oc-a", "open_message_id": "card-msg"},
                         "action": {"value": {"command": "replace_file", "file_id": old_file["id"]}}}}
    assert "已移除" in service.handle_card_action_event(replace)
    assert integration.active_draft("tenant-a", "ou-a", "oc-a")["step"] == "waiting_file"
    client.data = b"%PDF-1.7\nnew public regulation\n"
    client.remote_name = "替换法规.pdf"
    service.handle_message_event(message("evt-pdf-new", message_type="file", content={"file_key": "pdf-new"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["step"] == "confirm"

    service.handle_message_event(message("evt-guide-confirm", text="确认"))
    submitted = integration.draft(draft["id"])
    assert submitted["status"] == "SUBMITTED"
    channel = integration.channels()
    assert len(channel) == 1 and channel[0]["task_type"] == "guide"
    run = service.guides.get_run_for_owner("owner-a", channel[0]["task_id"])
    assert run["status"] == "queued"


def test_unknown_text_does_not_silently_rename_or_submit(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    before = integration.active_draft("tenant-a", "ou-a", "oc-a")["name"]
    service.handle_message_event(message("evt-chat", text="这个文件好像不对"))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft["name"] == before
    assert "需要我做什么" in json.dumps(client.sent[-1][1], ensure_ascii=False)


def test_switch_task_cancels_current_draft_and_starts_new_type(tmp_path):
    service, integration, _, _ = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    action = {"header": {"event_id": "switch-task"},
              "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                        "context": {"open_chat_id": "oc-a", "open_message_id": "card-msg"},
                        "action": {"value": {"command": "switch_task", "task_type": "compare"}}}}
    assert "已取消" in service.handle_card_action_event(action)
    assert integration.draft(draft["id"])["status"] == "CANCELLED"
    assert integration.active_draft("tenant-a", "ou-a", "oc-a")["task_type"] == "compare"


def test_result_card_explains_not_generated_delivery():
    card = result_card({"id": "task-1", "name": "带修订合同", "status": "completed",
                        "total": 1, "completed": 1, "failed": 0,
                        "delivery_counts": {"not_generated": 1}},
                       "https://fundlex.test", downloads={"report_md": "/api/report"})
    body = json.dumps(card, ensure_ascii=False)
    assert card["header"]["title"]["content"] == "任务未生成交付文件"
    assert "未生成交付文件" in body
    assert "接受/拒绝全部修订" in body
    assert "发送报告" in body


def test_task_list_paginates_and_returns_second_page(tmp_path):
    service, _, _, client = multi_service_fixture(tmp_path)
    items = [{"task_type": "revision", "task_id": f"task-{index}", "name": f"合同{index}",
              "status": "completed", "detail": "", "can_send": False, "created_at": index}
             for index in range(8)]
    service._collect_tasks = lambda owner: items
    event = MessageEvent("evt-tasks-2", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                         "p2p", "msg-tasks-2", "text", {"text": "任务"})
    service._show_tasks(event, "owner-a", page=2)
    body = json.dumps(client.sent[-1][1], ensure_ascii=False)
    assert "第 2 页" in body and "合同6" in body and "合同0" not in body
    assert "上一页" in body


def test_show_tasks_does_not_replace_the_pinned_menu_card(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    pinned = "pinned-menu"
    integration.set_state("feishu", "menu_card:tenant-a:ou-a", pinned)
    action = {"header": {"event_id": "tasks-from-pin"},
              "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                        "context": {"open_chat_id": "oc-a", "open_message_id": pinned},
                        "action": {"value": {"command": "show_tasks"}}}}
    assert "任务列表" in service.handle_card_action_event(action)
    assert not any(message_id == pinned for message_id, _ in client.updated)
    assert client.sent[-1][1]["header"]["title"]["content"] == "我的任务"


def test_binding_pins_the_menu_card_for_new_users(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    code = integration.create_binding_code("feishu", "owner-b")["code"]
    service.handle_message_event(message("evt-bind-b", text=f"绑定 {code}", open_id="ou-b"))
    assert client.pinned
    assert integration.get_state("feishu", "menu_card:tenant-a:ou-b") == client.pinned[-1]


def test_send_all_deliverables_skips_duplicate_report_formats(tmp_path):
    service, _, _, client = multi_service_fixture(tmp_path)
    event = MessageEvent("evt-send-all", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                         "p2p", "msg-send-all", "text", {"text": "发送全部"})
    assert service._send_result_file(event, "owner-a", "revision", "task-1", "all") == "已发送 2 个文件。"
    assert [name for _, name, _ in client.files] == ["合同-final.md", "合同-report_md.md"]


def test_tracked_revision_is_accepted_for_overlay(tmp_path):
    """Another department's tracked changes no longer block the upload."""
    data = docx_with_tracked_revision()
    assert has_tracked_revisions(data) is True
    service, integration, _, client = multi_service_fixture(tmp_path, data=data)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    client.remote_name = "带修订合同.docx"
    service.handle_message_event(message("evt-revision-file", message_type="file", content={"file_key": "rev"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    files = integration.draft_files(draft["id"])
    assert files and files[0]["status"] != "rejected"
    assert files[0]["error_code"] in ("", None)
    body = json.dumps(client.updated[-1][1], ensure_ascii=False)
    assert "EXISTING_REVISION_UNSUPPORTED" not in body


def test_pdf_sent_to_revision_shows_actionable_error(tmp_path):
    service, integration, _, client = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-revision", text="合同修订"))
    client.data = b"%PDF-1.7\npublic contract\n"
    client.remote_name = "合同.pdf"
    service.handle_message_event(message("evt-pdf", message_type="file", content={"file_key": "pdf"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None
    files = integration.draft_files(draft["id"])
    assert files[0]["status"] == "rejected"
    assert "另存为 DOCX" in json.dumps(client.updated[-1][1], ensure_ascii=False)


def test_diagnosis_flow_passes_mode_to_task_service(tmp_path):
    service, integration, tasks, _ = multi_service_fixture(tmp_path)
    service.handle_message_event(message("evt-diagnosis", text="只读诊断"))
    service.handle_message_event(message("evt-file", message_type="file", content={"file_key": "key"}))
    service.handle_message_event(message("evt-confirm", text="确认"))
    assert tasks.created
    assert tasks.created[-1][3] is not None
    channel = integration.channels()
    assert channel and channel[0]["task_type"] == "diagnosis"


def test_task_list_card_includes_revision_and_compare(tmp_path):
    service, _, _, client = multi_service_fixture(tmp_path)
    service.compare.create("owner-a", "对比任务", [{
        "client_pair_id": "pair-1", "label": "对比任务",
        "left": {"client_id": "left", "name": "左.docx", "size": 1},
        "right": {"client_id": "right", "name": "右.docx", "size": 1},
    }])
    service.handle_message_event(message("evt-tasks", text="我的任务"))
    title = client.sent[-1][1]["header"]["title"]["content"]
    assert title == "我的任务"
    body = json.dumps(client.sent[-1][1], ensure_ascii=False)
    assert "合同修订" in body and "合同对比" in body


def test_result_file_send_uses_owner_task_artifact(tmp_path):
    service, _, _, client = multi_service_fixture(tmp_path)
    event = MessageEvent("evt-send", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                         "p2p", "msg-send", "text", {"text": "发送报告"})
    assert service._send_result_file(event, "owner-a", "diagnosis", "task-1", "report_md") == "已发送 1 个文件。"
    assert client.files == [("oc-a", "合同-report_md.md", len(b"report-bytes"))]


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
    client.data = docx_bytes("第二份合同")
    service.handle_message_event(second)
    service.handle_message_event(first)
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is not None
    files = integration.draft_files(draft["id"])
    assert len(files) == 2 and all(item["status"] == "accepted" for item in files)
    assert client.downloads == 2


def test_duplicate_file_content_is_not_added_twice(tmp_path):
    service, integration, _, _ = service_fixture(tmp_path)
    service.handle_message_event(message("evt-dup-1", message_type="file", content={"file_key": "key-1"}))
    service.handle_message_event(message("evt-dup-2", message_type="file", content={"file_key": "key-2"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    files = integration.draft_files(draft["id"])
    assert len(files) == 1 and files[0]["status"] == "accepted"


def test_remove_file_and_cleanup_on_cancel(tmp_path):
    service, integration, _, _ = service_fixture(tmp_path)
    service.handle_message_event(message("evt-remove-1", message_type="file", content={"file_key": "key-1"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    item = integration.draft_files(draft["id"])[0]
    action = {"header": {"event_id": "remove-file-1"},
              "event": {"operator": {"tenant_key": "tenant-a", "open_id": "ou-a"},
                        "context": {"open_chat_id": "oc-a", "open_message_id": "card-msg"},
                        "action": {"value": {"command": "remove_file", "file_id": item["id"]}}}}
    assert "已移除" in service.handle_card_action_event(action)
    assert integration.draft_files(draft["id"])[0]["status"] == "removed"
    service._cancel_draft(MessageEvent("evt-cancel", "im.message.receive_v1", "tenant-a", "ou-a", "oc-a",
                                      "p2p", "msg-cancel", "text", {"text": "取消"}), draft)
    assert integration.draft_files(draft["id"]) == []


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


def test_oauth_state_is_one_time_and_binds_identity(tmp_path):
    store = RunStore(tmp_path / "oauth-state")
    integration = IntegrationStore(store)
    state = integration.create_oauth_state("feishu", "owner-a")
    assert integration.consume_oauth_state("feishu", state["state"]) == "owner-a"
    with pytest.raises(IntegrationConflict, match="FEISHU_OAUTH_STATE_CONSUMED"):
        integration.consume_oauth_state("feishu", state["state"])

    other = integration.create_oauth_state("feishu", "owner-b")
    integration.bind_oauth_identity("feishu", "owner-b", "tenant-a", "ou-oauth")
    assert integration.identity("feishu", "tenant-a", "ou-oauth")["user_id"] == "owner-b"
    with pytest.raises(IntegrationConflict, match="FEISHU_IDENTITY_ALREADY_BOUND"):
        integration.bind_oauth_identity("feishu", "owner-a", "tenant-a", "ou-oauth")
    # A different account's unused state remains valid for that account only.
    assert integration.consume_oauth_state("feishu", other["state"]) == "owner-b"
