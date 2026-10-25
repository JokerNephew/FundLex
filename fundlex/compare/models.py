"""Data contracts for deterministic DOCX comparison.

The compare pipeline is intentionally independent from the revision pipeline.
Objects in this module are immutable where practical and have small ``to_dict``
helpers so API and HTML layers can consume the same result without re-parsing
text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class CompareRun:
    """A visible run segment with the small style subset used by the viewer."""

    text: str
    start: int
    end: int
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    color: str = ""
    font_size: str = ""
    font_family: str = ""
    vertical_align: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text, "start": self.start, "end": self.end,
            "bold": self.bold, "italic": self.italic,
            "underline": self.underline, "strike": self.strike,
            "color": self.color, "font_size": self.font_size,
            "font_family": self.font_family,
            "vertical_align": self.vertical_align,
        }


@dataclass(frozen=True)
class CompareBlock:
    block_id: str
    ordinal: int
    location: str
    kind: str
    section_path: str = ""
    raw_text: str = ""
    match_text: str = ""
    diff_text: str = ""
    container: str = "body"
    table_index: int | None = None
    row_index: int | None = None
    cell_index: int | None = None
    paragraph_index: int | None = None
    style: str = ""
    warnings: tuple[str, ...] = ()
    runs: tuple[CompareRun, ...] = ()
    paragraph_format: tuple[tuple[str, str], ...] = ()
    table_colspan: int = 1
    table_rowspan: int = 1
    table_col_start: int = 0
    table_cell_continuation: bool = False
    table_origin_row: int | None = None
    table_origin_cell: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "block_id": self.block_id, "ordinal": self.ordinal,
            "location": self.location, "kind": self.kind,
            "section_path": self.section_path, "raw_text": self.raw_text,
            "match_text": self.match_text, "diff_text": self.diff_text,
            "container": self.container, "table_index": self.table_index,
            "row_index": self.row_index, "cell_index": self.cell_index,
            "paragraph_index": self.paragraph_index, "style": self.style,
            "warnings": list(self.warnings),
            "runs": [run.to_dict() for run in self.runs],
            "paragraph_format": dict(self.paragraph_format),
            "table_colspan": self.table_colspan,
            "table_rowspan": self.table_rowspan,
            "table_col_start": self.table_col_start,
            "table_cell_continuation": self.table_cell_continuation,
            "table_origin_row": self.table_origin_row,
            "table_origin_cell": self.table_origin_cell,
        }


@dataclass(frozen=True)
class Coverage:
    status: str = "complete"
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "warnings": list(self.warnings)}


@dataclass(frozen=True)
class CompareDocument:
    blocks: tuple[CompareBlock, ...]
    source_sha256: str = ""
    filename: str = ""
    coverage: Coverage = field(default_factory=Coverage)
    page_format: tuple[tuple[str, str], ...] = ()

    @property
    def block_count(self) -> int:
        return len(self.blocks)

    def to_dict(self) -> dict[str, Any]:
        return {"filename": self.filename, "sha256": self.source_sha256,
                "blocks": [b.to_dict() for b in self.blocks],
                "coverage": self.coverage.to_dict(),
                "page_format": dict(self.page_format)}


@dataclass(frozen=True)
class AlignmentGroup:
    group_id: str
    left: tuple[CompareBlock, ...] = ()
    right: tuple[CompareBlock, ...] = ()

    @property
    def left_text(self) -> str:
        return "".join(b.raw_text for b in self.left)

    @property
    def right_text(self) -> str:
        return "".join(b.raw_text for b in self.right)

    @property
    def left_match_text(self) -> str:
        return "".join(b.match_text for b in self.left)

    @property
    def right_match_text(self) -> str:
        return "".join(b.match_text for b in self.right)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.group_id,
                "left": [b.block_id for b in self.left],
                "right": [b.block_id for b in self.right]}


@dataclass(frozen=True)
class TextSpan:
    block_id: str
    start: int
    end: int
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"block_id": self.block_id, "start": self.start,
                "end": self.end, "text": self.text}


@dataclass(frozen=True)
class DiffItem:
    diff_id: str
    type: str  # modify | insert | delete
    left: TextSpan | None = None
    right: TextSpan | None = None
    left_anchor: TextSpan | None = None
    right_anchor: TextSpan | None = None
    left_spans: tuple[TextSpan, ...] = ()
    right_spans: tuple[TextSpan, ...] = ()
    group_id: str = ""
    section: str = ""

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"id": self.diff_id, "type": self.type,
                                  "group_id": self.group_id,
                                  "section": self.section}
        result["left"] = self.left.to_dict() if self.left else None
        result["right"] = self.right.to_dict() if self.right else None
        if self.left_anchor:
            result["left_anchor"] = self.left_anchor.to_dict()
        if self.right_anchor:
            result["right_anchor"] = self.right_anchor.to_dict()
        if self.left_spans:
            result["left_spans"] = [s.to_dict() for s in self.left_spans]
        if self.right_spans:
            result["right_spans"] = [s.to_dict() for s in self.right_spans]
        return result


@dataclass(frozen=True)
class CompareSummary:
    total: int
    modify: int
    insert: int
    delete: int

    def to_dict(self) -> dict[str, int]:
        return {"total": self.total, "modify": self.modify,
                "insert": self.insert, "delete": self.delete}


@dataclass(frozen=True)
class CompareResult:
    schema_version: str
    left: CompareDocument
    right: CompareDocument
    alignment: tuple[AlignmentGroup, ...]
    diffs: tuple[DiffItem, ...]
    coverage: Coverage
    diagnostics: Mapping[str, Any] = field(default_factory=dict)

    @property
    def summary(self) -> CompareSummary:
        counts = {"modify": 0, "insert": 0, "delete": 0}
        for item in self.diffs:
            counts[item.type] = counts.get(item.type, 0) + 1
        return CompareSummary(len(self.diffs), counts["modify"], counts["insert"], counts["delete"])

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version,
                "left": {"filename": self.left.filename, "sha256": self.left.source_sha256},
                "right": {"filename": self.right.filename, "sha256": self.right.source_sha256},
                "summary": self.summary.to_dict(), "coverage": self.coverage.to_dict(),
                "diffs": [d.to_dict() for d in self.diffs],
                "diagnostics": dict(self.diagnostics)}
