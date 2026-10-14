"""Evaluation-mode persistence and download isolation tests."""
from __future__ import annotations

from pathlib import Path
import re
from types import SimpleNamespace

from docx import Document
from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.docx import inspect_docx
from fundlex.jobs import Worker
from fundlex.v2_pipeline import process_v2

OWNER = "evaluation-user"
DEFINITION = ("基金份额类别设置：本基金将基金份额分为 H 类、J 类和 K 类三种不同的类别。"
              "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费；"
              "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费。")
GENERATED = ("投资者通过直销机构（含基金管理人及其销售子公司，下同）申购本基金 H 类基金份额时，"
             "不收取认购/申购费用；通过直销机构申购的 J 类、K 类基金份额，不收取销售服务费。"
             "对于投资者通过直销机构之外的其他销售机构申购的 J 类、K 类基金份额且持续持有期限超过一年的，"
             "不再继续收取销售服务费。")

PROFILE_VALUE = {
    "classes": [
        {"name": "H",
         "subscription_fee": {"value": True, "quote": "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费"},
         "sales_service_fee": {"value": False, "quote": "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费"}},
        {"name": "J",
         "subscription_fee": {"value": False, "quote": "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费"},
         "sales_service_fee": {"value": True, "quote": "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费"}},
        {"name": "K",
         "subscription_fee": {"value": False, "quote": "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费"},
         "sales_service_fee": {"value": True, "quote": "在投资者申购 J 类、K 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费"}},
    ],
    "share_class_count": {"value": 3, "quote": "本基金将基金份额分为 H 类、J 类和 K 类三种不同的类别"},
    "floating_management_fee": {"value": None, "quote": ""},
}


def build_fixture(path: Path) -> Path:
    document = Document()
    document.add_paragraph("广发示例混合型证券投资基金基金合同")
    document.add_heading("基金的基本情况", level=1)
    document.add_paragraph("基金的类别：混合型证券投资基金")
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph(DEFINITION)
    document.add_heading("基金的投资", level=1)
    document.add_paragraph("本基金投资于股票的比例为60%-95%，投资于债券的比例不低于基金资产的80%。")
    document.save(path)
    return path


class EvaluationGateway:
    """Scripted transport: fund type, profile, R02 generation and verification."""

    def __init__(self):
        self.model = "scripted-eval"
        self.max_context_chars = 12000
        self.calls = 0
        self.events: list[dict] = []

    def _event(self, task_type: str) -> dict:
        self.calls += 1
        event = {"task_type": task_type, "prompt_version": "scripted", "actual_model": self.model,
                 "request_id": f"req-{self.calls}", "latency_ms": 1, "http_status": 200, "error_code": None}
        self.events.append(event)
        return event

    def _result(self, value, task_type):
        event = self._event(task_type)
        return SimpleNamespace(value=value, model=self.model, latency_ms=1, prompt_tokens=1,
                               completion_tokens=1, total_tokens=2, request_id=event["request_id"],
                               attempts=1, estimated_cost_usd=0.0, task_type=task_type)

    def extract_fund_type(self, context: str, *, prompt_version: str = "fund_type_v3"):
        line = next(line for line in context.splitlines() if line.strip())
        return self._result({"quote": line, "fund_type": "ordinary"}, "fund_type")

    def call(self, *, task_type, bounded_context, response_schema, instruction, prompt_version="v1"):
        assert task_type == "profile"
        return self._result(PROFILE_VALUE, "profile")

    def generate_clause(self, context, *, instruction, **kwargs):
        return self._result({"source_quote": ANCHOR_SENTENCE, "replacement_text": GENERATED,
                             "facts": [], "changes": []}, "generate_clause")

    def verify_content(self, context, *, instruction, **kwargs):
        return self._result({"items": [
            {"requirement_id": "R02-REQ-5", "result": "satisfied",
             "evidence_quote": "不收取认购/申购费用", "evidence_source": "generated"}]}, "verify_content")


    def verify_artifact(self, context, **kwargs):
        action_id = re.search(r"\[ACTION ([^]]+)\]", context).group(1)
        identifiers = re.findall(r"^- (\S+) \[", context, re.MULTILINE)
        location = context.split("[EDIT_LOCATIONS]\n", 1)[1].split("\n", 1)[0].split(",")[0]
        quote = context.split(f"[AFTER location={location}]\n", 1)[1].split("\n", 1)[0]
        if action_id == "R02-A1":
            quote = GENERATED
        return self._result({"items": [{"action_id": action_id, "requirement_id": identifier,
            "result": "satisfied", "evidence_quote": quote, "evidence_source": "after"}
            for identifier in [*identifiers, "PRESERVATION", "COVERAGE"]]}, "verify_artifact")


