"""Overlay FundLex revisions on a document that already has tracked changes."""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest
from lxml import etree

from fundlex.docx import DocxError, generate_artifacts, inspect_docx, validate_edit_plan

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "tests/test_docx_structures.py"))
AUTHOR = "资金清算部"
FOREIGN = "法律部"


def _revision(tag: str, revision_id: int, author: str, text: str) -> str:
    tag_name = "w:delText" if tag == "del" else "w:t"
    return (f'<w:{tag} w:id="{revision_id}" w:author="{author}" '
            f'w:date="2026-10-01T00:00:00Z"><w:r><{tag_name} xml:space="preserve">'
            f'{text}</{tag_name}></w:r></w:{tag}>')


def plan_edit(source, location="p0", old="旧文", new="新文"):
    inspection = inspect_docx(source, full=True, allow_existing_revisions=True)
    paragraph = inspection.by_location(location)
    start = paragraph.text.index(old)
    return {"source_sha256": inspection.source_sha256, "verified": True,
            "location": location, "zone": paragraph.zone, "start": start,
            "end": start + len(old), "expected_old_text": old,
            "expected_old_hash": __import__("hashlib").sha256(
                old.encode()).hexdigest(),
            "template_id": "fixed", "replacement": new}


def build(tmp_path: Path, body: str, name: str = "contract.docx") -> Path:
    directory = tmp_path / name.replace(".docx", "")
    directory.mkdir()
    return HELPERS["package"](directory, body)


def test_inspection_uses_accepted_view_and_keeps_foreign_marks(tmp_path):
    body = ("<w:p>" + HELPERS["run"]("A") + _revision("ins", 10, FOREIGN, "B")
            + _revision("del", 11, FOREIGN, "C") + HELPERS["run"]("D") + "</w:p>")
    source = build(tmp_path, body)
    inspection = inspect_docx(source, full=True, allow_existing_revisions=True)
    span = inspection.by_location("p0")
    assert span.text.replace("\ufff9", "") == "ABD"
    assert "revision_content" not in span.reasons
    assert span.zone == "body"
    # Without the overlay flag the legacy rejection still applies.
    with pytest.raises(DocxError) as error:
        inspect_docx(source, full=True)
    assert error.value.code == "EXISTING_REVISION_UNSUPPORTED"


def test_overlay_edit_preserves_foreign_revisions_and_uses_our_author(tmp_path):
    body = ("<w:p>" + HELPERS["run"]("本基金应当修改该条款。") + "</w:p>"
            + "<w:p>" + _revision("ins", 10, FOREIGN, "对方新增") + "</w:p>")
    source = build(tmp_path, body)
    edit = plan_edit(source, "p0", "应当", "可以")
    plan = validate_edit_plan(source, [edit], {"fixed": "可以"},
                              allow_existing_revisions=True)
    redline, final = tmp_path / "redline.docx", tmp_path / "final.docx"
    generate_artifacts(source, plan, redline, final,
                       allow_existing_revisions=True, author=AUTHOR)

    red = etree.fromstring(__import__("zipfile").ZipFile(redline).read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    authors = [node.get(f"{{{ns['w']}}}author") for node in red.iter()
               if etree.QName(node).localname in {"ins", "del"}]
    assert FOREIGN in authors, "existing revisions must survive untouched"
    assert AUTHOR in authors, "our revisions must be distinguishable by author"
    # The foreign insertion is still a revision in the redline.
    foreign = [node for node in red.iter()
               if etree.QName(node).localname == "ins"
               and node.get(f"{{{ns['w']}}}author") == FOREIGN]
    assert len(foreign) == 1
    assert "对方新增" in "".join(foreign[0].itertext())

    # Final accepts every revision: no tracked changes remain, and both the
    # foreign insertion and our replacement are part of the accepted text.
    final_root = etree.fromstring(__import__("zipfile").ZipFile(final).read("word/document.xml"))
    assert not [node for node in final_root.iter()
                if etree.QName(node).localname in {"ins", "del"}]
    final_text = "".join(final_root.itertext())
    assert "对方新增" in final_text and "本基金可以修改该条款。" in final_text


def test_edit_inside_foreign_insertion_is_blocked(tmp_path):
    body = ("<w:p>" + _revision("ins", 10, FOREIGN, "对方新增条款。")
            + HELPERS["run"]("普通条款。") + "</w:p>")
    source = build(tmp_path, body)
    edit = plan_edit(source, "p0", "对方新增", "我方改写")
    with pytest.raises(DocxError) as error:
        validate_edit_plan(source, [edit], {"fixed": "我方改写"},
                           allow_existing_revisions=True)
    assert error.value.code in {"EDIT_CROSSES_BARRIER", "FOREIGN_INSERTION_EDIT_UNSUPPORTED",
                                "TARGET_OFFSET_MISMATCH", "EDIT_SOURCE_MISMATCH",
                                "EDIT_SPAN_INVALID", "RUN_STRUCTURE_UNSUPPORTED"}
