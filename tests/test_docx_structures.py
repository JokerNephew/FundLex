"""Small OOXML packages assembled independently of the production writer.

These are structural safety proofs, not Microsoft Word compatibility approval.
"""
from hashlib import sha256
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from lxml import etree

import fundlex.docx as editor


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/package/2006/relationships"
O = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
Q = lambda name: "{" + W + "}" + name


def package(tmp_path: Path, body: str, extra=None) -> Path:
    parts = {
        "[Content_Types].xml": (f'<Types xmlns="{CT}"><Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>').encode(),
        "_rels/.rels": f'<Relationships xmlns="{R}"><Relationship Id="main" Type="{O}/officeDocument" Target="word/document.xml"/></Relationships>'.encode(),
        "word/document.xml": f'<w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>'.encode(),
        "custom/preserved.xml": b'<private><text>untouched</text></private>',
    }
    parts.update(extra or {})
    source = tmp_path / "fixture.docx"
    save(source, parts)
    return source


def save(path, parts):
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        for name, value in parts.items():
            archive.writestr(name, value)


def parts_of(path):
    with ZipFile(path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def run(text):
    return f'<w:r><w:t>{text}</w:t></w:r>'


def plan_edit(source, location="p0", old="旧文", new="新文"):
    inspection = editor.inspect_docx(source, full=True)
    paragraph = inspection.by_location(location)
    start = paragraph.text.index(old)
    return {"source_sha256": inspection.source_sha256, "verified": True,
            "location": location, "zone": paragraph.zone, "start": start,
            "end": start + len(old), "expected_old_text": old,
            "expected_old_hash": sha256(old.encode()).hexdigest(),
            "template_id": "fixed", "replacement": new}


def rejects(source, edit, code):
    before = source.read_bytes()
    with pytest.raises(editor.DocxError) as error:
        editor.validate_edit_plan(source, [edit], {"fixed": edit["replacement"]})
    assert error.value.code == code
    assert source.read_bytes() == before


@pytest.mark.parametrize("name", ["tab", "sym", "noBreakHyphen", "softHyphen", "drawing", "object"])
def test_special_nodes_never_join_search_segments(tmp_path, name):
    source = package(tmp_path, '<w:p>' + run("左文") + f'<w:r><w:{name}/></w:r>' + run("右文") + '</w:p>')
    paragraph = editor.inspect_docx(source, full=True).by_location("p0")
    assert paragraph.safe_text == "左文 | 右文"
    rejects(source, plan_edit(source, old=paragraph.text), "EDIT_CROSSES_BARRIER")
    edit = plan_edit(source, old="左文")
    plan = editor.validate_edit_plan(source, [edit], {"fixed": "新文"})
    editor.generate_artifacts(source, plan, tmp_path / "red.docx", tmp_path / "final.docx")
    assert editor.inspect_docx(tmp_path / "final.docx").by_location("p0").safe_text == "新文 | 右文"


@pytest.mark.parametrize("wrapper", ["sdt", "smartTag", "customXml", "hyperlink", "fldSimple", "unknownExtension"])
def test_wrapper_content_is_readonly_but_neighbor_is_editable(tmp_path, wrapper):
    source = package(tmp_path, f'<w:p>{run("左文")}<w:{wrapper}>{run("旧文")}</w:{wrapper}>{run("右文")}</w:p>')
    paragraph = editor.inspect_docx(source, full=True).by_location("p0")
    assert paragraph.safe_text == "左文 | 右文"
    rejects(source, plan_edit(source), "EDIT_CROSSES_BARRIER")


@pytest.mark.parametrize("prefix", ["commentRange", "perm"])
def test_range_interior_and_cross_paragraph_range_are_readonly(tmp_path, prefix):
    source = package(tmp_path, f'<w:p><w:{prefix}Start w:id="9"/>{run("旧文")}</w:p>'
        f'<w:p>{run("续文")}<w:{prefix}End w:id="9"/>{run("安全")}</w:p>')
    inspected = editor.inspect_docx(source, full=True)
    assert not inspected.by_location("p0").editable
    assert inspected.by_location("p1").safe_text == "安全"
    rejects(source, plan_edit(source), "REGION_NOT_EDITABLE")
    rejects(source, plan_edit(source, "p1", "续文"), "EDIT_CROSSES_BARRIER")


def test_bookmark_range_is_editable_and_does_not_split_segments(tmp_path):
    """TOC/navigation bookmarks must not make whole contract sections readonly."""
    source = package(tmp_path, '<w:p><w:bookmarkStart w:id="9" w:name="_Toc1"/>'
        + run("旧文") + '</w:p><w:p>' + run("续文")
        + '<w:bookmarkEnd w:id="9"/>' + run("安全") + '</w:p>')
    inspected = editor.inspect_docx(source, full=True)
    assert inspected.by_location("p0").editable
    assert inspected.by_location("p1").editable
    assert inspected.by_location("p1").safe_text == "续文安全"
    plan = editor.validate_edit_plan(source, [plan_edit(source)], {"fixed": "新文"})
    assert plan.edits


@pytest.mark.parametrize("name", ["lastRenderedPageBreak", "proofErr"])
def test_layout_and_proofing_markers_do_not_split_editable_text(tmp_path, name):
    source = package(tmp_path, '<w:p>' + run("左文")
        + f'<w:r><w:{name}/><w:t>右文</w:t></w:r>' + '</w:p>')
    paragraph = editor.inspect_docx(source, full=True).by_location("p0")
    assert paragraph.editable
    assert len(paragraph.segments) == 1
    assert paragraph.text == "左文右文"
    plan = editor.validate_edit_plan(
        source, [plan_edit(source, old=paragraph.text)], {"fixed": "新文"})
    editor.generate_artifacts(source, plan, tmp_path / "r.docx", tmp_path / "f.docx")
    assert editor.inspect_docx(tmp_path / "f.docx").by_location("p0").text == "新文"


def test_bookmark_between_runs_is_dropped_inside_edit(tmp_path):
    source = package(tmp_path, '<w:p>' + run("左文")
        + '<w:bookmarkStart w:id="9" w:name="_Toc1"/>' + run("右文")
        + '<w:bookmarkEnd w:id="9"/></w:p>')
    paragraph = editor.inspect_docx(source, full=True).by_location("p0")
    assert paragraph.editable
    assert paragraph.text == "左文右文"
    plan = editor.validate_edit_plan(
        source, [plan_edit(source, old=paragraph.text)], {"fixed": "新文"})
    editor.generate_artifacts(source, plan, tmp_path / "r.docx", tmp_path / "f.docx")
    assert editor.inspect_docx(tmp_path / "f.docx").by_location("p0").text == "新文"


@pytest.mark.parametrize("marker", ["cellIns", "tblGridChange", "customXmlMoveFromRangeEnd", "moveTo", "rPrChange", "delText"])
def test_revisions_in_arbitrary_story_part_reject_entire_input(tmp_path, marker):
    story = f'<w:hdr xmlns:w="{W}"><w:p><w:{marker}/></w:p></w:hdr>'.encode()
    source = package(tmp_path, '<w:p>' + run("旧文") + '</w:p>', {"stories/header.xml": story})
    before = source.read_bytes()
    with pytest.raises(editor.DocxError) as error:
        editor.inspect_docx(source, full=True)
    assert error.value.code == "EXISTING_REVISION_UNSUPPORTED"
    assert source.read_bytes() == before


def test_unindexed_nested_stories_are_retained_as_readonly(tmp_path):
    source = package(tmp_path, '<w:sdt><w:sdtContent><w:p>' + run("内容控件") + '</w:p></w:sdtContent></w:sdt>'
        '<w:tbl><w:tr><w:tc><w:p>' + run("外层") + '</w:p><w:tbl><w:tr><w:tc><w:p>' + run("内层") + '</w:p></w:tc></w:tr></w:tbl></w:tc></w:tr></w:tbl>'
        '<w:p>' + run("旧文") + '<w:r><w:drawing><w:txbxContent><w:p>' + run("文本框") + '</w:p></w:txbxContent></w:drawing></w:r></w:p>')
    inspected = editor.inspect_docx(source, full=True)
    assert len(inspected.paragraphs) == 5
    assert inspected.by_location("tbl0/r0/c0/p0").zone == "unsupported_table"
    assert all(not p.editable for p in inspected.paragraphs if p.location.startswith("readonly:"))
    assert "文本框" not in inspected.evidence_text()


@pytest.mark.parametrize("bad", ['<w:fldChar w:fldCharType="end"/>', '<w:fldChar w:fldCharType="separate"/>', '<w:fldChar w:fldCharType="invalid"/>', '<w:fldChar w:fldCharType="begin"/>'])
def test_incomplete_fields_prohibit_affected_paragraph(tmp_path, bad):
    source = package(tmp_path, f'<w:p><w:r>{bad}</w:r>{run("旧文")}</w:p>')
    inspected = editor.inspect_docx(source, full=True)
    assert not inspected.by_location("p0").editable
    rejects(source, plan_edit(source), "REGION_NOT_EDITABLE")


def test_nested_cross_paragraph_toc_field_preserved(tmp_path):
    source = package(tmp_path, '<w:p><w:r><w:fldChar w:fldCharType="begin"/><w:instrText> TOC </w:instrText></w:r></w:p>'
        '<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r>' + run("字段结果") + '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
        '<w:p>' + run("目录结果") + '<w:r><w:fldChar w:fldCharType="end"/></w:r></w:p><w:p>' + run("旧文") + '</w:p>')
    inspected = editor.inspect_docx(source, full=True)
    assert inspected.has_toc_field
    assert all(not p.editable for p in inspected.paragraphs[:3])
    edit = plan_edit(source, "p3")
    plan = editor.validate_edit_plan(source, [edit], {"fixed": "新文"})
    result = editor.generate_artifacts(source, plan, tmp_path / "red.docx", tmp_path / "final.docx")
    assert result.toc_update_status == "not_updated"
    for name, content in parts_of(source).items():
        if name != editor.DOCUMENT:
            assert parts_of(tmp_path / "final.docx")[name] == content


@pytest.mark.parametrize("text,old", [("é末", "e"), ("✈️末", "✈"), ("👩‍💻末", "👩"), ("👍🏽末", "👍"), ("🇨🇳末", "🇨"), ("가末", "ᄀ")])
def test_cluster_fragments_cannot_be_edited(tmp_path, text, old):
    source = package(tmp_path, '<w:p>' + run(text) + '</w:p>')
    rejects(source, plan_edit(source, old=old), "GRAPHEME_BOUNDARY_INVALID")


def test_multiline_template_uses_word_breaks_and_preserves_formats(tmp_path):
    source = package(tmp_path, '<w:p><w:pPr><w:keepNext/></w:pPr><w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve"> 前旧文后 </w:t></w:r></w:p>')
    new = "第一行\n\n 第三行 "
    edit = plan_edit(source, new=new)
    plan = editor.validate_edit_plan(source, [edit], {"fixed": new})
    editor.generate_artifacts(source, plan, tmp_path / "red.docx", tmp_path / "final.docx")
    root = etree.fromstring(parts_of(tmp_path / "final.docx")[editor.DOCUMENT])
    assert len(root.findall('.//' + Q("br"))) == 2
    assert all('\n' not in (node.text or '') for node in root.iter(Q("t")))
    assert editor.inspect_docx(tmp_path / "final.docx").by_location("p0").text == " 前" + new + "后 "
    assert all(r.find(Q("rPr")) is not None for r in root.iter(Q("r")) if r.find(Q("t")) is not None)


@pytest.mark.parametrize("mutation,code", [("deleted_text", "REVISION_TEXT_MISMATCH"), ("paragraph_properties", "NON_TARGET_STRUCTURE_CHANGED"), ("table_properties", "NON_TARGET_STRUCTURE_CHANGED"), ("run_format", "RUN_FORMAT_CHANGED")])
def test_independent_reopen_detects_output_tampering(tmp_path, monkeypatch, mutation, code):
    source = package(tmp_path, '<w:p><w:pPr><w:keepNext/></w:pPr>' + run("前旧文后") + '</w:p><w:tbl><w:tblPr/><w:tr><w:tc><w:p>' + run("保护") + '</w:p></w:tc></w:tr></w:tbl>')
    edit = plan_edit(source)
    plan = editor.validate_edit_plan(source, [edit], {"fixed": "新文"})
    writer = editor._write_package

    def corrupt(path, original_parts, document_xml):
        root = etree.fromstring(document_xml)
        if mutation == "deleted_text":
            node = root.find('.//' + Q("delText"))
            if node is not None:
                node.text = "伪造删除"
        elif mutation == "paragraph_properties":
            etree.SubElement(root.find('.//' + Q("pPr")), Q("pageBreakBefore"))
        elif mutation == "table_properties":
            etree.SubElement(root.find('.//' + Q("tblPr")), Q("bidiVisual"))
        elif mutation == "run_format":
            node = root.find('.//' + Q("r"))
            props = etree.Element(Q("rPr"))
            etree.SubElement(props, Q("i"))
            node.insert(0, props)
        writer(path, original_parts, etree.tostring(root))

    monkeypatch.setattr(editor, "_write_package", corrupt)
    before = source.read_bytes()
    with pytest.raises(editor.DocxError) as error:
        editor.generate_artifacts(source, plan, tmp_path / "red.docx", tmp_path / "final.docx")
    assert error.value.code == code
    assert source.read_bytes() == before
    assert not (tmp_path / "red.docx").exists()
    assert not (tmp_path / "final.docx").exists()


@pytest.mark.parametrize("mutation,code", [
    ("encoded_control", "OPC_URI_INVALID"),
    ("normalized_duplicate", "ZIP_DUPLICATE_PART"),
    ("orphan_relationship", "RELATIONSHIP_SOURCE_MISSING"),
    ("missing_target", "RELATIONSHIP_TARGET_MISSING"),
    ("unknown_external", "EXTERNAL_RELATIONSHIP_UNSUPPORTED"),
    ("duplicate_content_type", "CONTENT_TYPE_DUPLICATE"),
    ("signature_mime", "SIGNED_OR_MACRO_UNSUPPORTED"),
    ("strict", "STRICT_OOXML_UNSUPPORTED"),
    ("dtd", "XML_DTD_UNSUPPORTED"),
    ("xinclude", "XML_XINCLUDE_UNSUPPORTED"),
    ("required_extension", "REQUIRED_EXTENSION_UNSUPPORTED"),
])
def test_package_and_xml_failures_preserve_source(tmp_path, mutation, code):
    source = package(tmp_path, '<w:p>' + run("旧文") + '</w:p>')
    parts = parts_of(source)
    if mutation == "encoded_control":
        parts["custom/%0A.xml"] = b"<x/>"
    elif mutation == "normalized_duplicate":
        parts["custom/%70reserved.xml"] = b"<x/>"
    elif mutation == "orphan_relationship":
        parts["custom/_rels/missing.xml.rels"] = f'<Relationships xmlns="{R}"/>'.encode()
    elif mutation in {"missing_target", "unknown_external"}:
        tail = ' TargetMode="External"' if mutation == "unknown_external" else ""
        parts["word/_rels/document.xml.rels"] = f'<Relationships xmlns="{R}"><Relationship Id="bad" Type="{O}/image" Target="missing.xml"{tail}/></Relationships>'.encode()
    elif mutation in {"duplicate_content_type", "signature_mime"}:
        content = etree.fromstring(parts["[Content_Types].xml"])
        item = etree.SubElement(content, "{" + CT + "}Default")
        item.set("Extension", "xml" if mutation == "duplicate_content_type" else "signature")
        item.set("ContentType", "application/xml" if mutation == "duplicate_content_type" else "application/vnd.openxmlformats-package.digital-signature-xmlsignature+xml")
        parts["[Content_Types].xml"] = etree.tostring(content)
    elif mutation == "strict":
        parts["stories/strict.xml"] = b'<hdr xmlns="http://purl.oclc.org/ooxml/wordprocessingml/main"/>'
    elif mutation == "dtd":
        parts["custom/preserved.xml"] = b'<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///missing">]><x>&secret;</x>'
    elif mutation == "xinclude":
        parts["custom/preserved.xml"] = b'<x xmlns:xi="http://www.w3.org/2001/XInclude"><xi:include href="missing"/></x>'
    elif mutation == "required_extension":
        parts["custom/preserved.xml"] = b'<x xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" mc:MustUnderstand="unknown"/>'
    save(source, parts)
    original = source.read_bytes()
    with pytest.raises(editor.DocxError) as error:
        editor.inspect_docx(source, full=True)
    assert error.value.code == code
    assert source.read_bytes() == original
