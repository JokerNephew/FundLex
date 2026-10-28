import hashlib
import io
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from docx import Document

from fundlex.compare import compare_docx, generate_selection_artifacts
from fundlex.docx import DOCUMENT, DocxError


def _save_doc(path: Path, paragraphs: list[str], *, table: tuple[str, str] | None = None) -> None:
    document = Document()
    for value in paragraphs:
        document.add_paragraph(value)
    if table is not None:
        grid = document.add_table(rows=1, cols=2)
        grid.cell(0, 0).text = table[0]
        grid.cell(0, 1).text = table[1]
    document.save(path)


def _save_cell_doc(path: Path, paragraphs: list[str]) -> None:
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
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return payload, hashlib.sha256(encoded).hexdigest()


def _generate(tmp_path: Path, left_text: list[str], right_text: list[str], decisions: dict[str, str], *, tables=None):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save_doc(left, left_text, table=tables[0] if tables else None)
    _save_doc(right, right_text, table=tables[1] if tables else None)
    result, result_hash = _result(left, right)
    choices = {diff["id"]: decisions.get(diff["id"], next(iter(decisions.values())))
               for diff in result["diffs"]}
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    validation = generate_selection_artifacts(
        left, right, result, choices, final, redline,
        selection_epoch=3, result_sha256=result_hash)
    return left, right, final, redline, result, validation


def test_modify_choice_right_writes_real_final_and_redline(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path, ["前文", "费率为0.40%", "后文"], ["前文", "费率为0.30%", "后文"], {"D0001": "right"})
    assert validation.final_sha256 == hashlib.sha256(final.read_bytes()).hexdigest()
    assert validation.redline_sha256 == hashlib.sha256(redline.read_bytes()).hexdigest()
    reopened = Document(final)
    assert [paragraph.text for paragraph in reopened.paragraphs] == ["前文", "费率为0.30%", "后文"]
    with ZipFile(redline) as archive:
        xml = archive.read(DOCUMENT)
    assert b"w:ins" in xml and b"w:del" in xml
    assert validation.manifest[0]["selected_text"] == "0.30%"


def test_consecutive_modify_paragraphs_are_written_independently(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path,
        ["第一段费率为0.40%", "第二段费率为0.10%"],
        ["第一段费率为0.30%", "第二段费率为0.08%"],
        {"D0001": "right", "D0002": "left"},
    )
    # The two adjacent modified paragraphs share one alignment group; each
    # selected diff must still map to its own corresponding left paragraph.
    assert [diff["group_id"] for diff in result["diffs"]] == ["G0001", "G0001"]
    assert [paragraph.text for paragraph in Document(final).paragraphs] == [
        "第一段费率为0.30%", "第二段费率为0.10%"]
    assert len(validation.manifest) == 1
    with ZipFile(redline) as archive:
        xml = archive.read(DOCUMENT)
    assert xml.count(b"<w:ins ") == 1
    assert xml.count(b"<w:del ") == 1


def test_header_coverage_warning_does_not_block_body_selection(tmp_path):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    for path, body in ((left, "费率为0.40%"), (right, "费率为0.30%")):
        document = Document()
        document.add_paragraph(body)
        document.sections[0].header.paragraphs[0].text = "基金合同页眉"
        document.save(path)
    result, result_hash = _result(left, right)
    decisions = {diff["id"]: "right" for diff in result["diffs"]}
    validation = generate_selection_artifacts(
        left, right, result, decisions, tmp_path / "final.docx", tmp_path / "redline.docx",
        selection_epoch=1, result_sha256=result_hash)
    assert Document(tmp_path / "final.docx").paragraphs[0].text == "费率为0.30%"
    assert any("header" in warning for warning in validation.limitations)


def test_multiple_selected_modifications_in_one_group_are_written(tmp_path):
    _, _, final, _, _, validation = _generate(
        tmp_path,
        ["第一段费率为0.40%", "第二段费率为0.10%"],
        ["第一段费率为0.30%", "第二段费率为0.08%"],
        {"D0001": "right", "D0002": "right"},
    )
    assert [paragraph.text for paragraph in Document(final).paragraphs] == [
        "第一段费率为0.30%", "第二段费率为0.08%"]
    assert len(validation.manifest) == 2


def test_modify_choice_left_keeps_left_and_has_no_redline_for_unmodified_selection(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path, ["费率为0.40%"], ["费率为0.30%"], {"D0001": "left"})
    assert Document(final).paragraphs[0].text == "费率为0.40%"
    # A selection that explicitly keeps the left side has no physical edit;
    # the redline artifact still reports that no right-side operation exists.
    assert validation.manifest == ()
    with ZipFile(redline) as archive:
        assert b"w:ins" not in archive.read(DOCUMENT)


def test_paragraph_insert_is_written_and_redlined(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path, ["前文", "尾部"], ["前文", "新增整段", "尾部"], {"D0001": "right"})
    assert [paragraph.text for paragraph in Document(final).paragraphs] == [
        "前文", "新增整段", "尾部"]
    assert len(validation.manifest) == 1
    with ZipFile(redline) as archive:
        xml = archive.read(DOCUMENT)
    assert xml.count(b"<w:ins ") >= 2
    assert xml.count(b"<w:del ") == 0


