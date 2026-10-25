"""Read-only Word formatting for the Compare HTML projection.

All coordinates continue to address the parser's visible text. Formatting and
list labels never enter alignment or diff spans. This is a continuous reading
view, not a Word pagination engine.
"""
from __future__ import annotations

import re
from typing import Mapping

from ..docx import Q, ZipLimits, _xml
from .models import CompareRun


def value(node, name="val", default=""):
    return node.get(Q(name), default) if node is not None else default


def number(raw, divisor=1, minimum=-10000, maximum=10000):
    try:
        result = float(raw) / divisor
        return result if minimum <= result <= maximum else None
    except (ValueError, TypeError):
        return None


def points(raw, divisor=20):
    result = number(raw, divisor)
    return f"{result:g}pt" if result is not None else ""


def text_of(element):
    out = []
    for node in element.iter():
        if node.tag in {Q("t"), Q("delText")}:
            out.append(node.text or "")
        elif node.tag in {Q("br"), Q("cr")}:
            out.append("\n")
        elif node.tag == Q("tab"):
            out.append("\t")
        elif node.tag == Q("noBreakHyphen"):
            out.append("\u2011")
    return "".join(out)


def properties(node):
    return {child.tag: dict(child.attrib) for child in node} if node is not None else {}


def merge(*groups):
    result = {}
    for group in groups:
        for tag, attrs in group.items():
            result[tag] = {**result.get(tag, {}), **attrs}
    return result


