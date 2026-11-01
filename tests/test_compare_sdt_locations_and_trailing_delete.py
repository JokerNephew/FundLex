"""Regression tests for compare correctness audit findings.

FL-D541  parser ``pN`` counted body-level ``w:sdt`` paragraphs while the
          writer-side resolver (:func:`fundlex.docx._paragraph_element`) only
          counts the body's direct ``w:p`` children, shifting every location
          after a content control.  ``pN`` now counts direct children only and
          control paragraphs keep their own ``sdtN/pM`` address.
FL-D543  Several trailing deletions written as separate block operations used
          to corrupt the trailing-delete chain (duplicated marks, leftover
          empty survivor), forcing ``SELECTION_FINAL_TEXT_MISMATCH``.
FL-D544  Coverage no longer claims ``complete`` when only numbering labels or
          header/footer images differ.
FL-D545  Long paragraphs sharing boilerplate boundaries no longer pair when
          their middles are unrelated (>256-char heuristic gained the same
          character-overlap evidence the short-text branch already had).
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from docx import Document
from docx.oxml import OxmlElement

from fundlex.compare import compare_docx, generate_selection_artifacts, parse_compare_document
from fundlex.docx import DocxError

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def _raw_docx(body_xml, *, header_xml=None, numbering_xml=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   + ('<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>' if header_xml else '')
                   + ('<Override PartName="/word/numbering.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>' if numbering_xml else '')
                   + '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        rels = ('<?xml version="1.0" encoding="UTF-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                + ('<Relationship Id="rIdH" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>' if header_xml else '')
                + ('<Relationship Id="rIdN" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" Target="numbering.xml"/>' if numbering_xml else '')
                + '</Relationships>')
        z.writestr("word/_rels/document.xml.rels", rels)
        hdr_ref = '<w:headerReference w:type="default" r:id="rIdH"/>' if header_xml else ''
        z.writestr("word/document.xml",
                   f'<?xml version="1.0" encoding="UTF-8"?>'
                   f'<w:document {NS}><w:body>{body_xml}<w:sectPr>{hdr_ref}</w:sectPr></w:body></w:document>')
        if header_xml:
            z.writestr("word/header1.xml", f'<?xml version="1.0" encoding="UTF-8"?><w:hdr {NS}>{header_xml}</w:hdr>')
        if numbering_xml:
            z.writestr("word/numbering.xml", numbering_xml)
    return buf.getvalue()


def _para(text):
    return f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def _sdt(*paragraphs):
    return '<w:sdt><w:sdtContent>' + "".join(_para(p) for p in paragraphs) + '</w:sdtContent></w:sdt>'


def _save(path: Path, texts):
    document = Document()
    for text in texts:
        document.add_paragraph(text)
    document.save(path)


def _result(left: Path, right: Path):
    payload = compare_docx(left, right).to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return payload, hashlib.sha256(encoded).hexdigest()


def _generate_all_right(left: Path, right: Path, payload, payload_hash, tmp_path: Path):
    decisions = {diff["id"]: "right" for diff in payload["diffs"]}
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    return generate_selection_artifacts(left, right, payload, decisions, final, redline,
                                        selection_epoch=1, result_sha256=payload_hash), final, redline


# ---------------------------------------------------------------- FL-D541 --

SDT_PARAGRAPHS = [f"目录文档部件第{i}段" for i in range(24)]
BODY_PARAGRAPHS = [f"第{i:03d}条 本条款约定基金管理人应当按照诚实信用原则履行职责义务。" for i in range(60)]


def _sdt_doc(texts):
    return _raw_docx(_sdt(*SDT_PARAGRAPHS) + "".join(_para(t) for t in texts))


def test_body_sdt_paragraphs_do_not_consume_plain_locations(tmp_path):
    left = tmp_path / "left.docx"
    left.write_bytes(_sdt_doc(BODY_PARAGRAPHS))
    parsed = parse_compare_document(left)
    sdt_blocks = [b for b in parsed.blocks if b.location.startswith("sdt")]
    plain = [b for b in parsed.blocks if b.location.startswith("p")]
    assert len(sdt_blocks) == 24
    assert {b.location for b in sdt_blocks} == {f"sdt{i}/p{i}" for i in range(24)}
    # pN must count only the body's direct w:p children, matching the writer.
    assert [b.location for b in plain] == [f"p{i}" for i in range(60)]
    assert plain[17].raw_text == BODY_PARAGRAPHS[17]


@pytest.mark.parametrize("case", ["tail", "insert", "delete", "combined"])
def test_generate_after_body_sdt_addresses_correct_paragraphs(tmp_path, case):
    left = tmp_path / "left.docx"
    right = tmp_path / "right.docx"
    left.write_bytes(_sdt_doc(BODY_PARAGRAPHS))
    changed = list(BODY_PARAGRAPHS)
    if case in {"tail", "combined"}:
        changed[-1] = changed[-1] + "。【尾部新增条款内容】"
    if case in {"insert", "combined"}:
        changed.insert(20, "【插入的全新独立条款段落】。")
    if case in {"delete", "combined"}:
        del changed[40]
    right.write_bytes(_sdt_doc(changed))
    payload, payload_hash = _result(left, right)
    _, final, _ = _generate_all_right(left, right, payload, payload_hash, tmp_path)
    # Every final paragraph must match the adopted right document verbatim.
    assert [b.raw_text for b in parse_compare_document(final).blocks] == SDT_PARAGRAPHS + changed


def test_cell_sdt_does_not_shift_cell_paragraph_location(tmp_path):
    table = ('<w:tbl><w:tr><w:tc>'
             '<w:sdt><w:sdtContent>'
             '<w:p><w:r><w:t>控件内段A</w:t></w:r></w:p>'
             '<w:p><w:r><w:t>控件内段B</w:t></w:r></w:p>'
             '</w:sdtContent></w:sdt>'
             '<w:p><w:r><w:t>普通单元格段</w:t></w:r></w:p>'
             '</w:tc></w:tr></w:tbl>')
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    left.write_bytes(_raw_docx(_para("前文") + table))
    right.write_bytes(_raw_docx(_para("前文") + table.replace("普通单元格段", "普通单元格段改")))
    parsed = parse_compare_document(left)
    assert [b.location for b in parsed.blocks if b.container == "table"] == [
        "tbl0/r0/c0/sdt1/p0", "tbl0/r0/c0/sdt2/p1", "tbl0/r0/c0/p0"]
    payload, payload_hash = _result(left, right)
    _, final, _ = _generate_all_right(left, right, payload, payload_hash, tmp_path)
    cells = [b.raw_text for b in parse_compare_document(final).blocks if b.container == "table"]
    assert cells == ["控件内段A", "控件内段B", "普通单元格段改"]


# ---------------------------------------------------------------- FL-D543 --

BASE = [f"第{i:03d}条本条款约定基金管理人应当按照诚实信用原则履行职责义务。" for i in range(10)]


@pytest.mark.parametrize("kept", [9, 8, 7, 5])
def test_adjacent_trailing_deletes_generate(tmp_path, kept):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE)
    _save(right, BASE[:kept])
    payload, payload_hash = _result(left, right)
    _, final, _ = _generate_all_right(left, right, payload, payload_hash, tmp_path)
    assert [p.text for p in Document(final).paragraphs] == BASE[:kept]


def test_large_tail_delete_chain_joins_every_operation(tmp_path):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    texts = [f"第{i:03d}条本条款约定基金管理人应当按照诚实信用原则履行职责义务。" for i in range(250)]
    _save(left, texts)
    _save(right, texts[:247])
    payload, payload_hash = _result(left, right)
    _, final, _ = _generate_all_right(left, right, payload, payload_hash, tmp_path)
    paragraphs = [p.text for p in Document(final).paragraphs]
    assert paragraphs == texts[:247]
    assert len(paragraphs) == 247


def test_adjacent_middle_deletes_regression(tmp_path):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE)
    _save(right, BASE[:4] + BASE[6:])
    payload, payload_hash = _result(left, right)
    _, final, _ = _generate_all_right(left, right, payload, payload_hash, tmp_path)
    assert [p.text for p in Document(final).paragraphs] == BASE[:4] + BASE[6:]


def _assert_fails_closed(excinfo, *paths):
    assert excinfo.value.code == "SELECTION_BLOCK_STRUCTURE_UNSUPPORTED"
    assert not any(path.exists() for path in paths)


def test_trailing_deletes_with_interleaved_insert_fail_closed(tmp_path):
    """Inserts between the chain keeper and the doomed run cannot be written:
    the forced end-of-document survivor would land *after* the inserts and
    change paragraph order.  The selection is rejected, never mis-rendered."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE)
    _save(right, BASE[:7] + ["全新增条款甲与本组合任何旧条款均不相似。",
                             "全新增条款乙内容也不相似于任何旧条款。"])
    payload, payload_hash = _result(left, right)
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        _generate_all_right(left, right, payload, payload_hash, tmp_path)
    _assert_fails_closed(excinfo, final, redline, tmp_path / "final.docx")