def test_paragraph_delete_is_written_and_redlined(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path, ["前文", "删除整段", "尾部"], ["前文", "尾部"], {"D0001": "right"})
    assert [paragraph.text for paragraph in Document(final).paragraphs] == ["前文", "尾部"]
    assert len(validation.manifest) == 1
    with ZipFile(redline) as archive:
        xml = archive.read(DOCUMENT)
    assert xml.count(b"<w:ins ") == 0
    assert xml.count(b"<w:del ") >= 2


def test_two_paragraphs_replaced_by_two_paragraphs(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path, ["A1", "A2", "尾部"], ["B1", "B2", "尾部"],
        {"D0001": "right", "D0002": "right", "D0003": "right", "D0004": "right"})
    assert [paragraph.text for paragraph in Document(final).paragraphs] == ["B1", "B2", "尾部"]
    assert len(validation.manifest) == 4
    with ZipFile(redline) as archive:
        xml = archive.read(DOCUMENT)
    assert xml.count(b"<w:ins ") >= 2
    assert xml.count(b"<w:del ") >= 2


def test_cross_paragraph_split_is_written(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path, ["abcdefgh"], ["abcdX", "Yefgh"], {"D0001": "right"})
    assert [paragraph.text for paragraph in Document(final).paragraphs] == ["abcdX", "Yefgh"]
    assert len(validation.manifest) == 1
    with ZipFile(redline) as archive:
        xml = archive.read(DOCUMENT)
    assert xml.count(b"<w:ins ") >= 2
    assert xml.count(b"<w:del ") >= 1


def test_cross_paragraph_merge_is_written(tmp_path):
    left, right, final, redline, result, validation = _generate(
        tmp_path, ["abcdX", "Yefgh"], ["abcdefgh"], {"D0001": "right"})
    assert [paragraph.text for paragraph in Document(final).paragraphs] == ["abcdefgh"]
    assert len(validation.manifest) == 1
    with ZipFile(redline) as archive:
        xml = archive.read(DOCUMENT)
    assert xml.count(b"<w:ins ") >= 1
    assert xml.count(b"<w:del ") >= 2


def test_table_cell_paragraph_insert_delete_and_split(tmp_path):
    for paragraphs, changed, expected in (
            (["A", "B"], ["A", "X", "B"], ["A", "X", "B"]),
            (["A", "X", "B"], ["A", "B"], ["A", "B"]),
            (["abcdefgh"], ["abcdX", "Yefgh"], ["abcdX", "Yefgh"])):
        left, right = tmp_path / "left.docx", tmp_path / "right.docx"
        _save_cell_doc(left, paragraphs)
        _save_cell_doc(right, changed)
        result, result_hash = _result(left, right)
        decisions = {diff["id"]: "right" for diff in result["diffs"]}
        final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
        final.unlink(missing_ok=True); redline.unlink(missing_ok=True)
        validation = generate_selection_artifacts(
            left, right, result, decisions, final, redline,
            selection_epoch=1, result_sha256=result_hash)
        reopened = Document(final)
        assert [paragraph.text for paragraph in reopened.tables[0].cell(0, 0).paragraphs] == expected
        assert validation.manifest


def test_table_cell_selection_is_written_and_reopened(tmp_path):
    _, _, final, _, _, validation = _generate(
        tmp_path, [], [], {"D0001": "right"}, tables=(("条款内容：左侧", "固定"), ("条款内容：右侧", "固定")))
    assert Document(final).tables[0].cell(0, 0).text == "条款内容：右侧"
    assert Document(final).tables[0].cell(0, 1).text == "固定"
    assert validation.checks[-1] == "selected_text"


def test_pending_and_source_or_result_tampering_are_blocked(tmp_path):
    left = tmp_path / "left.docx"
    right = tmp_path / "right.docx"
    _save_doc(left, ["旧"],)
    _save_doc(right, ["新"],)
    result, result_hash = _result(left, right)
    with pytest.raises(DocxError, match="PENDING_SELECTIONS"):
        generate_selection_artifacts(left, right, result, {}, tmp_path / "f.docx", tmp_path / "r.docx",
                                     selection_epoch=1, result_sha256=result_hash)
    changed = dict(result)
    changed["diffs"] = [dict(result["diffs"][0], section="changed")]
    with pytest.raises(DocxError, match="SELECTION_RESULT_HASH_MISMATCH"):
        generate_selection_artifacts(left, right, changed, {"D0001": "right"}, tmp_path / "f.docx", tmp_path / "r.docx",
                                     selection_epoch=1, result_sha256=result_hash)


def test_table_row_structure_change_is_blocked_before_output(tmp_path):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    for path, rows in ((left, 1), (right, 2)):
        document = Document()
        table = document.add_table(rows=rows, cols=1)
        for index in range(rows):
            table.cell(index, 0).text = f"R{index}"
        document.save(path)
    result, result_hash = _result(left, right)
    decisions = {diff["id"]: "right" for diff in result["diffs"]}
    with pytest.raises(DocxError) as caught:
        generate_selection_artifacts(left, right, result, decisions, tmp_path / "f.docx", tmp_path / "r.docx",
                                     selection_epoch=1, result_sha256=result_hash)
    assert caught.value.code.startswith("SELECTION_BLOCK_")
