"""Read-only DOCX → interactive HTML projection for the workbench.

This module renders a contract (WITH revision marks intact) as HTML so the user
can review the document and accept/reject each revision individually, exactly
like operating on the Word document itself.

Design rules
------------
* Read-only. Never mutates the source package. Artifact writing stays in
  :mod:`fundlex.docx`.
* Revision anchors are taken directly from the OOXML ``w:id`` on ``w:ins`` /
  ``w:del`` elements. These are exactly the ``ins_id`` / ``del_id`` values that
  :func:`fundlex.docx.generate_artifacts` records in its manifest, so the HTML
  needs **no text matching** to map a run to a business edit.
* General block traversal. The document body is walked recursively so block
  containers (``w:sdt`` / ``w:sdtContent``) and tables are not silently
  dropped. The previous demo converter only looked at top-level ``w:p`` /
  ``w:tbl`` and lost the entire table of contents (see FL-D087).
* Hyperlinks, fields, bookmarks, tabs and page breaks are all projected so the
  rendered page matches what the user sees in Word.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Mapping
from urllib.parse import unquote
import zipfile

from lxml import etree

from .docx import DOCUMENT, Q, W, DocxError, ZipLimits, _read_parts, _xml


R = "http://schemas.openxmlformats.org/package/2006/relationships"
# Relationship types we resolve to a real href; anything else stays text-only.
_HYPERLINK_REL = "/hyperlink"
_SAFE_SCHEMES = ("http://", "https://", "mailto:", "ftp://")


def _escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _text_content(element: etree._Element) -> str:
    """Concatenated visible text of an element subtree.

    Deleted text is stored in ``w:delText`` rather than ``w:t``, so both are
    collected here.
    """
    return "".join(node.text or "" for node in element.iter()
                   if node.tag in {Q("t"), Q("delText")})


@dataclass
class _ParagraphStyle:
    name: str = ""
    align: str = ""
    indent_left: int = 0
    indent_hanging: int = 0
    in_table: bool = False
    heading: bool = False


class HtmlProjection:
    """Projection of one DOCX revision artifact into reviewable HTML."""

    def __init__(self, parts: Mapping[str, bytes], limits: ZipLimits) -> None:
        self.limits = limits
        self.parts = parts
        self.root = _xml(parts[DOCUMENT], limits)
        self.relationships = self._load_relationships(parts)
        self.styles = self._load_styles(parts)
        self.bookmarks: dict[str, str] = {}
        self._bookmark_seq = 0
        # revision id -> {"text": ..., "paragraphs": [ids]}
        self.revisions: dict[str, dict[str, Any]] = {}
        self.page_count = 0
        self.has_toc = False

    # ----- package helpers -------------------------------------------------

    @staticmethod
    def _load_relationships(parts: Mapping[str, bytes]) -> dict[str, str]:
        rels = parts.get("word/_rels/document.xml.rels")
        if rels is None:
            return {}
        try:
            root = etree.fromstring(rels)
        except etree.XMLSyntaxError:
            return {}
        mapping: dict[str, str] = {}
        for node in root:
            rid = node.get("Id")
            target = node.get("Target", "")
            kind = node.get("Type", "")
            if rid and _HYPERLINK_REL in kind:
                mapping[rid] = target
        return mapping

    @staticmethod
    def _load_styles(parts: Mapping[str, bytes]) -> dict[str, dict[str, Any]]:
        styles = parts.get("word/styles.xml")
        if styles is None:
            return {}
        try:
            root = etree.fromstring(styles)
        except etree.XMLSyntaxError:
            return {}
        table: dict[str, dict[str, Any]] = {}
        for node in root.findall(Q("style")):
            if node.get(Q("type")) != "paragraph":
                continue
            style_id = node.get(Q("styleId"), "")
            if not style_id:
                continue
            name_node = node.find(Q("name"))
            outline = node.find(Q("pPr") + "/" + Q("outlineLvl")) if node.find(Q("pPr")) is not None else None
            table[style_id] = {
                "name": name_node.get(Q("val")) if name_node is not None else "",
                "hidden": node.find(Q("hidden")) is not None,
                "outline": outline.get(Q("val")) if outline is not None else None,
            }
        return table

    # ----- revision bookkeeping -------------------------------------------

    def _record(self, revision_id: str, text: str, kind: str) -> None:
        entry = self.revisions.setdefault(revision_id, {"ins": [], "del": []})
        entry[kind].append(text)

    # ----- run / inline rendering -----------------------------------------

    def _render_run(self, run: etree._Element, *, deleted: bool) -> str:
        chunks: list[str] = []
        for child in run:
            tag = child.tag
            if tag in {Q("t"), Q("delText"), Q("instrText")}:
                # instrText holds field codes; never show them to the user.
                if tag == Q("instrText"):
                    continue
                chunks.append(_escape(child.text or ""))
            elif tag in {Q("br"), Q("cr")}:
                if child.get(Q("type")) == "page":
                    self.page_count += 1
                    chunks.append('<span class="page-break" data-page-break="1"></span>')
                else:
                    chunks.append("<br>")
            elif tag == Q("tab"):
                chunks.append('<span class="doc-tab"></span>')
            elif tag == Q("sym"):
                char = child.get(Q("char"))
                if char:
                    try:
                        chunks.append(_escape(chr(int(char, 16))))
                    except ValueError:
                        pass
            elif tag == Q("drawing") or tag == Q("object") or tag == Q("pict"):
                chunks.append('<span class="doc-embed">[图形]</span>')
            elif tag == Q("noBreakHyphen"):
                chunks.append("&#8209;")
            elif tag == Q("softHyphen"):
                chunks.append("&shy;")
        return "".join(chunks)

    def _render_inline(self, element: etree._Element, *, link: str | None = None) -> str:
        """Render runs / ins / del / hyperlink / fields inside a paragraph."""
        pieces: list[str] = []
        for node in element:
            tag = node.tag
            if tag == Q("r"):
                pieces.append(self._render_run(node, deleted=False))
            elif tag == Q("ins"):
                rid = node.get(Q("id"), "")
                inner = "".join(self._render_run(run, deleted=False)
                                for run in node if run.tag == Q("r"))
                if rid:
                    self._record(rid, _text_content(node), "ins")
                if inner.strip():
                    pieces.append(f'<ins class="rev rev-ins" data-rev="{_escape(rid)}"'
                                  f' title="插入（修订）">{inner}</ins>')
            elif tag == Q("del"):
                rid = node.get(Q("id"), "")
                inner = "".join(self._render_run(run, deleted=True)
                                for run in node if run.tag == Q("r"))
                if rid:
                    self._record(rid, _text_content(node), "del")
                if inner.strip():
                    pieces.append(f'<del class="rev rev-del" data-rev="{_escape(rid)}"'
                                  f' title="删除（修订）">{inner}</del>')
            elif tag == Q("hyperlink"):
                rid = node.get(f"{{{R}}}id", "")
                anchor = node.get(Q("anchor"), "")
                href = ""
                if anchor:
                    href = f"#{_escape(anchor)}"
                elif rid and rid in self.relationships:
                    target = self.relationships[rid]
                    if target.startswith("#"):
                        href = _escape(target)
                    else:
                        safe = unquote(target)
                        if safe.lower().startswith(_SAFE_SCHEMES):
                            href = _escape(safe)
                inner = self._render_inline(node)
                if href and inner.strip():
                    pieces.append(f'<a href="{href}">{inner}</a>')
                else:
                    pieces.append(inner)
            elif tag in {Q("bookmarkStart"), Q("bookmarkEnd"), Q("proofErr"),
                         Q("commentRangeStart"), Q("commentRangeEnd"),
                         Q("permStart"), Q("permEnd")}:
                if tag == Q("bookmarkStart"):
                    name = node.get(Q("name"), "")
                    if name and not name.startswith("_") and name not in self.bookmarks:
                        self._bookmark_seq += 1
                        anchor = f"bm-{self._bookmark_seq}"
                        self.bookmarks[name] = anchor
                        pieces.append(f'<a id="{anchor}" class="doc-anchor"></a>')
            elif tag == Q("fldSimple"):
                # Cached field result is what Word displays.
                inner = self._render_inline(node)
                instr = node.get(Q("instr"), "")
                if "TOC" in instr.upper():
                    self.has_toc = True
                pieces.append(inner)
            elif tag == Q("sdt"):
                content = node.find(Q("sdtContent"))
                if content is not None:
                    pieces.append(self._render_inline(content))
            elif tag in {Q("smartTag"), Q("customXml"), Q("moveFrom"), Q("moveTo"),
                         Q("moveFromRangeStart"), Q("moveFromRangeEnd"),
                         Q("moveToRangeStart"), Q("moveToRangeEnd"),
                         Q("alinea"), Q("dir"), Q("bdo")}:
                pieces.append(self._render_inline(node))
            elif tag == Q("fldChar"):
                # Field boundaries: codes are skipped, cached results survive
                # as ordinary runs, so nothing needs to be emitted here.
                continue
        return "".join(pieces)

    # ----- paragraph / block rendering ------------------------------------

    def _paragraph_style(self, paragraph: etree._Element, *, in_table: bool) -> _ParagraphStyle:
        style = _ParagraphStyle(in_table=in_table)
        ppr = paragraph.find(Q("pPr"))
        if ppr is None:
            return style
        pstyle = ppr.find(Q("pStyle"))
        if pstyle is not None:
            sid = pstyle.get(Q("val"), "")
            style.name = self.styles.get(sid, {}).get("name", "") or sid
            outline = self.styles.get(sid, {}).get("outline")
            if outline is not None or sid.upper().startswith("HEADING") or sid.startswith("1") or sid == "2":
                style.heading = True
        jc = ppr.find(Q("jc"))
        if jc is not None:
            style.align = jc.get(Q("val"), "")
        ind = ppr.find(Q("ind"))
        if ind is not None:
            try:
                style.indent_left = int(ind.get(Q("left")) or 0)
            except ValueError:
                style.indent_left = 0
            try:
                style.indent_hanging = int(ind.get(Q("hanging")) or 0)
            except ValueError:
                style.indent_hanging = 0
        return style

    def _render_paragraph(self, paragraph: etree._Element, *, in_table: bool = False) -> str:
        inner = self._render_inline(paragraph)
        if not inner.strip():
            return ""
        style = self._paragraph_style(paragraph, in_table=in_table)
        classes = ["doc-p"]
        if style.heading:
            classes.append("doc-heading")
        if style.name.upper().startswith("TOC") or style.name.startswith("toc"):
            classes.append("doc-toc")
            self.has_toc = True
        attrs = [f'class="{" ".join(classes)}"']
        inline: list[str] = []
        if style.align in {"center", "right", "both", "justify"}:
            inline.append(f"text-align:{'justify' if style.align == 'both' else style.align}")
        if style.indent_left:
            inline.append(f"padding-left:{style.indent_left / 20:.1f}pt")
        if style.indent_hanging:
            inline.append(f"text-indent:-{style.indent_hanging / 20:.1f}pt")
        if inline:
            attrs.append(f'style="{";".join(inline)}"')
        return f'<p {" ".join(attrs)}>{inner}</p>'

    def _render_table(self, table: etree._Element) -> str:
        rows: list[str] = []
        for tr in table.findall(Q("tr")):
            cells: list[str] = []
            for tc in tr.findall(Q("tc")):
                grid = tc.find(Q("tcPr") + "/" + Q("gridSpan")) if tc.find(Q("tcPr")) is not None else None
                span = ""
                if grid is not None:
                    try:
                        count = int(grid.get(Q("val")) or 1)
                        if count > 1:
                            span = f' colspan="{count}"'
                    except ValueError:
                        span = ""
                body = self._render_block_children(tc, in_table=True)
                cells.append(f"<td{span}>{body}</td>")
            if cells:
                rows.append("<tr>" + "".join(cells) + "</tr>")
        if not rows:
            return ""
        return '<table class="doc-tbl">' + "".join(rows) + "</table>"

    def _render_block_children(self, container: etree._Element, *, in_table: bool = False) -> str:
        pieces: list[str] = []
        for element in container:
            tag = element.tag
            if tag == Q("p"):
                piece = self._render_paragraph(element, in_table=in_table)
                if piece:
                    pieces.append(piece)
            elif tag == Q("tbl"):
                piece = self._render_table(element)
                if piece:
                    pieces.append(piece)
            elif tag == Q("sdt"):
                content = element.find(Q("sdtContent"))
                if content is not None:
                    pieces.append(self._render_block_children(content, in_table=in_table))
            elif tag in {Q("customXml"), Q("smartTag"), Q("moveFrom"), Q("moveTo"),
                         Q("ins"), Q("del")}:
                # Block-level revision wrappers / containers: descend.
                pieces.append(self._render_block_children(element, in_table=in_table))
            elif tag == Q("sectPr"):
                self.page_count += 1
                pieces.append('<hr class="page-break-line">')
        return "".join(pieces)

    # ----- public API -----------------------------------------------------

    def render(self, *, report: Mapping[str, Any] | None = None) -> dict[str, Any]:
        body = self.root.find(Q("body"))
        if body is None:
            raise DocxError("BODY_MISSING")
        html = self._render_block_children(body)
        manifest_map = self._manifest_index(report)
        revisions = self._pair_revisions(manifest_map)
        return {
            "html": html,
            "revisions": revisions,
            "meta": {
                "pages": self.page_count,
                "has_toc": self.has_toc,
                "revision_count": len(revisions),
                "bookmarks": len(self.bookmarks),
            },
        }

    def _manifest_index(self, report: Mapping[str, Any] | None) -> dict[int, dict[str, Any]]:
        """Map ins_id/del_id → business edit info.

        ``generate_artifacts`` assigns revision ids deterministically: after
        sorting edits by ``(location, -start)`` the n-th edit gets
        ``del_id = 2n-1`` / ``ins_id = 2n``. Reports persist the *plan* (with
        ``rule_id``/``location``/``start``) but not the manifest, so we rebuild
        the same numbering here. If a manifest is present (evaluation reports
        may carry one) it wins, because it is the authoritative record.
        """
        index: dict[int, dict[str, Any]] = {}
        if not report:
            return index
        manifest = report.get("revision_manifest") if isinstance(report, Mapping) else None
        if isinstance(manifest, list) and manifest:
            for item in manifest:
                if not isinstance(item, Mapping):
                    continue
                info = _edit_info(item)
                for key in ("ins_id", "del_id"):
                    number = _as_int(item.get(key))
                    if number is not None:
                        index[number] = info
            return index
        plan = report.get("plan") if isinstance(report, Mapping) else None
        edits = plan.get("edits") if isinstance(plan, Mapping) else None
        if not isinstance(edits, list):
            return index
        ordered = [e for e in edits if isinstance(e, Mapping)]
        try:
            ordered.sort(key=lambda e: (str(e.get("location", "")), -int(e.get("start") or 0)))
        except (TypeError, ValueError):
            pass
        for number, edit in enumerate(ordered, start=1):
            index[2 * number - 1] = dict(_edit_info(edit), del_id=2 * number - 1, ins_id=2 * number)
            index[2 * number] = index[2 * number - 1]
        return index

    def _pair_revisions(self, manifest: Mapping[int, Mapping[str, Any]]) -> list[dict[str, Any]]:
        by_id = {int(k): v for k, v in self.revisions.items() if str(k).isdigit()}
        result: list[dict[str, Any]] = []
        for rid in sorted(by_id):
            if rid % 2 == 0 and (rid - 1) in by_id:
                continue  # already emitted as part of the odd/even pair
            entry = by_id.get(rid, {})
            ins_entry = by_id.get(rid + 1, {}) if rid % 2 == 1 else {}
            del_entry = entry if rid % 2 == 1 else by_id.get(rid - 1, {})
            pair_ids = sorted({i for i in (rid, rid + 1) if i in by_id})
            info: Mapping[str, Any] = {}
            for candidate in pair_ids:
                if candidate in manifest:
                    info = manifest[candidate]
                    break
            before = "".join(del_entry.get("del", []))
            after = "".join(ins_entry.get("ins", []))
            operation = info.get("operation") or ""
            if not operation:
                operation = "delete" if not after else ("insert" if not before else "replace")
            result.append({
                "index": len(result) + 1,
                "del_id": rid,
                "ins_id": rid + 1,
                "revision_ids": pair_ids,
                "before": before,
                "after": after,
                "operation": operation,
                "edit_id": info.get("edit_id", ""),
                "rule_id": info.get("rule_id", ""),
                "section": info.get("section", ""),
                "location": info.get("location", ""),
                "expected_old_text": info.get("expected_old_text", ""),
                "replacement": info.get("replacement", ""),
                "mapped": bool(info),
            })
        return result


def _edit_info(edit: Mapping[str, Any]) -> dict[str, Any]:
    """Business-facing fields shared by plan edits and manifest entries."""
    components = edit.get("components")
    expected = edit.get("expected_old_text", "")
    if not expected and isinstance(components, list):
        expected = "".join(str(c.get("expected_old_text", ""))
                           for c in components if isinstance(c, Mapping))
    return {
        "edit_id": edit.get("edit_id") or "",
        "rule_id": edit.get("rule_id", ""),
        "location": edit.get("location", ""),
        "section": edit.get("section", ""),
        "operation": edit.get("operation", ""),
        "expected_old_text": expected,
        "replacement": edit.get("replacement", ""),
    }


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def project_docx(path: str | Path, *, report: Mapping[str, Any] | None = None,
                 limits: ZipLimits | None = None) -> dict[str, Any]:
    """Project a revision DOCX into reviewable HTML plus its revision list.

    Stored artifacts keep their original upload name and may lack a ``.docx``
    suffix, while :func:`fundlex.docx._read_parts` deliberately rejects
    non-``.docx`` inputs (an upload-validation guard). Stage such files through
    a temporary ``.docx`` path so the read still applies every package limit.
    """
    limits = limits or ZipLimits()
    path = Path(path)
    if path.suffix.lower() == ".docx":
        parts = _read_parts(path, limits)
    else:
        with NamedTemporaryFile(prefix=".fundlex-view-", suffix=".docx", delete=False) as temp:
            temporary = Path(temp.name)
            temp.write(path.read_bytes())
        try:
            parts = _read_parts(temporary, limits)
        finally:
            temporary.unlink(missing_ok=True)
    projection = HtmlProjection(parts, limits)
    return projection.render(report=report)
