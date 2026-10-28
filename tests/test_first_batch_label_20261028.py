"""Unit tests for the independent first-batch labeler.

These tests do not call a model and never read engine artifacts.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/evaluation/first_batch_label_20261028.py"


def _load_tool():
    spec = importlib.util.spec_from_file_location("first_batch_label_tool", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


def _para(index, text, *, style="Normal", section="第三部分  基金的基本情况 > 八、基金份额类别设置", summary=False):
    return tool.Para(index, text, style, section, summary, False)


def _doc(paras):
    return tool.DocModel(
        path=Path("/nonexistent.docx"),
        paragraphs=paras,
        summary_start=None,
        summary_headings=[],
        protection={"protected": False, "edit": None, "enforcement": None},
        text_sha256="x",
    )


def test_compact_offsets_and_whitespace_tolerant_span():
    text = "本基金 A 类基金份额，不收取销售服务费。"
    span = tool.find_span(text, "A类基金份额")
    assert span is not None
    start, end = span
    assert text[start:end] == "A 类基金份额"
    cstart, cend = tool.compact_offsets(text, start, end)
    assert tool.compact(text)[cstart:cend] == tool.compact("A类基金份额")


def test_drop_noop_replacement_becomes_satisfied():
    target = {
        "target_id": "T1", "rule_id": "G02", "group": "G02", "op": "replace",
        "scope": "main", "site_scope": "main", "paragraph_index": 92,
        "location": "x", "old_text": "A类基金份额", "required_text": "A类基金份额",
        "source_quote": "A类基金份额", "anchor_quote": None, "anchor_position": None,
        "requirement": "", "class_scope": [], "guide_paragraphs": [],
        "rationale": "", "compact_start": 0, "compact_end": 6,
        "old_text_sha256": "x", "paragraph_text_sha256": "y",
        "confidence": "high", "review_flags": [],
    }
    coverage = [{
        "rule_id": "G02", "scope": "main", "status": "target", "paragraph_index": 92,
        "reason": "", "evidence_quote": None,
    }]
    kept, cov, notes = tool.drop_noop_replacements([target], coverage)
    assert kept == []
    assert cov[0]["status"] == "satisfied"
    assert notes and "no-op" in notes[0]


def test_ensure_g13_splits_sentence_out_of_g12():
    text = (
        "5、赎回费用由赎回基金份额的基金份额持有人承担，在基金份额持有人赎回基金份额时收取。"
        "赎回费用归入基金财产的比例应根据相关规定执行，并在招募说明书中列示。"
        "其中，对持续持有期少于7日的投资者收取不低于1.50%的赎回费，并全额计入基金财产。"
    )
    para = _para(207, text, section="第六部分  基金份额的申购与赎回 > 六、申购和赎回的价格、费用及其用途")
    doc = _doc([para])
    g12 = {
        "target_id": "T1", "rule_id": "G12", "group": "G12", "op": "replace",
        "scope": "main", "site_scope": "main", "paragraph_index": 207,
        "location": para.section_path, "old_text": text[text.index("赎回费用归入"):].rstrip(),
        "required_text": "赎回费用全额计入基金财产。", "source_quote": text,
        "anchor_quote": None, "anchor_position": None, "requirement": "",
        "class_scope": [], "guide_paragraphs": [], "rationale": "",
        "compact_start": 0, "compact_end": 0, "old_text_sha256": "x",
        "paragraph_text_sha256": "y", "confidence": "high", "review_flags": [],
    }
    targets, coverage, notes = tool.ensure_g13_targets([g12], [], doc, {"G13": {"requirement": "delete 7-day", "source_paragraphs": []}})
    rules = sorted({t["rule_id"] for t in targets})
    assert rules == ["G12", "G13"]
    g12_out = next(t for t in targets if t["rule_id"] == "G12")
    g13_out = next(t for t in targets if t["rule_id"] == "G13")
    assert "持续持有期少于7" not in g12_out["old_text"]
    assert "持续持有期少于7" in g13_out["old_text"]
    assert g13_out["op"] == "delete"


def test_mandatory_checks_flags_missing_g09_for_multi_class():
    text = (
        "3、赎回金额的计算及处理方式：本基金赎回金额的计算详见《招募说明书》。"
        "本基金的赎回费率由基金管理人决定，并在招募说明书中列示。"
        "赎回金额为按实际确认的有效赎回份额乘以当日基金份额净值并扣除相应的费用，赎回金额单位为元。"
    )
    para = _para(0, text, section="第六部分  基金份额的申购与赎回 > 六、申购和赎回的价格、费用及其用途")
    doc = _doc([para])
    fund = {"class_count": 2, "has_sales_service_fee": True, "floating_management_fee": False}
    issues = tool.mandatory_checks(doc, fund, [], [])
    assert any("G09 missing target" in issue for issue in issues)


def test_selection_is_frozen_20_8_and_hashes_match_copy():
    selection = ROOT / "docs/evidence/selection-first-batch-20261028.json"
    data = json.loads(selection.read_text(encoding="utf-8"))
    assert data["counts"] == {"dev": 20, "holdout": 8, "total": 28}
    assert len(data["cases"]) == 28
    assert hashlib.sha256(selection.read_bytes()).hexdigest() == (
        "d89f40b5aca2b40397d7c11eb4262a98d92d0b2b8b1eac193058bf88815a185c"
    )
    ids = {c["case_id"] for c in data["cases"]}
    assert "BH06" in ids


def test_bh06_protection_detected_from_original_docx():
    selection = json.loads((ROOT / "docs/evidence/selection-first-batch-20261028.json").read_text(encoding="utf-8"))
    case = next(c for c in selection["cases"] if c["case_id"] == "BH06")
    path = ROOT / case["relative"]
    if not path.exists():
        pytest.skip("first-batch contract corpus is not present in this worktree")
    protection = tool.detect_protection(path)
    assert protection["protected"] is True
    assert protection["edit"] == "trackedChanges"


def test_tool_accepts_arbitrary_selection_and_output_flags():
    parser_source = TOOL.read_text(encoding="utf-8")
    for token in ("--selection", "--out", "--concurrency", "--provider-env", "--case", "--all"):
        assert token in parser_source
    assert "first-batch-28" not in parser_source
