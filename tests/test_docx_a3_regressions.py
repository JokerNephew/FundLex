"""Regressions for the A3 DOCX/selective blind-audit findings (2026-10-31).

A3-F1  Overlay revision id parity: foreign revision ids have no parity
       contract, so generated del_id must be forced odd (ins_id = del_id + 1)
       or every selective-review artifact endpoint fails closed.
A3-F2  Persistent barriers (w:tab, hyperlink results, ...) before the edit
       span survive into the final package; final-text and run-format checks
       must compare expected and actual in the same plain view instead of
       stripping all barriers from one side only.
A3-F3  Dropping one half of a bookmark range inside an edit span must not
       leave an orphaned bookmarkStart/bookmarkEnd behind.
A3-F4  No-op edits (replacement == expected_old_text) are rejected.

Synthetic packages are built inside the tests; real contracts only appear in
skipped-when-absent smoke checks at the bottom.
"""
from __future__ import annotations

import hashlib
import runpy
from pathlib import Path
from zipfile import ZipFile

import pytest
from lxml import etree

from fundlex import docx as editor
from fundlex.selective import (generate_selected_artifact,
                               generate_selected_redline, resolve_selection)

ROOT = Path(__file__).resolve().parents[1]
HELPERS = runpy.run_path(str(ROOT / "tests/test_docx_structures.py"))

FOREIGN = "法律部"
AUTHOR = "资金清算部"


def _revision(tag: str, revision_id: int, author: str, text: str) -> str:
    child = "w:delText" if tag == "del" else "w:t"
    return (f'<w:{tag} w:id="{revision_id}" w:author="{author}" '
            f'w:date="2026-10-01T00:00:00Z"><w:r><{child} xml:space="preserve">'
            f'{text}</{child}></w:r></w:{tag}>')


def _build(tmp_path: Path, body: str, extra=None, name: str = "fixture.docx") -> Path:
    directory = tmp_path / name.replace(".docx", "")
    directory.mkdir(exist_ok=True)
    return HELPERS["package"](directory, body, extra)


def _plan(source: Path, location: str, old: str, new: str, *, overlay: bool = False):
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=overlay)
    paragraph = inspection.by_location(location)
    start = paragraph.text.index(old)
    return {
        "source_sha256": inspection.source_sha256, "verified": True,
        "location": location, "zone": paragraph.zone, "start": start,
        "end": start + len(old), "expected_old_text": old,
        "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
        "template_id": "fixed", "replacement": new,
    }


def _generate(source: Path, tmp_path: Path, location="p0", old="旧文", new="新文",
              *, overlay: bool = False, name: str = "out"):
    plan = editor.validate_edit_plan(source, [_plan(source, location, old, new, overlay=overlay)],
                                     {"fixed": new}, allow_existing_revisions=overlay)
    redline = tmp_path / f"{name}-redline.docx"
    final = tmp_path / f"{name}-final.docx"
    validation = editor.generate_artifacts(source, plan, redline, final,
                                           allow_existing_revisions=overlay, author=AUTHOR)
    return redline, final, validation


def _report(validation) -> dict:
    return {"revision_manifest": [dict(item) for item in validation.manifest],
            "source_revision_manifest": [dict(item) for item in validation.source_revisions]}


def _bookmark_ids(path: Path) -> tuple[list[str], list[str]]:
    root = etree.fromstring(ZipFile(path).read(editor.DOCUMENT))
    starts = [node.get(editor.Q("id"), "") for node in root.iter(editor.Q("bookmarkStart"))]
    ends = [node.get(editor.Q("id"), "") for node in root.iter(editor.Q("bookmarkEnd"))]
    return starts, ends


# ---------------------------------------------------------------- A3-F1

