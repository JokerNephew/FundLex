# -*- coding: utf-8 -*-
"""FL-D562: whole-body "全部采用B" (delete-all-left + insert-all-right) delivery.

The FL-D543 trailing-delete fail-closed hardening also covered the legitimate
whole-document replacement shape: every direct body paragraph changed, so the
alignment falls back to one delete diff per left paragraph plus one insert
diff per right paragraph.  A dedicated detector + writer now handles exactly
that shape while every partial/truncated chain keeps failing closed.

Guarantees verified here with real DOCX packages:

- delivery succeeds and the final text equals the right document verbatim;
- redline and final agree (writer accept, independent upload accept oracle);
- undo/audit information is complete (every left run retained inside w:del,
  every right run wrapped in w:ins, one manifest entry per diff, consistent
  author/timestamp);
- partial chains (deletes only, one insert dropped, tail delete + interleaved
  insert) and any payload/source tampering still fail closed without leaving
  artifacts behind.
"""
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from docx import Document
from lxml import etree

from fundlex.compare import compare_docx, generate_selection_artifacts, parse_compare_document
from fundlex.compare.revisions import prepare_compare_input
from fundlex.compare.selection_writer import Q
from fundlex.docx import DOCUMENT, DocxError, ZipLimits

BASE250 = [f"T{i:03d}旧条款内容甲乙丙丁戊己庚辛壬癸。" for i in range(250)]
REPLACEMENT250 = [f"T{i:03d}全新条款戌亥子丑寅卯辰巳午未。" for i in range(250)]
BASE300 = [f"第{i:03d}条本条款约定基金管理人应当按照诚实信用原则履行职责义务。" for i in range(300)]
REPLACEMENT300 = [
    f"第{i:03d}款修订后版本条款内容完全不同没有任何余留相似字符甲乙丙丁戊己庚辛。" for i in range(300)]


def _save(path: Path, texts):
    document = Document()
    for text in texts:
        document.add_paragraph(text)
    document.save(path)


def _result(left: Path, right: Path):
    payload = compare_docx(left, right).to_dict()
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode()
    return payload, hashlib.sha256(encoded).hexdigest()


def _generate(left, right, payload, payload_hash, decisions, tmp_path, tag=""):
    final = tmp_path / f"final{tag}.docx"
    redline = tmp_path / f"redline{tag}.docx"
    validation = generate_selection_artifacts(left, right, payload, decisions, final, redline,
                                              selection_epoch=1, result_sha256=payload_hash)
    return validation, final, redline


def _adopt_all_right(payload):
    return {diff["id"]: "right" for diff in payload["diffs"]}


# ------------------------------------------------ delivery (case ①) --------


@pytest.mark.parametrize("base,replacement,tag",
                         [(BASE250, REPLACEMENT250, "-before-anchor"),
                          (BASE300, REPLACEMENT300, "-after-anchor")])
