"""FL-D1095/1096/1097：飞书三件套修复验证——绑定人话卡/.doc 转换/超限流式。"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from docx import Document

from fundlex.integrations.feishu.service import _binding_failure_text
from fundlex.doc_convert import DocConvertError

from tests.test_feishu_integration import FakeClient, FakeTaskService, message, service_fixture


REAL_LEGACY_DOC = Path("/home/opencode/fundlex/references/source/原始文件/原始文件/广发恒裕一年持有期混合型证券投资基金基金合同.doc")


def docx_bytes(text: str = "公开合同") -> bytes:
    stream = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(stream)
    return stream.getvalue()


def last_card_text(client) -> str:
    return json.dumps(client.sent[-1][1], ensure_ascii=False)


def test_binding_failure_cards_are_human_readable():
    # 供给码风格：与工作台 code→reason 一致的中文人话，不含机读码。
    assert "不存在" in _binding_failure_text("FEISHU_BINDING_CODE_INVALID")
    assert "已用过" in _binding_failure_text("FEISHU_BINDING_CODE_CONSUMED")
    assert "已过期" in _binding_failure_text("FEISHU_BINDING_CODE_EXPIRED")
    assert "原账号解除绑定" in _binding_failure_text("FEISHU_IDENTITY_ALREADY_BOUND")
    assert "重新生成二维码" in _binding_failure_text("FEISHU_WEIRD_UNKNOWN")
    for code in ("FEISHU_BINDING_CODE_INVALID", "FEISHU_BINDING_CODE_CONSUMED",
                 "FEISHU_BINDING_CODE_EXPIRED"):
        assert code not in _binding_failure_text(code), "卡副本不得含裸机读码"


def test_binding_wrong_code_card_is_chinese(tmp_path):
    service, integration, _, client = service_fixture(tmp_path)
    integration.revoke_user_binding("feishu", "owner-a")
    service.handle_message_event(message("evt-needed", text="绑定"))
    requires = last_card_text(client)
    assert "需要绑定账号" in requires or "生成绑定码" in requires, "未绑的时候必须先提示"
    service.handle_message_event(message("evt-badbind", text="绑定 FAKEWRONG42"))
    text = last_card_text(client)
    assert "绑定码不存在" in text or "重新生成绑定码" in text, text[:400]
    assert "FEISHU_BINDING_CODE_INVALID" not in text


def test_legacy_doc_contract_file_converts_inline(tmp_path):
    if not REAL_LEGACY_DOC.is_file():
        pytest.skip("real legacy sample missing")
    data = REAL_LEGACY_DOC.read_bytes()
    store_fixture = service_fixture(tmp_path / "service", data=data)
    service, integration, _, client = store_fixture
    client.remote_name = "合同.doc"
    service.handle_message_event(message("evt-dock", message_type="file",
                                        content={"file_key": "legacy-key"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    files = [f for f in integration.draft_files(draft["id"]) if f["status"] == "accepted"]
    assert len(files) == 1
    from fundlex.store import RunStore
    staged = RunStore(integration.store.root).object_path(files[0]["storage_key"]).read_bytes()
    assert staged[:2] == b"PK", "存储必须是转换后的 DOCX 字节"
    assert staged != data, "不得把原 .doc 字节冒存为 DOCX"
    assert "绑定成功" not in last_card_text(client)


def test_legacy_doc_conversion_timeout_is_human(tmp_path, monkeypatch):
    data = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"payload" * 100
    service, integration, _, client = service_fixture(tmp_path / "service", data=data)
    client.remote_name = "合同.doc"
    def blown(data, *, timeout_s=None, max_output_bytes=None):
        raise DocConvertError("LEGACY_DOC_CONVERT_TIMEOUT")
    monkeypatch.setattr("fundlex.doc_convert.convert_doc_to_docx", blown, raising=False)
    # 兼容服务按需 import 方式。
    import fundlex.doc_convert as dc2
    monkeypatch.setattr(dc2, "convert_doc_to_docx", blown)
    service.handle_message_event(message("evt-timeout", message_type="file",
                                        content={"file_key": "legacy-timeout"}))
    texts = [json.dumps(s[1], ensure_ascii=False) for s in client.sent]
    assert any(all(token in t for token in ("转换超时", "DOCX", "重发")) for t in texts), texts[:400]
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert [f for f in integration.draft_files(draft["id"]) if f["status"] == "accepted"] == []


def test_pdf_still_rejected_as_unsupported(tmp_path):
    data = b"%PDF-1.7 not an office artifact"
    service, integration, _, client = service_fixture(tmp_path / "service", data=data)
    client.remote_name = "合同.pdf"
    service.handle_message_event(message("evt-pdf", message_type="file",
                                        content={"file_key": "pdf-key"}))
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    files = integration.draft_files(draft["id"])
    assert not any(f["status"] == "accepted" for f in files), "PDF 不得放行"
    assert any(f["error_code"] in {"UNSUPPORTED_FILE_FORMAT"} for f in files)


class _TooLargeClient(FakeClient):
    def download_message_resource(self, message_id, file_key, resource_type="file", *, max_bytes=None):
        from fundlex.integrations.feishu.client import FeishuFileTooLarge
        raise FeishuFileTooLarge("received 999999999 bytes > limit 26214400")


def test_oversize_download_rejected_with_human_text(tmp_path):
    store = __import__("pathlib").Path(tmp_path / "service")
    from fundlex.store import RunStore
    from fundlex.integrations.store import IntegrationStore
    runs_store = RunStore(store / "state")
    integration = IntegrationStore(runs_store)
    code = integration.create_binding_code("feishu", "owner-a")["code"]
    integration.consume_binding_code("feishu", "tenant-a", "ou-a", code)
    client = _TooLargeClient(docx_bytes())
    from fundlex.integrations.feishu.service import FeishuService
    service = FeishuService(runs_store, FakeTaskService(), FakeTaskService(), client,
                            base_url="https://fundlex.test")
    service.handle_message_event(message("evt-toolarge", message_type="file",
                                        content={"file_key": "big-key"}))
    text = last_card_text(client)
    assert "文件过大" in text and "工作台网页上传" in text, text[:300]
    assert "25 MB" in text
    draft = integration.active_draft("tenant-a", "ou-a", "oc-a")
    assert draft is None or not any(
        f["status"] == "accepted" for f in integration.draft_files(draft["id"]))


def test_download_message_resource_streams_and_aborts_over_limit():
    """构件层：流式分块过程中超限即抛 FEISHU_FILE_TOO_LARGE，不全部读入。"""
    from fundlex.integrations.feishu.client import FeishuFileTooLarge, FeishuOpenApiClient
    proxy = FeishuOpenApiClient.__new__(FeishuOpenApiClient)

    class _FakeResource:
        def __init__(self, total: int):
            self._pos = 0
            self._total = total

        def read(self, n: int):
            if self._pos >= self._total:
                return b""
            take = min(n, self._total - self._pos)
            self._pos += take
            return b"x" * take

    payload_size = 512 * 1024

    def make_proxy():
        proxy = FeishuOpenApiClient.__new__(FeishuOpenApiClient)
        response = type("Resp", (), {"code": 0, "file": _FakeResource(payload_size),
                                     "file_name": "终极超大.docx"})()
        holder = type("Msg", (), {})()
        holder.message_resource = type("MR", (), {"get": lambda self, req: response})()
        proxy.client = type("Client", (), {"im": type("IM", (), {"v1": holder})()})()
        return proxy

    # 小限额 → 立即超限（不读盘全部字节）。
    with pytest.raises(FeishuFileTooLarge) as caught:
        make_proxy().download_message_resource("m1", "k1", "file", max_bytes=1024)
    assert "limit 1024" in str(caught.value)
    # 正常限额 → 全量返回、hash 不受影响。
    data, name = make_proxy().download_message_resource("m2", "k2", "file",
                                                        max_bytes=payload_size + 1024)
    assert name == "终极超大.docx" and len(data) == payload_size
