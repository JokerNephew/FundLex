"""Overlay contract regressions for A01/A02/A03 (FL-D446).

These tests exercise the public inspection/validation/generation/selection
entry points.  They are intentionally separate from the shared overlay suite so
the compare/docx owner can extend the contract without editing shared files.
"""
from __future__ import annotations

import hashlib
import json
import runpy
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from fundlex import docx as editor
from fundlex.api import create_app
from fundlex.selective import apply_decisions, generate_selected_artifact, generate_selected_redline

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


def _plan(source: Path, location: str, old: str, new: str):
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    paragraph = inspection.by_location(location)
    start = paragraph.text.index(old)
    return {
        "source_sha256": inspection.source_sha256, "verified": True,
        "location": location, "zone": paragraph.zone, "start": start,
        "end": start + len(old), "expected_old_text": old,
        "expected_old_hash": hashlib.sha256(old.encode()).hexdigest(),
        "template_id": "fixed", "replacement": new,
    }


def _report(validation) -> dict:
    return {"revision_manifest": [dict(item) for item in validation.manifest],
            "source_revision_manifest": [dict(item) for item in validation.source_revisions]}


def _paragraph_texts(path: Path) -> list[str]:
    root = etree.fromstring(ZipFile(path).read(editor.DOCUMENT))
    body = root.find(editor.Q("body"))
    return ["".join(node.text or "" for node in paragraph.iter(editor.Q("t")))
            for paragraph in body if paragraph.tag == editor.Q("p")]


def _revision_inventory(path: Path, part: str = editor.DOCUMENT) -> list[tuple[str, str]]:
    root = etree.fromstring(ZipFile(path).read(part))
    return [(etree.QName(node).localname, node.get(editor.Q("id"), ""))
            for node in root.iter()
            if isinstance(node.tag, str)
            and etree.QName(node).localname in {"ins", "del", "pPrChange"}]


def _generate(source: Path, tmp_path: Path, location="p0", old="旧文", new="新文"):
    plan = editor.validate_edit_plan(source, [_plan(source, location, old, new)],
                                     {"fixed": new}, allow_existing_revisions=True)
    redline = tmp_path / "redline.docx"
    final = tmp_path / "final.docx"
    validation = editor.generate_artifacts(source, plan, redline, final,
                                           allow_existing_revisions=True, author=AUTHOR)
    return redline, final, validation


