"""P6 result-packaging tests: the deliverable layout the business reader opens."""
from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from tools.evaluation.p6_package import (
    build_result_csv,
    case_explanation,
    load_run,
    summary_row,
)


def _make_run(tmp_path: Path) -> Path:
    """A minimal one-case run directory in the recall-first report shape."""
    run = tmp_path / "run"
    case = run / "D01"
    case.mkdir(parents=True)
    document = Document()
    document.add_paragraph("依据基金财产清算的分配方案，按基金份额持有人持有的基金份额比例进行分配。")
    (case / "final").write_bytes(b"PK\x03\x04stub")
    (case / "redline").write_bytes(b"PK\x03\x04stub")
    report = {
        "source_sha256": "a" * 64,
        "delivery_status": "incomplete",
        "ruleset_version": "recall-first-1",
        "ruleset_sha256": "b" * 64,
        "engine_build": "c" * 64,
        "model": {"http_attempts": 7, "estimated_cost_usd": 0.0123},
        "output_validation": {"final_sha256": "d" * 64, "redline_sha256": "e" * 64},
        "guide": {"groups": [{"rule_id": "G22", "title": "清算分配：", "requirement": "补充销售服务费表述。"}]},
        "plan": {"edits": [
            {"rule_id": "G22", "location": "p934", "operation": "replace",
             "replacement": "按基金份额持有人持有的基金份额比例进行分配，并加上返还基金份额持有人的销售服务费（如有）。",
             "evidence": {"matched_old_text": "按基金份额持有人持有的基金份额比例进行分配。"}}]},
        "targets": [],
        "unresolved": [{"rule_id": "G15", "reason": "RECALL_TARGET_UNRESOLVED", "detail": {"rule": "G15"}}],
        "audit": {"rounds": [{"results": [{"rule_id": "G22", "verdict": "completed"}]}]},
    }
    (case / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    (case / "result.json").write_text(json.dumps({
        "case_id": "D01", "file": "测试基金合同.docx", "delivery_status": "incomplete"},
        ensure_ascii=False), encoding="utf-8")
    return run


def test_load_run_reads_case_and_report(tmp_path):
    run = _make_run(tmp_path)
    items = load_run(run)
    assert len(items) == 1
    assert items[0]["result"]["case_id"] == "D01"


def test_case_explanation_has_business_columns_and_reasons(tmp_path):
    run = _make_run(tmp_path)
    items = load_run(run)
    items[0]["original"] = "测试基金合同.docx"
    text = case_explanation("测试基金合同.docx", items[0])
    assert "## 逐处修改对照" in text
    assert "### 逐处修改详情" in text
    assert "## 未修改的内容及原因" in text
    # Each modification states what it was before and after.
    assert "**修改前**" in text
    assert "**修改后**" in text
    # The audit verdict column and the readable rule label are present.
    assert "通过（规则校验＋独立复核）" in text
    assert "非浮动多类别：清算分配表述" in text
    # The unresolved reason is turned into plain language, keeping the code for audit.
    assert "未能在合同中准确定位该条款" in text


def test_summary_row_reports_delivery_and_edits(tmp_path):
    run = _make_run(tmp_path)
    items = load_run(run)
    items[0]["original"] = "测试基金合同.docx"
    row = summary_row(items[0])
    assert "测试基金合同.docx" in row
    assert "部分条款未修改" in row
    assert "| 1 |" in row


def test_result_csv_matches_workbench_columns(tmp_path):
    """结果清单.csv reproduces the workbench export: BOM, CRLF and 7 columns."""
    run = _make_run(tmp_path)
    items = load_run(run)
    items[0]["original"] = "测试基金合同.docx"
    content = build_result_csv(items)
    assert content.startswith("\ufeff"), "Excel needs the UTF-8 BOM"
    assert "\r\n" in content, "the workbench writes CRLF rows"
    header = content.lstrip("\ufeff").split("\r\n", 1)[0]
    assert header == "序号,文件名,资格,处理状态,交付完整性,业务提示,原始原因码"
    body = content.split("\r\n")[1]
    assert body.startswith("1,测试基金合同.docx")
    # Only short machine codes go in the last column, never the audit's prose verdict.
    assert "RECALL_TARGET_UNRESOLVED" in body
