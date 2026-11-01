"""Multi-shape guide parse quality matrix (FL-D898, 检查清单 M1-M12).

Each case pins one shape of "解析得好" from the owner checklist
(docs/GUIDE_PARSE_QUALITY_GATE.md): clean chain for the standard shape,
explicit failures for broken inputs, and the presentation red lines
(no internal identifiers in owner-visible strings, FL-D883/S5).
Everything here is deterministic — the scripted gateway replaces only the
network transport.  The real-model lane (M12) lives in
``tools/guide_parse_benchmark.py`` and is run manually per FL-D445.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from docx import Document
from docx.shared import RGBColor

from fundlex.guide import (GuideError, build_guide_document, extract_guide_source,
                           segment_guide_blocks, validate_parsed_guide)
from fundlex.guide_canary import executability_report
from fundlex.guide_quality import (INTERNAL_TOKENS, check_parse_quality,
                                   presentation_report)
from fundlex.guide_report import CODE_EXPLANATIONS, explain_code

# Reuse the canonical synthetic guide fixtures (pytest prepend mode puts the
# tests directory on sys.path for sibling imports).
from test_guide import (GUIDE_PARAGRAPHS, ScriptedGateway, build_docx,
                        clean_verification, patch_document_xml, valid_parsed,
                        worker_parsed)


# ---------------------------------------------------------------------------
# M1 — standard shape: bold domain headings, verbatim ops, full chain green
# ---------------------------------------------------------------------------

def test_m1_standard_shape_full_chain_is_clean(tmp_path):
    path = build_docx(tmp_path / "guide.docx", GUIDE_PARAGRAPHS)
    source = extract_guide_source(path)
    gateway = ScriptedGateway([("guide_parse", worker_parsed()),
                               ("guide_verify", clean_verification())])
    document = build_guide_document(source, gateway)
    validation = document["validation"]
    assert validation["clean"] is True
    assert not validation["errors"] and not validation["coverage_gaps"]
    canary = executability_report(document)
    assert canary["passed"] is True
    # Operations stay verbatim after the whole loop.
    normalized_texts = [operation.get("new_text") or operation.get("old_text")
                        for group in document["groups"]
                        for operation in group["operations"]]
    assert all(isinstance(text, str) and text.strip() for text in normalized_texts)
    checklist = check_parse_quality(source, document, validation=validation,
                                    canary=canary)
    assert checklist["verdict"] == "pass"
    assert checklist["blocking_failures"] == []


# ---------------------------------------------------------------------------
# M2 — no emphasis at all: still parseable, segmentation falls back cleanly
# ---------------------------------------------------------------------------

def test_m2_plain_text_headings_no_emphasis(tmp_path):
    paragraphs = [(text, "plain") for text, _ in GUIDE_PARAGRAPHS]
    path = build_docx(tmp_path / "plain.docx", paragraphs)
    source = extract_guide_source(path)
    assert all(paragraph.emphasis == "plain" for paragraph in source.paragraphs)
    # Same paragraph indices -> the same faithful parse validates clean.
    result = validate_parsed_guide(source, worker_parsed())
    assert result["errors"] == []
    assert result["coverage_gaps"] == []
    # No emphasised headings -> the whole guide is one block, not an error.
    assert len(segment_guide_blocks(source)) == 1


# ---------------------------------------------------------------------------
# M3 — generic enumerated structure only: blocks split, not flagged as errors
# ---------------------------------------------------------------------------

def test_m3_generic_enumerated_headings_segment(tmp_path):
    paragraphs = [("一、份额类别定义：", "bold"),
                  ("本基金分A类和C类份额。", "plain"),
                  ("二、销售服务费：", "bold"),
                  ("有销售服务费的类别调低费率。", "plain")]
    path = build_docx(tmp_path / "enum.docx", paragraphs)
    source = extract_guide_source(path)
    blocks = segment_guide_blocks(source)
    assert len(blocks) == 2
    assert blocks[0].label.startswith("一、")
    # Validation itself never complains about structure shape.
    parsed = {"groups": [{
        "rule_id": "G01", "title": "份额类别定义",
        "section_hint": "释义",
        "requirement": "说明本基金分为A类和C类份额，无需修改合同。",
        "operations": [{"op": "noop", "text": "本基金分A类和C类份额。",
                        "condition": {"kind": "none", "value": None},
                        "group_kind": "INDEPENDENT", "one_of_group": ""}],
        "old_text_variants": [], "slot_tokens": [], "references": [],
        "class_substitution": False, "source_paragraphs": [0, 1], "notes": "",
    }, {
        "rule_id": "G02", "title": "销售服务费",
        "section_hint": "基金费用与税收",
        "requirement": "有销售服务费的类别按指引调低费率表述。",
        "operations": [{"op": "noop", "text": "有销售服务费的类别调低费率。",
                        "condition": {"kind": "has_service_fee", "value": True},
                        "group_kind": "INDEPENDENT", "one_of_group": ""}],
        "old_text_variants": [], "slot_tokens": [], "references": [],
        "class_substitution": False, "source_paragraphs": [2, 3], "notes": "",
    }]}
    result = validate_parsed_guide(source, parsed)
    assert result["errors"] == []
    assert result["coverage_gaps"] == []


# ---------------------------------------------------------------------------
# M4/M5 — empty / corrupt inputs fail with explicit codes (S9)
# ---------------------------------------------------------------------------

def test_m4_empty_document_is_explicit(tmp_path):
    empty = build_docx(tmp_path / "empty.docx", [("", "plain"), ("  ", "plain")])
    with pytest.raises(GuideError) as exc:
        extract_guide_source(empty)
    assert exc.value.code == "GUIDE_SOURCE_EMPTY"
    assert explain_code(exc.value.code)["zh"]


def test_m5_corrupt_document_is_explicit(tmp_path):
    broken = tmp_path / "broken.docx"
    broken.write_bytes(b"definitely not a zip archive")
    with pytest.raises(GuideError) as exc:
        extract_guide_source(broken)
    assert exc.value.code == "GUIDE_SOURCE_UNREADABLE"
    assert explain_code(exc.value.code)["zh"]


# ---------------------------------------------------------------------------
# M6 — instructions written inside tables are extracted (FL-D904 fix)
# ---------------------------------------------------------------------------

def test_m6_table_content_is_extracted_and_parseable(tmp_path):
    document = Document()
    document.add_paragraph("指引正文第一段。")
    table = document.add_table(rows=2, cols=1)
    table.cell(0, 0).text = "表格内规则一：调低销售服务费率表述。"
    table.cell(1, 0).text = "表格内规则二：删除备案句。"
    document.add_paragraph("指引正文结尾段。")
    path = tmp_path / "table.docx"
    document.save(path)
    source = extract_guide_source(path)
    texts = [paragraph.text for paragraph in source.paragraphs]
    assert "表格内规则一：调低销售服务费率表述。" in texts
    assert "表格内规则二：删除备案句。" in texts
    # Body order is preserved: heading, table rows, trailing paragraph.
    assert texts[0] == "指引正文第一段。"
    assert texts[-1] == "指引正文结尾段。"
    # A rule can cite a table paragraph verbatim and by index.
    row_index = texts.index("表格内规则二：删除备案句。")
    parsed = {"groups": [{
        "rule_id": "G01", "title": "备案句删除",
        "section_hint": "基金的基本情况",
        "requirement": "按表格内规则二删除备案句相关表述。",
        "operations": [{"op": "delete", "old_text": "表格内规则二：删除备案句。",
                        "condition": {"kind": "none", "value": None},
                        "group_kind": "INDEPENDENT", "one_of_group": ""}],
        "old_text_variants": [], "slot_tokens": [], "references": [],
        "class_substitution": False, "source_paragraphs": [0, 1, row_index, row_index + 1],
        "notes": "",
    }]}
    result = validate_parsed_guide(source, parsed)
    assert result["errors"] == []
    assert result["coverage_gaps"] == []


# ---------------------------------------------------------------------------
# M7 — tracked deletions (incl. inside tables) never become guide text
# ---------------------------------------------------------------------------

def test_m7_deleted_text_stays_out_even_in_tables(tmp_path):
    document = Document()
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "有效内容。"
    document.add_paragraph("末段。")
    path = tmp_path / "deleted.docx"
    document.save(path)
    patch_document_xml(path, lambda xml: xml.replace(
        "有效内容。",
        "有效内容。<w:del w:id=\"1\" w:author=\"a\"><w:r><w:delText>已删除内容</w:delText>"
        "</w:r></w:del>", 1))
    source = extract_guide_source(path)
    joined = "\n".join(paragraph.text for paragraph in source.paragraphs)
    assert "已删除内容" not in joined
    assert "有效内容。" in joined


# ---------------------------------------------------------------------------
# M8 — context overflow is an explicit code, never a silent truncation
# ---------------------------------------------------------------------------

def test_m8_context_limit_is_explicit(tmp_path):
    path = build_docx(tmp_path / "guide.docx", GUIDE_PARAGRAPHS)
    source = extract_guide_source(path)
    gateway = ScriptedGateway([("guide_parse", worker_parsed())],
                              max_context_chars=200)  # floor is 1000 chars
    with pytest.raises(GuideError) as exc:
        build_guide_document(source, gateway)
    assert exc.value.code == "GUIDE_CONTEXT_LIMIT"


# ---------------------------------------------------------------------------
# M9 — internal identifiers in rule fields are caught by the red line (S5)
# ---------------------------------------------------------------------------

def test_m9_internal_tokens_in_rule_fields_are_detected():
    document = {"groups": [{
        "rule_id": "G01",
        "title": "class_count 分支规则",
        "section_hint": "释义",
        "requirement": "按 operations[0] 的 new_text 修改。",
        "operations": [{"op": "append", "new_text": "正常的新条款内容。",
                        "condition": {"kind": "none", "value": None},
                        "group_kind": "INDEPENDENT", "one_of_group": ""}],
        "notes": "wrong_text 已核对",
    }]}
    report = presentation_report(document)
    assert report["pass"] is False
    flagged_fields = {problem["field"] for problem in report["problems"]
                      if problem["level"] == "error"}
    assert {"title", "requirement", "notes"} <= flagged_fields
    assert any("class_count" in problem["detail"] for problem in report["problems"])


def test_m9_placeholder_and_numeric_titles_are_detected():
    document = {"groups": [{
        "rule_id": "G01", "title": "G01",
        "section_hint": "释义",
        "requirement": "追加一则关于申购费用的说明条款。",
        "operations": [{"op": "append", "new_text": "申购费用待定____",
                        "condition": {"kind": "none", "value": None},
                        "group_kind": "INDEPENDENT", "one_of_group": ""}],
    }]}
    report = presentation_report(document)
    assert report["pass"] is False
    details = " | ".join(problem["detail"] for problem in report["problems"])
    assert "标题只是编号" in details
    assert "占位符" in details


def test_m9_faithful_parse_passes_presentation():
    report = presentation_report(worker_parsed())
    assert report["pass"] is True
    assert report["stats"]["errors"] == 0


# ---------------------------------------------------------------------------
# M10 — validation detail is Chinese for owners, technical for the model
# ---------------------------------------------------------------------------

def test_m10_detail_is_chinese_and_detail_tech_keeps_machine_phrasing(tmp_path):
    path = build_docx(tmp_path / "guide.docx", GUIDE_PARAGRAPHS)
    source = extract_guide_source(path)
    broken = valid_parsed()
    broken["groups"][0]["operations"][0]["new_text"] = "改写过的文本。"
    broken["groups"][1]["operations"][0]["condition"] = {"kind": "class_count", "value": 3}
    result = validate_parsed_guide(source, broken)
    assert result["errors"]
    for issue in result["errors"] + result["warnings"]:
        detail = str(issue["detail"])
        # S5 red line: no internal vocabulary in the owner-facing sentence.
        for token in INTERNAL_TOKENS:
            assert token.lower() not in detail.lower(), (token, detail)
        # The technical phrasing survives for the repair context.
        assert issue["detail_tech"]
    tech = " | ".join(str(issue["detail_tech"]) for issue in result["errors"])
    assert "operations[0]" in tech
    assert "class_count" in tech
    details = " | ".join(str(issue["detail"]) for issue in result["errors"])
    assert "份额类别数量条件" in details
    assert "逐字" in details


def test_m10_repair_context_uses_technical_phrasing(tmp_path):
    from fundlex.guide import _render_repair_context
    validation = {"errors": [{"code": "GUIDE_TEXT_NOT_VERBATIM", "rule_id": "G01",
                              "detail": "第 1 个操作的新条款文本不是逐字摘录",
                              "detail_tech": "operations[0].new_text is not verbatim"}],
                  "warnings": [], "coverage_gaps": []}
    context = _render_repair_context(validation, {"findings": []})
    assert "operations[0].new_text is not verbatim" in context


# ---------------------------------------------------------------------------
# M11 — every surfaced issue code has a Chinese explanation (mapping complete)
# ---------------------------------------------------------------------------

_SURFACED_CODES = {
    # deterministic validation (guide.py)
    "GUIDE_GROUP_INVALID", "GUIDE_RULE_ID_INVALID", "GUIDE_SECTION_HINT_EMPTY",
    "GUIDE_TEXT_NOT_VERBATIM", "GUIDE_SLOT_NOT_IN_TEXT",
    "GUIDE_PARAGRAPH_RANGE_INVALID", "GUIDE_PARAGRAPH_ORDER",
    # extraction / build exits (guide.py)
    "GUIDE_SOURCE_UNREADABLE", "GUIDE_SOURCE_EMPTY", "GUIDE_CONTEXT_LIMIT",
    "GUIDE_PARSE_INVALID", "GUIDE_DOCUMENT_INVALID",
    # channel outcomes (guide_store / worker)
    "GUIDE_PARSE_FAILED", "GUIDE_VALIDATION_UNCLEAN",
    "GUIDE_OPERATION_REGISTRY_MISSING", "GUIDE_PARSE_ATTEMPTS_EXHAUSTED",
    "GUIDE_VERSION_SUPERSEDED", "GUIDE_COVERAGE_GAP",
    # executability canary (guide_canary.py)
    "GUIDE_CANARY_PARTIAL_IDENTITY", "GUIDE_CANARY_OP_UNREGISTERED",
    "GUIDE_CANARY_ROUTE_BLOCKED", "GUIDE_CANARY_DEAD_CONDITION",
    "GUIDE_CANARY_COMPILE_FAILED", "GUIDE_CANARY_COMPILE_MISMATCH",
    "GUIDE_CANARY_LEGACY_RULE_UNREGISTERED",
}


def test_m11_static_code_map_is_complete():
    missing = _SURFACED_CODES - set(CODE_EXPLANATIONS)
    assert not missing, f"缺少中文解释的问题码: {sorted(missing)}"
    for code in _SURFACED_CODES:
        info = explain_code(code)
        assert info["zh"] and not info["zh"].startswith("未归类")
        assert info["remedy"]


def test_m11_behavioral_codes_have_explanations(tmp_path):
    """Codes actually emitted by validation/canary runs must be explainable."""
    path = build_docx(tmp_path / "guide.docx", GUIDE_PARAGRAPHS)
    source = extract_guide_source(path)
    broken = valid_parsed()
    broken["groups"][0]["operations"][0]["new_text"] = "改写过的文本。"
    broken["groups"][1]["rule_id"] = "G09"
    broken["groups"][2]["source_paragraphs"] = [11, 12, 99]
    result = validate_parsed_guide(source, broken)
    codes = {issue["code"] for issue in result["errors"] + result["warnings"]}
    assert codes  # the fixture must actually break something
    for code in codes:
        info = explain_code(code)
        assert not info["zh"].startswith("未归类"), code
    canary = executability_report({"groups": worker_parsed()["groups"]})
    for finding in canary["fatal"] + canary["advisory"]:
        assert not explain_code(str(finding["code"]))["zh"].startswith("未归类")


# ---------------------------------------------------------------------------
# M12 — real-model benchmark lane exists (executed manually per FL-D445)
# ---------------------------------------------------------------------------

def test_m12_real_model_benchmark_tool_is_available():
    root = Path(__file__).resolve().parent.parent
    tool = root / "tools" / "guide_parse_benchmark.py"
    assert tool.is_file()
    content = tool.read_text(encoding="utf-8")
    assert "--engine-smoke" in content
