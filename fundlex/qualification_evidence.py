"""Select locatable current-contract qualification evidence without name inference."""

from __future__ import annotations

import re
from typing import Any, Sequence


class QualificationEvidenceError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _body(span: Any) -> bool:
    return (span.zone == "body" and bool(span.segments)
            and not getattr(span, "reasons", ())
            and "摘要" not in span.section_path
            and getattr(span, "logical_zone", None) not in {"summary", "toc"})


_CHAPTER = re.compile(
    r"^(?:第[一二三四五六七八九十百零〇\d]+(?:部分|章|节)|"
    r"[一二三四五六七八九十百零〇]+[、.]|\d+(?:\.\d+)+[、.]?)([^\d.。；：:]{2,50})$"
)
_SECTIONS = {
    "前言", "释义", "前言和释义", "绪言", "基金的基本情况", "基金的投资",
    "基金的历史沿革", "基金的存续", "基金的募集", "基金份额的发售", "基金备案",
    "基金合同的生效", "基金份额的申购与赎回", "基金份额的申购和赎回",
    "基金份额的申购、赎回与转换",
    "基金合同当事人及权利义务", "基金份额持有人大会",
    "基金管理人、基金托管人的更换条件和程序", "基金的托管",
    "基金份额的登记", "基金份额的注册登记", "基金的财产", "基金资产估值",
    "基金的费用与税收", "基金的收益与分配", "基金的会计与审计", "基金的信息披露",
    "基金合同的变更、终止与基金财产的清算", "违约责任",
    "争议的处理和适用的法律", "基金合同的效力", "其他事项", "基金合同摘要",
    "基金合同内容摘要", "内容摘要", "合同当事人盖章及法定代表人签字、签约地、签订日",
}


def section_spans(paragraphs: Sequence[Any], title: str) -> tuple[Any, ...]:
    """Select a body section, including plain numbered headings lost by projection.

    Only an entire chapter heading establishes fallback scope. Directory entries
    with leaders/page numbers, sentences mentioning a chapter, and summary
    headings cannot establish it. Any following chapter ends fallback scope.
    """
    selected = []
    active = False
    summary = False
    explicit_section = False
    numeric_depth = None
    for span in paragraphs:
        text = _compact(span.text)
        # Projection barriers can make a bookmarked pure heading read-only.
        # Use its already classified section metadata only when it exactly
        # matches the whole visible heading; never remove barriers from facts.
        metadata_heading = ("\ufff9" in text and span.zone == "body"
                            and not getattr(span, "reasons", ())
                            and getattr(span, "logical_zone", None) not in {"summary", "toc"}
                            and "摘要" not in span.section_path
                            and text.replace("\ufff9", "") == _compact(span.section_path))
        if metadata_heading:
            text = text.replace("\ufff9", "")
        heading = _CHAPTER.fullmatch(text)
        # Plain numbered investment subheadings (e.g. 一、投资目标) are
        # nested clauses, rather than new contract sections.
        explicit_chapter = bool(re.match(r"^第[一二三四五六七八九十百零〇\d]+(?:部分|章)", text))
        number = re.match(r"^(\d+(?:\.\d+)+)", text)
        depth = len(number.group(1).split(".")) if number else None
        same_numeric_level = (numeric_depth is not None and depth is not None
                              and depth <= numeric_depth)
        if heading and (heading.group(1) in _SECTIONS or explicit_chapter or same_numeric_level):
            chapter = heading.group(1)
            summary = summary or "摘要" in chapter
            explicit_section = True
            active = chapter == title and not summary and (_body(span) or metadata_heading)
            numeric_depth = depth if active else None
        if not _body(span) or summary:
            continue
        # A recognized path must be an actual section component, never a
        # sentence merely containing the requested section's name.
        components = re.split(r"[/›>｜|]", span.section_path)
        known = any(_compact(p) == title or
                    (m := _CHAPTER.fullmatch(_compact(p))) and m.group(1) == title
                    for p in components)
        if active or (known and not explicit_section):
            selected.append(span)
    return tuple(selected)


