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
    generate_selected_redline,
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


def test_atomic_parent_manifest_uses_validated_source_text():
    """Review manifest recovery must validate an atomic parent revision."""
    from fundlex.recall_pipeline import _plan_ledger
    from types import SimpleNamespace

    planned = {"edits": [{"rule_id": "G05", "target_id": "T", "location": "p0",
                          "start": 0, "end": 8, "replacement": "新句。",
                          "components": []}], "conflicts": [], "ledger": []}
    plan = SimpleNamespace(plan_sha256="plan", edits=({"rule_id": "G05", "target_id": "T",
        "location": "p0", "start": 0, "end": 8, "replacement": "新句。",
        "expected_old_text": "旧句甲。", "expected_old_hash": "hash"},))
    report_plan = _plan_ledger(planned, plan)
    assert report_plan["edits"][0]["expected_old_text"] == "旧句甲。"


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
def test_selected_redline_keeps_only_accepted_edits(tmp_path):
    """The derived redline shows the accepted edits and nothing else."""
    report = _report()
    redline = _redline_copy(tmp_path)
    manifests = _manifests_from_report(report)
    kept, dropped = manifests[0], manifests[1]
    decisions = {int(kept["del_id"]): ACCEPT, int(dropped["del_id"]): REJECT}
    out = tmp_path / "selected_redline.docx"
    generate_selected_redline(redline, out, report, decisions)
    ids = set(_managed_revisions(out))
    # Accepted: still tracked, so it can be reviewed and settled to the new text.
    assert str(kept["del_id"]) in ids and str(kept["ins_id"]) in ids
    # Rejected: settled back to the original wording, no longer offered.
    assert str(dropped["del_id"]) not in ids and str(dropped["ins_id"]) not in ids


@requires_real
def test_selected_redline_reverts_rejected_edits_to_the_original(tmp_path):
    """A rejected edit reads as the original sentence, with no revision markup."""
    report = _report()
    redline = _redline_copy(tmp_path)
    manifest = _manifests_from_report(report)[0]
    out = tmp_path / "selected_redline.docx"
    generate_selected_redline(redline, out, report, {int(manifest["del_id"]): REJECT})
    # The rejected edit is settled back to the original wording and is no longer
    # offered for review...
    ids = set(_managed_revisions(out))
    assert str(manifest["del_id"]) not in ids and str(manifest["ins_id"]) not in ids
    # The rejected edit's wording is back as plain text (the original sentence).
    assert any(manifest["expected_old_text"] in para for para in _paragraph_texts(out))


@requires_real
def test_selected_redline_matches_the_selected_contract(tmp_path):
    """Only the accepted edits stay tracked, and settling them gives selected_final."""
    report = _report()
    redline = _redline_copy(tmp_path)
    manifests = _manifests_from_report(report)
    # The workbench sends a verdict for every revision; accept all but the first.
    decisions = {int(m["del_id"]): ACCEPT for m in manifests}
    decisions[int(manifests[0]["del_id"])] = REJECT

    selected = tmp_path / "selected.docx"
    generate_selected_artifact(redline, selected, report, decisions)
    derived = tmp_path / "selected_redline.docx"
    generate_selected_redline(redline, derived, report, decisions)

    # Exactly the accepted edits remain reviewable...
    expected = {str(m[key]) for m in manifests[1:] for key in ("del_id", "ins_id")}
    assert set(_managed_revisions(derived)) == expected
    # ...and reading the artifact as "accept what is tracked" gives selected_final.
    assert _accepted_view_texts(derived) == _paragraph_texts(selected)


@requires_real
def test_selected_redline_keeps_undecided_edits_tracked(tmp_path):
    """An edit the caller never mentioned keeps the engine's intent."""
    report = _report()
    redline = _redline_copy(tmp_path)
    manifests = _manifests_from_report(report)
    out = tmp_path / "selected_redline.docx"
    # Reject one edit and say nothing about the others.
    generate_selected_redline(redline, out, report, {int(manifests[0]["del_id"]): REJECT})
    remaining = set(_managed_revisions(out))
    # Everything except the rejected pair is still there, exactly as the engine
    # left it: an unmentioned edit is not silently turned down.
    assert remaining == set(_managed_revisions(redline)) - {str(manifests[0]["del_id"]),
                                                            str(manifests[0]["ins_id"])}


def _accepted_view_texts(path: Path) -> list[str]:
    """Paragraph text after accepting every change still tracked in the artifact.

    Accepting a change keeps its insertion and discards its deletion, so ``w:ins``
    text counts and ``w:del`` text does not.
    """
    root = etree.fromstring(_read_parts(str(path), ZipLimits())[DOCUMENT])
    texts = []
    for para in root.iter(Q("p")):
        parts = []
        for node in para.iter():
            if node.tag != Q("t"):
                continue
            if any(ancestor.tag == Q("del") for ancestor in node.iterancestors()):
                continue
            parts.append(node.text or "")
        texts.append("".join(parts))
    return texts


@requires_real
def test_selected_redline_requires_the_manifest(tmp_path):
    redline = _redline_copy(tmp_path)
    with pytest.raises(DocxError):
        generate_selected_redline(redline, tmp_path / "out.docx", {}, {1: ACCEPT})


@requires_real
def test_selected_redline_may_not_replace_the_redline(tmp_path):
    redline = _redline_copy(tmp_path)
    with pytest.raises(DocxError):
        generate_selected_redline(redline, redline, _report(), {1: ACCEPT})


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