@pytest.mark.parametrize("foreign_id", [2, 99, 100, 101])
def test_overlay_revision_id_parity_keeps_manifest_resolvable(tmp_path, foreign_id):
    source = _build(tmp_path, "<w:p>" + _revision("ins", foreign_id, FOREIGN, "外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    redline, _, validation = _generate(source, tmp_path, overlay=True)
    pair = validation.manifest[0]
    assert pair["del_id"] % 2 == 1
    assert pair["ins_id"] == pair["del_id"] + 1
    # The solver must accept what generation emitted, for every foreign id
    # parity (previously odd foreign max ids made this raise
    # REVISION_MANIFEST_INVALID).
    verdict = resolve_selection(validation.manifest, {pair["del_id"]: "reject"})
    assert verdict.rejected == (pair["del_id"],)
    report = _report(validation)
    selected = generate_selected_artifact(redline, tmp_path / "sel-final.docx",
                                          report, {pair["del_id"]: "reject"})
    assert selected.rejected == (pair["del_id"],)
    generate_selected_redline(redline, tmp_path / "sel-redline.docx", report,
                              {pair["del_id"]: "reject"})


@pytest.mark.parametrize("foreign_id", [100, 101])
def test_overlay_header_revision_id_parity_keeps_manifest_resolvable(tmp_path, foreign_id):
    header = ('<w:hdr xmlns:w="' + editor.W + '"><w:p>'
              + _revision("ins", foreign_id, FOREIGN, "页眉新增") + "</w:p></w:hdr>").encode()
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("旧文") + "</w:p>",
                    extra={"word/header1.xml": header})
    redline, _, validation = _generate(source, tmp_path, overlay=True)
    pair = validation.manifest[0]
    assert pair["del_id"] % 2 == 1
    assert pair["ins_id"] == pair["del_id"] + 1
    verdict = resolve_selection(validation.manifest, {pair["del_id"]: "reject"})
    assert verdict.rejected == (pair["del_id"],)
    generate_selected_artifact(redline, tmp_path / "sel-final.docx", _report(validation),
                               {pair["del_id"]: "reject"})


def test_plain_document_ids_still_start_at_one(tmp_path):
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("旧文") + "</w:p>")
    _, _, validation = _generate(source, tmp_path)
    assert validation.manifest[0]["del_id"] == 1
    assert validation.manifest[0]["ins_id"] == 2


# ---------------------------------------------------------------- A3-F2

def test_tab_run_before_target_edit_generates(tmp_path):
    """（二）⇥投资限制: a w:tab sharing the first run must not cause
    FINAL_TEXT_MISMATCH for an edit entirely after the barrier."""
    source = _build(tmp_path, '<w:p><w:r><w:t>（二）</w:t><w:tab/></w:r>'
                    + HELPERS["run"]("投资限制说明") + "</w:p>")
    redline, final, validation = _generate(source, tmp_path, old="投资限制说明",
                                           new="投资限制新文")
    final_text = editor.inspect_docx(final, full=True).by_location("p0").text
    assert final_text.replace(editor.BARRIER, "") == "（二）投资限制新文"
    assert not redline.read_bytes() == final.read_bytes()


def test_standalone_tab_between_runs_before_target_edit_generates(tmp_path):
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("（二）")
                    + '<w:r><w:tab/></w:r>' + HELPERS["run"]("投资限制说明") + "</w:p>")
    _, final, _ = _generate(source, tmp_path, old="投资限制说明", new="投资限制新文")
    final_text = editor.inspect_docx(final, full=True).by_location("p0").text
    assert final_text.replace(editor.BARRIER, "") == "（二）投资限制新文"


def test_hyperlink_before_target_edit_generates(tmp_path):
    source = _build(tmp_path, "<w:p><w:hyperlink>" + HELPERS["run"]("目录链接")
                    + "</w:hyperlink>" + HELPERS["run"]("投资限制说明") + "</w:p>")
    _, final, _ = _generate(source, tmp_path, old="投资限制说明", new="投资限制新文")
    final_text = editor.inspect_docx(final, full=True).by_location("p0").text
    assert final_text.replace(editor.BARRIER, "") == "目录链接投资限制新文"


def test_overlay_tab_and_foreign_revision_before_target(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, FOREIGN, "外方")
                    + '<w:r><w:t>（二）</w:t><w:tab/></w:r>'
                    + HELPERS["run"]("投资限制说明") + "</w:p>")
    redline, final, validation = _generate(source, tmp_path, old="投资限制说明",
                                           new="投资限制新文", overlay=True)
    final_text = editor.inspect_docx(final, full=True).by_location("p0").text
    assert final_text.replace(editor.BARRIER, "") == "外方（二）投资限制新文"
    assert validation.manifest[0]["del_id"] == 11
    resolve_selection(validation.manifest, {})
    # The same-barrier edit must also survive the per-edit selection path.
    report = _report(validation)
    generate_selected_artifact(redline, tmp_path / "sel.docx", report,
                               {validation.manifest[0]["del_id"]: "accept"})


def test_edit_span_crossing_tab_still_rejected(tmp_path):
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("左文")
                    + '<w:r><w:tab/></w:r>' + HELPERS["run"]("右文") + "</w:p>")
    plan = _plan(source, "p0", "左文\ufff9右文", "新文")
    with pytest.raises(editor.DocxError) as error:
        editor.validate_edit_plan(source, [plan], {"fixed": "新文"})
    assert error.value.code == "EDIT_CROSSES_BARRIER"


# ---------------------------------------------------------------- A3-F3

