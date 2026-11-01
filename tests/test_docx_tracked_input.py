"""Tracked-changes task input: base flattening + engine overlay.

Product decision (2026-10-31): an uploaded contract that still carries Word
tracked changes is processed from its **accepted view**.  ``w:ins``/``w:moveTo``
content is kept, ``w:del``/``w:moveFrom`` content is removed, and the original
marks are flattened into the base text — they are never carried into the
delivery.  The recall engine's own new revisions are the only tracked changes
in the output; a rejected-view projection is out of scope this round.

All fixtures here are synthetic and built offline with python-docx plus direct
OOXML injection; the scripted gateway performs no real model calls.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from pathlib import Path

import pytest
from docx import Document
from lxml import etree

from fundlex.docx import (DOCUMENT, DocxError, ZipLimits, _read_parts_bytes,
                          _validate_package, inspect_docx, normalize_tracked_base)
from fundlex.recall_pipeline import process_recall_first

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NSM = {"w": W_NS}
AUTHOR_FOREIGN = "法律部"
AUTHOR_ENGINE = "资金清算部"
REVISION_MARKUP = (
    b"<w:ins", b"<w:del", b"moveFrom", b"moveTo",
    b"<w:rPrChange", b"<w:pPrChange", b"<w:delText",
)


def _q(local: str) -> str:
    return f"{{{W_NS}}}{local}"


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _rewrite_package(path: Path, mutate) -> bytes:
    with zipfile.ZipFile(path) as source:
        parts = {name: source.read(name) for name in source.namelist()}
    mutate(parts)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _document_root(parts: dict[str, bytes]) -> etree._Element:
    return etree.fromstring(parts[DOCUMENT])


def _save_root(parts: dict[str, bytes], root: etree._Element) -> None:
    parts[DOCUMENT] = etree.tostring(root, encoding="UTF-8", xml_declaration=True)


def _body_paragraphs(root: etree._Element) -> list[etree._Element]:
    return root.find(_q("body")).findall(_q("p"))


def _new_run(text: str, tag: str = "t") -> etree._Element:
    run = etree.Element(_q("r"))
    node = etree.SubElement(run, _q(tag))
    node.text = text
    node.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    return run


def _revision_wrapper(kind: str, rid: int, author: str = AUTHOR_FOREIGN,
                      date: str = "2026-10-01T00:00:00Z") -> etree._Element:
    node = etree.Element(_q(kind))
    node.set(_q("id"), str(rid))
    node.set(_q("author"), author)
    node.set(_q("date"), date)
    return node


def _append_revision_run(paragraph: etree._Element, kind: str, rid: int,
                         text: str, *, delete: bool = False) -> etree._Element:
    wrapper = _revision_wrapper(kind, rid)
    wrapper.append(_new_run(text, "delText" if delete else "t"))
    paragraph.append(wrapper)
    return wrapper


def _basic_document(path: Path) -> None:
    document = Document()
    document.add_paragraph("某某混合型证券投资基金基金合同")
    document.add_paragraph("一、前言。本基金合同经中国证监会核准。")
    document.add_paragraph("基金管理人可以在不违反法律法规的前提下适当调低赎回费率。")
    document.save(path)


def _flatten(data: bytes) -> bytes:
    result = normalize_tracked_base(data)
    assert result.had_tracked_changes is True
    return result.data


def _assert_fully_accepted(data: bytes) -> etree._Element:
    """Byte-level and package-level proof that no tracked marks survive."""
    parts = _read_parts_bytes(data, ZipLimits())
    _validate_package(parts, ZipLimits(), full=True)  # rejects any revision tag
    for tag in REVISION_MARKUP:
        assert tag not in parts[DOCUMENT], f"residual {tag!r} in document.xml"
    # Round-trip open through python-docx as a consumer would.
    reopened = Document(io.BytesIO(data))
    assert reopened.paragraphs
    return etree.fromstring(parts[DOCUMENT])


def _accepted_text(data: bytes) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = etree.fromstring(archive.read(DOCUMENT))
    return ["".join(node.text or "" for node in p.iter(_q("t")))
            for p in root.find(_q("body")).iter(_q("p"))]


def _normalized_case(tmp_path: Path, mutate) -> bytes:
    source = tmp_path / "source.docx"
    _basic_document(source)
    return _flatten(_rewrite_package(source, mutate))


# ---------------------------------------------------------------------------
# Unit matrix: every revision combination flattens to the accepted view
# ---------------------------------------------------------------------------

def test_tracked_ins_kept_in_base(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        _append_revision_run(_body_paragraphs(root)[0], "ins", 9001, "（2026年修订稿）")
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    root = _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert texts[0] == "某某混合型证券投资基金基金合同（2026年修订稿）"


def test_tracked_del_removed_from_base(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        _append_revision_run(_body_paragraphs(root)[1], "del", 9002, "本句已删除占位。", delete=True)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert texts[1] == "一、前言。本基金合同经中国证监会核准。"
    assert "本句已删除占位。" not in "".join(texts)


def test_tracked_move_pair_keeps_move_to_only(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        body = root.find(_q("body"))
        p0, p1 = _body_paragraphs(root)[0], _body_paragraphs(root)[1]
        # moveFrom (removed) in the first paragraph, moveTo (kept) in the second.
        origin = _revision_wrapper("moveFrom", 9003)
        origin.append(_new_run("被移走的旧句子。", "delText"))
        p0.append(origin)
        settled = _revision_wrapper("moveTo", 9004)
        settled.append(_new_run("被移入的新句子。"))
        p1.append(settled)
        anchor = body.find(_q("sectPr"))
        for local in ("moveFromRangeStart", "moveFromRangeEnd", "moveToRangeStart", "moveToRangeEnd"):
            marker = etree.Element(_q(local))
            marker.set(_q("name"), "move1")
            marker.set(_q("id"), "9010")
            body.insert(list(body).index(anchor) if anchor is not None else len(body), marker)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert "被移走的旧句子。" not in "".join(texts)
    assert texts[1].endswith("被移入的新句子。")


def test_tracked_revision_inside_hyperlink(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        paragraph = _body_paragraphs(root)[0]
        hyperlink = etree.SubElement(paragraph, _q("hyperlink"))
        hyperlink.set(_q("anchor"), "_Toc1")
        insertion = _revision_wrapper("ins", 9005)
        insertion.append(_new_run("（链接内插入）"))
        hyperlink.append(insertion)
        deletion = _revision_wrapper("del", 9006)
        deletion.append(_new_run("链接内被删", "delText"))
        hyperlink.append(deletion)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert texts[0].endswith("（链接内插入）")
    assert "链接内被删" not in "".join(texts)


def test_tracked_hyperlink_inside_insertion(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        paragraph = _body_paragraphs(root)[0]
        insertion = _revision_wrapper("ins", 9007)
        hyperlink = etree.SubElement(insertion, _q("hyperlink"))
        hyperlink.set(_q("anchor"), "_Toc2")
        hyperlink.append(_new_run("插入的链接文字"))
        paragraph.append(insertion)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert texts[0].endswith("插入的链接文字")


def test_tracked_revision_inside_sdt(tmp_path: Path):
    """SDT 是 funds_word 主流结构（93.6% 合同包含）：控件内修订同样固化。"""

    def mutate(parts):
        root = _document_root(parts)
        body = root.find(_q("body"))
        sdt = etree.Element(_q("sdt"))
        etree.SubElement(sdt, _q("sdtPr"))
        content = etree.SubElement(sdt, _q("sdtContent"))
        paragraph = etree.SubElement(content, _q("p"))
        paragraph.append(_new_run("控件内固定文字"))
        _append = _revision_wrapper("ins", 9008)
        _append.append(_new_run("控件内插入文字"))
        paragraph.append(_append)
        dropped = _revision_wrapper("del", 9009)
        dropped.append(_new_run("控件内被删文字", "delText"))
        paragraph.append(dropped)
        body.insert(1, sdt)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    root = _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert "控件内固定文字控件内插入文字" in texts
    assert "控件内被删文字" not in "".join(texts)
    # The content control itself is structure, not text: it must survive.
    assert list(root.iter(_q("sdt"))), "SDT wrapper must survive normalization"
    assert list(root.iter(_q("sdtContent")))


def test_tracked_nested_revisions(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        p0, p1 = _body_paragraphs(root)[0], _body_paragraphs(root)[1]
        # ins containing a del: plain runs survive, the deleted run is dropped.
        outer_ins = _revision_wrapper("ins", 9011)
        outer_ins.append(_new_run("外层插入甲"))
        nested_del = _revision_wrapper("del", 9012)
        nested_del.append(_new_run("内层被删", "delText"))
        outer_ins.append(nested_del)
        outer_ins.append(_new_run("外层插入乙"))
        p0.append(outer_ins)
        # del containing an ins: the whole deleted subtree is dropped.
        outer_del = _revision_wrapper("del", 9013)
        outer_del.append(_new_run("外层被删", "delText"))
        nested_ins = _revision_wrapper("ins", 9014)
        nested_ins.append(_new_run("内层插入"))
        outer_del.append(nested_ins)
        p1.append(outer_del)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert texts[0].endswith("外层插入甲外层插入乙")
    assert "内层被删" not in "".join(texts)
    assert "外层被删" not in "".join(texts)
    assert "内层插入" not in "".join(texts)


def test_tracked_revisions_inside_comments_story(tmp_path: Path):
    """批注正文里的修订被接受；批注范围与引用标记原样保留。"""

    def mutate(parts):
        parts["word/comments.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:comments xmlns:w="{W_NS}">'
            f'<w:comment w:id="0" w:author="{AUTHOR_FOREIGN}" w:date="2026-10-01T00:00:00Z">'
            '<w:p><w:r><w:t>批注原文</w:t></w:r>'
            f'<w:ins w:id="9015" w:author="{AUTHOR_FOREIGN}" w:date="2026-10-01T00:00:00Z">'
            '<w:r><w:t>批注内插入</w:t></w:r></w:ins>'
            f'<w:del w:id="9016" w:author="{AUTHOR_FOREIGN}" w:date="2026-10-01T00:00:00Z">'
            '<w:r><w:delText>批注内被删</w:delText></w:r></w:del>'
            "</w:p></w:comment></w:comments>"
        ).encode("utf-8")
        parts["[Content_Types].xml"] = parts["[Content_Types].xml"].replace(
            b"</Types>",
            b'<Override PartName="/word/comments.xml" ContentType='
            b'"application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"/>'
            b"</Types>",
        )
        rels = etree.fromstring(parts["word/_rels/document.xml.rels"])
        rel = etree.SubElement(rels, "{http://schemas.openxmlformats.org/package/2006/relationships}Relationship")
        rel.set("Id", "rIdComment1")
        rel.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments")
        rel.set("Target", "comments.xml")
        parts["word/_rels/document.xml.rels"] = etree.tostring(
            rels, encoding="UTF-8", xml_declaration=True)
        root = _document_root(parts)
        paragraph = _body_paragraphs(root)[0]
        start = etree.Element(_q("commentRangeStart")); start.set(_q("id"), "0")
        end = etree.Element(_q("commentRangeEnd")); end.set(_q("id"), "0")
        reference_run = etree.Element(_q("r"))
        etree.SubElement(reference_run, _q("commentReference")).set(_q("id"), "0")
        first = paragraph.findall(_q("r"))[0]
        index = list(paragraph).index(first)
        paragraph.insert(index, start)
        paragraph.append(end)
        paragraph.append(reference_run)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        comments = etree.fromstring(archive.read("word/comments.xml"))
        document = archive.read(DOCUMENT)
    comment_text = "".join(node.text or "" for node in comments.iter(_q("t")))
    assert comment_text == "批注原文批注内插入"
    assert "批注内被删" not in "".join(node.text or "" for node in comments.iter(_q("delText")))
    # Comment anchors in the main story survive the normalization untouched.
    assert b"commentRangeStart" in document and b"commentReference" in document


def test_tracked_property_change_snapshots_removed(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        paragraph = _body_paragraphs(root)[1]
        p_pr = paragraph.find(_q("pPr"))
        if p_pr is None:
            p_pr = etree.Element(_q("pPr"))
            paragraph.insert(0, p_pr)
        change = etree.SubElement(p_pr, _q("pPrChange"))
        change.set(_q("id"), "9017")
        change.set(_q("author"), AUTHOR_FOREIGN)
        change.set(_q("date"), "2026-10-01T00:00:00Z")
        snapshot = etree.SubElement(change, _q("pPr"))
        r_pr = None
        for run in paragraph.findall(_q("r")):
            r_pr = run.find(_q("rPr"))
            if r_pr is None:
                r_pr = etree.Element(_q("rPr"))
                run.insert(0, r_pr)
            break
        if r_pr is not None:
            r_change = etree.SubElement(r_pr, _q("rPrChange"))
            r_change.set(_q("id"), "9018")
            r_change.set(_q("author"), AUTHOR_FOREIGN)
            r_change.set(_q("date"), "2026-10-01T00:00:00Z")
            etree.SubElement(r_change, _q("rPr"))
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    assert _accepted_text(data)[1].startswith("一、前言。")


def test_tracked_deleted_paragraph_mark_joins_paragraphs(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        first = _body_paragraphs(root)[0]
        run = first.findall(_q("r"))[-1]
        # A dedicated trailing paragraph whose paragraph mark is deleted joins
        # its content into the following "前言" paragraph.
        extra = etree.Element(_q("p"))
        p_pr = etree.SubElement(extra, _q("pPr"))
        r_pr = etree.SubElement(p_pr, _q("rPr"))
        marker = _revision_wrapper("del", 9019)
        r_pr.append(marker)
        extra.append(_new_run("（应并入下一段）"))
        first.addnext(extra)
        _save_root(parts, root)

    data = _normalized_case(tmp_path, mutate)
    _assert_fully_accepted(data)
    texts = _accepted_text(data)
    assert texts[1] == "（应并入下一段）一、前言。本基金合同经中国证监会核准。"


def test_plain_input_passes_through_byte_identical(tmp_path: Path):
    source = tmp_path / "plain.docx"
    _basic_document(source)
    original = source.read_bytes()
    result = normalize_tracked_base(original)
    assert result.had_tracked_changes is False
    assert result.data == original
    assert result.revisions_accepted == 0
    assert result.base_sha256 == result.original_sha256 == hashlib.sha256(original).hexdigest()
    assert result.source_revisions == ()


def test_normalization_is_idempotent(tmp_path: Path):
    def mutate(parts):
        root = _document_root(parts)
        _append_revision_run(_body_paragraphs(root)[0], "ins", 9001, "（修订）")
        _save_root(parts, root)

    once = _normalized_case(tmp_path, mutate)
    twice = normalize_tracked_base(once)
    assert twice.had_tracked_changes is False
    assert twice.data == once


def test_normalize_rejects_unsupported_paragraph_merge(tmp_path: Path):
    """A deleted paragraph mark followed by a non-paragraph fails closed."""

    def mutate(parts):
        root = _document_root(parts)
        first = _body_paragraphs(root)[0]
        p_pr = first.find(_q("pPr"))
        if p_pr is None:
            p_pr = etree.Element(_q("pPr"))
            first.insert(0, p_pr)
        r_pr = etree.SubElement(p_pr, _q("rPr"))
        r_pr.append(_revision_wrapper("del", 9020))
        table = etree.Element(_q("tbl"))
        row = etree.SubElement(table, _q("tr"))
        cell = etree.SubElement(row, _q("tc"))
        cell_p = etree.SubElement(cell, _q("p"))
        cell_p.append(_new_run("表格内容"))
        first.addnext(table)
        _save_root(parts, root)

    source = tmp_path / "source.docx"
    _basic_document(source)
    data = _rewrite_package(source, mutate)
    with pytest.raises(DocxError) as captured:
        normalize_tracked_base(data)
    assert captured.value.code == "REVISION_PARAGRAPH_MERGE_UNSUPPORTED"


# ---------------------------------------------------------------------------
# End-to-end (scripted gateway, offline): new marks on the flattened base
# ---------------------------------------------------------------------------

def _tracked_contract(path: Path) -> None:
    """Synthetic recall contract carrying foreign tracked changes.

    Foreign ``法律部`` marks: an insertion inside the fee-adjustment paragraph
    (a paragraph the engine edits) and a deletion in the preface paragraph.
    """
    from test_recall_core import build_contract

    build_contract(path)

    def mutate(parts):
        root = _document_root(parts)
        paragraphs = _body_paragraphs(root)
        # Insertion appended to the FEE_ADJUSTMENT paragraph (engine target).
        target = next(p for p in paragraphs
                      if "调低赎回费率" in "".join(n.text or "" for n in p.iter(_q("t"))))
        _append_revision_run(target, "ins", 9001, "（法律部意见：维持原表述）")
        # Deletion appended to the preface paragraph (never edited).
        preface = next(p for p in paragraphs
                       if "经中国证监会核准" in "".join(n.text or "" for n in p.iter(_q("t"))))
        _append_revision_run(preface, "del", 9002, "（法律部删去的旧句）", delete=True)
        _save_root(parts, root)

    path.write_bytes(_rewrite_package(path, mutate))


def _scripted_run(tmp_path: Path, source: Path):
    from test_recall_pipeline import PipelineGateway, base_responses, guide_document

    output_dir = tmp_path / "out"
    model = PipelineGateway(base_responses())
    report = process_recall_first(source, output_dir, guide_document=guide_document(),
                                  gateway=model)
    return output_dir, report


def test_pipeline_flattens_input_and_layers_fundlex_marks(tmp_path: Path):
    source = tmp_path / "tracked-contract.docx"
    _tracked_contract(source)
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    source_size = source.stat().st_size

    output_dir, report = _scripted_run(tmp_path, source)

    assert report["delivery_status"] == "complete", json.dumps(
        {"errors": report.get("errors"), "unresolved": report.get("unresolved")},
        ensure_ascii=False, default=str)[:2000]
    # Traceability: the run is bound to the uploaded file, and the flattened
    # base plus the pre-existing revision inventory are recorded.
    assert report["base_had_tracked_changes"] is True
    assert report["source_sha256"] == original_sha
    assert re.fullmatch(r"[0-9a-f]{64}", report["normalized_base_sha256"])
    assert report["normalized_base_sha256"] != original_sha
    inventory = report["source_revisions"]
    assert inventory["authors"] == [AUTHOR_FOREIGN]
    assert {item["kind"] for item in inventory["items"]} == {"ins", "del"}
    # The user's original upload is never modified in place.
    assert source.read_bytes() and hashlib.sha256(source.read_bytes()).hexdigest() == original_sha
    assert source.stat().st_size == source_size

    redline = (output_dir / "redline.docx").read_bytes()
    final = (output_dir / "final.docx").read_bytes()
    red_root = etree.fromstring(_read_parts_bytes(redline, ZipLimits())[DOCUMENT])

    authors = {
        etree.QName(node).localname: node.get(_q("author"), "")
        for node in red_root.iter() if etree.QName(node).localname in {"ins", "del"}
    }
    assert authors, "redline must carry the engine's tracked changes"
    assert set(authors.values()) == {AUTHOR_ENGINE}
    for tag in (b"moveFrom", b"moveTo"):
        assert tag not in _read_parts_bytes(redline, ZipLimits())[DOCUMENT]

    # Flattened foreign insertion now reads as plain base text, and the same
    # paragraph carries the engine's own new revision pair.
    flat_insertion = "（法律部意见：维持原表述）"
    red_plain = "".join(node.text or "" for node in red_root.iter(_q("t")))
    assert flat_insertion in red_plain
    fee_paragraph = next(
        p for p in red_root.find(_q("body")).iter(_q("p"))
        if flat_insertion in "".join(n.text or "" for n in p.iter())
    )
    fee_marks = {etree.QName(node).localname for node in fee_paragraph.iter()
                 if etree.QName(node).localname in {"ins", "del"}}
    assert fee_marks == {"ins", "del"}

    # The accepted final has no tracked marks at all and shows the accepted view.
    final_parts = _read_parts_bytes(final, ZipLimits())
    for tag in REVISION_MARKUP:
        assert tag not in final_parts[DOCUMENT]
    final_texts = _accepted_text(final)
    joined = "".join(final_texts)
    assert flat_insertion in joined
    assert "（法律部删去的旧句）" not in joined
    assert "调低销售服务费率" in joined
    # Accept-all and the engine final are byte-identical views.
    assert report["output_validation"]["final_sha256"] == hashlib.sha256(final).hexdigest()
    assert report["output_validation"]["redline_sha256"] == hashlib.sha256(redline).hexdigest()
    # Round-trip through python-docx.
    assert Document(io.BytesIO(final)).paragraphs
    assert Document(io.BytesIO(redline)).paragraphs
    # The input cleanup is gone with the run.
    assert not list(output_dir.glob("fundlex-base-*"))


def test_pipeline_plain_input_reports_no_tracked_base(tmp_path: Path):
    from test_recall_core import build_contract

    source = tmp_path / "contract.docx"
    build_contract(source)
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()

    _, report = _scripted_run(tmp_path, source)

    assert report["delivery_status"] == "complete"
    assert report["base_had_tracked_changes"] is False
    assert "normalized_base_sha256" not in report
    assert "source_revisions" not in report
    assert report["source_sha256"] == original_sha


def test_selection_works_on_flattened_redline(tmp_path: Path):
    """Public review (selective accept/reject) consumes base-flattened reports."""
    from fundlex.selective import generate_selected_artifact, generate_selected_redline

    source = tmp_path / "tracked-contract.docx"
    _tracked_contract(source)
    output_dir, report = _scripted_run(tmp_path, source)
    assert report["delivery_status"] == "complete"

    selected_final = tmp_path / "selected-final.docx"
    result = generate_selected_artifact(output_dir / "redline.docx", selected_final,
                                        report, decisions={})
    # Byte-identical ZIPs are not guaranteed across writers; compare canonical
    # XML, the same equivalence the engine relies on (empty `<w:t/>` vs
    # `<w:t></w:t>` serializations are c14n-identical).
    selected_parts = _read_parts_bytes(selected_final.read_bytes(), ZipLimits())
    final_parts = _read_parts_bytes((output_dir / "final.docx").read_bytes(), ZipLimits())
    assert selected_parts.keys() == final_parts.keys()
    for name in final_parts:
        if name.endswith(".xml"):
            assert etree.tostring(etree.fromstring(selected_parts[name]), method="c14n") == \
                etree.tostring(etree.fromstring(final_parts[name]), method="c14n"), name
        else:
            assert selected_parts[name] == final_parts[name], name
    assert result.accepted and not result.rejected

    selected_redline = tmp_path / "selected-redline.docx"
    generate_selected_redline(output_dir / "redline.docx", selected_redline,
                              report, decisions={})
    kept = _read_parts_bytes(selected_redline.read_bytes(), ZipLimits())[DOCUMENT]
    assert AUTHOR_ENGINE.encode() in kept
    # The foreign author survives only as flattened base *text*, never as the
    # author of a tracked mark.
    assert b'w:author="' + AUTHOR_FOREIGN.encode() + b'"' not in kept
    assert "（法律部意见：维持原表述）".encode() in kept
