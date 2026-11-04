"""直通重构 · 第 2 条：限定章节定位与模型改写提案引擎（direct_edit_v1）。

输入：一份合同 DOCX + guide_card_v1 原子规则卡（第 1 线冻结契约）；
输出：direct_edit_proposal_v1 提案（第 3 线写入器消费）+ direct_write_scope_v1 授权范围。

范围纪律（FL-D1022 用户裁决，2026-11-02）：
- 只允许修改目标章节与该事项对应的摘要小节；目录只用于章节判断，绝不全文漫游。
- 四道范围检查：定位、补扫、改写、提案构建各自独立做 in-scope 断言。
- 召回优先：章节内窗口全枚举 + 相邻窗一段重叠 + 一次补扫，不要求措辞与指引一致。
- 单卡/单窗口/单组失败只记内部诊断，其他继续；不向用户派发人工核查。
- 本模块不调用旧引擎（recall/recall_pipeline/obligations/rule_scope）任何符号，
  结构件（章节索引/窗口/引文回解）自包含重写。
"""

from __future__ import annotations

import concurrent.futures
import difflib
import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .docx import DocumentInspection, ParagraphSpan, DocxError, MAPPING_VERSION, inspect_docx

# FL-D1115（修订盲）：locate/scope 输入读口归一到 prepare_compare_input 上游
# （既有修订的接受定稿文本（w:ins/del 并入后视）入索引/选章/定位/补扫，
#  旧带 ins/del 原文不再接。strict_dual_layer/写回层契约不变）。
from .compare.revisions import prepare_compare_input  # noqa: E402

PROPOSAL_SCHEMA_VERSION = "direct_edit_proposal_v1"
SCOPE_SCHEMA_VERSION = "direct_write_scope_v2"  # v2=FL-D1029 摘要逐处白名单(对齐第3线/integration d41339a)
DIRECT_EDIT_VERSION = "direct-edit-1"

#: 单次定位/补扫调用投喂的批宽。FL-D1048 全集对拍证据链：批宽 32→0 提案、8→4、3→6
#: （赛前 12）——当前模型下共享调用批宽>1 有系统性召回稀释，默认保守置 1＝与提速前
#: 逐卡一致语义（提速改由并发/输出收窄/连接复用承载）；批式基建保留，待后续模型支撑
#: 共享批>1 时以 FUNDLEX_DIRECT_LOCATE_BATCH 实验重开（1..8）。
def _locate_batch_size() -> int:
    try:
        return max(1, min(8, int(os.environ.get("FUNDLEX_DIRECT_LOCATE_BATCH", "1"))))
    except ValueError:
        return 1

BARRIER = "￹"
_ACTIONS = ("replace", "delete", "insert_before", "insert_after")

_PROMPT_VERSION_SCOPE = "direct_scope_map_v1"
_PROMPT_VERSION_LOCATE = "direct_locate_v1"
_PROMPT_VERSION_SWEEP = "direct_sweep_v1"
_PROMPT_VERSION_REWRITE = "direct_rewrite_v1"
_PROMPT_VERSION_ANCHOR_CONFIRM = "direct_anchor_confirm_v1"
_PROMPT_VERSION_REVIEW = "direct_review_v1"

# FL-D1075：提案级审查提示词——禁止一切领域专有词（销售服务费/份额类别/费率…），
# 只引通用三元：原句句文 / 提案新文 / 指引卡原文（+合同事实对象）。
_REVIEW_SCHEMA = {
    "type": "object", "required": ["verdict"], "additionalProperties": False,
    "properties": {"verdict": {"enum": ["accept", "veto"]},
                   "reason": {"type": "string"}},
}

_WEAK_ANCHOR_INSTRUCTION = (
    "此前完全对位定位在该卡上没有命中。你现在做**近似锚点遴选**：在窗口中找出与规则卡"
    "事项语义最接近、措辞可以变形的候选句。宁多勿漏，但只限本窗口、与该卡事项真正相关；"
    "引句必须逐字来自窗口文字。只返回 JSON（同 card_id+location+quote 格式）。"
)
_PROMPT_VERSION_WEAK = "direct_weak_anchor_v1"

_REVIEW_INSTRUCTION = (
    "你是改写提案一致性审查员。对照复核一条提案：\n"
    "- [原句]：合同当前句文；[新文]：拟写回文本；[指引卡原文]：要求改成的内容；"
    "[合同事实]：从本合同机械提取的事实对象；[上下文]：目标句子所在段落全文。\n"
    "仅依据这些输入判断是否存在任一硬伤：\n"
    "1) 新文中同一成分累赘重复（相同的短语/分句被重复写入）；\n"
    "2) 新文把指引卡未要求、且[合同事实]中不存在的具体名称/字母符号/数字写入；\n"
    "3) 新文与[指引卡原文]或[合同事实]的论断直接矛盾；\n"
    "4) [上下文]表明新文挂错了句子的归属（文字内容与该句所在位置所谈内容明显不属同一条款）；\n"
    "5) 删除类提案拟删内容明显超过指引卡所要求的句/成分范围（把远超单句的整段删除）；\n"
    "6) [上下文（含相邻段）]中已存在与新文语义相同或近似的内容，新文再写入会形成相邻重复；\n"
    "7) 出现[依赖说明]时把它当作事实：删除/替换会使该句所支撑的公式、计算或记号失去定义或锚点。\n"
    "不存在上述硬伤 → accept；存在任一 → veto 并给一句理由。\n"
    "不要扩展要求，不做润色建议，不评判措辞风格。只返回 JSON。"
)

_ANCHOR_CONFIRM_SCHEMA = {
    "type": "object", "required": ["keep"], "additionalProperties": False,
    "properties": {"keep": {"type": "boolean"}},
}

_ANCHOR_CONFIRM_INSTRUCTION = (
    "复核一个插入锚点候选是否成立。给定规则卡（要求在该锚点之前/之后插入内容）与合同段落，"
    "判断：插入内容若施加在该引句锚点，语义与位置是否符合规则卡事项（锚句即该卡目标条款语境，"
    "未把不相干段落误认为目标条款）。成立 keep=true，不成立 keep=false。"
    "只返回 JSON，不要解释。"
)


class DirectEditError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code + (f" {detail}" if detail else ""))
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------------------
# 原子卡（guide_card_v1 契约适配）

@dataclass(frozen=True)
class AtomicCard:
    card_id: str
    title: str
    applicability: str            # 自然语言条件，可为空
    requirement: str              # action.content_requirement（自然语言修改要求；delete 可空）
    action: str                   # replace/delete/insert_before/insert_after
    anchor_quote: str             # 插入替换删除的目标/锚点引句线索，可空
    section_hints: tuple[str, ...]    # target.contract_sections 自由文本章节线索
    locator_quotes: tuple[str, ...]   # target.locator_quotes，可空
    notes: str = ""
    source_ref: str = ""          # 指引来源追溯（sections+paragraphs 压缩串）
    section_append: bool = False  # insert_after+空anchor+notes="section_append"（仲裁定形）

    @property
    def recall_text(self) -> str:
        """供范围绑定/定位/防编造共用的卡文本并集。"""
        parts = [self.title, self.applicability, self.requirement, self.anchor_quote,
                 self.notes, *self.section_hints, *self.locator_quotes]
        return "\n".join(p for p in parts if p)


def card_from_guide_card_v1(mapping: Mapping[str, Any]) -> AtomicCard:
    """第 1 线 guide_card_v1 卡片 dict → 引擎内卡。结构宽容（契约已校验，此处只取值）。"""
    target = mapping.get("target") or {}
    action = mapping.get("action") or {}
    applicability = mapping.get("applicability") or {}
    source = mapping.get("source") or {}
    src_sections = ", ".join(str(s) for s in (source.get("sections") or ()))
    src_paras = ",".join(str(p) for p in (source.get("paragraphs") or ()))
    notes = str(mapping.get("notes") or "")
    anchor_quote = str(action.get("anchor_quote") or "")
    action_type = str(action.get("type") or "")
    # 裁决定形：builtin 转换的 section-append = insert_after + 空 anchor + notes="section_append"
    is_section_append = (action_type == "insert_after" and not anchor_quote
                         and "section_append" in notes)
    return AtomicCard(
        card_id=str(mapping.get("card_id") or ""),
        title=str(mapping.get("title") or ""),
        applicability=str(applicability.get("text") or ""),
        requirement=str(action.get("content_requirement") or ""),
        action=action_type,
        anchor_quote=anchor_quote,
        section_hints=tuple(str(s) for s in (target.get("contract_sections") or ())),
        locator_quotes=tuple(str(q) for q in (target.get("locator_quotes") or ())),
        notes=notes,
        source_ref=f"{src_sections} ¶{src_paras}".strip(),
        section_append=is_section_append,
    )


# ---------------------------------------------------------------------------
# 结果结构

