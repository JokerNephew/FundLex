"""Safe HTML projection for compare documents.

The renderer is deliberately independent from the revision viewer.  Text is
escaped before insertion and every mark carries the backend's stable diff id,
so the browser never has to search visible text (which would be ambiguous for
repeated contract clauses).
"""
from __future__ import annotations

from html import escape
import re
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


def _style_projection(style: str) -> tuple[str, str]:
    """Return a safe CSS class and semantic block tag.

    The parser retains the source paragraph style name while the presentation
    layer resolves the common OOXML style graph. Projecting the common Word
    built-ins preserves useful document hierarchy without claiming that every
    custom style has been fully resolved.
    """
    raw = str(style or "").strip()
    slug = re.sub(r"[^a-z0-9]+", "-", raw.casefold()).strip("-")[:80]
    style_class = f"compare-style-{slug}" if slug else ""
    low = raw.casefold()
    heading = re.search(r"(?:heading|标题)\s*([1-6])$", low)
    if heading:
        level = heading.group(1)
        return f"compare-style-heading-{level}", f"h{level}"
    if low in {"title", "标题", "document title"}:
        return "compare-style-title", "h1"
    if low in {"subtitle", "副标题", "document subtitle"}:
        return "compare-style-subtitle", "h2"
    return style_class, "p"


def _style_attr(properties) -> str:
    """Allow only the inert formatting subset produced by Presentation."""
    safe = []
    dimensions = {"font-size", "margin-left", "margin-right", "margin-top", "margin-bottom", "text-indent", "max-width", "width", "padding-left", "padding-right", "padding-top", "padding-bottom"}
    enums = {"text-align": {"left", "right", "center", "justify", "start", "end"},
             "font-weight": {"bold", "normal"}, "font-style": {"italic", "normal"},
             "vertical-align": {"super", "sub", "baseline", "top", "center", "bottom"},
             "break-before": {"page"}, "border-style": {"solid", "none"}}
    for name, value in properties:
        value = str(value)
        if name in dimensions and re.fullmatch(r"-?\d+(?:\.\d+)?(?:pt|px|em|%)", value):
            safe.append(f"{name}:{value}")
        elif name == "line-height" and re.fullmatch(r"\d+(?:\.\d+)?(?:pt)?", value):
            safe.append(f"{name}:{value}")
        elif name in {"color", "background-color"} and re.fullmatch(r"#[a-fA-F0-9]{6}", value):
            safe.append(f"{name}:{value}")
        elif name == "font-family" and re.fullmatch(r'[\w .(),"\-]{1,300}', value):
            safe.append(f"{name}:{value}")
        elif name == "text-decoration" and value in {"underline", "line-through", "underline line-through", "none"}:
            safe.append(f"{name}:{value}")
        elif value in enums.get(name, set()):
            safe.append(f"{name}:{value}")
    return f' style="{escape(";".join(safe), quote=True)}"' if safe else ""