class Presentation:
    def __init__(self, parts: Mapping[str, bytes], limits: ZipLimits):
        self.styles = {}
        self.cache = {}
        self.default_paragraph = ""
        self.defaults = {"pPr": {}, "rPr": {}}
        if "word/styles.xml" in parts:
            root = _xml(parts["word/styles.xml"], limits)
            for kind in self.defaults:
                self.defaults[kind] = properties(root.find(f"{Q('docDefaults')}/{Q(kind + 'Default')}/{Q(kind)}"))
            for style in root.findall(Q("style")):
                self.styles[value(style, "styleId")] = style
                if value(style, "type") == "paragraph" and value(style, "default") in {"1", "true"}:
                    self.default_paragraph = value(style, "styleId")
        self.nums = {}
        self.abstracts = {}
        self.counters = {}
        if "word/numbering.xml" in parts:
            root = _xml(parts["word/numbering.xml"], limits)
            self.nums = {value(node, "numId"): node for node in root.findall(Q("num"))}
            self.abstracts = {value(node, "abstractNumId"): node for node in root.findall(Q("abstractNum"))}

    def style(self, style_id, kind, trail=()):
        key = (style_id, kind)
        if key in self.cache:
            return self.cache[key]
        node = self.styles.get(style_id)
        if node is None or style_id in trail or len(trail) >= 32:
            return {}
        parent = value(node.find(Q("basedOn")))
        result = merge(self.style(parent, kind, (*trail, style_id)), properties(node.find(Q(kind))))
        self.cache[key] = result
        return result

    def paragraph(self, paragraph):
        direct = paragraph.find(Q("pPr"))
        style_id = value(direct.find(Q("pStyle"))) if direct is not None else ""
        style_id = style_id or self.default_paragraph
        ppr = merge(self.defaults["pPr"], self.style(style_id, "pPr"), properties(direct))
        # numPr needs its children, not just its attributes.
        num_id = level = ""
        chain = []
        current = style_id
        while current and current not in chain and len(chain) < 32:
            chain.append(current)
            node = self.styles.get(current)
            current = value(node.find(Q("basedOn"))) if node is not None else ""
        style_sources = []
        for sid in reversed(chain):
            node = self.styles.get(sid)
            if node is not None:
                style_sources.append(node.find(Q("pPr")))
        for source in [*style_sources, direct]:
            num = source.find(Q("numPr")) if source is not None else None
            if num is not None:
                num_id = value(num.find(Q("numId")), default=num_id)
                level = value(num.find(Q("ilvl")), default=level)
        fmt = {}
        def attr(tag, name="val"):
            return ppr.get(Q(tag), {}).get(Q(name), "")
        align = {"both": "justify", "distribute": "justify", "left": "left", "right": "right", "center": "center", "start": "start", "end": "end"}.get(attr("jc"))
        if align:
            fmt["text-align"] = align
        for word, css in (("left", "margin-left"), ("right", "margin-right"), ("firstLine", "text-indent")):
            raw = attr("ind", word)
            if points(raw):
                fmt[css] = points(raw)
        if points(attr("ind", "hanging")):
            fmt["text-indent"] = points(-float(attr("ind", "hanging")))
        for word, css in (("before", "margin-top"), ("after", "margin-bottom")):
            if points(attr("spacing", word)):
                fmt[css] = points(attr("spacing", word))
        line = attr("spacing", "line")
        if line:
            n = number(line, 240, 0.2, 10) if attr("spacing", "lineRule") in {"", "auto"} else None
            if n is not None:
                fmt["line-height"] = f"{n:g}"
            elif points(line):
                fmt["line-height"] = points(line)
        outline = number(attr("outlineLvl"), minimum=0, maximum=5)
        if outline is not None:
            fmt["heading-level"] = str(int(outline) + 1)
        if attr("pageBreakBefore") not in {"", "0", "false", "off"} or Q("pageBreakBefore") in ppr and not attr("pageBreakBefore"):
            fmt["break-before"] = "page"
        label, list_ppr = self.label(num_id, level or "0")
        if label:
            fmt["list-label"] = label
            for word, css in (("left", "margin-left"), ("hanging", "text-indent")):
                raw = list_ppr.get(Q("ind"), {}).get(Q(word), "")
                if css not in fmt and points(raw):
                    fmt[css] = points(-float(raw) if word == "hanging" else raw)
        return tuple(fmt.items()), merge(self.defaults["rPr"], self.style(style_id, "rPr"))

    def runs(self, paragraph, base):
        result = []
        offset = 0
        for run in paragraph.iter(Q("r")):
            text = text_of(run)
            if not text:
                continue
            direct = run.find(Q("rPr"))
            run_style = value(direct.find(Q("rStyle"))) if direct is not None else ""
            props = merge(base, self.style(run_style, "rPr"), properties(direct))
            def attr(tag, name="val"):
                return props.get(Q(tag), {}).get(Q(name), "")
            def enabled(tag):
                return Q(tag) in props and attr(tag) not in {"0", "false", "off", "none"}
            color = attr("color")
            fonts = props.get(Q("rFonts"), {})
            names = [fonts.get(Q(name), "") for name in ("eastAsia", "ascii", "hAnsi")]
            family = ", ".join(dict.fromkeys(f'"{name}"' for name in names if name and re.fullmatch(r"[\w .()\-]{1,80}", name)))
            result.append(CompareRun(
                text, offset, offset + len(text), enabled("b"), enabled("i"), enabled("u"), enabled("strike"),
                f"#{color}" if re.fullmatch(r"[0-9a-fA-F]{6}", color) else "",
                points(attr("sz"), 2), family,
                {"superscript": "super", "subscript": "sub"}.get(attr("vertAlign"), ""),
            ))
            offset += len(text)
        return tuple(result) if text_of(paragraph) == "".join(run.text for run in result) else ()

    def label(self, num_id, raw_level):
        num = self.nums.get(num_id)
        if num is None or num_id == "0":
            return "", {}
        level = int(number(raw_level, minimum=0, maximum=8) or 0)
        abstract = self.abstracts.get(value(num.find(Q("abstractNumId"))))
        if abstract is None:
            return "", {}
        levels = {int(value(node, "ilvl", "0")): node for node in abstract.findall(Q("lvl")) if value(node, "ilvl", "0").isdigit()}
        overrides = {int(value(node, "ilvl", "0")): node for node in num.findall(Q("lvlOverride")) if value(node, "ilvl", "0").isdigit()}
        override = overrides.get(level)
        lvl = override.find(Q("lvl")) if override is not None else None
        if lvl is None:
            lvl = levels.get(level)
        if lvl is None:
            return "", {}
        start = value(override.find(Q("startOverride"))) if override is not None else ""
        start = int(number(start or value(lvl.find(Q("start")), default="1"), minimum=0, maximum=100000) or 1)
        counters = self.counters.setdefault(num_id, {})
        counters[level] = counters.get(level, start - 1) + 1
        for deeper in list(counters):
            if deeper > level:
                del counters[deeper]
        template = value(lvl.find(Q("lvlText")))
        if value(lvl.find(Q("numFmt"))) == "bullet":
            # Word symbol fonts frequently store private-use bullet glyphs.
            return (template if template and not any(0xE000 <= ord(c) <= 0xF8FF for c in template) else "•"), properties(lvl.find(Q("pPr")))
        def replacement(match):
            index = int(match.group(1)) - 1
            definition = levels.get(index)
            count = counters.get(index, int(number(value(definition.find(Q("start")), default="1") if definition is not None else "1", minimum=0) or 1))
            kind = value(definition.find(Q("numFmt"))) if definition is not None else "decimal"
            if kind in {"lowerLetter", "upperLetter"} and count > 0:
                chars = ""
                while count:
                    count, digit = divmod(count - 1, 26)
                    chars = chr(97 + digit) + chars
                return chars.upper() if kind == "upperLetter" else chars
            if kind in {"lowerRoman", "upperRoman"} and 0 < count < 4000:
                roman = ""
                for n, symbol in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
                    while count >= n:
                        roman += symbol
                        count -= n
                return roman.lower() if kind == "lowerRoman" else roman
            return str(count)
        return re.sub(r"%([1-9])", replacement, template), properties(lvl.find(Q("pPr")))

    @staticmethod
    def page(body):
        section = body.find(Q("sectPr"))
        if section is None:
            return ()
        size = section.find(Q("pgSz"))
        margins = section.find(Q("pgMar"))
        width = number(value(size, "w"), minimum=1000, maximum=40000)
        fmt = {}
        if width:
            fmt["max-width"] = points(width)
        for side in ("left", "right"):
            margin = number(value(margins, side), minimum=0, maximum=10000)
            if width and margin is not None and margin < width / 2:
                fmt[f"padding-{side}"] = f"{margin / width * 100:g}%"
        for side in ("top", "bottom"):
            margin = number(value(margins, side), minimum=0, maximum=10000)
            if margin is not None:
                fmt[f"padding-{side}"] = points(value(margins, side))
        return tuple(fmt.items())