@dataclass(frozen=True)
class EditProposal:
    """direct_edit_proposal_v1（第 3 线消费；本线只产提案，绝不标记已写入/已验证）。"""
    proposal_id: str
    rule_card_id: str
    scope_ref: str
    action: str
    location: str
    zone: str                              # "body" | "summary"
    start: int
    end: int
    expected_old_text: str
    replacement: str
    anchor: Mapping[str, Any] | None       # insert_* 必填: {start,end,text,sha256}
    fingerprint: str
    source_sha256: str
    merged_card_ids: tuple[str, ...] = ()  # 多卡合并时的其余卡（rule_card_id 为主卡）
    source_ref: str = ""
    section_title: str = ""

    def binding_fields(self) -> dict[str, Any]:
        anchor = self.anchor or {}
        return {
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "rule_card_id": self.rule_card_id,
            "scope_ref": self.scope_ref,
            "action": self.action,
            "location": self.location,
            "zone": self.zone,
            "start": self.start,
            "end": self.end,
            "expected_old_text": self.expected_old_text,
            "replacement": self.replacement,
            # 键名 "anchor_text"：未见写入器实现前的解读，待第 3 线确认（协调者同步）。
            "anchor_text": anchor.get("text") or "",
            "source_sha256": self.source_sha256,
            "fingerprint": self.fingerprint,
        }

    def generation_sha256(self) -> str:
        payload = json.dumps(self.binding_fields(), ensure_ascii=False,
                             sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def expected_old_hash(self) -> str:
        return hashlib.sha256(self.expected_old_text.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": PROPOSAL_SCHEMA_VERSION,
            "proposal_id": self.proposal_id,
            "rule_card_id": self.rule_card_id,
            "scope_ref": self.scope_ref,
            "action": self.action,
            "location": self.location,
            "zone": self.zone,
            "start": self.start,
            "end": self.end,
            "expected_old_text": self.expected_old_text,
            "expected_old_hash": self.expected_old_hash(),
            "replacement": self.replacement,
            "anchor": dict(self.anchor) if self.anchor else None,
            "fingerprint": self.fingerprint,
            "mapping_version": MAPPING_VERSION,
            "source_sha256": self.source_sha256,
            "generation_sha256": self.generation_sha256(),
        }

    def to_edit_dict(self) -> dict[str, Any]:
        """转换为 docx.validate_edit_plan / generate_artifacts 消费的 edit dict。"""
        edit: dict[str, Any] = {
            "source_sha256": self.source_sha256,
            "verified": True,
            "location": self.location,
            "zone": self.zone,
            "mapping_version": MAPPING_VERSION,
            "fingerprint": self.fingerprint,
            "start": self.start,
            "end": self.end,
            "expected_old_text": self.expected_old_text,
            "expected_old_hash": self.expected_old_hash(),
            "replacement": self.replacement,
            "content_source": "generated",
            "edit_id": self.proposal_id,
        }
        if self.action in ("insert_before", "insert_after"):
            # 第 3 线扩展后 validate_edit_plan 原生接受这两个动词；本仓主线仅知 "insert"。
            edit["operation"] = self.action
            edit["anchor"] = dict(self.anchor or {})
        return edit


@dataclass(frozen=True)
class CardReport:
    card_id: str
    scope_id: str
    body_sections: tuple[str, ...]        # section_path 精确名
    summary_sections: tuple[str, ...]
    authorized_locations: tuple[str, ...]
    summary_authorized_locations: tuple[str, ...]  # 提案命中的精确摘要段（写入器严格化用）
    hits: int
    proposal_ids: tuple[str, ...]
    diagnostics: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class EngineResult:
    source_sha256: str
    engine_version: str
    proposals: tuple[EditProposal, ...]
    scope: dict[str, Any]                 # direct_write_scope_v2
    card_reports: tuple[CardReport, ...]
    diagnostics: tuple[dict[str, Any], ...]   # 仅内部运维台账
    stats: dict[str, Any]
    not_applicable: dict[str, Any] | None = None   # FL-D1064 品种不适用明确边界（非失败）
    exceptions: tuple[dict[str, Any], ...] = ()    # FL-D1075 审查连续否决的放弃目标清单

    def proposal_dicts(self) -> list[dict[str, Any]]:
        return [p.to_dict() for p in self.proposals]


# ---------------------------------------------------------------------------
# 纯结构件：章节索引 / 屏障清理 / 窗口 / 引文回解（自包含，不依赖旧引擎）

@dataclass(frozen=True)
class Section:
    section_id: str
    title: str            # == inspect section_path（写入器 scope 按此精确匹配）
    zone: str             # "body" | "summary"
    locations: tuple[str, ...]
    preview: str
    level: int = 1        # 1=章级（docx section_path 直接可见）；2=节级（引擎内子标题切分）
    parent_id: str = ""   # 节级→父级章唯一路径；章级=自身 id


_SUBHEAD_CANDIDATES: tuple[re.Pattern, ...] = (
    re.compile(r"^第[一二三四五六七八九十百零〇\d]+节\s*.{0,24}$"),
    re.compile(r"^[一二三四五六七八九十]+[、．.]\s*[^\s。；：]{2,24}$"),
    re.compile(r"^（[一二三四五六七八九十]+）\s*[^\s。；：]{2,24}$"),
    re.compile(r"^\d+(?:\.\d+)+\s*[^\s。；：]{2,24}$"),
)


def _is_subheading(text: str) -> bool:
    plain = re.sub(r"\s+", "", text.strip())
    if not (2 <= len(plain) <= 30) or "。" in plain:
        return False
    return any(p.match(plain) for p in _SUBHEAD_CANDIDATES)


def _build_sections(inspection: DocumentInspection) -> list[Section]:
    """两级章节索引：章级（zone+section_path 连段）+ 节级（章内子标题切分，保守判标题）。

    节级 id=T，父级=所属章级 id；摘要区小节本身即为 docx 可见标题，视作章级档（沿用旧语义）。
    """
    zones: list[tuple[str, str, list[ParagraphSpan]]] = []
    cur: list[ParagraphSpan] = []
    cur_key: tuple[str, str] | None = None
    for span in inspection.paragraphs:
        if span.zone not in ("body", "summary"):
            continue
        if not re.fullmatch(r"(?:p\d+|tbl\d+/r\d+/c\d+/p\d+)", span.location):
            # 释义两栏表格等蓝胞段落 = tblX/rY/cZ/pW 位置语义（scope 闸同守——
            # 自身 zone/section_path 由 docx 投影给出，只有见即可能被授权）
            continue
        key = (span.zone, span.section_path or "")
        if cur_key is not None and key != cur_key:
            zones.append((cur_key[0], cur_key[1], cur))
            cur = []
        cur_key = key
        cur.append(span)
    if cur:
        zones.append((cur_key[0], cur_key[1], cur))

    sections: list[Section] = []

    def preview(spans: list[ParagraphSpan]) -> str:
        return " ".join(p.text.strip() for p in spans if p.text.strip())[:120]

    for zone, title, spans in zones:
        chapter_id = f"S{len(sections) + 1:02d}"
        parent: Section | None = None
        sub_runs: list[list[ParagraphSpan]] = []
        sub_titles: list[str] = []
        if zone == "body" and len(spans) >= 3:
            pending: list[ParagraphSpan] = []
            pending_title = ""
            for span_obj in spans:
                plain = span_obj.text.strip()
                if _is_subheading(plain):
                    if pending:
                        sub_runs.append(pending)
                        sub_titles.append(pending_title)
                    pending, pending_title = [span_obj], plain
                else:
                    pending.append(span_obj)
            if pending or pending_title:
                sub_runs.append(pending)
                sub_titles.append(pending_title)
            if len(sub_runs) <= 1:
                sub_runs, sub_titles = [], []
        if zone != "body" or len(sub_runs) <= 1:
            parent = Section(section_id=chapter_id, title=title, zone=zone,
                             locations=tuple(p.location for p in spans),
                             preview=preview(spans), level=1, parent_id=chapter_id)
            sections.append(parent)
            continue
        # 节级拆分成立：父级章作为聚合节点（locations=全章，level=1），节为 level=2
        parent = Section(section_id=chapter_id, title=title, zone=zone,
                         locations=tuple(p.location for p in spans),
                         preview=preview(spans), level=1, parent_id=chapter_id)
        sections.append(parent)
        head_title = sub_titles[0] or f"{title}（章首）"
        for idx, (run, stitle) in enumerate(zip(sub_runs, sub_titles)):
            if not run:
                continue
            sections.append(Section(
                section_id=f"T{len(sections) + 1:03d}",
                title=(stitle if stitle else head_title)[:60] or f"{title}（段组{idx + 1}）",
                zone=zone, locations=tuple(p.location for p in run),
                preview=preview(run), level=2, parent_id=chapter_id))
    return sections


def _strip_barriers(text: str) -> tuple[str, list[int]]:
    """去 \ufff9 屏障；返回 (clean, clean_char_index -> raw_offset) 映射。"""
    clean_chars: list[str] = []
    index_map: list[int] = []
    for i, ch in enumerate(text):
        if ch == BARRIER:
            continue
        clean_chars.append(ch)
        index_map.append(i)
    return "".join(clean_chars), index_map


@dataclass(frozen=True)
class _Window:
    window_id: str
    locations: tuple[str, ...]
    text: str          # 渲染为 "[pN] <clean text>" 行


def _build_windows(locations: Sequence[str], span_by_loc: Mapping[str, ParagraphSpan],
                   max_chars: int) -> list[_Window]:
    windows: list[_Window] = []
    cur: list[str] = []
    cur_chars = 0
    for loc in locations:
        span = span_by_loc[loc]
        clean, _ = _strip_barriers(span.text)
        line = f"[{loc}] {clean.strip()}"
        need = len(line) + 1
        if cur and cur_chars + need > max_chars:
            windows.append(_make_window(len(windows), cur, span_by_loc))
            # 相邻窗一段重叠，防窗口交界漏目标
            cur = [cur[-1]]
            cur_chars = len(f"[{cur[0]}] ") + len(_strip_barriers(span_by_loc[cur[0]].text)[0].strip()) + 1
            cur.append(loc)
            cur_chars += need
        else:
            cur.append(loc)
            cur_chars += need
    if cur:
        windows.append(_make_window(len(windows), cur, span_by_loc))
    return windows


def _make_window(idx: int | str, locations: Sequence[str],
                 span_by_loc: Mapping[str, ParagraphSpan]) -> _Window:
    lines = [f"[{loc}] {_strip_barriers(span_by_loc[loc].text)[0].strip()}" for loc in locations]
    window_id = f"W{idx + 1}" if isinstance(idx, int) else str(idx)
    return _Window(window_id=window_id, locations=tuple(locations), text="\n".join(lines))


_SENTENCE_END = "。；！？!?；\n"


def _sentences(clean: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    start = 0
    for i, ch in enumerate(clean):
        if ch in _SENTENCE_END:
            end = i + 1
            seg = clean[start:end]
            if seg.strip():
                out.append((start, end, seg))
            start = end
    if start < len(clean) and clean[start:].strip():
        out.append((start, len(clean), clean[start:]))
    return out


_CATEGORY_GAP = r"(?:[A-Z]\s?类(?:基金份额)?|类|份额)?"


def _category_gap_pattern(compact_quote: str) -> str:
    """引用逐字转义，字间嵌入类别词/份额可选插槽（容错匹配用）。"""
    body = _CATEGORY_GAP.join(re.escape(ch) for ch in compact_quote)
    return _CATEGORY_GAP + body + _CATEGORY_GAP


def _compact_positions(text: str) -> tuple[str, list[int]]:
    chars: list[str] = []
    pos: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        chars.append(ch)
        pos.append(i)
    return "".join(chars), pos


def _resolve_quote(span_text: str, quote: str) -> tuple[int, int] | None:
    """把模型引句回解为段落投影原坐标 (start,end)；失败返回 None。"""
    q = quote.strip()
    if not q:
        return None
    clean, index_map = _strip_barriers(span_text)

    def clean_to_raw(cs: int, ce: int) -> tuple[int, int] | None:
        if not (0 <= cs < ce <= len(index_map)):
            return None
        return index_map[cs], index_map[ce - 1] + 1

    # 1) 精确
    idx = clean.find(q)
    if idx >= 0:
        return clean_to_raw(idx, idx + len(q))
    # 2) 去空白匹配
    compact_q, _ = _compact_positions(q)
    compact_t, pos = _compact_positions(clean)
    idx = compact_t.find(compact_q)
    if idx >= 0:
        cs, ce = pos[idx], pos[idx + len(compact_q) - 1] + 1
        return clean_to_raw(cs, ce)
    # 2.5) 类别词插入容错匹配（语料硬破损带，ca-corpus 优化令§2.1：裸锚命中 80.2%、
    # 类别词插入变体 ~100%——“前一日A类基金份额资产净值”≡“前一日基金资产净值”）。
    # 逐字之间允许插入 `[A-Z]\s?类(基金份额)?` / 单个“类” / 单个“份额”。
    compact_t, cpos = _compact_positions(clean)
    if compact_q and len(compact_q) >= 6:
        pattern = _category_gap_pattern(compact_q)
        m = re.search(pattern, compact_t)
        if m:
            cs, ce = cpos[m.start()], cpos[m.end() - 1] + 1
            return clean_to_raw(cs, ce)
    # 3) 句子级模糊（合同与指引措辞不同也要能定位；阈值宁高）
    q_norm = re.sub(r"\s+", "", q)
    best: tuple[float, int, int] | None = None
    for s, e, seg in _sentences(clean):
        seg_norm = re.sub(r"\s+", "", seg)
        if not seg_norm:
            continue
        quick = difflib.SequenceMatcher(None, q_norm, seg_norm).quick_ratio()
        if quick >= 0.80:
            ratio = difflib.SequenceMatcher(None, q_norm, seg_norm).ratio()
            if best is None or ratio > best[0]:
                best = (ratio, s, e)
    if best and best[0] >= 0.85:
        return clean_to_raw(best[1], best[2])
    return None


def _last_sentence_range(span: ParagraphSpan) -> tuple[int, int] | None:
    """段落末可写句的原坐标范围（须整句落在同一可写 segment，否则 None）。"""
    clean, index_map = _strip_barriers(span.text)
    sentences = _sentences(clean)
    if not sentences:
        return None
    s, e, _ = sentences[-1]
    if not index_map:
        return None
    raw_s, raw_e = index_map[s], index_map[e - 1] + 1
    if not any(seg.start <= raw_s and raw_e <= seg.end for seg in span.segments):
        return None
    return (raw_s, raw_e)


def _section_append_hits(scope: _CardScope, sections: Sequence[Section],
                         span_by_loc: Mapping[str, ParagraphSpan],
                         hits: list[_Hit], diagnostics: list[dict[str, Any]]) -> None:
    """裁决定形的 section-append：锚定绑定章节最后一个可写段落的段尾之后。"""
    bound = ([s for s in sections if s.title in scope.body_titles]
             or [s for s in sections if s.title in scope.summary_titles])
    for section in bound:
        made = False
        for loc in reversed(section.locations):
            span = span_by_loc[loc]
            if not span.editable:
                continue
            rng = _last_sentence_range(span)
            if rng is None:
                diagnostics.append({"card_id": scope.card.card_id, "stage": "section_append",
                                    "location": loc, "code": "section_append_no_anchor",
                                    "note": "末可写段尾部无法锚定，本节跳过（卡保留）"})
                made = True
                break
            hits.append(_Hit(card=scope.card, location=loc, zone=span.zone,
                             action="insert_after",
                             quote=span.text[rng[0]:rng[1]], quote_range=rng,
                             edit_range=(rng[1], rng[1]), stage="section_append"))
            made = True
            break
        if not made:
            diagnostics.append({"card_id": scope.card.card_id, "stage": "section_append",
                                "section": section.title, "code": "section_append_no_anchor",
                                "note": "绑定章节内无可写段落，无提案但卡保留"})


def _confirm_insert_anchor(hit: _Hit, span_by_loc: Mapping[str, ParagraphSpan],
                           gw: _GatewayWrap, diagnostics: list[dict[str, Any]]) -> bool:
    """insert 类补扫候选的主模型锚点确认（恒主池调用；失败保守丢弃存疑候选）。"""
    span = span_by_loc[hit.location]
    clean, _ = _strip_barriers(span.text)
    context = (f"{_card_block(hit.card)}\n\n[段落 {hit.location}]\n{clean.strip()}\n\n"
               f"[候选锚点引句]\n{hit.quote}")
    try:
        result = gw.call_idempotent(
            task_type="direct_anchor_confirm", diagnostics=diagnostics,
            context=context, schema=_ANCHOR_CONFIRM_SCHEMA,
            instruction=_ANCHOR_CONFIRM_INSTRUCTION,
            prompt_version=_PROMPT_VERSION_ANCHOR_CONFIRM)
        value = result.value if hasattr(result, "value") else result
        keep = bool(value.get("keep"))
    except Exception as exc:
        keep = False
        diagnostics.append({"card_id": hit.card.card_id, "stage": "anchor_confirm",
                            "location": hit.location,
                            "code": getattr(exc, "code", type(exc).__name__),
                            "note": "锚点确认调用失败，保守丢弃该补扫插入候选"})
        return keep
    if not keep:
        diagnostics.append({"card_id": hit.card.card_id, "stage": "anchor_confirm",
                            "location": hit.location, "code": "anchor_confirmation_rejected",
                            "quote": hit.quote[:60],
                            "note": "主模型复核否决该补扫插入候选，丢弃"})
    return keep


# 零领域词汇自查用黑名单（与测试断言共用）
_REVIEW_FORBIDDEN_TERMS = ("销售服务费", "份额类别", "费率", "申购费", "赎回费", "基金")


_FORMULA_VAR_RE = re.compile(r"([A-Z])\s*[＝=]")


def _review_dependency_hint(proposal: EditProposal, span: ParagraphSpan,
                            span_by_loc: Mapping[str, ParagraphSpan]) -> str:
    """D2 依赖事实注入（非机械门）：原句是公式/计算方法的锚句，而相邻段仍含公式行
    或引用该句定义的记号——把这一依存事实显式给审查模型。"""
    if proposal.action != "delete" and not proposal.expected_old_text:
        return ""
    old = proposal.expected_old_text or ""
    hints: list[str] = []
    loc = proposal.location
    match = re.fullmatch(r"p(\d+)", loc)
    neighbors: list[ParagraphSpan] = []
    if match:
        n = int(match.group(1))
        for off in (-2, -1, 1, 2):
            nb = span_by_loc.get(f"p{n + off}")
            if nb is not None:
                neighbors.append(nb)
    # 依赖变体 A：句为“计算方法/公式如下”类入口，相邻段仍含公式行
    if "如下" in old and any(_FORMULA_VAR_RE.search(nb.text) for nb in neighbors):
        marks = sorted({m.group(1) for nb in neighbors
                       for m in _FORMULA_VAR_RE.finditer(nb.text)})
        hints.append(f"[依赖说明] 原句为公式/计算方法入门（含“如下”），"
                     f"相邻段仍含公式记号{''.join(marks)}＝，删除将使这些行失去锚句。")
    # 依赖变体 B：句内定义某字母变量（X为……），相邻段仍写该字母的公式
    defined: set[str] = set()
    for m in re.finditer(r"([A-Z])为[一-龥A-Za-z０-９]", old):
        defined.add(m.group(1))
    used_elsewhere = [
        (d, nb.location) for d in sorted(defined) for nb in neighbors
        if re.search(re.escape(d) + r"\s*[＝=]", nb.text)
    ]
    if used_elsewhere:
        d, nb_loc = used_elsewhere[0]
        hints.append(f"[依赖说明] 原句定义变量 {d}，相邻段 {nb_loc} 仍在公式中使用 {d}＝，"
                     "删除将使公式失去变量定义。")
    return "\n".join(hints)


def _review_neighborhood(proposal: EditProposal,
                         span_by_loc: Mapping[str, ParagraphSpan]) -> str:
    """目标段全文+相邻段（含 D1 相邻重复判据所需的邻里）。"""
    span = span_by_loc.get(proposal.location)
    if span is None:
        return ""
    match = re.fullmatch(r"p(\d+)", proposal.location)
    lines = []
    for offset in (-1, 0, 1):
        neighbor = span_by_loc.get(f"p{int(match.group(1)) + offset}") if match else None
        if neighbor is None:
            continue
        label = proposal.location if offset == 0 else f"{neighbor.location}(相邻)"
        lines.append(f"<{label}> {_strip_barriers(neighbor.text)[0].strip()[:800]}")
    return "\n\n".join(lines)


def _review_proposal(proposal: EditProposal, card: AtomicCard,
                     span: ParagraphSpan, share_fact_text: str,
                     gw, diagnostics: list[dict[str, Any]],
                     span_by_loc: Mapping[str, ParagraphSpan] | None = None) -> bool:
    """提案级模型审查（FL-D1075）：一次审查调用；失败放行+review_unavailable。"""
    original = proposal.expected_old_text or (proposal.anchor or {}).get("text", "")
    neighborhood = (_review_neighborhood(proposal, span_by_loc)
                    if span_by_loc else _strip_barriers(span.text)[0].strip()[:1200])
    # FL-D1079-B 加固（量级事实，审查可稳定初判「拟删范围超卡指向」；
    # 属事实注入而非机械门，最终 veto 仍由审查模型判）
    old_len = len(_compact_positions(original)[0]) if original else 0
    anchor_hint = card.anchor_quote or (card.locator_quotes[0] if card.locator_quotes else "")
    anchor_len = len(_compact_positions(anchor_hint)[0]) if anchor_hint else 0
    magnitude = (f"[提案量级] 拟修改范围 {old_len} 字；"
                 f"指引卡删除/替换指向 {anchor_len} 字。")
    dependency = (_review_dependency_hint(proposal, span, span_by_loc)
                  if span_by_loc else "")
    context = (
        f"[原句]\n{original}\n\n[新文]\n{proposal.replacement or '（删除该句）'}\n\n"
        f"[指引卡原文]\n{_card_block(card)}\n\n"
        f"[合同事实]\n{share_fact_text or '（无）'}\n\n"
        f"{magnitude}\n"
        + (f"{dependency}\n\n" if dependency else "\n")
        + f"[上下文（含相邻段）]\n{neighborhood}"
    )
    try:
        result = gw.call_idempotent(
            task_type="direct_review", diagnostics=diagnostics,
            context=context, schema=_REVIEW_SCHEMA,
            instruction=_REVIEW_INSTRUCTION,
            prompt_version=_PROMPT_VERSION_REVIEW)
        value = result.value if hasattr(result, "value") else result
        verdict = str(value.get("verdict") or "accept")
        reason = str(value.get("reason") or "")[:200]
    except Exception as exc:
        diagnostics.append({"stage": "review", "card_id": proposal.rule_card_id,
                            "location": proposal.location,
                            "code": "review_unavailable",
                            "cause": getattr(exc, "code", type(exc).__name__),
                            "note": "审查调用失败，放行（误杀比漏杀更贵）"})
        return True
    if verdict == "veto":
        diagnostics.append({"stage": "review", "card_id": proposal.rule_card_id,
                            "location": proposal.location,
                            "code": "review_veto", "reason": reason,
                            "note": "提案级审查否决，不写入（落诊断可检索）"})
        return False
    return True


_REVIEW_MAX_ATTEMPTS = 2  # 产出尝试硬顶（含原改写；否决理由反馈自我修正）


def _review_proposals(proposals: Sequence[EditProposal],
                      card_by_id: Mapping[str, AtomicCard],
                      span_by_loc: Mapping[str, ParagraphSpan],
                      regenerate: Mapping[str, Any] | None,
                      share_fact_text: str, gw,
                      diagnostics: list[dict[str, Any]]
                      ) -> tuple[list[EditProposal], list[dict[str, Any]]]:
    """提案级审查：veto → 理由反馈自我修正（≤2 次产出尝试）→ 仍不过 → 例外清单。

    返回 (保留提案, 例外清单)。例外=放弃该处目标，原文不动，仅留目标/卡/理由/次数。
    delete 型无可修正文本，一次否决即入例外。
    """
    kept: list[EditProposal] = []
    exceptions: list[dict[str, Any]] = []

    def exception_for(p: EditProposal, reasons: list[str], attempts: int) -> None:
        loc_text = span_by_loc[p.location].text if p.location in span_by_loc else ""
        exceptions.append({
            "proposal_id": p.proposal_id, "rule_card_id": p.rule_card_id,
            "action": p.action, "location": p.location, "zone": p.zone,
            "original_excerpt": (p.expected_old_text or loc_text)[:120],
            "veto_reasons": list(reasons), "attempts": attempts,
            "note": "审查连续否决，放弃该处目标，原文保留不动",
        })

    for proposal in proposals:
        card = card_by_id.get(proposal.rule_card_id)
        span = span_by_loc.get(proposal.location)
        if card is None or span is None:
            kept.append(proposal)
            continue
        reasons: list[str] = []
        current = proposal
        attempts = 1
        while True:
            keep = _review_proposal(current, card, span, share_fact_text, gw, diagnostics,
                                    span_by_loc=span_by_loc)
            if keep:
                kept.append(current)
                break
            # _review_proposal 已记 review_veto；取最新一条理由做修正输入
            reasons.append(next((d.get("reason") for d in reversed(diagnostics)
                                 if d.get("code") == "review_veto"
                                 and d.get("location") == proposal.location), ""))
            regen = (regenerate or {}).get(current.proposal_id)
            if attempts >= _REVIEW_MAX_ATTEMPTS or regen is None \
                    or not current.replacement:
                exception_for(current, reasons, attempts)
                break
            attempts += 1
            reason = reasons[-1]
            new_text = regen(extra_warning=(
                f"\n[审查否决后的修正要求] 上一次产出被审查否决，理由：{reason}。"
                "请修正后重新生成，仍须完全满足原卡要求。\n") if reason else "")
            if new_text is None or new_text == current.replacement:
                exception_for(current, reasons, attempts)
                break
            current = replace(current, replacement=new_text)
        continue
    return kept, exceptions


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# 提示词（新引擎专属；无 G 编号/固定章节/固定措辞依赖）

_SCOPE_SCHEMA = {
    "type": "object", "required": ["body_sections", "summary_sections"],
    "additionalProperties": False,
    "properties": {
        "body_sections": {"type": "array", "items": {"type": "string"}},
        "summary_sections": {"type": "array", "items": {"type": "string"}},
    },
}
_HITS_SCHEMA = {
    "type": "object", "required": ["hits"], "additionalProperties": False,
    "properties": {"hits": {"type": "array", "items": {
        "type": "object", "required": ["card_id", "location", "quote"], "additionalProperties": False,
        "properties": {"card_id": {"type": "string"}, "location": {"type": "string"},
                       "quote": {"type": "string"}}}}},
}
_REWRITE_SCHEMA = {
    "type": "object", "required": ["edits"], "additionalProperties": False,
    "properties": {"edits": {"type": "array", "items": {
        "type": "object", "required": ["group_id", "new_text"], "additionalProperties": False,
        "properties": {"group_id": {"type": "string"}, "new_text": {"type": "string"}}}}},
}

_SCOPE_INSTRUCTION = (
    "你是基金合同章节绑定助手。给定一条原子规则卡和合同的两级章节索引（编号、章/节层级"
    "与父级、类型、标题、预览；类型含 body=正文、summary=基金合同内容摘要内小节）。"
    "合同目录只用于判断规则对应哪一章，不构成任何修改授权。"
    "规则：只从给定章节编号中选择与该规则事项直接相关的正文条目（body_sections），"
    "以及该事项**对应的**摘要小节（summary_sections）。"
    "摘要不默认全开：只有与规则事项语义对应的摘要小节才可选择。"
    "指引明确涉及多个章节时全部选上；不得因其他章节出现相同或相似语句而扩域。"
    "粒度规则（保守宁粗勿细）：只有当卡内线索（章节线索/引句）与某个节级条目标题清晰、"
    "唯一对应时才可选节级(T 开头)编号；信心不足、事项横跨多节或节级标题不精确时选其父级"
    "章级(S 开头)编号；严禁杜撰不在索引中的编号。都不相关时返回空数组。只返回 JSON。"
)

_LOCATE_INSTRUCTION = (
    "你在合同授权章节的**一个窗口**内做多卡目标定位。段落以 [pN] 编号给出；窗口前置列出"
    "多张规则卡（各带 card_id/动作/条件/要求/引句线索）。逐卡找出该窗口内**所有**可能需要"
    "处理的句子：replace=需替换的句子，delete=需删除的句子，insert_before/insert_after="
    "作为插入锚点的句子。规则：\n"
    "1) 每条命中返回 card_id、段落编号和该句**原文引句**（必须与窗口所示文字逐字一致、连续）；\n"
    "2) 只返回与该 card_id 事项真正相关的句子；\n"
    "3) 宁多勿漏；合同措辞与指引引句不同也要按语义识别（含锚句中类别词插入——如"
    "“按前一日A类/C类基金份额资产净值”与“按前一日基金资产净值”视为同一目标句）；"
    "不要修改文字、不要解释、不要输出窗口外内容。"
    "只返回 JSON。"
)

_SWEEP_INSTRUCTION = (
    "对同一窗口做**遗漏补扫**：下方按卡列出本轮已找到的目标引句；请继续检查窗口内是否还有"
    "与各卡事项相关、需要处理但**尚未列出**的句子。只返回新增目标（同格式 card_id+段落编号+"
    "逐字引句），已列出的不要重复；确认无遗漏时返回空 hits。只返回 JSON。"
)

_REWRITE_INSTRUCTION = (
    "按每组给出的原始文字与规则卡要求，生成替换/插入文本。\n"
    "硬约束：\n"
    "1) 新文本中的事实不得超出规则卡与原文：不得引入双方均未出现的具体费率、数值、日期、"
    "份额类别名称或当事人名称；\n"
    "2) 只处理给定位置，不重写整章、不润色相邻句子、不顺手统一其他内容；\n"
    "3) 替换组：输出替换原句后的完整新句；插入组：只输出要插入的新句子本身（不含锚点句）；\n"
    "4) 保持合同语境、条款编号与句式风格；不要求与指引文字逐字一致。\n"
    "只返回 JSON。"
)


# ---------------------------------------------------------------------------
# 模型网关包装

@dataclass
class _GatewayWrap:
    gateway: Any
    secondary: Any = None               # 副模型池（FUNDLEX_MODEL_SECONDARY；无则单池）
    calls: int = 0
    failures: int = 0
    calls_by_pool: dict[str, int] = field(default_factory=lambda: {"primary": 0, "secondary": 0})

    @property
    def context_limit(self) -> int:
        limit = getattr(self.gateway, "max_context_chars", 12000)
        return max(1000, int(limit) - 200)

    @property
    def pool_count(self) -> int:
        return 2 if self.secondary is not None else 1

    #: 定位/补扫薄层预算（施工令③：1500→600；真长引文回退 1500，不可改回源结果）
    TOKEN_TIER_SMALL = 600
    TOKEN_TIER_BIG = 1500

    def tier_gateway(self, target: Any, tokens: int) -> Any:
        """按目标池克隆只读令牌层网关（共享连接与账本，线程安全）；
        非 ModelGateway 目标（测试替身等）直接返回原对象。"""
        if not hasattr(target, "base_url") or not hasattr(target, "api_key"):
            return target
        key = (id(target), tokens)
        cached = getattr(self, "_tier_cache", None) or {}
        if key in cached:
            return cached[key]
        from .model import ModelGateway
        clone = ModelGateway(
            base_url=target.base_url, model=target.model, api_key=target.api_key,
            max_context_chars=target.max_context_chars, max_calls=target.max_calls,
            max_completion_tokens=tokens,
            timeout_s=target.timeout_s, retries=target.retries,
            client=getattr(target, "_client", None), budget=getattr(target, "budget", None),
            provider=getattr(target, "provider", ""),
            request_options=dict(getattr(target, "request_options", {}) or {}),
            extra_headers=dict(getattr(target, "extra_headers", {}) or {}),
            user_agent=getattr(target, "user_agent", None) or None,
            enforce_calls=getattr(target, "enforce_calls", False))
        cached[key] = clone
        self._tier_cache = cached
        return clone

    def call_tiered(self, *, task_type: str, context: str, schema: dict,
                    instruction: str, prompt_version: str,
                    tokens: int | None = None, pool_index: int | None = None) -> Any:
        """带令牌层的池分配调用（tokens 仅用于 locate/sweep 类薄层任务）。"""
        target = self.gateway
        pool_name = "primary"
        if pool_index is not None and self.secondary is not None and pool_index % 2 == 1:
            target = self.secondary
            pool_name = "secondary"
        if tokens is not None:
            target = self.tier_gateway(target, tokens)
        self.calls += 1
        self.calls_by_pool[pool_name] += 1
        return target.call(task_type=task_type, bounded_context=context,
                           response_schema=schema, instruction=instruction,
                           prompt_version=prompt_version)

    def call(self, *, task_type: str, context: str, schema: dict, instruction: str,
             prompt_version: str, pool_index: int | None = None) -> Any:
        self.calls += 1
        target = self.gateway
        pool_name = "primary"
        if pool_index is not None and self.secondary is not None and pool_index % 2 == 1:
            target = self.secondary
            pool_name = "secondary"
        self.calls_by_pool[pool_name] += 1
        return target.call(task_type=task_type, bounded_context=context,
                           response_schema=schema, instruction=instruction,
                           prompt_version=prompt_version)

    def call_idempotent(self, *, pool_index: int | None = None,
                        diagnostics: list[dict[str, Any]] | None = None,
                        tokens: int | None = None, **kwargs) -> Any:
        """只读型调用的限流/瞬断引擎级有限重试（有界；不改写状态，重试安全）。
        副池失败后降级回主池一次（单模型兜底=不降级召回）。"""
        transient = {"MODEL_NETWORK_ERROR", "MODEL_HTTP_ERROR", "MODEL_RETRY_EXHAUSTED"}

        def dispatch() -> Any:
            if tokens is not None or pool_index is not None:
                return self.call_tiered(pool_index=pool_index, tokens=tokens, **kwargs)
            return self.call(**kwargs)

        for attempt in range(4):
            try:
                return dispatch()
            except Exception as exc:
                code = getattr(exc, "code", "")
                if code == "MODEL_CONCURRENCY_LIMIT" and attempt < 3:
                    # 账本并发槽暂时打满：退避后重试（有界，不空转）
                    time.sleep(2.0 + 2.0 * attempt)
                    continue
                if code == "MODEL_CIRCUIT_OPEN" and attempt < 3:
                    # 账本熔断（冷却 120s 级）：长退避跨过冷却（有界）
                    time.sleep(25.0 + 15.0 * attempt)
                    continue
                if code in transient and attempt < 1:
                    time.sleep(1.0 + attempt)
                    continue
                if (pool_index is not None and pool_index % 2 == 1
                        and self.secondary is not None):
                    if diagnostics is not None:
                        diagnostics.append({"stage": "pool", "code": "pool_fallback",
                                            "from_pool": "secondary", "to_pool": "primary",
                                            "cause": code,
                                            "note": "副池调用失败降级回主池"})
                    return self.call(pool_index=0, **kwargs)
                raise


def _build_secondary_gateway(primary: Any, diagnostics: list[dict[str, Any]]) -> Any:
    """按 FUNDLEX_MODEL_SECONDARY（当前 glm-5.3）从主网关克隆副池：
    同源同端点同密钥，共享 httpx 连接与 ModelBudget（账本升并发 8 供双池）。"""
    model_id = (os.environ.get("FUNDLEX_MODEL_SECONDARY") or "").strip()
    if not model_id:
        return None
    try:
        from .model import ModelGateway
        budget = getattr(primary, "budget", None)
        if budget is not None and getattr(budget, "concurrency", 0):
            budget.concurrency = max(int(budget.concurrency), 8)
        return ModelGateway(
            base_url=primary.base_url, model=model_id, api_key=primary.api_key,
            max_context_chars=primary.max_context_chars, max_calls=primary.max_calls,
            max_completion_tokens=primary.max_completion_tokens,
            timeout_s=primary.timeout_s, retries=primary.retries,
            client=getattr(primary, "_client", None), budget=budget,
            provider=getattr(primary, "provider", ""),
            request_options=dict(getattr(primary, "request_options", {}) or {}),
            extra_headers=dict(getattr(primary, "extra_headers", {}) or {}),
            user_agent=getattr(primary, "user_agent", None) or None,
            enforce_calls=getattr(primary, "enforce_calls", False))
    except Exception as exc:
        diagnostics.append({"stage": "pool", "code": "secondary_pool_unavailable",
                            "cause": getattr(exc, "code", type(exc).__name__),
                            "note": "副模型池构建失败，回退单模型（不降级召回）"})
        return None

    def call_idempotent(self, **kwargs) -> Any:
        """只读型调用的限流/瞬断引擎级有限重试（有界；不改写状态，重试安全）。"""
        transient = {"MODEL_NETWORK_ERROR", "MODEL_HTTP_ERROR", "MODEL_RETRY_EXHAUSTED"}
        for attempt in range(4):
            try:
                return self.call(**kwargs)
            except Exception as exc:
                code = getattr(exc, "code", "")
                if code == "MODEL_CONCURRENCY_LIMIT" and attempt < 3:
                    # 账本并发槽暂时打满：退避后重试（有界，不空转）
                    time.sleep(2.0 + 2.0 * attempt)
                    continue
                if code in transient and attempt < 1:
                    time.sleep(1.0 + attempt)
                    continue
                raise


# ---------------------------------------------------------------------------
# 引擎主体

@dataclass(frozen=True)
class _CardScope:
    card: AtomicCard
    scope_id: str
    body_titles: tuple[str, ...]
    summary_titles: tuple[str, ...]
    locations: frozenset                  # 授权段落 location 全集
    summary_locations: frozenset          # 其中摘要段
    bound_ids: tuple[str, ...] = ()       # 绑定的索引条目 id（含节级 T）


@dataclass(frozen=True)
class _Hit:
    card: AtomicCard
    location: str
    zone: str
    action: str
    quote: str
    quote_range: tuple[int, int]          # 引句在段落投影坐标中的范围
    edit_range: tuple[int, int]           # 替换/删除=引句范围；插入=(pos,pos)
    stage: str                            # locate | sweep


@dataclass
class _Group:
    location: str
    start: int
    end: int
    members: list[_Hit] = field(default_factory=list)


def _scope_map(card: AtomicCard, sections: Sequence[Section], gw: _GatewayWrap,
               diagnostics: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    id_parent = {s.section_id: s for s in sections}
    listing = "\n".join(
        f"{s.section_id} | {'章' if s.level == 1 else '节(属' + s.parent_id + ')'} | {s.zone} | "
        f"{s.title} | {len(s.locations)}段 | {s.preview}"
        for s in sections
    )
    context = (
        f"[规则卡 {card.card_id}]\n标题:{card.title}\n适用条件:{card.applicability}\n"
        f"章节线索:{';'.join(card.section_hints) or '（无）'}\n"
        f"定位引句:{'；'.join(card.locator_quotes) or '（无）'}\n"
        f"修改要求:{card.requirement or '（删除）'}\n\n[章节索引]\n{listing}"
    )
    known = {s.section_id for s in sections}
    try:
        result = gw.call_idempotent(task_type="direct_scope_map", context=context,
                                    schema=_SCOPE_SCHEMA,
                                    instruction=_SCOPE_INSTRUCTION,
                                    prompt_version=_PROMPT_VERSION_SCOPE)
        value = result.value if hasattr(result, "value") else result
        body = [x for x in value.get("body_sections", []) if x in known]
        summary = [x for x in value.get("summary_sections", []) if x in known]
        dropped = [x for x in (value.get("body_sections", []) + value.get("summary_sections", []))
                   if x not in known]
        if dropped:
            diagnostics.append({"card_id": card.card_id, "stage": "scope_map",
                                "code": "fabricated_section_dropped", "ids": dropped,
                                "note": "秦撰章节/节编号丢弃（索引外）"})
        if body or summary:
            return sorted(set(body)), sorted(set(summary))
        diagnostics.append({"card_id": card.card_id, "stage": "scope_map",
                            "code": "scope_map_empty", "note": "模型未绑定任何章节，启用章节线索回退"})
    except Exception as exc:  # ModelError 及未知技术故障：回退，不中断
        diagnostics.append({"card_id": card.card_id, "stage": "scope_map",
                            "code": getattr(exc, "code", type(exc).__name__),
                            "note": "scope_map 调用失败，启用章节线索回退"})
    return _fallback_scope(card, sections, diagnostics)


def _fallback_scope(card: AtomicCard, sections: Sequence[Section],
                    diagnostics: list[dict[str, Any]] | None = None) -> tuple[list[str], list[str]]:
    body: list[str] = []
    summary: list[str] = []
    hints = [h.strip() for h in card.section_hints if h.strip()]
    if not hints:
        return body, summary
    matched: list[Section] = []
    for s in sections:
        title = re.sub(r"\s+", "", s.title)
        if not title:
            continue  # 空标题：空串恒真属于任何提示词，杜绝封面段误绑（FL-D1080 附录）
        if any(h in title or title in h or (h in title.replace("的", "")) for h in hints):
            matched.append(s)
    # 跨章同名节歧义：节级同名属不同父章时不映射，仅记诊断（保守回章级/不绑）
    sub_matches = [s for s in matched if s.level == 2]
    if sub_matches:
        by_title: dict[str, set[str]] = {}
        for s in sub_matches:
            by_title.setdefault(re.sub(r"\s+", "", s.title), set()).add(s.parent_id)
        ambiguous = {t for t, parents in by_title.items() if len(parents) > 1}
        if ambiguous:
            matched = [s for s in matched
                       if s.level == 1 or re.sub(r"\s+", "", s.title) not in ambiguous]
            if diagnostics is not None:
                diagnostics.append({"card_id": card.card_id, "stage": "scope_map",
                                    "code": "subsection_hint_ambiguous",
                                    "titles": sorted(ambiguous),
                                    "note": "跨章同名节歧义，节级不映射仅诊断为道"})
    for s in matched:
        (body if s.zone == "body" else summary).append(s.section_id)
    return body, summary


def _family_key(card: AtomicCard) -> str | None:
    """同一指引目标的互斥分支卡族：同锚点/同定位引句（足够长才算，‘-’等占位不算）。
    族内一卡命中即全族同组改写，模型按各卡适用条件与合同事实选分支。"""
    for raw in ([card.anchor_quote] if card.anchor_quote else []) or list(card.locator_quotes[:1]):
        compact, _ = _compact_positions(raw)
        if len(compact) >= 8:
            return compact[:60]
    return None


def _card_block(card: AtomicCard) -> str:
    return (
        f"[规则卡 {card.card_id}] 动作={card.action}\n标题:{card.title}\n"
        f"适用条件:{card.applicability}\n要求:{card.requirement or '（删除目标句）'}\n"
        f"章节线索:{';'.join(card.section_hints) or '（无）'}\n"
        f"指引定位引句:{'；'.join(card.locator_quotes) or '（无）'}\n"
        f"目标/锚点引句:{card.anchor_quote or '（无）'}"
    )


def _cluster_scopes(scopes: Sequence[_CardScope]) -> list[list[_CardScope]]:
    """授权段落相交的卡归同一簇（union-find）；簇间窗口相互独立可并发。"""
    parent = list(range(len(scopes)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    first_owner: dict[str, int] = {}
    for i, scope in enumerate(scopes):
        for loc in scope.locations:
            if loc in first_owner:
                union(i, first_owner[loc])
            else:
                first_owner[loc] = i
    groups: dict[int, list[int]] = {}
    for i in range(len(scopes)):
        groups.setdefault(find(i), []).append(i)
    clusters = [[scopes[i] for i in idxs] for idxs in groups.values()]
    clusters.sort(key=lambda cl: min((_hit_sort_key(loc) for s in cl for loc in s.locations),
                                     default=(0, "")))
    return clusters


def _longest_common_substring(a: str, b: str) -> int:
    match = difflib.SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
    return match.size


def _attribution_ok(card: AtomicCard, quote: str) -> bool:
    """命中归属确定性校验：卡有强引句线索（≥8字）时，模型归属句须与某条线索实质重叠
    ——互含、最长公共子串≥8 或相似度≥0.45（拦截促销句→申购费卡这类错归属）。"""
    compact_q, _ = _compact_positions(quote)
    if len(compact_q) < 8:
        return True  # 命中句本身太短，跳过归属校验
    hints = ([card.anchor_quote] if card.anchor_quote else []) + list(card.locator_quotes)
    strong = False
    for hint in hints:
        compact_h, _ = _compact_positions(hint)
        if len(compact_h) < 8:
            continue
        strong = True
        if compact_q in compact_h or compact_h in compact_q:
            return True
        if _longest_common_substring(compact_q, compact_h) >= 8:
            return True
        if difflib.SequenceMatcher(None, compact_q, compact_h).ratio() >= 0.45:
            return True
    return not strong


def _collect_hits_multi(value: Mapping[str, Any], window: _Window,
                        cards: Sequence[AtomicCard], scope_by_card: Mapping[str, _CardScope],
                        span_by_loc: Mapping[str, ParagraphSpan], *,
                        stage: str, diagnostics: list[dict[str, Any]]) -> list[_Hit]:
    """共享窗口多卡命中过滤：未知 card_id / 窗口外 / 授权范围外 / 不可写 / 归属不符 / 引句不可回解一律丢弃。"""
    out: list[_Hit] = []
    known = {c.card_id: c for c in cards}
    window_locations = set(window.locations)
    for item in value.get("hits") or ():
        card_id = str(item.get("card_id") or "")
        card = known.get(card_id)
        loc = str(item.get("location") or "")
        quote = str(item.get("quote") or "")
        if card is None:
            diagnostics.append({"stage": stage, "location": loc, "window": window.window_id,
                                "code": "unknown_card_hit_dropped",
                                "note": "模型返回未列出的 card_id，已丢弃", "card_id": card_id})
            continue
        scope = scope_by_card.get(card_id)
        if scope is None or loc not in window_locations or loc not in scope.locations \
                or loc not in span_by_loc:
            if loc and (scope is None or loc not in scope.locations):
                diagnostics.append({"card_id": card_id, "stage": stage, "location": loc,
                                    "code": "out_of_scope_hit_dropped",
                                    "note": "模型返回未授权/越界段落，已丢弃"})
            continue
        span = span_by_loc[loc]
        if not span.editable:
            diagnostics.append({"card_id": card_id, "stage": stage, "location": loc,
                                "code": "uneditable_hit_dropped", "note": "段落不可写，已丢弃"})
            continue
        resolved = _resolve_quote(span.text, quote)
        if resolved is None:
            diagnostics.append({"card_id": card_id, "stage": stage, "location": loc,
                                "code": "quote_unresolved", "quote": quote[:80],
                                "note": "引句无法回解到段落坐标"})
            continue
        # 短锚强制共现（FL-D1080 附录）：卡锚 ≤9 字且有长引句时，须有长引句同段共现才算真锚
        anchor_compact = _compact_positions(card.anchor_quote)[0] if card.anchor_quote else ""
        if 0 < len(anchor_compact) < 10 and card.locator_quotes:
            span_compact = _compact_positions(span.text)[0]
            if not any(len(_compact_positions(q)[0]) >= 10
                       and _compact_positions(q)[0] in span_compact
                       for q in card.locator_quotes):
                diagnostics.append({"card_id": card_id, "stage": stage, "location": loc,
                                    "code": "short_anchor_unqualified", "quote": quote[:60],
                                    "note": "短锚且无长引句同段共现，拒锚（防误中）"})
                continue
        if not _attribution_ok(card, quote):
            diagnostics.append({"card_id": card_id, "stage": stage, "location": loc,
                                "code": "attribution_rejected", "quote": quote[:60],
                                "note": "命中归属与卡引句线索不符，拦截（防错卡改写）"})
            continue
        qs, qe = resolved
        if card.action == "insert_after":
            edit_range = (qe, qe)
        elif card.action == "insert_before":
            edit_range = (qs, qs)
        else:
            edit_range = (qs, qe)
        out.append(_Hit(card=card, location=loc, zone=span.zone, action=card.action,
                        quote=quote, quote_range=(qs, qe), edit_range=edit_range, stage=stage))
    return out


def _hit_sort_key(loc: str) -> tuple[int, str]:
    m = re.fullmatch(r"p(\d+)", loc)
    return (int(m.group(1)) if m else -1, loc)


def _loc_order_make(inspection: DocumentInspection):
    """文档顺序 positional 键（p 与表格胞段共存，窗口不依赖形状编号大小序）。"""
    pos = {p.location: i for i, p in enumerate(inspection.paragraphs)}
    return lambda loc: (pos.get(loc, 10 ** 9), loc)


def _group_hits(hits: Sequence[_Hit]) -> list[_Group]:
    by_loc: dict[str, list[_Hit]] = {}
    for h in hits:
        by_loc.setdefault(h.location, []).append(h)
    groups: list[_Group] = []
    for loc, items in by_loc.items():
        items = sorted(items, key=lambda h: (h.edit_range[0], h.edit_range[1]))
        cur = _Group(location=loc, start=items[0].edit_range[0], end=items[0].edit_range[1])
        for h in items:
            s, e = h.edit_range
            # 重叠或紧邻（含零宽插入落在区间端点）归入同组，防止互相覆盖
            if s <= cur.end:
                cur.end = max(cur.end, e)
                cur.members.append(h)
            else:
                groups.append(cur)
                cur = _Group(location=loc, start=s, end=e, members=[h])
        groups.append(cur)
    groups.sort(key=lambda g: (_hit_sort_key(g.location), g.start))
    return groups


_FABRIC_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?%?|[A-Za-z][A-Za-z0-9.\-]*")

# FOF/联接基金计提基数剥离形态（ca-corpus 优化令§6.1，S-048/联接 CA-NEW-2：
# E定义含“扣除…剩余部分（负数取0）”——改写/替换时必须保留剥离支，不得按普通费率句重写）。
_STRIPPED_BASE_RE = re.compile(r"扣除[^。；]{2,80}?剩余部分")

# FL-D1064 品种前置分流：销售费用新规族只适用常规公募份额制基金；
# 货币型/REIT 一刀切不适用——确定性标记 100% 精度才拦，不明默认放行+模型轻判一次。
_PRODUCT_HEAD_PARAGRAPHS = 80

# ---- 优化令② FL-DT-18(占位号)：确定性份额类别结构抽取（进定位前一次性） ----
_CLASS_DEF_RE = re.compile(r"称为\s*[「“\"]?([A-Z])\s*类基金份额")
_CLASS_LIST_RE = re.compile(r"分为\s*[「“\"]?([A-Z])\s*类[^。]{0,40}?和\s*([A-Z])\s*类")
_CLASS_TOKEN_ANY = re.compile(r"(?<![A-Za-z0-9])([A-Z])\s*类(?:\s*基金份额)?")
_CLASS_NAME_SCAN = 400  # 释义/基本情况区段前 400 段（覆盖含长释义的 FOF/联接）
_SUB_POS_RE = re.compile(r"(?<!不)收取[^。；]{0,10}(?:认购|申购)[^。；]{0,4}费")
_SUB_NEG_RE = re.compile(r"不收取[^。；]{0,10}(?:认购|申购)[^。；]{0,4}费")
_SVC_POS_RE = re.compile(r"(?<!不)计提销售服务费")
_SVC_NEG_RE = re.compile(r"不计提销售服务费")


def extract_share_classes(inspection: DocumentInspection) -> dict[str, dict[str, Any]]:
    """从释义/份额设置区段一次性抽 {类别名: {sub_fee(收认购/申购费), svc_fee(计提销售服务费)}}。

    - “称为X类基金份额”定义句的收费行为归并到该类；仅出现“分为A类…和C类”名单时
      类别存在但行为=未知（None）；
    - 纯确定性；抽取失败返回 {}，由调用方降级原路径（不影响主流程）。
    """
    facts: dict[str, dict[str, Any]] = {}
    head = [p for p in inspection.paragraphs[:_CLASS_NAME_SCAN]
            if p.zone in ("body", "summary")]
    text_span = [(p.location, p.text) for p in head]

    def window_around(location_idx: int, start: int) -> str:
        text = text_span[location_idx][1]
        stops = "。；！？"
        s = max((text.rfind(ch, 0, start) for ch in stops), default=-1) + 1
        ends = [text.find(ch, start) for ch in stops if text.find(ch, start) >= 0]
        return text[s: min(ends) if ends else len(text)]

    for idx, (_, text) in enumerate(text_span):
        for m in _CLASS_TOKEN_ANY.finditer(text):
            cls = m.group(1)
            body = window_around(idx, m.start())
            is_def = ("称为" in body) or ("分为" in body)
            sub_pos = bool(_SUB_POS_RE.search(body))
            sub_neg = bool(_SUB_NEG_RE.search(body))
            svc_pos = bool(_SVC_POS_RE.search(body))
            svc_neg = bool(_SVC_NEG_RE.search(body))
            # 登记条件：定义句，或窗口含明确收费行为标记（使用的费句也是事实）
            if not is_def and not (sub_pos or sub_neg or svc_pos or svc_neg):
                continue
            sub = True if sub_pos and not sub_neg else (False if sub_neg else None)
            svc = True if svc_pos and not svc_neg else (False if svc_neg else None)
            entry = facts.setdefault(cls, {"sub_fee": None, "svc_fee": None,
                                           "definition": body[:120]})
            if entry["sub_fee"] is None and sub is not None:
                entry["sub_fee"] = sub
            if entry["svc_fee"] is None and svc is not None:
                entry["svc_fee"] = svc
    return facts


def _share_class_block(facts: Mapping[str, Mapping[str, Any]]) -> str:
    if not facts:
        return ""
    parts = []
    for cls in sorted(facts):
        bits = facts[cls]
        beh = []
        if bits["sub_fee"] is True:
            beh.append("收认购/申购费")
        elif bits["sub_fee"] is False:
            beh.append("不收认购/申购费")
        if bits["svc_fee"] is True:
            beh.append("计提销售服务费")
        elif bits["svc_fee"] is False:
            beh.append("不计提销售服务费")
        parts.append(f"{cls}类" + ("（" + "、".join(beh) + "）" if beh else "（行为未明）"))
    return "[合同份额类别事实（确定性抽取，视为合同事实）] " + "；".join(parts)


_CLASS_TOKEN_GUARD = re.compile(r"(?<![A-Za-z0-9])([A-Z])类")


def _class_guard(new_text: str, facts: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """防编造/防错位（优化令②③）：抽取非空时，新文出现的类别必须存在且费行为
    不与抽取结论冲突；返回违规说明列表（空=通过）。"""
    violations: list[str] = []
    if not facts:
        return violations
    for cls in sorted(set(_CLASS_TOKEN_GUARD.findall(new_text))):
        if cls not in facts:
            violations.append(f"unknown_class:{cls}")
            continue
        bits = facts[cls]
        zone = re.search(re.escape(cls + "类") + r"[^。；]{0,24}计提销售服务费", new_text)
        if zone and bits["svc_fee"] is False:
            violations.append(f"svc_mismatch:{cls}")
        zone = re.search(re.escape(cls + "类") + r"[^。；]{0,24}(?:收取|收取.{0,4})(?:认购|申购)[^。；]{0,4}费",
                         new_text)
        if zone and bits["sub_fee"] is False:
            violations.append(f"sub_mismatch:{cls}")
    return violations
_PRODUCT_BLOCKERS: tuple[tuple[str, re.Pattern, str], ...] = (
    ("money_market", re.compile(r"投资于具有良好流动性的货币市场工具"), "money_market_objective"),
    ("money_market", re.compile(r"指[^。\n]{0,40}货币市场基金"), "money_market_name_definition"),
    ("money_market", re.compile(r"货币市场基金基金合同"), "money_market_title"),
    ("reit", re.compile(r"基础设施证券投资基金"), "reit_infrastructure"),
    ("reit", re.compile(r"不动产投资信托基金"), "reit_title"),
)
_FEEDER_RE = re.compile(r"联接基金|投资于目标ETF")
_FOF_RE = re.compile(r"基金中基金|FOF")

_PRODUCT_TYPE_SCHEMA = {
    "type": "object", "required": ["family", "not_applicable"], "additionalProperties": False,
    "properties": {"family": {"type": "string",
                              "enum": ["standard", "money_market", "reit", "fof", "feeder", "unknown"]},
                   "not_applicable": {"type": "boolean"}},
}
_PRODUCT_TYPE_INSTRUCTION = (
    "判断合同品种族（仅判型不判改）。family: standard=常规股票/混合/债券份额制基金；"
    "money_market=货币市场基金；reit=基础设施REIT；fof=基金中基金；feeder=ETF联接基金；"
    "unknown=无法判断。not_applicable：该合同是否**不属于**常规份额制基金"
    "（money_market/reit/明确非份额制）→ true。不确定就 family=unknown 且 not_applicable=false。"
    "只返回 JSON。"
)


def _detect_product_type(inspection: DocumentInspection,
                         gw: _GatewayWrap | None,
                         diagnostics: list[dict[str, Any]]) -> tuple[str, str, str]:
    """返回 (family, decided_by, evidence)。family: money_market/reit(拦) 或
    standard/feeder/fof/unknown(放行；feeder/fof 仅作标签与优化令1机制共存)。"""
    head = [p.text for p in inspection.paragraphs[:_PRODUCT_HEAD_PARAGRAPHS]]
    for family, pattern, evidence_tag in _PRODUCT_BLOCKERS:
        for text in head:
            if pattern.search(text):
                return family, "deterministic", f"{evidence_tag}:{text.strip()[:60]}"
    head_joined = "\n".join(head[:60])
    if _FOF_RE.search(head_joined):
        return "fof", "deterministic", "fof_marker"
    if _FEEDER_RE.search(head_joined):
        return "feeder", "deterministic", "feeder_marker"
    if gw is not None:
        try:
            result = gw.call_idempotent(
                task_type="direct_product_type", diagnostics=diagnostics,
                context=head_joined[:3000], schema=_PRODUCT_TYPE_SCHEMA,
                instruction=_PRODUCT_TYPE_INSTRUCTION,
                prompt_version="direct_product_type_v1")
            value = result.value if hasattr(result, "value") else result
            family = str(value.get("family") or "unknown")
            blocked = bool(value.get("not_applicable"))
            if blocked and family in ("money_market", "reit"):
                return family, "model", f"model_judgment:{family}"
            return ("standard" if family in ("standard", "unknown") else family), "model", \
                f"model_judgment:{family}"
        except Exception as exc:
            diagnostics.append({"stage": "product_type_gate",
                                "code": getattr(exc, "code", type(exc).__name__),
                                "note": "判型调用失败，按默认放行（不冒拦）"})
    return "standard", "none", "no_blocker_marker"


def stripped_base_present(text: str) -> bool:
    """类型判断：文本是否含计提基数剥离形态（E 定义“扣除……剩余部分”支）。"""
    return bool(_STRIPPED_BASE_RE.search(text))


def _preserves_stripped_base(original: str, new_text: str) -> bool:
    """原句含剥离形态时，新句必须仍含“扣除”与“剩余部分”双要件。"""
    if not stripped_base_present(original):
        return True
    return "扣除" in new_text and "剩余部分" in new_text


def _fabricated_tokens(new_text: str, allowed_text: str) -> list[str]:
    bad: list[str] = []
    for tok in _FABRIC_TOKEN_RE.findall(new_text):
        if tok and tok not in allowed_text:
            bad.append(tok)
    return bad


def propose_edits(contract_path: str | Path,
                  cards: Sequence[Mapping[str, Any] | AtomicCard],
                  *,
                  gateway: Any = None,
                  secondary_gateway: Any = None,
                  max_window_chars: int | None = None) -> EngineResult:
    """产物：定位与改写提案（不写 DOCX、不判完成）。抛 DirectEditError 仅限合同不可读/无可写内容。"""
    # 入口归一：既往修订并入定稿文本后再读（prepare_compare_input 形态；
    # 无修订=字节直通零行为变化，原始哈希仅在报告留痕）
    input_bytes = Path(contract_path).read_bytes()
    journal: Mapping[str, Any] = {"revisions_accepted": 0, "changed": False}
    read_path: Path | None = None
    try:
        prepared = prepare_compare_input(input_bytes)
        if prepared.data != input_bytes:
            journal = {"revisions_accepted": prepared.revisions_accepted,
                       "changed": True,
                       "original_sha256": prepared.original_sha256}
        input_data = prepared.data
    except DocxError as exc:
        if getattr(exc, "code", "") == "DOCUMENT_PROTECTED":
            # 受保护包的全包校验拒绝（含修订归一所作严检）——退回原 plain inspect，不冒称归一；
            # 该类文件在写回端同样不可能通过全包校验（受控边界，不失控）。
            journal = {"revisions_accepted": 0, "changed": False,
                       "fallback_reason": exc.code}
            input_data = input_bytes
        else:
            raise DirectEditError("CONTRACT_UNREADABLE", getattr(exc, "code", "")) from exc
    temp_staged = None
    if input_data != input_bytes:
        temp_staged = tempfile.NamedTemporaryFile(prefix="direct_edit_revision_base_",
                                                  suffix=".docx", delete=False)
        try:
            temp_staged.write(input_data)
            staged_path = temp_staged.name
        finally:
            temp_staged.close()
        read_path = Path(staged_path)
    else:
        read_path = Path(contract_path)
    try:
        inspection = inspect_docx(read_path)
    except DocxError as exc:
        raise DirectEditError("CONTRACT_UNREADABLE", getattr(exc, "code", "")) from exc
    finally:
        if temp_staged is not None:
            try:
                Path(temp_staged.name).unlink()
            except OSError:
                pass

    span_by_loc = {p.location: p for p in inspection.paragraphs}
    sections = _build_sections(inspection)
    if not sections:
        raise DirectEditError("CONTRACT_NO_EDITABLE_CONTENT")
    section_by_id = {s.section_id: s for s in sections}

    norm_cards: list[AtomicCard] = [
        c if isinstance(c, AtomicCard) else card_from_guide_card_v1(c) for c in cards
    ]
    norm_cards = [c for c in norm_cards if c.card_id and c.action in _ACTIONS]
    loc_order = _loc_order_make(inspection)

    if gateway is None:
        from .model import ModelGateway
        gateway = ModelGateway.from_env()
    gw = _GatewayWrap(gateway=gateway)
    try:
        concurrency = max(1, min(16, int(os.environ.get("FUNDLEX_DIRECT_CONCURRENCY", "4"))))
    except ValueError:
        concurrency = 4
    # 尊重模型账本并发闸：账本 budget.concurrency 为硬上限（生产=1）。
    # 引擎并发超过闸值只会互相挤掉产生整窗丢失（FL-D1048 对拍 v5/v6 实证）。
    budget = getattr(gateway, "budget", None)
    budget_concurrency = getattr(budget, "concurrency", None)
    if budget_concurrency:
        concurrency = max(1, min(concurrency, int(budget_concurrency)))

    diagnostics: list[dict[str, Any]] = []
    # 副模型池（双池提速；注入优先，否则按 env 克隆；失败回退单模型=不降级召回）
    secondary = (secondary_gateway if secondary_gateway is not None
                 else _build_secondary_gateway(gateway, diagnostics))
    if secondary is not None:
        gw.secondary = secondary
    scopes: list[_CardScope] = []

    # ---- FL-D1064 品种前置分流：货币型/REIT 一刀切不适用（全卡跳，非失败=明确边界） ----
    family, decided_by, evidence = _detect_product_type(inspection, gw, diagnostics)
    blocked = family in ("money_market", "reit")
    diagnostics.append({"stage": "product_type_gate", "code": "product_type_gate",
                        "family": family, "decided_by": decided_by,
                        "evidence": evidence, "blocked": blocked,
                        "note": "机械前置品种判定台账（不可人智绕过）"})
    if blocked:
        return EngineResult(
            source_sha256=inspection.source_sha256,
            engine_version=DIRECT_EDIT_VERSION,
            proposals=(), scope={"schema_version": SCOPE_SCHEMA_VERSION,
                                 "source_sha256": inspection.source_sha256,
                                 "entries": []},
            card_reports=(),
            diagnostics=tuple(diagnostics),
            stats={"model_calls": gw.calls, "model_failures": gw.failures,
                   "sections": len(sections), "cards": len(norm_cards),
                   "cards_scoped": 0, "proposals": 0,
                   "pools": gw.pool_count,
                   "model_calls_by_pool": dict(gw.calls_by_pool),
                   "secondary_model": os.environ.get("FUNDLEX_MODEL_SECONDARY") or None},
            not_applicable={"reason": "product_type_not_applicable",
                            "product_type": family, "decided_by": decided_by,
                            "evidence": evidence,
                            "affected_cards": [c.card_id for c in norm_cards]},
        )

    # ---- 优化令②：进定位前一次性确定性份额结构抽取（失败不影响主流程） ----
    share_facts: dict[str, dict[str, Any]] = {}
    if journal.get("fallback_reason"):
        diagnostics.append({"stage": "input_normalize", "code": "revision_base_protected_fallback",
                            "reason": journal["fallback_reason"],
                            "note": "受保护包无法全包校验归一，退回原 plain inspect（受控边界，不误称归一）"})
    if journal.get("changed"):
        diagnostics.append({"stage": "input_normalize", "code": "revision_base_accepted",
                            "original_sha256": journal["original_sha256"],
                            "revisions_accepted": journal["revisions_accepted"],
                            "note": "FL-D1115：既有修订并入定稿文本后作定位基准"})
    try:
        share_facts = extract_share_classes(inspection)
    except Exception as exc:
        diagnostics.append({"stage": "share_class_extract",
                            "code": getattr(exc, "code", type(exc).__name__),
                            "note": "份额结构抽取异常，降级原路径（不影响主流程）"})
        share_facts = {}
    if not share_facts:
        diagnostics.append({"stage": "share_class_extract", "code": "share_class_extract_empty",
                            "note": "未抽到份额类别定义，降级原路径（不影响主流程）"})
    share_fact_text = _share_class_block(share_facts)

    # ---- 阶段 0：章节绑定（含摘要逐小节；模型失效时章节线索回退；卡间并发） ----
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        scope_maps = list(pool.map(lambda c: _scope_map(c, sections, gw, diagnostics),
                                   norm_cards))
    for card, (body_ids, summary_ids) in zip(norm_cards, scope_maps):
        if not body_ids and not summary_ids:
            diagnostics.append({"card_id": card.card_id, "stage": "scope_map",
                                "code": "scope_unbound",
                                "note": "章节模型与线索均未绑定到章节，本卡无授权范围"})
            continue
        locations: set[str] = set()
        summary_locs: set[str] = set()
        body_titles: list[str] = []
        summary_titles: list[str] = []
        for sid in body_ids:
            s = section_by_id[sid]
            locations.update(s.locations)
            body_titles.append(s.title)
        for sid in summary_ids:
            s = section_by_id[sid]
            locations.update(s.locations)
            summary_locs.update(s.locations)
            summary_titles.append(s.title)
        scopes.append(_CardScope(
            card=card, scope_id=f"SC-{card.card_id}",
            body_titles=tuple(dict.fromkeys(body_titles)),
            summary_titles=tuple(dict.fromkeys(summary_titles)),
            locations=frozenset(locations), summary_locations=frozenset(summary_locs),
            bound_ids=tuple(dict.fromkeys([*body_ids, *summary_ids])),
        ))

    # ---- 阶段 0.5：分支卡族授权并集（互斥分支共享同一目标位置空间） ----
    families: dict[str, list[int]] = {}
    for i, scope in enumerate(scopes):
        key = _family_key(scope.card)
        if key:
            families.setdefault(key, []).append(i)
    # FL-D1054 防呆：疑似分支卡但兄弟分支不在本次卡集（上游丢支）→ 台账警示，不拒跑
    _BRANCH_MARKER = re.compile(r"仅有一个份额类别|多个份额类别|单一份额类别|浮动管理费")
    fam_of_card: dict[str, int] = {}
    for key, idxs in families.items():
        for i in idxs:
            fam_of_card[scopes[i].card.card_id] = len(idxs)
    for scope in scopes:
        if scope.card.applicability and _BRANCH_MARKER.search(scope.card.applicability) \
                and fam_of_card.get(scope.card.card_id, 0) < 2:
            diagnostics.append({"card_id": scope.card.card_id, "stage": "scope_map",
                                "code": "branch_sibling_missing", "level": "warning",
                                "note": "疑似互斥分支卡但兄弟分支不在本卡集，"
                                        "改写可能误选分支（生产应传全卡包）"})
    for key, idxs in families.items():
        if len(idxs) < 2:
            continue
        union_loc: set[str] = set().union(*(scopes[i].locations for i in idxs))
        union_summary: set[str] = set().union(*(scopes[i].summary_locations for i in idxs))
        union_body = list(dict.fromkeys(t for i in idxs for t in scopes[i].body_titles))
        union_stitles = list(dict.fromkeys(t for i in idxs for t in scopes[i].summary_titles))
        for i in idxs:
            scopes[i] = replace(
                scopes[i], locations=frozenset(union_loc),
                summary_locations=frozenset(union_summary),
                body_titles=tuple(union_body), summary_titles=tuple(union_stitles))
        diagnostics.append({"stage": "branch_family", "code": "branch_family_union",
                            "cards": [scopes[i].card.card_id for i in idxs],
                            "note": "同目标互斥分支卡授权并集，族内一卡命中即同组改写"})

    # ---- 阶段 1+2：章节簇共享窗口定位 + 一次补扫（范围过滤 #1/#2；FL-D1048 提速） ----
    # 同一批授权段落只切一次窗口（相邻窗 1 段重叠语义不变），共享窗口的多卡一次调用
    # 按 card_id 分列返回命中；窗口间按 FUNDLEX_DIRECT_CONCURRENCY(默认4) 并发。
    hits: list[_Hit] = []
    section_append_scopes = [s for s in scopes if s.card.section_append]
    for scope in section_append_scopes:
        _section_append_hits(scope, sections, span_by_loc, hits, diagnostics)

    window_scopes = [s for s in scopes if not s.card.section_append]
    clusters = _cluster_scopes(window_scopes)
    # 定位窗口预算：默认走 FUNDLEX_DIRECT_WINDOW_CHARS（试点默认 8000 保守中档；
    # 引文+卡事实+结构注入还占 ctx，安全边 = context_limit//3 同步裁剪）
    if max_window_chars is None:
        try:
            max_window_chars = max(800, int(os.environ.get("FUNDLEX_DIRECT_WINDOW_CHARS",
                                                           "8000")))
        except ValueError:
            max_window_chars = 8000
    win_char_budget = min(max_window_chars, max(800, gw.context_limit // 3))
    tasks: list[tuple[_Window, list[_CardScope], int]] = []
    for cluster in clusters:
        union_locations: list[str] = sorted(
            {loc for s in cluster for loc in s.locations}, key=loc_order)
        windows = _build_windows(union_locations, span_by_loc, win_char_budget)
        for window in windows:
            tasks.append((window, cluster, len(tasks)))

    scope_by_card_all = {s.card.card_id: s for s in scopes}

    # 施工令④：卡级早停资格（决策在 scope→locate 调度层）——
    # 稳定单锚（仅一张卡/仅 replace|delete/无多目标措辞/强引句线索唯一）才允许首窗命中即停。
    _EARLY_STOP_MULTI_RE = re.compile(
        r"所有|全部|每个|每处|任一|任意|二选一|描述[12]|多种|多处|多个|逐项|逐条")
    early_stop_cards: set[str] = set()
    for scope in scopes:
        c = scope.card
        if c.action not in ("replace", "delete"):
            continue
        if _EARLY_STOP_MULTI_RE.search(f"{c.title}\n{c.applicability}\n{c.requirement}"):
            continue
        strong_quotes = [q for q in ([c.anchor_quote] if c.anchor_quote else [])
                         + list(c.locator_quotes)
                         if len(_compact_positions(q)[0]) >= 8]
        if len(strong_quotes) != 1:
            continue
        early_stop_cards.add(c.card_id)
    done_cards: set[str] = set()
    card_windows_seen: dict[str, int] = {}

    def _window_task(window: _Window, cluster: list[_CardScope], ordinal: int) -> list[_Hit]:
        window_locs = set(window.locations)
        # 只列授权范围与本窗口相交的卡；卡数超过单批上限时拆成多次调用
        # （全集场景单次硬塞全量卡会稀释召回——FL-D1048 全集对拍实测后修复）
        batch_size = _locate_batch_size()
        cards = sorted((s.card for s in cluster if window_locs & s.locations),
                       key=lambda c: c.card_id)
        out: list[_Hit] = []
        for start in range(0, len(cards), batch_size):
            out.extend(_window_batch_round(window, cards[start:start + batch_size], ordinal))
        return out

    _TRUNC_CODES = {"MODEL_OUTPUT_TRUNCATED", "MODEL_SCHEMA_INVALID"}

    def _hits_call(task_type: str, context: str, window: _Window,
                   cards: list[AtomicCard], ordinal: int, stage: str,
                   current_listed: str = "（暂无）", initial_depth: int = 0) -> list[_Hit]:
        """600 薄层调用 + 截断保护：finish 非 stop/schema 缺 = 截断 → 同一窗一分为二
        小层重试 → 仍截断 → 单窗大层 1500 重试一次（真长引文）→ 仍败记诊断不误判无命中。"""
        def attempt(tokens: int) -> Any:
            return gw.call_idempotent(
                task_type=task_type, tokens=tokens,
                pool_index=(1 if task_type == "direct_sweep" and gw.secondary is not None
                            else None),
                diagnostics=diagnostics,
                context=context, schema=_HITS_SCHEMA,
                instruction=(_LOCATE_INSTRUCTION if stage == "locate" else _SWEEP_INSTRUCTION),
                prompt_version=(_PROMPT_VERSION_LOCATE if stage == "locate"
                                else _PROMPT_VERSION_SWEEP))

        def run_unit(unit_window: _Window, unit_cards: list[AtomicCard],
                     depth: int) -> list[_Hit]:
            try:
                result = attempt(gw.TOKEN_TIER_SMALL)
            except Exception as exc:
                if getattr(exc, "code", "") in _TRUNC_CODES:
                    if depth == 0 and len(unit_cards) > 1:
                        half = (len(unit_cards) + 1) // 2
                        return (run_unit(unit_window, unit_cards[:half], depth + 1)
                                + run_unit(unit_window, unit_cards[half:], depth + 1))
                    if depth == 0 and len(unit_window.locations) > 1:
                        mid = len(unit_window.locations) // 2
                        sub_a = _make_window(unit_window.window_id + "a",
                                             unit_window.locations[:mid], span_by_loc)
                        sub_b = _make_window(unit_window.window_id + "b",
                                             unit_window.locations[mid:], span_by_loc)
                        return (_unit_with_sub_context(sub_a, stage, cards,
                                                       current_listed, depth + 1)
                                + _unit_with_sub_context(sub_b, stage, cards,
                                                         current_listed, depth + 1))
                    try:
                        result = attempt(gw.TOKEN_TIER_BIG)
                    except Exception as exc2:
                        diagnostics.append({"stage": stage, "window": unit_window.window_id,
                                            "cards": [c.card_id for c in unit_cards],
                                            "code": "truncation_unresolved",
                                            "cause": getattr(exc2, "code", type(exc2).__name__),
                                            "note": "1500 大层仍截断，记诊断不误判为无命中"})
                        return []
                    return _collect_hits_multi(result.value, unit_window, unit_cards,
                                               scope_by_card_all, span_by_loc,
                                               stage=stage, diagnostics=diagnostics)
                raise
            return _collect_hits_multi(result.value, unit_window, unit_cards,
                                       scope_by_card_all, span_by_loc,
                                       stage=stage, diagnostics=diagnostics)

        return run_unit(window, cards, initial_depth)

    def _unit_with_sub_context(sub_window: _Window, stage: str,
                               cards: list[AtomicCard], listed: str, depth: int) -> list[_Hit]:
        sub_blocks = ((share_fact_text + "\n\n") if share_fact_text else "") + \
            "\n\n".join(_card_block(c) for c in cards)
        sub_context = (f"{sub_blocks}\n\n"
                       + (f"[已找到]\n{listed}\n\n" if stage != "locate" else "")
                       + f"[窗口 {sub_window.window_id}]\n{sub_window.text}")
        return _hits_call("direct_locate" if stage == "locate" else "direct_sweep",
                          sub_context, sub_window, cards, 0, stage,
                          current_listed=listed, initial_depth=depth)

    def _window_batch_round(window: _Window, cards: list[AtomicCard], ordinal: int) -> list[_Hit]:
        blocks = ((share_fact_text + "\n\n") if share_fact_text else "") + \
            "\n\n".join(_card_block(c) for c in cards)
        out: list[_Hit] = []
        found: dict[str, set[str]] = {}
        cards = [c for c in cards if c.card_id not in done_cards]
        if not cards:
            return out
        # 首窗判据：卡的「命中文窗序」——仅在第一个已扫窗口就完整命中才允许早停；
        # 首窗落空必须照常扫满全部窗口（召回优先于省调用）。
        first_scanned: set[str] = set()
        for c in cards:
            c_windows = card_windows_seen.get(c.card_id, 0)
            card_windows_seen[c.card_id] = c_windows + 1
            if c_windows == 0:
                first_scanned.add(c.card_id)
        try:
            new_hits = _hits_call("direct_locate",
                                  f"{blocks}\n\n[窗口 {window.window_id}]\n{window.text}",
                                  window, cards, ordinal, "locate")
        except Exception as exc:
            gw.failures += 1
            diagnostics.append({"stage": "locate", "window": window.window_id,
                                "cards": [c.card_id for c in cards],
                                "code": getattr(exc, "code", type(exc).__name__),
                                "note": "本窗口定位失败，其余窗口/卡继续"})
            return out
        for h in new_hits:
            out.append(h)
            found.setdefault(h.card.card_id, set()).add(h.quote)

        recent = {c.card_id: set(found.get(c.card_id, set())) for c in cards}

        def recent_lines_for_current() -> str:
            lines = [f"[{cid}] {q}" for cid in sorted(recent) for q in sorted(recent[cid])]
            return "\n".join(lines) or "（暂无）"

        listed = recent_lines_for_current()
        try:
            new_hits = _hits_call(
                "direct_sweep",
                (f"{blocks}\n\n[已找到]\n{listed}\n\n[窗口 {window.window_id}]\n{window.text}"),
                window, cards, ordinal, "sweep")
        except Exception as exc:
            gw.failures += 1
            diagnostics.append({"stage": "sweep", "window": window.window_id,
                                "cards": [c.card_id for c in cards],
                                "code": getattr(exc, "code", type(exc).__name__),
                                "note": "补扫失败，保留已有命中继续"})
            return out
        out.extend(new_hits)
        # 卡级早停（仅稳定单锚资格 + 首窗即完整命中）：打满 skip 后续窗口调度
        hit_here = {h.card.card_id for h in out}
        for cid in early_stop_cards:
            if cid in first_scanned and cid in hit_here:
                done_cards.add(cid)
        return out

    if tasks:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            for window_hits in pool.map(lambda t: _window_task(*t), tasks):
                hits.extend(window_hits)

    # ---- 阶段 1.5：节级绑定零命中→退章级重扫一次（硬校验：授权窗内丢标即回补） ----
    for i, scope in enumerate(list(scopes)):
        sub_ids = [sid for sid in scope.bound_ids
                   if sid in section_by_id and section_by_id[sid].level == 2]
        if not sub_ids or any(h.card is scope.card for h in hits):
            continue
        parents = {section_by_id[sid].parent_id for sid in sub_ids}
        extra: set[str] = set()
        for pid in parents:
            extra.update(section_by_id[pid].locations)
        extra -= set(scope.locations)
        if not extra:
            continue
        diagnostics.append({"card_id": scope.card.card_id, "stage": "scope_fallback",
                            "code": "section_fallback_to_chapter",
                            "note": "节级绑定零命中，退章级重扫一次（丢标风险回收）"})
        scopes[i] = replace(
            scope,
            locations=frozenset(set(scope.locations) | extra),
            body_titles=tuple(dict.fromkeys(
                [*scope.body_titles,
                 *[section_by_id[p].title for p in sorted(parents)]])))
        scope_by_card_all[scope.card.card_id] = scopes[i]
        for window in _build_windows(sorted(extra, key=loc_order),
                                     span_by_loc, win_char_budget):
            hits.extend(_window_batch_round(window, [scope.card], 0))

    # ---- 阶段 1.7：弱锚再确认副通道（②）——零命中卡的近似锚探针（每卡最多2窗一次）。
    # 候选放宽只放模型侧遴选；确认侧 _resolve_quote/_attribution_ok/_confirm_insert_anchor
    # 硬闸一个不降（②；mf 类 A 措辞失配的预期增援路径）。
    hit_card_ids = {h.card.card_id for h in hits}
    for scope in scopes:
        card = scope.card
        if card.section_append or card.card_id in hit_card_ids:
            continue
        own_windows = _build_windows(sorted(scope.locations, key=loc_order),
                                     span_by_loc, win_char_budget)
        if not own_windows:
            continue
        hints = [h for h in ([card.anchor_quote] if card.anchor_quote else [])
                 + list(card.locator_quotes)]
        scored: list[tuple[int, int]] = []
        for wi, window in enumerate(own_windows):
            compact_w = _compact_positions(window.text)[0]
            score = sum(1 for h in hints
                        for frag in (h[i:i + 8] for i in range(0, max(1, len(h) - 7), 6))
                        if len(frag) >= 6 and frag in compact_w)
            scored.append((score, wi))
        scored.sort(reverse=True)
        probe_windows = [own_windows[i] for score, i in scored[:2] if score > 0] \
            or own_windows[:1]
        block = _card_block(card)
        for window in probe_windows:
            try:
                result = gw.call_idempotent(
                    task_type="direct_locate",
                    context=f"[弱锚副通道]\n{block}\n\n[窗口 {window.window_id}]\n{window.text}",
                    schema=_HITS_SCHEMA, instruction=_WEAK_ANCHOR_INSTRUCTION,
                    prompt_version=_PROMPT_VERSION_WEAK,
                    diagnostics=diagnostics)
                value = result.value if hasattr(result, "value") else result
                new_hits = _collect_hits_multi(
                    value, window, [card], scope_by_card_all, span_by_loc,
                    stage="weak_anchor", diagnostics=diagnostics)
            except Exception as exc:
                gw.failures += 1
                diagnostics.append({"card_id": card.card_id, "stage": "weak_anchor",
                                    "window": window.window_id,
                                    "code": getattr(exc, "code", type(exc).__name__),
                                    "note": "弱锚副通道失败，按零命中继续主流程"})
                new_hits = []
            for h in new_hits:
                # ②：副通道又产生的 insert 类候选必须额外过锚点确认才放行（硬闸不降）
                if h.action in ("insert_before", "insert_after") and \
                        not _confirm_insert_anchor(h, span_by_loc, gw, diagnostics):
                    continue
                hits.append(h)
                diagnostics.append({"card_id": card.card_id, "stage": "weak_anchor",
                                    "location": h.location, "code": "weak_anchor_rescued",
                                    "note": "副通道近似锚补齐候选"})
                hit_card_ids.add(card.card_id)

    stats_pools = {"pools": gw.pool_count,
                   "model_calls_by_pool": dict(gw.calls_by_pool),
                   "secondary_model": os.environ.get("FUNDLEX_MODEL_SECONDARY") or None}

    # ---- 阶段 2.5：摘要同句复制检查（“该事项对应的摘要”的确定性兜底） ----
    # 模型已把某句定位为本卡目标 ⇒ 摘要区内逐字相同的副本即同一业务条款、同属授权范围；
    # 仅限 summary zone，绝不带入其他正文章节（不得全文漫游）。
    summary_spans = [p for p in inspection.paragraphs
                     if p.zone == "summary" and re.fullmatch(r"p\d+", p.location)]
    for index, scope in enumerate(list(scopes)):
        card_hits = [h for h in hits if h.card is scope.card]
        if not card_hits:
            continue
        hit_locs = {h.location for h in card_hits}
        add_locations: set[str] = set()
        add_titles: list[str] = []
        for h in card_hits:
            src_span = span_by_loc[h.location]
            sentence = src_span.text[h.quote_range[0]:h.quote_range[1]]
            compact_hit, _ = _compact_positions(sentence)
            if len(compact_hit) < 12:
                continue
            for sp in summary_spans:
                # 已绑定摘要段若主定位命中则跳过；主定位漏掉时照扫（摘要副本救援链，
                # 大窗口下主定位漏绑命中=副本机制兜住同句）
                if sp.location in hit_locs:
                    continue
                clean_p, _ = _strip_barriers(sp.text)
                compact_p, _ = _compact_positions(clean_p)
                if compact_hit not in compact_p:
                    continue
                resolved = _resolve_quote(sp.text, sentence)
                if resolved is None:
                    continue
                qs, qe = resolved
                if card.action == "insert_after":
                    edit_range = (qe, qe)
                elif card.action == "insert_before":
                    edit_range = (qs, qs)
                else:
                    edit_range = (qs, qe)
                hits.append(_Hit(card=scope.card, location=sp.location, zone="summary",
                                 action=card.action, quote=sentence,
                                 quote_range=(qs, qe), edit_range=edit_range,
                                 stage="summary_copy"))
                add_locations.add(sp.location)
                if sp.section_path and sp.section_path not in add_titles:
                    add_titles.append(sp.section_path)
                diagnostics.append({"card_id": scope.card.card_id, "stage": "summary_copy",
                                    "location": sp.location, "code": "summary_copy_found",
                                    "note": "摘要同句副本纳入对应摘要授权"})
        if add_locations:
            scopes[index] = replace(
                scope,
                locations=frozenset(set(scope.locations) | add_locations),
                summary_locations=frozenset(set(scope.summary_locations) | add_locations),
                summary_titles=tuple(dict.fromkeys([*scope.summary_titles, *add_titles])),
            )

    # ---- 阶段 2.8：insert 类补扫候选的主模型锚点确认（裁决②：零存疑插入硬门） ----
    # 仅 lint 补扫（sweep 阶段）来源的 insert 候选；replace/delete 补扫提案直接合并。
    kept: list[_Hit] = []
    for h in hits:
        if h.stage == "sweep" and h.action in ("insert_before", "insert_after"):
            if _confirm_insert_anchor(h, span_by_loc, gw, diagnostics):
                kept.append(h)
            continue
        kept.append(h)
    hits = kept

    # 窗口重叠/补扫去重（卡×段落×范围 唯一）
    dedup: dict[tuple[str, str, int, int, str], _Hit] = {}
    for h in hits:
        key = (h.card.card_id, h.location, h.edit_range[0], h.edit_range[1], h.action)
        dedup.setdefault(key, h)
    hits = sorted(dedup.values(), key=lambda h: (h.card.card_id, _hit_sort_key(h.location),
                                                 h.edit_range[0]))

    # ---- 阶段 3.5：分支共命中（族内一卡命中⇒其余分支卡并入同组，选支交给改写模型） ----
    card_by_id = {s.card.card_id: s.card for s in scopes}
    for fam_key, idxs in families.items():
        if len(idxs) < 2:
            continue
        fam_cards = [scopes[i].card for i in idxs]
        fam_ids = {c.card_id for c in fam_cards}
        for h in list(hits):
            if h.card.card_id not in fam_ids:
                continue
            for c in fam_cards:
                if c.card_id == h.card.card_id or c.action != h.action:
                    continue
                clone_key = (c.card_id, h.location, h.edit_range[0], h.edit_range[1], c.action)
                if clone_key in dedup or any(
                        x.card.card_id == c.card_id and x.location == h.location
                        and x.action == h.action for x in hits):
                    continue
                hits.append(_Hit(card=c, location=h.location, zone=h.zone, action=h.action,
                                 quote=h.quote, quote_range=h.quote_range,
                                 edit_range=h.edit_range, stage="branch_cohit"))
                diagnostics.append({"card_id": c.card_id, "stage": "branch_cohit",
                                    "location": h.location, "code": "branch_cohit_added",
                                    "note": "分支族共命中并入同组"})

    # ---- 阶段 3：分组合并（多卡同句合并且不互相覆盖；紧邻/重叠归组） ----
    groups = _group_hits(hits)

    # ---- 阶段 4：改写生成（范围过滤 #3/#4 在提案构建侧再次断言；组间并发） ----
    proposals: list[EditProposal] = []
    scope_by_card = {s.card.card_id: s for s in scopes}

    # 第一轮：定组形态与生成需求；delete 组不需要模型
    jobs: list[dict[str, Any]] = []
    for group in groups:
        replace_members = [m for m in group.members if m.action in ("replace", "delete")]
        insert_members = [m for m in group.members if m.action in ("insert_before", "insert_after")]
        if replace_members:
            all_delete = all(m.action == "delete" for m in replace_members)
            jobs.append({"group": group,
                         "action": "delete" if all_delete else "replace",
                         "edit_range": (group.start, group.end),
                         "lead": replace_members[0],
                         "anchor_hit": None,
                         "needs_generation": not all_delete})
        elif insert_members:
            anchor_hit = next((m for m in insert_members if m.action == "insert_before"),
                              insert_members[0])
            jobs.append({"group": group,
                         "action": "insert_before" if anchor_hit.action == "insert_before"
                         else "insert_after",
                         "edit_range": (group.start, group.start),
                         "lead": anchor_hit,
                         "anchor_hit": anchor_hit,
                         "needs_generation": True})

    generated: dict[int, str | None] = {}
    gen_jobs = [(i, j) for i, j in enumerate(jobs) if j["needs_generation"]]
    if gen_jobs:
        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
            texts = list(pool.map(lambda ij: _generate_replacement(
                ij[1]["group"], span_by_loc, gw, diagnostics,
                share_fact_block=share_fact_text, share_facts=share_facts), gen_jobs))
        for (i, _), text in zip(gen_jobs, texts):
            generated[i] = text

    for i, job in enumerate(jobs):
        new_text = generated.get(i, "") or ""
        if job["needs_generation"] and generated.get(i) is None:
            continue  # 诊断已记；该组跳过失，其他继续
        lead = job["lead"]
        group = job["group"]
        if _proposal_in_scope(group, scope_by_card, span_by_loc):
            proposal = _make_proposal(
                len(proposals) + 1, group, job["action"], job["edit_range"],
                new_text, lead, scope_by_card[lead.card.card_id], span_by_loc,
                source_sha256=inspection.source_sha256, anchor_hit=job["anchor_hit"])
            proposals.append(proposal)
            job["_proposal_id"] = proposal.proposal_id

    # ---- 阶段 5：提案级模型审查（FL-D1075，唯一一层；零领域词审查提示） ----
    proposals_before_review = len(proposals)
    card_by_id_all = {s.card.card_id: s.card for s in scopes}
    regenerate: dict[str, Any] = {}
    for i, job in enumerate(jobs):
        if job.get("_proposal_id"):
            pid = job["_proposal_id"]
            regenerate[pid] = lambda extra_warning, _j=job: _generate_replacement(
                _j["group"], span_by_loc, gw, diagnostics,
                share_fact_block=share_fact_text, share_facts=share_facts,
                extra_warning=extra_warning)
    proposals, exceptions = _review_proposals(
        proposals, card_by_id_all, span_by_loc, regenerate,
        share_fact_text, gw, diagnostics)
    scope_doc = _scope_document(inspection, scopes, proposals, span_by_loc, section_by_id)
    reports = _card_reports(scopes, hits, proposals, diagnostics)
    internal_diags = [d for d in diagnostics]
    return EngineResult(
        source_sha256=inspection.source_sha256,
        engine_version=DIRECT_EDIT_VERSION,
        proposals=tuple(proposals),
        scope=scope_doc,
        card_reports=tuple(reports),
        diagnostics=tuple(internal_diags),
        stats={"model_calls": gw.calls, "model_failures": gw.failures,
               "sections": len(sections), "cards": len(norm_cards),
               "cards_scoped": len(scopes), "proposals": len(proposals),
               "proposals_before_review": proposals_before_review,
               "review_vetoed": proposals_before_review - len(proposals),
               "exceptions_count": len(exceptions),
               "review_calls": sum(1 for d in diagnostics if d.get("stage") == "review"),
               "share_classes": share_facts,
               "revision_base": dict(journal),
               **stats_pools},
        exceptions=tuple(exceptions),
    )


def _generate_replacement(group: _Group, span_by_loc: Mapping[str, ParagraphSpan],
                          gw: _GatewayWrap, diagnostics: list[dict[str, Any]], *,
                          share_fact_block: str = "",
                          share_facts: Mapping[str, Mapping[str, Any]] | None = None,
                          extra_warning: str = "") -> str | None:
    """单组改写；失败有限重试。防编造硬约束（费率/份额类别不得无中生有）。"""
    span = span_by_loc[group.location]
    raw = span.text
    original = raw[group.start:group.end]
    cards = list({m.card.card_id: m.card for m in group.members}.values())
    req_lines = []
    for c in cards:
        insert_notes = [m for m in group.members
                        if m.card.card_id == c.card_id and m.action in ("insert_before", "insert_after")]
        req = c.requirement or "（删除该句）" if c.action == "delete" else c.requirement
        extra = ""
        if insert_notes and c.action != "replace":
            pos_desc = "前" if insert_notes[0].action == "insert_before" else "后"
            extra = f"（本组为在锚句之{pos_desc}插入；输出仅为待插入新句）"
        cond = f"[适用条件：{c.applicability}]" if c.applicability else ""
        req_lines.append(f"[{c.card_id}]{cond} {req}{extra}")
    requirements = "\n".join(req_lines)
    allowed = original + "\n" + "\n".join(c.recall_text for c in cards)

    def attempt(warning: str) -> str | None:
        base_note = ("[计提基数剥离] 原句含“扣除……剩余部分”计提基数剥离形态："
                     "新文必须原样保留该剥离支（扣除/剩余部分双要件），"
                     "不得把它当普通费率句重写剥掉。\n"
                     if stripped_base_present(original) else "")
        class_fact = share_fact_block or ""
        context = (
            (class_fact + "\n" if class_fact else "")
            + f"[组 group_id=G1 位置={group.location}]\n"
            f"[原文]\n{original if original else '（纯插入组，无原文；锚点句见下）'}\n"
            + (f"[锚点句]\n{raw[group.members[0].quote_range[0]:group.members[0].quote_range[1]]}\n"
               if not original else "")
            + f"[规则卡要求（多卡合并时须同时满足）]\n{requirements}\n{extra_warning}{base_note}{warning}"
        )
        result = gw.call_idempotent(task_type="direct_rewrite", context=context,
                                    schema=_REWRITE_SCHEMA, instruction=_REWRITE_INSTRUCTION,
                                    prompt_version=_PROMPT_VERSION_REWRITE)
        value = result.value if hasattr(result, "value") else result
        for edit in value.get("edits") or ():
            if str(edit.get("group_id")) == "G1":
                return str(edit.get("new_text") or "")
        return None

    warning = ""
    for retry in range(2):
        try:
            new_text = attempt(warning)
        except Exception as exc:
            gw.failures += 1
            if retry == 0 and getattr(exc, "code", "") == "MODEL_OUTPUT_TRUNCATED":
                continue  # 输出过长：单次缩短重来一次；单组无更小单元可拆
            diagnostics.append({"stage": "rewrite", "location": group.location,
                                "cards": [c.card_id for c in cards],
                                "code": getattr(exc, "code", type(exc).__name__),
                                "note": "该组生成失败，跳过本组继续其他"})
            return None
        if new_text is None:
            diagnostics.append({"stage": "rewrite", "location": group.location,
                                "cards": [c.card_id for c in cards], "code": "rewrite_empty",
                                "note": "模型未返回该组文本"})
            return None
        bad = _fabricated_tokens(new_text, allowed)
        if bad and retry == 0:
            warning = f"\n[纠偏] 上一次输出含既不在规则卡也不在原文的记号 {bad}，已被拒绝；请重生成。"
            continue
        if bad:
            diagnostics.append({"stage": "rewrite", "location": group.location,
                                "cards": [c.card_id for c in cards], "code": "fabricated_token",
                                "tokens": bad[:5], "note": "含未授权事实记号，该组已弃"})
            return None
        class_bad = _class_guard(new_text, share_facts or {})
        if class_bad:
            if retry == 0:
                warning = (f"\n[纠偏] 上一次输出的份额类别/费用行为与合同类别事实冲突 {class_bad}，"
                           "已被拒绝；请按[合同份额类别事实]重生成。")
                continue
            diagnostics.append({"stage": "rewrite", "location": group.location,
                                "cards": [c.card_id for c in cards],
                                "code": "class_guard_blocked", "violations": class_bad[:5],
                                "note": "类别名/费行为与抽取结构冲突，仅诊断不产提案（不退回原文）"})
            return None
        if not _preserves_stripped_base(original, new_text):
            if retry == 0:
                warning = ("\n[纠偏] 上一次输出丢掉了原句中的计提基数剥离支"
                           "（扣除……剩余部分），已被拒绝；请重生成并原样保留该剥离支。")
                continue
            diagnostics.append({"stage": "rewrite", "location": group.location,
                                "cards": [c.card_id for c in cards],
                                "code": "stripped_base_loss_blocked",
                                "note": "改写丢失计提基数剥离支，该组已拦（防实质改错费率基数）"})
            return None
        return new_text
    return None


def _proposal_in_scope(group: _Group, scope_by_card: Mapping[str, _CardScope],
                       span_by_loc: Mapping[str, ParagraphSpan]) -> bool:
    """提案构建前最终断言：组内每张卡的授权范围都必须包含该段落。"""
    for m in group.members:
        scope = scope_by_card.get(m.card.card_id)
        if scope is None or group.location not in scope.locations:
            return False
    return group.location in span_by_loc


def _make_proposal(index: int, group: _Group, action: str, edit_range: tuple[int, int],
                   new_text: str, lead: _Hit, scope: _CardScope,
                   span_by_loc: Mapping[str, ParagraphSpan], *, source_sha256: str,
                   anchor_hit: _Hit | None = None) -> EditProposal:
    span = span_by_loc[group.location]
    s, e = edit_range
    anchor = None
    if action in ("insert_before", "insert_after"):
        a = (anchor_hit or lead).quote_range
        anchor_text = span.text[a[0]:a[1]]
        anchor = {"start": a[0], "end": a[1], "text": anchor_text, "sha256": _sha_text(anchor_text)}
    merged = tuple(dict.fromkeys(m.card.card_id for m in group.members if m.card is not lead.card))
    return EditProposal(
        proposal_id=f"P-{index:04d}",
        rule_card_id=lead.card.card_id,
        scope_ref=scope.scope_id,
        action=action,
        location=group.location,
        zone=span.zone,
        start=s, end=e,
        expected_old_text=span.text[s:e] if action in ("replace", "delete") else "",
        replacement=new_text,
        anchor=anchor,
        fingerprint=span.fingerprint,
        source_sha256=source_sha256,
        merged_card_ids=merged,
        source_ref=lead.card.source_ref,
        section_title=span.section_path,
    )


def _summary_whitelist_entry(proposal: EditProposal,
                             span_by_loc: Mapping[str, ParagraphSpan]) -> dict[str, str]:
    """direct-writer-1 摘要白名单条目：location + 语义 anchor(≥6字,须为当前段子串)。"""
    anchor = proposal.expected_old_text
    if not anchor and proposal.anchor:
        anchor = str(proposal.anchor.get("text") or "")
    span = span_by_loc.get(proposal.location)
    if span is not None and len(_compact_positions(anchor)[0]) < 6:
        # 极短目标句退化为段首归一子串(仍在当前段内),保证写入器语义复核可执行。
        anchor = span.text[: max(12, len(anchor))] or span.text[:12]
    return {"location": proposal.location, "anchor": anchor}


def _scope_document(inspection: DocumentInspection, scopes: Sequence[_CardScope],
                    proposals: Sequence[EditProposal],
                    span_by_loc: Mapping[str, ParagraphSpan],
                    section_by_id: Mapping[str, Section]) -> dict[str, Any]:
    entries = []
    for scope in scopes:
        # 摘要授权只在“该事项对应”且实际产出摘要提案时给出；summary_sections 只列
        # 实际命中提案所在的小节——模型曾绑定但未命中的摘要不进入写回授权（FL-D1029）。
        summary_props = [p for p in proposals
                         if p.rule_card_id == scope.card.card_id and p.zone == "summary"]
        hit_summary_titles = list(dict.fromkeys(p.section_title for p in summary_props))
        entries.append({
            "scope_id": scope.scope_id,
            "rule_card_ids": [scope.card.card_id],
            "sections": list(scope.body_titles),
            "summary": bool(hit_summary_titles),
            "summary_sections": hit_summary_titles,
            # 摘要逐处白名单（integration-line6 d41339a/第3线契约形状）:每个命中摘要段
            # 携一句语义 anchor(原文子串),写入器独立重开时对当前段归一子串复核。
            "summary_locations": [_summary_whitelist_entry(p, span_by_loc)
                                  for p in summary_props],
            # 附加正文精确段白名单（additive；FL-D1064 节级绑定的越界防线——节级
            # 授权不写整个父章，按绑定条目逐段列出；写入器升级后可取交集）。
            "body_locations": sorted((loc for loc in scope.locations
                                      if span_by_loc[loc].zone == "body"),
                                     key=_hit_sort_key),
            # 附加绑定粒度（additive：chapter/subsection/mixed）
            "binding_granularity": (
                "subsection" if scope.bound_ids and
                all(section_by_id.get(sid) and section_by_id[sid].level == 2
                    for sid in scope.bound_ids) else
                ("mixed" if any(section_by_id.get(sid) and section_by_id[sid].level == 2
                                for sid in scope.bound_ids) else "chapter")),
        })
    return {
        "schema_version": SCOPE_SCHEMA_VERSION,
        "source_sha256": inspection.source_sha256,
        "entries": entries,
    }


def _card_reports(scopes: Sequence[_CardScope], hits: Sequence[_Hit],
                  proposals: Sequence[EditProposal],
                  diagnostics: Sequence[dict[str, Any]]) -> list[CardReport]:
    reports: list[CardReport] = []
    for scope in scopes:
        cid = scope.card.card_id
        prop_ids = tuple(p.proposal_id for p in proposals if p.rule_card_id == cid)
        card_diags = tuple(d for d in diagnostics
                           if d.get("card_id") == cid
                           or cid in (d.get("cards") or ()))
        reports.append(CardReport(
            card_id=cid,
            scope_id=scope.scope_id,
            body_sections=scope.body_titles,
            summary_sections=scope.summary_titles,
            authorized_locations=tuple(sorted(scope.locations, key=_hit_sort_key)),
            summary_authorized_locations=tuple(
                sorted({p.location for p in proposals
                        if p.rule_card_id == cid and p.zone == "summary"},
                       key=_hit_sort_key)),
            hits=sum(1 for h in hits if h.card.card_id == cid),
            proposal_ids=prop_ids,
            diagnostics=card_diags,
        ))
    return reports


__all__ = [
    "AtomicCard", "DirectEditError", "EditProposal", "EngineResult", "CardReport",
    "card_from_guide_card_v1", "propose_edits",
    "PROPOSAL_SCHEMA_VERSION", "SCOPE_SCHEMA_VERSION", "DIRECT_EDIT_VERSION",
]
