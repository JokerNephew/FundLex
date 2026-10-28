"""Compare remediation regressions: A01/A02 writer, A03 story, A04 structure, A05 scope."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from fundlex.compare import compare_docx, generate_selection_artifacts
from fundlex.compare.revisions import prepare_compare_input
from fundlex.compare.selection_writer import _Operation, _expected_sequence
from fundlex.docx import DOCUMENT, Q


def _save(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(path)


def _save_cell(path: Path, paragraphs: list[str]) -> None:
    document = Document()
    cell = document.add_table(rows=1, cols=1).cell(0, 0)
    cell.text = ""
    for index, text in enumerate(paragraphs):
        if index == 0:
            cell.paragraphs[0].text = text
        else:
            cell.add_paragraph(text)
    document.save(path)


def _result(left: Path, right: Path) -> tuple[dict, str]:
    payload = compare_docx(left, right).to_dict()
    digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
    return payload, digest


def _generate(tmp_path: Path, left_text: list[str], right_text: list[str],
              decisions: dict[str, str] | None = None, *, cell: bool = False):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    saver = _save_cell if cell else _save
    saver(left, left_text)
    saver(right, right_text)
    result, digest = _result(left, right)
    choices = ({diff["id"]: "right" for diff in result["diffs"]}
               if decisions is None else decisions)
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    validation = generate_selection_artifacts(
        left, right, result, choices, final, redline,
        selection_epoch=1, result_sha256=digest)
    return left, right, final, redline, result, validation


def _paragraph_texts(path: Path) -> list[str]:
    return [paragraph.text for paragraph in Document(path).paragraphs]


def _accepted_texts(redline: Path) -> list[str]:
    accepted = prepare_compare_input(redline.read_bytes())
    return [paragraph.text for paragraph in Document(io.BytesIO(accepted.data)).paragraphs]


def _canonical(path: Path) -> bytes:
    root = etree.fromstring(ZipFile(path).read(DOCUMENT))
    return etree.tostring(root, method="c14n")


def test_two_diffs_in_one_paragraph_with_first_growing(tmp_path):
    left = ["前文锚点", "本基金的管理费率为0.40%，托管费率为0.10%，上述费用按日计提。", "尾部锚点"]
    right = ["前文锚点", "本基金的管理费率为0.355%，托管费率为0.08%，上述费用按日计提。", "尾部锚点"]
    _, _, final, redline, result, _ = _generate(tmp_path, left, right)
    assert len(result["diffs"]) == 2
    assert _paragraph_texts(final) == right
    assert _accepted_texts(redline) == right


@pytest.mark.parametrize("left_fee,left_custody,right_fee,right_custody,expect_first", [
    ("0.40%", "0.10%", "0.355%", "0.08%", "0.355%"),
    ("0.40%", "0.10%", "0.4%", "0.100%", "0.4%"),
])
def test_partial_selection_of_same_paragraph_diffs(tmp_path, left_fee, left_custody,
                                                   right_fee, right_custody, expect_first):
    left = ["前文锚点", f"本基金的管理费率为{left_fee}，托管费率为{left_custody}，上述费用按日计提。", "尾部锚点"]
    right = ["前文锚点", f"本基金的管理费率为{right_fee}，托管费率为{right_custody}，上述费用按日计提。", "尾部锚点"]
    left_file, right_file = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left_file, left)
    _save(right_file, right)
    result, digest = _result(left_file, right_file)
    diffs = result["diffs"]
    assert len(diffs) == 2
    first, second = diffs[0]["id"], diffs[1]["id"]
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    generate_selection_artifacts(left_file, right_file, result,
                                 {first: "right", second: "left"}, final, redline,
                                 selection_epoch=2, result_sha256=digest)
    texts = _paragraph_texts(final)
    assert expect_first in texts[1] and left_custody in texts[1]
    assert _accepted_texts(redline) == texts


def test_expected_sequence_applies_same_point_inserts_in_order(tmp_path):
    from fundlex.compare.parser import parse_compare_document

    left = ["锚点", "abcd", "尾部"]
    right = ["锚点", "abXYcd", "尾部"]
    left_file, right_file = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left_file, left)
    _save(right_file, right)
    left_doc = parse_compare_document(left_file)
    right_doc = parse_compare_document(right_file)
    location = left_doc.blocks[1].location
    operations = [
        _Operation("D0001", "right", location, 2, 2, "", "X"),
        _Operation("D0002", "right", location, 2, 2, "", "Y"),
    ]
    sequence = _expected_sequence(left_doc, right_doc, operations, [])
    assert sequence[1][1] == "abXYcd"


def test_trailing_paragraph_delete_matches_independent_accept(tmp_path):
    _, _, final, redline, result, _ = _generate(tmp_path, ["前文", "删除末段"], ["前文"])
    assert _paragraph_texts(final) == ["前文"]
    assert _accepted_texts(redline) == ["前文"]
    assert _canonical(final) == _canonical_accepted(redline)


def _canonical_accepted(redline: Path) -> bytes:
    accepted = prepare_compare_input(redline.read_bytes())
    root = etree.fromstring(ZipFile(io.BytesIO(accepted.data)).read(DOCUMENT))
    return etree.tostring(root, method="c14n")


def test_trailing_split_and_merge_match_independent_accept(tmp_path):
    for left, right in ((["abcdefgh"], ["abcdX", "Yefgh"]),
                        (["abcdX", "Yefgh"], ["abcdefgh"])):
        directory = tmp_path / ("case-" + str(abs(hash(tuple(left)))))
        directory.mkdir()
        _, _, final, redline, _, _ = _generate(directory, left, right)
        assert _paragraph_texts(final) == right
        assert _accepted_texts(redline) == right
        assert _canonical(final) == _canonical_accepted(redline)


def test_trailing_table_cell_delete_matches_independent_accept(tmp_path):
    _, _, final, redline, _, _ = _generate(
        tmp_path, ["A", "删除"], ["A"], cell=True)
    cell_texts = [p.text for p in Document(final).tables[0].cell(0, 0).paragraphs]
    assert cell_texts == ["A"]
    accepted = prepare_compare_input(redline.read_bytes())
    accepted_cell = [p.text for p in Document(io.BytesIO(accepted.data)).tables[0].cell(0, 0).paragraphs]
    assert accepted_cell == ["A"]


def test_pure_structure_change_is_not_complete_without_a_warning(tmp_path):
    for index, (left, right) in enumerate((
            (["abcdefgh"], ["abcd", "efgh"]),
            (["abcd", "efgh"], ["abcdefgh"]),
            (["甲", "乙"], ["甲", "", "乙"]))):
        directory = tmp_path / f"structure-{index}"
        directory.mkdir()
        left_file, right_file = directory / "left.docx", directory / "right.docx"
        _save(left_file, left)
        _save(right_file, right)
        result = compare_docx(left_file, right_file).to_dict()
        assert result["summary"]["total"] == 0
        assert result["coverage"]["status"] == "incomplete"
        assert any(warning.startswith("STRUCTURAL_DIFFERENCE_NOT_COMPARED:")
                   for warning in result["coverage"]["warnings"])
        assert result["diagnostics"]["structural_not_compared"] is True
        assert result["comparison_scope"]["structure_not_compared"] is True


@pytest.mark.parametrize("name", ["word/header1.xml", "word/otherstory.xml",
                                  "word/media/legal-header.xml"])
def test_header_story_is_identified_by_opc_relationship_not_name(tmp_path, name):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    for target, text in ((left, "左侧页眉"), (right, "右侧页眉")):
        document = Document()
        document.add_paragraph("相同正文")
        document.sections[0].header.paragraphs[0].text = text
        document.save(target)
        if name != "word/header1.xml":
            with ZipFile(target) as archive:
                parts = {item: archive.read(item) for item in archive.namelist()}
            parts[name] = parts.pop("word/header1.xml")
            relative = name.removeprefix("word/")
            parts["word/_rels/document.xml.rels"] = parts["word/_rels/document.xml.rels"].replace(
                b"header1.xml", relative.encode())
            parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
                b"/word/header1.xml", ("/" + name).encode())
            with ZipFile(target, "w", ZIP_DEFLATED) as archive:
                for part, data in parts.items():
                    archive.writestr(part, data)
    result = compare_docx(left, right).to_dict()
    assert result["coverage"]["status"] == "incomplete"
    assert "UNSUPPORTED_VISIBLE_CONTENT:header" in result["coverage"]["warnings"]


def test_comparison_scope_and_numbering_collision_are_reported(tmp_path):
    def decorate(document: Document, side: str) -> None:
        numbering = document.part.numbering_part.element
        for abstract in numbering.findall(Q("abstractNum")):
            if abstract.get(Q("abstractNumId")) == "0":
                abstract.find(".//" + Q("numFmt")).set(Q("val"), "decimal" if side == "left" else "lowerLetter")
                abstract.find(".//" + Q("lvlText")).set(Q("val"), "%1." if side == "left" else "(%1)")
        if side == "right":
            ppr = document.paragraphs[1]._p.get_or_add_pPr()
            numpr = OxmlElement("w:numPr")
            ilvl = OxmlElement("w:ilvl")
            ilvl.set(qn("w:val"), "0")
            numpr.append(ilvl)
            numid = OxmlElement("w:numId")
            numid.set(qn("w:val"), "9")
            numpr.append(numid)
            ppr.append(numpr)

    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    for side, path, texts in (("left", left, ["前文", "尾部"]),
                              ("right", right, ["前文", "新增编号条款", "尾部"])):
        document = Document()
        for text in texts:
            document.add_paragraph(text)
        decorate(document, side)
        document.save(path)
    result, digest = _result(left, right)
    assert result["comparison_scope"]["text"] == "compared"
    assert result["comparison_scope"]["base_side"] == "left"
    assert result["comparison_scope"]["formatting_not_compared"] is True
    assert "horizontal_whitespace_collapsed" in result["comparison_scope"]["normalizations"]
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    validation = generate_selection_artifacts(
        left, right, result, {diff["id"]: "right" for diff in result["diffs"]},
        final, redline, selection_epoch=1, result_sha256=digest)
    assert any(warning.startswith("NUMBERING_DEFINITION_ADOPTED_LEFT:numId=9")
               for warning in validation.limitations)
    assert "FORMATTING_NOT_COMPARED:base_side=left" in validation.limitations
    assert validation.comparison_scope["base_side"] == "left"
    assert validation.to_dict()["comparison_scope"]["formatting_not_compared"] is True
    assert "accept_oracle" in validation.checks