def test_full_body_replacement_delivers_final_equal_right(tmp_path, base, replacement, tag):
    """Both anchor orientations (insert groups ordered before/after the delete
    groups produce before/after anchors) deliver final == right verbatim."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, base)
    _save(right, replacement)
    payload, payload_hash = _result(left, right)
    validation, final, redline = _generate(
        left, right, payload, payload_hash, _adopt_all_right(payload), tmp_path, tag)
    assert "full_body_replacement" in validation.checks
    final_texts = [block.raw_text for block in parse_compare_document(final).blocks]
    assert final_texts == replacement
    right_texts = [block.raw_text for block in parse_compare_document(right).blocks]
    assert final_texts == right_texts
    # One manifest entry per adopted diff: the audit trail is complete.
    assert {item["diff_id"] for item in validation.manifest} == {
        diff["id"] for diff in payload["diffs"]}

    root = etree.fromstring(zipfile.ZipFile(io.BytesIO(redline.read_bytes())).read(DOCUMENT))
    deleted_text = "".join(node.text or "" for node in root.iter(Q("delText")))
    inserted_text = "".join(text.text or ""
                            for node in root.iter(Q("ins")) if node.getparent().tag == Q("p")
                            for text in node.iter(Q("t")))
    # Undo information: every original left run survives inside w:del;
    # every right paragraph's text is carried by w:ins revisions.
    assert deleted_text == "".join(base)
    assert inserted_text == "".join(replacement)
    authors = {node.get(Q("author")) for node in root.iter(Q("del"))}
    assert authors == {"FundLex Compare"}
    assert all(node.get(Q("date")) for node in root.iter(Q("ins")))
    # Double-write consistency: the independent upload accept oracle reaches
    # the delivered final byte tree.
    prepared = prepare_compare_input(redline.read_bytes(), limits=ZipLimits())
    prepared_root = etree.fromstring(zipfile.ZipFile(io.BytesIO(prepared.data)).read(DOCUMENT))
    final_root = etree.fromstring(zipfile.ZipFile(io.BytesIO(final.read_bytes())).read(DOCUMENT))
    assert etree.tostring(prepared_root, method="c14n") == etree.tostring(
        final_root, method="c14n")


def test_full_body_replace_kind_still_works_when_not_split(tmp_path):
    """Small documents align as one big modify (replace) covering both bodies;
    the ordinary writer already handled that shape — it must keep working."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE250[:10])
    _save(right, REPLACEMENT250[:10])
    payload, payload_hash = _result(left, right)
    _, final, _ = _generate(left, right, payload, payload_hash,
                            _adopt_all_right(payload), tmp_path, "-small")
    assert [block.raw_text for block in parse_compare_document(final).blocks] == REPLACEMENT250[:10]


# ------------------------------------------------ rejection (cases ② ③) ----


def _assert_rejected(excinfo, *paths):
    assert excinfo.value.code == "SELECTION_BLOCK_STRUCTURE_UNSUPPORTED"
    assert not any(path.exists() for path in paths)


