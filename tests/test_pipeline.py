from __future__ import annotations

import hashlib
from pathlib import Path

from docx import Document

from fundlex.model import ModelError, ModelResult
from fundlex.pipeline import process
from fundlex.rules import RuleError, classify_fund_type, load_ruleset
from fundlex.docx import inspect_docx


def _contract(path: Path, category: str, operation: str = "契约型开放式") -> None:
    doc = Document()
    doc.add_paragraph("示例证券投资基金基金合同")
    doc.add_paragraph("第四部分 基金的基本情况")
    doc.add_paragraph("二、基金的类别")
    doc.add_paragraph(category)
    doc.add_paragraph("三、基金的运作方式")
    doc.add_paragraph(operation)
    doc.add_paragraph("份额类别设置")
    doc.add_paragraph("本基金可在约定范围内调低赎回费率并报中国证监会备案。")
    doc.save(path)


class StubGateway:
    model = "unit-model"
    calls = 0

    def __init__(self, kind: str, fail: bool = False):
        self.kind, self.fail = kind, fail

    def extract_fund_type(self, context: str) -> ModelResult:
        self.calls += 1
        if self.fail:
            raise ModelError("MODEL_SCHEMA_INVALID")
        quote = context.splitlines()[0]
        return ModelResult({"quote": quote, "fund_type": self.kind}, self.model,
                           7, 20, 10, 30, None, 1)


def test_ruleset_gate_is_closed():
    rules = load_ruleset("v1")
    assert not rules.auto_write_enabled
    assert all(not action["auto_write"] for action in rules.actions)
    try:
        load_ruleset("v99")
    except RuleError as exc:
        assert exc.code == "RULESET_NOT_FOUND"
    else:
        raise AssertionError("unknown ruleset accepted")


def test_ordinary_contract_read_only_artifacts(tmp_path: Path):
    source = tmp_path / "contract.docx"
    _contract(source, "混合型证券投资基金")
    output = tmp_path / "out"
    report = process(source, output, "v1", StubGateway("ordinary"))
    assert report["qualification_status"] == "eligible"
    assert report["release_gate"]["status"] == "closed"
    assert report["edit_plan"]["validated"] and report["edit_plan"]["count"] == 0
    assert report["delivery_status"] != "complete"
    assert report["output_validation"]["not_a_final_contract"]
    assert hashlib.sha256(source.read_bytes()).digest() == hashlib.sha256((output / "evaluation_redline.docx").read_bytes()).digest()
    assert (output / "evaluation_final.docx").read_bytes() == source.read_bytes()
    assert "不完整" in (output / "report.md").read_text(encoding="utf-8")


def test_etf_excluded_from_operation_evidence(tmp_path: Path):
    source = tmp_path / "etf.docx"
    _contract(source, "股票型、指数型证券投资基金", "交易型开放式")
    inspection = inspect_docx(source)
    evidence = classify_fund_type(inspection)
    assert evidence["fund_type"] == "etf"
    report = process(source, tmp_path / "out", "v1", StubGateway("etf"))
    assert report["qualification_status"] == "excluded_by_fund_type"
    assert not (tmp_path / "out" / "evaluation_final.docx").exists()


def test_model_failure_closes_contract(tmp_path: Path):
    source = tmp_path / "contract.docx"
    _contract(source, "混合型证券投资基金")
    report = process(source, tmp_path / "out", "v1", StubGateway("ordinary", fail=True))
    assert report["qualification_status"] == "failed"
    assert report["error_code"] == "MODEL_SCHEMA_INVALID"
    assert report["delivery_status"] == "not_generated"
    assert report["model"]["error_count"] == 1