def test_foreign_insertion_before_target_uses_accepted_coordinates(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, FOREIGN, "外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    assert inspection.by_location("p0").text == "\ufff9外方\ufff9旧文"
    redline, final, validation = _generate(source, tmp_path)
    assert _paragraph_texts(final) == ["外方新文"]
    assert validation.manifest[0]["del_id"] == 11
    assert validation.manifest[0]["ins_id"] == 12


def test_foreign_deletion_before_target_uses_same_mapping(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("del", 10, FOREIGN, "删除")
                    + HELPERS["run"]("旧文") + "</w:p>")
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    assert inspection.by_location("p0").text == "旧文"
    redline, final, validation = _generate(source, tmp_path)
    assert _paragraph_texts(final) == ["新文"]
    assert validation.source_revisions[0]["kind"] == "del"


def test_selection_keeps_foreign_revisions_but_selected_final_accepts_them(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, FOREIGN, "外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    redline, final, validation = _generate(source, tmp_path)
    report = _report(validation)

    selected_final = tmp_path / "selected_final.docx"
    result = generate_selected_artifact(redline, selected_final, report, {11: "reject"})
    assert result.rejected == (11,)
    assert _paragraph_texts(selected_final) == ["外方旧文"]
    assert _revision_inventory(selected_final) == []

    selected_redline = tmp_path / "selected_redline.docx"
    generate_selected_redline(redline, selected_redline, report, {11: "reject"})
    # Foreign insertion survives, our pair is settled back to original text.
    assert _revision_inventory(selected_redline) == [("ins", "10")]
    assert _paragraph_texts(selected_redline) == ["外方旧文"]


def test_selection_fails_closed_without_bound_source_manifest(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, FOREIGN, "外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    redline, _, validation = _generate(source, tmp_path)
    report = {"revision_manifest": [dict(item) for item in validation.manifest]}
    with pytest.raises(editor.DocxError) as error:
        generate_selected_artifact(redline, tmp_path / "out.docx", report, {11: "reject"})
    assert error.value.code == "SOURCE_REVISION_MANIFEST_UNAVAILABLE"


def test_selection_rejects_foreign_content_substitution(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, FOREIGN, "外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    redline, _, validation = _generate(source, tmp_path)
    report = _report(validation)
    parts = editor._read_parts(redline, editor.ZipLimits())
    root = editor._xml(parts[editor.DOCUMENT], editor.ZipLimits())
    foreign = next(node for node in root.iter(editor.Q("ins"))
                   if node.get(editor.Q("id")) == "10")
    foreign.find(editor.Q("r")).find(editor.Q("t")).text = "被替换"
    tampered = tmp_path / "tampered.docx"
    with ZipFile(tampered, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, etree.tostring(root) if name == editor.DOCUMENT else data)
    with pytest.raises(editor.DocxError) as error:
        generate_selected_artifact(tampered, tmp_path / "out.docx", report, {11: "reject"})
    assert error.value.code == "SOURCE_REVISION_MISMATCH"


def test_property_change_is_inventoried_and_accepted(tmp_path):
    body = ("<w:p><w:pPr><w:pPrChange w:id=\"100\" w:author=\"" + FOREIGN
            + "\" w:date=\"2026-10-01T00:00:00Z\"><w:pPr/></w:pPrChange></w:pPr>"
            + HELPERS["run"]("旧文") + "</w:p>")
    source = _build(tmp_path, body)
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    assert [item["kind"] for item in inspection.revisions] == ["pPrChange"]
    redline, final, validation = _generate(source, tmp_path)
    assert validation.source_revisions[0]["kind"] == "pPrChange"
    assert ("pPrChange", "100") in _revision_inventory(redline)
    assert _revision_inventory(final) == []
    assert _paragraph_texts(final) == ["新文"]


def test_story_revision_is_inventoried_and_accepted_in_final_only(tmp_path):
    header = ('<w:hdr xmlns:w="' + editor.W + '"><w:p>'
              + _revision("ins", 100, FOREIGN, "页眉新增") + "</w:p></w:hdr>").encode()
    source = _build(tmp_path, "<w:p>" + HELPERS["run"]("旧文") + "</w:p>",
                    extra={"word/header1.xml": header})
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    assert {(item["part"], item["id"]) for item in inspection.revisions} == {
        ("word/header1.xml", "100")}
    redline, final, validation = _generate(source, tmp_path)
    # Full-package id allocation starts after the foreign id in the header.
    assert validation.manifest[0]["del_id"] == 101
    assert validation.manifest[0]["ins_id"] == 102
    with ZipFile(redline) as archive:
        assert b"w:ins" in archive.read("word/header1.xml")
    with ZipFile(final) as archive:
        header_xml = archive.read("word/header1.xml")
        assert b"w:ins" not in header_xml
        assert "页眉新增".encode() in header_xml


def test_same_author_foreign_revision_remains_distinguishable(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, AUTHOR, "同名外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    redline, final, validation = _generate(source, tmp_path)
    assert validation.manifest[0]["del_id"] == 11
    report = _report(validation)
    selected = tmp_path / "selected.docx"
    generate_selected_artifact(redline, selected, report, {11: "reject"})
    assert _paragraph_texts(selected) == ["同名外方旧文"]
    assert _revision_inventory(selected) == []


def test_paragraph_mark_revision_is_carried_as_opaque_metadata(tmp_path):
    # EN3 (2026-11-02): paragraph-mark revisions (pPr/rPr/ins|del) are Word's
    # standard shape for an inserted/deleted pilcrow.  They carry no text and
    # shift no projection offsets, so the overlay admits them as opaque
    # metadata.  Row marks and moves keep their fail-closed rejection.
    body = ("<w:p><w:pPr><w:rPr><w:del w:id=\"10\" w:author=\"" + FOREIGN
            + "\" w:date=\"2026-10-01T00:00:00Z\"/></w:rPr></w:pPr>"
            + HELPERS["run"]("前文") + "</w:p><w:p>" + HELPERS["run"]("旧文") + "</w:p>")
    source = _build(tmp_path, body)
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    assert any(entry["kind"] == "del" and entry["id"] == "10"
               for entry in inspection.revisions)
    # The paragraph text is unchanged by the mark revision and stays editable.
    assert inspection.by_location("p1").editable
    # A table-row mark still changes topology and stays rejected.
    row_body = ("<w:tbl><w:tr><w:trPr><w:del w:id=\"10\" w:author=\"" + FOREIGN
                + "\" w:date=\"2026-10-01T00:00:00Z\"/></w:trPr>"
                + "<w:tc><w:p>" + HELPERS["run"]("单元格") + "</w:p></w:tc></w:tr></w:tbl>")
    row_source = _build(tmp_path, row_body, name="row.docx")
    with pytest.raises(editor.DocxError) as error:
        editor.inspect_docx(row_source, full=True, allow_existing_revisions=True)
    assert error.value.code == "EXISTING_REVISION_STRUCTURE_UNSUPPORTED"
    assert "paragraph-or-row-mark" in str(error.value)


def test_nested_inline_revision_is_carried_as_opaque_region(tmp_path):
    # EN3 (2026-11-02): Word legally nests inline revisions (a reviewer
    # retracting part of their own insertion, ins>del).  The outermost wrapper
    # is one opaque foreign region: the projection already handles both
    # branches and the writer never enters a foreign wrapper.
    body = ("<w:p><w:ins w:id=\"10\" w:author=\"" + FOREIGN
            + "\" w:date=\"2026-10-01T00:00:00Z\"><w:del w:id=\"11\" w:author=\""
            + FOREIGN + "\" w:date=\"2026-10-01T00:00:00Z\"><w:r><w:delText>旧</w:delText>"
            + "</w:r></w:del><w:r><w:t>新</w:t></w:r></w:ins></w:p>")
    source = _build(tmp_path, body)
    inspection = editor.inspect_docx(source, full=True, allow_existing_revisions=True)
    assert inspection.by_location("p0").text.replace("\ufff9", "") == "新"
    ids = {entry["id"] for entry in inspection.revisions}
    assert "10" in ids
    # A move still carries topology the overlay cannot preserve: rejected.
    with pytest.raises(editor.DocxError) as error:
        editor.inspect_docx(
            _build(tmp_path, "<w:moveFromRangeStart w:id=\"20\" w:name=\"m\"/>"
                   "<w:p>" + HELPERS["run"]("挪动") + "</w:p>"
                   "<w:moveFromRangeEnd w:id=\"20\"/>"
                   "<w:moveFrom w:id=\"21\" w:author=\"" + FOREIGN
                   + "\" w:date=\"2026-10-01T00:00:00Z\"><w:r><w:delText>挪</w:delText></w:r></w:moveFrom>",
                   name="move.docx"),
            full=True, allow_existing_revisions=True)
    assert error.value.code == "EXISTING_REVISION_STRUCTURE_UNSUPPORTED"


def test_low_level_reject_restores_source_with_foreign_marks(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, FOREIGN, "外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    redline, _, validation = _generate(source, tmp_path)
    root = editor._xml(editor._read_parts(redline, editor.ZipLimits())[editor.DOCUMENT],
                       editor.ZipLimits())
    apply_decisions(root, validation.manifest, {validation.manifest[0]["del_id"]: "reject"})
    assert "".join(node.text or "" for node in root.iter(editor.Q("t"))) == "外方旧文"
    assert {node.get(editor.Q("id")) for node in root.iter(editor.Q("ins"))} == {"10"}


def test_public_api_selection_uses_persisted_overlay_manifests(tmp_path):
    source = _build(tmp_path, "<w:p>" + _revision("ins", 10, FOREIGN, "外方")
                    + HELPERS["run"]("旧文") + "</w:p>")
    redline, final, validation = _generate(source, tmp_path)
    data = tmp_path / "api-data"
    data.mkdir()
    app = create_app(data_dir=data)
    store = app.state.store
    batch = store.create_batch(owner="dev", ruleset_version="v1",
                               uploads=[("contract.docx", redline.read_bytes())])
    lease = store.claim(lease_seconds=300)
    assert lease is not None
    report = {
        "engine_id": "recall_first", "schema_version": "3", "engine_version": "0.2.0",
        "delivery_status": "incomplete",
        "source_sha256": hashlib.sha256(redline.read_bytes()).hexdigest(),
        "revision_manifest": [dict(item) for item in validation.manifest],
        "source_revision_manifest": [dict(item) for item in validation.source_revisions],
        "plan": {"edits": [dict(item) for item in validation.manifest],
                 "count": len(validation.manifest)},
        "unresolved": [{"reason": "test"}],
        "output_validation": {
            "kind": "recall_working_edits",
            "checks": ["package", "revisions", "final_equivalence", "non_target",
                       "template_text", "actual_content_verification"],
            "final_sha256": hashlib.sha256(final.read_bytes()).hexdigest(),
            "redline_sha256": hashlib.sha256(redline.read_bytes()).hexdigest(),
        },
    }
    store.finish(lease["id"], lease["fencing_token"], report=report,
                 artifacts={"working_final": final, "working_redline": redline})
    client = TestClient(app)
    headers = {"X-FundLex-User": "dev"}
    response = client.post(
        f"/api/batches/{batch['id']}/documents/{lease['id']}/decisions",
        headers=headers, json={"decisions": [{"del_id": 11, "decision": "reject"}]})
    assert response.status_code == 200, response.text
    assert response.json()["rejected"] == [11]
    download = client.get(
        f"/api/batches/{batch['id']}/documents/{lease['id']}/download/selected_final",
        headers=headers)
    assert download.status_code == 200
    selected = tmp_path / "api-selected.docx"
    selected.write_bytes(download.content)
    assert _paragraph_texts(selected) == ["外方旧文"]
    assert _revision_inventory(selected) == []


REAL = (ROOT / "funds_word/基金合同第一批/"
        "广发弘利3个月滚动持有债券型证券投资基金基金合同.docx")


@pytest.mark.skipif(not REAL.is_file(), reason="real fund contract unavailable")
def test_real_hongli_p159_foreign_insertion_before_target(tmp_path):
    original_hash = hashlib.sha256(REAL.read_bytes()).hexdigest()
    with ZipFile(REAL) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    root = etree.fromstring(parts[editor.DOCUMENT])
    paragraph = editor._paragraph_element(root, "p159")
    foreign = etree.fromstring((
        f'<w:ins xmlns:w="{editor.W}" w:id="10" w:author="{FOREIGN}" '
        'w:date="2026-10-01T00:00:00Z"><w:r><w:t>外方新增说明。</w:t></w:r></w:ins>'
    ).encode())
    paragraph.insert(1 if paragraph.find(editor.Q("pPr")) is not None else 0, foreign)
    source = tmp_path / "hongli.docx"
    with ZipFile(source, "w", ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, etree.tostring(root) if name == editor.DOCUMENT else data)
    redline, final, validation = _generate(source, tmp_path, "p159", "具体设置", "详细设置")
    final_text = _paragraph_texts(final)[159]
    assert final_text.startswith("外方新增说明。")
    assert "详细设置" in final_text and "具体设置" not in final_text
    assert hashlib.sha256(REAL.read_bytes()).hexdigest() == original_hash
    assert any(item["part"] == editor.DOCUMENT and item["id"] == "10"
               for item in validation.source_revisions)