def _bm_start(bid: int) -> str:
    return f'<w:bookmarkStart w:id="{bid}" w:name="bm{bid}"/>'


def _bm_end(bid: int) -> str:
    return f'<w:bookmarkEnd w:id="{bid}"/>'


def test_bookmark_pair_fully_inside_span_still_dropped(tmp_path):
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("甲") + _bm_start(7)
                    + _bm_end(7) + HELPERS["run"]("乙") + "</w:p>")
    _, final, _ = _generate(source, tmp_path, old="甲乙", new="新文")
    assert _bookmark_ids(final) == ([], [])


@pytest.mark.parametrize("mode", ["start_inside", "end_inside"])
def test_bookmark_partner_in_same_paragraph_removed_pairwise(tmp_path, mode):
    """One half inside the edit span, the partner a sibling in the same
    paragraph: the writer removes the pair, never an orphan."""
    if mode == "start_inside":
        # bookmarkStart sits between the two selected runs (dropped), its
        # bookmarkEnd survives just past the last selected run.
        body = ("<w:p>" + HELPERS["run"]("前缀甲") + HELPERS["run"]("目标乙")
                + _bm_start(7) + HELPERS["run"]("后缀丙") + _bm_end(7) + "</w:p>")
        old = "目标乙后缀丙"
    else:
        body = ("<w:p>" + _bm_start(7) + HELPERS["run"]("前缀甲") + _bm_end(7)
                + HELPERS["run"]("目标乙") + "</w:p>")
        old = "前缀甲目标乙"
    source = _build(tmp_path, body)
    redline, final, _ = _generate(source, tmp_path, old=old, new="新文")
    # Whatever remains of bookmark 7 must come in pairs; here the whole range
    # collapsed, so nothing may be left.
    assert _bookmark_ids(final) == ([], [])
    assert _bookmark_ids(redline) == ([], [])
    final_text = editor.inspect_docx(final, full=True).by_location("p0").text
    assert "新文" in final_text


def test_bookmark_range_fully_outside_span_survives_untouched(tmp_path):
    """A bookmark wrapping the edit but with both markers outside the selected
    run range keeps both halves exactly where they were."""
    source = _build(tmp_path, "<w:p>" + _bm_start(7) + HELPERS["run"]("前缀甲")
                    + HELPERS["run"]("目标乙") + _bm_end(7) + "</w:p>")
    redline, final, _ = _generate(source, tmp_path, old="目标乙", new="新文")
    assert _bookmark_ids(final) == (["7"], ["7"])
    assert _bookmark_ids(redline) == (["7"], ["7"])


def test_bookmark_partner_in_other_paragraph_rejected_fail_closed(tmp_path):
    body = ("<w:p>" + HELPERS["run"]("甲") + _bm_start(7) + HELPERS["run"]("乙")
            + "</w:p><w:p>" + HELPERS["run"]("尾") + _bm_end(7) + "</w:p>")
    source = _build(tmp_path, body)
    edit = _plan(source, "p0", "甲乙", "新文")
    with pytest.raises(editor.DocxError) as error:
        editor.validate_edit_plan(source, [edit], {"fixed": "新文"})
    assert error.value.code == "EDIT_BOOKMARK_RANGE_BROKEN"


def test_bookmark_end_inside_start_in_earlier_paragraph_rejected(tmp_path):
    body = ("<w:p>" + _bm_start(7) + HELPERS["run"]("头") + "</w:p>"
            + "<w:p>" + HELPERS["run"]("甲") + _bm_end(7) + HELPERS["run"]("乙") + "</w:p>")
    source = _build(tmp_path, body)
    edit = _plan(source, "p1", "甲乙", "新文")
    with pytest.raises(editor.DocxError) as error:
        editor.validate_edit_plan(source, [edit], {"fixed": "新文"})
    assert error.value.code == "EDIT_BOOKMARK_RANGE_BROKEN"