def test_full_document_delete_fails_closed(tmp_path):
    """Deleting every body paragraph leaves no keeper paragraph to carry the
    final text; the writer cannot produce a valid empty document."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE)
    _save(right, ["。", "。"])
    # Only the deletes are adopted; the right-side paragraphs stay unselected.
    payload, payload_hash = _result(left, right)
    decisions = {diff["id"]: ("right" if diff["type"] == "delete" else "left")
                 for diff in payload["diffs"]}
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        generate_selection_artifacts(left, right, payload, decisions, final, redline,
                                     selection_epoch=1, result_sha256=payload_hash)
    _assert_fails_closed(excinfo, final, redline)


# ---------------------------------------------------------------- FL-D544 --

NUMBERING = ('<?xml version="1.0" encoding="UTF-8"?><w:numbering {ns}>'
             '<w:abstractNum w:abstractNumId="0"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
             '<w:numFmt w:val="decimal"/><w:lvlText w:val="%1、"/></w:lvl></w:abstractNum>'
             '<w:num w:numId="7"><w:abstractNumId w:val="0"/></w:num></w:numbering>').format(ns=NS)


def test_numbering_only_difference_is_not_silent_complete():
    body = ('<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="7"/></w:numPr></w:pPr>'
            '<w:r><w:t>条款内容相同</w:t></w:r></w:p>') * 8
    left = _raw_docx(body, numbering_xml=NUMBERING)
    right = _raw_docx(body, numbering_xml=NUMBERING.replace('<w:start w:val="1"/>',
                                                            '<w:start w:val="5"/>'))
    result = compare_docx(left, right)
    assert result.diffs == ()
    assert result.coverage.status == "incomplete"
    assert any(w.startswith("NUMBERING_LABEL_DIFFERENCE_NOT_COMPARED")
               for w in result.coverage.warnings)
    assert result.diagnostics["numbering_labels_not_compared"] is True


def test_numbering_same_labels_keep_complete_coverage():
    body = ('<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="7"/></w:numPr></w:pPr>'
            '<w:r><w:t>条款内容相同</w:t></w:r></w:p>') * 8
    result = compare_docx(_raw_docx(body, numbering_xml=NUMBERING),
                          _raw_docx(body, numbering_xml=NUMBERING))
    assert result.coverage.status == "complete"
    assert result.diagnostics["numbering_labels_not_compared"] is False


HEADER_IMAGE = ('<w:p><w:r><w:drawing><wp:inline '
                'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
                '<wp:extent cx="LONG" cy="100"/></wp:inline></w:drawing></w:r></w:p>')


def test_header_image_only_difference_is_not_silent_complete():
    body = _para("正文段落甲") * 3
    left = _raw_docx(body, header_xml=HEADER_IMAGE.replace("LONG", "100"))
    right = _raw_docx(body, header_xml=HEADER_IMAGE.replace("LONG", "200"))
    result = compare_docx(left, right)
    assert result.diffs == ()
    assert result.coverage.status == "incomplete"
    assert "UNSUPPORTED_VISIBLE_CONTENT:header:drawing" in result.coverage.warnings


def test_header_text_difference_keeps_plain_warning():
    body = _para("正文段落甲") * 3
    result = compare_docx(_raw_docx(body, header_xml=_para("抬头甲")),
                          _raw_docx(body, header_xml=_para("抬头乙")))
    assert "UNSUPPORTED_VISIBLE_CONTENT:header" in result.coverage.warnings
    assert result.coverage.status == "incomplete"


# ---------------------------------------------------------------- FL-D545 --

def test_long_boilerplate_paragraphs_with_disjoint_middles_never_pair():
    pre = "根据《中华人民共和国证券投资基金法》《公开募集证券投资基金运作管理办法》等法律法规的规定，"
    suf = "，并由基金管理人依照诚实信用、勤勉尽责的原则管理和运用基金财产，特此说明。"
    m1 = "本基金主要投资于具有良好流动性的金融工具，包括国内依法发行上市的股票、债券等" + "甲" * 160
    m2 = "本基金的投资组合比例为股票资产占基金资产的百分之六十至百分之九十五，债券资产占" + "乙" * 160
    a1, a2 = pre + m1 + suf, pre + m2 + suf
    assert max(len(a1), len(a2)) > 256
    a1p = a1.replace("流动性", "高流动性")
    a2p = a2.replace("百分之六十", "百分之五十五")

    def doc(texts):
        return _raw_docx("".join(_para(t) for t in texts))

    result = compare_docx(doc(["开头段一。", a1, "中间的独立条款段落。", a2, "结尾段。"]),
                          doc(["开头段一。", a2p, "中间的独立条款段落。", a1p, "结尾段。"]))
    cross = [d for d in result.diffs
             if "甲" * 20 in "".join(s.text for s in d.left_spans)
             and "乙" * 20 in "".join(s.text for s in d.right_spans)]
    assert cross == []


def test_presentation_runs_match_paragraph_text_in_single_pass(tmp_path):
    document = Document()
    paragraph = document.add_paragraph()
    run = paragraph.add_run("前文")
    run.bold = True
    paragraph.add_run().add_tab()
    paragraph.add_run().add_break()
    paragraph.add_run("后文")
    path = tmp_path / "runs.docx"
    document.save(path)
    block = parse_compare_document(path).blocks[0]
    assert block.raw_text == "前文\t\n后文"
    assert "".join(r.text for r in block.runs) == block.raw_text
    assert block.runs[0].bold is True