def test_deletes_only_over_full_change_stay_rejected(tmp_path):
    """A big delete chain without adopted inserts is not a full replacement."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE250)
    _save(right, REPLACEMENT250)
    payload, payload_hash = _result(left, right)
    decisions = {diff["id"]: ("right" if diff["type"] == "delete" else "left")
                 for diff in payload["diffs"]}
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        _generate(left, right, payload, payload_hash, decisions, tmp_path)
    _assert_rejected(excinfo, final, redline)


def test_single_dropped_insert_breaks_full_replacement(tmp_path):
    """Withholding one insert drops the plan out of whole-body equivalence."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE250)
    _save(right, REPLACEMENT250)
    payload, payload_hash = _result(left, right)
    decisions = _adopt_all_right(payload)
    insert_ids = [diff["id"] for diff in payload["diffs"] if diff["type"] == "insert"]
    decisions[insert_ids[len(insert_ids) // 2]] = "left"
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        _generate(left, right, payload, payload_hash, decisions, tmp_path)
    _assert_rejected(excinfo, final, redline)


TAIL_BASE = [f"第{i:03d}条本条款约定基金管理人应当按照诚实信用原则履行职责义务。"
             for i in range(250)]
TAIL_INSERTS = ["全新增条款甲与本组合任何旧条款均不相似。", "全新增条款乙内容也不相似于任何旧条款。"]


def test_tail_delete_plus_interleaved_insert_still_rejected(tmp_path):
    """A tail delete chain on a kept prefix is a trailing chain, not a whole
    body replacement (kept paragraphs are direct body paragraphs too).  Inserts
    anchored on the kept prefix cannot be merged into the chain keeper; this
    stays fail-closed at the large-document scale."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, TAIL_BASE)
    _save(right, TAIL_BASE[:247] + TAIL_INSERTS)
    payload, payload_hash = _result(left, right)
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        _generate(left, right, payload, payload_hash, _adopt_all_right(payload), tmp_path)
    _assert_rejected(excinfo, final, redline)


def test_insert_anchored_on_deleted_tail_block_stays_deliverable(tmp_path):
    """Pre-existing deliverable shape (verified identical on the pre-FL-D562
    writer): the same tail delete + insert composition aligned in the other
    order anchors the inserts on the last deleted paragraph.  Every deleted
    paragraph then receives a plain mark+run deletion, the redline collapses
    cleanly, and final == right passes all three accept validations.  The
    FL-D562 path must not disturb this behavior."""
    tail250 = [f"T{i:03d}旧条款内容甲乙丙丁戊己庚辛壬癸。" for i in range(250)]
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, tail250)
    _save(right, tail250[:247] + TAIL_INSERTS)
    payload, payload_hash = _result(left, right)
    anchors = {(diff.get("left_anchor") or {}).get("block_id")
               for diff in payload["diffs"] if diff["type"] == "insert"}
    if anchors != {"L000249"}:
        pytest.skip("alignment produced the kept-anchor order; the twin "
                    "fail-closed test covers that shape")
    validation, final, _ = _generate(left, right, payload, payload_hash,
                                     _adopt_all_right(payload), tmp_path, "-tail-anchor")
    assert "full_body_replacement" not in validation.checks
    expected = tail250[:247] + TAIL_INSERTS
    assert [block.raw_text for block in parse_compare_document(final).blocks] == expected


# ------------------------------------------------ mutation (case ④) --------


def test_tampered_right_source_bytes_fail_closed(tmp_path):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE250)
    _save(right, REPLACEMENT250)
    payload, payload_hash = _result(left, right)
    tampered = tmp_path / "right-tampered.docx"
    data = bytearray(right.read_bytes())
    data[-8] ^= 0x5A
    tampered.write_bytes(bytes(data))
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        generate_selection_artifacts(left, tampered, payload, _adopt_all_right(payload),
                                     final, redline, selection_epoch=1,
                                     result_sha256=payload_hash)
    assert excinfo.value.code in {"SELECTION_SOURCE_HASH_MISMATCH", "PACKAGE_ZIP_INVALID",
                                  "SELECTION_BLOCK_STRUCTURE_UNSUPPORTED"}
    assert not final.exists() and not redline.exists()


def test_tampered_diff_payload_fails_result_hash(tmp_path):
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE250)
    _save(right, REPLACEMENT250)
    payload, payload_hash = _result(left, right)
    bad = json.loads(json.dumps(payload))
    bad["diffs"][0]["right_spans"][0]["text"] += "篡改"
    bad_hash = hashlib.sha256(json.dumps(bad, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode()).hexdigest()
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        generate_selection_artifacts(left, right, bad, _adopt_all_right(bad),
                                     final, redline, selection_epoch=1,
                                     result_sha256=bad_hash)
    assert excinfo.value.code == "SELECTION_RESULT_DIFF_MISMATCH"
    assert not final.exists() and not redline.exists()


def test_genuinely_inconsistent_right_document_fails_closed(tmp_path):
    """A result computed for a *different* right document can never pass the
    source/result binding of this selection."""
    left, right = tmp_path / "left.docx", tmp_path / "right.docx"
    _save(left, BASE250)
    _save(right, REPLACEMENT250)
    other = tmp_path / "right-other.docx"
    _save(other, [text + "其一。" for text in REPLACEMENT250])
    payload, payload_hash = _result(left, other)
    final, redline = tmp_path / "final.docx", tmp_path / "redline.docx"
    with pytest.raises(DocxError) as excinfo:
        generate_selection_artifacts(left, right, payload, _adopt_all_right(payload),
                                     final, redline, selection_epoch=1,
                                     result_sha256=payload_hash)
    assert excinfo.value.code == "SELECTION_SOURCE_HASH_MISMATCH"
    assert not final.exists() and not redline.exists()
