"""FL-D459: approved span deletes use one absolute paragraph coordinate system.

The old audit probe placed the same approved clause after a retained sentence; the
approval stayed valid but the planner fell back to compose because it sliced the
paragraph and then applied absolute offsets to the slice.  The delete must stay
exact and must never consume the neighbouring retained sentences.
"""
from __future__ import annotations

from pathlib import Path

from docx import Document

from fundlex.docx import inspect_docx
from fundlex.recall import Facts, Target, approval_book_for, plan_target

CLAUSE = "销售服务费主要用于销售机构营销。"

RULE = {
    "rule_id": "G99", "title": "删除旧用途",
    "operations": [{"op": "delete", "old_text": "销售服务费主要用于销售机构营销。",
                    "condition": {"kind": "none"}}],
}


class NoModel:
    def call(self, **kwargs):  # pragma: no cover - must never run
        raise AssertionError("model must not be called")


def _facts() -> Facts:
    return Facts("普通开放式基金", "", "", (), False, "", "", "", {}, ())


def _plan(tmp_path: Path, paragraph: str, start: int):
    path = tmp_path / "approved-delete.docx"
    document = Document()
    document.add_paragraph(paragraph)
    document.save(path)
    inspection = inspect_docx(path)
    target = Target("T1", "G99", "p0", CLAUSE, "needs_edit", "semantic target",
                    start=start, end=start + len(CLAUSE), resolution="resolved",
                    segment_ok=True, operations=("G99:0",), scope_id="G99:S:L")
    book = approval_book_for({"G99": RULE}, [target], inspection)
    assert book.allows(target, inspection).ok
    edit = plan_target(RULE, target, inspection, _facts(), NoModel(),
                       compose_budget=[0], approvals=book)
    assert edit is not None
    return edit, inspection


def test_approved_delete_after_retained_prefix_is_still_deterministic(tmp_path):
    prefix = "必须保留的相邻合同原句。"
    edit, inspection = _plan(tmp_path, prefix + CLAUSE, len(prefix))
    assert edit.content_source == "approved_span_delete"
    assert (edit.start, edit.end) == (len(prefix), len(prefix) + len(CLAUSE))
    assert edit.replacement == ""
    text = inspection.by_location("p0").text
    assert text[:edit.start] == prefix
    assert text[edit.end:] == ""


def test_approved_delete_never_eats_the_neighbouring_sentences(tmp_path):
    before, after = "必须保留的前句。", "必须保留的后句。"
    paragraph = before + CLAUSE + after
    edit, inspection = _plan(tmp_path, paragraph, len(before))
    assert edit.content_source == "approved_span_delete"
    assert edit.start >= len(before)
    assert edit.end <= len(before) + len(CLAUSE)
    text = inspection.by_location("p0").text
    assert text[:edit.start].endswith(before)
    assert text[edit.end:].startswith(after)


def test_offset_zero_is_unchanged(tmp_path):
    edit, inspection = _plan(tmp_path, CLAUSE, 0)
    assert edit.content_source == "approved_span_delete"
    assert (edit.start, edit.end) == (0, len(CLAUSE))
    assert inspection.by_location("p0").text[edit.start:edit.end] == CLAUSE
