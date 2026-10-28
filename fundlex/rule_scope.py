"""Deterministic rule scopes resolved to physical leaf subsections.

The recall engine historically mapped a rule to a whole ``Section`` such as
``第三部分基金的基本情况``.  Several rules only apply to one clause inside that
chapter, so a section-level scope admits unrelated sibling clauses (the D06
``p280`` conversion sentence is the canonical example).

This module builds a *leaf* tree inside every inspected section and resolves a
rule to the smallest physical leaf set that its explicit policy supports.  A
business clause can legitimately repeat across sibling leaves (景宁's
``基金份额类别设置`` and ``基金份额的类别``); such leaves are merged only when
they share the parent body section and the same class/fee title word family.  It
is deliberately independent of :mod:`fundlex.recall`: callers pass the existing
``Section`` objects and ``scope_map`` mapping, and receive plain dataclasses.

Design rules:

* A rule never falls back to the whole document.  The widest accepted fallback
  is the mapped base section's own leaves (``section_fallback``).
* Summary paragraphs are copies, not extra business sites.  They are included
  only through an explicit ``copy_key`` policy; a generic summary chapter title
  never authorises a copy.
* A missing target returns ``resolution="unresolved"`` with empty locations.
  Resolution never raises for contract-specific structure; callers decide
  whether an unresolved rule fails the run.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from .docx import BARRIER

__all__ = [
    "LeafSection",
    "RuleScope",
    "build_leaf_sections",
    "resolve_rule_scopes",
    "scope_locations",
    "scope_locations_for_window",
]

_READABLE_ZONES = frozenset({"body", "summary"})


@dataclass(frozen=True)
class LeafSection:
    """One physical clause/site inside a :class:`fundlex.recall.Section`."""

    id: str
    parent_section_id: str
    title: str
    zone: str
    heading_level: int
    locations: tuple[str, ...]
    summary_of: str = ""
    copy_key: str = ""


@dataclass(frozen=True)
class RuleScope:
    """The physical locations one guide rule may inspect and edit."""

    rule_id: str
    leaf_ids: frozenset[str]
    locations: frozenset[str]
    zone: str
    include_summary_copies: bool
    copy_keys: frozenset[str]
    resolution: str
    evidence: tuple[str, ...]

    def contains(self, location: str) -> bool:
        return str(location) in self.locations

    def as_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "leaf_ids": sorted(self.leaf_ids),
            "locations": sorted(self.locations, key=_location_sort_key),
            "location_count": len(self.locations),
            "zone": self.zone,
            "include_summary_copies": self.include_summary_copies,
            "copy_keys": sorted(self.copy_keys),
            "resolution": self.resolution,
            "evidence": list(self.evidence),
        }


# ---------------------------------------------------------------------------
# Text and heading helpers
# ---------------------------------------------------------------------------

_CN_NUMBER = "一二三四五六七八九十百零〇"
_CN_HEADING_RE = re.compile(rf"^([{_CN_NUMBER}]+)、(.+)$")
_ARABIC_HEADING_RE = re.compile(r"^(\d{1,3})[、.](.+)$")
_PAREN_HEADING_RE = re.compile(rf"^\(([{_CN_NUMBER}\d]{{1,4}})\)(.+)$")
_CLASS_LABEL_RE = re.compile(r"([A-Z])类")
_CLASS_FEE_TITLE_RE = re.compile(r"^[A-Z]类(?:基金)?份额(?:的)?销售服务费$")
_SENTENCE_SPLIT_RE = re.compile(r"[。；;，,：:]")
_TRAILING_NUMBER_RE = re.compile(r"\d+[、.].*$")

# Known business short titles.  Values are the clause identity used for audit;
# they are intentionally narrower than recap chapter titles.
_KNOWN_TITLES: dict[str, str] = {
    "基金份额类别设置": "份额类别",
    "份额类别设置": "份额类别",
    "基金份额类别": "份额类别",
    "基金份额的类别": "份额类别",
    "基金销售服务费": "销售服务费",
    "销售服务费": "销售服务费",
    "基金收益分配原则": "收益分配",
    "收益分配原则": "收益分配",
    "基金利润的构成": "收益分配利润",
    "基金可供分配利润": "收益分配利润",
    "收益分配方案": "收益分配方案",
    "收益分配方案的确定、公告与实施": "收益分配方案",
    "基金收益分配中发生的费用": "收益分配费用",
    "基金财产清算剩余资产的分配": "清算剩余资产",
    "清算剩余资产的分配": "清算剩余资产",
    "基金财产清算的公告": "清算公告",
    "基金财产清算账册及文件的保存": "清算账册",
    "清算费用": "清算费用",
    "基金财产的清算": "清算",
    "申购和赎回的价格、费用及其用途": "申购赎回价格费用用途",
    "申购与赎回的价格、费用及其用途": "申购赎回价格费用用途",
    "基金费用的种类": "基金费用种类",
    "基金费用计提方法、计提标准和支付方式": "基金费用计提",
    "基金的收益与分配": "收益分配",
    "基金的申购与赎回": "申购赎回",
}


def _visible(value: Any) -> str:
    return str(value or "").replace(BARRIER, "")


def _nfkc(value: Any) -> str:
    return unicodedata.normalize("NFKC", _visible(value))


def _compact(value: Any) -> str:
    return re.sub(r"\s+", "", _nfkc(value))


def _span_zone(span: Any) -> str:
    return str(getattr(span, "logical_zone", None) or getattr(span, "zone", "body"))


def _section_title(section: Any) -> str:
    return _visible(getattr(section, "title", "")).strip()


def _known_title_key(title: str) -> str:
    compact = _compact(title)
    key = _KNOWN_TITLES.get(compact, "")
    if key:
        return key
    # Contracts commonly title the fee sub-clause as
    # ``3、C类基金份额的销售服务费``.  The class prefix is part of the same
    # business clause, so recognise it without treating the neighbouring
    # ``3、从C类基金份额的基金财产中计提的销售服务费；`` list item as a heading.
    if _CLASS_FEE_TITLE_RE.fullmatch(compact):
        return "销售服务费"
    return ""


def _heading_title(raw: str) -> str:
    """Trim body text that is glued onto a heading paragraph.

    Contract paragraphs often merge ``二、基金的费用`` and the first sentence in
    one OOXML paragraph.  Cutting at sentence punctuation (never at ``、``, which
    is part of real headings) keeps the heading identity stable while preserving
    the original location as the leaf start.
    """

    title = _SENTENCE_SPLIT_RE.split(raw, maxsplit=1)[0]
    title = _TRAILING_NUMBER_RE.sub("", title)
    return title.strip("、.。；;，,：: ").strip()[:80]


_PLAIN_SALES_FEE_TITLES = frozenset({"销售服务费", "基金销售服务费"})


def _is_sales_fee_heading(value: Any) -> bool:
    """Recognise a sales-service-fee clause heading without a fixed prefix.

    Contracts title the same clause as ``3、C类基金份额的销售服务费``,
    ``3、销售服务费的计提与支付`` or ``3、服务费``.  The length/leading-word
    guard keeps fee-types list items such as
    ``3、从C类基金份额的基金财产中计提的销售服务费；`` inside their parent
    leaf instead of promoting them to a heading.
    """

    compact = _compact(value)
    if not compact or len(compact) > 20:
        return False
    if compact.startswith(("从", "在", "按", "由", "于")):
        return False
    # Sentence-shaped list items ("销售服务费由基金管理人收取", "销售服务费
    # 在基金财产中列支") are fee-types content, not clause headings.
    if any(token in compact for token in ("从", "在", "按", "由", "于", "每", "为")):
        return False
    return "销售服务费" in compact or "服务费" in compact


def _is_sales_fee_subheading(value: Any) -> bool:
    """True for a class-prefixed/calculation sub-item of a plain fee heading."""

    compact = _compact(value)
    if compact in _PLAIN_SALES_FEE_TITLES:
        return False
    return bool(_CLASS_FEE_TITLE_RE.fullmatch(compact)) or _is_sales_fee_heading(compact)


def _heading_for(text: Any, section_title: str) -> tuple[str, int] | None:
    """Return ``(title, level)`` when a paragraph starts a leaf heading."""

    compact = _compact(text)
    if not compact:
        return None
    match = _CN_HEADING_RE.match(compact)
    if match:
        return _heading_title(match.group(2)), 2
    match = _ARABIC_HEADING_RE.match(compact)
    if match:
        title = _heading_title(match.group(2))
        # Nested fee/definition numbering is only a leaf when it names a known
        # business clause.  Otherwise it must stay inside its parent leaf (e.g.
        # the per-class ``(1) C类基金份额的销售服务费`` subparagraphs).
        if (_known_title_key(title) or _is_sales_fee_heading(title)
                or _is_glossary_title(section_title)):
            return title, 3
        return None
    match = _PAREN_HEADING_RE.match(compact)
    if match:
        title = _heading_title(match.group(2))
        if _known_title_key(title) or _is_sales_fee_heading(title):
            return title, 3
        return None
    if _known_title_key(compact):
        return compact, 3
    return None


def _is_glossary_title(value: Any) -> bool:
    return "释义" in _compact(value)


def _is_fee_tax_section(value: Any) -> bool:
    """Accept the fee word family, not only titles that also say 税收.

    Real contracts title the chapter ``基金费用``, ``基金的费用`` or
    ``基金费用与税收``.  Requiring both 费用 and 税收 dropped the plain
    ``基金费用`` chapter before its leaves were ever inspected.
    """

    compact = _compact(value)
    return "费用" in compact or "销售服务费" in compact


def _is_income_section(value: Any) -> bool:
    compact = _compact(value)
    return "收益" in compact and "分配" in compact


def _is_liquidation_section(value: Any) -> bool:
    compact = _compact(value)
    return "清算" in compact and ("基金财产" in compact or "财产的清算" in compact)


def _is_basic_info_section(value: Any) -> bool:
    return "基本情况" in _compact(value)


def _is_purchase_section(value: Any) -> bool:
    compact = _compact(value)
    return "申购" in compact and "赎回" in compact


def _is_class_definition(text: Any) -> bool:
    compact = _compact(text)
    if not compact:
        return False
    if "基金份额类别" not in compact and "将基金份额分为" not in compact:
        return False
    labels = set(_CLASS_LABEL_RE.findall(compact))
    if len(labels) < 2:
        return False
    return any(token in compact for token in
               ("申购费", "认购费", "销售服务费", "不计提", "收取"))


_CLASS_SETUP_TOKENS = (
    "基金份额类别",
    "份额类别",
    "将基金份额分为",
    "份额分类",
    "增加新的基金份额类别",
    "变更现有基金份额类别",
    "停止现有基金份额类别",
    "调低赎回费率",
    "变更收费方式",
    "调整前基金管理人",
)


def _is_class_setup_text(text: Any) -> bool:
    """True when a leaf carries the share-class setup/fee-adjustment clause."""

    compact = _compact(text)
    return bool(compact) and any(token in compact for token in _CLASS_SETUP_TOKENS)


def _title_copy_key(title: Any) -> str:
    """Return a stable clause key from the normalised title word family.

    Titles such as ``基金份额的类别`` and ``基金份额类别设置`` describe the
    same business clause but share no fixed token; ``基金费用的种类`` must not
    become ``销售服务费`` merely because the fee list mentions it.  Title keys
    therefore use the clause word family and always win over body tokens.
    """

    compact = _compact(title)
    if not compact:
        return ""
    exact = _KNOWN_TITLES.get(compact, "")
    if exact:
        return exact
    # General fee clauses win over a service-fee mention in the same title:
    # ``基金费用的种类（含销售服务费）`` is a fee-types list, not the service
    # fee clause.
    if "基金费用" in compact and "种类" in compact:
        return "基金费用种类"
    if "基金费用" in compact and ("计提" in compact or "支付" in compact):
        return "基金费用计提"
    if "费用" in compact and "调整" in compact:
        return "费用调整"
    if "不列入" in compact and "费用" in compact:
        return "不列入基金费用"
    if compact == "税收" or "基金税收" in compact:
        return "基金税收"
    if "清算" in compact and "费用" in compact:
        return "清算费用"
    if _CLASS_FEE_TITLE_RE.fullmatch(compact) or _is_sales_fee_heading(compact):
        return "销售服务费"
    for tokens, key in (
        (("收益分配中发生的费用",), "收益分配费用"),
        (("收益分配方案",), "收益分配方案"),
        (("收益分配原则",), "收益分配"),
        (("利润的构成", "可供分配利润"), "收益分配利润"),
        (("清算剩余资产",), "清算剩余资产"),
        (("申购和赎回的价格", "申购与赎回的价格"), "申购赎回价格费用用途"),
        (("销售服务费",), "销售服务费"),
    ):
        if any(token in compact for token in tokens):
            return key
    if "份额" in compact and ("类别" in compact or "分类" in compact):
        return "份额类别"
    return ""



def _content_copy_key(content: Any) -> str:
    """Bounded fallback for compact clauses whose title carries no identity."""

    text = _compact(content)[:400]
    if not text:
        return ""
    for tokens, key in (
        (("销售服务费",), "销售服务费"),
        (("清算剩余资产",), "清算剩余资产"),
        (("收益分配中发生的费用",), "收益分配费用"),
        (("收益分配方案",), "收益分配方案"),
        (("收益分配原则",), "收益分配"),
        (("利润的构成", "可供分配利润"), "收益分配利润"),
        (("份额类别",), "份额类别"),
        (("申购和赎回的价格", "申购与赎回的价格"), "申购赎回价格费用用途"),
        (("收益分配",), "收益分配"),
    ):
        if any(token in text for token in tokens):
            return key
    return ""


def _copy_key(title: Any, content: Any, heading_level: int = 0) -> str:
    """Normalise the clause identity used to relate a summary copy to its body.

    The key is derived from the leaf's own business text, never from a generic
    recap chapter title such as ``三、基金的收益与分配``.  Title matches win over
    content matches so a clause that merely mentions another topic (e.g. the
    fee-types list mentioning 销售服务费) keeps its own identity.  Content
    fallback is limited to clause-level leaves (heading level 3); a whole
    chapter that happens to mention 销售服务费 is not a copy of the fee clause.
    """

    title_key = _title_copy_key(title)
    if title_key:
        return title_key
    if heading_level and heading_level < 3:
        return ""
    return _content_copy_key(content)


def _copy_key_match(leaf: LeafSection, keys: Iterable[str]) -> bool:
    """Match an explicit ``copy_key`` against a real leaf without fixed tokens."""

    wanted = {_compact(key) for key in keys if _compact(key)}
    if not wanted:
        return False
    aliases = {_compact(leaf.copy_key), _compact(leaf.title)}
    title_key = _title_copy_key(leaf.title)
    if title_key:
        aliases.add(title_key)
    if wanted & aliases:
        return True
    title = _compact(leaf.title)
    return any(len(key) >= 3 and key in title for key in wanted)


def _location_sort_key(location: str) -> tuple[str, int, str]:
    match = re.match(r"^([A-Za-z]+)(\d+)$", str(location))
    if match:
        return match.group(1), int(match.group(2)), ""
    return str(location), -1, str(location)


# ---------------------------------------------------------------------------
# Leaf construction
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _LeafDraft:
    title: str
    heading_level: int
    locations: tuple[str, ...]


def _leaf_text(locations: Iterable[str], spans: Mapping[str, Any]) -> str:
    return "".join(_compact(getattr(spans[loc], "text", "")) for loc in locations
                   if loc in spans)


def _glossary_entry_title(text: Any) -> str:
    """Return a readable 释义 entry title without its leading entry number."""

    compact = re.sub(r"^\d{1,3}[、.]", "", _compact(text))
    title = re.split(r"[:：]", compact, maxsplit=1)[0]
    return title.strip()[:60]


def _glossary_groups(locations: Sequence[str], spans: Mapping[str, Any],
                     section_title: str) -> list[_LeafDraft]:
    """Treat each 释义 entry as its own clause.

    Definition entries are separated by paragraph, not by numbered headings in
    several contracts.  Keeping one paragraph per leaf makes the class-definition
    scope exact instead of the whole glossary chapter.
    """

    groups: list[_LeafDraft] = []
    pending_blanks: list[str] = []
    current: list[str] = []
    current_title = ""
    for location in locations:
        text = _compact(getattr(spans[location], "text", ""))
        if text:
            if current:
                groups.append(_LeafDraft(current_title or section_title, 3, tuple(current)))
            elif pending_blanks:
                current.extend(pending_blanks)
                pending_blanks = []
            current = [location]
            current_title = _glossary_entry_title(text) or section_title
        elif current:
            current.append(location)
        else:
            pending_blanks.append(location)
    if current:
        groups.append(_LeafDraft(current_title or section_title, 3, tuple(current)))
    elif pending_blanks:
        groups.append(_LeafDraft(section_title, 3, tuple(pending_blanks)))
    return groups


def _section_groups(locations: Sequence[str], spans: Mapping[str, Any],
                    section_title: str) -> list[_LeafDraft]:
    if _is_glossary_title(section_title):
        return _glossary_groups(locations, spans, section_title)
    headings: list[tuple[int, str, int]] = []
    for index, location in enumerate(locations):
        heading = _heading_for(getattr(spans[location], "text", ""), section_title)
        if heading is not None:
            headings.append((index, heading[0], heading[1]))
    if not headings:
        return [_LeafDraft(section_title, 1, tuple(locations))]
    # Some contracts use a plain ``3、销售服务费`` heading followed by per-class
    # or calculation subheadings ``（1）C类基金份额的销售服务费`` /
    # ``（2）销售服务费的计提与支付``.  In that shape the subheadings are
    # rate/calculation sub-items of the same clause, not new clauses: keep them
    # inside the plain leaf.  When the plain heading is absent (QDII uses only
    # ``3、C类基金份额的销售服务费``), the variant heading is the clause.
    plain_fee_heading = any(_compact(title) in _PLAIN_SALES_FEE_TITLES
                            for _, title, _level in headings)
    if plain_fee_heading:
        headings = [item for item in headings
                    if not _is_sales_fee_subheading(item[1])]
    groups: list[_LeafDraft] = []
    if headings[0][0] > 0:
        groups.append(_LeafDraft(section_title, 1, tuple(locations[:headings[0][0]])))
    for position, (start, title, level) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(locations)
        groups.append(_LeafDraft(title or section_title, level, tuple(locations[start:end])))
    return groups


def build_leaf_sections(inspection: Any, sections: Sequence[Any]) -> tuple[LeafSection, ...]:
    """Build deterministic physical leaf sections for every readable section."""

    spans = {str(getattr(span, "location", "")): span
             for span in getattr(inspection, "paragraphs", ())}
    glossary_section_ids = {str(getattr(section, "id", "")) for section in sections
                            if _is_glossary_title(_section_title(section))}
    leaves: list[LeafSection] = []
    for section in sections:
        section_id = str(getattr(section, "id", ""))
        if not section_id:
            continue
        title = _section_title(section)
        zone = str(getattr(section, "zone", "body"))
        locations = [str(location) for location in getattr(section, "locations", ())]
        readable = [location for location in locations
                    if location in spans and _span_zone(spans[location]) in _READABLE_ZONES]
        if not readable:
            continue
        for index, draft in enumerate(_section_groups(readable, spans, title), 1):
            content = _leaf_text(draft.locations, spans)
            key = _copy_key(draft.title, content, draft.heading_level)
            leaves.append(LeafSection(
                id=f"{section_id}:L{index:02d}",
                parent_section_id=section_id,
                title=draft.title,
                zone=zone if zone in _READABLE_ZONES else "body",
                heading_level=draft.heading_level,
                locations=draft.locations,
                copy_key=key,
            ))
    body_by_key: dict[str, str] = {}
    for leaf in leaves:
        if (leaf.zone != "body" or not leaf.copy_key
                or leaf.parent_section_id in glossary_section_ids
                or _is_glossary_title(leaf.title)):
            continue
        existing = body_by_key.get(leaf.copy_key)
        if existing is None:
            body_by_key[leaf.copy_key] = leaf.id
            continue
        # Prefer the leaf whose own title names the clause over a chapter/preamble
        # leaf that merely mentions the words in its body.
        needle = {"收益分配": "收益分配原则",
                  "销售服务费": "销售服务费",
                  "清算剩余资产": "清算剩余资产"}.get(leaf.copy_key, leaf.copy_key)
        current = next(item for item in leaves if item.id == existing)
        if needle not in _compact(current.title) and needle in _compact(leaf.title):
            body_by_key[leaf.copy_key] = leaf.id
    return tuple(
        replace(leaf, summary_of=body_by_key.get(leaf.copy_key, ""))
        if leaf.zone == "summary" and leaf.copy_key else leaf
        for leaf in leaves
    )


# ---------------------------------------------------------------------------
# Rule resolution
# ---------------------------------------------------------------------------

def _rule_field(rule: Any, key: str, default: Any = "") -> Any:
    if isinstance(rule, Mapping):
        return rule.get(key, default)
    return getattr(rule, key, default)


def _mapping_ids(mapping: Mapping[str, Any], rule_id: str) -> list[str]:
    raw = mapping.get(rule_id, ()) if isinstance(mapping, Mapping) else ()
    if isinstance(raw, str):
        return [raw]
    return [str(value) for value in raw or ()]


def _valid_sections(sections: Sequence[Any], ids: Iterable[str]) -> list[Any]:
    by_id = {str(getattr(section, "id", "")): section for section in sections}
    result: list[Any] = []
    seen: set[str] = set()
    for section_id in ids:
        section = by_id.get(str(section_id))
        if section is not None and str(section.id) not in seen:
            seen.add(str(section.id))
            result.append(section)
    return result


def _leaves_for(leaves: Sequence[LeafSection], section_ids: Iterable[str], *,
                zone: str | None = None) -> list[LeafSection]:
    wanted = {str(section_id) for section_id in section_ids}
    return [leaf for leaf in leaves
            if leaf.parent_section_id in wanted and (zone is None or leaf.zone == zone)]


def _leaf_label(leaf: LeafSection) -> str:
    return f"leaf={leaf.id}:{leaf.title[:36]}"


def _scope(rule_id: str, selected: Sequence[LeafSection], *, resolution: str,
           copy_keys: Iterable[str], evidence: Sequence[str],
           include_summary_copies: bool = False) -> RuleScope:
    unique = list(dict.fromkeys(selected))
    zones = {leaf.zone for leaf in unique}
    zone = "body+summary" if zones == {"body", "summary"} else (next(iter(zones), "body"))
    return RuleScope(
        rule_id=rule_id,
        leaf_ids=frozenset(leaf.id for leaf in unique),
        locations=frozenset(location for leaf in unique for location in leaf.locations),
        zone=zone,
        include_summary_copies=include_summary_copies or "summary" in zones,
        copy_keys=frozenset(key for key in copy_keys if key),
        resolution=resolution,
        evidence=tuple(dict.fromkeys(str(item) for item in evidence if item)),
    )


def _unresolved(rule_id: str, *evidence: str) -> RuleScope:
    return RuleScope(rule_id=rule_id, leaf_ids=frozenset(), locations=frozenset(),
                     zone="", include_summary_copies=False, copy_keys=frozenset(),
                     resolution="unresolved", evidence=tuple(dict.fromkeys(evidence)))


def _summary_enabled(overrides: Mapping[str, Any] | Iterable[str] | None,
                     rule_id: str, default: bool) -> bool:
    if overrides is None:
        return default
    if isinstance(overrides, Mapping):
        return bool(overrides.get(rule_id, default))
    return rule_id in overrides


def _copy_key_override(overrides: Mapping[str, Iterable[str]] | None,
                       rule_id: str) -> set[str]:
    if not overrides:
        return set()
    raw = overrides.get(rule_id, ())
    if isinstance(raw, str):
        return {raw}
    return {str(value) for value in raw or ()}


def _title_mentions_class(leaf: LeafSection) -> bool:
    compact = _compact(leaf.title)
    if "份额" in compact and ("类别" in compact or "分类" in compact):
        return True
    # ``类别设置`` without the 份额 prefix still names the class clause;
    # ``基金的类别`` (bond/equity fund type) does not, because it has no 设置.
    return "设置" in compact and ("类别" in compact or "分类" in compact)


def _class_definition_leaves(leaves: Sequence[LeafSection], spans: Mapping[str, Any],
                             allowed_ids: Iterable[str]) -> tuple[list[LeafSection], int]:
    """Return every complete class-definition leaf, never ``pool[0]``."""

    allowed = {str(section_id) for section_id in allowed_ids}
    candidates = [leaf for leaf in leaves
                  if leaf.zone == "body" and leaf.parent_section_id in allowed
                  and _is_class_definition(_leaf_text(leaf.locations, spans))]
    preferred = [leaf for leaf in candidates if _title_mentions_class(leaf)]
    if preferred:
        return preferred, len(candidates)
    if len(candidates) == 1 and candidates[0].heading_level == 1:
        # A compact contract may have no subsection heading at all; its whole
        # basics chapter is then the definition leaf.
        return candidates, len(candidates)
    return [], len(candidates)


def _class_set_leaves(leaves: Sequence[LeafSection], spans: Mapping[str, Any],
                      allowed_ids: Iterable[str]
                      ) -> tuple[list[LeafSection], int, bool]:
    """Return every valid 份额类别 setup leaf in one mapped basics section.

    Real contracts place the same business clause in sibling leaves:
    ``八、基金份额类别设置`` carries the fee-adjustment sentence and
    ``九、基金份额的类别`` repeats it after the class definition (景宁 p148 and
    p155).  Selecting the first leaf loses the second body site.  Leaves are
    merged only when they are body leaves of the *same* parent section and their
    titles belong to the class word family (设置/类别/分类/份额类别).  When
    candidates span different parent sections the topology is ambiguous; the
    caller keeps the mapped parent section instead of guessing.
    """

    allowed = {str(section_id) for section_id in allowed_ids}
    candidates = [
        leaf for leaf in leaves
        if leaf.zone == "body" and leaf.parent_section_id in allowed
        and _title_mentions_class(leaf)
        and ("设置" in _compact(leaf.title)
             or _is_class_setup_text(_leaf_text(leaf.locations, spans)))
    ]
    if not candidates:
        return [], 0, False
    if len({leaf.parent_section_id for leaf in candidates}) > 1:
        return [], len(candidates), True
    return candidates, len(candidates), False


def _class_scope(rule_id: str, selected: Sequence[LeafSection], *,
                 resolution: str, base: Sequence[Any],
                 leaves: Sequence[LeafSection],
                 summary_overrides: Mapping[str, Any] | Iterable[str] | None,
                 summary_keys: Mapping[str, Iterable[str]] | None,
                 evidence: list[str]) -> RuleScope:
    """Build a class scope and append only explicitly keyed summary copies."""

    summary_ids = [str(section.id) for section in base if str(section.zone) == "summary"]
    summary_leaves: list[LeafSection] = []
    if summary_ids:
        enabled = _summary_enabled(summary_overrides, rule_id, False)
        explicit = _copy_key_override(summary_keys, rule_id)
        if not enabled:
            evidence.append("summary_copy=excluded_default")
        elif not explicit:
            evidence.append("summary_copy=excluded_no_explicit_copy_key")
        else:
            body_keys = {leaf.copy_key for leaf in selected if leaf.copy_key}
            summary_leaves = [
                leaf for leaf in _leaves_for(leaves, summary_ids, zone="summary")
                if leaf.copy_key in body_keys and _copy_key_match(leaf, explicit)
            ]
            if summary_leaves:
                evidence.append("summary_copy_keys=" + ",".join(sorted(explicit)))
            else:
                evidence.append("summary_copy=no_matching_copy_key")
    return _scope(rule_id, list(selected) + summary_leaves, resolution=resolution,
                  copy_keys={"份额类别"} | {leaf.copy_key for leaf in selected},
                  evidence=evidence, include_summary_copies=bool(summary_leaves))


def _resolve_class_basics(rule_id: str,
                          sections: Sequence[Any], leaves: Sequence[LeafSection],
                          spans: Mapping[str, Any], mapping: Mapping[str, Any], *,
                          summary_overrides: Mapping[str, Any] | Iterable[str] | None = None,
                          summary_keys: Mapping[str, Iterable[str]] | None = None) -> RuleScope:
    """G03/G04/G05/G06: 基金的基本情况 class clause policies."""

    base = _valid_sections(sections, _mapping_ids(mapping, rule_id))
    base_ids = [str(section.id) for section in base]
    basic = [str(section.id) for section in base if _is_basic_info_section(section.title)]
    evidence = [f"policy={rule_id}.class_basics", f"base_sections={','.join(base_ids)}"]

    if not basic:
        return _unresolved(rule_id, *evidence, "basic_info_section_missing")

    if rule_id in {"G03", "G04"}:
        def_leaves, count = _class_definition_leaves(leaves, spans, basic)
        if def_leaves:
            evidence.extend([f"definition_candidates={count}"])
            if len(def_leaves) > 1:
                evidence.append(f"multi_leaf={len(def_leaves)}")
            evidence.extend([_leaf_label(leaf) for leaf in def_leaves])
            evidence.append("source=basic_info_definition")
            return _class_scope(rule_id, def_leaves, resolution="resolved", base=base,
                                leaves=leaves, summary_overrides=summary_overrides,
                                summary_keys=summary_keys, evidence=evidence)
        if rule_id == "G03":
            # Some contracts split the class-setup clause (fee adjustment) from the
            # class definition.  G03 appends after the definition; only fall back to
            # the setup leaf when no complete definition exists.
            set_leaves, set_count, ambiguous = _class_set_leaves(leaves, spans, basic)
            if set_leaves:
                evidence.extend([f"definition_candidates={set_count}"])
                if len(set_leaves) > 1:
                    evidence.append(f"multi_leaf={len(set_leaves)}")
                evidence.extend([_leaf_label(leaf) for leaf in set_leaves])
                evidence.append("source=basic_info_class_leaf")
                return _class_scope(rule_id, set_leaves, resolution="resolved",
                                    base=base, leaves=leaves,
                                    summary_overrides=summary_overrides,
                                    summary_keys=summary_keys, evidence=evidence)
            if ambiguous:
                fallback = _leaves_for(leaves, basic, zone="body")
                if fallback:
                    evidence.extend([f"definition_candidates={set_count}",
                                     "fallback=class_leaves_ambiguous",
                                     "fallback=base_section_leaves"])
                    return _class_scope(rule_id, fallback, resolution="section_fallback",
                                        base=base, leaves=leaves,
                                        summary_overrides=summary_overrides,
                                        summary_keys=summary_keys, evidence=evidence)
            return _unresolved(rule_id, *evidence, "class_definition_missing")
        # G04 is the only rule allowed to add the 释义 definition when the
        # basics chapter only carries a fee-adjustment paragraph.
        glossary_ids = [str(section.id) for section in sections
                        if _is_glossary_title(section.title)]
        glossary_leaves, glossary_count = _class_definition_leaves(
            leaves, spans, glossary_ids)
        if glossary_leaves:
            evidence.extend([f"definition_candidates={count}",
                             f"glossary_candidates={glossary_count}"])
            if len(glossary_leaves) > 1:
                evidence.append(f"multi_leaf={len(glossary_leaves)}")
            evidence.extend([_leaf_label(leaf) for leaf in glossary_leaves])
            evidence.append("source=glossary_definition_added")
            return _class_scope(rule_id, glossary_leaves, resolution="resolved",
                                base=base, leaves=leaves,
                                summary_overrides=summary_overrides,
                                summary_keys=summary_keys, evidence=evidence)
        return _unresolved(rule_id, *evidence, "class_definition_missing")

    set_leaves, count, ambiguous = _class_set_leaves(leaves, spans, basic)
    if set_leaves:
        evidence.extend([f"definition_candidates={count}"])
        if len(set_leaves) > 1:
            evidence.append(f"multi_leaf={len(set_leaves)}")
        evidence.extend([_leaf_label(leaf) for leaf in set_leaves])
        evidence.append("source=basic_info_class_leaf")
        return _class_scope(rule_id, set_leaves, resolution="resolved", base=base,
                            leaves=leaves, summary_overrides=summary_overrides,
                            summary_keys=summary_keys, evidence=evidence)
    if ambiguous:
        fallback = _leaves_for(leaves, basic, zone="body")
        if fallback:
            evidence.extend([f"definition_candidates={count}",
                             "fallback=class_leaves_ambiguous",
                             "fallback=base_section_leaves"])
            return _class_scope(rule_id, fallback, resolution="section_fallback",
                                base=base, leaves=leaves,
                                summary_overrides=summary_overrides,
                                summary_keys=summary_keys, evidence=evidence)

    if rule_id == "G06":
        # Exact, paragraph-bound compatibility fallback.  It is restricted to the
        # mapped 基本情况 sections, so the D06 p280 conversion sentence can
        # never be admitted.
        phrase = "不同基金份额类别之间不得互相转换。"
        basic_locations = {location for leaf in _leaves_for(leaves, basic)
                           for location in leaf.locations}
        basic_spans = [location for location in basic_locations
                       if phrase in _compact(getattr(spans.get(location), "text", ""))]
        if basic_spans:
            exact = frozenset(basic_spans)
            exact_leaf_ids = frozenset(
                leaf.id for leaf in _leaves_for(leaves, basic)
                if exact.intersection(leaf.locations)
            )
            evidence.extend(["resolution=fallback_exact",
                             f"exact_locations={','.join(sorted(basic_spans))}"])
            return RuleScope(rule_id=rule_id, leaf_ids=exact_leaf_ids,
                             locations=exact, zone="body",
                             include_summary_copies=False,
                             copy_keys=frozenset({"份额类别"}),
                             resolution="fallback_exact", evidence=tuple(evidence))
        return _unresolved(rule_id, *evidence, "class_clause_missing")

    fallback = _leaves_for(leaves, basic, zone="body")
    if fallback:
        evidence.append("fallback=base_section_leaves")
        return _scope(rule_id, fallback, resolution="section_fallback",
                      copy_keys={"份额类别"}, evidence=evidence)
    return _unresolved(rule_id, *evidence, "class_clause_missing")


def _resolve_definition(rule_id: str, sections: Sequence[Any],
                        leaves: Sequence[LeafSection], spans: Mapping[str, Any],
                        mapping: Mapping[str, Any]) -> RuleScope:
    base = _valid_sections(sections, _mapping_ids(mapping, rule_id))
    glossary_ids = [str(section.id) for section in base if _is_glossary_title(section.title)]
    selected = [leaf for leaf in _leaves_for(leaves, glossary_ids, zone="body")
                if _is_class_definition(_leaf_text(leaf.locations, spans))]
    evidence = [f"policy={rule_id}.glossary_class_definition",
                f"glossary_sections={','.join(glossary_ids)}"]
    if not selected:
        # Compact definitions may omit the fee distinction but still be the only
        # class-definition paragraph in 释义.  Keep that bounded fallback.
        selected = [leaf for leaf in _leaves_for(leaves, glossary_ids, zone="body")
                    if leaf.copy_key == "份额类别"
                    and "基金份额类别" in _leaf_text(leaf.locations, spans)]
        if not selected:
            return _unresolved(rule_id, *evidence, "glossary_class_definition_missing")
        evidence.append("fallback=glossary_class_label")
    evidence.extend(_leaf_label(leaf) for leaf in selected)
    return _scope(rule_id, selected, resolution="resolved",
                  copy_keys={"份额类别"}, evidence=evidence)


def _resolve_fee_tax(rule_id: str, sections: Sequence[Any], leaves: Sequence[LeafSection],
                     mapping: Mapping[str, Any], *,
                     summary_overrides: Mapping[str, Any] | Iterable[str] | None,
                     summary_keys: Mapping[str, Iterable[str]] | None) -> RuleScope:
    base = _valid_sections(sections, _mapping_ids(mapping, rule_id))
    base_ids = [str(section.id) for section in base]
    fee_ids = [str(section.id) for section in base if _is_fee_tax_section(section.title)]
    evidence = [f"policy={rule_id}.sales_service_fee",
                f"base_sections={','.join(base_ids)}"]
    body = [leaf for leaf in _leaves_for(leaves, fee_ids, zone="body")
            if "服务费" in _compact(leaf.title)]
    if not body:
        return _unresolved(rule_id, *evidence, "sales_service_fee_leaf_missing")

    selected: list[LeafSection] = list(body)
    enabled = _summary_enabled(summary_overrides, rule_id, False)
    explicit_keys = _copy_key_override(summary_keys, rule_id)
    summary_leaves: list[LeafSection] = []
    if enabled and explicit_keys:
        summary_ids = [str(section.id) for section in base if str(section.zone) == "summary"]
        body_keys = {leaf.copy_key for leaf in body if leaf.copy_key}
        summary_leaves = [
            leaf for leaf in _leaves_for(leaves, summary_ids, zone="summary")
            if leaf.copy_key in body_keys and _copy_key_match(leaf, explicit_keys)
        ]
        selected.extend(summary_leaves)
        if summary_leaves:
            evidence.append("summary_copy_keys=" + ",".join(sorted(explicit_keys)))
        else:
            evidence.append("summary_copy=no_matching_copy_key")
    elif any(str(section.zone) == "summary" for section in base):
        evidence.append("summary_copy=excluded_default" if not enabled
                        else "summary_copy=excluded_no_explicit_copy_key")

    evidence.extend(_leaf_label(leaf) for leaf in selected)
    return _scope(rule_id, selected, resolution="resolved",
                  copy_keys={"销售服务费"}, evidence=evidence,
                  include_summary_copies=bool(summary_leaves))


def _resolve_income(rule_id: str, sections: Sequence[Any], leaves: Sequence[LeafSection],
                    mapping: Mapping[str, Any], *,
                    summary_overrides: Mapping[str, Any] | Iterable[str] | None) -> RuleScope:
    base = _valid_sections(sections, _mapping_ids(mapping, rule_id))
    base_ids = [str(section.id) for section in base]
    body_ids = [str(section.id) for section in base
                if str(section.zone) == "body" and _is_income_section(section.title)]
    evidence = [f"policy={rule_id}.income_distribution", f"base_sections={','.join(base_ids)}"]
    body = [leaf for leaf in _leaves_for(leaves, body_ids, zone="body")
            if "收益分配原则" in _compact(leaf.title)]
    resolution = "resolved"
    if not body:
        chapter_leaves = _leaves_for(leaves, body_ids, zone="body")
        if len(chapter_leaves) == 1:
            # No subsection headings: the chapter itself is the only leaf.
            body = chapter_leaves
            resolution = "section_fallback"
    if not body:
        return _unresolved(rule_id, *evidence, "income_principle_leaf_missing")

    selected: list[LeafSection] = list(body)
    summary_ids = [str(section.id) for section in base if str(section.zone) == "summary"]
    enabled = _summary_enabled(summary_overrides, rule_id, True)
    summary_leaves = ([leaf for leaf in _leaves_for(leaves, summary_ids, zone="summary")
                       if leaf.copy_key == "收益分配"
                       and "收益分配原则" in _compact(leaf.title)] if enabled else [])
    selected.extend(summary_leaves)
    evidence.extend(_leaf_label(leaf) for leaf in selected)
    if summary_leaves:
        evidence.append("summary_copy_keys=收益分配")
    return _scope(rule_id, selected, resolution=resolution, copy_keys={"收益分配"},
                  evidence=evidence, include_summary_copies=bool(summary_leaves))


def _resolve_liquidation(rule_id: str, sections: Sequence[Any], leaves: Sequence[LeafSection],
                         mapping: Mapping[str, Any], *,
                         summary_overrides: Mapping[str, Any] | Iterable[str] | None) -> RuleScope:
    base = _valid_sections(sections, _mapping_ids(mapping, rule_id))
    base_ids = [str(section.id) for section in base]
    body_ids = [str(section.id) for section in base
                if str(section.zone) == "body" and _is_liquidation_section(section.title)]
    evidence = [f"policy={rule_id}.liquidation_residual",
                f"base_sections={','.join(base_ids)}"]
    body = [leaf for leaf in _leaves_for(leaves, body_ids, zone="body")
            if "清算剩余资产" in _compact(leaf.title)]
    resolution = "resolved"
    if not body:
        chapter_leaves = _leaves_for(leaves, body_ids, zone="body")
        if len(chapter_leaves) == 1:
            body = chapter_leaves
            resolution = "section_fallback"
    if not body:
        return _unresolved(rule_id, *evidence, "liquidation_residual_leaf_missing")

    selected: list[LeafSection] = list(body)
    summary_ids = [str(section.id) for section in base if str(section.zone) == "summary"]
    enabled = _summary_enabled(summary_overrides, rule_id, True)
    summary_leaves = ([leaf for leaf in _leaves_for(leaves, summary_ids, zone="summary")
                       if leaf.copy_key == "清算剩余资产"] if enabled else [])
    selected.extend(summary_leaves)
    evidence.extend(_leaf_label(leaf) for leaf in selected)
    if summary_leaves:
        evidence.append("summary_copy_keys=清算剩余资产")
    return _scope(rule_id, selected, resolution=resolution,
                  copy_keys={"清算剩余资产"}, evidence=evidence,
                  include_summary_copies=bool(summary_leaves))


def _resolve_purchase(rule_id: str, sections: Sequence[Any], leaves: Sequence[LeafSection],
                      mapping: Mapping[str, Any]) -> RuleScope:
    base = _valid_sections(sections, _mapping_ids(mapping, rule_id))
    base_ids = [str(section.id) for section in base]
    purchase_ids = [str(section.id) for section in base
                    if str(section.zone) == "body" and _is_purchase_section(section.title)]
    evidence = [f"policy={rule_id}.purchase_price_fee",
                f"base_sections={','.join(base_ids)}"]
    selected = [leaf for leaf in _leaves_for(leaves, purchase_ids, zone="body")
                if ("申购和赎回的价格" in _compact(leaf.title)
                    or "申购与赎回的价格" in _compact(leaf.title))]
    if selected:
        evidence.extend(_leaf_label(leaf) for leaf in selected)
        return _scope(rule_id, selected, resolution="resolved",
                      copy_keys={"申购赎回价格费用用途"}, evidence=evidence)
    fallback = _leaves_for(leaves, purchase_ids, zone="body")
    if fallback:
        evidence.extend(["fallback=base_section_leaves",
                         *(_leaf_label(leaf) for leaf in fallback)])
        return _scope(rule_id, fallback, resolution="section_fallback",
                      copy_keys={"申购赎回价格费用用途"}, evidence=evidence)
    return _unresolved(rule_id, *evidence, "purchase_price_leaf_missing")


def _rule_anchor(rule: Any) -> str:
    title = _visible(_rule_field(rule, "title", ""))
    title = re.sub(r"[（(][^）)]*[）)]", "", title)
    parts = [part.strip() for part in re.split(r"[-—：:]", title) if part.strip()]
    anchor = parts[-1] if parts else title
    anchor = re.sub(r"^\d+[、.]", "", anchor)
    return _compact(anchor)


def _resolve_default(rule_id: str, rule: Any, sections: Sequence[Any],
                     leaves: Sequence[LeafSection], mapping: Mapping[str, Any],
                     *, summary_overrides: Mapping[str, Any] | Iterable[str] | None,
                     summary_keys: Mapping[str, Iterable[str]] | None) -> RuleScope:
    base = _valid_sections(sections, _mapping_ids(mapping, rule_id))
    body_ids = [str(section.id) for section in base if str(section.zone) == "body"]
    base_leaves = _leaves_for(leaves, body_ids, zone="body")
    evidence = [f"base_sections={','.join(str(section.id) for section in base)}"]
    if not base_leaves:
        return _unresolved(rule_id, *evidence, "no_body_leaf_in_mapped_sections")

    hint = _compact(_rule_field(rule, "section_hint", ""))
    anchor = _rule_anchor(rule)
    matches = [leaf for leaf in base_leaves
               if (anchor and (anchor in _compact(leaf.title)
                               or anchor == leaf.copy_key
                               or anchor in leaf.copy_key))
               or (hint and hint in _compact(leaf.title))]
    if len(matches) == 1:
        evidence.extend([f"anchor={anchor or hint}", _leaf_label(matches[0])])
        selected = matches
        resolution = "resolved"
    else:
        selected = base_leaves
        resolution = "section_fallback"
        evidence.append(f"anchor_candidates={len(matches)}")

    enabled = _summary_enabled(summary_overrides, rule_id, False)
    explicit_keys = _copy_key_override(summary_keys, rule_id)
    if enabled and explicit_keys:
        summary_ids = [str(section.id) for section in base if str(section.zone) == "summary"]
        selected = list(selected) + [leaf for leaf in _leaves_for(leaves, summary_ids, zone="summary")
                                     if leaf.copy_key in explicit_keys]
        evidence.append("summary_copy_keys=" + ",".join(sorted(explicit_keys)))
    evidence.extend(_leaf_label(leaf) for leaf in selected)
    return _scope(rule_id, selected, resolution=resolution,
                  copy_keys={leaf.copy_key for leaf in selected},
                  evidence=evidence,
                  include_summary_copies=any(leaf.zone == "summary" for leaf in selected))


def resolve_rule_scopes(
    rules: Sequence[Any],
    sections: Sequence[Any],
    inspection: Any,
    mapping: Mapping[str, Any],
    *,
    include_summary_copies: Mapping[str, Any] | Iterable[str] | None = None,
    summary_copy_keys: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, RuleScope]:
    """Resolve every rule to leaf locations without ever widening to the document.

    ``mapping`` is the existing section-level ``scope_map`` output and is the base
    boundary.  Explicit policies may add the 释义 definition for G04 (the same
    bounded expansion as ``expand_class_definition_scope``); no other rule reads
    outside its mapped sections.

    ``include_summary_copies`` / ``summary_copy_keys`` are opt-in overrides for
    summary copies.  G18/G19-G22 include a copy only when its ``copy_key`` matches
    the body clause; G15-G17 default to body only and require both an explicit
    flag and an explicit copy key.
    """

    span_map = {str(getattr(span, "location", "")): span
                for span in getattr(inspection, "paragraphs", ())}
    leaves = build_leaf_sections(inspection, sections)
    by_rule = {str(_rule_field(rule, "rule_id", "")): rule for rule in rules
               if _rule_field(rule, "rule_id", "")}
    result: dict[str, RuleScope] = {}
    for rule_id, rule in by_rule.items():
        try:
            if rule_id in {"G01", "G02"}:
                scope = _resolve_definition(rule_id, sections, leaves, span_map, mapping)
            elif rule_id in {"G03", "G04", "G05", "G06"}:
                scope = _resolve_class_basics(rule_id, sections, leaves, span_map, mapping,
                                              summary_overrides=include_summary_copies,
                                              summary_keys=summary_copy_keys)
            elif rule_id in {"G15", "G16", "G17"}:
                scope = _resolve_fee_tax(rule_id, sections, leaves, mapping,
                                         summary_overrides=include_summary_copies,
                                         summary_keys=summary_copy_keys)
            elif rule_id == "G18":
                scope = _resolve_income(rule_id, sections, leaves, mapping,
                                        summary_overrides=include_summary_copies)
            elif rule_id in {"G19", "G20", "G21", "G22"}:
                scope = _resolve_liquidation(rule_id, sections, leaves, mapping,
                                             summary_overrides=include_summary_copies)
            elif rule_id in {f"G{number:02d}" for number in range(7, 15)}:
                scope = _resolve_purchase(rule_id, sections, leaves, mapping)
            else:
                scope = _resolve_default(rule_id, rule, sections, leaves, mapping,
                                         summary_overrides=include_summary_copies,
                                         summary_keys=summary_copy_keys)
        except Exception as exc:  # resolution must never fail the whole contract
            scope = _unresolved(rule_id, f"resolution_error={type(exc).__name__}",
                                str(exc)[:160])
        result[rule_id] = scope
    return result


# ---------------------------------------------------------------------------
# Convenience projections for the integration phase
# ---------------------------------------------------------------------------

def _scope_items(scopes: Mapping[str, RuleScope] | Iterable[RuleScope]) -> Iterable[tuple[str, RuleScope]]:
    if isinstance(scopes, Mapping):
        return ((str(rule_id), scope) for rule_id, scope in scopes.items())
    return ((scope.rule_id, scope) for scope in scopes)


def scope_locations_for_window(
    scopes: Mapping[str, RuleScope] | Iterable[RuleScope],
    window_locations: Any,
) -> dict[str, frozenset[str]]:
    """Intersect every rule scope with one window's physical locations."""

    if hasattr(window_locations, "locations"):
        values = getattr(window_locations, "locations")
    elif isinstance(window_locations, str):
        values = (window_locations,)
    else:
        values = window_locations or ()
    allowed = {str(location) for location in values}
    return {rule_id: frozenset(scope.locations & allowed)
            for rule_id, scope in _scope_items(scopes)}


def scope_locations(
    scopes: Mapping[str, RuleScope] | Iterable[RuleScope],
) -> dict[str, frozenset[str]]:
    """Return the rule id to physical location projection used by recall paths."""

    return {rule_id: frozenset(scope.locations) for rule_id, scope in _scope_items(scopes)}
