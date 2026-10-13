"""Release-gate and formal-delivery tests for the v2 rule package and pipeline."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi.testclient import TestClient

from fundlex.api import create_app
from fundlex.docx import inspect_docx
from fundlex.jobs import Worker, _default_processor
from fundlex.model import ModelError
from fundlex.rules_v2 import PROMPT_VERSIONS_V2, RuleSetV2, RuleV2Error, load_ruleset_v2
from fundlex.store import RunStore, validate_delivery
from fundlex import v2_pipeline

REPO_RULES = Path(__file__).resolve().parents[1] / "rules" / "rules_v2.json"
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


class ScriptedGateway:
    """Answers fund type, profile, generation and verification for the fixture."""

    def __init__(self):
        self.model = "scripted-release"
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
        return self._result({"source_quote": ANCHOR, "replacement_text": GENERATED,
                             "facts": [], "changes": []}, "generate_clause")

    def verify_content(self, context, *, instruction, **kwargs):
        return self._result({"items": [
            {"requirement_id": "R02-REQ-5", "result": "satisfied",
             "evidence_quote": "不收取认购/申购费用", "evidence_source": "generated"}]}, "verify_content")


ANCHOR = DEFINITION[DEFINITION.index("在投资者申购 J"):]


def released_package() -> dict:
    """A released package with complete, preregistered evidence for R02-A1."""
    data = json.loads(REPO_RULES.read_text(encoding="utf-8"))
    context = {"engine_build": "a" * 64, "model_transport_sha256": "b" * 64,
               "actual_model": "release-model", "prompt_versions": PROMPT_VERSIONS_V2}
    data["release_policy"] = {"status": "released", "basis": "test release",
                              "evaluation_report_id": "report-1", "approval_record": "approval-1",
                              "evaluation_context": context, "auto_write_actions": ["R02-A1"]}
    for action in data["actions"]:
        auto = action["action_id"] == "R02-A1"
        action["approval"] = {"auto_write": auto, "approved": auto, "status": "released"}
        if auto:
            action["evaluation_report_id"] = "report-1"
            action["approval_record"] = "approval-1"
            action["release_threshold"] = {"registration_id": "reg-1", "registered_before_full_evaluation": True,
                                           "metrics": {"accuracy": {"min": 0.9}},
                                           "profile_metrics": {field: {"accuracy": {"min": 0.9}}
                                                               for field in action.get("requires_profile", [])}}
            action["evaluation_metrics"] = {"tested_context": context, "action_id": action["action_id"],
                                            "evaluation_report_id": "report-1", "threshold_registration_id": "reg-1",
                                            "metrics": {"accuracy": 0.99},
                                            "profile_metrics": {field: {"accuracy": 0.99}
                                                                for field in action.get("requires_profile", [])}}
    return data


def write_package(tmp_path: Path, data: dict) -> Path:
    path = tmp_path / "rules_v2_released.json"
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_unreleased_package_rejects_auto_write(tmp_path):
    data = json.loads(REPO_RULES.read_text(encoding="utf-8"))
    data["actions"][0]["approval"]["auto_write"] = True
    with pytest.raises(RuleV2Error) as excinfo:
        load_ruleset_v2(path=write_package(tmp_path, data))
    assert excinfo.value.code == "V2_RELEASE_NOT_SEPARATE"


def test_released_package_requires_complete_evidence(tmp_path):
    data = released_package()
    action = next(item for item in data["actions"] if item["action_id"] == "R02-A1")
    action["evaluation_metrics"]["metrics"]["accuracy"] = 0.5  # below the preregistered threshold
    with pytest.raises(RuleV2Error) as excinfo:
        load_ruleset_v2(path=write_package(tmp_path, data))
    assert excinfo.value.code == "V2_RELEASE_METRIC_BELOW_THRESHOLD"
    data = released_package()
    action = next(item for item in data["actions"] if item["action_id"] == "R02-A1")
    action["approval"]["approved"] = False
    with pytest.raises(RuleV2Error) as excinfo:
        load_ruleset_v2(path=write_package(tmp_path, data))
    assert excinfo.value.code == "V2_RELEASE_EVIDENCE_MISSING"
    data = released_package()
    data["release_policy"]["approval_record"] = None
    with pytest.raises(RuleV2Error) as excinfo:
        load_ruleset_v2(path=write_package(tmp_path, data))
    assert excinfo.value.code == "V2_RELEASE_EVIDENCE_MISSING"


def test_released_package_with_evidence_loads(tmp_path):
    ruleset = load_ruleset_v2(path=write_package(tmp_path, released_package()))
    assert ruleset.auto_write_enabled is True
    r02 = next(action for action in ruleset.actions if action["action_id"] == "R02-A1")
    assert r02["approval"]["auto_write"] is True
    others = [action for action in ruleset.actions if action["action_id"] != "R02-A1"]
    assert all(action["approval"]["auto_write"] is False for action in others)


def test_delivery_pipeline_publishes_formal_artifacts(tmp_path, monkeypatch):
    source = build_fixture(tmp_path / "delivery.docx")
    data = released_package()
    ruleset = RuleSetV2("v2", "f" * 64, tuple(data["actions"]), data["release_policy"])
    monkeypatch.setattr(v2_pipeline, "load_ruleset_v2", lambda version="v2": ruleset)
    gateway = ScriptedGateway()
    output = tmp_path / "out"
    report = v2_pipeline.process_v2(source, output, "v2", gateway)
    assert report["execution_mode"] == "delivery"
    assert report["delivery_status"] == "complete"
    assert report["edit_plan"]["executable"] is True
    assert report["output_validation"]["kind"] == "validated_edits"
    assert "content_verification" in report["output_validation"]["checks"]
    assert set(report["artifacts"]) == {"redline", "final"}
    validate_delivery(report, {"redline": output / "redline.docx", "final": output / "final.docx"})
    assert (output / "final.docx").is_file()


def test_delivery_worker_publishes_final_downloads(tmp_path, monkeypatch):
    source = build_fixture(tmp_path / "delivery-worker.docx")
    data = released_package()
    ruleset = RuleSetV2("v2", "f" * 64, tuple(data["actions"]), data["release_policy"])
    monkeypatch.setattr(v2_pipeline, "load_ruleset_v2", lambda version="v2": ruleset)
    app = create_app(tmp_path / "state")
    client = TestClient(app)
    headers = {"X-FundLex-User": "delivery-user"}
    response = client.post("/api/batches", headers=headers, data={"ruleset_version": "v2"},
                           files=[("files", ("delivery.docx", source.read_bytes()))])
    assert response.status_code == 201, response.text
    batch_id = response.json()["id"]
    gateway = ScriptedGateway()
    worker = Worker(app.state.store, lambda src, out, ver: v2_pipeline.process_v2(src, out, ver, gateway))
    assert worker.run_once()
    detail = client.get(f"/api/batches/{batch_id}", headers=headers).json()
    document = detail["documents"][0]
    assert document["execution_mode"] == "delivery"
    assert document["delivery_status"] == "complete"
    assert {"final", "redline"}.issubset(document["downloads"])
    assert "evaluation_final" not in document["downloads"]
    downloaded = client.get(document["downloads"]["final"], headers=headers)
    assert downloaded.status_code == 200
    assert client.get(document["downloads"]["redline"], headers=headers).status_code == 200


def test_delivery_with_failed_action_publishes_no_contract(tmp_path, monkeypatch):
    # Hybrid fee classes make the action fail closed; a formal delivery must not
    # publish any contract file for an incomplete action set.
    document = Document()
    document.add_paragraph("广发示例混合型证券投资基金基金合同")
    document.add_heading("基金的基本情况", level=1)
    document.add_paragraph("基金的类别：混合型证券投资基金")
    document.add_paragraph("三、基金的份额类别设置")
    document.add_paragraph("基金份额类别设置：本基金将基金份额分为 H 类、J 类和 K 类三种不同的类别。"
                           "在投资者申购 H 类基金份额时收取申购费用，不计提销售服务费；"
                           "在投资者申购 J 类基金份额时不收取申购费用，而从本类别基金资产中计提销售服务费；"
                           "在投资者申购 K 类基金份额时收取申购费用，并从本类别基金资产中计提销售服务费。")
    document.add_heading("基金的投资", level=1)
    document.add_paragraph("本基金投资于股票的比例为60%-95%，投资于债券的比例不低于基金资产的80%。")
    source = tmp_path / "hybrid.docx"
    document.save(source)
    data = released_package()
    ruleset = RuleSetV2("v2", "f" * 64, tuple(data["actions"]), data["release_policy"])
    monkeypatch.setattr(v2_pipeline, "load_ruleset_v2", lambda version="v2": ruleset)
    gateway = ScriptedGateway()
    report = v2_pipeline.process_v2(source, tmp_path / "out", "v2", gateway)
    assert report["delivery_status"] == "incomplete"
    assert report["artifacts"] == {}
    assert not (tmp_path / "out" / "final.docx").exists()


def test_default_processor_dispatches_v2(tmp_path, monkeypatch):
    called = {}

    def fake_process_v2(source, output, version, gateway=None, *, evaluation=None):
        called["version"] = version
        return {"ok": True}

    monkeypatch.setattr(v2_pipeline, "process_v2", fake_process_v2)
    result = _default_processor(tmp_path / "x.docx", tmp_path / "out", "v2")
    assert result == {"ok": True} and called["version"] == "v2"
