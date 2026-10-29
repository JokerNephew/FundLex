from fundlex.compare.models import (AlignmentGroup, CompareBlock, CompareDocument,
                                    CompareResult, DiffItem, TextSpan)
from fundlex.compare.render import render_merged_document


def _block(block_id: str, text: str, ordinal: int = 0, **kwargs) -> CompareBlock:
    return CompareBlock(block_id, ordinal, f"p{ordinal}", "paragraph", raw_text=text, **kwargs)


def _result(left_text: str, right_text: str, diffs: tuple[DiffItem, ...]) -> CompareResult:
    left = CompareDocument((_block("L000001", left_text),))
    right = CompareDocument((_block("R000001", right_text),))
    return CompareResult("contract-compare-v1", left, right,
                         (AlignmentGroup("G0001", left.blocks, right.blocks),), diffs,
                         # Coverage is not relevant to projection tests.
                         __import__("fundlex.compare.models", fromlist=["Coverage"]).Coverage())


def test_merged_projection_places_removed_text_before_inserted_text():
    result = _result("保留 旧 结尾", "保留 新 结尾", (
        DiffItem("D0001", "modify",
                 left=TextSpan("L000001", 3, 4, "旧"),
                 right=TextSpan("R000001", 3, 4, "新")),
    ))

    html = render_merged_document(result.right, [d.to_dict() for d in result.diffs],
                                  left_document=result.left)

    assert '<del class="compare-del" data-diff-id="D0001">旧</del>' in html
    assert '<ins class="compare-ins" data-diff-id="D0001">新</ins>' in html
    assert html.index("旧") < html.index("新")
    assert "has-change" in html


def test_merged_projection_marks_a_fully_inserted_paragraph():
    right = CompareDocument((_block("R000001", "新增条款"),))
    diff = DiffItem("D0001", "insert", right=TextSpan("R000001", 0, 4, "新增条款"),
                    right_spans=(TextSpan("R000001", 0, 4, "新增条款"),))

    html = render_merged_document(right, [diff], left_document=CompareDocument(()))

    assert '<ins class="compare-ins" data-diff-id="D0001">新增条款</ins>' in html
    assert "has-change" in html


def test_merged_projection_keeps_fully_deleted_paragraphs_separate():
    left = CompareDocument((_block("L000001", "删除段落一", 0), _block("L000002", "删除段落二", 1)))
    right = CompareDocument((_block("R000001", "保留段落"),))
    spans = (TextSpan("L000001", 0, 5, "删除段落一"), TextSpan("L000002", 0, 5, "删除段落二"))
    diff = DiffItem("D0001", "delete", left=spans[0], left_spans=spans,
                    right_anchor=TextSpan("R000001", 0, 0, ""))

    html = render_merged_document(right, [diff], left_document=left)

    assert html.count("compare-deleted-paragraph") == 2
    assert "删除段落一" in html and "删除段落二" in html
    assert html.index("删除段落一") < html.index("删除段落二") < html.index("保留段落")
    assert "compare-paragraph-mark" in html


def test_merged_projection_escapes_document_text():
    right = CompareDocument((_block("R000001", "<script>alert(1)</script>"),))
    diff = DiffItem("D0001", "insert",
                    right=TextSpan("R000001", 0, 25, "<script>alert(1)</script>"))

    html = render_merged_document(right, [diff], left_document=CompareDocument(()))

    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_merged_projection_preserves_table_cell_geometry():
    from docx import Document
    from fundlex.compare.parser import parse_compare_document
    from io import BytesIO

    document = Document()
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "旧值"
    table.cell(0, 1).text = "保留"
    data = BytesIO()
    document.save(data)
    right = parse_compare_document(data.getvalue(), filename="right.docx", side="R")
    cell_block = right.blocks[0]
    diff = DiffItem("D0001", "insert",
                    right=TextSpan(cell_block.block_id, 0, 2, cell_block.raw_text[:2]))

    html = render_merged_document(right, [diff], left_document=CompareDocument(()))

    assert html.count("<table") == 1
    assert "<td>" in html
    assert "<ins" in html