def investment_spans(paragraphs: Sequence[Any]) -> tuple[Any, ...]:
    return section_spans(paragraphs, "基金的投资")


def basic_spans(paragraphs: Sequence[Any]) -> tuple[Any, ...]:
    return section_spans(paragraphs, "基金的基本情况")


_VALUE = re.compile(
    r"^(?:(?:股票型|债券型|混合型|指数型|货币型|货币市场)"
    r"(?:[、，,](?:股票型|债券型|混合型|指数型))*(?:证券投资基金|基金)?|"
    r"(?:股票型|债券型|混合型|指数型)?(?:ETF联接基金|联接基金)|"
    r"交易型开放式(?:指数)?(?:证券投资)?基金联接基金|"
    r"(?:股票型|债券型|混合型|指数型)?基金中基金(?:[（(]FOF[）)])?|FOF|"
    r"[\u4e00-\u9fff]{0,6}交易型开放式(?:指数)?(?:证券投资)?基金|"
    r"同业存单(?:指数)?(?:证券投资)?基金|"
    r"中国证监会认可的其他基金(?:或基金份额)?)[。；;]?$", re.IGNORECASE
)
_LABEL = re.compile(r"^(?:(?:[（(]?[一二三四五六七八九十\d]+[）)、.])?)(?:本)?基金的(?:类别|类型)[：:]?(.*)$")
_NUMBERED_FIELD = re.compile(
    r"(?:[（(][一二三四五六七八九十\d]+[）)]|[一二三四五六七八九十\d]+[、.])"
    r"(?:本)?基金的(?:名称|类别|类型|运作方式|投资目标|最低募集份额总额|存续期限|份额类别)[：:]?"
)


def _category_clauses(text: str) -> tuple[tuple[str, int], ...]:
    """Read numbered basic fields without treating narrative text as a boundary."""
    fields = list(_NUMBERED_FIELD.finditer(text))
    clauses = []
    # The first field can be unnumbered; subsequent boundaries require both
    # an explicit number and a recognized basic field label.
    first_end = fields[0].start() if fields else len(text)
    if first_end and _LABEL.fullmatch(text[:first_end]):
        clauses.append((text[:first_end], 0))
    for index, field in enumerate(fields):
        end = fields[index + 1].start() if index + 1 < len(fields) else len(text)
        clause = text[field.start():end]
        if _LABEL.fullmatch(clause):
            clauses.append((clause, field.start()))
    return tuple(clauses)


def category_value(paragraphs: Sequence[Any]) -> tuple[str, Any, int] | None:
    """Return the literal category value; reject disagreeing current body clauses."""
    scope = {id(p) for p in basic_spans(paragraphs)}
    found: list[tuple[str, Any, int]] = []
    unresolved = False
    for index, span in enumerate(paragraphs):
        if id(span) not in scope:
            continue
        for clause, clause_start in _category_clauses(_compact(span.text)):
            label = _LABEL.fullmatch(clause)
            value = label.group(1)
            source = span
            value_start = clause_start + label.start(1)
            if not value:
                # Adjacent blank paragraphs may intervene; another field cannot.
                for following in paragraphs[index + 1:index + 3]:
                    if id(following) not in scope:
                        break
                    value = _compact(following.text)
                    if value:
                        boundary = _NUMBERED_FIELD.search(value)
                        if boundary:
                            value = value[:boundary.start()]
                        source = following
                        value_start = 0
                        break
            if not _VALUE.fullmatch(value):
                unresolved = True
                continue
            positions = [i for i, c in enumerate(source.text) if not c.isspace()]
            at = value_start
            quote = source.text[positions[at]:positions[at + len(value) - 1] + 1]
            found.append((quote, source, index))
    if not found:
        return None
    if unresolved:
        raise QualificationEvidenceError("FUND_TYPE_EVIDENCE_AMBIGUOUS")
    normalized = {_compact(q).rstrip("。；;") for q, _, _ in found}
    if len(normalized) != 1:
        raise QualificationEvidenceError("FUND_TYPE_EVIDENCE_CONFLICT")
    return found[0]