def _run_style(run):
    # Omit false values so paragraph styles (for example Word Heading/Title)
    # can supply their inherited weight and style.  The parser intentionally
    # keeps a compact boolean representation and cannot distinguish an
    # explicit OOXML ``w:b w:val="0"`` from an inherited false value.
    props = []
    if run.bold:
        props.append(("font-weight", "bold"))
    if run.italic:
        props.append(("font-style", "italic"))
    decoration = " ".join(filter(None, ("underline" if run.underline else "", "line-through" if run.strike else "")))
    if decoration:
        props.append(("text-decoration", decoration))
    for key, value in (("font-size", run.font_size), ("font-family", run.font_family), ("color", run.color), ("vertical-align", run.vertical_align)):
        if value:
            props.append((key, value))
    return _style_attr(props)


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
        runs = block.runs
        # A malformed presentation must never alter the text/coordinate stream.
        if "".join(run.text for run in runs) != text or any(run.start < 0 or run.end > len(text) or text[run.start:run.end] != run.text for run in runs):
            runs = ()
        boundaries = sorted({0, len(text), *(x for m in marks for x in m[:2]), *(x[0] for x in anchors), *(x for run in runs for x in (run.start, run.end))})
        body = []
        mi = 0
        ri = 0
        for i, start in enumerate(boundaries):
            body.extend(anchor_html(did) for offset, did in sorted(anchors) if offset == start)
            if i + 1 == len(boundaries):
                break
            end = boundaries[i + 1]
            while mi < len(marks) and marks[mi][1] <= start:
                mi += 1
            fragment = escape(text[start:end])
            while ri < len(runs) and runs[ri].end <= start:
                ri += 1
            if ri < len(runs) and runs[ri].start <= start < runs[ri].end:
                fragment = f'<span class="compare-run"{_run_style(runs[ri])}>{fragment}</span>'
            if mi < len(marks) and marks[mi][0] <= start < marks[mi][1]:
                _, _, did, kind = marks[mi]
                fragment = f'<mark class="compare-diff {escape(kind, quote=True)}" data-diff-id="{escape(did, quote=True)}">{fragment}</mark>'
            body.append(fragment)
        return ''.join(body)

    chunks = [f'<div class="compare-document"{_style_attr(document.page_format)}>']
    table = row = cell = None
    def close_table():
        nonlocal table, row, cell
        if table is not None:
            chunks.append('</td></tr></tbody></table>')
        table = row = cell = None

    def cell_open(block) -> str:
        attrs = []
        if block.table_colspan > 1:
            attrs.append(f' colspan="{block.table_colspan}"')
        if block.table_rowspan > 1:
            attrs.append(f' rowspan="{block.table_rowspan}"')
        return '<td' + ''.join(attrs) + '>'

    for block in document.blocks:
        if block.table_index is not None:
            # OOXML represents the lower rows of a vertical merge as empty
            # continuation cells. Their content belongs to the origin cell;
            # emitting them would create duplicate columns and invalid HTML.
            if block.table_cell_continuation:
                continue
            if table != block.table_index:
                close_table()
                chunks.append('<table class="compare-table"><tbody><tr>' + cell_open(block))
                table, row, cell = block.table_index, block.row_index, block.cell_index
            elif row != block.row_index:
                chunks.append('</td></tr><tr>' + cell_open(block))
                row, cell = block.row_index, block.cell_index
            elif cell != block.cell_index:
                chunks.append('</td>' + cell_open(block))
                cell = block.cell_index
        else:
            close_table()
        style_class, tag = _style_projection(block.style)
        fmt = dict(block.paragraph_format)
        if fmt.get("heading-level") in {"1", "2", "3", "4", "5", "6"}:
            tag = f'h{fmt["heading-level"]}'
        classes = ["compare-block"]
        if style_class:
            classes.append(style_class)
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            classes.append("compare-heading")
        if fmt.get("list-label"):
            classes.append("compare-list-item")
            classes.append("compare-list-with-label")
        attrs = f' class="{" ".join(classes)}" data-block-id="{escape(block.block_id, quote=True)}" data-location="{escape(block.location, quote=True)}"'
        attrs += _style_attr(block.paragraph_format)
        label = f'<span class="compare-list-label" aria-hidden="true">{escape(fmt["list-label"])}\t</span>' if fmt.get("list-label") else ""
        chunks.append(f'<{tag}{attrs}>{label}{body_html(block)}</{tag}>')
    close_table()
    if not document.blocks:
        bid = f"{'L' if side == 'left' else 'R'}-virtual"
        chunks.append(f'<p class="compare-block compare-empty" data-block-id="{bid}">' + ''.join(anchor_html(did) for _, did in virtual.get(bid, [])) + '</p>')
    chunks.append('</div>')
    return ''.join(chunks)


# Backwards-friendly alias used by the API worker.
render_document = render_compare_document
