"""Independent deterministic DOCX contract comparison pipeline."""
from .models import (AlignmentGroup, CompareBlock, CompareDocument, CompareResult,
                     CompareSummary, Coverage, DiffItem, TextSpan)
from .parser import parse_compare_document, parse_docx, parse_document
from .align import align_documents, align, sequence_align
from .text_diff import compare_docx, compare_documents, compare, diff_group, diff_text, compute_text_diff
from .selection import (SelectionAssessment, SelectionError, SelectionIssue,
                        SelectionSnapshot, assess_selection, binding_hash,
                        decision_hash, make_snapshot, normalize_decisions,
                        require_generation_ready)

__all__ = [
    "AlignmentGroup", "CompareBlock", "CompareDocument", "CompareResult",
    "CompareSummary", "Coverage", "DiffItem", "TextSpan",
    "parse_compare_document", "parse_docx", "parse_document", "align_documents", "align", "sequence_align",
    "compare_docx", "compare_documents", "compare", "diff_group", "diff_text", "compute_text_diff",
    "SelectionAssessment", "SelectionError", "SelectionIssue", "SelectionSnapshot",
    "assess_selection", "binding_hash", "decision_hash", "make_snapshot",
    "normalize_decisions", "require_generation_ready",
]