ANCHOR_SENTENCE = DEFINITION[DEFINITION.index("在投资者申购 J"):]


def submit(client: TestClient, data: bytes, ruleset: str = "v2"):
    return client.post("/api/batches", headers={"X-FundLex-User": OWNER},
                       data={"ruleset_version": ruleset}, files=[("files", ("fixture.docx", data))])


def test_evaluation_artifacts_persist_and_download_only_in_evaluation_mode(tmp_path):
    source = build_fixture(tmp_path / "fixture.docx")
    app = create_app(tmp_path / "state")
    client = TestClient(app)
    headers = {"X-FundLex-User": OWNER}
    response = submit(client, source.read_bytes())
    assert response.status_code == 201, response.text
    batch_id = response.json()["id"]
    gateway = EvaluationGateway()
    worker = Worker(app.state.store, lambda src, out, version: process_v2(src, out, version, gateway, evaluation=True))
    assert worker.run_once()
    detail = client.get(f"/api/batches/{batch_id}", headers=headers).json()
    document = detail["documents"][0]
    assert document["execution_mode"] == "evaluation"
    assert document["delivery_status"] == "evaluation_modified_with_exceptions"
    assert {"evaluation_final", "evaluation_redline"}.issubset(document["downloads"])
    assert "final" not in document["downloads"] and "redline" not in document["downloads"]

    report = client.get(document["report_url"], headers=headers).json()
    assert report["execution_mode"] == "evaluation"
    assert report["edit_plan"]["count"] == 1
    assert report["content_verifications"] and report["content_verifications"][0]["passed"] is True
    assert report["output_validation"]["not_a_final_contract"] is True

    download = client.get(document["downloads"]["evaluation_final"], headers=headers)
    assert download.status_code == 200
    final_path = tmp_path / "downloaded.docx"
    final_path.write_bytes(download.content)
    final = inspect_docx(final_path, full=True)
    text = next(span.text for span in final.paragraphs if "基金份额类别设置" in span.text)
    assert "H 类基金份额" in text and "A类" not in text and "C类" not in text
    assert GENERATED in text
    assert client.get(f"/api/batches/{batch_id}/documents/{document['document_id']}/download/final",
                      headers=headers).status_code == 404
    assert client.get(f"/api/batches/{batch_id}/documents/{document['document_id']}/download/evaluation_redline",
                      headers=headers).status_code == 200


def test_qualification_quote_repair_retry_is_bounded(tmp_path):
    source = build_fixture(tmp_path / "fixture-retry.docx")

    class RepairGateway(EvaluationGateway):
        def __init__(self):
            super().__init__()
            self.fund_type_calls = 0

        def extract_fund_type(self, context: str, *, prompt_version: str = "fund_type_v3"):
            self.fund_type_calls += 1
            result = super().extract_fund_type(context, prompt_version=prompt_version)
            if self.fund_type_calls == 1:
                result.value = {"quote": "这条引文并非上下文中的逐字原文", "fund_type": "ordinary"}
            return result

    gateway = RepairGateway()
    report = process_v2(source, tmp_path / "out-retry", "v2", gateway, evaluation=True)
    assert report["qualification_status"] == "eligible"
    assert gateway.fund_type_calls == 2
    assert report["model"]["calls"] == 2
    assert report["qualification"]["model_verification"] == "verified"
    assert report["qualification"]["model_quote"]


def test_delivery_mode_document_cannot_expose_evaluation_kinds(tmp_path):
    from fundlex.pipeline import process

    source = build_fixture(tmp_path / "fixture2.docx")
    app = create_app(tmp_path / "state2")
    client = TestClient(app)
    response = submit(client, source.read_bytes(), ruleset="v1")
    assert response.status_code == 201, response.text
    batch_id = response.json()["id"]

    class Gateway:
        model = "test-gateway"
        calls = 0

        def extract_fund_type(self, context: str):
            line = next(line for line in context.splitlines() if line.strip())
            return SimpleNamespace(value={"quote": line, "fund_type": "ordinary"}, model=self.model,
                                   latency_ms=1, prompt_tokens=1, completion_tokens=1, total_tokens=2,
                                   request_id=None, attempts=1, estimated_cost_usd=None)

    worker = Worker(app.state.store, lambda src, out, version: process(src, out, version, Gateway()))
    assert worker.run_once()
    detail = client.get(f"/api/batches/{batch_id}", headers={"X-FundLex-User": OWNER}).json()
    document = detail["documents"][0]
    assert "evaluation_final" not in document["downloads"]
    assert client.get(f"/api/batches/{batch_id}/documents/{document['document_id']}/download/evaluation_final",
                      headers={"X-FundLex-User": OWNER}).status_code == 404
