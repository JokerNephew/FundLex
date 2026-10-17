"""FL-D109 step 2: sweep windows follow section boundaries, with a character fallback.

The sweep used a pure character window, so one window could straddle unrelated sections
and a clause could be cut across two windows. ``_section_aware_chunks`` groups whole
sections into a window until the char budget would overflow, splits a section that is
itself too big, and collects paragraphs belonging to no section (``structure_index`` caps
at 80 sections, so trailing content can be unassigned) into character windows.

The tests below pin the three properties that matter: section alignment, no overflow, and
zero coverage loss.
"""

from __future__ import annotations

from dataclasses import dataclass

from fundlex.recall_pipeline import _Chunk, _section_aware_chunks


@dataclass
class _Span:
    location: str
    text: str
    zone: str = "body"
    logical_zone: str | None = None


@dataclass
class _Section:
    id: str
    locations: tuple[str, ...]


class _Inspection:
    def __init__(self, spans):
        self.paragraphs = spans
        self._by_location = {span.location: span for span in spans}

    def by_location(self, location):
        return self._by_location[location]


def test_windows_follow_section_boundaries():
    spans = [_Span("p1", "第一节第一段"), _Span("p2", "第一节第二段"),
             _Span("p3", "第二节第一段"), _Span("p4", "第二节第二段")]
    sections = [_Section("S01", ("p1", "p2")), _Section("S02", ("p3", "p4"))]
    chunks = _section_aware_chunks(_Inspection(spans), sections, max_chars=1000)
    # Both small sections fit one window: sections are packed, not one window per section.
    assert len(chunks) == 1
    assert list(chunks[0].locations) == ["p1", "p2", "p3", "p4"]


def test_sections_group_into_separate_windows_when_budget_is_tight():
    spans = [_Span("p1", "甲" * 40), _Span("p2", "乙" * 40),
             _Span("p3", "丙" * 40), _Span("p4", "丁" * 40)]
    sections = [_Section("S01", ("p1", "p2")), _Section("S02", ("p3", "p4"))]
    # Each section is ~92 chars (two 44-char lines + newline); a 150-char budget fits one
    # section per window but not both.
    chunks = _section_aware_chunks(_Inspection(spans), sections, max_chars=150)
    assert len(chunks) == 2
    assert list(chunks[0].locations) == ["p1", "p2"]
    assert list(chunks[1].locations) == ["p3", "p4"]


def test_oversized_section_is_split_without_exceeding_budget():
    spans = [_Span(f"p{i}", "字" * 30) for i in range(1, 7)]
    sections = [_Section("S01", tuple(f"p{i}" for i in range(1, 7)))]
    chunks = _section_aware_chunks(_Inspection(spans), sections, max_chars=80)
    assert len(chunks) > 1
    assert all(len(chunk.text) <= 80 for chunk in chunks)
    assert [loc for chunk in chunks for loc in chunk.locations] == [f"p{i}" for i in range(1, 7)]


def test_unassigned_paragraphs_are_still_swept():
    """Paragraphs outside every section must not be dropped (coverage hole guard)."""
    spans = [_Span("p1", "第一节"), _Span("p9", "不属于任何章节的段落")]
    sections = [_Section("S01", ("p1",))]
    chunks = _section_aware_chunks(_Inspection(spans), sections, max_chars=1000)
    locations = {loc for chunk in chunks for loc in chunk.locations}
    assert "p9" in locations
    assert "p9" in "\n".join(chunk.text for chunk in chunks)


def test_non_readable_zones_are_excluded():
    spans = [_Span("p1", "正文", zone="body"), _Span("p2", "目录", zone="toc")]
    sections = [_Section("S01", ("p1", "p2"))]
    chunks = _section_aware_chunks(_Inspection(spans), sections, max_chars=1000)
    locations = {loc for chunk in chunks for loc in chunk.locations}
    assert locations == {"p1"}


def test_chunk_ids_are_dense_and_unique():
    spans = [_Span(f"p{i}", "字" * 30) for i in range(1, 7)]
    sections = [_Section("S01", ("p1", "p2")), _Section("S02", ("p3", "p4")),
                _Section("S03", ("p5", "p6"))]
    chunks = _section_aware_chunks(_Inspection(spans), sections, max_chars=80)
    ids = [chunk.id for chunk in chunks]
    assert ids == [f"C{i:03d}" for i in range(1, len(chunks) + 1)]