@pytest.mark.parametrize("direction", ["start_in_span", "end_in_span"])
def test_bookmark_partner_at_body_level_removed_pairwise(tmp_path, direction):
    """FL-D568 (B16 广发聚安): Word writes bookmark halves as direct children
    of ``w:body`` (e.g. the ``_GoBack`` tail). A partner at body level carries
    no text and belongs to no non-target paragraph, so it dies pairwise with
    the span-dropped half instead of rejecting a legal edit.
    """
    if direction == "start_in_span":
        body = ("<w:p>" + HELPERS["run"]("前缀甲") + HELPERS["run"]("目标乙")
                + _bm_start(78) + HELPERS["run"]("目标丙") + "</w:p>"
                + "<w:p>" + HELPERS["run"]("无关段落") + "</w:p>" + _bm_end(78))
        old, new = "目标乙目标丙", "新文"
    else:
        body = (_bm_start(78) + "<w:p>" + HELPERS["run"]("目标乙")
                + _bm_end(78) + HELPERS["run"]("目标丙") + "</w:p>"
                + "<w:p>" + HELPERS["run"]("无关段落") + "</w:p>")
        old, new = "目标乙目标丙", "新文"
    source = _build(tmp_path, body)
    redline, final, _ = _generate(source, tmp_path, old=old, new=new)
    assert _bookmark_ids(final) == ([], [])
    assert _bookmark_ids(redline) == ([], [])
    final_text = editor.inspect_docx(final, full=True).by_location("p1").text
    assert "无关段落" in final_text
    assert "新文" in editor.inspect_docx(final, full=True).by_location("p0").text


def test_bookmark_in_other_paragraph_still_fail_closed_at_body_tail_present(tmp_path):
    """A partner inside another *paragraph* remains an unconditional rejection:
    the body-level exception must not widen the fail-closed geometry."""
    body = ("<w:p>" + HELPERS["run"]("甲") + _bm_start(7) + HELPERS["run"]("乙")
            + "</w:p><w:p>" + HELPERS["run"]("尾") + _bm_end(7) + "</w:p>"
            + _bm_end(9))  # stray body-level half must not relax the rule
    source = _build(tmp_path, body)
    edit = _plan(source, "p0", "甲乙", "新文")
    with pytest.raises(editor.DocxError) as error:
        editor.validate_edit_plan(source, [edit], {"fixed": "新文"})
    assert error.value.code == "EDIT_BOOKMARK_RANGE_BROKEN"


def test_unpaired_bookmark_half_without_any_partner_stays_allowed(tmp_path):
    """A lone malformed bookmark half dropped inside the span has no surviving
    partner; removing it cannot orphan anything."""
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("甲") + _bm_start(7)
                    + HELPERS["run"]("乙") + "</w:p>")
    _, final, _ = _generate(source, tmp_path, old="甲乙", new="新文")
    assert _bookmark_ids(final) == ([], [])


# ---------------------------------------------------------------- A3-F4

def test_noop_edit_rejected_at_validation(tmp_path):
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("旧文") + "</w:p>")
    edit = _plan(source, "p0", "旧文", "旧文")
    before = source.read_bytes()
    with pytest.raises(editor.DocxError) as error:
        editor.validate_edit_plan(source, [edit], {"fixed": "旧文"})
    assert error.value.code == "NOOP_EDIT"
    assert source.read_bytes() == before


def test_noop_edit_rejected_with_generated_content_source(tmp_path):
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("旧文") + "</w:p>")
    edit = _plan(source, "p0", "旧文", "旧文")
    edit["content_source"] = "generated"
    with pytest.raises(editor.DocxError) as error:
        editor.validate_edit_plan(source, [edit], {}, content_check=lambda e: True)
    assert error.value.code == "NOOP_EDIT"


# ------------------------------------------------- real contract smoke (optional)

REAL_ESG = ROOT / "funds_word/广发ESG责任投资混合型证券投资基金基金合同_20230708.docx"


@pytest.mark.skipif(not REAL_ESG.is_file(), reason="real fund contract unavailable")
def test_real_gf_esg_edit_after_persistent_barrier_generates(tmp_path):
    """E8 fuzz trial 23 hit p1309 (（二）⇥投资限制) with FINAL_TEXT_MISMATCH.
    Re-derive the same shape from the real contract: any editable paragraph
    whose writable segment starts after a barrier."""
    inspection = editor.inspect_docx(REAL_ESG, full=True)
    candidate = None
    for paragraph in inspection.paragraphs:
        if not paragraph.editable:
            continue
        for segment in paragraph.segments:
            if segment.end - segment.start >= 4 and editor.BARRIER in paragraph.text[:segment.start]:
                candidate = (paragraph, segment)
                break
        if candidate:
            break
    assert candidate is not None, "no barrier-before-segment paragraph found"
    paragraph, segment = candidate
    old = paragraph.text[segment.start:segment.end]
    edit = _plan(REAL_ESG, paragraph.location, old, old[:2] + "核验")
    plan = editor.validate_edit_plan(REAL_ESG, [edit], {"fixed": edit["replacement"]})
    redline, final = tmp_path / "red.docx", tmp_path / "fin.docx"
    validation = editor.generate_artifacts(REAL_ESG, plan, redline, final)
    final_para = editor.inspect_docx(final, full=True).by_location(paragraph.location)
    assert "核验" in final_para.text
    assert validation.manifest[0]["del_id"] % 2 == 1
