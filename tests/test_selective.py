"""Tests for selective accept/reject of engine revision marks."""

from __future__ import annotations

from pathlib import Path

import pytest
from lxml import etree

from fundlex.docx import DOCUMENT, Q, DocxError, ZipLimits, _read_parts, _xml
from fundlex.selective import (
    ACCEPT,
    REJECT,
    _manifests_from_report,
    _normalise_decisions,
    apply_decisions,
    generate_selected_artifact,
)

REAL = Path("var/recall-first-evaluation/p6-dev-round1-01/D01")


def _report() -> dict:
    import json
    return json.loads((REAL / "report.json").read_text())


def _redline_copy(tmp_path: Path) -> Path:
    """The real revision artifact, renamed to .docx so the reader accepts it."""
    target = tmp_path / "redline.docx"
    target.write_bytes((REAL / "working_redline").read_bytes())
    return target


def _paragraph_texts(path: Path) -> list[str]:
    root = etree.fromstring(_read_parts(str(path), ZipLimits())[DOCUMENT])
    return ["".join(node.text or "" for node in para.iter() if node.tag == Q("t"))
            for para in root.iter(Q("p"))]


def _body_paragraph_text(path: Path, index: int) -> str:
    """Text of the body-level paragraph ``p{index}`` — the engine's locations.

    ``_paragraph_element`` indexes direct ``body/w:p`` children only; paragraphs
    nested in containers (e.g. the table of contents inside ``w:sdt``) are not
    part of that numbering.
    """
    root = etree.fromstring(_read_parts(str(path), ZipLimits())[DOCUMENT])
    body = root.find(Q("body"))
    paragraphs = [child for child in body if child.tag == Q("p")]
    return "".join(node.text or "" for node in paragraphs[index].iter() if node.tag == Q("t"))


def _managed_revisions(path: Path) -> list[str]:
    root = etree.fromstring(_read_parts(str(path), ZipLimits())[DOCUMENT])
    return [node.get(Q("id"), "") for node in root.iter()
            if node.tag in {Q("ins"), Q("del")}]


requires_real = pytest.mark.skipif(not (REAL / "report.json").is_file(),
                                   reason="real D01 evaluation artifact unavailable")


def test_normalise_decisions_accepts_id_map():
    assert _normalise_decisions({1: "accept", 2: "reject"}) == {1: ACCEPT, 2: REJECT}


def test_normalise_decisions_accepts_grouped_shape():
    assert _normalise_decisions({"accept": [1, "3"], "reject": [2]}) == {1: ACCEPT, 3: ACCEPT, 2: REJECT}


def test_normalise_decisions_ignores_unknown_verdicts():
    assert _normalise_decisions({1: "maybe", 2: "reject"}) == {2: REJECT}


@requires_real
def test_manifests_rebuilt_with_same_numbering_as_generation():
    manifests = _manifests_from_report(_report())
    assert [m["del_id"] for m in manifests] == list(range(1, 2 * len(manifests), 2))
    assert [m["ins_id"] for m in manifests] == list(range(2, 2 * len(manifests) + 1, 2))
    # Generation sorts by (location, -start); the plan must rebuild identically.
    assert manifests[0]["location"] == "p1191"


@requires_real
def test_accept_all_matches_engine_final_paragraph_text(tmp_path):
    report = _report()
    redline = _redline_copy(tmp_path)
    out = tmp_path / "selected.docx"
    all_accept = {int(m["del_id"]): ACCEPT for m in _manifests_from_report(report)}
    result = generate_selected_artifact(redline, out, report, all_accept)
    assert not result.rejected
    engine_final = tmp_path / "engine_final.docx"
    engine_final.write_bytes((REAL / "working_final").read_bytes())
    assert _paragraph_texts(out) == _paragraph_texts(engine_final)


@requires_real
def test_reject_all_restores_original_text(tmp_path):
    report = _report()
    redline = _redline_copy(tmp_path)
    out = tmp_path / "rejected.docx"
    manifests = _manifests_from_report(report)
    result = generate_selected_artifact(
        redline, out, report, {int(m["del_id"]): REJECT for m in manifests})
    assert not result.accepted
    for manifest in manifests:
        if not manifest["expected_old_text"]:
            continue  # insertion-only edit: nothing was deleted to restore
        index = int(manifest["location"][1:])
        assert manifest["expected_old_text"] in _body_paragraph_text(out, index), manifest["location"]


@requires_real
def test_single_reject_changes_only_its_own_paragraph(tmp_path):
    report = _report()
    redline = _redline_copy(tmp_path)
    manifests = _manifests_from_report(report)
    generate_selected_artifact(redline, tmp_path / "all.docx", report,
                               {int(m["del_id"]): ACCEPT for m in manifests})
    generate_selected_artifact(redline, tmp_path / "one.docx", report,
                               {int(manifests[0]["del_id"]): REJECT})
    baseline = [_body_paragraph_text(tmp_path / "all.docx", i) for i in range(1300)]
    changed = [i for i, (a, b) in enumerate(
        zip((_body_paragraph_text(tmp_path / "one.docx", i) for i in range(1300)), baseline))
        if a != b]
    assert changed == [1191]


@requires_real
def test_no_managed_revision_markup_survives(tmp_path):
    report = _report()
    redline = _redline_copy(tmp_path)
    out = tmp_path / "selected.docx"
    generate_selected_artifact(redline, out, report, {1: REJECT, 3: ACCEPT})
    assert _managed_revisions(out) == []


@requires_real
def test_pure_delete_rejection_restores_deleted_text(tmp_path):
    report = _report()
    redline = _redline_copy(tmp_path)
    manifests = _manifests_from_report(report)
    # Edit 2 is a pure deletion (no inserted text).
    manifest = manifests[1]
    assert manifest["replacement"] == ""
    out = tmp_path / "pure.docx"
    generate_selected_artifact(redline, out, report, {int(manifest["del_id"]): REJECT})
    assert manifest["expected_old_text"] in "\n".join(_paragraph_texts(out))


@requires_real
def test_accepting_a_revision_drops_its_deleted_text(tmp_path):
    report = _report()
    redline = _redline_copy(tmp_path)
    manifests = _manifests_from_report(report)
    manifest = manifests[0]
    out = tmp_path / "accepted.docx"
    generate_selected_artifact(redline, out, report, {int(manifest["del_id"]): ACCEPT})
    paragraph = next(p for p in _paragraph_texts(out) if manifest["replacement"][:20] in p)
    assert manifest["expected_old_text"] not in paragraph


@requires_real
def test_missing_manifest_fails_closed(tmp_path):
    redline = _redline_copy(tmp_path)
    with pytest.raises(DocxError):
        generate_selected_artifact(redline, tmp_path / "out.docx", {}, {1: ACCEPT})


@requires_real
def test_output_path_may_not_replace_the_redline(tmp_path):
    redline = _redline_copy(tmp_path)
    with pytest.raises(DocxError):
        generate_selected_artifact(redline, redline, _report(), {1: ACCEPT})


@requires_real
def test_apply_decisions_is_idempotent_over_unknown_ids(tmp_path):
    """Ids we did not generate must be reported, not silently rewritten."""
    report = _report()
    parts = _read_parts(str(_redline_copy(tmp_path)), ZipLimits())
    root = _xml(parts[DOCUMENT], ZipLimits())
    manifests = _manifests_from_report(report)
    absent = apply_decisions(root, manifests, {9999: REJECT})
    assert absent == ()
