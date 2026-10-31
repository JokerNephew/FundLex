"""Compare uploads may carry Word tracked changes.

Contract under test: both sides of a pair (either one or both with revision
marks) are normalized to the "accept all revisions" view before parsing, and
that view is the only comparison baseline.  Results and reports are computed
from the accepted view and record ``metadata.original_had_tracked_changes``
for each side.  A tracked upload must produce byte-identical comparison
content (same diffs/alignment/summary) as uploading the pre-accepted document.
"""
from __future__ import annotations

import io
import zipfile
from hashlib import sha256

import pytest
from docx import Document
from fastapi.testclient import TestClient
from lxml import etree

from fundlex.api import create_app
from fundlex.compare.revisions import prepare_compare_input
from fundlex.compare.parser import parse_compare_document
from fundlex.compare.service import CompareService
from fundlex.compare.worker import CompareWorker
from fundlex.docx import DOCUMENT, DocxError, Q

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _plain_docx(paragraphs: list[str]) -> bytes:
    buffer = io.BytesIO()
    document = Document()
    for text in paragraphs:
        document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()


def _rezip(parts: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _with_body(body_xml: str) -> bytes:
    """Build a DOCX whose main document body is the given WordprocessingML."""
    with zipfile.ZipFile(io.BytesIO(_plain_docx(["占位"]))) as archive:
        parts = {name: archive.read(name) for name in archive.namelist()}
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body_xml}'
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
        '</w:body></w:document>'
    )
    parts[DOCUMENT] = document_xml.encode("utf-8")
    return _rezip(parts)


def _ins_del_paragraph(*, prefix: str, deleted: str, inserted: str, suffix: str,
                       first_id: int = 1) -> str:
    """Paragraph whose accepted view is ``prefix + inserted + suffix``."""
    return (
        f'<w:p><w:r><w:t>{prefix}</w:t></w:r>'
        f'<w:del w:id="{first_id}" w:author="法务"><w:r><w:delText>{deleted}</w:delText></w:r></w:del>'
        f'<w:ins w:id="{first_id + 1}" w:author="法务"><w:r><w:t>{inserted}</w:t></w:r></w:ins>'
        f'<w:r><w:t>{suffix}</w:t></w:r></w:p>'
    )


LEFT_ACCEPTED_TEXT = "本基金的管理费率为0.30%，托管费率为0.08%。"
RIGHT_ACCEPTED_TEXT = "对侧合同约定的托管账户不同。"


def _tracked_left() -> bytes:
    return _with_body(_ins_del_paragraph(
        prefix="本基金的管理费率为", deleted="0.40%", inserted="0.30%",
        suffix="，托管费率为0.08%。", first_id=1))


def _tracked_right() -> bytes:
    return _with_body(_ins_del_paragraph(
        prefix="对侧合同约定的", deleted="收费账户", inserted="托管账户",
        suffix="不同。", first_id=3))


def _tracked_combo() -> bytes:
    """SDT + hyperlink + move + nested-in-ins wrappers in one document."""
    body = (
        '<w:sdt><w:sdtPr/><w:sdtContent><w:p>'
        '<w:ins w:id="11" w:author="法务"><w:hyperlink><w:r><w:t>详见费用条款</w:t></w:r></w:hyperlink></w:ins>'
        '<w:moveFromRangeStart w:id="12" w:name="m1"/>'
        '<w:moveFrom w:id="13" w:author="法务"><w:r><w:delText>（已移走的旧注）</w:delText></w:r></w:moveFrom>'
        '<w:moveFromRangeEnd w:id="12"/>'
        '<w:r><w:t>；本段其余文字不变。</w:t></w:r>'
        '</w:p></w:sdtContent></w:sdt>'
        '<w:p>'
        '<w:moveToRangeStart w:id="14" w:name="m1"/>'
        '<w:moveTo w:id="15" w:author="法务"><w:r><w:t>移动进来的尾句</w:t></w:r></w:moveTo>'
        '<w:moveToRangeEnd w:id="14"/>'
        '<w:ins w:id="16" w:author="法务"><w:r><w:t>（外层插入</w:t></w:r>'
        '<w:del w:id="17" w:author="法务"><w:r><w:delText>内嵌删除</w:delText></w:r></w:del></w:ins>'
        '<w:del w:id="18" w:author="法务"><w:r><w:delText>整句删除的内容</w:delText></w:r></w:del>'
        '<w:r><w:t>保持不变。</w:t></w:r>'
        '</w:p>'
    )
    return _with_body(body)


