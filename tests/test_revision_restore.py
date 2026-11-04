"""FL-D1133 回补模块红线：原修订痕迹盖回+硬校验守卫。"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from lxml import etree

from fundlex.docx import DOCUMENT, Q
from fundlex.revision_restore import restore_source_revisions

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _para(inner: str) -> str:
    return f"<w:p><w:r><w:t xml:space=\"preserve\">{inner}</w:t></w:r></w:p>"


def _para_marked(text: str, mark_xml: str) -> str:
    return f"<w:p><w:r><w:t xml:space=\"preserve\">{text}</w:t></w:r>{mark_xml}</w:p>"


def _ins(rid: str, author: str, text: str, date: str = "2024-01-01T00:00:00Z") -> str:
    return (f"<w:ins w:id=\"{rid}\" w:author=\"{author}\" w:date=\"{date}\">"
            f"<w:r><w:t>{text}</w:t></w:r></w:ins>")


def _del(rid: str, author: str, text: str, date: str = "2024-01-01T00:00:00Z") -> str:
    return (f"<w:del w:id=\"{rid}\" w:author=\"{author}\" w:date=\"{date}\">"
            f"<w:r><w:delText>{text}</w:delText></w:r></w:del>")


def _docx(body_paras: list[str]) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>'
        + "".join(body_paras)
        + "<w:sectPr/></w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                   '<Default Extension="xml" ContentType="application/xml"/>'
                   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
                   '</Types>')
        z.writestr("_rels/.rels",
                   '<?xml version="1.0" encoding="UTF-8"?>'
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                   '</Relationships>')
        z.writestr(DOCUMENT, document.encode("utf-8"))
    return buf.getvalue()


def _read_xml(path: Path) -> etree._Element:
    with zipfile.ZipFile(path) as z:
        return etree.fromstring(z.read(DOCUMENT))


def _marks(root: etree._Element) -> list[tuple[str, str, str]]:
    out = []
    for node in root.iter():
        if node.tag in (Q("ins"), Q("del")):
            out.append((node.tag, node.get(Q("author"), ""), node.get(Q("id"), "")))
    return out


def _visible(p: etree._Element) -> str:
    chars = []
    for node in p.iter():
        if node.tag == Q("t") and not any(a.tag == Q("del") for a in node.iterancestors()):
            chars.append(node.text or "")
    return "".join(chars)


def test_restore_grafts_original_marks_and_never_loses_ours(tmp_path):
    original = _docx([
        _para("第一段干净"),
        _para_marked("第二段含", _ins("5", "王悦棋", "原作者插入句") + _del("6", "王悦棋", "原作者删的旧词")),
        _para("第三段干净"),
    ])
    redline = _docx([
        _para("第一段干净"),
        _para("第二段含原作者插入句"),  # 已接受（修订被归一吞掉）
        _para_marked("第三段干", _ins("1", "FundLex", "净·我方补丁")),
    ])
    path = tmp_path / "redline.docx"
    path.write_bytes(redline)
    report = restore_source_revisions(path, original, now_id_base=500)
    assert report["rolled_back"] is False
    assert report["restored_paragraphs"] == 1
    assert report["restored_marks"] == 2
    root = _read_xml(path)
    authors = {(tag, author) for tag, author, _ in _marks(root)}
    assert (f"{{{W_NS}}}ins", "王悦棋") in authors
    assert (f"{{{W_NS}}}del", "王悦棋") in authors
    assert (f"{{{W_NS}}}ins", "FundLex") in authors  # 我方痕迹绝不丢
    ids = {rid for _, _, rid in _marks(root)}
    assert "1" in ids and "5" not in ids and "6" not in ids  # 原 id 已换号,不撞 manifest
    texts = [_visible(p) for p in root.iter(Q("p"))]
    assert texts == ["第一段干净", "第二段含原作者插入句", "第三段干净·我方补丁"]


def test_restore_skips_unaligned_and_marked_targets(tmp_path):
    original = _docx([
        _para_marked("甲段", _ins("5", "王悦棋", "甲补")),
        _para_marked("乙段原文", _del("6", "王悦棋", "乙删")),
    ])
    redline = _docx([
        _para_marked("甲段", _ins("1", "FundLex", "我方也动过甲")),
        _para("乙段已被整体改写"),  # 文本不一致→不对齐→不盖
    ])
    path = tmp_path / "redline.docx"
    path.write_bytes(redline)
    report = restore_source_revisions(path, original, now_id_base=900)
    assert report["rolled_back"] is False
    assert report["restored_paragraphs"] == 0  # 两处都不得盖回
    root = _read_xml(path)
    assert all(author != "王悦棋" for _, author, _ in _marks(root))


def test_restore_no_source_revisions_is_noop(tmp_path):
    original = _docx([_para("全干净")])
    redline = _docx([_para("全干净")])
    path = tmp_path / "redline.docx"
    path.write_bytes(redline)
    before = path.read_bytes()
    report = restore_source_revisions(path, original)
    assert report["restored_paragraphs"] == 0
    assert path.read_bytes() == before  # 无事文件原样


def test_restore_bad_redline_rolls_back_without_touching(tmp_path):
    path = tmp_path / "redline.docx"
    path.write_bytes(b"not a zip at all")
    report = restore_source_revisions(path, _docx([_para("甲")]))
    assert report["rolled_back"] is True
    assert path.read_bytes() == b"not a zip at all"
