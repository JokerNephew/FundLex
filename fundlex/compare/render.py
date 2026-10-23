"""Safe HTML projection for compare documents.

The renderer is deliberately independent from the revision viewer.  Text is
escaped before insertion and every mark carries the backend's stable diff id,
so the browser never has to search visible text (which would be ambiguous for
repeated contract clauses).
"""
from __future__ import annotations

from html import escape
from typing import Any, Iterable

from .models import CompareDocument, DiffItem, TextSpan


def _span_value(value: Any) -> TextSpan | None:
    if isinstance(value, TextSpan):
        return value
    if not isinstance(value, dict) or not value.get("block_id"):
        return None
    return TextSpan(str(value["block_id"]), int(value.get("start", 0)),
                    int(value.get("end", 0)), str(value.get("text", "")))


def _item_value(item: Any, name: str) -> TextSpan | None:
    if isinstance(item, DiffItem):
        return getattr(item, name, None)
    if isinstance(item, dict):
        return _span_value(item.get(name))
    return None


def _item_id(item: Any) -> str:
    if isinstance(item, DiffItem):
        return item.diff_id
    return str(item.get("id", ""))


def _item_spans(item: Any, side: str) -> list[TextSpan]:
    if isinstance(item, DiffItem):
        values = getattr(item, f"{side}_spans", ())
        if values:
            return list(values)
        value = getattr(item, side, None)
    elif isinstance(item, dict):
        values = item.get(f"{side}_spans") or []
        if values:
            return [span for span in (_span_value(v) for v in values) if span]
        value = _span_value(item.get(side))
    else:
        value = None
    return [value] if value else []


def render_compare_document(document: CompareDocument, diffs: Iterable[Any], *, side: str) -> str:
    """Render an escaped, block-addressable compare projection.

    ``side`` is ``left`` or ``right``.  Empty insert/delete sides receive a
    zero-width virtual anchor in the nearest block, allowing SVG connectors to
    remain visible.
    """
    if side not in {"left", "right"}:
        raise ValueError("side must be left or right")
    per_block: dict[str, list[tuple[int, int, str, str]]] = {}
    virtual: dict[str, list[tuple[int, str]]] = {}
    blocks = {b.block_id: b for b in document.blocks}
    for item in diffs:
        diff_id = _item_id(item)
        spans = _item_spans(item, side)
        if not spans:
            anchor = _item_value(item, f"{side}_anchor")
            bid = anchor.block_id if anchor else (document.blocks[0].block_id if document.blocks else f"{'L' if side == 'left' else 'R'}-virtual")
            if bid not in blocks and document.blocks:
                raise ValueError("COMPARE_RESULT_INVALID")
            virtual.setdefault(bid, []).append((anchor.start if anchor else 0, diff_id))
        for span in spans:
            block = blocks.get(span.block_id)
            if block is None or not 0 <= span.start < span.end <= len(block.raw_text) or block.raw_text[span.start:span.end] != span.text:
                raise ValueError("COMPARE_RESULT_INVALID")
            kind = "diff-" + (item.type if isinstance(item, DiffItem) else str(item.get("type", "modify")))
            per_block.setdefault(span.block_id, []).append((span.start, span.end, diff_id, kind))

    def anchor_html(diff_id: str) -> str:
        return f'<span class="compare-diff-anchor" data-diff-id="{escape(diff_id, quote=True)}" aria-hidden="true"></span>'

    def body_html(block) -> str:
        text = block.raw_text
        marks = sorted(per_block.get(block.block_id, []), key=lambda x: (x[0], x[1], x[2]))
        anchors = virtual.get(block.block_id, [])
        previous = 0
        for start, end, _, _ in marks:
            if start < previous:
                raise ValueError("COMPARE_RESULT_INVALID")
            previous = end
        if any(offset < 0 or offset > len(text) for offset, _ in anchors):
            raise ValueError("COMPARE_RESULT_INVALID")
        # Split only at known offsets; no client text search and no lost marks.
        boundaries = sorted({0, len(text), *(x for m in marks for x in m[:2]), *(x[0] for x in anchors)})
        body = []
        mi = 0
        for i, start in enumerate(boundaries):
            body.extend(anchor_html(did) for offset, did in sorted(anchors) if offset == start)
            if i + 1 == len(boundaries):
                break
            end = boundaries[i + 1]
            while mi < len(marks) and marks[mi][1] <= start:
                mi += 1
            fragment = escape(text[start:end])
            if mi < len(marks) and marks[mi][0] <= start < marks[mi][1]:
                _, _, did, kind = marks[mi]
                fragment = f'<mark class="compare-diff {escape(kind, quote=True)}" data-diff-id="{escape(did, quote=True)}">{fragment}</mark>'
            body.append(fragment)
        return ''.join(body)

    chunks = ['<div class="compare-document">']
    table = row = cell = None
    def close_table():
        nonlocal table, row, cell
        if table is not None:
            chunks.append('</td></tr></tbody></table>')
        table = row = cell = None

    for block in document.blocks:
        if block.table_index is not None:
            if table != block.table_index:
                close_table()
                chunks.append('<table class="compare-table"><tbody><tr><td>')
                table, row, cell = block.table_index, block.row_index, block.cell_index
            elif row != block.row_index:
                chunks.append('</td></tr><tr><td>')
                row, cell = block.row_index, block.cell_index
            elif cell != block.cell_index:
                chunks.append('</td><td>')
                cell = block.cell_index
        else:
            close_table()
        attrs = f' class="compare-block" data-block-id="{escape(block.block_id, quote=True)}" data-location="{escape(block.location, quote=True)}"'
        chunks.append(f'<p{attrs}>{body_html(block)}</p>')
    close_table()
    if not document.blocks:
        bid = f"{'L' if side == 'left' else 'R'}-virtual"
        chunks.append(f'<p class="compare-block compare-empty" data-block-id="{bid}">' + ''.join(anchor_html(did) for _, did in virtual.get(bid, [])) + '</p>')
    chunks.append('</div>')
    return ''.join(chunks)


# Backwards-friendly alias used by the API worker.
render_document = render_compare_document