COMBO_ACCEPTED_TEXTS = ["详见费用条款；本段其余文字不变。", "移动进来的尾句（外层插入保持不变。"]


def _accepted_texts(data: bytes) -> list[str]:
    prepared = prepare_compare_input(data)
    parsed = parse_compare_document(prepared.data, filename="input.docx")
    return [block.raw_text for block in parsed.blocks]


def _compare_via_api(client: TestClient, headers: dict, left: bytes, right: bytes,
                     *, name: str = "cmp", task_no: int = 0):
    payload = {"name": f"{name}-{task_no}", "pairs": [{"client_pair_id": "p", "label": "P",
               "left": {"client_id": "l", "name": "left.docx", "size": len(left)},
               "right": {"client_id": "r", "name": "right.docx", "size": len(right)}}]}
    created = client.post("/api/compare/tasks", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    pair_id = created.json()["pairs"][0]["id"]
    uploaded = client.post(f"/api/compare/tasks/{task_id}/uploads", headers=headers,
                           data={"client_ids": '["l","r"]'},
                           files=[("files", ("left.docx", left)),
                                  ("files", ("right.docx", right))])
    assert uploaded.status_code == 200, uploaded.text
    receipts = {item["client_id"]: item for item in uploaded.json()["receipts"]}
    sealed = client.post(f"/api/compare/tasks/{task_id}/seal", headers=headers)
    assert sealed.status_code == 200, sealed.text
    assert CompareWorker(client.app.state.compare_store).run_once()
    detail = client.get(f"/api/compare/pairs/{pair_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    return task_id, pair_id, receipts, detail.json()


def _document_xml(data: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(DOCUMENT)


def test_combined_revision_wrappers_accept_to_plain_text():
    """SDT/move/hyperlink/nested inputs normalize to a precise accepted view."""
    combo = _tracked_combo()
    for tag in (b"<w:ins", b"<w:del", b"<w:moveFrom", b"<w:moveTo"):
        assert tag in _document_xml(combo)
    prepared = prepare_compare_input(combo)
    assert prepared.revisions_accepted > 0
    for tag in (b"<w:ins", b"<w:del", b"<w:moveFrom", b"<w:moveTo", b"<w:delText"):
        assert tag not in _document_xml(prepared.data)
    assert _accepted_texts(combo) == COMBO_ACCEPTED_TEXTS
    # Original upload bytes are never modified by normalization.
    assert sha256(combo).hexdigest() == prepared.original_sha256
    assert prepared.original_size == len(combo)


def test_parser_still_rejects_unnormalized_revision_input():
    """Fail-closed invariant: the parser itself never silently accepts marks.

    The accept-all view is produced at the ingest boundary; a raw document
    with tracked changes must still be rejected by the parser so no read path
    can drift to a different (e.g. rejected-view) projection.
    """
    with pytest.raises(DocxError, match="EXISTING_REVISION_UNSUPPORTED"):
        parse_compare_document(_tracked_left(), filename="left.docx")


@pytest.mark.parametrize("left_tracked", [False, True], ids=["clean-left", "tracked-left"])
@pytest.mark.parametrize("right_tracked", [False, True], ids=["clean-right", "tracked-right"])
def test_upload_matrix_baseline_and_metadata(tmp_path, left_tracked, right_tracked):
    """2x2 matrix: any combination of tracked/clean sides compares identically."""
    clean_left = _plain_docx([LEFT_ACCEPTED_TEXT])
    clean_right = _plain_docx([RIGHT_ACCEPTED_TEXT])
    left = _tracked_left() if left_tracked else clean_left
    right = _tracked_right() if right_tracked else clean_right
    client = TestClient(create_app(tmp_path / "store"))
    headers = {"X-FundLex-User": "alice"}
    task_id, _, receipts, pair = _compare_via_api(client, headers, left, right)

    assert receipts["l"]["status"] == "accepted"
    assert receipts["r"]["status"] == "accepted"
    assert (receipts["l"]["revisions_accepted"] > 0) is left_tracked
    assert (receipts["r"]["revisions_accepted"] > 0) is right_tracked
    if left_tracked:
        assert receipts["l"]["original_sha256"] == sha256(left).hexdigest()
    assert pair["status"] == "succeeded"
    assert pair["error_code"] is None

    # Result/report metadata: the comparison baseline and per-side flags.
    result = pair["result"]
    assert result["metadata"]["comparison_baseline"] == "accepted_tracked_changes"
    flags = result["metadata"]["original_had_tracked_changes"]
    assert flags == {"current": left_tracked, "other": right_tracked}
    assert pair["metadata"]["original_had_tracked_changes"] == flags

    # The comparison ran on the accepted view: the two fully-different
    # paragraphs align as one insert plus one delete over the accepted text.
    assert result["summary"] == {"total": 2, "modify": 0, "insert": 1, "delete": 1}
    left_text = "".join(span["text"] for diff in result["diffs"] for span in diff.get("left_spans") or [])
    right_text = "".join(span["text"] for diff in result["diffs"] for span in diff.get("right_spans") or [])
    assert "0.30%" in left_text and "托管账户" in right_text
    assert LEFT_ACCEPTED_TEXT == left_text and RIGHT_ACCEPTED_TEXT == right_text

    # The persisted comparison is byte-identical to comparing pre-accepted
    # inputs directly through the deterministic service.
    service = CompareService()
    expected = service.compare_bytes(
        prepare_compare_input(left).data, prepare_compare_input(right).data,
        left_filename="left.docx", right_filename="right.docx")
    assert result["diffs"] == expected["diffs"]
    assert result["summary"] == expected["summary"]
    assert result["alignment"] == expected["alignment"]
    assert result["left"]["sha256"] == sha256(prepare_compare_input(left).data).hexdigest()


def test_tracked_upload_matches_pre_accepted_upload(tmp_path):
    """Same content in different revision wrappers yields identical diffs."""
    client = TestClient(create_app(tmp_path / "store-equivalence"))
    headers = {"X-FundLex-User": "alice"}
    tracked_result = _compare_via_api(
        client, headers, _tracked_left(), _tracked_right(), name="tracked", task_no=1)[3]["result"]
    pre_accepted_left = prepare_compare_input(_tracked_left()).data
    pre_accepted_right = prepare_compare_input(_tracked_right()).data
    accepted_result = _compare_via_api(
        client, headers, pre_accepted_left, pre_accepted_right,
        name="accepted", task_no=2)[3]["result"]

    for key in ("diffs", "summary", "alignment"):
        assert tracked_result[key] == accepted_result[key]
    # Same accepted-view content hashes; only the provenance metadata differs.
    for side in ("left", "right"):
        assert tracked_result[side]["sha256"] == accepted_result[side]["sha256"]
    assert tracked_result["metadata"]["original_had_tracked_changes"] == {
        "current": True, "other": True}
    assert accepted_result["metadata"]["original_had_tracked_changes"] == {
        "current": False, "other": False}
    assert (tracked_result["metadata"]["comparison_baseline"]
            == accepted_result["metadata"]["comparison_baseline"]
            == "accepted_tracked_changes")
